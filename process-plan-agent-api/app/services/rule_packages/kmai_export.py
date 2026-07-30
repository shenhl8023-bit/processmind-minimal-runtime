"""Build drop-in KmAI v1 runtime files from a ProcessMind V2 rule package."""

from __future__ import annotations

import hashlib
import json
import os
import re
import unicodedata
from dataclasses import dataclass
from itertools import product
from typing import Any, Literal, Sequence

from app.services.rule_packages.contracts import (
    ConditionNode,
    KmaiCompatibilityExport,
    KmaiCompatibilityIssue,
    RulePackageV2,
    ValidationIssue,
)
from app.services.rule_packages.standard_factors import (
    STANDARD_FACTOR_CATALOG_VERSION,
    standard_factor_map,
    validate_factor_bindings,
)

KMAI_TARGET_DIRECTORY = r"KmMpsMcpServer\skills\process-route-generator\references\v1"
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
    ("F021", "needs_chromic_acid_anodizing", "\u94ec\u9178\u9633\u6781\u6c27\u5316", "surface_treatment", "boolean"),
    ("F022", "needs_hard_anodizing", "\u786c\u8d28\u9633\u6781\u6c27\u5316", "surface_treatment", "boolean"),
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


def _issue(
    code: str,
    message: str,
    path: str = "",
    **details: Any,
) -> KmaiCompatibilityIssue:
    return KmaiCompatibilityIssue(code=code, path=path, message=message, **details)


class StandardFactorExportError(ValueError):
    def __init__(self, code: Literal["standard_factor_unbound", "standard_factor_mismatch"], message: str):
        self.code = code
        super().__init__(message)


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


def _factor_schema(package: RulePackageV2, dynamic_factors: dict[str, dict[str, Any]]) -> dict[str, Any]:
    material_options = _material_options(package)
    factors: list[dict[str, Any]] = []
    for factor_id, factor_key, name, category, value_type in _FACTOR_SPECS:
        options: list[str] = []
        if factor_key == "material_grade":
            options = material_options
        elif factor_key == "part_type":
            options = _field_options(package, "part.type") or ["活门", "衬套"]
        factors.append(
            {
                "factor_key": factor_key,
                "factor_id": factor_id,
                "name": name,
                "category": category,
                "value_type": value_type,
                "multiple": False,
                "required": factor_key == "material_grade",
                "source_mode": "cad" if category in {"feature", "precision"} else "manual",
                "default_value": False if value_type == "boolean" else None,
                "options": options,
                "description": f"由 ProcessMind 规则包导出的 KmAI 运行因素：{name}。",
            }
        )
    factors.extend(dynamic_factors.values())
    return {
        "schema_version": "1.0",
        "dataset_id": f"processmind_project_{package.manifest.project_id}_factors",
        "dataset_name": f"{package.manifest.package_name} - KmAI 因素定义",
        "description": "由 ProcessMind V2 规则包自动转换，供 KmAI process-route-generator 直接使用。",
        "factors": factors,
    }


def _set_factor_rule(
    rule_id: str,
    priority: int,
    conditions: list[dict[str, Any]],
    factor_key: str,
    value: Any,
) -> dict[str, Any]:
    return {
        "rule_id": rule_id,
        "enabled": True,
        "priority": priority,
        "when": {"all": conditions},
        "then": {
            "set_factors": [
                {"factor_key": factor_key, "value": value, "write_mode": "overwrite"}
            ]
        },
    }


def _cad_condition(filters: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"source": "cad_feature", "match_mode": "exists", "filters": filters}]


