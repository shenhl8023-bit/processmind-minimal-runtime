from __future__ import annotations

from collections import defaultdict

from app.models.models import DocumentOperationDetail, Operation
from app.services.process_knowledge import canonicalize_route_label
from app.services.process_tree_builder_support import (
    ORDER_SLOT_BY_KEY,
    ORDER_SLOTS,
    REPEATABLE_STAGE_LABELS,
    TreeNodeBucket,
    extract_step_payload,
    extra_node_sort_key,
    find_next_turning_group,
    group_detail_rows_by_document,
    group_document_operations,
    normalize_process_name,
    normalize_tree_label,
    resolve_node_key,
    slot_description,
)


def build_superset_process_tree(
    *,
    operations: list[Operation],
    detail_rows: list[DocumentOperationDetail],
    sample_count: int,
) -> list[dict[str, object]]:
    if not detail_rows:
        return []

    grouped_rows = group_detail_rows_by_document(detail_rows)
    buckets: dict[str, TreeNodeBucket] = {}
    global_index = 0

    for rows in grouped_rows.values():
        grouped_operations = group_document_operations(rows)
        turning_seen = 0
        repeatable_seen: defaultdict[str, int] = defaultdict(int)
        for index_in_doc, operation_group in enumerate(grouped_operations):
            global_index += 1
            original_name = str(operation_group.operation_name or "").strip()
            if not original_name:
                continue
            label, next_turning_seen = normalize_tree_label(
                original_name,
                operation_group.operation_content or "",
                turning_seen,
            )
            if not label:
                continue

            next_turning_group = find_next_turning_group(grouped_operations, index_in_doc)

            turning_seen_before = turning_seen
            node_key, display_label = resolve_node_key(
                label=label,
                turning_seen_before=turning_seen_before,
                current_group=operation_group,
                next_turning_group=next_turning_group,
            )
            display_label = canonicalize_route_label(display_label)
            turning_seen = next_turning_seen

            if display_label in REPEATABLE_STAGE_LABELS:
                repeatable_seen[display_label] += 1
                stage_index = repeatable_seen[display_label] if repeatable_seen[display_label] <= 3 else 3
                node_key = f"{display_label}::{stage_index}"
            elif node_key == display_label and display_label in REPEATABLE_STAGE_LABELS:
                repeatable_seen[label] += 1
                stage_index = repeatable_seen[display_label] if repeatable_seen[display_label] <= 3 else 3
                node_key = f"{display_label}::{stage_index}"

            bucket = buckets.get(node_key)
            if not bucket:
                bucket = TreeNodeBucket(
                    node_key=node_key,
                    label=display_label,
                    first_sequence=operation_group.operation_seq,
                    first_index=global_index,
                )
                buckets[node_key] = bucket
            elif bucket.first_sequence <= 0 and operation_group.operation_seq > 0:
                bucket.first_sequence = operation_group.operation_seq

            bucket.coverage_docs.add(operation_group.document_key)
            bucket.add_source_node(original_name)
            for row_id in operation_group.row_ids:
                bucket.add_detail_row_id(row_id)
            step_items, attached_step_items = extract_step_payload(
                display_label,
                original_name,
                operation_group.operation_content or "",
            )
            for step in step_items:
                bucket.add_step_item(step)
            for step in attached_step_items:
                bucket.add_attached_step_item(step)

    tree_items: list[dict[str, object]] = []
    known_keys = {str(item["node_key"]) for item in ORDER_SLOTS}
    ordered_keys = [str(item["node_key"]) for item in ORDER_SLOTS if str(item["node_key"]) in buckets]
    extra_keys = [key for key in buckets if key not in known_keys]
    extra_keys.sort(key=lambda key: extra_node_sort_key(buckets[key]))
    ordered_node_keys = ordered_keys + extra_keys

    raw_ops_by_name: defaultdict[str, list[Operation]] = defaultdict(list)
    for op in operations:
        raw_name = str(op.name or "").strip()
        if raw_name:
            raw_ops_by_name[raw_name].append(op)
        normalized_name = normalize_process_name(raw_name)
        if normalized_name and normalized_name != raw_name:
            raw_ops_by_name[normalized_name].append(op)

    project_id = int(getattr(operations[0], "project_id", 0) or 0) if operations else int(getattr(detail_rows[0], "project_id", 0) or 0)
    for index, node_key in enumerate(ordered_node_keys, start=1):
        bucket = buckets[node_key]
        slot = ORDER_SLOT_BY_KEY.get(node_key)
        sequence = int(slot["sequence"]) if slot else index * 10
        description = slot_description(node_key, bucket.label, bucket.source_nodes)
        display_name = bucket.label

        factors: dict[str, dict[str, object]] = {}
        warnings: dict[str, dict[str, str]] = {}
        source_values: list[str] = []
        chain = ""
        op_type = "MAIN"
        for raw_name in bucket.source_nodes:
            for op in raw_ops_by_name.get(raw_name, []):
                if getattr(op, "source", None):
                    source_values.append(str(op.source).strip())
                if not chain and getattr(op, "chain", None):
                    chain = str(op.chain or "").strip()
                if getattr(op, "op_type", None) == "BRANCH":
                    op_type = "BRANCH"
                for factor in list(getattr(op, "factors", []) or []):
                    factor_name = str(getattr(factor, "name", "") or "").strip()
                    if not factor_name or factor_name in factors:
                        continue
                    factors[factor_name] = {
                        "id": int(getattr(factor, "id", 0) or 0),
                        "name": factor_name,
                        "evidence": getattr(factor, "evidence", None),
                        "strength": str(getattr(factor, "strength", "WEAK") or "WEAK"),
                        "confirmed": bool(getattr(factor, "confirmed", False)),
                    }
                for warning in list(getattr(op, "_harness_warnings", []) or []):
                    code = str(warning.get("code") or "").strip()
                    if code and code not in warnings:
                        warnings[code] = dict(warning)

        coverage_count = len(bucket.coverage_docs)
        tree_items.append({
            "id": 900000 + index,
            "project_id": project_id or None,
            "name": display_name,
            "sequence": sequence,
            "chain": chain or None,
            "op_type": op_type,
            "description": description or None,
            "source": "；".join(dict.fromkeys([item for item in source_values if item])) or None,
            "confidence": "STRONG" if sample_count > 0 and coverage_count >= sample_count else "WEAK",
            "factors": list(factors.values()),
            "sample_count": sample_count,
            "coverage_count": coverage_count,
            "harness_warnings": list(warnings.values()),
            "source_nodes": list(bucket.source_nodes),
            "step_items": list(bucket.step_items),
            "attached_step_items": list(bucket.attached_step_items),
            "detail_row_ids": list(bucket.detail_row_ids),
        })

    return tree_items


__all__ = ["build_superset_process_tree"]
