"""
参数审核问题流转与当前问题构造辅助。
"""

from __future__ import annotations

import re
from collections import Counter

from app.schemas.schemas import (
    FactorFieldOut,
    ParamConfirmOptionOut,
    ParamConfirmQuestionOut,
    ParamCurrentQuestionOut,
    ParamJsonStageOut,
    ParamReviewedFactorOut,
)


UNCONDITIONAL_MERGE_VARIANT_GROUPS = {
    frozenset({"下料", "备料"}),
    frozenset({"标印", "打标"}),
    frozenset({"检验", "检查"}),
}

PARAM_QUESTION_CATEGORY_RULES: tuple[tuple[str, tuple[str, ...], tuple[str, ...]], ...] = (
    ("heat_treatment", ("调质", "淬火", "渗氮", "氰化", "正常化", "时效", "钝化", "热处理"), ()),
    ("precision", ("配套", "精度", "粗糙度", "公差", "跳动"), ("磨外圆", "研外圆", "珩孔", "研孔", "精磨", "粗糙度")),
    ("manufacturability", (), ("线切割", "电火花")),
    ("stress_risk", (), ("去应力", "时效")),
    ("slot_structure", (), ("槽",)),
    ("hole_structure", ("孔",), ("孔", "钻", "镗", "铰")),
)


def sample_has_stage_step(stages: list[ParamJsonStageOut], stage_name: str, occurrence_index: int, step_name: str) -> bool:
    for stage in stages:
        if stage.stage == stage_name and stage.occurrence_index == occurrence_index:
            return any(step.name == step_name for step in stage.steps)
    return False


def build_param_factor_review(
    term: str,
    factor_fields: list[FactorFieldOut],
    sample_pairs: list[dict[str, object]],
    stage_name: str,
    occurrence_index: int,
    step_name: str,
    *,
    parse_factor_condition,
    match_rule_expr,
    term_expected_value_text,
) -> ParamReviewedFactorOut:
    normalized = (term or "").strip()
    parsed = parse_factor_condition(normalized.replace(" ", ""))
    factor_key = str(parsed.get("key") or normalized) if parsed else normalized
    factor_field = next((item for item in factor_fields if item.key == factor_key), None)
    factor_label = factor_field.label if factor_field else factor_key

    matched_count = 0
    matched_with_step = 0
    unmatched_with_step = 0
    sample_total = len(sample_pairs)

    for pair in sample_pairs:
        attrs = pair["attrs"]
        stages = pair["stages"]
        matched, _ = match_rule_expr(normalized, attrs)
        has_step = sample_has_stage_step(stages, stage_name, occurrence_index, step_name)
        if matched:
            matched_count += 1
            if has_step:
                matched_with_step += 1
        elif has_step:
            unmatched_with_step += 1

    counterexample_count = max(matched_count - matched_with_step, 0) + unmatched_with_step
    coverage_count = max(sample_total - counterexample_count, 0)
    status = "resolved" if counterexample_count == 0 and sample_total > 0 else "pending_confirm"
    reason_type = "need_confirm"
    if counterexample_count == 0 and sample_total > 0:
        reason_text = "该因素已在当前样本中零反例解释该工序边界。"
    else:
        reason_text = (
            f"当前仍有 {counterexample_count} 个反例样本，"
            "尚未由该因素零反例解释该工序的出现/不出现。"
        )

    return ParamReviewedFactorOut(
        factor_key=factor_key,
        factor_label=factor_label,
        expected_value=term_expected_value_text(normalized, factor_fields),
        coverage_count=coverage_count,
        total_count=sample_total,
        status=status,
        reason_type=reason_type,
        reason_text=reason_text,
    )


def _contains_any_token(text: str, tokens: tuple[str, ...]) -> bool:
    return bool(text) and any(token in text for token in tokens)


