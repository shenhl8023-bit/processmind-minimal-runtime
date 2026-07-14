"""
候选工序统计、重复槽位推断与路线全集候选组装。
"""

from __future__ import annotations

from collections import defaultdict

from app.services.route_rules_parsing import (
    _infer_operation_chain,
    _is_general_main_operation,
    _is_repeatable_operation_name,
    _looks_like_equipment_name,
    _normalize_operation_name,
    _operation_key,
    _preferred_route_sequence,
    _preserve_sequence_slot,
    _repeatable_stage_slots,
    _representative_operation_sequence,
    _resequence_route_ops,
)


def build_missing_route_candidates(candidate_summary: dict[str, dict], existing_keys: set[tuple[str, int]], total_docs: int) -> list[dict]:
    backfilled: list[dict] = []
    if total_docs <= 0:
        return backfilled

    for key, meta in candidate_summary.items():
        name = _normalize_operation_name(meta["name"])
        doc_hits = len(meta["sources"])
        card_hits = len(meta.get("card_sources") or [])
        representative_seq = _representative_operation_sequence(name, meta)
        normalized_seq = _preferred_route_sequence(name, representative_seq)
        route_key = _operation_key(name, normalized_seq)
        if route_key in existing_keys:
            continue
        if doc_hits < max(2, total_docs // 3) and card_hits == 0 and not _is_general_main_operation(name):
            continue

        op_type = "MAIN" if doc_hits >= max(2, total_docs // 2) or _is_general_main_operation(name) else "BRANCH"
        card_suffix = "；因独立工序卡明确存在而保留" if card_hits > 0 and doc_hits < max(2, total_docs // 3) else ""
        backfilled.append({
            "name": name,
            "seq": normalized_seq,
            "chain": _infer_operation_chain(name, ""),
            "type": op_type,
            "desc": f"由候选工序统计自动补回，出现于 {doc_hits}/{total_docs} 份工艺规程{card_suffix}",
            "source": "；".join(sorted(meta["sources"])),
            "confidence": "WEAK",
            "factors": [],
        })
    return backfilled


def describe_route_set_candidate(name: str, doc_hits: int, total_docs: int, card_hits: int, op_type: str) -> str:
    if op_type == "MAIN":
        if doc_hits >= total_docs:
            return f"在 {doc_hits}/{total_docs} 份工艺规程中稳定出现的主工序，作为工艺路线全集中的稳定节点保留。"
        return f"在 {doc_hits}/{total_docs} 份工艺规程中高频出现的主工序，作为工艺路线全集中的主体节点保留。"
    if card_hits > 0:
        return f"在 {doc_hits}/{total_docs} 份工艺规程中出现，且存在独立工序卡证据，作为分支/低频主工序保留。"
    return f"在 {doc_hits}/{total_docs} 份工艺规程中出现的分支工序，作为工艺路线全集中的候选节点保留。"


def _sorted_occurrences(items: list[dict]) -> list[dict]:
    return sorted(
        items,
        key=lambda item: (
            int(item.get("sequence") or 0) <= 0,
            int(item.get("sequence") or 0),
            int(item.get("index") or 0),
        ),
    )


def _consecutive_occurrence_runs(items: list[dict]) -> list[list[dict]]:
    ordered_items = _sorted_occurrences(items)
    if not ordered_items:
        return []

    runs: list[list[dict]] = []
    current_run: list[dict] = [ordered_items[0]]
    for current in ordered_items[1:]:
        previous = current_run[-1]
        previous_index = int(previous.get("index") or 0)
        current_index = int(current.get("index") or 0)
        previous_seq = int(previous.get("sequence") or 0)
        current_seq = int(current.get("sequence") or 0)
        is_adjacent = current_index == previous_index + 1
        seq_gap_ok = previous_seq <= 0 or current_seq <= 0 or current_seq - previous_seq <= 10
        if is_adjacent and seq_gap_ok:
            current_run.append(current)
            continue
        runs.append(current_run)
        current_run = [current]
    runs.append(current_run)
    return runs


def _max_consecutive_occurrence_run(items: list[dict]) -> int:
    return max((len(run) for run in _consecutive_occurrence_runs(items)), default=0)


def _has_repeated_main_occurrences(name: str, meta: dict) -> bool:
    if _is_repeatable_operation_name(name):
        return False
    normalized = _normalize_operation_name(name)
    if normalized not in {"车零件", "车外形", "车外圆", "车端面", "平端面"}:
        return False

    grouped_by_source: defaultdict[str, list[dict]] = defaultdict(list)
    for occ in (meta.get("occurrences") or []):
        source = str(occ.get("source") or "").strip()
        if source:
            grouped_by_source[source].append(occ)

    return any(_max_consecutive_occurrence_run(items) >= 2 for items in grouped_by_source.values())


def _build_repeated_main_route_set_candidates(name: str, meta: dict, total_docs: int) -> list[dict]:
    occurrences = list(meta.get("occurrences") or [])
    if not occurrences:
        return []

    grouped_by_source: defaultdict[str, list[dict]] = defaultdict(list)
    for occ in occurrences:
        source = str(occ.get("source") or "").strip()
        if source:
            grouped_by_source[source].append(occ)

    if max((_max_consecutive_occurrence_run(items) for items in grouped_by_source.values()), default=0) <= 1:
        return []

    slots: defaultdict[int, dict[str, object]] = defaultdict(
        lambda: {"sources": set(), "card_sources": set(), "sequences": []}
    )
    for source, items in grouped_by_source.items():
        candidate_runs = [run for run in _consecutive_occurrence_runs(items) if len(run) >= 2]
        if candidate_runs:
            selected_run = max(candidate_runs, key=lambda run: (len(run), -int(run[0].get("index") or 0)))
        else:
            ordered_items = _sorted_occurrences(items)
            if not ordered_items:
                continue
            selected_run = [ordered_items[0]]
        for rank, occ in enumerate(selected_run):
            slots[rank]["sources"].add(source)
            if occ.get("from_card"):
                slots[rank]["card_sources"].add(source)
            seq = int(occ.get("sequence") or 0)
            if seq > 0:
                slots[rank]["sequences"].append(seq)

    candidates: list[dict] = []
    last_seq = 0
    for rank in sorted(slots.keys()):
        slot = slots[rank]
        sources = sorted(slot["sources"])
        if not sources:
            continue
        card_hits = len(slot["card_sources"])
        seq_samples = sorted(int(seq) for seq in slot["sequences"] if int(seq) > 0)
        representative_seq = seq_samples[len(seq_samples) // 2] if seq_samples else 0
        normalized_seq = _preferred_route_sequence(name, representative_seq)
        if normalized_seq <= last_seq:
            normalized_seq = last_seq + 5
        last_seq = normalized_seq

        doc_hits = len(sources)
        op_type = "MAIN" if doc_hits >= max(2, total_docs // 2) or _is_general_main_operation(name) else "BRANCH"
        confidence = "STRONG" if card_hits > 0 or doc_hits >= 2 else "WEAK"
        candidates.append({
            "name": name,
            "seq": normalized_seq,
            "chain": _infer_operation_chain(name, ""),
            "type": op_type,
            "desc": (
                f"同名主工序第{rank + 1}次槽位，当前在 {doc_hits}/{total_docs} 份工艺规程中出现；"
                "对称零件常见为一端/另一端分别加工，需保留为独立路线节点。"
            ),
            "source": "；".join(sources),
            "confidence": confidence,
            "factors": [],
        })
    return candidates


def _repeatable_phase_bucket(index: int, total: int) -> str:
    if total <= 1:
        return "mid"
    ratio = index / max(total - 1, 1)
    if ratio < 0.34:
        return "early"
    if ratio < 0.67:
        return "mid"
    return "final"


def _repeatable_phase_slot(name: str, phase: str) -> int:
    slots = _repeatable_stage_slots(name)
    mapping = {"early": 0, "mid": min(1, len(slots) - 1), "final": len(slots) - 1}
    return int(slots[mapping.get(phase, len(slots) - 1)])


def _build_repeatable_route_set_candidates(name: str, meta: dict, total_docs: int) -> list[dict]:
    occurrences = list(meta.get("occurrences") or [])
    if not occurrences:
        return []

    phase_groups: dict[str, dict[str, object]] = {
        "early": {"sources": set(), "card_sources": set()},
        "mid": {"sources": set(), "card_sources": set()},
        "final": {"sources": set(), "card_sources": set()},
    }

    for occ in occurrences:
        source = str(occ.get("source") or "").strip()
        if not source:
            continue
        phase = _repeatable_phase_bucket(int(occ.get("index") or 0), int(occ.get("total") or 1))
        phase_groups[phase]["sources"].add(source)
        if occ.get("from_card"):
            phase_groups[phase]["card_sources"].add(source)

    candidates: list[dict] = []
    phase_labels = {"early": "前段", "mid": "中段", "final": "终段"}
    for phase in ("early", "mid", "final"):
        sources = sorted(phase_groups[phase]["sources"])
        if not sources:
            continue
        if len(sources) < 2 and phase != "final" and name != "包装":
            continue
        card_hits = len(phase_groups[phase]["card_sources"])
        op_type = "MAIN" if len(sources) >= max(2, total_docs // 2) else "BRANCH"
        confidence = "STRONG" if card_hits > 0 or len(sources) >= 2 else "WEAK"
        candidates.append({
            "name": name,
            "seq": _repeatable_phase_slot(name, phase),
            "chain": _infer_operation_chain(name, ""),
            "type": op_type,
            "desc": f"重复工序的{phase_labels[phase]}槽位，当前在 {len(sources)}/{total_docs} 份工艺规程中出现。",
            "source": "；".join(sources),
            "confidence": confidence,
            "factors": [],
        })
    return candidates


def _refine_operation_rule(op_name: str, op_type: str, factors: list[dict]) -> tuple[str, list[dict], str]:
    del op_name
    return op_type, factors, "STRONG" if any(item["strength"] == "STRONG" for item in factors) else "WEAK"


def dedupe_and_refine_ops(ops_data: list[dict]) -> list[dict]:
    name_seq_buckets: defaultdict[str, set[int]] = defaultdict(set)
    for item in ops_data:
        name = _normalize_operation_name(item.get("name", ""))
        if not name:
            continue
        seq = int(item.get("seq", item.get("sequence", 0)) or 0)
        if seq > 0:
            name_seq_buckets[name].add(seq)

    grouped: dict[tuple[str, int], dict] = {}

    for item in ops_data:
        name = _normalize_operation_name(item.get("name", ""))
        if not name:
            continue
        if _looks_like_equipment_name(name):
            continue
        seq = item.get("seq", item.get("sequence", 0))

        refined_type, refined_factors, refined_confidence = _refine_operation_rule(
            name,
            item.get("type", "MAIN"),
            item.get("factors", []),
        )

        candidate = {
            "name": name,
            "seq": seq,
            "chain": item.get("chain") or _infer_operation_chain(name, item.get("desc", item.get("description", ""))),
            "type": refined_type,
            "desc": item.get("desc", item.get("description", "")),
            "source": item.get("source", "AI分析"),
            "confidence": refined_confidence,
            "factors": refined_factors,
            "harness_warnings": list(item.get("harness_warnings") or []),
        }

        preserve_sequence = _preserve_sequence_slot(name, seq) or len(name_seq_buckets[name]) > 1
        key = (name, int(seq or 0)) if preserve_sequence else (name, 0)
        existing = grouped.get(key)
        if not existing:
            grouped[key] = candidate
            continue

        existing["seq"] = min(existing["seq"], candidate["seq"])
        existing["source"] = "；".join(sorted(set((existing["source"] + "；" + candidate["source"]).split("；"))))
        existing["type"] = "MAIN" if existing["type"] == "MAIN" or candidate["type"] == "MAIN" else "BRANCH"
        existing["confidence"] = "STRONG" if existing["confidence"] == "STRONG" or candidate["confidence"] == "STRONG" else "WEAK"
        if not existing.get("chain") or existing.get("chain") == "other":
            existing["chain"] = candidate.get("chain", "other")

        merged_factors: dict[str, dict] = {factor["name"]: factor for factor in existing["factors"]}
        for factor in candidate["factors"]:
            merged_factors.setdefault(factor["name"], factor)
        existing["factors"] = list(merged_factors.values())
        merged_warnings: dict[str, dict] = {
            str(warning.get("code") or "") + "::" + str(warning.get("target") or ""): warning
            for warning in existing.get("harness_warnings", [])
            if warning.get("code")
        }
        for warning in candidate.get("harness_warnings", []):
            warning_key = str(warning.get("code") or "") + "::" + str(warning.get("target") or "")
            if warning_key.strip(":"):
                merged_warnings.setdefault(warning_key, warning)
        existing["harness_warnings"] = list(merged_warnings.values())

    refined = sorted(grouped.values(), key=lambda item: (item["seq"], item["name"]))

    names = {str(item.get("name") or "").strip() for item in refined}
    is_assembly_family = any(name in names for name in ("导管配套", "导管镶装", "导管清洗", "气密试验"))
    if not is_assembly_family:
        return refined

    cleaned: list[dict] = []
    seen_cleaning = False
    for item in refined:
        name = str(item.get("name") or "").strip()
        if name == "试验" and "气密试验" in names:
            continue
        if name == "检验" and "总检" in names:
            continue
        if name == "标印":
            continue
        if name == "导管清洗":
            if seen_cleaning:
                continue
            seen_cleaning = True
        cleaned.append(item)
    return cleaned


def build_route_set_ops_from_candidates(
    candidate_summary: dict[str, dict],
    total_docs: int,
    doc_orders: dict[str, list[str]] | None = None,
) -> list[dict]:
    ops_data: list[dict] = []
    for key in sorted(candidate_summary.keys()):
        meta = candidate_summary[key]
        name = _normalize_operation_name(meta["name"])
        if not name or _looks_like_equipment_name(name):
            continue
        if _is_repeatable_operation_name(name):
            ops_data.extend(_build_repeatable_route_set_candidates(name, meta, total_docs))
            continue
        if _has_repeated_main_occurrences(name, meta):
            ops_data.extend(_build_repeated_main_route_set_candidates(name, meta, total_docs))
            continue
        doc_hits = len(meta["sources"])
        card_hits = len(meta.get("card_sources") or [])
        avg_seq = round(sum(meta["sequences"]) / len(meta["sequences"]))
        normalized_seq = _preferred_route_sequence(name, avg_seq)
        op_type = "MAIN" if doc_hits >= max(2, total_docs // 2) or _is_general_main_operation(name) else "BRANCH"
        confidence = "STRONG" if card_hits > 0 or op_type == "MAIN" else "WEAK"
        ops_data.append({
            "name": name,
            "seq": normalized_seq,
            "chain": _infer_operation_chain(name, ""),
            "type": op_type,
            "desc": describe_route_set_candidate(name, doc_hits, total_docs, card_hits, op_type),
            "source": "；".join(sorted(meta["sources"])),
            "confidence": confidence,
            "factors": [],
        })
    return _resequence_route_ops(dedupe_and_refine_ops(ops_data), doc_orders)


__all__ = [
    "build_missing_route_candidates",
    "build_route_set_ops_from_candidates",
    "dedupe_and_refine_ops",
    "describe_route_set_candidate",
]
