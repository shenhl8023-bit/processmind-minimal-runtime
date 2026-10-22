"""Search the bundled machining demo records without remote services."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

from app.core.paths import API_ROOT
from app.services.knowledge.guidance_search import search_guidance, guidance_warnings


DATA_PATH = API_ROOT / "knowledge" / "demo" / "local_records.json"
CATEGORY_LABELS = {
    "history": "历史工艺",
    "capability": "加工能力",
    "equipment": "设备",
    "tool": "刀具",
    "gauge": "量具",
    "process_guidance": "工艺说明",
    "typical_route": "典型路线",
}
DOMAIN_TERMS = (
    "轴套", "衬套", "套筒", "活门", "内孔", "内圆", "外圆", "端面", "沟槽", "槽", "螺纹", "倒角",
    "钻孔", "扩孔", "铰孔", "镗孔", "粗镗", "半精镗", "精镗", "精铰", "钻削", "镗削", "车外圆", "车内孔", "车削", "磨削", "拉削", "滚齿", "切断",
    "粗加工", "半精加工", "精加工", "粗糙度", "精度", "余量", "硬度", "材料", "工序", "工步", "工艺",
    "设备", "刀具", "量具", "夹具", "测量", "检验", "批量", "转速", "功率",
)
SYNONYMS = {
    "轴套": ("衬套", "套筒"),
    "内孔": ("内圆", "镗孔", "铰孔"),
    "外圆": ("车外圆", "车削"),
    "量具": ("测量", "检验"),
}
STOP_TERMS = {"应该", "怎么", "如何", "安排", "相关", "哪些", "什么", "可以", "需要", "推荐", "参考", "一下", "有关", "进行", "里面"}
IDENTIFIER_RE = re.compile(r"(?i)(?=[a-z0-9./+-]*\d)[a-z][a-z0-9./+-]{2,}")
RELATION_LABELS = {"equipment": "设备", "tool": "刀具", "gauge": "量具"}
ENTITY_ID_FIELDS = {"equipment": "设备ID", "tool": "刀具ID", "gauge": "量具ID"}
ENTITY_RESOURCE_FIELDS = {"equipment": "设备", "tool": "刀具", "gauge": "量具"}
ENTITY_CATALOG_MARKERS = (
    "有哪些", "哪些", "清单", "列表", "主数据", "参数", "规格", "型号", "范围", "是什么",
    "所有", "全部", "有没有", "有多少", "多少", "很多",
)
FEATURE_ALIASES = {
    "内孔": ("内孔", "内圆"),
    "孔": ("孔", "内孔", "内圆", "镗孔", "铰孔", "钻孔"),
    "外圆": ("外圆", "外圆柱表面", "车外圆"),
    "端面": ("端面", "平面"),
    "螺纹": ("螺纹",),
    "槽": ("沟槽", "槽"),
}
STAGE_ALIASES = {
    "粗加工阶段": ("粗加工阶段", "粗加工", "粗车", "粗镗", "粗磨"),
    "半精加工阶段": ("半精加工阶段", "半精加工", "半精车", "半精镗", "半精磨"),
    "精加工阶段": ("精加工阶段", "精加工", "精车", "精镗", "精铰", "精磨"),
}
METHOD_QUERY_ALIASES = {
    "精铰": ("精铰孔", "精铰"),
    "铰孔": ("铰孔",),
    "钻孔": ("钻孔",),
    "扩孔": ("扩孔",),
    "镗削": ("镗削", "镗孔"),
    "粗镗": ("粗镗",),
    "半精镗": ("半精镗",),
    "精镗": ("精镗",),
}
HISTORY_CATALOG_MARKERS = ("历史案例", "历史工艺", "历史记录", "工艺案例", "案例")
MATERIAL_TERMS = (
    "不锈钢", "淬火钢", "未淬火钢", "钛合金", "高温合金", "铝合金", "有色金属", "黑色金属", "非金属",
    "铸铁", "铸钢", "黄铜", "青铜", "轻合金", "铝铜", "金属", "钢", "铜", "铝",
)


@lru_cache(maxsize=1)
def _load_records(path: str = str(DATA_PATH)) -> tuple[dict[str, Any], ...]:
    records = json.loads(Path(path).read_text(encoding="utf-8"))
    if not isinstance(records, list):
        raise ValueError("本地知识数据格式无效")
    extra_path = Path(path).with_name("word_records.json")
    if extra_path.is_file():
        extra = json.loads(extra_path.read_text(encoding="utf-8"))
        if not isinstance(extra, list):
            raise ValueError("本地 Word 知识数据格式无效")
        records.extend(extra)
    return tuple(record for record in records if isinstance(record, dict))


def _search_terms(query: str) -> list[str]:
    lowered = query.lower()
    terms = [term.lower() for term in DOMAIN_TERMS if term in query and term not in STOP_TERMS]
    terms.extend(token.lower() for token in re.findall(r"[a-zA-Z0-9][a-zA-Z0-9./+-]*", query))
    for term, synonyms in SYNONYMS.items():
        if term in query:
            terms.extend(synonym.lower() for synonym in synonyms)
    if not terms:
        for chunk in re.findall(r"[\u3400-\u9fff]+", query):
            terms.extend(chunk[index:index + 2].lower() for index in range(len(chunk) - 1))
    return list(dict.fromkeys(term for term in terms if term and term not in STOP_TERMS))


def _flatten(value: Any) -> str:
    if isinstance(value, dict):
        return " ".join(f"{key} {_flatten(item)}" for key, item in value.items())
    if isinstance(value, (list, tuple)):
        return " ".join(_flatten(item) for item in value)
    return "" if value is None else str(value)


def _format_value(value: Any) -> str:
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    return str(value)


def _record_content(record: dict[str, Any]) -> str:
    fields = record.get("fields", {})
    if not isinstance(fields, dict):
        fields = {}
    lines = [f"{key}：{_format_value(value)}" for key, value in fields.items() if value not in (None, "", [], {})]
    return "\n".join(lines)[:5000]


def _record_warnings(record: dict[str, Any]) -> list[str]:
    fields = record.get("fields", {})
    warnings = []
    for label, low_key, high_key in (
        ("精度等级", "精度等级下限", "精度等级上限"),
        ("Ra", "Ra下限_μm", "Ra上限_μm"),
        ("加工余量", "加工余量下限_mm", "加工余量上限_mm"),
        ("量具测量范围", "测量范围下限_mm", "测量范围上限_mm"),
    ):
        low, high = _number(fields.get(low_key)), _number(fields.get(high_key))
        if low is not None and high is not None and low > high:
            warnings.append(f"{label}原始下限 {low} 大于上限 {high}，该范围异常，不作为适配或能力结论依据；请核对来源。")
    return warnings


def _record_source(record: dict[str, Any]) -> dict[str, Any]:
    source = record.get("source") or {}
    return {key: source.get(key) for key in ("document_id", "document_name", "page_no", "worksheet", "row_no", "cell_range", "identity")}


def _number(value: Any) -> int | float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    try:
        return float(str(value).strip().replace(",", ""))
    except (TypeError, ValueError):
        return None


def _reference_values(value: Any) -> list[str]:
    if value in (None, "", [], {}):
        return []
    raw_values = value if isinstance(value, (list, tuple)) else re.split(r"[,，;；\s]+", str(value))
    return [str(item).strip() for item in raw_values if str(item).strip()]


def _entity_index(records: tuple[dict[str, Any], ...], category: str, id_field: str) -> dict[str, dict[str, Any]]:
    return {
        str(record.get("fields", {}).get(id_field)): record
        for record in records
        if record.get("category") == category
        and isinstance(record.get("fields"), dict)
        and record.get("fields", {}).get(id_field)
    }


def _entity_summary(record: dict[str, Any]) -> dict[str, Any]:
    fields = record.get("fields", {})
    id_field = {"equipment": "设备ID", "tool": "刀具ID", "gauge": "量具ID"}.get(record.get("category"), "")
    name_field = {"equipment": "设备名称", "tool": "刀具名称", "gauge": "量具名称"}.get(record.get("category"), "")
    reserved = {id_field, "来源文件", "来源工作表", "来源行号", "来源单元格范围", "证据来源", "备注", "数据状态"}
    return {
        "id": str(fields.get(id_field) or "") or None,
        "name": str(fields.get(name_field) or record.get("title") or "本地记录"),
        "record_level": str(fields.get("记录层级") or "") or None,
        "entity_category": str(fields.get("设备类别") or fields.get("刀具类别") or fields.get("量具类别") or "") or None,
        "model": str(fields.get("设备型号") or fields.get("型号或规格") or "") or None,
        "fields": {key: value for key, value in fields.items() if key not in reserved and value not in (None, "", [], {})},
    }


def _relationship(
    fields: dict[str, Any],
    *,
    relation_name: str,
    id_key: str,
    text_keys: tuple[str, ...],
    index: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    references = _reference_values(fields.get(id_key))
    linked = [index[reference] for reference in references if reference in index]
    if linked:
        return {
            "status": "linked",
            "basis": "id",
            "items": [_entity_summary(record) for record in linked],
        }
    hints = [str(fields[key]).strip() for key in text_keys if fields.get(key) not in (None, "", [], {})]
    if hints:
        return {
            "status": "category_hint",
            "basis": "record_text",
            "items": [{"id": None, "name": hint, "record_level": "类别线索", "entity_category": None, "model": None, "fields": {}} for hint in dict.fromkeys(hints)],
        }
    return {"status": "not_provided", "basis": "missing", "items": []}


def _capability_data(record: dict[str, Any], indexes: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    fields = record.get("fields", {})
    precision_min = _number(fields.get("精度等级下限"))
    precision_max = _number(fields.get("精度等级上限"))
    roughness_min = _number(fields.get("Ra下限_μm"))
    roughness_max = _number(fields.get("Ra上限_μm"))
    allowance_min = _number(fields.get("加工余量下限_mm"))
    allowance_max = _number(fields.get("加工余量上限_mm"))
    precision_valid = precision_min is None or precision_max is None or precision_min <= precision_max
    roughness_valid = roughness_min is None or roughness_max is None or roughness_min <= roughness_max
    allowance_valid = allowance_min is None or allowance_max is None or allowance_min <= allowance_max
    return {
        "feature": fields.get("加工特征"),
        "method": fields.get("加工方法"),
        "stage": fields.get("加工阶段"),
        "precision": {
            "type": fields.get("精度指标类型"),
            "min_grade": precision_min if precision_valid else None,
            "max_grade": precision_max if precision_valid else None,
            "code": fields.get("精度代号_原文"),
            "bounds_valid": precision_valid,
        },
        "roughness": {
            "min_um": roughness_min if roughness_valid else None,
            "max_um": roughness_max if roughness_valid else None,
            "bounds_valid": roughness_valid,
        },
        "allowance": {
            "min_mm": allowance_min if allowance_valid else None,
            "max_mm": allowance_max if allowance_valid else None,
            "basis": fields.get("余量口径"),
            "bounds_valid": allowance_valid,
        },
        "material": fields.get("工件材料"),
        "material_state": fields.get("材料状态"),
        "size": {
            "type": fields.get("适用尺寸类型"),
            "min_mm": _number(fields.get("适用尺寸下限_mm")),
            "max_mm": _number(fields.get("适用尺寸上限_mm")),
        },
        "conditions": fields.get("适用条件"),
        "tool_material": fields.get("刀具材料条件"),
        "other_metrics": fields.get("其他指标_原文"),
    }


def _to_item(record: dict[str, Any], score: float, indexes: dict[str, dict[str, dict[str, Any]]]) -> dict[str, Any]:
    source = record.get("source", {})
    warnings = _record_warnings(record)
    if isinstance(record.get("guidance"), dict):
        warnings.extend(guidance_warnings(record))
    item = {
        "id": str(record.get("id") or "local-record"),
        "category": str(record.get("category") or "other"),
        "title": str(record.get("title") or "本地知识记录"),
        "content": _record_content(record) + ("\n数据校验提示：" + "；".join(warnings) if warnings else ""),
        "data_warnings": warnings,
        "score": score,
        "retrieval_method": "本地关键词检索",
        "source": {
            "document_id": source.get("document_id"),
            "document_name": source.get("document_name"),
            "page_no": source.get("page_no"),
            "identity": source.get("identity"),
            "worksheet": source.get("worksheet"),
            "row_no": source.get("row_no"),
            "cell_range": source.get("cell_range"),
        },
    }
    if isinstance(record.get("guidance"), dict):
        item["guidance"] = record["guidance"]
    if item["category"] == "capability":
        fields = record.get("fields", {})
        item["capability"] = _capability_data(record, indexes)
        item["relationships"] = {
            "equipment": _relationship(fields, relation_name="equipment", id_key="关联设备ID", text_keys=("设备名称或类别",), index=indexes["equipment"]),
            "tool": _relationship(fields, relation_name="tool", id_key="关联刀具ID", text_keys=("刀具类别",), index=indexes["tool"]),
            "gauge": _relationship(fields, relation_name="gauge", id_key="关联量具ID", text_keys=("量具名称或类别", "量具类别"), index=indexes["gauge"]),
        }
    return item


def _query_methods(query: str, records: tuple[dict[str, Any], ...]) -> list[str]:
    methods = {
        str(record.get("fields", {}).get("加工方法")).strip()
        for record in records
        if record.get("category") == "capability" and record.get("fields", {}).get("加工方法")
    }
    lowered = re.sub(r"\s+", "", query.lower())
    matches: list[tuple[int, int, str]] = []
    for method in methods:
        # Stage wording and one-character labels inside equipment names are
        # not explicit machining methods.
        if len(method.strip()) < 2 or method == "精加工":
            continue
        for alias in METHOD_QUERY_ALIASES.get(method, (method,)):
            normalized = alias.lower().replace(" ", "")
            matches.extend(
                (match.start(), match.end(), method)
                for match in re.finditer(re.escape(normalized), lowered)
                if lowered[match.end():match.end() + 1] != "床"
            )
    selected: list[tuple[int, int, str]] = []
    for match in sorted(matches, key=lambda value: (-(value[1] - value[0]), value[0], value[2])):
        if not any(start <= match[0] and end >= match[1] for start, end, _ in selected):
            selected.append(match)
    return list(dict.fromkeys(method for _, _, method in sorted(selected)))


def _query_features(query: str) -> list[str]:
    matches: list[str] = []
    for canonical, aliases in sorted(FEATURE_ALIASES.items(), key=lambda item: max(map(len, item[1])), reverse=True):
        if any(alias in query for alias in sorted(aliases, key=len, reverse=True)):
            if canonical == "孔" and "内孔" in matches:
                continue
            matches.append(canonical)
    return matches


def _feature_matches(value: Any, target: str) -> bool:
    if not value:
        return False
    normalized = str(value)
    aliases = FEATURE_ALIASES[target]
    if target == "内孔" and normalized == "孔":
        return True
    return any(alias in normalized or normalized in alias for alias in aliases)


def _query_stages(query: str) -> list[str]:
    # A method such as "粗镗" describes the method itself; only explicit
    # phase wording should constrain the capability table to that stage.
    remaining = query
    stages = []
    for canonical, aliases in sorted(STAGE_ALIASES.items(), key=lambda item: len(item[0]), reverse=True):
        explicit_aliases = tuple(alias for alias in aliases if "阶段" in alias or alias in {"粗加工", "半精加工", "精加工"})
        if any(alias in remaining for alias in explicit_aliases):
            stages.append(canonical)
            for alias in sorted(explicit_aliases, key=len, reverse=True):
                remaining = remaining.replace(alias, " ")
    return stages


def _stage_matches(value: Any, stages: list[str]) -> bool:
    normalized = str(value or "")
    return any(normalized in {stage, stage.removesuffix("加工阶段")} for stage in stages)


def _entity_query_terms(query: str, records: tuple[dict[str, Any], ...], category: str) -> list[str]:
    label = RELATION_LABELS[category]
    terms = {
        str(record.get("fields", {}).get(key) or "").strip()
        for record in records if record.get("category") == category
        for key in (f"{label}名称", f"{label}类别")
    }
    matched = [term for term in terms if len(term) > 1 and term in query]
    return [term for term in matched if not any(term != other and term in other for other in matched)]


def _query_materials(query: str) -> list[str]:
    # Match literal material classes only; do not infer that a named alloy
    # grade belongs to a class without a mapping in the sample data.
    matched = [term for term in MATERIAL_TERMS if term in query]
    return [term for term in matched if not any(term != other and term in other for other in matched)]


def _query_dimension_range(query: str) -> tuple[float, float] | None:
    """Parse a requested dimension interval such as ``20～25 mm``."""
    pattern = re.compile(
        r"(?<![A-Za-z0-9.])(?P<lower>\d+(?:\.\d+)?)\s*(?:mm|毫米)?\s*"
        r"(?:(?:~|～|-|—|至|到)\s*(?P<upper>\d+(?:\.\d+)?)\s*(?:mm|毫米)?)?",
        re.IGNORECASE,
    )
    for match in pattern.finditer(query):
        # IDs, model numbers and IT/Ra targets are not dimensions. Require
        # a dimensional unit or an explicit object immediately before it.
        if not re.search(r"(?i)mm|毫米", match.group()) and not re.search(r"(?:内径|外径|孔径|直径|尺寸|测量范围|深度|厚度)\s*[为是:：φΦØø]?\s*$", query[:match.start()]):
            continue
        lower = _number(match.group("lower"))
        upper = _number(match.group("upper")) if match.group("upper") else lower
        if lower is None or upper is None:
            continue
        if lower > upper:
            lower, upper = upper, lower
        return lower, upper
    return None


def _query_measurement_object(query: str) -> str | None:
    for marker in ("内径", "外径", "深度", "厚度", "螺纹"):
        if marker in query:
            return marker
    return None


def _gauge_matches_query(record: dict[str, Any], dimension_range: tuple[float, float] | None, measurement_object: str | None) -> bool:
    fields = record.get("fields", {})
    if measurement_object:
        object_text = str(fields.get("测量对象") or "")
        if measurement_object not in object_text:
            return False
    if dimension_range is None:
        return True
    low = _number(fields.get("测量范围下限_mm"))
    high = _number(fields.get("测量范围上限_mm"))
    if low is None or high is None or low > high:
        return False
    requested_low, requested_high = dimension_range
    # The instrument must cover the complete requested interval, not merely
    # touch one endpoint of it.
    return low <= requested_low and high >= requested_high


def _requested_relationships(query: str) -> list[str]:
    return [
        key for key, label in RELATION_LABELS.items()
        if label in query
        or (key == "equipment" and any(
            term in query for term in ("机床", "车床", "铣床", "镗床", "磨床", "加工中心", "设备型号", "设备类别")
        ))
    ]


def _is_history_resource_query(query: str, requested_relationships: list[str]) -> bool:
    """Recognize historical process resource questions separately from capability queries."""
    return bool(requested_relationships) and any(marker in query for marker in ("历史", "历史工艺", "工序案例"))


def _is_history_catalog_query(query: str, requested_relationships: list[str]) -> bool:
    return not requested_relationships and any(marker in query for marker in HISTORY_CATALOG_MARKERS)


def _history_resource_present(fields: dict[str, Any], relationship: str) -> bool:
    key = ENTITY_RESOURCE_FIELDS[relationship]
    value = fields.get(key)
    if isinstance(value, (list, tuple, dict)):
        return bool(value)
    return value not in (None, "")


def _history_part_requested(query: str) -> bool:
    return any(marker in query for marker in ("轴套", "衬套", "套筒"))


def _requested_entity_category(query: str) -> str | None:
    """Return a directly requested master-data category, if the query is a catalog lookup."""
    # Relationship questions must stay on the capability path so that missing
    # links are reported as insufficient evidence instead of being answered by
    # an unrelated entity catalog (for example, "精铰孔适用哪些量具").
    if any(marker in query for marker in (
        "能力", "能达到", "达到", "适用", "适合", "对应", "可以用", "可用", "推荐",
        "粗糙度", "余量", "加工方法", "加工阶段", "工艺方法", "经济精度",
    )):
        return None
    if not any(marker in query for marker in ENTITY_CATALOG_MARKERS):
        return None
    if any(marker in query for marker in ("设备", "车床", "铣床", "镗床", "磨床", "加工中心")):
        return "equipment"
    if "刀具" in query or any(marker in query for marker in ("钻头", "铰刀", "镗刀", "车刀")):
        return "tool"
    if "量具" in query or any(marker in query for marker in ("卡尺", "千分尺", "内径表", "测量仪")):
        return "gauge"
    return None


def _is_capability_query(query: str, methods: list[str]) -> bool:
    markers = (
        "能力", "精度", "粗糙度", "ra", "it", "余量", "加工方法", "加工阶段", "加工方式",
        "粗加工", "半精加工", "精加工", "粗车", "半精车", "精车", "粗镗", "半精镗", "精镗",
        "适用条件", "能达到", "工艺方法",
    )
    return any(marker in query.lower() for marker in markers) or bool(methods and any(term in query for term in ("加工", "适用", "达到", "精度", "粗糙度", "方法")))


def _target_precision(query: str) -> int | None:
    match = re.search(r"(?i)(?<![a-z0-9])IT\s*(\d{1,2})(?!\d)", query)
    return int(match.group(1)) if match else None


def _target_roughness(query: str) -> float | None:
    match = re.search(r"(?i)(?<![a-z0-9])Ra\s*([0-9]+(?:\.[0-9]+)?)", query)
    return float(match.group(1)) if match else None


def _has_requested_metrics(fields: dict[str, Any], query: str) -> bool:
    """A catalog row only answers metrics actually present in its business fields."""
    keys = " ".join(str(key).lower() for key, value in fields.items() if value not in (None, "", [], {}))
    checks: list[tuple[str, ...]] = []
    if "经济精度" in query or _target_precision(query) is not None:
        checks.append(("经济精度", "精度等级"))
    elif "精度" in query:
        checks.append(("精度", "误差", "公差"))
    if "粗糙度" in query or re.search(r"(?i)(?<![a-z])ra", query):
        checks.append(("粗糙度", "ra"))
    if "余量" in query:
        checks.append(("余量",))
    return all(any(marker in keys for marker in markers) for markers in checks)


def _contains_target(record: dict[str, Any], precision: int | None, roughness: float | None) -> bool:
    fields = record.get("fields", {})
    if precision is not None:
        low, high = _number(fields.get("精度等级下限")), _number(fields.get("精度等级上限"))
        if low is None or high is None or low > high or not low <= precision <= high:
            return False
    if roughness is not None:
        low, high = _number(fields.get("Ra下限_μm")), _number(fields.get("Ra上限_μm"))
        if low is None or high is None or low > high or not low <= roughness <= high:
            return False
    return True


def _answer(items: list[dict[str, Any]]) -> str:
    counts: dict[str, int] = {}
    history_names: list[str] = []
    methods: list[str] = []
    for item in items:
        category = item["category"]
        counts[category] = counts.get(category, 0) + 1
        if category == "history" and item["title"] not in history_names:
            history_names.append(item["title"])
        elif category == "capability" and item["title"] not in methods:
            methods.append(item["title"])
    parts = [f"本地知识库检索到 {len(items)} 条相关记录。"]
    if history_names:
        parts.append("历史工艺参考：" + "；".join(history_names[:3]) + "。")
    if methods:
        parts.append("加工能力参考：" + "；".join(methods[:3]) + "。")
    other = [f"{CATEGORY_LABELS.get(category, category)} {count} 条" for category, count in counts.items() if category not in {"history", "capability"}]
    if other:
        parts.append("相关主数据：" + "、".join(other) + "。")
    parts.append("历史案例仅代表样本记录；能力表数据为手册整理参考，需结合企业现场条件确认。")
    return "".join(parts)


def _resource_summary(records: list[dict[str, Any]], relationships: list[str]) -> dict[str, Any]:
    """Aggregate resources across all matching historical operations, beyond visible top_k cards."""
    summary: dict[str, Any] = {
        "scope": "history",
        "record_count": len(records),
    }
    for relationship in relationships:
        values: dict[tuple[str, str], dict[str, Any]] = {}
        field_name = ENTITY_RESOURCE_FIELDS[relationship]
        for record in records:
            fields = record.get("fields", {})
            raw_values = fields.get(field_name) or []
            if not isinstance(raw_values, (list, tuple)):
                raw_values = [raw_values]
            source_ref = _record_source(record)
            for raw_value in raw_values:
                if isinstance(raw_value, dict):
                    name = str(raw_value.get(f"{field_name}名称") or raw_value.get("名称") or raw_value.get("name") or "").strip()
                    model = str(raw_value.get(f"{field_name}型号") or raw_value.get("型号") or raw_value.get("model") or "").strip()
                    if not name and model:
                        name = model
                else:
                    name, model = str(raw_value).strip(), ""
                if not name and not model:
                    continue
                key = (name.casefold(), model.casefold())
                entry = values.setdefault(key, {"name": name or model, "model": model or None, "count": 0, "sources": []})
                entry["count"] += 1
                if source_ref not in entry["sources"]:
                    entry["sources"].append(source_ref)
        entries = sorted(values.values(), key=lambda item: (-item["count"], str(item["name"]), str(item.get("model") or "")))
        summary[relationship] = entries
        summary[f"{relationship}_count"] = len(entries)
    return summary


def _catalog_summary(records: list[dict[str, Any]], category: str) -> dict[str, Any]:
    """Summarize a master-data lookup without limiting it to the evidence card top_k."""
    id_field = ENTITY_ID_FIELDS[category]
    name_field = {"equipment": "设备名称", "tool": "刀具名称", "gauge": "量具名称"}[category]
    entries_by_key: dict[tuple[str, str, str], dict[str, Any]] = {}
    for record in records:
        fields = record.get("fields", {})
        name = str(fields.get(name_field) or record.get("title") or "本地记录")
        model = str(fields.get("设备型号") or fields.get("型号或规格") or "")
        # Identical source rows are duplicated in the extracted demo JSON.
        # Preserve distinct parameter variants while collapsing exact repeats.
        metadata_keys = {id_field, "来源文件", "来源工作表", "来源行号", "来源单元格范围", "证据来源", "备注", "数据状态"}
        variant = json.dumps({key: value for key, value in fields.items() if key not in metadata_keys}, ensure_ascii=False, sort_keys=True, default=str)
        key = (name.casefold(), model.casefold(), variant)
        source_ref = _record_source(record)
        entry = entries_by_key.setdefault(key, {
            "id": str(fields.get(id_field) or record.get("id") or "") or None,
            "name": name,
            "model": model or None,
            "count": 0,
            "sources": [],
            "fields": _entity_summary(record)["fields"],
            "data_warnings": _record_warnings(record),
        })
        entry["count"] += 1
        if source_ref not in entry["sources"]:
            entry["sources"].append(source_ref)
    entries = sorted(entries_by_key.values(), key=lambda item: (str(item["name"]), str(item.get("model") or "")))
    return {
        "scope": "catalog",
        "record_count": len(records),
        "unique_count": len(entries),
        f"{category}_count": len(entries),
        category: entries,
    }


def _history_catalog_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    entries = []
    for record in records:
        entries.append({
            "id": str(record.get("id") or "") or None,
            "name": str(record.get("title") or "历史工艺记录"),
            "model": None,
            "count": 1,
            "sources": [_record_source(record)],
        })
    return {
        "scope": "catalog",
        "record_count": len(records),
        "unique_count": len(entries),
        "history_count": len(entries),
        "history": entries,
    }


def _is_history_route_query(query: str, records: tuple[dict[str, Any], ...]) -> bool:
    route_markers = ("工艺路线", "加工路线", "工序路线", "工序顺序", "加工顺序", "工序流程", "全部工序", "完整工艺")
    return any(marker in query for marker in route_markers) and (
        "历史" in query or _history_part_requested(query)
        or bool(IDENTIFIER_RE.search(query)) or not _is_capability_query(query, _query_methods(query, records))
    )


def _search_history_routes(query: str, records: tuple[dict[str, Any], ...], top_k: int) -> dict[str, Any]:
    """Retrieve whole source cases atomically; top_k limits cases, never operations."""
    groups: dict[tuple[str, ...], list[dict[str, Any]]] = {}
    for record in records:
        if record.get("category") != "history":
            continue
        fields = record.get("fields", {})
        key = tuple(str(value or "") for value in (
            record.get("source", {}).get("document_name"), fields.get("零件编号"),
            fields.get("工艺规程编号"), fields.get("版本"),
        ))
        groups.setdefault(key, []).append(record)
    names = {str(group[0].get("fields", {}).get("零件名称") or "") for group in groups.values()}
    matched_names = [name for name in names if name and re.search(re.escape(name) + r"(?![0-9]|衬套|轴套|套筒)", query)]
    # A shorter part name can be a substring of another part's full name.
    matched_names = [name for name in matched_names if not any(name != other and name in other for other in matched_names)]
    identifiers = [identifier.casefold() for identifier in IDENTIFIER_RE.findall(query)
                   if not re.fullmatch(r"(?i)(?:it\d{1,2}|ra\d+(?:\.\d+)?)", identifier)]
    identifiers.extend(re.findall(r"(?<![\w.])\d{4,}(?![\w.])", query))
    materials = _query_materials(query)
    requested_parts = re.findall(r"[\u3400-\u9fff]*(?:轴套|衬套|套筒)\d*", query)
    unknown_part = False
    for part in requested_parts:
        if matched_names:
            break
        prefix = re.sub(r"(?:轴套|衬套|套筒)\d*$", "", part)
        for word in (*MATERIAL_TERMS, "请问", "请", "查询", "查找", "历史", "关于", "某个", "某", "类", "零件", "的", "一个", "所有", "全部", "这些", "这个", "中"):
            prefix = prefix.replace(word, "")
        unknown_part = unknown_part or bool(prefix)
    version_match = re.search(r"(?i)(?:版本\s*[:：]?\s*([a-z]\d*)|([a-z]\d*)\s*版本)", query)
    version = next((value for value in version_match.groups() if value), "") if version_match else ""
    operation_names = {str(record.get("fields", {}).get("工序名称") or "") for group in groups.values() for record in group}
    requested_operations = [name for name in operation_names if name and name in query]
    requested_operations = [name for name in requested_operations if not any(name != other and name in other for other in requested_operations)]
    excluded_operations = [name for name in requested_operations if re.search(r"(?:不含|不包含|不包括|没有|不经过|无需|排除)\s*" + re.escape(name), query)]
    requested_operations = [name for name in requested_operations if name not in excluded_operations]
    relationships = _requested_relationships(query)
    terms = _search_terms(query)
    candidates = []
    for key, group in groups.items():
        if unknown_part:
            continue
        fields = group[0].get("fields", {})
        part_name = str(fields.get("零件名称") or "")
        if matched_names and part_name not in matched_names:
            continue
        if not matched_names and _history_part_requested(query) and not any(
            marker in part_name for marker in ("轴套", "衬套", "套筒")
        ):
            continue
        if materials and str(fields.get("材料") or "") not in materials:
            continue
        if version and str(fields.get("版本") or "").casefold() != version.casefold():
            continue
        group_operations = {str(record.get("fields", {}).get("工序名称") or "") for record in group}
        if requested_operations and not all(name in group_operations for name in requested_operations):
            continue
        if any(name in group_operations for name in excluded_operations):
            continue
        text = _flatten([record.get("fields", {}) for record in group]).casefold()
        if identifiers and not all(identifier in text for identifier in identifiers):
            continue
        score = sum(5.0 if re.search(r"[a-z0-9]", term) else 1.0 for term in terms if term in text)
        if not score and not any(marker in query for marker in ("历史", "全部工序", "工艺路线", "工序流程")):
            continue
        candidates.append((score, key, group))
    candidates.sort(key=lambda candidate: (-candidate[0], candidate[1]))
    items = []
    for score, key, group in candidates[:top_k]:
        # Numeric operation numbers carry the source order in this dataset.
        # Preserve source array order for ambiguous/composite/missing numbers.
        numbers = [str(record.get("fields", {}).get("工序号", "")) for record in group]
        ordered = sorted(group, key=lambda record: int(record["fields"]["工序号"])) if (
            all(number.isdecimal() for number in numbers) and len(set(numbers)) == len(numbers)
        ) else group
        fields = ordered[0].get("fields", {})
        operations = [{
            "id": str(record.get("id") or ""),
            "number": str(record.get("fields", {}).get("工序号", "")),
            "name": str(record.get("fields", {}).get("工序名称") or "未提供工序名"),
            "source": _record_source(record),
            **{relation: record.get("fields", {}).get(ENTITY_RESOURCE_FIELDS[relation]) or [] for relation in relationships},
        } for record in ordered]
        route = {
            "part_id": str(fields.get("零件编号") or ""),
            "part_name": str(fields.get("零件名称") or ""),
            "material": str(fields.get("材料") or ""),
            "process_id": str(fields.get("工艺规程编号") or ""),
            "version": str(fields.get("版本") or ""),
            "operation_count": len(operations),
            "operations": operations,
        }
        chain = " → ".join(f"{operation['number']} {operation['name']}" for operation in operations)
        resource_text = "\n".join(
            f"工序{op['number']} {op['name']}：" + "；".join(f"{RELATION_LABELS[relation]}：{_format_value(op[relation])}" for relation in relationships)
            for op in operations
        ) if relationships else ""
        source = _record_source(ordered[0])
        source["identity"] = f"{route['part_id']} / {route['process_id']} / 版本{route['version']} / 全部{len(operations)}道工序"
        items.append({
            "id": "history-route:" + json.dumps(key, ensure_ascii=False, separators=(",", ":")),
            "category": "history", "title": f"{route['part_name']} · {route['part_id']} · 工艺路线（版本{route['version']}）",
            "score": score, "retrieval_method": "local_keyword_route", "source": source, "route": route,
            "content": (
                f"零件编号：{route['part_id']}\n零件名称：{route['part_name']}\n材料：{route['material']}\n"
                f"工艺规程编号：{route['process_id']}\n版本：{route['version']}\n"
                f"样例文件全部工序（共{len(operations)}道，按原工序号排列；编号间隔不代表缺失）：\n{chain}"
                + (f"\n工序直接资源记录（空列表表示样例未提供）：\n{resource_text}" if resource_text else "")
            ),
        })
    gaps = [relation for relation in relationships if items and not all(
        any(op.get(relation) for op in item["route"]["operations"]) for item in items
    )]
    target_requested = _target_precision(query) is not None or _target_roughness(query) is not None
    return {
        "status": "insufficient_evidence" if gaps or target_requested else "ok",
        "intent": "history_route", "items": items, "relationship_gaps": gaps,
        "resource_summary": None, "answer": "",
        "message": (
            "已检索历史路线，但样例库没有足够依据证明整条路线符合指定精度或粗糙度；请指定具体工序或加工特征查询能力。" if target_requested
            else "已检索历史路线，但样例库未提供所请求的完整资源关联：" + "、".join(RELATION_LABELS[key] for key in gaps) + "。" if gaps
            else "" if items else "本地样例数据中没有找到符合条件的历史工艺路线，没有足够依据生成路线。"
        ),
    }


def _select_evidence(
    ranked: list[tuple[float, dict[str, Any]]],
    top_k: int,
    indexes: dict[str, dict[str, dict[str, Any]]],
    *,
    methods: list[str],
    features: list[str],
    stages: list[str],
    requested_relationships: list[str],
    capability_query: bool,
) -> list[dict[str, Any]]:
    candidates = [_to_item(record, round(score, 3), indexes) for score, record in ranked]
    selected: list[dict[str, Any]] = []
    if capability_query:
        groups = []
        groups.extend([item for item in candidates if item.get("relationships", {}).get(relation, {}).get("status") in {"linked", "category_hint"}] for relation in requested_relationships)
        if len(methods) > 1:
            groups.extend([item for item in candidates if item.get("capability", {}).get("method") == method] for method in methods)
        if len(features) > 1:
            groups.extend([item for item in candidates if _feature_matches(item.get("capability", {}).get("feature"), feature)] for feature in features)
        if len(stages) > 1:
            groups.extend([item for item in candidates if _stage_matches(item.get("capability", {}).get("stage"), [stage])] for stage in stages)
        for group in groups:
            if group and not any(item in group for item in selected):
                selected.append(group[0])
    for item in candidates:
        if len(selected) >= top_k:
            break
        if item not in selected:
            selected.append(item)
    # A small top_k remains a hard limit. Missing requested relationships are
    # evaluated from this exact list before the model can be called.
    return selected[:top_k]


def search_local_knowledge(query: str, top_k: int = 8) -> dict[str, Any]:
    normalized_query = query.strip().lower()
    records = _load_records()
    guidance_result = search_guidance(query, records, top_k, lambda record, score: _to_item(record, score, {}))
    if guidance_result is not None:
        return guidance_result
    # Word evidence is intentionally routed above, rather than mixing generic
    # family words into historic/capability/catalog keyword results.
    records = tuple(record for record in records if record.get("category") not in {"process_guidance", "typical_route"})
    if _is_history_route_query(query, records):
        return _search_history_routes(query, records, top_k)
    terms = _search_terms(query)
    identifiers = [
        identifier.lower()
        for identifier in IDENTIFIER_RE.findall(query)
        if not re.fullmatch(r"(?i)it\d{1,2}", identifier)
        and not re.fullmatch(r"(?i)ra\d+(?:\.\d+)?", identifier)
    ]
    methods = _query_methods(query, records)
    features = _query_features(query)
    stages = _query_stages(query)
    materials = _query_materials(query)
    dimension_range = _query_dimension_range(query)
    measurement_object = _query_measurement_object(query)
    precision_target = _target_precision(query)
    roughness_target = _target_roughness(query)
    capability_id_query = any(
        record.get("category") == "capability"
        and str(record.get("fields", {}).get("能力ID") or record.get("id") or "").lower() in identifiers
        for record in records
    )
    capability_query = capability_id_query or _is_capability_query(query, methods)
    named_entities = {category: _entity_query_terms(query, records, category) for category in ENTITY_ID_FIELDS}
    identified_entities = {
        category: [
            record for record in records
            if identifiers and record.get("category") == category
            and all(any(identifier in str(record.get("fields", {}).get(key) or "").lower() for key in (id_field, "设备型号", "型号或规格")) for identifier in identifiers)
        ]
        for category, id_field in ENTITY_ID_FIELDS.items()
    }
    requested_relationships = _requested_relationships(query)
    requested_relationships.extend(category for category, names in named_entities.items() if (names or identified_entities[category]) and category not in requested_relationships)
    history_resource_query = _is_history_resource_query(query, requested_relationships)
    history_catalog_query = _is_history_catalog_query(query, requested_relationships)
    entity_category = None if capability_id_query or history_resource_query or history_catalog_query else _requested_entity_category(query)
    if (
        not capability_id_query and not history_resource_query and not history_catalog_query
        and named_entities["tool"] and not methods
        and not any(marker in query.lower() for marker in ("能力", "精度", "粗糙度", "余量", "达到", "阶段", "ra", "it"))
        and re.search(r"适用.*方法|(?:哪些|什么|哪种)(?:加工)?方法", query)
        and all(relation == "tool" for relation in requested_relationships)
    ):
        entity_category = "tool"
    if not entity_category and not history_resource_query and not history_catalog_query and identifiers and not methods and precision_target is None and roughness_target is None:
        # A model's own technical parameters are direct evidence; they do not
        # require inventing a link to an unrelated generic capability row.
        for category, matching_records in identified_entities.items():
            if matching_records and all(_has_requested_metrics(record.get("fields", {}), query) for record in matching_records) and not any(relation != category for relation in requested_relationships):
                entity_category = category
                break
    if entity_category and capability_query:
        direct_candidates = identified_entities[entity_category] or [
            record for record in records if record.get("category") == entity_category
            and (not named_entities[entity_category] or any(name in _flatten(record.get("fields", {})) for name in named_entities[entity_category]))
        ]
        if not any(_has_requested_metrics(record.get("fields", {}), query) for record in direct_candidates):
            entity_category = None
    entity_terms = named_entities[entity_category] if entity_category else []
    equipment_terms = named_entities["equipment"]
    missing_specific_equipment = bool(
        capability_query
        and "equipment" in requested_relationships
        and not identifiers
        and not equipment_terms
        and (any(marker in query for marker in ("具体设备", "某设备", "这台设备", "这个设备", "指定设备")) or re.match(r"^设备(?:能达到|可以达到)", query))
    )
    indexes = {
        "equipment": _entity_index(records, "equipment", "设备ID"),
        "tool": _entity_index(records, "tool", "刀具ID"),
        "gauge": _entity_index(records, "gauge", "量具ID"),
    }
    ranked = []
    for record in records:
        if history_resource_query and record.get("category") != "history":
            continue
        if history_catalog_query and record.get("category") != "history":
            continue
        if entity_category and record.get("category") != entity_category:
            continue
        if entity_category and capability_query and not _has_requested_metrics(record.get("fields", {}), query):
            continue
        # Capability questions must be answered by capability rows. Other
        # categories can contain the same words (for example, "量具" in a
        # historical operation), but cannot establish a capability relation.
        if (
            capability_query
            and not entity_category
            and not history_resource_query
            and not history_catalog_query
            and record.get("category") != "capability"
        ):
            continue
        if entity_category == "gauge" and not _gauge_matches_query(record, dimension_range, measurement_object):
            continue
        searchable = f"{record.get('title', '')} {_flatten(record.get('fields', {}))}".lower()
        if entity_terms and not any(term.lower() in searchable for term in entity_terms):
            continue
        if history_resource_query and _history_part_requested(query) and not any(
            marker in searchable for marker in ("轴套", "衬套", "套筒")
        ):
            continue
        if history_resource_query and any(
            names and not any(name.lower() in _flatten(record.get("fields", {}).get(ENTITY_RESOURCE_FIELDS[relation])).lower() for name in names)
            for relation, names in named_entities.items()
        ):
            continue
        identifier_text = searchable
        if record.get("category") == "capability" and identifiers:
            fields = record.get("fields", {})
            for category, id_field in ENTITY_ID_FIELDS.items():
                identifier_text += " " + " ".join(
                    _flatten(indexes[category][reference].get("fields", {})).lower()
                    for reference in _reference_values(fields.get(f"关联{id_field}")) if reference in indexes[category]
                )
        if identifiers and not all(identifier in identifier_text for identifier in identifiers):
            continue
        if capability_query and record.get("category") == "capability":
            if materials and str(record.get("fields", {}).get("工件材料") or "") not in materials:
                continue
            if precision_target is not None or roughness_target is not None:
                if not _contains_target(record, precision_target, roughness_target):
                    continue
            record_methods = str(record.get("fields", {}).get("加工方法") or "")
            if methods and record_methods not in methods:
                continue
            if features and record.get("fields", {}).get("加工特征") and not any(_feature_matches(record["fields"].get("加工特征"), feature) for feature in features):
                continue
            if stages and not _stage_matches(record.get("fields", {}).get("加工阶段"), stages):
                continue
        matched = [term for term in terms if term in searchable]
        if not matched and not history_catalog_query:
            continue
        if history_catalog_query and not matched:
            matched = ["历史案例"]
        score = sum(5.0 if re.search(r"[a-z0-9]", term) else 1.0 for term in matched)
        score += 1.0 if normalized_query in searchable else 0.0
        fields = record.get("fields", {})
        if record.get("category") == "capability":
            if methods and str(fields.get("加工方法") or "") in methods:
                score += 12.0
            if features and any(_feature_matches(fields.get("加工特征"), feature) for feature in features):
                score += 5.0
            if precision_target is not None or roughness_target is not None:
                score += 6.0
            if requested_relationships and any(
                _relationship(fields, relation_name=key, id_key=f"关联{'设备' if key == 'equipment' else '刀具' if key == 'tool' else '量具'}ID", text_keys=(("设备名称或类别",) if key == "equipment" else ("刀具类别",) if key == "tool" else ("量具名称或类别", "量具类别")), index=indexes[key])["status"] in {"linked", "category_hint"}
                for key in requested_relationships
            ):
                score += 4.0
        if record.get("category") == "history" and any(term in searchable for term in ("零件名称", "工序名称")):
            score += 0.15
        if history_resource_query and record.get("category") == "history":
            resource_hits = sum(_history_resource_present(record.get("fields", {}), relation) for relation in requested_relationships)
            score += resource_hits * 8.0
            if resource_hits == len(requested_relationships):
                score += 8.0
            else:
                score -= (len(requested_relationships) - resource_hits) * 3.0
        ranked.append((score, record))
    ranked.sort(key=lambda pair: (-pair[0], str(pair[1].get("id", ""))))
    capability_context = capability_query and not entity_category and not history_resource_query and not history_catalog_query
    mismatched_relationships: set[str] = set()
    if capability_context:
        for relation in requested_relationships:
            if not named_entities[relation]:
                continue
            related = [
                (score, record) for score, record in ranked
                if any(term.lower() in _flatten(_to_item(record, score, indexes).get("relationships", {}).get(relation, {})).lower() for term in named_entities[relation])
            ]
            if related:
                ranked = related
            else:
                mismatched_relationships.add(relation)
    items = _select_evidence(ranked, top_k, indexes, methods=methods, features=features, stages=stages, requested_relationships=requested_relationships, capability_query=capability_context)
    if not items:
        missing_links = [relation for relation in requested_relationships if capability_context and identified_entities[relation]]
        return {
            "status": "insufficient_evidence" if missing_links else "ok",
            "message": "样例库未提供指定对象与所查询加工能力的明确关联。" if missing_links else "本地样例数据中没有找到相关记录，请换材料牌号、零件名称或加工特征再试。",
            "answer": "",
            "items": [],
            "intent": "history" if history_catalog_query or history_resource_query else entity_category or ("capability" if capability_query else "general"),
            "relationship_gaps": missing_links,
        }
    gaps: list[str] = []
    if history_resource_query:
        selected_ids = {item["id"] for item in items}
        visible_records = [record for _, record in ranked if str(record.get("id")) in selected_ids]
        gaps.extend(relation for relation in requested_relationships if not any(_history_resource_present(record.get("fields", {}), relation) for record in visible_records))
    if requested_relationships and capability_context:
        # Only evidence actually sent to the model can justify its answer.
        capability_items = [item for item in items if item["category"] == "capability"]
        for relation in requested_relationships:
            statuses = {item.get("relationships", {}).get(relation, {}).get("status") for item in capability_items}
            if relation in mismatched_relationships or not capability_items or not statuses or statuses.issubset({"not_provided"}):
                gaps.append(relation)
    if missing_specific_equipment and capability_context and "equipment" not in gaps:
        gaps.append("equipment")
    return {
        "status": "insufficient_evidence" if gaps else "ok",
        "message": "样例库没有足够依据支持所请求的关联：" + "、".join(RELATION_LABELS[key] for key in gaps) + "。" if gaps else "",
        "answer": "" if gaps else _answer(items),
        "items": items,
        "intent": "history" if history_catalog_query or history_resource_query else entity_category or ("capability" if capability_query else "general"),
        "relationship_gaps": gaps,
        "resource_summary": (
            _resource_summary([record for _, record in ranked], requested_relationships)
            if history_resource_query
            else _history_catalog_summary([record for _, record in ranked])
            if history_catalog_query
            else _catalog_summary([record for _, record in ranked], entity_category)
            if entity_category
            else None
        ),
    }
