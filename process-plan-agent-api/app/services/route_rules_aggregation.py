"""
工艺规程模式下的候选工序汇总、路线全集构造与上下文拼装。
"""

from __future__ import annotations

import asyncio
import logging
import os
from collections import defaultdict
from collections.abc import Callable

from app.core.paths import UPLOAD_DIR
from app.models.models import Document, DocumentOperationDetail
from app.services.extraction_parallel import run_extraction_cpu
from app.services.file_parser import extract_text
from app.services.route_candidate_summary import (
    build_missing_route_candidates as _build_missing_route_candidates,
    build_route_set_ops_from_candidates as _build_route_set_ops_from_candidates,
    dedupe_and_refine_ops as _dedupe_and_refine_ops,
    describe_route_set_candidate as _describe_route_set_candidate,
)
from app.services.route_rules_parsing import (
    _extract_operations_from_text,
    _normalize_operation_name,
    _split_combined_operation_names,
)


logger = logging.getLogger(__name__)


build_missing_route_candidates = _build_missing_route_candidates
build_route_set_ops_from_candidates = _build_route_set_ops_from_candidates
dedupe_and_refine_ops = _dedupe_and_refine_ops
describe_route_set_candidate = _describe_route_set_candidate


def _summarize_one_document(
    filename: str,
    file_type: str | None,
    original_name: str,
) -> tuple[str, list[dict], list[str]]:
    filepath = os.path.join(UPLOAD_DIR, filename)
    text = extract_text(filepath, file_type, max_chars=None)
    logger.info("[Extract] 已提取文档 %s 内容，长度: %s 字符", original_name, len(text))
    candidates = _extract_operations_from_text(text, original_name)
    ordered_items = sorted(
        candidates,
        key=lambda row: (int(row.get("sequence") or 0), _normalize_operation_name(str(row.get("name") or ""))),
    )
    ordered_names: list[str] = []
    seen_in_doc: set[str] = set()
    for item in ordered_items:
        key_name = _normalize_operation_name(item["name"])
        if key_name and key_name not in seen_in_doc:
            seen_in_doc.add(key_name)
            ordered_names.append(key_name)
    return original_name, ordered_items, ordered_names


def _merge_ordered_items_into_summary(
    grouped: dict[str, dict],
    original_name: str,
    ordered_items: list[dict],
) -> None:
    total_in_doc = max(1, len(ordered_items))
    for idx, item in enumerate(ordered_items):
        key = _normalize_operation_name(item["name"])
        if key not in grouped:
            grouped[key] = {
                "name": key,
                "sequences": [],
                "sources": set(),
                "card_sources": set(),
                "occurrences": [],
            }
        grouped[key]["sequences"].append(item["sequence"])
        grouped[key]["sources"].add(original_name)
        if item.get("from_card"):
            grouped[key]["card_sources"].add(original_name)
        grouped[key]["occurrences"].append(
            {
                "source": original_name,
                "sequence": int(item.get("sequence") or 0),
                "from_card": bool(item.get("from_card")),
                "index": idx,
                "total": total_in_doc,
            }
        )


async def _collect_candidate_summary(
    docs: list[Document],
    progress_callback: Callable[[str, int], None] | None = None,
) -> tuple[dict[str, dict], list[str], dict[str, list[str]]]:
    grouped: dict[str, dict] = {}
    doc_names: list[str] = []
    doc_orders: dict[str, list[str]] = {}
    total = len(docs)
    if progress_callback and total:
        progress_callback(f"正在读取工艺文档（0/{total}）...", 12)

    results: list[tuple[str, list[dict], list[str]] | None] = [None] * total
    completed = 0
    progress_lock = asyncio.Lock()

    async def _run_one(index: int, doc: Document) -> None:
        nonlocal completed
        original_name = str(doc.original_name or doc.filename or "")
        results[index] = await run_extraction_cpu(
            _summarize_one_document,
            str(doc.filename or ""),
            doc.file_type,
            original_name,
        )
        async with progress_lock:
            completed += 1
            done = completed
        if progress_callback:
            progress_callback(
                f"正在读取工艺文档（{done}/{total}）: {original_name}",
                12 + int((done / max(total, 1)) * 16),
            )

    if docs:
        await asyncio.gather(*[_run_one(index, doc) for index, doc in enumerate(docs)])

    for result in results:
        if result is None:
            continue
        original_name, ordered_items, ordered_names = result
        doc_names.append(original_name)
        if ordered_names:
            doc_orders[original_name] = ordered_names
        _merge_ordered_items_into_summary(grouped, original_name, ordered_items)

    return grouped, doc_names, doc_orders


def _merge_document_detail_rows_into_candidate_summary(
    candidate_summary: dict[str, dict],
    doc_orders: dict[str, list[str]],
    detail_rows: list[DocumentOperationDetail],
    doc_name_map: dict[int, str],
) -> None:
    if not detail_rows:
        return

    existing_occurrence_keys: set[tuple[str, int, str]] = set()
    for name, meta in candidate_summary.items():
        for occ in meta.get("occurrences") or []:
            existing_occurrence_keys.add(
                (
                    str(occ.get("source") or "").strip(),
                    int(occ.get("sequence") or 0),
                    _normalize_operation_name(name),
                )
            )

    detail_entries_by_doc: defaultdict[str, list[tuple[int, str]]] = defaultdict(list)
    detail_name_sets_by_doc: defaultdict[str, set[str]] = defaultdict(set)

    for row in detail_rows:
        source_name = doc_name_map.get(int(row.document_id or 0)) or str(row.pdf_name or "").strip()
        if not source_name:
            continue
        raw_name = _normalize_operation_name(row.normalized_name or row.operation_name or "")
        split_names = _split_combined_operation_names(raw_name) or ([raw_name] if raw_name else [])
        seq = int(row.operation_seq or 0)
        for name in split_names:
            normalized_name = _normalize_operation_name(name)
            if not normalized_name:
                continue
            meta = candidate_summary.setdefault(
                normalized_name,
                {
                    "name": normalized_name,
                    "sequences": [],
                    "sources": set(),
                    "card_sources": set(),
                    "occurrences": [],
                },
            )
            meta["sources"].add(source_name)
            meta["card_sources"].add(source_name)
            occurrence_key = (source_name, seq, normalized_name)
            if occurrence_key not in existing_occurrence_keys:
                meta["sequences"].append(seq)
                detail_entries_by_doc[source_name].append((seq, normalized_name))
                existing_occurrence_keys.add(occurrence_key)
            detail_name_sets_by_doc[source_name].add(normalized_name)

    for source_name, names in detail_name_sets_by_doc.items():
        existing_order = list(doc_orders.get(source_name) or [])
        seen = set(existing_order)
        for _, name in sorted(detail_entries_by_doc.get(source_name, []), key=lambda item: (item[0], item[1])):
            if name in seen:
                continue
            existing_order.append(name)
            seen.add(name)
        for name in sorted(names):
            if name in seen:
                continue
            existing_order.append(name)
            seen.add(name)
        if existing_order:
            doc_orders[source_name] = existing_order

    for source_name, entries in detail_entries_by_doc.items():
        ordered_entries = sorted(entries, key=lambda item: (item[0], item[1]))
        total_in_doc = max(1, len(ordered_entries))
        for idx, (seq, name) in enumerate(ordered_entries):
            candidate_summary[name]["occurrences"].append(
                {
                    "source": source_name,
                    "sequence": seq,
                    "from_card": True,
                    "index": idx,
                    "total": total_in_doc,
                }
            )
