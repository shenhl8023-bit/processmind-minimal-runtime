"""Place additional process nodes using their source-document neighbors."""
from __future__ import annotations

from collections import defaultdict
from statistics import median_low

from app.services.process_tree_builder_support import ORDER_SLOTS


def place_additional_process_nodes(tree: list[dict], detail_rows: list) -> list[dict]:
    known_names = {str(slot['label']).split('::', 1)[0] for slot in ORDER_SLOTS}
    base = [node for node in tree if node.get('name') in known_names]
    additional = [node for node in tree if node.get('name') not in known_names]
    if not base or not additional:
        return list(tree)

    row_nodes = {row_id: node['id'] for node in tree for row_id in node.get('detail_row_ids') or []}
    base_indices = {node['id']: index for index, node in enumerate(base)}
    docs = defaultdict(list)
    for row in detail_rows:
        node_id = row_nodes.get(row.id)
        if node_id is not None:
            key = ('doc', row.document_id) if row.document_id else ('pdf', row.pdf_name)
            docs[key].append((int(row.operation_seq or 0), node_id))

    # An undocumented additional node stays before the final release suffix,
    # rather than being appended after cleaning and inspection.
    release_start = len(base)
    while release_start and base[release_start - 1].get('name') in {'清洗', '检验', '包装'}:
        release_start -= 1
    insertions = defaultdict(list)
    for node in additional:
        votes = []
        for operations in docs.values():
            positions = [seq for seq, node_id in operations if node_id == node['id']]
            if not positions:
                continue
            # One vote per document; duplicate extracted rows do not add weight.
            sequence = min(positions)
            later = [(seq, base_indices[node_id]) for seq, node_id in operations
                     if seq > sequence and node_id in base_indices]
            if later:
                next_sequence = min(seq for seq, _ in later)
                votes.append(min(index for seq, index in later if seq == next_sequence))
            else:
                votes.append(release_start)
        index = int(median_low(sorted(votes))) if votes else release_start
        insertions[index].append(node)

    result = []
    for index, node in enumerate(base):
        result.extend(insertions[index])
        result.append(node)
    result.extend(insertions[len(base)])
    return result


def renumber_process_tree(tree: list[dict]) -> list[dict]:
    return [{**node, 'sequence': index * 10} for index, node in enumerate(tree, 1)]
