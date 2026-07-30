"""Compilation of a constrained finalize DTO into a materialized V2 package."""

from __future__ import annotations

from app.services.rule_packages.contracts import (
    CompileRulePackageRequest,
    FactorBindingIssue,
    RulePackageManifestV2,
    RulePackageV2,
    InputSchemaV2,
    PackageScope,
    RouteCatalogV2,
    RouteRulesV2,
)
from app.services.rule_packages.validator import validate_rule_factor_bindings


class RulePackageCompilationError(Exception):
    def __init__(self, issues: list[FactorBindingIssue]):
        super().__init__("标准因子绑定校验未通过")
        self.issues = issues


def compile_rule_package(request: CompileRulePackageRequest) -> RulePackageV2:
    binding_issues = validate_rule_factor_bindings(
        request.rules,
        request.fields,
        path_prefix="rules",
    )
    if binding_issues:
        raise RulePackageCompilationError(binding_issues)
    return RulePackageV2(
        manifest=RulePackageManifestV2(
            package_name=request.package_name,
            project_id=request.project_id,
            route_version_id=request.route_version_id,
            scope=PackageScope(key=str(request.project_id)),
            applicability=request.applicability,
        ),
        input_schema=InputSchemaV2(fields=request.fields),
        route_catalog=RouteCatalogV2(processes=request.processes),
        route_rules=RouteRulesV2(rules=request.rules, process_relations=request.process_relations),
        test_cases=request.test_cases,
    )
