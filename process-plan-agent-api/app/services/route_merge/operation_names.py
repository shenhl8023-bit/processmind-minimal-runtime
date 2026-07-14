"""Operation-name helpers shared by route merge services."""

from __future__ import annotations

import re

from app.models.models import DocumentOperationDetail
from app.services.route_merge.sorting import normalize_operation_name


def split_composite_operation_name(name: str) -> list[str]:
    normalized = normalize_operation_name(name or "")
    if not normalized:
        return []

    parts = [
        normalize_operation_name(part)
        for part in re.split(r"[，,、/／]+", normalized)
        if normalize_operation_name(part)
    ]
    if len(parts) > 1:
        return list(dict.fromkeys(parts))

    turning_candidates = ("车外形", "车外圆", "车零件", "车端面", "平端面")
    hole_candidates = ("钻镗孔", "钻铰孔", "攻螺纹", "镗孔", "钻孔")
    turning_match = next((item for item in turning_candidates if item in normalized), "")
    hole_match = next((item for item in hole_candidates if item in normalized), "")
    if turning_match and hole_match and turning_match != normalized and hole_match != normalized:
        return [turning_match, hole_match]

    return [normalized]


def detail_row_atomic_names(row: DocumentOperationDetail | dict) -> list[str]:
    raw_name = str(row.get("operation_name") or "") if isinstance(row, dict) else (row.operation_name or "")
    normalized_name = str(row.get("normalized_name") or "") if isinstance(row, dict) else (row.normalized_name or "")
    names = split_composite_operation_name(raw_name)
    names.extend(split_composite_operation_name(normalized_name))
    normalized = normalize_operation_name(normalized_name or raw_name)
    if normalized:
        names.append(normalized)
    return list(dict.fromkeys(name for name in names if name))


__all__ = [
    "detail_row_atomic_names",
    "split_composite_operation_name",
]
