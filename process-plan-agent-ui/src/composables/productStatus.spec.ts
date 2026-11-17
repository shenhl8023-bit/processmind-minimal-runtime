import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import 'vue'

const full = { edition: 'full', template_mapping_enabled: true, expires_at: null, expired: false, server_time: '2026-12-30T15:59:59Z' }
const trial = { ...full, edition: 'basic-trial', template_mapping_enabled: false, expires_at: '2026-12-31T00:00:00+08:00' }

beforeEach(() => {
  vi.resetModules(); vi.useFakeTimers()
  vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'basic-trial' }) })
})
afterEach(() => { vi.clearAllTimers(); vi.useRealTimers(); vi.unstubAllGlobals() })

describe('product status access state', () => {
  it('loads full visibility independently of license capabilities and without trial timers', async () => {
    vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'full' }) })
    const state = await import('./productStatus')
    await state.loadProductStatus(async () => ({ ...full, template_mapping_enabled: false }))
    expect(state.productStatus.value?.template_mapping_enabled).toBe(false)
    expect(state.templateMappingVisible.value).toBe(false)
    expect(state.templateMappingEnabled.value).toBe(true)
    expect(state.knowledgeLibraryEnabled.value).toBe(true)
    expect(state.productAccess.value).toBe('ready')
    expect(vi.getTimerCount()).toBe(0)
    await state.loadProductStatus(async () => full)
    expect(state.templateMappingVisible.value).toBe(true)
    state.markTrialExpired()
    expect(state.productAccess.value).toBe('ready')
  })

  it.each([{}, { ...full, edition: 'basic-trial', expires_at: '2026-12-31T00:00:00+08:00' }, { ...full, expired: true }])(
    'retains the last full visibility without adding restrictions after invalid status %j', async invalid => {
      vi.stubGlobal('document', { querySelector: () => ({ getAttribute: () => 'full' }) })
      const state = await import('./productStatus')
      await state.loadProductStatus(async () => ({ ...full, template_mapping_enabled: false }))
      await state.loadProductStatus(async () => invalid)
      await state.loadProductStatus(async () => { throw new Error('offline') })
      expect(state.templateMappingVisible.value).toBe(false)
      expect(state.templateMappingEnabled.value).toBe(true)
      expect(state.productAccess.value).toBe('ready')
      expect(vi.getTimerCount()).toBe(0)
    },
  )

  it('starts closed and opens full only after successful status initialization', async () => {
    const state = await import('./productStatus')
    expect(state.productAccess.value).toBe('loading')
    let finish!: (value: unknown) => void
    const pending = state.loadProductStatus(() => new Promise(resolve => { finish = resolve }) as any)
    expect(state.productAccess.value).toBe('loading')
    finish(full)
    await pending
    expect(state.productAccess.value).toBe('ready')
    expect(state.templateMappingEnabled.value).toBe(true)
    await vi.advanceTimersByTimeAsync(2000)
    expect(state.productAccess.value).toBe('ready')
  })

  it('blocks business after a failed request and permits retry', async () => {
    const state = await import('./productStatus')
    await state.loadProductStatus(async () => { throw new Error('offline') })
    expect(state.productAccess.value).toBe('error')
    await state.loadProductStatus(async () => trial as any)
    expect(state.productAccess.value).toBe('ready')
    expect(state.templateMappingEnabled.value).toBe(false)
  })

  it.each([{}, { ...trial, server_time: 'bad' }, { ...trial, expires_at: null }, { ...full, edition: 'unknown' }, { ...full, expired: 'false' }])(
    'fails closed on malformed status %j', async invalid => {
      const state = await import('./productStatus')
      await state.loadProductStatus(async () => invalid as any)
      expect(state.productAccess.value).toBe('error')
    },
  )

  it('locks at the Beijing expiry boundary using server time despite a different client date', async () => {
    vi.setSystemTime(new Date('2025-01-01T00:00:00Z'))
    const state = await import('./productStatus')
    await state.loadProductStatus(async () => trial as any)
    await vi.advanceTimersByTimeAsync(999)
    expect(state.productAccess.value).toBe('ready')
    await vi.advanceTimersByTimeAsync(1)
    expect(state.productAccess.value).toBe('expired')
  })

  it('locks immediately at expiry even if expired is incorrectly false', async () => {
    const state = await import('./productStatus')
    await state.loadProductStatus(async () => ({ ...trial, server_time: '2026-12-30T16:00:00Z' }) as any)
    expect(state.productAccess.value).toBe('expired')
  })

  it('never unlocks a backend expiry notification with an in-flight status response', async () => {
    const state = await import('./productStatus')
    let finish!: (value: unknown) => void
    const pending = state.loadProductStatus(() => new Promise(resolve => { finish = resolve }) as any)
    state.markTrialExpired()
    finish(full)
    await pending
    expect(state.productAccess.value).toBe('expired')
  })

  it('ignores an older status response after a successful retry', async () => {
    const state = await import('./productStatus')
    let finish!: (value: unknown) => void
    const pending = state.loadProductStatus(() => new Promise(resolve => { finish = resolve }) as any)
    await state.loadProductStatus(async () => trial as any)
    finish(full)
    await pending
    expect(state.templateMappingEnabled.value).toBe(false)
  })

  it('handles long trial deadlines without overflowing the browser timer', async () => {
    const state = await import('./productStatus')
    await state.loadProductStatus(async () => ({ ...trial, server_time: '2026-10-30T00:00:00Z' }) as any)
    await vi.advanceTimersByTimeAsync(2147483647)
    expect(state.productAccess.value).toBe('ready')
    await vi.advanceTimersByTimeAsync(2147483647)
    expect(state.productAccess.value).toBe('ready')
    await vi.advanceTimersByTimeAsync(1033032706)
    expect(state.productAccess.value).toBe('expired')
  })
})
