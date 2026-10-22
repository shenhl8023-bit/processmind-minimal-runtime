"""企业工艺知识库查询和证据快照接口。"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.models.models import KnowledgeEvidenceSnapshot, Project
from app.schemas.schemas import (
    KnowledgeEvidenceCreate,
    KnowledgeEvidenceOut,
    KnowledgeSearchItemOut,
    KnowledgeSearchRequest,
    KnowledgeSearchResponse,
    KnowledgeRuleSuggestionDraft,
    KnowledgeRuleSuggestionOut,
    KnowledgeRuleSuggestionUpdate,
)
from app.services.knowledge.service import (
    save_evidence_snapshot,
)
from app.services.knowledge.local_search import search_local_knowledge
from app.services.knowledge.answer import generate_local_knowledge_answer
from app.services.knowledge.suggestions import (
    create_suggestion_draft,
    list_suggestions,
    serialize_suggestion,
    update_suggestion,
)

router = APIRouter(prefix="/api/knowledge", tags=["企业知识库"])


@router.post("/search", response_model=KnowledgeSearchResponse)
async def search_knowledge(
    payload: KnowledgeSearchRequest,
    db: AsyncSession = Depends(get_db),
):
    if payload.project_id is not None:
        project = await db.scalar(select(Project).where(Project.id == payload.project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")

    result = search_local_knowledge(payload.query, payload.top_k)
    items = [KnowledgeSearchItemOut.model_validate(item) for item in result["items"]]
    answer_result = (
        await generate_local_knowledge_answer(
            payload.query,
            [item.model_dump() for item in items],
            resource_summary=result.get("resource_summary"),
        )
        if items and result.get("status") != "insufficient_evidence"
        else {
            "status": "no_evidence" if not items else result.get("status", "insufficient_evidence"),
            "message": result["message"],
            "answer": "",
        }
    )
    return KnowledgeSearchResponse(
        status=result.get("status") if result.get("status") == "insufficient_evidence" else answer_result["status"],
        message=result["message"] if result.get("status") == "insufficient_evidence" else answer_result["message"],
        answer=answer_result["answer"],
        items=items,
        intent=result.get("intent", "general"),
        relationship_gaps=result.get("relationship_gaps", []),
        resource_summary=result.get("resource_summary"),
    )


@router.post("/evidence", response_model=KnowledgeEvidenceOut)
async def create_evidence_snapshot(
    payload: KnowledgeEvidenceCreate,
    db: AsyncSession = Depends(get_db),
):
    if payload.project_id is not None:
        project = await db.scalar(select(Project).where(Project.id == payload.project_id))
        if project is None:
            raise HTTPException(status_code=404, detail="项目不存在")
    row = await save_evidence_snapshot(db, payload)
    return row


@router.get("/evidence", response_model=list[KnowledgeEvidenceOut])
async def list_evidence_snapshots(
    project_id: int | None = Query(default=None, gt=0),
    db: AsyncSession = Depends(get_db),
):
    query = select(KnowledgeEvidenceSnapshot).order_by(
        KnowledgeEvidenceSnapshot.created_at.desc(), KnowledgeEvidenceSnapshot.id.desc()
    )
    if project_id is not None:
        query = query.where(KnowledgeEvidenceSnapshot.project_id == project_id)
    result = await db.execute(query)
    return result.scalars().all()


@router.post("/suggestions/draft", response_model=KnowledgeRuleSuggestionOut)
async def create_knowledge_rule_suggestion_draft(
    payload: KnowledgeRuleSuggestionDraft,
    db: AsyncSession = Depends(get_db),
):
    row = await create_suggestion_draft(db, payload)
    return serialize_suggestion(row)


@router.get("/suggestions", response_model=list[KnowledgeRuleSuggestionOut])
async def get_knowledge_rule_suggestions(
    project_id: int = Query(..., gt=0),
    route_version_id: int | None = Query(default=None, gt=0),
    segment_id: str | None = Query(default=None, min_length=1),
    status: str | None = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
):
    project = await db.scalar(select(Project).where(Project.id == project_id))
    if project is None:
        raise HTTPException(status_code=404, detail="项目不存在")
    rows = await list_suggestions(
        db,
        project_id=project_id,
        route_version_id=route_version_id,
        segment_id=segment_id,
        status=status,
    )
    return [serialize_suggestion(row) for row in rows]


@router.patch("/suggestions/{suggestion_id}", response_model=KnowledgeRuleSuggestionOut)
async def patch_knowledge_rule_suggestion(
    suggestion_id: int,
    payload: KnowledgeRuleSuggestionUpdate,
    db: AsyncSession = Depends(get_db),
):
    row = await update_suggestion(db, suggestion_id, payload)
    return serialize_suggestion(row)
