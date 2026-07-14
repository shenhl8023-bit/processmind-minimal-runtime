"""
第二步路线归并排序与阶段识别工具。

这里集中放置路线项取值、工序名标准化、阶段识别，以及“末尾清洗/检验/包装”
放行链排序逻辑，避免 workspace 同时承担构建、持久化和排序三类职责。
"""
from __future__ import annotations

import re

from app.services.process_knowledge import (
    canonical_route_operation_name,
    canonicalize_route_label,
    infer_merge_family_key,
)
from app.services.route_merge.config import (
    POST_BRANCH_STAGE_ORDER,
    TERMINAL_RELEASE_ORDER,
)


def route_item_value(item: object, key: str, default: object = "") -> object:
    if isinstance(item, dict):
        return item.get(key, default)
    return getattr(item, key, default)


def normalize_operation_name(name: str) -> str:
    return canonical_route_operation_name(name or "")


def display_operation_name(name: object) -> str:
    return canonicalize_route_label(str(name or "").strip())


def merge_family_key(name: str) -> str:
    return infer_merge_family_key(name or "")


def infer_operation_phase(name: str) -> str:
    normalized = normalize_operation_name(name)
    family_key = merge_family_key(normalized)
    if normalized in {"镀铜", "除铜", "铬酸阳极化", "硬质阳极化"}:
        return "surface_treatment"
    if family_key == "inspection":
        return "inspection"
    if family_key == "heat":
        return "heat_treatment"
    if family_key == "release":
        return "auxiliary"
    if normalized.startswith(("磨", "研", "珩")):
        return "finish"
    return "rough"


def route_item_phase(item: object) -> str:
    phase = str(route_item_value(item, "phase", "") or "").strip()
    return phase


def sequence_sort_value(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def post_branch_stage_rank(normalized_name: str) -> int:
    return POST_BRANCH_STAGE_ORDER.get(normalized_name, 0)


def route_merge_sort_key(item: object, terminal_release_ids: set[str] | None = None) -> tuple[int, int, int, str]:
    name = (
        display_operation_name(route_item_value(item, "normalized_step_name", ""))
        or display_operation_name(route_item_value(item, "name", ""))
    )
    normalized_name = re.sub(r"（第\d+次）$", "", normalize_operation_name(name))
    terminal_rank = TERMINAL_RELEASE_ORDER.get(normalized_name, 0)
    sequence = int(route_item_value(item, "_raw_first_sequence", 0) or route_item_value(item, "sequence", 0) or 0)
    first_index = int(route_item_value(item, "_first_index", 0) or 0)
    item_id = str(route_item_value(item, "id", "") or "")
    if terminal_rank and item_id in (terminal_release_ids or set()):
        return (900_000 + terminal_rank, sequence, first_index, item_id)
    post_branch_rank = post_branch_stage_rank(normalized_name)
    if post_branch_rank and sequence >= 290:
        return (700_000 + post_branch_rank, sequence, first_index, item_id)
    return (sequence, first_index, 0, item_id)


def route_merge_terminal_release_ids(items: list[object]) -> set[str]:
    packaging_sequences = [
        int(route_item_value(item, "_raw_first_sequence", 0) or route_item_value(item, "sequence", 0) or 0)
        for item in items or []
        if re.sub(
            r"（第\d+次）$",
            "",
            normalize_operation_name(
                display_operation_name(route_item_value(item, "normalized_step_name", ""))
                or display_operation_name(route_item_value(item, "name", ""))
            ),
        ) == "包装"
    ]
    if not packaging_sequences:
        return set()
    packaging_sequence = min(packaging_sequences)
    terminal_ids: set[str] = set()
    for item in items or []:
        item_id = str(route_item_value(item, "id", "") or "")
        if not item_id:
            continue
        name = (
            display_operation_name(route_item_value(item, "normalized_step_name", ""))
            or display_operation_name(route_item_value(item, "name", ""))
        )
        normalized_name = re.sub(r"（第\d+次）$", "", normalize_operation_name(name))
        sequence = int(route_item_value(item, "_raw_first_sequence", 0) or route_item_value(item, "sequence", 0) or 0)
        if normalized_name == "包装" or (
            normalized_name in {"清洗", "检验"}
            and packaging_sequence - 30 <= sequence <= packaging_sequence
        ):
            terminal_ids.add(item_id)
    return terminal_ids


def sort_route_items_with_terminal_release(items: list[dict[str, object]]) -> list[dict[str, object]]:
    terminal_release_ids = route_merge_terminal_release_ids(list(items or []))
    return sorted(
        list(items or []),
        key=lambda item: route_merge_sort_key(item, terminal_release_ids),
    )
