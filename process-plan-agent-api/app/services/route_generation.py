"""Application service for V1/V2 route generation selection.

The service has no HTTP or transaction ownership. It turns a validated
published package and project rules into a domain result that the router can
persist and serialize.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.models import FinalizedRulePackage, Operation, Project
from app.schemas.schemas import FactorFieldOut, GenerateRequest, RouteStep
from app.services.finalized_route_generator import generate_steps_from_finalized_rule_package
from app.services.generate_factor_schema_loader import build_project_factor_schema
from app.services.generate_route_result_builder import build_minimal_fallback_steps
from app.services.harness_validators import is_harness_warning_factor_name
from app.services.legacy_operation_route_selector import (
    collapse_redundant_quality_gates,
    select_best_operations,
)
from app.services.param_rule_expression import (
    matches_factor_condition,
    parse_factor_condition,
    to_bool,
    to_float,
)
from app.services.param_project_context import load_project_resource_bundle
from app.services.rule_packages.contracts import RulePackageValidationReport
from app.services.rule_packages.execution import execute_published_v2_rule_package
from app.services.rule_packages.execution import (
    PublishedRulePackageInvalid,
    PublishedRulePackageInputInvalid,
    RulePackageExpectation,
    load_published_rule_package_for_execution,
)
from app.services.rule_packages.lifecycle import RulePackageLifecycleError
from app.services.rule_packages.planner import RoutePlanningError


@dataclass(frozen=True)
class RouteGenerationResult:
    steps: list[RouteStep]
    summary: str
    output_mode: str
    rule_package_id: int | None
    rule_package_version: int | None
    rule_package_hash: str | None
    schema_version: str | None
    matched_rule_ids: list[str]
    selected_process_ids: list[str]
    project: Project | None = None


class RouteGenerationNoExecutableRoute(ValueError):
    pass


class RouteGenerationInvalidPackage(ValueError):
    def __init__(self, version: int, validation: RulePackageValidationReport):
        self.version = version
        self.validation = validation
        super().__init__(f"已发布规则包 V{version} 校验未通过，无法生成")


class RouteGenerationV2ValueError(ValueError):
    """Preserve the V2 route's legacy ValueError-to-422 HTTP mapping."""


class RouteGenerationProjectNotFound(LookupError):
    pass


class RouteGenerationNoPublishedPackage(LookupError):
    pass


def normalize_input_values(
    body: GenerateRequest,
    *,
    explicit_legacy_fields_only: bool = False,
) -> dict[str, object]:
    values = dict(body.factor_values or {})
    submitted_fields = body.model_fields_set if explicit_legacy_fields_only else None
    legacy = {
        "family": body.family,
        "material": body.material,
        "hardness": body.hardness,
        "has_hole": body.has_hole,
        "has_spline": body.has_spline,
        "roughness": body.roughness,
    }
    for key, value in legacy.items():
        if submitted_fields is not None and key not in submitted_fields:
            continue
        if key not in values and value not in ("", None):
            values[key] = value
    return values


