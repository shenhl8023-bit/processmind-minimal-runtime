"""Natural-language parser for user-authored process conditions."""

from __future__ import annotations

import json
import logging
import math
import os
import re
from typing import Any

from pydantic import ValidationError

from app.services.llm_service import call_llm, parse_json_from_llm
from app.services.rule_packages.authoring_validation import validate_authored_candidate
from app.services.rule_packages.condition_contracts import (
    CanonicalConditionField,
    ProcessRelationCandidate,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_registry import (
    FIELD_REGISTRY_VERSION,
    condition_field_map,
    condition_fields,
    condition_preview,
    validate_condition_tree,
)
from app.services.rule_packages.contracts import ConditionNode, RuleAction
from app.services.rule_packages.expression_engine import iter_condition_fields

# Bump this whenever deterministic parsing changes.  Persisted reviews include
# the parser version, so a new rule vocabulary must invalidate stale/invalid
# candidates instead of reusing the old result after a page reload.
CONDITION_PARSER_VERSION = "2026.11.05.1"
logger = logging.getLogger(__name__)


# These are the recurring, low-information phrases produced by the third-step
# factor summary.  They describe that a branch is optional, but do not identify
# a field or value by themselves.  We may ignore one of these clauses only when
# another clause contains an explicit, controlled condition; a sentence made
# entirely of vague wording must remain unresolved.
_VAGUE_TEMPLATE_CLAUSE_PATTERNS = (
    re.compile(r"只有部分结构或工艺要求(?:下)?才会出现"),
    re.compile(r"不同结构类型(?:下)?工艺安排存在差异"),
    re.compile(r"工艺安排存在差异"),
    # Factor summaries sometimes describe a high-level quality trigger without
    # providing a measurable threshold.  Keep the explicit feature clauses in
    # the sentence, but do not turn this non-actionable wording into a field.
    re.compile(r"(?:尺寸)?公差要求较高|精度要求较高"),
)


def _is_vague_template_clause(text: str) -> bool:
    normalized = re.sub(r"^(?:当|如果|若)\s*|[时则情况下，,。；;\s]+$", "", str(text or "").strip())
    return bool(normalized) and any(pattern.fullmatch(normalized) for pattern in _VAGUE_TEMPLATE_CLAUSE_PATTERNS)


def _has_vague_template_qualifier(text: str) -> bool:
    source = str(text or "")
    return any(pattern.search(source) for pattern in _VAGUE_TEMPLATE_CLAUSE_PATTERNS)


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


def _normalized_process_name(value: str) -> str:
    return re.sub(r"[\s“”\"'、，,。；;（）()]", "", str(value or "")).casefold()


def _source_evidence(source_text: str) -> str:
    text = str(source_text or "").strip()
    match = re.search(r"(?:当|如果|若)\s*(.+?)(?:时|则|情况下)[，,。；;\s]*", text)
    return (match.group(1).strip() if match else text)[:160]


def _with_source_evidence(
    candidate: RuleConditionCandidate | None,
    source_text: str,
) -> RuleConditionCandidate | None:
    if not candidate:
        return candidate
    evidence = str(candidate.evidence or "").strip()
    if evidence and evidence in str(source_text or ""):
        return candidate
    return candidate.model_copy(update={"evidence": _source_evidence(source_text)})


def _resolve_process_ids(text: str, current_process_id: str, processes: list[RuleConditionProcessOption]) -> list[str]:
    # A condition card controls its own process. Other process names in the
    # condition clause are inputs or should be expressed as a process relation.
    return [current_process_id]


def validate_candidate(
    candidate: RuleConditionCandidate,
    processes: list[RuleConditionProcessOption],
    *,
    current_process_id: str | None = None,
) -> list[str]:
    allowed_ids = {item.process_id for item in processes}
    if candidate.kind == "process_configuration":
        config = candidate.configuration
        if config is None:
            return ["工序规则缺少配置。"]
        issues = []
        if config.process_id not in allowed_ids or (current_process_id and config.process_id != current_process_id):
            issues.append("规则配置只能控制当前工序。")
        if config.when is not None:
            nested = RuleConditionCandidate(when=config.when, then={"include_process_ids": [config.process_id]}, field_definitions=candidate.field_definitions)
            issues.extend(validate_candidate(nested, processes, current_process_id=config.process_id))
        elif candidate.field_definitions:
            issues.append("没有条件时不能保留未引用的动态因素。")
        if config.occurrence == "manual":
            # Use the same stable switch identity as the manual editor.
            value = 0x811C9DC5
            for char in config.process_id:
                value = ((value ^ ord(char)) * 0x01000193) & 0xFFFFFFFF
            key = f"project_factor.manual_process_{value:08x}"
            fields = candidate.field_definitions
            if not (config.when and config.when.field == key and config.when.op == "eq" and config.when.value is True
                    and len(fields) == 1 and fields[0].key == key and fields[0].type == "boolean"
                    and fields[0].source == "用户直接设定" and fields[0].allow_custom is False):
                issues.append("人工选择必须使用当前工序固定的 Bool 开关字段。")
        for relation in config.relations:
            nested = RuleConditionCandidate(kind="process_relation", relation=relation.model_dump())
            issues.extend(validate_candidate(nested, processes))
            if config.process_id not in relation.target_process_ids:
                issues.append("关联关系必须以当前工序为目标。")
            if relation.target_process_ids != [config.process_id]:
                issues.append("关联关系只能控制当前工序。")
        return list(dict.fromkeys(issues))
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
            if not definition.key.startswith("project_factor."):
                issues.append(f"动态因素必须使用 project_factor 命名空间：{definition.key}")
                continue
            if not re.fullmatch(r"project_factor\.[a-z0-9_.-]+", definition.key):
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
        if current_process_id and set(referenced_ids) != {current_process_id}:
            issues.append("条件规则只能控制当前工序；跨工序依赖请改为关联工序规则。")
    for process_id in referenced_ids:
        if process_id not in allowed_ids:
            issues.append(f"规则引用了当前路线中不存在的工序：{process_id}")
    return list(dict.fromkeys(issues))


def _candidate_from_payload(payload: Any) -> RuleConditionCandidate | None:
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
当前只允许四种互斥出现方式：固定出现、人工Bool选择、全部条件满足、跟随一个来源工序。
关联只允许单来源触发并排序(trigger_after)，目标只能是 current_process，不得附加字段条件。
仅排序、前置依赖、互斥、多来源、混合字段条件和关联的原文必须返回 unresolved，不得改写或丢弃其中一部分。
参数条件转换为严格的 when/then AST：并且用 all；只允许纳入 current_process，不允许排除或控制其他工序。
不允许 any/not 分组。跨字段的“或”和整体否定必须返回 unresolved，禁止改成 all 或只保留一个分支。
单一字段的值列表可以使用非空的 in/contains_any/contains_all；每个条件必须有完整且非空的字段、关系、值。保留原文全部条件。
candidate.evidence 必须原样截取 source_text 中支持判断的关键片段，禁止改写或补充原文不存在的内容。
标准字段已经能表达的检验、标印、表面处理等特殊要求继续使用 special.requirements，value 使用简明、可复用的要求名称，例如“追溯标印”“镀铜要求”。如果原文明确提出了一个标准字段无法表达、后续可由用户回答的新属性，例如“是否为试制件”“是否需要客户见证”，则创建 project_factor.* 的 boolean 动态因素；不要新增 custom.requirements 字段。
遇到字段库未预列、但原文已经给出明确取值的结构特征或工艺要求时，仍使用受控字段：未知结构特征使用 cad.features contains 原文中的简明特征标签；未知工艺要求使用 special.requirements contains 原文中的简明要求标签。不要因为标签值不在 options 中而返回 unresolved。
IT 等级数字越小代表精度越高；“达到 IT8/IT8及以上精度”通常转换为数值 <= 8。
公差、粗糙度等“达到某值/不大于某值”转换为 <=。
硬度“达到 HRC58”转换为 >= 58；禁止将其他硬度量表直接当成 HRC。
完整闭区间使用 between 并保留两端；不完整、倒置或边界不明确的区间返回 unresolved。
公差字段单位为 mm，粗糙度字段单位为 μm；只支持明确的毫米与微米换算，其他显式单位必须返回 unresolved，不能丢弃单位。
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
    try:
        raw = await call_llm(
            system_prompt,
            user_prompt,
            temperature=0.0,
            config=llm_config,
            timeout_seconds=_condition_llm_timeout_seconds(),
            max_retries=_condition_llm_max_retries(),
        )
    except Exception as exc:
        logger.warning("rule_condition_llm_failed error=%s", exc)
        return None, None, ["AI 解析服务暂时不可用，已改用本地解析器，请重点核对。"]
    if not raw:
        return None, None, []
    payload = parse_json_from_llm(raw)
    if not isinstance(payload, dict):
        return None, None, ["AI 返回内容不是有效 JSON，已尝试使用本地解析器。"]
    raw_unresolved = payload.get("unresolved", [])
    raw_warnings = payload.get("warnings", [])
    if raw_unresolved is not None and not isinstance(raw_unresolved, list):
        return None, None, ["AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    if raw_warnings is not None and not isinstance(raw_warnings, list):
        return None, None, ["AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    unresolved = [str(item) for item in (raw_unresolved or []) if str(item).strip()]
    warnings = [str(item) for item in (raw_warnings or []) if str(item).strip()]
    raw_confidence = payload.get("confidence")
    try:
        confidence = float(raw_confidence) if raw_confidence is not None else (0.0 if unresolved else 0.8)
        if isinstance(raw_confidence, bool) or not math.isfinite(confidence):
            raise ValueError("confidence must be a finite number")
    except (TypeError, ValueError, OverflowError):
        return None, None, [*warnings, "AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    confidence = max(0.0, min(1.0, confidence))
    if unresolved:
        return None, confidence, [*warnings, *unresolved]
    candidate = _candidate_from_payload(payload)
    if not candidate:
        return None, None, [*warnings, "AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。"]
    return candidate, confidence, warnings


def _comparison_operator(text: str, *, it_grade: bool = False, higher_is_better: bool = False) -> str:
    # Match the complete inclusive/negative phrase before its positive substring.
    if re.search(r"不低于|不小于|不少于|至少|大于等于|>=|≥", text):
        return "lte" if it_grade else "gte"
    if re.search(r"不高于", text):
        return "gte" if it_grade else "lte"
    if re.search(r"不大于|不超过|不多于|至多|小于等于|<=|≤|及以上精度", text):
        return "lte"
    if re.search(r"达到", text):
        return "gte" if higher_is_better else "lte"
    if re.search(r"优于", text):
        return "lt" if it_grade else "lte"
    if re.search(r"高于|大于|超过|>", text):
        return "lt" if it_grade else "gt"
    if re.search(r"低于|小于|少于|<", text):
        return "gt" if it_grade else "lt"
    return "lte" if it_grade else "eq"


_NUMERIC_VALUE = r"[+-]?(?:\d+(?:\.\d+)?|\.\d+)"
_NUMERIC_UNIT = r"[A-Za-zμµ\u4e00-\u9fff°/%²³]*"
_NUMERIC_RANGE_SEPARATOR = r"(?:到|至|[~～〜–—-])"
_TOLERANCE_FIELDS = {
    "圆柱度": "tolerance.cylindricity_mm",
    "同轴度": "tolerance.coaxiality_mm",
    "同心度": "tolerance.coaxiality_mm",
    "圆跳动": "tolerance.runout_mm",
    "全跳动": "tolerance.runout_mm",
    "位置度": "tolerance.position_mm",
    "平面度": "tolerance.flatness_mm",
    "垂直度": "tolerance.perpendicularity_mm",
    "圆度": "tolerance.roundness_mm",
}


def _numeric_condition_from_clause(text: str) -> tuple[ConditionNode | None, list[str]]:
    """Parse complete numeric quantities, or explain why they need clarification."""
    marker = re.search(r"IT\s*(?=\d)", text, re.IGNORECASE)
    scale = "it"
    if marker:
        field = ("precision.outer_diameter_it" if re.search(r"外圆|外径", text) else
                 "precision.inner_diameter_it" if re.search(r"内孔|内径|孔", text) else
                 "precision.dimension_it")
    else:
        marker = re.search(r"粗糙度|R[azqt](?=\s*" + _NUMERIC_VALUE + r")", text, re.IGNORECASE)
        field, scale = "surface.roughness_ra", "ra"
    if marker is None:
        for label, tolerance_field in _TOLERANCE_FIELDS.items():
            marker = re.search(label, text)
            if marker:
                field, scale = tolerance_field, ""
                break
    if marker is None:
        marker = re.search(r"硬度|(?:HR[A-Z]|HBW?|HV|HS)(?=\s*" + _NUMERIC_VALUE + r")", text, re.IGNORECASE)
        field, scale = "mechanical.hardness_hrc", "hrc"
    if marker is None:
        return None, []

    expression = text[marker.end():]
    first_number = re.search(_NUMERIC_VALUE, expression)
    if first_number is None:
        return None, []
    boundary_issue = ["数值区间或比较关系不完整，无法保留全部边界；请明确上下限及其是否包含等号。"]
    prefix = expression[:first_number.start()]
    if (re.search(r"不在|不介于|未达到|不到|不等于|!=|≠", text)
            or re.search(_NUMERIC_RANGE_SEPARATOR, re.sub(r"达到|至少|至多", "", prefix))):
        return None, boundary_issue
    # Prefix scales (HB200) matter just as much as suffix units (200HV).
    prefix_units = re.findall(r"[A-Za-zμµ]+|[\u4e00-\u9fff]*氏", text[:marker.end()] + prefix)
    unit_issue = ["数值条件含不支持或不明确的单位/硬度量表，请明确使用字段单位后重试。"]
    if any(unit.casefold() != scale for unit in prefix_units):
        return None, unit_issue
    # Only comparison vocabulary and the field's own scale may precede the
    # quantity. Otherwise a prefix unit such as “英寸10” would disappear.
    numeric_prefix = re.sub(r"HRC|Ra|IT", "", prefix, flags=re.IGNORECASE)
    if not re.fullmatch(
        r"(?:不低于|不小于|不少于|不高于|不大于|不超过|不多于|大于等于|小于等于"
        r"|达到|优于|高于|低于|大于|小于|超过|少于|至少|至多|等于|介于"
        r"|公差|要求|数值|目标|必须|应|需|为|是|在|[<>=≤≥:：\s])*", numeric_prefix,
    ):
        return None, unit_issue

    body = expression[first_number.start():].strip()
    body = re.sub(r"(?:之间|范围内|范围|及以上精度|以上精度)$", "", body).strip()
    interval = re.fullmatch(
        rf"(?P<low>{_NUMERIC_VALUE})\s*(?P<low_unit>{_NUMERIC_UNIT}?)\s*"
        rf"{_NUMERIC_RANGE_SEPARATOR}\s*(?P<high_scale>[A-Za-z]+)?\s*"
        rf"(?P<high>{_NUMERIC_VALUE})\s*(?P<high_unit>{_NUMERIC_UNIT})", body,
    )
    if interval:
        if re.search(r"大于|小于|高于|低于|超过|至少|至多|不少于|不多于|优于|达到|[<>≤≥]", text[:marker.end()] + prefix):
            return None, boundary_issue
        if interval.group("high_scale") and interval.group("high_scale").casefold() != scale:
            return None, unit_issue
        quantities = [float(interval.group("low")), float(interval.group("high"))]
        low_unit, high_unit = interval.group("low_unit"), interval.group("high_unit")
        # A single written unit applies to both bounds; explicit mixed units
        # are converted separately before checking their numeric order.
        units = [low_unit or high_unit, high_unit or low_unit]
    else:
        single = re.fullmatch(rf"(?P<value>{_NUMERIC_VALUE})\s*(?P<unit>{_NUMERIC_UNIT})", body)
        if single is None:
            return None, boundary_issue
        quantities, units = [float(single.group("value"))], [single.group("unit")]

    if field.startswith("tolerance."):
        factors = {"": 1.0, "mm": 1.0, "毫米": 1.0, "um": 0.001, "μm": 0.001, "µm": 0.001, "微米": 0.001}
    elif scale == "ra":
        factors = {"": 1.0, "mm": 1000.0, "毫米": 1000.0, "um": 1.0, "μm": 1.0, "µm": 1.0, "微米": 1.0}
    else:
        factors = {"": 1.0, scale: 1.0}
        if scale == "it":
            factors["级"] = 1.0
    if any(unit.casefold() not in factors for unit in units):
        return None, unit_issue
    values = [quantity * factors[unit.casefold()] for quantity, unit in zip(quantities, units)]
    if not all(math.isfinite(value) for value in values):
        return None, ["数值阈值必须是有限数字，请明确条件。"]
    if interval:
        if values[0] > values[1]:
            return None, ["数值区间下限不能大于上限，请核对数值与单位。"]
        return ConditionNode(field=field, op="between", value=values), []
    return ConditionNode(
        field=field, op=_comparison_operator(text, it_grade=scale == "it", higher_is_better=scale == "hrc"),
        value=values[0],
    ), []


def _leaf_from_clause(clause: str) -> ConditionNode | None:
    text = clause.strip()
    if re.fullmatch(r"(?:零件|工件|产品)?(?:存在|具有|具备|包含)?孔类(?:结构|特征)", text):
        # The question-tree answer names the broad hole category. Express it
        # using the existing reviewed CAD categories, without inventing a
        # separate machining requirement or an unconstrained tag value.
        return ConditionNode(field="cad.features", op="contains_any", value=[
            "普通孔/辅助孔", "铰孔/精孔", "型孔/割扁", "顶尖孔",
        ])
    if text in {"键", "键结构"}:
        return ConditionNode(field="cad.features", op="contains", value="槽类特征")
    alternatives = [part.strip() for part in re.split(r"或者|或是|或|、", text) if part.strip()]
    if len(alternatives) > 1:
        children = [_leaf_from_clause(part) for part in alternatives]
        if all(child is not None and child.op == "contains" for child in children):
            if len({child.field for child in children}) == 1:
                values = list(dict.fromkeys(child.value for child in children))
                return ConditionNode(field=children[0].field, op="contains_any" if len(values) > 1 else "contains", value=values if len(values) > 1 else values[0])
    numeric_condition, numeric_issues = _numeric_condition_from_clause(text)
    if numeric_condition is not None or numeric_issues:
        return numeric_condition

    material_values = re.findall(
        r"(?:材料(?:牌号)?|材质|牌号)[为是：:\s]*"
        r"([A-Za-z0-9\-]+(?:\s*(?:或者|或是|或|、)\s*[A-Za-z0-9\-]+)*)", text,
    )
    if material_values:
        values = list(dict.fromkeys(value.strip() for group in material_values for value in re.split(r"或者|或是|或|、", group)))
        return ConditionNode(field="material.grade", op="in" if len(values) > 1 else "eq", value=values if len(values) > 1 else values[0])

    feature_aliases = (
        ("中心孔", "顶尖孔"),
        ("定位孔", "顶尖孔"),
        ("顶尖孔", "顶尖孔"),
        ("顶针孔", "顶尖孔"),
        ("钻铰孔", "铰孔/精孔"),
        ("铰孔", "铰孔/精孔"),
        ("精孔", "铰孔/精孔"),
        ("精密孔", "铰孔/精孔"),
        ("割型孔", "型孔/割扁"),
        ("打型孔", "型孔/割扁"),
        ("异形孔", "型孔/割扁"),
        ("异型孔", "型孔/割扁"),
        ("仿形孔", "型孔/割扁"),
        ("型孔", "型孔/割扁"),
        ("辅助孔", "普通孔/辅助孔"),
        ("普通孔", "普通孔/辅助孔"),
        ("一般孔", "普通孔/辅助孔"),
        ("通孔", "普通孔/辅助孔"),
        ("盲孔", "普通孔/辅助孔"),
        ("内孔", "普通孔/辅助孔"),
        ("割扁", "扁位/平面"),
        ("铣扁", "扁位/平面"),
        ("扁位", "扁位/平面"),
        ("扁", "扁位/平面"),
        ("平面", "扁位/平面"),
        ("花键", "槽类特征"),
        ("键槽", "槽类特征"),
        ("退刀槽", "槽类特征"),
        ("环槽", "槽类特征"),
        ("切槽", "槽类特征"),
        ("越程槽", "槽类特征"),
        ("槽", "槽类特征"),
    )
    matched_values: list[str] = []
    for alias, value in feature_aliases:
        if alias not in text:
            continue
        leaf = ConditionNode(field="cad.features", op="contains", value=value)
        if re.search(rf"(?:无|不含|没有|不具备|不存在|未包含)\s*{re.escape(alias)}", text):
            return ConditionNode(not_condition=leaf)
        matched_values.append(value)
    matched_values = list(dict.fromkeys(matched_values))
    if len(matched_values) == 1:
        return ConditionNode(field="cad.features", op="contains", value=matched_values[0])
    if matched_values:
        return ConditionNode(field="cad.features", op="contains_any", value=matched_values)

    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return ConditionNode(field="special.requirements", op="contains", value="无损检测要求")

    special_values = ["渗氮层要求", "铬酸阳极化要求", "硬质阳极化要求", "追溯标印", "磁粉检查要求", "烧伤检查要求"]
    for value in special_values:
        if value in text or value.replace("要求", "") in text:
            return ConditionNode(field="special.requirements", op="contains", value=value)
    return None


_DYNAMIC_FACTOR_KEY_ALIASES = {
    "材料类别": "material_category",
    "材质类别": "material_category",
    "材料类型": "material_type",
    "零件类型": "part_type",
    "产品类型": "product_type",
    "工件类型": "workpiece_type",
    "结构类型": "structure_type",
    "热处理状态": "heat_treatment_state",
    "表面处理类型": "surface_treatment_type",
    "生产批次": "production_batch",
    "试制状态": "prototype_status",
    "客户见证": "customer_witness",
}


def _project_factor_key(label: str) -> str:
    normalized = re.sub(r"\s+", "", str(label or "").strip()).casefold()
    alias = _DYNAMIC_FACTOR_KEY_ALIASES.get(normalized)
    if alias:
        return f"project_factor.{alias}"

    ascii_slug = re.sub(r"[^a-z0-9]+", "_", normalized).strip("_")
    if ascii_slug:
        return f"project_factor.{ascii_slug}"

    # Keep unfamiliar Chinese labels deterministic and reversible instead of opaque hashes.
    codepoint_slug = "_".join(f"u{ord(character):x}" for character in normalized)
    return f"project_factor.{codepoint_slug or 'user_factor'}"


def _dynamic_categorical_condition(
    source_text: str,
) -> tuple[ConditionNode, CanonicalConditionField] | None:
    text = str(source_text or "").strip()
    if not text or not re.search(r"纳入|加入|安排|设置|增加|出现|进行|执行|实施|排除|不纳入|取消", text):
        return None
    if re.search(r"前面|此前|之前|之后|完成后|依赖|前置|互斥|不能同时|不得同时", text):
        return None
    match = re.search(
        r"(?:当|如果|若)?\s*(?:零件|产品|工件)?\s*"
        r"(?P<label>[\u4e00-\u9fffA-Za-z][\u4e00-\u9fffA-Za-z0-9_／/\-]{1,23}?)\s*"
        r"(?:为|是|等于|属于)\s*[“\"']?"
        r"(?P<value>[^，,。；;\s时则]{1,30})[”\"']?\s*"
        r"(?:时|则|情况下|，|,|。|；|;)",
        text,
    )
    if not match:
        return None
    label = match.group("label").strip()
    raw_value = match.group("value").strip(" “'\"”")
    values = [re.sub(rf"^{re.escape(label)}(?:为|是|等于|属于)\s*", "", item.strip())
              for item in re.split(r"或者|或是|或|、", raw_value) if item.strip()]
    if not label or not values or label in {"该工序", "此工序", "当前工序"}:
        return None
    if label in {"零件", "产品", "工件"}:
        label = f"{label}类型"
    key = _project_factor_key(label)
    category = "材料" if re.search(r"材料|材质", label) else "用户因素"
    definition = CanonicalConditionField(
        key=key,
        label=label,
        category=category,
        type="single_select",
        operators=["eq", "neq", "in"],
        aliases=[],
        source="用户条件",
        options=[{"value": value, "label": value} for value in values],
        allow_custom=True,
    )
    return ConditionNode(
        field=key,
        op="in" if len(values) > 1 else "eq",
        value=values if len(values) > 1 else values[0],
    ), definition


def _known_special_requirement(text: str, current_process_name: str) -> str | None:
    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return "无损检测要求"
    if re.search(r"追溯|编号|批次.{0,6}标识|标识需求", text):
        return "追溯标印"
    if re.search(r"防护|防腐蚀|绝缘|表面稳定性|表面处理", text):
        name = str(current_process_name or "当前工序").strip()
        return name if name.endswith("要求") else f"{name}要求"
    return None


def _generic_tag_condition(source_text: str) -> ConditionNode | None:
    """Map a clear unseen feature/requirement onto a controlled tag field.

    Only the tag value is extensible. Vague phrases stay unresolved so a
    guessed value cannot silently change the generated route.
    """
    text = str(source_text or "").strip()
    action_pattern = r"纳入|加入|安排|设置|增加|出现|进行|执行|实施|排除|不纳入|取消"
    if not text or not re.search(action_pattern, text):
        return None
    if re.search(r"前面|此前|之前|之后|完成后|依赖|前置|互斥|不能同时|不得同时", text):
        return None
    if re.search(r"不同结构类型|部分结构|视情况|酌情|根据.{0,12}决定|要求较高|满足要求|条件满足", text):
        return None

    clause = ""
    for pattern in (
        rf"(?:当|如果|若)(.+?)(?:时|情况下|则)[，,。；;\s]*(?:需(?:要)?|应|就|才|可)?(?:{action_pattern})",
        rf"(?:当|如果|若)(.+?)[，,。；;](?:需(?:要)?|应|就|才|可)?(?:{action_pattern})",
    ):
        match = re.search(pattern, text)
        if match:
            clause = match.group(1).strip()
            break
    if not clause:
        return None

    negated = bool(re.search(r"(?:^|零件)(?:无|没有|不含|不存在|不具备)", clause))
    label = re.sub(r"^(?:零件|产品|工件|图样|技术条件)", "", clause).strip()
    label = re.sub(r"^(?:存在|具有|具备|包含|带有|需要|要求|满足)", "", label).strip()
    label = re.sub(r"^(?:无|没有|不含|不存在|不具备)", "", label).strip()
    label = re.sub(r"(?:是否)?(?:存在|具有|具备|包含|满足|需要)$", "", label).strip()
    label = re.sub(r"(?:的)?(?:情况下|条件)$", "", label).strip(" ，,。；;：:")
    if not label or len(label) > 36 or label in {"该工序", "此工序", "当前工序"}:
        return None

    feature_hint = re.search(
        r"结构|特征|形状|轮廓|孔|槽|台阶|凸台|凹坑|缺口|螺纹|花键|键槽|齿|扁位|平面|曲面|外圆|内腔",
        label,
    )
    requirement_hint = re.search(
        r"要求|需求|性能|精度|质量|检验|检查|探伤|标识|追溯|防护|防腐|绝缘|清洁|装配|配合|热处理|表面处理",
        label,
    ) or re.search(r"需要|要求|需求|规定|技术条件", clause)
    if feature_hint and not requirement_hint:
        field = "cad.features"
        value = re.sub(r"(?:结构|特征)$", "", label).strip() or label
    elif requirement_hint:
        field = "special.requirements"
        value = label if label.endswith(("要求", "需求")) else f"{label}要求"
    else:
        return None

    leaf = ConditionNode(field=field, op="contains", value=value)
    return ConditionNode(not_condition=leaf) if negated else leaf


def _special_requirement_for_boolean_field(field: CanonicalConditionField) -> str:
    text = " ".join([field.label, *field.aliases])
    if re.search(r"追溯|编号|批次.{0,6}标识", text):
        return "追溯标印"
    label = re.sub(r"^(?:是否需要|是否具备|是否)", "", field.label).strip()
    if not label:
        label = "特殊工艺要求"
    return label if label.endswith("要求") else f"{label}要求"


def _convert_boolean_fields_to_special_requirements(
    candidate: RuleConditionCandidate,
) -> RuleConditionCandidate:
    if candidate.kind != "condition" or candidate.when is None:
        return candidate
    dynamic_fields = {
        field.key: field
        for field in candidate.field_definitions
        if field.type == "boolean" and field.key.startswith("custom.requirements.")
    }
    if not dynamic_fields:
        return candidate

    def convert(node: ConditionNode) -> ConditionNode:
        if node.field:
            definition = dynamic_fields.get(node.field)
            if definition and node.op in {"eq", "neq"} and isinstance(node.value, bool):
                leaf = ConditionNode(
                    field="special.requirements",
                    op="contains",
                    value=_special_requirement_for_boolean_field(definition),
                )
                positive = node.value if node.op == "eq" else not node.value
                return leaf if positive else ConditionNode(not_condition=leaf)
            return node
        if node.all_conditions is not None:
            return ConditionNode(all_conditions=[convert(child) for child in node.all_conditions])
        if node.any_conditions is not None:
            return ConditionNode(any_conditions=[convert(child) for child in node.any_conditions])
        if node.not_condition is not None:
            return ConditionNode(not_condition=convert(node.not_condition))
        return node

    when = convert(candidate.when)
    if when == candidate.when:
        return candidate
    referenced_fields = set(iter_condition_fields(when))
    return candidate.model_copy(update={
        "when": when,
        "field_definitions": [field for field in candidate.field_definitions if field.key in referenced_fields],
    })


def _condition_text(source_text: str) -> str:
    """Remove the action before looking for fields or conjunctions in its gate."""
    text = re.split(r"不纳入|纳入|加入|(?<!工艺)安排|设置|增加|排除|取消", source_text, maxsplit=1)[0]
    text = re.split(
        r"(?:时|则|情况下)[，,。；;\s]*(?:需(?:要)?|应|就|才|可)?(?:出现|进行|执行|实施)",
        text, maxsplit=1,
    )[0]
    text = re.sub(r"^(?:当|如果|若)\s*", "", text.strip())
    return re.sub(r"(?:时|则|情况下)?[，,。；;\s]*$", "", text).strip()


def _condition_clauses(source_text: str) -> list[str]:
    return [part.strip() for part in re.split(
        r"并且|同时|而且|且|以及|和|与|及(?!以[上下])|[，,；;]", _condition_text(source_text),
    ) if part.strip()]


def _negated_requirement_issues(source_text: str) -> list[str]:
    # “无损” names an inspection requirement; its first character is not
    # negation. Check the surrounding predicate before either local or AI parsing.
    for clause in _condition_clauses(source_text):
        if not re.search(r"要求|需求|无损|磁粉|裂纹|荧光|探伤|追溯|标印", clause):
            continue
        if re.search(r"没有|不存在|不具备|不含|不需要|无需|无(?!损)|未提出|未要求", clause):
            return ["特殊要求的否定条件当前无法表达，请重新明确出现条件；不能改写为正向包含。"]
    return []


def _disjunction_issues(source_text: str) -> list[str]:
    for clause in _condition_clauses(source_text):
        if _is_vague_template_clause(clause) or not re.search(r"或者|或是|或", clause):
            continue
        fields = set()
        unmapped = []
        for part in re.split(r"或者|或是|或|、", clause):
            leaf = _leaf_from_clause(part)
            dynamic = _dynamic_categorical_condition(f"当{part}时，纳入此工序")
            if leaf is not None:
                fields.update(iter_condition_fields(leaf))
            elif dynamic:
                fields.add(dynamic[0].field)
            elif _known_special_requirement(part, "当前工序"):
                fields.add("special.requirements")
            else:
                unmapped.append(part.strip())
        inherited_field = next(iter(fields)) if len(fields) == 1 else None
        definition = condition_field_map().get(inherited_field)
        if definition and definition.type == "number":
            return ["数值比较之间的“或”需要任一满足分组，当前只支持全部满足；请明确条件。"]
        for part in unmapped:
            if inherited_field == "material.grade" and re.fullmatch(r"[A-Za-z0-9\-]+", part):
                continue
            if inherited_field and inherited_field.startswith("project_factor.") and not re.search(
                r"为|等于|属于|满足|存在|具有|具备|需要|要求|完成|硬度|精度|粗糙度|公差|材料|材质|客户见证", part,
            ):
                continue
            return ["含“或”的条件分支无法可靠映射到同一字段的值列表；请补充全部分支，不能只保留一项。"]
        if len(fields) > 1:
            return ["当前条件只支持全部满足；跨字段的“或”不能自动改写，请明确选择出现条件。"]
    return []


def _parse_condition_tree(source_text: str) -> ConditionNode | None:
    if _disjunction_issues(source_text):
        return None
    and_parts = _condition_clauses(source_text)
    if len(and_parts) > 1:
        parsed_parts = [(item, _leaf_from_clause(item)) for item in and_parts]
        unresolved_parts = [item for item, child in parsed_parts if child is None]
        children_by_shape = {
            child.model_dump_json(by_alias=True): child
            for _, child in parsed_parts
            if child is not None
        }
        children = list(children_by_shape.values())
        if children and all(_is_vague_template_clause(item) for item in unresolved_parts):
            return children[0] if len(children) == 1 else ConditionNode(all_conditions=children)
        return None
    return _leaf_from_clause(and_parts[0]) if and_parts else None


def _parse_locally(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
) -> RuleConditionCandidate | None:
    parsed_condition = _parse_condition_tree(source_text)
    clauses = [clause for clause in _condition_clauses(source_text) if not _is_vague_template_clause(clause)]
    # A failed conjunction is not permission to salvage a single matching field.
    if parsed_condition is None and len(clauses) != 1:
        return None
    special_requirement = _known_special_requirement(_condition_text(source_text), current_process_name)
    dynamic_condition = None if special_requirement else _dynamic_categorical_condition(source_text)
    when = parsed_condition or (
        ConditionNode(field="special.requirements", op="contains", value=special_requirement) if special_requirement else (
            (dynamic_condition[0] if dynamic_condition else None)
            or _generic_tag_condition(source_text)
        )
    )
    if not when:
        return None
    process_ids = [current_process_id] if special_requirement else _resolve_process_ids(
        source_text,
        current_process_id,
        processes,
    )
    # Match the action as a whole: “安排除铜” contains “排除” across its
    # verb/name boundary, but still means include the stripping process.
    action_match = re.search(r"不纳入|纳入|加入|(?<!工艺)安排|设置|增加|排除|取消", source_text)
    exclude = bool(action_match and action_match.group() in {"排除", "不纳入", "取消"})
    action = RuleAction(
        include_process_ids=[] if exclude else process_ids,
        exclude_process_ids=process_ids if exclude else [],
        reason=f"用户确认条件：{source_text}",
    )
    return RuleConditionCandidate(
        kind="condition",
        when=when,
        then=action,
        field_definitions=[dynamic_condition[1]] if dynamic_condition and when.field == dynamic_condition[0].field else [],
        preview=condition_preview(
            when,
            {dynamic_condition[1].key: dynamic_condition[1]} if dynamic_condition and when.field == dynamic_condition[0].field else None,
        ),
    )


def _relation_preview(
    relation: ProcessRelationCandidate,
    processes: list[RuleConditionProcessOption],
) -> str:
    names = {item.process_id: item.display_name for item in processes}
    sources = "、".join(dict.fromkeys(names.get(item, item) for item in relation.source_process_ids))
    targets = "、".join(dict.fromkeys(names.get(item, item) for item in relation.target_process_ids))
    if relation.relation_type == "trigger_after":
        return f"{sources}进入路线 → 纳入{targets}，并排在{sources}之后"
    if relation.relation_type == "order_after":
        return f"{targets}如进入路线 → 排在{sources}之后"
    if relation.relation_type == "requires":
        return f"{targets}进入路线 → 必须同时包含{sources}"
    return f"{targets}与{sources}不能同时进入路线"


def _resolve_relation_source_ids(
    source_text: str,
    current_process_id: str,
    processes: list[RuleConditionProcessOption],
) -> list[str]:
    """Resolve only existing route nodes referenced by a relation sentence.

    Most relations name an operation directly (for example, ``镀铜``).  A few
    common route-stage terms such as ``粗加工`` describe a stage rather than a
    normalized operation name.  For those terms, use the first preceding,
    route-resolvable coarse-machining operation as a conservative anchor.  We
    deliberately never manufacture an ID or infer a process after the target.
    """
    normalized_text = _normalized_process_name(source_text)
    def is_incidental_inspection_reference(item: RuleConditionProcessOption) -> bool:
        name = _normalized_process_name(item.display_name)
        return (
            name in {"检验", "检查"}
            and re.search(r"(?:过程|中间|质量)?(?:检验|检查)点|质量确认节点", source_text)
            and not re.search(rf"{re.escape(item.display_name)}(?:工序|进入路线|之后|后)", source_text)
        )

    direct_matches = [
        item.process_id
        for item in sorted(processes, key=lambda value: len(_normalized_process_name(value.display_name)), reverse=True)
        if _normalized_process_name(item.display_name)
        and _normalized_process_name(item.display_name) in normalized_text
        and item.process_id != current_process_id
        and not is_incidental_inspection_reference(item)
    ]
    if direct_matches:
        return list(dict.fromkeys(direct_matches))

    try:
        target_index = next(index for index, item in enumerate(processes) if item.process_id == current_process_id)
    except StopIteration:
        return []

    preceding_processes = processes[:target_index]
    if re.search(r"车削后|车后|周边加工后|机械加工后", source_text):
        machining_process_pattern = re.compile(r"车|铣|钻|镗|铰|拉削|刨|插削|磨|研|珩|割|打孔")
        return [
            item.process_id
            for item in preceding_processes
            if machining_process_pattern.search(item.display_name)
        ]

    if not re.search(r"粗加工|粗车|粗铣|粗磨|粗镗|粗钻", source_text):
        return []

    coarse_process_pattern = re.compile(r"粗|车削|车加工|铣削|铣[扁槽面]|镗|钻|铰|拉削|刨|插削")
    for item in preceding_processes:
        if coarse_process_pattern.search(item.display_name):
            return [item.process_id]
    return []


def _parse_process_relation(
    source_text: str,
    current_process_id: str,
    processes: list[RuleConditionProcessOption],
) -> RuleConditionCandidate | None:
    source_ids = _resolve_relation_source_ids(source_text, current_process_id, processes)
    if not source_ids:
        return None

    if re.search(r"不能同时|不得同时|互斥|二选一|不可共存", source_text):
        relation_type = "conflicts"
    elif re.search(r"(?:前|之前).{0,12}(?:必须|需要).{0,8}(?:完成|存在|经过)|依赖于|以前置", source_text):
        relation_type = "requires"
    elif re.search(r"必须在.{0,30}(?:后|之后)|应在.{0,30}(?:后|之后)|不得早于", source_text) and not re.search(r"安排|纳入|设置|增加|出现", source_text):
        relation_type = "order_after"
    elif re.search(
        r"(?:后|之后|完成后).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)"
        r"|(?:有|存在|出现).{1,30}工序(?:时|后|之后|的情况下).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)"
        r"|工序(?:存在|出现|有)时.{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)"
        r"|(?:前面|此前|之前).{0,20}(?:有|存在|出现).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)",
        source_text,
    ):
        relation_type = "trigger_after"
    else:
        return None

    relation = ProcessRelationCandidate(
        relation_type=relation_type,
        source_process_ids=source_ids,
        target_process_ids=[current_process_id],
        source_match="all" if len(source_ids) > 1 and re.search(r"并且|同时|以及|和", source_text) else "any",
    )
    return RuleConditionCandidate(
        kind="process_relation",
        relation=relation,
        preview=_relation_preview(relation, processes),
    )


def _has_field_gate(source_text: str, processes: list[RuleConditionProcessOption]) -> bool:
    gate = _condition_text(source_text)
    # Process names may themselves contain feature/inspection words. They are
    # relation references, not additional parameter predicates.
    for process in sorted(processes, key=lambda item: len(item.display_name), reverse=True):
        gate = gate.replace(process.display_name, "")
    # These action/purpose clauses follow the relation's gate rather than
    # adding predicates (for example “粗加工后释放应力，避免变形”).
    gate = re.split(
        r"(?<=后)(?:[，,\s]*(?:需(?:要)?|应|就|才|可))?(?:释放|进行|执行|实施|处理)"
        r"|(?:就|才)(?:出现|释放|进行|执行|实施|处理)", gate, maxsplit=1,
    )[0]
    for clause in _condition_clauses(gate):
        if _leaf_from_clause(clause) is not None:
            return True
        sentence = f"当{clause}时，纳入此工序"
        if _dynamic_categorical_condition(sentence) or _generic_tag_condition(sentence):
            return True
        # Recognizing a relation does not authorize discarding unknown gate
        # text. Only relation vocabulary may remain after process references.
        residual = re.sub(
            r"前面|此前|之前|之后|进入路线|工序|这个|这道|当前|该|此|存在|出现|已经|已|完成"
            r"|粗加工|粗车|粗铣|粗磨|粗镗|粗钻|车削|周边加工|机械加工|车后"
            r"|需要|需|应|就|才|可|有|后|时|的情况下", "", clause,
        )
        if residual.strip(" ，,。；;：:。“”\"'（）()"):
            return True
    return False


def _condition_leaves(node: ConditionNode) -> list[ConditionNode]:
    if node.all_conditions is not None:
        return [leaf for child in node.all_conditions for leaf in _condition_leaves(child)]
    return [node]


def _requires_leaf(node: ConditionNode, expected: ConditionNode) -> bool:
    """Check required semantics throughout ALL, including set-valued leaves."""
    for leaf in _condition_leaves(node):
        if leaf == expected:
            return True
        if leaf.field == expected.field and expected.op == "contains":
            if leaf.op == "contains_all" and expected.value in leaf.value:
                return True
            if leaf.op == "contains_any" and leaf.value == [expected.value]:
                return True
    return False


def _model_coverage_issues(
    candidate: RuleConditionCandidate, source_text: str, current_process_name: str,
) -> list[str]:
    clauses = [clause for clause in _condition_clauses(source_text) if not _is_vague_template_clause(clause)]
    when = candidate.configuration.when if candidate.configuration else candidate.when
    expected = []
    for clause in clauses:
        leaf = _leaf_from_clause(clause)
        if leaf is None:
            dynamic = _dynamic_categorical_condition(f"当{clause}时，纳入此工序")
            if dynamic:
                leaf = dynamic[0]
                # A model may choose a different key for the same authored label.
                definition = next((item for item in candidate.field_definitions if item.label == dynamic[1].label), None)
                if definition:
                    leaf = leaf.model_copy(update={"field": definition.key})
        if leaf is not None:
            expected.append(leaf)
    requirement = _known_special_requirement(_condition_text(source_text), current_process_name)
    if requirement:
        expected.append(ConditionNode(field="special.requirements", op="contains", value=requirement))
    if when is None:
        return ["模型候选丢失了原文的出现条件，请重新设置。"] if expected or len(clauses) > 1 else []
    missing = any(not _requires_leaf(when, leaf) for leaf in expected)
    # Unmapped clauses must not disappear just because a known clause matched.
    if missing or (len(clauses) > 1 and len(_condition_leaves(when)) < len(set(clauses))):
        return ["模型候选未保留原文全部条件，无法可靠映射；请补充完整条件后重试。"]
    return []


def _parse_manual_configuration(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
) -> RuleConditionCandidate | None:
    # This is the complete guided-manual summary, not a substring signal.
    # Recognize it before feature/category inference can mistake the process
    # name for a feature, or split “是否” into “是” + a categorical value.
    name = current_process_name.strip()
    if not name or source_text.strip().rstrip("。").strip() != f"{name}由用户每次决定是否安排":
        return None
    value = 0x811C9DC5
    for char in current_process_id:
        value = ((value ^ ord(char)) * 0x01000193) & 0xFFFFFFFF
    key = f"project_factor.manual_process_{value:08x}"
    return RuleConditionCandidate(
        kind="process_configuration",
        configuration={
            "process_id": current_process_id,
            "occurrence": "manual",
            "when": {"field": key, "op": "eq", "value": True},
            "relations": [],
        },
        field_definitions=[CanonicalConditionField(
            key=key, label=f"是否需要{name}", category="可选工序", type="boolean",
            operators=["eq", "neq"], required=False, source="用户直接设定",
            options=[], allow_custom=False,
        )],
        preview=source_text.strip(),
        evidence=source_text.strip(),
    )


async def parse_rule_condition(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
    *,
    llm_config: dict[str, str] | None = None,
) -> tuple[RuleConditionCandidate | None, float | None, list[str]]:
    manual_candidate = _parse_manual_configuration(source_text, current_process_id, current_process_name)
    if manual_candidate is not None:
        issues = [
            *validate_candidate(manual_candidate, processes, current_process_id=current_process_id),
            *validate_authored_candidate(manual_candidate, current_process_id),
        ]
        if issues:
            return None, None, list(dict.fromkeys(issues))
        logger.info("rule_condition_parse_source source=local_manual")
        return manual_candidate, 1.0, []
    source_issues = _negated_requirement_issues(source_text)
    if source_issues:
        return None, None, source_issues
    local_relation_candidate = _parse_process_relation(
        source_text,
        current_process_id,
        processes,
    )
    source_issues = _disjunction_issues(source_text)
    if source_issues and local_relation_candidate is None:
        return None, None, source_issues
    numeric_issues = [issue for clause in _condition_clauses(source_text)
                      for issue in _numeric_condition_from_clause(clause)[1]]
    if numeric_issues:
        return None, None, list(dict.fromkeys(numeric_issues))
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
        relation_issues = [
            *validate_candidate(local_relation_candidate, processes),
            *validate_authored_candidate(local_relation_candidate, current_process_id),
        ]
        if relation_issues:
            return None, None, list(dict.fromkeys(relation_issues))
        if _has_field_gate(source_text, processes):
            return None, None, ["字段条件与关联工序不能混合，请明确选择一种出现模式；原文条件未作改写。"]
        logger.info("rule_condition_parse_source source=local_relation")
        return local_relation_candidate, 0.9, []

    if local_condition_candidate and (
        local_condition_candidate.field_definitions
        or deterministic_condition is not None
    ):
        local_issues = validate_candidate(
            local_condition_candidate,
            processes,
            current_process_id=current_process_id,
        )
        local_issues.extend(validate_authored_candidate(local_condition_candidate, current_process_id))
        if not local_issues:
            logger.info("rule_condition_parse_source source=local_condition")
            issues = (
                ["已忽略原文中的泛化模板描述，请重点核对具体结构条件。"]
                if _has_vague_template_qualifier(source_text)
                else []
            )
            confidence = 0.75 if issues else 0.9
            return local_condition_candidate, confidence, issues
        return None, None, list(dict.fromkeys(local_issues))

    candidate, confidence, issues = await _parse_with_llm(
        source_text,
        current_process_id,
        current_process_name,
        processes,
        llm_config=llm_config,
    )
    if candidate:
        candidate = _with_source_evidence(candidate, source_text)
        assert candidate is not None
        candidate = _convert_boolean_fields_to_special_requirements(candidate)
        validation_issues = validate_candidate(
            candidate,
            processes,
            current_process_id=current_process_id,
        )
        validation_issues.extend(validate_authored_candidate(candidate, current_process_id))
        if candidate.kind == "process_relation" and _has_field_gate(source_text, processes):
            validation_issues.append("字段条件与关联工序不能混合，请明确选择一种出现模式。")
        if not validation_issues:
            validation_issues.extend(_model_coverage_issues(candidate, source_text, current_process_name))
        if not validation_issues:
            logger.info("rule_condition_parse_source source=llm")
            return candidate, confidence, issues
        issues.extend(validation_issues)

    local_candidate = local_condition_candidate
    if local_candidate:
        local_issues = validate_candidate(
            local_candidate,
            processes,
            current_process_id=current_process_id,
        )
        local_issues.extend(validate_authored_candidate(local_candidate, current_process_id))
        if not local_issues:
            fallback_note = "已使用内置规则解析器生成候选结果，请重点核对。" if issues else ""
            logger.info("rule_condition_parse_source source=local_condition_fallback")
            return local_candidate, 0.65, [*issues, *([fallback_note] if fallback_note else [])]
        issues.extend(local_issues)

    logger.info("rule_condition_parse_source source=unresolved")
    return None, confidence, list(dict.fromkeys([*issues, "条件无法可靠映射到标准字段，请补充字段、比较关系和阈值。"]))
