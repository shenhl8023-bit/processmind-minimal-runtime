"""Controlled field registry used by natural-language condition rules."""

from __future__ import annotations

from typing import Any

from app.services.rule_packages.condition_contracts import CanonicalConditionField
from app.services.rule_packages.contracts import ConditionNode, InputField, InputOption, InputValidation


FIELD_REGISTRY_VERSION = "2026.09"


_FIELDS = [
    CanonicalConditionField(
        key="material.grade", label="材料牌号", category="材料", type="single_select",
        operators=["eq", "neq", "in"], aliases=["材料", "材质", "材料牌号"], source="CAD/PLM",
        options=[{"value": value, "label": value} for value in ["9Cr18", "95Cr18", "4Cr14Ni14W2Mo", "6061"]], required=True,
    ),
    CanonicalConditionField(
        key="precision.outer_diameter_it", label="外圆尺寸精度 IT", category="尺寸精度", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["外圆精度", "外径精度", "外圆IT"],
        source="CAD/工艺要求", validation={"min": 1, "max": 18},
    ),
    CanonicalConditionField(
        key="precision.inner_diameter_it", label="内孔尺寸精度 IT", category="尺寸精度", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["内孔精度", "孔精度", "内径精度", "孔IT"],
        source="CAD/工艺要求", validation={"min": 1, "max": 18},
    ),
    CanonicalConditionField(
        key="precision.dimension_it", label="尺寸精度 IT", category="尺寸精度", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["尺寸精度", "IT等级", "公差等级"],
        source="CAD/工艺要求", validation={"min": 1, "max": 18},
    ),
    CanonicalConditionField(
        key="surface.roughness_ra", label="表面粗糙度 Ra", category="表面质量", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["粗糙度", "表面粗糙度", "Ra"],
        unit="μm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.roundness_mm", label="圆度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["圆度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.cylindricity_mm", label="圆柱度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["圆柱度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.coaxiality_mm", label="同轴度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["同轴度", "同心度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.runout_mm", label="跳动公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["圆跳动", "全跳动", "跳动"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.position_mm", label="位置度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["位置度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.flatness_mm", label="平面度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["平面度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="tolerance.perpendicularity_mm", label="垂直度公差", category="形位公差", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["垂直度"], unit="mm", source="CAD/工艺要求", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="geometry.diameter_mm", label="特征直径", category="几何尺寸", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["直径", "孔径", "外径"], unit="mm", source="CAD", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="geometry.length_mm", label="特征长度", category="几何尺寸", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["长度", "深度"], unit="mm", source="CAD", validation={"min": 0},
    ),
    CanonicalConditionField(
        key="mechanical.hardness_hrc", label="目标硬度 HRC", category="性能要求", type="number",
        operators=["eq", "gt", "gte", "lt", "lte", "between"], aliases=["硬度", "HRC", "目标硬度"], unit="HRC", source="图样技术要求", validation={"min": 0, "max": 80},
    ),
    CanonicalConditionField(
        key="cad.features", label="CAD 特征集合", category="结构特征", type="multi_select",
        operators=["contains", "contains_any", "contains_all"], aliases=["CAD特征", "结构特征", "槽", "孔", "扁位"], source="CAD",
        options=[{"value": value, "label": value} for value in ["扁位/平面", "槽类特征", "普通孔/辅助孔", "铰孔/精孔", "型孔/割扁", "顶尖孔"]], required=True,
    ),
    CanonicalConditionField(
        key="precision.grades", label="精度/表面要求集合", category="精度要求", type="multi_select",
        operators=["contains", "contains_any", "contains_all"], aliases=["精加工要求", "磨削要求", "研磨要求"], source="CAD/工艺要求",
        options=[{"value": value, "label": value} for value in ["孔精加工", "珩孔要求", "研孔要求", "外圆磨削", "端面磨削", "槽磨削", "研外圆"]], required=True,
    ),
    CanonicalConditionField(
        key="special.requirements", label="特殊要求", category="特殊要求", type="multi_select",
        operators=["contains", "contains_any", "contains_all"], aliases=["特殊要求", "技术要求", "检验要求", "表面处理要求"], source="人工补充/图样技术要求",
        options=[{"value": value, "label": value} for value in ["渗氮层要求", "铬酸阳极化要求", "硬质阳极化要求", "追溯标印", "无损检测要求", "磁粉检查要求", "烧伤检查要求"]],
    ),
]


def condition_fields() -> list[CanonicalConditionField]:
    return [field.model_copy(deep=True) for field in _FIELDS]


def condition_field_map() -> dict[str, CanonicalConditionField]:
    return {field.key: field for field in _FIELDS}


def input_field_for(key: str) -> InputField | None:
    field = condition_field_map().get(key)
    if not field:
        return None
    validation = InputValidation(**field.validation) if field.validation else None
    return InputField(
        key=field.key,
        label=field.label,
        type=field.type,
        required=field.required,
        source=field.source,
        options=[InputOption(**option) for option in field.options],
        allow_custom=field.allow_custom,
        unit=field.unit,
        validation=validation,
    )


def validate_condition_tree(
    node: ConditionNode,
    additional_fields: dict[str, CanonicalConditionField] | None = None,
) -> list[str]:
    issues: list[str] = []
    fields = condition_field_map()
    fields.update(additional_fields or {})

    def walk(current: ConditionNode) -> None:
        if current.field:
            definition = fields.get(current.field)
            if not definition:
                issues.append(f"条件字段不在标准字段库中：{current.field}")
                return
            if current.op not in definition.operators:
                issues.append(f"字段“{definition.label}”不支持运算符 {current.op}")
            value = current.value
            if definition.type == "number" and current.op not in {"exists", "not_exists"}:
                values = value if isinstance(value, list) else [value]
                if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
                    issues.append(f"字段“{definition.label}”必须使用数值")
            if definition.type == "boolean" and current.op not in {"exists", "not_exists"} and not isinstance(value, bool):
                issues.append(f"字段“{definition.label}”必须使用布尔值")
            return
        for child in current.all_conditions or []:
            walk(child)
        for child in current.any_conditions or []:
            walk(child)
        if current.not_condition is not None:
            walk(current.not_condition)

    walk(node)
    return issues


def condition_preview(
    node: ConditionNode,
    additional_fields: dict[str, CanonicalConditionField] | None = None,
) -> str:
    fields = condition_field_map()
    fields.update(additional_fields or {})
    operator_labels = {
        "eq": "等于", "neq": "不等于", "in": "属于", "contains": "包含",
        "contains_any": "包含任一", "contains_all": "包含全部", "gt": ">", "gte": "≥",
        "lt": "<", "lte": "≤", "between": "介于", "exists": "已填写", "not_exists": "未填写",
    }
    if node.all_conditions is not None:
        return " 且 ".join(f"({condition_preview(child, additional_fields)})" for child in node.all_conditions)
    if node.any_conditions is not None:
        return " 或 ".join(f"({condition_preview(child, additional_fields)})" for child in node.any_conditions)
    if node.not_condition is not None:
        return f"不满足（{condition_preview(node.not_condition, additional_fields)}）"
    definition = fields.get(str(node.field or ""))
    label = definition.label if definition else str(node.field or "")
    unit = f" {definition.unit}" if definition and definition.unit else ""
    value = node.value
    if definition and definition.type == "boolean" and isinstance(value, bool):
        value_text = "是" if value else "否"
        return f"{label} {operator_labels.get(str(node.op), str(node.op))} {value_text}".strip()
    if isinstance(value, list):
        value_text = "、".join(str(item) for item in value)
    else:
        value_text = str(value)
    return f"{label} {operator_labels.get(str(node.op), str(node.op))} {value_text}{unit}".strip()
