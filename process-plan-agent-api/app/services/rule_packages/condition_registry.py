"""Controlled field registry used by natural-language condition rules."""

from __future__ import annotations

from typing import Any
from pathlib import Path
import json
import math
import re

from app.services.rule_packages.condition_contracts import CanonicalConditionField
from app.services.rule_packages.contracts import ConditionNode, InputField, InputOption, InputValidation
from app.services.rule_packages.project_conditions import PROJECT_CONDITION_EXPRESSIONS, project_condition_fields, project_authoring_condition


FIELD_REGISTRY_VERSION = "2026.11-v3.7"


_FIELDS = [CanonicalConditionField.model_validate(field) for field in json.loads(
    (Path(__file__).resolve().parents[2] / "assets" / "legacy_condition_fields.json").read_text(encoding="utf-8")
)]


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
    node = project_authoring_condition(node)
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
            if (current.field.startswith('project_factor.') and definition.type in {'single_select', 'multi_select'}
                    and not definition.allow_custom and current.op not in {'exists', 'not_exists'}):
                values = value if isinstance(value, list) else [value]
                allowed = [option.get('value') for option in definition.options]
                if any(item not in allowed for item in values):
                    issues.append(f'字段“{definition.label}”的条件值不在该规则自身定义的候选中')
            if definition.type == "number" and current.op not in {"exists", "not_exists"}:
                values = value if isinstance(value, list) else [value]
                if any(isinstance(item, bool) or not isinstance(item, (int, float)) for item in values):
                    issues.append(f"字段“{definition.label}”必须使用数值")
                else:
                    if re.fullmatch(r'project_factor\.operation_[^.]+\.it', current.field) and any(not math.isfinite(item) or item != int(item) or not -1 <= item <= 18 for item in values):
                        issues.append('尺寸精度阈值必须是 IT01、IT0 或 IT1～IT18 等级，不能使用小数。')
                    validation = definition.validation or {}
                    minimum = validation.get("min")
                    maximum = validation.get("max")
                    if minimum is not None and any(item < minimum for item in values):
                        issues.append(f"字段“{definition.label}”不能小于 {minimum}")
                    if maximum is not None and any(item > maximum for item in values):
                        issues.append(f"字段“{definition.label}”不能大于 {maximum}")
                    if current.op == "between" and len(values) == 2 and values[0] > values[1]:
                        issues.append(f"字段“{definition.label}”的区间下限不能大于上限")
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
    # Two scalar inputs represent one explicitly identified machining object.
    # Never let a feature on object A and a direction on object B form C01.
    def scopes(current: ConditionNode):
        if current.field:
            match = re.fullmatch(r'(project_factor\.operation_[^.]+)\.(features|direction)', current.field)
            if match:
                yield match.group(1), match.group(2)
        for child in current.all_conditions or []:
            yield from scopes(child)
    object_fields = list(scopes(node))
    if {kind for _, kind in object_fields} == {'features', 'direction'} and len({scope for scope, _ in object_fields}) != 1:
        issues.append('加工特征与方位必须属于同一加工对象，不能分别匹配不同对象。')
    def leaves(current: ConditionNode):
        if current.field:
            yield current
        for child in current.all_conditions or []:
            yield from leaves(child)
    intervals: dict[str, dict[str, ConditionNode]] = {}
    for leaf in leaves(node):
        match = re.fullmatch(r'(project_factor\.operation_[^.]+)\.(hardness_unit|hardness_min|hardness_max)', leaf.field)
        if match:
            intervals.setdefault(match.group(1), {})[match.group(2)] = leaf
    for interval in intervals.values():
        if set(interval) != {'hardness_unit', 'hardness_min', 'hardness_max'}:
            issues.append('目标硬度必须同时设置硬度制、下限及上限，判断完整图纸区间。')
            continue
        low, high, unit = interval['hardness_min'], interval['hardness_max'], interval['hardness_unit']
        if low.op != 'gte' or high.op != 'lte' or unit.op != 'eq':
            issues.append('目标硬度完整区间须按下限≥、上限≤并使用相同硬度制判断。')
        if isinstance(low.value, (int, float)) and isinstance(high.value, (int, float)) and low.value > high.value:
            issues.append('目标硬度完整区间下限不能大于上限。')
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
