"""Transactional invalidation for route-rule workflow steps."""

from __future__ import annotations

from dataclasses import dataclass, field

from fastapi import HTTPException
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Factor,
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Operation,
    Project,
    RouteMergeSnapshot,
)


@dataclass
class WorkflowInvalidationResult:
    project_id: int
    from_step: int
    workflow_revision: int
    deleted_operations: int = 0
    deleted_route_merge_snapshots: int = 0
    deleted_route_versions: int = 0
    deleted_factor_reviews: int = 0
    deleted_rule_reviews: int = 0
    reset_condition_reviews: int = 0
    preserved_manual_condition_reviews: int = 0
    deleted_generated_routes: int = 0
    archived_rule_package_versions: list[int] = field(default_factory=list)


async def acquire_workflow_revision(
    db: AsyncSession,
    project_id: int,
    expected_workflow_revision: int,
) -> Project:
    """Validate the revision and hold the project write lock until commit."""
    expected = int(expected_workflow_revision or 0)
    locked_revision = (
        await db.execute(
            text(
                "UPDATE projects SET workflow_revision = workflow_revision "
                "WHERE id = :project_id AND workflow_revision = :expected_revision "
                "RETURNING workflow_revision"
            ),
            {"project_id": project_id, "expected_revision": expected},
        )
    ).scalar_one_or_none()
    if locked_revision is None:
        project = (
            await db.execute(select(Project).where(Project.id == project_id))
        ).scalar_one_or_none()
        if not project:
            raise HTTPException(404, "任务不存在")
        raise HTTPException(409, {
            "message": "当前页面已过期，请刷新后再操作。",
            "workflow_revision": int(project.workflow_revision or 0),
        })
    project = (
        await db.execute(select(Project).where(Project.id == project_id))
    ).scalar_one()
    return project


async def _claim_next_workflow_revision(
    db: AsyncSession,
    project_id: int,
    expected_workflow_revision: int,
) -> int:
    expected = int(expected_workflow_revision or 0)
    next_revision = (
        await db.execute(
            text(
                "UPDATE projects SET workflow_revision = workflow_revision + 1 "
                "WHERE id = :project_id AND workflow_revision = :expected_revision "
                "RETURNING workflow_revision"
            ),
            {"project_id": project_id, "expected_revision": expected},
        )
    ).scalar_one_or_none()
    if next_revision is None:
        current_revision = (
            await db.execute(select(Project.workflow_revision).where(Project.id == project_id))
        ).scalar_one_or_none()
        if current_revision is None:
            raise HTTPException(404, "任务不存在")
        raise HTTPException(409, {
            "message": "当前页面已过期，请刷新后再操作。",
            "workflow_revision": int(current_revision or 0),
        })
    return int(next_revision)


async def _rows(db: AsyncSession, model, project_id: int):
    return (
        await db.execute(select(model).where(model.project_id == project_id))
    ).scalars().all()


def _is_manual_boolean_review(review: NormalizedRouteSegmentRuleReview) -> bool:
    return (
        str(review.condition_parser_version or "") == "manual"
        and str(review.condition_confirmed_by or "") == "用户直接设定"
    )


def _reset_machine_condition(review: NormalizedRouteSegmentRuleReview) -> None:
    review.condition_status = "draft"
    review.condition_candidate_json = None
    review.condition_confirmed_json = None
    review.condition_confidence = None
    review.condition_issues_json = "[]"
    review.condition_field_registry_version = None
    review.condition_parser_version = None
    review.condition_parse_duration_ms = None
    review.condition_confirmed_by = None
    review.condition_confirmed_at = None


async def invalidate_project_workflow(
    db: AsyncSession,
    project: Project,
    *,
    from_step: int,
    expected_workflow_revision: int | None = None,
) -> WorkflowInvalidationResult:
    """Invalidate one workflow step and everything derived from it.

    The caller owns commit/rollback so task claiming and invalidation can share
    one transaction.
    """
    if from_step not in {2, 3, 4}:
        raise ValueError("from_step must be 2, 3, or 4")

    project_id = int(project.id)
    expected_revision = (
        int(project.workflow_revision or 0)
        if expected_workflow_revision is None
        else int(expected_workflow_revision)
    )
    next_revision = await _claim_next_workflow_revision(db, project_id, expected_revision)
    project.workflow_revision = next_revision
    packages = await _rows(db, FinalizedRulePackage, project_id)
    archived_versions: list[int] = []
    for package in packages:
        if package.status == "published":
            package.status = "archived"
            archived_versions.append(int(package.version or 0))
        if from_step == 2:
            package.route_version_id = None
    if from_step == 2 and packages:
        # Route versions cannot be deleted while historical packages still
        # reference them through SQLite foreign keys.
        await db.flush()

    generated_routes = await _rows(db, GeneratedRoute, project_id)
    for route in generated_routes:
        await db.delete(route)

    factor_reviews = await _rows(db, NormalizedRouteSegmentFactorReview, project_id)
    rule_reviews = await _rows(db, NormalizedRouteSegmentRuleReview, project_id)
    reset_condition_reviews = 0
    preserved_manual_condition_reviews = 0

    if from_step <= 3:
        for review in factor_reviews:
            await db.delete(review)
        for review in rule_reviews:
            await db.delete(review)
    else:
        for review in rule_reviews:
            has_condition_state = bool(
                str(review.condition_source_text or "").strip()
                or review.condition_candidate_json
                or review.condition_confirmed_json
            )
            if not has_condition_state:
                continue
            if _is_manual_boolean_review(review):
                preserved_manual_condition_reviews += 1
                continue
            _reset_machine_condition(review)
            reset_condition_reviews += 1

    route_versions = []
    snapshots = []
    operations = []
    if from_step == 2:
        route_versions = await _rows(db, NormalizedRouteVersion, project_id)
        snapshots = await _rows(db, RouteMergeSnapshot, project_id)
        operations = await _rows(db, Operation, project_id)
        for version in route_versions:
            await db.delete(version)
        for snapshot in snapshots:
            await db.delete(snapshot)
        for operation in operations:
            factors = (
                await db.execute(select(Factor).where(Factor.operation_id == operation.id))
            ).scalars().all()
            for factor in factors:
                await db.delete(factor)
            await db.delete(operation)
    else:
        project.status = "ROUTE_SET_READY"

    await db.flush()
    return WorkflowInvalidationResult(
        project_id=project_id,
        from_step=from_step,
        workflow_revision=project.workflow_revision,
        deleted_operations=len(operations),
        deleted_route_merge_snapshots=len(snapshots),
        deleted_route_versions=len(route_versions),
        deleted_factor_reviews=len(factor_reviews) if from_step <= 3 else 0,
        deleted_rule_reviews=len(rule_reviews) if from_step <= 3 else 0,
        reset_condition_reviews=reset_condition_reviews,
        preserved_manual_condition_reviews=preserved_manual_condition_reviews,
        deleted_generated_routes=len(generated_routes),
        archived_rule_package_versions=sorted(archived_versions),
    )
