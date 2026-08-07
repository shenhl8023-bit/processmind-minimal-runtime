"""Prepare and publish finalized rule packages inside a caller-owned transaction."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.schemas.schemas import FinalizedRulePackageSaveRequest
from app.services.finalized_rule_package_helpers import json_dumps, json_dumps_list, json_loads_list
from app.services.rule_packages.confirmation_validation import (
    ConfirmedRuleSourcesChanged,
    require_confirmed_user_rule_sources,
)
from app.services.rule_packages.contracts import KmaiCompatibilityExport, RulePackageV2
from app.services.rule_packages.hashing import (
    legacy_rule_package_content_hash,
    rule_package_content_hash,
)
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.lifecycle import publish_rule_package
from app.services.rule_packages.process_identity import package_process_reference_issues
from app.services.rule_packages.validator import (
    validate_rule_package,
    validate_rule_package_factor_bindings,
)


class _RulePackagePublicationError(ValueError):
    def __init__(self, detail: object):
        super().__init__(detail)
        self.detail = detail


class RulePackagePublicationRequestInvalid(_RulePackagePublicationError):
    pass


class RulePackagePublicationConflict(_RulePackagePublicationError):
    pass


class RulePackagePublicationUnprocessable(_RulePackagePublicationError):
    pass


class RulePackageVersionConflict(_RulePackagePublicationError):
    pass


@dataclass(frozen=True)
class FinalizedRulePackagePublication:
    row: FinalizedRulePackage
    kmai_compatibility: KmaiCompatibilityExport | None


@dataclass(frozen=True)
class _PreparedRulePackagePublication:
    package_name: str
    schema_version: str
    manifest: dict[str, Any]
    test_cases: list[dict[str, Any]]
    server_validation: dict[str, Any]
    content_hash: str
    kmai_compatibility: KmaiCompatibilityExport | None


async def _prepare_rule_package_publication(
    body: FinalizedRulePackageSaveRequest,
    project: Project,
    db: AsyncSession,
) -> _PreparedRulePackagePublication:
    if project.status not in {"ROUTE_SET_READY", "GENERATED"}:
        raise RulePackagePublicationConflict(
            "当前资料已变更或尚未完成路线提炼，请重新完成第二至四步后再导出规则包。"
        )
    if not body.input_schema:
        raise RulePackagePublicationRequestInvalid("input_schema.json 内容不能为空")
    if not body.route_catalog:
        raise RulePackagePublicationRequestInvalid("route_catalog.json 内容不能为空")
    if not body.route_rules:
        raise RulePackagePublicationRequestInvalid("route_rules.json 内容不能为空")
    if not (body.rule_report_md or "").strip():
        raise RulePackagePublicationRequestInvalid("rule_report.md 内容不能为空")

    schema_version = str(body.schema_version or "1.0").strip()
    if schema_version not in {"1.0", "2.0"}:
        raise RulePackagePublicationRequestInvalid(
            f"不支持的规则包 schema_version：{schema_version}"
        )
    package_name = (body.package_name or "process_route_rules").strip() or "process_route_rules"

    route_row = None
    if body.route_version_id is not None:
        route_row = (
            await db.execute(
                select(NormalizedRouteVersion).where(
                    NormalizedRouteVersion.id == body.route_version_id,
                    NormalizedRouteVersion.project_id == body.project_id,
                )
            )
        ).scalars().first()
        if not route_row:
            raise RulePackagePublicationUnprocessable(
                "规则包关联的路线版本不属于当前任务"
            )

    server_validation = dict(body.validation_report or {})
    manifest = dict(body.manifest or {})
    test_cases = list(body.test_cases or [])
    kmai_compatibility: KmaiCompatibilityExport | None = None
    if schema_version == "2.0":
        try:
            package_v2 = RulePackageV2.model_validate({
                "manifest": manifest,
                "input_schema": body.input_schema,
                "route_catalog": body.route_catalog,
                "route_rules": body.route_rules,
                "test_cases": test_cases,
            })
        except ValidationError as exc:
            raise RulePackagePublicationUnprocessable(
                exc.errors(include_url=False)
            ) from exc
        if package_v2.manifest.project_id != body.project_id:
            raise RulePackagePublicationUnprocessable(
                "manifest.project_id 与请求 project_id 不一致"
            )
        if package_v2.manifest.package_name != package_name:
            raise RulePackagePublicationUnprocessable(
                "manifest.package_name 与请求 package_name 不一致"
            )
        binding_issues = validate_rule_package_factor_bindings(package_v2)
        if binding_issues:
            raise RulePackagePublicationUnprocessable({
                "message": "标准因子绑定校验未通过",
                "issues": [issue.model_dump(mode="json") for issue in binding_issues],
            })
        validation = validate_rule_package(package_v2)
        server_validation = validation.model_dump(mode="json")
        if not validation.valid:
            raise RulePackagePublicationUnprocessable({
                "message": "规则包校验未通过，无法导出。",
                "validation": server_validation,
            })
        if route_row is not None:
            identity_issues = package_process_reference_issues(
                package_v2,
                json_loads_list(route_row.route_json),
            )
            if identity_issues:
                raise RulePackagePublicationUnprocessable({
                    "message": "规则包工序引用与当前路线不一致，无法发布。",
                    "issues": identity_issues,
                })
        if body.route_version_id is None:
            raise RulePackagePublicationUnprocessable("V2 规则包必须关联当前路线版本")
        try:
            await require_confirmed_user_rule_sources(
                package_v2,
                project_id=body.project_id,
                route_version_id=body.route_version_id,
                db=db,
            )
        except ConfirmedRuleSourcesChanged as exc:
            raise RulePackagePublicationConflict(exc.detail) from exc
        content_hash = rule_package_content_hash(package_v2)
        kmai_compatibility = build_kmai_compatibility_export(package_v2)
        if not kmai_compatibility.valid:
            raise RulePackagePublicationUnprocessable({
                "message": (
                    "KmAI compatibility validation failed; return to standard-factor "
                    "review before publishing."
                ),
                "kmai_compatibility": kmai_compatibility.model_dump(mode="json"),
            })
        server_validation["kmai_compatibility"] = {
            "factor_catalog_version": kmai_compatibility.factor_catalog_version,
        }
    else:
        content_hash = legacy_rule_package_content_hash(
            package_name=package_name,
            input_schema=body.input_schema,
            route_catalog=body.route_catalog,
            route_rules=body.route_rules,
            rule_report_md=body.rule_report_md,
        )

    if body.route_version_id is not None:
        route_exists = (
            await db.execute(
                select(NormalizedRouteVersion.id).where(
                    NormalizedRouteVersion.id == body.route_version_id,
                    NormalizedRouteVersion.project_id == body.project_id,
                )
            )
        ).scalar_one_or_none()
        if not route_exists:
            raise RulePackagePublicationUnprocessable(
                "规则包关联的路线版本不属于当前任务"
            )

    return _PreparedRulePackagePublication(
        package_name=package_name,
        schema_version=schema_version,
        manifest=manifest,
        test_cases=test_cases,
        server_validation=server_validation,
        content_hash=content_hash,
        kmai_compatibility=kmai_compatibility,
    )


async def create_published_rule_package(
    body: FinalizedRulePackageSaveRequest,
    project: Project,
    db: AsyncSession,
) -> FinalizedRulePackagePublication:
    prepared = await _prepare_rule_package_publication(body, project, db)

    for _ in range(3):
        latest_version = (
            await db.execute(
                select(func.max(FinalizedRulePackage.version)).where(
                    FinalizedRulePackage.project_id == body.project_id
                )
            )
        ).scalar_one_or_none()
        row = FinalizedRulePackage(
            project_id=body.project_id,
            route_version_id=body.route_version_id,
            version=int(latest_version or 0) + 1,
            package_name=prepared.package_name,
            schema_version=prepared.schema_version,
            status="draft",
            manifest_json=json_dumps(prepared.manifest),
            input_schema_json=json_dumps(body.input_schema),
            route_catalog_json=json_dumps(body.route_catalog),
            route_rules_json=json_dumps(body.route_rules),
            test_cases_json=json_dumps_list(prepared.test_cases),
            rule_report_md=body.rule_report_md,
            validation_report_json=json_dumps(prepared.server_validation),
            content_hash=prepared.content_hash,
            created_by=(body.created_by or "默认用户").strip() or "默认用户",
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
                await publish_rule_package(row, db, actor=row.created_by)
            return FinalizedRulePackagePublication(
                row=row,
                kmai_compatibility=prepared.kmai_compatibility,
            )
        except IntegrityError:
            continue

    raise RulePackageVersionConflict(
        "规则包版本正在由其他请求导出，请稍后重试。"
    )
