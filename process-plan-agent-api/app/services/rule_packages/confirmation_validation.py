"""Validate exported user rules against the server-owned confirmations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteSegmentRuleReview
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.contracts import RuleAction, RulePackageV2


class ConfirmedRuleSourcesChanged(ValueError):
    def __init__(self, rule_ids: list[str]):
        super().__init__(
            "规则包中的用户规则与数据库中的已确认规则不一致，请刷新第四步后重新审核。"
        )
        self.rule_ids = rule_ids

    @property
    def detail(self) -> dict[str, object]:
        return {"message": str(self), "rule_ids": self.rule_ids}


def _load_confirmed_candidate(row: NormalizedRouteSegmentRuleReview) -> RuleConditionCandidate | None:
    if row.condition_status != "confirmed" or not row.condition_confirmed_json:
        return None
    try:
        return RuleConditionCandidate.model_validate(json.loads(row.condition_confirmed_json))
    except Exception:
        return None


def _same_action(left: RuleAction, right: RuleAction) -> bool:
    return (
        left.include_process_ids == right.include_process_ids
        and left.exclude_process_ids == right.exclude_process_ids
    )


def _same_confirmation(row: NormalizedRouteSegmentRuleReview, confirmed_by: str, confirmed_at: str) -> bool:
    if str(row.condition_confirmed_by or "") != str(confirmed_by or ""):
        return False
    if not row.condition_confirmed_at or not confirmed_at:
        return False
    try:
        exported_at = datetime.fromisoformat(str(confirmed_at).replace("Z", "+00:00"))
    except ValueError:
        return False
    stored_at = row.condition_confirmed_at
    if stored_at.tzinfo is None:
        stored_at = stored_at.replace(tzinfo=timezone.utc)
    if exported_at.tzinfo is None:
        exported_at = exported_at.replace(tzinfo=timezone.utc)
    return stored_at.astimezone(timezone.utc) == exported_at.astimezone(timezone.utc)


def _matches_manual_false_rule(
    rule,
    candidate: RuleConditionCandidate,
    row: NormalizedRouteSegmentRuleReview,
) -> bool:
    return bool(
        row.condition_parser_version == "manual"
        and row.condition_confirmed_by == "用户直接设定"
        and candidate.kind == "condition"
        and candidate.when is not None
        and candidate.when.field
        and candidate.when.field.startswith("project_factor.manual_process_")
        and candidate.when.op == "eq"
        and candidate.when.value is True
        and candidate.then is not None
        and rule.when.field == candidate.when.field
        and rule.when.op == "eq"
        and rule.when.value is False
        and rule.then.include_process_ids == []
        and rule.then.exclude_process_ids == candidate.then.include_process_ids
    )


def _matches_confirmed_rule(
    rule,
    candidate: RuleConditionCandidate,
    row: NormalizedRouteSegmentRuleReview,
) -> bool:
    if candidate.kind != "condition" or candidate.when is None or candidate.then is None:
        return False
    return (
        (rule.when == candidate.when and _same_action(rule.then, candidate.then))
        or _matches_manual_false_rule(rule, candidate, row)
    )


async def require_confirmed_user_rule_sources(
    package: RulePackageV2,
    *,
    project_id: int,
    route_version_id: int,
    db: AsyncSession,
) -> None:
    user_rules = [rule for rule in package.route_rules.rules if rule.source == "user_confirmed"]
    user_relations = [
        relation for relation in package.route_rules.process_relations
        if relation.source == "user_confirmed"
    ]
    if not user_rules and not user_relations:
        return

    rows = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.project_id == project_id,
                NormalizedRouteSegmentRuleReview.route_version_id == route_version_id,
            )
        )
    ).scalars().all()
    reviews = {row.segment_id: row for row in rows}
    failures: list[str] = []

    for rule in user_rules:
        row = reviews.get(rule.source_segment_id)
        candidate = _load_confirmed_candidate(row) if row else None
        if (
            candidate is None
            or row.condition_source_text != rule.source_text
            or not _same_confirmation(row, rule.confirmed_by, rule.confirmed_at)
            or not _matches_confirmed_rule(rule, candidate, row)
        ):
            failures.append(rule.rule_id)

    for relation in user_relations:
        row = reviews.get(relation.source_segment_id)
        candidate = _load_confirmed_candidate(row) if row else None
        if (
            candidate is None
            or candidate.kind != "process_relation"
            or candidate.relation is None
            or row.condition_source_text != relation.source_text
            or not _same_confirmation(row, relation.confirmed_by, relation.confirmed_at)
            or candidate.relation.relation_type != relation.relation_type
            or candidate.relation.source_process_ids != relation.source_process_ids
            or candidate.relation.target_process_ids != relation.target_process_ids
            or candidate.relation.source_match != relation.source_match
        ):
            failures.append(relation.relation_id)

    if failures:
        raise ConfirmedRuleSourcesChanged(failures)
