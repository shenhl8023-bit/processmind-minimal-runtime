"""Pure state transitions for persisted condition reviews."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class ConditionReviewStateUpdate:
    values: dict[str, object]


def condition_source_hash(source_text: str) -> str:
    return hashlib.sha256(str(source_text or "").strip().encode("utf-8")).hexdigest()


def manual_process_field_key(process_id: str) -> str:
    """Mirror the UI's stable FNV-1a key for user-controlled process switches."""
    hash_value = 0x811C9DC5
    for char in process_id:
        hash_value ^= ord(char)
        hash_value = ((hash_value * 0x01000193) & 0xFFFFFFFF)
    return f"project_factor.manual_process_{hash_value:08x}"


def new_draft_update(
    source_text: str,
    source_hash: str,
    field_registry_version: str,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_source_text": source_text,
        "condition_source_hash": source_hash,
        "condition_status": "draft",
        "condition_candidate_json": None,
        "condition_confirmed_json": None,
        "condition_confidence": None,
        "condition_issues_json": "[]",
        "condition_field_registry_version": field_registry_version,
        "condition_confirmed_by": None,
        "condition_confirmed_at": None,
    })


def parsing_update(
    source_text: str,
    source_hash: str,
    parser_version: str,
    field_registry_version: str,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_source_text": source_text,
        "condition_source_hash": source_hash,
        "condition_status": "parsing",
        "condition_candidate_json": None,
        "condition_confirmed_json": None,
        "condition_confidence": None,
        "condition_issues_json": "[]",
        "condition_field_registry_version": field_registry_version,
        "condition_parser_version": parser_version,
        "condition_parse_duration_ms": None,
        "condition_confirmed_by": None,
        "condition_confirmed_at": None,
    })


def parse_result_update(
    candidate_json: str | None,
    confidence: float | None,
    issues_json: str,
    duration_ms: int,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_status": "pending_confirmation" if candidate_json else "invalid",
        "condition_candidate_json": candidate_json,
        "condition_confidence": confidence,
        "condition_issues_json": issues_json,
        "condition_parse_duration_ms": duration_ms,
    })


def invalid_parse_update(
    confidence: float | None,
    issues_json: str,
    duration_ms: int,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_status": "invalid",
        "condition_candidate_json": None,
        "condition_confidence": confidence,
        "condition_issues_json": issues_json,
        "condition_parse_duration_ms": duration_ms,
    })


def confirmation_update(
    source_text: str,
    source_hash: str,
    candidate_json: str,
    field_registry_version: str,
    confirmed_by: str,
    confirmed_at: datetime,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_source_text": source_text,
        "condition_source_hash": source_hash,
        "condition_status": "confirmed",
        "condition_candidate_json": candidate_json,
        "condition_confirmed_json": candidate_json,
        "condition_issues_json": "[]",
        "condition_field_registry_version": field_registry_version,
        "condition_confirmed_by": confirmed_by,
        "condition_confirmed_at": confirmed_at,
    })


def manual_confirmation_update(
    source_text: str,
    source_hash: str,
    candidate_json: str,
    field_registry_version: str,
    confirmed_at: datetime,
) -> ConditionReviewStateUpdate:
    update = confirmation_update(
        source_text,
        source_hash,
        candidate_json,
        field_registry_version,
        "用户直接设定",
        confirmed_at,
    )
    return ConditionReviewStateUpdate({
        **update.values,
        "condition_confidence": 1.0,
        "condition_parser_version": "manual",
        "condition_parse_duration_ms": 0,
    })


def legacy_invalidation_update(
    source_text: str,
    source_hash: str,
    field_registry_version: str,
    issues_json: str,
) -> ConditionReviewStateUpdate:
    return ConditionReviewStateUpdate({
        "condition_source_text": source_text,
        "condition_source_hash": source_hash,
        "condition_status": "draft",
        "condition_candidate_json": None,
        "condition_confirmed_json": None,
        "condition_confidence": None,
        "condition_issues_json": issues_json,
        "condition_field_registry_version": field_registry_version,
        "condition_confirmed_by": None,
        "condition_confirmed_at": None,
    })
