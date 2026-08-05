"""Factor and historical mapping builders for KmAI V1 exports."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Literal

from app.services.rule_packages.contracts import ConditionNode, RulePackageV2
from app.services.rule_packages.kmai_export_context import (
    FactorRegistry,
    KmaiExportContext,
)


# KmAI's immutable runtime schema. Keep these IDs stable for packages replayed
# after the legacy mapping registry has been removed.
_FACTOR_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    ("F001", "material_grade", "\u6750\u6599\u724c\u53f7", "material", "enum"),
    ("F002", "part_type", "\u96f6\u4ef6\u7c7b\u578b", "part", "enum"),
    ("F003", "has_flat_or_plane", "\u6241\u4f4d/\u5e73\u9762", "feature", "boolean"),
    ("F004", "has_slot_feature", "\u69fd\u7c7b\u7279\u5f81", "feature", "boolean"),
    ("F005", "has_standard_or_aux_hole", "\u666e\u901a\u5b54/\u8f85\u52a9\u5b54", "feature", "boolean"),
    ("F005A", "has_center_through_hole", "\u4e2d\u95f4\u901a\u5b54", "feature", "boolean"),
    ("F006", "has_reamed_or_precision_hole", "\u94f0\u5b54/\u7cbe\u5b54", "feature", "boolean"),
    ("F007", "has_shaped_hole_or_cut_flat", "\u578b\u5b54/\u5272\u6241", "feature", "boolean"),
    ("F008", "has_post_stage_added_hole", "\u540e\u6bb5\u8865\u5145\u5b54", "feature", "boolean"),
    ("F009", "has_hole_finish_machining", "\u5b54\u7cbe\u52a0\u5de5", "precision", "boolean"),
    ("F010", "requires_honing", "\u73e9\u5b54\u8981\u6c42", "precision", "boolean"),
    ("F011", "requires_hole_lapping", "\u7814\u5b54\u8981\u6c42", "precision", "boolean"),
    ("F012", "requires_outer_diameter_grinding", "\u5916\u5706\u78e8\u524a", "precision", "boolean"),
    ("F013", "requires_end_face_grinding", "\u7aef\u9762\u78e8\u524a", "precision", "boolean"),
    ("F014", "requires_slot_grinding", "\u69fd\u78e8\u524a", "precision", "boolean"),
    ("F015", "requires_outer_diameter_lapping", "\u7814\u5916\u5706", "precision", "boolean"),
    ("F016", "uses_center_hole_location", "\u9876\u5c16\u5b54\u5b9a\u4f4d", "precision", "boolean"),
    ("F017", "needs_stress_relief", "\u53bb\u5e94\u529b", "heat_treatment", "boolean"),
    ("F018", "needs_quenching", "\u6dec\u706b", "heat_treatment", "boolean"),
    ("F019", "needs_vacuum_quenching", "\u771f\u7a7a\u6dec\u706b", "heat_treatment", "boolean"),
    ("F020", "has_nitrided_layer", "\u6e17\u6c2e\u5c42", "heat_treatment", "boolean"),
    ("F021", "needs_chromic_acid_anodizing", "\u94ec\u9178\u9633\u6781\u5316", "surface_treatment", "boolean"),
    ("F022", "needs_hard_anodizing", "\u786c\u8d28\u9633\u6781\u5316", "surface_treatment", "boolean"),
    ("F023", "needs_marking", "\u6807\u5370/\u6807\u523b", "inspection_marking", "boolean"),
    ("F024", "needs_crack_inspection", "\u88c2\u7eb9\u68c0\u6d4b", "inspection_marking", "boolean"),
    ("F025", "needs_burn_inspection", "\u70e7\u4f24\u68c0\u67e5", "inspection_marking", "boolean"),
    ("F026", "needs_ndt_inspection", "\u65e0\u635f\u68c0\u6d4b", "inspection_marking", "boolean"),
)

_BUILTIN_LEGACY_VALUE_FACTORS = {
    ("cad.features", "\u6241\u4f4d/\u5e73\u9762"): "has_flat_or_plane",
    ("cad.features", "\u69fd\u7c7b\u7279\u5f81"): "has_slot_feature",
    ("cad.features", "\u666e\u901a\u5b54/\u8f85\u52a9\u5b54"): "has_standard_or_aux_hole",
    ("cad.features", "\u94f0\u5b54/\u7cbe\u5b54"): "has_reamed_or_precision_hole",
    ("cad.features", "\u578b\u5b54/\u5272\u6241"): "has_shaped_hole_or_cut_flat",
    ("cad.features", "\u9876\u5c16\u5b54"): "uses_center_hole_location",
}


def normalize_legacy_adapter_value(value: object) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", str(value))).strip()


@dataclass(frozen=True)
class LegacyFactorAdapterEntry:
    source_field: str
    source_value: str
    mapping_mode: Literal["existing_factor", "manual_factor"]
    target_factor_key: str
    target_factor_name: str
    target_factor_category: str


def legacy_mapping_snapshot_from_validation_report(
    raw_json: str | None,
) -> list[LegacyFactorAdapterEntry]:
    """Load immutable historical mappings from a package validation report."""
    report = json.loads(raw_json or "{}")
    snapshots = report.get("kmai_compatibility", {}).get("mapping_snapshot", [])
    if not isinstance(snapshots, list):
        return []
    entries: list[LegacyFactorAdapterEntry] = []
    for item in snapshots:
        if not isinstance(item, dict):
            raise ValueError("invalid historical mapping snapshot")
        mode = str(item.get("mapping_mode") or "")
        if mode not in {"existing_factor", "manual_factor"}:
            raise ValueError(f"unsupported historical mapping mode: {mode}")
        entries.append(
            LegacyFactorAdapterEntry(
                source_field=str(item["source_field"]),
                source_value=str(item["source_value"]),
                mapping_mode=mode,
                target_factor_key=str(item["target_factor_key"]),
                target_factor_name=str(item["target_factor_name"]),
                target_factor_category=str(item["target_factor_category"]),
            )
        )
    return entries


def _field_options(package: RulePackageV2, key: str) -> list[str]:
    for field in package.input_schema.fields:
        if field.key == key:
            return [option.value for option in field.options if option.value]
    return []


def _walk_condition_values(node: ConditionNode, field: str) -> list[str]:
    values: list[str] = []
    if node.field == field:
        raw = node.value if isinstance(node.value, list) else [node.value]
        values.extend(str(item) for item in raw if item not in (None, ""))
    for child in node.all_conditions or []:
        values.extend(_walk_condition_values(child, field))
    for child in node.any_conditions or []:
        values.extend(_walk_condition_values(child, field))
    if node.not_condition is not None:
        values.extend(_walk_condition_values(node.not_condition, field))
    return values


def _material_options(package: RulePackageV2) -> list[str]:
    values = _field_options(package, "material.grade")
    for rule in package.route_rules.rules:
        values.extend(_walk_condition_values(rule.when, "material.grade"))
    return list(dict.fromkeys(value for value in values if value))


def build_factor_schema(package: RulePackageV2, registry: FactorRegistry) -> dict[str, Any]:
    material_options = _material_options(package)
    factors: list[dict[str, Any]] = []
    for factor_id, factor_key, name, category, value_type in _FACTOR_SPECS:
        options: list[str] = []
        if factor_key == "material_grade":
            options = material_options
        elif factor_key == "part_type":
            options = _field_options(package, "part.type") or ["\u6d3b\u95e8", "\u886c\u5957"]
        factors.append({
            "factor_key": factor_key, "factor_id": factor_id, "name": name,
            "category": category, "value_type": value_type, "multiple": False,
            "required": factor_key == "material_grade",
            "source_mode": "cad" if category in {"feature", "precision"} else "manual",
            "default_value": False if value_type == "boolean" else None,
            "options": options,
            "description": f"\u7531 ProcessMind \u89c4\u5219\u5305\u5bfc\u51fa\u7684 KmAI \u8fd0\u884c\u56e0\u7d20\uff1a{name}\u3002",
        })
    factors.extend(registry.values())
    return {
        "schema_version": "1.0",
        "dataset_id": f"processmind_project_{package.manifest.project_id}_factors",
        "dataset_name": f"{package.manifest.package_name} - KmAI \u56e0\u7d20\u5b9a\u4e49",
        "description": "\u7531 ProcessMind V2 \u89c4\u5219\u5305\u81ea\u52a8\u8f6c\u6362\uff0c\u4f9b KmAI process-route-generator \u76f4\u63a5\u4f7f\u7528\u3002",
        "factors": factors,
    }


def build_factor_schema_for_context(context: KmaiExportContext) -> dict[str, Any]:
    """Build the factor schema from one export's shared state."""
    return build_factor_schema(context.package, context.registry)


