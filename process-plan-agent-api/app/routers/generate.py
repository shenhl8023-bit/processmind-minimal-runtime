"""
工艺路线生成 API —— 基于影响因素匹配规则并输出工序序列
"""
import json
import os
import re
from collections import Counter
from pathlib import Path
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.orm import selectinload

from app.core.paths import UPLOAD_DIR
from app.database import get_db
from app.models.models import (
    Document,
    FinalizedRulePackage,
    GeneratedRoute,
    Operation,
    ParamAuditAnswer,
    Project,
    Reference,
)
from app.schemas.schemas import (
    FactorFieldOut,
    GenerateRequest,
    GenerateResponse,
    ParamAuditOverviewOut,
    ParamConfirmOptionOut,
    ParamConfirmQuestionOut,
    ParamCandidateCombinationOut,
    ParamCurrentQuestionOut,
    ParamJsonStageOut,
    ParamJsonStepOut,
    ParamOperationReviewOut,
    ParamReviewedFactorOut,
    RouteStep,
)
from app.services.llm_service import call_llm, parse_json_from_llm, get_prompt_template
from app.services.harness_validators import (
    is_harness_warning_factor_name,
    raise_for_harness_errors,
    validate_param_followup_questions,
)
from app.services.generate_factor_schema import extract_document_body, parse_reference_attributes
from app.services.generate_factor_schema_loader import build_project_factor_schema
from app.services.generate_route_result_builder import (
    build_generate_output_json,
    build_generate_summary,
    build_minimal_fallback_steps,
)
from app.services.param_project_context import (
    load_project_resource_bundle,
)
from app.services.question_harness_hooks import build_question_harness_hooks
from app.services.finalized_route_generator import generate_steps_from_finalized_rule_package
from app.services.legacy_operation_route_selector import (
    collapse_redundant_quality_gates as _collapse_redundant_quality_gates,
    select_best_operations as _select_best_operations,
)
from app.services.param_json_route_builder import (
    build_param_sample_stages as _build_param_sample_stages,
    build_param_superset_stages as _build_param_superset_stages,
    read_raw_text_with_fallbacks as _read_raw_text_with_fallbacks,
)
from app.services.param_rule_expression import (
    canonicalize_factor_name as _canonicalize_factor_name,
    humanize_param_rule_expr as _humanize_param_rule_expr,
    match_rule_expr as _match_rule_expr,
    matches_factor_condition as _matches_factor_condition,
    normalize_candidate_factor_terms as _normalize_candidate_factor_terms,
    parse_factor_condition as _parse_factor_condition,
    split_condition_terms as _split_condition_terms,
    strength_rank as _strength_rank,
    term_expected_value_text as _term_expected_value_text,
    to_bool as _to_bool,
    to_float as _to_float,
)
from app.services.param_answer_service import (
    normalize_param_answer_kind as _normalize_param_answer_kind,
    param_answer_display_text as _param_answer_display_text,
    param_answer_expression as _param_answer_expression,
    param_driver_factor_key as _param_driver_factor_key,
    param_driver_storage_key as _param_driver_storage_key,
)
from app.services.param_question_strategy import (
    default_param_question_meta as _default_param_question_meta,
    estimate_param_operation_round_limit as _estimate_param_operation_round_limit,
    param_operation_family as _param_operation_family,
    param_question_tree_meta as _param_question_tree_meta,
    sort_param_question_options as _sort_param_question_options,
)
from app.services.param_question_tree_config import (
    tree_next_node_id as _tree_next_node_id,
    tree_node_options as _tree_node_options,
    tree_node_question as _tree_node_question,
    tree_node_question_type as _tree_node_question_type,
)
from app.services.param_question_option_builder import (
    root_reason_options_for_step as _root_reason_options_for_step,
    with_standard_tail_options as _with_standard_tail_options,
)
from app.services.param_question_spec_builder import (
    _build_param_question_spec_for_category,
    _factor_review_display_label,
    _selected_factor_key_from_answer,
    _should_continue_param_operation_questions,
)
from app.services.param_question_flow import (
    build_merge_coverage_question as _build_merge_coverage_question,
    build_merge_name_question as _build_merge_name_question,
    build_param_confirm_question_from_rule as _build_param_confirm_question_from_rule,
    build_param_factor_review as _build_param_factor_review,
    build_param_followup_question_from_drivers as _build_param_followup_question_from_drivers,
    build_param_operation_question as _build_param_operation_question,
    build_param_question_spec as _build_param_question_spec,
    classify_param_operation as _classify_param_operation,
    coverage_like_status_from_answers as _coverage_like_status_from_answers,
    is_merged_step_name as _is_merged_step_name,
    sample_has_stage_step as _sample_has_stage_step,
    selected_merge_name as _selected_merge_name,
)

router = APIRouter(prefix="/api/generate", tags=["工艺路线生成"])

