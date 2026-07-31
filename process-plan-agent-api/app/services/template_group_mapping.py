"""Controlled mapping suggestions constrained to the confirmed project template."""

from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import re
from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.schemas import (
    TemplateGroupMappingCandidateIn,
    TemplateGroupMappingOperationIn,
    TemplateGroupMappingSuggestRequest,
    TemplateGroupMappingSuggestResponse,
    TemplateGroupMappingSuggestionOut,
    TemplateStepMappingSuggestRequest,
    TemplateStepMappingSuggestResponse,
    TemplateStepMappingSuggestionOut,
)
from app.services.group_template_xml import is_feature_mapping_target
from app.services.llm_service import call_llm, parse_json_from_llm
from app.services.project_group_templates import (
    REVISION_CONFLICT_DETAIL,
    get_project_group_template,
    serialize_project_group_template,
    stable_step_key,
    step_text_hash,
)


logger = logging.getLogger(__name__)
MIN_ACCEPTED_CONFIDENCE = 0.90

_FEATURE_ALIASES: dict[str, tuple[str, ...]] = {
    "轴端面": ("端面", "平端面", "车端面"),
    "外圆柱面": ("外圆", "车外圆", "磨外圆", "研外圆"),
    "孔": ("孔", "钻孔", "镗孔", "铰孔", "研孔"),
    "孔(盲孔)": ("盲孔", "钻孔", "孔"),
    "孔(通孔)": ("通孔", "钻孔", "孔"),
    "U形外环槽": ("外环槽", "车槽", "铣槽", "磨槽"),
    "U形内环槽": ("内环槽", "车槽", "铣槽", "磨槽"),
    "倒角": ("倒角",),
    "内倒角": ("内倒角", "倒角"),
    "外倒角": ("外倒角", "倒角"),
    "边倒角": ("边倒角", "倒角"),
    "倒圆": ("倒圆", "磨圆"),
    "回转面倒圆": ("回转面倒圆", "倒圆", "磨圆"),
    "平面": ("平面", "铣面", "磨面"),
}


@dataclass(frozen=True)
class TemplateStepRef:
    operation_id: int
    operation_name: str
    step_key: str
    step_order: int
    step_name: str
    step_text_hash: str


def _clean_text(value: Any) -> str:
    return str(value or "").strip()


def _normalized_text(value: Any) -> str:
    return re.sub(r"[\s，,。；;：:（）()、/_-]+", "", _clean_text(value)).lower()


def _clean_confidence(value: Any) -> float:
    try:
        return max(0.0, min(float(value), 1.0))
    except (TypeError, ValueError):
        return 0.0


def _clean_text_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return list(dict.fromkeys(filter(None, (_clean_text(item) for item in value))))


def _flatten_template_nodes(tree: list[dict[str, object]]) -> list[dict[str, object]]:
    flattened: list[dict[str, object]] = []

    def visit(nodes: list[dict[str, object]]) -> None:
        for node in nodes:
            flattened.append(node)
            children = node.get("children", [])
            if isinstance(children, list):
                visit(children)

    visit(tree)
    return flattened


def _feature_terms(feature: str) -> list[str]:
    return list(dict.fromkeys([feature, *_FEATURE_ALIASES.get(feature, ())]))


