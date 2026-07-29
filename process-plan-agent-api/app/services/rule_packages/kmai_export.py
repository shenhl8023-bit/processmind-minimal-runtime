"""Build drop-in KmAI v1 runtime files from a ProcessMind V2 rule package."""

from __future__ import annotations

import hashlib
import os
import re
from itertools import product
from typing import Any

from app.services.rule_packages.contracts import (
    ConditionNode,
    KmaiCompatibilityExport,
    KmaiCompatibilityIssue,
    KmaiMappingUsageSnapshot,
    RulePackageV2,
    ValidationIssue,
)
from app.services.rule_packages.kmai_mapping_registry import (
    BUILTIN_FACTOR_SPECS as _FACTOR_SPECS,
    KmaiMappingRegistry,
    builtin_factor_catalog,
    builtin_mapping_registry,
    normalize_mapping_value,
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


def _issue(
    code: str,
    message: str,
    path: str = "",
    **details: Any,
) -> KmaiCompatibilityIssue:
    return KmaiCompatibilityIssue(code=code, path=path, message=message, **details)


class _UnmappedMappingValue(ValueError):
    def __init__(self, field: str, value: str):
        self.field = field
        self.value = value
        super().__init__(f"KmAI mapping is required for {field}: {value}")


class _IncompatibleMappingTarget(ValueError):
    def __init__(self, field: str, value: str, factor_key: str, value_type: str):
        self.field = field
        self.value = value
        self.factor_key = factor_key
        self.value_type = value_type
        super().__init__(
            f"KmAI presence mapping {field}={value} cannot target "
            f"{factor_key} ({value_type}); a boolean factor is required"
        )


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
        "category": "manual_override",
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


def _leaf_condition(
    package: RulePackageV2,
    node: ConditionNode,
    dynamic_factors: dict[str, dict[str, Any]],
    warnings: list[ValidationIssue],
    path: str,
    mapping_registry: KmaiMappingRegistry,
    mapping_usages: dict[str, KmaiMappingUsageSnapshot],
) -> list[list[dict[str, Any]]]:
    field = node.field or ""
    op = node.op or ""
    if field == "material.grade":
        mapped = _OPERATOR_MAP.get(op)
        if mapped:
            return [[{"factor_key": "material_grade", "op": mapped, "value": node.value}]]

    if field in {"cad.features", "precision.grades", "special.requirements"}:
        values = node.value if isinstance(node.value, list) else [node.value]
        factor_keys: list[str] = []
        catalog_by_key = {item.factor_key: item for item in builtin_factor_catalog()}
        for value in values:
            snapshot = mapping_registry.resolve(field, str(value))
            factor_key = snapshot.target_factor_key if snapshot is not None else None
            if snapshot is not None:
                if snapshot.mapping_mode == "existing_factor":
                    catalog_item = catalog_by_key.get(snapshot.target_factor_key)
                    value_type = catalog_item.value_type if catalog_item is not None else "unknown"
                    if value_type != "boolean":
                        raise _IncompatibleMappingTarget(
                            field,
                            normalize_mapping_value(value),
                            snapshot.target_factor_key,
                            value_type,
                        )
                mapping_usages[snapshot.mapping_identity] = KmaiMappingUsageSnapshot.model_validate(
                    snapshot.model_dump(mode="json")
                )
                if snapshot.mapping_mode == "manual_factor":
                    _mapped_manual_factor(snapshot, dynamic_factors)
            if not factor_key and field == "special.requirements":
                factor_key = _dynamic_special_requirement_factor(str(value), dynamic_factors)
                warnings.append(
                    _issue(
                        "kmai_manual_override_required",
                        f"特殊要求“{value}”将作为 KmAI 手工布尔因子 {factor_key} 输入。",
                        path,
                    )
                )
            if not factor_key:
                raise _UnmappedMappingValue(field, normalize_mapping_value(value))
            factor_keys.append(factor_key)
        leaves = [{"factor_key": factor_key, "op": "=", "value": True} for factor_key in factor_keys]
        if op in {"contains", "eq", "contains_all"}:
            return [leaves]
        if op in {"contains_any", "in"}:
            return [[leaf] for leaf in leaves]
        raise ValueError(f"字段 {field} 不支持转换操作符：{op}")

    mapped = _OPERATOR_MAP.get(op)
    if not mapped:
        raise ValueError(f"KmAI V1 不支持操作符：{op}")
    factor_key = _dynamic_factor(package, field, dynamic_factors)
    warnings.append(
        _issue(
            "kmai_manual_override_required",
            f"字段 {field} 需由 KmAI manual.factor_overrides 提供，因素键为 {factor_key}",
            path,
        )
    )
    return [[{"factor_key": factor_key, "op": mapped, "value": node.value}]]


def _condition_dnf(
    package: RulePackageV2,
    node: ConditionNode,
    dynamic_factors: dict[str, dict[str, Any]],
    warnings: list[ValidationIssue],
    path: str,
    mapping_registry: KmaiMappingRegistry,
    mapping_usages: dict[str, KmaiMappingUsageSnapshot],
) -> list[list[dict[str, Any]]]:
    if node.field is not None:
        return _leaf_condition(
            package,
            node,
            dynamic_factors,
            warnings,
            path,
            mapping_registry,
            mapping_usages,
        )
    if node.all_conditions is not None:
        groups = [
            _condition_dnf(
                package,
                child,
                dynamic_factors,
                warnings,
                f"{path}.all[{index}]",
                mapping_registry,
                mapping_usages,
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
                    mapping_registry,
                    mapping_usages,
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


def _collect_unmapped_mapping_values(
    node: ConditionNode,
    mapping_registry: KmaiMappingRegistry,
    unmapped_mappings: dict[tuple[str, str], dict[str, Any]],
    rule_id: str,
) -> bool:
    """Collect every unresolved CAD/precision value before converting a rule."""
    if node.field is not None:
        if node.field not in {"cad.features", "precision.grades"}:
            return False
        values = node.value if isinstance(node.value, list) else [node.value]
        unresolved = False
        for value in values:
            normalized_value = normalize_mapping_value(value)
            if mapping_registry.resolve(node.field, normalized_value) is not None:
                continue
            details = unmapped_mappings.setdefault(
                (node.field, normalized_value),
                {"occurrences": 0, "rule_refs": set()},
            )
            details["occurrences"] += 1
            details["rule_refs"].add(rule_id)
            unresolved = True
        return unresolved

    children = node.all_conditions or node.any_conditions
    if children is not None:
        return any(
            [
                _collect_unmapped_mapping_values(
                    child,
                    mapping_registry,
                    unmapped_mappings,
                    rule_id,
                )
                for child in children
            ]
        )
    if node.not_condition is not None:
        return _collect_unmapped_mapping_values(
            node.not_condition,
            mapping_registry,
            unmapped_mappings,
            rule_id,
        )
    return False


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
    mapping_registry: KmaiMappingRegistry,
    mapping_usages: dict[str, KmaiMappingUsageSnapshot],
    unmapped_mappings: dict[tuple[str, str], dict[str, Any]],
) -> dict[str, Any]:
    rules: list[dict[str, Any]] = []
    generated_combination_count = 0
    generated_condition_object_count = 0
    for rule_index, rule in enumerate(package.route_rules.rules):
        path = f"route_rules.rules[{rule_index}]"
        if _collect_unmapped_mapping_values(
            rule.when,
            mapping_registry,
            unmapped_mappings,
            rule.rule_id,
        ):
            continue
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
                mapping_registry,
                mapping_usages,
            )
        except _UnmappedMappingValue as exc:
            details = unmapped_mappings.setdefault(
                (exc.field, exc.value),
                {"occurrences": 0, "rule_refs": set()},
            )
            details["occurrences"] += 1
            details["rule_refs"].add(rule.rule_id)
            continue
        except _IncompatibleMappingTarget as exc:
            errors.append(
                _issue(
                    "kmai_mapping_factor_type_incompatible",
                    str(exc),
                    f"{path}.when",
                    field=exc.field,
                    value=exc.value,
                )
            )
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
    mapping_registry: KmaiMappingRegistry | None = None,
    *,
    max_combinations: int | None = None,
    max_condition_objects: int | None = None,
) -> KmaiCompatibilityExport:
    errors: list[ValidationIssue] = []
    warnings: list[ValidationIssue] = []
    dynamic_factors: dict[str, dict[str, Any]] = {}
    registry = mapping_registry or builtin_mapping_registry()
    mapping_usages: dict[str, KmaiMappingUsageSnapshot] = {}
    unmapped_mappings: dict[tuple[str, str], dict[str, Any]] = {}
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
        registry,
        mapping_usages,
        unmapped_mappings,
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

    suggested_existing_factors = [
        item.factor_key
        for item in builtin_factor_catalog()
        if item.value_type == "boolean"
    ]
    for (field, value), details in sorted(unmapped_mappings.items()):
        errors.append(
            _issue(
                "kmai_mapping_required",
                f"字段 {field} 存在需要映射到 KmAI 因素的值：{value}",
                field=field,
                value=value,
                occurrences=details["occurrences"],
                rule_refs=sorted(details["rule_refs"]),
                suggested_existing_factors=suggested_existing_factors,
                can_create_manual_factor=True,
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
        mapping_signature=registry.signature,
        mapping_usages=sorted(mapping_usages.values(), key=lambda item: item.mapping_identity),
    )