def _normalize_input_values(body: GenerateRequest) -> dict[str, object]:
    values = dict(body.factor_values or {})
    legacy = {
        "family": body.family,
        "material": body.material,
        "hardness": body.hardness,
        "has_hole": body.has_hole,
        "has_spline": body.has_spline,
        "roughness": body.roughness,
    }
    for key, value in legacy.items():
        if key not in values and value not in ("", None):
            values[key] = value
    return values


async def _latest_finalized_rule_package(project_id: int, db: AsyncSession) -> FinalizedRulePackage | None:
    return (
        await db.execute(
            select(FinalizedRulePackage)
            .where(FinalizedRulePackage.project_id == project_id)
            .order_by(FinalizedRulePackage.version.desc(), FinalizedRulePackage.id.desc())
        )
    ).scalar_one_or_none()


def _source_labels_for_factor_field(field: FactorFieldOut) -> list[str]:
    if field.key == "material":
        return ["零件材质", "材料", "材质"]
    if field.key == "structure_type":
        return ["结构类型", "零件类型", "零件家族"]
    if field.key.startswith("ref__"):
        return [field.label]
    return [field.label]


def _field_value_counts_from_rows(field: FactorFieldOut, rows: list[dict[str, str]]) -> Counter[str]:
    counts: Counter[str] = Counter()
    labels = _source_labels_for_factor_field(field)
    for attrs in rows:
        for label in labels:
            value = str(attrs.get(label, "")).strip()
            if value:
                counts[value] += 1
                break
    return counts


def _value_for_factor_field(field: FactorFieldOut, attrs: dict[str, str]) -> str:
    labels = _source_labels_for_factor_field(field)
    for label in labels:
        value = str(attrs.get(label, "")).strip()
        if value:
            return _normalize_question_option_value(field, value)
    return ""


def _normalize_question_option_value(field: FactorFieldOut, raw_value: str) -> str:
    value = raw_value.strip()
    if field.input_type == "boolean":
        return "true" if value == "是" else "false"
    return value


def _label_for_option_value(field: FactorFieldOut, option_value: str, fallback: str) -> str:
    for option in field.options:
        if option.value == option_value:
            return option.label
    return fallback


def _sample_key_for_document(doc: Document) -> str:
    return Path(doc.original_name or doc.filename or "").stem.strip().lower()


def _build_process_presence_pairs(documents: list[Document]) -> list[tuple[dict[str, str], set[str]]]:
    param_docs: dict[str, dict[str, str]] = {}
    json_docs: dict[str, set[str]] = {}

    for doc in documents:
        file_type = (doc.file_type or "").lower()
        sample_key = _sample_key_for_document(doc)
        if not sample_key:
            continue

        if file_type == "json":
            if not doc.filename:
                continue
            filepath = os.path.join(UPLOAD_DIR, doc.filename)
            if not os.path.exists(filepath):
                continue
            try:
                raw_text = _read_raw_text_with_fallbacks(filepath)
            except Exception:
                continue
            stages = _build_param_sample_stages(raw_text)
            process_names = {step.name for stage in stages for step in stage.steps if step.name}
            if process_names:
                json_docs[sample_key] = process_names
            continue

        attrs = parse_reference_attributes(extract_document_body(doc))
        if attrs:
            param_docs[sample_key] = attrs

    pairs: list[tuple[dict[str, str], set[str]]] = []
    for sample_key in sorted(set(param_docs.keys()) & set(json_docs.keys())):
        pairs.append((param_docs[sample_key], json_docs[sample_key]))
    return pairs


def _build_param_confirm_questions(factor_fields: list[FactorFieldOut], documents: list[Document], limit: int = 6) -> list[ParamConfirmQuestionOut]:
    pairs = _build_process_presence_pairs(documents)
    if len(pairs) < 4:
        return []

    all_processes = sorted({process for _, processes in pairs for process in processes})
    candidates: list[tuple[tuple[int, float, int, str], ParamConfirmQuestionOut]] = []

    for field in factor_fields:
        if field.input_type not in {"boolean", "select", "radio"}:
            continue

        values = [_value_for_factor_field(field, attrs) for attrs, _ in pairs]
        counts = Counter(value for value in values if value)
        if len(counts) < 2:
            continue

        best_question: ParamConfirmQuestionOut | None = None
        best_score: tuple[int, float, int, str] | None = None
        total_pairs = len(pairs)

        for option_value, option_total in counts.items():
            if option_total < 3:
                continue

            option_label = _label_for_option_value(field, option_value, "是" if option_value == "true" else "否" if option_value == "false" else option_value)
            for process_name in all_processes:
                hit = sum(1 for (attrs, processes) in pairs if _value_for_factor_field(field, attrs) == option_value and process_name in processes)
                other_total = sum(1 for attrs, _ in pairs if _value_for_factor_field(field, attrs) and _value_for_factor_field(field, attrs) != option_value)
                other_hit = sum(1 for (attrs, processes) in pairs if _value_for_factor_field(field, attrs) and _value_for_factor_field(field, attrs) != option_value and process_name in processes)
                if hit < 3 or other_total < 2:
                    continue

                rate = hit / option_total
                other_rate = other_hit / other_total if other_total else 0.0
                diff = rate - other_rate
                if rate < 0.6 or diff < 0.35:
                    continue

                reason = (
                    f"样本统计显示：当“{field.label}={option_label}”时，"
                    f"{hit}/{option_total} 份样本出现“{process_name}”；"
                    f"其他取值时仅 {other_hit}/{other_total} 份出现。"
                )
                question = ParamConfirmQuestionOut(
                    key=f"confirm_relation__{field.key}__{process_name}__{option_value}",
                    label=field.label,
                    prompt=f"从当前候选条件看，“{field.label}={option_label}”是否应作为工序“{process_name}”的候选触发条件？",
                    input_type="radio",
                    required=field.required,
                    reason=reason,
                    options=[
                        ParamConfirmOptionOut(value="agree", label="可作为候选条件", count=0),
                        ParamConfirmOptionOut(value="disagree", label="更像伴随现象", count=0),
                    ],
                )
                priority = 0 if field.required else 1
                score = (priority, -(diff * rate), -option_total, question.prompt)
                if best_score is None or score < best_score:
                    best_score = score
                    best_question = question

        if best_question and best_score:
            candidates.append((best_score, best_question))

    candidates.sort(key=lambda item: item[0])
    return [question for _, question in candidates[:limit]]


