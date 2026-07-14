from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass, field

from app.models.models import DocumentOperationDetail
from app.services.process_knowledge import canonicalize_route_label, normalize_process_name


TURNING_NAMES = {
    "车外形",
    "车外圆",
    "车零件",
    "车外形,钻镗孔",
    "车外形，钻镗孔",
    "车外圆，螺纹",
    "车端面",
    "镗孔",
    "倒角",
    "车端面镗孔",
    "平端面、镗孔",
    "车端面，镗孔",
    "攻螺纹",
    "钻孔、攻螺纹",
    "攻螺纹钻孔",
    "车槽",
}

NO_STEP_PROCESSES = {
    "下料",
    "备料",
    "标印",
    "标记",
    "去毛刺",
    "清洗",
    "检验",
    "包装",
    "磁粉检查",
    "裂纹检查",
    "荧光检查",
    "烧伤检查",
}

REPEATABLE_STAGE_LABELS = {"去毛刺", "清洗", "检验"}

MAIN_CHAIN_ORDER = [
    "下料",
    "备料",
    "正常化",
    "调质",
    "车削加工（A侧）",
    "车削加工（B侧）",
    "铣扁",
    "钻孔::post_turning",
    "钻铰孔",
    "铣槽",
    "挖槽去毛刺",
    "标印",
    "去毛刺",
    "清洗",
    "检验",
]

TAIL_CHAIN_ORDER = [
    "去应力",
    "磨孔",
    "珩孔",
    "磨外圆",
    "磨端面",
    "磨槽",
    "去毛刺",
    "清洗",
    "检验",
    "淬火",
    "真空淬火",
    "镀铜",
    "铬酸阳极化",
    "渗氮",
    "除铜",
    "硬质阳极化",
    "磁粉检查",
    "裂纹检查",
    "荧光检查",
    "烧伤检查",
    "打孔",
    "割型孔",
    "割扁、割型孔",
    "打型孔",
    "去毛刺",
    "研顶尖孔",
    "研孔",
    "研外圆",
    "清洗",
    "检验",
    "包装",
]

HOLE_TURNING_STEP_TOKENS = (
    "钻镗孔",
    "钻、镗孔",
    "钻,堂孔",
    "钻堂孔",
    "镗孔",
    "粗镗孔",
    "精镗孔",
    "钻孔",
    "螺纹底孔",
    "攻螺纹",
)


def normalize_text(text: str) -> str:
    return re.sub(r"\s+", "", text or "")


def unique_join(values: object) -> str:
    ordered: list[str] = []
    for value in values or []:
        text = str(value or "").strip()
        if text and text not in ordered:
            ordered.append(text)
    return "；".join(ordered)


def sequence_sort_value(value: object) -> int:
    try:
        return int(value or 0)
    except Exception:
        return 0


def build_order_slots() -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    seen: defaultdict[str, int] = defaultdict(int)
    for index, label in enumerate(MAIN_CHAIN_ORDER + TAIL_CHAIN_ORDER, start=1):
        seen[label] += 1
        occurrence = seen[label]
        node_key = f"{label}::{occurrence}" if label in REPEATABLE_STAGE_LABELS else label
        items.append({
            "node_key": node_key,
            "label": label,
            "occurrence": occurrence,
            "sequence": index * 10,
        })
    return items


ORDER_SLOTS = build_order_slots()
ORDER_SLOT_BY_KEY = {str(item["node_key"]): item for item in ORDER_SLOTS}


