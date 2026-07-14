import { api } from './client'

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
}

export async function generateRoute(body: {
  project_id: number
  factor_values: Record<string, any>
}) {
  const { data } = await api.post('/api/generate/', body)
  return data as GenerateRouteResult
}
