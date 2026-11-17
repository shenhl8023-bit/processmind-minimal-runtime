"""Reported missing recommendations and slow/opaque generation regressions."""
import asyncio
from copy import deepcopy
import json

import pytest

from test_analysis_guidance import guidance_client, _preserved_rows
from test_analysis_guidance_generation import _model_result, _unlock


def test_null_model_recommendation_retains_valid_configured_manual_choice():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    raw = _model_result()
    raw['operation_guidance']['标记']['recommendation'] = None
    result = validate_generated_guidance(raw, default_analysis_guidance([]), ['标记'])
    assert result['operation_guidance']['标记']['recommendation'] == {'mode': 'manual'}
    assert not result['operation_guidance']['标记'].get('recommendation_issues')


def test_repeated_nodes_use_their_own_reviewed_reference_recommendation():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    defaults = default_analysis_guidance([])
    defaults['operation_guidance']['去毛刺#1']['recommendation'] = {'mode': 'manual'}
    operation = _model_result()['operation_guidance']['标记']
    operation['recommendation'] = None
    result = validate_generated_guidance({'operation_guidance': {
        '去毛刺#1': deepcopy(operation), '去毛刺#2': deepcopy(operation),
    }}, defaults, ['去毛刺#1', '去毛刺#2'])
    assert result['operation_guidance']['去毛刺#1']['recommendation'] == {'mode': 'manual'}
    assert result['operation_guidance']['去毛刺#2']['recommendation'] == {'mode': 'mainline'}


def test_fallback_never_restores_features_removed_from_current_candidates():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    operation = _model_result()['operation_guidance']['标记']
    operation['feature_group'] = '孔/内孔'
    operation['recommendation'] = None
    result = validate_generated_guidance({'operation_guidance': {'钻孔': operation},
        'feature_mappings': {'孔/内孔': ['项目专用孔']}}, default_analysis_guidance([]), ['钻孔'])
    assert not result['operation_guidance']['钻孔'].get('recommendation')
    assert result['operation_guidance']['钻孔']['recommendation_issues']


def test_missing_known_question_is_rebuilt_but_unknown_operation_is_not_invented():
    from fastapi import HTTPException
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    result = validate_generated_guidance({'operation_guidance': {}}, default_analysis_guidance([]), ['标记'])
    assert result['operation_guidance']['标记']['recommendation'] == {'mode': 'manual'}
    assert result['operation_guidance']['标记']['questions']['guided_mode']['prompt']
    with pytest.raises(HTTPException) as error:
        validate_generated_guidance({'operation_guidance': {}}, default_analysis_guidance([]), ['未知项目工序'])
    assert error.value.status_code == 422


def test_root_options_are_system_contract_even_when_model_omits_or_renames_them():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    raw = _model_result()
    raw['operation_guidance']['标记']['questions']['guided_mode']['option_labels'] = {'condition': '只看材料'}
    result = validate_generated_guidance(raw, default_analysis_guidance([]), ['标记'])
    labels = result['operation_guidance']['标记']['questions']['guided_mode']['option_labels']
    assert list(labels) == ['mainline', 'manual', 'condition', 'relation', 'custom']
    assert labels['condition'] == '根据条件设置'
    assert labels['custom'] == '其他'


def test_model_context_deduplicates_documents_without_losing_distinct_process_facts():
    from app.services import analysis_guidance_generation as generation
    rows = [{'document_id': index, 'pdf_name': 'sample%d.pdf' % index,
             'operation_content': '钻通孔，精度IT7' if index % 2 else '钻盲孔，深度8'} for index in range(20)]
    items = [{'id': 'hole-a', 'normalized_step_name': '钻孔', 'sequence': 10, 'phase': '粗加工',
              'doc_coverage': {'hit_docs': 10, 'total_docs': 20}, 'matched_detail_rows': rows,
              'evidence_excerpt': ['A侧孔'], 'source_operation_names': ['钻孔']}]
    compact = generation._model_route_context(items)
    encoded = json.dumps(compact, ensure_ascii=False)
    assert '钻通孔，精度IT7' in encoded and '钻盲孔，深度8' in encoded
    assert 'hole-a' in encoded and 'A侧孔' in encoded and '粗加工' in encoded
    assert encoded.count('钻通孔，精度IT7') == 1
    assert len(encoded) < len(json.dumps(items, ensure_ascii=False)) / 2


