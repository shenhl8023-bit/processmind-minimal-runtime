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
