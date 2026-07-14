"""
路线归并来源映射工具。

这里集中处理结果工序项和原始来源工序之间的映射关系，包括来源节点、
来源工序 ID、来源工序名称和单来源 lookup 构造。
"""
from __future__ import annotations

from app.services.route_merge.sorting import display_operation_name, route_item_value


def unique_nonblank_strings(values: object) -> list[str]:
    unique: list[str] = []
    for value in values or []:
        text = display_operation_name(value)
        if text and text not in unique:
            unique.append(text)
    return unique


def route_item_source_operation_ids(item: object) -> list[int]:
    operation_ids: list[int] = []
    for op_id in route_item_value(item, "source_operation_ids", []) or []:
        try:
            parsed = int(op_id)
        except Exception:
            continue
        if parsed > 0 and parsed not in operation_ids:
            operation_ids.append(parsed)
    return operation_ids


def route_item_source_nodes(item: object) -> list[str]:
    return unique_nonblank_strings(route_item_value(item, "source_nodes", []) or [])


def route_item_source_operation_names(item: object) -> list[str]:
    return unique_nonblank_strings(route_item_value(item, "source_operation_names", []) or [])


def build_route_item_source_lookup(items: list[object]) -> dict[int, dict[str, object]]:
    lookup: dict[int, dict[str, object]] = {}
    for item in items or []:
        source_items = list(route_item_value(item, "_source_items", []) or [])
        if source_items:
            for source_item in source_items:
                op_id = int(source_item.get("id") or 0)
                if op_id <= 0:
                    continue
                source_nodes = unique_nonblank_strings(
                    source_item.get("source_nodes")
                    or ([str(source_item.get("name") or "")] if str(source_item.get("name") or "").strip() else [])
                )
                lookup[op_id] = {
                    "name": display_operation_name(source_item.get("name")),
                    "source_nodes": source_nodes,
                    "matched_detail_rows": list(source_item.get("matched_detail_rows") or []),
                }
            continue

        operation_ids = route_item_source_operation_ids(item)
        if len(operation_ids) != 1:
            continue
        op_id = operation_ids[0]
        source_nodes = route_item_source_nodes(item)
        if not source_nodes:
            fallback_name = (
                display_operation_name(route_item_value(item, "normalized_step_name", ""))
                or display_operation_name(route_item_value(item, "name", ""))
            )
            source_nodes = [fallback_name] if fallback_name else []
        lookup[op_id] = {
            "name": display_operation_name(route_item_value(item, "normalized_step_name", "") or route_item_value(item, "name", "")),
            "source_nodes": source_nodes,
            "matched_detail_rows": list(route_item_value(item, "matched_detail_rows", []) or []),
        }
    return lookup


def resolved_route_item_source_nodes(
    item: object,
    source_lookup: dict[int, dict[str, object]] | None = None,
) -> list[str]:
    resolved: list[str] = []
    if source_lookup:
        for op_id in route_item_source_operation_ids(item):
            for source_name in source_lookup.get(op_id, {}).get("source_nodes") or []:
                text = str(source_name or "").strip()
                if text and text not in resolved:
                    resolved.append(text)
    if resolved:
        return resolved
    source_nodes = route_item_source_nodes(item)
    if source_nodes:
        return source_nodes
    fallback_name = (
        display_operation_name(route_item_value(item, "normalized_step_name", ""))
        or display_operation_name(route_item_value(item, "name", ""))
    )
    return [fallback_name] if fallback_name else []
