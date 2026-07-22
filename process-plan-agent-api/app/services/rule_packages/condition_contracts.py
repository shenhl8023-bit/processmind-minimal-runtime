"""Contracts for turning reviewed natural-language conditions into V2 rules."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import Field, model_validator

from app.services.rule_packages.contracts import ConditionNode, ProcessRelationType, RuleAction, StrictModel


class CanonicalConditionField(StrictModel):
    key: str
    label: str
    category: str
    type: Literal["string", "number", "boolean", "single_select", "multi_select"]
    operators: list[str]
    aliases: list[str] = Field(default_factory=list)
    unit: str | None = None
    required: bool = False
    source: str = ""
    options: list[dict[str, Any]] = Field(default_factory=list)
    allow_custom: bool = True
    validation: dict[str, Any] | None = None


class RuleConditionProcessOption(StrictModel):
    process_id: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    main: bool = False


class ProcessRelationCandidate(StrictModel):
    relation_type: ProcessRelationType
    source_process_ids: list[str] = Field(min_length=1)
    target_process_ids: list[str] = Field(min_length=1)
    source_match: Literal["any", "all"] = "any"


class RuleConditionCandidate(StrictModel):
    kind: Literal["condition", "process_relation"] = "condition"
    when: ConditionNode | None = None
    then: RuleAction | None = None
    relation: ProcessRelationCandidate | None = None
    field_definitions: list[CanonicalConditionField] = Field(default_factory=list)
    preview: str = ""

    @model_validator(mode="after")
    def validate_candidate_kind(self):
        if self.kind == "condition":
            if self.when is None or self.then is None or self.relation is not None:
                raise ValueError("condition candidate requires when/then only")
        elif self.relation is None or self.when is not None or self.then is not None or self.field_definitions:
            raise ValueError("process_relation candidate requires relation only")
        return self


class SaveRuleConditionDraftRequest(StrictModel):
    project_id: int = Field(gt=0)
    route_id: int = Field(gt=0)
    segment_id: str = Field(min_length=1)
    source_text: str = ""


class ParseRuleConditionRequest(SaveRuleConditionDraftRequest):
    process_id: str = Field(min_length=1)
    process_name: str = Field(min_length=1)
    processes: list[RuleConditionProcessOption]


class ConfirmRuleConditionRequest(SaveRuleConditionDraftRequest):
    source_hash: str = Field(min_length=64, max_length=64)
    candidate: RuleConditionCandidate
    processes: list[RuleConditionProcessOption]
    confirmed_by: str = "默认用户"


class RuleConditionReview(StrictModel):
    source_text: str = ""
    source_hash: str = ""
    status: Literal["draft", "parsing", "pending_confirmation", "confirmed", "invalid"] = "draft"
    candidate: RuleConditionCandidate | None = None
    confirmed: RuleConditionCandidate | None = None
    confidence: float | None = None
    issues: list[str] = Field(default_factory=list)
    field_registry_version: str = ""
    confirmed_by: str = ""
    confirmed_at: str = ""


class RuleConditionReviewResponse(StrictModel):
    project_id: int
    route_id: int
    segment_id: str
    review: RuleConditionReview


class ConditionFieldRegistryResponse(StrictModel):
    version: str
    fields: list[CanonicalConditionField]
