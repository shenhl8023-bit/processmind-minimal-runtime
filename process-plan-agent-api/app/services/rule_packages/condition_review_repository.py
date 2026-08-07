"""Persistence and serialization mechanics for condition reviews."""

from __future__ import annotations

import json

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
    RuleConditionReview,
    RuleConditionReviewResponse,
)
from app.services.rule_packages.condition_review_errors import ConditionReviewNotFound
from app.services.rule_packages.condition_review_state import ConditionReviewStateUpdate
from app.services.rule_packages.process_identity import route_process_identities


def loads_candidate(raw: str | None) -> RuleConditionCandidate | None:
    if not raw:
        return None
    try:
        return RuleConditionCandidate.model_validate(json.loads(raw))
    except Exception:
        return None


def loads_issues(raw: str | None) -> list[str]:
    try:
        payload = json.loads(raw or "[]")
    except Exception:
        return []
    return [str(item) for item in payload] if isinstance(payload, list) else []


def candidate_json(candidate: RuleConditionCandidate) -> str:
    return json.dumps(candidate.model_dump(mode="json", by_alias=True), ensure_ascii=False)


def route_process_options(route: NormalizedRouteVersion) -> list[RuleConditionProcessOption]:
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    options: list[RuleConditionProcessOption] = []
    for identity, item in zip(route_process_identities(route_items), route_items):
        if not isinstance(item, dict):
            continue
        process_id = identity.export_process_id
        if not process_id:
            continue
        display_name = str(
            item.get("normalized_step_name") or item.get("process_name") or process_id
        ).strip() or process_id
        options.append(RuleConditionProcessOption(
            process_id=process_id,
            display_name=display_name,
            main=bool(item.get("main")),
        ))
    return options


async def load_route_and_review(
    project_id: int,
    route_id: int,
    segment_id: str,
    db: AsyncSession,
) -> tuple[NormalizedRouteVersion, NormalizedRouteSegmentRuleReview]:
    route = (
        await db.execute(
            select(NormalizedRouteVersion).where(
                NormalizedRouteVersion.id == route_id,
                NormalizedRouteVersion.project_id == project_id,
            )
        )
    ).scalars().first()
    if not route:
        raise ConditionReviewNotFound("当前保存路线版本不存在。")
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    if not any(
        isinstance(item, dict) and str(item.get("id") or "") == segment_id
        for item in route_items
    ):
        raise ConditionReviewNotFound("当前工序不属于该保存路线版本。")

    review = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route_id,
                NormalizedRouteSegmentRuleReview.segment_id == segment_id,
            )
        )
    ).scalars().first()
    if not review:
        review = NormalizedRouteSegmentRuleReview(
            project_id=project_id,
            route_version_id=route_id,
            segment_id=segment_id,
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
        )
        db.add(review)
        await db.flush()
    return route, review


def apply_state_update(
    review: NormalizedRouteSegmentRuleReview,
    update: ConditionReviewStateUpdate,
) -> None:
    for field_name, value in update.values.items():
        setattr(review, field_name, value)


def serialize_condition_review(row: NormalizedRouteSegmentRuleReview) -> RuleConditionReview:
    confirmed_at = row.condition_confirmed_at
    return RuleConditionReview(
        source_text=row.condition_source_text or "",
        source_hash=row.condition_source_hash or "",
        status=row.condition_status or "draft",
        candidate=loads_candidate(row.condition_candidate_json),
        confirmed=loads_candidate(row.condition_confirmed_json),
        confidence=row.condition_confidence,
        issues=loads_issues(row.condition_issues_json),
        field_registry_version=row.condition_field_registry_version or "",
        parser_version=row.condition_parser_version or "",
        parse_duration_ms=row.condition_parse_duration_ms,
        confirmed_by=row.condition_confirmed_by or "",
        confirmed_at=confirmed_at.isoformat() if confirmed_at else "",
    )


def review_response(body, row: NormalizedRouteSegmentRuleReview) -> RuleConditionReviewResponse:
    return RuleConditionReviewResponse(
        project_id=body.project_id,
        route_id=body.route_id,
        segment_id=body.segment_id,
        review=serialize_condition_review(row),
    )
