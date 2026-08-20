"""Natural-language parser for user-authored process conditions."""

from __future__ import annotations

import logging

from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_parser_llm import parse_with_llm
from app.services.rule_packages.condition_parser_local import (
    MANUAL_BOOLEAN_PREFILL_NOTE,
    PRUNED_UNBOUND_LEAF_NOTE,
    PROCESS_ALIGNED_FACTOR_NOTE,
    align_candidate_to_process,
    build_manual_boolean_draft,
    fill_unbound_leaves_from_catalog,
    is_manual_boolean_candidate,
    known_special_requirement,
    parse_condition_tree,
    parse_local_condition,
    parse_partial_condition_candidate,
    parse_process_relation,
    prune_unbound_leaves,
)
from app.services.rule_packages.condition_registry import condition_preview
from app.services.rule_packages.condition_semantics import (
    bind_candidate_factors,
    has_unregistered_project_factor,
    validate_candidate,
    with_source_evidence,
)

CONDITION_PARSER_VERSION = "2026.08.19.2"
logger = logging.getLogger(__name__)


def _with_when(candidate: RuleConditionCandidate, when) -> RuleConditionCandidate:
    return candidate.model_copy(update={"when": when, "preview": condition_preview(when)})


def _bind_and_align(
    candidate: RuleConditionCandidate,
    process_name: str,
    process_id: str,
    source_text: str,
) -> tuple[RuleConditionCandidate, list[str]]:
    bound, issues = bind_candidate_factors(candidate)
    if not issues:
        return bound, []
    if candidate.kind != "condition" or candidate.when is None:
        return bound, issues

    aligned, changed = align_candidate_to_process(bound, process_name)
    current = aligned if changed else bound
    current, issues = bind_candidate_factors(current)
    if not issues:
        return current, [PROCESS_ALIGNED_FACTOR_NOTE] if changed else []

    filled_when = fill_unbound_leaves_from_catalog(current.when, process_name)
    if filled_when != current.when:
        current, issues = bind_candidate_factors(_with_when(current, filled_when))
        if not issues:
            return current, [PROCESS_ALIGNED_FACTOR_NOTE]

    if current.when and (
        str(current.when.field or "").startswith("custom.requirements.")
        or is_manual_boolean_candidate(current)
    ):
        return current, issues

    pruned = prune_unbound_leaves(current.when) if current.when is not None else None
    if pruned is not None:
        pruned_candidate, pruned_issues = bind_candidate_factors(_with_when(current, pruned))
        if not pruned_issues:
            return pruned_candidate, [PRUNED_UNBOUND_LEAF_NOTE]
        current, issues = pruned_candidate, pruned_issues

    return build_manual_boolean_draft(process_id, process_name, source_text), [MANUAL_BOOLEAN_PREFILL_NOTE]


