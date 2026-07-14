"""
工艺规程规则提炼运行时服务。
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import Document, DocumentOperationDetail, Factor, Operation
from app.services.route_rules_document_details_runtime import (
    ensure_document_operation_details as _ensure_document_operation_details,
    extract_document_operation_details as _extract_document_operation_details,
)
from app.services.harness_validators import (
    is_harness_warning_factor_name,
    merge_validation_results,
    raise_for_harness_errors,
    validate_extracted_operations,
    validate_merged_route,
)
from app.services.route_rules_warning_helpers import (
    merge_harness_warning_factors as _merge_harness_warning_factors,
    recover_equipment_promoted_to_operation,
)


NormalizeOperationName = Callable[[str], str]
OperationChainInferer = Callable[[str, str], str]
TaskStateSetter = Callable[..., dict[str, Any]]


async def save_ops(
    db: AsyncSession,
    project_id: int,
    ops_data: list[dict[str, Any]],
    *,
    normalize_operation_name: NormalizeOperationName,
    preserve_sequence_slot: Callable[[str, int | str | None], bool],
    infer_operation_chain: OperationChainInferer,
) -> None:
    raise_for_harness_errors(
        validate_extracted_operations(ops_data),
        stage="save_operations",
    )

    name_seq_buckets: defaultdict[str, set[int]] = defaultdict(set)
    for item in ops_data:
        name = normalize_operation_name(item.get("name", ""))
        seq = int(item.get("seq", item.get("sequence", 0)) or 0)
        if name and seq > 0:
            name_seq_buckets[name].add(seq)

    seen_keys: set[tuple[str, int]] = set()
    for item in ops_data:
        name = normalize_operation_name(item["name"])
        seq = item.get("seq", item.get("sequence", 0))
        preserve_sequence = preserve_sequence_slot(name, seq) or len(name_seq_buckets[name]) > 1
        key = (name, int(seq or 0)) if preserve_sequence else (name, 0)
        if key in seen_keys:
            continue
        seen_keys.add(key)

        stmt = select(Operation).where(
            Operation.project_id == project_id,
            Operation.name == name,
        )
        if preserve_sequence:
            stmt = stmt.where(Operation.sequence == seq)
        existing = (await db.execute(stmt)).scalars().first()
        if existing:
            continue

        op = Operation(
            project_id=project_id,
            name=name,
            sequence=seq,
            chain=item.get("chain") or infer_operation_chain(name, item.get("desc", item.get("description", ""))),
            op_type=item.get("type", item.get("op_type", "MAIN")),
            description=item.get("desc", item.get("description", "")),
            source=item.get("source", "AI分析"),
            confidence=item.get("confidence", "STRONG"),
        )
        transient_warnings = list(item.get("harness_warnings") or [])
        transient_warnings.extend(list(item.get("harness_recovery_warnings") or []))
        if transient_warnings:
            existing_warnings = list(getattr(op, "_harness_warnings", []) or [])
            setattr(op, "_harness_warnings", existing_warnings + transient_warnings)
        db.add(op)
        await db.flush()

        persisted_factors = _merge_harness_warning_factors(
            item.get("factors", []),
            transient_warnings,
        )
        for factor_data in persisted_factors:
            if not isinstance(factor_data, dict) or not str(factor_data.get("name") or "").strip():
                continue
            factor = Factor(
                operation_id=op.id,
                name=factor_data["name"],
                evidence=factor_data.get("evidence", ""),
                strength=factor_data.get("strength", "STRONG"),
                confirmed=False if is_harness_warning_factor_name(factor_data.get("name")) else factor_data.get("strength", "STRONG") == "STRONG",
            )
            db.add(factor)


async def extract_document_operation_details(
    db: AsyncSession,
    project_id: int,
    *,
    detail_row_normalized_names: Callable[[str], list[str]],
    normalize_operation_name: NormalizeOperationName,
    docs: list[Document] | None = None,
) -> list[DocumentOperationDetail]:
    return await _extract_document_operation_details(
        db,
        project_id,
        detail_row_normalized_names=detail_row_normalized_names,
        normalize_operation_name=normalize_operation_name,
        docs=docs,
    )


async def ensure_document_operation_details(
    db: AsyncSession,
    project_id: int,
    *,
    extract_document_operation_details_fn: Callable[..., Any],
    progress_callback: Callable[[str, int], None] | None = None,
) -> list[DocumentOperationDetail]:
    return await _ensure_document_operation_details(
        db,
        project_id,
        extract_document_operation_details_fn=extract_document_operation_details_fn,
        progress_callback=progress_callback,
    )


async def extract_route_set_with_llm(
    db: AsyncSession,
    project_id: int,
    *,
    collect_candidate_summary: Callable[[list[Document]], tuple[dict[str, Any], list[str], dict[str, list[str]]]],
    ensure_document_operation_details_fn: Callable[..., Any],
    merge_document_detail_rows_into_candidate_summary: Callable[[dict[str, Any], dict[str, list[str]], list[DocumentOperationDetail], dict[int, str]], None],
    build_route_set_ops_from_candidates: Callable[[dict[str, Any], int, dict[str, list[str]] | None], list[dict[str, Any]]],
    set_extraction_task_state: TaskStateSetter,
) -> list[dict[str, Any]] | None:
    docs_result = await db.execute(select(Document).where(Document.project_id == project_id))
    docs = docs_result.scalars().all()
    if not docs:
        return None

    candidate_summary, doc_names, doc_orders = collect_candidate_summary(docs)
    if not candidate_summary:
        return None
    total_docs = len(doc_names)
    detail_rows = await ensure_document_operation_details_fn(
        db,
        project_id,
        progress_callback=lambda message, progress: set_extraction_task_state(
            project_id,
            task_status="running",
            stage="extracting_operations",
            message=message,
            progress=progress,
        ),
    )
    doc_name_map = {int(doc.id): str(doc.original_name or doc.filename or "") for doc in docs}
    merge_document_detail_rows_into_candidate_summary(candidate_summary, doc_orders, detail_rows, doc_name_map)

    set_extraction_task_state(
        project_id,
        task_status="running",
        stage="extracting_operations",
        message="正在汇总工艺路线全集...",
        progress=40,
    )

    ops_data = build_route_set_ops_from_candidates(candidate_summary, total_docs, doc_orders)
    ops_data = recover_equipment_promoted_to_operation(ops_data)
    raise_for_harness_errors(
        merge_validation_results(
            validate_extracted_operations(ops_data),
            validate_merged_route(ops_data),
        ),
        stage="route_set_candidates",
    )

    set_extraction_task_state(
        project_id,
        task_status="running",
        stage="extracting_operations",
        message="正在整理工艺路线全集...",
        progress=85,
    )
    return ops_data
