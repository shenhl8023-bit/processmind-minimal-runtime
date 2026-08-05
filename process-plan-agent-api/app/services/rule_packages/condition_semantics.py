"""Semantic post-processing and validation for condition candidates."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from app.services.rule_packages.condition_contracts import (
    CanonicalConditionField,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_registry import (
    condition_field_map,
    condition_fields,
    condition_preview,
    validate_condition_tree,
)
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.expression_engine import iter_condition_fields
from app.services.rule_packages.standard_factors import bind_unambiguous_factor_ids


def source_evidence(source_text: str) -> str:
    text = str(source_text or "").strip()
    match = re.search(r"(?:当|如果|若)\s*(.+?)(?:时|则|情况下)[，,。；;\s]*", text)
    return (match.group(1).strip() if match else text)[:160]


def with_source_evidence(
    candidate: RuleConditionCandidate | None,
    source_text: str,
) -> RuleConditionCandidate | None:
    if not candidate:
        return candidate
    evidence = str(candidate.evidence or "").strip()
    if evidence and evidence in str(source_text or ""):
        return candidate
    return candidate.model_copy(update={"evidence": source_evidence(source_text)})


def validate_candidate(
    candidate: RuleConditionCandidate,
    processes: list[RuleConditionProcessOption],
) -> list[str]:
    allowed_ids = {item.process_id for item in processes}
    if candidate.kind == "process_relation":
        relation = candidate.relation
        if relation is None:
            return ["关联工序规则缺少关系定义。"]
        referenced_ids = [*relation.source_process_ids, *relation.target_process_ids]
        issues = []
        if set(relation.source_process_ids) & set(relation.target_process_ids):
            issues.append("关联工序的来源和目标不能是同一道工序。")
    else:
        if candidate.when is None or candidate.then is None:
            return ["参数条件规则缺少 when/then。"]
        issues = []
        standard_fields = condition_field_map()
        dynamic_fields: dict[str, CanonicalConditionField] = {}
        referenced_fields = set(iter_condition_fields(candidate.when))
        for definition in candidate.field_definitions:
            if definition.key in standard_fields:
                issues.append(f"动态因素不能覆盖标准字段：{definition.key}")
                continue
            review_only_custom_boolean = (
                definition.type == "boolean"
                and definition.key.startswith("custom.requirements.")
            )
            if not definition.key.startswith("project_factor.") and not review_only_custom_boolean:
                issues.append(f"动态因素必须使用 project_factor 命名空间：{definition.key}")
                continue
            if not re.fullmatch(
                r"(?:project_factor|custom\.requirements)\.[a-z0-9_.-]+",
                definition.key,
            ):
                issues.append(f"动态因素 key 只能使用小写字母、数字、点、下划线和连字符：{definition.key}")
                continue
            if definition.key in dynamic_fields:
                issues.append(f"动态因素定义重复：{definition.key}")
                continue
            if definition.key not in referenced_fields:
                issues.append(f"动态因素未被当前规则引用：{definition.key}")
                continue
            dynamic_fields[definition.key] = definition
        issues.extend(validate_condition_tree(candidate.when, dynamic_fields))
        referenced_ids = [*candidate.then.include_process_ids, *candidate.then.exclude_process_ids]
    for process_id in referenced_ids:
        if process_id not in allowed_ids:
            issues.append(f"规则引用了当前路线中不存在的工序：{process_id}")
    return list(dict.fromkeys(issues))


def candidate_from_payload(payload: Any) -> RuleConditionCandidate | None:
    if not isinstance(payload, dict):
        return None
    body = payload.get("candidate") if isinstance(payload.get("candidate"), dict) else payload
    try:
        candidate = RuleConditionCandidate.model_validate(body)
    except ValidationError:
        return None
    if not candidate.preview and candidate.when is not None:
        dynamic_fields = {field.key: field for field in candidate.field_definitions}
        candidate.preview = condition_preview(candidate.when, dynamic_fields)
    return candidate


def bind_candidate_factors(
    candidate: RuleConditionCandidate,
) -> tuple[RuleConditionCandidate, list[str]]:
    if candidate.kind != "condition" or candidate.when is None:
        return candidate, []
    bound, binding_issues = bind_unambiguous_factor_ids(candidate.when)
    return candidate.model_copy(update={"when": bound, "preview": condition_preview(bound)}), [
        issue.message for issue in binding_issues
    ]


def has_unregistered_project_factor(candidate: RuleConditionCandidate) -> bool:
    return any(
        field.key.startswith("project_factor.")
        and not field.key.startswith("project_factor.manual_process_")
        for field in candidate.field_definitions
    )
