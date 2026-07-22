import { api } from './client'
import {
  clearAllWorkflowDataCache,
  clearWorkflowProjectDataCache,
  getWorkflowDataCache,
  setWorkflowDataCache,
} from '@/composables/workflowDataCache'

export interface OperationFactor {
  id: number
  name: string
  evidence?: string | null
  strength: string
  confirmed: boolean
}

export interface OperationItem {
  id: number
  project_id?: number | null
  name: string
  sequence: number
  chain?: string | null
  op_type: string
  description?: string | null
  source?: string | null
  confidence: string
  factors: OperationFactor[]
  review_status?: 'stable' | 'pending_confirm' | 'exception' | 'evidence' | 'data_issue' | null
  review_label?: string | null
  review_reason?: string | null
  sample_count?: number
  coverage_count?: number
  has_exception?: boolean
  has_user_note?: boolean
  reviewed?: boolean
  harness_warnings?: HarnessValidationIssue[]
  source_nodes?: string[]
  step_items?: string[]
  attached_step_items?: string[]
  source_operation_id?: number
  source_operation_name?: string
  display_key?: string
}

export interface DocumentOperationDetailItem {
  id: number
  project_id?: number | null
  document_id?: number | null
  pdf_name: string
  operation_seq: number
  operation_name: string
  operation_content: string
  page_no?: number | null
  normalized_name?: string | null
  is_composite: boolean
  source_type: string
  equipment_types?: string | null
  equipment_models?: string | null
}

export interface DocumentOperationDetailResult {
  project_id: number
  items: DocumentOperationDetailItem[]
}

export interface MergeMatchedDetailRow {
  detail_id: number
  document_id?: number | null
  pdf_name: string
  operation_seq: number
  operation_name: string
  operation_content: string
  page_no?: number | null
  equipment_types?: string | null
  equipment_models?: string | null
}

export interface MergeSuggestion {
  suggestion_id: string
  target_group_id: string
  sequence: number
  source_nodes: string[]
  source_operation_ids: number[]
  normalized_step_name: string
  suggestion_type: string
  recommendation_label: string
  recommendation_reason: string
  recommended_target_name: string
  step_family: string
  phase: string
  separator_result: string
  manual_review_required: boolean
  reason_codes: string[]
  evidence_excerpt: string[]
  matched_detail_rows: MergeMatchedDetailRow[]
  parent_segment: string
  equipment_child_segment: string
  equipment_split_applied: boolean
  equipment_types: string[]
  equipment_models: string[]
  equipment_support_result: string
  equipment_support_reason: string
  suggested_action: string
  status: string
}

export interface MergeSuggestionResult {
  project_id: number
  merge_suggestions: MergeSuggestion[]
  source_signature: string
  algo_version: string
}

export interface NormalizedRouteSegment {
  id: string
  sequence: number
  normalized_step_name: string
  step_family: string
  phase: string
  source_nodes: string[]
  source_operation_names?: string[]
  source_operation_ids: number[]
  review_status: string
  source_type: string
  coverage_label: string
  separator_result: string
  manual_review_required: boolean
  reason_codes: string[]
  evidence_excerpt: string[]
  matched_detail_rows: MergeMatchedDetailRow[]
  parent_segment: string
  equipment_child_segment: string
  equipment_split_applied: boolean
  equipment_types: string[]
  equipment_models: string[]
  equipment_support_result: string
  equipment_support_reason: string
}

export interface SupersetRouteResult {
  project_id: number
  superset_route: OperationItem[]
}

export interface NormalizedSupersetRouteResult {
  project_id: number
  normalized_superset_route: NormalizedRouteSegment[]
  saved_route_version?: number | null
  source_signature: string
  algo_version: string
}

export interface SavedRouteCoverage {
  hit_docs: number
  total_docs: number
  ratio: number
  label: string
}

export interface SavedRouteDetailCoverage {
  matched_rows: number
}

export interface SavedRouteEquipmentProfile {
  split_applied: boolean
  equipment_types: string[]
  equipment_models: string[]
}

export interface SegmentFactorReview {
  id: number
  factor_name: string
  decision: 'confirmed' | 'excluded'
  note: string
  source_type: 'aggregated' | 'manual' | 'heuristic'
  evidence_refs: string[]
  source_operation_ids: number[]
  source_operation_names: string[]
  created_at: string
  updated_at: string
}

