"""Persistence lifecycle helpers for immutable finalized rule packages."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, utcnow
from app.services.finalized_rule_package_helpers import json_loads, json_loads_list
from app.services.rule_packages.contracts import RulePackageV2, RulePackageValidationReport
from app.services.rule_packages.validator import validate_rule_package


class RulePackageLifecycleError(ValueError):
    def __init__(self, message: str, validation: RulePackageValidationReport | None = None):
        super().__init__(message)
        self.validation = validation


async def supersede_published_rule_packages(
    project_id: int,
    db: AsyncSession,
) -> int:
    """Retire packages derived from a project's previous document set."""
    rows = (
        await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == project_id,
                FinalizedRulePackage.status == "published",
            )
        )
    ).scalars().all()
    for row in rows:
        row.status = "superseded"
    await db.flush()
    return len(rows)


def v2_package_from_row(row: FinalizedRulePackage) -> RulePackageV2:
    if str(row.schema_version or "") != "2.0":
        raise RulePackageLifecycleError("当前规则包不是可执行的 V2 规则包")
    return RulePackageV2.model_validate({
        "manifest": json_loads(row.manifest_json),
        "factor_dictionary": json_loads(row.factor_dictionary_json) or None,
        "input_schema": json_loads(row.input_schema_json),
        "route_catalog": json_loads(row.route_catalog_json),
        "route_rules": json_loads(row.route_rules_json),
        "test_cases": json_loads_list(row.test_cases_json),
    })


async def publish_rule_package(
    row: FinalizedRulePackage,
    db: AsyncSession,
    *,
    actor: str,
) -> FinalizedRulePackage:
    if row.status == "archived":
        raise RulePackageLifecycleError("已归档规则包不能直接发布")

    validation = validate_rule_package(v2_package_from_row(row))
    if not validation.valid:
        raise RulePackageLifecycleError("规则包校验或包内测试未通过，不能发布", validation)

    current = (
        await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == row.project_id,
                FinalizedRulePackage.status == "published",
                FinalizedRulePackage.id != row.id,
            )
        )
    ).scalar_one_or_none()
    if current:
        current.status = "superseded"
        row.supersedes_id = current.id
        await db.flush()

    row.status = "published"
    row.published_by = (actor or "默认用户").strip() or "默认用户"
    row.published_at = utcnow()
    await db.flush()
    return row
