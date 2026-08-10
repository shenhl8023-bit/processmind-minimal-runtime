import { api } from './client'
import { clearAllWorkflowDataCache } from '@/composables/workflowDataCache'
import type { ApiRecord } from './dto'
import type { TemplateGroupAliasBinding } from './extract'

export interface GeneratedRouteStep {
  process_id?: string
  sequence?: number | null
  name: string
  op_type: 'MAIN' | 'BRANCH' | string
  reason: string
  process_steps?: string[]
  template_group_aliases?: TemplateGroupAliasBinding[]
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
  expected_workflow_revision: number
  factor_values: ApiRecord
  expected_rule_package_id?: number
  expected_rule_package_version?: number
  expected_rule_package_hash?: string
}) {
  const { data } = await api.post('/api/generate/', body)
  clearAllWorkflowDataCache()
  return data as GenerateRouteResult
}
