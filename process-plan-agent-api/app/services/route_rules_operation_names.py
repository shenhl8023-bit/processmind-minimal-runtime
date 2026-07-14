"""
工序名称标准化与名称级别的纯规则辅助。
"""

from __future__ import annotations

import re


INVALID_OP_TOKENS = (
    "产品型号", "零组件号", "零组件名称", "材料牌号", "材料标准", "毛坯类型",
    "工艺名称", "工艺规程", "工艺版次", "设计版次", "编制", "校对", "审核",
    "批准", "会签", "单位", "总页数", "编号", "备注", "设备", "工艺装备",
    "刀具图号", "量具图号", "名称型号", "夹具图号", "共", "第", "初样",
    "车削中心", "数控车床", "台钻", "珩磨机", "铰刀", "研磨膏",
    "工序卡片", "样板", "塞规", "塞尺", "环规", "量块",
    "车间", "工装", "工具", "拉杆", "夹块", "底座", "接嘴", "丝堵",
)

PROCESS_HINTS = (
    "备料", "下料", "锻", "车", "铣", "钻", "镗", "铰", "攻", "拉", "插", "磨", "研",
    "抛", "滚", "校", "清洗", "去毛刺", "检验", "检查", "探伤", "淬火",
    "回火", "调质", "热处理", "去应力", "装配", "装", "割", "焊", "刻",
    "打标", "倒角", "镀铜", "渗氮", "滲氮", "除铜", "氰化", "阳极化", "钝化",
)

INVALID_SENTENCE_TOKENS = (
    "使用", "允许", "不得", "进行", "指导", "零件", "表面", "自动清洗机",
    "冷光源", "比样块", "光洁", "干燥", "交接", "箭示", "试样件",
    "可参照", "改为", "目视检查", "槽深尺寸", "记录时间精确到分钟",
)

KNOWN_OPERATION_NAMES = (
    "备料", "下料", "调质", "去应力", "去毛刺", "清洗", "检验", "外观检查", "尺寸检查",
    "真空淬火", "车零件", "车外形", "磨孔", "磨外圆", "精车外圆", "粗车外圆", "车倒角",
    "孔口倒角", "攻螺纹", "钻镗孔", "钻铰孔", "铣扁", "倒角", "倒角,倒圆", "抛光", "刻线",
    "车外圆", "车端面", "平端面", "钻孔", "镗孔", "铣槽", "车槽", "割型孔",
    "磨端面", "研孔", "研外圆", "磁粉检查", "烧伤检查", "镀铜", "渗氮", "除铜", "氰化",
    "铬酸阳极化", "硬质阳极化", "钝化",
    "裂纹检查", "荧光检查", "包装", "标印", "淬火", "正常化", "真空淬火", "无心磨",
    "导管配套", "除油", "阿洛丁", "导管镶装", "总检", "喷漆", "导管清洗",
    "气密试验", "吹干", "试验",
    "管材下料", "数控弯曲", "切割", "数控下料", "冲压成形", "钣金成形",
    "开工前准备", "倒毛刺", "均质检验", "最终检验", "称重",
)

