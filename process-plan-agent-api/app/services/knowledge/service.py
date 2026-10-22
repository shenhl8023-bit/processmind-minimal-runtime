"""知识查询结果和证据快照的本地业务服务。"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import KnowledgeEvidenceSnapshot


def canonical_snapshot_hash(payload: dict[str, object]) -> str:
    canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def evidence_hash_payload(payload) -> dict[str, object]:
    return {
        "project_id": payload.project_id,
        "route_version_id": payload.route_version_id,
        "segment_id": payload.segment_id,
        "query": payload.query.strip(),
        "item_id": payload.item_id.strip(),
        "content": payload.content.strip(),
        "document_id": payload.document_id,
        "document_name": payload.document_name,
        "page_no": payload.page_no,
        "identity": payload.identity,
        "retrieval_method": payload.retrieval_method,
    }


async def save_evidence_snapshot(db: AsyncSession, payload):
    hash_payload = evidence_hash_payload(payload)
    snapshot_hash = canonical_snapshot_hash(hash_payload)
    existing = await db.scalar(
        select(KnowledgeEvidenceSnapshot).where(
            KnowledgeEvidenceSnapshot.snapshot_hash == snapshot_hash
        )
    )
    if existing:
        return existing

    row = KnowledgeEvidenceSnapshot(
        **hash_payload,
        snapshot_hash=snapshot_hash,
        retrieved_at=datetime.now(timezone.utc),
    )
    db.add(row)
    try:
        await db.commit()
    except Exception:
        await db.rollback()
        existing = await db.scalar(
            select(KnowledgeEvidenceSnapshot).where(
                KnowledgeEvidenceSnapshot.snapshot_hash == snapshot_hash
            )
        )
        if existing:
            return existing
        raise
    await db.refresh(row)
    return row


def _normalize_ids(values, *, numeric: bool) -> list:
    normalized = []
    for raw in values or []:
        try:
            value = int(raw) if numeric else str(raw).strip()
        except (TypeError, ValueError):
            continue
        if (value > 0 if numeric else bool(value)) and value not in normalized:
            normalized.append(value)
    return normalized
