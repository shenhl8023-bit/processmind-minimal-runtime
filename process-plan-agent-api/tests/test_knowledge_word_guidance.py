"""Behavioral coverage for grounded Word guidance alongside existing samples."""
import json

import pytest

from app.services.knowledge import local_search
from app.services.knowledge.answer import build_evidence_prompt, generate_local_knowledge_answer
from app.schemas.schemas import KnowledgeSearchItemOut


def word_record(record_id, topic, *, family="衬套", material="9Cr18", kind="rule", condition="", conclusion="", status="verified", conflict_ids=None, category="process_guidance", **guidance):
    return {
        "id": record_id, "category": category, "title": f"{family}：{topic}",
        "fields": {"知识类型": kind, "适用对象": family, "条件": condition, "结论或要求": conclusion},
        "source": {"document_id": "WD01", "document_name": "钢件衬套工艺说明.docx", "identity": f"05-JB50-21 / §3.4 / {record_id}", "page_no": None},
        "guidance": {
            "kind": kind, "applicability": f"{material}{family}典型指导", "part_family": family,
            "typical_part": "2219.026F", "materials": [material], "topics": [topic],
            "conditions": condition, "conclusion": conclusion, "exceptions": "以零件图为准",
            "verification_status": status, "original_excerpt": condition + conclusion, **guidance,
        }, "conflict_ids": conflict_ids or [],
    }


@pytest.fixture
def guidance_records(monkeypatch):
    base = tuple(
        record for record in local_search._load_records()
        if record.get("category") not in {"process_guidance", "typical_route"}
    )
    records = [
        word_record("stress", "去应力", condition="粗加工后应力和变形影响后续精加工时", conclusion="按条件安排去应力"),
        word_record("lapping", "研孔", condition="珩孔已满足配套要求", conclusion="可以省略研孔", exceptions="未满足配套要求时不得据此省略"),
        word_record("allowance", "硬阳化内孔余量", material="6061-T6", kind="allowance", condition="硬阳化前半精加工", conclusion="内孔单边过加工0～0.005mm，给向孔内增长的膜层留空间", metrics=[{"name": "内孔余量", "min": 0, "max": 0.005, "unit": "mm", "basis": "单边", "direction": "过加工"}]),
        word_record("flushing", "组件冲洗", family="组件", material="", kind="quality", condition="有深长孔结构", conclusion="按需冲洗"),
        word_record("cold", "低温灵活性试验", family="组件", material="", condition="按设计要求，典型件未要求", conclusion="虚拟工序"),
        word_record("hard-body", "调质硬度", conclusion="22～32 HRC", status="conflict", conflict_ids=["hardness"]),
        word_record("hard-appendix", "调质硬度", conclusion="27～35 HRC", status="conflict", conflict_ids=["hardness"]),
        word_record("unreadable", "特殊夹具", kind="resource", status="pending", conclusion="图片型号不清楚"),
        word_record("drill", "钻孔设备", kind="resource", condition="附件钻孔工序", conclusion="Z512", resources=[{"category": "equipment", "name": "台式钻床", "model": "Z512", "identifier": "", "basis": "附件图片明确标注"}]),
        word_record("formula", "加工余量公式", kind="formula", conclusion="保留公式和变量，仅供解释"),
        word_record("route", "典型路线", kind="route", category="typical_route", completeness="stage_overview", conclusion="阶段概要", operations=[{"id": "cold-step", "sequence": 1, "number": "", "name": "低温灵活性试验", "execution_status": "virtual", "condition": "设计要求时", "source": {"document_id": "WD01", "document_name": "钢件衬套工艺说明.docx", "identity": "附件image2", "page_no": None}}]),
    ]
    monkeypatch.setattr(local_search, "_load_records", lambda: tuple(base) + tuple(records))
    return records


def test_word_rules_precede_historical_route_routing(guidance_records):
    result = local_search.search_local_knowledge("轴套工艺路线中什么时候省略研孔？", top_k=1)
    assert result["intent"] == "process_guidance"
    assert result["items"][0]["id"] == "lapping"
    assert result["items"][0]["guidance"]["conditions"] == "珩孔已满足配套要求"
    assert not result["items"][0].get("route")