async def parse_rule_condition(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
    *,
    llm_config: dict[str, str] | None = None,
) -> tuple[RuleConditionCandidate | None, float | None, list[str]]:
    # Explicit relationship words in the user's text take precedence over the
    # target process category. A process can be conditionally included in one
    # sentence and ordered after another process in a different sentence.
    local_relation_candidate = parse_process_relation(
        source_text,
        current_process_id,
        processes,
    )
    local_condition_candidate = parse_local_condition(
        source_text,
        current_process_id,
        current_process_name,
        processes,
    )
    local_relation_candidate = with_source_evidence(local_relation_candidate, source_text)
    local_condition_candidate = with_source_evidence(local_condition_candidate, source_text)
    deterministic_condition = parse_condition_tree(source_text)

    # A relation that names a route process and gives an explicit ordering or
    # trigger is deterministic. Return it immediately: it avoids letting an
    # unavailable or over-general LLM turn a clear dependency into a vague
    # parameter condition. It still remains only a candidate and must be
    # confirmed by the user before it can enter the exported rule package.
    if local_relation_candidate:
        relation_issues = validate_candidate(local_relation_candidate, processes)
        if not relation_issues:
            logger.info("rule_condition_parse_source source=local_relation")
            bound_candidate, binding_issues = _bind_and_align(
                local_relation_candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, 0.9, binding_issues

    if local_condition_candidate and (
        local_condition_candidate.field_definitions
        or deterministic_condition is not None
    ):
        local_issues = validate_candidate(local_condition_candidate, processes)
        if not local_issues:
            logger.info("rule_condition_parse_source source=local_condition")
            bound_candidate, binding_issues = _bind_and_align(
                local_condition_candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, 0.9, binding_issues

    try:
        candidate, confidence, issues = await parse_with_llm(
            source_text,
            current_process_id,
            current_process_name,
            processes,
            llm_config=llm_config,
        )
    except Exception:
        logger.exception("rule_condition_llm_parse_failed")
        candidate = None
        confidence = None
        issues = ["AI 服务暂时不可用，已使用本地解析器生成待审核草稿。"]
    if candidate:
        candidate = with_source_evidence(candidate, source_text)
        assert candidate is not None
        validation_issues = validate_candidate(candidate, processes)
        if has_unregistered_project_factor(candidate):
            validation_issues.append("未注册的类别条件不能创建项目因素，请选择标准因子或使用人工 Bool 条件。")
        expected_special_requirement = (
            None if local_relation_candidate else known_special_requirement(source_text, current_process_name)
        )
        model_uses_expected_special_requirement = (
            candidate.kind == "condition"
            and candidate.when is not None
            and candidate.when.field == "special.requirements"
            and candidate.when.op == "contains"
            and candidate.when.value == expected_special_requirement
        )
        if not validation_issues and not (
            local_relation_candidate and candidate.kind != "process_relation"
        ) and not (expected_special_requirement and not model_uses_expected_special_requirement):
            logger.info("rule_condition_parse_source source=llm")
            bound_candidate, binding_issues = _bind_and_align(
                candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, confidence, [*issues, *binding_issues]
        issues.extend(validation_issues)
        if local_relation_candidate and candidate.kind != "process_relation":
            issues.append("模型候选与明确的工序关系语义不一致，已改用关联工序候选。")
        if expected_special_requirement and not model_uses_expected_special_requirement:
            issues.append("模型候选与明确的特殊要求语义不一致，已改用特殊要求候选。")

    # A model may be unavailable or reject an ambiguous sentence. Local patterns keep
    # the most common process-relation wording usable without lowering validation rules.
    if local_relation_candidate:
        relation_issues = validate_candidate(local_relation_candidate, processes)
        if not relation_issues:
            fallback_note = "已使用内置规则解析器生成候选结果，请重点核对。" if issues else ""
            logger.info("rule_condition_parse_source source=local_relation_fallback")
            bound_candidate, binding_issues = _bind_and_align(
                local_relation_candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, 0.9, [*issues, *binding_issues, *([fallback_note] if fallback_note else [])]
        issues.extend(relation_issues)

    local_candidate = local_condition_candidate
    if local_candidate:
        local_issues = validate_candidate(local_candidate, processes)
        if not local_issues:
            fallback_note = "已使用内置规则解析器生成候选结果，请重点核对。" if issues else ""
            logger.info("rule_condition_parse_source source=local_condition_fallback")
            bound_candidate, binding_issues = _bind_and_align(
                local_candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, 0.65, [*issues, *binding_issues, *([fallback_note] if fallback_note else [])]
        issues.extend(local_issues)

    partial_candidate, partial_issues = parse_partial_condition_candidate(
        source_text,
        current_process_id,
        processes,
    )
    if partial_candidate:
        partial_validation_issues = validate_candidate(partial_candidate, processes)
        if not partial_validation_issues:
            logger.info("rule_condition_parse_source source=partial_local_fallback")
            bound_candidate, binding_issues = _bind_and_align(
                partial_candidate,
                current_process_name,
                current_process_id,
                source_text,
            )
            return bound_candidate, 0.55, list(dict.fromkeys([
                *issues,
                *partial_issues,
                *binding_issues,
            ]))
        issues.extend(partial_validation_issues)

    logger.info("rule_condition_parse_source source=manual_boolean_prefill")
    return (
        build_manual_boolean_draft(current_process_id, current_process_name, source_text),
        0.45,
        list(dict.fromkeys([*issues, MANUAL_BOOLEAN_PREFILL_NOTE])),
    )
