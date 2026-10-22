import pytest

from app.services.knowledge.answer import generate_local_knowledge_answer


@pytest.mark.asyncio
async def test_answer_uses_llm_with_local_evidence_and_returns_citations(monkeypatch):
    captured = {}

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        captured["system"] = system_prompt
        captured["user"] = user_prompt
        captured["temperature"] = temperature
        return "建议先粗车外圆，再精车内孔。"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer(
        "9Cr18 衬套应该怎么安排工艺？",
        [
            {
                "id": "history-1",
                "title": "9Cr18 衬套历史工艺",
                "category": "history",
                "content": "工序：粗车外圆；精车内孔",
                "source": {"document_name": "case-01.json", "identity": "工序-20"},
            }
        ],
    )

    assert result["status"] == "ok"
    assert result["answer"].startswith("建议先粗车外圆，再精车内孔。")
    assert "[1] case-01.json / 工序-20" in result["answer"]
    assert "9Cr18 衬套" in captured["user"]
    assert "[1]" in captured["user"]
    assert captured["temperature"] == 0.2


@pytest.mark.asyncio
async def test_answer_does_not_call_llm_without_local_evidence(monkeypatch):
    called = False

    async def fake_call_llm(*_args, **_kwargs):
        nonlocal called
        called = True
        return "不应出现"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer("不存在的材料", [])

    assert called is False
    assert result["status"] == "no_evidence"
    assert result["answer"] == ""
    assert "没有找到" in result["message"]


@pytest.mark.asyncio
async def test_answer_preserves_evidence_when_llm_is_unavailable(monkeypatch):
    async def fake_call_llm(*_args, **_kwargs):
        return ""

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer(
        "如何选择刀具？",
        [{"id": "tool-1", "title": "刀具", "category": "tool", "content": "硬质合金刀片"}],
    )

    assert result["status"] == "llm_unavailable"
    assert result["answer"] == ""
    assert "大模型" in result["message"]


@pytest.mark.asyncio
async def test_equipment_answer_receives_full_catalog_counts_without_extra_source_numbers(monkeypatch):
    captured = {}

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        captured["prompt"] = user_prompt
        return "设备目录共 370 条原始记录，去重后 290 项；以下为部分示例。[1]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer(
        "设备有哪些？",
        [{"id": "equipment-1", "title": "卧式车床", "category": "equipment", "content": "设备型号：CL6134A"}],
        resource_summary={
            "scope": "catalog",
            "record_count": 370,
            "unique_count": 290,
            "equipment_count": 290,
            "equipment": [{"name": "卧式车床", "model": "CL6134A"}],
        },
    )

    assert result["status"] == "ok"
    assert "主数据目录" in captured["prompt"]
    assert "原始记录数：370" in captured["prompt"]
    assert "去重记录数：290" in captured["prompt"]
    assert "设备：290 项" in captured["prompt"]
    assert "当前提供 1 条编号证据，仅为相关记录示例" in captured["prompt"]
    assert "完整清单见页面" in captured["prompt"]
    assert "历史量具" not in captured["prompt"]
    assert "[2]" not in captured["prompt"]
    assert "[2]" not in result["answer"]


@pytest.mark.asyncio
async def test_history_summary_keeps_equipment_and_gauge_totals_separate(monkeypatch):
    captured = {}

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        captured["prompt"] = user_prompt
        return "历史工序记录中有设备与量具，完整资源清单见页面。[1]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer(
        "历史轴套工序有哪些设备和量具？",
        [{"id": "history-1", "title": "轴套工序", "category": "history", "content": "设备：车床；量具：游标卡尺"}],
        resource_summary={
            "scope": "history",
            "record_count": 243,
            "equipment_count": 30,
            "gauge_count": 18,
        },
    )

    assert result["status"] == "ok"
    assert "历史工序资源" in captured["prompt"]
    assert "原始记录数：243" in captured["prompt"]
    assert "设备：30 项" in captured["prompt"]
    assert "量具：18 项" in captured["prompt"]
    assert "设备、刀具、量具分别统计" in captured["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("include_count", [True, False])
async def test_history_catalog_prompt_uses_history_label_and_count(monkeypatch, include_count):
    captured = {}

    async def fake_call_llm(system_prompt, user_prompt, temperature=0.2):
        captured["prompt"] = user_prompt
        return "历史案例目录有 2 项记录，以下是其中一项。[1]"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    summary = {
        "scope": "catalog",
        "record_count": 2,
        "unique_count": 2,
        "history": [{"id": "history-1"}, {"id": "history-2"}],
    }
    if include_count:
        summary["history_count"] = 2
    result = await generate_local_knowledge_answer(
        "有哪些历史轴套工艺案例？",
        [{"id": "history-1", "title": "轴套工序", "category": "history", "content": "工序：粗车"}],
        resource_summary=summary,
    )

    assert result["status"] == "ok"
    assert "历史案例目录" in captured["prompt"]
    assert "历史案例：2 项" in captured["prompt"]
    assert "主数据目录" not in captured["prompt"]
    assert "当前提供 1 条编号证据，仅为相关记录示例" in captured["prompt"]
    assert "[2]" not in captured["prompt"]


@pytest.mark.asyncio
@pytest.mark.parametrize("citation", ["[0]", "[2]", "[999]", "[ 9 ]"])
async def test_answer_rejects_nonexistent_citations_without_retrying(monkeypatch, citation):
    calls = 0

    async def fake_call_llm(*_args, **_kwargs):
        nonlocal calls
        calls += 1
        return f"卧式车床可以满足要求。[1]{citation}"

    monkeypatch.setattr("app.services.knowledge.answer.call_llm", fake_call_llm)
    result = await generate_local_knowledge_answer(
        "设备参数是什么？",
        [{"id": "equipment-1", "title": "卧式车床", "category": "equipment", "content": "设备型号：CL6134A"}],
    )

    assert result["status"] == "insufficient_evidence"
    assert result["answer"] == ""
    assert "不存在的来源编号" in result["message"]
    assert "本地检索记录仍可查看" in result["message"]
    assert calls == 1
