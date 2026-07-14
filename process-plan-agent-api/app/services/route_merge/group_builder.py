"""
第二步路线归并中的来源组构造与候选组合装。
"""

from __future__ import annotations

from app.models.models import DocumentOperationDetail
from app.services.route_merge.config import ABSORB_INTO_PARENT_RULES, DIRECT_MERGE_RULES, KEEP_SEPARATE_RULES
from app.services.route_merge.equipment import extract_detail_excerpt
from app.services.route_merge.operation_names import detail_row_atomic_names, split_composite_operation_name
from app.services.route_merge.sorting import (
    display_operation_name as _display_operation_name,
    infer_operation_phase as _infer_operation_phase,
    merge_family_key,
    normalize_operation_name as _normalize_operation_name,
    route_merge_sort_key as _route_merge_sort_key,
    route_merge_terminal_release_ids as _route_merge_terminal_release_ids,
    sequence_sort_value as _sequence_sort_value,
)


def _coverage_label(hit: int, total: int) -> str:
    if total > 0:
        return f"{hit}/{total}"
    if hit > 0:
        return str(hit)
    return ""


def _compose_merged_source_name(names: list[object]) -> str:
    ordered: list[str] = []
    for name in names:
        text = _display_operation_name(name)
        if text and text not in ordered:
            ordered.append(text)
    return "/".join(ordered)


def _merge_family_label(family_key: str) -> str:
    mapping = {
        "shape": "车削/成形类",
        "hole": "孔加工类",
        "feature": "特征加工类",
        "heat": "热处理类",
        "inspection": "检验类",
        "release": "辅助/放行类",
        "surface": "表面处理类",
    }
    return mapping.get(family_key, family_key or "其他")


