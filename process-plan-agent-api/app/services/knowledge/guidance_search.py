"""Intent and constrained keyword retrieval for the bundled Word guidance.

A machining topic, family and material are independent constraints. Generic
words such as 轴套 and 工艺 must never substitute for a missing rule topic.
"""
from __future__ import annotations

import re
from typing import Any, Callable

GUIDANCE_CATEGORIES = {"process_guidance", "typical_route"}
RULE_MARKERS = ("何时", "什么时候", "为什么", "能否", "可否", "是否", "必须", "省略", "适用条件", "前提", "需不需要", "什么条件", "哪些条件")
SOURCE_MARKERS = ("工艺说明", "word", "附件", "图片", "图中", "典型指导")
TOPIC_ALIASES = {
    "去应力": ("去应力", "消除应力", "去除应力"),
    "研孔": ("研孔",), "珩孔": ("珩孔", "珩磨"), "时效": ("时效",),
    "配研": ("配研",), "配套": ("配套", "配合间隙"),
    "硬阳化": ("硬阳化", "硬质阳极氧化", "硬质阳极化"),
    "冲洗": ("冲洗",), "低温灵活性试验": ("低温灵活性试验", "低温灵活性", "低温试验"),
    "调质": ("调质",), "硬度": ("硬度", "hrc"),
    "氮化": ("氮化",), "氰化": ("氰化",), "镀铬": ("镀铬",),
    "电火花": ("电火花",), "线切割": ("线切割",), "锐边": ("锐边", "尖边"),
    "余量": ("余量", "过加工", "膜层增长", "膜层生长"),
    "公式": ("公式", "计算式", "变量"), "清洗": ("清洗",), "油封": ("油封",),
}
# These objects narrow a rule/resource question, but do not make a plain
# capacity or master-data query a Word query by themselves.
OBJECT_TERMS = ("内孔", "外圆", "端面", "沟槽", "钻孔", "铰孔", "镗孔", "磨削", "车削", "质量检验", "检验", "夹具", "刀具", "量具", "设备")
GENERIC_TERMS = ("轴套", "衬套", "套筒", "活门", "组件", "工艺", "路线", "典型", "说明", "使用", "需要", "什么", "哪些", "时候", "是否", "必须", "省略", "为什么", "何时", "有关", "如何", "怎么", "样例", "资料", "条件", "适用", "阶段", "加工", "可以", "中的", "附件", "图片", "图中", "相关", "要求", "参数", "材料", "状态", "钢件", "有色金属")
CONFLICT_MESSAGE = "资料存在冲突，暂无足够依据确定；已同时列出相关原值及来源，请核对后再确定。"
PENDING_MESSAGE = "相关资料仍待核对，样例库没有足够依据确定；请查看原文与核对提示。"


