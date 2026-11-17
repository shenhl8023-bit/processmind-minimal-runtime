import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), delete: vi.fn() }))

vi.mock('@/api/client', () => ({ api: apiMocks }))

import { clearSetting, testLLMConnection } from './settings'
import * as settings from './settings'

describe('settings API contracts', () => {
  beforeEach(() => {
    apiMocks.post.mockReset()
    apiMocks.delete.mockReset()
  })

  it('tests a model using the supplied configuration', async () => {
    apiMocks.post.mockResolvedValueOnce({ data: { success: true, message: '连接成功' } })

    const result = await testLLMConnection({
      api_url: 'https://example.test/v1',
      api_key: '__use_saved__',
      model: 'demo-model',
    })

    expect(result.success).toBe(true)
    expect(apiMocks.post).toHaveBeenCalledWith('/api/settings/test-connection', {
      api_url: 'https://example.test/v1',
      api_key: '__use_saved__',
      model: 'demo-model',
    })
  })

  it('clears a saved API key through the explicit clear endpoint', async () => {
    apiMocks.delete.mockResolvedValueOnce({ data: { key: 'LLM_API_KEY', is_configured: false } })

    const result = await clearSetting('LLM_API_KEY')

    expect(result.is_configured).toBe(false)
    expect(apiMocks.delete).toHaveBeenCalledWith('/api/settings/LLM_API_KEY')
  })
})

describe('model settings request contracts', () => {
  beforeEach(() => vi.resetAllMocks())
  it('posts the draft endpoint and credential for model suggestions', async () => {
    apiMocks.post.mockResolvedValue({ data: [{ id: 'draft-model', name: 'Draft model' }] })
    apiMocks.get.mockResolvedValue({ data: [{ id: 'saved-model', name: 'Saved model' }] })
    const models = await settings.getAvailableModels({ api_url: 'https://draft.test/v1', api_key: 'draft-key' })
    expect(models).toEqual([{ id: 'draft-model', name: 'Draft model' }])
    expect(apiMocks.post).toHaveBeenCalledWith('/api/settings/models', { api_url: 'https://draft.test/v1', api_key: 'draft-key' })
    expect(apiMocks.get).not.toHaveBeenCalled()
  })

  it('retains the legacy GET when no draft is provided', async () => {
    apiMocks.get.mockResolvedValue({ data: [] })
    expect(await settings.getAvailableModels()).toEqual([])
    expect(apiMocks.get).toHaveBeenCalledWith('/api/settings/models')
  })

  it('saves a complete configuration with exactly one atomic request and returns masked settings', async () => {
    const masked = [{ key: 'LLM_API_KEY', value: '', is_configured: true, is_secret: true }]
    apiMocks.post.mockResolvedValue({ data: masked })
    expect(settings.saveLLMSettings).toBeTypeOf('function')
    expect(await settings.saveLLMSettings({ api_url: 'https://draft.test/v1', model: 'draft-model', api_key: 'draft-key' })).toEqual(masked)
    expect(apiMocks.post.mock.calls).toEqual([['/api/settings/llm', { api_url: 'https://draft.test/v1', model: 'draft-model', api_key: 'draft-key' }]])
  })

  it('omits a replacement credential when preserving the saved key', async () => {
    apiMocks.post.mockResolvedValue({ data: [] })
    expect(settings.saveLLMSettings).toBeTypeOf('function')
    await settings.saveLLMSettings({ api_url: 'https://draft.test/v1', model: 'draft-model' })
    expect(apiMocks.post).toHaveBeenCalledWith('/api/settings/llm', { api_url: 'https://draft.test/v1', model: 'draft-model' })
  })
})