def build_template_candidates(
    operation: TemplateGroupMappingOperationIn,
    tree: list[dict[str, object]],
) -> list[TemplateGroupMappingCandidateIn]:
    source = _normalized_text("\n".join([
        operation.operation_name,
        *operation.step_items,
        *operation.rule_evidence,
        *operation.rule_reasons,
    ]))
    if not source:
        return []

    scored: list[tuple[TemplateGroupMappingCandidateIn, bool, bool]] = []
    for node in _flatten_template_nodes(tree):
        path = [str(item) for item in node.get("path", [])] if isinstance(node.get("path"), list) else []
        features = (
            [str(item) for item in node.get("feature_selections", [])]
            if isinstance(node.get("feature_selections"), list)
            else []
        )
        name = str(node.get("name", ""))
        evidence: list[str] = []
        parent_match = False

        for parent_name in path[:-1]:
            normalized = _normalized_text(parent_name)
            if normalized and normalized in source:
                parent_match = True
                evidence.append(parent_name)

        leaf_match = bool(_normalized_text(name) and _normalized_text(name) in source)
        if leaf_match:
            evidence.append(name)

        feature_match = False
        for feature in features:
            for term in _feature_terms(feature):
                normalized = _normalized_text(term)
                if normalized and normalized in source:
                    feature_match = True
                    evidence.append(term)
                    break

        if not leaf_match and not feature_match:
            continue
        score = min(1.0, 0.45 + (0.25 if feature_match else 0.0) + (0.20 if parent_match else 0.0))
        scored.append((
            TemplateGroupMappingCandidateIn(
                group_id=str(node.get("key", "")),
                path=path,
                score=score,
                reason=f"原文命中：{'、'.join(dict.fromkeys(evidence))}",
            ),
            parent_match,
            bool(features),
        ))

    if any(parent_match for _, parent_match, _ in scored):
        scored = [item for item in scored if item[1]]
    if any(has_features for _, _, has_features in scored):
        scored = [item for item in scored if item[2]]
    return [candidate for candidate, _, _ in scored]


def build_step_candidates(
    step: TemplateStepRef,
    tree: list[dict[str, object]],
) -> list[TemplateGroupMappingCandidateIn]:
    step_source = _normalized_text(step.step_name)
    operation_source = _normalized_text(step.operation_name)
    if not step_source:
        return []

    scored: list[tuple[TemplateGroupMappingCandidateIn, bool]] = []
    for node in _flatten_template_nodes(tree):
        if not is_feature_mapping_target(node):
            continue
        raw_path = node.get("path", [])
        path = [str(item) for item in raw_path] if isinstance(raw_path, list) else []
        raw_features = node.get("feature_selections", [])
        features = [str(item) for item in raw_features] if isinstance(raw_features, list) else []
        name = str(node.get("name", ""))
        evidence: list[str] = []

        leaf_term = _normalized_text(name)
        leaf_match = bool(leaf_term and leaf_term in step_source)
        if leaf_match:
            evidence.append(name)

        feature_match = False
        for feature in features:
            for term in _feature_terms(feature):
                normalized = _normalized_text(term)
                if normalized and normalized in step_source:
                    feature_match = True
                    evidence.append(term)
                    break

        if not leaf_match and not feature_match:
            continue

        matching_ancestors = [
            parent
            for parent in path[:-1]
            if _normalized_text(parent) and _normalized_text(parent) in operation_source
        ]
        context_match = bool(matching_ancestors)
        evidence.extend(matching_ancestors)
        score = min(
            1.0,
            0.45 + (0.25 if feature_match else 0.0) + (0.20 if context_match else 0.0),
        )
        scored.append((
            TemplateGroupMappingCandidateIn(
                group_id=str(node.get("key", "")),
                path=path,
                score=score,
                reason=f"工步命中：{'、'.join(dict.fromkeys(evidence))}",
            ),
            context_match,
        ))

    if any(context_match for _, context_match in scored):
        scored = [item for item in scored if item[1]]
    return [candidate for candidate, _ in scored]


def prepare_step_candidates(
    operation: TemplateGroupMappingOperationIn,
    tree: list[dict[str, object]],
) -> list[tuple[TemplateStepRef, list[TemplateGroupMappingCandidateIn]]]:
    prepared: list[tuple[TemplateStepRef, list[TemplateGroupMappingCandidateIn]]] = []
    for order, raw_step in enumerate(operation.step_items, start=1):
        step_name = _clean_text(raw_step)
        if not step_name:
            continue
        ref = TemplateStepRef(
            operation_id=operation.operation_id,
            operation_name=operation.operation_name,
            step_key=stable_step_key(operation.operation_id, order),
            step_order=order,
            step_name=step_name,
            step_text_hash=step_text_hash(step_name),
        )
        prepared.append((ref, build_step_candidates(ref, tree)))
    return prepared


