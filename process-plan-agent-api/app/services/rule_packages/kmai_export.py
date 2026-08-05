"""Build drop-in KmAI v1 runtime files from a ProcessMind V2 rule package."""

from __future__ import annotations

from typing import Any, Sequence

from app.services.rule_packages.contracts import (
    KmaiCompatibilityExport,
    KmaiCompatibilityIssue,
    RulePackageV2,
    ValidationIssue,
)
from app.services.rule_packages.kmai_export_conditions import (
    DEFAULT_KMAI_MAX_COMBINATIONS,
    DEFAULT_KMAI_MAX_CONDITION_OBJECTS,
    KMAI_MAX_COMBINATIONS_ENV,
    KMAI_MAX_CONDITION_OBJECTS_ENV,
    StandardFactorExportError,
    condition_dnf as _condition_dnf,
    condition_expansion_size as _condition_expansion_size,
    configured_max_combinations as _configured_max_combinations,
    configured_max_condition_objects as _configured_max_condition_objects,
)
from app.services.rule_packages.kmai_export_context import ConditionBudget, FactorRegistry
from app.services.rule_packages.kmai_export_factors import (
    LegacyFactorAdapterEntry,
    build_factor_expansion_rules,
    build_factor_schema,
    builtin_legacy_mapping_snapshot,
    legacy_adapter_key,
    legacy_mapping_snapshot_from_validation_report,
    normalize_legacy_adapter_value,
)
from app.services.rule_packages.kmai_export_routes import (
    build_route_catalog,
    build_route_rules,
)
from app.services.rule_packages.standard_factors import (
    STANDARD_FACTOR_CATALOG_VERSION,
)

KMAI_TARGET_DIRECTORY = r"KmMpsMcpServer\skills\process-route-generator\references\v1"

def _issue(
    code: str,
    message: str,
    path: str = "",
    **details: Any,
) -> KmaiCompatibilityIssue:
    return KmaiCompatibilityIssue(code=code, path=path, message=message, **details)


def build_kmai_compatibility_export(
    package: RulePackageV2,
    *,
    legacy_mapping_snapshot: Sequence[LegacyFactorAdapterEntry] | None = None,
    max_combinations: int | None = None,
    max_condition_objects: int | None = None,
) -> KmaiCompatibilityExport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    registry = FactorRegistry()
    legacy_adapters = (
        {
            legacy_adapter_key(entry.source_field, entry.source_value): entry
            for entry in legacy_mapping_snapshot
        }
        if legacy_mapping_snapshot is not None
        else None
    )
    combination_limit = max_combinations or _configured_max_combinations()
    if combination_limit <= 0:
        combination_limit = DEFAULT_KMAI_MAX_COMBINATIONS
    condition_object_limit = max_condition_objects or _configured_max_condition_objects()
    if condition_object_limit <= 0:
        condition_object_limit = DEFAULT_KMAI_MAX_CONDITION_OBJECTS
    budget = ConditionBudget(combination_limit, condition_object_limit)
    route_catalog, process_keys = build_route_catalog(package)
    route_rules_result = build_route_rules(
        package,
        process_keys,
        registry,
        budget,
        legacy_adapters,
        condition_dnf_fn=_condition_dnf,
        condition_expansion_size_fn=_condition_expansion_size,
    )
    errors.extend(route_rules_result.errors)
    warnings.extend(route_rules_result.warnings)
    route_rules = route_rules_result.payload
    factor_schema = build_factor_schema(package, registry)
    factor_expansion_rules = build_factor_expansion_rules(package)

    factor_keys = {item["factor_key"] for item in factor_schema["factors"]}
    for rule_index, rule in enumerate(route_rules["rules"]):
        for condition_index, condition in enumerate(rule["when"]["all"]):
            if condition["factor_key"] not in factor_keys:
                errors.append(
                    _issue(
                        "kmai_factor_reference_missing",
                        f"KmAI 规则引用了未定义因素：{condition['factor_key']}",
                        f"route_rules.rules[{rule_index}].when.all[{condition_index}]",
                    )
                )

    files = {
        "factor_schema.json": factor_schema,
        "factor_expansion_rules.json": factor_expansion_rules,
        "route_catalog.json": route_catalog,
        "route_rules.json": route_rules,
    }
    return KmaiCompatibilityExport(
        valid=not errors,
        target_directory=KMAI_TARGET_DIRECTORY,
        errors=errors,
        warnings=warnings,
        files=files,
        factor_catalog_version=STANDARD_FACTOR_CATALOG_VERSION,
    )
