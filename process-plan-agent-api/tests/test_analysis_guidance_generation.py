"""File instructions must reach model output, without rewriting existing work."""
import asyncio
from copy import deepcopy
import json

import pytest
from sqlalchemy import update

from test_analysis_guidance import guidance_client, _preserved_rows
from app.models.models import NormalizedRouteVersion


def _unlock(sessions):
    async def run():
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(
                NormalizedRouteVersion.id == 90).values(analysis_locked_at=None))
            await db.commit()
    asyncio.run(run())


def _model_result():
    return {"operation_guidance": {"标记": {
        "recommendation": {"mode": "manual"},
        "questions": {"guided_mode": {"prompt": "这件活，标记这一步平时怎么安排？",
            "option_labels": {"mainline": "每件都做", "manual": "做不做，由我来定",
                "condition": "看具体条件", "relation": "跟着前面的工序走", "custom": "其它安排"}}},
    }}}


def test_missing_feature_group_uses_only_the_operation_reference_group():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    operation = _model_result()["operation_guidance"]["标记"]
    operation["recommendation"] = None
    result = validate_generated_guidance(
        {"operation_guidance": {"铣扁": operation}},
        default_analysis_guidance([]), ["铣扁"],
    )
    assert result["operation_guidance"]["铣扁"]["feature_group"] == "扁位"
    assert result["feature_mappings"]["扁位"]
    assert result["operation_guidance"]["铣扁"]["recommendation"] == {
        'mode': 'condition', 'basis': 'feature', 'features': ['平面'], 'direction': '周边',
    }


def test_finishing_threshold_only_keeps_valid_same_operation_object_fallback():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    result = validate_generated_guidance({'operation_guidance': {'磨孔': {
        'recommendation': {'mode': 'condition', 'basis': 'precision', 'it_threshold': 6},
    }}}, default_analysis_guidance([]), ['磨孔'])
    recommendation = result['operation_guidance']['磨孔']['recommendation']
    assert recommendation['it_threshold'] == 6
    assert recommendation['features'] == ['内圆柱面']
    assert recommendation['direction'] == '所有方位'


def test_finishing_without_any_object_domain_is_rejected_before_saving_guide():
    from fastapi import HTTPException
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    with pytest.raises(HTTPException) as error:
        validate_generated_guidance({'operation_guidance': {'项目精加工': {
            'recommendation': {'mode': 'condition', 'basis': 'precision', 'it_threshold': 7},
        }}}, default_analysis_guidance([]), ['项目精加工'], operation_phases={'项目精加工': 'finish'})
    assert '特征条件分支缺少有效分组和候选' in error.value.detail['reason']


def test_finishing_can_remain_threshold_only_for_runtime_confirmed_object_reuse():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    result = validate_generated_guidance({'operation_guidance': {'项目精加工': {
        'feature_group': '孔/内孔',
        'recommendation': {'mode': 'condition', 'basis': 'precision', 'it_threshold': 6},
    }}}, default_analysis_guidance([]), ['项目精加工'], operation_phases={'项目精加工': 'finish'})
    assert result['operation_guidance']['项目精加工']['recommendation'] == {
        'mode': 'condition', 'basis': 'precision', 'it_threshold': 6,
    }


def test_old_threshold_only_recommendations_can_use_valid_current_object_fallback_without_writes():
    from app.services.analysis_guidance import default_analysis_guidance, complete_object_recommendations
    defaults = default_analysis_guidance([])
    saved = deepcopy(defaults)
    saved['operation_guidance']['磨孔']['recommendation'] = {'mode': 'condition', 'basis': 'precision', 'it_threshold': 5}
    raw = deepcopy(saved)
    actual = complete_object_recommendations(saved, defaults)
    assert actual['operation_guidance']['磨孔']['recommendation'] == {
        'mode': 'condition', 'basis': 'precision', 'it_threshold': 5, 'features': ['内圆柱面'], 'direction': '所有方位'}
    assert saved == raw
    # No incompatible candidate or ambiguous occurrence fallback.
    for changes in [{'feature_group': '外圆'}, {'recommendation_reference_blocked': True}]:
        limited = deepcopy(saved)
        limited['operation_guidance']['磨孔'].update(changes)
        assert not complete_object_recommendations(limited, defaults)['operation_guidance']['磨孔']['recommendation'].get('features')
    limited = deepcopy(saved)
    limited['feature_mappings']['孔/内孔'] = ['自定义孔']
    assert not complete_object_recommendations(limited, defaults)['operation_guidance']['磨孔']['recommendation'].get('features')


def test_copper_removal_relation_accepts_surface_questions_without_feature_groups():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    copper = _model_result()["operation_guidance"]["标记"]
    removal = deepcopy(copper)
    removal["recommendation"] = {"mode": "relation", "source_operation_name": "镀铜"}
    result = validate_generated_guidance(
        {"operation_guidance": {"镀铜": copper, "除铜": removal}},
        default_analysis_guidance(["6061"]), ["镀铜", "除铜"],
    )
    assert result["operation_guidance"]["镀铜"]["recommendation"] == {"mode": "manual"}
    assert result["operation_guidance"]["除铜"]["recommendation"] == {
        "mode": "relation", "source_operation_name": "镀铜",
    }
    assert not result["operation_guidance"]["除铜"].get("feature_group")


