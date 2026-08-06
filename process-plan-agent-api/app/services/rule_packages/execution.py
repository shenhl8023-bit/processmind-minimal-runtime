"""Published rule-package loading contract for route execution."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage
from app.services.rule_packages.confirmation_validation import (
    ConfirmedRuleSourcesChanged,
    require_confirmed_user_rule_sources,
)
from app.services.rule_packages.contracts import RoutePlan, RulePackageValidationReport
from app.services.rule_packages.input_validation import InputValidationIssue, validate_inputs
from app.services.rule_packages.lifecycle import (
    archive_published_rule_packages,
    v2_package_from_row,
)
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


@dataclass(frozen=True)
class RulePackageExpectation:
    package_id: int | None
    version: int | None
    content_hash: str | None

    @property
    def supplied(self) -> bool:
        return any(value is not None for value in (self.package_id, self.version, self.content_hash))


class PublishedRulePackageChanged(Exception):
    def __init__(self, current: FinalizedRulePackage | None):
        self.detail = {
            "code": "published_rule_package_changed",
            "message": "规则包已更新，请刷新后重新生成。",
            "current_rule_package": (
                {
                    "id": current.id,
                    "version": current.version,
                    "content_hash": current.content_hash,
                }
                if current is not None
                else None
            ),
        }
        super().__init__(self.detail["message"])


class PublishedRulePackageSourcesChanged(Exception):
    def __init__(self):
        self.detail = {
            "code": "published_rule_package_changed",
            "message": "当前规则内容已变化，请返回第四步重新发布后再生成。",
            "current_rule_package": None,
        }
        super().__init__(self.detail["message"])


@dataclass(frozen=True)
class V2RulePackageExecution:
    plan: RoutePlan


class PublishedRulePackageInvalid(ValueError):
    def __init__(self, validation: RulePackageValidationReport):
        self.validation = validation
        super().__init__("已发布规则包校验未通过，无法生成")


class PublishedRulePackageInputInvalid(ValueError):
    def __init__(self, issues: list[InputValidationIssue]):
        self.issues = issues
        super().__init__("已发布规则包输入校验未通过，无法生成")


async def load_published_rule_package_for_execution(
    project_id: int,
    db: AsyncSession,
    *,
    expectation: RulePackageExpectation,
) -> FinalizedRulePackage | None:
    current = await load_published_rule_package(project_id, db)
    if current is None:
        if expectation.supplied:
            raise PublishedRulePackageChanged(None)
        return None

    if (
        (expectation.package_id is not None and expectation.package_id != current.id)
        or (expectation.version is not None and expectation.version != current.version)
        or (
            expectation.content_hash is not None
            and expectation.content_hash != current.content_hash
        )
    ):
        raise PublishedRulePackageChanged(current)

    if str(current.schema_version or "1.0") == "2.0":
        package = v2_package_from_row(current)
        try:
            await require_confirmed_user_rule_sources(
                package,
                project_id=project_id,
                route_version_id=int(current.route_version_id or 0),
                db=db,
            )
        except ConfirmedRuleSourcesChanged as exc:
            await archive_published_rule_packages(project_id, db)
            raise PublishedRulePackageSourcesChanged() from exc
    return current


def execute_published_v2_rule_package(
    row: FinalizedRulePackage,
    inputs: dict[str, Any],
) -> V2RulePackageExecution:
    package = v2_package_from_row(row)
    validation = validate_rule_package(package)
    if not validation.valid:
        raise PublishedRulePackageInvalid(validation)

    issues = validate_inputs(package.input_schema, inputs)
    if issues:
        raise PublishedRulePackageInputInvalid(issues)

    return V2RulePackageExecution(plan=plan_route(package, inputs))