def test_material_pdf_reads_are_reused_and_replaced_files_invalidate_cache(tmp_path, monkeypatch):
    from app.services import analysis_guidance as guidance
    root = tmp_path / 'uploads'
    root.mkdir()
    source = root / 'material.pdf'
    source.write_bytes(b'first')
    monkeypatch.setattr(guidance.paths, 'UPLOAD_DIR', root)
    opened = []
    class Page:
        def get_text(self):
            return '材料牌号: 6061\n'
    class Pdf:
        def __enter__(self): return [Page()]
        def __exit__(self, *args): pass
    def open_pdf(path):
        opened.append(path)
        return Pdf()
    monkeypatch.setattr(guidance.fitz, 'open', open_pdf)
    assert guidance._read_pdf_materials(['material.pdf']) == ['6061']
    assert guidance._read_pdf_materials(['material.pdf']) == ['6061']
    assert len(opened) == 1
    source.write_bytes(b'second version')
    assert guidance._read_pdf_materials(['material.pdf']) == ['6061']
    assert len(opened) == 2


def test_generation_timeout_has_clear_reason_and_bounded_provider_retries(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    calls = []
    async def model(*args, **kwargs):
        calls.append(kwargs)
        raise asyncio.TimeoutError()
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 503
    assert '超时' in response.json()['detail']['message']
    assert calls[0]['timeout_seconds'] == 50
    assert calls[0]['max_retries'] == 2


def test_generation_duplicate_requests_share_one_model_result(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    calls = []
    async def model(*args, **kwargs):
        calls.append(True)
        await asyncio.sleep(0.02)
        return json.dumps(_model_result(), ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    async def run():
        async with sessions() as first, sessions() as second:
            return await asyncio.gather(generation.generate_analysis_guidance(first, 9),
                                        generation.generate_analysis_guidance(second, 9))
    results = asyncio.run(run())
    assert results[0]['configuration'] == results[1]['configuration']
    assert len(calls) == 1


def test_null_model_preserves_saved_project_choice_and_supplies_it_to_model(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    configuration['operation_guidance']['标记']['recommendation'] = {'mode': 'mainline'}
    saved = client.put('/api/projects/9/analysis-guidance', json={
        'expected_configuration_revision': 0, 'configuration': configuration,
    })
    assert saved.status_code == 200, saved.text
    references = []
    async def model(_prompt, user, **kwargs):
        references.append(json.loads(user)['reference_configuration'])
        output = _model_result()
        output['operation_guidance']['标记']['recommendation'] = None
        return json.dumps(output, ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['operation_guidance']['标记']['recommendation'] == {'mode': 'mainline'}
    assert references[0]['operation_guidance']['标记']['recommendation'] == {'mode': 'mainline'}
    # Using the saved reference must not make the version hash depend on output.
    assert client.post('/api/projects/9/analysis-guidance/generate').json() == response.json()
    assert len(references) == 1


def test_exact_saved_heat_recommendation_is_preserved_without_factory_alias(guidance_client, monkeypatch):
    from sqlalchemy import update
    from app.models.models import NormalizedRouteVersion
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    async def set_route():
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90)
                .values(route_json='[{"id":"vacuum","normalized_step_name":"真空淬火"}]'))
            await db.commit()
    asyncio.run(set_route())
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    configuration['operation_guidance']['真空淬火'] = {
        'recommendation': {'mode': 'condition', 'basis': 'material', 'materials': ['9Cr18']}}
    assert client.put('/api/projects/9/analysis-guidance', json={
        'expected_configuration_revision': 0, 'configuration': configuration}).status_code == 200
    async def model(*args, **kwargs):
        return json.dumps({'operation_guidance': {'真空淬火': {'recommendation': None}}})
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['operation_guidance']['真空淬火']['recommendation'] == {
        'mode': 'condition', 'basis': 'material', 'materials': ['9Cr18']}


@pytest.mark.parametrize('name', ['去毛刺', '清洗', '检验'])
@pytest.mark.parametrize('omitted', [False, True])
def test_single_auxiliary_resolves_first_occurrence_reference(name, omitted):
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    raw = {'operation_guidance': {} if omitted else {name: {'recommendation': None}}}
    actual = validate_generated_guidance(raw, default_analysis_guidance([]), [name])
    assert actual['operation_guidance'][name]['recommendation'] == {'mode': 'mainline'}


def test_first_occurrence_reference_is_not_applied_to_later_repeats():
    from app.services.analysis_guidance import default_analysis_guidance
    from app.services.analysis_guidance_generation import validate_generated_guidance
    defaults = default_analysis_guidance([])
    del defaults['operation_guidance']['清洗#2']
    result = validate_generated_guidance({'operation_guidance': {
        '清洗#1': {'recommendation': None}, '清洗#2': {'recommendation': None}}}, defaults, ['清洗#1', '清洗#2'])
    assert result['operation_guidance']['清洗#1']['recommendation'] == {'mode': 'mainline'}
    assert not result['operation_guidance']['清洗#2'].get('recommendation')


@pytest.mark.parametrize('error_name', ['ReadTimeout', 'ConnectTimeout', 'PoolTimeout', 'WriteTimeout'])
def test_actual_provider_timeout_uses_safe_timeout_diagnosis(guidance_client, monkeypatch, error_name):
    import httpx
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    async def model(*args, **kwargs):
        raise getattr(httpx, error_name)('secret-provider-url-and-token')
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'analysis_generation_timeout'
    assert '超时' in response.json()['detail']['message']
    assert 'secret-provider' not in response.text


@pytest.mark.parametrize('failure, expected_code', [
    ('tls', 'analysis_model_tls_failed'),
    ('connect', 'analysis_model_connect_failed'),
    ('auth', 'analysis_model_auth_failed'),
])
def test_provider_connection_failure_keeps_answers_and_explains_cause(guidance_client, monkeypatch, failure, expected_code):
    import ssl
    import httpx
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    before = _preserved_rows(sessions)
    async def model(*args, **kwargs):
        if failure == 'auth':
            request = httpx.Request('POST', 'https://synthetic.example.test/v1/chat/completions')
            raise httpx.HTTPStatusError('synthetic-provider-secret', request=request,
                response=httpx.Response(401, request=request))
        error = httpx.ConnectError('synthetic-provider-secret')
        if failure == 'tls':
            error.__cause__ = ssl.SSLEOFError('synthetic TLS closed')
        raise error
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == expected_code
    assert '已有回答会保留' in response.json()['detail']['message']
    assert 'synthetic-provider-secret' not in response.text
    assert _preserved_rows(sessions) == before


@pytest.mark.parametrize('case', ['material', 'direction', 'ambiguous_relation'])
def test_saved_reference_is_revalidated_against_new_model_domains(guidance_client, monkeypatch, case):
    from sqlalchemy import update
    from app.models.models import NormalizedRouteVersion
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    if case == 'material':
        name, names = '真空淬火', ['真空淬火']
        configuration['operation_guidance'][name] = {
            'recommendation': {'mode': 'condition', 'basis': 'material', 'materials': ['9Cr18']}}
        raw = {'materials': ['6061']}
    elif case == 'direction':
        name, names = '钻孔', ['钻孔']
        raw = {'directions': ['A侧']}
    else:
        name, names = '除铜', ['镀铜#1', '镀铜#2', '除铜']
        raw = {}
    async def set_route():
        async with sessions() as db:
            rows = [{'id': 'p%s' % index, 'normalized_step_name': key.split('#')[0]}
                    for index, key in enumerate(names)]
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90)
                .values(route_json=json.dumps(rows, ensure_ascii=False)))
            await db.commit()
    asyncio.run(set_route())
    assert client.put('/api/projects/9/analysis-guidance', json={
        'expected_configuration_revision': 0, 'configuration': configuration}).status_code == 200
    raw['operation_guidance'] = {key: {'recommendation': None} for key in names}
    async def model(*args, **kwargs):
        return json.dumps(raw, ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    operation = response.json()['configuration']['operation_guidance'][name]
    assert not operation.get('recommendation')
    assert operation['recommendation_issues']


def test_saved_custom_recommendation_survives_when_final_candidates_still_include_it(guidance_client, monkeypatch):
    from sqlalchemy import update
    from app.models.models import NormalizedRouteVersion
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    async def set_route():
        async with sessions() as db:
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90)
                .values(route_json='[{"id":"drill","normalized_step_name":"钻孔"}]'))
            await db.commit()
    asyncio.run(set_route())
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    configuration['feature_mappings']['孔/内孔'] = ['项目专用孔']
    for operation in configuration['operation_guidance'].values():
        if operation.get('feature_group') == '孔/内孔':
            operation.pop('recommendation', None)
    expected = {'mode': 'condition', 'basis': 'feature', 'features': ['项目专用孔'], 'direction': '周边'}
    configuration['operation_guidance']['钻孔']['recommendation'] = expected
    assert client.put('/api/projects/9/analysis-guidance', json={
        'expected_configuration_revision': 0, 'configuration': configuration}).status_code == 200
    async def model(*args, **kwargs):
        return json.dumps({'feature_mappings': {'孔/内孔': ['项目专用孔']},
            'operation_guidance': {'钻孔': {'recommendation': None}}}, ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    assert response.json()['configuration']['operation_guidance']['钻孔']['recommendation'] == expected


@pytest.mark.parametrize('has_node_identity', [False, True])
def test_renaming_first_repeated_node_never_assigns_its_saved_choice_to_second(
    guidance_client, monkeypatch, has_node_identity,
):
    from sqlalchemy import update
    from app.models.models import NormalizedRouteVersion, Project
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    configuration['operation_guidance'] = {'清洗#1': {'recommendation': {'mode': 'mainline'}},
        '清洗#2': {'recommendation': {'mode': 'manual'}}}
    configuration['generation_route_id'] = 90
    if has_node_identity:
        configuration['generation_operation_ids'] = {'清洗#1': 'first', '清洗#2': 'second'}
    async def seed_saved_guide_and_rename_first():
        async with sessions() as db:
            # Same route record, same stable node IDs: only first node's name changes.
            await db.execute(update(Project).where(Project.id == 9).values(
                analysis_guidance_json=json.dumps(configuration, ensure_ascii=False)))
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90)
                .values(route_json=json.dumps([
                    {'id': 'first', 'normalized_step_name': '清洗前检查'},
                    {'id': 'second', 'normalized_step_name': '清洗'}], ensure_ascii=False)))
            await db.commit()
    asyncio.run(seed_saved_guide_and_rename_first())
    async def model(*args, **kwargs):
        return json.dumps({'operation_guidance': {
            '清洗前检查': {'recommendation': None}, '清洗': {'recommendation': None}}}, ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 200, response.text
    actual = response.json()['configuration']
    operation = actual['operation_guidance']['清洗']
    if has_node_identity:
        assert operation['recommendation'] == {'mode': 'manual'}
    else:
        assert not operation.get('recommendation')
        assert operation['recommendation_issues']
    assert actual['generation_operation_ids'] == {'清洗前检查': 'first', '清洗': 'second'}


def test_unresolved_legacy_occurrence_reference_stays_blocked_across_retries(guidance_client, monkeypatch):
    from sqlalchemy import update
    from app.models.models import NormalizedRouteVersion, Project
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    configuration.update(generation_route_id=90, operation_guidance={
        '清洗#1': {'recommendation': {'mode': 'mainline'}},
        '清洗#2': {'recommendation': {'mode': 'manual'}}})
    async def seed():
        async with sessions() as db:
            await db.execute(update(Project).where(Project.id == 9).values(
                analysis_guidance_json=json.dumps(configuration, ensure_ascii=False)))
            await db.execute(update(NormalizedRouteVersion).where(NormalizedRouteVersion.id == 90)
                .values(route_json='[{"id":"first","normalized_step_name":"清洗前检查"},{"id":"second","normalized_step_name":"清洗"}]'))
            await db.commit()
    asyncio.run(seed())
    suggestion = None
    async def model(*args, **kwargs):
        return json.dumps({'operation_guidance': {
            '清洗前检查': {'recommendation': None}, '清洗': {'recommendation': suggestion}}}, ensure_ascii=False)
    monkeypatch.setattr(generation, 'call_llm', model)
    for attempt in range(3):
        response = client.post('/api/projects/9/analysis-guidance/generate?retry_recommendations=true')
        assert response.status_code == 200, response.text
        operation = response.json()['configuration']['operation_guidance']['清洗']
        assert not operation.get('recommendation'), (attempt, operation)
        assert operation['recommendation_issues']
    # A real valid new recommendation can resolve the uncertainty.
    suggestion = {'mode': 'manual'}
    response = client.post('/api/projects/9/analysis-guidance/generate?retry_recommendations=true')
    assert response.status_code == 200, response.text
    operation = response.json()['configuration']['operation_guidance']['清洗']
    assert operation['recommendation'] == suggestion
    assert not operation.get('recommendation_reference_blocked')