def _build_param_confirm_questions_from_compiled_rules(
    compiled_rules: list[dict[str, object]],
    factor_fields: list[FactorFieldOut],
    sample_pairs: list[dict[str, object]],
    compiled_with_llm: bool,
    limit: int = 6,
) -> list[ParamConfirmQuestionOut]:
    if not compiled_rules:
        return []

    questions: list[tuple[tuple[int, int, int, str], ParamConfirmQuestionOut]] = []
    seen_keys: set[str] = set()

    for rule in compiled_rules:
        include_when = str(rule.get("include_when") or "").strip()
        if not include_when or include_when == "always=true":
            continue

        stage_name = str(rule.get("stage") or "").strip()
        occurrence_index = int(rule.get("occurrence_index") or 1)
        step_name = str(rule.get("step_name") or "").strip()
        strength = str(rule.get("strength") or "STRONG").upper()
        priority = int(rule.get("priority") or 100)
        question_key = f"{stage_name}__{occurrence_index}__{step_name}__{include_when}"
        if question_key in seen_keys:
            continue
        seen_keys.add(question_key)

        question = _build_param_confirm_question_from_rule(rule, factor_fields, sample_pairs)
        if question is None:
            continue
        if not compiled_with_llm:
            question.reason = "当前未命中 LLM 规则编译，问题基于启发式规则草案生成。 " + question.reason

        questions.append((
            (_strength_rank(strength), priority, -len(_split_condition_terms(include_when)), question_key),
            question,
        ))

    return [question for _, question in sorted(questions, key=lambda item: item[0])[:limit]]


def _param_operation_key(stage: str, occurrence_index: int, step_name: str) -> str:
    return f"{stage}__{occurrence_index}__{step_name}"


