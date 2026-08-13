"""Read-only aggregation for project rule-package capabilities."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    FinalizedRulePackage,
    NormalizedRouteSegmentRuleReview,
    Project,
)
from app.services.route_analysis import get_latest_normalized_route_version
from app.services.rule_packages.condition_review_repository import loads_candidate
from app.services.rule_packages.contracts import (
    RulePackageKmaiSummary,
    RulePackageReviewSummary,
    RulePackageStatusBlocker,
    RulePackageStatusPackage,
    RulePackageStatusResponse,
    RulePackageStatusRoute,
)
from app.services.rule_packages.execution import inspect_published_rule_package
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.publishing import PUBLISHABLE_PROJECT_STATUSES
from app.services.rule_packages.standard_factors import validate_factor_bindings


def _blocker(
    code: str,
    message: str,
    *blocks: str,
    count: int | None = None,
) -> RulePackageStatusBlocker:
    return RulePackageStatusBlocker(
        code=code,
        message=message,
        blocks=list(blocks),
        count=count,
    )


async def _latest_package(project_id: int, db: AsyncSession) -> FinalizedRulePackage | None:
    return (
        await db.execute(
            select(FinalizedRulePackage)
            .where(FinalizedRulePackage.project_id == project_id)
            .order_by(FinalizedRulePackage.version.desc(), FinalizedRulePackage.id.desc())
        )
    ).scalars().first()


def _package_summary(row: FinalizedRulePackage | None) -> RulePackageStatusPackage | None:
    if row is None:
        return None
    return RulePackageStatusPackage(
        id=row.id,
        version=row.version,
        route_version_id=row.route_version_id,
        schema_version=str(row.schema_version or "1.0"),
        content_hash=str(row.content_hash or ""),
        status=str(row.status or "archived"),
    )


async def _review_summary(
    route_id: int,
    db: AsyncSession,
) -> RulePackageReviewSummary:
    rows = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route_id,
            )
        )
    ).scalars().all()
    relevant = [
        row
        for row in rows
        if (
            row.condition_source_text
            or row.condition_candidate_json
            or row.condition_confirmed_json
        )
    ]
    confirmed = [
        row
        for row in relevant
        if (
            row.condition_status == "confirmed"
            and row.condition_confirmed_json
            and loads_candidate(row.condition_confirmed_json) is not None
        )
    ]
    invalid_binding_count = 0
    for row in confirmed:
        candidate = loads_candidate(row.condition_confirmed_json)
        if candidate is None or candidate.kind != "condition" or candidate.when is None:
            continue
        definitions = {item.key: item for item in candidate.field_definitions}
        invalid_binding_count += len(
            validate_factor_bindings(candidate.when, definitions)
        )
    return RulePackageReviewSummary(
        total=len(relevant),
        confirmed=len(confirmed),
        pending=len(relevant) - len(confirmed),
        invalid_factor_bindings=invalid_binding_count,
    )


async def build_rule_package_status(
    project_id: int,
    db: AsyncSession,
) -> RulePackageStatusResponse | None:
    project = await db.get(Project, project_id)
    if project is None:
        return None

    route = await get_latest_normalized_route_version(project_id, db)
    latest = await _latest_package(project_id, db)
    active = await load_published_rule_package(project_id, db)
    review_summary = (
        await _review_summary(route.id, db)
        if route is not None
        else RulePackageReviewSummary()
    )
    blockers: list[RulePackageStatusBlocker] = []
    blocker_codes: set[str] = set()

    def add_blocker(
        code: str,
        message: str,
        *blocks: str,
        count: int | None = None,
    ) -> None:
        if code in blocker_codes:
            return
        blocker_codes.add(code)
        blockers.append(_blocker(code, message, *blocks, count=count))

    if str(project.status or "") not in PUBLISHABLE_PROJECT_STATUSES:
        add_blocker(
            "project_not_ready",
            "当前任务尚未完成路线提炼。",
            "publish",
            "generate",
        )
    if route is None:
        add_blocker(
            "route_missing",
            "当前任务没有可用的规范化路线。",
            "publish",
            "generate",
        )
    if review_summary.pending:
        add_blocker(
            "pending_rule_reviews",
            "仍有规则需要确认。",
            "publish",
            count=review_summary.pending,
        )
    if review_summary.invalid_factor_bindings:
        add_blocker(
            "invalid_factor_bindings",
            "已确认规则存在无效的标准因素绑定。",
            "publish",
            count=review_summary.invalid_factor_bindings,
        )
    if active is None:
        add_blocker(
            "no_published_package",
            "当前任务没有已发布规则包。",
            "generate",
        )

    package_executable = active is not None and route is not None
    kmai_summary = RulePackageKmaiSummary()
    if active is not None and route is not None and active.route_version_id != route.id:
        package_executable = False
        add_blocker(
            "published_package_route_changed",
            "已发布规则包关联的路线已变化。",
            "generate",
        )

    if active is not None and str(active.schema_version or "1.0") == "2.0":
        inspection = await inspect_published_rule_package(
            active,
            project_id=project_id,
            db=db,
        )
        if inspection.parse_error is None and not inspection.sources_current:
            package_executable = False
            add_blocker(
                "published_rule_sources_changed",
                "已发布规则包的确认来源已变化。",
                "generate",
            )
        if (
            inspection.parse_error is not None
            or inspection.validation is None
            or not inspection.validation.valid
        ):
            package_executable = False
            add_blocker(
                "published_package_invalid",
                "已发布规则包无法解析或校验未通过。",
                "generate",
            )
        if (
            inspection.package is not None
            and inspection.validation is not None
            and inspection.validation.valid
        ):
            compatibility = build_kmai_compatibility_export(inspection.package)
            kmai_summary = RulePackageKmaiSummary(
                available=True,
                valid=compatibility.valid,
                error_count=len(compatibility.errors),
                warning_count=len(compatibility.warnings),
                factor_catalog_version=compatibility.factor_catalog_version,
            )
            if not compatibility.valid:
                add_blocker(
                    "kmai_incompatible",
                    "已发布规则包无法生成有效的 KmAI 兼容导出。",
                    "generate",
                )

    blocked = {capability for item in blockers for capability in item.blocks}
    return RulePackageStatusResponse(
        project_id=project.id,
        project_status=str(project.status or ""),
        workflow_revision=int(project.workflow_revision or 0),
        route=(
            RulePackageStatusRoute(id=route.id, version=route.version)
            if route is not None else None
        ),
        latest_package=_package_summary(latest),
        can_publish="publish" not in blocked,
        can_generate=package_executable and "generate" not in blocked,
        package_executable=package_executable,
        blockers=blockers,
        review_summary=review_summary,
        kmai_compatibility=kmai_summary,
    )