def _text(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(_text(item) for item in value.values())
    if isinstance(value, (list, tuple)):
        return " ".join(_text(item) for item in value)
    return "" if value is None else str(value)


def _normalized(value: Any) -> str:
    return re.sub(r"\s+", "", _text(value)).lower()


def _topics(query: str) -> list[str]:
    lowered = query.lower()
    return [canonical for canonical, aliases in TOPIC_ALIASES.items() if any(alias in lowered for alias in aliases)]


def _rule_query(query: str) -> bool:
    return any(marker in query for marker in RULE_MARKERS) or bool(re.search(r"需要.*吗|条件.*(?:是什么|有哪些)", query))


def guidance_intent(query: str, records: tuple[dict[str, Any], ...]) -> str | None:
    """Return a Word intent only where evidence type is identifiable."""
    lowered = query.lower()
    if any(marker in query for marker in ("历史", "案例", "曾经", "实际执行")):
        return None
    explicit_source = any(marker in lowered for marker in SOURCE_MARKERS)
    # Target IT/Ra questions continue to use numeric capability matching.
    if not explicit_source and re.search(r"(?i)\bit\s*\d|\bra\s*\d|精度|粗糙度|经济精度", query):
        return None
    topics = _topics(query)
    rule = _rule_query(query)
    # Tool applicability is master data; it is not a process rule merely
    # because the sentence contains the word 适用.
    if not explicit_source and not topics and any(word in query for word in ("刀具", "铰刀", "镗刀", "钻头", "量具", "车床")):
        return None
    if rule:
        return "process_guidance"
    if ("典型" in query or explicit_source) and any(word in query for word in ("路线", "流程", "工序顺序")):
        return "typical_route"
    if explicit_source or topics:
        return "process_guidance"
    if any(_normalized(record.get("id")) in lowered for record in records if record.get("category") in GUIDANCE_CATEGORIES and record.get("id")):
        return "process_guidance"
    return None


def _family(query: str) -> str | None:
    if "组件" in query:
        return "组件"
    if any(word in query for word in ("轴套", "衬套", "套筒")):
        return "衬套"
    return "活门" if "活门" in query else None


def _identifiers(query: str) -> list[str]:
    # Require an alphanumeric identifier: bare dimensions and numeric ranges
    # (such as 22-32 HRC) are not material/part constraints.
    return [
        token.lower()
        for token in re.findall(r"[A-Za-z0-9][A-Za-z0-9./+-]*", query)
        if re.search(r"\d", token) and re.search(r"[A-Za-z]", token)
    ]


def _matches_constraints(
    query: str,
    record: dict[str, Any],
    *,
    check_identifiers: bool = True,
) -> bool:
    guidance = record.get("guidance") or {}
    family = _family(query)
    if family and family not in _text(guidance.get("part_family")):
        return False
    context = _normalized([
        guidance.get("materials"), guidance.get("applicability"), guidance.get("typical_part"),
        record.get("id"), record.get("source", {}).get("identity"), guidance.get("resources"),
        guidance.get("conditions"), guidance.get("original_excerpt"),
    ])
    if check_identifiers and any(token not in context for token in _identifiers(query)):
        return False
    material_context = _normalized([guidance.get("materials"), guidance.get("applicability")])
    if "钢件" in query and not any(word in material_context for word in ("钢", "9cr", "4cr")):
        return False
    if "有色金属" in query and not any(word in material_context for word in ("有色", "6061", "qa", "铜", "铝")):
        return False
    return True


def _query_keywords(query: str) -> list[str]:
    residual = query.lower()
    for word in sorted((*GENERIC_TERMS, *SOURCE_MARKERS, *RULE_MARKERS, "是什么", "有哪些", "是多少", "怎么做", "怎么办"), key=len, reverse=True):
        residual = residual.replace(word, " ")
    residual = re.sub(r"[A-Za-z0-9][A-Za-z0-9./+-]*", " ", residual)
    return list(dict.fromkeys(chunk for chunk in re.findall(r"[\u3400-\u9fff]{2,}", residual) if chunk not in ("是什", "多少", "这个")))


def _topic_matches(topic: str, value: Any) -> bool:
    text = _normalized(value)
    return any(alias in text for alias in TOPIC_ALIASES[topic])


def _rank(query: str, record: dict[str, Any], intent: str) -> float | None:
    guidance = record.get("guidance") or {}
    if not _matches_constraints(query, record):
        return None
    primary = [record.get("title"), guidance.get("topics")]
    details = [guidance.get("conditions"), guidance.get("conclusion"), guidance.get("exceptions"), guidance.get("resources")]
    topics = _topics(query)
    if intent == "typical_route":
        # Family/material select a route. A named operation additionally
        # filters that route; it does not reconstruct an undocumented order.
        route_text = [primary, details, guidance.get("operations")]
        specific_topics = [topic for topic in topics if topic not in ("配套",)]
        if specific_topics and not all(_topic_matches(topic, route_text) for topic in specific_topics):
            return None
        return 20.0 + len(specific_topics)
    kind = guidance.get("kind")
    if "余量" in topics and "公式" not in topics and kind != "allowance":
        return None
    if "公式" in topics and kind != "formula":
        return None
    # A source-specific resource question is answered by a resource record,
    # never by a general operation mention that happens to contain 设备.
    resources_requested = [word for word in ("设备", "刀具", "量具", "夹具") if word in query]
    if resources_requested and any(marker in query for marker in ("使用", "用什么", "哪些", "是什么", "附件", "图片", "图中")) and kind != "resource":
        return None
    explicit_source = any(marker in query.lower() for marker in SOURCE_MARKERS)
    if kind == "resource" and explicit_source:
        category_aliases = {
            "设备": "equipment", "刀具": "tool", "量具": "gauge", "夹具": "fixture",
        }
        requested_categories = {category_aliases[word] for word in resources_requested if word in category_aliases}
        resource_items = guidance.get("resources") or []
        available_categories = {item.get("category") for item in resource_items if isinstance(item, dict)}
        if requested_categories and not requested_categories.intersection(available_categories):
            status = guidance.get("verification_status")
            unresolved_mention = status == "pending" and any(word in _text([primary, details]) for word in resources_requested)
            if not unresolved_mention:
                return None
        if topics:
            primary_hits = [topic for topic in topics if _topic_matches(topic, primary)]
            detail_hits = [topic for topic in topics if _topic_matches(topic, details)]
            if not primary_hits and not detail_hits:
                return None
        return 12.0 + len(topics)
    primary_hits = [topic for topic in topics if _topic_matches(topic, primary)]
    detail_hits = [topic for topic in topics if _topic_matches(topic, details)]
    matched_topics = [topic for topic in topics if topic in primary_hits or topic in detail_hits]
    if topics and not matched_topics:
        return None
    if not topics:
        objects = [word for word in OBJECT_TERMS if word in query]
        keywords = _query_keywords(query)
        searchable = _normalized([primary, details])
        # Exact residual words and their meaningful bigrams let resource names
        # work without a closed topic dictionary, while generic family words
        # never qualify. Unknown rule topics do not fall back to family hits.
        keyword_hits = [word for word in keywords if word in searchable or (len(word) > 2 and all(word[i:i + 2] in searchable for i in range(len(word) - 1)))]
        object_hits = [word for word in objects if word in searchable]
        id_match = any(token in _normalized([record.get("id"), guidance.get("resources")]) for token in _identifiers(query))
        if keywords and len(keyword_hits) != len(keywords):
            return None
        if not keyword_hits and not object_hits and not id_match:
            return None
        score = 4.0 * len(keyword_hits) + 2.0 * len(object_hits)
    else:
        score = 8.0 * len(primary_hits) + 3.0 * len(detail_hits)
    if "省略" in query and "省略" in _text(details):
        score += 10.0
    if _rule_query(query) and kind == "rule":
        score += 2.0
    return score


def guidance_warnings(record: dict[str, Any]) -> list[str]:
    guidance = record.get("guidance") or {}
    warnings = list(record.get("data_warnings") or [])
    status = guidance.get("verification_status")
    if status == "conflict":
        warnings.append("存在尚未解决的原文冲突，不作为唯一结论。")
    elif status != "verified":
        warnings.append("内容待核对，不能作为确定结论依据。")
    if record.get("category") == "typical_route" and guidance.get("completeness") != "verified_sequence":
        warnings.append("此记录仅为阶段概要，未核实为完整工序路线。")
    warnings.append("已核对原文仅表示提取一致，不代表文件现行有效或业务批准。")
    return list(dict.fromkeys(warnings))


def search_guidance(
    query: str,
    records: tuple[dict[str, Any], ...],
    top_k: int,
    to_item: Callable[[dict[str, Any], float], dict[str, Any]],
) -> dict[str, Any] | None:
    intent = guidance_intent(query, records)
    if intent is None:
        return None
    ranked = []
    for record in records:
        if record.get("category") != intent or not isinstance(record.get("guidance"), dict):
            continue
        score = _rank(query, record, intent)
        if score is not None:
            ranked.append((score, record))
    ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("id"))))
    selected = ranked[:top_k]
    # An unresolved contradiction is part of the evidence, including the side
    # that ranks below the UI's top_k. Expand all members using stable groups.
    groups = {group for _, record in ranked for group in record.get("conflict_ids", [])}
    selected_ids = {record.get("id") for _, record in selected}
    for record in records:
        if (
            groups.intersection(record.get("conflict_ids") or [])
            and record.get("id") not in selected_ids
            and _matches_constraints(query, record, check_identifiers=False)
        ):
            selected.append((0.0, record))
            selected_ids.add(record.get("id"))
    items = [to_item(record, round(score, 3)) for score, record in selected]
    conflict = bool(groups) or any((item.get("guidance") or {}).get("verification_status") == "conflict" for item in items)
    pending = any((item.get("guidance") or {}).get("verification_status") not in ("verified", "conflict") for item in items)
    return {
        "status": "insufficient_evidence" if conflict or pending else "ok",
        "message": CONFLICT_MESSAGE if conflict else PENDING_MESSAGE if pending else "" if items else "本地样例库没有找到该问题的工艺说明依据，请补充加工主题、材料或适用对象。",
        "answer": "", "items": items, "intent": intent, "relationship_gaps": [],
    }
