"""Persistence and scope validation for enterprise-knowledge rule suggestions."""

from __future__ import annotations

import json

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    KnowledgeEvidenceSnapshot,
    KnowledgeRuleSuggestion,
    NormalizedRouteVersion,
    Project,
)


SUGGESTION_STATUSES = {"draft", "pending_review", "confirmed", "rejected", "stale"}
SUGGESTION_TRANSITIONS = {
    "draft": {"draft", "pending_review", "rejected"},
    "pending_review": {"pending_review", "confirmed", "rejected"},
    "confirmed": {"confirmed"},
    "rejected": {"rejected"},
    "stale": {"stale"},
}


def _required_text(value: str | None, field: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail=f"{field} 不能为空")
    return text


def _json_loads_object(raw: str | None):
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def _json_loads_ids(raw: str | None) -> list[int]:
    try:
        values = json.loads(raw or "[]")
    except (TypeError, ValueError):
        values = []
    if not isinstance(values, list):
        return []
    result: list[int] = []
    for value in values:
        try:
            value = int(value)
        except (TypeError, ValueError):
            continue
        if value > 0 and value not in result:
            result.append(value)
    return result


def _has_legacy_domain_context(row: KnowledgeRuleSuggestion) -> bool:
    try:
        domain_evidence = json.loads(row.domain_evidence_refs_json or "[]")
    except (TypeError, ValueError):
        domain_evidence = []
    return bool(
        _json_loads_object(row.domain_package_ref_json)
        or _json_loads_ids(row.sample_detail_ids_json)
        or (isinstance(domain_evidence, list) and domain_evidence)
    )


