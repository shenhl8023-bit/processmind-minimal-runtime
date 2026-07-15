import { api } from './client'
import { clearAllWorkflowDataCache } from '@/composables/workflowDataCache'

export interface GeneratedRouteStep {
  process_id?: string
  sequence?: number | null
  name: string
  op_type: 'MAIN' | 'BRANCH' | string
  reason: string
  process_steps?: string[]
}

export interface GenerateRouteResult {
  id?: number | null
  steps: GeneratedRouteStep[]
  summary: string
  output_json_text?: string | null
  output_mode: string
  rule_package_id?: number | null
  rule_package_version?: number | null
  rule_package_hash?: string | null
  schema_version?: string | null
  matched_rule_ids?: string[]
  selected_process_ids?: string[]
}

export async function generateRoute(body: {
  project_id: number
  factor_values: Record<string, any>
}) {
  const { data } = await api.post('/api/generate/', body)
  clearAllWorkflowDataCache()
  return data as GenerateRouteResult
}
