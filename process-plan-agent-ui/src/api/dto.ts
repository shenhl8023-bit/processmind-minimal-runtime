import {
  ANALYSIS_STATUS_VALUES,
  CONDITION_REVIEW_STATUS_VALUES,
  DOCUMENT_STATUS_VALUES,
  EXTRACTION_TASK_STATUS_VALUES,
  FACTOR_REVIEW_DECISION_VALUES,
  OPERATION_REVIEW_STATUS_VALUES,
  PROJECT_STATUS_VALUES,
  ROUTE_MERGE_REVIEW_STATUS_VALUES,
  ROUTE_REVIEW_DECISION_VALUES,
  RULE_PACKAGE_STATUS_BLOCKER_CODE_VALUES,
  RULE_PACKAGE_STATUS_VALUES,
  WORKFLOW_CAPABILITY_VALUES,
} from './generated/status'
import type {
  AnalysisStatus,
  ConditionReviewStatus,
  DocumentStatus,
  ExtractionTaskStatus,
  FactorReviewDecision,
  OperationReviewStatus,
  ProjectStatus,
  RouteMergeReviewStatus,
  RouteReviewDecision,
  RulePackageStatus,
  RulePackageStatusBlockerCode,
  WorkflowCapability,
} from './generated/status'

export {
  ANALYSIS_STATUS_VALUES,
  CONDITION_REVIEW_STATUS_VALUES,
  DOCUMENT_STATUS_VALUES,
  EXTRACTION_TASK_STATUS_VALUES,
  FACTOR_REVIEW_DECISION_VALUES,
  OPERATION_REVIEW_STATUS_VALUES,
  PROJECT_STATUS_VALUES,
  ROUTE_MERGE_REVIEW_STATUS_VALUES,
  ROUTE_REVIEW_DECISION_VALUES,
  RULE_PACKAGE_STATUS_BLOCKER_CODE_VALUES,
  RULE_PACKAGE_STATUS_VALUES,
  WORKFLOW_CAPABILITY_VALUES,
}
export type {
  AnalysisStatus,
  ConditionReviewStatus,
  DocumentStatus,
  ExtractionTaskStatus,
  FactorReviewDecision,
  OperationReviewStatus,
  ProjectStatus,
  RouteMergeReviewStatus,
  RouteReviewDecision,
  RulePackageStatus,
  RulePackageStatusBlockerCode,
  WorkflowCapability,
}

export type ApiRecord = Record<string, unknown>

function includesStatus<T extends string>(values: readonly T[], value: unknown): value is T {
  return typeof value === 'string' && values.includes(value as T)
}

export const isProjectStatus = (value: unknown): value is ProjectStatus => (
  includesStatus(PROJECT_STATUS_VALUES, value)
)

export const isExtractionTaskStatus = (value: unknown): value is ExtractionTaskStatus => (
  includesStatus(EXTRACTION_TASK_STATUS_VALUES, value)
)

export const isConditionReviewStatus = (value: unknown): value is ConditionReviewStatus => (
  includesStatus(CONDITION_REVIEW_STATUS_VALUES, value)
)

export const isRulePackageStatus = (value: unknown): value is RulePackageStatus => (
  includesStatus(RULE_PACKAGE_STATUS_VALUES, value)
)

export type ProjectMode = 'route_rules'
export type RuleEngine = 'auto' | 'v1' | 'v2'

export interface ProjectDto {
  id: number
  name: string
  mode: ProjectMode
  profile: string
  rule_engine: RuleEngine
  workflow_revision: number
  status: ProjectStatus
  created_at: string
  updated_at: string
}

export interface HarnessValidationIssueDto {
  level: 'error' | 'warning'
  code: string
  message: string
  target?: string
  suggested_action?: string
}

export interface HarnessValidationPayloadDto {
  ok: boolean
  stage: string
  errors: HarnessValidationIssueDto[]
  warnings: HarnessValidationIssueDto[]
}

export interface ExtractionTaskStartDto {
  ok: boolean
  project_id: number
  task_status: ExtractionTaskStatus
  stage: string
  message: string
  workflow_revision: number
}

export interface ExtractionTaskStatusDto {
  project_id: number
  task_status: ExtractionTaskStatus
  stage: string
  message: string
  error?: string | null
  progress: number
  started_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  project_status?: ProjectStatus | null
  harness?: HarnessValidationPayloadDto | null
  local_execution_active: boolean
  lease_valid: boolean
}

export interface WorkflowResetDto {
  project_id: number
  from_step: 3 | 4
  workflow_revision: number
  deleted_operations: number
  deleted_route_merge_snapshots: number
  deleted_route_versions: number
  deleted_factor_reviews: number
  deleted_rule_reviews: number
  reset_condition_reviews: number
  preserved_manual_condition_reviews: number
  deleted_generated_routes: number
  archived_rule_package_versions: number[]
}

export interface FinalizedRulePackageDto<TCompatibility = unknown> {
  id: number
  project_id: number
  route_version_id?: number | null
  version: number
  package_name: string
  schema_version: string
  status: RulePackageStatus
  manifest: ApiRecord
  input_schema: ApiRecord
  route_catalog: ApiRecord
  route_rules: ApiRecord
  test_cases: ApiRecord[]
  rule_report_md: string
  validation_report: ApiRecord
  content_hash: string
  created_by: string
  created_at: string
  published_by?: string | null
  published_at?: string | null
  supersedes_id?: number | null
  kmai_compatibility?: TCompatibility
}

export interface FinalizedRulePackageListItemDto {
  id: number
  project_id: number
  route_version_id?: number | null
  version: number
  package_name: string
  schema_version: string
  status: RulePackageStatus
  content_hash: string
  created_by: string
  created_at: string
  published_by?: string | null
  published_at?: string | null
  supersedes_id?: number | null
  validation_report?: ApiRecord
  test_case_count?: number
}

export interface RulePackageStatusDto {
  project_id: number
  project_status: ProjectStatus
  workflow_revision: number
  route: { id: number; version: number } | null
  latest_package: {
    id: number
    version: number
    route_version_id: number | null
    schema_version: string
    content_hash: string
    status: RulePackageStatus
  } | null
  can_publish: boolean
  can_generate: boolean
  package_executable: boolean
  blockers: Array<{
    code: RulePackageStatusBlockerCode
    message: string
    blocks: WorkflowCapability[]
    count?: number | null
  }>
  review_summary: {
    total: number
    confirmed: number
    pending: number
    invalid_factor_bindings: number
  }
  kmai_compatibility: {
    available: boolean
    valid: boolean
    error_count: number
    warning_count: number
    factor_catalog_version: string
  }
}