def _factor_expansion_rules(package: RulePackageV2) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    for index, material in enumerate(_material_options(package), start=1):
        rules.append(
            _set_factor_rule(
                f"PM-MAT-{index:03d}",
                200,
                [{"source": "input", "field": "material_grade", "op": "=", "value": material}],
                "material_grade",
                material,
            )
        )

    feature_rules = (
        ("PM-CAD-001", "has_flat_or_plane", [{"field": "canonical_feature", "op": "in", "value": ["平面", "轴端面"]}]),
        ("PM-CAD-002", "has_slot_feature", [{"field": "canonical_feature", "op": "in", "value": ["U形端面环槽", "U形外环槽", "U形直槽", "V形环槽", "V形直槽", "凹槽", "环槽", "越程槽"]}]),
        ("PM-CAD-003", "has_standard_or_aux_hole", [{"field": "canonical_feature", "op": "in", "value": ["孔", "阶梯孔", "孔台阶", "埋头孔"]}, {"field": "precision_rank", "op": ">=", "value": 10}]),
        ("PM-CAD-004", "has_reamed_or_precision_hole", [{"field": "canonical_feature", "op": "in", "value": ["孔", "阶梯孔", "孔台阶", "埋头孔"]}, {"field": "precision_rank", "op": "<=", "value": 9}]),
        ("PM-CAD-005", "has_center_through_hole", [{"field": "group_path", "op": "contains", "value": "中间通孔"}]),
        ("PM-CAD-006", "uses_center_hole_location", [{"field": "canonical_feature", "op": "=", "value": "中心孔"}]),
        ("PM-CAD-007", "has_hole_finish_machining", [{"field": "canonical_feature", "op": "in", "value": ["孔", "阶梯孔", "孔台阶", "埋头孔"]}, {"field": "precision_rank", "op": "<=", "value": 9}]),
        ("PM-CAD-008", "requires_honing", [{"field": "canonical_feature", "op": "in", "value": ["孔", "阶梯孔", "孔台阶", "埋头孔"]}, {"field": "precision_rank", "op": "<=", "value": 7}]),
        ("PM-CAD-009", "requires_hole_lapping", [{"field": "canonical_feature", "op": "in", "value": ["孔", "阶梯孔", "孔台阶", "埋头孔"]}, {"field": "precision_rank", "op": "<=", "value": 6}]),
        ("PM-CAD-010", "requires_outer_diameter_grinding", [{"field": "canonical_feature", "op": "=", "value": "外圆柱面"}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-011", "requires_end_face_grinding", [{"field": "canonical_feature", "op": "in", "value": ["平面", "轴端面"]}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-012", "requires_slot_grinding", [{"field": "canonical_feature", "op": "in", "value": ["U形端面环槽", "U形外环槽", "U形直槽", "V形环槽", "V形直槽", "凹槽", "环槽", "越程槽"]}, {"field": "precision_rank", "op": "<=", "value": 8}]),
        ("PM-CAD-013", "requires_outer_diameter_lapping", [{"field": "canonical_feature", "op": "=", "value": "外圆柱面"}, {"field": "precision_rank", "op": "<=", "value": 6}]),
    )
    for rule_id, factor_key, filters in feature_rules:
        rules.append(_set_factor_rule(rule_id, 150, _cad_condition(filters), factor_key, True))

    manual_rules = (
        ("PM-MAN-001", "special_process_flags.shaped_hole_or_cut_flat", "=", True, "has_shaped_hole_or_cut_flat"),
        ("PM-MAN-002", "special_process_flags.post_stage_added_hole", "=", True, "has_post_stage_added_hole"),
        ("PM-MAN-003", "heat_treatment", "=", "去应力", "needs_stress_relief"),
        ("PM-MAN-004", "heat_treatment", "=", "淬火", "needs_quenching"),
        ("PM-MAN-005", "heat_treatment", "=", "真空淬火", "needs_vacuum_quenching"),
        ("PM-MAN-006", "heat_treatment", "contains", "渗氮", "has_nitrided_layer"),
        ("PM-MAN-007", "surface_treatments", "contains", "铬酸阳极化", "needs_chromic_acid_anodizing"),
        ("PM-MAN-008", "surface_treatments", "contains", "硬质阳极化", "needs_hard_anodizing"),
        ("PM-MAN-009", "marking_methods", "contains", "标印", "needs_marking"),
        ("PM-MAN-010", "marking_methods", "contains", "标刻", "needs_marking"),
        ("PM-MAN-011", "inspection_items", "contains", "裂纹检测", "needs_crack_inspection"),
        ("PM-MAN-012", "inspection_items", "contains", "磁粉检查", "needs_crack_inspection"),
        ("PM-MAN-013", "inspection_items", "contains", "烧伤检查", "needs_burn_inspection"),
        ("PM-MAN-014", "inspection_items", "contains", "无损检测", "needs_ndt_inspection"),
        ("PM-MAN-015", "inspection_items", "contains", "磁粉检查", "needs_ndt_inspection"),
        ("PM-MAN-016", "inspection_items", "contains", "裂纹检查", "needs_ndt_inspection"),
        ("PM-MAN-017", "inspection_items", "contains", "荧光检查", "needs_ndt_inspection"),
    )
    for rule_id, field, op, value, factor_key in manual_rules:
        rules.append(
            _set_factor_rule(
                rule_id,
                120,
                [{"source": "manual", "field": field, "op": op, "value": value}],
                factor_key,
                True,
            )
        )

    return {
        "schema_version": "1.0",
        "dataset_id": f"processmind_project_{package.manifest.project_id}_factor_expansion",
        "dataset_name": f"{package.manifest.package_name} - KmAI 因素展开规则",
        "description": "把 KmAI 的 CAD 分组特征和人工补充参数展开为 ProcessMind 规则所需因素。",
        "runtime_policy": {"rule_order": "priority_desc", "manual_overrides_last": True},
        "input_contract": {
            "cad_features": "cad_input",
            "part_info": ["material_grade", "part_type"],
            "manual": ["heat_treatment", "surface_treatments", "inspection_items", "marking_methods", "special_process_flags", "factor_overrides"],
        },
        "rules": rules,
    }


def _process_stage(phase: str, name: str) -> str:
    text = f"{phase} {name}"
    if any(token in name for token in ("阳极化", "镀铜", "除铜", "渗氮", "钝化")):
        return "surface_treatment"
    if any(token in text for token in ("调质", "正常化", "淬火", "热处理", "去应力", "回火")):
        return "heat_treatment"
    if any(token in text for token in ("专项检查", "终检", "检验", "检查")):
        return "inspection"
    if any(token in text for token in ("放行", "包装")):
        return "package"
    if any(token in text for token in ("热后", "精加工", "磨", "研", "珩")):
        return "finish"
    if any(token in text for token in ("准备", "下料", "备料")):
        return "prepare"
    if any(token in text for token in ("辅助", "清洗", "去毛刺")):
        return "auxiliary"
    return "rough_machining"


def _fallback_steps(name: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"\s*[/／]\s*", name) if part.strip()]
    return parts or [name]