@pytest.mark.parametrize("recommendation", [
    {"mode": "mainline"}, {"mode": "manual"}, {"mode": "relation", "source_operation_name": "镀铜"},
])
def test_recommendation_does_not_bypass_missing_feature_branch(recommendation):
    from fastapi import HTTPException
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    copper = _model_result()["operation_guidance"]["标记"]
    machining = deepcopy(copper)
    machining["recommendation"] = recommendation
    with pytest.raises(HTTPException) as error:
        validate_generated_guidance(
            {"operation_guidance": {"镀铜": copper, "项目铣削": machining}},
            default_analysis_guidance(["6061"]), ["镀铜", "项目铣削"],
        )
    assert error.value.status_code == 422
    assert "特征条件分支缺少有效分组和候选" in error.value.detail["reason"]


@pytest.mark.parametrize("items, expected_status", [
    ([{"id": "cut", "normalized_step_name": "下料备料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "cut", "normalized_step_name": "下料备料", "doc_coverage": {"hit_docs": 1, "total_docs": 2}}], 200),
    ([{"id": "cut", "normalized_step_name": "下料备料"}], 200),
    ([{"id": "merged", "normalized_step_name": "下料/备料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "merged", "normalized_step_name": "下料／备料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "qualified", "normalized_step_name": "下料/备料（锯床）", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "named", "normalized_step_name": "下料准备（锯床）", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "opened", "normalized_step_name": "开料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "cut", "normalized_step_name": "切料／下料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}}], 200),
    ([{"id": "cut1", "normalized_step_name": "下料备料", "doc_coverage": {"hit_docs": 2, "total_docs": 2}},
      {"id": "cut2", "normalized_step_name": "下料备料", "doc_coverage": {"hit_docs": 1, "total_docs": 2}}], 200),
])
def test_preparation_branches_are_usable_but_mixed_names_still_need_features(
    guidance_client, monkeypatch, items, expected_status,
):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)

    async def set_route():
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(
                NormalizedRouteVersion.id == 90).values(route_json=json.dumps(items, ensure_ascii=False)))
            await db.commit()
    asyncio.run(set_route())

    async def model(_system, user, **_kwargs):
        operation = _model_result()["operation_guidance"]["标记"]
        operation["recommendation"] = {"mode": "mainline"}
        return json.dumps({"operation_guidance": {
            name: operation for name in json.loads(user)["operation_names"]
        }}, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    response = client.post("/api/projects/9/analysis-guidance/generate")
    assert response.status_code == expected_status, response.text
    if expected_status == 200:
        assert all(op["recommendation"] == {"mode": "mainline"}
                   for op in response.json()["configuration"]["operation_guidance"].values())
    else:
        assert response.json()["detail"]["code"] == "analysis_questions_invalid"


@pytest.mark.parametrize("name, materials", [("项目铣削", []), ("淬火", [])])
def test_unusable_manual_branch_is_a_structure_error(name, materials):
    from fastapi import HTTPException
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance

    operation = _model_result()["operation_guidance"]["标记"]
    operation["recommendation"] = None
    with pytest.raises(HTTPException) as error:
        validate_generated_guidance(
            {"operation_guidance": {name: operation}},
            default_analysis_guidance(materials), [name],
        )
    assert error.value.status_code == 422
    assert error.value.detail["code"] == "analysis_questions_invalid"


def test_file_changes_generate_new_questions_and_cache_only_same_version(guidance_client, monkeypatch, tmp_path):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    prompt = tmp_path / "common.md"
    prompt.write_text("用老师傅口吻；孔候选加入项目孔", encoding="utf-8")
    monkeypatch.setattr(generation, "COMMON_PROMPT_PATH", prompt)
    monkeypatch.setattr(generation, "PROJECT_PROMPT_DIR", tmp_path / "projects")
    calls = []
    async def model(system, user, **kwargs):
        calls.append((system, user))
        result = _model_result()
        result["feature_mappings"] = {"孔/内孔": ["孔", "项目孔"]}
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    before = _preserved_rows(sessions)
    first = client.post("/api/projects/9/analysis-guidance/generate")
    assert first.status_code == 200, first.text
    config = first.json()["configuration"]
    assert config["feature_mappings"]["孔/内孔"] == ["孔", "项目孔"]
    assert config["operation_guidance"]["标记"]["questions"]["guided_mode"]["prompt"].startswith("这件活")
    assert "孔候选加入项目孔" in calls[0][0]
    assert client.post("/api/projects/9/analysis-guidance/generate").json()["configuration"] == config
    assert len(calls) == 1
    prompt.write_text("用老师傅口吻；更新了项目指导", encoding="utf-8")
    second = client.post("/api/projects/9/analysis-guidance/generate")
    assert second.status_code == 200, second.text
    assert second.json()["configuration"]["generation_version"] != config["generation_version"]
    assert len(calls) == 2
    assert _preserved_rows(sessions) == before


@pytest.mark.parametrize("recommendation", [
    {"mode": "condition", "basis": "material", "materials": ["UNKNOWN"]},
    {"mode": "condition", "basis": "feature", "features": ["孔(盲孔)"]},
    {"mode": "relation", "source_operation_name": "不存在的前序工序"},
])
def test_invalid_model_recommendation_retains_valid_configured_manual_choice(guidance_client, monkeypatch, recommendation):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    async def model(*args, **kwargs):
        result = _model_result()
        result["operation_guidance"]["标记"]["feature_group"] = "孔/内孔"
        result["operation_guidance"]["标记"]["recommendation"] = deepcopy(recommendation)
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    response = client.post("/api/projects/9/analysis-guidance/generate")
    assert response.status_code == 200, response.text
    operation = response.json()["configuration"]["operation_guidance"]["标记"]
    assert operation["recommendation"] == {'mode': 'manual'}
    assert not operation.get("recommendation_issues")
    assert operation["questions"]["guided_mode"]["option_labels"]["manual"]


def test_missing_root_label_is_normalized_and_locked_generation_never_calls_model(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    calls = []
    async def model(*args, **kwargs):
        calls.append(True)
        result = _model_result()
        del result["operation_guidance"]["标记"]["questions"]["guided_mode"]["option_labels"]["custom"]
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    assert client.post("/api/projects/9/analysis-guidance/generate").status_code == 409
    assert calls == []
    _unlock(sessions)
    response = client.post("/api/projects/9/analysis-guidance/generate")
    assert response.status_code == 200, response.text
    labels = response.json()['configuration']['operation_guidance']['标记']['questions']['guided_mode']['option_labels']
    assert labels['custom'] == '其他'
    assert len(labels) == 5


def test_finalization_lock_while_model_runs_prevents_late_guidance_write(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    async def model(*args, **kwargs):
        from datetime import datetime
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(
                NormalizedRouteVersion.id == 90).values(analysis_locked_at=datetime(2026, 11, 5)))
            await db.commit()
        return json.dumps(_model_result(), ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    response = client.post("/api/projects/9/analysis-guidance/generate")
    assert response.status_code == 409, response.text
    assert response.json()["detail"]["code"] == "analysis_locked"
    assert not client.get("/api/projects/9/analysis-guidance").json()["configuration"].get("generation_version")


def test_explicit_retry_refreshes_missing_recommendation_without_changing_cached_questions(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    calls = []
    async def model(*args, **kwargs):
        calls.append(True)
        result = _model_result()
        operation = result["operation_guidance"]["标记"]
        if len(calls) == 1:
            operation["recommendation"] = None
        else:
            operation["questions"]["guided_mode"]["prompt"] = "重试不应替换已有题面"
            result["materials"] = ["新的材料不能覆盖缓存候选"]
        return json.dumps(result, ensure_ascii=False)
    monkeypatch.setattr(generation, "call_llm", model)
    before = _preserved_rows(sessions)
    first = client.post("/api/projects/9/analysis-guidance/generate").json()["configuration"]
    # Reproduce an existing same-version missing recommendation (as seen in the
    # user's saved guide), without weakening the new first-generation fallback.
    first['operation_guidance']['标记'].pop('recommendation', None)
    first['operation_guidance']['标记']['recommendation_issues'] = ['推荐暂不可用']
    async def seed_existing_missing_guide():
        from app.models.models import Project
        async with sessions() as db:
            await db.execute(update(Project).where(Project.id == 9).values(
                analysis_guidance_json=json.dumps(first, ensure_ascii=False)))
            await db.commit()
    asyncio.run(seed_existing_missing_guide())
    assert not first["operation_guidance"]["标记"].get("recommendation")
    assert client.post("/api/projects/9/analysis-guidance/generate").json()["configuration"] == first
    retried = client.post("/api/projects/9/analysis-guidance/generate?retry_recommendations=true")
    assert retried.status_code == 200, retried.text
    config = retried.json()["configuration"]
    assert config["operation_guidance"]["标记"].get("recommendation") == {"mode": "manual"}
    assert config["operation_guidance"]["标记"]["questions"] == first["operation_guidance"]["标记"]["questions"]
    assert config["materials"] == first["materials"]
    assert config["generation_version"] == first["generation_version"]
    assert config["revision"] == first["revision"] + 1
    # Complete caches cannot be force-regenerated by repeatedly clicking retry.
    again = client.post("/api/projects/9/analysis-guidance/generate?retry_recommendations=true")
    assert again.json()["configuration"] == config
    assert len(calls) == 2
    assert _preserved_rows(sessions) == before
