"""Natural-language parser for user-authored process conditions."""

from __future__ import annotations

import json
import logging
import os

from app.services.llm_service import call_llm, parse_json_from_llm
from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_registry import (
    FIELD_REGISTRY_VERSION,
    condition_fields,
)
from app.services.rule_packages.condition_semantics import (
    bind_candidate_factors as _bind_candidate_factors,
    candidate_from_payload as _candidate_from_payload,
    has_unregistered_project_factor as _has_unregistered_project_factor,
    validate_candidate,
    with_source_evidence as _with_source_evidence,
)

from app.services.rule_packages.condition_parser_local import (
    known_special_requirement as _known_special_requirement,
    parse_condition_tree as _parse_condition_tree,
    parse_local_condition as _parse_locally,
    parse_partial_condition_candidate as _partial_condition_candidate,
    parse_process_relation as _parse_process_relation,
)

CONDITION_PARSER_VERSION = "2026.08.04.2"
logger = logging.getLogger(__name__)


def _condition_llm_timeout_seconds() -> float:
    try:
        value = float(os.getenv("RULE_CONDITION_LLM_TIMEOUT_SECONDS", "45"))
    except (TypeError, ValueError):
        value = 45.0
    return max(5.0, min(value, 300.0))


def _condition_llm_max_retries() -> int:
    try:
        value = int(os.getenv("RULE_CONDITION_LLM_MAX_RETRIES", "1"))
    except (TypeError, ValueError):
        value = 1
    return max(0, min(value, 3))