OPERATION_NORMALIZATION_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"^备料(准备)?$"), "备料"),
    (re.compile(r"^按图下料.*$"), "下料"),
    (re.compile(r"^下料[Φ⌀].*$"), "下料"),
    (re.compile(r"^(外观)?检验$"), "检验"),
    (re.compile(r"^外观检验$"), "外观检查"),
    (re.compile(r"^尺寸检验$"), "检验"),
    (re.compile(r"^磁粉检验$"), "磁粉检查"),
    (re.compile(r"^烧伤检验$"), "烧伤检查"),
    (re.compile(r"^裂纹检验$"), "裂纹检查"),
    (re.compile(r"^荧光检验$"), "荧光检查"),
    (re.compile(r"^真空淬火(处理)?$"), "真空淬火"),
    (re.compile(r"^调质(处理)?$"), "调质"),
    (re.compile(r"^去应力(处理|退火)?$"), "去应力"),
    (re.compile(r"^镀铜(处理)?$"), "镀铜"),
    (re.compile(r"^(渗氮|滲氮)(处理)?$"), "渗氮"),
    (re.compile(r"^氰化(处理)?$"), "氰化"),
    (re.compile(r"^除铜(处理)?$"), "除铜"),
    (re.compile(r"^铬酸阳极化(处理)?$"), "铬酸阳极化"),
    (re.compile(r"^硬质阳极化(处理)?$"), "硬质阳极化"),
    (re.compile(r"^钝化(处理)?$"), "钝化"),
    (re.compile(r"^清洗(处理)?$"), "清洗"),
    (re.compile(r"^多功能清洗$"), "清洗"),
    (re.compile(r"^去毛刺(处理)?$"), "去毛刺"),
    (re.compile(r"^标记$"), "标印"),
    (re.compile(r"^标引$"), "标印"),
    (re.compile(r"^打标$"), "标印"),
    (re.compile(r"^钻[、,/／]?铰孔$"), "钻铰孔"),
    (re.compile(r"^钻铰(孔)?$"), "钻铰孔"),
    (re.compile(r"^钻[、,/／]?镗孔$"), "钻镗孔"),
    (re.compile(r"^钻镗孔.*$"), "钻镗孔"),
    (re.compile(r"^钻铰孔.*$"), "钻铰孔"),
    (re.compile(r"^攻螺纹.*$"), "攻螺纹"),
    (re.compile(r"^倒角[、,，/]?倒圆$"), "倒角"),
    (re.compile(r"^磨外$"), "磨外圆"),
    (re.compile(r"^.*内圆磨.*$"), "磨孔"),
    (re.compile(r"^(数控)?外圆磨.*$"), "磨外圆"),
    (re.compile(r"^(数控)?无心磨.*$"), "磨外圆"),
    (re.compile(r"^.*外圆磨.*$"), "磨外圆"),
    (re.compile(r"^磨孔(加工)?$"), "磨孔"),
]

INVALID_OPERATION_EXACT = {
    "清洗槽",
    "技术要求",
    "程序编号",
    "车间",
    "工装",
    "工具",
    "拉杆",
    "夹块",
    "底座",
    "接嘴",
    "丝堵",
}

INVALID_OPERATION_CONTAINS = (
    "工序号前车间由",
    "导管及接头滚波制造可参照",
    "改为“目视检查管内槽深",
    "改为目视检查管内槽深",
    "条执行钝化",
    "实际切割参数记录下表",
    "切口和无切割残留物",
    "模具切割线公差",
)

GENERAL_MAIN_OPERATION_NAMES = {
    "下料", "车外圆", "车端面", "去毛刺", "清洗", "检验",
}

ASSEMBLY_ROUTE_SEQUENCE_HINTS = {
    "导管配套": 10,
    "除油": 20,
    "阿洛丁": 30,
    "导管镶装": 40,
    "气密试验": 50,
    "试验": 50,
    "总检": 60,
    "导管清洗": 70,
    "吹干": 80,
    "喷漆": 90,
}

EQUIPMENT_NAME_TOKENS = (
    "车床", "磨床", "铣床", "钻床", "镗床", "加工中心",
    "打标机", "机床", "机组", "设备", "线切割",
)

EQUIPMENT_NAME_EXACT = {
    "数控车床", "激光打标机", "数控磨床", "数控铣床", "加工中心",
    "数控车", "万能铣", "检验台", "检验心棒", "检验工序卡片",
    "研磨器", "研磨套", "研磨机", "研磨杆", "研磨车头",
    "多功能清洗机", "水基型封闭式多功能清洗机", "能清洗机",
    "钻攻中心", "小型钻孔中心TC－", "小型钻铣中心TC－", "内外圆研磨机",
    "慢走丝线切割", "数控线切割", "数控电火花线切割", "电火花线切割", "线切割",
    "工装", "工具", "拉杆", "夹块", "胀形用底座", "打压接嘴", "打压丝堵", "试验器",
}


def _clean_text_line(line: str) -> str:
    return re.sub(r"\s+", "", line or "").strip()


def _looks_like_equipment_name(text: str) -> bool:
    text = _clean_text_line(text)
    if not text:
        return False
    if text in EQUIPMENT_NAME_EXACT:
        return True
    if text.endswith("研磨机"):
        return True
    if "中心TC" in text:
        return True
    if text.endswith("中心") and "中心孔" not in text:
        return True
    if any(token in text for token in EQUIPMENT_NAME_TOKENS):
        operation_tokens = (
            "下料", "调质", "淬火", "清洗", "去毛刺", "检验", "检查", "倒角", "钻孔",
            "镗孔", "铰孔", "铣槽", "铣扁", "磨外圆", "磨孔", "车端面", "车外圆", "车外形",
        )
        if not any(token in text for token in operation_tokens):
            return True
    return False


