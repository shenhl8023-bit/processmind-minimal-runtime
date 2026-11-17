import { api } from './client'
import type { FinalizedRulePackageResult, saveFinalizedRulePackage } from './extract'
import type { GenerateRouteResult } from './generate'
import { clearWorkflowProjectDataCache } from '@/composables/workflowDataCache'

export interface ExecutableRuleRevision {
  id: number
  project_id: number
  route_version_id: number
  revision: number
  content_hash: string
  package: { manifest: Record<string, any>; factor_dictionary: Record<string, any>; input_schema: Record<string, any>; route_catalog: Record<string, any>; route_rules: Record<string, any>; test_cases: any[] }
  validation: Record<string, any>
  generation_ready: boolean
  has_current_generation: boolean
}
const base = '/api/extract/executable-rule-revisions'
export async function getLatestExecutableRuleRevision(projectId: number): Promise<ExecutableRuleRevision | null> {
  try { return (await api.get(`${base}/latest`, { params: { project_id: projectId } })).data }
  catch (e: any) { if (e?.response?.status === 404) return null; throw e }
}
export async function saveExecutableRuleRevision(payload: Parameters<typeof saveFinalizedRulePackage>[0], expectedRevision: number): Promise<ExecutableRuleRevision> {
  const { data } = await api.post(base, { ...payload, expected_executable_revision: expectedRevision })
  clearWorkflowProjectDataCache(payload.project_id)
  return data
}
export async function getCurrentGenerationResults(projectId: number): Promise<{ executable_revision_id: number; revision: number; content_hash: string; results: GenerateRouteResult[] }> {
  return (await api.get('/api/generate/results', { params: { project_id: projectId } })).data
}
export async function exportExecutableRuleRevision(revisionId: number, payload: {
  project_id: number; expected_workflow_revision: number; expected_content_hash: string
  include_template_mapping: boolean; template_mapping?: { expected_template_revision: number; mappings: any[]; operations: any[]; replace_all: boolean; hidden_step_keys?: string[]; waived_group_paths?: string[][] }
}): Promise<FinalizedRulePackageResult> {
  const { data } = await api.post(`${base}/${revisionId}/export`, payload)
  clearWorkflowProjectDataCache(payload.project_id)
  return data
}
