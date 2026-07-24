"""Natural-language parser for user-authored process conditions."""

from __future__ import annotations

import json
import hashlib
import re
from typing import Any

from pydantic import ValidationError

from app.services.llm_service import call_llm, parse_json_from_llm
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


def _normalized_process_name(value: str) -> str:
    return re.sub(r"[\s“”\"'、，,。；;（）()]", "", str(value or "")).casefold()


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
标准字段已经能表达的检验、标印、表面处理等特殊要求继续使用 special.requirements，value 使用简明、可复用的要求名称，例如“追溯标印”“镀铜要求”。如果原文明确提出了一个标准字段无法表达、后续可由用户回答的新属性，例如“是否为试制件”“是否需要客户见证”，则创建 project_factor.* 的 boolean 动态因素；不要新增 custom.requirements 字段。
遇到字段库未预列、但原文已经给出明确取值的结构特征或工艺要求时，仍使用受控字段：未知结构特征使用 cad.features contains 原文中的简明特征标签；未知工艺要求使用 special.requirements contains 原文中的简明要求标签。不要因为标签值不在 options 中而返回 unresolved。
IT 等级数字越小代表精度越高；“达到 IT8/IT8及以上精度”通常转换为数值 <= 8。
公差、粗糙度等“达到某值/不大于某值”转换为 <=。
如果条件无法可靠映射，返回 unresolved，并且不要猜测。
参数条件输出格式：
{"candidate":{"kind":"condition","when":{"field":"...","op":"...","value":1},"then":{"include_process_ids":["..."],"exclude_process_ids":[],"reason":"..."},"field_definitions":[],"preview":"..."},"confidence":0.0,"warnings":[],"unresolved":[]}
动态类别示例：用户写“材料类别为不锈钢”，可输出 field=project_factor.material_category、op=eq、value=不锈钢，并定义 label=材料类别、category=材料、type=single_select、operators=[eq,neq,in]、options=[{value:不锈钢,label:不锈钢}]、allow_custom=true、source=用户条件。
工序关系输出格式：
{"candidate":{"kind":"process_relation","relation":{"relation_type":"trigger_after","source_process_ids":["process_a"],"target_process_ids":["process_b"]},"preview":"工序A进入路线 → 纳入工序B，并排在工序A之后"},"confidence":0.0,"warnings":[],"unresolved":[]}
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


def _project_factor_key(label: str) -> str:
    normalized = re.sub(r"\s+", "", str(label or "").strip()).casefold()
    digest = hashlib.sha256(normalized.encode("utf-8")).hexdigest()[:12]
    return f"project_factor.{digest}"


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
    values = [item.strip() for item in re.split(r"或者|或是|或|、", raw_value) if item.strip()]
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
    dynamic_condition = None if special_requirement else _dynamic_categorical_condition(source_text)
    when = ConditionNode(field="special.requirements", op="contains", value=special_requirement) if special_requirement else (
        _parse_condition_tree(source_text)
        or (dynamic_condition[0] if dynamic_condition else None)
        or _generic_tag_condition(source_text)
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
        r"(?:后|之后|完成后|存在).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)"
        r"|(?:前面|此前|之前).{0,20}(?:有|存在|出现).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)"
        r"|当.{0,30}(?:后|存在|有|出现).{0,40}(?:安排|纳入|加入|添加|设置|增加|出现|检查|释放|进行|执行|实施|处理)",
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

    # A relation that names a route process and gives an explicit ordering or
    # trigger is deterministic.  Return it immediately: it avoids letting an
    # unavailable or over-general LLM turn a clear dependency into a vague
    # parameter condition.  It still remains only a *candidate* and must be
    # confirmed by the user before it can enter the exported rule package.
    if local_relation_candidate:
        relation_issues = validate_candidate(local_relation_candidate, processes)
        if not relation_issues:
            return local_relation_candidate, 0.9, []

    if local_condition_candidate and local_condition_candidate.field_definitions:
        local_issues = validate_candidate(local_condition_candidate, processes)
        if not local_issues:
            return local_condition_candidate, 0.9, []

    candidate, confidence, issues = await _parse_with_llm(
        source_text,
        current_process_id,
        current_process_name,
        processes,
    )
    if candidate:
        candidate = _convert_boolean_fields_to_special_requirements(candidate)
        validation_issues = validate_candidate(candidate, processes)
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
