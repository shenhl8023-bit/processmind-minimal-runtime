"""LLM boundary for natural-language rule-condition parsing."""

from __future__ import annotations

import json
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
from app.services.rule_packages.condition_semantics import candidate_from_payload
from app.services.rule_packages.standard_factors import standard_factors


def condition_llm_timeout_seconds() -> float:
    try:
        value = float(os.getenv("RULE_CONDITION_LLM_TIMEOUT_SECONDS", "45"))
    except (TypeError, ValueError):
        value = 45.0
    return max(5.0, min(value, 300.0))


def condition_llm_max_retries() -> int:
    try:
        value = int(os.getenv("RULE_CONDITION_LLM_MAX_RETRIES", "1"))
    except (TypeError, ValueError):
        value = 1
    return max(0, min(value, 3))


async def parse_with_llm(
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
每个条件叶子必须绑定 allowed_standard_factors 中的 factor_id；presence 类因子的 value 必须使用该因子的 canonical_value，禁止把“孔类结构”“孔加工要求”“孔结构”等伞形短语原样当作条件值。
原文是伞形孔类表述时，按 current_process 选择最接近的孔类标准因子：钻孔/打孔→普通孔/辅助孔，钻铰孔/铰孔→铰孔/精孔，研顶尖孔→顶尖孔，珩孔→珩孔要求，割型孔/型孔→型孔/割扁；“孔加工要求”对应孔精加工、珩孔要求或研孔要求中与当前工序一致的一项。
原文是“防护、防腐蚀、绝缘或表面稳定性要求”，且当前工序是硬质阳极化或铬酸阳极化时，分别绑定硬质阳极化要求或铬酸阳极化要求。不要根据工序名凭空编造原文没有的条件。
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
{"candidate":{"kind":"condition","when":{"field":"...","op":"...","value":1,"factor_id":"..."},"then":{"include_process_ids":["..."],"exclude_process_ids":[],"reason":"..."},"field_definitions":[],"preview":"...","evidence":"原文关键片段"},"confidence":0.0,"warnings":[],"unresolved":[]}
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
            "current_process": {
                "process_id": current_process_id,
                "display_name": current_process_name,
            },
            "allowed_fields": fields_payload,
            "allowed_standard_factors": [
                {
                    "factor_id": item.factor_id,
                    "label": item.label,
                    "category": item.category,
                    "source_field": item.source_field,
                    "canonical_value": item.canonical_value,
                    "allowed_operators": item.allowed_operators,
                }
                for item in standard_factors()
            ],
            "allowed_processes": [item.model_dump(mode="json") for item in processes],
        },
        ensure_ascii=False,
    )
    raw = await call_llm(
        system_prompt,
        user_prompt,
        temperature=0.0,
        config=llm_config,
        timeout_seconds=condition_llm_timeout_seconds(),
        max_retries=condition_llm_max_retries(),
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
    candidate = candidate_from_payload(payload)
    if not candidate:
        return None, None, [*warnings, "AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    try:
        confidence = float(payload.get("confidence"))
    except (TypeError, ValueError):
        confidence = 0.8
    return candidate, max(0.0, min(1.0, confidence)), warnings
