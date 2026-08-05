"""Deterministic local parsing for user-authored process conditions."""

from __future__ import annotations

import re

from app.services.rule_packages.condition_contracts import (
    ProcessRelationCandidate,
    RuleConditionCandidate,
    RuleConditionProcessOption,
)
from app.services.rule_packages.condition_registry import condition_preview
from app.services.rule_packages.condition_semantics import with_source_evidence as _with_source_evidence
from app.services.rule_packages.contracts import ConditionNode, RuleAction


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


def known_special_requirement(text: str, current_process_name: str) -> str | None:
    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return "无损检测要求"
    if re.search(r"追溯|编号|批次.{0,6}标识|标识需求", text):
        return "追溯标印"
    surface_requirement = re.search(
        r"防护、防腐蚀、绝缘或表面稳定性要求|防护、防腐蚀、绝缘或表面稳定性处理",
        text,
    )
    if surface_requirement:
        return surface_requirement.group(0)
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
    # This umbrella phrase is expanded by the partial hole parser into known
    # standard factors. It must not be downgraded to an unbound free-form tag.
    if re.search(r"孔类结构.*孔加工要求|孔加工要求.*孔类结构", text):
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


def parse_condition_tree(source_text: str) -> ConditionNode | None:
    condition_text = re.split(r"(?:则|时)[，,]?\s*(?:纳入|加入|排除|不纳入|取消)", source_text, maxsplit=1)[0]
    or_parts = [item.strip() for item in re.split(r"或者|或是|\s或\s", condition_text) if item.strip()]
    if len(or_parts) > 1:
        children = [parse_condition_tree(item) for item in or_parts]
        if all(children):
            return ConditionNode(any_conditions=children)
        return None
    and_parts = [item.strip() for item in re.split(r"并且|同时|而且|且", condition_text) if item.strip()]
    if len(and_parts) > 1:
        children = [_leaf_from_clause(item) for item in and_parts]
        if all(children):
            return ConditionNode(all_conditions=children)
        return None
    return _leaf_from_clause(condition_text)


def parse_local_condition(
    source_text: str,
    current_process_id: str,
    current_process_name: str,
    processes: list[RuleConditionProcessOption],
) -> RuleConditionCandidate | None:
    special_requirement = known_special_requirement(source_text, current_process_name)
    when = ConditionNode(field="special.requirements", op="contains", value=special_requirement) if special_requirement else (
        parse_condition_tree(source_text)
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
        preview=condition_preview(when),
    )


def _partial_hole_condition(text: str) -> ConditionNode | None:
    if re.search(r"(?:无|没有|不含|不存在).{0,4}(?:内孔|通孔|盲孔|中心孔|顶尖孔)", text):
        return None
    if re.search(r"孔类结构.*孔加工要求|孔加工要求.*孔类结构", text):
        values = [
            ("cad.features", "普通孔/辅助孔"),
            ("cad.features", "铰孔/精孔"),
            ("cad.features", "型孔/割扁"),
            ("cad.features", "顶尖孔"),
            ("precision.grades", "孔精加工"),
            ("precision.grades", "珩孔要求"),
            ("precision.grades", "研孔要求"),
        ]
        return ConditionNode(
            any_conditions=[
                ConditionNode(field=field, op="contains", value=value)
                for field, value in values
            ]
        )
    values: list[str] = []
    if re.search(r"内孔|通孔|盲孔|一般孔|普通孔|辅助孔", text):
        values.append("普通孔/辅助孔")
    if re.search(r"中心孔|顶尖孔", text):
        values.append("顶尖孔")
    if re.search(r"铰孔|精孔", text):
        values.append("铰孔/精孔")
    if re.search(r"型孔|异形孔|异型孔|割扁", text):
        values.append("型孔/割扁")
    values = list(dict.fromkeys(values))
    if not values:
        return None
    children = [ConditionNode(field="cad.features", op="contains", value=value) for value in values]
    return children[0] if len(children) == 1 else ConditionNode(any_conditions=children)


def parse_partial_condition_candidate(
    source_text: str,
    current_process_id: str,
    processes: list[RuleConditionProcessOption],
) -> tuple[RuleConditionCandidate | None, list[str]]:
    condition_text = re.split(
        r"(?:则|时)[，,]?\s*(?:纳入|加入|安排|设置|排除|不纳入|取消)",
        source_text,
        maxsplit=1,
    )[0]
    parts = [
        part.strip()
        for part in re.split(r"以及|并且|同时|而且|且", condition_text)
        if part.strip()
    ]
    recognized: list[ConditionNode] = []
    ignored: list[str] = []
    for raw_part in parts:
        part = re.sub(r"^(?:当|如果|若)?(?:零件|产品|工件)?", "", raw_part).strip(" ，,。；;：:")
        node = _partial_hole_condition(part) or _leaf_from_clause(part)
        if node is not None:
            recognized.append(node)
        elif part:
            ignored.append(part)
    if not recognized:
        return None, []

    when = recognized[0] if len(recognized) == 1 else ConditionNode(all_conditions=recognized)
    process_ids = _resolve_process_ids(source_text, current_process_id, processes)
    exclude = bool(re.search(r"排除|不纳入|取消", source_text))
    candidate = RuleConditionCandidate(
        kind="condition",
        when=when,
        then=RuleAction(
            include_process_ids=[] if exclude else process_ids,
            exclude_process_ids=process_ids if exclude else [],
            reason=f"AI 草稿依据：{source_text}",
        ),
        preview=condition_preview(when),
    )
    issues = [f"原文中“{part}”未能明确转化为具体条件，已忽略。" for part in ignored]
    return _with_source_evidence(candidate, source_text), issues


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


def parse_process_relation(
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

__all__ = [
    "known_special_requirement",
    "parse_condition_tree",
    "parse_local_condition",
    "parse_partial_condition_candidate",
    "parse_process_relation",
]
