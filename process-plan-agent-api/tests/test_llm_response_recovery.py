"""PM-092: successful HTTP responses still need usable, complete model output."""
import json
import logging

import httpx
import pytest

from app.services import llm_client
from app.services.llm_errors import describe_llm_error
from test_analysis_guidance import guidance_client, _preserved_rows
from test_analysis_guidance_generation import _unlock
from test_model_settings_regressions import settings_client

CONFIG = {'url': 'https://example.test/v1/chat/completions', 'key': 'synthetic-secret', 'model': 'demo'}


def _reply(content, reason='stop', **message):
    return {'choices': [{'message': dict(message, content=content), 'finish_reason': reason}]}


def _provider(monkeypatch, replies):
    requests = []
    client = httpx.AsyncClient

    def respond(request):
        requests.append(json.loads(request.content))
        reply = replies[min(len(requests) - 1, len(replies) - 1)]
        return httpx.Response(200, text=reply) if isinstance(reply, str) else httpx.Response(200, json=reply)

    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(llm_client.httpx, 'AsyncClient', lambda **kwargs: client(transport=transport, **kwargs))

    async def no_sleep(_seconds):
        pass
    monkeypatch.setattr(llm_client.asyncio, 'sleep', no_sleep)
    return requests


@pytest.mark.asyncio
@pytest.mark.parametrize('empty', [None, '', '   ', []])
async def test_empty_response_retries_without_replacing_request_or_using_reasoning(monkeypatch, empty):
    calls = _provider(monkeypatch, [_reply(empty, reasoning_content='private reasoning'), _reply('{"ok":true}')])
    result = await llm_client.request_llm_completion(CONFIG, 'system', 'user', max_retries=2, max_tokens=900)
    assert result == '{"ok":true}'
    assert len(calls) == 2
    assert calls[0] == calls[1]


@pytest.mark.asyncio
@pytest.mark.parametrize('max_retries, attempts', [(0, 1), (1, 2), (2, 2)])
async def test_repeated_empty_output_stops_and_reports_empty_response(monkeypatch, max_retries, attempts):
    calls = _provider(monkeypatch, [_reply(None)])
    with pytest.raises(llm_client.LLMResponseError) as failure:
        await llm_client.request_llm_completion(CONFIG, 'system', 'user', max_retries=max_retries)
    assert len(calls) == attempts
    code, message = describe_llm_error(failure.value)
    assert code == 'llm_empty_response'
    assert '未返回' in message
    assert 'OpenAI' not in message


@pytest.mark.asyncio
@pytest.mark.parametrize('reply, expected', [
    (_reply('{"apparently_complete":true}', 'length'), 'llm_output_truncated'),
    (_reply(None, 'length', reasoning_content='private reasoning'), 'llm_output_truncated'),
    (_reply(None, 'content_filter'), 'llm_response_refused'),
    (_reply('partial', refusal='private refusal'), 'llm_response_refused'),
    ({'choices': []}, 'llm_response_invalid'),
    (_reply([{'type': 'image_url', 'image_url': {'url': 'private'}}]), 'llm_response_invalid'),
    ({'error': {'message': 'private provider body'}}, 'llm_response_invalid'),
    ('<html>private proxy body</html>', 'llm_response_invalid'),
])
async def test_nonrecoverable_output_is_rejected_and_classified_without_blind_retry(monkeypatch, reply, expected):
    calls = _provider(monkeypatch, [reply, _reply('must not retry')])
    with pytest.raises(llm_client.LLMResponseError) as failure:
        await llm_client.request_llm_completion(CONFIG, 'system', 'user', max_retries=2)
    assert describe_llm_error(failure.value)[0] == expected
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_response_diagnostics_exclude_provider_text_keys_and_credentials(monkeypatch, caplog):
    reply = _reply(None, 'synthetic-secret', reasoning_content='private reasoning')
    reply['private field'] = CONFIG['key']
    _provider(monkeypatch, [reply])
    with caplog.at_level(logging.WARNING, logger='app.services.llm_client'):
        with pytest.raises(llm_client.LLMResponseError) as failure:
            await llm_client.request_llm_completion(CONFIG, 'private prompt', 'private input', max_retries=0)
    assert 'reason=' in caplog.text
    public = str(failure.value) + caplog.text + str(describe_llm_error(failure.value))
    for secret in ['private', CONFIG['key'], CONFIG['url']]:
        assert secret not in public


@pytest.mark.asyncio
@pytest.mark.parametrize('status, parts, expected', [
    ('incomplete', [{'type': 'output_text', 'text': 'partial'}], 'llm_output_truncated'),
    ('completed', [{'type': 'refusal', 'refusal': 'private refusal'}], 'llm_response_refused'),
    ('failed', [], 'llm_response_invalid'),
])
async def test_responses_terminal_status_never_publishes_partial_or_refused_output(monkeypatch, status, parts, expected):
    calls = _provider(monkeypatch, [{'status': status, 'output': [{'type': 'message', 'content': parts}]}])
    config = dict(CONFIG, url='https://example.test/v1/responses')
    with pytest.raises(llm_client.LLMResponseError) as failure:
        await llm_client.request_llm_completion(config, 'system', 'user', max_retries=0)
    assert describe_llm_error(failure.value)[0] == expected
    assert len(calls) == 1