@dataclass
class TreeNodeBucket:
    node_key: str
    label: str
    coverage_docs: set[str] = field(default_factory=set)
    source_nodes: list[str] = field(default_factory=list)
    source_node_seen: set[str] = field(default_factory=set)
    step_items: list[str] = field(default_factory=list)
    step_seen: set[str] = field(default_factory=set)
    attached_step_items: list[str] = field(default_factory=list)
    attached_step_seen: set[str] = field(default_factory=set)
    detail_row_ids: list[int] = field(default_factory=list)
    detail_row_id_seen: set[int] = field(default_factory=set)
    first_sequence: int = 0
    first_index: int = 0

    def add_source_node(self, value: str) -> None:
        text = str(value or "").strip()
        if not text or text in self.source_node_seen:
            return
        self.source_node_seen.add(text)
        self.source_nodes.append(text)

    def add_step_item(self, value: str) -> None:
        text = str(value or "").strip()
        if not text or text in self.step_seen:
            return
        self.step_seen.add(text)
        self.step_items.append(text)

    def add_attached_step_item(self, value: str) -> None:
        text = str(value or "").strip()
        if not text or text in self.attached_step_seen:
            return
        self.attached_step_seen.add(text)
        self.attached_step_items.append(text)

    def add_detail_row_id(self, value: int) -> None:
        row_id = int(value or 0)
        if row_id <= 0 or row_id in self.detail_row_id_seen:
            return
        self.detail_row_id_seen.add(row_id)
        self.detail_row_ids.append(row_id)


@dataclass
class DocumentOperationGroup:
    document_key: str
    operation_seq: int
    operation_name: str
    raw_operation_name: str
    operation_content: str
    page_no: int
    equipment_types: tuple[str, ...]
    row_ids: tuple[int, ...]


def normalize_tree_label(name: str, content: str, turning_seen: int) -> tuple[str, int]:
    normalized_name = normalize_process_name(name or "")
    cleaned_content = normalize_text(content)

    if normalized_name in TURNING_NAMES:
        turning_seen += 1
        return ("车削加工（A侧）" if turning_seen == 1 else "车削加工（B侧）", turning_seen)
    if normalized_name == "钻孔":
        if any(token in cleaned_content for token in ("钻铰孔", "钻较孔", "铰孔")):
            return ("钻铰孔", turning_seen)
        return ("钻孔", turning_seen)
    if normalized_name == "研孔" and "珩孔" in cleaned_content and "研孔" not in cleaned_content:
        return ("珩孔", turning_seen)
    if normalized_name in {"研顶尖", "研顶尖孔"}:
        return ("研顶尖孔", turning_seen)
    return (normalized_name, turning_seen)


def extract_turning_steps(content: str) -> list[str]:
    cleaned = normalize_text(content)
    cleaned_without_drill_bore = re.sub(r"钻[、,，]?[镗堂]孔", "", cleaned).replace("钻镗孔", "")
    steps: list[str] = []
    if "平端面" in cleaned:
        steps.append("平端面")
    if "车端面" in cleaned:
        steps.append("车端面")
    if any(token in cleaned for token in ("车外圆", "粗车外圆", "精车外圆")):
        steps.append("车外圆")
    if any(token in cleaned for token in ("车槽", "精车槽")):
        steps.append("车槽")
    if "切槽" in cleaned:
        steps.append("切槽")
    if "挖槽" in cleaned:
        steps.append("挖槽")
    if any(token in cleaned for token in ("钻镗孔", "钻、镗孔", "钻,堂孔", "钻堂孔")):
        steps.append("钻镗孔")
    if "钻孔" in cleaned_without_drill_bore:
        steps.append("钻孔")
    if any(token in cleaned for token in ("镗孔", "粗镗孔", "精镗孔")) and "钻镗孔" not in cleaned:
        steps.append("镗孔")
    if "螺纹底孔" in cleaned or re.search(r"底孔[：:]*[⌀Φφ]", cleaned):
        steps.append("螺纹底孔加工")
    if "攻螺纹" in cleaned:
        steps.append("攻螺纹")
    if "车螺纹" in cleaned:
        steps.append("车螺纹")
    if "车球面" in cleaned:
        steps.append("车球面")
    if "车锥面" in cleaned:
        steps.append("车锥面")
    if any(token in cleaned for token in ("倒角", "车倒角", "孔口倒角")):
        steps.append("倒角")
    if any(token in cleaned for token in ("锐边磨圆", "棱边磨圆", "锐边倒圆", "棱边倒圆", "倒圆")):
        steps.append("锐边磨圆")
    if any(token in cleaned for token in ("车顶尖孔", "车顶尖")):
        steps.append("车顶尖孔")
    if any(token in cleaned for token in ("切断", "车断")):
        steps.append("切断")
    return steps


