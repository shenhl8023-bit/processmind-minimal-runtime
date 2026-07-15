import json
from pathlib import Path
import sys

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_ROOT))

from app.services.rule_packages.contracts import RulePackageV2


FIXTURE_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def rule_package_v2_payload():
    return json.loads((FIXTURE_DIR / "rule_package_v2.json").read_text(encoding="utf-8"))


@pytest.fixture
def rule_package_v2(rule_package_v2_payload):
    return RulePackageV2.model_validate(rule_package_v2_payload)