def infer_param_question_category(
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    question_hint: str,
) -> str:
    step_text = (step_name or "").strip()
    factor_label = (target_factor.factor_label or "").strip()
    factor_key = (target_factor.factor_key or "").strip()
    hint_text = (question_hint or "").strip()
    merged = f"{step_text} {factor_label} {factor_key} {hint_text}"

    if factor_key == "material" or _contains_any_token(merged, ("材料", "材质")):
        return "material"
    for category, merged_tokens, step_tokens in PARAM_QUESTION_CATEGORY_RULES:
        if _contains_any_token(merged, merged_tokens):
            return category
        if _contains_any_token(step_text, step_tokens) or _contains_any_token(factor_label, step_tokens):
            return category
    return "generic_structure"


def build_param_question_spec(
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    question_hint: str,
    sample_pairs: list[dict[str, object]],
    *,
    build_param_question_spec_for_category,
) -> tuple[str, str, list[ParamConfirmOptionOut]]:
    category = infer_param_question_category(step_name, target_factor, question_hint)
    question_type, prompt, options = build_param_question_spec_for_category(
        category=category,
        step_name=step_name,
        target_factor=target_factor,
        sample_pairs=sample_pairs,
    )
    if question_type == "generic_reason_select":
        prompt = question_hint or prompt
    return question_type, prompt, options


def is_merged_step_name(step_name: str) -> bool:
    parts = [part.strip() for part in re.split(r"[／/]", str(step_name or "")) if part.strip()]
    return len(parts) >= 2 and len(set(parts)) >= 2


def split_step_name_variants(step_name: str) -> list[str]:
    parts = [part.strip() for part in re.split(r"[／/]", str(step_name or "")) if part.strip()]
    deduped: list[str] = []
    for part in parts:
        if part not in deduped:
            deduped.append(part)
    return deduped


def is_unconditional_merge_variants(parts: list[str]) -> bool:
    if len(parts) < 2:
        return False
    normalized = frozenset(parts)
    if normalized in UNCONDITIONAL_MERGE_VARIANT_GROUPS:
        return True
    for idx, part in enumerate(parts):
        for other in parts[idx + 1:]:
            if part in other or other in part:
                return True
    return True


def classify_param_operation(step_name: str) -> tuple[str, str, list[str]]:
    parts = split_step_name_variants(step_name)
    if not parts:
        return "independent", "当前工序名称已固定，按独立工序处理。", []
    if is_unconditional_merge_variants(parts):
        return "merged_name", "名称中包含多个可统一为同一名称的候选名称，按组合名工序处理。", parts
    return "independent", "当前工序名称已固定，按独立工序处理。", parts


def build_param_current_question(
    *,
    factor_key: str,
    question_type: str,
    prompt: str,
    options: list[ParamConfirmOptionOut],
    round_index: int,
    round_total_hint: int,
    question_goal: str,
    continue_reason: str,
    param_question_tree_meta,
) -> ParamCurrentQuestionOut:
    tree_branch, tree_node_id, option_source = param_question_tree_meta(question_type)
    if option_source == "fixed" and any(int(getattr(option, "count", 0) or 0) > 0 for option in options):
        option_source = "extracted"
    return ParamCurrentQuestionOut(
        factor_key=factor_key,
        question_type=question_type,
        prompt=prompt,
        options=options,
        tree_branch=tree_branch,
        tree_node_id=tree_node_id,
        option_source=option_source,
        round_index=round_index,
        round_total_hint=round_total_hint,
        question_goal=question_goal,
        continue_reason=continue_reason,
    )