def _contains_any(text: str, hints: tuple[str, ...]) -> bool:
    return any(hint in text for hint in hints)


def _normalize_operation_name(name: str) -> str:
    name = _clean_text_line(name)
    name = name.strip("：:;；，,。./")
    name = name.replace("／", "/")
    name = re.sub(r"[、,，/]+", "", name) if name in {"钻、铰孔", "钻/铰孔", "钻，铰孔", "钻／铰孔"} else name
    for pattern, normalized in OPERATION_NORMALIZATION_RULES:
        if pattern.fullmatch(name):
            return normalized
    return name


def _looks_like_operation_name(text: str) -> bool:
    text = _clean_text_line(text)
    if not text or len(text) < 2 or len(text) > 12:
        return False
    if text in INVALID_OPERATION_EXACT:
        return False
    if any(token in text for token in INVALID_OPERATION_CONTAINS):
        return False
    if text.startswith("名称") or text.startswith("工序名称"):
        return False
    if _looks_like_equipment_name(text):
        return False
    if any(token in text for token in INVALID_OP_TOKENS):
        return False
    if any(token in text for token in INVALID_SENTENCE_TOKENS) and text not in KNOWN_OPERATION_NAMES:
        return False
    if re.search(r"[,，]", text) and text not in KNOWN_OPERATION_NAMES:
        return False
    if any(token in text for token in ("保证", "总长", "程序编号", "定位基准", "技术要求", "粗糙度")):
        return False
    if "尺寸" in text and text != "尺寸检查":
        return False
    if re.search(r"\d", text):
        return False
    if re.search(r"[()（）<>《》[\]{}]", text):
        return False
    if re.fullmatch(r"[A-Za-z0-9/()._-]+", text):
        return False
    if not bool(re.search(r"[\u4e00-\u9fff]", text)):
        return False
    if text in KNOWN_OPERATION_NAMES:
        return True
    if _segment_concatenated_operation_names(text):
        return False
    if text.startswith("检验") and text not in {"检验", "外观检查", "尺寸检查"}:
        return False
    if text.startswith("研磨") and text not in {"研孔", "研外圆", "研顶尖", "研顶尖孔"}:
        return False
    if any(text.endswith(suffix) for suffix in ("底座", "拉杆", "夹块", "接嘴", "丝堵")):
        return False
    if any(text.endswith(suffix) and text != suffix for suffix in ("去毛刺", "清洗", "检验", "检查")):
        return False
    if _contains_any(text, PROCESS_HINTS):
        return True
    if text.endswith(("划线", "探伤", "抛光", "打磨", "倒角", "圆角", "端面", "中心孔", "标识", "检验")):
        return True
    return False


def _split_source_names(source: str | None) -> list[str]:
    if not source:
        return []
    parts = [
        item.strip()
        for item in re.split(r"[;,；，\n]+", source)
        if item and item.strip()
    ]
    return list(dict.fromkeys(parts))


def _is_repeatable_operation_name(name: str) -> bool:
    normalized = _normalize_operation_name(name or "")
    return any(token in normalized for token in ("检验", "清洗", "去毛刺"))


def _infer_operation_chain(name: str, description: str = "") -> str:
    del description
    text = (name or "").lower()
    if any(token in text for token in ("淬火", "调质", "正常化", "回火", "热处理", "去应力", "渗氮", "氰化", "镀铜", "除铜", "阳极化", "钝化")):
        return "heat"
    if any(token in text for token in ("磁粉", "烧伤", "外观检查", "检验", "探伤")):
        return "inspection"
    if any(token in text for token in ("磨孔", "研孔", "钻孔", "镗孔", "钻铰孔", "攻螺纹", "通孔", "孔")):
        return "hole"
    if any(token in text for token in ("铣扁", "铣槽", "花键", "键槽", "铣", "槽", "扁")):
        return "feature"
    if any(token in text for token in ("清洗", "去毛刺", "包装", "标印", "倒角", "倒圆", "锐边")):
        return "release"
    if any(token in text for token in ("磨外圆", "车外形", "车零件", "磨外", "精车", "粗车", "外圆", "下料", "备料")):
        return "shape"
    return "other"


def _preserve_sequence_slot(name: str, seq: int | str | None = 0) -> bool:
    normalized = _normalize_operation_name(name or "")
    seq_num = int(seq or 0)
    if not normalized or seq_num <= 0:
        return False
    if _is_repeatable_operation_name(normalized):
        return True
    return _infer_operation_chain(normalized, "") in {"shape", "hole", "feature"}