def _route_catalog(package: RulePackageV2) -> tuple[dict[str, Any], dict[str, str]]:
    processes: list[dict[str, Any]] = []
    process_keys: dict[str, str] = {}
    relation_requires: dict[str, set[str]] = {}
    relation_after: dict[str, set[str]] = {}
    relation_conflicts: dict[str, set[str]] = {}
    for relation in package.route_rules.process_relations:
        if not relation.enabled:
            continue
        for target_id in relation.target_process_ids:
            if relation.relation_type in {"trigger_after", "order_after", "requires"}:
                relation_after.setdefault(target_id, set()).update(relation.source_process_ids)
            if relation.relation_type == "requires":
                relation_requires.setdefault(target_id, set()).update(relation.source_process_ids)
        if relation.relation_type == "conflicts":
            for source_id in relation.source_process_ids:
                for target_id in relation.target_process_ids:
                    relation_conflicts.setdefault(source_id, set()).add(target_id)
                    relation_conflicts.setdefault(target_id, set()).add(source_id)
    for index, process in enumerate(package.route_catalog.processes, start=1):
        process_key = process.process_id
        process_keys[process.process_id] = process_key
        step_names = [step.name for step in process.steps if step.name] or _fallback_steps(process.display_name)
        processes.append(
            {
                "process_key": process_key,
                "process_id": f"P{index:03d}",
                "process_name": process.display_name,
                # Optional ProcessMind metadata. KmAI v1 ignores unknown process
                # properties, so this keeps the original route contract intact.
                "template_group_aliases": [
                    alias.model_dump(mode="json")
                    for alias in process.template_group_aliases
                ],
                "process_type": "main" if process.main else "conditional",
                "stage": _process_stage(process.phase, process.display_name),
                "sequence": process.default_sequence,
                "enabled": True,
                "default_included": process.main,
                "requires_process_keys": sorted(set(process.constraints.requires) | relation_requires.get(process.process_id, set())),
                "must_run_after_process_keys": sorted(set(process.constraints.must_run_after) | relation_after.get(process.process_id, set())),
                "must_run_before_process_keys": sorted(process.constraints.must_run_before),
                "conflicts_with_process_keys": sorted(set(process.constraints.conflicts_with) | relation_conflicts.get(process.process_id, set())),
                "steps": [
                    {
                        "step_key": f"{process_key}_s{step_index:02d}",
                        "step_name": step_name,
                        "step_order": step_index,
                    }
                    for step_index, step_name in enumerate(step_names, start=1)
                ],
            }
        )
    relation_payload = [
        {
            "relation_id": relation.relation_id,
            "relation_type": relation.relation_type,
            "source_match": relation.source_match,
            "source_process_keys": relation.source_process_ids,
            "target_process_keys": relation.target_process_ids,
            "enabled": relation.enabled,
            "note": relation.reason,
        }
        for relation in package.route_rules.process_relations
    ]
    post_stage_bundles = [
        {
            "bundle_id": relation.relation_id,
            "trigger_mode": relation.source_match,
            "trigger_process_keys": relation.source_process_ids,
            "include_process_keys": relation.target_process_ids,
            "must_run_after_process_keys": relation.source_process_ids,
            "enabled": relation.enabled,
            "note": relation.reason,
        }
        for relation in package.route_rules.process_relations
        if relation.enabled and relation.relation_type == "trigger_after"
    ]
    return (
        {
            "schema_version": "1.0",
            "dataset_id": f"processmind_project_{package.manifest.project_id}_route_catalog",
            "dataset_name": f"{package.manifest.package_name} - KmAI 工序目录",
            "description": "由 ProcessMind V2 route_catalog.json 自动转换。",
            "post_stage_bundles": post_stage_bundles,
            "process_relations": relation_payload,
            "processes": processes,
        },
        process_keys,
    )