async def _enhance_param_operation_questions_with_llm(
    operation_reviews: list[ParamOperationReviewOut],
) -> list[ParamOperationReviewOut]:
    candidates = [item for item in operation_reviews if item.current_question]
    if not candidates:
        return operation_reviews

    payload = {
        "questions": [
            {
                "operation_key": item.operation_key,
                "stage": item.stage,
                "step_name": item.step_name,
                "operation_kind": item.operation_kind,
                "operation_kind_reason": item.operation_kind_reason,
                "review_status": item.review_status,
                "summary": item.summary,
                "pending_factors": [
                    {
                        "factor_key": factor.factor_key,
                        "factor_label": factor.factor_label,
                        "expected_value": factor.expected_value,
                        "reason_text": factor.reason_text,
                    }
                    for factor in item.pending_factors[:3]
                ],
                "resolved_factors": [
                    {
                        "factor_key": factor.factor_key,
                        "factor_label": factor.factor_label,
                        "expected_value": factor.expected_value,
                    }
                    for factor in item.resolved_factors[:3]
                ],
                "answer_summary": item.answer_summary,
                "question_round_completed": item.question_round_completed,
                "question_round_limit": item.question_round_limit,
                "current_question": {
                    "factor_key": item.current_question.factor_key,
                    "question_type": item.current_question.question_type,
                    "prompt": item.current_question.prompt,
                    "tree_branch": item.current_question.tree_branch,
                    "tree_node_id": item.current_question.tree_node_id,
                    "option_source": item.current_question.option_source,
                    "round_index": item.current_question.round_index,
                    "round_total_hint": item.current_question.round_total_hint,
                    "options": [
                        {
                            "value": option.value,
                            "label": option.label,
                            "count": option.count,
                        }
                        for option in item.current_question.options
                    ],
                },
                "candidate_combination": (
                    item.candidate_combination.expression_text if item.candidate_combination else ""
                ),
                "stop_conditions": [
                    "已能形成规则边界",
                    "达到建议追问上限",
                    "连续两轮暂不确定",
                    "样本/数据需核查",
                    "继续追问只会进入过细术语层",
                ],
            }
            for item in candidates
        ]
    }

    try:
        system_prompt = get_prompt_template("param_followup_question_system")
        user_prompt_template = get_prompt_template("param_followup_question_user")
        if not system_prompt.strip() or not user_prompt_template.strip():
            return operation_reviews
        user_prompt = user_prompt_template.replace(
            "{{question_payload_json}}",
            json.dumps(payload, ensure_ascii=False, indent=2),
        )
        llm_text = await call_llm(system_prompt, user_prompt, temperature=0.1)
        llm_json = parse_json_from_llm(llm_text) if llm_text else None
        rows = llm_json.get("questions") if isinstance(llm_json, dict) else llm_json
        if not isinstance(rows, list):
            return operation_reviews
        question_harness = validate_param_followup_questions(payload=payload, rows=rows)
        raise_for_harness_errors(question_harness, stage="param_followup_questions")

        enhancement_map: dict[tuple[str, str, str], dict[str, object]] = {}
        for row in rows:
            if not isinstance(row, dict):
                continue
            operation_key = str(row.get("operation_key") or "").strip()
            factor_key = str(row.get("factor_key") or "").strip()
            question_type = str(row.get("question_type") or "").strip()
            if not operation_key or not factor_key or not question_type:
                continue
            enhancement_map[(operation_key, factor_key, question_type)] = row

        enhanced_reviews: list[ParamOperationReviewOut] = []
        for review in operation_reviews:
            current = review.current_question
            if not current:
                enhanced_reviews.append(review)
                continue
            row = enhancement_map.get((review.operation_key, current.factor_key, current.question_type))
            if not row:
                enhanced_reviews.append(review)
                continue

            prompt = str(row.get("question_text") or "").strip() or current.prompt
            ordered_values = row.get("recommended_option_values")
            ordered_options = _sort_param_question_options(
                current.options,
                [str(item) for item in ordered_values] if isinstance(ordered_values, list) else [],
            )
            continue_strategy = row.get("continue_strategy") if isinstance(row.get("continue_strategy"), dict) else {}
            question_goal = str(row.get("question_goal") or "").strip()
            continue_reason = str(continue_strategy.get("reason") or "").strip()
            next_focus = str(continue_strategy.get("next_focus") or "").strip()
            enhanced_reviews.append(
                review.model_copy(
                    update={
                        "current_question": current.model_copy(
                            update={
                                "prompt": prompt,
                                "options": ordered_options,
                                "question_goal": question_goal,
                                "continue_reason": continue_reason,
                                "next_focus": next_focus,
                                "llm_enhanced": True,
                            }
                        ),
                        "question_hooks": build_question_harness_hooks(
                            operation_name=review.step_name,
                            coverage_count=review.sample_hit_count,
                            sample_count=review.sample_total_count,
                            is_combination=review.operation_kind == "merged_name",
                            questions=[
                                current.model_copy(
                                    update={
                                        "prompt": prompt,
                                        "options": ordered_options,
                                        "question_goal": question_goal,
                                        "continue_reason": continue_reason,
                                        "next_focus": next_focus,
                                        "llm_enhanced": True,
                                    }
                                )
                            ],
                        ),
                    }
                )
            )
        return enhanced_reviews
    except Exception:
        return operation_reviews


async def _load_param_audit_answer_map(
    db: AsyncSession,
    project_id: int,
) -> dict[str, dict[str, ParamAuditAnswer]]:
    result = await db.execute(
        select(ParamAuditAnswer)
        .where(ParamAuditAnswer.project_id == project_id)
        .order_by(ParamAuditAnswer.updated_at.desc(), ParamAuditAnswer.id.desc())
    )
    rows = result.scalars().all()
    mapping: dict[str, dict[str, ParamAuditAnswer]] = {}
    for row in rows:
        bucket = mapping.setdefault(row.operation_key, {})
        if row.factor_key not in bucket:
            bucket[row.factor_key] = row
    return mapping


def _build_param_pending_questions_from_reviews(
    operation_reviews: list[ParamOperationReviewOut],
) -> list[ParamConfirmQuestionOut]:
    questions: list[ParamConfirmQuestionOut] = []
    for review in operation_reviews:
        current_question = review.current_question
        if not current_question:
            continue
        pending_reason = review.pending_factors[0].reason_text if review.pending_factors else review.summary
        questions.append(
            ParamConfirmQuestionOut(
                key=f"{review.operation_key}__{current_question.factor_key}",
                label=f"{review.step_name} 规则确认",
                prompt=current_question.prompt,
                input_type="radio",
                required=True,
                reason=pending_reason,
                options=current_question.options,
            )
        )
    return questions
