"""
文件上传与参考资料管理 API
"""
import json
import logging
import os
import uuid
import zipfile
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, select, update
from typing import List

from app.core.paths import UPLOAD_DIR
from app.database import get_db
from app.models.models import Document, DocumentOperationDetail, Reference, Project
from app.schemas.schemas import DocumentOut, DocumentPreviewOut, ReferenceCreate, ReferenceOut
from app.services.file_parser import extract_text
from app.services.document_detail_cache_prewarm import (
    cancel_document_detail_cache_prewarm,
    start_document_detail_cache_prewarm,
)
from app.services.route_merge.workspace import (
    get_route_merge_project_lock,
    invalidate_project_document_derived_state,
)
from app.services.rule_packages.lifecycle import supersede_published_rule_packages

router = APIRouter(prefix="/api/documents", tags=["文件与资料管理"])
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

ALLOWED_UPLOAD_EXTENSIONS = frozenset({"pdf", "doc", "docx", "xls", "xlsx", "json"})
REFERENCE_UPLOAD_EXTENSIONS = frozenset({*ALLOWED_UPLOAD_EXTENSIONS, "txt", "md"})
UPLOAD_CHUNK_BYTES = 1024 * 1024


def _positive_env_int(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError:
        return default
    return value if value > 0 else default


MAX_UPLOAD_FILES = _positive_env_int("PROCESSMIND_MAX_UPLOAD_FILES", 20)
MAX_UPLOAD_FILE_BYTES = _positive_env_int("PROCESSMIND_MAX_UPLOAD_FILE_BYTES", 50 * 1024 * 1024)
MAX_UPLOAD_BATCH_BYTES = _positive_env_int("PROCESSMIND_MAX_UPLOAD_BATCH_BYTES", 200 * 1024 * 1024)


@dataclass(frozen=True)
class StagedUpload:
    original_name: str
    extension: str
    path: Path
    size: int


def _safe_original_name(filename: str | None) -> str:
    normalized = str(filename or "").replace("\\", "/").split("/")[-1]
    normalized = normalized.replace("\r", "_").replace("\n", "_").replace("\x00", "").strip()
    if not normalized:
        raise HTTPException(400, "文件名不能为空")
    if len(normalized) > 255:
        raise HTTPException(400, "文件名不能超过 255 个字符")
    return normalized


def _upload_extension(filename: str, allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in allowed_extensions:
        supported = ", ".join(sorted(allowed_extensions))
        raise HTTPException(415, f"不支持的文件类型，仅允许：{supported}")
    return extension


def _validate_upload_content(path: Path, extension: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(8)

    if extension == "pdf":
        if not header.startswith(b"%PDF-"):
            raise HTTPException(415, "PDF 文件内容与扩展名不匹配")
        return

    if extension in {"doc", "xls"}:
        if header != bytes.fromhex("D0CF11E0A1B11AE1"):
            raise HTTPException(415, f"{extension.upper()} 文件内容与扩展名不匹配")
        return

    if extension in {"docx", "xlsx"}:
        try:
            with zipfile.ZipFile(path) as archive:
                entries = archive.infolist()
                names = {entry.filename for entry in entries}
                total_uncompressed = sum(entry.file_size for entry in entries)
                total_compressed = sum(entry.compress_size for entry in entries)
        except (OSError, zipfile.BadZipFile) as exc:
            raise HTTPException(415, f"{extension.upper()} 文件不是有效的 Office 文档") from exc
        if total_uncompressed > 300 * 1024 * 1024:
            raise HTTPException(413, "Office 文件解压后不能超过 300 MB")
        if total_compressed and total_uncompressed / total_compressed > 100:
            raise HTTPException(422, "Office 文件压缩比异常，无法处理")
        expected_prefix = "word/" if extension == "docx" else "xl/"
        if "[Content_Types].xml" not in names or not any(name.startswith(expected_prefix) for name in names):
            raise HTTPException(415, f"{extension.upper()} 文件内容与扩展名不匹配")
        return

    if extension == "json":
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                json.load(handle)
        except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise HTTPException(415, "JSON 文件内容无效") from exc


def _cleanup_upload_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to clean uploaded file %s", path, exc_info=True)


async def _invalidate_reference_rule_assets(db: AsyncSession, project_id: int | None) -> None:
    normalized_project_id = int(project_id or 0)
    if normalized_project_id <= 0:
        return
    await supersede_published_rule_packages(normalized_project_id, db)
    project = (
        await db.execute(select(Project).where(Project.id == normalized_project_id))
    ).scalar_one_or_none()
    if project:
        has_documents = bool(
            (
                await db.execute(
                    select(Document.id).where(Document.project_id == normalized_project_id).limit(1)
                )
            ).first()
        )
        project.status = "UPLOADED" if has_documents else "CREATED"


async def _stage_upload(
    upload: UploadFile,
    remaining_batch_bytes: int,
    allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS,
) -> StagedUpload:
    original_name = _safe_original_name(upload.filename)
    extension = _upload_extension(original_name, allowed_extensions)
    token = uuid.uuid4().hex
    staged_path = UPLOAD_DIR / f".{token}.part"
    final_path = UPLOAD_DIR / f"{token}.{extension}"
    size = 0
    try:
        with staged_path.open("xb") as output:
            while True:
                chunk = await upload.read(UPLOAD_CHUNK_BYTES)
                if not chunk:
                    break
                size += len(chunk)
                if size > MAX_UPLOAD_FILE_BYTES:
                    raise HTTPException(413, f"文件 {original_name} 超过单文件大小限制")
                if size > remaining_batch_bytes:
                    raise HTTPException(413, "本次上传总大小超过限制")
                output.write(chunk)
            output.flush()
            os.fsync(output.fileno())
        if size == 0:
            raise HTTPException(400, f"文件 {original_name} 不能为空")
        _validate_upload_content(staged_path, extension)
        os.replace(staged_path, final_path)
        return StagedUpload(original_name, extension, final_path, size)
    except Exception:
        _cleanup_upload_paths([staged_path, final_path])
        raise
    finally:
        await upload.close()


async def _stage_uploads(
    files: List[UploadFile],
    allowed_extensions=ALLOWED_UPLOAD_EXTENSIONS,
) -> list[StagedUpload]:
    if not files:
        raise HTTPException(400, "至少选择一个文件")
    if len(files) > MAX_UPLOAD_FILES:
        for upload in files:
            await upload.close()
        raise HTTPException(413, f"单次最多上传 {MAX_UPLOAD_FILES} 个文件")

    staged: list[StagedUpload] = []
    total_size = 0
    try:
        for upload in files:
            item = await _stage_upload(
                upload,
                MAX_UPLOAD_BATCH_BYTES - total_size,
                allowed_extensions,
            )
            staged.append(item)
            total_size += item.size
        return staged
    except Exception:
        _cleanup_upload_paths([item.path for item in staged])
        for upload in files:
            await upload.close()
        raise


def _content_disposition(filename: str, disposition: str) -> str:
    safe_name = (filename or "document").replace("\\", "_").replace('"', "_")
    ascii_fallback = safe_name.encode("ascii", "ignore").decode("ascii").strip() or "document"
    encoded_name = quote(safe_name)
    return f"{disposition}; filename=\"{ascii_fallback}\"; filename*=UTF-8''{encoded_name}"


@router.post("/upload", response_model=List[DocumentOut])
async def upload_documents(
    files: List[UploadFile] = File(...),
    project_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """批量上传典型工艺规程文件"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")

    staged = await _stage_uploads(files)
    results: list[Document] = []
    try:
        for item in staged:
            doc = Document(
                project_id=project_id,
                filename=item.path.name,
                original_name=item.original_name,
                file_type=item.extension,
                file_size=item.size,
            )
            db.add(doc)
            await db.flush()
            results.append(doc)

        async with get_route_merge_project_lock(project_id):
            cancel_document_detail_cache_prewarm(project_id)
            await invalidate_project_document_derived_state(db, project_id)
            project.status = "UPLOADED"
            await db.commit()
        start_document_detail_cache_prewarm(project_id)
        return results
    except Exception:
        await db.rollback()
        _cleanup_upload_paths([item.path for item in staged])
        raise


@router.get("/", response_model=List[DocumentOut])
async def list_documents(project_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """列出所有已上传文档"""
    result = await db.execute(
        select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{doc_id}")
async def delete_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """删除文档"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    path = UPLOAD_DIR / doc.filename
    project_id = int(doc.project_id or 0)
    try:
        if project_id > 0:
            async with get_route_merge_project_lock(project_id):
                cancel_document_detail_cache_prewarm(project_id)
                await invalidate_project_document_derived_state(db, project_id)
                await db.execute(
                    update(Reference)
                    .where(Reference.document_id == doc_id)
                    .values(document_id=None)
                )
                await db.execute(
                    delete(DocumentOperationDetail).where(
                        DocumentOperationDetail.document_id == doc_id
                    )
                )
                await db.delete(doc)
                remaining = (
                    await db.execute(
                        select(func.count(Document.id)).where(
                            Document.project_id == project_id,
                            Document.id != doc_id,
                        )
                    )
                ).scalar_one()
                if not remaining:
                    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
                    if project and project.status == "UPLOADED":
                        project.status = "CREATED"
                await db.commit()
        else:
            await db.delete(doc)
            await db.commit()
    except Exception:
        await db.rollback()
        raise

    try:
        path.unlink(missing_ok=True)
    except OSError:
        logger.warning("Deleted document row but could not remove file %s", path, exc_info=True)
    return {"ok": True}


@router.get("/{doc_id}/preview", response_model=DocumentPreviewOut)
async def preview_document(doc_id: int, db: AsyncSession = Depends(get_db)):
    """读取文档预览文本，供前端快速浏览内容。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")

    path = UPLOAD_DIR / doc.filename
    if not path.exists():
        raise HTTPException(404, "文档文件不存在")

    preview_text = extract_text(str(path), doc.file_type or None, max_chars=24000)
    return DocumentPreviewOut(
        id=doc.id,
        original_name=doc.original_name,
        file_type=doc.file_type,
        preview_text=preview_text,
    )


@router.get("/{doc_id}/file")
async def view_document_file(doc_id: int, db: AsyncSession = Depends(get_db)):
    """返回原始上传文件，便于浏览器直接打开。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")

    path = UPLOAD_DIR / doc.filename
    if not path.exists():
        raise HTTPException(404, "文档文件不存在")

    media_type_map = {
        "pdf": "application/pdf",
        "doc": "application/msword",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "xls": "application/vnd.ms-excel",
        "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        "json": "application/json",
        "txt": "text/plain; charset=utf-8",
    }
    file_type = (doc.file_type or "").lower()
    media_type = media_type_map.get(file_type, "application/octet-stream")
    disposition = "inline" if file_type == "pdf" else "attachment"
    headers = {
        "Content-Disposition": _content_disposition(doc.original_name, disposition)
    }
    return FileResponse(path, media_type=media_type, headers=headers)


@router.get("/{doc_id}/pdf-pages")
async def get_pdf_page_count(doc_id: int, db: AsyncSession = Depends(get_db)):
    """返回 PDF 页数，前端据此按页加载图片预览。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    if (doc.file_type or "").lower() != "pdf":
        raise HTTPException(400, "当前文档不是 PDF")

    path = UPLOAD_DIR / doc.filename
    if not path.exists():
        raise HTTPException(404, "文档文件不存在")

    try:
        import fitz

        with fitz.open(path) as pdf:
            return {"page_count": pdf.page_count}
    except Exception as exc:
        raise HTTPException(400, f"PDF 页数读取失败：{exc}")


@router.get("/{doc_id}/pdf-pages/{page_no}")
async def render_pdf_page(
    doc_id: int,
    page_no: int,
    zoom: float = Query(1.6, ge=0.5, le=3.0),
    db: AsyncSession = Depends(get_db),
):
    """把 PDF 单页渲染为 PNG，避免依赖浏览器内置 PDF 预览器。"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    if (doc.file_type or "").lower() != "pdf":
        raise HTTPException(400, "当前文档不是 PDF")

    path = UPLOAD_DIR / doc.filename
    if not path.exists():
        raise HTTPException(404, "文档文件不存在")

    try:
        import fitz

        with fitz.open(path) as pdf:
            if page_no < 1 or page_no > pdf.page_count:
                raise HTTPException(404, "PDF 页码不存在")
            page = pdf.load_page(page_no - 1)
            matrix = fitz.Matrix(zoom, zoom)
            pixmap = page.get_pixmap(matrix=matrix, alpha=False)
            image = BytesIO(pixmap.tobytes("png"))
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(400, f"PDF 页面渲染失败：{exc}")

    headers = {"Cache-Control": "private, max-age=300"}
    return StreamingResponse(image, media_type="image/png", headers=headers)


# ---------- 参考资料 ----------

@router.post("/references", response_model=ReferenceOut)
async def create_reference(
    body: ReferenceCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建手写参考资料"""
    if body.ref_type != "written":
        raise HTTPException(422, "手写参考资料的 ref_type 必须为 written")
    project_id = body.project_id
    if project_id is not None:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "任务不存在")

    document_id = body.document_id
    if document_id is not None:
        document = (await db.execute(select(Document).where(Document.id == document_id))).scalar_one_or_none()
        if not document:
            raise HTTPException(404, "关联文档不存在")
        if project_id is not None and document.project_id != project_id:
            raise HTTPException(400, "关联文档不属于当前任务")
        project_id = document.project_id

    ref = Reference(
        project_id=project_id,
        title=body.title,
        content=body.content,
        ref_type=body.ref_type,
        document_id=document_id,
    )
    db.add(ref)
    await db.flush()
    await _invalidate_reference_rule_assets(db, project_id)
    await db.commit()
    await db.refresh(ref)
    return ref


@router.post("/references/upload", response_model=List[ReferenceOut])
async def upload_references(
    files: List[UploadFile] = File(...),
    project_id: int = Form(...),
    db: AsyncSession = Depends(get_db)
):
    """批量上传参考资料文件"""
    project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
    if not project:
        raise HTTPException(404, "任务不存在")

    staged = await _stage_uploads(files, REFERENCE_UPLOAD_EXTENSIONS)
    results: list[Reference] = []
    try:
        for item in staged:
            ref = Reference(
                project_id=project_id,
                title=item.original_name,
                ref_type="uploaded",
                filename=item.path.name,
            )
            db.add(ref)
            await db.flush()
            results.append(ref)
        await _invalidate_reference_rule_assets(db, project_id)
        await db.commit()
        return results
    except Exception:
        await db.rollback()
        _cleanup_upload_paths([item.path for item in staged])
        raise


@router.get("/references", response_model=List[ReferenceOut])
async def list_references(project_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """列出所有参考资料"""
    result = await db.execute(
        select(Reference).where(Reference.project_id == project_id).order_by(Reference.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/references/{ref_id}")
async def delete_reference(ref_id: int, db: AsyncSession = Depends(get_db)):
    """删除参考资料"""
    result = await db.execute(select(Reference).where(Reference.id == ref_id))
    ref = result.scalar_one_or_none()
    if not ref:
        raise HTTPException(404, "参考资料不存在")
    project_id = int(ref.project_id or 0)
    path = UPLOAD_DIR / ref.filename if ref.ref_type == "uploaded" and ref.filename else None
    await db.delete(ref)
    await _invalidate_reference_rule_assets(db, project_id)
    await db.commit()
    if path is not None:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Deleted reference row but could not remove file %s", path, exc_info=True)
    return {"ok": True}
