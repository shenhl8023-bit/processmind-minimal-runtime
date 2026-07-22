"""Natural-language parser for user-authored process conditions."""

from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.services.llm_service import call_llm, parse_json_from_llm
from app.services.rule_packages.condition_contracts import (
    ProcessRelationCandidate,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_registry import (
    FIELD_REGISTRY_VERSION,
    condition_fields,
    condition_preview,
    validate_condition_tree,
)
from app.services.rule_packages.contracts import ConditionNode, RuleAction
from app.services.rule_packages.expression_engine import iter_condition_fields


def _normalized_process_name(value: str) -> str:
    return re.sub(r"[\s“”\"'、，,。；;（）()]", "", str(value or "")).casefold()


def _is_nondestructive_inspection_process(value: str) -> bool:
    return bool(re.search(r"无损|磁粉|裂纹|荧光|探伤", str(value or "")))


def _resolve_process_ids(text: str, current_process_id: str, processes: list[RuleConditionProcessOption]) -> list[str]:
    normalized_text = _normalized_process_name(text)
    matched = [
        item.process_id
        for item in processes
        if _normalized_process_name(item.display_name) and _normalized_process_name(item.display_name) in normalized_text
    ]
    return list(dict.fromkeys(matched or [current_process_id]))


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
        if candidate.field_definitions:
            issues.append("规则不能再新增自定义字段，请重新解析并改用标准字段或“特殊要求”。")
        issues.extend(validate_condition_tree(candidate.when))
        referenced_ids = [*candidate.then.include_process_ids, *candidate.then.exclude_process_ids]
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
        candidate.preview = condition_preview(candidate.when)
    return candidate


async def _parse_with_llm(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
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
你只能使用输入给出的标准字段 key、运算符和工序 process_id，禁止创造字段或工序。
优先判断是否为工序关系：触发并排序(trigger_after)、仅排序(order_after)、前置依赖(requires)、互斥(conflicts)。
工序关系只能引用 allowed_processes 中的 process_id；current_process 通常是目标工序。
非工序关系再转换为严格的 when/then 规则 AST：并且用 all，或者用 any，否定用 not。
对于所有“是否需要/是否具备/某要求是否满足”这类二元需求，都使用 special.requirements 的 contains 条件；value 使用简明、可复用的要求名称，例如“追溯标印”“镀铜要求”。不要创建 boolean 字段，也不要新增 custom.requirements 字段。
IT 等级数字越小代表精度越高；“达到 IT8/IT8及以上精度”通常转换为数值 <= 8。
公差、粗糙度等“达到某值/不大于某值”转换为 <=。
如果条件无法可靠映射，返回 unresolved，并且不要猜测。
参数条件输出格式：
{"candidate":{"kind":"condition","when":{"field":"...","op":"...","value":1},"then":{"include_process_ids":["..."],"exclude_process_ids":[],"reason":"..."},"preview":"..."},"confidence":0.0,"warnings":[],"unresolved":[]}
工序关系输出格式：
{"candidate":{"kind":"process_relation","relation":{"relation_type":"trigger_after","source_process_ids":["process_a"],"target_process_ids":["process_b"]},"preview":"工序A进入路线 → 纳入工序B，并排在工序A之后"},"confidence":0.0,"warnings":[],"unresolved":[]}
例如“前面有镀铜时，安排此工序”，如果当前工序为除铜，应输出 trigger_after，source_process_ids 使用镀铜的 process_id，target_process_ids 使用当前工序 ID。
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
    raw = await call_llm(system_prompt, user_prompt, temperature=0.0)
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


def _comparison_operator(text: str, *, it_grade: bool = False) -> str:
    if re.search(r"不低于|不少于|至少|大于等于|≥", text):
        return "lte" if it_grade else "gte"
    if re.search(r"高于|大于|超过|>", text):
        return "lt" if it_grade else "gt"
    if re.search(r"低于|小于|少于|<", text):
        return "gt" if it_grade else "lt"
    if re.search(r"不大于|不超过|至多|小于等于|≤|达到|优于|及以上精度", text):
        return "lte"
    return "lte" if it_grade else "eq"


def _leaf_from_clause(clause: str) -> ConditionNode | None:
    text = clause.strip()
    it_match = re.search(r"IT\s*(\d{1,2})", text, re.IGNORECASE)
    if it_match:
        if re.search(r"外圆|外径", text):
            field = "precision.outer_diameter_it"
        elif re.search(r"内孔|内径|孔", text):
            field = "precision.inner_diameter_it"
        else:
            field = "precision.dimension_it"
        return ConditionNode(field=field, op=_comparison_operator(text, it_grade=True), value=int(it_match.group(1)))

    ra_match = re.search(r"(?:Ra|粗糙度)[^\d]{0,8}(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if ra_match:
        return ConditionNode(
            field="surface.roughness_ra",
            op=_comparison_operator(text),
            value=float(ra_match.group(1)),
        )

    tolerance_fields = {
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
    for label, field in tolerance_fields.items():
        if label not in text:
            continue
        value_match = re.search(rf"{label}[^\d]{{0,12}}(\d+(?:\.\d+)?)", text)
        if value_match:
            return ConditionNode(field=field, op=_comparison_operator(text), value=float(value_match.group(1)))

    hardness_match = re.search(r"(?:HRC|硬度)[^\d]{0,8}(\d+(?:\.\d+)?)", text, re.IGNORECASE)
    if hardness_match:
        return ConditionNode(
            field="mechanical.hardness_hrc",
            op=_comparison_operator(text),
            value=float(hardness_match.group(1)),
        )

    material_match = re.search(r"(?:材料|材质|牌号)[为是：:\s]*([A-Za-z0-9\-]+)", text)
    if material_match:
        return ConditionNode(field="material.grade", op="eq", value=material_match.group(1))

    feature_aliases = {
        "扁位": "扁位/平面", "平面": "扁位/平面", "槽": "槽类特征",
        "铰孔": "铰孔/精孔", "精孔": "铰孔/精孔", "型孔": "型孔/割扁",
        "顶尖孔": "顶尖孔", "辅助孔": "普通孔/辅助孔", "普通孔": "普通孔/辅助孔",
    }
    for alias, value in feature_aliases.items():
        if alias in text:
            leaf = ConditionNode(field="cad.features", op="contains", value=value)
            if re.search(rf"无{re.escape(alias)}|不含{re.escape(alias)}|没有{re.escape(alias)}", text):
                return ConditionNode(not_condition=leaf)
            return leaf

    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return ConditionNode(field="special.requirements", op="contains", value="无损检测要求")

    special_values = ["渗氮层要求", "铬酸阳极化要求", "硬质阳极化要求", "追溯标印", "磁粉检查要求", "烧伤检查要求"]
    for value in special_values:
        if value in text or value.replace("要求", "") in text:
            return ConditionNode(field="special.requirements", op="contains", value=value)
    return None


def _known_special_requirement(text: str, current_process_name: str) -> str | None:
    if _is_nondestructive_inspection_process(current_process_name):
        return "无损检测要求"
    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return "无损检测要求"
    if re.search(r"追溯|编号|批次.{0,6}标识|标识需求", text):
        return "追溯标印"
    if re.search(r"防护|防腐蚀|绝缘|表面稳定性|表面处理", text):
        name = str(current_process_name or "当前工序").strip()
        return name if name.endswith("要求") else f"{name}要求"
    return None


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
    dynamic_fields = {field.key: field for field in candidate.field_definitions if field.type == "boolean"}
    if not dynamic_fields:
        return candidate

    def convert(node: ConditionNode) -> ConditionNode:
        if node.field:
            definition = dynamic_fields.get(node.field)
            if definition:
                return ConditionNode(
                    field="special.requirements",
                    op="contains",
                    value=_special_requirement_for_boolean_field(definition),
                )
            return node
        if node.all_conditions is not None:
            return ConditionNode(all_conditions=[convert(child) for child in node.all_conditions])
        if node.any_conditions is not None:
            return ConditionNode(any_conditions=[convert(child) for child in node.any_conditions])
        if node.not_condition is not None:
            return ConditionNode(not_condition=convert(node.not_condition))
        return node

    when = convert(candidate.when)
    referenced_fields = set(iter_condition_fields(when))
    return candidate.model_copy(update={
        "when": when,
        "field_definitions": [field for field in candidate.field_definitions if field.key in referenced_fields],
    })


def _parse_condition_tree(source_text: str) -> ConditionNode | None:
    condition_text = re.split(r"(?:则|时)[，,]?\s*(?:纳入|加入|排除|不纳入|取消)", source_text, maxsplit=1)[0]
    or_parts = [item.strip() for item in re.split(r"或者|或是|\s或\s", condition_text) if item.strip()]
    if len(or_parts) > 1:
        children = [_parse_condition_tree(item) for item in or_parts]
        if all(children):
            return ConditionNode(any_conditions=children)
    and_parts = [item.strip() for item in re.split(r"并且|同时|而且|且", condition_text) if item.strip()]
    if len(and_parts) > 1:
        children = [_leaf_from_clause(item) for item in and_parts]
        if all(children):
            return ConditionNode(all_conditions=children)
    return _leaf_from_clause(condition_text)


def _parse_locally(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
) -> RuleConditionCandidate | None:
    special_requirement = _known_special_requirement(source_text, current_process_name)
    when = (
        ConditionNode(field="special.requirements", op="contains", value=special_requirement)
        if special_requirement else _parse_condition_tree(source_text)
    )
    if not when:
        return None
    process_ids = [current_process_id] if special_requirement else _resolve_process_ids(
        source_text,
        current_process_id,
        processes,
    )
    exclude = bool(re.search(r"排除|不纳入|取消", source_text))
    action = RuleAction(
        include_process_ids=[] if exclude else process_ids,
        exclude_process_ids=process_ids if exclude else [],
        reason=f"用户确认条件：{source_text}",
    )
    return RuleConditionCandidate(
        kind="condition",
        when=when,
        then=action,
        preview=condition_preview(when),
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


def _parse_process_relation(
    source_text: str,
    current_process_id: str,
    processes: list[RuleConditionProcessOption],
) -> RuleConditionCandidate | None:
    normalized_text = _normalized_process_name(source_text)
    referenced = [
        item.process_id
        for item in sorted(processes, key=lambda value: len(_normalized_process_name(value.display_name)), reverse=True)
        if _normalized_process_name(item.display_name)
        and _normalized_process_name(item.display_name) in normalized_text
        and item.process_id != current_process_id
    ]
    source_ids = list(dict.fromkeys(referenced))
    if not source_ids:
        return None

    if re.search(r"不能同时|不得同时|互斥|二选一|不可共存", source_text):
        relation_type = "conflicts"
    elif re.search(r"(?:前|之前).{0,12}(?:必须|需要).{0,8}(?:完成|存在|经过)|依赖于|以前置", source_text):
        relation_type = "requires"
    elif re.search(r"必须在.{0,30}(?:后|之后)|应在.{0,30}(?:后|之后)|不得早于", source_text) and not re.search(r"安排|纳入|设置|增加|出现", source_text):
        relation_type = "order_after"
    elif re.search(
        r"(?:后|之后|完成后|存在).{0,40}(?:安排|纳入|设置|增加|出现|检查)"
        r"|(?:前面|此前|之前).{0,20}(?:有|存在).{0,40}(?:安排|纳入|设置|增加|出现|检查)"
        r"|当.{0,30}(?:后|存在|有).{0,40}(?:安排|纳入|设置|增加|出现|检查)",
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


async def parse_rule_condition(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
) -> tuple[RuleConditionCandidate | None, float | None, list[str]]:
    local_relation_candidate = None if _is_nondestructive_inspection_process(current_process_name) else _parse_process_relation(
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
    candidate, confidence, issues = await _parse_with_llm(
        source_text,
        current_process_id,
        current_process_name,
        processes,
    )
    if candidate:
        candidate = _convert_boolean_fields_to_special_requirements(candidate)
        validation_issues = validate_candidate(candidate, processes)
        expected_special_requirement = _known_special_requirement(source_text, current_process_name)
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
            return candidate, confidence, issues
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
            return local_relation_candidate, 0.9, [*issues, *([fallback_note] if fallback_note else [])]
        issues.extend(relation_issues)

    local_candidate = local_condition_candidate
    if local_candidate:
        local_issues = validate_candidate(local_candidate, processes)
        if not local_issues:
            fallback_note = "已使用内置规则解析器生成候选结果，请重点核对。" if issues else ""
            return local_candidate, 0.65, [*issues, *([fallback_note] if fallback_note else [])]
        issues.extend(local_issues)

    return None, confidence, list(dict.fromkeys([*issues, "条件无法可靠映射到标准字段，请补充字段、比较关系和阈值。"]))
