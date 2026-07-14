"""参考资料到因素字段的解析与装配。"""

from __future__ import annotations

import os
import re
from collections import defaultdict

from app.core.paths import UPLOAD_DIR
from app.models.models import Document, Reference
from app.schemas.schemas import FactorFieldOption, FactorFieldOut
from app.services.file_parser import extract_text


def clean_reference_line(line: str) -> str:
    return re.sub(r"\s+", "", line or "").strip()


def parse_reference_attributes(text: str) -> dict[str, str]:
    attrs: dict[str, str] = {}
    for raw_line in text.splitlines():
        line = clean_reference_line(raw_line)
        if not line or "|" not in line:
            continue
        parts = [part.strip() for part in line.split("|") if part.strip()]
        if len(parts) >= 3 and parts[0].isdigit():
            key = parts[1]
            value = parts[2]
        elif len(parts) >= 2:
            key = parts[0]
            value = parts[1]
        else:
            continue
        if key in {"序号", "参数", "参数值", "工作表", "[工作表:Sheet1]"}:
            continue
        if len(key) > 40 or len(value) > 80:
            continue
        attrs.setdefault(key, value)
    return attrs


def extract_reference_body(ref: Reference) -> str:
    if ref.ref_type == "written":
        return (ref.content or "").strip()
    if ref.ref_type == "uploaded" and ref.filename:
        filepath = os.path.join(UPLOAD_DIR, ref.filename)
        return extract_text(filepath).strip()
    return ""


def extract_document_body(doc: Document) -> str:
    if not doc.filename:
        return ""
    filepath = os.path.join(UPLOAD_DIR, doc.filename)
    return extract_text(filepath, doc.file_type or None).strip()


def collect_attribute_rows_from_texts(texts: list[str]) -> list[dict[str, str]]:
    rows: list[dict[str, str]] = []
    for text in texts:
        if not text:
            continue
        attrs = parse_reference_attributes(text)
        if attrs:
            rows.append(attrs)
    return rows


def collect_reference_attribute_rows(references: list[Reference]) -> list[dict[str, str]]:
    return collect_attribute_rows_from_texts([extract_reference_body(ref) for ref in references])


def reference_group_for_label(label: str) -> str:
    text = (label or "").strip()
    if any(token in text for token in ("材质", "材料", "类型")):
        return "基础与材料"
    if text.startswith("是否有"):
        return "结构特征"
    if any(token in text for token in ("探伤", "检验")):
        return "专项检查与放行"
    if any(token in text for token in ("硬度", "淬火", "应力", "机械性能")):
        return "热处理与性能"
    if any(token in text for token in ("粗糙度", "同轴度", "圆柱度", "圆跳动")):
        return "精度与表面"
    return "结构补充"


def is_numeric_value(value: str) -> bool:
    try:
        float((value or "").strip())
        return True
    except (TypeError, ValueError):
        return False


def material_options_from_rows(rows: list[dict[str, str]]) -> list[tuple[str, str]]:
    values: set[str] = set()
    for attrs in rows:
        for key in ("零件材质", "材料", "材质"):
            value = attrs.get(key, "").strip()
            if value:
                values.add(value)
    return [(value, value) for value in sorted(values)]


def structure_options_from_rows(rows: list[dict[str, str]]) -> list[str]:
    values: set[str] = set()
    for attrs in rows:
        for key in ("结构类型", "零件类型", "零件家族"):
            value = attrs.get(key, "").strip()
            if value:
                values.add(value)
    return sorted(values)


def build_attribute_factor_schema(rows: list[dict[str, str]], prefix: str = "ref__") -> list[FactorFieldOut]:
    if not rows:
        return []

    mapped_labels = {"零件材质", "材料", "材质", "结构类型", "零件类型", "零件家族"}
    value_sets: defaultdict[str, set[str]] = defaultdict(set)

    for attrs in rows:
        for label, raw_value in attrs.items():
            value = str(raw_value).strip()
            if not value:
                continue
            value_sets[label].add(value)

    fields: list[FactorFieldOut] = []
    ordered_labels = sorted(value_sets.keys(), key=lambda item: (reference_group_for_label(item), item))
    for label in ordered_labels:
        if label in mapped_labels:
            continue
        values = sorted(value_sets[label], key=lambda item: (len(item), item))
        if not values:
            continue

        key = f"{prefix}{label}"
        group = reference_group_for_label(label)

        if set(values).issubset({"是", "否"}):
            fields.append(
                FactorFieldOut(
                    key=key,
                    label=label,
                    group=group,
                    input_type="boolean",
                    required=False,
                    placeholder=None,
                    options=[
                        FactorFieldOption(value="false", label="否"),
                        FactorFieldOption(value="true", label="是"),
                    ],
                )
            )
        elif all(is_numeric_value(value) for value in values):
            fields.append(
                FactorFieldOut(
                    key=key,
                    label=label,
                    group=group,
                    input_type="number",
                    required=False,
                    placeholder=f"请输入{label}",
                    options=[],
                )
            )
        elif len(values) <= 8:
            fields.append(
                FactorFieldOut(
                    key=key,
                    label=label,
                    group=group,
                    input_type="select",
                    required=False,
                    placeholder=None,
                    options=[FactorFieldOption(value=value, label=value) for value in values],
                )
            )
        else:
            fields.append(
                FactorFieldOut(
                    key=key,
                    label=label,
                    group=group,
                    input_type="text",
                    required=False,
                    placeholder=f"请输入{label}",
                    options=[],
                )
            )
    return fields


def reference_material_options(references: list[Reference]) -> list[tuple[str, str]]:
    return material_options_from_rows(collect_reference_attribute_rows(references))


def reference_structure_options(references: list[Reference]) -> list[str]:
    return structure_options_from_rows(collect_reference_attribute_rows(references))


def build_reference_factor_schema(references: list[Reference]) -> list[FactorFieldOut]:
    return build_attribute_factor_schema(collect_reference_attribute_rows(references))


__all__ = [
    "build_attribute_factor_schema",
    "build_reference_factor_schema",
    "clean_reference_line",
    "collect_attribute_rows_from_texts",
    "collect_reference_attribute_rows",
    "extract_document_body",
    "extract_reference_body",
    "is_numeric_value",
    "material_options_from_rows",
    "parse_reference_attributes",
    "reference_group_for_label",
    "reference_material_options",
    "reference_structure_options",
    "structure_options_from_rows",
]