def build_custom_reason_root_question(
    *,
    factor_key: str,
    step_name: str,
    prompt: str,
    round_index: int,
    round_total_hint: int,
    root_reason_options_for_step,
    tree_node_options,
    default_param_question_meta,
    with_standard_tail_options,
    param_question_tree_meta,
) -> ParamCurrentQuestionOut:
    question_type = "generic_reason_select"
    options = root_reason_options_for_step(
        step_name,
        tree_node_options("coverage", "coverage_reason_root"),
    )
    question_goal, continue_reason = default_param_question_meta(
        question_type=question_type,
        step_name=step_name,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )
    return build_param_current_question(
        factor_key=factor_key,
        question_type=question_type,
        prompt=prompt,
        options=with_standard_tail_options(options),
        round_index=round_index,
        round_total_hint=round_total_hint,
        question_goal=question_goal,
        continue_reason=continue_reason,
        param_question_tree_meta=param_question_tree_meta,
    )


def has_terminal_factor_answer(operation_answers, factor_key: str) -> bool:
    return operation_answers.get(factor_key) is not None


def operation_driver_answers(operation_answers, factor_key: str):
    prefix = f"__driver__::"
    target_suffix = f"::{factor_key}"
    result = {}
    for key, value in operation_answers.items():
        if not key.startswith(prefix):
            continue
        if not key.endswith(target_suffix):
            continue
        layer = key[len(prefix): -len(target_suffix)]
        if layer:
            result[layer] = value
    return result


def coverage_like_status_from_answers(
    *,
    current_question: ParamCurrentQuestionOut | None,
    operation_answers,
    factor_key: str,
    pending_message: str,
    stable_message: str,
    evidence_message: str,
) -> tuple[str, str]:
    if current_question is not None:
        return "pending_confirm", pending_message
    driver_answers = operation_driver_answers(operation_answers, factor_key)
    if not driver_answers:
        return "pending_confirm", pending_message
    if any(
        str(answer.selected_value or "").strip() in {"coverage_reason::uncertain", "missing::unknown", "unsure", "data_issue"}
        for answer in driver_answers.values()
    ):
        return "evidence", evidence_message
    return "stable", stable_message


def selected_merge_name(*, step_name: str, operation_answers, param_driver_factor_key, param_answer_display_text) -> str:
    name_answer = operation_answers.get(param_driver_factor_key("__merge__", "name"))
    if name_answer is not None:
        answer_text = param_answer_display_text(name_answer)
        if answer_text:
            return answer_text
        selected_value = str(name_answer.selected_value or "").strip()
        if selected_value.startswith("merge_name::"):
            index_text = selected_value.split("::", 1)[1]
            if index_text.isdigit():
                parts = split_step_name_variants(step_name)
                index = int(index_text)
                if 0 <= index < len(parts):
                    return parts[index]
    parts = split_step_name_variants(step_name)
    return parts[0] if parts else str(step_name or "").strip()


def build_merge_name_question(
    step_name: str,
    round_index: int,
    round_total_hint: int,
    *,
    tree_node_question_type,
    tree_node_question,
    default_param_question_meta,
    with_standard_tail_options,
    param_question_tree_meta,
) -> ParamCurrentQuestionOut | None:
    parts = split_step_name_variants(step_name)
    if len(parts) < 2:
        return None
    options = [
        ParamConfirmOptionOut(value=f"merge_name::{index}", label=part, count=0)
        for index, part in enumerate(parts)
    ]
    options.append(ParamConfirmOptionOut(value="other", label="其他（请补充）", count=0))
    question_type = tree_node_question_type("merge", "merge_name_root") or "merge_name_select"
    prompt = tree_node_question(
        "merge",
        "merge_name_root",
        f"当前工序名为“{step_name}”。以后统一使用哪个名称？",
    )
    question_goal, continue_reason = default_param_question_meta(
        question_type=question_type,
        step_name=step_name,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )
    return build_param_current_question(
        factor_key="__merge__",
        question_type=question_type,
        prompt=prompt,
        options=with_standard_tail_options(options),
        round_index=round_index,
        round_total_hint=round_total_hint,
        question_goal=question_goal,
        continue_reason=continue_reason,
        param_question_tree_meta=param_question_tree_meta,
    )


