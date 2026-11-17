import { api } from './client'

export interface OperationRecommendation {
  mode: 'mainline' | 'manual' | 'condition' | 'relation'
  basis?: 'feature' | 'precision' | 'roughness' | 'material' | 'hardness' | 'requirement'
  features?: string[]
  direction?: string
  materials?: string[]
  it_threshold?: number
  ra_threshold?: number
  source_operation_name?: string
  source_segment_id?: string
}
export interface AnalysisGuidanceConfiguration {
  schema_version: '1.0'
  revision: number
  feature_mappings: Record<string, string[]>
  directions: string[]
  materials: string[]
  operation_guidance: Record<string, {
    feature_group?: string; recommendation?: OperationRecommendation; instruction?: string
    questions?: Record<string, { prompt: string; option_labels?: Record<string, string> }>
    recommendation_issues?: string[]
    recommendation_reference_blocked?: boolean
  }>
  guidance: string
  generation_version?: string
  generation_route_id?: number
  generation_operation_ids?: Record<string, string>
}
export interface AnalysisGuidanceResult {
  project_id: number
  configuration: AnalysisGuidanceConfiguration
  prompt_reference?: string
}
export async function getAnalysisGuidance(projectId: number): Promise<AnalysisGuidanceResult> {
  return (await api.get(`/api/projects/${projectId}/analysis-guidance`)).data
}
export async function generateAnalysisGuidance(projectId: number, retryRecommendations = false): Promise<AnalysisGuidanceResult> {
  return (await api.post(`/api/projects/${projectId}/analysis-guidance/generate`, {}, {
    timeout: 180000,
    ...(retryRecommendations ? { params: { retry_recommendations: true } } : {}),
  })).data
}
export async function saveAnalysisGuidance(projectId: number, configuration: AnalysisGuidanceConfiguration): Promise<AnalysisGuidanceResult> {
  return (await api.put(`/api/projects/${projectId}/analysis-guidance`, { expected_configuration_revision: configuration.revision, configuration })).data
}
