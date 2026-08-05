"""Condition translation and expansion limits for KmAI V1 exports."""

from __future__ import annotations

import os
from itertools import product
from typing import Any, Literal

from app.services.rule_packages.contracts import (
    ConditionNode,
    KmaiCompatibilityIssue,
    RulePackageV2,
    ValidationIssue,
)
from app.services.rule_packages.kmai_export_context import (
    FactorRegistry,
    KmaiExportContext,
)
from app.services.rule_packages.kmai_export_factors import (
    LegacyFactorAdapterEntry,
    dynamic_factor,
    legacy_adapter_key,
    mapped_manual_factor,
)
from app.services.rule_packages.standard_factors import (
    standard_factor_map,
    validate_factor_bindings,
)


KMAI_MAX_COMBINATIONS_ENV = "PROCESSMIND_KMAI_MAX_COMBINATIONS"
DEFAULT_KMAI_MAX_COMBINATIONS = 10_000
KMAI_MAX_CONDITION_OBJECTS_ENV = "PROCESSMIND_KMAI_MAX_CONDITION_OBJECTS"
DEFAULT_KMAI_MAX_CONDITION_OBJECTS = 100_000

_OPERATOR_MAP = {
    "eq": "=",
    "neq": "!=",
    "in": "in",
    "gt": ">",
    "gte": ">=",
    "lt": "<",
    "lte": "<=",
    "exists": "exists",
}


def _issue(code: str, message: str, path: str = "") -> KmaiCompatibilityIssue:
    return KmaiCompatibilityIssue(code=code, path=path, message=message)


class StandardFactorExportError(ValueError):
    def __init__(
        self,
        code: Literal["standard_factor_unbound", "standard_factor_mismatch"],
        message: str,
    ):
        self.code = code
        super().__init__(message)


def _manual_process_condition(node: ConditionNode) -> bool:
    return (
        bool(node.field)
        and node.field.startswith("project_factor.manual_process_")
        and node.op == "eq"
        and type(node.value) is bool
        and node.factor_id is None
    )


