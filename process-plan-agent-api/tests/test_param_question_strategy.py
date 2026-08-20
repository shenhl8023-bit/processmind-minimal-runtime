from __future__ import annotations

import asyncio
import json
from pathlib import Path

import pytest

from app import main as main_module
from app.core.paths import PROJECT_ROOT
from app.services import param_question_strategy as strategy_module


def _valid_strategy_payload() -> dict[str, object]:
    return {
        "version": "test-1",
        "familyRules": [
            {"family": "other", "label": "当前工序", "patterns": []},
        ],
        "rootReasonPriority": {
            "other": ["coverage_reason::material"],
        },
        "terminalQuestionTypes": ["material_scope_select"],
    }


def test_loads_strategy_from_shared_delivery_file():
    payload = strategy_module.load_param_question_strategy(force=True)

    assert payload["version"] == "1.0.0"
    assert strategy_module.PARAM_QUESTION_STRATEGY_PATH == (
        PROJECT_ROOT / "docs" / "配置模板" / "第五步参数问答策略.json"
    )
    assert not (PROJECT_ROOT / "process-plan-agent-ui" / "src" / "config" / "paramQuestionStrategy.json").exists()


def test_explicit_strategy_path_can_be_injected_for_tests(tmp_path: Path):
    path = tmp_path / "strategy.json"
    payload = _valid_strategy_payload()
    path.write_text(json.dumps(payload), encoding="utf-8")

    assert strategy_module.load_param_question_strategy(path=path) == payload


def test_missing_strategy_file_raises_clear_error(tmp_path: Path):
    with pytest.raises(strategy_module.ParamQuestionStrategyError, match="不存在"):
        strategy_module.load_param_question_strategy(path=tmp_path / "missing.json")


def test_malformed_strategy_file_raises_clear_error(tmp_path: Path):
    path = tmp_path / "strategy.json"
    path.write_text("{invalid", encoding="utf-8")

    with pytest.raises(strategy_module.ParamQuestionStrategyError, match="无法解析 JSON"):
        strategy_module.load_param_question_strategy(path=path)


def test_invalid_strategy_shape_raises_clear_error(tmp_path: Path):
    path = tmp_path / "strategy.json"
    path.write_text(json.dumps({"version": "test-1"}), encoding="utf-8")

    with pytest.raises(strategy_module.ParamQuestionStrategyError, match="familyRules"):
        strategy_module.load_param_question_strategy(path=path)


def test_invalid_strategy_aborts_startup_before_database_initialization(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(
        strategy_module,
        "PARAM_QUESTION_STRATEGY_PATH",
        tmp_path / "missing-startup-strategy.json",
    )

    def fail_if_database_initializes():
        raise AssertionError("database initialization must happen after strategy validation")

    monkeypatch.setattr(main_module, "init_db", fail_if_database_initializes)

    async def run_lifespan():
        async with main_module.app.router.lifespan_context(main_module.app):
            pass

    with pytest.raises(strategy_module.ParamQuestionStrategyError, match="不存在"):
        asyncio.run(run_lifespan())
