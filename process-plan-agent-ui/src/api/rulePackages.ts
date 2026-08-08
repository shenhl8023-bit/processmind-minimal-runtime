import { api } from './client'
import type {
  FinalizedRulePackageResult,
  FinalizedRulePackageSimulationResult,
  TemplateGroupAliasBinding,
} from './extract'

export type InputFieldType = 'string' | 'number' | 'boolean' | 'single_select' | 'multi_select'

export type RulePackageInputOption = {
  value: string
  label: string
  aliases?: string[]
}

export type RulePackageInputField = {
  key: string
  label: string
  type: InputFieldType
  required?: boolean
  source?: string
  options?: RulePackageInputOption[]
  allow_custom?: boolean
  unit?: string | null
  validation?: {
    min?: number | null
    max?: number | null
    min_length?: number | null
    max_length?: number | null
  } | null
}

export type RulePackageProcessStep = {
  step_id: string
  name: string
  kind?: 'primary' | 'attached'
}

export type RulePackageProcess = {
  process_id: string
  process_code?: string
  display_name: string
  template_group_aliases?: TemplateGroupAliasBinding[]
  phase?: string
  default_sequence?: number
  main?: boolean
  steps?: RulePackageProcessStep[]
  constraints?: {
    requires?: string[]
    must_run_after?: string[]
    must_run_before?: string[]
    conflicts_with?: string[]
  }
}

export type RulePackageCondition =
  | { all: RulePackageCondition[] }
  | { any: RulePackageCondition[] }
  | { not: RulePackageCondition }
  | { field: string; op: string; value?: unknown; factor_id?: string | null }

export type StandardFactorDefinition = {
  factor_id: string
  label: string
  category: string
  source_field: string
  source_field_aliases: string[]
  canonical_value: unknown
  allowed_operators: string[]
  kmai_factor_key: string
  kmai_value_mode: 'presence' | 'condition_value'
  runtime_source: 'computed' | 'manual_override'
}

export type KmaiCompatibilityIssue = {
  code: string
  path?: string
  message: string
}

export type KmaiCompatibilityExport = {
  format: 'kmai-v1'
  valid: boolean
  target_directory: string
  errors: KmaiCompatibilityIssue[]
  warnings: KmaiCompatibilityIssue[]
  files: Record<string, Record<string, unknown>>
  factor_catalog_version: string
}

export type RulePackageRule = {
  rule_id: string
  priority?: number
  enabled?: boolean
  source?: 'system_static' | 'user_confirmed'
  source_segment_id?: string
  source_text?: string
  confirmed_by?: string
  confirmed_at?: string
  when: RulePackageCondition
  then: {
    include_process_ids?: string[]
    exclude_process_ids?: string[]
    reason?: string
  }
}

export type ProcessRelationType = 'trigger_after' | 'order_after' | 'requires' | 'conflicts'

export type RulePackageProcessRelation = {
  relation_id: string
  relation_type: ProcessRelationType
  source_process_ids: string[]
  target_process_ids: string[]
  source_match?: 'any' | 'all'
  enabled?: boolean
  source?: 'system_static' | 'user_confirmed'
  source_segment_id?: string
  source_text?: string
  confirmed_by?: string
  confirmed_at?: string
  reason?: string
}

export type CanonicalConditionField = RulePackageInputField & {
  category: string
  operators: string[]
  aliases: string[]
}

export type ConditionFieldRegistryResponse = {
  version: string
  fields: CanonicalConditionField[]
  factors: StandardFactorDefinition[]
}

export type RuleConditionProcessOption = {
  process_id: string
  display_name: string
  main?: boolean
}

export type RuleConditionCandidate = {
  kind?: 'condition' | 'process_relation'
  when?: RulePackageCondition | null
  then?: RulePackageRule['then'] | null
  field_definitions?: CanonicalConditionField[]
  relation?: {
    relation_type: ProcessRelationType
    source_process_ids: string[]
    target_process_ids: string[]
    source_match?: 'any' | 'all'
  } | null
  preview: string
  evidence?: string
}

export type RuleConditionReview = {
  source_text: string
  source_hash: string
  status: 'draft' | 'parsing' | 'pending_confirmation' | 'confirmed' | 'invalid'
  candidate?: RuleConditionCandidate | null
  confirmed?: RuleConditionCandidate | null
  confidence?: number | null
  issues: string[]
  field_registry_version: string
  parser_version?: string
  parse_duration_ms?: number | null
  confirmed_by: string
  confirmed_at: string
}

export type RuleConditionReviewResponse = {
  project_id: number
  route_id: number
  segment_id: string
  review: RuleConditionReview
}

export type RulePackageTestCase = {
  case_id: string
  input: Record<string, unknown>
  expect: {
    included_process_ids?: string[]
    excluded_process_ids?: string[]
  }
}

export type CompileRulePackageRequest = {
  project_id: number
  package_name: string
  route_version_id?: number | null
  applicability?: {
    part_families?: string[]
    manufacturing_modes?: string[]
  }
  fields: RulePackageInputField[]
  processes: RulePackageProcess[]
  rules?: RulePackageRule[]
  process_relations?: RulePackageProcessRelation[]
  test_cases?: RulePackageTestCase[]
}

