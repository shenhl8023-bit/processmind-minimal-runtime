import httpx
from fastapi.testclient import TestClient

from app.main import app
from app.services import settings_store


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