def _step_unresolved(
    step: TemplateStepRef,
    candidates: list[TemplateGroupMappingCandidateIn],
    *,
    confidence: float = 0.0,
    reason: str = "",
    warnings: list[str] | None = None,
) -> TemplateStepMappingSuggestionOut:
    return TemplateStepMappingSuggestionOut(
        operation_id=step.operation_id,
        operation_name=step.operation_name,
        step_key=step.step_key,
        step_order=step.step_order,
        step_name=step.step_name,
        step_text_hash=step.step_text_hash,
        candidates=candidates,
        confidence=confidence,
        source="unresolved",
        reason=reason or "没有找到可自动采用的唯一叶子分组。",
        warnings=warnings or [],
    )


def _deterministic_step_suggestion(
    step: TemplateStepRef,
    candidates: list[TemplateGroupMappingCandidateIn],
) -> TemplateStepMappingSuggestionOut:
    if len(candidates) != 1 or candidates[0].score < MIN_ACCEPTED_CONFIDENCE:
        return _step_unresolved(step, candidates)
    candidate = candidates[0]
    return TemplateStepMappingSuggestionOut(
        operation_id=step.operation_id,
        operation_name=step.operation_name,
        step_key=step.step_key,
        step_order=step.step_order,
        step_name=step.step_name,
        step_text_hash=step.step_text_hash,
        recommended_group_ids=[candidate.group_id],
        candidates=candidates,
        confidence=candidate.score,
        source="auto_confirmed",
        evidence=[step.step_name],
        reason=candidate.reason,
    )


def _validated_step_model_result(
    step: TemplateStepRef,
    candidates: list[TemplateGroupMappingCandidateIn],
    payload: dict[str, Any] | None,
) -> TemplateStepMappingSuggestionOut:
    if not payload:
        return _step_unresolved(step, candidates, warnings=["模型没有返回该工步的映射建议。"])
    group_ids = _clean_text_list(payload.get("group_ids"))
    confidence = _clean_confidence(payload.get("confidence"))
    reason = _clean_text(payload.get("reason"))
    allowed_ids = {candidate.group_id for candidate in candidates}
    if not group_ids or any(group_id not in allowed_ids for group_id in group_ids):
        return _step_unresolved(
            step,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["模型返回的分组不在该工步候选范围内，已忽略。"],
        )
    if confidence < MIN_ACCEPTED_CONFIDENCE:
        return _step_unresolved(
            step,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["模型置信度不足，保留为待人工确认。"],
        )
    evidence = _clean_text_list(payload.get("evidence"))
    source_text = f"{step.operation_name}\n{step.step_name}"
    if not evidence or any(item not in source_text for item in evidence):
        return _step_unresolved(
            step,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["模型证据不是工序或工步原文，已忽略。"],
        )
    return TemplateStepMappingSuggestionOut(
        operation_id=step.operation_id,
        operation_name=step.operation_name,
        step_key=step.step_key,
        step_order=step.step_order,
        step_name=step.step_name,
        step_text_hash=step.step_text_hash,
        recommended_group_ids=group_ids,
        candidates=candidates,
        confidence=confidence,
        source="llm",
        evidence=evidence,
        reason=reason,
    )


def _base_unresolved(
    operation: TemplateGroupMappingOperationIn,
    candidates: list[TemplateGroupMappingCandidateIn],
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
        candidate_group_ids=[candidate.group_id for candidate in candidates],
    )


