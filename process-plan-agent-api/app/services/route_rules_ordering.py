"""
工艺路线顺序推断与重排辅助。
"""

from __future__ import annotations

from collections import Counter, defaultdict

from app.services.route_rules_operation_names import (
    ASSEMBLY_ROUTE_SEQUENCE_HINTS,
    _infer_operation_chain,
    _is_repeatable_operation_name,
    _normalize_operation_name,
)


ASSEMBLY_ROUTE_ORDER = [
    "导管配套",
    "除油",
    "阿洛丁",
    "导管镶装",
    "气密试验",
    "试验",
    "总检",
    "导管清洗",
    "吹干",
    "喷漆",
]


def _heuristic_sequence_hint(name: str, avg_seq: int) -> int:
    normalized = _normalize_operation_name(name)
    text = normalized or ""
    normalized_avg = max(10, int(round(avg_seq / 5.0) * 5))

    if text in ASSEMBLY_ROUTE_SEQUENCE_HINTS:
        return ASSEMBLY_ROUTE_SEQUENCE_HINTS[text]

    if "备料" in text:
        return 5
    if any(token in text for token in ("下料", "锻造", "毛坯", "棒料")):
        return 10
    if "正常化" in text:
        return 20
    if any(token in text for token in ("调质", "退火")):
        return 30
    if "车零件" in text:
        return 40
    if "车外形" in text:
        return 50
    if "车外圆" in text:
        return 60
    if any(token in text for token in ("车端面", "平端面")):
        return 70
    if any(token in text for token in ("钻", "镗", "铰", "攻螺纹", "中心孔")):
        return 80
    if any(token in text for token in ("铣", "槽", "扁", "线切割", "电火花", "割型孔")):
        return 90
    if any(token in text for token in ("倒角", "倒圆")):
        return min(75, max(65, normalized_avg))
    if any(token in text for token in ("去应力", "时效")):
        return 110
    if "镀铜" in text:
        return 115
    if any(token in text for token in ("淬火", "真空淬火", "渗氮", "氰化", "热处理")):
        return 120
    if "除铜" in text:
        return 125
    if any(token in text for token in ("阳极化", "钝化", "表面处理")):
        return 170
    if any(token in text for token in ("磨", "研", "珩")):
        return 130
    if any(token in text for token in ("检验", "检查", "探伤", "磁粉", "烧伤", "荧光")):
        return 140
    if any(token in text for token in ("清洗", "去毛刺", "标印", "包装")):
        return 150
    return normalized_avg


def _preferred_route_sequence(name: str, avg_seq: int) -> int:
    normalized = _normalize_operation_name(name)
    if normalized in ASSEMBLY_ROUTE_SEQUENCE_HINTS:
        return ASSEMBLY_ROUTE_SEQUENCE_HINTS[normalized]
    if int(avg_seq or 0) > 0:
        return max(5, int(round(int(avg_seq) / 5.0) * 5))
    return _heuristic_sequence_hint(name, avg_seq)


