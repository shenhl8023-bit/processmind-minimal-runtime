"""Execute the generated KmAI V1 files in-process for compatibility checks.

This intentionally mirrors the current KmAI V1 route selection behaviour so a
ProcessMind user can see semantic differences before copying files to KmAI.
"""

from __future__ import annotations

import hashlib
from typing import Any

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.expression_engine import MISSING, resolve_field
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_mapping_registry import (
    KmaiMappingRegistry,
    builtin_mapping_registry,
)
from app.services.rule_packages.planner import plan_route


def _response_issues(issues) -> list[dict[str, Any]]:
    return [
        issue.model_dump(mode="json", include={"code", "path", "message"})
        for issue in issues
    ]


def _compare(actual: Any, op: str, expected: Any) -> bool:
    if op == "=":
        return actual == expected
    if op == "!=":
        return actual != expected
    if op == ">":
        return actual is not None and actual > expected
    if op == ">=":
        return actual is not None and actual >= expected
    if op == "<":
        return actual is not None and actual < expected
    if op == "<=":
        return actual is not None and actual <= expected
    if op == "in":
        return actual in expected if isinstance(expected, (list, tuple, set)) else False
    if op == "exists":
        return actual is not None
    return False


def _manual_factors(
    package: RulePackageV2,
    inputs: dict[str, Any],
    factor_schema: dict[str, Any],
    mapping_registry: KmaiMappingRegistry,
) -> tuple[dict[str, Any], set[str], list[str]]:
    factors: dict[str, Any] = {}
    persisted_manual_keys = {
        snapshot.target_factor_key
        for snapshot in mapping_registry.snapshots
        if snapshot.mapping_mode == "manual_factor"
    }
    for definition in factor_schema.get("factors", []):
        key = str(definition.get("factor_key") or "")
        if not key:
            continue
        default = definition.get("default_value")
        factors[key] = default if default is not None else (False if definition.get("value_type") == "boolean" else None)

    material = resolve_field(inputs, "material.grade")
    if material is not MISSING:
        factors["material_grade"] = material

    for field_key in ("cad.features", "precision.grades", "special.requirements"):
        value = resolve_field(inputs, field_key)
        values = value if isinstance(value, list) else []
        for item in values:
            snapshot = mapping_registry.resolve(field_key, str(item))
            if snapshot:
                factors[snapshot.target_factor_key] = snapshot.mapping_mode == "existing_factor"

    selected_requirements = resolve_field(inputs, "special.requirements")
    if isinstance(selected_requirements, list):
        for requirement in selected_requirements:
            digest = hashlib.sha256(str(requirement).encode("utf-8")).hexdigest()[:12]
            factor_key = f"processmind_special_{digest}"
            if factor_key in factors and factor_key not in persisted_manual_keys:
                factors[factor_key] = True

    for definition in factor_schema.get("factors", []):
        key = str(definition.get("factor_key") or "")
        if key in persisted_manual_keys:
            continue
        description = str(definition.get("description") or "")
        if "ProcessMind 字段 " in description and definition.get("category") == "processmind_input":
            field_key = description.rsplit("ProcessMind 字段 ", 1)[-1].strip(" 。")
            value = resolve_field(inputs, field_key)
            if value is not MISSING:
                factors[key] = value
    overrides = resolve_field(inputs, "manual.factor_overrides")
    explicit_overrides = overrides if isinstance(overrides, dict) else {}
    definitions_by_key = {
        str(definition.get("factor_key") or ""): definition
        for definition in factor_schema.get("factors", [])
        if definition.get("factor_key")
    }
    invalid_override_gaps: list[str] = []
    for key, value in explicit_overrides.items():
        if key in factors:
            definition = definitions_by_key.get(key, {})
            if definition.get("value_type") == "boolean" and type(value) is not bool:
                invalid_override_gaps.append(
                    f"manual.factor_overrides invalid value for {key}: expected exact JSON boolean"
                )
                continue
            factors[key] = value

    manual_keys = persisted_manual_keys | {
        str(definition.get("factor_key") or "")
        for definition in factor_schema.get("factors", [])
        if definition.get("source_mode") == "manual_override"
        and definition.get("category") not in {"processmind_input", "processmind_special_requirement"}
    }
    missing_overrides = {
        key for key in manual_keys
        if key not in explicit_overrides
    }
    return factors, missing_overrides, invalid_override_gaps


