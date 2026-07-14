"""
第二步路线归并审核动作。
"""

from __future__ import annotations

from app.services.process_knowledge import canonicalize_route_label
from app.services.route_merge.workspace import (
    build_merge_suggestions_from_groups,
    build_normalized_route_from_groups,
    build_source_group_from_operation,
    find_group_index,
)


def apply_merge_suggestion_review(
    snapshot: dict[str, object],
    suggestion_id: str,
    action: str,
    manual_label: str,
    operations_by_id: dict[int, dict],
    detail_rows: list,
) -> dict[str, object]:
    groups = list(snapshot.get("merge_groups") or [])
    suggestions = list(snapshot.get("merge_suggestions") or [])
    target_group_id = ""
    for suggestion in suggestions:
        if str(suggestion.get("suggestion_id") or "") == suggestion_id:
            target_group_id = str(suggestion.get("target_group_id") or "")
            break
    if not target_group_id:
        raise KeyError("missing_suggestion")

    group_idx = find_group_index(groups, target_group_id)
    if group_idx < 0:
        raise KeyError("missing_group")

    current = dict(groups[group_idx])
    normalized_action = (action or "").strip().lower()
    if normalized_action == "accept":
        current["review_status"] = "merged"
        groups[group_idx] = current
    elif normalized_action == "reject":
        split_groups = []
        for source_op_id in [int(item) for item in current.get("source_operation_ids") or [] if int(item) > 0]:
            operation = operations_by_id.get(source_op_id)
            if not operation:
                continue
            split_groups.append(build_source_group_from_operation(operation, detail_rows))
        if split_groups:
            groups = [*groups[:group_idx], *split_groups, *groups[group_idx + 1 :]]
        else:
            current["review_status"] = "kept"
            groups[group_idx] = current
    elif normalized_action == "rename":
        current["normalized_step_name"] = (
            canonicalize_route_label(manual_label.strip())
            or current.get("normalized_step_name")
            or "未命名工序段"
        )
        current["source_type"] = "manual_adjusted"
        current["review_status"] = current.get("review_status") or "pending"
        groups[group_idx] = current
    elif normalized_action == "unsure":
        current["review_status"] = "conflict"
        groups[group_idx] = current
    else:
        raise ValueError("unsupported_action")

    snapshot["merge_groups"] = groups
    snapshot["merge_suggestions"] = build_merge_suggestions_from_groups(groups)
    snapshot["normalized_superset_route"] = build_normalized_route_from_groups(groups)
    review_state = dict(snapshot.get("review_state") or {})
    review_state[suggestion_id] = {
        "action": normalized_action,
        "manual_label": canonicalize_route_label(manual_label.strip()),
    }
    snapshot["review_state"] = review_state
    return snapshot


__all__ = [
    "apply_merge_suggestion_review",
]
