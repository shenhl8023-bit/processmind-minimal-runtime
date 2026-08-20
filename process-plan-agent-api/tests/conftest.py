import json
import os
from pathlib import Path
import sys
import tempfile

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

# Pytest must never inherit the repository's persistent runtime data paths.
# Set these before importing any app module because app.core.paths and
# app.database resolve their paths and engine once at import time.
_TEST_DATA_ROOT = tempfile.TemporaryDirectory(prefix="processmind-pytest-")
_TEST_DATA_DIR = Path(_TEST_DATA_ROOT.name)
os.environ["PROCESSMIND_DATA_DIR"] = str(_TEST_DATA_DIR)
os.environ["PROCESSMIND_DB_PATH"] = str(_TEST_DATA_DIR / "db" / "process_mind.db")
os.environ["PROCESSMIND_UPLOAD_DIR"] = str(_TEST_DATA_DIR / "uploads")
os.environ["PROCESSMIND_SETTINGS_PATH"] = str(_TEST_DATA_DIR / "config" / "process_settings.json")

from app.services.rule_packages.contracts import RulePackageV2


FIXTURE_DIR = Path(__file__).parent / "fixtures"


def pytest_unconfigure(config):
    del config
    _TEST_DATA_ROOT.cleanup()


@pytest.fixture
def rule_package_v2_payload():
    return json.loads((FIXTURE_DIR / "rule_package_v2.json").read_text(encoding="utf-8"))


@pytest.fixture
def rule_package_v2(rule_package_v2_payload):
    return RulePackageV2.model_validate(rule_package_v2_payload)