def serialize_suggestion(row: KnowledgeRuleSuggestion) -> dict[str, object]:
    return {
        "id": row.id,
        "project_id": row.project_id,
        "route_version_id": row.route_version_id,
        "segment_id": row.segment_id,
        "title": row.title,
        "suggestion_text": row.suggestion_text,
        "candidate": _json_loads_object(row.candidate_json),
        "evidence_ids": _json_loads_ids(row.evidence_ids_json),
        "status": row.status,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


async def _validate_context(
    db: AsyncSession,
    *,
    project_id: int,
    route_version_id: int,
    segment_id: str,
) -> None:
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    route = await db.scalar(
        select(NormalizedRouteVersion).where(
            NormalizedRouteVersion.id == route_version_id,
            NormalizedRouteVersion.project_id == project_id,
        )
    )
    if route is None:
        raise HTTPException(status_code=404, detail="路线版本不存在或不属于当前项目")
    if not segment_id.strip():
        raise HTTPException(status_code=422, detail="segment_id 不能为空")
    try:
        route_items = json.loads(route.route_json or "[]")
    except (TypeError, ValueError):
        route_items = []
    known_segment_ids = {
        str(item.get("id") or "").strip()
        for item in route_items
        if isinstance(item, dict) and str(item.get("id") or "").strip()
    } if isinstance(route_items, list) else set()
    if segment_id.strip() not in known_segment_ids:
        raise HTTPException(status_code=404, detail="当前工序不属于该保存路线版本")


async def _validate_evidence_ids(
    db: AsyncSession,
    *,
    evidence_ids: list[int] | None,
    project_id: int,
    route_version_id: int,
    segment_id: str,
) -> list[int]:
    if not isinstance(evidence_ids, list):
        raise HTTPException(status_code=422, detail="至少需要一条知识证据")
    normalized: list[int] = []
    for raw in evidence_ids:
        try:
            value = int(raw)
        except (TypeError, ValueError):
            continue
        if value <= 0:
            continue
        if value not in normalized:
            normalized.append(value)
    if not normalized:
        raise HTTPException(status_code=422, detail="至少需要一条知识证据")

    result = await db.execute(
        select(KnowledgeEvidenceSnapshot).where(
            KnowledgeEvidenceSnapshot.id.in_(normalized),
            KnowledgeEvidenceSnapshot.project_id == project_id,
            KnowledgeEvidenceSnapshot.route_version_id == route_version_id,
            KnowledgeEvidenceSnapshot.segment_id == segment_id,
        )
    )
    found = {row.id for row in result.scalars().all()}
    missing = [str(value) for value in normalized if value not in found]
    if missing:
        raise HTTPException(
            status_code=422,
            detail=f"知识证据不存在或不属于当前项目/路线/工序：{', '.join(missing)}",
        )
    return normalized


async def create_suggestion_draft(db: AsyncSession, payload) -> KnowledgeRuleSuggestion:
    title = _required_text(payload.title, "title")
    suggestion_text = _required_text(payload.suggestion_text, "suggestion_text")
    segment_id = payload.segment_id.strip()
    await _validate_context(
        db,
        project_id=payload.project_id,
        route_version_id=payload.route_version_id,
        segment_id=segment_id,
    )
    evidence_ids = await _validate_evidence_ids(
        db,
        evidence_ids=payload.evidence_ids,
        project_id=payload.project_id,
        route_version_id=payload.route_version_id,
        segment_id=segment_id,
    )
    row = KnowledgeRuleSuggestion(
        project_id=payload.project_id,
        route_version_id=payload.route_version_id,
        segment_id=segment_id,
        title=title,
        suggestion_text=suggestion_text,
        candidate_json=(json.dumps(payload.candidate, ensure_ascii=False) if payload.candidate is not None else None),
        evidence_ids_json=json.dumps(evidence_ids),
        status="draft",
        created_by=payload.created_by.strip() or "默认用户",
        updated_by=payload.created_by.strip() or "默认用户",
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def list_suggestions(
    db: AsyncSession,
    *,
    project_id: int,
    route_version_id: int | None = None,
    segment_id: str | None = None,
    status: str | None = None,
) -> list[KnowledgeRuleSuggestion]:
    query = select(KnowledgeRuleSuggestion).where(KnowledgeRuleSuggestion.project_id == project_id)
    if route_version_id is not None:
        query = query.where(KnowledgeRuleSuggestion.route_version_id == route_version_id)
    if segment_id:
        query = query.where(KnowledgeRuleSuggestion.segment_id == segment_id)
    if status:
        if status not in SUGGESTION_STATUSES:
            raise HTTPException(status_code=422, detail="无效的知识规则建议状态")
        query = query.where(KnowledgeRuleSuggestion.status == status)
    query = query.order_by(KnowledgeRuleSuggestion.updated_at.desc(), KnowledgeRuleSuggestion.id.desc())
    result = await db.execute(query)
    return [row for row in result.scalars().all() if not _has_legacy_domain_context(row)]


async def update_suggestion(db: AsyncSession, suggestion_id: int, payload) -> KnowledgeRuleSuggestion:
    row = await db.scalar(select(KnowledgeRuleSuggestion).where(KnowledgeRuleSuggestion.id == suggestion_id))
    if row is None:
        raise HTTPException(status_code=404, detail="知识规则建议不存在")
    if _has_legacy_domain_context(row):
        raise HTTPException(status_code=410, detail="该领域知识包建议已停用")
    fields = payload.model_fields_set
    mutable_fields = {"title", "suggestion_text", "candidate", "evidence_ids"}
    if row.status != "draft" and fields.intersection(mutable_fields):
        raise HTTPException(status_code=409, detail="只有草稿状态的规则建议可以编辑")
    if "status" in fields:
        if payload.status not in SUGGESTION_STATUSES:
            raise HTTPException(status_code=422, detail="无效的知识规则建议状态")
        if payload.status not in SUGGESTION_TRANSITIONS.get(row.status, set()):
            raise HTTPException(
                status_code=409,
                detail=f"规则建议不能从 {row.status} 变更为 {payload.status}",
            )
    if "title" in fields:
        row.title = _required_text(payload.title, "title")
    if "suggestion_text" in fields:
        row.suggestion_text = _required_text(payload.suggestion_text, "suggestion_text")
    if "candidate" in fields:
        row.candidate_json = (
            json.dumps(payload.candidate, ensure_ascii=False) if payload.candidate is not None else None
        )
    if "evidence_ids" in fields:
        evidence_ids = await _validate_evidence_ids(
            db,
            evidence_ids=payload.evidence_ids,
            project_id=row.project_id,
            route_version_id=row.route_version_id,
            segment_id=row.segment_id,
        )
        row.evidence_ids_json = json.dumps(evidence_ids)
    if "status" in fields:
        if payload.status in {"pending_review", "confirmed"}:
            await _validate_context(
                db,
                project_id=row.project_id,
                route_version_id=row.route_version_id,
                segment_id=row.segment_id,
            )
            _required_text(row.title, "title")
            _required_text(row.suggestion_text, "suggestion_text")
            await _validate_evidence_ids(
                db,
                evidence_ids=_json_loads_ids(row.evidence_ids_json),
                project_id=row.project_id,
                route_version_id=row.route_version_id,
                segment_id=row.segment_id,
            )
        row.status = payload.status
    row.updated_by = payload.updated_by.strip() or "默认用户"
    await db.commit()
    await db.refresh(row)
    return row


async def validate_suggestion_for_condition_draft(
    db: AsyncSession,
    *,
    suggestion_id: int,
    project_id: int,
    route_id: int,
    segment_id: str,
    source_text: str,
) -> None:
    """Allow reviewed knowledge text into the existing draft/parse flow only."""
    row = await db.scalar(select(KnowledgeRuleSuggestion).where(KnowledgeRuleSuggestion.id == suggestion_id))
    if row is None:
        raise HTTPException(status_code=404, detail="知识规则建议不存在")
    if _has_legacy_domain_context(row):
        raise HTTPException(status_code=410, detail="该领域知识包建议已停用")
    if row.status != "confirmed":
        raise HTTPException(status_code=409, detail="只有已确认的知识规则建议可以带入条件草稿")
    if (row.project_id, row.route_version_id, row.segment_id) != (project_id, route_id, segment_id):
        raise HTTPException(status_code=409, detail="知识规则建议不属于当前项目/路线/工序")
    reviewed_text = _required_text(row.suggestion_text, "suggestion_text")
    if source_text.strip() != reviewed_text:
        raise HTTPException(status_code=409, detail="条件文字与已审核的知识规则建议不一致")
    await _validate_context(
        db, project_id=project_id, route_version_id=route_id, segment_id=segment_id,
    )
    await _validate_evidence_ids(
        db,
        evidence_ids=_json_loads_ids(row.evidence_ids_json),
        project_id=project_id,
        route_version_id=route_id,
        segment_id=segment_id,
    )