@pytest.mark.asyncio
async def test_explicit_incomplete_sse_response_overrides_preceding_text(monkeypatch):
    client = httpx.AsyncClient
    events = [
        {'type': 'response.output_text.delta', 'delta': '{"partial":true}'},
        {'type': 'response.incomplete', 'response': {'output': []}},
    ]
    body = ''.join('data:' + json.dumps(event) + '\n\n' for event in events)
    transport = httpx.MockTransport(lambda request: httpx.Response(200, text=body, headers={'content-type': 'text/event-stream'}))
    monkeypatch.setattr(llm_client.httpx, 'AsyncClient', lambda **kwargs: client(transport=transport, **kwargs))
    with pytest.raises(llm_client.LLMResponseError) as failure:
        await llm_client.request_llm_completion(dict(CONFIG, url='https://example.test/v1/responses'), 'system', 'user', max_retries=0)
    assert describe_llm_error(failure.value)[0] == 'llm_output_truncated'


@pytest.mark.asyncio
@pytest.mark.parametrize('reply, expected', [
    ('data: {"type":"error","code":"server_error"}\n\n', 'llm_response_invalid'),
    ('data: {"type":"response.refusal.done","refusal":"private"}\n\n', 'llm_response_refused'),
    ('data: {"type":"response.output_text.delta","delta":"partial"}\n\n'
     'data: {"type":"response.failed"}\n\n', 'llm_response_invalid'),
    ('data: {"type":"response.output_text.delta","delta":"partial"}\n\n'
     'data: {"type":"response.incomplete","response":{"status":"completed","output":[]}}\n\n',
     'llm_output_truncated'),
    ('data: {"type":"unknown"}\n\n', 'llm_response_invalid'),
    ({'output': [{}]}, 'llm_response_invalid'),
    ({'output': [{'type': 'message', 'content': [{'type': 'unknown'}]}]}, 'llm_response_invalid'),
])
async def test_responses_errors_and_unknown_shapes_never_retry_as_empty(monkeypatch, reply, expected):
    calls = _provider(monkeypatch, [reply, {'output_text': 'must not retry'}])
    config = dict(CONFIG, url='https://example.test/v1/responses')
    with pytest.raises(llm_client.LLMResponseError) as failure:
        await llm_client.request_llm_completion(config, 'system', 'user', max_retries=2)
    assert describe_llm_error(failure.value)[0] == expected
    assert len(calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize('empty', [
    {'output': []},
    {'output': [{'type': 'message', 'content': []}]},
    'data: {"type":"response.output_text.done","text":""}\n\n',
])
async def test_recognized_empty_responses_still_recover_once(monkeypatch, empty):
    calls = _provider(monkeypatch, [empty, {'output_text': 'recovered'}])
    result = await llm_client.request_llm_completion(
        dict(CONFIG, url='https://example.test/v1/responses'), 'system', 'user', max_retries=2)
    assert result == 'recovered'
    assert len(calls) == 2


def test_connection_test_reports_empty_output_once_without_changing_settings(settings_client, monkeypatch):
    client, path = settings_client
    before = path.read_bytes()
    calls = _provider(monkeypatch, [_reply(None), _reply('pong')])
    response = client.post('/api/settings/test-connection', json={
        'api_url': CONFIG['url'], 'api_key': CONFIG['key'], 'model': CONFIG['model'],
    })
    assert response.status_code == 200
    assert response.json()['success'] is False
    assert response.json()['code'] == 'llm_empty_response'
    assert len(calls) == 1
    assert path.read_bytes() == before


def test_generation_failure_keeps_saved_guidance_and_answers_with_specific_reason(guidance_client, monkeypatch):
    from app.services import analysis_guidance_generation as generation
    client, sessions, _, _ = guidance_client
    _unlock(sessions)
    configuration = client.get('/api/projects/9/analysis-guidance').json()['configuration']
    saved = client.put('/api/projects/9/analysis-guidance', json={
        'expected_configuration_revision': 0, 'configuration': configuration,
    })
    assert saved.status_code == 200
    before = client.get('/api/projects/9/analysis-guidance').json()
    rows = _preserved_rows(sessions)
    async def configured_model():
        return dict(CONFIG)
    monkeypatch.setattr(generation, 'get_llm_config', configured_model)
    _provider(monkeypatch, [_reply(None)])
    response = client.post('/api/projects/9/analysis-guidance/generate')
    assert response.status_code == 503
    assert response.json()['detail']['code'] == 'analysis_model_empty_response'
    assert '已有回答会保留' in response.json()['detail']['message']
    assert client.get('/api/projects/9/analysis-guidance').json() == before
    assert _preserved_rows(sessions) == rows