def build_route_generation_result(
    *,
    project: Project,
    operations: list[Operation],
    finalized_package: FinalizedRulePackage,
    body: GenerateRequest,
) -> RouteGenerationResult:
    rule_engine = str(getattr(project, "rule_engine", None) or "auto").strip().lower()
    if rule_engine not in {"auto", "v1", "v2"}:
        rule_engine = "auto"

    schema_version = str(finalized_package.schema_version or "1.0")
    package_metadata = {
        "rule_package_id": finalized_package.id,
        "rule_package_version": finalized_package.version,
        "rule_package_hash": finalized_package.content_hash or "",
        "schema_version": schema_version,
    }
    legacy_inputs = normalize_input_values(body)

    if schema_version == "2.0" and rule_engine != "v1":
        # V2 validation only sees fields the caller actually sent, not schema
        # defaults from the legacy request model.
        v2_inputs = normalize_input_values(body, explicit_legacy_fields_only=True)
        try:
            execution = execute_published_v2_rule_package(finalized_package, v2_inputs)
        except PublishedRulePackageInvalid as exc:
            raise RouteGenerationInvalidPackage(finalized_package.version, exc.validation) from exc
        except (PublishedRulePackageInputInvalid, RulePackageLifecycleError, RoutePlanningError):
            raise
        except ValueError as exc:
            raise RouteGenerationV2ValueError(str(exc)) from exc
        plan = execution.plan
        steps = [
            RouteStep(
                process_id=step.process_id,
                sequence=step.sequence,
                name=step.name,
                op_type=step.op_type,
                reason=step.reason,
                process_steps=list(step.process_steps or []),
                template_group_aliases=[alias.model_dump() for alias in step.template_group_aliases],
            )
            for step in plan.steps
        ]
        if not steps:
            raise RouteGenerationNoExecutableRoute(
                "规则包未生成可执行路线，请检查主线工序和规则条件。"
            )
        matched_rule_ids = [trace.rule_id for trace in plan.traces if trace.matched]
        return RouteGenerationResult(
            steps=steps,
            summary=(
                f"已基于已发布规则包 V{finalized_package.version}（schema 2.0）"
                f"确定性规划生成，命中 {len(matched_rule_ids)} 条规则"
            ),
            output_mode="finalized_rule_package_v2",
            matched_rule_ids=matched_rule_ids,
            selected_process_ids=list(plan.selected_process_ids),
            **package_metadata,
        )

    if schema_version != "2.0":
        package_result = generate_steps_from_finalized_rule_package(
            finalized_package,
            legacy_inputs,
            collapse_quality_gates=collapse_redundant_quality_gates,
            parse_factor_condition=parse_factor_condition,
            matches_factor_condition=matches_factor_condition,
            to_bool=to_bool,
            to_float=to_float,
        )
        if package_result:
            steps, summary = package_result
            return RouteGenerationResult(
                steps=steps,
                summary=summary,
                output_mode="finalized_rule_package",
                matched_rule_ids=[],
                selected_process_ids=[],
                **package_metadata,
            )
        source_summary = "当前已基于第二步提炼结果生成路线"
    else:
        source_summary = (
            f"当前任务已将规则引擎切到 V1/旧规则路径；"
            f"已发布 V2 规则包 V{finalized_package.version} 本次未参与正式生成"
        )

    steps = select_best_operations(operations, legacy_inputs)
    if not steps:
        steps = build_minimal_fallback_steps(legacy_inputs, to_bool=to_bool, to_float=to_float)
    return RouteGenerationResult(
        steps=steps,
        summary=source_summary,
        output_mode="route_rules",
        matched_rule_ids=[],
        selected_process_ids=[],
        **package_metadata,
    )


async def generate_published_route(
    body: GenerateRequest,
    db: AsyncSession,
) -> RouteGenerationResult:
    """Load the current package and assemble a route without committing."""
    if not body.project_id:
        raise ValueError("project_id 不能为空")

    project = (
        await db.execute(select(Project).where(Project.id == body.project_id))
    ).scalar_one_or_none()
    if project is None:
        raise RouteGenerationProjectNotFound("任务不存在")

    finalized_package = await load_published_rule_package_for_execution(
        body.project_id,
        db,
        expectation=RulePackageExpectation(
            package_id=body.expected_rule_package_id,
            version=body.expected_rule_package_version,
            content_hash=body.expected_rule_package_hash,
        ),
    )
    if finalized_package is None:
        raise RouteGenerationNoPublishedPackage(
            "当前资料尚未导出有效规则包。请重新完成提炼、审核并导出后再生成。"
        )

    operations = (
        await db.execute(
            select(Operation)
            .where(Operation.project_id == body.project_id)
            .options(selectinload(Operation.factors))
            .order_by(Operation.sequence, Operation.id)
        )
    ).scalars().unique().all()
    result = build_route_generation_result(
        project=project,
        operations=operations,
        finalized_package=finalized_package,
        body=body,
    )
    return replace(result, project=project)


async def load_project_factor_schema(
    project_id: int,
    db: AsyncSession,
) -> list[FactorFieldOut]:
    resources = await load_project_resource_bundle(project_id, db)
    if resources.project is None:
        raise RouteGenerationProjectNotFound("任务不存在")

    operations = (
        await db.execute(
            select(Operation)
            .where(Operation.project_id == project_id)
            .options(selectinload(Operation.factors))
            .order_by(Operation.sequence, Operation.id)
        )
    ).scalars().unique().all()
    return build_project_factor_schema(
        operations,
        resources.references,
        parse_factor_condition=parse_factor_condition,
        is_warning_factor_name=is_harness_warning_factor_name,
    )


__all__ = [
    "RouteGenerationNoExecutableRoute",
    "RouteGenerationInvalidPackage",
    "RouteGenerationNoPublishedPackage",
    "RouteGenerationProjectNotFound",
    "RouteGenerationResult",
    "RouteGenerationV2ValueError",
    "build_route_generation_result",
    "generate_published_route",
    "load_project_factor_schema",
    "normalize_input_values",
]