def _review_status_rank(status: str | None) -> int:
    normalized = (status or "pending_confirm").strip()
    if normalized == "data_issue":
        return 5
    if normalized == "exception":
        return 4
    if normalized == "evidence":
        return 3
    if normalized == "pending_confirm":
        return 2
    if normalized == "stable":
        return 1
    return 0


def _merge_serialized_operations(rows: list[dict]) -> list[dict]:
    grouped: dict[tuple[str, int], dict] = {}

    for row in rows:
        name = _normalize_operation_name(str(row.get("name") or ""))
        if not name or _looks_like_equipment_name(name):
            continue
        seq = int(row.get("sequence") or 0)
        key = (name, seq) if _preserve_sequence_slot(name, seq) else (name, 0)
        existing = grouped.get(key)
        if not existing:
            grouped[key] = dict(row)
            continue

        current = dict(existing)
        better = row
        if _review_status_rank(str(existing.get("review_status"))) > _review_status_rank(str(row.get("review_status"))):
            better = existing

        merged_factors: dict[str, dict] = {
            str(item.get("name") or ""): item
            for item in current.get("factors", [])
            if item.get("name")
        }
        for factor in row.get("factors", []):
            factor_name = str(factor.get("name") or "")
            if factor_name and factor_name not in merged_factors:
                merged_factors[factor_name] = factor
        merged_warnings: dict[str, dict] = {
            str(item.get("code") or "") + "::" + str(item.get("target") or ""): item
            for item in current.get("harness_warnings", [])
            if item.get("code")
        }
        for warning in row.get("harness_warnings", []):
            warning_key = str(warning.get("code") or "") + "::" + str(warning.get("target") or "")
            if warning_key.strip(":") and warning_key not in merged_warnings:
                merged_warnings[warning_key] = warning

        merged_sources = "；".join(sorted(set(
            _split_source_names(str(current.get("source") or "")) +
            _split_source_names(str(row.get("source") or ""))
        )))

        grouped[key] = {
            **current,
            **better,
            "name": name,
            "sequence": min(int(current.get("sequence") or 0), int(row.get("sequence") or 0)),
            "source": merged_sources,
            "factors": list(merged_factors.values()),
            "harness_warnings": list(merged_warnings.values()),
            "sample_count": max(int(current.get("sample_count") or 0), int(row.get("sample_count") or 0)),
            "coverage_count": max(int(current.get("coverage_count") or 0), int(row.get("coverage_count") or 0)),
        }

    return sorted(grouped.values(), key=lambda item: (int(item.get("sequence") or 0), str(item.get("name") or "")))


def _normalize_sequence_number(raw_seq: int | str | None) -> int:
    try:
        seq = int(raw_seq or 0)
    except Exception:
        return 0
    if seq <= 0:
        return 0
    if seq % 5 == 0 or seq % 10 == 0:
        return seq
    if seq <= 60:
        return seq * 10
    return int(round(seq / 5.0) * 5)


def _is_general_main_operation(name: str) -> bool:
    return name in GENERAL_MAIN_OPERATION_NAMES


def _operation_key(name: str, seq: int) -> tuple[str, int]:
    normalized = _normalize_operation_name(name)
    seq_num = int(seq or 0)
    return (normalized, seq_num) if _preserve_sequence_slot(normalized, seq_num) else (normalized, 0)


def _looks_like_embedded_operation_content_line(text: str) -> bool:
    raw = _clean_text_line(text)
    if not raw or all(sep not in raw for sep in ("：", ":")):
        return False

    head, tail = re.split(r"[:：]", raw, maxsplit=1)
    head_name = _normalize_operation_name(head)
    if not head_name or not _looks_like_operation_name(head_name):
        return False

    content = _clean_text_line(tail)
    if not content:
        return False

    if any(token in content for token in ("材料技术条件", "下料尺寸", "试样件", "件/根", "单件")):
        return True
    if any(token in content for token in ("⌀", "Φ", "φ", "×", "*")):
        return True

    digit_count = sum(ch.isdigit() for ch in content)
    if digit_count >= 3 and any(token in content for token in ("(", ")", "（", "）", "/")):
        return True
    return False


def _looks_like_operation_content_noise_line(text: str) -> bool:
    raw = _clean_text_line(text)
    if not raw:
        return False
    return any(token in raw for token in ("下料尺寸", "发料单", "材料技术条件", "试样件", "件/根"))


