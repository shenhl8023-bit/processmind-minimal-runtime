"""
工艺规程模式下的工序文本解析与顺序归一工具。
"""

from __future__ import annotations

import os
import re
from collections import defaultdict

from app.core.paths import UPLOAD_DIR
from app.models.models import Document, Operation
from app.services.file_parser import extract_text
from app.services.harness_validators import HARNESS_WARNING_FACTOR_PREFIX, is_harness_warning_factor_name
from app.services.operation_review_meta import build_operation_review_meta
from app.services.route_rules_operation_names import (
    KNOWN_OPERATION_NAMES,
    PROCESS_HINTS,
    _clean_text_line,
    _detail_row_normalized_names,
    _extract_inline_operation_names,
    _infer_operation_chain,
    _is_general_main_operation,
    _is_repeatable_operation_name,
    _looks_like_equipment_name,
    _looks_like_operation_name,
    _looks_like_sequence_break,
    _merge_serialized_operations,
    _normalize_operation_name,
    _normalize_sequence_number,
    _operation_key,
    _preserve_sequence_slot,
    _split_combined_operation_names,
)
from app.services.route_rules_ordering import (
    _preferred_route_sequence,
    _repeatable_stage_slots,
    _representative_operation_sequence,
    _resequence_route_ops,
    _resolve_route_order,
)

CARD_BOUNDARY_TOKENS = ("会", "签", "设备名称", "设备型号", "工序号", "技术要求")
NAME_FIELD_STOP_TOKENS = (
    "材料牌号", "毛坯类型", "协作单位", "硬度", "设备名称", "设备型号",
    "工艺装备", "夹具图号", "刀具图号", "量具图号", "备注", "技术要求",
    "特殊过程", "共", "第",
)


def _operation_harness_warnings(op: Operation) -> list[dict[str, str]]:
    warnings: list[dict[str, str]] = [dict(item) for item in list(getattr(op, "_harness_warnings", []) or [])]
    for factor in op.factors:
        if is_harness_warning_factor_name(factor.name):
            code = str(factor.name or "").strip()[len(HARNESS_WARNING_FACTOR_PREFIX):] or "UNKNOWN"
            warnings.append({
                "code": code,
                "message": str(factor.evidence or "").strip() or "Harness 自动恢复记录。",
                "target": str(op.name or "").strip(),
                "suggested_action": "仅作为审核提醒，不作为正式工艺触发条件。",
            })
            continue
        if str(factor.name or "").strip() and not str(factor.evidence or "").strip():
            warnings.append({
                "code": "MISSING_FACTOR_EVIDENCE",
                "message": "因素规则缺少 evidence，后续审核和回放会缺少依据。",
                "target": str(factor.name or op.name or "").strip(),
                "suggested_action": "补充样本覆盖、反例边界或人工判断依据。",
            })
    return warnings


def _serialize_operation(op: Operation, sample_count: int) -> dict:
    review_meta = build_operation_review_meta(op, sample_count)
    return {
        "id": op.id,
        "project_id": op.project_id,
        "name": op.name,
        "sequence": op.sequence,
        "chain": op.chain,
        "op_type": op.op_type,
        "description": op.description,
        "source": op.source,
        "confidence": op.confidence,
        "factors": [
            {
                "id": factor.id,
                "name": factor.name,
                "evidence": factor.evidence,
                "strength": factor.strength,
                "confirmed": factor.confirmed,
            }
            for factor in op.factors
            if not is_harness_warning_factor_name(factor.name)
        ],
        "harness_warnings": _operation_harness_warnings(op),
        **review_meta,
    }


def _build_document_operation_orders(docs: list[Document]) -> dict[str, list[str]]:
    doc_orders: dict[str, list[str]] = {}
    for doc in docs:
        filepath = os.path.join(UPLOAD_DIR, doc.filename)
        text = extract_text(filepath, doc.file_type, max_chars=None)
        if not text:
            continue
        candidates = _extract_operations_from_text(text, doc.original_name)
        if not candidates:
            continue
        ordered = sorted(
            candidates,
            key=lambda item: (
                int(item.get("sequence") or 0),
                _normalize_operation_name(str(item.get("name") or "")),
            ),
        )
        names: list[str] = []
        seen: set[str] = set()
        for item in ordered:
            name = _normalize_operation_name(str(item.get("name") or ""))
            if not name or name in seen or _looks_like_equipment_name(name):
                continue
            seen.add(name)
            names.append(name)
        if names:
            doc_orders[doc.original_name] = names
    return doc_orders


