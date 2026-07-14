"""Build saved route-version segments from normalized route items."""

from __future__ import annotations

import re

from app.models.models import DocumentOperationDetail
from app.services.route_merge.equipment import extract_detail_excerpt
from app.services.route_merge.operation_names import detail_row_atomic_names, split_composite_operation_name
from app.services.route_merge.source_lookup import (
    resolved_route_item_source_nodes,
    route_item_source_nodes,
    route_item_source_operation_ids,
    route_item_source_operation_names,
    unique_nonblank_strings,
)
from app.services.route_merge.sorting import display_operation_name, route_item_phase, route_item_value


def _parse_coverage_label(label: str) -> tuple[int, int]:
    text = str(label or "").strip()
    if not text:
        return 0, 0
    ratio_match = re.fullmatch(r"(\d+)\s*/\s*(\d+)", text)
    if ratio_match:
        return int(ratio_match.group(1)), int(ratio_match.group(2))
    if text.isdigit():
        return int(text), 0
    return 0, 0


def _unique_rows(rows: list[dict[str, object]]) -> list[dict[str, object]]:
    result: list[dict[str, object]] = []
    seen: set[tuple[int, int, str]] = set()
    for row in rows:
        key = (
            int(row.get("detail_id") or 0),
            int(row.get("document_id") or 0),
            str(row.get("operation_name") or ""),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(row)
    return result


def _matched_rows_for_route_item(
    item: object,
    detail_rows: list[DocumentOperationDetail],
    source_lookup: dict[int, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    if source_lookup:
        lookup_rows: list[dict[str, object]] = []
        for op_id in route_item_source_operation_ids(item):
            for row in source_lookup.get(op_id, {}).get("matched_detail_rows") or []:
                if hasattr(row, "model_dump"):
                    lookup_rows.append(row.model_dump())
                elif isinstance(row, dict):
                    lookup_rows.append(dict(row))
        lookup_rows = _unique_rows(lookup_rows)
        if lookup_rows:
            return lookup_rows

    source_nodes = resolved_route_item_source_nodes(item, source_lookup)
    operation_name_set: set[str] = set()
    for name in source_nodes:
        operation_name_set.update(split_composite_operation_name(name))

    matched_rows: list[dict[str, object]] = []
    if operation_name_set:
        matched_rows = [
            {
                "detail_id": row.id,
                "document_id": row.document_id,
                "pdf_name": row.pdf_name,
                "operation_seq": row.operation_seq,
                "operation_name": row.operation_name,
                "normalized_name": row.normalized_name or "",
                "operation_content": row.operation_content or "",
                "page_no": row.page_no,
                "equipment_types": row.equipment_types or "",
                "equipment_models": row.equipment_models or "",
            }
            for row in detail_rows
            if operation_name_set.intersection(detail_row_atomic_names(row))
        ]

    if matched_rows:
        return matched_rows

    fallback_rows: list[dict[str, object]] = []
    for row in route_item_value(item, "matched_detail_rows", []) or []:
        if hasattr(row, "model_dump"):
            fallback_rows.append(row.model_dump())
        elif isinstance(row, dict):
            fallback_rows.append(dict(row))
    return fallback_rows


def _route_item_coverage_stats(
    matched_rows: list[dict[str, object]],
    total_docs: int,
    fallback_label: str,
) -> tuple[dict[str, object], dict[str, object], str]:
    hit_docs = len({
        int(row.get("document_id") or 0)
        for row in matched_rows
        if int(row.get("document_id") or 0) > 0
    })
    matched_row_count = len(matched_rows)
    fallback_hit, fallback_total = _parse_coverage_label(fallback_label)

    # Some legacy route entries may carry reliable route-level coverage but no
    # per-card detail rows. Preserve that route-level coverage instead of
    # turning every saved segment into 0/N.
    if hit_docs == 0 and matched_row_count == 0 and fallback_hit > 0:
        hit_docs = fallback_hit

    coverage_total = total_docs if total_docs > 0 else fallback_total
    if coverage_total > 0:
        label = f"{hit_docs}/{coverage_total}"
    else:
        label = fallback_label or (str(hit_docs) if hit_docs > 0 else "")

    ratio = round((hit_docs / coverage_total), 4) if coverage_total > 0 else 0.0
    return (
        {
            "hit_docs": hit_docs,
            "total_docs": coverage_total,
            "ratio": ratio,
            "label": label,
        },
        {
            "matched_rows": matched_row_count,
        },
        label,
    )


def build_saved_route_version_segments(
    items: list[object],
    detail_rows: list[DocumentOperationDetail],
    total_docs: int,
    source_lookup: dict[int, dict[str, object]] | None = None,
) -> list[dict[str, object]]:
    segments: list[dict[str, object]] = []
    for idx, item in enumerate(items, start=1):
        source_operation_ids = route_item_source_operation_ids(item)
        source_nodes = resolved_route_item_source_nodes(item, source_lookup)
        source_operation_names = route_item_source_operation_names(item) or route_item_source_nodes(item)
        matched_rows = _matched_rows_for_route_item(item, detail_rows, source_lookup)
        evidence_excerpt = list(dict.fromkeys(
            extract_detail_excerpt(str(row.get("operation_content") or ""))
            for row in matched_rows
            if row.get("operation_content")
        ))[:4]
        doc_coverage, detail_coverage, coverage_label = _route_item_coverage_stats(
            matched_rows,
            total_docs,
            str(route_item_value(item, "coverage_label", "") or ""),
        )

        segments.append({
            "id": str(route_item_value(item, "id", f"manual-route-{idx}") or f"manual-route-{idx}"),
            "sequence": idx * 10,
            "normalized_step_name": display_operation_name(route_item_value(item, "normalized_step_name", "")) or "未命名工序段",
            "parent_segment": display_operation_name(route_item_value(item, "parent_segment", "")),
            "step_family": str(route_item_value(item, "step_family", "") or ""),
            "phase": route_item_phase(item),
            "source_nodes": source_nodes,
            "source_operation_names": unique_nonblank_strings(source_operation_names),
            "source_operation_ids": source_operation_ids,
            "review_status": str(route_item_value(item, "review_status", "merged") or "merged"),
            "source_type": str(route_item_value(item, "source_type", "manual_adjusted") or "manual_adjusted"),
            "coverage_label": coverage_label,
            "doc_coverage": doc_coverage,
            "detail_coverage": detail_coverage,
            "evidence_excerpt": evidence_excerpt,
            "matched_detail_rows": matched_rows,
            "equipment_profile": {
                "split_applied": bool(route_item_value(item, "equipment_split_applied", False)),
                "equipment_types": list(route_item_value(item, "equipment_types", []) or []),
                "equipment_models": list(route_item_value(item, "equipment_models", []) or []),
            },
            "equipment_child_segment": str(route_item_value(item, "equipment_child_segment", "") or ""),
            "equipment_split_applied": bool(route_item_value(item, "equipment_split_applied", False)),
            "equipment_types": list(route_item_value(item, "equipment_types", []) or []),
            "equipment_models": list(route_item_value(item, "equipment_models", []) or []),
            "equipment_support_result": str(route_item_value(item, "equipment_support_result", "neutral") or "neutral"),
            "equipment_support_reason": str(route_item_value(item, "equipment_support_reason", "") or ""),
            "analysis_status": "pending",
            "separator_result": str(route_item_value(item, "separator_result", "pass") or "pass"),
            "manual_review_required": bool(route_item_value(item, "manual_review_required", False)),
            "reason_codes": list(route_item_value(item, "reason_codes", []) or []),
        })
    return segments


__all__ = ["build_saved_route_version_segments"]