def _dynamic_factor(
    package: RulePackageV2,
    field_key: str,
    dynamic_factors: dict[str, dict[str, Any]],
) -> str:
    factor_key = re.sub(r"[^a-zA-Z0-9_]+", "_", field_key.replace(".", "_")).strip("_").lower()
    factor_key = factor_key or f"input_field_{len(dynamic_factors) + 1}"
    if factor_key in dynamic_factors:
        return factor_key
    field = next((item for item in package.input_schema.fields if item.key == field_key), None)
    value_type = "string"
    options: list[str] = []
    default_value: Any = None
    if field is not None:
        value_type = {
            "single_select": "enum",
            "multi_select": "list",
            "boolean": "boolean",
            "number": "number",
        }.get(field.type, "string")
        options = [option.value for option in field.options]
        if value_type == "boolean":
            default_value = False
        elif value_type == "list":
            default_value = []
    dynamic_factors[factor_key] = {
        "factor_key": factor_key,
        "factor_id": f"F{900 + len(dynamic_factors):03d}",
        "name": field.label if field is not None else field_key,
        "category": "processmind_input",
        "value_type": value_type,
        "multiple": value_type == "list",
        "required": bool(field.required) if field is not None else False,
        "source_mode": "manual_override",
        "default_value": default_value,
        "options": options,
        "description": f"KmAI 需通过 manual.factor_overrides 提供 ProcessMind 字段 {field_key}。",
    }
    return factor_key


def _dynamic_special_requirement_factor(
    value: str,
    dynamic_factors: dict[str, dict[str, Any]],
) -> str:
    digest = hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]
    factor_key = f"processmind_special_{digest}"
    if factor_key in dynamic_factors:
        return factor_key
    dynamic_factors[factor_key] = {
        "factor_key": factor_key,
        "factor_id": f"F{900 + len(dynamic_factors):03d}",
        "name": f"特殊要求：{value}",
        "category": "processmind_special_requirement",
        "value_type": "boolean",
        "multiple": False,
        "required": False,
        "source_mode": "manual_override",
        "default_value": False,
        "options": [],
        "description": f"由 ProcessMind 特殊要求“{value}”自动生成；KmAI 需通过 manual.factor_overrides 提供 true/false。",
    }
    return factor_key


def _mapped_manual_factor(snapshot: Any, dynamic_factors: dict[str, dict[str, Any]]) -> str:
    """Expose a persisted manual mapping as a KmAI boolean factor once per export."""
    factor_key = snapshot.target_factor_key
    if factor_key in dynamic_factors:
        return factor_key
    dynamic_factors[factor_key] = {
        "factor_key": factor_key,
        "factor_id": f"F{900 + len(dynamic_factors):03d}",
        "name": snapshot.target_factor_name,
        "category": snapshot.target_factor_category,
        "value_type": "boolean",
        "multiple": False,
        "required": False,
        "source_mode": "manual_override",
        "default_value": False,
        "options": [],
        "description": (
            f"由 ProcessMind 映射 {snapshot.source_field}={snapshot.source_value} 生成；"
            "KmAI 通过 manual.factor_overrides 提供 true/false。"
        ),
    }
    return factor_key


def _legacy_adapter_key(source_field: str, source_value: object) -> tuple[str, str]:
    return source_field, normalize_legacy_adapter_value(source_value)


