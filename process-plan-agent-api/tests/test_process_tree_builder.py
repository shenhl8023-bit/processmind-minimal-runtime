from types import SimpleNamespace

from app.services.process_tree_builder import build_superset_process_tree
from app.services.process_tree_builder_support import ORDER_SLOTS, REPEATABLE_STAGE_LABELS


def _detail(row_id: int, sequence: int, name: str) -> SimpleNamespace:
    return SimpleNamespace(
        id=row_id,
        project_id=1,
        document_id=1,
        pdf_name="sample.pdf",
        operation_seq=sequence,
        operation_name=name,
        normalized_name=name,
        operation_content=name,
        page_no=sequence,
        equipment_types="",
    )


def test_superset_tree_has_unique_sequences_and_packaging_after_unmapped_tail_nodes():
    labels: list[str] = []
    occurrences: dict[str, int] = {}
    for slot in ORDER_SLOTS:
        label = str(slot["label"])
        occurrences[label] = occurrences.get(label, 0) + 1
        if label == "下料":
            continue
        if label in REPEATABLE_STAGE_LABELS:
            labels.append(label)
        elif occurrences[label] == 1:
            labels.append(label)
    labels.append("钻镗孔")

    details = [_detail(index, index * 10, label) for index, label in enumerate(labels, start=1)]
    tree = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)

    sorted_tree = sorted(tree, key=lambda item: (item["sequence"], item["id"]))
    sequences = [item["sequence"] for item in sorted_tree]

    assert len(sequences) == len(set(sequences))
    assert sorted_tree[-1]["name"] == "包装"


def test_model_order_is_applied_and_sequences_are_rebuilt(monkeypatch):
    import asyncio
    from app.services import process_tree_orderer

    tree = [{"id": 10, "name": "包装", "sequence": 10}, {"id": 20, "name": "车外形", "sequence": 20}]

    async def fake_call_llm(*_args, **_kwargs):
        return '{"ordered_ids": [20, 10]}'

    monkeypatch.setattr(process_tree_orderer, "call_llm", fake_call_llm)
    ordered = asyncio.run(process_tree_orderer.order_process_tree(tree, []))
    assert [item["id"] for item in ordered] == [20, 10]
    assert [item["sequence"] for item in ordered] == [10, 20]


def test_invalid_model_order_falls_back_and_keeps_packaging_last(monkeypatch):
    import asyncio
    from app.services import process_tree_orderer

    tree = [{"id": 10, "name": "包装", "sequence": 10}, {"id": 20, "name": "钻镗孔", "sequence": 20}]

    async def fake_call_llm(*_args, **_kwargs):
        return '{"ordered_ids": [20, 20]}'

    monkeypatch.setattr(process_tree_orderer, "call_llm", fake_call_llm)
    ordered = asyncio.run(process_tree_orderer.order_process_tree(tree, []))
    assert [item["id"] for item in ordered] == [20, 10]
    assert [item["sequence"] for item in ordered] == [10, 20]


def test_slow_tree_ordering_falls_back_without_waiting_for_provider(monkeypatch):
    import asyncio
    from app.services import process_tree_orderer

    async def stalled_provider(*_args, **_kwargs):
        await asyncio.Event().wait()

    monkeypatch.setattr(process_tree_orderer, "call_llm", stalled_provider)
    monkeypatch.setattr(process_tree_orderer, "ORDER_TIMEOUT_SECONDS", 0.01, raising=False)
    tree = [{"id": 10, "name": "包装", "sequence": 10}, {"id": 20, "name": "钻镗孔", "sequence": 20}]

    async def run():
        return await asyncio.wait_for(process_tree_orderer.order_process_tree(tree, []), timeout=0.5)

    ordered = asyncio.run(run())
    assert [item["id"] for item in ordered] == [20, 10]
    assert [item["sequence"] for item in ordered] == [10, 20]


def test_unmapped_machining_nodes_follow_document_neighbors_before_release():
    names = ["下料", "车外形", "钻镗孔", "平端面", "铣扁", "割扁", "去毛刺", "清洗", "检验", "包装"]
    details = [_detail(i, i * 5, name) for i, name in enumerate(names, 1)]
    tree = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)
    labels = [item["name"] for item in tree]
    assert labels == ["下料", "车削加工（A侧）", "钻镗孔", "平端面", "铣扁", "割扁", "去毛刺", "清洗", "检验", "包装"]
    # Existing synthetic IDs must survive reordering or saved reviews lose identity.
    assert next(item["id"] for item in tree if item["name"] == "平端面") == 900008


def test_final_release_chain_does_not_move_intermediate_cleaning():
    names = ["下料", "清洗", "检验", "钻镗孔", "平端面", "清洗", "检验", "包装"]
    details = [_detail(i, i * 5, name) for i, name in enumerate(names, 1)]
    tree = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)
    assert [item["name"] for item in tree] == names


def test_model_cannot_move_unmapped_machining_after_final_inspection(monkeypatch):
    import asyncio
    import json
    from app.services import process_tree_orderer

    names = ["下料", "车外形", "钻镗孔", "平端面", "铣扁", "清洗", "检验", "包装"]
    details = [_detail(i, i * 5, name) for i, name in enumerate(names, 1)]
    tree = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)

    async def wrong_but_complete_order(*_args, **_kwargs):
        by_name = {item["name"]: item["id"] for item in tree}
        order = ["下料", "车削加工（A侧）", "铣扁", "清洗", "检验", "钻镗孔", "平端面", "包装"]
        return json.dumps({"ordered_ids": [by_name[name] for name in order]})

    monkeypatch.setattr(process_tree_orderer, "call_llm", wrong_but_complete_order)
    result = asyncio.run(process_tree_orderer.order_process_tree(tree, details))
    assert [item["name"] for item in result] == ["下料", "车削加工（A侧）", "钻镗孔", "平端面", "铣扁", "清洗", "检验", "包装"]


def test_model_cannot_reverse_final_cleaning_and_inspection(monkeypatch):
    import asyncio
    import json
    from app.services import process_tree_orderer

    names = ["下料", "车外形", "清洗", "检验", "包装"]
    details = [_detail(i, i * 5, name) for i, name in enumerate(names, 1)]
    tree = build_superset_process_tree(operations=[], detail_rows=details, sample_count=1)

    async def reversed_release(*_args, **_kwargs):
        ids = [item['id'] for item in tree]
        ids[-3], ids[-2] = ids[-2], ids[-3]
        return json.dumps({'ordered_ids': ids})

    monkeypatch.setattr(process_tree_orderer, 'call_llm', reversed_release)
    result = asyncio.run(process_tree_orderer.order_process_tree(tree, details))
    assert [item['id'] for item in result] == [item['id'] for item in tree]
