"""Immutable ProcessMind standard-factor catalog and binding helpers."""

from __future__ import annotations

import unicodedata
from collections.abc import Iterable

from app.services.rule_packages.condition_contracts import CanonicalConditionField
from app.services.rule_packages.contracts import (
    ConditionNode,
    FactorBindingIssue,
    StandardFactorDefinition,
)


STANDARD_FACTOR_CATALOG_VERSION = "2026.11"


def _presence_factor(
    factor_id: str,
    label: str,
    category: str,
    source_field: str,
    canonical_value: str,
    kmai_factor_key: str,
) -> StandardFactorDefinition:
    return StandardFactorDefinition(
        factor_id=factor_id,
        label=label,
        category=category,
        source_field=source_field,
        canonical_value=canonical_value,
        allowed_operators=["contains", "eq"],
        kmai_factor_key=kmai_factor_key,
        kmai_value_mode="presence",
    )


def _scalar_factor(
    source_field: str,
    label: str,
    category: str,
    allowed_operators: list[str],
    *,
    source_field_aliases: list[str] | None = None,
) -> StandardFactorDefinition:
    suffix = source_field.rsplit(".", 1)[-1]
    return StandardFactorDefinition(
        factor_id=f"measurement.{suffix}",
        label=label,
        category=category,
        source_field=source_field,
        source_field_aliases=source_field_aliases or [],
        allowed_operators=allowed_operators,
        kmai_factor_key=source_field.replace(".", "_"),
        kmai_value_mode="condition_value",
        runtime_source="manual_override",
    )


