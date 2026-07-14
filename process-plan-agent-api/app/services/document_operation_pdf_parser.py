"""
普通 PDF 工序卡的行级与工序级抽取逻辑。
"""

from __future__ import annotations

import re
from collections.abc import Iterable

import fitz

from app.services.document_operation_detail_types import ExtractedOperationDetail, OperationRow


SIGN_KEYWORDS = ("编制", "校对", "标审", "审核", "审定", "批准", "工艺版次", "会签", "初样")
HEADER_SKIP_KEYWORDS = (
    "产品型号",
    "零组件号",
    "零组件名称",
    "材料牌号",
    "毛坯类型",
    "协作单位",
    "设备名称",
    "设备型号",
    "程序编号",
    "工序号",
    "工序名称",
    "工序",
    "名称",
    "共1页第1页",
    "共 1 页 第 1 页",
    "编号",
    "检验内容",
    "量具图号",
    "技术要求",
    "技术要",
    "技 术 要 求",
    "技 术",
    "序号",
    "硬度",
    "编 号",
    "工步",
    "加工内容",
)
ROMAN_NUMERALS = "ⅠⅡⅢⅣⅤⅥⅦⅧⅨⅩ"
EQUIPMENT_TYPE_PATTERNS = [
    "小型钻孔中心",
    "钻攻中心",
    "钻孔中心",
    "车削中心",
    "加工中心",
    "数控车床",
    "数控外圆磨床",
    "数控外圆磨",
    "半自动外圆磨",
    "外圆磨床",
    "外圆磨",
    "槽边磨床",
    "激光打标机",
    "研磨机",
    "清洗槽",
    "钳工台",
    "钻床",
    "磨床",
    "车床",
]
EQUIPMENT_STOP_KEYWORDS = (
    "程序编号",
    "工序号",
    "工序名称",
    "检验内容",
    "加工内容",
    "技术要求",
    "量具图号",
    "刀具图号",
)


def normalize_spaces(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("\u3000", " ")).strip()


