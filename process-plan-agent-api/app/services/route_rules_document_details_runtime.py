"""
route_rules_runtime 的文档工序明细抽取与缓存复用逻辑。
"""

from __future__ import annotations

import os
from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.paths import UPLOAD_DIR
from app.models.models import Document, DocumentOperationDetail
from app.services.document_operation_details import extract_pdf_operation_details


async def extract_document_operation_details(
    db: AsyncSession,
    project_id: int,
    *,
    detail_row_normalized_names: Callable[[str], list[str]],
    normalize_operation_name: Callable[[str], str],
    docs: list[Document] | None = None,
) -> list[DocumentOperationDetail]:
    docs = docs or (
        await db.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
    ).scalars().all()

    saved_rows: list[DocumentOperationDetail] = []
    for doc in docs:
        filepath = os.path.join(UPLOAD_DIR, doc.filename)
        extracted_rows = []
        if (doc.file_type or "").lower() == "pdf" and os.path.exists(filepath):
            try:
                extracted_rows = extract_pdf_operation_details(filepath)
            except Exception:
                extracted_rows = []

        for item in extracted_rows:
            normalized_names = detail_row_normalized_names(item.normalized_name or item.operation_name)
            if not normalized_names:
                normalized_names = [normalize_operation_name(item.operation_name)]
            for normalized_name in normalized_names:
                row = DocumentOperationDetail(
                    project_id=project_id,
                    document_id=doc.id,
                    pdf_name=doc.original_name,
                    operation_seq=item.operation_seq,
                    operation_name=item.operation_name,
                    operation_content=item.operation_content,
                    page_no=item.page_no,
                    normalized_name=normalized_name,
                    is_composite=item.is_composite or len(normalized_names) > 1,
                    source_type=item.source_type,
                    equipment_types=item.equipment_types or "",
                    equipment_models=item.equipment_models or "",
                )
                db.add(row)
                saved_rows.append(row)

    await db.flush()
    return saved_rows


async def ensure_document_operation_details(
    db: AsyncSession,
    project_id: int,
    *,
    extract_document_operation_details_fn: Callable[..., Any],
    progress_callback: Callable[[str, int], None] | None = None,
) -> list[DocumentOperationDetail]:
    docs = (
        await db.execute(
            select(Document)
            .where(Document.project_id == project_id)
            .order_by(Document.created_at.asc(), Document.id.asc())
        )
    ).scalars().all()

    existing = (
        await db.execute(
            select(DocumentOperationDetail)
            .where(DocumentOperationDetail.project_id == project_id)
            .order_by(
                DocumentOperationDetail.operation_seq.asc(),
                DocumentOperationDetail.page_no.asc(),
                DocumentOperationDetail.id.asc(),
            )
        )
    ).scalars().all()
    existing_by_doc: dict[int, list[DocumentOperationDetail]] = defaultdict(list)
    for row in existing:
        if row.document_id is not None:
            existing_by_doc[int(row.document_id)].append(row)

    valid_pdf_docs: list[Document] = []
    valid_doc_ids: set[int] = set()
    for doc in docs:
        if (doc.file_type or "").lower() != "pdf":
            continue
        filepath = os.path.join(UPLOAD_DIR, doc.filename)
        if not os.path.exists(filepath):
            continue
        valid_pdf_docs.append(doc)
        valid_doc_ids.add(int(doc.id))

    modified = False
    reusable_rows: list[DocumentOperationDetail] = []
    missing_docs: list[Document] = []

    for row in existing:
        doc_id = int(row.document_id or 0)
        if doc_id <= 0 or doc_id not in valid_doc_ids:
            await db.delete(row)
            modified = True
            continue
        if row not in reusable_rows:
            reusable_rows.append(row)

    for doc in valid_pdf_docs:
        if existing_by_doc.get(int(doc.id)):
            continue
        missing_docs.append(doc)

    total_pdf_docs = len(valid_pdf_docs)
    reused_count = total_pdf_docs - len(missing_docs)
    if progress_callback:
        if total_pdf_docs and not missing_docs:
            progress_callback(f"正在复用已缓存工序明细（{reused_count}/{total_pdf_docs}）...", 35)
        elif total_pdf_docs:
            progress_callback(
                f"正在核对工序明细缓存（已复用 {reused_count}/{total_pdf_docs}）...",
                18 if reused_count else 14,
            )

    for index, doc in enumerate(missing_docs, start=1):
        if progress_callback:
            progress = 18 + int((index / max(len(missing_docs), 1)) * 16)
            progress_callback(
                f"正在解析工序明细（{index}/{len(missing_docs)}）: {doc.original_name or doc.filename}",
                progress,
            )
        extracted_rows = await extract_document_operation_details_fn(db, project_id, docs=[doc])
        reusable_rows.extend(extracted_rows)
        modified = True

    if modified:
        await db.commit()

    reusable_rows.sort(key=lambda row: (
        int(row.document_id or 0),
        int(row.operation_seq or 0),
        int(row.page_no or 0),
        int(row.id or 0),
    ))
    return reusable_rows


__all__ = [
    "ensure_document_operation_details",
    "extract_document_operation_details",
]
