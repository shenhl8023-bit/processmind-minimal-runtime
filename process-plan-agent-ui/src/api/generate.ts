import { api } from './client'
import { clearAllWorkflowDataCache } from '@/composables/workflowDataCache'
import type { GroupTemplateMappingOutputProcess, TemplateGroupAliasBinding } from './extract'

export interface GeneratedRouteStep {
  process_id?: string
  sequence?: number | null
  name: string
  phase?: string
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
  full_route_structure?: GroupTemplateMappingOutputProcess[]
  output_mode: string
  rule_package_id?: number | null
  rule_package_version?: number | null
  rule_package_hash?: string | null
  schema_version?: string | null
  matched_rule_ids?: string[]
  selected_process_ids?: string[]
  input_metadata?: Record<string, GenerateInputMetadata>
}

export type GenerateInputMetadata = {
  origin: 'unset' | 'extracted' | 'manual' | 'example'
  unit?: string
  evidence: string[]
}

export async function generateRoute(body: {
  project_id: number
  expected_workflow_revision: number
  factor_values: Record<string, any>
  input_metadata?: Record<string, GenerateInputMetadata>
}) {
  const { data } = await api.post('/api/generate/', body)
  clearAllWorkflowDataCache()
  return data as GenerateRouteResult
}