def _validated_model_result(
    operation: TemplateGroupMappingOperationIn,
    candidates: list[TemplateGroupMappingCandidateIn],
    payload: dict[str, Any] | None,
) -> TemplateGroupMappingSuggestionOut:
    if not payload:
        return _base_unresolved(operation, candidates, warnings=["模型没有返回该工序的映射建议。"])

    group_id = _clean_text(payload.get("group_id"))
    confidence = _clean_confidence(payload.get("confidence"))
    reason = _clean_text(payload.get("reason"))
    allowed_ids = {candidate.group_id for candidate in candidates}
    if not group_id or group_id not in allowed_ids:
        return _base_unresolved(
            operation,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["模型返回的分组不在当前工序候选范围内，已忽略。"],
        )
    if len(candidates) != 1:
        return _base_unresolved(
            operation,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["当前工序存在多个候选分组，必须由用户确认。"],
        )
    if confidence < MIN_ACCEPTED_CONFIDENCE:
        return _base_unresolved(
            operation,
            candidates,
            confidence=confidence,
            reason=reason,
            warnings=["模型置信度不足，保留为待人工确认。"],
        )

    model_evidence = _clean_text_list(payload.get("evidence"))
    source_text = "\n".join([operation.operation_name, *operation.step_items, *operation.rule_evidence])
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
        candidate_group_ids=[candidate.group_id for candidate in candidates],
    )


async def resolve_template_group_mappings(
    db: AsyncSession,
    body: TemplateGroupMappingSuggestRequest,
) -> TemplateGroupMappingSuggestResponse:
    if not body.operations:
        return TemplateGroupMappingSuggestResponse(project_id=body.project_id)

    template_row = await get_project_group_template(db, body.project_id)
    if template_row is None:
        return TemplateGroupMappingSuggestResponse(
            project_id=body.project_id,
            suggestions=[_base_unresolved(operation, []) for operation in body.operations],
            warnings=["当前项目尚未确认分组模板，请先上传模板后再使用智能映射。"],
        )
    tree = serialize_project_group_template(template_row).tree
    prepared = [
        (operation, build_template_candidates(operation, tree))
        for operation in body.operations
    ]

    system_prompt = """你是机械加工模板分组审核器。只输出 JSON，不要输出 Markdown。
你只能为每道工序从其 candidates 中选择 group_id，禁止创造、改写或跨工序复用 ID。
只有原始工序名或工步能够支持具体位置与特征时才选择；无法可靠判断时返回 group_id=null。
evidence 必须逐字摘自 operation_name 或 step_items。confidence 范围为 0 到 1。
输出格式：{"suggestions":[{"operation_id":1,"group_id":"候选ID或null","confidence":0.8,"evidence":["原文片段"],"reason":"简短理由"}]}。"""
    user_payload = {
        "project_id": body.project_id,
        "operations": [
            {
                **operation.model_dump(),
                "candidates": [candidate.model_dump() for candidate in candidates],
            }
            for operation, candidates in prepared
        ],
    }
    try:
        raw = await call_llm(
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False),
            temperature=0.0,
            timeout_seconds=12.0,
            max_retries=0,
        )
    except Exception as exc:
        logger.warning("template_group_mapping_llm_failed project_id=%s error=%s", body.project_id, exc)
        return TemplateGroupMappingSuggestResponse(
            project_id=body.project_id,
            suggestions=[_base_unresolved(operation, candidates) for operation, candidates in prepared],
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
            _validated_model_result(
                operation,
                candidates,
                payload_by_operation.get(operation.operation_id),
            )
            for operation, candidates in prepared
        ],
        warnings=warnings,
    )


