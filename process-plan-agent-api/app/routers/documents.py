"""
文件上传与参考资料管理 API
"""
import uuid
from io import BytesIO
from urllib.parse import quote
from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List

from app.core.paths import UPLOAD_DIR
from app.database import get_db
from app.models.models import Document, Reference, Project
from app.schemas.schemas import DocumentOut, DocumentPreviewOut, ReferenceCreate, ReferenceOut
from app.services.file_parser import extract_text

router = APIRouter(prefix="/api/documents", tags=["文件与资料管理"])
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)


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

    results = []
    for f in files:
        ext = f.filename.split(".")[-1].lower() if f.filename else "bin"
        safe_name = f"{uuid.uuid4().hex}.{ext}"
        path = UPLOAD_DIR / safe_name

        content = await f.read()
        with path.open("wb") as fp:
            fp.write(content)

        doc = Document(
            project_id=project_id,
            filename=safe_name,
            original_name=f.filename or "unknown",
            file_type=ext,
            file_size=len(content),
        )
        db.add(doc)
        await db.flush()
        results.append(doc)

    project.status = "UPLOADED"
    await db.commit()
    return results


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
    # 删除文件
    path = UPLOAD_DIR / doc.filename
    if path.exists():
        path.unlink()
    await db.delete(doc)
    remaining = (
        await db.execute(select(Document).where(Document.project_id == doc.project_id))
    ).scalars().all()
    if not remaining:
        project = (await db.execute(select(Project).where(Project.id == doc.project_id))).scalar_one_or_none()
        if project and project.status == "UPLOADED":
            project.status = "CREATED"
    await db.commit()
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
    ref = Reference(
        project_id=body.project_id,
        title=body.title,
        content=body.content,
        ref_type=body.ref_type,
        document_id=body.document_id,
    )
    db.add(ref)
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

    results = []
    for f in files:
        ext = f.filename.split(".")[-1].lower() if f.filename else "bin"
        safe_name = f"{uuid.uuid4().hex}.{ext}"
        path = UPLOAD_DIR / safe_name

        content = await f.read()
        with path.open("wb") as fp:
            fp.write(content)

        ref = Reference(
            project_id=project_id,
            title=f.filename or "unknown",
            ref_type="uploaded",
            filename=safe_name,
        )
        db.add(ref)
        await db.flush()
        results.append(ref)

    await db.commit()
    return results


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
    if ref.ref_type == "uploaded" and ref.filename:
        path = UPLOAD_DIR / ref.filename
        if path.exists():
            path.unlink()
    await db.delete(ref)
    await db.commit()
    return {"ok": True}