def test_stress_rule_matches_topic_not_generic_sleeve(guidance_records):
    result = local_search.search_local_knowledge("轴套何时需要去应力？")
    assert result["status"] == "ok"
    assert [item["id"] for item in result["items"]] == ["stress"]
    source = result["items"][0]["source"]
    assert source["document_id"] == "WD01"
    assert source["page_no"] is None
    assert "§3.4 / stress" in source["identity"]


def test_rule_with_unknown_topic_does_not_fall_back_to_generic_history(guidance_records):
    result = local_search.search_local_knowledge("轴套什么时候需要激光淬火？")
    assert result["intent"] == "process_guidance"
    assert result["items"] == []
    assert "没有" in result["message"]


def test_material_specific_allowance_preserves_stage_basis_and_growth(guidance_records):
    result = local_search.search_local_knowledge("6061-T6硬阳化衬套内孔如何留余量？")
    assert [item["id"] for item in result["items"]] == ["allowance"]
    guidance = result["items"][0]["guidance"]
    assert guidance["conditions"] == "硬阳化前半精加工"
    assert guidance["metrics"][0]["basis"] == "单边"
    assert guidance["metrics"][0]["direction"] == "过加工"
    assert "向孔内增长" in guidance["conclusion"]
    assert local_search.search_local_knowledge("9Cr18硬阳化衬套内孔如何留余量？")["items"] == []


@pytest.mark.parametrize("query,record_id", [("组件什么时候需要冲洗？", "flushing"), ("组件低温灵活性试验是必须的吗？", "cold")])
def test_assembly_rules_keep_structural_and_virtual_conditions(guidance_records, query, record_id):
    result = local_search.search_local_knowledge(query)
    assert [item["id"] for item in result["items"]] == [record_id]
    assert result["items"][0]["guidance"]["conditions"]


def test_hardness_conflict_expands_whole_group_past_top_k(guidance_records):
    result = local_search.search_local_knowledge("钢件衬套调质硬度是多少？", top_k=1)
    assert result["status"] == "insufficient_evidence"
    assert result["answer"] == ""
    assert {item["id"] for item in result["items"]} == {"hard-body", "hard-appendix"}
    assert "资料存在冲突，暂无足够依据确定" in result["message"]
    assert "22～32" in str(result["items"])
    assert "27～35" in str(result["items"])


def test_hardness_numeric_range_does_not_become_a_material_constraint(guidance_records):
    result = local_search.search_local_knowledge("钢件衬套调质硬度22～32 HRC是什么？", top_k=1)
    assert result["status"] == "insufficient_evidence"
    assert {item["id"] for item in result["items"]} == {"hard-body", "hard-appendix"}


def test_pending_resource_is_visible_but_cannot_support_a_conclusion(guidance_records):
    result = local_search.search_local_knowledge("工艺说明附件中的特殊夹具是什么？")
    assert result["status"] == "insufficient_evidence"
    assert result["items"][0]["guidance"]["verification_status"] == "pending"
    assert result["items"][0]["data_warnings"]


def test_explicit_image_resource_preserves_source_without_master_id(guidance_records):
    result = local_search.search_local_knowledge("工艺说明附件钻孔使用什么设备？")
    assert result["items"][0]["id"] == "drill"
    assert result["items"][0]["guidance"]["resources"][0]["model"] == "Z512"
    assert result["items"][0].get("relationships", {}) == {}


def test_typical_route_is_separate_and_not_promoted_to_complete_history(guidance_records):
    result = local_search.search_local_knowledge("9Cr18衬套典型工艺路线是什么？", top_k=1)
    assert result["intent"] == "typical_route"
    assert result["items"][0]["category"] == "typical_route"
    assert result["items"][0]["guidance"]["completeness"] == "stage_overview"
    assert result["items"][0]["guidance"]["operations"][0]["execution_status"] == "virtual"
    assert not result["items"][0].get("route")


