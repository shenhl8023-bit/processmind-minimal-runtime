"""
已保存标准化路线的轻量序列化与排序辅助。
"""

from __future__ import annotations

import json
from collections import defaultdict

from app.models.models import (
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
)
from app.schemas.schemas import (
    SavedNormalizedRouteVersionOut,
    SegmentFactorReviewOut,
    SegmentRuleReviewOut,
)
from app.services.route_merge.workspace import sort_route_items_with_terminal_release
from app.services.rule_packages.condition_reviews import serialize_condition_review


def serialize_saved_normalized_route_version(version_row: NormalizedRouteVersion) -> SavedNormalizedRouteVersionOut:
    try:
        segments = json.loads(version_row.route_json or "[]")
    except Exception:
        segments = []
    return SavedNormalizedRouteVersionOut(
        route_id=version_row.id,
        project_id=version_row.project_id,
        version=version_row.version,
        source_signature=version_row.source_signature or "",
        saved_by=version_row.saved_by or "默认用户",
        saved_at=version_row.created_at,
        total_docs=int(version_row.total_docs or 0),
        segment_count=int(version_row.segment_count or 0),
        segments=list(segments or []),
    )


def serialize_segment_factor_review(row: NormalizedRouteSegmentFactorReview) -> SegmentFactorReviewOut:
    try:
        evidence_refs = json.loads(row.evidence_refs_json or "[]")
    except Exception:
        evidence_refs = []
    try:
        source_operation_ids = [int(item) for item in json.loads(row.source_operation_ids_json or "[]")]
    except Exception:
        source_operation_ids = []
    try:
        source_operation_names = [str(item or "") for item in json.loads(row.source_operation_names_json or "[]")]
    except Exception:
        source_operation_names = []
    return SegmentFactorReviewOut(
        id=row.id,
        factor_name=row.factor_name or "",
        decision=row.decision or "confirmed",
        note=row.note or "",
        source_type=row.source_type or "aggregated",
        evidence_refs=list(evidence_refs or []),
        source_operation_ids=list(source_operation_ids or []),
        source_operation_names=list(source_operation_names or []),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def serialize_segment_rule_review(row: NormalizedRouteSegmentRuleReview) -> SegmentRuleReviewOut:
    try:
        summary_lines = [str(item or "") for item in json.loads(row.summary_json or "[]")]
    except Exception:
        summary_lines = []
    try:
        question_trail = [
            {
                "nodeId": str(item.get("nodeId") or ""),
                "value": str(item.get("value") or ""),
                "label": str(item.get("label") or ""),
            }
            for item in json.loads(row.question_trail_json or "[]")
            if isinstance(item, dict)
        ]
    except Exception:
        question_trail = []
    return SegmentRuleReviewOut(
        id=row.id,
        decision=row.decision or "accepted",
        note=row.note or "",
        summary_lines=list(summary_lines or []),
        question_trail=list(question_trail or []),
        condition_review=serialize_condition_review(row),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def sort_and_resequence_saved_route(items: list[dict[str, object]]) -> list[dict[str, object]]:
    ordered = sort_route_items_with_terminal_release(list(items or []))
    for index, item in enumerate(ordered, start=1):
        item["sequence"] = index * 10
    return ordered


def group_factor_reviews_by_segment(
    rows: list[NormalizedRouteSegmentFactorReview],
) -> dict[str, list[SegmentFactorReviewOut]]:
    grouped: dict[str, list[SegmentFactorReviewOut]] = defaultdict(list)
    for row in rows:
        grouped[str(row.segment_id or "")].append(serialize_segment_factor_review(row))
    return grouped


def group_rule_reviews_by_segment(
    rows: list[NormalizedRouteSegmentRuleReview],
) -> dict[str, SegmentRuleReviewOut]:
    grouped: dict[str, SegmentRuleReviewOut] = {}
    for row in rows:
        key = str(row.segment_id or "")
        if key not in grouped:
            grouped[key] = serialize_segment_rule_review(row)
    return grouped


__all__ = [
    "group_factor_reviews_by_segment",
    "group_rule_reviews_by_segment",
    "serialize_saved_normalized_route_version",
    "serialize_segment_factor_review",
    "serialize_segment_rule_review",
    "sort_and_resequence_saved_route",
]
