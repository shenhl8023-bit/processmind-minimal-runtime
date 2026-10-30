import { api } from './client'

export interface KnowledgeSource {
  document_id?: string | null
  document_name?: string | null
  page_no?: number | null
  identity?: string | null
  url?: string | null
  worksheet?: string | null
  row_no?: number | null
  cell_range?: string | null
}

export type KnowledgeRelationshipStatus = 'linked' | 'category_hint' | 'not_provided'

export interface KnowledgeCapabilityPrecision {
  type?: string | null
  min_grade?: number | string | null
  max_grade?: number | string | null
  code?: string | null
  bounds_valid?: boolean | null
}

export interface KnowledgeCapabilityRoughness {
  min_um?: number | null
  max_um?: number | null
  bounds_valid?: boolean | null
}

export interface KnowledgeCapabilityAllowance {
  min_mm?: number | null
  max_mm?: number | null
  basis?: string | null
  bounds_valid?: boolean | null
}

export interface KnowledgeCapabilitySize {
  type?: string | null
  min_mm?: number | null
  max_mm?: number | null
  bounds_valid?: boolean | null
}

export interface KnowledgeCapability {
  feature?: string | null
  method?: string | null
  stage?: string | null
  precision?: KnowledgeCapabilityPrecision | null
  roughness?: KnowledgeCapabilityRoughness | null
  allowance?: KnowledgeCapabilityAllowance | null
  material?: string | null
  material_state?: string | null
  size?: KnowledgeCapabilitySize | null
  conditions?: string | null
  tool_material?: string | null
  other_metrics?: unknown
}

export interface KnowledgeRelationshipItem {
  id?: string | null
  name: string
  model?: string | null
  record_level?: string | null
  entity_category?: string | null
  fields?: Record<string, unknown>
}

export interface KnowledgeRelationship {
  status: KnowledgeRelationshipStatus
  basis: 'id' | 'record_text' | 'missing' | string
  items: KnowledgeRelationshipItem[]
}

export interface KnowledgeRelationships {
  equipment?: KnowledgeRelationship
  tool?: KnowledgeRelationship
  gauge?: KnowledgeRelationship
}

export interface KnowledgeRouteOperation {
  id: string
  number: string
  name: string
  source: KnowledgeSource
  equipment?: unknown[]
  tool?: unknown[]
  gauge?: unknown[]
}

export interface KnowledgeHistoricalRoute {
  part_id: string
  part_name: string
  material: string
  process_id: string
  version: string
  operation_count: number
  operations: KnowledgeRouteOperation[]
}

export interface KnowledgeGuidanceMetric {
  name: string
  min?: number | null
  max?: number | null
  unit: string
  basis: string
  direction?: string
}

export interface KnowledgeGuidanceOperation {
  id: string
  sequence: number
  number: string
  name: string
  execution_status: 'required' | 'conditional' | 'virtual' | 'unspecified'
  condition: string
  source: KnowledgeSource
}

export interface KnowledgeGuidanceResource {
  category: 'equipment' | 'tool' | 'gauge' | 'fixture'
  name: string
  model: string
  identifier: string
  basis: string
}

export interface KnowledgeGuidance {
  kind: 'scope' | 'rule' | 'allowance' | 'quality' | 'fit' | 'formula' | 'resource' | 'stage_overview' | 'route' | 'reference'
  applicability: string
  part_family: string
  typical_part: string
  materials: string[]
  topics: string[]
  conditions: string
  conclusion: string
  exceptions: string
  verification_status: 'verified' | 'pending' | 'conflict'
  original_excerpt: string
  metrics?: KnowledgeGuidanceMetric[]
  completeness?: 'stage_overview' | 'verified_sequence'
  operations?: KnowledgeGuidanceOperation[]
  resources?: KnowledgeGuidanceResource[]
}

export interface KnowledgeSearchItem {
  id: string
  content: string
  category: 'history' | 'capability' | 'equipment' | 'tool' | 'gauge' | string
  title: string
  score?: number | null
  retrieval_method: string
  source: KnowledgeSource
  route?: KnowledgeHistoricalRoute | null
  guidance?: KnowledgeGuidance | null
  capability?: KnowledgeCapability | null
  relationships?: KnowledgeRelationships | null
  data_warnings?: string[]
}

export interface KnowledgeSearchRequest {
  project_id?: number
  query: string
  top_k?: number
  context?: Record<string, string | number | null>
}

export interface KnowledgeSearchResponse {
  status: 'ok' | 'no_evidence' | 'llm_unavailable' | 'insufficient_evidence'
  message: string
  answer: string
  items: KnowledgeSearchItem[]
  intent?: 'capability' | 'general' | string
  relationship_gaps?: string[]
  resource_summary?: KnowledgeResourceSummary | null
}

export interface KnowledgeResourceSummaryItem {
  id?: string | null
  name: string
  model?: string | null
  count?: number | null
  unique_count?: number | null
  sources?: Array<string | KnowledgeSource>
  fields?: Record<string, unknown>
  data_warnings?: string[]
}

