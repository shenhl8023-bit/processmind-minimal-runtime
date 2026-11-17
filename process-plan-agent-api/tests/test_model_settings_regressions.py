"""PM-038: exercise settings transactions and provider boundaries without user data."""
import asyncio
import ssl

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.routers import settings as settings_router
from app.schemas.schemas import LLMTestRequest
from app.services import llm_client, settings_store


@pytest.fixture
def settings_client(tmp_path, monkeypatch):
    path = tmp_path / 'config' / 'settings.json'
    monkeypatch.setattr(settings_store, 'SETTINGS_FILE_PATH', path)
    for key, value in [
        ('LLM_API_URL', 'https://saved.example.test/v1'),
        ('LLM_MODEL', 'saved-model'), ('LLM_API_KEY', 'synthetic-saved-key'),
        ('KNOWLEDGE_SEARCH_API_KEY', 'synthetic-other-key'),
    ]:
        settings_store.update_setting_value(key, value)
    app = FastAPI()
    app.include_router(settings_router.router)
    with TestClient(app) as client:
        yield client, path


def test_model_settings_save_all_fields_and_mask_secrets(settings_client):
    client, _ = settings_client
    response = client.post('/api/settings/llm', json={
        'api_url': ' https://draft.example.test/v1 ',
        'model': ' draft-model ', 'api_key': ' synthetic-new-key ',
    })
    assert response.status_code == 200, response.text
    saved = settings_store.get_llm_settings_map()
    assert saved['LLM_API_URL'] == 'https://draft.example.test/v1'
    assert saved['LLM_MODEL'] == 'draft-model'
    assert saved['LLM_API_KEY'] == 'synthetic-new-key'
    assert saved['KNOWLEDGE_SEARCH_API_KEY'] == 'synthetic-other-key'
    public = {row['key']: row for row in response.json()}
    assert public['LLM_API_KEY']['value'] == ''
    assert public['LLM_API_KEY']['is_configured'] is True
    assert 'synthetic-new-key' not in response.text
    assert 'synthetic-other-key' not in response.text


@pytest.mark.parametrize('key_value', [None, '', '   '])
def test_model_settings_empty_key_keeps_saved_key(settings_client, key_value):
    client, _ = settings_client
    body = {'api_url': 'https://draft.example.test/v1', 'model': 'draft-model'}
    if key_value is not None:
        body['api_key'] = key_value
    response = client.post('/api/settings/llm', json=body)
    assert response.status_code == 200, response.text
    saved = settings_store.get_llm_settings_map()
    assert saved['LLM_API_KEY'] == 'synthetic-saved-key'
    assert saved['LLM_MODEL'] == 'draft-model'


@pytest.mark.parametrize('changes', [
    {'api_url': 'ftp://bad.example.test'}, {'model': '  '},
    {'api_key': '__use_saved__'},
])
def test_model_settings_validation_keeps_whole_previous_config(settings_client, changes):
    client, path = settings_client
    before = path.read_bytes()
    body = {'api_url': 'https://draft.example.test/v1', 'model': 'draft-model', 'api_key': 'synthetic-new-key'}
    body.update(changes)
    response = client.post('/api/settings/llm', json=body)
    assert response.status_code == 400, response.text
    assert path.read_bytes() == before


def test_model_settings_without_saved_or_input_key_is_rejected(settings_client):
    client, path = settings_client
    settings_store.clear_setting_value('LLM_API_KEY')
    before = path.read_bytes()
    response = client.post('/api/settings/llm', json={
        'api_url': 'https://draft.example.test/v1', 'model': 'draft-model',
    })
    assert response.status_code == 400, response.text
    assert path.read_bytes() == before


def test_atomic_model_save_failure_retains_all_old_fields(settings_client, monkeypatch):
    client, path = settings_client
    before = path.read_bytes()
    def fail_replace(*_args):
        raise OSError('synthetic disk failure')
    monkeypatch.setattr(settings_store.os, 'replace', fail_replace)
    response = client.post('/api/settings/llm', json={
        'api_url': 'https://draft.example.test/v1', 'model': 'draft-model', 'api_key': 'synthetic-new-key',
    })
    assert response.status_code == 500, response.text
    assert path.read_bytes() == before
    assert list(path.parent.glob('*.tmp')) == []
    assert 'synthetic-new-key' not in response.text


def _mock_provider(monkeypatch, respond):
    real_client = httpx.AsyncClient
    transport = httpx.MockTransport(respond)
    monkeypatch.setattr(settings_router.httpx, 'AsyncClient',
        lambda **kwargs: real_client(transport=transport, **kwargs))


