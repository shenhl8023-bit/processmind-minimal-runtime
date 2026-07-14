"""
第二步路线归并工作台的构建与快照持久化。

当前版本不再走“标准段 + 设备细分”的粗归并路线，
而是严格基于左侧工序工步树，按下面三类推荐生成候选组：
- 直接归并：加工意图相同，仅命名口径不同
- 并入上位工序：独立工序更像前序主工序中的局部内容
- 不建议归并：名称相近，但方法、精度或对象不同
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import re
from collections.abc import Awaitable, Callable

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import DocumentOperationDetail, RouteMergeSnapshot
from app.services.route_merge.config import (
    ROUTE_MERGE_ALGO_VERSION,
)
from app.services.route_merge.equipment import extract_detail_excerpt
from app.services.route_merge.group_builder import (
    build_initial_merge_groups,
    build_source_group_from_operation,
)
from app.services.route_merge.operation_names import (
    detail_row_atomic_names,
    split_composite_operation_name,
)
from app.services.route_merge.saved_route_segments import build_saved_route_version_segments
from app.services.route_merge.source_lookup import (
    build_route_item_source_lookup,
)
from app.services.route_merge.sorting import (
    display_operation_name as _display_operation_name,
    infer_operation_phase as _infer_operation_phase,
    merge_family_key,
    normalize_operation_name as _normalize_operation_name,
    route_item_phase as _route_item_phase,
    route_item_value as _route_item_value,
    route_merge_sort_key as _route_merge_sort_key,
    route_merge_terminal_release_ids as _route_merge_terminal_release_ids,
    sequence_sort_value as _sequence_sort_value,
    sort_route_items_with_terminal_release,
)

ROUTE_MERGE_BUILD_LOCKS: dict[int, asyncio.Lock] = {}


def _clean_text_line(line: str) -> str:
    return re.sub(r"\s+", "", line or "").strip()


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


def _suggested_action_for_group(group: dict[str, object]) -> str:
    suggestion_type = str(group.get("suggestion_type") or "")
    review_status = str(group.get("review_status") or "pending")
    if suggestion_type == "direct_merge":
        return "accept_merge" if review_status == "pending" else "keep"
    if suggestion_type == "absorb_into_parent":
        return "merge_into_parent" if review_status == "pending" else "keep"
    if suggestion_type == "keep_separate":
        return "keep_separate"
    return "keep"


def _build_non_merged_route_items(group: dict[str, object]) -> list[dict[str, object]]:
    source_items = list(group.get("_source_items") or [])
    if not source_items:
        return [{
            "id": str(group.get("id") or ""),
            "normalized_step_name": _display_operation_name(group.get("normalized_step_name")) or "未命名工序段",
            "step_family": str(group.get("step_family") or ""),
            "phase": str(group.get("phase") or ""),
            "source_nodes": [_display_operation_name(item) for item in list(group.get("source_nodes") or []) if _display_operation_name(item)],
            "source_operation_ids": list(group.get("source_operation_ids") or []),
            "review_status": str(group.get("review_status") or "kept"),
            "source_type": "split_from_non_merged_group",
            "coverage_label": str(group.get("coverage_label") or ""),
            "separator_result": str(group.get("separator_result") or "pass"),
            "manual_review_required": False,
            "reason_codes": ["split_from_non_merged_group"],
            "evidence_excerpt": list(group.get("evidence_excerpt") or []),
            "matched_detail_rows": list(group.get("matched_detail_rows") or []),
            "parent_segment": _display_operation_name(group.get("parent_segment")),
            "equipment_child_segment": "",
            "equipment_split_applied": False,
            "equipment_types": [],
            "equipment_models": [],
            "equipment_support_result": "neutral",
            "equipment_support_reason": "",
        }]

    route_items: list[dict[str, object]] = []
    for item in source_items:
        route_items.append({
            "id": str(item.get("group_id") or item.get("id") or ""),
            "normalized_step_name": _display_operation_name(item.get("name")) or "未命名工序段",
            "step_family": str(item.get("step_family") or ""),
            "phase": str(item.get("phase") or ""),
            "source_nodes": [
                _display_operation_name(node)
                for node in list(item.get("source_nodes") or [str(item.get("name") or "")])
                if _display_operation_name(node)
            ],
            "source_operation_ids": [int(item.get("id") or 0)] if int(item.get("id") or 0) > 0 else [],
            "review_status": "kept",
            "source_type": "split_from_non_merged_group",
            "coverage_label": str(item.get("coverage_label") or ""),
            "separator_result": "pass",
            "manual_review_required": False,
            "reason_codes": ["split_from_non_merged_group"],
            "evidence_excerpt": list(item.get("evidence_excerpt") or []),
            "matched_detail_rows": list(item.get("matched_detail_rows") or []),
            "parent_segment": "",
            "equipment_child_segment": "",
            "equipment_split_applied": False,
            "equipment_types": [],
            "equipment_models": [],
            "equipment_support_result": "neutral",
            "equipment_support_reason": "",
            "_raw_first_sequence": int(item.get("sequence") or 0),
            "_first_index": int(item.get("index") or 0),
        })
    return route_items


def build_merge_suggestions_from_groups(groups: list[dict]) -> list[dict]:
    suggestions: list[dict] = []
    terminal_release_ids = _route_merge_terminal_release_ids(groups)
    ordered_groups = sorted(
        groups,
        key=lambda item: _route_merge_sort_key(item, terminal_release_ids),
    )
    for index, group in enumerate(ordered_groups, start=1):
        suggestions.append({
            "suggestion_id": f"suggestion-{group['id']}",
            "target_group_id": group["id"],
            "sequence": index * 10,
            "source_nodes": list(group.get("source_nodes") or []),
            "source_operation_ids": list(group.get("source_operation_ids") or []),
            "normalized_step_name": _display_operation_name(group.get("normalized_step_name")) or "未命名工序段",
            "step_family": group.get("step_family") or "",
            "phase": group.get("phase") or "",
            "separator_result": group.get("separator_result") or "pass",
            "manual_review_required": bool(group.get("manual_review_required")),
            "reason_codes": list(group.get("reason_codes") or []),
            "evidence_excerpt": list(group.get("evidence_excerpt") or []),
            "matched_detail_rows": list(group.get("matched_detail_rows") or []),
            "parent_segment": _display_operation_name(group.get("parent_segment")),
            "equipment_child_segment": "",
            "equipment_split_applied": False,
            "equipment_types": [],
            "equipment_models": [],
            "equipment_support_result": "neutral",
            "equipment_support_reason": "",
            "suggestion_type": str(group.get("suggestion_type") or "single"),
            "recommendation_label": str(group.get("recommendation_label") or ""),
            "recommendation_reason": str(group.get("recommendation_reason") or ""),
            "recommended_target_name": _display_operation_name(group.get("recommended_target_name") or group.get("normalized_step_name")) or "未命名工序段",
            "suggested_action": _suggested_action_for_group(group),
            "status": group.get("review_status") or "pending",
        })
    return suggestions


def build_normalized_route_from_groups(groups: list[dict]) -> list[dict]:
    terminal_release_group_ids = _route_merge_terminal_release_ids(groups)
    ordered_groups = sorted(
        groups,
        key=lambda item: _route_merge_sort_key(item, terminal_release_group_ids),
    )
    normalized: list[dict] = []

    for group in ordered_groups:
        if int(len(group.get("source_operation_ids") or [])) > 1 and str(group.get("review_status") or "") != "merged":
            normalized.extend(_build_non_merged_route_items(group))
            continue
        normalized.append({
            "id": str(group.get("id") or ""),
            "normalized_step_name": _display_operation_name(group.get("normalized_step_name")) or "未命名工序段",
            "step_family": str(group.get("step_family") or ""),
            "phase": str(group.get("phase") or ""),
            "source_nodes": [_display_operation_name(item) for item in list(group.get("source_nodes") or []) if _display_operation_name(item)],
            "source_operation_ids": list(group.get("source_operation_ids") or []),
            "review_status": str(group.get("review_status") or "pending"),
            "source_type": str(group.get("source_type") or "system_generated"),
            "coverage_label": str(group.get("coverage_label") or ""),
            "separator_result": str(group.get("separator_result") or "pass"),
            "manual_review_required": bool(group.get("manual_review_required")),
            "reason_codes": list(group.get("reason_codes") or []),
            "evidence_excerpt": list(group.get("evidence_excerpt") or []),
            "matched_detail_rows": list(group.get("matched_detail_rows") or []),
            "parent_segment": _display_operation_name(group.get("parent_segment")),
            "equipment_child_segment": "",
            "equipment_split_applied": False,
            "equipment_types": [],
            "equipment_models": [],
            "equipment_support_result": "neutral",
            "equipment_support_reason": "",
            "_raw_first_sequence": int(group.get("_raw_first_sequence") or group.get("sequence") or 0),
            "_first_index": int(group.get("_first_index") or 0),
        })

    terminal_release_item_ids = _route_merge_terminal_release_ids(normalized)
    normalized.sort(key=lambda item: _route_merge_sort_key(item, terminal_release_item_ids))
    route_items: list[dict] = []
    for index, item in enumerate(normalized, start=1):
        route_items.append({
            "id": str(item.get("id") or ""),
            "sequence": index * 10,
            "normalized_step_name": _display_operation_name(item.get("normalized_step_name")) or "未命名工序段",
            "step_family": str(item.get("step_family") or ""),
            "phase": str(item.get("phase") or ""),
            "source_nodes": [_display_operation_name(source_name) for source_name in list(item.get("source_nodes") or []) if _display_operation_name(source_name)],
            "source_operation_ids": list(item.get("source_operation_ids") or []),
            "review_status": str(item.get("review_status") or "pending"),
            "source_type": str(item.get("source_type") or "system_generated"),
            "coverage_label": str(item.get("coverage_label") or ""),
            "separator_result": str(item.get("separator_result") or "pass"),
            "manual_review_required": bool(item.get("manual_review_required")),
            "reason_codes": list(item.get("reason_codes") or []),
            "evidence_excerpt": list(item.get("evidence_excerpt") or []),
            "matched_detail_rows": list(item.get("matched_detail_rows") or []),
            "parent_segment": _display_operation_name(item.get("parent_segment")),
            "equipment_child_segment": "",
            "equipment_split_applied": False,
            "equipment_types": [],
            "equipment_models": [],
            "equipment_support_result": "neutral",
            "equipment_support_reason": "",
        })
    return route_items


def route_merge_source_signature(operations: list[dict], detail_rows: list[DocumentOperationDetail]) -> str:
    op_keys = sorted(f"{item.get('id')}:{item.get('name')}:{item.get('sequence')}" for item in operations)
    detail_keys = sorted(
        (
            f"{row.document_id}:{row.operation_seq}:{row.operation_name}:{row.page_no}:"
            f"{row.normalized_name or ''}:{row.operation_content or ''}:"
            f"{row.equipment_types or ''}:{row.equipment_models or ''}"
        )
        for row in detail_rows
    )
    payload = json.dumps(
        {"operations": op_keys, "details": detail_keys},
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()
    return f"{ROUTE_MERGE_ALGO_VERSION}|ops={len(op_keys)}|details={len(detail_keys)}|sha256={digest}"


async def get_latest_route_merge_snapshot(project_id: int, db: AsyncSession) -> RouteMergeSnapshot | None:
    return (
        await db.execute(
            select(RouteMergeSnapshot)
            .where(RouteMergeSnapshot.project_id == project_id)
            .order_by(RouteMergeSnapshot.updated_at.desc(), RouteMergeSnapshot.id.desc())
        )
    ).scalars().first()


async def save_route_merge_snapshot(
    project_id: int,
    db: AsyncSession,
    payload: dict[str, object],
    review_state: dict[str, object] | None = None,
) -> dict[str, object]:
    latest = await get_latest_route_merge_snapshot(project_id, db)
    review_state = review_state if review_state is not None else dict(payload.get("review_state") or {})
    if not latest:
        latest = RouteMergeSnapshot(project_id=project_id)
        db.add(latest)
    latest.source_signature = str(payload.get("source_signature") or "")
    latest.superset_route_json = json.dumps(payload.get("superset_route") or [], ensure_ascii=False)
    latest.merge_groups_json = json.dumps(payload.get("merge_groups") or [], ensure_ascii=False)
    latest.merge_suggestions_json = json.dumps(payload.get("merge_suggestions") or [], ensure_ascii=False)
    latest.normalized_superset_route_json = json.dumps(payload.get("normalized_superset_route") or [], ensure_ascii=False)
    latest.review_state_json = json.dumps(review_state, ensure_ascii=False)
    await db.flush()
    payload["review_state"] = review_state
    return payload


def build_route_merge_snapshot_payload(
    project_id: int,
    raw_operations: list[dict],
    detail_rows: list[DocumentOperationDetail],
) -> dict[str, object]:
    groups = build_initial_merge_groups(raw_operations, detail_rows)
    suggestions = build_merge_suggestions_from_groups(groups)
    normalized_route = build_normalized_route_from_groups(groups)
    return {
        "project_id": project_id,
        "superset_route": raw_operations,
        "merge_groups": groups,
        "merge_suggestions": suggestions,
        "normalized_superset_route": normalized_route,
        "source_signature": route_merge_source_signature(raw_operations, detail_rows),
    }


async def ensure_route_merge_snapshot(
    project_id: int,
    db: AsyncSession,
    load_superset_route: Callable[[], Awaitable[list[dict]]],
    load_detail_rows: Callable[[], Awaitable[list[DocumentOperationDetail]]],
) -> dict[str, object]:
    async def _load_snapshot_payload() -> dict[str, object] | None:
        latest = await get_latest_route_merge_snapshot(project_id, db)
        if not latest:
            return None
        try:
            payload = {
                "project_id": project_id,
                "superset_route": json.loads(latest.superset_route_json or "[]"),
                "merge_groups": json.loads(latest.merge_groups_json or "[]"),
                "merge_suggestions": json.loads(latest.merge_suggestions_json or "[]"),
                "normalized_superset_route": json.loads(latest.normalized_superset_route_json or "[]"),
                "source_signature": latest.source_signature or "",
                "review_state": json.loads(latest.review_state_json or "{}"),
            }
            if not str(payload.get("source_signature") or "").startswith(f"{ROUTE_MERGE_ALGO_VERSION}|"):
                raise ValueError("stale_route_merge_snapshot")
            detail_count = int(
                (
                    await db.execute(
                        select(func.count())
                        .select_from(DocumentOperationDetail)
                        .where(DocumentOperationDetail.project_id == project_id)
                    )
                ).scalar_one()
                or 0
            )
            has_detail_evidence = any(
                group.get("matched_detail_rows") or group.get("evidence_excerpt")
                for group in payload.get("merge_groups") or []
            )
            if detail_count > 0 or not payload.get("merge_groups") or has_detail_evidence:
                return payload
        except Exception:
            return None
        return None

    cached = await _load_snapshot_payload()
    if cached:
        return cached

    lock = ROUTE_MERGE_BUILD_LOCKS.setdefault(project_id, asyncio.Lock())
    async with lock:
        cached = await _load_snapshot_payload()
        if cached:
            return cached

        raw_operations = await load_superset_route()
        detail_rows = await load_detail_rows()
        payload = build_route_merge_snapshot_payload(project_id, raw_operations, detail_rows)
        await save_route_merge_snapshot(project_id, db, payload, review_state={})
        await db.commit()
        return payload

async def persist_normalized_superset_route(
    *,
    project_id: int,
    db: AsyncSession,
    snapshot: dict[str, object],
    items: list[object],
    detail_rows: list[DocumentOperationDetail] | None = None,
    total_docs: int = 0,
) -> list[dict[str, object]]:
    source_lookup = build_route_item_source_lookup(
        list(snapshot.get("merge_groups") or []) or list(snapshot.get("normalized_superset_route") or [])
    )
    normalized_route = build_saved_route_version_segments(
        items,
        detail_rows or [],
        total_docs,
        source_lookup=source_lookup,
    )

    snapshot["normalized_superset_route"] = normalized_route
    review_state = dict(snapshot.get("review_state") or {})
    review_state["_manual_normalized_route_saved"] = True
    review_state["_manual_normalized_route_count"] = len(normalized_route)
    snapshot["review_state"] = review_state
    await save_route_merge_snapshot(
        project_id,
        db,
        snapshot,
        review_state=review_state,
    )
    await db.commit()
    return normalized_route


def find_group_index(groups: list[dict], group_id: str) -> int:
    for idx, group in enumerate(groups):
        if str(group.get("id") or "") == group_id:
            return idx
    return -1


__all__ = [
    "build_initial_merge_groups",
    "build_route_merge_snapshot_payload",
    "build_merge_suggestions_from_groups",
    "build_normalized_route_from_groups",
    "build_source_group_from_operation",
    "detail_row_atomic_names",
    "ensure_route_merge_snapshot",
    "find_group_index",
    "get_latest_route_merge_snapshot",
    "build_route_item_source_lookup",
    "build_saved_route_version_segments",
    "merge_family_key",
    "persist_normalized_superset_route",
    "route_merge_source_signature",
    "save_route_merge_snapshot",
    "sort_route_items_with_terminal_release",
    "split_composite_operation_name",
]
