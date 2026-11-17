"""
工艺规程文件管理 API
"""
from __future__ import annotations

import asyncio
import logging
import os
import uuid
from dataclasses import dataclass
from io import BytesIO
from pathlib import Path
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, func, select, text
from typing import List

from app.core.paths import UPLOAD_DIR
from app.database import get_db
from app.models.models import Document, DocumentOperationDetail, Project
from app.schemas.schemas import DocumentOut, DocumentPreviewOut
from app.services.file_parser import extract_text
from app.services.document_detail_cache_prewarm import (
    cancel_document_detail_cache_prewarm,
    start_document_detail_cache_prewarm,
)
from app.services.route_merge.workspace import (
    get_route_merge_project_lock,
    invalidate_project_document_derived_state,
)
from app.services.extraction_tasks import cancel_extraction_task, delete_extraction_task_state

router = APIRouter(prefix="/api/documents", tags=["文件与资料管理"])
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
logger = logging.getLogger(__name__)

PRIMARY_DOCUMENT_EXTENSIONS = frozenset({"pdf"})
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


def _upload_extension(filename: str, allowed_extensions=PRIMARY_DOCUMENT_EXTENSIONS) -> str:
    extension = Path(filename).suffix.lower().lstrip(".")
    if extension not in allowed_extensions:
        supported = ", ".join(sorted(allowed_extensions))
        raise HTTPException(415, f"不支持的文件类型，仅允许：{supported}")
    return extension


def _pdf_has_unreadable_image_body(page) -> bool:
    """Flag a dominant raster body supported only by incidental text.

    This is a scan warning heuristic, not OCR: a small logo is harmless, and
    an existing searchable scan needs meaningful lines across its body.
    """
    import fitz

    # Text/image coordinates are unrotated even when the displayed page rotates.
    bounds = page.rect * page.derotation_matrix
    body = fitz.Rect(bounds.x0 + bounds.width * 0.05, bounds.y0 + bounds.height * 0.10,
                     bounds.x1 - bounds.width * 0.05, bounds.y1 - bounds.height * 0.10)
    if body.is_empty:
        return False
    # Excluding image bytes avoids decoding large scans just to inspect text.
    text_blocks = page.get_text("dict", flags=0)["blocks"]
    for image in page.get_image_info():
        image_body = fitz.Rect(image["bbox"]) & body
        if image_body.get_area() < body.get_area() * 0.5:
            continue
        lines = []
        character_count = 0
        for block in text_blocks:
            for line in block.get("lines", []):
                text_value = "".join(span["text"] for span in line["spans"])
                meaningful_count = sum(character.isalnum() for character in text_value)
                line_bounds = fitz.Rect(line["bbox"])
                center = (line_bounds.tl + line_bounds.br) / 2
                if meaningful_count < 4 or center not in image_body:
                    continue
                lines.append(line_bounds)
                character_count += meaningful_count
        # Page numbers, headers and a single long watermark cannot establish
        # body readability. Require multiple meaningful, distributed lines.
        if character_count < 40 or len(lines) < 3:
            return True
        text_height = max(line.y1 for line in lines) - min(line.y0 for line in lines)
        if text_height < image_body.height * 0.2:
            return True
    return False


def _validate_upload_content(path: Path, extension: str, original_name: str) -> None:
    with path.open("rb") as handle:
        header = handle.read(8)

    if extension == "pdf":
        if not header.startswith(b"%PDF-"):
            raise HTTPException(415, "PDF 文件内容与扩展名不匹配")
        try:
            import fitz

            # The staged file intentionally uses a .part suffix, so provide
            # the content type explicitly instead of relying on its suffix.
            with fitz.open(stream=path.read_bytes(), filetype="pdf") as document:
                if document.is_encrypted:
                    raise HTTPException(422, f"文件 {original_name} 受密码保护，请解除密码后重新上传")
                if document.page_count < 1:
                    raise HTTPException(422, f"文件 {original_name} 没有可读取页面")

                unreadable_pages = []
                readable_text_found = False
                for page_number in range(document.page_count):
                    page = document.load_page(page_number)
                    page_text = page.get_text("text").strip()
                    if page_text:
                        readable_text_found = True
                        if _pdf_has_unreadable_image_body(page):
                            unreadable_pages.append(page_number + 1)
                    elif page.get_images(full=True):
                        unreadable_pages.append(page_number + 1)

                if unreadable_pages:
                    page_list = "、".join(str(number) for number in unreadable_pages)
                    raise HTTPException(
                        422,
                        f"文件 {original_name} 的第{page_list}页正文文字不足或不可提取，疑似扫描页；请先完成文字识别后重新上传",
                    )
                if not readable_text_found:
                    raise HTTPException(
                        422,
                        f"文件 {original_name} 未提取到可读取文字，请检查 PDF 内容或先完成文字识别",
                    )
        except HTTPException:
            raise
        except Exception as exc:
            raise HTTPException(
                422,
                f"文件 {original_name} 无法读取，请检查 PDF 是否损坏或重新导出",
            ) from exc
        return