@pytest.mark.parametrize('use_saved_key', [False, True])
def test_model_list_uses_draft_url_and_requested_key_without_saving(settings_client, monkeypatch, use_saved_key):
    client, path = settings_client
    before = path.read_bytes()
    def provider(request):
        assert str(request.url) == 'https://draft.example.test/v1/models'
        expected = 'synthetic-saved-key' if use_saved_key else 'synthetic-draft-key'
        assert request.headers['Authorization'] == 'Bearer ' + expected
        return httpx.Response(200, json={'data': [{'id': 'draft-model'}]})
    _mock_provider(monkeypatch, provider)
    response = client.post('/api/settings/models', json={
        'api_url': 'https://draft.example.test/v1',
        'api_key': '__use_saved__' if use_saved_key else 'synthetic-draft-key',
    })
    assert response.status_code == 200, response.text
    assert response.json() == [{'id': 'draft-model', 'name': 'draft-model'}]
    assert path.read_bytes() == before


def test_connection_test_tries_only_once_on_connect_failure(settings_client, monkeypatch):
    client, _ = settings_client
    attempts = []
    def provider(request):
        attempts.append(request)
        raise httpx.ConnectError('synthetic-secret-in-error', request=request)
    async def no_wait(_seconds):
        pass
    _mock_provider(monkeypatch, provider)
    monkeypatch.setenv('LLM_MAX_RETRIES', '2')
    monkeypatch.setattr(llm_client.asyncio, 'sleep', no_wait)
    response = client.post('/api/settings/test-connection', json={
        'api_url': 'https://draft.example.test/v1', 'model': 'draft-model', 'api_key': 'synthetic-key',
    })
    assert response.status_code == 200
    assert len(attempts) == 1
    assert response.json()['success'] is False
    assert response.json()['code'] == 'llm_connect_failed'
    assert 'synthetic-secret-in-error' not in response.text


def _tls_error():
    error = httpx.ConnectError('synthetic-secret-in-error')
    error.__cause__ = ssl.SSLEOFError('synthetic TLS closed')
    return error


def test_connection_test_explains_tls_failure_without_provider_secrets(settings_client, monkeypatch):
    client, _ = settings_client
    async def model(*_args, **_kwargs):
        raise _tls_error()
    monkeypatch.setattr(settings_router, 'request_llm_completion', model)
    response = client.post('/api/settings/test-connection', json={
        'api_url': 'https://draft.example.test/v1', 'model': 'draft-model', 'api_key': 'synthetic-key',
    })
    assert response.json()['code'] == 'llm_tls_failed'
    assert 'HTTPS' in response.json()['message']
    assert 'synthetic-' not in response.text


@pytest.mark.asyncio
async def test_interactive_connection_test_has_a_whole_request_deadline(monkeypatch):
    async def slow_model(*_args, **_kwargs):
        await asyncio.sleep(1)
        return 'pong'
    monkeypatch.setattr(settings_router, 'request_llm_completion', slow_model)
    monkeypatch.setattr(settings_router, 'LLM_TEST_TIMEOUT_SECONDS', 0.01, raising=False)
    payload = LLMTestRequest(api_url='https://draft.example.test/v1', api_key='synthetic', model='demo')
    try:
        result = await asyncio.wait_for(settings_router.test_llm_connection(payload), timeout=0.2)
    except asyncio.TimeoutError:
        pytest.fail('connection test did not enforce its own whole-request deadline')
    assert result.success is False
    assert result.code == 'llm_timeout'


@pytest.mark.asyncio
async def test_shared_client_does_not_retry_established_tls_failure(monkeypatch):
    attempts = []
    waits = []
    def provider(request):
        attempts.append(request)
        raise _tls_error()
    async def no_wait(seconds):
        waits.append(seconds)
    _mock_provider(monkeypatch, provider)
    monkeypatch.setattr(llm_client.asyncio, 'sleep', no_wait)
    with pytest.raises(httpx.ConnectError):
        await llm_client.request_llm_completion(
            {'url': 'https://draft.example.test/v1/chat/completions', 'key': 'synthetic', 'model': 'demo'},
            'system', 'user', max_retries=2,
        )
    assert len(attempts) == 1
    assert waits == []


@pytest.mark.parametrize('status, code', [(401, 'llm_auth_failed'), (429, 'llm_rate_limited'), (503, 'llm_service_unavailable')])
def test_model_list_failure_is_classified_and_sanitized(settings_client, monkeypatch, status, code):
    client, _ = settings_client
    def provider(request):
        return httpx.Response(status, json={'error': 'synthetic-provider-secret'}, request=request)
    _mock_provider(monkeypatch, provider)
    response = client.post('/api/settings/models', json={
        'api_url': 'https://draft.example.test/v1', 'api_key': 'synthetic-key',
    })
    assert response.status_code == 502
    assert response.json()['detail']['code'] == code
    assert 'synthetic-provider-secret' not in response.text