async def _parse_with_llm(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
    *,
    llm_config: dict[str, str] | None = None,
) -> tuple[RuleConditionCandidate | None, float | None, list[str]]:
    fields_payload = [
        {
            "key": item.key,
            "label": item.label,
            "type": item.type,
            "unit": item.unit,
            "operators": item.operators,
            "aliases": item.aliases,
            "options": item.options,
        }
        for item in condition_fields()
    ]
    system_prompt = """你是机械加工规则条件解析器。只输出一个 JSON 对象，不要输出 Markdown 或解释。
工序只能使用输入给出的 process_id，禁止创造工序。
条件字段优先复用 allowed_fields。原文明确给出了新的属性名称和取值、但 allowed_fields 无法表达时，必须创建项目动态因素，并放入 candidate.field_definitions；禁止把明确的属性条件错误塞进“特殊要求”。
动态因素 key 必须以 project_factor. 开头，只能使用小写英文字母、数字、点、下划线和连字符；label 保留用户原始中文字段名。类别取值使用 single_select，是否类使用 boolean，数值阈值使用 number；动态类别允许后续出现更多取值，所以 allow_custom 必须为 true。
优先判断是否为工序关系：触发并排序(trigger_after)、仅排序(order_after)、前置依赖(requires)、互斥(conflicts)。
工序关系只能引用 allowed_processes 中的 process_id；current_process 通常是目标工序。
非工序关系再转换为严格的 when/then 规则 AST：并且用 all，或者用 any，否定用 not。
candidate.evidence 必须原样截取 source_text 中支持判断的关键片段，禁止改写或补充原文不存在的内容。
标准字段已经能表达的检验、标印、表面处理等特殊要求继续使用 special.requirements，value 使用简明、可复用的要求名称，例如“追溯标印”“镀铜要求”。如果原文明确提出了一个标准字段无法表达、后续可由用户回答的新属性，例如“是否为试制件”“是否需要客户见证”，则创建 project_factor.* 的 boolean 动态因素；不要新增 custom.requirements 字段。
遇到字段库未预列、但原文已经给出明确取值的结构特征或工艺要求时，仍使用受控字段：未知结构特征使用 cad.features contains 原文中的简明特征标签；未知工艺要求使用 special.requirements contains 原文中的简明要求标签。不要因为标签值不在 options 中而返回 unresolved。
IT 等级数字越小代表精度越高；“达到 IT8/IT8及以上精度”通常转换为数值 <= 8。
公差、粗糙度等“达到某值/不大于某值”转换为 <=。
如果条件无法可靠映射，返回 unresolved，并且不要猜测。
参数条件输出格式：
{"candidate":{"kind":"condition","when":{"field":"...","op":"...","value":1},"then":{"include_process_ids":["..."],"exclude_process_ids":[],"reason":"..."},"field_definitions":[],"preview":"...","evidence":"原文关键片段"},"confidence":0.0,"warnings":[],"unresolved":[]}
动态类别示例：用户写“材料类别为不锈钢”，可输出 field=project_factor.material_category、op=eq、value=不锈钢，并定义 label=材料类别、category=材料、type=single_select、operators=[eq,neq,in]、options=[{value:不锈钢,label:不锈钢}]、allow_custom=true、source=用户条件。
工序关系输出格式：
{"candidate":{"kind":"process_relation","relation":{"relation_type":"trigger_after","source_process_ids":["process_a"],"target_process_ids":["process_b"]},"preview":"工序A进入路线 → 纳入工序B，并排在工序A之后","evidence":"原文关键片段"},"confidence":0.0,"warnings":[],"unresolved":[]}
例如“前面有镀铜时，安排此工序”，如果当前工序为除铜，应输出 trigger_after，source_process_ids 使用镀铜的 process_id，target_process_ids 使用当前工序 ID。
“过程检验点”“质量确认点”是在描述检查时机，不等同于路线中名为“检验”的工序；只有明确写出“检验工序”或“检验进入路线”时才能把它作为来源工序。
当 unresolved 非空时 candidate 可以为 null。"""
    user_prompt = json.dumps(
        {
            "registry_version": FIELD_REGISTRY_VERSION,
            "source_text": source_text,
            "current_process": {"process_id": current_process_id, "display_name": current_process_name},
            "allowed_fields": fields_payload,
            "allowed_processes": [item.model_dump(mode="json") for item in processes],
        },
        ensure_ascii=False,
    )
    raw = await call_llm(
        system_prompt,
        user_prompt,
        temperature=0.0,
        config=llm_config,
        timeout_seconds=_condition_llm_timeout_seconds(),
        max_retries=_condition_llm_max_retries(),
    )
    if not raw:
        return None, None, []
    payload = parse_json_from_llm(raw)
    if not isinstance(payload, dict):
        return None, None, ["AI 返回内容不是有效 JSON，已尝试使用本地解析器。"]
    unresolved = [str(item) for item in payload.get("unresolved", []) if str(item).strip()]
    warnings = [str(item) for item in payload.get("warnings", []) if str(item).strip()]
    if unresolved:
        return None, float(payload.get("confidence") or 0), [*warnings, *unresolved]
    candidate = _candidate_from_payload(payload)
    if not candidate:
        return None, None, [*warnings, "AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.8
    return candidate, max(0.0, min(1.0, confidence)), warnings


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
    local_relation_candidate = _parse_process_relation(
        source_text,
        current_process_id,
        processes,
    )
    local_condition_candidate = _parse_locally(
        source_text,
        current_process_id,
        current_process_name,
        processes,
    )
    local_relation_candidate = _with_source_evidence(local_relation_candidate, source_text)
    local_condition_candidate = _with_source_evidence(local_condition_candidate, source_text)
    deterministic_condition = _parse_condition_tree(source_text)

    # A relation that names a route process and gives an explicit ordering or
    # trigger is deterministic.  Return it immediately: it avoids letting an
    # unavailable or over-general LLM turn a clear dependency into a vague
    # parameter condition.  It still remains only a *candidate* and must be
    # confirmed by the user before it can enter the exported rule package.
    if local_relation_candidate:
        relation_issues = validate_candidate(local_relation_candidate, processes)
        if not relation_issues:
            logger.info("rule_condition_parse_source source=local_relation")
            bound_candidate, binding_issues = _bind_candidate_factors(local_relation_candidate)
            return bound_candidate, 0.9, binding_issues

    if local_condition_candidate and (
        local_condition_candidate.field_definitions
        or deterministic_condition is not None
    ):
        local_issues = validate_candidate(local_condition_candidate, processes)
        if not local_issues:
            logger.info("rule_condition_parse_source source=local_condition")
            bound_candidate, binding_issues = _bind_candidate_factors(local_condition_candidate)
            return bound_candidate, 0.9, binding_issues

    try:
        candidate, confidence, issues = await _parse_with_llm(
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
        candidate = _with_source_evidence(candidate, source_text)
        assert candidate is not None
        validation_issues = validate_candidate(candidate, processes)
        if _has_unregistered_project_factor(candidate):
            validation_issues.append("未注册的类别条件不能创建项目因素，请选择标准因子或使用人工 Bool 条件。")
        expected_special_requirement = (
            None if local_relation_candidate else _known_special_requirement(source_text, current_process_name)
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
            bound_candidate, binding_issues = _bind_candidate_factors(candidate)
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
            bound_candidate, binding_issues = _bind_candidate_factors(local_relation_candidate)
            return bound_candidate, 0.9, [*issues, *binding_issues, *([fallback_note] if fallback_note else [])]
        issues.extend(relation_issues)

    local_candidate = local_condition_candidate
    if local_candidate:
        local_issues = validate_candidate(local_candidate, processes)
        if not local_issues:
            fallback_note = "已使用内置规则解析器生成候选结果，请重点核对。" if issues else ""
            logger.info("rule_condition_parse_source source=local_condition_fallback")
            bound_candidate, binding_issues = _bind_candidate_factors(local_candidate)
            return bound_candidate, 0.65, [*issues, *binding_issues, *([fallback_note] if fallback_note else [])]
        issues.extend(local_issues)

    partial_candidate, partial_issues = _partial_condition_candidate(
        source_text,
        current_process_id,
        processes,
    )
    if partial_candidate:
        partial_validation_issues = validate_candidate(partial_candidate, processes)
        if not partial_validation_issues:
            logger.info("rule_condition_parse_source source=partial_local_fallback")
            bound_candidate, binding_issues = _bind_candidate_factors(partial_candidate)
            return bound_candidate, 0.55, list(dict.fromkeys([
                *issues,
                *partial_issues,
                *binding_issues,
            ]))
        issues.extend(partial_validation_issues)

    logger.info("rule_condition_parse_source source=unresolved")
    return None, confidence, list(dict.fromkeys([*issues, "条件无法可靠映射到标准字段，请补充字段、比较关系和阈值。"]))