def _builtin_legacy_adapter() -> dict[tuple[str, str], LegacyFactorAdapterEntry]:
    metadata = {
        factor_key: (name, category)
        for _, factor_key, name, category, _ in _FACTOR_SPECS
    }
    return {
        _legacy_adapter_key(field, value): LegacyFactorAdapterEntry(
            source_field=field,
            source_value=value,
            mapping_mode="existing_factor",
            target_factor_key=factor_key,
            target_factor_name=metadata[factor_key][0],
            target_factor_category=metadata[factor_key][1],
        )
        for (field, value), factor_key in _BUILTIN_LEGACY_VALUE_FACTORS.items()
    }


def builtin_legacy_mapping_snapshot() -> list[LegacyFactorAdapterEntry]:
    """Return the six code-owned adapters available to snapshot-less packages."""
    return sorted(
        _builtin_legacy_adapter().values(),
        key=lambda item: (item.source_field, item.source_value),
    )


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
    dynamic_factors: dict[str, dict[str, Any]],
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    if _manual_process_condition(node):
        field = node.field or ""
        factor_key = _dynamic_factor(package, field, dynamic_factors)
        dynamic_factors[factor_key].update(
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
        factor_key = _dynamic_factor(package, definition.source_field, dynamic_factors)
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
        entry = legacy_adapters.get(_legacy_adapter_key(field, value))
        if entry is None:
            raise StandardFactorExportError("standard_factor_unbound", f"historical condition is not covered by an immutable adapter: {field}")
        if entry.mapping_mode == "manual_factor":
            _mapped_manual_factor(entry, dynamic_factors)
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
    dynamic_factors: dict[str, dict[str, Any]],
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    return _fixed_leaf_condition(
        package,
        node,
        dynamic_factors,
        warnings,
        path,
        legacy_adapters,
    )


def _condition_dnf(
    package: RulePackageV2,
    node: ConditionNode,
    dynamic_factors: dict[str, dict[str, Any]],
    warnings: list[ValidationIssue],
    path: str,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> list[list[dict[str, Any]]]:
    if node.field is not None:
        return _leaf_condition(
            package,
            node,
            dynamic_factors,
            warnings,
            path,
            legacy_adapters,
        )
    if node.all_conditions is not None:
        groups = [
            _condition_dnf(
                package,
                child,
                dynamic_factors,
                warnings,
                f"{path}.all[{index}]",
                legacy_adapters,
            )
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
                _condition_dnf(
                    package,
                    child,
                    dynamic_factors,
                    warnings,
                    f"{path}.any[{index}]",
                    legacy_adapters,
                )
            )
        return clauses
    raise ValueError("KmAI V1 暂不支持 not 条件，请先在 ProcessMind 中改写为正向条件")


def _condition_expansion_size(node: ConditionNode) -> tuple[int, int]:
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
            child_clause_count, child_condition_object_count = _condition_expansion_size(child)
            # A Cartesian product repeats each side's conditions once per clause on the other side.
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
            child_clause_count, child_condition_object_count = _condition_expansion_size(child)
            clause_count += child_clause_count
            condition_object_count += child_condition_object_count
        return clause_count, condition_object_count
    raise ValueError("KmAI V1 暂不支持 not 条件，请先在 ProcessMind 中改写为正向条件")


def _configured_max_combinations() -> int:
    raw_value = os.getenv(KMAI_MAX_COMBINATIONS_ENV, "").strip()
    if not raw_value:
        return DEFAULT_KMAI_MAX_COMBINATIONS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_KMAI_MAX_COMBINATIONS
    return value if value > 0 else DEFAULT_KMAI_MAX_COMBINATIONS


def _configured_max_condition_objects() -> int:
    raw_value = os.getenv(KMAI_MAX_CONDITION_OBJECTS_ENV, "").strip()
    if not raw_value:
        return DEFAULT_KMAI_MAX_CONDITION_OBJECTS
    try:
        value = int(raw_value)
    except ValueError:
        return DEFAULT_KMAI_MAX_CONDITION_OBJECTS
    return value if value > 0 else DEFAULT_KMAI_MAX_CONDITION_OBJECTS


def _route_rules(
    package: RulePackageV2,
    process_keys: dict[str, str],
    dynamic_factors: dict[str, dict[str, Any]],
    errors: list[ValidationIssue],
    warnings: list[ValidationIssue],
    max_combinations: int,
    max_condition_objects: int,
    legacy_adapters: dict[tuple[str, str], LegacyFactorAdapterEntry] | None,
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    generated_combination_count = 0
    generated_condition_object_count = 0
    for rule_index, rule in enumerate(package.route_rules.rules):
        path = f"route_rules.rules[{rule_index}]"
        try:
            combination_count, condition_object_count = _condition_expansion_size(rule.when)
        except ValueError as exc:
            errors.append(_issue("kmai_condition_unsupported", str(exc), f"{path}.when"))
            continue
        projected_count = generated_combination_count + combination_count
        if combination_count > max_combinations or projected_count > max_combinations:
            errors.append(
                _issue(
                    "kmai_combination_limit_exceeded",
                    (
                        f"规则 {rule.rule_id} 的 all/any 条件将展开为 {combination_count} 个组合，"
                        f"累计组合数为 {projected_count}，超过上限 {max_combinations}。"
                        f"请缩小条件范围或调整 {KMAI_MAX_COMBINATIONS_ENV}。"
                    ),
                    f"{path}.when",
                )
            )
            continue
        projected_condition_object_count = (
            generated_condition_object_count + condition_object_count
        )
        if (
            condition_object_count > max_condition_objects
            or projected_condition_object_count > max_condition_objects
        ):
            errors.append(
                _issue(
                    "kmai_condition_object_limit_exceeded",
                    (
                        f"规则 {rule.rule_id} 的 all/any 条件展开后包含 {condition_object_count} 个条件对象，"
                        f"累计条件对象数为 {projected_condition_object_count}，"
                        f"超过上限 {max_condition_objects}。"
                        f"请缩小条件范围或调整 {KMAI_MAX_CONDITION_OBJECTS_ENV}。"
                    ),
                    f"{path}.when",
                )
            )
            continue
        try:
            clauses = _condition_dnf(
                package,
                rule.when,
                dynamic_factors,
                warnings,
                f"{path}.when",
                legacy_adapters,
            )
        except StandardFactorExportError as exc:
            errors.append(_issue(exc.code, str(exc), f"{path}.when"))
            continue
        except ValueError as exc:
            errors.append(_issue("kmai_condition_unsupported", str(exc), f"{path}.when"))
            continue
        generated_combination_count += len(clauses)
        generated_condition_object_count += sum(len(clause) for clause in clauses)
        include_keys = [process_keys[item] for item in rule.then.include_process_ids if item in process_keys]
        exclude_keys = [process_keys[item] for item in rule.then.exclude_process_ids if item in process_keys]
        missing_ids = [
            item
            for item in (*rule.then.include_process_ids, *rule.then.exclude_process_ids)
            if item not in process_keys
        ]
        if missing_ids:
            errors.append(
                _issue(
                    "kmai_process_reference_missing",
                    f"规则 {rule.rule_id} 引用了不存在的工序：{', '.join(missing_ids)}",
                    f"{path}.then",
                )
            )
            continue
        for clause_index, clause in enumerate(clauses, start=1):
            suffix = f".{clause_index}" if len(clauses) > 1 else ""
            rules.append(
                {
                    "rule_id": f"{rule.rule_id}{suffix}",
                    "enabled": rule.enabled,
                    "priority": rule.priority,
                    "when": {"all": clause},
                    "then": {
                        "include_process_keys": include_keys,
                        "exclude_process_keys": exclude_keys,
                    },
                    "confidence": "high",
                    "note": rule.then.reason,
                }
            )
    return {
        "schema_version": "1.0",
        "dataset_id": f"processmind_project_{package.manifest.project_id}_route_rules",
        "dataset_name": f"{package.manifest.package_name} - KmAI 路线规则",
        "description": "由 ProcessMind V2 route_rules.json 自动转换。",
        "rules": rules,
    }


def build_kmai_compatibility_export(
    package: RulePackageV2,
    *,
    legacy_mapping_snapshot: Sequence[LegacyFactorAdapterEntry] | None = None,
    max_combinations: int | None = None,
    max_condition_objects: int | None = None,
) -> KmaiCompatibilityExport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    dynamic_factors: dict[str, dict[str, Any]] = {}
    legacy_adapters = (
        {
            _legacy_adapter_key(entry.source_field, entry.source_value): entry
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
    route_catalog, process_keys = _route_catalog(package)
    route_rules = _route_rules(
        package,
        process_keys,
        dynamic_factors,
        errors,
        warnings,
        combination_limit,
        condition_object_limit,
        legacy_adapters,
    )
    factor_schema = _factor_schema(package, dynamic_factors)
    factor_expansion_rules = _factor_expansion_rules(package)

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
