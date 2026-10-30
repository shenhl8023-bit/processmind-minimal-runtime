"""Validate exported user rules against the server-owned confirmations."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.process_knowledge import canonicalize_route_label
from app.services.rule_packages.condition_contracts import RuleConditionCandidate
from app.services.rule_packages.contracts import InputField, RuleAction, RulePackageV2


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


_LEGACY_MAINLINE_SOURCES = frozenset({
    "将其设置为主工序，始终保留在路线中",
    "把该工序改为主线工序",
    "作为基础工序无条件进入路线",
    "此工序属于必经工序",
    "固定为主工序，默认保留",
})


def _is_explicit_mainline_source(value: str | None, process_name: str | None) -> bool:
    """Only an entire known instruction can bypass conditional confirmation."""
    if process_name is None:
        return False
    text = str(value or "").strip()
    if text.endswith("。"):
        text = text[:-1]
    if text in _LEGACY_MAINLINE_SOURCES:
        return True
    # Match the editor's existing display-name aliases using server-owned
    # route data, never a name supplied by the publication request.
    name = canonicalize_route_label(process_name)
    if "淬火" in name:
        name = "淬火"
    return bool(name) and text == f"设置为主工序，始终纳入“{name}”工序"


async def _saved_mainline_segments(
    package: RulePackageV2,
    *,
    project_id: int,
    route_version_id: int,
    db: AsyncSession,
) -> dict[str, str]:
    route = (
        await db.execute(select(NormalizedRouteVersion).where(
            NormalizedRouteVersion.id == route_version_id,
            NormalizedRouteVersion.project_id == project_id,
        ))
    ).scalar_one_or_none()
    try:
        segments = json.loads(route.route_json or "[]") if route else []
    except (TypeError, ValueError):
        return {}
    if not isinstance(segments, list):
        return {}
    main_process_ids = {process.process_id for process in package.route_catalog.processes if process.main}
    return {
        str(segment["id"]): str(segment.get("normalized_step_name") or "").strip()
        for segment in segments
        if isinstance(segment, dict)
        and segment.get("id")
        and str(segment.get("export_process_id") or segment["id"]) in main_process_ids
    }


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
    failure_segments: list[str] = []
    covered_segments: set[str] = set()

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
            if rule.source_segment_id:
                failure_segments.append(rule.source_segment_id)
        elif (
            rule.enabled
            and candidate.kind == "condition"
            and rule.when == candidate.when
            and _same_action(rule.then, candidate.then)
        ):
            # The generated manual "false" companion cannot stand in for the
            # user's positive condition if the positive rule was omitted.
            covered_segments.add(row.segment_id)

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
            if relation.source_segment_id:
                failure_segments.append(relation.source_segment_id)
        elif relation.enabled:
            covered_segments.add(row.segment_id)

    # A shared dynamic field may be witnessed with different options in several
    # confirmations. Audit the exact server-owned union, keeping all other
    # attributes identical and refusing invented or conflicting option values.
    confirmed_fields: dict[str, InputField] = {}
    conflicting_fields: set[str] = set()
    for row in rows:
        saved = _load_confirmed_candidate(row)
        if saved is None:
            continue
        for field in saved.field_definitions:
            definition = InputField.model_validate({key: value for key, value in field.model_dump().items() if key in InputField.model_fields})
            existing = confirmed_fields.get(field.key)
            if existing is None:
                confirmed_fields[field.key] = definition
                continue
            if existing.model_dump(exclude={"options"}) != definition.model_dump(exclude={"options"}):
                conflicting_fields.add(field.key)
            options = {option.value: option for option in existing.options}
            for option in definition.options:
                if option.value in options and options[option.value] != option:
                    conflicting_fields.add(field.key)
                options[option.value] = option
            existing.options = list(options.values())

    def matches_confirmed_field(actual: InputField | None, expected: InputField) -> bool:
        return bool(
            actual is not None
            and actual.model_dump(exclude={"options"}) == expected.model_dump(exclude={"options"})
            and len(actual.options) == len(expected.options)
            and {option.value: option for option in actual.options} == {option.value: option for option in expected.options}
        )

    configuration_segments: set[str] = set()
    input_fields = {field.key: field for field in package.input_schema.fields}
    dictionary_fields = {field.key: field for field in package.factor_dictionary.fields}
    process_map = {process.process_id: process for process in package.route_catalog.processes}
    for row in rows:
        if row.segment_id not in covered_segments:
            continue
        candidate = _load_confirmed_candidate(row)
        if any(
            field.key in conflicting_fields
            or not matches_confirmed_field(input_fields.get(field.key), confirmed_fields[field.key])
            or not matches_confirmed_field(dictionary_fields.get(field.key), confirmed_fields[field.key])
            for field in candidate.field_definitions
        ):
            covered_segments.remove(row.segment_id)
    for config in package.route_rules.process_configurations:
        if config.source != "user_confirmed":
            continue
        row = reviews.get(config.source_segment_id)
        candidate = _load_confirmed_candidate(row) if row else None
        valid = bool(
            candidate and candidate.kind == "process_configuration" and candidate.configuration
            and config.enabled and row.condition_source_text == config.source_text
            and _same_confirmation(row, config.confirmed_by, config.confirmed_at)
            and candidate.configuration.model_dump() == {
                "process_id": config.process_id, "occurrence": config.occurrence,
                "when": config.when.model_dump() if config.when else None,
                "relations": [relation.model_dump() for relation in config.relations],
            }
            and config.source_segment_id not in configuration_segments
            and config.process_id in process_map
            and process_map[config.process_id].main == (config.occurrence == "always")
        )
        if valid:
            for field in candidate.field_definitions:
                expected = confirmed_fields[field.key]
                if (field.key in conflicting_fields
                        or not matches_confirmed_field(input_fields.get(field.key), expected)
                        or not matches_confirmed_field(dictionary_fields.get(field.key), expected)):
                    valid = False
                    break
        if valid:
            configuration_segments.add(config.source_segment_id)
            covered_segments.add(config.source_segment_id)
        else:
            failures.append(f"configuration.{config.process_id}")
            if config.source_segment_id:
                failure_segments.append(config.source_segment_id)

    mainline_segments = await _saved_mainline_segments(
        package, project_id=project_id, route_version_id=route_version_id, db=db,
    ) if rows else {}
    missing_segments: list[str] = []
    for row in rows:
        has_condition_state = bool(
            str(row.condition_source_text or "").strip()
            or row.condition_source_hash
            or row.condition_candidate_json
            or row.condition_confirmed_json
        )
        if not has_condition_state:
            # Step-three-only/legacy reviews have no step-five source to
            # validate. Existing static packages remain compatible.
            continue
        if (
            row.condition_status == "draft"
            and not row.condition_candidate_json
            and not row.condition_confirmed_json
            and _is_explicit_mainline_source(row.condition_source_text, mainline_segments.get(row.segment_id))
        ):
            # "Always keep" is saved through the existing text-draft endpoint.
            # The authoritative saved instruction and route ID must agree
            # with the catalog; a client-side main flag alone is insufficient.
            continue
        if row.segment_id not in covered_segments:
            missing_segments.append(row.segment_id)

    if failures or missing_segments:
        raise HTTPException(409, {
            "message": "规则包中的用户规则与数据库中的已确认规则不一致，或存在未确认、遗漏的规则，请刷新规则定稿后重新审核。",
            "rule_ids": failures,
            "segment_ids": list(dict.fromkeys([*failure_segments, *missing_segments])),
        })
