import { api } from './client'

export interface Setting {
  id: number
  key: string
  value: string
  description?: string | null
  updated_at: string
  is_secret?: boolean
  is_configured?: boolean
}

export interface LLMTestRequest {
  api_url: string
  api_key: string
  model?: string
}

export interface LLMSettingsRequest {
  api_url: string
  model: string
  api_key?: string
}

export interface LLMModelsRequest {
  api_url: string
  api_key: string
}

export interface LLMTestResult {
  success: boolean
  message: string
  code?: string
}

export interface LLMModel {
  id: string
  name: string
}

export async function listSettings() {
  const { data } = await api.get('/api/settings')
  return data as Setting[]
}

export async function updateSetting(key: string, value: string) {
  const { data } = await api.post('/api/settings', { key, value })
  return data as Setting
}

export async function saveLLMSettings(payload: LLMSettingsRequest) {
  const { data } = await api.post('/api/settings/llm', payload)
  return data as Setting[]
}

export async function clearSetting(key: string) {
  const { data } = await api.delete(`/api/settings/${encodeURIComponent(key)}`)
  return data as Setting
}

export async function testLLMConnection(payload: LLMTestRequest) {
  const { data } = await api.post('/api/settings/test-connection', payload)
  return data as LLMTestResult
}

export async function getAvailableModels(payload?: LLMModelsRequest) {
  const { data } = payload
    ? await api.post('/api/settings/models', payload)
    : await api.get('/api/settings/models')
  return data as LLMModel[]
}