def _extract_names_from_name_field_line(line: str) -> list[str]:
    cleaned = _clean_text_line(line)
    if not cleaned or "名称" not in cleaned:
        return []
    if cleaned.startswith("零组件名称") or cleaned.startswith("产品名称"):
        return []

    tail = cleaned.split("名称", 1)[1]
    if not tail:
        return []
    for token in NAME_FIELD_STOP_TOKENS:
        if token in tail:
            tail = tail.split(token, 1)[0]
    tail = tail.strip("：:;；，,、/ ")
    if not tail:
        return []

    split_names = _extract_inline_operation_names(tail)
    if split_names:
        return split_names

    normalized = _normalize_operation_name(tail)
    if _looks_like_operation_name(normalized):
        return [normalized]
    return []


def _extract_operations_from_text(text: str, source_name: str) -> list[dict]:
    lines = [_clean_text_line(line) for line in text.splitlines()]
    lines = [line for line in lines if line]

    ops: list[dict] = []
    seen: set[tuple[int, str, int]] = set()

    def add_op(name: str, seq: int, from_card: bool = False) -> None:
        split_names = _split_combined_operation_names(name) or [_normalize_operation_name(name)]
        local_occurrences: defaultdict[str, int] = defaultdict(int)
        for normalized_name in split_names:
            occurrence_index = local_occurrences[normalized_name]
            local_occurrences[normalized_name] += 1
            key = (seq, normalized_name, occurrence_index)
            if not normalized_name or key in seen:
                continue
            seen.add(key)
            ops.append({
                "name": normalized_name,
                "sequence": seq,
                "source": source_name,
                "from_card": from_card,
            })

    def extract_card_page_ops(card_lines: list[str]) -> list[tuple[list[str], int]]:
        if not any("工序号" in line for line in card_lines):
            return []

        card_ops: list[tuple[list[str], int]] = []
        seen_card_keys: set[tuple[int, str, int]] = set()
        header_indices = [idx for idx, line in enumerate(card_lines) if "工序号" in line]

        for header_idx in header_indices:
            seq = 0
            seq_idx = header_idx
            header_line = card_lines[header_idx]

            inline_seq = re.search(r"工序号[:：]?\s*(\d{1,3})", header_line)
            if inline_seq:
                seq = _normalize_sequence_number(inline_seq.group(1))

            if not seq:
                window_start = max(0, header_idx - 3)
                window_end = min(len(card_lines), header_idx + 5)
                for pos in range(window_start, window_end):
                    if pos == header_idx:
                        continue
                    maybe_seq = _normalize_sequence_number(card_lines[pos])
                    if maybe_seq:
                        seq = maybe_seq
                        seq_idx = pos
                        break

            names: list[str] = []
            if seq:
                upper_bound = min(len(card_lines), max(seq_idx, header_idx) + 14)
                for candidate in card_lines[min(seq_idx, header_idx): upper_bound]:
                    explicit_names = _extract_names_from_name_field_line(candidate)
                    if explicit_names:
                        names = explicit_names
                        break
                    split_names = _extract_inline_operation_names(candidate)
                    if split_names:
                        names = split_names
                        break
                    normalized_candidate = _normalize_operation_name(candidate)
                    if _looks_like_operation_name(normalized_candidate):
                        names = [normalized_candidate]
                        break

            if not names:
                lower_bound = max(0, header_idx - 6)
                for candidate in reversed(card_lines[lower_bound: header_idx]):
                    explicit_names = _extract_names_from_name_field_line(candidate)
                    if explicit_names:
                        names = explicit_names
                        break
                    split_names = _extract_inline_operation_names(candidate)
                    if split_names:
                        names = split_names
                        break
                    normalized_candidate = _normalize_operation_name(candidate)
                    if _looks_like_operation_name(normalized_candidate):
                        names = [normalized_candidate]
                        break

            for idx, line in enumerate(card_lines):
                if "工序" not in line:
                    continue
                explicit_names = _extract_names_from_name_field_line(line)
                if explicit_names:
                    names = explicit_names
                    break
                if line == "工序" and idx + 2 < len(card_lines) and card_lines[idx + 1] == "名称":
                    explicit_names = _extract_names_from_name_field_line(card_lines[idx + 2])
                    if explicit_names:
                        names = explicit_names
                        break
                    split_names = _extract_inline_operation_names(card_lines[idx + 2])
                    if split_names:
                        names = split_names
                        break
                    candidate = _normalize_operation_name(card_lines[idx + 2])
                    if _looks_like_operation_name(candidate):
                        names = [candidate]
                        break
                for candidate in card_lines[idx + 1: idx + 6]:
                    explicit_names = _extract_names_from_name_field_line(candidate)
                    if explicit_names:
                        names = explicit_names
                        break
                    split_names = _extract_inline_operation_names(candidate)
                    if split_names:
                        names = split_names
                        break
                    normalized_candidate = _normalize_operation_name(candidate)
                    if _looks_like_operation_name(normalized_candidate):
                        names = [normalized_candidate]
                        break
                if names:
                    break

            if names and seq:
                deduped_names: list[str] = []
                local_occurrences: defaultdict[str, int] = defaultdict(int)
                for name in names:
                    occurrence_index = local_occurrences[name]
                    local_occurrences[name] += 1
                    key = (seq, name, occurrence_index)
                    if key in seen_card_keys:
                        continue
                    seen_card_keys.add(key)
                    deduped_names.append(name)
                if deduped_names:
                    card_ops.append((deduped_names, seq))

        return card_ops

    card_ranges: list[tuple[int, int]] = []
    raw_starts = [idx for idx, line in enumerate(lines) if line == "工序卡片" or "工序号" in line]
    card_starts: list[int] = []
    for idx in raw_starts:
        start_idx = max(0, idx - 8)
        if card_starts and start_idx - card_starts[-1] <= 3:
            continue
        card_starts.append(start_idx)

    for pos, start in enumerate(card_starts):
        end = card_starts[pos + 1] if pos + 1 < len(card_starts) else len(lines)
        for idx in range(start + 1, end):
            if "综合目录" in lines[idx]:
                end = idx
                break
        segment = lines[start:end]
        card_ops = extract_card_page_ops(segment)
        if card_ops:
            for names, seq in card_ops:
                for op_name in names:
                    add_op(op_name, seq, from_card=True)
            card_ranges.append((start, end))

    def in_card_range(index: int) -> bool:
        for start, end in card_ranges:
            if start <= index < end:
                return True
        return False

    for idx, line in enumerate(lines):
        if in_card_range(idx):
            continue

        seq = None
        op_name = ""

        exact_num = re.fullmatch(r"(\d{1,3})", line)
        inline_num = re.fullmatch(r"(\d{1,3})[.、]?(.*)", line)

        if exact_num:
            seq = _normalize_sequence_number(exact_num.group(1))
            candidate_names: list[str] = []
            for j in range(idx + 1, min(idx + 10, len(lines))):
                if in_card_range(j):
                    continue
                if _looks_like_sequence_break(lines[j]):
                    break
                if any(boundary in lines[j] for boundary in CARD_BOUNDARY_TOKENS):
                    break
                split_names = _extract_inline_operation_names(lines[j])
                if split_names:
                    candidate_names = split_names
                    break
                normalized_candidate = _normalize_operation_name(lines[j])
                if _looks_like_operation_name(normalized_candidate):
                    candidate_names = [normalized_candidate]
                    break
            if candidate_names:
                for candidate_name in candidate_names:
                    add_op(candidate_name, seq)
                continue

        elif inline_num:
            maybe_seq = _normalize_sequence_number(inline_num.group(1))
            raw_tail = inline_num.group(2) or ""
            maybe_name = _normalize_operation_name(raw_tail)
            if maybe_seq and _looks_like_operation_name(maybe_name):
                seq = maybe_seq
                op_name = maybe_name
            elif maybe_seq:
                split_names = _extract_inline_operation_names(raw_tail)
                if split_names:
                    for split_name in split_names:
                        add_op(split_name, maybe_seq)
                    continue

        if seq is None or not op_name:
            table_match = re.fullmatch(r"(\d{1,3})[|｜](.+)", line)
            if table_match:
                maybe_seq = _normalize_sequence_number(table_match.group(1))
                rest = table_match.group(2)
                parts = [part.strip() for part in re.split(r"[|｜]", rest) if part.strip()]
                for part in parts:
                    normalized_part = _normalize_operation_name(part)
                    if maybe_seq and _looks_like_operation_name(normalized_part):
                        seq = maybe_seq
                        op_name = normalized_part
                        break

        if seq is None or not op_name:
            continue

        add_op(op_name, seq)

    if ops:
        return ops

    inferred_seq = 10
    for idx, line in enumerate(lines):
        if in_card_range(idx):
            continue
        split_names = _extract_inline_operation_names(line)
        normalized_line = _normalize_operation_name(line)
        if not split_names and not _looks_like_operation_name(normalized_line):
            continue

        next_line = lines[idx + 1] if idx + 1 < len(lines) else ""
        if not next_line:
            continue
        if _looks_like_operation_name(next_line):
            continue
        if "&&" not in next_line and len(next_line) < 6 and not any(token in next_line for token in PROCESS_HINTS):
            continue

        names_to_add = split_names or [normalized_line]
        added = False
        for normalized_name in names_to_add:
            if not normalized_name:
                continue
            ops.append({
                "name": normalized_name,
                "sequence": inferred_seq,
                "source": source_name,
                "from_card": False,
            })
            added = True
        if not added:
            continue
        inferred_seq += 10

    return ops
