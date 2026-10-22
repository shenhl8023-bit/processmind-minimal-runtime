"""Validated structured drafts passed from step 3 analysis to step 4 rules."""

from __future__ import annotations

from typing import Literal

from pydantic import Field

from app.services.rule_packages.condition_contracts import (
    RuleConditionCandidate,
    RuleConditionProcessOption,
    StrictModel,
)
from app.services.rule_packages.condition_parser import validate_candidate


class RuleDraftProvenance(StrictModel):
    kind: Literal["document", "user", "knowledge", "model"]
    label: str
    evidence: str = ""


class AnalysisRuleDraft(StrictModel):
    scope: str = ""
    object: str = ""
    condition_text: str = ""
    candidate: RuleConditionCandidate | None = None
    missing: list[str] = Field(default_factory=list)
    provenance: list[RuleDraftProvenance] = Field(default_factory=list)
    status: Literal["incomplete", "ready", "confirmed"] = "incomplete"


def validate_rule_draft(
    draft: AnalysisRuleDraft,
    processes: list[RuleConditionProcessOption],
    current_process_id: str,
    *,
    require_confirmation: bool = False,
) -> list[str]:
    issues = list(draft.missing)
    if not draft.scope.strip():
        issues.append("请确认规则适用范围。")
    if not draft.object.strip():
        issues.append("请确认规则对应的加工对象。")
    if not draft.condition_text.strip() and draft.candidate is None:
        issues.append("请补充工序保留条件。")
    if draft.candidate is not None:
        issues.extend(validate_candidate(draft.candidate, processes, current_process_id=current_process_id))
    if require_confirmation and draft.status != "confirmed":
        issues.append("第三步规则草稿尚未由用户确认。")
    if require_confirmation and draft.status == "confirmed" and draft.missing:
        issues.append("仍有未补充的信息，不能确认规则。")
    return list(dict.fromkeys(issues))


def build_rule_draft_source_text(draft: AnalysisRuleDraft) -> str:
    parts = []
    if draft.scope.strip():
        parts.append(f"适用范围：{draft.scope.strip()}。")
    if draft.object.strip():
        parts.append(f"加工对象：{draft.object.strip()}。")
    if draft.condition_text.strip():
        parts.append(draft.condition_text.strip())
    elif draft.candidate is not None and draft.candidate.preview.strip():
        parts.append(draft.candidate.preview.strip())
    return "".join(parts)