export interface SegmentRuleReview {
  id: number
  decision: 'accepted' | 'rejected'
  note: string
  summary_lines: string[]
  question_trail: Array<{
    nodeId: string
    value: string
    label: string
  }>
  condition_review?: import('./rulePackages').RuleConditionReview | null
  created_at: string
  updated_at: string
}

export interface SavedNormalizedRouteSegment {
  id: string
  sequence: number
  normalized_step_name: string
  step_family: string
  phase: string
  parent_segment: string
  source_type: string
  source_operation_ids: number[]
  source_nodes: string[]
  source_operation_names?: string[]
  reason_codes?: string[]
  doc_coverage: SavedRouteCoverage
  detail_coverage: SavedRouteDetailCoverage
  evidence_excerpt: string[]
  matched_detail_rows: MergeMatchedDetailRow[]
  equipment_profile: SavedRouteEquipmentProfile
  analysis_status: string
  factor_reviews: SegmentFactorReview[]
  rule_review?: SegmentRuleReview | null
}

export interface SavedNormalizedRouteVersionResult {
  route_id: number
  project_id: number
  version: number
  source_signature: string
  saved_by: string
  saved_at: string
  total_docs: number
  segment_count: number
  segments: SavedNormalizedRouteSegment[]
}

export interface SegmentRuleReviewSaveResult {
  project_id: number
  route_id: number
  segment_id: string
  analysis_status: string
  normalized_step_name?: string | null
  rule_review?: SegmentRuleReview | null
}

export interface FinalizedRulePackageResult {
  id: number
  project_id: number
  route_version_id?: number | null
  version: number
  package_name: string
  schema_version: string
  status: 'draft' | 'published' | 'superseded' | 'archived' | string
  manifest: Record<string, any>
  input_schema: Record<string, any>
  route_catalog: Record<string, any>
  route_rules: Record<string, any>
  test_cases: Array<Record<string, any>>
  rule_report_md: string
  validation_report: Record<string, any>
  content_hash: string
  created_by: string
  created_at: string
  published_by?: string | null
  published_at?: string | null
  supersedes_id?: number | null
}

export interface FinalizedRulePackageListItem {
  id: number
  project_id: number
  route_version_id?: number | null
  version: number
  package_name: string
  schema_version: string
  status: 'draft' | 'published' | 'superseded' | 'archived' | string
  content_hash: string
  created_by: string
  created_at: string
  published_by?: string | null
  published_at?: string | null
  supersedes_id?: number | null
  validation_report?: Record<string, any>
  test_case_count?: number
}

export interface ExtractionTaskStartResult {
  ok: boolean
  project_id: number
  task_status: string
  stage: string
  message: string
}

export interface HarnessValidationIssue {
  level: 'error' | 'warning'
  code: string
  message: string
  target?: string
  suggested_action?: string
}

export interface HarnessValidationPayload {
  ok: boolean
  stage: string
  errors: HarnessValidationIssue[]
  warnings: HarnessValidationIssue[]
}

export interface ExtractionTaskStatus {
  project_id: number
  task_status: 'idle' | 'running' | 'completed' | 'failed'
  stage: string
  message: string
  error?: string | null
  progress: number
  started_at?: string | null
  updated_at?: string | null
  finished_at?: string | null
  project_status?: string | null
  harness?: HarnessValidationPayload | null
}

export async function startExtraction(projectId: number, forceReextract: boolean = false) {
  const { data } = await api.post('/api/extract/start', null, {
    params: {
      project_id: projectId,
      ...(forceReextract ? { force_reextract: true } : {}),
    },
  })
  clearAllWorkflowDataCache()
  return data as ExtractionTaskStartResult
}

export async function listOperations(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:operations:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<OperationItem[]>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/operations', { params: { project_id: projectId } })
  const operations = data as OperationItem[]
  setWorkflowDataCache(cacheKey, operations)
  return operations
}