export interface KnowledgeResourceSummary {
  scope: 'history' | 'catalog' | string
  record_count: number
  unique_count?: number | null
  equipment_count?: number
  equipment?: KnowledgeResourceSummaryItem[]
  tool_count?: number
  tool?: KnowledgeResourceSummaryItem[]
  gauge_count?: number
  gauge?: KnowledgeResourceSummaryItem[]
  history_count?: number
  history?: KnowledgeResourceSummaryItem[]
}

export interface KnowledgeEvidenceCreate {
  project_id?: number
  route_version_id?: number
  segment_id?: string | null
  query: string
  item_id: string
  content: string
  document_id?: string | null
  document_name?: string | null
  page_no?: number | null
  identity?: string | null
  retrieval_method?: string
}

export interface KnowledgeEvidence extends KnowledgeEvidenceCreate {
  id: number
  snapshot_hash: string
  retrieved_at: string
}

export type KnowledgeSuggestionStatus = 'draft' | 'pending_review' | 'confirmed' | 'rejected' | 'stale'

export interface KnowledgeSuggestion {
  id: number
  project_id?: number | null
  route_version_id?: number | null
  segment_id?: string | null
  title: string
  suggestion_text: string
  candidate?: Record<string, unknown> | null
  evidence_ids: number[]
  status: KnowledgeSuggestionStatus
  created_by: string
  updated_by: string
  created_at: string
  updated_at: string
}

export interface KnowledgeSuggestionCreate {
  project_id?: number
  route_version_id?: number
  segment_id?: string | null
  title?: string
  suggestion_text: string
  candidate?: Record<string, unknown> | null
  evidence_ids: number[]
  created_by?: string
}

export interface KnowledgeSuggestionUpdate {
  title?: string
  suggestion_text?: string
  candidate?: Record<string, unknown> | null
  evidence_ids?: number[]
  status?: KnowledgeSuggestionStatus
  updated_by?: string
}

export interface KnowledgeSuggestionListFilters {
  route_version_id?: number
  segment_id?: string
  status?: KnowledgeSuggestionStatus
}

export async function searchKnowledge(
  request: KnowledgeSearchRequest,
): Promise<KnowledgeSearchResponse> {
  const response = await api.post<KnowledgeSearchResponse>('/api/knowledge/search', request)
  return response.data
}

export type KnowledgeCatalogSection = 'knowledge' | 'resources'
export interface KnowledgeCatalogRequest {
  section: KnowledgeCatalogSection
  category?: string
  topic?: string
  q?: string
  sort?: 'title_asc' | 'title_desc'
  page?: number
  page_size?: number
}
export interface KnowledgeCatalogRow {
  id: string
  title: string
  category: string
  source_kind: string
  source_label: string
  verification_status: string
  data_warnings: string[]
  values: Record<string, string>
}
export interface KnowledgeCatalogResponse {
  section: KnowledgeCatalogSection
  total: number
  raw_count: number
  page: number
  page_size: number
  categories: Array<{ value: string; label: string; count: number }>
  topics: Array<{ value: string; label: string; count: number }>
  columns: Array<{ key: string; label: string }>
  items: KnowledgeCatalogRow[]
}
export interface KnowledgeCatalogDetail extends KnowledgeCatalogRow {
  fields: Record<string, unknown>
  sources: KnowledgeSource[]
  guidance?: KnowledgeGuidance | null
  original_records: Array<Record<string, unknown>>
}
export async function listKnowledgeCatalog(params: KnowledgeCatalogRequest): Promise<KnowledgeCatalogResponse> {
  return (await api.get<KnowledgeCatalogResponse>('/api/knowledge/catalog', { params })).data
}
export async function getKnowledgeCatalogRecord(recordId: string): Promise<KnowledgeCatalogDetail> {
  return (await api.get<KnowledgeCatalogDetail>('/api/knowledge/catalog/record', { params: { record_id: recordId } })).data
}

export async function saveKnowledgeEvidence(
  request: KnowledgeEvidenceCreate,
): Promise<KnowledgeEvidence> {
  const response = await api.post<KnowledgeEvidence>('/api/knowledge/evidence', request)
  return response.data
}

export async function listKnowledgeEvidence(projectId?: number): Promise<KnowledgeEvidence[]> {
  const response = await api.get<KnowledgeEvidence[]>('/api/knowledge/evidence', {
    params: projectId ? { project_id: projectId } : undefined,
  })
  return response.data
}

export async function createKnowledgeSuggestion(
  request: KnowledgeSuggestionCreate,
): Promise<KnowledgeSuggestion> {
  const response = await api.post<KnowledgeSuggestion>('/api/knowledge/suggestions/draft', request)
  return response.data
}

export async function listKnowledgeSuggestions(
  projectId: number,
  filters: KnowledgeSuggestionListFilters = {},
): Promise<KnowledgeSuggestion[]> {
  const response = await api.get<KnowledgeSuggestion[]>('/api/knowledge/suggestions', {
    params: { project_id: projectId, ...filters },
  })
  return response.data
}

export async function updateKnowledgeSuggestion(
  suggestionId: number,
  request: KnowledgeSuggestionUpdate,
): Promise<KnowledgeSuggestion> {
  const response = await api.patch<KnowledgeSuggestion>(
    `/api/knowledge/suggestions/${suggestionId}`,
    request,
  )
  return response.data
}