def _strip_non_operation_tail(text: str) -> str:
    raw = _clean_text_line(text)
    if not raw:
        return ""

    for token in EQUIPMENT_NAME_TOKENS:
        pos = raw.find(token)
        if pos > 0:
            raw = raw[:pos]
            break

    raw = re.sub(r"[A-Za-z0-9._-]+$", "", raw)
    return _normalize_operation_name(raw)


def _segment_concatenated_operation_names(text: str) -> list[str]:
    raw = _strip_non_operation_tail(text)
    if not raw or raw in KNOWN_OPERATION_NAMES or len(raw) > 16:
        return []

    candidates = sorted(
        {name for name in KNOWN_OPERATION_NAMES if len(name) >= 2},
        key=len,
        reverse=True,
    )
    memo: dict[int, list[str] | None] = {}

    def dfs(index: int) -> list[str] | None:
        if index == len(raw):
            return []
        if index in memo:
            return memo[index]
        for name in candidates:
            if raw.startswith(name, index):
                tail = dfs(index + len(name))
                if tail is not None:
                    memo[index] = [name, *tail]
                    return memo[index]
        memo[index] = None
        return None

    parts = dfs(0) or []
    if len(parts) >= 2 and "".join(parts) == raw:
        return parts
    return []


def _split_combined_operation_names(text: str) -> list[str]:
    raw = _clean_text_line(text)
    if not raw:
        return []
    parts = [part.strip() for part in re.split(r"[，,、/／]+", raw) if part.strip()]
    normalized_parts: list[str] = []
    for part in parts:
        normalized = _normalize_operation_name(part)
        if not normalized:
            continue
        if _looks_like_operation_name(normalized):
            normalized_parts.append(normalized)
            continue
        stripped = _strip_non_operation_tail(part)
        if stripped and _looks_like_operation_name(stripped):
            normalized_parts.append(stripped)
            continue
        for segmented in _segment_concatenated_operation_names(part):
            normalized_parts.append(segmented)
    if normalized_parts:
        return normalized_parts

    for segmented in _segment_concatenated_operation_names(raw):
        normalized_parts.append(segmented)
    return normalized_parts


def _detail_row_normalized_names(name: str) -> list[str]:
    normalized = _normalize_operation_name(name or "")
    split_names = _split_combined_operation_names(normalized)
    if split_names:
        return split_names
    return [normalized] if normalized else []


def _extract_inline_operation_names(text: str) -> list[str]:
    raw = _clean_text_line(text)
    if not raw:
        return []
    if _looks_like_embedded_operation_content_line(raw):
        return []
    if _looks_like_operation_content_noise_line(raw):
        return []

    found: list[str] = []
    for name in _split_combined_operation_names(raw):
        found.append(name)
    if found:
        return found

    stripped = _strip_non_operation_tail(raw)
    if stripped and _looks_like_operation_name(stripped):
        found.append(stripped)
        return found

    for name in sorted(KNOWN_OPERATION_NAMES, key=len, reverse=True):
        if name and raw.startswith(name):
            found.append(name)
            break
    return found


def _looks_like_sequence_break(line: str) -> bool:
    compact = _clean_text_line(line)
    if not compact:
        return False
    if re.fullmatch(r"\d{1,3}", compact):
        return True
    if re.fullmatch(r"\d{1,3}[.、]", compact):
        return True
    return False


__all__ = [
    "ASSEMBLY_ROUTE_SEQUENCE_HINTS",
    "EQUIPMENT_NAME_TOKENS",
    "GENERAL_MAIN_OPERATION_NAMES",
    "KNOWN_OPERATION_NAMES",
    "PROCESS_HINTS",
    "_clean_text_line",
    "_contains_any",
    "_detail_row_normalized_names",
    "_extract_inline_operation_names",
    "_infer_operation_chain",
    "_is_general_main_operation",
    "_is_repeatable_operation_name",
    "_looks_like_embedded_operation_content_line",
    "_looks_like_equipment_name",
    "_looks_like_operation_content_noise_line",
    "_looks_like_operation_name",
    "_looks_like_sequence_break",
    "_merge_serialized_operations",
    "_normalize_operation_name",
    "_normalize_sequence_number",
    "_operation_key",
    "_preserve_sequence_slot",
    "_review_status_rank",
    "_segment_concatenated_operation_names",
    "_split_combined_operation_names",
    "_split_source_names",
    "_strip_non_operation_tail",
]
