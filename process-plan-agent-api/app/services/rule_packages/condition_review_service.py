"""Application services for condition-review workflows.

This module deliberately stops at the current database session. HTTP mapping,
workflow locks, and transaction completion belong to the API routers.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion
from app.services.llm_client import get_llm_config
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ManualRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
    RuleConditionReviewResponse,
    SaveRuleConditionDraftRequest,
)
from app.services.rule_packages.condition_parser import (
    CONDITION_PARSER_VERSION,
    parse_rule_condition,
    validate_candidate,
)
from app.services.rule_packages.condition_registry import FIELD_REGISTRY_VERSION, condition_preview
from app.services.rule_packages.condition_review_errors import (
    ConditionReviewConflict,
    ConditionReviewValidation,
)
from app.services.rule_packages.condition_review_repository import (
    apply_state_update,
    candidate_json as serialize_candidate,
    loads_candidate,
    loads_issues,
    load_route_and_review,
    review_response,
    route_process_options,
)
from app.services.rule_packages.condition_review_state import (
    condition_source_hash,
    confirmation_update,
    legacy_invalidation_update,
    manual_confirmation_update,
    manual_process_field_key,
    new_draft_update,
    parse_result_update,
    parsing_update,
)
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.lifecycle import archive_published_rule_packages
from app.services.rule_packages.standard_factors import (
    STANDARD_FACTOR_CATALOG_VERSION,
    bind_unambiguous_factor_ids,
    normalize_factor_leaves,
    validate_factor_bindings,
)

logger = logging.getLogger(__name__)


@dataclass
class ParseReviewPreparation:
    cache_hit: bool
    cached_response: RuleConditionReviewResponse | None
    source_text: str
    source_hash: str
    parser_version: str
    llm_config: dict[str, str] | None
    review: NormalizedRouteSegmentRuleReview


async def _active_condition_parser_context() -> tuple[str, dict[str, str]]:
    config = await get_llm_config()
    model_digest = hashlib.sha256(str(config.get("model") or "").encode("utf-8")).hexdigest()[:8]
    return f"{CONDITION_PARSER_VERSION}:{model_digest}", config


def _validate_process_catalog(
    route: NormalizedRouteVersion,
    processes: list[RuleConditionProcessOption],
) -> None:
    if not processes:
        raise ConditionReviewValidation("当前路线没有可用的标准工序。")
    process_ids = [item.process_id for item in processes]
    if len(process_ids) != len(set(process_ids)):
        raise ConditionReviewValidation("标准工序列表包含重复 process_id。")
    try:
        route_items = json.loads(route.route_json or "[]")
    except Exception:
        route_items = []
    allowed_route_ids = {
        str(item.get("id") or "")
        for item in route_items
        if isinstance(item, dict)
    }
    allowed_route_ids.add("process_quench")
    unknown = [process_id for process_id in process_ids if process_id not in allowed_route_ids]
    if unknown:
        raise ConditionReviewValidation(
            f"标准工序列表包含不属于当前路线的工序：{', '.join(unknown)}"
        )


def _binding_issue_text(issue) -> str:
    return f"{issue.path or 'when'}: {issue.message}"


def _semantic_review_issues(raw: str | None) -> list[str]:
    binding_markers = (
        "条件尚未绑定标准因子",
        "标准因子存在多个候选",
        "条件与指定的标准因子不匹配",
    )
    return [
        issue
        for issue in loads_issues(raw)
        if not any(marker in issue for marker in binding_markers)
    ]


def _selected_factor_paths(node: ConditionNode, path: str = "") -> set[str]:
    if node.field is not None:
        return {path} if node.factor_id is not None else set()
    if node.all_conditions is not None:
        return {
            selected_path
            for index, child in enumerate(node.all_conditions)
            for selected_path in _selected_factor_paths(
                child,
                f"{path + '.' if path else ''}all[{index}]",
            )
        }
    if node.any_conditions is not None:
        return {
            selected_path
            for index, child in enumerate(node.any_conditions)
            for selected_path in _selected_factor_paths(
                child,
                f"{path + '.' if path else ''}any[{index}]",
            )
        }
    return _selected_factor_paths(node.not_condition, f"{path + '.' if path else ''}not")


def _migrate_review_candidate(
    candidate: RuleConditionCandidate,
    processes: list[RuleConditionProcessOption],
) -> tuple[RuleConditionCandidate, list[str]]:
    if candidate.kind != "condition" or candidate.when is None:
        return candidate, validate_candidate(candidate, processes)
    normalized = normalize_factor_leaves(candidate.when)
    selected_paths = _selected_factor_paths(normalized)
    selected_binding_issues = [
        issue
        for issue in validate_factor_bindings(
            normalized,
            {field.key: field for field in candidate.field_definitions},
        )
        if issue.path in selected_paths
    ]
    bound, binding_issues = bind_unambiguous_factor_ids(normalized)
    migrated = candidate.model_copy(update={"when": bound})
    candidate_issues = validate_candidate(migrated, processes)
    all_issues = [
        *(_binding_issue_text(issue) for issue in selected_binding_issues),
        *(_binding_issue_text(issue) for issue in binding_issues),
        *candidate_issues,
    ]
    return migrated, list(dict.fromkeys(all_issues))


async def save_condition_draft(
    body: SaveRuleConditionDraftRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    _, review = await load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    source_text = body.source_text.strip()
    source_hash = condition_source_hash(source_text)
    if review.condition_source_hash == source_hash and review.condition_source_text == source_text:
        return review_response(body, review)
    apply_state_update(
        review,
        new_draft_update(source_text, source_hash, FIELD_REGISTRY_VERSION),
    )
    await archive_published_rule_packages(body.project_id, db)
    return review_response(body, review)


async def prepare_condition_parse(
    body: ParseRuleConditionRequest,
    db: AsyncSession,
) -> ParseReviewPreparation:
    route, review = await load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    _validate_process_catalog(route, body.processes)
    if body.process_id not in {item.process_id for item in body.processes}:
        raise ConditionReviewValidation("当前工序不在可用标准工序列表中。")
    source_text = body.source_text.strip()
    if not source_text:
        raise ConditionReviewValidation("请先填写需要解析的工序条件。")
    source_hash = condition_source_hash(source_text)
    parser_version, llm_config = await _active_condition_parser_context()
    if (
        review.condition_source_hash == source_hash
        and review.condition_source_text == source_text
        and review.condition_field_registry_version == FIELD_REGISTRY_VERSION
        and review.condition_parser_version == parser_version
        and review.condition_status in {"pending_confirmation", "confirmed"}
        and review.condition_candidate_json
    ):
        logger.info(
            "rule_condition_parse cache_hit=true project_id=%s route_id=%s segment_id=%s",
            body.project_id,
            body.route_id,
            body.segment_id,
        )
        return ParseReviewPreparation(
            cache_hit=True,
            cached_response=review_response(body, review),
            source_text=source_text,
            source_hash=source_hash,
            parser_version=parser_version,
            llm_config=llm_config,
            review=review,
        )

    apply_state_update(
        review,
        parsing_update(source_text, source_hash, parser_version, FIELD_REGISTRY_VERSION),
    )
    await archive_published_rule_packages(body.project_id, db)
    return ParseReviewPreparation(
        cache_hit=False,
        cached_response=None,
        source_text=source_text,
        source_hash=source_hash,
        parser_version=parser_version,
        llm_config=llm_config,
        review=review,
    )


async def execute_condition_parse(
    body: ParseRuleConditionRequest,
    preparation: ParseReviewPreparation,
) -> tuple[RuleConditionCandidate | None, float | None, list[str], int]:
    started_at = time.perf_counter()
    candidate, confidence, issues = await parse_rule_condition(
        preparation.source_text,
        body.process_id,
        body.process_name,
        body.processes,
        llm_config=preparation.llm_config,
    )
    duration_ms = max(0, round((time.perf_counter() - started_at) * 1000))
    return candidate, confidence, issues, duration_ms


async def complete_condition_parse(
    body: ParseRuleConditionRequest,
    preparation: ParseReviewPreparation,
    result: tuple,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    _, review = await load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    # The parser runs outside the transaction. Refresh before the stale-write
    # check so a newer request committed by another session remains authoritative.
    await db.refresh(review)
    if (
        review.condition_source_hash != preparation.source_hash
        or review.condition_parser_version != preparation.parser_version
    ):
        return review_response(body, review)

    candidate, confidence, issues = result[:3]
    duration_ms = int(result[3]) if len(result) > 3 else 0
    serialized_candidate = None
    if candidate:
        if candidate.kind == "condition" and candidate.when is not None:
            candidate.preview = condition_preview(candidate.when)
        serialized_candidate = serialize_candidate(candidate)
    apply_state_update(
        review,
        parse_result_update(serialized_candidate, confidence, json.dumps(issues, ensure_ascii=False), duration_ms),
    )
    logger.info(
        "rule_condition_parse cache_hit=false project_id=%s route_id=%s segment_id=%s status=%s duration_ms=%s",
        body.project_id,
        body.route_id,
        body.segment_id,
        review.condition_status,
        duration_ms,
    )
    return review_response(body, review)


async def parse_condition_review(
    body: ParseRuleConditionRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    """Compatibility orchestration for direct service callers.

    API routes use the three explicit phases so they can own transactions.
    This helper intentionally performs no commit or workflow locking.
    """
    preparation = await prepare_condition_parse(body, db)
    if preparation.cache_hit:
        assert preparation.cached_response is not None
        return preparation.cached_response
    result = await execute_condition_parse(body, preparation)
    return await complete_condition_parse(body, preparation, result, db)


async def confirm_condition_review(
    body: ConfirmRuleConditionRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    route, review = await load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    _validate_process_catalog(route, body.processes)
    source_text = body.source_text.strip()
    expected_hash = condition_source_hash(source_text)
    if body.source_hash != expected_hash or review.condition_source_hash != expected_hash:
        raise ConditionReviewConflict("条件文字已经发生变化，请重新解析后再确认。")
    if review.condition_status not in {"pending_confirmation", "confirmed"}:
        raise ConditionReviewConflict("当前条件尚未生成可确认的候选规则。")
    candidate = body.candidate.model_copy(deep=True)
    issues = validate_candidate(candidate, body.processes)
    if issues:
        raise ConditionReviewValidation({"message": "候选规则校验未通过", "issues": issues})
    if candidate.kind == "condition" and candidate.when is not None:
        definitions = {field.key: field for field in candidate.field_definitions}
        binding_issues = validate_factor_bindings(candidate.when, definitions)
        if binding_issues:
            raise ConditionReviewValidation({
                "message": "标准因子绑定校验未通过",
                "issues": [issue.model_dump(mode="json") for issue in binding_issues],
            })
        candidate.preview = condition_preview(candidate.when)
    apply_state_update(
        review,
        confirmation_update(
            source_text,
            expected_hash,
            serialize_candidate(candidate),
            FIELD_REGISTRY_VERSION,
            body.confirmed_by.strip() or "默认用户",
            datetime.now(timezone.utc),
        ),
    )
    await archive_published_rule_packages(body.project_id, db)
    return review_response(body, review)


async def set_manual_condition_review(
    body: ManualRuleConditionRequest,
    db: AsyncSession,
) -> RuleConditionReviewResponse:
    route, review = await load_route_and_review(body.project_id, body.route_id, body.segment_id, db)
    _validate_process_catalog(route, body.processes)
    source_text = body.source_text.strip()
    if not source_text:
        raise ConditionReviewValidation("请说明此工序由用户如何控制。")
    if body.process_id not in {item.process_id for item in body.processes}:
        raise ConditionReviewValidation("人工 Bool 条件的目标工序不在当前标准工序列表中。")
    candidate = body.candidate.model_copy(deep=True)
    issues = validate_candidate(candidate, body.processes)
    if issues:
        raise ConditionReviewValidation({"message": "人工设定的规则校验未通过", "issues": issues})
    expected_field_key = manual_process_field_key(body.process_id)
    definitions = candidate.field_definitions
    valid_manual_shape = (
        candidate.kind == "condition"
        and candidate.when is not None
        and candidate.when.field == expected_field_key
        and candidate.when.op == "eq"
        and candidate.when.value is True
        and len(definitions) == 1
        and definitions[0].key == expected_field_key
        and definitions[0].type == "boolean"
        and definitions[0].source == "用户直接设定"
        and definitions[0].allow_custom is False
        and candidate.then is not None
        and candidate.then.include_process_ids == [body.process_id]
        and candidate.then.exclude_process_ids == []
    )
    if not valid_manual_shape:
        raise ConditionReviewValidation("人工 Bool 条件必须只控制当前工序，并使用固定的用户开关字段。")
    binding_issues = validate_factor_bindings(
        candidate.when,
        {field.key: field for field in candidate.field_definitions},
    )
    if binding_issues:
        raise ConditionReviewValidation({
            "message": "人工设定的规则校验未通过",
            "issues": [issue.model_dump(mode="json") for issue in binding_issues],
        })
    candidate.preview = condition_preview(
        candidate.when,
        {field.key: field for field in candidate.field_definitions},
    )
    apply_state_update(
        review,
        manual_confirmation_update(
            source_text,
            condition_source_hash(source_text),
            serialize_candidate(candidate),
            FIELD_REGISTRY_VERSION,
            datetime.now(timezone.utc),
        ),
    )
    await archive_published_rule_packages(body.project_id, db)
    return review_response(body, review)


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
        confirmed = loads_candidate(review.condition_confirmed_json)
        if not re.search(r"无损|磁粉|裂纹|荧光|探伤", process_name):
            continue
        if not confirmed or confirmed.kind != "process_relation":
            continue
        source_text = f"当零件有无损检测要求时，纳入“{process_name}”工序。"
        apply_state_update(
            review,
            legacy_invalidation_update(
                source_text,
                condition_source_hash(source_text),
                FIELD_REGISTRY_VERSION,
                json.dumps(["旧版规则曾将无损检查误判为工序关系，已改为待审核的无损检测要求。"], ensure_ascii=False),
            ),
        )
        changed = True
    if changed:
        await archive_published_rule_packages(route.project_id, db)
    return changed


async def migrate_legacy_standard_factor_reviews(
    route: NormalizedRouteVersion,
    db: AsyncSession,
) -> bool:
    """Safely recheck every unpublished condition review against the immutable catalog."""
    reviews = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route.id,
            )
        )
    ).scalars().all()
    processes = route_process_options(route)
    changed = False
    for review in reviews:
        candidate = loads_candidate(review.condition_candidate_json)
        confirmed = loads_candidate(review.condition_confirmed_json)
        if candidate is None and confirmed is None:
            continue

        migrated_candidate, candidate_issues = _migrate_review_candidate(candidate or confirmed, processes)
        migrated_confirmed = None
        confirmed_issues: list[str] = []
        if confirmed is not None:
            migrated_confirmed, confirmed_issues = _migrate_review_candidate(confirmed, processes)
        all_issues = list(dict.fromkeys([
            *_semantic_review_issues(review.condition_issues_json),
            *candidate_issues,
            *confirmed_issues,
        ]))

        next_status = review.condition_status
        next_candidate_json = serialize_candidate(migrated_candidate)
        next_confirmed_json = review.condition_confirmed_json
        next_confirmed_by = review.condition_confirmed_by
        next_confirmed_at = review.condition_confirmed_at
        next_issues_json = review.condition_issues_json or "[]"
        if confirmed is not None:
            if all_issues:
                next_status = "pending_confirmation"
                next_confirmed_json = None
                next_confirmed_by = None
                next_confirmed_at = None
                next_issues_json = json.dumps(all_issues, ensure_ascii=False)
            else:
                next_status = "confirmed"
                next_confirmed_json = serialize_candidate(migrated_confirmed or migrated_candidate)
                next_issues_json = "[]"
        elif all_issues:
            next_status = "pending_confirmation"
            next_issues_json = json.dumps(all_issues, ensure_ascii=False)
        else:
            next_issues_json = "[]"

        if (
            review.condition_status != next_status
            or review.condition_candidate_json != next_candidate_json
            or review.condition_confirmed_json != next_confirmed_json
            or review.condition_confirmed_by != next_confirmed_by
            or review.condition_confirmed_at != next_confirmed_at
            or review.condition_issues_json != next_issues_json
            or review.condition_field_registry_version != STANDARD_FACTOR_CATALOG_VERSION
        ):
            review.condition_status = next_status
            review.condition_candidate_json = next_candidate_json
            review.condition_confirmed_json = next_confirmed_json
            review.condition_confirmed_by = next_confirmed_by
            review.condition_confirmed_at = next_confirmed_at
            review.condition_issues_json = next_issues_json
            review.condition_field_registry_version = STANDARD_FACTOR_CATALOG_VERSION
            changed = True
    if changed:
        await archive_published_rule_packages(route.project_id, db)
    return changed


async def migrate_legacy_condition_reviews(
    route: NormalizedRouteVersion,
    db: AsyncSession,
) -> bool:
    invalidated = await invalidate_legacy_nondestructive_relation_reviews(route, db)
    migrated = await migrate_legacy_standard_factor_reviews(route, db)
    return invalidated or migrated
