import pytest

from app.services.worker_mode import (
    MultiWorkerConfiguredError,
    check_single_worker,
    single_worker_enabled,
)


def test_single_worker_is_enabled_by_default(monkeypatch):
    monkeypatch.delenv("PROCESSMIND_SINGLE_WORKER", raising=False)

    assert single_worker_enabled() is True


def test_single_worker_check_rejects_any_multi_worker_environment(monkeypatch):
    monkeypatch.delenv("PROCESSMIND_SINGLE_WORKER", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "1")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")

    with pytest.raises(MultiWorkerConfiguredError, match="worker 数=4"):
        check_single_worker()


def test_single_worker_check_rejects_multi_worker_after_invalid_value(monkeypatch):
    monkeypatch.delenv("PROCESSMIND_SINGLE_WORKER", raising=False)
    monkeypatch.setenv("UVICORN_WORKERS", "invalid")
    monkeypatch.setenv("WEB_CONCURRENCY", "3")

    with pytest.raises(MultiWorkerConfiguredError, match="worker 数=3"):
        check_single_worker()


def test_explicit_multi_worker_acknowledgement_bypasses_guard(monkeypatch):
    monkeypatch.setenv("PROCESSMIND_SINGLE_WORKER", "false")
    monkeypatch.setenv("WEB_CONCURRENCY", "4")

    check_single_worker()
    assert single_worker_enabled() is False
