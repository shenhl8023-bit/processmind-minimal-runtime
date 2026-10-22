from __future__ import annotations

import asyncio
import json
import logging
from collections import defaultdict

from app.models.models import DocumentOperationDetail
from app.services.llm_service import call_llm, parse_json_from_llm
from app.services.process_tree_ordering import place_additional_process_nodes, renumber_process_tree

logger = logging.getLogger(__name__)
ORDER_TIMEOUT_SECONDS = 25

SYSTEM_PROMPT = """你是机械加工工艺路线排序器。根据样本文档中真实出现的工序先后，为给定候选节点排序。
只能重排候选节点，不能增删、合并、拆分或改名。重复名称可能代表不同阶段，必须按节点 ID 区分。
优先保持样本文档明确支持的先后关系；不同样本顺序冲突时，综合多数样本，兼顾稳定主链。
包装、标印等收尾放行节点通常靠后；只有样本文档明确存在更晚工序时，才允许它们不在最后。
必须保留输入给出的 terminal_release_ids 顺序并放在末尾，中间阶段的清洗、检验仍保留原阶段。
不在预设表中的加工节点应根据来源文档的相邻工序定位，不能因为低覆盖率而追加到收尾链之后。
只输出 JSON 对象，格式为 {\"ordered_ids\": [候选节点 ID...]}，必须完整且每个 ID 仅出现一次。"""


def _build_evidence(
    tree: list[dict[str, object]], detail_rows: list[DocumentOperationDetail]
) -> tuple[list[dict[str, object]], bool]:
    row_to_node: dict[int, int] = {}
    packaging_ids: set[int] = set()
    for node in tree:
        node_id = int(node.get("id") or 0)
        if str(node.get("name") or "").strip() == "包装":
            packaging_ids.add(node_id)
        for row_id in node.get("detail_row_ids", []) or []:
            row_to_node[int(row_id)] = node_id

    documents: defaultdict[str, list[dict[str, object]]] = defaultdict(list)
    packaging_has_later_operation = False
    for row in detail_rows:
        row_id = int(getattr(row, "id", 0) or 0)
        node_id = row_to_node.get(row_id)
        if not node_id:
            continue
        sequence = int(getattr(row, "operation_seq", 0) or 0)
        name = str(getattr(row, "operation_name", "") or "").strip()
        document = str(getattr(row, "pdf_name", "") or getattr(row, "document_id", "") or "")
        documents[document].append({"sequence": sequence, "name": name, "node_id": node_id})

    for items in documents.values():
        items.sort(key=lambda item: (int(item["sequence"]), int(item["node_id"])))
        package_sequences = [int(item["sequence"]) for item in items if int(item["node_id"]) in packaging_ids]
        if package_sequences and any(int(item["sequence"]) > max(package_sequences) for item in items):
            packaging_has_later_operation = True

    evidence = [
        {"document": name, "operations": items}
        for name, items in sorted(documents.items())
    ]
    return evidence, packaging_has_later_operation


def _local_order(tree: list[dict[str, object]], packaging_last: bool) -> list[dict[str, object]]:
    ordered = sorted(tree, key=lambda item: (int(item.get("sequence") or 0), int(item.get("id") or 0)))
    if packaging_last:
        packaging = [item for item in ordered if str(item.get("name") or "").strip() == "包装"]
        ordered = [item for item in ordered if str(item.get("name") or "").strip() != "包装"] + packaging
    return ordered


async def order_process_tree(
    tree: list[dict[str, object]], detail_rows: list[DocumentOperationDetail]
) -> list[dict[str, object]]:
    if not tree:
        return []
    evidence, packaging_has_later_operation = _build_evidence(tree, detail_rows)
    packaging_last = not packaging_has_later_operation
    fallback = place_additional_process_nodes(_local_order(tree, packaging_last), detail_rows)
    release_suffix = []
    if packaging_last and fallback[-1].get('name') == '包装':
        for node in reversed(fallback):
            if node.get('name') not in {'清洗', '检验', '包装'}:
                break
            release_suffix.insert(0, node['id'])
    node_ids = [int(item.get("id") or 0) for item in tree]
    if len(node_ids) != len(set(node_ids)) or 0 in node_ids:
        logger.warning("Process-tree ordering skipped: candidate IDs are not unique positive integers")
        return _renumber(fallback)

    prompt = json.dumps(
        {
            "candidate_nodes": [
                {"id": int(item["id"]), "name": item.get("name"), "description": item.get("description")}
                for item in tree
            ],
            "sample_order_evidence": evidence,
            "packaging_must_be_last": packaging_last,
            "terminal_release_ids": release_suffix,
        },
        ensure_ascii=False,
    )
    try:
        response = await asyncio.wait_for(
            call_llm(
                SYSTEM_PROMPT, prompt, temperature=0.0,
                timeout_seconds=ORDER_TIMEOUT_SECONDS, max_retries=0,
            ),
            timeout=ORDER_TIMEOUT_SECONDS,
        )
        parsed = parse_json_from_llm(response or "")
        ordered_ids = parsed.get("ordered_ids") if isinstance(parsed, dict) else None
        if not isinstance(ordered_ids, list) or any(type(item) is not int for item in ordered_ids):
            raise ValueError("model response must contain integer ordered_ids")
        if len(ordered_ids) != len(node_ids) or set(ordered_ids) != set(node_ids):
            raise ValueError("model response must be a complete permutation of candidate IDs")
        by_id = {int(item["id"]): item for item in tree}
        ordered = [by_id[node_id] for node_id in ordered_ids]
        if packaging_last and ordered[-1].get("name") != "包装":
            raise ValueError("packaging must be the final node when no later operation is documented")
        if release_suffix and ordered_ids[-len(release_suffix):] != release_suffix:
            raise ValueError("final cleaning, inspection and packaging must retain their release order")
        corrected = place_additional_process_nodes(ordered, detail_rows)
        if [node['id'] for node in corrected] != ordered_ids:
            raise ValueError("additional process nodes violate source-document neighbor order")
        return _renumber(ordered)
    except Exception:
        logger.exception("LLM process-tree ordering failed; using local order")
        return _renumber(fallback)


def _renumber(tree: list[dict[str, object]]) -> list[dict[str, object]]:
    return renumber_process_tree(tree)