async def resolve_template_step_mappings(
    db: AsyncSession,
    body: TemplateStepMappingSuggestRequest,
) -> TemplateStepMappingSuggestResponse:
    if not body.operations:
        return TemplateStepMappingSuggestResponse(
            project_id=body.project_id,
            template_revision=0,
        )

    template_row = await get_project_group_template(db, body.project_id)
    if template_row is None:
        return TemplateStepMappingSuggestResponse(
            project_id=body.project_id,
            template_revision=0,
            suggestions=[
                _step_unresolved(
                    step,
                    [],
                    warnings=["当前项目尚未确认分组模板，请先上传模板。"],
                )
                for operation in body.operations
                for step, _ in prepare_step_candidates(operation, [])
            ],
            warnings=["当前项目尚未确认分组模板，请先上传模板。"],
        )

    template_revision = int(template_row.template_revision)
    if template_revision != body.expected_template_revision:
        raise HTTPException(409, REVISION_CONFLICT_DETAIL)
    tree = serialize_project_group_template(template_row).tree
    prepared = [
        (step, candidates)
        for operation in body.operations
        for step, candidates in prepare_step_candidates(operation, tree)
    ]
    suggestions = [
        _deterministic_step_suggestion(step, candidates)
        for step, candidates in prepared
    ]
    ambiguous = [
        (step, candidates)
        for (step, candidates), suggestion in zip(prepared, suggestions)
        if suggestion.source == "unresolved" and candidates
    ]
    if not ambiguous:
        return TemplateStepMappingSuggestResponse(
            project_id=body.project_id,
            template_revision=template_revision,
            suggestions=suggestions,
        )

    system_prompt = """你是机械加工工步与模板特征审核器。只输出 JSON，不要输出 Markdown。
每个 suggestion 只处理一个 step_key。你只能从该工步 candidates 中选择 group_ids，禁止创造或改写 ID。
证据必须逐字摘自 step_name 或 operation_name；无法可靠判断时返回空 group_ids。
输出格式：{"suggestions":[{"step_key":"op_1_s01","group_ids":["grp_x"],"confidence":0.9,"evidence":["钻孔"],"reason":"简短理由"}]}。"""
    user_payload = {
        "project_id": body.project_id,
        "steps": [
            {
                "operation_id": step.operation_id,
                "operation_name": step.operation_name,
                "step_key": step.step_key,
                "step_order": step.step_order,
                "step_name": step.step_name,
                "candidates": [candidate.model_dump() for candidate in candidates],
            }
            for step, candidates in ambiguous
        ],
    }
    try:
        raw = await call_llm(
            system_prompt,
            json.dumps(user_payload, ensure_ascii=False),
            temperature=0.0,
            timeout_seconds=12.0,
            max_retries=0,
        )
    except Exception as exc:
        logger.warning("template_step_mapping_llm_failed project_id=%s error=%s", body.project_id, exc)
        return TemplateStepMappingSuggestResponse(
            project_id=body.project_id,
            template_revision=template_revision,
            suggestions=[
                suggestion if suggestion.source != "unresolved" or not candidates
                else _step_unresolved(
                    step,
                    candidates,
                    warnings=["模型调用失败，已保留程序候选供人工选择。"],
                )
                for (step, candidates), suggestion in zip(prepared, suggestions)
            ],
            warnings=["模型调用失败，已保留程序候选供人工选择。"],
        )

    parsed = parse_json_from_llm(raw) if raw else None
    rows = parsed.get("suggestions") if isinstance(parsed, dict) else parsed if isinstance(parsed, list) else []
    rows = rows if isinstance(rows, list) else []
    payload_by_step: dict[str, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        step_key = _clean_text(row.get("step_key"))
        if step_key and step_key not in payload_by_step:
            payload_by_step[step_key] = row

    model_used = bool(raw and parsed is not None)
    resolved_suggestions: list[TemplateStepMappingSuggestionOut] = []
    for (step, candidates), suggestion in zip(prepared, suggestions):
        if suggestion.source != "unresolved" or not candidates:
            resolved_suggestions.append(suggestion)
            continue
        resolved_suggestions.append(
            _validated_step_model_result(step, candidates, payload_by_step.get(step.step_key))
        )
    warnings = [] if model_used else ["模型未返回有效结构化结果，已保留程序候选供人工选择。"]
    return TemplateStepMappingSuggestResponse(
        project_id=body.project_id,
        template_revision=template_revision,
        model_used=model_used,
        suggestions=resolved_suggestions,
        warnings=warnings,
    )
