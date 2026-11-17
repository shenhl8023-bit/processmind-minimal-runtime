"""Current rule-writing contract, separate from historical package execution."""

from __future__ import annotations

import math

from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.project_conditions import project_authoring_condition


def validate_authored_condition(node: ConditionNode | None) -> list[str]:
    if node is None:
        return ["尚未设置出现条件，请自行添加至少一条条件。"]
    node = project_authoring_condition(node)
    if node.any_conditions is not None or node.not_condition is not None:
        return ["条件工序只支持全部满足的三元组；此规则包含任一满足或否定分组，请重新设置出现条件。"]
    if node.all_conditions is not None:
        if not node.all_conditions:
            return ["尚未设置出现条件，请自行添加至少一条条件。"]
        return list(dict.fromkeys(issue for child in node.all_conditions for issue in validate_authored_condition(child)))
    if not node.field or not node.op:
        return ["请补全每一项条件的字段和判断关系。"]
    if node.op in {"exists", "not_exists"}:
        return []

    def complete(value: object) -> bool:
        return (value is not None
                and not (isinstance(value, str) and not value.strip())
                and not (isinstance(value, float) and not math.isfinite(value)))

    if isinstance(node.value, list):
        valid = bool(node.value) and all(complete(value) for value in node.value)
    else:
        valid = complete(node.value)
    return [] if valid else ["请补全条件值；条件值和列表不能为空。"]


def validate_authored_candidate(
    candidate: RuleConditionCandidate,
    current_process_id: str | None = None,
) -> list[str]:
    """Validate simple authoring without rewriting an existing candidate."""
    if candidate.kind == "process_configuration":
        config = candidate.configuration
        if config is None:
            return ["工序规则缺少配置。"]
        if current_process_id and config.process_id != current_process_id:
            return ["规则配置只能控制当前工序。"]
        if config.occurrence == "associated":
            if config.when is not None or len(config.relations) != 1:
                return ["关联工序只跟随一个来源，不能同时设置出现条件。"]
            relation = config.relations[0]
            if (relation.relation_type != "trigger_after" or len(relation.source_process_ids) != 1
                    or relation.target_process_ids != [config.process_id]
                    or config.process_id in relation.source_process_ids):
                return ["请选择一个其他工序作为来源，来源出现后带出当前工序并排在其后。"]
            return []
        if config.relations:
            return ["每道工序只能选择一种出现模式；字段条件与关联工序不能混合，请重新设置。"]
        if config.occurrence == "always":
            return [] if config.when is None else ["主工序固定出现，不能附加出现条件。"]
        issues = validate_authored_condition(config.when)
        if config.occurrence == "manual" and not (
            config.when and config.when.field and config.when.op == "eq" and config.when.value is True
        ):
            issues.append("Bool 工序必须使用当前工序的是否出现开关。")
        return list(dict.fromkeys(issues))

    if candidate.kind == "process_relation":
        relation = candidate.relation
        if (relation is None or relation.relation_type != "trigger_after"
                or len(relation.source_process_ids) != 1 or len(relation.target_process_ids) != 1
                or (current_process_id and relation.target_process_ids != [current_process_id])
                or set(relation.source_process_ids) & set(relation.target_process_ids)):
            return ["关联工序只支持跟随一个来源并排在其后；请重新选择出现模式和来源工序。"]
        return []

    issues = validate_authored_condition(candidate.when)
    action = candidate.then
    if (action is None or action.exclude_process_ids or len(action.include_process_ids) != 1
            or (current_process_id and action.include_process_ids != [current_process_id])):
        issues.append("条件工序只控制当前工序是否纳入；此动作需要重新选择出现模式设置。")
    return list(dict.fromkeys(issues))
