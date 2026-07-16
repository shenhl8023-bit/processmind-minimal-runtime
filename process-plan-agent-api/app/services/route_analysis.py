import hashlib
import json
from typing import Any, Awaitable, Callable

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import (
    Document,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
)
from app.schemas.schemas import (
    SavedNormalizedRouteSegmentOut,
    SavedNormalizedRouteVersionOut,
    SegmentRuleReviewSaveOut,
)
from app.services.route_analysis_helpers import (
    group_factor_reviews_by_segment,
    group_rule_reviews_by_segment,
    serialize_saved_normalized_route_version,
    serialize_segment_rule_review,
    sort_and_resequence_saved_route,
)
from app.services.route_merge.workspace import (
    build_route_item_source_lookup,
    build_saved_route_version_segments,
    get_latest_route_merge_snapshot,
)
from app.services.process_knowledge import canonicalize_route_label


def canonical_normalized_route_json(normalized_route: list[dict[str, object]] | list[Any] | Any) -> str:
    """Stable JSON for route content comparison (key order independent)."""
    return json.dumps(normalized_route, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def normalized_route_content_hash(normalized_route: list[dict[str, object]] | list[Any] | Any) -> str:
    return hashlib.sha256(canonical_normalized_route_json(normalized_route).encode("utf-8")).hexdigest()


def parse_route_json(route_json: str | None) -> list[Any]:
    try:
        payload = json.loads(route_json or "[]")
    except Exception:
        return []
    return payload if isinstance(payload, list) else []


async def get_latest_normalized_route_version(
    project_id: int,
    db: AsyncSession,
) -> NormalizedRouteVersion | None:
    return (
        await db.execute(
            select(NormalizedRouteVersion)
            .where(NormalizedRouteVersion.project_id == project_id)
            .order_by(NormalizedRouteVersion.version.desc(), NormalizedRouteVersion.id.desc())
        )
    ).scalars().first()


async def load_route_factor_reviews(
    route_id: int,
    db: AsyncSession,
) -> dict[str, list[object]]:
    try:
        rows = (
            await db.execute(
                select(NormalizedRouteSegmentFactorReview)
                .where(NormalizedRouteSegmentFactorReview.route_version_id == route_id)
                .order_by(
                    NormalizedRouteSegmentFactorReview.updated_at.desc(),
                    NormalizedRouteSegmentFactorReview.id.desc(),
                )
            )
        ).scalars().all()
    except OperationalError:
        return {}
    return group_factor_reviews_by_segment(list(rows or []))


async def load_route_rule_reviews(
    route_id: int,
    db: AsyncSession,
) -> dict[str, object]:
    try:
        rows = (
            await db.execute(
                select(NormalizedRouteSegmentRuleReview)
                .where(NormalizedRouteSegmentRuleReview.route_version_id == route_id)
                .order_by(
                    NormalizedRouteSegmentRuleReview.updated_at.desc(),
                    NormalizedRouteSegmentRuleReview.id.desc(),
                )
            )
        ).scalars().all()
    except OperationalError:
        return {}
    return group_rule_reviews_by_segment(list(rows or []))


async def save_normalized_route_version(
    *,
    project_id: int,
    db: AsyncSession,
    source_signature: str,
    total_docs: int,
    normalized_route: list[dict[str, object]],
) -> NormalizedRouteVersion:
    latest = await get_latest_normalized_route_version(project_id, db)
    if latest:
        latest_items = parse_route_json(latest.route_json)
        if normalized_route_content_hash(latest_items) == normalized_route_content_hash(normalized_route):
            # Same route content: reuse current version (no bump). Refresh metadata if needed.
            dirty = False
            if str(latest.source_signature or "") != str(source_signature or ""):
                latest.source_signature = source_signature
                dirty = True
            if int(latest.total_docs or 0) != int(total_docs):
                latest.total_docs = total_docs
                dirty = True
            if int(latest.segment_count or 0) != len(normalized_route):
                latest.segment_count = len(normalized_route)
                dirty = True
            if dirty:
                await db.commit()
                await db.refresh(latest)
            return latest

    version_number = int(latest.version or 0) + 1 if latest else 1
    version_row = NormalizedRouteVersion(
        project_id=project_id,
        version=version_number,
        source_signature=source_signature,
        saved_by="默认用户",
        total_docs=total_docs,
        segment_count=len(normalized_route),
        route_json=json.dumps(normalized_route, ensure_ascii=False),
    )
    db.add(version_row)
    await db.commit()
    await db.refresh(version_row)
    return version_row


async def ensure_saved_normalized_route_version(
    project_id: int,
    db: AsyncSession,
    ensure_detail_rows: Callable[[], Awaitable[list]],
) -> NormalizedRouteVersion | None:
    snapshot_row = await get_latest_route_merge_snapshot(project_id, db)
    detail_rows = await ensure_detail_rows()
    docs = (
        await db.execute(
            select(Document.id).where(Document.project_id == project_id)
        )
    ).all()
    total_docs = len(docs)

    def _build_source_lookup() -> dict[int, dict[str, object]]:
        if not snapshot_row:
            return {}
        try:
            merge_groups = json.loads(snapshot_row.merge_groups_json or "[]")
        except Exception:
            merge_groups = []
        lookup = build_route_item_source_lookup(list(merge_groups or []))
        if lookup:
            return lookup
        try:
            normalized_route = json.loads(snapshot_row.normalized_superset_route_json or "[]")
        except Exception:
            normalized_route = []
        return build_route_item_source_lookup(list(normalized_route or []))

    source_lookup = _build_source_lookup()
    snapshot_items: list[object] = []
    if snapshot_row:
        try:
            snapshot_items = json.loads(snapshot_row.normalized_superset_route_json or "[]")
        except Exception:
            snapshot_items = []
    latest = await get_latest_normalized_route_version(project_id, db)
    if latest:
        try:
            latest_items = json.loads(latest.route_json or "[]")
        except Exception:
            latest_items = []
        latest_names_by_id = {
            str(item.get("id") or ""): str(item.get("normalized_step_name") or "").strip()
            for item in latest_items
            if isinstance(item, dict) and str(item.get("id") or "") and str(item.get("normalized_step_name") or "").strip()
        }
        rebuilt_route = build_saved_route_version_segments(
            latest_items or snapshot_items,
            detail_rows,
            total_docs,
            source_lookup=source_lookup,
        )
        rebuilt_route = sort_and_resequence_saved_route(rebuilt_route)
        for item in rebuilt_route:
            if not isinstance(item, dict):
                continue
            preserved_name = latest_names_by_id.get(str(item.get("id") or ""))
            if preserved_name:
                item["normalized_step_name"] = preserved_name
        rebuilt_route_json = json.dumps(rebuilt_route, ensure_ascii=False)
        if (
            rebuilt_route
            and (
                rebuilt_route_json != (latest.route_json or "[]")
                or int(latest.total_docs or 0) != total_docs
                or int(latest.segment_count or 0) != len(rebuilt_route)
                or (
                    snapshot_row
                    and snapshot_row.source_signature
                    and str(latest.source_signature or "") != str(snapshot_row.source_signature or "")
                )
            )
        ):
            latest.route_json = rebuilt_route_json
            latest.total_docs = total_docs
            latest.segment_count = len(rebuilt_route)
            if snapshot_row and snapshot_row.source_signature:
                latest.source_signature = snapshot_row.source_signature
            await db.commit()
            await db.refresh(latest)
        return latest

    if not snapshot_row:
        return None

    if not snapshot_items:
        return None

    normalized_route = build_saved_route_version_segments(
        snapshot_items,
        detail_rows,
        total_docs,
        source_lookup=source_lookup,
    )
    normalized_route = sort_and_resequence_saved_route(normalized_route)
    if not normalized_route:
        return None

    return await save_normalized_route_version(
        project_id=project_id,
        db=db,
        source_signature=snapshot_row.source_signature or "",
        total_docs=total_docs,
        normalized_route=normalized_route,
    )


async def build_saved_normalized_route_response(
    version_row: NormalizedRouteVersion,
    db: AsyncSession,
) -> SavedNormalizedRouteVersionOut:
    response = serialize_saved_normalized_route_version(version_row)
    reviews_by_segment = await load_route_factor_reviews(version_row.id, db)
    rule_reviews_by_segment = await load_route_rule_reviews(version_row.id, db)
    next_segments: list[dict[str, object]] = []
    for segment in response.segments:
        payload = segment.model_dump()
        factor_reviews = reviews_by_segment.get(segment.id, [])
        rule_review = rule_reviews_by_segment.get(segment.id)
        payload["factor_reviews"] = [review.model_dump() for review in factor_reviews]
        payload["rule_review"] = rule_review.model_dump() if rule_review else None
        payload["analysis_status"] = "reviewed" if factor_reviews or rule_review else "pending"
        next_segments.append(payload)
    response.segments = [SavedNormalizedRouteSegmentOut(**item) for item in next_segments]
    response.segment_count = len(response.segments)
    return response


async def save_segment_rule_review_record(
    *,
    project_id: int,
    route_id: int,
    segment_id: str,
    decision: str,
    note: str,
    summary_lines: list[str],
    question_trail: list[dict[str, str]],
    db: AsyncSession,
) -> SegmentRuleReviewSaveOut:
    version_row = (
        await db.execute(
            select(NormalizedRouteVersion).where(
                NormalizedRouteVersion.id == route_id,
                NormalizedRouteVersion.project_id == project_id,
            )
        )
    ).scalars().first()
    if not version_row:
        raise HTTPException(404, "当前保存路线版本不存在。")

    normalized_decision = str(decision or "accepted").strip().lower()
    if normalized_decision not in {"accepted", "rejected", "pending"}:
        raise HTTPException(400, "规则决策只支持 accepted / rejected / pending。")

    def _resolved_merge_name_from_trail() -> str:
        for item in question_trail or []:
            if str(item.get("nodeId") or "") != "merge_name_root":
                continue
            label = canonicalize_route_label(str(item.get("label") or "").strip())
            if label:
                return label
        return ""

    def _apply_segment_name_to_route_json(next_name: str) -> str:
        if not next_name:
            return ""
        try:
            route_items = json.loads(version_row.route_json or "[]")
        except Exception:
            route_items = []
        if not isinstance(route_items, list):
            return ""
        changed = False
        for item in route_items:
            if not isinstance(item, dict):
                continue
            if str(item.get("id") or "") != segment_id:
                continue
            if str(item.get("normalized_step_name") or "") == next_name:
                return next_name
            item["normalized_step_name"] = next_name
            changed = True
        if changed:
            version_row.route_json = json.dumps(route_items, ensure_ascii=False)
            return next_name
        return ""

    existing = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route_id,
                NormalizedRouteSegmentRuleReview.segment_id == segment_id,
            )
        )
    ).scalars().first()

    normalized_step_name = ""
    if normalized_decision == "pending":
        if existing:
            await db.delete(existing)
            await db.commit()
        rule_review = None
    else:
        normalized_step_name = _apply_segment_name_to_route_json(_resolved_merge_name_from_trail())
        if not existing:
            existing = NormalizedRouteSegmentRuleReview(
                project_id=project_id,
                route_version_id=route_id,
                segment_id=segment_id,
            )
            db.add(existing)
        existing.decision = normalized_decision
        existing.note = note
        existing.summary_json = json.dumps(list(summary_lines or []), ensure_ascii=False)
        existing.question_trail_json = json.dumps(list(question_trail or []), ensure_ascii=False)
        await db.commit()
        await db.refresh(existing)
        rule_review = serialize_segment_rule_review(existing)

    factor_reviews = (await load_route_factor_reviews(route_id, db)).get(segment_id, [])
    return SegmentRuleReviewSaveOut(
        project_id=project_id,
        route_id=route_id,
        segment_id=segment_id,
        analysis_status="reviewed" if factor_reviews or rule_review else "pending",
        normalized_step_name=normalized_step_name or None,
        rule_review=rule_review,
    )