def coverage_category_for_node(node_id: str) -> str:
    mapping = {
        "coverage_reason_root": "root",
        "coverage_material_type": "material",
        "coverage_material_list": "material_scope",
        "coverage_structure_type": "generic_structure",
        "coverage_structure_need": "structure_need",
        "coverage_size_type": "size",
        "coverage_size_boundary": "size_boundary",
        "coverage_blank_type": "blank",
        "coverage_blank_need": "blank_need",
        "coverage_requirement_type": "requirement",
        "coverage_requirement_need": "requirement_need",
        "coverage_multi_pair": "multi_factor",
        "coverage_multi_primary": "multi_primary",
        "coverage_uncertain_missing": "uncertain",
    }
    return mapping.get(node_id, "")


def coverage_next_node_id(factor_key: str, operation_answers, *, param_driver_factor_key, tree_next_node_id) -> str:
    reason_answer = (
        operation_answers.get(param_driver_factor_key(factor_key, "reason"))
        or operation_answers.get(f"__driver__::{factor_key}")
    )
    if reason_answer is None:
        return "coverage_reason_root"

    reason_value = str(reason_answer.selected_value or "").strip()
    reason_value = {
        "generic::材料相关": "coverage_reason::material",
        "generic::结构相关": "coverage_reason::structure",
        "generic::精度相关": "coverage_reason::requirement",
        "generic::热处理相关": "coverage_reason::material",
        "generic::可加工性相关": "coverage_reason::requirement",
    }.get(reason_value, reason_value)
    reason_next = tree_next_node_id("coverage", "coverage_reason_root", reason_value)
    if not reason_next:
        return ""
    if reason_next in {"coverage_uncertain_missing"}:
        return reason_next

    driver_layer_map = {
        "coverage_material_type": "material",
        "coverage_structure_type": "structure",
        "coverage_size_type": "size",
        "coverage_blank_type": "blank",
        "coverage_requirement_type": "requirement",
        "coverage_multi_pair": "multi",
    }
    driver_layer = driver_layer_map.get(reason_next)
    if not driver_layer:
        return reason_next

    driver_answer = operation_answers.get(param_driver_factor_key(factor_key, driver_layer))
    if driver_answer is None:
        return reason_next

    return tree_next_node_id(
        "coverage",
        reason_next,
        str(driver_answer.selected_value or "").strip(),
    ) or ""


def build_coverage_question_from_node(
    *,
    node_id: str,
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    sample_pairs: list[dict[str, object]],
    round_index: int,
    round_total_hint: int,
    build_param_question_spec_for_category,
    default_param_question_meta,
    param_question_tree_meta,
) -> ParamCurrentQuestionOut | None:
    category = coverage_category_for_node(node_id)
    if not category:
        return None
    working_factor = target_factor
    if node_id == "coverage_multi_primary":
        working_factor = target_factor.model_copy(update={"expected_value": target_factor.expected_value})
    question_type, prompt, options = build_param_question_spec_for_category(
        category=category,
        step_name=step_name,
        target_factor=working_factor,
        sample_pairs=sample_pairs,
    )
    question_goal, continue_reason = default_param_question_meta(
        question_type=question_type,
        step_name=step_name,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )
    return build_param_current_question(
        factor_key=target_factor.factor_key,
        question_type=question_type,
        prompt=prompt,
        options=options,
        round_index=round_index,
        round_total_hint=round_total_hint,
        question_goal=question_goal,
        continue_reason=continue_reason,
        param_question_tree_meta=param_question_tree_meta,
    )