def _set_factor_rule(rule_id: str, priority: int, conditions: list[dict[str, Any]], factor_key: str, value: Any) -> dict[str, Any]:
    return {"rule_id": rule_id, "enabled": True, "priority": priority, "when": {"all": conditions}, "then": {"set_factors": [{"factor_key": factor_key, "value": value, "write_mode": "overwrite"}]}}


def _cad_condition(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": "cad_feature", "match_mode": "exists", "filters": filters}]


def build_factor_expansion_rules(package: RulePackageV2) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for index, material in enumerate(_material_options(package), start=1):
        rules.append(_set_factor_rule(f"PM-MAT-{index:03d}", 200, [{"source": "input", "field": "material_grade", "op": "=", "value": material}], "material_grade", material))
    feature_rules = (
        ("PM-CAD-001", "has_flat_or_plane", [{"field": "canonical_feature", "op": "in", "value": ["\u5e73\u9762", "\u8f74\u7aef\u9762"]}]),
        ("PM-CAD-002", "has_slot_feature", [{"field": "canonical_feature", "op": "in", "value": ["U\u5f62\u7aef\u9762\u73af\u69fd", "U\u5f62\u5916\u73af\u69fd", "U\u5f62\u76f4\u69fd", "V\u5f62\u73af\u69fd", "V\u5f62\u76f4\u69fd", "\u51f9\u69fd", "\u73af\u69fd", "\u8d8a\u7a0b\u69fd"]}]),
        ("PM-CAD-003", "has_standard_or_aux_hole", [{"field": "canonical_feature", "op": "in", "value": ["\u5b54", "\u9636\u68af\u5b54", "\u5b54\u53f0\u9636", "\u57cb\u5934\u5b54"]}, {"field": "precision_rank", "op": ">=", "value": 10}]),
        ("PM-CAD-004", "has_reamed_or_precision_hole", [{"field": "canonical_feature", "op": "in", "value": ["\u5b54", "\u9636\u68af\u5b54", "\u5b54\u53f0\u9636", "\u57cb\u5934\u5b54"]}, {"field": "precision_rank", "op": "<=", "value": 9}]),
        ("PM-CAD-005", "has_center_through_hole", [{"field": "group_path", "op": "contains", "value": "\u4e2d\u95f4\u901a\u5b54"}]),
        ("PM-CAD-006", "uses_center_hole_location", [{"field": "canonical_feature", "op": "=", "value": "\u4e2d\u5fc3\u5b54"}]),
        ("PM-CAD-007", "has_hole_finish_machining", [{"field": "canonical_feature", "op": "in", "value": ["\u5b54", "\u9636\u68af\u5b54", "\u5b54\u53f0\u9636", "\u57cb\u5934\u5b54"]}, {"field": "precision_rank", "op": "<=", "value": 9}]),
        ("PM-CAD-008", "requires_honing", [{"field": "canonical_feature", "op": "in", "value": ["\u5b54", "\u9636\u68af\u5b54", "\u5b54\u53f0\u9636", "\u57cb\u5934\u5b54"]}, {"field": "precision_rank", "op": "<=", "value": 7}]),
        ("PM-CAD-009", "requires_hole_lapping", [{"field": "canonical_feature", "op": "in", "value": ["\u5b54", "\u9636\u68af\u5b54", "\u5b54\u53f0\u9636", "\u57cb\u5934\u5b54"]}, {"field": "precision_rank", "op": "<=", "value": 6}]),
        ("PM-CAD-010", "requires_outer_diameter_grinding", [{"field": "canonical_feature", "op": "=", "value": "\u5916\u5706\u67f1\u9762"}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-011", "requires_end_face_grinding", [{"field": "canonical_feature", "op": "in", "value": ["\u5e73\u9762", "\u8f74\u7aef\u9762"]}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-012", "requires_slot_grinding", [{"field": "canonical_feature", "op": "in", "value": ["U\u5f62\u7aef\u9762\u73af\u69fd", "U\u5f62\u5916\u73af\u69fd", "U\u5f62\u76f4\u69fd", "V\u5f62\u73af\u69fd", "V\u5f62\u76f4\u69fd", "\u51f9\u69fd", "\u73af\u69fd", "\u8d8a\u7a0b\u69fd"]}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-013", "requires_outer_diameter_lapping", [{"field": "canonical_feature", "op": "=", "value": "\u5916\u5706\u67f1\u9762"}, {"field": "precision_rank", "op": "<=", "value": 6}]),
    )
    for rule_id, factor_key, filters in feature_rules:
        rules.append(_set_factor_rule(rule_id, 150, _cad_condition(filters), factor_key, True))
    manual_rules = (
        ("PM-MAN-001", "special_process_flags.shaped_hole_or_cut_flat", "=", True, "has_shaped_hole_or_cut_flat"),
        ("PM-MAN-002", "special_process_flags.post_stage_added_hole", "=", True, "has_post_stage_added_hole"),
        ("PM-MAN-003", "heat_treatment", "=", "\u53bb\u5e94\u529b", "needs_stress_relief"), ("PM-MAN-004", "heat_treatment", "=", "\u6dec\u706b", "needs_quenching"), ("PM-MAN-005", "heat_treatment", "=", "\u771f\u7a7a\u6dec\u706b", "needs_vacuum_quenching"), ("PM-MAN-006", "heat_treatment", "contains", "\u6e17\u6c2e", "has_nitrided_layer"),
        ("PM-MAN-007", "surface_treatments", "contains", "\u94ec\u9178\u9633\u6781\u5316", "needs_chromic_acid_anodizing"), ("PM-MAN-008", "surface_treatments", "contains", "\u786c\u8d28\u9633\u6781\u5316", "needs_hard_anodizing"), ("PM-MAN-009", "marking_methods", "contains", "\u6807\u5370", "needs_marking"), ("PM-MAN-010", "marking_methods", "contains", "\u6807\u523b", "needs_marking"),
        ("PM-MAN-011", "inspection_items", "contains", "\u88c2\u7eb9\u68c0\u6d4b", "needs_crack_inspection"), ("PM-MAN-012", "inspection_items", "contains", "\u78c1\u7c89\u68c0\u67e5", "needs_crack_inspection"), ("PM-MAN-013", "inspection_items", "contains", "\u70e7\u4f24\u68c0\u67e5", "needs_burn_inspection"), ("PM-MAN-014", "inspection_items", "contains", "\u65e0\u635f\u68c0\u6d4b", "needs_ndt_inspection"), ("PM-MAN-015", "inspection_items", "contains", "\u78c1\u7c89\u68c0\u67e5", "needs_ndt_inspection"), ("PM-MAN-016", "inspection_items", "contains", "\u88c2\u7eb9\u68c0\u67e5", "needs_ndt_inspection"), ("PM-MAN-017", "inspection_items", "contains", "\u8367\u5149\u68c0\u67e5", "needs_ndt_inspection"),
    )
    for rule_id, field, op, value, factor_key in manual_rules:
        rules.append(_set_factor_rule(rule_id, 120, [{"source": "manual", "field": field, "op": op, "value": value}], factor_key, True))
    return {"schema_version": "1.0", "dataset_id": f"processmind_project_{package.manifest.project_id}_factor_expansion", "dataset_name": f"{package.manifest.package_name} - KmAI \u56e0\u7d20\u5c55\u5f00\u89c4\u5219", "description": "\u628a KmAI \u7684 CAD \u5206\u7ec4\u7279\u5f81\u548c\u4eba\u5de5\u8865\u5145\u53c2\u6570\u5c55\u5f00\u4e3a ProcessMind \u89c4\u5219\u6240\u9700\u56e0\u7d20\u3002", "runtime_policy": {"rule_order": "priority_desc", "manual_overrides_last": True}, "input_contract": {"cad_features": "cad_input", "part_info": ["material_grade", "part_type"], "manual": ["heat_treatment", "surface_treatments", "inspection_items", "marking_methods", "special_process_flags", "factor_overrides"]}, "rules": rules}


def build_factor_expansion_rules_for_context(
    context: KmaiExportContext,
) -> dict[str, Any]:
    """Build factor expansion rules from one export's package snapshot."""
    return build_factor_expansion_rules(context.package)


def dynamic_factor(package: RulePackageV2, field_key: str, registry: FactorRegistry) -> str:
    factor_key = re.sub(r"[^a-zA-Z0-9_]+", "_", field_key.replace(".", "_")).strip("_").lower()
    factor_key = factor_key or f"input_field_{len(registry) + 1}"
    if factor_key in registry:
        return factor_key
    field = next((item for item in package.input_schema.fields if item.key == field_key), None)
    value_type = "string"; options: list[str] = []; default_value: Any = None
    if field is not None:
        value_type = {"single_select": "enum", "multi_select": "list", "boolean": "boolean", "number": "number"}.get(field.type, "string")
        options = [option.value for option in field.options]
        if value_type == "boolean": default_value = False
        elif value_type == "list": default_value = []
    registry.register(factor_key, {"factor_key": factor_key, "factor_id": f"F{900 + len(registry):03d}", "name": field.label if field is not None else field_key, "category": "processmind_input", "value_type": value_type, "multiple": value_type == "list", "required": bool(field.required) if field is not None else False, "source_mode": "manual_override", "default_value": default_value, "options": options, "description": f"KmAI \u9700\u901a\u8fc7 manual.factor_overrides \u63d0\u4f9b ProcessMind \u5b57\u6bb5 {field_key}\u3002"})
    return factor_key


def dynamic_special_requirement_factor(value: str, registry: FactorRegistry) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]; factor_key = f"processmind_special_{digest}"
    if factor_key not in registry:
        registry.register(factor_key, {"factor_key": factor_key, "factor_id": f"F{900 + len(registry):03d}", "name": f"\u7279\u6b8a\u8981\u6c42\uff1a{value}", "category": "processmind_special_requirement", "value_type": "boolean", "multiple": False, "required": False, "source_mode": "manual_override", "default_value": False, "options": [], "description": f"\u7531 ProcessMind \u7279\u6b8a\u8981\u6c42\u201c{value}\u201d\u81ea\u52a8\u751f\u6210\uff1bKmAI \u9700\u901a\u8fc7 manual.factor_overrides \u63d0\u4f9b true/false\u3002"})
    return factor_key


def mapped_manual_factor(snapshot: Any, registry: FactorRegistry) -> str:
    """Expose a persisted manual mapping as a KmAI boolean factor once per export."""
    factor_key = snapshot.target_factor_key
    if factor_key not in registry:
        registry.register(factor_key, {"factor_key": factor_key, "factor_id": f"F{900 + len(registry):03d}", "name": snapshot.target_factor_name, "category": snapshot.target_factor_category, "value_type": "boolean", "multiple": False, "required": False, "source_mode": "manual_override", "default_value": False, "options": [], "description": f"\u7531 ProcessMind \u6620\u5c04 {snapshot.source_field}={snapshot.source_value} \u751f\u6210\uff1bKmAI \u901a\u8fc7 manual.factor_overrides \u63d0\u4f9b true/false\u3002"})
    return factor_key


def legacy_adapter_key(source_field: str, source_value: object) -> tuple[str, str]:
    return source_field, normalize_legacy_adapter_value(source_value)


def _builtin_legacy_adapter() -> dict[tuple[str, str], LegacyFactorAdapterEntry]:
    metadata = {factor_key: (name, category) for _, factor_key, name, category, _ in _FACTOR_SPECS}
    return {legacy_adapter_key(field, value): LegacyFactorAdapterEntry(source_field=field, source_value=value, mapping_mode="existing_factor", target_factor_key=factor_key, target_factor_name=metadata[factor_key][0], target_factor_category=metadata[factor_key][1]) for (field, value), factor_key in _BUILTIN_LEGACY_VALUE_FACTORS.items()}


def builtin_legacy_mapping_snapshot() -> list[LegacyFactorAdapterEntry]:
    """Return the six code-owned adapters available to snapshot-less packages."""
    return sorted(_builtin_legacy_adapter().values(), key=lambda item: (item.source_field, item.source_value))