_STANDARD_FACTORS = (
    StandardFactorDefinition(
        factor_id="material.grade",
        label="材料牌号",
        category="材料",
        source_field="material.grade",
        allowed_operators=["eq", "neq", "in"],
        kmai_factor_key="material_grade",
        kmai_value_mode="condition_value",
    ),
    _presence_factor("feature.flat_or_plane", "扁位/平面", "结构特征", "cad.features", "扁位/平面", "has_flat_or_plane"),
    _presence_factor("feature.slot", "槽类特征", "结构特征", "cad.features", "槽类特征", "has_slot_feature"),
    _presence_factor("feature.standard_or_aux_hole", "普通孔/辅助孔", "结构特征", "cad.features", "普通孔/辅助孔", "has_standard_or_aux_hole"),
    _presence_factor("feature.reamed_or_precision_hole", "铰孔/精孔", "结构特征", "cad.features", "铰孔/精孔", "has_reamed_or_precision_hole"),
    _presence_factor("feature.shaped_hole_or_cut_flat", "型孔/割扁", "结构特征", "cad.features", "型孔/割扁", "has_shaped_hole_or_cut_flat"),
    _presence_factor("feature.center_hole_location", "顶尖孔定位", "精度要求", "cad.features", "顶尖孔", "uses_center_hole_location"),
    _presence_factor("precision.hole_finish", "孔精加工", "精度要求", "precision.grades", "孔精加工", "has_hole_finish_machining"),
    _presence_factor("precision.honing", "珩孔要求", "精度要求", "precision.grades", "珩孔要求", "requires_honing"),
    _presence_factor("precision.hole_lapping", "研孔要求", "精度要求", "precision.grades", "研孔要求", "requires_hole_lapping"),
    _presence_factor("precision.outer_diameter_grinding", "外圆磨削", "精度要求", "precision.grades", "外圆磨削", "requires_outer_diameter_grinding"),
    _presence_factor("precision.end_face_grinding", "端面磨削", "精度要求", "precision.grades", "端面磨削", "requires_end_face_grinding"),
    _presence_factor("precision.slot_grinding", "槽磨削", "精度要求", "precision.grades", "槽磨削", "requires_slot_grinding"),
    _presence_factor("precision.outer_diameter_lapping", "研外圆", "精度要求", "precision.grades", "研外圆", "requires_outer_diameter_lapping"),
    _presence_factor("requirement.nitrided_layer", "渗氮层要求", "热处理", "special.requirements", "渗氮层要求", "has_nitrided_layer"),
    _presence_factor("requirement.chromic_acid_anodizing", "铬酸阳极化要求", "表面处理", "special.requirements", "铬酸阳极化要求", "needs_chromic_acid_anodizing"),
    _presence_factor("requirement.hard_anodizing", "硬质阳极化要求", "表面处理", "special.requirements", "硬质阳极化要求", "needs_hard_anodizing"),
    _presence_factor("requirement.traceability_marking", "追溯标印", "检验与标识", "special.requirements", "追溯标印", "needs_marking"),
    _presence_factor("requirement.nondestructive_testing", "无损检测要求", "检验与标识", "special.requirements", "无损检测要求", "needs_ndt_inspection"),
    _presence_factor("requirement.magnetic_particle_inspection", "磁粉检查要求", "检验与标识", "special.requirements", "磁粉检查要求", "needs_crack_inspection"),
    _presence_factor("requirement.burn_inspection", "烧伤检查要求", "检验与标识", "special.requirements", "烧伤检查要求", "needs_burn_inspection"),
    _scalar_factor("precision.outer_diameter_it", "外圆尺寸精度 IT", "尺寸精度", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("precision.inner_diameter_it", "内孔尺寸精度 IT", "尺寸精度", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("precision.dimension_it", "尺寸精度 IT", "尺寸精度", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("surface.roughness_ra", "表面粗糙度 Ra", "表面质量", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.roundness_mm", "圆度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.cylindricity_mm", "圆柱度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.coaxiality_mm", "同轴度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.runout_mm", "跳动公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.position_mm", "位置度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.flatness_mm", "平面度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("tolerance.perpendicularity_mm", "垂直度公差", "形位公差", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("geometry.diameter_mm", "特征直径", "几何尺寸", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("geometry.length_mm", "特征长度", "几何尺寸", ["eq", "gt", "gte", "lt", "lte", "between"]),
    _scalar_factor("mechanical.hardness_hrc", "目标硬度 HRC", "性能要求", ["eq", "gt", "gte", "lt", "lte", "between"], source_field_aliases=["target_hardness_hrc"]),
)


def standard_factors() -> list[StandardFactorDefinition]:
    """Return independent copies of the code-owned catalog."""
    return [factor.model_copy(deep=True) for factor in _STANDARD_FACTORS]


def standard_factor_map() -> dict[str, StandardFactorDefinition]:
    """Return independent copies keyed by stable ProcessMind factor ID."""
    return {factor.factor_id: factor.model_copy(deep=True) for factor in _STANDARD_FACTORS}


def _normalized_value(value: object) -> object:
    if not isinstance(value, str):
        return value
    return " ".join(unicodedata.normalize("NFKC", value).split())


def matching_standard_factors(
    node: ConditionNode,
    *,
    _catalog: Iterable[StandardFactorDefinition] | None = None,
) -> list[StandardFactorDefinition]:
    """Return catalog factors that exactly match one leaf condition."""
    if node.field is None or node.op is None:
        return []
    catalog = _STANDARD_FACTORS if _catalog is None else _catalog
    return [
        factor.model_copy(deep=True)
        for factor in catalog
        if node.field in {factor.source_field, *factor.source_field_aliases}
        and node.op in factor.allowed_operators
        and (
            factor.canonical_value is None
            or _normalized_value(node.value) == _normalized_value(factor.canonical_value)
        )
    ]


def normalize_factor_leaves(node: ConditionNode) -> ConditionNode:
    """Split multi-value presence checks into independently bindable leaves."""
    if node.field is not None:
        values = node.value if isinstance(node.value, list) else None
        split = {
            "contains_any": ("any", "contains"),
            "contains_all": ("all", "contains"),
            "in": ("any", "eq"),
        }.get(str(node.op)) if node.field in {"cad.features", "precision.grades", "special.requirements"} else None
        if values is None or split is None:
            return node.model_copy(deep=True)
        branch, child_op = split
        children = [ConditionNode(field=node.field, op=child_op, value=value) for value in values]
        return ConditionNode(any_conditions=children) if branch == "any" else ConditionNode(all_conditions=children)
    if node.all_conditions is not None:
        return ConditionNode(all_conditions=[normalize_factor_leaves(child) for child in node.all_conditions])
    if node.any_conditions is not None:
        return ConditionNode(any_conditions=[normalize_factor_leaves(child) for child in node.any_conditions])
    return ConditionNode(not_condition=normalize_factor_leaves(node.not_condition))


def _is_manual_process_leaf(
    node: ConditionNode,
    additional_fields: dict[str, CanonicalConditionField] | None = None,
) -> bool:
    if not node.field or not node.field.startswith("project_factor.manual_process_"):
        return False
    field = (additional_fields or {}).get(node.field)
    return field is None or field.type == "boolean"


def _binding_issue(
    code: str,
    path: str,
    matches: list[StandardFactorDefinition],
) -> FactorBindingIssue:
    messages = {
        "factor_unbound": "条件尚未绑定标准因子",
        "factor_ambiguous": "标准因子存在多个候选",
        "factor_mismatch": "条件与指定的标准因子不匹配",
    }
    return FactorBindingIssue(
        code=code,
        path=path,
        message=messages[code],
        candidate_factor_ids=[factor.factor_id for factor in matches],
    )


def _bind_leaf(
    node: ConditionNode,
    path: str,
    *,
    _catalog: Iterable[StandardFactorDefinition] | None = None,
) -> tuple[ConditionNode, list[FactorBindingIssue]]:
    if _is_manual_process_leaf(node):
        return node.model_copy(update={"factor_id": None}), []
    matches = matching_standard_factors(node, _catalog=_catalog)
    if len(matches) == 1:
        return node.model_copy(update={"factor_id": matches[0].factor_id}), []
    code = "factor_ambiguous" if matches else "factor_unbound"
    return node.model_copy(update={"factor_id": None}), [_binding_issue(code, path, matches)]


def _child_path(path: str, branch: str, index: int | None = None) -> str:
    suffix = branch if index is None else f"{branch}[{index}]"
    return f"{path}.{suffix}" if path else suffix


def _bind_tree(node: ConditionNode, path: str) -> tuple[ConditionNode, list[FactorBindingIssue]]:
    if node.field is not None:
        return _bind_leaf(node, path)
    if node.all_conditions is not None:
        children, issues = zip(*(_bind_tree(child, _child_path(path, "all", index)) for index, child in enumerate(node.all_conditions)))
        return ConditionNode(all_conditions=list(children)), [issue for group in issues for issue in group]
    if node.any_conditions is not None:
        children, issues = zip(*(_bind_tree(child, _child_path(path, "any", index)) for index, child in enumerate(node.any_conditions)))
        return ConditionNode(any_conditions=list(children)), [issue for group in issues for issue in group]
    child, issues = _bind_tree(node.not_condition, _child_path(path, "not"))
    return ConditionNode(not_condition=child), issues


def bind_unambiguous_factor_ids(node: ConditionNode) -> tuple[ConditionNode, list[FactorBindingIssue]]:
    """Normalize then bind only leaves with exactly one catalog match."""
    return _bind_tree(normalize_factor_leaves(node), "")


def _validate_tree(
    node: ConditionNode,
    path: str,
    additional_fields: dict[str, CanonicalConditionField] | None,
) -> list[FactorBindingIssue]:
    if node.field is not None:
        if _is_manual_process_leaf(node, additional_fields):
            return [] if node.factor_id is None else [_binding_issue("factor_mismatch", path, [])]
        matches = matching_standard_factors(node)
        if node.factor_id is None:
            code = "factor_ambiguous" if len(matches) > 1 else "factor_unbound"
            return [_binding_issue(code, path, matches)]
        if any(factor.factor_id == node.factor_id for factor in matches):
            return []
        return [_binding_issue("factor_mismatch", path, matches)]
    if node.all_conditions is not None:
        return [issue for index, child in enumerate(node.all_conditions) for issue in _validate_tree(child, _child_path(path, "all", index), additional_fields)]
    if node.any_conditions is not None:
        return [issue for index, child in enumerate(node.any_conditions) for issue in _validate_tree(child, _child_path(path, "any", index), additional_fields)]
    return _validate_tree(node.not_condition, _child_path(path, "not"), additional_fields)


def validate_factor_bindings(
    node: ConditionNode,
    additional_fields: dict[str, CanonicalConditionField] | None = None,
) -> list[FactorBindingIssue]:
    """Report every leaf that is unbound, ambiguous, or bound to the wrong factor."""
    return _validate_tree(normalize_factor_leaves(node), "", additional_fields)