def test_explicit_history_and_catalog_and_it_ra_paths_keep_their_original_intent(guidance_records):
    historical = local_search.search_local_knowledge("计量活门衬套1的历史工艺路线是什么？", top_k=1)
    assert historical["intent"] == "history_route"
    assert historical["items"][0]["route"]["operation_count"] == 27
    assert local_search.search_local_knowledge("设备有哪些？")["intent"] == "equipment"
    assert local_search.search_local_knowledge("铰刀适用于哪些加工方法？")["intent"] == "tool"
    assert local_search.search_local_knowledge("内孔目标IT7、Ra1.6有哪些工艺方法？")["intent"] == "capability"


def test_loader_combines_independent_word_file_and_keeps_missing_extra_compatible(tmp_path):
    base_path = tmp_path / "local_records.json"
    base_path.write_text(json.dumps([{"id": "base"}]), encoding="utf-8")
    local_search._load_records.cache_clear()
    assert [item["id"] for item in local_search._load_records(str(base_path))] == ["base"]
    (tmp_path / "word_records.json").write_text(json.dumps([{"id": "word"}]), encoding="utf-8")
    local_search._load_records.cache_clear()
    assert [item["id"] for item in local_search._load_records(str(base_path))] == ["base", "word"]
    local_search._load_records.cache_clear()


def test_schema_and_prompt_keep_guidance_and_exact_word_locator(guidance_records):
    item = local_search.search_local_knowledge("轴套何时需要去应力？")["items"][0]
    serialized = KnowledgeSearchItemOut.model_validate(item).model_dump()
    assert serialized["guidance"]["conditions"]
    prompt = build_evidence_prompt("何时去应力", [serialized])
    assert "工艺说明结构" in prompt
    assert "粗加工后应力和变形" in prompt
    assert "WD01" in prompt
    assert "§3.4 / stress" in prompt


@pytest.mark.asyncio
async def test_answer_defense_does_not_call_model_for_conflict_or_pending(guidance_records, monkeypatch):
    async def forbidden(*args, **kwargs):
        raise AssertionError("unresolved Word evidence must not call LLM")
    monkeypatch.setattr("app.services.knowledge.answer.call_llm", forbidden)
    for record in [guidance_records[5], guidance_records[7]]:
        result = await generate_local_knowledge_answer("工艺说明", [record])
        assert result["status"] == "insufficient_evidence"
        assert result["answer"] == ""


def test_rule_unknown_operation_does_not_match_only_a_generic_feature(guidance_records):
    result = local_search.search_local_knowledge("轴套内孔什么时候需要激光淬火？")
    assert result["items"] == []


def test_word_conflict_api_skips_model_and_exposes_both_sources(tmp_path, guidance_records, monkeypatch):
    import asyncio
    from tests.test_knowledge_local_api import _client
    from app.database import get_db
    from app.main import app

    async def forbidden(*args, **kwargs):
        raise AssertionError("conflict response must bypass the answer service")
    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", forbidden)
    client, engine = _client(tmp_path)
    try:
        response = client.post("/api/knowledge/search", json={"query": "钢件衬套调质硬度是多少？", "top_k": 1})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "insufficient_evidence"
        assert len(payload["items"]) == 2
        assert all(item["guidance"]["verification_status"] == "conflict" for item in payload["items"])
        assert all(item["source"]["document_id"] == "WD01" for item in payload["items"])
        assert payload["answer"] == ""
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_word_evidence_snapshot_keeps_search_locator(tmp_path, guidance_records):
    import asyncio
    from tests.test_knowledge_local_api import _client
    from app.database import get_db
    from app.main import app

    item = local_search.search_local_knowledge("轴套何时需要去应力？")["items"][0]
    client, engine = _client(tmp_path)
    try:
        response = client.post("/api/knowledge/evidence", json={
            "query": "轴套何时需要去应力？", "item_id": item["id"], "content": item["content"],
            **{key: item["source"].get(key) for key in ("document_id", "document_name", "page_no", "identity")},
        })
        assert response.status_code == 200
        saved = response.json()
        for key in ("document_id", "document_name", "page_no", "identity"):
            assert saved[key] == item["source"][key]
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_image_resource_can_be_found_by_its_explicit_model_but_not_used_as_capability(guidance_records):
    result = local_search.search_local_knowledge("工艺说明图片中的Z512是什么设备？")
    assert result["intent"] == "process_guidance"
    assert result["items"][0]["id"] == "drill"
    capacity = local_search.search_local_knowledge("Z512设备能达到什么精度？")
    assert capacity["intent"] == "capability"
    assert capacity["items"] == [] or capacity["status"] == "insufficient_evidence"