def _serialize_detail_row(row: DocumentOperationDetail) -> dict[str, object]:
    return {
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


def _matched_rows_for_names(
    source_names: list[str],
    detail_rows: list[DocumentOperationDetail],
) -> list[dict[str, object]]:
    operation_name_set: set[str] = set()
    for source_name in source_names:
        operation_name_set.update(split_composite_operation_name(source_name))
    if not operation_name_set:
        return []
    return [
        _serialize_detail_row(row)
        for row in detail_rows
        if operation_name_set.intersection(detail_row_atomic_names(row))
    ]


def _matched_rows_for_detail_ids(
    detail_row_ids: list[object],
    detail_rows: list[DocumentOperationDetail],
) -> list[dict[str, object]]:
    ids = {int(item or 0) for item in detail_row_ids if int(item or 0) > 0}
    if not ids:
        return []
    return [_serialize_detail_row(row) for row in detail_rows if int(row.id or 0) in ids]


def _derive_group_coverage_label(
    matched_rows: list[dict[str, object]],
    detail_rows: list[DocumentOperationDetail],
    fallback_hit: int,
    fallback_total: int,
) -> str:
    matched_doc_ids = {int(row.get("document_id") or 0) for row in matched_rows if int(row.get("document_id") or 0) > 0}
    if matched_doc_ids:
        total_docs = len({int(row.document_id or 0) for row in detail_rows if int(row.document_id or 0) > 0})
        return _coverage_label(len(matched_doc_ids), total_docs)
    return _coverage_label(fallback_hit, fallback_total)


def _evidence_excerpt(rows: list[dict[str, object]]) -> list[str]:
    excerpts: list[str] = []
    for row in rows:
        excerpt = extract_detail_excerpt(str(row.get("operation_content") or ""))
        if excerpt and excerpt not in excerpts:
            excerpts.append(excerpt)
        if len(excerpts) >= 4:
            break
    return excerpts


def _build_group_payload_from_members(
    *,
    group_id: str,
    group_key: str,
    normalized_step_name: str,
    members: list[dict[str, object]],
    detail_rows: list[DocumentOperationDetail],
    review_status: str,
    suggestion_type: str,
    recommendation_label: str,
    recommendation_reason: str,
    step_family: str = "",
    phase: str = "",
    parent_segment: str = "",
    manual_review_required: bool = False,
    reason_codes: list[str] | None = None,
) -> dict[str, object]:
    source_nodes: list[str] = []
    source_operation_ids: list[int] = []
    matched_rows: list[dict[str, object]] = []
    source_items: list[dict[str, object]] = []
    coverage_hit = 0
    coverage_total = 0
    first_sequence = 0
    first_index = 0

    for member in members:
        for source_name in member.get("source_nodes") or []:
            text = _display_operation_name(source_name)
            if text and text not in source_nodes:
                source_nodes.append(text)
        for op_id in member.get("source_operation_ids") or []:
            parsed_id = int(op_id or 0)
            if parsed_id > 0 and parsed_id not in source_operation_ids:
                source_operation_ids.append(parsed_id)
        for row in member.get("matched_detail_rows") or []:
            matched_rows.append(dict(row))
        for item in member.get("_source_items") or []:
            source_items.append(dict(item))

        member_sequence = int(member.get("sequence") or 0)
        member_index = int(member.get("_first_index") or 0)
        if first_sequence <= 0 or (member_sequence > 0 and member_sequence < first_sequence):
            first_sequence = member_sequence
        if first_index <= 0 or (member_index > 0 and member_index < first_index):
            first_index = member_index

        coverage_hit = max(coverage_hit, int(member.get("_coverage_hit") or 0))
        coverage_total = max(coverage_total, int(member.get("_coverage_total") or 0))

    matched_rows = _unique_rows(matched_rows)
    source_items.sort(key=lambda item: (int(item.get("sequence") or 0), int(item.get("index") or 0), int(item.get("id") or 0)))
    coverage_label = _derive_group_coverage_label(matched_rows, detail_rows, coverage_hit, coverage_total)

    return {
        "id": group_id,
        "group_key": group_key,
        "sequence": first_sequence,
        "normalized_step_name": _display_operation_name(normalized_step_name) or "未命名工序段",
        "step_family": step_family or str(members[0].get("step_family") or ""),
        "phase": phase or str(members[0].get("phase") or ""),
        "source_nodes": source_nodes,
        "source_operation_ids": source_operation_ids,
        "review_status": review_status,
        "source_type": "system_recommendation",
        "coverage_label": coverage_label,
        "separator_result": "pass",
        "manual_review_required": manual_review_required,
        "reason_codes": list(reason_codes or []),
        "evidence_excerpt": _evidence_excerpt(matched_rows),
        "matched_detail_rows": matched_rows,
        "parent_segment": _display_operation_name(parent_segment),
        "equipment_child_segment": "",
        "equipment_split_applied": False,
        "equipment_types": [],
        "equipment_models": [],
        "equipment_support_result": "neutral",
        "equipment_support_reason": "",
        "suggestion_type": suggestion_type,
        "recommendation_label": recommendation_label,
        "recommendation_reason": recommendation_reason,
        "recommended_target_name": _display_operation_name(normalized_step_name) or "未命名工序段",
        "_source_items": source_items,
        "_raw_first_sequence": first_sequence,
        "_first_index": first_index,
        "_coverage_hit": coverage_hit,
        "_coverage_total": coverage_total,
    }


def _default_direct_merge_name(members: list[dict[str, object]], fallback_name: str) -> str:
    source_names: list[object] = []
    for member in members:
        source_names.extend(member.get("source_nodes") or [])
    composite_name = _compose_merged_source_name(source_names)
    if composite_name:
        return composite_name
    return _display_operation_name(fallback_name) or "未命名工序段"


def _operation_step_items(operation: dict) -> list[str]:
    step_items = [
        str(item or "").strip()
        for item in operation.get("step_items") or []
        if str(item or "").strip()
    ]
    attached_items = [
        str(item or "").strip()
        for item in operation.get("attached_step_items") or []
        if str(item or "").strip()
    ]
    return list(dict.fromkeys(step_items + attached_items))


def _rule_name_set(rule: dict[str, object], singular_key: str, plural_key: str) -> set[str]:
    names: set[str] = set()
    singular_value = str(rule.get(singular_key) or "").strip()
    if singular_value:
        names.add(_normalize_operation_name(singular_value))
    names.update(
        _normalize_operation_name(str(item))
        for item in rule.get(plural_key, set()) or set()
        if str(item or "").strip()
    )
    return {name for name in names if name}


def _is_absorb_candidate_pair(
    *,
    child_operation: dict,
    parent_operation: dict,
    rule: dict[str, object],
) -> bool:
    child_names = _rule_name_set(rule, "child_name", "child_names")
    parent_names = _rule_name_set(rule, "parent_name", "parent_names")
    if _normalize_operation_name(str(child_operation.get("name") or "")) not in child_names:
        return False
    if _normalize_operation_name(str(parent_operation.get("name") or "")) not in parent_names:
        return False
    required_parent_steps = {str(item) for item in rule.get("required_parent_steps", set())}
    parent_steps = {_normalize_operation_name(item) for item in _operation_step_items(parent_operation)}
    required_steps = {_normalize_operation_name(item) for item in required_parent_steps}
    if required_steps and not required_steps.issubset(parent_steps):
        return False
    return True


def build_source_group_from_operation(operation: dict, detail_rows: list[DocumentOperationDetail]) -> dict[str, object]:
    op_name = _display_operation_name(operation.get("name"))
    op_id = int(operation.get("id") or 0)
    sequence = _sequence_sort_value(operation.get("sequence"))
    raw_source_nodes = [
        _display_operation_name(name)
        for name in operation.get("source_nodes", []) or []
        if _display_operation_name(name)
    ]
    source_names = raw_source_nodes or ([op_name] if op_name else [])
    matched_rows = _matched_rows_for_detail_ids(list(operation.get("detail_row_ids") or []), detail_rows)
    if not matched_rows:
        matched_rows = _matched_rows_for_names(source_names, detail_rows)
    family_key = merge_family_key(op_name)
    step_family = _merge_family_label(family_key)
    phase = _infer_operation_phase(op_name)
    coverage_hit = int(operation.get("coverage_count") or 0)
    coverage_total = int(operation.get("sample_count") or 0)
    coverage_label = _derive_group_coverage_label(matched_rows, detail_rows, coverage_hit, coverage_total)
    source_item = {
        "id": op_id,
        "group_id": f"split-{op_id or _normalize_operation_name(op_name)}",
        "name": op_name or "未命名工序段",
        "sequence": sequence,
        "index": int(operation.get("_index") or sequence or 0),
        "source_nodes": list(source_names),
        "coverage_label": coverage_label,
        "step_family": step_family,
        "phase": phase,
        "matched_detail_rows": list(matched_rows),
        "evidence_excerpt": _evidence_excerpt(matched_rows),
    }
    return {
        "id": source_item["group_id"],
        "group_key": f"single::{_normalize_operation_name(op_name)}",
        "sequence": sequence,
        "normalized_step_name": op_name or "未命名工序段",
        "step_family": step_family,
        "phase": phase,
        "source_nodes": list(source_names),
        "source_operation_ids": [op_id] if op_id > 0 else [],
        "review_status": "kept",
        "source_type": "split_from_reject",
        "coverage_label": coverage_label,
        "separator_result": "pass",
        "manual_review_required": False,
        "reason_codes": ["single_operation"],
        "evidence_excerpt": list(source_item["evidence_excerpt"]),
        "matched_detail_rows": list(matched_rows),
        "parent_segment": "",
        "equipment_child_segment": "",
        "equipment_split_applied": False,
        "equipment_types": [],
        "equipment_models": [],
        "equipment_support_result": "neutral",
        "equipment_support_reason": "",
        "suggestion_type": "single",
        "recommendation_label": "",
        "recommendation_reason": "",
        "recommended_target_name": op_name or "未命名工序段",
        "_source_items": [source_item],
        "_raw_first_sequence": sequence,
        "_first_index": int(source_item["index"]),
        "_coverage_hit": coverage_hit,
        "_coverage_total": coverage_total,
    }


def build_initial_merge_groups(operations: list[dict], detail_rows: list[DocumentOperationDetail]) -> list[dict]:
    ordered_operations = sorted(
        [dict(item, _index=index) for index, item in enumerate(operations, start=1)],
        key=lambda item: (int(item.get("sequence") or 0), int(item.get("id") or 0)),
    )
    source_groups_by_id = {
        int(op.get("id") or 0): build_source_group_from_operation(op, detail_rows)
        for op in ordered_operations
        if int(op.get("id") or 0) > 0
    }
    candidate_groups: list[dict[str, object]] = []
    claimed_operation_ids: set[int] = set()

    for rule in DIRECT_MERGE_RULES:
        required_names = {_normalize_operation_name(str(item)) for item in rule.get("required_names", set())}
        matched_ops = [
            op for op in ordered_operations
            if _normalize_operation_name(str(op.get("name") or "")) in required_names
            and int(op.get("id") or 0) not in claimed_operation_ids
        ]
        if {_normalize_operation_name(str(op.get("name") or "")) for op in matched_ops} != required_names:
            continue
        members = [source_groups_by_id[int(op.get("id") or 0)] for op in matched_ops if int(op.get("id") or 0) in source_groups_by_id]
        if len(members) < 2:
            continue
        merged_name = (
            _display_operation_name(rule["standard_name"])
            if bool(rule.get("prefer_standard_name"))
            else _default_direct_merge_name(members, str(rule["standard_name"]))
        )
        candidate_groups.append(_build_group_payload_from_members(
            group_id=f"segment-{rule['key']}",
            group_key=str(rule["key"]),
            normalized_step_name=merged_name,
            members=members,
            detail_rows=detail_rows,
            review_status="pending",
            suggestion_type="direct_merge",
            recommendation_label=str(rule["recommendation_label"]),
            recommendation_reason=str(rule["recommendation_reason"]),
            step_family=str(rule["step_family"]),
            phase=str(rule["phase"]),
            manual_review_required=False,
            reason_codes=list(rule.get("reason_codes") or ["same_process_intent", "naming_variant", "direct_merge"]),
        ))
        claimed_operation_ids.update(int(op.get("id") or 0) for op in matched_ops if int(op.get("id") or 0) > 0)

    absorb_members_by_parent_id: dict[int, dict[str, object]] = {}

    for rule in ABSORB_INTO_PARENT_RULES:
        child_names = _rule_name_set(rule, "child_name", "child_names")
        parent_names = _rule_name_set(rule, "parent_name", "parent_names")
        child_ops = [
            op for op in ordered_operations
            if _normalize_operation_name(str(op.get("name") or "")) in child_names
            and int(op.get("id") or 0) not in claimed_operation_ids
        ]
        if not child_ops:
            continue
        parent_ops = [
            op for op in ordered_operations
            if _normalize_operation_name(str(op.get("name") or "")) in parent_names
            and int(op.get("id") or 0) not in claimed_operation_ids
        ]
        if not parent_ops:
            continue

        for child_op in child_ops:
            parent_op = next(
                (
                    candidate for candidate in parent_ops
                    if _is_absorb_candidate_pair(
                        child_operation=child_op,
                        parent_operation=candidate,
                        rule=rule,
                    )
                ),
                None,
            )
            if not parent_op:
                continue
            child_id = int(child_op.get("id") or 0)
            parent_id = int(parent_op.get("id") or 0)
            if child_id <= 0 or parent_id <= 0:
                continue
            bucket = absorb_members_by_parent_id.setdefault(parent_id, {
                "parent_op": parent_op,
                "child_ids": [],
                "keys": [],
                "reasons": [],
                "reason_codes": [],
                "step_family": str(rule["step_family"]),
                "phase": str(rule["phase"]),
                "recommendation_label": str(rule["recommendation_label"]),
            })
            child_ids = bucket["child_ids"]
            if isinstance(child_ids, list) and child_id not in child_ids:
                child_ids.append(child_id)
            keys = bucket["keys"]
            if isinstance(keys, list):
                keys.append(str(rule["key"]))
            reasons = bucket["reasons"]
            if isinstance(reasons, list):
                reason_text = str(rule["recommendation_reason"])
                if reason_text not in reasons:
                    reasons.append(reason_text)
            reason_codes = bucket["reason_codes"]
            if isinstance(reason_codes, list):
                for code in list(rule.get("reason_codes") or ["covered_by_parent_steps", "local_content_promoted", "absorb_into_parent"]):
                    if code not in reason_codes:
                        reason_codes.append(code)
            claimed_operation_ids.add(child_id)

    for parent_id, bucket in absorb_members_by_parent_id.items():
        parent_op = bucket.get("parent_op")
        if not isinstance(parent_op, dict):
            continue
        child_ids = [int(item or 0) for item in bucket.get("child_ids") or [] if int(item or 0) > 0]
        member_ids = [parent_id, *child_ids]
        members = [
            source_groups_by_id[member_id]
            for member_id in member_ids
            if member_id in source_groups_by_id
        ]
        if len(members) < 2:
            continue
        keys = [str(item) for item in bucket.get("keys") or [] if str(item).strip()]
        reasons = [str(item) for item in bucket.get("reasons") or [] if str(item).strip()]
        candidate_groups.append(_build_group_payload_from_members(
            group_id=f"segment-{'-'.join(keys) or 'absorb'}-{parent_id}-{'-'.join(str(item) for item in child_ids)}",
            group_key=";".join(keys) or "absorb_into_parent",
            normalized_step_name=_display_operation_name(parent_op.get("name")),
            members=members,
            detail_rows=detail_rows,
            review_status="pending",
            suggestion_type="absorb_into_parent",
            recommendation_label=str(bucket.get("recommendation_label") or "并入上位工序"),
            recommendation_reason="；".join(reasons),
            step_family=str(bucket.get("step_family") or "车削类"),
            phase=str(bucket.get("phase") or "rough"),
            parent_segment=_display_operation_name(parent_op.get("name")),
            manual_review_required=True,
            reason_codes=list(bucket.get("reason_codes") or ["covered_by_parent_steps", "local_content_promoted", "absorb_into_parent"]),
        ))
        claimed_operation_ids.add(parent_id)

    for rule in KEEP_SEPARATE_RULES:
        required_names = {_normalize_operation_name(str(item)) for item in rule.get("required_names", set())}
        matched_ops = [
            op for op in ordered_operations
            if _normalize_operation_name(str(op.get("name") or "")) in required_names
            and int(op.get("id") or 0) not in claimed_operation_ids
        ]
        if {_normalize_operation_name(str(op.get("name") or "")) for op in matched_ops} != required_names:
            continue
        members = [source_groups_by_id[int(op.get("id") or 0)] for op in matched_ops if int(op.get("id") or 0) in source_groups_by_id]
        if len(members) < 2:
            continue
        candidate_groups.append(_build_group_payload_from_members(
            group_id=f"segment-{rule['key']}",
            group_key=str(rule["key"]),
            normalized_step_name=_display_operation_name(rule["display_name"]),
            members=members,
            detail_rows=detail_rows,
            review_status="kept",
            suggestion_type="keep_separate",
            recommendation_label=str(rule["recommendation_label"]),
            recommendation_reason=str(rule["recommendation_reason"]),
            step_family=str(rule["step_family"]),
            phase=str(rule["phase"]),
            manual_review_required=False,
            reason_codes=["same_broad_family", "different_process_intent", "keep_separate"],
        ))
        claimed_operation_ids.update(int(op.get("id") or 0) for op in matched_ops if int(op.get("id") or 0) > 0)

    candidate_by_op_id: dict[int, dict[str, object]] = {}
    for group in candidate_groups:
        for op_id in group.get("source_operation_ids") or []:
            parsed_id = int(op_id or 0)
            if parsed_id > 0:
                candidate_by_op_id[parsed_id] = group

    final_groups: list[dict[str, object]] = []
    emitted_group_ids: set[str] = set()
    for op in ordered_operations:
        op_id = int(op.get("id") or 0)
        if op_id <= 0:
            continue
        candidate = candidate_by_op_id.get(op_id)
        if candidate:
            candidate_id = str(candidate.get("id") or "")
            if candidate_id and candidate_id not in emitted_group_ids:
                final_groups.append(candidate)
                emitted_group_ids.add(candidate_id)
            continue
        final_groups.append(source_groups_by_id[op_id])

    terminal_release_ids = _route_merge_terminal_release_ids(final_groups)
    final_groups.sort(key=lambda item: _route_merge_sort_key(item, terminal_release_ids))
    return final_groups


__all__ = ["build_initial_merge_groups", "build_source_group_from_operation"]
