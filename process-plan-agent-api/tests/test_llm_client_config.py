import httpx
import pytest

from app.services import llm_client


def test_general_llm_request_timeout_remains_long_and_configurable(monkeypatch):
    monkeypatch.delenv("LLM_REQUEST_TIMEOUT_SECONDS", raising=False)
    assert llm_client.llm_request_timeout_seconds() == 180.0

    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "90")
    assert llm_client.llm_request_timeout_seconds() == 90.0


def test_general_llm_retry_count_keeps_two_retries(monkeypatch):
    monkeypatch.delenv("LLM_MAX_RETRIES", raising=False)
    assert llm_client.llm_max_retries() == 2

    monkeypatch.setenv("LLM_MAX_RETRIES", "0")
    assert llm_client.llm_max_retries() == 0


def test_request_specific_limits_override_general_defaults(monkeypatch):
    monkeypatch.setenv("LLM_REQUEST_TIMEOUT_SECONDS", "180")
    monkeypatch.setenv("LLM_MAX_RETRIES", "2")

    assert llm_client.llm_request_timeout_seconds(45) == 45.0
    assert llm_client.llm_max_retries(1) == 1


@pytest.mark.asyncio
async def test_request_llm_completion_retries_transient_503(monkeypatch):
    attempts = 0

    class FakeResponse:
        def __init__(self, status_code):
            self.status_code = status_code
            self.request = httpx.Request("POST", "https://example.test/v1/chat/completions")

        def raise_for_status(self):
            if self.status_code >= 400:
                raise httpx.HTTPStatusError("temporary outage", request=self.request, response=self)

        def json(self):
            return {"choices": [{"message": {"content": "ok"}}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            nonlocal attempts
            attempts += 1
            return FakeResponse(503 if attempts < 3 else 200)

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())
    monkeypatch.setattr(llm_client.asyncio, "sleep", lambda _seconds: _completed())

    result = await llm_client.request_llm_completion(
        {"url": "https://example.test/v1", "key": "secret", "model": "demo"},
        "system",
        "user",
    )

    assert result == "ok"
    assert attempts == 3


async def _completed():
    return None


@pytest.mark.asyncio
async def test_responses_endpoint_accepts_a_non_streaming_json_response(monkeypatch):
    """Some OpenAI-compatible Responses endpoints ignore stream=true and return JSON."""

    payload = {
        "output": [
            {
                "type": "message",
                "content": [{"type": "output_text", "text": "pong"}],
            }
        ]
    }

    class FakeResponse:
        def raise_for_status(self):
            return None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def aiter_lines(self):
            yield __import__("json").dumps(payload)

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        def stream(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    result = await llm_client.request_llm_completion(
        {"url": "https://example.test/v1/responses", "key": "secret", "model": "demo"},
        "system",
        "user",
        max_retries=0,
    )

    assert result == "pong"


@pytest.mark.asyncio
async def test_chat_completion_accepts_openai_content_parts(monkeypatch):
    """OpenAI-compatible gateways may return message content as text parts."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "content": [
                            {"type": "text", "text": "{\"pong\":"},
                            {"type": "text", "text": "true}"},
                        ],
                    },
                }],
            }

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    result = await llm_client.request_llm_completion(
        {"url": "https://example.test/v1", "key": "secret", "model": "demo"},
        "system",
        "user",
        max_retries=0,
    )

    assert result == '{"pong":true}'


@pytest.mark.asyncio
async def test_chat_completion_accepts_completion_text_fallback(monkeypatch):
    """Older OpenAI-compatible endpoints may expose choices.text instead of message.content."""

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"text": "pong"}]}

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    result = await llm_client.request_llm_completion(
        {"url": "https://example.test/v1", "key": "secret", "model": "demo"},
        "system",
        "user",
        max_retries=0,
    )

    assert result == "pong"


@pytest.mark.asyncio
@pytest.mark.parametrize("response_body", [
    {},
    {"choices": []},
    {"choices": [{"message": {"content": "   "}}]},
])
async def test_chat_completion_rejects_missing_or_empty_text(response_body, monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return response_body

    class FakeClient:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return False

        async def post(self, *_args, **_kwargs):
            return FakeResponse()

    monkeypatch.setattr(llm_client.httpx, "AsyncClient", lambda **_kwargs: FakeClient())

    with pytest.raises(ValueError, match="did not contain text"):
        await llm_client.request_llm_completion(
            {"url": "https://example.test/v1", "key": "secret", "model": "demo"},
            "system",
            "user",
            max_retries=0,
        )
