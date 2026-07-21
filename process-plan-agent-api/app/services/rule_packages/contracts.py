"""Strict Pydantic contracts for the executable rule package V2 format."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class InputOption(StrictModel):
    value: str
    label: str
    aliases: list[str] = Field(default_factory=list)


class InputValidation(StrictModel):
    min: float | None = None
    max: float | None = None
    min_length: int | None = None
    max_length: int | None = None

    @model_validator(mode="after")
    def validate_ranges(self):
        if self.min is not None and self.max is not None and self.min > self.max:
            raise ValueError("validation.min cannot be greater than validation.max")
        if self.min_length is not None and self.max_length is not None and self.min_length > self.max_length:
            raise ValueError("validation.min_length cannot be greater than validation.max_length")
        return self


class InputField(StrictModel):
    key: str = Field(min_length=1)
    label: str = Field(min_length=1)
    type: Literal["string", "number", "boolean", "single_select", "multi_select"]
    required: bool = False
    source: str = ""
    options: list[InputOption] = Field(default_factory=list)
    allow_custom: bool = False
    unit: str | None = None
    validation: InputValidation | None = None


class InputSchemaV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    fields: list[InputField]


class ProcessStepV2(StrictModel):
    step_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    kind: Literal["primary", "attached"] = "primary"


class ProcessConstraints(StrictModel):
    requires: list[str] = Field(default_factory=list)
    must_run_after: list[str] = Field(default_factory=list)
    must_run_before: list[str] = Field(default_factory=list)
    conflicts_with: list[str] = Field(default_factory=list)


class ProcessV2(StrictModel):
    process_id: str = Field(min_length=1)
    process_code: str = ""
    display_name: str = Field(min_length=1)
    phase: str = ""
    default_sequence: int = Field(default=0, ge=0)
    main: bool = False
    steps: list[ProcessStepV2] = Field(default_factory=list)
    constraints: ProcessConstraints = Field(default_factory=ProcessConstraints)


class RouteCatalogV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    processes: list[ProcessV2]


ConditionOperator = Literal[
    "eq",
    "neq",
    "in",
    "contains",
    "contains_any",
    "contains_all",
    "gt",
    "gte",
    "lt",
    "lte",
    "between",
    "exists",
    "not_exists",
]


class ConditionNode(StrictModel):
    all_conditions: list[ConditionNode] | None = Field(default=None, alias="all")
    any_conditions: list[ConditionNode] | None = Field(default=None, alias="any")
    not_condition: ConditionNode | None = Field(default=None, alias="not")
    field: str | None = None
    op: ConditionOperator | None = None
    value: Any = None

    @model_validator(mode="after")
    def validate_shape(self):
        branches = [
            self.all_conditions is not None,
            self.any_conditions is not None,
            self.not_condition is not None,
            self.field is not None or self.op is not None,
        ]
        if sum(branches) != 1:
            raise ValueError("condition must contain exactly one of all, any, not, or field/op")
        if self.all_conditions is not None and not self.all_conditions:
            raise ValueError("all must contain at least one condition")
        if self.any_conditions is not None and not self.any_conditions:
            raise ValueError("any must contain at least one condition")
        if self.field is not None or self.op is not None:
            if not self.field or not self.op:
                raise ValueError("leaf condition requires both field and op")
            if self.op not in {"exists", "not_exists"} and self.value is None:
                raise ValueError(f"operator {self.op} requires value")
            if self.op == "between" and (not isinstance(self.value, list) or len(self.value) != 2):
                raise ValueError("between requires a two-item list value")
            if self.op in {"in", "contains_any", "contains_all"} and not isinstance(self.value, list):
                raise ValueError(f"operator {self.op} requires a list value")
        return self


class RuleAction(StrictModel):
    include_process_ids: list[str] = Field(default_factory=list)
    exclude_process_ids: list[str] = Field(default_factory=list)
    reason: str = ""

    @model_validator(mode="after")
    def validate_action(self):
        if not self.include_process_ids and not self.exclude_process_ids:
            raise ValueError("rule action must include or exclude at least one process")
        overlap = set(self.include_process_ids) & set(self.exclude_process_ids)
        if overlap:
            raise ValueError(f"rule action both includes and excludes: {', '.join(sorted(overlap))}")
        return self


class RuleV2(StrictModel):
    rule_id: str = Field(min_length=1)
    priority: int = 0
    enabled: bool = True
    when: ConditionNode
    then: RuleAction


class RouteRulesV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    rules: list[RuleV2] = Field(default_factory=list)


class Applicability(StrictModel):
    part_families: list[str] = Field(default_factory=list)
    manufacturing_modes: list[str] = Field(default_factory=list)


class CompiledFrom(StrictModel):
    template_ids: list[int] = Field(default_factory=list)
    source_rule_package_ids: list[int] = Field(default_factory=list)


class PackageScope(StrictModel):
    type: Literal["project"] = "project"
    key: str = Field(pattern=r"^[1-9]\d*$")


class RulePackageManifestV2(StrictModel):
    schema_version: Literal["2.0"] = "2.0"
    package_name: str = Field(min_length=1)
    project_id: int = Field(gt=0)
    route_version_id: int | None = None
    scope: PackageScope
    applicability: Applicability = Field(default_factory=Applicability)
    compiled_from: CompiledFrom = Field(default_factory=CompiledFrom)


class TestExpectation(StrictModel):
    included_process_ids: list[str] = Field(default_factory=list)
    excluded_process_ids: list[str] = Field(default_factory=list)


class RulePackageTestCase(StrictModel):
    case_id: str = Field(min_length=1)
    input: dict[str, Any] = Field(default_factory=dict)
    expect: TestExpectation


class RulePackageV2(StrictModel):
    manifest: RulePackageManifestV2
    input_schema: InputSchemaV2
    route_catalog: RouteCatalogV2
    route_rules: RouteRulesV2
    test_cases: list[RulePackageTestCase] = Field(default_factory=list)


class CompileRulePackageRequest(StrictModel):
    project_id: int = Field(gt=0)
    package_name: str = Field(min_length=1)
    route_version_id: int | None = None
    applicability: Applicability = Field(default_factory=Applicability)
    fields: list[InputField]
    processes: list[ProcessV2]
    rules: list[RuleV2] = Field(default_factory=list)
    test_cases: list[RulePackageTestCase] = Field(default_factory=list)


class ValidationIssue(StrictModel):
    code: str
    path: str = ""
    message: str


class TestCaseResult(StrictModel):
    case_id: str
    passed: bool
    message: str = ""


class RulePackageValidationReport(StrictModel):
    valid: bool
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    test_results: list[TestCaseResult] = Field(default_factory=list)


class KmaiCompatibilityExport(StrictModel):
    format: Literal["kmai-v1"] = "kmai-v1"
    valid: bool
    target_directory: str
    errors: list[ValidationIssue] = Field(default_factory=list)
    warnings: list[ValidationIssue] = Field(default_factory=list)
    files: dict[str, dict[str, Any]] = Field(default_factory=dict)


class CompileRulePackageResponse(StrictModel):
    package: RulePackageV2
    content_hash: str
    validation: RulePackageValidationReport
    kmai_compatibility: KmaiCompatibilityExport


class ConditionTrace(StrictModel):
    kind: Literal["all", "any", "not", "leaf"]
    matched: bool
    reason: str
    field: str | None = None
    op: str | None = None
    actual: Any = None
    expected: Any = None
    children: list["ConditionTrace"] = Field(default_factory=list)


class RuleExecutionTrace(StrictModel):
    rule_id: str
    priority: int
    matched: bool
    condition: ConditionTrace


class PlannedRouteStep(StrictModel):
    process_id: str
    sequence: int
    name: str
    op_type: Literal["MAIN", "BRANCH"]
    reason: str
    process_steps: list[str] = Field(default_factory=list)


class RoutePlan(StrictModel):
    steps: list[PlannedRouteStep]
    traces: list[RuleExecutionTrace]
    selected_process_ids: list[str]


class SimulateRulePackageRequest(StrictModel):
    package: RulePackageV2
    inputs: dict[str, Any] = Field(default_factory=dict)


class SimulateRulePackageResponse(StrictModel):
    content_hash: str
    validation: RulePackageValidationReport
    plan: RoutePlan | None = None


ConditionNode.model_rebuild()
ConditionTrace.model_rebuild()
