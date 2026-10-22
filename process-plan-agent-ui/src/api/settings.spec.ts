import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), delete: vi.fn() }))

vi.mock('@/api/client', () => ({ api: apiMocks }))

import { clearSetting, testLLMConnection } from './settings'

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