def extract_step_payload(label: str, original_name: str, content: str) -> tuple[list[str], list[str]]:
    cleaned = normalize_text(content)
    if label.startswith("车削加工"):
        return (extract_turning_steps(content), [])
    if label == "钻孔":
        if "钻铣孔" in cleaned:
            return (["钻铣孔（待核验）"], [])
        return (["钻孔"], [])
    if label == "铣扁":
        attached: list[str] = []
        if "钻孔" in cleaned:
            attached.append("钻孔")
        if "刻线" in cleaned:
            attached.append("刻线")
        return (["铣扁"], attached)
    if label == "钻铰孔":
        steps: list[str] = []
        if any(token in cleaned for token in ("钻铰孔", "钻较孔")) or original_name == "钻铰孔":
            steps.append("钻铰孔")
        if "钻预孔" in cleaned:
            steps.append("钻预孔")
        if "铰孔" in cleaned and "钻铰孔" not in cleaned:
            steps.append("铰孔")
        return (steps, [])
    if label == "铣槽":
        return (["铣槽"], [])
    if label == "挖槽去毛刺":
        return (["挖槽"], [])
    if label in {
        "正常化",
        "调质",
        "去应力",
        "磨孔",
        "珩孔",
        "磨外圆",
        "磨端面",
        "磨槽",
        "淬火",
        "真空淬火",
        "镀铜",
        "铬酸阳极化",
        "渗氮",
        "除铜",
        "硬质阳极化",
        "打孔",
        "割型孔",
        "打型孔",
        "研顶尖孔",
        "研孔",
        "研外圆",
    }:
        return ([label], [])
    if label == "割扁、割型孔":
        return (["割扁", "割型孔"], [])
    if label in NO_STEP_PROCESSES:
        return ([], [])
    return ([label], [])


def slot_description(node_key: str, label: str, source_nodes: list[str]) -> str:
    parts: list[str] = []
    if label in REPEATABLE_STAGE_LABELS:
        occurrence = int(str(node_key).rsplit("::", 1)[-1] or "1")
        if occurrence == 1:
            parts.append("前段槽位")
        elif occurrence == 2:
            parts.append("中段槽位")
        else:
            parts.append("终段槽位")
    if source_nodes:
        display_sources = [canonicalize_route_label(item) for item in source_nodes if str(item or "").strip()]
        parts.append(f"原始工序来源：{'、'.join(display_sources)}")
    return "；".join(parts)


def doc_key(row: DocumentOperationDetail) -> str:
    doc_id = int(row.document_id or 0)
    if doc_id > 0:
        return f"doc:{doc_id}"
    return f"pdf:{row.pdf_name or ''}"


def group_detail_rows_by_document(detail_rows: list[DocumentOperationDetail]) -> dict[str, list[DocumentOperationDetail]]:
    grouped: dict[str, list[DocumentOperationDetail]] = defaultdict(list)
    for row in detail_rows:
        grouped[doc_key(row)].append(row)
    for rows in grouped.values():
        rows.sort(
            key=lambda item: (
                sequence_sort_value(item.operation_seq),
                sequence_sort_value(item.page_no),
                sequence_sort_value(item.id),
            )
        )
    return grouped