def _fixed_leaf_condition(
    package: RulePackageV2,
    node: ConditionNode,
    registry: FactorRegistry,
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    if _manual_process_condition(node):
        field = node.field or ""
        factor_key = dynamic_factor(package, field, registry)
        registry.update(
            factor_key,
            value_type="boolean",
            multiple=False,
            default_value=False,
            source_mode="manual_override",
        )
        warnings.append(_issue("kmai_manual_override_required", f"manual Boolean factor requires override: {factor_key}", path))
        return [[{"factor_key": factor_key, "op": "=", "value": node.value}]]

    if node.factor_id is not None:
        definition = standard_factor_map().get(node.factor_id)
        binding_issues = validate_factor_bindings(node)
        if definition is None:
            raise StandardFactorExportError("standard_factor_unbound", "condition has no known standard factor")
        if binding_issues:
            raise StandardFactorExportError("standard_factor_mismatch", binding_issues[0].message)
        if definition.kmai_value_mode == "presence":
            return [[{"factor_key": definition.kmai_factor_key, "op": "=", "value": True}]]
        mapped = _OPERATOR_MAP.get(node.op or "")
        if not mapped:
            raise ValueError(f"Unsupported KmAI V1 operator: {node.op}")
        if definition.factor_id == "material.grade":
            return [[{"factor_key": definition.kmai_factor_key, "op": mapped, "value": node.value}]]
        factor_key = dynamic_factor(package, definition.source_field, registry)
        warnings.append(_issue("kmai_manual_override_required", f"field {definition.source_field} requires KmAI manual.factor_overrides input: {factor_key}", path))
        return [[{"factor_key": factor_key, "op": mapped, "value": node.value}]]

    if legacy_adapters is None:
        raise StandardFactorExportError("standard_factor_unbound", "condition has no bound standard factor")

    field = node.field or ""
    op = node.op or ""
    if field == "material.grade":
        mapped = _OPERATOR_MAP.get(op)
        if mapped:
            return [[{"factor_key": "material_grade", "op": mapped, "value": node.value}]]
    if field not in {"cad.features", "precision.grades", "special.requirements"}:
        raise StandardFactorExportError("standard_factor_unbound", f"historical condition is not covered by an immutable adapter: {field}")
    values = node.value if isinstance(node.value, list) else [node.value]
    leaves: list[dict[str, Any]] = []
    for value in values:
        entry = legacy_adapters.get(legacy_adapter_key(field, value))
        if entry is None:
            raise StandardFactorExportError("standard_factor_unbound", f"historical condition is not covered by an immutable adapter: {field}")
        if entry.mapping_mode == "manual_factor":
            mapped_manual_factor(entry, registry)
            warnings.append(_issue("kmai_manual_override_required", f"historical manual factor requires override: {entry.target_factor_key}", path))
        leaves.append({"factor_key": entry.target_factor_key, "op": "=", "value": True})
    if op in {"contains", "eq", "contains_all"}:
        return [leaves]
    if op in {"contains_any", "in"}:
        return [[leaf] for leaf in leaves]
    raise ValueError(f"Unsupported KmAI V1 operator: {op}")


def _leaf_condition(
    package: RulePackageV2,
    node: ConditionNode,
    registry: FactorRegistry,
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    return _fixed_leaf_condition(package, node, registry, warnings, path, legacy_adapters)


def condition_dnf(
    package: RulePackageV2,
    node: ConditionNode,
    registry: FactorRegistry,
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    if node.field is not None:
        return _leaf_condition(package, node, registry, warnings, path, legacy_adapters)
    if node.all_conditions is not None:
        groups = [
            condition_dnf(package, child, registry, warnings, f"{path}.all[{index}]", legacy_adapters)
            for index, child in enumerate(node.all_conditions)
        ]
        clauses: list[list[dict[str, Any]]] = [[]]
        for group in groups:
            clauses = [left + right for left, right in product(clauses, group)]
        return clauses
    if node.any_conditions is not None:
        clauses: list[list[dict[str, Any]]] = []
        for index, child in enumerate(node.any_conditions):
            clauses.extend(
                condition_dnf(
                    package,
                    child,
                    registry,
                    warnings,
                    f"{path}.any[{index}]",
                    legacy_adapters,
                )
            )
        return clauses
    raise ValueError("KmAI V1 暂不支持 not 条件，请先在 ProcessMind 中改写为正向条件")


def condition_dnf_with_context(
    context: KmaiExportContext,
    node: ConditionNode,
    path: str,
) -> list[list[dict[str, Any]]]:
    """Translate one condition using the state owned by a single export."""
    return condition_dnf(
        context.package,
        node,
        context.registry,
        context.warnings,
        path,
        context.legacy_adapters,
    )


def condition_expansion_size(node: ConditionNode) -> tuple[int, int]:
    """Return DNF clause and condition-object counts without materializing them."""
    if node.field is not None:
        values = node.value if isinstance(node.value, list) else [node.value]
        if node.field in {"cad.features", "precision.grades", "special.requirements"}:
            if node.op in {"contains_any", "in"}:
                return len(values), len(values)
            if node.op in {"contains", "eq", "contains_all"}:
                return 1, len(values)
        return 1, 1
    if node.all_conditions is not None:
        clause_count = 1
        condition_object_count = 0
        for child in node.all_conditions:
            child_clause_count, child_condition_object_count = condition_expansion_size(child)
            condition_object_count = (
                condition_object_count * child_clause_count
                + child_condition_object_count * clause_count
            )
            clause_count *= child_clause_count
        return clause_count, condition_object_count
    if node.any_conditions is not None:
        clause_count = 0
        condition_object_count = 0
        for child in node.any_conditions:
            child_clause_count, child_condition_object_count = condition_expansion_size(child)
            clause_count += child_clause_count
            condition_object_count += child_condition_object_count
        return clause_count, condition_object_count
    raise ValueError("KmAI V1 暂不支持 not 条件，请先在 ProcessMind 中改写为正向条件")


def configured_max_combinations() -> int:
    raw_value = os.getenv(KMAI_MAX_COMBINATIONS_ENV, "").strip()
    if not raw_value:
        return DEFAULT_KMAI_MAX_COMBINATIONS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_KMAI_MAX_COMBINATIONS
    return value if value > 0 else DEFAULT_KMAI_MAX_COMBINATIONS


def configured_max_condition_objects() -> int:
    raw_value = os.getenv(KMAI_MAX_CONDITION_OBJECTS_ENV, "").strip()
    if not raw_value:
        return DEFAULT_KMAI_MAX_CONDITION_OBJECTS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_KMAI_MAX_CONDITION_OBJECTS
    return value if value > 0 else DEFAULT_KMAI_MAX_CONDITION_OBJECTS
