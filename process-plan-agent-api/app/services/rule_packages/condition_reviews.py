"""Persistence and state transitions for reviewed natural-language rules."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
    RuleConditionReview,
    RuleConditionReviewResponse,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.condition_parser import parse_rule_condition, validate_candidate
from app.services.rule_packages.condition_registry import FIELD_REGISTRY_VERSION, condition_preview


def condition_source_hash(source_text: str) -> str:
    return hashlib.sha256(str(source_text or "").strip().encode("utf-8")).hexdigest()


def _loads_candidate(raw: str | None) -> RuleConditionCandidate | None:
    if not raw:
        return None
    try:
        return RuleConditionCandidate.model_validate(json.loads(raw))
    except Exception:
        return None


def _loads_issues(raw: str | None) -> list[str]:
    try:
        payload = json.loads(raw or "[]")
    except Exception:
        return []
    return [str(item) for item in payload] if isinstance(payload, list) else []


def _special_requirement_for_legacy_boolean(field) -> str:
    text = " ".join([field.label, *field.aliases])
    if re.search(r"追溯|编号|批次.{0,6}标识", text):
        return "追溯标印"
    if re.search(r"无损|磁粉|裂纹|荧光|探伤", text):
        return "无损检测要求"
    label = re.sub(r"^(?:是否需要|是否具备|是否)", "", field.label).strip()
    return label if label.endswith("要求") else f"{label or '特殊工艺'}要求"


def _migrate_legacy_boolean_candidate(candidate: RuleConditionCandidate) -> RuleConditionCandidate:
    if candidate.kind != "condition" or candidate.when is None:
        return candidate
    legacy_fields = {
        field.key: field
        for field in candidate.field_definitions
        if field.type == "boolean" and field.key.startswith("custom.requirements.")
    }
    if not legacy_fields:
        return candidate

    def convert(node: ConditionNode) -> ConditionNode:
        if node.field:
            definition = legacy_fields.get(node.field)
            if definition:
                return ConditionNode(
                    field="special.requirements",
                    op="contains",
                    value=_special_requirement_for_legacy_boolean(definition),
                )
            return node
        if node.all_conditions is not None:
            return ConditionNode(all_conditions=[convert(child) for child in node.all_conditions])
        if node.any_conditions is not None:
            return ConditionNode(any_conditions=[convert(child) for child in node.any_conditions])
        if node.not_condition is not None:
            return ConditionNode(not_condition=convert(node.not_condition))
        return node

    when = convert(candidate.when)
    remaining_definitions = [
        field for field in candidate.field_definitions
        if field.key not in legacy_fields
    ]
    migrated = candidate.model_copy(update={"when": when, "field_definitions": remaining_definitions})
    migrated.preview = condition_preview(migrated.when)
    return migrated


def serialize_condition_review(row: NormalizedRouteSegmentRuleReview) -> RuleConditionReview:
    confirmed_at = row.condition_confirmed_at
    return RuleConditionReview(
        source_text=row.condition_source_text or "",
        source_hash=row.condition_source_hash or "",
        status=row.condition_status or "draft",
        candidate=_loads_candidate(row.condition_candidate_json),
        confirmed=_loads_candidate(row.condition_confirmed_json),
        confidence=row.condition_confidence,
        issues=_loads_issues(row.condition_issues_json),
        field_registry_version=row.condition_field_registry_version or "",
        confirmed_by=row.condition_confirmed_by or "",
        confirmed_at=confirmed_at.isoformat() if confirmed_at else "",
    )


async def invalidate_legacy_nondestructive_relation_reviews(
    route: NormalizedRouteVersion,
    db: AsyncSession,
) -> bool:
    """Retire old NDT rules that were incorrectly confirmed as process relations."""
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    names_by_segment_id = {
        str(item.get("id") or ""): str(item.get("normalized_step_name") or "").strip()
        for item in route_items
        if isinstance(item, dict)
    }
    reviews = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route.id,
                NormalizedRouteSegmentRuleReview.condition_status == "confirmed",
            )
        )
    ).scalars().all()
    changed = False
    for review in reviews:
        process_name = names_by_segment_id.get(str(review.segment_id or ""), "")
        confirmed = _loads_candidate(review.condition_confirmed_json)
        if not re.search(r"无损|磁粉|裂纹|荧光|探伤", process_name):
            continue
        if not confirmed or confirmed.kind != "process_relation":
            continue
        source_text = f"当零件有无损检测要求时，纳入“{process_name}”工序。"
        review.condition_source_text = source_text
        review.condition_source_hash = condition_source_hash(source_text)
        review.condition_status = "draft"
        review.condition_candidate_json = None
        review.condition_confirmed_json = None
        review.condition_confidence = None
        review.condition_issues_json = json.dumps([
            "旧版规则曾将无损检查误判为工序关系，已改为待审核的无损检测要求。",
        ], ensure_ascii=False)
        review.condition_field_registry_version = FIELD_REGISTRY_VERSION
        review.condition_confirmed_by = None
        review.condition_confirmed_at = None
        changed = True
    if changed:
        await db.commit()
    return changed


async def migrate_legacy_boolean_requirement_reviews(
    route: NormalizedRouteVersion,
    db: AsyncSession,
) -> bool:
    reviews = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route.id,
            )
        )
    ).scalars().all()
    changed = False
    for review in reviews:
        candidate = _loads_candidate(review.condition_candidate_json)
        confirmed = _loads_candidate(review.condition_confirmed_json)
        migrated_candidate = _migrate_legacy_boolean_candidate(candidate) if candidate else None
        migrated_confirmed = _migrate_legacy_boolean_candidate(confirmed) if confirmed else None
        if migrated_candidate == candidate and migrated_confirmed == confirmed:
            continue
        review.condition_candidate_json = (
            json.dumps(migrated_candidate.model_dump(mode="json", by_alias=True), ensure_ascii=False)
            if migrated_candidate else None
        )
        review.condition_confirmed_json = (
            json.dumps(migrated_confirmed.model_dump(mode="json", by_alias=True), ensure_ascii=False)
            if migrated_confirmed else None
        )
        review.condition_field_registry_version = FIELD_REGISTRY_VERSION
        changed = True
    if changed:
        await db.commit()
    return changed


async def _load_route_and_review(
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
        raise HTTPException(404, "当前保存路线版本不存在。")
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    if not any(isinstance(item, dict) and str(item.get("id") or "") == segment_id for item in route_items):
        raise HTTPException(404, "当前工序不属于该保存路线版本。")

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
    return route, review


def _validate_process_catalog(
    route: NormalizedRouteVersion,
    processes: list[RuleConditionProcessOption],
) -> None:
    if not processes:
        raise HTTPException(422, "当前路线没有可用的标准工序。")
    process_ids = [item.process_id for item in processes]
    if len(process_ids) != len(set(process_ids)):
        raise HTTPException(422, "标准工序列表包含重复 process_id。")
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    allowed_route_ids = {str(item.get("id") or "") for item in route_items if isinstance(item, dict)}
    allowed_route_ids.add("process_quench")
    unknown = [process_id for process_id in process_ids if process_id not in allowed_route_ids]
    if unknown:
        raise HTTPException(422, f"标准工序列表包含不属于当前路线的工序：{', '.join(unknown)}")


def _response(body, review: NormalizedRouteSegmentRuleReview) -> RuleConditionReviewResponse:
    return RuleConditionReviewResponse(
        project_id=body.project_id,
        route_id=body.route_id,
        segment_id=body.segment_id,
        review=serialize_condition_review(review),
    )


async def save_condition_draft(
    body: SaveRuleConditionDraftRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    _, review = await _load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    source_text = body.source_text.strip()
    source_hash = condition_source_hash(source_text)
    if review.condition_source_hash == source_hash and review.condition_source_text == source_text:
        return _response(body, review)
    review.condition_source_text = source_text
    review.condition_source_hash = source_hash
    review.condition_status = "draft"
    review.condition_candidate_json = None
    review.condition_confirmed_json = None
    review.condition_confidence = None
    review.condition_issues_json = "[]"
    review.condition_field_registry_version = FIELD_REGISTRY_VERSION
    review.condition_confirmed_by = None
    review.condition_confirmed_at = None
    await db.commit()
    await db.refresh(review)
    return _response(body, review)


async def parse_condition_review(
    body: ParseRuleConditionRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    route, review = await _load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    _validate_process_catalog(route, body.processes)
    if body.process_id not in {item.process_id for item in body.processes}:
        raise HTTPException(422, "当前工序不在可用标准工序列表中。")
    source_text = body.source_text.strip()
    if not source_text:
        raise HTTPException(422, "请先填写需要解析的工序条件。")

    review.condition_source_text = source_text
    review.condition_source_hash = condition_source_hash(source_text)
    review.condition_status = "parsing"
    review.condition_candidate_json = None
    review.condition_confirmed_json = None
    review.condition_confidence = None
    review.condition_issues_json = "[]"
    review.condition_field_registry_version = FIELD_REGISTRY_VERSION
    review.condition_confirmed_by = None
    review.condition_confirmed_at = None
    await db.commit()

    candidate, confidence, issues = await parse_rule_condition(
        source_text,
        body.process_id,
        body.process_name,
        body.processes,
    )
    review.condition_confidence = confidence
    review.condition_issues_json = json.dumps(issues, ensure_ascii=False)
    if candidate:
        if candidate.kind == "condition" and candidate.when is not None:
            candidate.preview = condition_preview(candidate.when)
        review.condition_candidate_json = json.dumps(candidate.model_dump(mode="json", by_alias=True), ensure_ascii=False)
        review.condition_status = "pending_confirmation"
    else:
        review.condition_candidate_json = None
        review.condition_status = "invalid"
    await db.commit()
    await db.refresh(review)
    return _response(body, review)


async def confirm_condition_review(
    body: ConfirmRuleConditionRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    route, review = await _load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    _validate_process_catalog(route, body.processes)
    source_text = body.source_text.strip()
    expected_hash = condition_source_hash(source_text)
    if body.source_hash != expected_hash or review.condition_source_hash != expected_hash:
        raise HTTPException(409, "条件文字已经发生变化，请重新解析后再确认。")
    if review.condition_status not in {"pending_confirmation", "confirmed"}:
        raise HTTPException(409, "当前条件尚未生成可确认的候选规则。")
    candidate = _migrate_legacy_boolean_candidate(body.candidate.model_copy(deep=True))
    issues = validate_candidate(candidate, body.processes)
    if issues:
        raise HTTPException(422, {"message": "候选规则校验未通过", "issues": issues})

    if candidate.kind == "condition" and candidate.when is not None:
        candidate.preview = condition_preview(candidate.when)
    candidate_json = json.dumps(candidate.model_dump(mode="json", by_alias=True), ensure_ascii=False)
    review.condition_source_text = source_text
    review.condition_source_hash = expected_hash
    review.condition_status = "confirmed"
    review.condition_candidate_json = candidate_json
    review.condition_confirmed_json = candidate_json
    review.condition_issues_json = "[]"
    review.condition_field_registry_version = FIELD_REGISTRY_VERSION
    review.condition_confirmed_by = body.confirmed_by.strip() or "默认用户"
    review.condition_confirmed_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(review)
    return _response(body, review)
