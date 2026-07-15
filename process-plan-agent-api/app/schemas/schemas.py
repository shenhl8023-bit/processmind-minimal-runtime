"""
Pydantic 响应与请求模型
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Any, Dict
from datetime import datetime


# ---------- 项目 ----------
class ProjectCreate(BaseModel):
    name: str
    mode: str = "route_rules"
    profile: Optional[str] = None


class ProjectOut(BaseModel):
    id: int
    name: str
    mode: str
    profile: str
    rule_engine: str = "auto"
    status: str
    created_at: datetime
    updated_at: datetime

    model_config = {"from_attributes": True}


class ProjectRuleEngineUpdate(BaseModel):
    rule_engine: str = "auto"


class ProjectProfileOut(BaseModel):
    key: str
    mode: str
    label: str
    short_label: str
    description: str


# ---------- 文档 ----------
class DocumentOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    filename: str
    original_name: str
    file_type: Optional[str] = None
    file_size: Optional[int] = None
    uploader: str
    status: str
    created_at: datetime

    model_config = {"from_attributes": True}


class DocumentPreviewOut(BaseModel):
    id: int
    original_name: str
    file_type: Optional[str] = None
    preview_text: str = ""


# ---------- 参考资料 ----------
class ReferenceCreate(BaseModel):
    title: str
    content: Optional[str] = None
    ref_type: str = "written"
    document_id: Optional[int] = None
    project_id: Optional[int] = None


class ReferenceOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    title: str
    content: Optional[str] = None
    ref_type: str
    filename: Optional[str] = None
    document_id: Optional[int] = None
    created_at: datetime

    model_config = {"from_attributes": True}


# ---------- 工序 & 影响因素 ----------
class FactorOut(BaseModel):
    id: int
    name: str
    evidence: Optional[str] = None
    strength: str
    confirmed: bool

    model_config = {"from_attributes": True}


class OperationOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    name: str
    sequence: int
    chain: Optional[str] = None
    op_type: str
    description: Optional[str] = None
    source: Optional[str] = None
    confidence: str
    factors: List[FactorOut] = []
    review_status: Optional[str] = None
    review_label: Optional[str] = None
    review_reason: Optional[str] = None
    sample_count: int = 0
    coverage_count: int = 0
    has_exception: bool = False
    has_user_note: bool = False
    reviewed: bool = False
    harness_warnings: List[Dict[str, str]] = []
    source_nodes: List[str] = []
    step_items: List[str] = []
    attached_step_items: List[str] = []

    model_config = {"from_attributes": True}


class DocumentOperationDetailOut(BaseModel):
    id: int
    project_id: Optional[int] = None
    document_id: Optional[int] = None
    pdf_name: str
    operation_seq: int
    operation_name: str
    operation_content: str = ""
    page_no: Optional[int] = None
    equipment_types: str = ""
    equipment_models: str = ""
    normalized_name: Optional[str] = None
    is_composite: bool = False
    source_type: str = "pdf_table_extract"

    model_config = {"from_attributes": True}


class DocumentOperationDetailListOut(BaseModel):
    project_id: int
    items: List[DocumentOperationDetailOut] = []


class MergeMatchedDetailRowOut(BaseModel):
    detail_id: int
    document_id: Optional[int] = None
    pdf_name: str
    operation_seq: int
    operation_name: str
    normalized_name: Optional[str] = None
    operation_content: str
    page_no: Optional[int] = None
    equipment_types: str = ""
    equipment_models: str = ""


class MergeSuggestionOut(BaseModel):
    suggestion_id: str
    target_group_id: str
    sequence: int = 0
    source_nodes: List[str] = []
    source_operation_ids: List[int] = []
    normalized_step_name: str
    suggestion_type: str = "single"
    recommendation_label: str = ""
    recommendation_reason: str = ""
    recommended_target_name: str = ""
    parent_segment: str = ""
    equipment_child_segment: str = ""
    equipment_split_applied: bool = False
    equipment_types: List[str] = []
    equipment_models: List[str] = []
    equipment_support_result: str = "neutral"
    equipment_support_reason: str = ""
    step_family: str = ""
    phase: str = ""
    separator_result: str = "pass"
    manual_review_required: bool = False
    reason_codes: List[str] = []
    evidence_excerpt: List[str] = []
    matched_detail_rows: List[MergeMatchedDetailRowOut] = []
    suggested_action: str = "review"
    status: str = "pending"


class MergeSuggestionListOut(BaseModel):
    project_id: int
    merge_suggestions: List[MergeSuggestionOut] = []
    source_signature: str = ""
    algo_version: str = ""


class NormalizedRouteSegmentOut(BaseModel):
    id: str
    sequence: int
    normalized_step_name: str
    parent_segment: str = ""
    equipment_child_segment: str = ""
    equipment_split_applied: bool = False
    equipment_types: List[str] = []
    equipment_models: List[str] = []
    equipment_support_result: str = "neutral"
    equipment_support_reason: str = ""
    step_family: str = ""
    phase: str = ""
    source_nodes: List[str] = []
    source_operation_names: List[str] = []
    source_operation_ids: List[int] = []
    review_status: str = "pending"
    source_type: str = "system_generated"
    coverage_label: str = ""
    separator_result: str = "pass"
    manual_review_required: bool = False
    reason_codes: List[str] = []
    evidence_excerpt: List[str] = []
    matched_detail_rows: List[MergeMatchedDetailRowOut] = []


class NormalizedSupersetRouteOut(BaseModel):
    project_id: int
    normalized_superset_route: List[NormalizedRouteSegmentOut] = []
    saved_route_version: Optional[int] = None
    source_signature: str = ""
    algo_version: str = ""


class DocumentCoverageOut(BaseModel):
    hit_docs: int = 0
    total_docs: int = 0
    ratio: float = 0.0
    label: str = ""


class DetailCoverageOut(BaseModel):
    matched_rows: int = 0


class EquipmentProfileOut(BaseModel):
    split_applied: bool = False
    equipment_types: List[str] = []
    equipment_models: List[str] = []


class SegmentFactorReviewOut(BaseModel):
    id: int
    factor_name: str
    decision: str
    note: str = ""
    source_type: str = "aggregated"
    evidence_refs: List[str] = []
    source_operation_ids: List[int] = []
    source_operation_names: List[str] = []
    created_at: datetime
    updated_at: datetime


class SegmentRuleReviewOut(BaseModel):
    id: int
    decision: str
    note: str = ""
    summary_lines: List[str] = []
    question_trail: List[Dict[str, str]] = []
    created_at: datetime
    updated_at: datetime


class SavedNormalizedRouteSegmentOut(BaseModel):
    id: str
    sequence: int
    normalized_step_name: str
    step_family: str = ""
    phase: str = ""
    parent_segment: str = ""
    source_type: str = "manual_adjusted"
    source_operation_ids: List[int] = []
    source_nodes: List[str] = []
    source_operation_names: List[str] = []
    reason_codes: List[str] = []
    doc_coverage: DocumentCoverageOut = Field(default_factory=DocumentCoverageOut)
    detail_coverage: DetailCoverageOut = Field(default_factory=DetailCoverageOut)
    evidence_excerpt: List[str] = []
    matched_detail_rows: List[MergeMatchedDetailRowOut] = []
    equipment_profile: EquipmentProfileOut = Field(default_factory=EquipmentProfileOut)
    analysis_status: str = "pending"
    factor_reviews: List[SegmentFactorReviewOut] = []
    rule_review: Optional[SegmentRuleReviewOut] = None


class SavedNormalizedRouteVersionOut(BaseModel):
    route_id: int
    project_id: int
    version: int
    source_signature: str = ""
    saved_by: str = "默认用户"
    saved_at: datetime
    total_docs: int = 0
    segment_count: int = 0
    segments: List[SavedNormalizedRouteSegmentOut] = []


class NormalizedRouteSegmentSaveItem(BaseModel):
    id: str
    normalized_step_name: str
    source_operation_ids: List[int] = []
    source_nodes: List[str] = []
    source_operation_names: List[str] = []
    review_status: str = "merged"
    step_family: str = ""
    phase: str = ""
    parent_segment: str = ""
    equipment_child_segment: str = ""
    equipment_split_applied: bool = False
    equipment_types: List[str] = []
    equipment_models: List[str] = []
    equipment_support_result: str = "neutral"
    equipment_support_reason: str = ""
    source_type: str = "manual_adjusted"
    coverage_label: str = ""
    separator_result: str = "pass"
    manual_review_required: bool = False
    reason_codes: List[str] = []
    evidence_excerpt: List[str] = []
    matched_detail_rows: List[MergeMatchedDetailRowOut] = []


class SaveNormalizedSupersetRouteRequest(BaseModel):
    project_id: int
    normalized_superset_route: List[NormalizedRouteSegmentSaveItem] = []


class SaveSegmentRuleReviewRequest(BaseModel):
    project_id: int
    route_id: int
    segment_id: str
    decision: str = "accepted"
    note: str = ""
    summary_lines: List[str] = []
    question_trail: List[Dict[str, str]] = []


class SegmentRuleReviewSaveOut(BaseModel):
    project_id: int
    route_id: int
    segment_id: str
    analysis_status: str = "pending"
    normalized_step_name: Optional[str] = None
    rule_review: Optional[SegmentRuleReviewOut] = None


class FinalizedRulePackageSaveRequest(BaseModel):
    project_id: int
    route_version_id: Optional[int] = None
    package_name: str = "process_route_rules"
    schema_version: str = "1.0"
    manifest: Dict[str, Any] = Field(default_factory=dict)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    route_catalog: Dict[str, Any] = Field(default_factory=dict)
    route_rules: Dict[str, Any] = Field(default_factory=dict)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    rule_report_md: str = ""
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    created_by: str = "默认用户"


class FinalizedRulePackageOut(BaseModel):
    id: int
    project_id: int
    route_version_id: Optional[int] = None
    version: int
    package_name: str
    schema_version: str = "1.0"
    status: str = "published"
    manifest: Dict[str, Any] = Field(default_factory=dict)
    input_schema: Dict[str, Any] = Field(default_factory=dict)
    route_catalog: Dict[str, Any] = Field(default_factory=dict)
    route_rules: Dict[str, Any] = Field(default_factory=dict)
    test_cases: List[Dict[str, Any]] = Field(default_factory=list)
    rule_report_md: str = ""
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    content_hash: str = ""
    created_by: str = "默认用户"
    created_at: datetime
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None
    supersedes_id: Optional[int] = None


class FinalizedRulePackageListItemOut(BaseModel):
    id: int
    project_id: int
    route_version_id: Optional[int] = None
    version: int
    package_name: str
    schema_version: str = "1.0"
    status: str = "published"
    content_hash: str = ""
    created_by: str = "默认用户"
    created_at: datetime
    published_by: Optional[str] = None
    published_at: Optional[datetime] = None
    supersedes_id: Optional[int] = None
    validation_report: Dict[str, Any] = Field(default_factory=dict)
    test_case_count: int = 0


class SupersetRouteOut(BaseModel):
    project_id: int
    superset_route: List[OperationOut] = []


class MergeSuggestionReviewRequest(BaseModel):
    project_id: int
    suggestion_id: str
    action: str
    manual_label: Optional[str] = None


class QuestionHarnessHookOut(BaseModel):
    hook: str
    status: str = "pass"
    message: str = ""
    issues: List[Dict[str, str]] = []


class ExtractionTaskStartOut(BaseModel):
    ok: bool = True
    project_id: int
    task_status: str
    stage: str
    message: str


class ExtractionTaskStatusOut(BaseModel):
    project_id: int
    task_status: str
    stage: str
    message: str = ""
    error: Optional[str] = None
    progress: int = 0
    started_at: Optional[str] = None
    updated_at: Optional[str] = None
    finished_at: Optional[str] = None
    project_status: Optional[str] = None
    harness: Optional[Dict[str, Any]] = None


# ---------- 工艺路线生成 ----------
class GenerateRequest(BaseModel):
    project_id: Optional[int] = None
    factor_values: dict[str, Any] = Field(default_factory=dict)
    family: str = ""
    material: str = ""
    hardness: str = "LOW"
    has_hole: bool = False
    has_spline: bool = False
    roughness: float = 3.2


class FactorFieldOption(BaseModel):
    value: str
    label: str


class FactorFieldOut(BaseModel):
    key: str
    label: str
    group: str
    input_type: str
    required: bool = False
    placeholder: Optional[str] = None
    options: List[FactorFieldOption] = []


class RouteStep(BaseModel):
    process_id: str = ""
    sequence: Optional[int] = None
    name: str
    op_type: str  # MAIN / BRANCH
    reason: str
    process_steps: List[str] = Field(default_factory=list)


class GenerateResponse(BaseModel):
    id: Optional[int] = None
    steps: List[RouteStep]
    summary: str
    output_json_text: Optional[str] = None
    output_mode: str = "route_rules"
    rule_package_id: Optional[int] = None
    rule_package_version: Optional[int] = None
    rule_package_hash: Optional[str] = None
    schema_version: Optional[str] = None
    matched_rule_ids: List[str] = Field(default_factory=list)
    selected_process_ids: List[str] = Field(default_factory=list)


class ParamJsonStepOut(BaseModel):
    name: str
    description: str = ""
    machine: str = ""
    note: str = ""
    evidence_count: int = 0


class ParamJsonStageOut(BaseModel):
    stage: str
    steps: List[ParamJsonStepOut] = []
    occurrence_index: int = 1
    evidence_count: int = 0


class ParamConfirmOptionOut(BaseModel):
    value: str
    label: str
    count: int = 0


class ParamConfirmQuestionOut(BaseModel):
    key: str
    label: str
    prompt: str
    input_type: str
    required: bool = False
    reason: str = ""
    options: List[ParamConfirmOptionOut] = []


class ParamCompiledRuleOut(BaseModel):
    stage: str
    occurrence_index: int = 1
    step_name: str
    include_when: str
    priority: int = 100
    strength: str = "STRONG"
    evidence: str = ""
    why_not_stable: str = ""
    candidate_factors: List[str] = []
    question_hint: str = ""


class ParamAuditOverviewOut(BaseModel):
    sample_pair_count: int = 0
    operation_count: int = 0
    stable_operation_count: int = 0
    pending_operation_count: int = 0
    data_issue_operation_count: int = 0


class ParamReviewedFactorOut(BaseModel):
    factor_key: str
    factor_label: str
    expected_value: str = ""
    coverage_count: int = 0
    total_count: int = 0
    status: str = "pending_confirm"
    reason_type: str = ""
    reason_text: str = ""


class ParamCandidateCombinationOut(BaseModel):
    factor_keys: List[str] = []
    expression_text: str = ""
    status: str = "pending_confirm"


class ParamCurrentQuestionOut(BaseModel):
    factor_key: str
    question_type: str
    prompt: str
    options: List[ParamConfirmOptionOut] = []
    tree_branch: str = ""
    tree_node_id: str = ""
    option_source: str = "fixed"
    round_index: int = 1
    round_total_hint: int = 1
    question_goal: str = ""
    continue_reason: str = ""
    next_focus: str = ""
    llm_enhanced: bool = False


class ParamOperationReviewOut(BaseModel):
    operation_key: str
    stage: str
    occurrence_index: int = 1
    step_name: str
    sample_hit_count: int = 0
    sample_total_count: int = 0
    operation_kind: str = ""
    operation_kind_reason: str = ""
    review_status: str = "pending_confirm"
    summary: str = ""
    resolved_factors: List[ParamReviewedFactorOut] = []
    pending_factors: List[ParamReviewedFactorOut] = []
    auxiliary_factors: List[ParamReviewedFactorOut] = []
    candidate_combination: Optional[ParamCandidateCombinationOut] = None
    current_question: Optional[ParamCurrentQuestionOut] = None
    answered: bool = False
    answer_summary: str = ""
    question_round_completed: int = 0
    question_round_limit: int = 1
    question_hooks: List[QuestionHarnessHookOut] = []


class ParamPreviewOut(BaseModel):
    project_id: int
    factor_fields: List[FactorFieldOut] = []
    sample_documents: List[DocumentOut] = []
    selected_document_id: Optional[int] = None
    superset_stages: List[ParamJsonStageOut] = []
    sample_stages: List[ParamJsonStageOut] = []
    pending_questions: List[ParamConfirmQuestionOut] = []
    summary: str = ""
    compiled_rule_summary: str = ""
    compiled_rule_count: int = 0
    compiled_with_llm: bool = False
    compiled_rules: List[ParamCompiledRuleOut] = []
    validation_report: dict[str, Any] = Field(default_factory=dict)
    audit_overview: ParamAuditOverviewOut = Field(default_factory=ParamAuditOverviewOut)
    operation_reviews: List[ParamOperationReviewOut] = []
    answered_question_count: int = 0
    remaining_question_count: int = 0
    audit_report_ready: bool = False


class ParamAnswerSubmitRequest(BaseModel):
    project_id: int
    operation_key: str
    stage: str
    occurrence_index: int = 1
    step_name: str
    factor_key: str
    question_type: str
    selected_value: str
    selected_label: Optional[str] = None
    note: Optional[str] = None


class ParamAnswerSubmitResponse(BaseModel):
    ok: bool = True
    project_id: int
    operation_key: str
    factor_key: str
    answer_kind: str
    answer_hooks: List[QuestionHarnessHookOut] = []


class ParamAuditReportOut(BaseModel):
    project_id: int
    title: str
    filename: str
    summary: str
    content_markdown: str



# ---------- 系统设置 ----------
class SettingUpdate(BaseModel):
    key: str
    value: str


class SettingOut(BaseModel):
    id: int
    key: str
    value: str
    description: Optional[str] = None
    updated_at: datetime
    is_secret: bool = False
    is_configured: bool = False

    model_config = {"from_attributes": True}


class LLMTestRequest(BaseModel):
    api_url: str
    api_key: str
    model: Optional[str] = None


class LLMTestOut(BaseModel):
    success: bool
    message: str


class LLMModelOut(BaseModel):
    id: str
    name: str