def _build_param_operation_reviews(
    factor_fields: list[FactorFieldOut],
    compiled_rules: list[dict[str, object]],
    sample_pairs: list[dict[str, object]],
    superset_stages: list[ParamJsonStageOut],
    answer_map: dict[str, dict[str, ParamAuditAnswer]] | None = None,
) -> list[ParamOperationReviewOut]:
    rules_by_operation: dict[str, list[dict[str, object]]] = defaultdict(list)
    for rule in compiled_rules:
        op_key = _param_operation_key(
            str(rule.get("stage") or "").strip(),
            int(rule.get("occurrence_index") or 1),
            str(rule.get("step_name") or "").strip(),
        )
        rules_by_operation[op_key].append(rule)

    reviews: list[ParamOperationReviewOut] = []
    sample_total = len(sample_pairs)
    for stage in superset_stages:
        for step in stage.steps:
            op_key = _param_operation_key(stage.stage, stage.occurrence_index, step.name)
            op_rules = rules_by_operation.get(op_key, [])
            operation_answers = (answer_map or {}).get(op_key, {})
            factor_answers = {
                key: value for key, value in operation_answers.items()
                if not key.startswith("__driver__::")
            }
            question_round_limit = _estimate_param_operation_round_limit(step.name)
            term_order: list[str] = []
            seen_terms: set[str] = set()
            why_not_stable = ""
            question_hint = ""
            for rule in sorted(
                op_rules,
                key=lambda item: (
                    _strength_rank(str(item.get("strength") or "STRONG")),
                    int(item.get("priority") or 100),
                    str(item.get("include_when") or ""),
                ),
            ):
                if not why_not_stable:
                    why_not_stable = str(rule.get("why_not_stable") or "").strip()
                if not question_hint:
                    question_hint = str(rule.get("question_hint") or "").strip()
                include_when = str(rule.get("include_when") or "").strip()
                if not include_when or include_when == "always=true":
                    candidate_terms = _normalize_candidate_factor_terms(rule.get("candidate_factors"))
                else:
                    candidate_terms = _split_condition_terms(include_when)
                if include_when and include_when != "always=true":
                    extra_terms = _normalize_candidate_factor_terms(rule.get("candidate_factors"))
                    if extra_terms:
                        candidate_terms = [*candidate_terms, *extra_terms]
                for term in candidate_terms:
                    normalized = term.strip()
                    if not normalized or normalized in seen_terms:
                        continue
                    seen_terms.add(normalized)
                    term_order.append(normalized)

            resolved_factors: list[ParamReviewedFactorOut] = []
            pending_factors: list[ParamReviewedFactorOut] = []
            auxiliary_factors: list[ParamReviewedFactorOut] = []
            answer_summaries: list[str] = []
            has_answered_factor = bool(operation_answers)
            main_factor_answer = operation_answers.get("__driver__::main_factor")
            main_factor_key = _selected_factor_key_from_answer(main_factor_answer)
            rule_shape_answer = operation_answers.get("__driver__::rule_shape")
            rule_shape_value = (rule_shape_answer.selected_value or "").strip() if rule_shape_answer else ""
            partner_answer = operation_answers.get("__driver__::combo_partner")
            partner_factor_key = _selected_factor_key_from_answer(partner_answer)

            main_answer_text = _param_answer_display_text(main_factor_answer)
            if main_answer_text:
                answer_summaries.append(f"主导因素={main_answer_text}")
            shape_answer_text = _param_answer_display_text(rule_shape_answer)
            if shape_answer_text:
                answer_summaries.append(f"规则形态={shape_answer_text}")
            partner_answer_text = _param_answer_display_text(partner_answer)
            if partner_answer_text:
                answer_summaries.append(f"联合因素={partner_answer_text}")

            factor_key_order: list[str] = []
            factor_term_map: dict[str, str] = {}
            for term in term_order:
                parsed = _parse_factor_condition(str(term or "").strip().replace(" ", ""))
                factor_key = str(parsed.get("key") or term) if parsed else str(term or "").strip()
                if factor_key and factor_key not in factor_term_map:
                    factor_key_order.append(factor_key)
                    factor_term_map[factor_key] = term

            selected_factor_keys: set[str] = set()
            if main_factor_key:
                selected_factor_keys.add(main_factor_key)
            if rule_shape_value == "shape::combination" and partner_factor_key:
                selected_factor_keys.add(partner_factor_key)

            shape_resolved = rule_shape_value == "shape::single" or (
                rule_shape_value == "shape::combination" and bool(partner_factor_key)
            )
            excluded_factor_keys: set[str] = set()
            if shape_resolved and selected_factor_keys:
                excluded_factor_keys = set(factor_key_order) - selected_factor_keys

            for term in term_order:
                factor_review = _build_param_factor_review(
                    term,
                    factor_fields,
                    sample_pairs,
                    stage.stage,
                    stage.occurrence_index,
                    step.name,
                    parse_factor_condition=_parse_factor_condition,
                    match_rule_expr=_match_rule_expr,
                    term_expected_value_text=_term_expected_value_text,
                )
                answer = factor_answers.get(factor_review.factor_key)

                if factor_review.status == "resolved":
                    resolved_factors.append(factor_review)
                    continue

                if factor_review.factor_key in selected_factor_keys:
                    selected_answer = main_factor_answer if factor_review.factor_key == main_factor_key else partner_answer
                    resolved_factors.append(
                        factor_review.model_copy(
                            update={
                                "status": "resolved",
                                "expected_value": _param_answer_display_text(selected_answer) or factor_review.expected_value,
                                "coverage_count": factor_review.total_count or factor_review.coverage_count,
                                "reason_type": "user_confirmed",
                                "reason_text": "工艺专家已将该候选因素确认为当前工序规则的关键条件。",
                            }
                        )
                    )
                    continue

                if factor_review.factor_key in excluded_factor_keys:
                    auxiliary_factors.append(
                        factor_review.model_copy(
                            update={
                                "status": "evidence",
                                "reason_type": "accompanying_factor",
                                "reason_text": "当前已确认其他候选因素为主导或联合条件，该因素先按伴随候选保留，不写入主规则。",
                            }
                        )
                    )
                    continue

                if answer is None:
                    pending_factors.append(factor_review)
                    continue

                has_answered_factor = True
                answer_text = _param_answer_display_text(answer)
                if answer_text:
                    answer_summaries.append(f"{factor_review.factor_label}={answer_text}")

                if answer.answer_kind in {"selected", "custom"}:
                    resolved_factors.append(
                        factor_review.model_copy(
                            update={
                                "status": "resolved",
                                "expected_value": answer_text or factor_review.expected_value,
                                "coverage_count": factor_review.total_count or factor_review.coverage_count,
                                "reason_type": "user_confirmed",
                                "reason_text": f"工艺专家已确认该因素边界：{answer_text or factor_review.expected_value or factor_review.factor_label}",
                            }
                        )
                    )
                elif answer.answer_kind == "data_issue":
                    auxiliary_factors.append(
                        factor_review.model_copy(
                            update={
                                "status": "data_issue",
                                "reason_type": "data_issue",
                                "reason_text": answer_text or "已由工艺专家标记为样本/数据需核查。",
                            }
                        )
                    )
                else:
                    auxiliary_factors.append(
                        factor_review.model_copy(
                            update={
                                "status": "evidence",
                                "reason_type": "manual_unsure",
                                "reason_text": answer_text or "工艺专家当前暂不确定，保留待后续确认。",
                            }
                        )
                    )

            candidate_combination = None
            if selected_factor_keys and shape_resolved:
                ordered_selected = [key for key in factor_key_order if key in selected_factor_keys]
                candidate_combination = ParamCandidateCombinationOut(
                    factor_keys=ordered_selected,
                    expression_text=" and ".join(factor_term_map.get(key, key) for key in ordered_selected),
                    status="stable",
                )
            elif term_order:
                combination_factor_keys: list[str] = []
                for factor in [*resolved_factors, *pending_factors]:
                    if factor.factor_key not in combination_factor_keys:
                        combination_factor_keys.append(factor.factor_key)
                candidate_combination = ParamCandidateCombinationOut(
                    factor_keys=combination_factor_keys,
                    expression_text=" and ".join(term_order),
                    status="stable" if not pending_factors else "pending_confirm",
                )

            answered_round_count = len(operation_answers)
            unsure_count = sum(1 for item in operation_answers.values() if item.answer_kind == "unsure")
            has_data_issue = any(item.status == "data_issue" for item in auxiliary_factors)
            stop_due_to_unsure = bool(pending_factors) and unsure_count >= 2
            stop_due_to_round_limit = bool(pending_factors) and answered_round_count >= question_round_limit

            if _should_continue_param_operation_questions(
                pending_factors=pending_factors,
                has_data_issue=has_data_issue,
                stop_due_to_unsure=stop_due_to_unsure,
                stop_due_to_round_limit=stop_due_to_round_limit,
            ):
                review_status = "pending_confirm"
            elif has_data_issue:
                review_status = "data_issue"
            elif stop_due_to_unsure or stop_due_to_round_limit or any(item.status == "evidence" for item in auxiliary_factors):
                review_status = "evidence"
            else:
                review_status = "stable"

            if not term_order and step.evidence_count >= sample_total and sample_total > 0:
                summary = "该工序在全部样本中稳定出现，当前可视为稳定主线工序。"
            elif stop_due_to_unsure:
                summary = "该工序已连续两轮被标记为暂不确定，当前先保留为待确认边界。"
            elif stop_due_to_round_limit:
                summary = f"该工序已达到建议追问上限（{question_round_limit} 轮），当前先保留为待确认边界。"
            elif pending_factors:
                summary = why_not_stable or f"该工序当前仍有 {len(pending_factors)} 个关键相关因素未收敛。"
            elif review_status == "data_issue":
                summary = "该工序已完成人工审核，但当前被标记为样本/数据需核查。"
            elif review_status == "evidence":
                summary = "该工序已完成人工审核，但当前仍保留暂不确定边界。"
            elif selected_factor_keys and rule_shape_value == "shape::single":
                main_label = next(
                    (_factor_review_display_label(factor) for factor in resolved_factors if factor.factor_key == main_factor_key),
                    main_factor_key,
                )
                summary = f"该工序已确认由单一主导因素“{main_label}”解释。"
            elif selected_factor_keys and rule_shape_value == "shape::combination":
                summary = "该工序已确认需要多个候选因素联合成立。"
            elif resolved_factors:
                summary = "该工序已由当前关键相关因素零反例解释。"
            else:
                summary = "该工序当前尚未识别出可直接审核的关键相关因素。"

            current_question = None
            operation_kind, operation_kind_reason, _ = _classify_param_operation(step.name)
            if operation_kind == "merged_name":
                merge_name_answer = operation_answers.get(_param_driver_factor_key("__merge__", "name"))
                need_rename_confirm = _is_merged_step_name(step.name)
                fully_covered = sample_total > 0 and step.evidence_count >= sample_total
                merge_round_limit = 1 if fully_covered else 4
                if need_rename_confirm and merge_name_answer is None:
                    current_question = _build_merge_name_question(
                        step_name=step.name,
                        round_index=1,
                        round_total_hint=merge_round_limit,
                        tree_node_question_type=_tree_node_question_type,
                        tree_node_question=_tree_node_question,
                        default_param_question_meta=_default_param_question_meta,
                        with_standard_tail_options=_with_standard_tail_options,
                        param_question_tree_meta=_param_question_tree_meta,
                    )
                elif not fully_covered:
                    coverage_round_index = 2 if need_rename_confirm else 1
                    merge_answered = len(operation_answers)
                    current_question = _build_merge_coverage_question(
                        step_name=step.name,
                        operation_answers=operation_answers,
                        sample_pairs=sample_pairs,
                        param_driver_factor_key=_param_driver_factor_key,
                        param_answer_display_text=_param_answer_display_text,
                        tree_node_options=_tree_node_options,
                        root_reason_options_for_step=_root_reason_options_for_step,
                        default_param_question_meta=_default_param_question_meta,
                        with_standard_tail_options=_with_standard_tail_options,
                        param_question_tree_meta=_param_question_tree_meta,
                        tree_next_node_id=_tree_next_node_id,
                        build_param_question_spec_for_category=_build_param_question_spec_for_category,
                        round_index=min(max(coverage_round_index, merge_answered + 1), merge_round_limit),
                        round_total_hint=merge_round_limit,
                    )
                selected_name = _selected_merge_name(step_name=step.name, operation_answers=operation_answers)
                if current_question is not None:
                    if current_question.question_type == "merge_name_select":
                        review_status = "pending_confirm"
                        summary = f"组合名工序“{step.name}”还需要先确认统一名称。"
                    else:
                        review_status = "pending_confirm"
                        summary = f"组合名工序“{step.name}”已确认统一名称“{selected_name}”，仍需补充出现条件。"
                elif fully_covered:
                    review_status = "stable"
                    summary = f"组合名工序“{step.name}”已统一为名称“{selected_name}”，且已全覆盖，无需继续追问。"
                else:
                    review_status, summary = _coverage_like_status_from_answers(
                        current_question=current_question,
                        operation_answers=operation_answers,
                        factor_key="__merge_coverage__",
                        pending_message=f"组合名工序“{step.name}”已确认统一名称“{selected_name}”，仍需补充出现条件。",
                        stable_message=f"组合名工序“{step.name}”已统一为名称“{selected_name}”，当前规则已收敛。",
                        evidence_message=f"组合名工序“{step.name}”已完成命名，但当前出现条件仍有证据不足，先保留待复核。",
                    )
            elif _should_continue_param_operation_questions(
                pending_factors=pending_factors,
                has_data_issue=has_data_issue,
                stop_due_to_unsure=stop_due_to_unsure,
                stop_due_to_round_limit=stop_due_to_round_limit,
            ):
                round_index = min(answered_round_count + 1, question_round_limit)
                round_total_hint = question_round_limit
                target_factor = pending_factors[0]
                current_question = _build_param_followup_question_from_drivers(
                    step_name=step.name,
                    target_factor=target_factor,
                    operation_answers=operation_answers,
                    sample_pairs=sample_pairs,
                    param_driver_factor_key=_param_driver_factor_key,
                    param_answer_display_text=_param_answer_display_text,
                    tree_next_node_id=_tree_next_node_id,
                    build_param_question_spec_for_category=_build_param_question_spec_for_category,
                    default_param_question_meta=_default_param_question_meta,
                    param_question_tree_meta=_param_question_tree_meta,
                    round_index=round_index,
                    round_total_hint=round_total_hint,
                )
                if current_question is None:
                    current_question = _build_param_operation_question(
                        step_name=step.name,
                        target_factor=target_factor,
                        question_hint=question_hint,
                        sample_pairs=sample_pairs,
                        build_param_question_spec_for_category=_build_param_question_spec_for_category,
                        default_param_question_meta=_default_param_question_meta,
                        param_question_tree_meta=_param_question_tree_meta,
                        round_index=round_index,
                        round_total_hint=round_total_hint,
                    )

            reviews.append(
                ParamOperationReviewOut(
                    operation_key=op_key,
                    stage=stage.stage,
                    occurrence_index=stage.occurrence_index,
                    step_name=step.name,
                    sample_hit_count=step.evidence_count,
                    sample_total_count=sample_total,
                    review_status=review_status,
                    summary=summary,
                    operation_kind=operation_kind,
                    operation_kind_reason=operation_kind_reason,
                    resolved_factors=resolved_factors,
                    pending_factors=pending_factors,
                    auxiliary_factors=auxiliary_factors,
                    candidate_combination=candidate_combination,
                    current_question=current_question,
                    answered=has_answered_factor,
                    answer_summary="；".join(answer_summaries),
                    question_round_completed=answered_round_count,
                    question_round_limit=question_round_limit,
                    question_hooks=build_question_harness_hooks(
                        operation_name=step.name,
                        coverage_count=step.evidence_count,
                        sample_count=sample_total,
                        is_combination=operation_kind == "merged_name",
                        questions=[current_question] if current_question is not None else [],
                    ),
                )
            )

    return reviews


