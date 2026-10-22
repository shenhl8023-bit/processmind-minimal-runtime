import asyncio

from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import Project
from app.services.db_schema_maintenance import ensure_project_schema


def _client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-local.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            session.add(Project(id=1, name="测试项目", status="CREATED"))
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    return TestClient(app), engine


def test_route_api_keeps_all_ordered_operations_and_sends_complete_evidence_to_model(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    prompts = []

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        prompts.append(user_prompt)
        return "计量活门衬套1的样例路线共27道工序，从下料到包装。[1]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    try:
        response = client.post("/api/knowledge/search", json={"query": "计量活门衬套1的工艺路线是什么？", "top_k": 1})
        assert response.status_code == 200
        payload = response.json()
        assert payload["status"] == "ok"
        assert len(payload["items"]) == 1
        route = payload["items"][0]["route"]
        assert route["operation_count"] == 27
        assert [op["number"] for op in route["operations"][:4]] == ["0", "5", "10", "15"]
        assert route["operations"][-1]["number"] == "130"
        assert route["operations"][1]["source"]["identity"] == "J/RT145-13-02:工序5"
        assert "0 下料 → 5 调质 → 10 车外形 → 15 车外形" in prompts[0]
        assert "125 检验 → 130 包装" in prompts[0]
        assert "参考来源：" in payload["answer"]
        assert "JRT145-13-02.json" in payload["answer"]
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_search_returns_grounded_llm_answer_and_local_source(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)

    async def fake_answer(query, items, resource_summary=None):
        assert query == "9Cr18 衬套工艺"
        assert items[0]["source"]["document_name"]
        return {"status": "ok", "message": "", "answer": "根据样例安排粗车外圆。[1]"}

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", fake_answer)
    response = client.post("/api/knowledge/search", json={"query": "9Cr18 衬套工艺", "top_k": 3})

    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["answer"].endswith("[1]")
    assert response.json()["items"]
    assert response.json()["items"][0]["source"]["document_name"]

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_search_reports_no_evidence_without_calling_llm(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    called = False

    async def fake_answer(*_args, **_kwargs):
        nonlocal called
        called = True
        raise AssertionError("no-evidence query must not call the LLM")

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", fake_answer)
    response = client.post("/api/knowledge/search", json={"query": "完全不存在的材料XQ-999"})

    assert response.status_code == 200
    assert response.json()["status"] == "no_evidence"
    assert response.json()["answer"] == ""
    assert response.json()["items"] == []
    assert called is False

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_capability_query_without_requested_relationship_skips_llm(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    called = False

    async def fake_answer(*_args, **_kwargs):
        nonlocal called
        called = True
        return {"status": "ok", "message": "", "answer": "猜测的量具推荐"}

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", fake_answer)
    response = client.post("/api/knowledge/search", json={"query": "精铰孔适用哪些量具？", "top_k": 20})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "insufficient_evidence"
    assert payload["intent"] == "capability"
    assert payload["relationship_gaps"] == ["gauge"]
    assert payload["answer"] == ""
    assert any(item["capability"]["method"] == "精铰" for item in payload["items"])
    assert all(item["relationships"]["gauge"]["status"] == "not_provided" for item in payload["items"])
    assert called is False

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_history_resource_response_includes_cross_operation_summary(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)

    async def fake_answer(*_args, **_kwargs):
        return {"status": "ok", "message": "", "answer": "历史记录中的设备和量具见下方汇总。"}

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", fake_answer)
    response = client.post(
        "/api/knowledge/search",
        json={"query": "某历史轴套类工序使用了哪些设备和量具？", "top_k": 5},
    )

    assert response.status_code == 200
    payload = response.json()
    assert payload["resource_summary"]["record_count"] >= 5
    assert payload["resource_summary"]["equipment_count"] > 5
    assert payload["resource_summary"]["equipment"]

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_equipment_answer_uses_full_catalog_context_beyond_top_k(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    captured = {}

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        captured["prompt"] = user_prompt
        return "设备很多，当前证据为示例，完整清单见页面。[1]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    response = client.post("/api/knowledge/search", json={"query": "设备有哪些？", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert len(payload["items"]) == 3
    assert "原始记录数：370" in captured["prompt"]
    assert "当前提供 3 条编号证据，仅为相关记录示例" in captured["prompt"]
    assert "设备：" in captured["prompt"]
    assert "[4]" not in payload["answer"]
    assert payload["resource_summary"]["record_count"] == 370

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_search_rejects_invalid_model_citation_and_keeps_local_records(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)
    calls = 0

    async def fake_call_llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return "全部设备只有这几种。[99]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    response = client.post("/api/knowledge/search", json={"query": "设备有哪些？", "top_k": 3})

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "insufficient_evidence"
    assert payload["answer"] == ""
    assert "不存在的来源编号" in payload["message"]
    assert len(payload["items"]) == 3
    assert all(item["source"]["document_name"] for item in payload["items"])
    assert payload["resource_summary"]["record_count"] == 370
    assert calls == 1

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def test_capability_id_missing_relationship_does_not_call_model(tmp_path, monkeypatch):
    client, engine = _client(tmp_path)

    async def reject_model(*_args, **_kwargs):
        raise AssertionError("missing capability relationship must not call model")

    monkeypatch.setattr("app.routers.knowledge.generate_local_knowledge_answer", reject_model)
    response = client.post("/api/knowledge/search", json={"query": "CP-014适用哪些量具？"})
    payload = response.json()
    assert response.status_code == 200
    assert payload["status"] == "insufficient_evidence"
    assert payload["relationship_gaps"] == ["gauge"]
    assert payload["answer"] == ""
    assert payload["items"][0]["id"] == "CP-014"

    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())
