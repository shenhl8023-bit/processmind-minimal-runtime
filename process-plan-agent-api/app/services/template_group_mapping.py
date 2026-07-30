"""Controlled batch LLM resolver for template-group mapping candidates."""

from __future__ import annotations

import json
import logging
from typing import Any

from app.schemas.schemas import (
    TemplateGroupMappingOperationIn,
    TemplateGroupMappingSuggestRequest,
    TemplateGroupMappingSuggestResponse,
    TemplateGroupMappingSuggestionOut,
)
from app.services.llm_service import call_llm, parse_json_from_llm


logger = logging.getLogger(__name__)
MIN_ACCEPTED_CONFIDENCE = 0.65


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _clean_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(filter(None, (_clean_text(item) for item in value))))


def _base_unresolved(
    operation: TemplateGroupMappingOperationIn,
    *,
    confidence: float = 0.0,
    reason: str = "",
    warnings: list[str] | None = None,
) -> TemplateGroupMappingSuggestionOut:
    return TemplateGroupMappingSuggestionOut(
        operation_id=operation.operation_id,
        confidence=confidence,
        source="unresolved",
        evidence=list(operation.rule_evidence),
        reason=reason or "模型未能在合法候选中给出可靠选择。",
        warnings=warnings or [],
        candidate_group_ids=[candidate.group_id for candidate in operation.candidates],
    )


def _validated_model_result(
    operation: TemplateGroupMappingOperationIn,
    payload: dict[str, Any] | None,
) -> TemplateGroupMappingSuggestionOut:
    if not payload:
        return _base_unresolved(operation, warnings=["模型没有返回该工序的映射建议。"])

    group_id = _clean_text(payload.get("group_id"))
    confidence = _clean_confidence(payload.get("confidence"))
    reason = _clean_text(payload.get("reason"))
    allowed_ids = {candidate.group_id for candidate in operation.candidates}
    if not group_id or group_id not in allowed_ids:
        return _base_unresolved(
            operation,
            confidence=confidence,
            reason=reason,
            warnings=["模型返回的分组不在当前工序候选范围内，已忽略。"],
        )
    if confidence < MIN_ACCEPTED_CONFIDENCE:
        return _base_unresolved(
            operation,
            confidence=confidence,
            reason=reason,
            warnings=["模型置信度不足，保留为待人工确认。"],
        )

    model_evidence = _clean_text_list(payload.get("evidence"))
    source_text = "\n".join([
        operation.operation_name,
        *operation.step_items,
        *operation.rule_evidence,
    ])
    evidence_is_valid = bool(model_evidence) and all(item in source_text for item in model_evidence)
    warnings: list[str] = []
    evidence = model_evidence
    if not evidence_is_valid:
        evidence = list(operation.rule_evidence)
        if model_evidence:
            warnings.append("模型证据未出现在原始工序信息中，已改用规则证据。")

    return TemplateGroupMappingSuggestionOut(
        operation_id=operation.operation_id,
        group_id=group_id,
        confidence=confidence,
        source="llm",
        evidence=evidence,
        reason=reason,
        warnings=warnings,
        candidate_group_ids=[candidate.group_id for candidate in operation.candidates],
    )


async def resolve_template_group_mappings(
    body: TemplateGroupMappingSuggestRequest,
) -> TemplateGroupMappingSuggestResponse:
    if not body.operations:
        return TemplateGroupMappingSuggestResponse(project_id=body.project_id)

    system_prompt = """你是机械加工模板分组审核器。只输出 JSON，不要输出 Markdown。
你只能为每道工序从其 candidates 中选择 group_id，禁止创造、改写或跨工序复用 ID。
只有原始工序名或工步能够支持具体位置与特征时才选择；不能判断 A侧、B侧或周边时返回 group_id=null。
evidence 必须逐字摘自 operation_name 或 step_items。confidence 范围为 0 到 1。
输出格式：{"suggestions":[{"operation_id":1,"group_id":"候选ID或null","confidence":0.8,"evidence":["原文片段"],"reason":"简短理由"}]}。"""
    user_payload = {
        "project_id": body.project_id,
        "operations": [operation.model_dump() for operation in body.operations],
    }
    try:
        raw = await call_llm(
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False),
            temperature=0.0,
            timeout_seconds=45.0,
            max_retries=1,
        )
    except Exception as exc:  # model availability must not block manual mapping
        logger.warning("template_group_mapping_llm_failed project_id=%s error=%s", body.project_id, exc)
        return TemplateGroupMappingSuggestResponse(
            project_id=body.project_id,
            suggestions=[_base_unresolved(item) for item in body.operations],
            warnings=["模型调用失败，已保留程序候选供人工选择。"],
        )

    parsed = parse_json_from_llm(raw) if raw else None
    rows = parsed.get("suggestions") if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
    rows = rows if isinstance(rows, list) else []
    payload_by_operation: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        try:
            operation_id = int(row.get("operation_id") or 0)
        except (TypeError, ValueError):
            continue
        if operation_id > 0 and operation_id not in payload_by_operation:
            payload_by_operation[operation_id] = row

    model_used = bool(raw and parsed is not None)
    warnings = [] if model_used else ["模型未返回有效结构化结果，已保留程序候选供人工选择。"]
    return TemplateGroupMappingSuggestResponse(
        project_id=body.project_id,
        model_used=model_used,
        suggestions=[
            _validated_model_result(operation, payload_by_operation.get(operation.operation_id))
            for operation in body.operations
        ],
        warnings=warnings,
    )
