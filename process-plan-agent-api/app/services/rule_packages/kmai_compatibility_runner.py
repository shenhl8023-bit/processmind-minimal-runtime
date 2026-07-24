"""Execute the generated KmAI V1 files in-process for compatibility checks.

This intentionally mirrors the current KmAI V1 route selection behaviour so a
ProcessMind user can see semantic differences before copying files to KmAI.
"""

from __future__ import annotations

from typing import Any

from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.expression_engine import MISSING, resolve_field
from app.services.rule_packages.kmai_export import _VALUE_FACTOR_MAP, build_kmai_compatibility_export
from app.services.rule_packages.planner import plan_route


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


def _manual_factors(package: RulePackageV2, inputs: dict[str, Any], factor_schema: dict[str, Any]) -> dict[str, Any]:
    factors: dict[str, Any] = {}
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
            mapped = _VALUE_FACTOR_MAP.get((field_key, str(item)))
            if mapped:
                factors[mapped] = True

    for definition in factor_schema.get("factors", []):
        key = str(definition.get("factor_key") or "")
        description = str(definition.get("description") or "")
        if "ProcessMind 字段 " in description:
            field_key = description.rsplit("ProcessMind 字段 ", 1)[-1].strip(" 。")
            value = resolve_field(inputs, field_key)
            if value is not MISSING:
                factors[key] = value
        elif "特殊要求：" in str(definition.get("name") or ""):
            requirement = str(definition.get("name")).split("特殊要求：", 1)[-1]
            selected = resolve_field(inputs, "special.requirements")
            factors[key] = isinstance(selected, list) and requirement in selected
    return factors


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


def compare_kmai_v1(package: RulePackageV2, inputs: dict[str, Any]) -> dict[str, Any]:
    exported = build_kmai_compatibility_export(package)
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
            "warnings": [issue.model_dump() for issue in exported.warnings],
            "errors": [issue.model_dump() for issue in exported.errors],
            "manual_factors": {},
            "semantic_gaps": [],
        }

    files = exported.files
    factors = _manual_factors(package, inputs, files["factor_schema.json"])
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
    return {
        "compatible": not only_v2 and not only_kmai,
        "v2_process_ids": v2_ids,
        "v2_matched_rule_ids": [trace.rule_id for trace in v2_plan.traces if trace.matched],
        "kmai_process_ids": kmai_process_ids,
        "kmai_matched_rule_ids": kmai_rule_ids,
        "only_v2_process_ids": only_v2,
        "only_kmai_process_ids": only_kmai,
        "warnings": [issue.model_dump() for issue in exported.warnings],
        "errors": [],
        "manual_factors": factors,
        "semantic_gaps": gaps,
    }
