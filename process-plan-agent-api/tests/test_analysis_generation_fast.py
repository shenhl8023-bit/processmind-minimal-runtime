"""Performance regressions through the real generation/save boundary."""
import asyncio
from copy import deepcopy
import json

import pytest
from sqlalchemy import update

from app.models.models import NormalizedRouteVersion, Project
from test_analysis_guidance import guidance_client, _preserved_rows
from test_analysis_guidance_generation import _unlock


def _route(sessions, names):
    async def seed():
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90).values(
                route_json=json.dumps([{'id': 'p%s' % i, 'normalized_step_name': n}
                                       for i, n in enumerate(names)], ensure_ascii=False)))
            await db.commit()
    asyncio.run(seed())


@pytest.mark.parametrize('name', ['下料', '备料', '下料备料', '下料#2'])
def test_preparation_has_requirement_branch_without_invented_feature_group(name):
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    result = validate_generated_guidance({'operation_guidance': {name: {
        'recommendation': {'mode': 'condition', 'basis': 'requirement'}}}},
        default_analysis_guidance([]), [name])
    assert result['operation_guidance'][name]['recommendation']['basis'] == 'requirement'
    assert not result['operation_guidance'][name].get('feature_group')


def test_large_route_uses_small_parallel_requests_and_scoped_reference(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    names = ['检查%s' % i for i in range(40)]
    _route(sessions, names)
    active = 0
    peak = 0
    sizes = []
    async def model(system, user, **kwargs):
        nonlocal active, peak
        data = json.loads(user)
        active += 1
        peak = max(peak, active)
        sizes.append(len(data['operation_names']))
        assert set(data['reference_configuration']['operation_guidance']) <= set(data['operation_names'])
        assert len(data['route']) == len(data['operation_names'])
        await asyncio.sleep(0.02)
        active -= 1
        return json.dumps({'operation_guidance': {name: {'recommendation': {'mode': 'manual'}}
                                                for name in data['operation_names']}})
    monkeypatch.setattr(generation, 'call_llm', model)
    before = _preserved_rows(sessions)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert max(sizes) <= 16
    assert 1 < peak <= 3
    assert set(response.json()['configuration']['operation_guidance']) == set(names)
    assert _preserved_rows(sessions) == before


def test_repairs_only_bad_node_and_preserves_good_questions(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    _route(sessions, ['检查', '项目铣削'])
    calls = []
    async def model(system, user, **kwargs):
        data = json.loads(user)
        calls.append(data['operation_names'])
        if len(calls) == 1:
            return json.dumps({'operation_guidance': {
                '检查': {'questions': {'guided_mode': {'prompt': '已完成的检查问句'}},
                         'recommendation': {'mode': 'manual'}},
                '项目铣削': {'recommendation': {'mode': 'manual'}}}})
        return json.dumps({'operation_guidance': {'项目铣削': {
            'feature_group': '扁位', 'recommendation': {'mode': 'condition', 'basis': 'feature',
                'features': ['平面'], 'direction': '周边'}}}})
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert calls == [['检查', '项目铣削'], ['项目铣削']]
    ops = response.json()['configuration']['operation_guidance']
    assert ops['检查']['questions']['guided_mode']['prompt'] == '已完成的检查问句'
    assert ops['项目铣削']['feature_group'] == '扁位'


def test_cross_batch_relation_keeps_full_route_identity(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    names = ['镀铜'] + ['检查%s' % i for i in range(17)] + ['除铜']
    _route(sessions, names)
    async def model(system, user, **kwargs):
        data = json.loads(user)
        assert data['route_operation_names'] == names
        return json.dumps({'operation_guidance': {name: {'recommendation': (
            {'mode': 'relation', 'source_operation_name': '镀铜'} if name == '除铜' else {'mode': 'manual'})}
            for name in data['operation_names']}})
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['operation_guidance']['除铜']['recommendation']['mode'] == 'relation'


def test_conflicting_batch_candidates_never_save_partial_result(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    _route(sessions, ['检查%s' % i for i in range(20)])
    async def model(system, user, **kwargs):
        names = json.loads(user)['operation_names']
        return json.dumps({'directions': ['A侧'] if names[0] == '检查0' else ['B侧'],
            'operation_guidance': {name: {'recommendation': {'mode': 'manual'}} for name in names}})
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 422, response.text
    assert '冲突' in response.json()['detail']['reason']
    assert not client.get('/api/projects/9/analysis-guidance').json()['configuration'].get('generation_version')


def test_same_version_retry_sends_only_missing_node(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    _route(sessions, ['检查', '标记'])
    calls = []
    async def model(system, user, **kwargs):
        names = json.loads(user)['operation_names']
        calls.append(names)
        return json.dumps({'operation_guidance': {n: {'recommendation': {'mode': 'manual'}} for n in names}})
    monkeypatch.setattr(generation, 'call_llm', model)
    first = client.post('/api/projects/9/analysis-guidance/generate').json()['configuration']
    first['operation_guidance']['检查'].pop('recommendation')
    first['operation_guidance']['检查']['recommendation_issues'] = ['推荐暂不可用']
    async def seed():
        async with sessions() as db:
            await db.execute(update(Project).where(Project.id == 9).values(analysis_guidance_json=json.dumps(first)))
            await db.commit()
    asyncio.run(seed())
    response = client.post('/api/projects/9/analysis-guidance/generate?retry_recommendations=true')
    assert response.status_code == 200, response.text
    assert calls == [['检查', '标记'], ['检查']]
    assert response.json()['configuration']['operation_guidance']['标记'] == first['operation_guidance']['标记']


def test_route_phase_disambiguates_rough_composite_and_named_finishing():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    names = ['挖槽去毛刺', '精车', '下料']
    raw = {'operation_guidance': {
        '挖槽去毛刺': {'feature_group': '铣槽', 'recommendation': {'mode': 'condition',
            'basis': 'feature', 'features': ['通槽'], 'direction': '周边'}},
        '精车': {'feature_group': '外圆', 'recommendation': {'mode': 'condition', 'basis': 'precision', 'it_threshold': 7}},
        '下料': {'recommendation': {'mode': 'condition', 'basis': 'requirement'}}}}
    actual = validate_generated_guidance(raw, default_analysis_guidance([]), names,
        operation_phases={'挖槽去毛刺': 'rough', '精车': 'finish', '下料': 'rough'})
    assert [actual['operation_guidance'][name]['recommendation']['basis'] for name in names] == [
        'feature', 'precision', 'requirement']


def test_failed_batch_cancels_siblings_without_publishing(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    _route(sessions, ['检查%s' % i for i in range(32)])
    cancelled = []
    entered = None
    async def model(system, user, **kwargs):
        nonlocal entered
        if entered is None:
            entered = asyncio.Event()
        names = json.loads(user)['operation_names']
        if names[0] == '检查0':
            await entered.wait()
            raise asyncio.TimeoutError()
        try:
            entered.set()
            await asyncio.Event().wait()
        finally:
            cancelled.append(True)
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 503
    assert cancelled == [True]
    assert not client.get('/api/projects/9/analysis-guidance').json()['configuration'].get('generation_version')