def group_document_operations(detail_rows: list[DocumentOperationDetail]) -> list[DocumentOperationGroup]:
    grouped: dict[tuple[int, str], dict[str, object]] = {}
    ordered_keys: list[tuple[int, str]] = []
    document_key = doc_key(detail_rows[0]) if detail_rows else ""
    for row in detail_rows:
        raw_name = str(row.operation_name or "").strip()
        normalized_name = str(row.normalized_name or "").strip() or raw_name
        key = (sequence_sort_value(row.operation_seq), normalized_name)
        bucket = grouped.get(key)
        if not bucket:
            bucket = {
                "contents": [],
                "content_seen": set(),
                "page_no": sequence_sort_value(getattr(row, "page_no", 0)),
                "equipment_types": set(),
                "raw_names": [],
                "raw_name_seen": set(),
                "row_ids": [],
            }
            grouped[key] = bucket
            ordered_keys.append(key)

        if raw_name and raw_name not in bucket["raw_name_seen"]:
            bucket["raw_name_seen"].add(raw_name)
            bucket["raw_names"].append(raw_name)

        text = str(getattr(row, "operation_content", "") or "").strip()
        if text and text not in bucket["content_seen"]:
            bucket["content_seen"].add(text)
            bucket["contents"].append(text)

        equipment_text = str(getattr(row, "equipment_types", "") or "").strip()
        if equipment_text:
            bucket["equipment_types"].add(equipment_text)

        row_id = sequence_sort_value(getattr(row, "id", 0))
        if row_id > 0:
            bucket["row_ids"].append(row_id)

    groups: list[DocumentOperationGroup] = []
    for seq, name in ordered_keys:
        bucket = grouped[(seq, name)]
        groups.append(
            DocumentOperationGroup(
                document_key=document_key,
                operation_seq=seq,
                operation_name=name,
                raw_operation_name=unique_join(bucket["raw_names"]) or name,
                operation_content="；".join(bucket["contents"]),
                page_no=int(bucket["page_no"] or 0),
                equipment_types=tuple(sorted(str(item) for item in bucket["equipment_types"] if str(item).strip())),
                row_ids=tuple(sorted(int(item) for item in bucket["row_ids"] if int(item) > 0)),
            )
        )
    return groups


def equipment_is_turning_like(equipment_types: tuple[str, ...]) -> bool:
    return any("车" in item for item in equipment_types)


def is_plain_drilling_content(content: str) -> bool:
    cleaned = normalize_text(content)
    if not cleaned:
        return False
    if "钻铣孔" in cleaned:
        return False
    if any(token in cleaned for token in ("钻铰孔", "钻较孔", "铰孔")):
        return False
    return "钻孔" in cleaned


def find_next_turning_group(groups: list[DocumentOperationGroup], start_index: int) -> DocumentOperationGroup | None:
    for item in groups[start_index + 1:]:
        if normalize_process_name(item.operation_name) in TURNING_NAMES:
            return item
    return None


def should_merge_front_drilling_into_first_turning(
    current_group: DocumentOperationGroup,
    next_turning_group: DocumentOperationGroup | None,
    turning_seen: int,
) -> bool:
    if turning_seen != 0:
        return False
    if normalize_process_name(current_group.operation_name) != "钻孔":
        return False
    if not is_plain_drilling_content(current_group.operation_content):
        return False
    if not next_turning_group:
        return False
    if not equipment_is_turning_like(current_group.equipment_types):
        return False
    if not equipment_is_turning_like(next_turning_group.equipment_types):
        return False
    cleaned_turning_content = normalize_text(next_turning_group.operation_content)
    return any(token in cleaned_turning_content for token in HOLE_TURNING_STEP_TOKENS)


def resolve_node_key(
    *,
    label: str,
    turning_seen_before: int,
    current_group: DocumentOperationGroup,
    next_turning_group: DocumentOperationGroup | None,
) -> tuple[str, str]:
    if label == "钻孔":
        if should_merge_front_drilling_into_first_turning(current_group, next_turning_group, turning_seen_before):
            return ("车削加工（A侧）", "车削加工（A侧）")
        if turning_seen_before > 0:
            return ("钻孔::post_turning", "钻孔")
        return ("钻孔::front", "钻孔")
    return (label, label)


def extra_node_sort_key(bucket: TreeNodeBucket) -> tuple[int, int, str]:
    return (
        bucket.first_sequence if bucket.first_sequence > 0 else 9999,
        bucket.first_index if bucket.first_index > 0 else 9999,
        bucket.label,
    )


__all__ = [
    "DocumentOperationGroup",
    "ORDER_SLOT_BY_KEY",
    "ORDER_SLOTS",
    "REPEATABLE_STAGE_LABELS",
    "TreeNodeBucket",
    "extract_step_payload",
    "extra_node_sort_key",
    "find_next_turning_group",
    "group_detail_rows_by_document",
    "group_document_operations",
    "normalize_process_name",
    "normalize_tree_label",
    "resolve_node_key",
    "slot_description",
]