def _representative_operation_sequence(name: str, meta: dict) -> int:
    occurrences = list(meta.get("occurrences") or [])
    if not occurrences:
        sequences = [int(seq or 0) for seq in (meta.get("sequences") or []) if int(seq or 0) > 0]
        if sequences:
            sequences.sort()
            return sequences[len(sequences) // 2]
        return 0

    grouped_by_source: defaultdict[str, list[dict]] = defaultdict(list)
    for occ in occurrences:
        source = str(occ.get("source") or "").strip()
        if source:
            grouped_by_source[source].append(occ)

    per_doc_anchors: list[int] = []
    for items in grouped_by_source.values():
        positive_card = sorted(
            int(item.get("sequence") or 0)
            for item in items
            if bool(item.get("from_card")) and int(item.get("sequence") or 0) > 0
        )
        if positive_card:
            per_doc_anchors.append(positive_card[0])
            continue

        positive_any = sorted(
            int(item.get("sequence") or 0)
            for item in items
            if int(item.get("sequence") or 0) > 0
        )
        if positive_any:
            per_doc_anchors.append(positive_any[0])
            continue

        earliest_index = min(int(item.get("index") or 0) for item in items)
        per_doc_anchors.append(max(5, (earliest_index + 1) * 10))

    if not per_doc_anchors:
        return 0

    per_doc_anchors.sort()
    median_anchor = per_doc_anchors[len(per_doc_anchors) // 2]
    return _preferred_route_sequence(name, median_anchor)


def _repeatable_stage_slots(name: str) -> list[int]:
    normalized = _normalize_operation_name(name)
    if any(token in normalized for token in ("检验", "检查", "探伤", "磁粉", "烧伤", "荧光")):
        return [46, 86, 96]
    if "清洗" in normalized:
        return [45, 85, 95]
    if "去毛刺" in normalized:
        return [44, 84, 94]
    if "包装" in normalized:
        return [98]
    return [90]


def _successor_frequency_graph(
    unique_names: list[str],
    doc_orders: dict[str, list[str]],
) -> tuple[defaultdict[tuple[str, str], int], Counter[str]]:
    direct_successor_counts: defaultdict[tuple[str, str], int] = defaultdict(int)
    related_doc_hits: Counter[str] = Counter()
    unique_set = set(unique_names)

    for ordered_names in doc_orders.values():
        filtered: list[str] = []
        seen_in_doc: set[str] = set()
        for name in ordered_names:
            if name not in unique_set:
                continue
            if name in seen_in_doc and not _is_repeatable_operation_name(name):
                continue
            filtered.append(name)
            seen_in_doc.add(name)

        for name in set(filtered):
            related_doc_hits[name] += 1

        for left, right in zip(filtered, filtered[1:]):
            if left == right:
                continue
            direct_successor_counts[(left, right)] += 1

    return direct_successor_counts, related_doc_hits


def _finishing_order_rank(name: str) -> int:
    normalized = _normalize_operation_name(name)
    if any(token in normalized for token in ("珩", "磨")) and "研" not in normalized:
        return 10
    if "研" in normalized:
        return 20
    return 0


def _route_order_sort_key(name: str, raw_seq_map: dict[str, int], related_doc_hits: Counter[str]) -> tuple[int, int, int, int, str]:
    return (
        int(_preferred_route_sequence(name, raw_seq_map.get(name, 0)) or 0),
        _finishing_order_rank(name),
        int(_heuristic_sequence_hint(name, raw_seq_map.get(name, 0)) or 0),
        -int(related_doc_hits.get(name, 0) or 0),
        name,
    )


def _resolve_route_order(names: list[str], raw_seq_map: dict[str, int], doc_orders: dict[str, list[str]] | None = None) -> list[str]:
    unique_names = [name for name in names if name]
    if not unique_names:
        return []

    doc_orders = doc_orders or {}
    direct_successor_counts, related_doc_hits = _successor_frequency_graph(unique_names, doc_orders)
    precedence_counts: defaultdict[tuple[str, str], int] = defaultdict(int)

    for ordered_names in doc_orders.values():
        filtered = [name for name in ordered_names if name in unique_names]
        if len(filtered) < 2:
            continue
        for idx, left in enumerate(filtered):
            for right in filtered[idx + 1:]:
                precedence_counts[(left, right)] += 1

    assembly_filtered = [name for name in ASSEMBLY_ROUTE_ORDER if name in unique_names]
    for idx, left in enumerate(assembly_filtered):
        for right in assembly_filtered[idx + 1:]:
            precedence_counts[(left, right)] += 2

    adjacency: dict[str, set[str]] = {name: set() for name in unique_names}
    indegree: dict[str, int] = {name: 0 for name in unique_names}

    for left in unique_names:
        for right in unique_names:
            if left == right:
                continue
            direct_forward = direct_successor_counts.get((left, right), 0)
            direct_backward = direct_successor_counts.get((right, left), 0)
            forward = precedence_counts.get((left, right), 0)
            backward = precedence_counts.get((right, left), 0)
            if direct_forward <= 0 and forward <= 0:
                continue
            if direct_forward > 0:
                if direct_forward <= direct_backward:
                    continue
                if direct_forward < 2 and direct_backward > 0:
                    continue
            elif forward <= backward:
                continue
            elif forward < 2 and backward > 0:
                continue
            if right in adjacency[left]:
                continue
            adjacency[left].add(right)
            indegree[right] += 1

    def sort_key(name: str) -> tuple[int, int, int, int, str]:
        return _route_order_sort_key(name, raw_seq_map, related_doc_hits)

    def successor_priority(current: str, target: str) -> tuple[int, int, int, int, int, int, str]:
        return (
            -int(direct_successor_counts.get((current, target), 0) or 0),
            -int(precedence_counts.get((current, target), 0) or 0),
            *sort_key(target),
        )

    ready = sorted([name for name, degree in indegree.items() if degree == 0], key=sort_key)
    ordered: list[str] = []
    remaining_adjacency = {name: set(targets) for name, targets in adjacency.items()}
    remaining_indegree = dict(indegree)

    while ready:
        current = ready.pop(0)
        ordered.append(current)
        for target in sorted(remaining_adjacency.get(current, set()), key=lambda item: successor_priority(current, item)):
            remaining_indegree[target] -= 1
            if remaining_indegree[target] == 0:
                ready.append(target)
        ready.sort(key=sort_key)

    leftovers = [name for name in unique_names if name not in ordered]
    ordered.extend(sorted(leftovers, key=sort_key))
    return ordered


def _resequence_route_ops(ops_data: list[dict], doc_orders: dict[str, list[str]] | None = None) -> list[dict]:
    if not ops_data:
        return ops_data

    repeatable_groups: defaultdict[str, list[dict]] = defaultdict(list)
    ordered_candidates: list[dict] = []

    for item in ops_data:
        name = _normalize_operation_name(str(item.get("name") or ""))
        if not name:
            continue
        raw_seq = int(item.get("seq", item.get("sequence", 0)) or 0)
        candidate = dict(item)
        candidate["name"] = name
        candidate["_raw_seq"] = raw_seq
        if _is_repeatable_operation_name(name):
            repeatable_groups[name].append(candidate)
            continue
        candidate["_stage_seq"] = _preferred_route_sequence(name, raw_seq)
        ordered_candidates.append(candidate)

    for name, items in repeatable_groups.items():
        slots = _repeatable_stage_slots(name)
        for idx, candidate in enumerate(sorted(items, key=lambda item: (item["_raw_seq"], name))):
            stage_seq = slots[min(idx, len(slots) - 1)] + max(0, idx - len(slots) + 1)
            candidate["_stage_seq"] = stage_seq
            ordered_candidates.append(candidate)

    raw_seq_map = {
        str(item.get("name") or ""): int(item.get("_raw_seq") or 0)
        for item in ordered_candidates
        if item.get("name")
    }
    ordered_names = _resolve_route_order(
        [str(item.get("name") or "") for item in ordered_candidates],
        raw_seq_map,
        doc_orders,
    )
    name_order = {name: idx for idx, name in enumerate(ordered_names)}
    ordered_candidates.sort(
        key=lambda item: (
            int(name_order.get(str(item.get("name") or ""), 9999)),
            int(item.get("_raw_seq") or 0),
            int(item.get("_stage_seq") or 0),
            str(item.get("name") or ""),
        )
    )

    resequenced: list[dict] = []
    for idx, item in enumerate(ordered_candidates, start=1):
        normalized = dict(item)
        normalized["seq"] = idx * 10
        normalized.pop("_stage_seq", None)
        normalized.pop("_raw_seq", None)
        resequenced.append(normalized)
    return resequenced


__all__ = [
    "ASSEMBLY_ROUTE_ORDER",
    "_finishing_order_rank",
    "_heuristic_sequence_hint",
    "_preferred_route_sequence",
    "_repeatable_stage_slots",
    "_representative_operation_sequence",
    "_resequence_route_ops",
    "_resolve_route_order",
    "_route_order_sort_key",
    "_successor_frequency_graph",
]