export type RulePackageV2 = {
  manifest: Record<string, unknown>
  input_schema: {
    schema_version: '2.0'
    fields: RulePackageInputField[]
  }
  route_catalog: {
    schema_version: '2.0'
    processes: RulePackageProcess[]
  }
  route_rules: {
    schema_version: '2.0'
    rules: RulePackageRule[]
    process_relations?: RulePackageProcessRelation[]
  }
  test_cases: RulePackageTestCase[]
}

export type RulePackageValidationReport = {
  valid: boolean
  errors: Array<{ code: string; path?: string; message: string }>
  warnings: Array<{ code: string; path?: string; message: string }>
  test_results: Array<{ case_id: string; passed: boolean; message?: string }>
}

export type CompileRulePackageResponse = {
  package: RulePackageV2
  content_hash: string
  validation: RulePackageValidationReport
  kmai_compatibility: KmaiCompatibilityExport
}

export type SimulateRulePackageDraftResponse = FinalizedRulePackageSimulationResult

export type KmaiCompatibilityTestResult = {
  project_id: number
  package_id: number
  package_version: number
  compatible: boolean
  v2_process_ids: string[]
  v2_matched_rule_ids: string[]
  kmai_process_ids: string[]
  kmai_matched_rule_ids: string[]
  only_v2_process_ids: string[]
  only_kmai_process_ids: string[]
  warnings: Array<{ code: string; path?: string; message: string }>
  errors: Array<{ code: string; path?: string; message: string }>
  manual_factors: Record<string, unknown>
  semantic_gaps: string[]
}

export type RulePackageStatusBlockerCode =
  | 'project_not_ready'
  | 'route_missing'
  | 'pending_rule_reviews'
  | 'invalid_factor_bindings'
  | 'no_published_package'
  | 'published_package_route_changed'
  | 'published_rule_sources_changed'
  | 'published_package_invalid'
  | 'kmai_incompatible'

export type RulePackageStatusResponse = {
  project_id: number
  project_status: string
  workflow_revision: number
  route: { id: number; version: number } | null
  latest_package: {
    id: number
    version: number
    route_version_id: number | null
    schema_version: string
    content_hash: string
    status: string
  } | null
  can_publish: boolean
  can_generate: boolean
  package_executable: boolean
  blockers: Array<{
    code: RulePackageStatusBlockerCode
    message: string
    blocks: Array<'publish' | 'generate'>
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

export async function getFinalizedRulePackageStatus(projectId: number) {
  const { data } = await api.get('/api/extract/finalized-rule-packages/status', {
    params: { project_id: projectId },
  })
  return data as RulePackageStatusResponse
}

export async function testKmaiCompatibility(projectId: number, inputs: Record<string, unknown>) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/compatibility-test', {
    project_id: projectId,
    inputs,
  })
  return data as KmaiCompatibilityTestResult
}

export async function compileRulePackage(body: CompileRulePackageRequest) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/compile', body)
  return data as CompileRulePackageResponse
}

export async function getConditionFieldRegistry() {
  const { data } = await api.get('/api/extract/finalized-rule-packages/condition-fields')
  return data as ConditionFieldRegistryResponse
}

export async function saveRuleConditionDraft(body: {
  project_id: number
  route_id: number
  expected_workflow_revision: number
  segment_id: string
  source_text: string
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/rule-conditions/draft', body)
  return data as RuleConditionReviewResponse
}

export async function parseRuleCondition(body: {
  project_id: number
  route_id: number
  expected_workflow_revision: number
  segment_id: string
  source_text: string
  process_id: string
  process_name: string
  processes: RuleConditionProcessOption[]
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/rule-conditions/parse', body)
  return data as RuleConditionReviewResponse
}

export async function confirmRuleCondition(body: {
  project_id: number
  route_id: number
  expected_workflow_revision: number
  segment_id: string
  source_text: string
  source_hash: string
  candidate: RuleConditionCandidate
  processes: RuleConditionProcessOption[]
  confirmed_by?: string
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/rule-conditions/confirm', body)
  return data as RuleConditionReviewResponse
}

export async function setManualRuleCondition(body: {
  project_id: number
  route_id: number
  expected_workflow_revision: number
  segment_id: string
  process_id: string
  source_text: string
  candidate: RuleConditionCandidate
  processes: RuleConditionProcessOption[]
  confirmed_by?: string
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/rule-conditions/manual', body)
  return data as RuleConditionReviewResponse
}

export async function validateRulePackageV2(body: RulePackageV2) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/validate', body)
  return data as RulePackageValidationReport
}

export async function simulateRulePackageDraft(body: {
  package: RulePackageV2
  inputs: Record<string, unknown>
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages/simulate', body)
  return data as SimulateRulePackageDraftResponse
}

export async function simulatePersistedRulePackage(
  packageId: number,
  inputs: Record<string, unknown>,
) {
  const { data } = await api.post(`/api/extract/finalized-rule-packages/${packageId}/simulate`, { inputs })
  return data as FinalizedRulePackageSimulationResult
}

export type { FinalizedRulePackageResult }