def test_combined_query_returns_each_matching_word_topic(guidance_records):
    result = local_search.search_local_knowledge("组件冲洗与低温灵活性试验分别有什么要求？")
    assert {item["id"] for item in result["items"]} >= {"flushing", "cold"}


def test_generic_attachment_resource_query_lists_only_explicit_word_assets(guidance_records):
    result = local_search.search_local_knowledge("工艺说明附件图中的设备资源有哪些？", top_k=20)
    assert result["items"]
    assert all(item["guidance"]["kind"] == "resource" for item in result["items"])
    assert all(item["guidance"]["resources"] for item in result["items"])


def test_real_word_dataset_acceptance_regressions():
    stress = local_search.search_local_knowledge("轴套何时需要去应力？")
    assert stress["intent"] == "process_guidance"
    assert any("去应力" in item["guidance"]["topics"] for item in stress["items"])
    assert all(item["source"]["document_id"].startswith("WD") for item in stress["items"])

    lapping = local_search.search_local_knowledge("轴套工艺路线中什么时候省略研孔？")
    assert lapping["intent"] == "process_guidance"
    assert any("珩" in item["guidance"]["conditions"] or "珩" in item["guidance"]["conclusion"] for item in lapping["items"])

    allowance = local_search.search_local_knowledge("6061-T6硬阳化衬套内孔如何留余量？")
    assert allowance["items"]
    metrics = [metric for item in allowance["items"] for metric in item["guidance"].get("metrics", [])]
    assert any("单边" in metric.get("basis", "") for metric in metrics)
    assert any(metric.get("direction") for metric in metrics)

    assembly = local_search.search_local_knowledge("组件冲洗与低温灵活性试验分别有什么要求？", top_k=20)
    topics = {topic for item in assembly["items"] for topic in item["guidance"]["topics"]}
    assert "冲洗" in topics and "低温灵活性试验" in topics

    hardness = local_search.search_local_knowledge("钢件衬套调质硬度是多少？", top_k=1)
    assert hardness["status"] == "insufficient_evidence"
    assert len(hardness["items"]) == 2
    assert {item["guidance"]["verification_status"] for item in hardness["items"]} == {"conflict"}

    resource = local_search.search_local_knowledge("工艺说明附件中Z512是什么设备？")
    assert any("Z512" in str(item["guidance"].get("resources")) for item in resource["items"])
    assert any("image" in item["source"]["identity"] for item in resource["items"])

    route = local_search.search_local_knowledge("9Cr18衬套典型工艺路线是什么？")
    assert route["intent"] == "typical_route"
    assert all(item["guidance"].get("completeness") != "verified_sequence" for item in route["items"])

    history = local_search.search_local_knowledge("计量活门衬套1的历史工艺路线是什么？", top_k=1)
    assert history["items"][0]["route"]["operation_count"] == 27
    assert local_search.search_local_knowledge("内孔目标IT7、Ra1.6有哪些工艺方法？")["intent"] == "capability"


@pytest.mark.parametrize("source_anchor", ["P058", "P083"])
def test_real_hardness_conflict_api_keeps_both_sources_when_one_anchor_is_named(source_anchor, tmp_path, monkeypatch):
    import asyncio
    from tests.test_knowledge_local_api import _client
    from app.database import get_db
    from app.main import app

    async def forbidden(*args, **kwargs):
        raise AssertionError("an unresolved hardness conflict must bypass the answer service")

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", forbidden)
    client, engine = _client(tmp_path)
    try:
        response = client.post("/api/knowledge/search", json={
            "query": f"钢件衬套调质硬度{source_anchor}是多少？", "top_k": 1
        })
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "insufficient_evidence"
        assert payload["answer"] == ""
        assert {item["source"]["identity"] for item in payload["items"]} == {
            "05-JB50-21:P058",
            "05-JB50-21:image3.png",
        }
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())