def _run_v1(catalog: dict[str, Any], rules: dict[str, Any], factors: dict[str, Any]) -> tuple[list[str], list[str]]:
    included: set[str] = set()
    excluded: set[str] = set()
    matched_rules: list[str] = []
    active_rules = sorted(
        [rule for rule in rules.get("rules", []) if rule.get("enabled", True)],
        key=lambda item: item.get("priority", 0),
        reverse=True,
    )
    for rule in active_rules:
        conditions = rule.get("when", {}).get("all", [])
        if not all(_compare(factors.get(condition.get("factor_key")), condition.get("op", "="), condition.get("value")) for condition in conditions):
            continue
        matched_rules.append(str(rule.get("rule_id") or ""))
        action = rule.get("then", {})
        included.update(str(item) for item in action.get("include_process_keys", []))
        excluded.update(str(item) for item in action.get("exclude_process_keys", []))
    for process in catalog.get("processes", []):
        if process.get("default_included"):
            included.add(str(process.get("process_key")))
    included.difference_update(excluded)
    ordered = sorted(
        [process for process in catalog.get("processes", []) if process.get("enabled", True) and process.get("process_key") in included],
        key=lambda item: (item.get("sequence", 0), str(item.get("process_key") or "")),
    )
    return [str(item.get("process_key")) for item in ordered], matched_rules


def compare_kmai_v1(
    package: RulePackageV2,
    inputs: dict[str, Any],
    *,
    mapping_registry: KmaiMappingRegistry | None = None,
) -> dict[str, Any]:
    registry = mapping_registry or builtin_mapping_registry()
    exported = build_kmai_compatibility_export(package, mapping_registry=registry)
    v2_plan = plan_route(package, inputs)
    if not exported.valid:
        return {
            "compatible": False,
            "v2_process_ids": v2_plan.selected_process_ids,
            "v2_matched_rule_ids": [trace.rule_id for trace in v2_plan.traces if trace.matched],
            "kmai_process_ids": [],
            "kmai_matched_rule_ids": [],
            "only_v2_process_ids": list(v2_plan.selected_process_ids),
            "only_kmai_process_ids": [],
            "warnings": _response_issues(exported.warnings),
            "errors": _response_issues(exported.errors),
            "manual_factors": {},
            "semantic_gaps": [],
        }

    files = exported.files
    factors, missing_overrides, invalid_override_gaps = _manual_factors(
        package,
        inputs,
        files["factor_schema.json"],
        registry,
    )
    kmai_process_ids, kmai_rule_ids = _run_v1(files["route_catalog.json"], files["route_rules.json"], factors)
    v2_ids = list(v2_plan.selected_process_ids)
    only_v2 = [process_id for process_id in v2_ids if process_id not in kmai_process_ids]
    only_kmai = [process_id for process_id in kmai_process_ids if process_id not in v2_ids]
    gaps: list[str] = []
    enabled_relations = [relation for relation in package.route_rules.process_relations if relation.enabled]
    if enabled_relations:
        gaps.append("KmAI V1 当前执行器不会按 process_relations 做依赖、互斥和先后排序；测试结果会据实显示差异。")
    if any(issue.code == "kmai_manual_override_required" for issue in exported.warnings):
        gaps.append("部分条件需要 KmAI 通过 manual.factor_overrides 传入；本页已按 ProcessMind 输入模拟这些值。")
    gaps.extend(invalid_override_gaps)
    gaps.extend(
        f"manual.factor_overrides missing required value for {factor_key}"
        for factor_key in sorted(missing_overrides)
    )
    return {
        "compatible": not only_v2 and not only_kmai,
        "v2_process_ids": v2_ids,
        "v2_matched_rule_ids": [trace.rule_id for trace in v2_plan.traces if trace.matched],
        "kmai_process_ids": kmai_process_ids,
        "kmai_matched_rule_ids": kmai_rule_ids,
        "only_v2_process_ids": only_v2,
        "only_kmai_process_ids": only_kmai,
        "warnings": _response_issues(exported.warnings),
        "errors": [],
        "manual_factors": factors,
        "semantic_gaps": gaps,
    }