def build_param_followup_question_from_drivers(
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    operation_answers,
    sample_pairs: list[dict[str, object]],
    *,
    param_driver_factor_key,
    param_answer_display_text,
    tree_next_node_id,
    build_param_question_spec_for_category,
    default_param_question_meta,
    param_question_tree_meta,
    round_index: int = 1,
    round_total_hint: int = 1,
) -> ParamCurrentQuestionOut | None:
    next_node_id = coverage_next_node_id(
        target_factor.factor_key,
        operation_answers,
        param_driver_factor_key=param_driver_factor_key,
        tree_next_node_id=tree_next_node_id,
    )
    if not next_node_id:
        return None
    working_factor = target_factor
    if next_node_id == "coverage_multi_primary":
        multi_answer = operation_answers.get(param_driver_factor_key(target_factor.factor_key, "multi"))
        if multi_answer is not None:
            working_factor = target_factor.model_copy(update={"expected_value": param_answer_display_text(multi_answer)})
    return build_coverage_question_from_node(
        node_id=next_node_id,
        step_name=step_name,
        target_factor=working_factor,
        sample_pairs=sample_pairs,
        round_index=round_index,
        round_total_hint=round_total_hint,
        build_param_question_spec_for_category=build_param_question_spec_for_category,
        default_param_question_meta=default_param_question_meta,
        param_question_tree_meta=param_question_tree_meta,
    )


def build_param_operation_question(
    step_name: str,
    target_factor: ParamReviewedFactorOut,
    question_hint: str,
    sample_pairs: list[dict[str, object]],
    *,
    build_param_question_spec_for_category,
    default_param_question_meta,
    param_question_tree_meta,
    round_index: int = 1,
    round_total_hint: int = 1,
) -> ParamCurrentQuestionOut:
    if round_index <= 1:
        question_type, prompt, options = build_param_question_spec_for_category(
            category="root",
            step_name=step_name,
            target_factor=target_factor,
            sample_pairs=sample_pairs,
        )
    else:
        question_type, prompt, options = build_param_question_spec(
            step_name=step_name,
            target_factor=target_factor,
            question_hint=question_hint,
            sample_pairs=sample_pairs,
            build_param_question_spec_for_category=build_param_question_spec_for_category,
        )
    question_goal, continue_reason = default_param_question_meta(
        question_type=question_type,
        step_name=step_name,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )
    return build_param_current_question(
        factor_key=target_factor.factor_key,
        question_type=question_type,
        prompt=prompt,
        options=options,
        round_index=round_index,
        round_total_hint=round_total_hint,
        question_goal=question_goal,
        continue_reason=continue_reason,
        param_question_tree_meta=param_question_tree_meta,
    )


def build_merge_coverage_question(
    *,
    step_name: str,
    operation_answers,
    sample_pairs: list[dict[str, object]],
    param_driver_factor_key,
    param_answer_display_text,
    tree_node_options,
    root_reason_options_for_step,
    default_param_question_meta,
    with_standard_tail_options,
    param_question_tree_meta,
    tree_next_node_id,
    build_param_question_spec_for_category,
    round_index: int,
    round_total_hint: int,
) -> ParamCurrentQuestionOut | None:
    normalized_name = selected_merge_name(
        step_name=step_name,
        operation_answers=operation_answers,
        param_driver_factor_key=param_driver_factor_key,
        param_answer_display_text=param_answer_display_text,
    )
    target_factor = ParamReviewedFactorOut(
        factor_key="__merge_coverage__",
        factor_label=f"{normalized_name}出现条件",
    )
    if has_terminal_factor_answer(operation_answers, target_factor.factor_key):
        return None
    if not operation_driver_answers(operation_answers, target_factor.factor_key):
        return build_custom_reason_root_question(
            factor_key=target_factor.factor_key,
            step_name=normalized_name,
            prompt=f"这组工序已统一为“{normalized_name}”。如果该工序不是全覆盖，请补充：在什么条件下应保留“{normalized_name}”？",
            round_index=round_index,
            round_total_hint=round_total_hint,
            root_reason_options_for_step=root_reason_options_for_step,
            tree_node_options=tree_node_options,
            default_param_question_meta=default_param_question_meta,
            with_standard_tail_options=with_standard_tail_options,
            param_question_tree_meta=param_question_tree_meta,
        )
    current_question = build_param_followup_question_from_drivers(
        step_name=normalized_name,
        target_factor=target_factor,
        operation_answers=operation_answers,
        sample_pairs=sample_pairs,
        param_driver_factor_key=param_driver_factor_key,
        param_answer_display_text=param_answer_display_text,
        tree_next_node_id=tree_next_node_id,
        build_param_question_spec_for_category=build_param_question_spec_for_category,
        default_param_question_meta=default_param_question_meta,
        param_question_tree_meta=param_question_tree_meta,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )
    if current_question is not None:
        return current_question
    return build_param_operation_question(
        step_name=normalized_name,
        target_factor=target_factor,
        question_hint="",
        sample_pairs=sample_pairs,
        build_param_question_spec_for_category=build_param_question_spec_for_category,
        default_param_question_meta=default_param_question_meta,
        param_question_tree_meta=param_question_tree_meta,
        round_index=round_index,
        round_total_hint=round_total_hint,
    )


