import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import 'vue'

beforeEach(() => {
  vi.resetModules()
  vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'basic-trial' }) })
})
afterEach(() => { vi.clearAllTimers(); vi.unstubAllGlobals() })

describe('business expiry response interceptor', () => {
  it('locks the product on a trial_expired 403 while preserving the rejection', async () => {
    const { api } = await import('./client')
    const state = await import('@/composables/productStatus')
    const failure = { response: { status: 403, data: { detail: { code: 'trial_expired', message: '试用已到期，请联系供应方。' } } } }
    api.defaults.adapter = async () => { throw failure }
    await expect(api.get('/api/projects')).rejects.toBe(failure)
    expect(state.productAccess.value).toBe('expired')
  })

  it('does not treat feature_disabled as trial expiry', async () => {
    const { api } = await import('./client')
    const state = await import('@/composables/productStatus')
    const failure = { response: { status: 403, data: { detail: { code: 'feature_disabled' } } } }
    api.defaults.adapter = async () => { throw failure }
    await expect(api.get('/api/group-template')).rejects.toBe(failure)
    expect(state.productAccess.value).not.toBe('expired')
  })
})
