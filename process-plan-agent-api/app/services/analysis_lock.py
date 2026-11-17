"""Explicit finalization entry and route-scoped step-three write protection."""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteVersion, utcnow
from app.schemas.schemas import AnalysisLockOut, FinalizationEntryRequest
from app.services.project_workflow_lifecycle import acquire_workflow_revision
from app.services.workflow_progress import _analysis_is_complete, _route_items


def require_analysis_editable(route: NormalizedRouteVersion) -> None:
    if route.analysis_locked_at is not None:
        raise HTTPException(409, {
            "code": "analysis_locked",
            "message": "已进入规则定稿，请到规则定稿页调整；需要从头分析时，请使用重新回答全部。",
            "route_id": route.id,
        })


async def enter_finalization(db: AsyncSession, body: FinalizationEntryRequest) -> AnalysisLockOut:
    # Shares the project write lock with saves and resets, including old tabs.
    project = await acquire_workflow_revision(db, body.project_id, body.expected_workflow_revision)
    route = (await db.execute(select(NormalizedRouteVersion).where(
        NormalizedRouteVersion.id == body.route_id,
        NormalizedRouteVersion.project_id == body.project_id,
    ).execution_options(populate_existing=True))).scalar_one_or_none()
    if route is None:
        raise HTTPException(404, "当前保存路线版本不存在。")
    latest_id = (await db.execute(select(NormalizedRouteVersion.id).where(
        NormalizedRouteVersion.project_id == body.project_id,
    ).order_by(NormalizedRouteVersion.version.desc(), NormalizedRouteVersion.id.desc()).limit(1))).scalar_one()
    if latest_id != route.id:
        raise HTTPException(409, "路线版本已变化，请刷新后进入规则定稿。")
    if not await _analysis_is_complete(db, route, _route_items(route)):
        raise HTTPException(409, "请先完成当前路线的规则分析。")
    if route.analysis_locked_at is None:
        route.analysis_locked_at = utcnow()
    # Read the stored timestamp so repeat entry has the same SQLite timezone representation.
    await db.flush()
    await db.refresh(route)
    return AnalysisLockOut(
        project_id=project.id, route_id=route.id,
        workflow_revision=int(project.workflow_revision or 0),
        analysis_locked=True, analysis_locked_at=route.analysis_locked_at,
    )
