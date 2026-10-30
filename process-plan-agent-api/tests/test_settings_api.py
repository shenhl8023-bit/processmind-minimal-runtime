import httpx
import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.services import settings_store
from app.routers import settings as settings_router


def test_test_connection_uses_shared_llm_request_and_does_not_save_form(monkeypatch, tmp_path):
    settings_path = tmp_path / "process_settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", settings_path)
    calls = []

    async def fake_request(config, system_prompt, user_prompt, **kwargs):
        calls.append((config, system_prompt, user_prompt, kwargs))
        return "pong"

    monkeypatch.setattr("app.routers.settings.request_llm_completion", fake_request)

    with TestClient(app) as client:
        response = client.post(
            "/api/settings/test-connection",
            json={
                "api_url": "https://example.test/v1",
                "api_key": "new-secret",
                "model": "demo-model",
            },
        )

    assert response.status_code == 200
    assert response.json() == {"success": True, "message": "连接成功，模型可用"}
    assert calls[0][0] == {
        "url": "https://example.test/v1/chat/completions",
        "key": "new-secret",
        "model": "demo-model",
    }
    assert not settings_path.exists()


def test_test_connection_maps_transient_provider_error(monkeypatch):
    request = httpx.Request("POST", "https://example.test/v1/chat/completions")
    response = httpx.Response(503, request=request)

    async def fail_request(*_args, **_kwargs):
        raise httpx.HTTPStatusError("503 Service Unavailable", request=request, response=response)

    monkeypatch.setattr("app.routers.settings.request_llm_completion", fail_request)

    with TestClient(app) as client:
        result = client.post(
            "/api/settings/test-connection",
            json={"api_url": "https://example.test/v1", "api_key": "secret", "model": "demo"},
        )

    assert result.status_code == 200
    assert result.json() == {
        "success": False,
        "message": "模型服务暂时不可用，请稍后重试。",
    }


def test_clear_secret_setting_removes_saved_key(monkeypatch, tmp_path):
    settings_path = tmp_path / "process_settings.json"
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", settings_path)

    with TestClient(app) as client:
        saved = client.post("/api/settings", json={"key": "LLM_API_KEY", "value": "secret"})
        cleared = client.delete("/api/settings/LLM_API_KEY")

    assert saved.status_code == 200
    assert cleared.status_code == 200
    assert cleared.json()["is_configured"] is False
    assert settings_store.get_llm_settings_map()["LLM_API_KEY"] == ""


@pytest.mark.parametrize("url", ["provider.test/v1", "ftp://provider.test/v1", "https://", "https://bad host/v1", "https://provider.test:bad/v1"])
def test_invalid_provider_url_is_rejected_before_connection(monkeypatch, url):
    async def unreachable_request(*_args, **_kwargs):
        return "pong"

    monkeypatch.setattr(settings_router, "request_llm_completion", unreachable_request)
    with TestClient(app) as client:
        response = client.post("/api/settings/test-connection", json={
            "api_url": url, "api_key": "fake-test-key", "model": "demo",
        })
    assert response.status_code == 400, response.text


@pytest.mark.parametrize("key", ["LLM_API_URL", "KNOWLEDGE_SEARCH_API_URL"])
def test_invalid_provider_url_cannot_replace_saved_setting(monkeypatch, tmp_path, key):
    monkeypatch.setattr(settings_store, "SETTINGS_FILE_PATH", tmp_path / "settings.json")
    before = settings_store.get_llm_settings_map()[key]
    with TestClient(app) as client:
        response = client.post("/api/settings", json={"key": key, "value": "ftp://provider.test"})
    assert response.status_code == 400, response.text
    assert settings_store.get_llm_settings_map()[key] == before


@pytest.mark.parametrize("payload", [[], None, {"data": None}, {"data": {}}, {"data": [None]}, {"data": ["bad-model"]}, {"data": [{"id": ["bad"]}]}])
def test_models_rejects_malformed_provider_response_with_controlled_error(monkeypatch, payload):
    monkeypatch.setattr(settings_router, "get_llm_settings_map", lambda: {
        "LLM_API_URL": "https://provider.test/v1", "LLM_API_KEY": "fake-test-key",
    })
    transport = httpx.MockTransport(lambda request: httpx.Response(200, json=payload, request=request))
    original_client = httpx.AsyncClient
    monkeypatch.setattr(settings_router.httpx, "AsyncClient", lambda **kwargs: original_client(transport=transport, **kwargs))
    with TestClient(app, raise_server_exceptions=False) as client:
        response = client.get("/api/settings/models")
    assert response.status_code == 502, response.text
    assert isinstance(response.json()["detail"], str)


def test_models_returns_sorted_unique_provider_identifiers(monkeypatch):
    monkeypatch.setattr(settings_router, "get_llm_settings_map", lambda: {
        "LLM_API_URL": "https://provider.test/v1/responses", "LLM_API_KEY": "fake-test-key",
    })
    def respond(request):
        assert str(request.url) == "https://provider.test/v1/models"
        return httpx.Response(200, json={"data": [{"id": "z"}, {"id": "a"}, {"id": "z"}]}, request=request)
    original_client = httpx.AsyncClient
    monkeypatch.setattr(settings_router.httpx, "AsyncClient", lambda **kwargs: original_client(transport=httpx.MockTransport(respond), **kwargs))
    with TestClient(app) as client:
        response = client.get("/api/settings/models")
    assert response.status_code == 200
    assert response.json() == [{"id": "a", "name": "a"}, {"id": "z", "name": "z"}]
