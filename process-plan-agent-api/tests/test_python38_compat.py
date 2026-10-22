import importlib.util
from pathlib import Path
import sys

import pytest

from app.core.compat import remove_suffix, run_in_thread


REPO_ROOT = Path(__file__).resolve().parents[2]
APP_ROOT = REPO_ROOT / "process-plan-agent-api" / "app"
VALIDATOR_PATH = REPO_ROOT / "scripts" / "validate-python38.py"


def _load_validator():
    spec = importlib.util.spec_from_file_location("processmind_python38_validator", VALIDATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_remove_suffix_matches_only_a_real_suffix():
    assert remove_suffix("粗加工阶段", "加工阶段") == "粗"
    assert remove_suffix("粗加工", "加工阶段") == "粗加工"


@pytest.mark.asyncio
async def test_run_in_thread_executes_blocking_callable_with_args():
    result = await run_in_thread(lambda left, right: left + right, 20, right=22)
    assert result == 42


def test_python38_validator_covers_backend_and_reports_no_forbidden_apis():
    validator = _load_validator()
    issues = validator.validate_tree(APP_ROOT)

    assert validator.count_python_files(APP_ROOT) == len(list(APP_ROOT.rglob("*.py")))
    assert issues == []


