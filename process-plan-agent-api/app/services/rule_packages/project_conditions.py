"""Confirmed v3.7 project authoring catalog; legacy registry stays independent."""

from __future__ import annotations

import json
from pathlib import Path
import re
from typing import Any

from app.services.rule_packages.condition_contracts import CanonicalConditionField, RuleConditionCandidate
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.expression_engine import iter_condition_fields


PROJECT_CONDITIONS = json.loads((Path(__file__).resolve().parents[2] / 'assets' / 'project_conditions.json').read_text(encoding='utf-8'))
PROJECT_CONDITION_EXPRESSIONS = PROJECT_CONDITIONS['expressions']
PROJECT_ACTUAL_IT_GRADES = tuple(PROJECT_CONDITIONS['actual_it_grades'])


def project_condition_scope(process_id: str) -> str:
    # Match existing JS for-of + charCodeAt(0), including astral characters.
    value = 2166136261
    for character in process_id:
        codepoint = ord(character)
        unit = codepoint if codepoint <= 0xffff else 0xd800 + ((codepoint - 0x10000) >> 10)
        value = ((value ^ unit) * 16777619) & 0xffffffff
    return 'project_factor.operation_%08x' % value


def is_project_actual_it(key: str, unit: str | None = None) -> bool:
    return unit == 'IT' or bool(re.fullmatch(
        r'project_factor\.(?:operation|feature)_[^.]+\.it|precision\.(dimension|outer_diameter|inner_diameter)_it', key))


def project_authoring_condition(node: ConditionNode) -> ConditionNode:
    """Recover only the exact normalized A/B select choice for authoring checks.

    Frozen domains can contain 所有方位 without literal A/B options. General OR
    expressions remain unsupported, and execution of historical EQ is unchanged.
    """
    sides = node.any_conditions
    if (sides is not None and len(sides) == 2
            and sides[0].field and re.fullmatch(r'project_factor\.operation_[^.]+\.direction', sides[0].field)
            and all(side.field == sides[0].field and side.op == 'eq' for side in sides)
            and all(isinstance(side.value, str) for side in sides)
            and {side.value for side in sides} == {'A侧', 'B侧'}):
        return ConditionNode(field=sides[0].field, op='eq', value='所有方位')
    if node.all_conditions is not None:
        return ConditionNode(all=[project_authoring_condition(child) for child in node.all_conditions])
    return node


def normalize_project_authored_candidate(candidate: RuleConditionCandidate) -> RuleConditionCandidate:
    """Lower the A/B authoring choice without changing historical packages."""
    when = candidate.configuration.when if candidate.configuration else candidate.when
    changed = False

    def lower(node: ConditionNode) -> ConditionNode:
        nonlocal changed
        if (node.field and re.fullmatch(r'project_factor\.operation_[^.]+\.direction', node.field)
                and node.op == 'eq' and node.value == '所有方位'):
            changed = True
            return ConditionNode(any=[ConditionNode(field=node.field, op='eq', value=side) for side in ('A侧', 'B侧')])
        if node.all_conditions is not None:
            return ConditionNode(all=[lower(item) for item in node.all_conditions])
        if node.any_conditions is not None:
            return ConditionNode(any=[lower(item) for item in node.any_conditions])
        if node.not_condition is not None:
            return ConditionNode.model_validate({'not': lower(node.not_condition).model_dump(by_alias=True)})
        return node

    normalized = lower(when) if when is not None else None
    if not changed:
        return candidate
    result = candidate.model_copy(deep=True)
    if result.configuration:
        result.configuration.when = normalized
    else:
        result.when = normalized
    referenced = set(iter_condition_fields(normalized))
    result.field_definitions = [field for field in result.field_definitions if field.key in referenced]
    return result


def project_condition_fields(
    process_id: str,
    process_name: str,
    *,
    feature_mappings: dict[str, list[str]] | None = None,
    directions: list[str] | None = None,
    materials: list[str] | None = None,
) -> list[CanonicalConditionField]:
    scope = project_condition_scope(process_id)
    mappings = feature_mappings if feature_mappings is not None else PROJECT_CONDITIONS['feature_mappings']
    aliases = {'扁位': ['铣扁', '割扁'], '倒圆/边缘圆角': ['倒圆', '磨圆']}
    groups = [(max([len(alias) for alias in [*key.split('/'), *aliases.get(key, [])] if alias in process_name] or [0]), key) for key in mappings]
    score, group = max(groups, default=(0, ''))
    features = mappings[group] if score else list(dict.fromkeys(value for values in mappings.values() for value in values))
    fields: list[CanonicalConditionField] = []

    def add(suffix: str, label: str, kind: str, operators: list[str], values=None, **kwargs: Any) -> None:
        key = 'project_factor.material_grade' if suffix == 'material_grade' else scope + '.' + suffix
        fields.append(CanonicalConditionField(key=key, label=label, category='本项目条件', type=kind,
            operators=operators, source='项目问答配置；同一加工对象；工序=' + process_id,
            options=[{'value': str(value), 'label': str(value)} for value in (values or [])], allow_custom=False, **kwargs))

    add('features', '加工对象的特征', 'multi_select', ['contains_any'], features)
    add('direction', '同一加工对象的方位', 'single_select', ['eq'], directions if directions is not None else PROJECT_CONDITIONS['directions'])
    add('it', ('、'.join(features) if score else '加工对象') + '的实际尺寸精度等级', 'number', ['lte'], unit='IT', validation={'min': -1, 'max': 18})
    fields[-1].options = [{'value': str(value), 'label': 'IT01' if value == -1 else 'IT%d' % value} for value in range(-1, 19)]
    add('ra', ('、'.join(features) if score else '加工对象') + '的实际Ra要求值', 'number', ['lte'], unit='μm', validation={'min': 0})
    add('material_grade', '材料牌号', 'single_select', ['eq', 'in'], materials if materials is not None else PROJECT_CONDITIONS['materials'])
    fields[-1].allow_custom = True
    add('hardness_unit', '目标硬度制', 'single_select', ['eq'], ['HRC', 'HBW', 'HV', 'HRB'])
    add('hardness_min', '目标硬度下限（含）', 'number', ['gte'], validation={'min': 0})
    add('hardness_max', '目标硬度上限（含）', 'number', ['lte'], validation={'min': 0})
    add('requirement', '当前部位是否有明确' + process_name + '要求', 'boolean', ['eq'])
    return fields
