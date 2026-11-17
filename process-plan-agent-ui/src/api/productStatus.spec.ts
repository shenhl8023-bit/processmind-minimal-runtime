import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import 'vue'
import type { InternalAxiosRequestConfig } from 'axios'

beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers()
  vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'basic-trial' }) })
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('product status server synchronization', () => {
  it('periodically checks status and refreshes on focus or returning to the page', async () => {
    const browser = Object.assign(new EventTarget(), { setInterval, clearInterval })
    const document = Object.assign(new EventTarget(), { visibilityState: 'visible' })
    const { api } = await import('./client')
    const { refreshProductStatus, startProductStatusSync } = await import('./productStatus')
    const { productAccess } = await import('@/composables/productStatus')
    vi.stubGlobal('window', browser)
    vi.stubGlobal('document', document)
    const adapter = vi.fn(async (config: InternalAxiosRequestConfig) => ({ data: { edition: 'full', template_mapping_enabled: true, expires_at: null, expired: false, server_time: '2026-10-30T00:00:00Z' }, status: 200, statusText: 'OK', headers: {}, config }))
    api.defaults.adapter = adapter
    await refreshProductStatus()
    expect(adapter.mock.calls[0]![0].url).toBe('/api/product-status')
    expect(productAccess.value).toBe('ready')
    const stop = startProductStatusSync()
    await vi.advanceTimersByTimeAsync(30000)
    expect(adapter).toHaveBeenCalledTimes(2)
    browser.dispatchEvent(new Event('focus'))
    await refreshProductStatus()
    expect(adapter).toHaveBeenCalledTimes(3)
    document.dispatchEvent(new Event('visibilitychange'))
    await refreshProductStatus()
    expect(adapter).toHaveBeenCalledTimes(4)
    stop()
    browser.dispatchEvent(new Event('focus'))
    await vi.advanceTimersByTimeAsync(30000)
    expect(adapter).toHaveBeenCalledTimes(4)
  })
})

describe('full edition without trial checks', () => {
  it('reads full feature visibility once while staying usable without polling or expiry checks', async () => {
    const browser = Object.assign(new EventTarget(), { setInterval, clearInterval })
    const document = Object.assign(new EventTarget(), {
      visibilityState: 'visible', querySelector: () => ({ getAttribute: () => 'full' }),
    })
    vi.stubGlobal('document', document)
    const { api } = await import('./client')
    const { refreshProductStatus, startProductStatusSync } = await import('./productStatus')
    const state = await import('@/composables/productStatus')
    vi.stubGlobal('window', browser)
    const adapter = vi.fn(async () => { throw new Error('status service unavailable') })
    api.defaults.adapter = adapter

    expect(state.productAccess.value).toBe('ready')
    await refreshProductStatus()
    const stop = startProductStatusSync()
    await vi.advanceTimersByTimeAsync(60000)
    browser.dispatchEvent(new Event('focus'))
    document.dispatchEvent(new Event('visibilitychange'))
    await refreshProductStatus()

    expect(adapter).toHaveBeenCalledTimes(2)
    expect(vi.getTimerCount()).toBe(0)
    expect(state.productAccess.value).toBe('ready')
    expect(state.templateMappingEnabled.value).toBe(true)
    expect(state.knowledgeLibraryEnabled.value).toBe(true)
    state.markTrialExpired()
    expect(state.productAccess.value).toBe('ready')
    stop()
  })

  it('applies the full deployment visibility returned by the status API', async () => {
    vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'full' }) })
    const { api } = await import('./client')
    const { refreshProductStatus } = await import('./productStatus')
    const state = await import('@/composables/productStatus')
    api.defaults.adapter = async (config: InternalAxiosRequestConfig) => ({
      data: { edition: 'full', template_mapping_enabled: false, expires_at: null, expired: false, server_time: '2026-11-16T00:00:00Z' },
      status: 200, statusText: 'OK', headers: {}, config,
    })
    await refreshProductStatus()
    expect(state.templateMappingVisible.value).toBe(false)
    expect(state.templateMappingEnabled.value).toBe(true)
    expect(state.productAccess.value).toBe('ready')
  })
})