def build_param_confirm_question_from_rule(
    rule: dict[str, object],
    factor_fields: list[FactorFieldOut],
    sample_pairs: list[dict[str, object]],
    *,
    normalize_candidate_factor_terms,
    split_condition_terms,
    parse_factor_condition,
    match_rule_expr,
    term_expected_value_text,
    build_param_question_spec_for_category,
) -> ParamConfirmQuestionOut | None:
    stage_name = str(rule.get("stage") or "").strip()
    occurrence_index = int(rule.get("occurrence_index") or 1)
    step_name = str(rule.get("step_name") or "").strip()
    if not stage_name or not step_name:
        return None

    include_when = str(rule.get("include_when") or "").strip()
    candidate_terms = normalize_candidate_factor_terms(rule.get("candidate_factors"))
    if include_when and include_when != "always=true":
        candidate_terms = [*candidate_terms, *split_condition_terms(include_when)]
    target_term = next((term for term in candidate_terms if term and term != "always=true"), "")
    if not target_term:
        return None

    target_factor = build_param_factor_review(
        target_term,
        factor_fields,
        sample_pairs,
        stage_name,
        occurrence_index,
        step_name,
        parse_factor_condition=parse_factor_condition,
        match_rule_expr=match_rule_expr,
        term_expected_value_text=term_expected_value_text,
    )
    question_hint = str(rule.get("question_hint") or "").strip()
    question_type, prompt, options = build_param_question_spec(
        step_name=step_name,
        target_factor=target_factor,
        question_hint=question_hint,
        sample_pairs=sample_pairs,
        build_param_question_spec_for_category=build_param_question_spec_for_category,
    )

    evidence = str(rule.get("evidence") or "").strip()
    why_not_stable = str(rule.get("why_not_stable") or "").strip()
    compile_source = "当前问题来自你修改后的参数规则编译提示词结果。"
    reason = compile_source
    if evidence:
        reason += f" 证据：{evidence}"
    if why_not_stable:
        reason += f" 当前卡点：{why_not_stable}"

    return ParamConfirmQuestionOut(
        key=f"{stage_name}__{occurrence_index}__{step_name}__{target_term}",
        label=f"{step_name} 规则确认",
        prompt=prompt,
        input_type="radio",
        required=str(rule.get("strength") or "STRONG").upper() != "STRONG",
        reason=reason,
        options=options,
    )


__all__ = [
    "build_merge_coverage_question",
    "build_merge_name_question",
    "build_param_confirm_question_from_rule",
    "build_param_current_question",
    "build_param_factor_review",
    "build_param_followup_question_from_drivers",
    "build_param_operation_question",
    "build_param_question_spec",
    "classify_param_operation",
    "coverage_like_status_from_answers",
    "has_terminal_factor_answer",
    "infer_param_question_category",
    "is_merged_step_name",
    "operation_driver_answers",
    "sample_has_stage_step",
    "selected_merge_name",
    "split_step_name_variants",
]