export async function getDocumentOperationDetails(
  projectId: number,
  documentId?: number,
  operationName?: string,
  forceRefresh = false,
) {
  const cacheKey = `api:extract:document-operation-details:${projectId}:${documentId || 'all'}:${operationName || 'all'}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<DocumentOperationDetailResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/document-operation-details', {
    params: {
      project_id: projectId,
      ...(documentId ? { document_id: documentId } : {}),
      ...(operationName ? { operation_name: operationName } : {}),
    },
  })
  const result = data as DocumentOperationDetailResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function getSupersetRoute(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:superset-route:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<SupersetRouteResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/superset-route', { params: { project_id: projectId } })
  const result = data as SupersetRouteResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function getMergeSuggestions(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:merge-suggestions:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<MergeSuggestionResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/merge-suggestions', { params: { project_id: projectId } })
  const result = data as MergeSuggestionResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function getNormalizedSupersetRoute(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:normalized-superset-route:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<NormalizedSupersetRouteResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/normalized-superset-route', { params: { project_id: projectId } })
  const result = data as NormalizedSupersetRouteResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function getSavedNormalizedRoute(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:saved-normalized-route:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<SavedNormalizedRouteVersionResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/saved-normalized-route', { params: { project_id: projectId } })
  const result = data as SavedNormalizedRouteVersionResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function saveNormalizedSupersetRoute(body: {
  project_id: number
  normalized_superset_route: Array<{
    id: string
    normalized_step_name: string
    source_operation_ids: number[]
    source_nodes: string[]
    source_operation_names?: string[]
    review_status?: string
    step_family?: string
    phase?: string
    parent_segment?: string
    equipment_child_segment?: string
    equipment_split_applied?: boolean
    equipment_types?: string[]
    equipment_models?: string[]
    equipment_support_result?: string
    equipment_support_reason?: string
    source_type?: string
    coverage_label?: string
    separator_result?: string
    manual_review_required?: boolean
    reason_codes?: string[]
    evidence_excerpt?: string[]
    matched_detail_rows?: Array<Record<string, any>>
  }>
}) {
  const { data } = await api.post('/api/extract/normalized-superset-route/save', body)
  clearAllWorkflowDataCache()
  return data as NormalizedSupersetRouteResult
}

export async function saveSegmentRuleReview(body: {
  project_id: number
  route_id: number
  segment_id: string
  decision: 'accepted' | 'rejected' | 'pending'
  note?: string
  summary_lines?: string[]
  question_trail?: Array<{
    nodeId: string
    value: string
    label: string
  }>
}) {
  const { data } = await api.post('/api/extract/segment-rule-reviews', body)
  clearWorkflowProjectDataCache(body.project_id)
  return data as SegmentRuleReviewSaveResult
}

export async function saveFinalizedRulePackage(body: {
  project_id: number
  route_version_id?: number | null
  package_name?: string
  schema_version?: string
  manifest?: Record<string, any>
  input_schema: Record<string, any>
  route_catalog: Record<string, any>
  route_rules: Record<string, any>
  test_cases?: Array<Record<string, any>>
  rule_report_md: string
  validation_report?: Record<string, any>
  created_by?: string
}) {
  const { data } = await api.post('/api/extract/finalized-rule-packages', body)
  clearAllWorkflowDataCache()
  return data as FinalizedRulePackageResult
}

export async function getLatestFinalizedRulePackage(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:finalized-rule-packages:latest:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<FinalizedRulePackageResult>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/finalized-rule-packages/latest', { params: { project_id: projectId } })
  const result = data as FinalizedRulePackageResult
  setWorkflowDataCache(cacheKey, result)
  return result
}

export async function listFinalizedRulePackages(projectId: number, forceRefresh = false) {
  const cacheKey = `api:extract:finalized-rule-packages:list:${projectId}`
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<FinalizedRulePackageListItem[]>(cacheKey)
    if (cached) return cached
  }
  const { data } = await api.get('/api/extract/finalized-rule-packages', { params: { project_id: projectId } })
  const result = data as FinalizedRulePackageListItem[]
  setWorkflowDataCache(cacheKey, result)
  return result
}

export interface FinalizedRulePackageSimulationResult {
  content_hash: string
  validation: {
    valid: boolean
    errors: Array<Record<string, any>>
    warnings: Array<Record<string, any>>
    test_results: Array<Record<string, any>>
  }
  plan?: {
    steps: Array<Record<string, any>>
    selected_process_ids: string[]
    traces: Array<Record<string, any>>
  } | null
}

export async function reviewMergeSuggestion(body: {
  project_id: number
  suggestion_id: string
  action: 'accept' | 'reject' | 'rename' | 'unsure'
  manual_label?: string
}) {
  const { data } = await api.post('/api/extract/merge-suggestions/review', body)
  clearWorkflowProjectDataCache(body.project_id)
  return data
}

export async function getExtractTaskStatus(projectId: number) {
  const { data } = await api.get('/api/extract/task-status', { params: { project_id: projectId } })
  return data as ExtractionTaskStatus
}
