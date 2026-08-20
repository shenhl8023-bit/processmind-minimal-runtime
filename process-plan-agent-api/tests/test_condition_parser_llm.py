import json

import pytest

from app.services.rule_packages import condition_parser_llm
from app.services.rule_packages.condition_contracts import RuleConditionProcessOption


@pytest.mark.asyncio
async def test_llm_boundary_passes_rule_specific_timeout_and_returns_candidate(monkeypatch):
    captured = {}

    async def fake_llm(*args, **kwargs):
        captured["args"] = args
        captured.update(kwargs)
        return json.dumps(
            {
                "candidate": {
                    "kind": "condition",
                    "when": {"field": "material.grade", "op": "eq", "value": "9Cr18"},
                    "then": {
                        "include_process_ids": ["process_inspect"],
                        "exclude_process_ids": [],
                    },
                },
                "confidence": 0.88,
                "warnings": [],
                "unresolved": [],
            }
        )

    monkeypatch.setattr(condition_parser_llm, "call_llm", fake_llm)
    candidate, confidence, issues = await condition_parser_llm.parse_with_llm(
        "complex condition",
        "process_inspect",
        "inspect",
        [
            RuleConditionProcessOption(
                process_id="process_inspect",
                display_name="inspect",
            )
        ],
    )

    assert candidate is not None
    assert candidate.when.field == "material.grade"
    assert confidence == 0.88
    assert issues == []
    assert captured["timeout_seconds"] == 45.0
    assert captured["max_retries"] == 1
    user_prompt = json.loads(captured["args"][1])
    assert "allowed_standard_factors" in user_prompt
    assert any(item["factor_id"] == "feature.standard_or_aux_hole" for item in user_prompt["allowed_standard_factors"])
    assert "伞形" in captured["args"][0]