def _build_param_audit_overview(operation_reviews: list[ParamOperationReviewOut], sample_pair_count: int) -> ParamAuditOverviewOut:
    stable_count = sum(1 for item in operation_reviews if item.review_status == "stable")
    pending_count = sum(1 for item in operation_reviews if item.review_status == "pending_confirm")
    data_issue_count = sum(1 for item in operation_reviews if item.review_status == "data_issue")
    return ParamAuditOverviewOut(
        sample_pair_count=sample_pair_count,
        operation_count=len(operation_reviews),
        stable_operation_count=stable_count,
        pending_operation_count=pending_count,
        data_issue_operation_count=data_issue_count,
    )
@router.get("/factor-schema", response_model=list[FactorFieldOut])
async def get_factor_schema(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    resources = await load_project_resource_bundle(project_id, db)
    project = resources.project
    if not project:
        raise HTTPException(404, "任务不存在")

    references = resources.references

    result = await db.execute(
        select(Operation)
        .where(Operation.project_id == project_id)
        .options(selectinload(Operation.factors))
        .order_by(Operation.sequence, Operation.id)
    )
    operations = result.scalars().all()
    return build_project_factor_schema(
        operations,
        references,
        parse_factor_condition=_parse_factor_condition,
        is_warning_factor_name=is_harness_warning_factor_name,
    )


@router.post("/", response_model=GenerateResponse)
async def generate_route(
    body: GenerateRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    基于用户录入的影响因素生成工艺路线。
    当前版本优先读取第四步定稿导出的规则包；
    若规则包不存在，则退回第二步产出的工序与影响因素规则。
    """
    if not body.project_id:
        raise HTTPException(400, "project_id 不能为空")

    resources = await load_project_resource_bundle(body.project_id, db)
    project = resources.project
    if not project:
        raise HTTPException(404, "任务不存在")

    steps: list[RouteStep] = []
    summary = "当前已基于第二步提炼结果生成路线"
    output_mode = "route_rules"
    result = await db.execute(
        select(Operation)
        .where(Operation.project_id == body.project_id)
        .options(selectinload(Operation.factors))
        .order_by(Operation.sequence, Operation.id)
    )
    operations = result.scalars().all()
    inputs = _normalize_input_values(body)
    finalized_package = await _latest_finalized_rule_package(body.project_id, db)
    if finalized_package:
        package_result = generate_steps_from_finalized_rule_package(
            finalized_package,
            inputs,
            collapse_quality_gates=_collapse_redundant_quality_gates,
            parse_factor_condition=_parse_factor_condition,
            matches_factor_condition=_matches_factor_condition,
            to_bool=_to_bool,
            to_float=_to_float,
        )
        if package_result:
            steps, summary = package_result
            output_mode = "finalized_rule_package"

    if not steps and operations:
        steps = _select_best_operations(operations, inputs)
    elif not steps:
        steps = build_minimal_fallback_steps(inputs, to_bool=_to_bool, to_float=_to_float)

    # 持久化
    route = GeneratedRoute(
        project_id=body.project_id,
        input_factors=body.model_dump_json(),
        result_json=json.dumps([s.model_dump() for s in steps], ensure_ascii=False),
    )
    db.add(route)
    project.status = "GENERATED"
    await db.commit()
    await db.refresh(route)

    return GenerateResponse(
        id=route.id,
        steps=steps,
        summary=build_generate_summary(steps, summary),
        output_json_text=build_generate_output_json(body.project_id, output_mode, steps),
        output_mode=output_mode,
    )