def compact(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def clean_line(text: str) -> str:
    return normalize_spaces((text or "").replace("|", " "))


def unique_join(values: Iterable[str]) -> str:
    ordered: list[str] = []
    seen: set[str] = set()
    for value in values:
        cleaned = normalize_spaces(value)
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        ordered.append(cleaned)
    return "；".join(ordered)


def strip_noise_suffixes(text: str) -> str:
    cleaned = text or ""
    cleaned = re.split(r"\s技\s*\d|\s技\s*术", cleaned, maxsplit=1)[0]
    for token in (
        "标记 更改单号",
        "标记更改单号",
        "编制",
        "校对",
        "标审",
        "审核",
        "审定",
        "批准",
        "技 术 要 求",
        "技术要求",
        "技 术",
        "要 求",
        "夹具图号",
        "刀具图号",
        "量 具",
        "量具图号",
    ):
        if token in cleaned:
            cleaned = cleaned.split(token, 1)[0]
    return normalize_spaces(cleaned.strip(" ,;；"))


def chinese_char_count(text: str) -> int:
    return len(re.findall(r"[\u4e00-\u9fff]", text or ""))


def is_date_or_name_line(text: str) -> bool:
    value = compact(text)
    if not value:
        return True
    if re.fullmatch(r"[\d/\-:.]+", value):
        return True
    if re.fullmatch(r"20\d{2}[./-]\d{1,2}[./-]\d{1,2}", value):
        return True
    if any(keyword in value for keyword in SIGN_KEYWORDS):
        return True
    return False


def looks_like_dimension_noise(text: str) -> bool:
    value = compact(text)
    if not value:
        return True
    if re.fullmatch(r"[A-Za-z0-9+\-./×()（）⌀≥≤~,:：]+", value):
        return True
    if re.fullmatch(rf"[{ROMAN_NUMERALS}0-9+\-./×()（）⌀≥≤~,:：]+", value):
        return True
    return False


def normalize_equipment_type(text: str) -> str:
    value = normalize_spaces(text)
    replacements = {
        "数控外圆磨床": "数控外圆磨",
        "外圆磨床": "外圆磨",
    }
    return replacements.get(value, value)


def looks_like_program_code(text: str) -> bool:
    value = compact(text)
    if not value:
        return False
    if re.fullmatch(r"[A-Za-z0-9/_\-]+", value) and any(token in value for token in ("/", "-", "_")):
        return True
    return False


def extract_equipment_details(text: str) -> tuple[str, str]:
    lines = [clean_line(line) for line in (text or "").splitlines() if clean_line(line)]
    if not lines:
        return "", ""

    candidate_lines: list[str] = []
    header_indexes = [
        idx for idx, line in enumerate(lines)
        if "设备名称" in line or "设备型号" in line
    ]
    if header_indexes:
        start = header_indexes[0]
        for line in lines[start: min(start + 6, len(lines))]:
            if any(keyword in line for keyword in EQUIPMENT_STOP_KEYWORDS):
                continue
            candidate_lines.append(line)
    else:
        candidate_lines = lines[:8]

    equipment_types: list[str] = []
    equipment_models: list[str] = []
    pattern = "|".join(sorted((re.escape(item) for item in EQUIPMENT_TYPE_PATTERNS), key=len, reverse=True))

    for line in candidate_lines:
        inline = re.search(rf"设备名称[:：]?\s*({pattern})(?:\s+设备型号[:：]?\s*([^\s]+))?", line)
        if inline:
            equipment_types.append(normalize_equipment_type(inline.group(1)))
            model = normalize_spaces(inline.group(2) or "")
            if model and not looks_like_program_code(model):
                equipment_models.append(model)

        for match in re.finditer(rf"({pattern})(.*)", line):
            equipment_type = normalize_equipment_type(match.group(1))
            remainder = normalize_spaces(match.group(2) or "")
            if equipment_type:
                equipment_types.append(equipment_type)
            if not remainder:
                continue
            remainder = re.split(r"(程序编号|工序号|工序名称)", remainder, maxsplit=1)[0].strip(" ,;；")
            if not remainder or looks_like_program_code(remainder):
                continue
            equipment_models.append(remainder)

    return unique_join(equipment_types), unique_join(equipment_models)


def is_composite_operation_name(name: str) -> bool:
    normalized = compact(name)
    if not normalized:
        return False
    separators = [",", "，", "/", "／", "、"]
    if not any(symbol in (name or "") for symbol in separators):
        return False
    turning = any(token in normalized for token in ("车", "端面", "外形", "外圆", "切槽"))
    hole = any(token in normalized for token in ("孔", "钻", "镗", "铰", "攻螺纹"))
    return turning and hole


def detect_card_clip(page: fitz.Page) -> fitz.Rect:
    blocks = page.get_text("blocks")
    candidates: list[float] = []
    for x0, _, _, _, text, *_ in blocks:
        normalized = compact(text)
        if any(
            keyword in normalized
            for keyword in (
                "工序号",
                "工序卡片",
                "检验工序卡片",
                "协作卡片",
                "工步",
                "检验内容",
            )
        ):
            candidates.append(x0)
    if not candidates:
        return page.rect
    left = max(min(candidates) - 8, 0)
    if page.rect.width > 900 and left < page.rect.width * 0.45:
        left = page.rect.width * 0.55
    return fitz.Rect(left, 0, page.rect.width, page.rect.height)


def extract_operation_name(page: fitz.Page, clip: fitz.Rect, text: str) -> str:
    for _, y0, _, _, block_text, *_ in page.get_text("blocks", clip=clip):
        if y0 > 220:
            continue
        lines = [clean_line(line) for line in block_text.splitlines() if clean_line(line)]
        for line in lines:
            compact_line = compact(line)
            if not re.match(r"^(工\s*序\s*)?名\s*称", line):
                continue
            inline_match = re.search(r"^(?:工\s*序\s*)?名\s*称\s*[:：]?\s*(.+)$", line)
            if inline_match and compact_line not in {"名称", "工序名称"}:
                candidate = compact(inline_match.group(1))
                if candidate and not any(keyword in candidate for keyword in HEADER_SKIP_KEYWORDS):
                    return candidate
        compact_lines = [compact(line) for line in lines]
        if any(value in {"工序", "名称", "工序名称"} for value in compact_lines) and any(
            "工序" in value or value == "工序" for value in compact_lines
        ):
            for line, value in zip(reversed(lines), reversed(compact_lines)):
                if value and value not in {"工序", "名称", "工序名称"} and not any(
                    keyword in value for keyword in HEADER_SKIP_KEYWORDS
                ):
                    return value

    lines = [clean_line(line) for line in text.splitlines() if clean_line(line)]
    for idx, line in enumerate(lines):
        value = compact(line)
        if value in {"工序", "名称", "工序名称"}:
            for next_line in lines[idx + 1: idx + 6]:
                next_value = compact(next_line)
                if next_value and not any(keyword in next_value for keyword in HEADER_SKIP_KEYWORDS) and not is_date_or_name_line(next_line):
                    return next_value
    match = re.search(r"工\s*序\s*名\s*称\s*([^\n]+)", text)
    if match:
        return compact(match.group(1))
    return ""


def choose_table(page: fitz.Page, clip: fitz.Rect):
    tables = page.find_tables(clip=clip).tables
    if not tables:
        return None
    return max(tables, key=lambda table: table.row_count * table.col_count)


def normalize_row_text(raw: str) -> str:
    parts = [clean_line(part) for part in (raw or "").splitlines() if clean_line(part)]
    if not parts:
        return ""
    if re.fullmatch(r"\d+", parts[-1]):
        return f"{parts[-1]} {''.join(parts[:-1])}".strip()
    if len(parts) == 1:
        text = parts[0]
    else:
        text = "".join(parts)
    if not re.match(rf"^\s*(\d+|[{ROMAN_NUMERALS}])\b", text):
        swapped = re.match(rf"^(.*\S)\s+(\d+|[{ROMAN_NUMERALS}])$", text)
        if swapped:
            text = f"{swapped.group(2)} {swapped.group(1)}"
    return normalize_spaces(text)


def extract_standard_rows(table) -> list[tuple[str, str]]:
    rows = table.extract()
    header_idx = 0
    for idx, row in enumerate(rows):
        joined = compact("".join(cell or "" for cell in row))
        if "工步" in joined and ("加工内容" in joined or "加内容" in joined or "加工内" in joined):
            header_idx = idx
            break

    if table.col_count <= 2:
        content_cols = [0]
    else:
        header = [compact(cell or "") for cell in rows[header_idx]]
        start_col = next((i for i, cell in enumerate(header) if "工步" in cell), 0)
        end_col = next(
            (
                i for i, cell in enumerate(header[start_col + 1:], start_col + 1)
                if any(token in cell for token in ("刀具", "量具", "技术要求", "技术"))
            ),
            min(start_col + 2, table.col_count),
        )
        content_cols = list(range(start_col, max(end_col, start_col + 1)))

    items: list[tuple[str, str]] = []
    current_no = ""
    current_content = ""
    for row in rows[header_idx + 1:]:
        raw = "".join(clean_line(row[col] or "") for col in content_cols)
        text = strip_noise_suffixes(normalize_row_text(raw))
        if not text:
            continue
        if any(keyword in compact(text) for keyword in ("初样", "会签", "工艺版次")):
            continue
        match = re.match(rf"^\s*(\d+)\s*(.*)$", text)
        if match and 0 < int(match.group(1)) <= 20:
            if current_content:
                items.append((current_no, current_content.strip()))
            current_no = match.group(1)
            current_content = match.group(2).strip()
        elif current_content:
            current_content = f"{current_content} {text}".strip()
    if current_content:
        items.append((current_no, current_content.strip()))
    return items


def extract_inspection_rows(table) -> list[tuple[str, str]]:
    rows = table.extract()
    header_idx = 0
    for idx, row in enumerate(rows):
        joined = compact("".join(cell or "" for cell in row))
        if "检验内容" in joined:
            header_idx = idx
            break

    content_cols = list(range(min(3, table.col_count)))
    items: list[tuple[str, str]] = []
    current_no = ""
    current_content = ""
    for row in rows[header_idx + 1:]:
        raw = "".join(clean_line(row[col] or "") for col in content_cols)
        text = strip_noise_suffixes(normalize_row_text(raw))
        if not text:
            continue
        if any(keyword in compact(text) for keyword in ("编制", "校对", "标审", "批准")):
            continue
        if chinese_char_count(text) < 3 and any(char.isdigit() for char in text):
            continue
        if any(token in text for token in ("卡尺", "块规", "指示尺", "千分尺", "内径表", "量具")) and chinese_char_count(text) < 6:
            continue
        match = re.match(rf"^\s*([{ROMAN_NUMERALS}]|\d+)\s*(.*)$", text)
        if match and (match.group(1) in ROMAN_NUMERALS or 0 < int(match.group(1)) <= 20):
            if current_content:
                items.append((current_no, current_content.strip()))
            current_no = match.group(1)
            current_content = match.group(2).strip()
        elif current_content:
            current_content = f"{current_content} {text}".strip()
    if current_content:
        items.append((current_no, current_content.strip()))
    return items


def extract_external_rows(text: str) -> list[tuple[str, str]]:
    lines = [clean_line(line) for line in (text or "").splitlines() if clean_line(line)]
    content_lines: list[str] = []
    keep_keywords = (
        "调质",
        "正常化",
        "淬火",
        "真空淬火",
        "磁粉检查",
        "磁力探伤",
        "烧伤检查",
        "渗氮",
        "镀铜",
        "除铜",
        "去应力",
        "硬度",
        "试样件",
        "应无",
        "检验",
        "保持光洁锐边",
    )
    for line in lines:
        value = compact(line)
        if not value:
            continue
        if any(keyword in value for keyword in HEADER_SKIP_KEYWORDS):
            continue
        if is_date_or_name_line(line):
            continue
        if value in {"一四三厂", "军品机加分厂", "协作卡片", "检验工序卡片", "备注"}:
            continue
        if looks_like_dimension_noise(line):
            continue
        if re.search(r"[一-龥]", value) and (any(keyword in line for keyword in keep_keywords) or re.match(r"^\d+[.．、]", line)):
            cleaned = strip_noise_suffixes(line)
            if cleaned:
                content_lines.append(cleaned)

    merged: list[str] = []
    for line in content_lines:
        if merged and len(line) <= 8 and not re.match(r"^\d+[.．、]", line):
            merged[-1] = f"{merged[-1]} {line}".strip()
        else:
            merged.append(line)

    deduped: list[str] = []
    for line in merged:
        if line not in deduped:
            deduped.append(line)
    if not deduped:
        return []
    return [("", "；".join(deduped))]


def extract_rows_from_page(page: fitz.Page) -> tuple[int | None, str, list[tuple[str, str]], str, str]:
    clip = detect_card_clip(page)
    text = page.get_text("text", clip=clip)
    normalized = compact(text)
    if "工序号" not in normalized:
        return None, "", [], "", ""

    match_no = re.search(r"工序号\s*(\d+)", text)
    if not match_no:
        return None, "", [], "", ""
    process_no = int(match_no.group(1))
    process_name = extract_operation_name(page, clip, text)
    equipment_types, equipment_models = extract_equipment_details(text)
    page_type = "external"
    if "检验内容" in normalized:
        page_type = "inspection"
    elif "工步" in normalized and "加工内容" in normalized:
        page_type = "standard"
    if not process_name and page_type == "inspection":
        process_name = "检验"

    if page_type in {"standard", "inspection"}:
        table = choose_table(page, clip)
        if table is not None:
            items = extract_standard_rows(table) if page_type == "standard" else extract_inspection_rows(table)
            if items:
                return process_no, process_name, items, equipment_types, equipment_models
    return process_no, process_name, extract_external_rows(text), equipment_types, equipment_models


def extract_pdf_operation_rows(pdf_path: str) -> list[OperationRow]:
    rows_by_operation: dict[tuple[int, str], list[OperationRow]] = {}
    with fitz.open(pdf_path) as doc:
        for index, page in enumerate(doc, start=1):
            process_no, process_name, items, equipment_types, equipment_models = extract_rows_from_page(page)
            if process_no is None or not items:
                continue
            key = (process_no, process_name or f"工序{process_no}")
            rows_by_operation.setdefault(key, [])
            for item_no, content in items:
                cleaned = normalize_spaces(content)
                if not cleaned:
                    continue
                rows_by_operation[key].append(
                    OperationRow(
                        process_no=process_no,
                        process_name=key[1],
                        item_no=item_no,
                        content=cleaned,
                        page_no=index,
                        equipment_types=equipment_types,
                        equipment_models=equipment_models,
                    )
                )

    final_rows: list[OperationRow] = []
    for key in sorted(rows_by_operation, key=lambda item: item[0]):
        seen: set[tuple[str, str]] = set()
        for row in rows_by_operation[key]:
            signature = (row.item_no, row.content)
            if signature in seen:
                continue
            seen.add(signature)
            final_rows.append(row)
    return final_rows


def merge_pdf_operation_rows(rows: Iterable[OperationRow]) -> list[ExtractedOperationDetail]:
    grouped: dict[tuple[int, str], dict[str, object]] = {}
    for row in rows:
        key = (row.process_no, row.process_name)
        bucket = grouped.setdefault(key, {"contents": [], "pages": [], "equipment_types": [], "equipment_models": []})
        content = strip_noise_suffixes(row.content)
        if content and content not in bucket["contents"]:
            bucket["contents"].append(content)
        if row.page_no not in bucket["pages"]:
            bucket["pages"].append(row.page_no)
        if row.equipment_types and row.equipment_types not in bucket["equipment_types"]:
            bucket["equipment_types"].append(row.equipment_types)
        if row.equipment_models and row.equipment_models not in bucket["equipment_models"]:
            bucket["equipment_models"].append(row.equipment_models)

    results: list[ExtractedOperationDetail] = []
    for process_no in sorted({key[0] for key in grouped}):
        matched_keys = [key for key in grouped if key[0] == process_no]
        payload = grouped[matched_keys[0]]
        process_name = matched_keys[0][1] or f"工序{process_no}"
        contents = [text for text in payload["contents"] if text]
        joined = "；".join(contents) or process_name
        page_no = min(payload["pages"]) if payload["pages"] else None
        results.append(
            ExtractedOperationDetail(
                operation_seq=process_no,
                operation_name=process_name,
                operation_content=strip_noise_suffixes(joined) or process_name,
                page_no=page_no,
                normalized_name=process_name,
                is_composite=is_composite_operation_name(process_name),
                source_type="pdf_table_extract",
                equipment_types=unique_join(payload["equipment_types"]),
                equipment_models=unique_join(payload["equipment_models"]),
            )
        )
    return results


def extract_pdf_operation_details(pdf_path: str) -> list[ExtractedOperationDetail]:
    return merge_pdf_operation_rows(extract_pdf_operation_rows(pdf_path))


__all__ = [
    "ExtractedOperationDetail",
    "OperationRow",
    "extract_pdf_operation_details",
    "extract_pdf_operation_rows",
    "merge_pdf_operation_rows",
    "normalize_spaces",
    "strip_noise_suffixes",
]