def _cleanup_upload_paths(paths: list[Path]) -> None:
    for path in paths:
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Failed to clean uploaded file %s", path, exc_info=True)


async def _stage_upload(
    upload: UploadFile,
    remaining_batch_bytes: int,
    allowed_extensions=PRIMARY_DOCUMENT_EXTENSIONS,
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
        _validate_upload_content(staged_path, extension, original_name)
        os.replace(staged_path, final_path)
        return StagedUpload(original_name, extension, final_path, size)
    except BaseException:
        _cleanup_upload_paths([staged_path, final_path])
        raise
    finally:
        try:
            await upload.close()
        except BaseException:
            # Cancellation here happens after rename, before the caller owns it.
            _cleanup_upload_paths([staged_path, final_path])
            raise


async def _stage_uploads(
    files: List[UploadFile],
    allowed_extensions=PRIMARY_DOCUMENT_EXTENSIONS,
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
    except BaseException:
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
    staged = await _stage_uploads(files)
    results: list[Document] = []
    committed = False
    try:
        async with get_route_merge_project_lock(project_id):
            project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
            if not project:
                raise HTTPException(404, "任务不存在")

            # Include records inserted by older clients/importers after startup.
            await db.execute(text("""
                INSERT OR IGNORE INTO document_id_sequence (id)
                SELECT id FROM documents ORDER BY id DESC LIMIT 1
            """))
            for item in staged:
                document_id = (await db.execute(text(
                    "INSERT INTO document_id_sequence DEFAULT VALUES RETURNING id"
                ))).scalar_one()
                doc = Document(
                    id=int(document_id),
                    project_id=project_id,
                    filename=item.path.name,
                    original_name=item.original_name,
                    file_type=item.extension,
                    file_size=item.size,
                )
                db.add(doc)
                await db.flush()
                results.append(doc)

            cancel_document_detail_cache_prewarm(project_id)
            await invalidate_project_document_derived_state(
                db, project_id, document_ids=[int(doc.id) for doc in results],
            )
            cancel_extraction_task(project_id)
            await delete_extraction_task_state(db, project_id)
            project.status = "UPLOADED"
            commit_task = asyncio.create_task(db.commit())
            try:
                await asyncio.shield(commit_task)
            except asyncio.CancelledError:
                # A commit can succeed before its await returns. Keep the lock
                # and settle it before deciding whether staged PDFs can be removed.
                while not commit_task.done():
                    try:
                        await asyncio.shield(commit_task)
                    except asyncio.CancelledError:
                        continue
                    except Exception:
                        break
                committed = not commit_task.cancelled() and commit_task.exception() is None
                raise
            committed = True
    except BaseException:
        if not committed:
            try:
                await db.rollback()
            finally:
                _cleanup_upload_paths([item.path for item in staged])
        raise

    try:
        start_document_detail_cache_prewarm(project_id)
    except Exception:
        logger.warning("Could not start document detail cache prewarm for project %s", project_id, exc_info=True)
    return results


@router.get("/", response_model=List[DocumentOut])
async def list_documents(project_id: int = Query(...), db: AsyncSession = Depends(get_db)):
    """列出所有已上传文档"""
    result = await db.execute(
        select(Document).where(Document.project_id == project_id).order_by(Document.created_at.desc())
    )
    return result.scalars().all()


@router.delete("/{doc_id}")
async def delete_document(
    doc_id: int,
    db: AsyncSession = Depends(get_db),
    project_id: int | None = None,
    expected_filename: str | None = None,
):
    """删除文档"""
    result = await db.execute(select(Document).where(Document.id == doc_id))
    doc = result.scalar_one_or_none()
    if not doc:
        raise HTTPException(404, "文档不存在")
    if (
        project_id is None
        or not expected_filename
        or doc.project_id != project_id
        or doc.filename != expected_filename
    ):
        raise HTTPException(409, "文件列表已变化，请刷新后再删除。")
    path = UPLOAD_DIR / doc.filename
    project_id = int(doc.project_id or 0)
    try:
        if project_id > 0:
            async with get_route_merge_project_lock(project_id):
                cancel_document_detail_cache_prewarm(project_id)
                await invalidate_project_document_derived_state(db, project_id, document_ids=[doc_id])
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
                project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one_or_none()
                if project:
                    project.status = "UPLOADED" if remaining else "CREATED"
                cancel_extraction_task(project_id)
                await delete_extraction_task_state(db, project_id)
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

    file_type = (doc.file_type or "").lower()
    headers = {
        "Content-Disposition": _content_disposition(doc.original_name, "inline")
    }
    return FileResponse(path, media_type="application/pdf", headers=headers)


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
