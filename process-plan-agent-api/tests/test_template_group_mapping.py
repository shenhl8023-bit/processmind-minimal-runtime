import json

import pytest

from app.schemas.schemas import (
    TemplateGroupMappingCandidateIn,
    TemplateGroupMappingOperationIn,
    TemplateGroupMappingSuggestRequest,
)
from app.services import template_group_mapping


def request_for_hole() -> TemplateGroupMappingSuggestRequest:
    return TemplateGroupMappingSuggestRequest(
        project_id=7,
        operations=[
            TemplateGroupMappingOperationIn(
                operation_id=360,
                operation_name="打孔",
                step_items=["在A侧钻安装孔"],
                rule_evidence=["孔"],
                rule_reasons=["加工特征明确，但加工位置仍需确认。"],
                candidates=[
                    TemplateGroupMappingCandidateIn(group_id="a-hole", path=["A侧", "孔"], score=0.72),
                    TemplateGroupMappingCandidateIn(group_id="b-hole", path=["B侧", "孔"], score=0.72),
                    TemplateGroupMappingCandidateIn(group_id="peripheral-hole", path=["周边", "孔"], score=0.72),
                ],
            )
        ],
    )


@pytest.mark.asyncio
async def test_accepts_a_model_choice_only_from_the_supplied_candidates(monkeypatch):
    async def valid_llm(*args, **kwargs):
        return json.dumps({
            "suggestions": [{
                "operation_id": 360,
                "group_id": "a-hole",
                "confidence": 0.93,
                "evidence": ["在A侧钻安装孔"],
                "reason": "工步明确说明在A侧加工孔。",
            }]
        }, ensure_ascii=False)

    monkeypatch.setattr(template_group_mapping, "call_llm", valid_llm)
    result = await template_group_mapping.resolve_template_group_mappings(request_for_hole())

    assert result.model_used is True
    assert result.suggestions[0].group_id == "a-hole"
    assert result.suggestions[0].confidence == 0.93
    assert result.suggestions[0].source == "llm"
    assert result.suggestions[0].evidence == ["在A侧钻安装孔"]


@pytest.mark.asyncio
async def test_rejects_a_model_group_id_that_was_not_a_candidate(monkeypatch):
    async def invalid_group_llm(*args, **kwargs):
        return '{"suggestions":[{"operation_id":360,"group_id":"outer-diameter","confidence":0.99}]}'

    monkeypatch.setattr(template_group_mapping, "call_llm", invalid_group_llm)
    result = await template_group_mapping.resolve_template_group_mappings(request_for_hole())

    assert result.suggestions[0].group_id is None
    assert result.suggestions[0].source == "unresolved"
    assert any("候选范围" in warning for warning in result.suggestions[0].warnings)


@pytest.mark.asyncio
async def test_keeps_a_low_confidence_model_choice_unresolved(monkeypatch):
    async def low_confidence_llm(*args, **kwargs):
        return '{"suggestions":[{"operation_id":360,"group_id":"a-hole","confidence":0.42,"reason":"位置不清楚"}]}'

    monkeypatch.setattr(template_group_mapping, "call_llm", low_confidence_llm)
    result = await template_group_mapping.resolve_template_group_mappings(request_for_hole())

    assert result.suggestions[0].group_id is None
    assert result.suggestions[0].confidence == 0.42
    assert result.suggestions[0].source == "unresolved"


@pytest.mark.asyncio
async def test_returns_rule_candidates_when_the_model_is_unavailable(monkeypatch):
    async def empty_llm(*args, **kwargs):
        return ""

    monkeypatch.setattr(template_group_mapping, "call_llm", empty_llm)
    result = await template_group_mapping.resolve_template_group_mappings(request_for_hole())

    assert result.model_used is False
    assert result.suggestions[0].group_id is None
    assert result.suggestions[0].source == "unresolved"
    assert result.suggestions[0].candidate_group_ids == ["a-hole", "b-hole", "peripheral-hole"]


@pytest.mark.asyncio
async def test_discards_model_evidence_that_is_not_present_in_the_source(monkeypatch):
    async def hallucinated_evidence_llm(*args, **kwargs):
        return json.dumps({
            "suggestions": [{
                "operation_id": 360,
                "group_id": "a-hole",
                "confidence": 0.95,
                "evidence": ["图纸明确标注A侧"],
                "reason": "选择A侧孔。",
            }]
        }, ensure_ascii=False)

    monkeypatch.setattr(template_group_mapping, "call_llm", hallucinated_evidence_llm)
    result = await template_group_mapping.resolve_template_group_mappings(request_for_hole())

    assert result.suggestions[0].evidence == ["孔"]
    assert any("证据" in warning for warning in result.suggestions[0].warnings)
