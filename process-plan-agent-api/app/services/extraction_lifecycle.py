import asyncio

from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    DocumentOperationDetail,
    Factor,
    NormalizedRouteVersion,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    Operation,
    Project,
    RouteMergeSnapshot,
)


async def clear_project_extraction_results(
    db: AsyncSession,
    project_id: int,
    preserve_document_details: bool = False,
) -> None:
    if not preserve_document_details:
        detail_rows = (
            await db.execute(select(DocumentOperationDetail).where(DocumentOperationDetail.project_id == project_id))
        ).scalars().all()
        for row in detail_rows:
            await db.delete(row)

    old_ops = (await db.execute(select(Operation).where(Operation.project_id == project_id))).scalars().all()
    for op in old_ops:
        old_factors = (await db.execute(select(Factor).where(Factor.operation_id == op.id))).scalars().all()
        for factor in old_factors:
            await db.delete(factor)
        await db.delete(op)

    snapshots = (
        await db.execute(select(RouteMergeSnapshot).where(RouteMergeSnapshot.project_id == project_id))
    ).scalars().all()
    for snapshot in snapshots:
        await db.delete(snapshot)

    segment_reviews = (
        await db.execute(select(NormalizedRouteSegmentFactorReview).where(NormalizedRouteSegmentFactorReview.project_id == project_id))
    ).scalars().all()
    for review in segment_reviews:
        await db.delete(review)

    rule_reviews = (
        await db.execute(select(NormalizedRouteSegmentRuleReview).where(NormalizedRouteSegmentRuleReview.project_id == project_id))
    ).scalars().all()
    for review in rule_reviews:
        await db.delete(review)

    versions = (
        await db.execute(select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == project_id))
    ).scalars().all()
    for version in versions:
        await db.delete(version)
    await db.flush()


async def try_commit_project_status(db: AsyncSession, project: Project, status: str) -> None:
    for attempt in range(3):
        project.status = status
        try:
            await db.commit()
            return
        except OperationalError:
            await db.rollback()
            if attempt >= 2:
                raise
            await asyncio.sleep(0.3 * (attempt + 1))
