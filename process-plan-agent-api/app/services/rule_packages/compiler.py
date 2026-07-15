"""Compilation of a constrained finalize DTO into a materialized V2 package."""

from __future__ import annotations

from app.services.rule_packages.contracts import (
    CompileRulePackageRequest,
    RulePackageManifestV2,
    RulePackageV2,
    InputSchemaV2,
    PackageScope,
    RouteCatalogV2,
    RouteRulesV2,
)


def compile_rule_package(request: CompileRulePackageRequest) -> RulePackageV2:
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
        route_rules=RouteRulesV2(rules=request.rules),
        test_cases=request.test_cases,
    )
