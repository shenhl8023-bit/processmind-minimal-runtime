import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import source from './SettingsView.vue?raw'

const api = { listSettings: vi.fn(), saveLLMSettings: vi.fn(), updateSetting: vi.fn(), clearSetting: vi.fn(), testLLMConnection: vi.fn() }
const compiled = compileScript(parse(source).descriptor, { id: 'settings-functional-test' })
const code = transformSync(compiled.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const module = { exports: {} as any }
new Function('require', 'module', 'exports', code)((id: string) => {
  if (id === 'vue') return Vue
  if (id === '@/api') return api
  throw new Error(id)
}, module, module.exports)
const renderer = Vue.createRenderer({
  createComment: () => ({}), insert: () => {}, remove: () => {}, parentNode: () => null, nextSibling: () => null,
} as any)
let app: ReturnType<typeof renderer.createApp> | undefined
async function mount() {
  let model: any
  app = renderer.createApp({ setup() { model = module.exports.default.setup({}, { expose() {} }); return () => null } })
  app.mount({})
  for (let i = 0; i < 8; i++) await Vue.nextTick()
  return model
}
function settings(configured = true) { return [
  { key: 'LLM_API_URL', value: 'https://example.test/v1' }, { key: 'LLM_MODEL', value: 'demo' },
  { key: 'LLM_API_KEY', value: '', is_secret: true, is_configured: configured },
] }
afterEach(() => app?.unmount())
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  vi.resetAllMocks()
  api.updateSetting.mockResolvedValue({})
  api.saveLLMSettings.mockResolvedValue(settings())
  api.listSettings.mockResolvedValue(settings())
  api.clearSetting.mockResolvedValue({})
})

describe('settings in-flight save boundaries', () => {
  it('preserves a new API key typed while an earlier key is being saved', async () => {
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    const model = await mount()
    model.form.value.LLM_API_KEY = 'submitted-test-key'
    const saving = model.saveSettings()
    model.form.value.LLM_API_KEY = 'new-unsaved-test-key'
    saved.resolve(settings())
    await saving
    expect(model.form.value.LLM_API_KEY).toBe('new-unsaved-test-key')
    expect(model.hasStoredKey.value).toBe(true)
  })

  it('keeps the key draft unconfigured after an atomic save fails', async () => {
    api.listSettings.mockResolvedValue(settings(false))
    api.saveLLMSettings.mockRejectedValue({ response: { data: { detail: { code: 'save_failed', message: 'Atomic save failed' } } } })
    const model = await mount()
    model.form.value.LLM_API_KEY = 'submitted-test-key'
    await model.saveSettings()
    expect(model.hasStoredKey.value).toBe(false)
    expect(model.form.value.LLM_API_KEY).toBe('submitted-test-key')
    expect(model.saveStatus.value).toEqual({ type: 'error', msg: 'Atomic save failed' })
    expect(model.saving.value).toBe(false)
  })

  it('preserves a new key draft typed while clearing the saved key', async () => {
    const cleared = deferred<any>()
    api.clearSetting.mockReturnValue(cleared.promise)
    const model = await mount()
    model.hasStoredKey.value = true
    const clearing = model.clearApiKey()
    model.form.value.LLM_API_KEY = 'new-unsaved-test-key'
    cleared.resolve({})
    await clearing
    expect(model.form.value.LLM_API_KEY).toBe('new-unsaved-test-key')
    expect(model.hasStoredKey.value).toBe(false)
  })

  it('prevents a second save or clear from racing an in-flight save', async () => {
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    const model = await mount()
    model.hasStoredKey.value = true
    const saving = model.saveSettings()
    const secondSave = model.saveSettings()
    const clearing = model.clearApiKey()
    expect(api.saveLLMSettings).toHaveBeenCalledTimes(1)
    expect(api.clearSetting).not.toHaveBeenCalled()
    saved.resolve(settings())
    await Promise.all([saving, secondSave, clearing])
  })
})


describe('settings page draft consistency', () => {
  it('saves a captured and trimmed configuration with one atomic request', async () => {
    const model = await mount()
    model.form.value = { LLM_API_URL: ' https://draft.test/v1 ', LLM_MODEL: ' draft-model ', LLM_API_KEY: ' draft-key ' }
    await model.saveSettings()
    expect(api.saveLLMSettings.mock.calls).toEqual([[{ api_url: 'https://draft.test/v1', model: 'draft-model', api_key: 'draft-key' }]])
    expect(api.updateSetting).not.toHaveBeenCalled()
  })

  it('omits a blank replacement when keeping a saved credential', async () => {
    const model = await mount()
    await model.saveSettings()
    expect(api.saveLLMSettings).toHaveBeenCalledWith({ api_url: 'https://example.test/v1', model: 'demo' })
  })

  it.each(['LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL'])('invalidates a completed test after editing %s', async field => {
    const model = await mount()
    api.testLLMConnection.mockResolvedValue({ success: true, message: 'old-success' })
    await model.testConnection()
    model.form.value[field] += '-edited'
    expect(model.saveStatus.value).toBeNull()
  })

  it.each(['LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL'])('ignores a test when %s is changed and restored before completion', async field => {
    const model = await mount()
    const result = deferred<any>()
    api.testLLMConnection.mockReturnValue(result.promise)
    const testing = model.testConnection()
    const original = model.form.value[field]
    model.form.value[field] = 'changed'
    model.form.value[field] = original
    result.resolve({ success: true, message: 'obsolete-success' })
    await testing
    expect(model.saveStatus.value).toBeNull()
  })

  it('ignores an obsolete test failure while a newer test remains pending', async () => {
    const model = await mount()
    const old = deferred<any>()
    const current = deferred<any>()
    api.testLLMConnection.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const testingOld = model.testConnection()
    model.form.value.LLM_MODEL = 'new-model'
    const testingCurrent = model.testConnection()
    old.resolve({ success: false, message: 'obsolete-failure' })
    await testingOld
    expect(model.testing.value).toBe(true)
    expect(model.saveStatus.value).toBeNull()
    current.resolve({ success: true, message: 'current-success' })
    await testingCurrent
    expect(model.saveStatus.value?.msg).toBe('current-success')
    expect(api.testLLMConnection).toHaveBeenLastCalledWith({ api_url: 'https://example.test/v1', model: 'new-model', api_key: '__use_saved__' })
  })

  it.each(['TLS failed', { code: 'tls_error', message: 'TLS failed' }])('renders a safe string for error detail %j', async detail => {
    const model = await mount()
    api.testLLMConnection.mockRejectedValue({ response: { data: { detail } } })
    await model.testConnection()
    expect(model.saveStatus.value).toEqual({ type: 'error', msg: 'TLS failed' })
  })

  it('retains an edit-back key draft when a pending save completes', async () => {
    const model = await mount()
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    api.updateSetting.mockReturnValue(saved.promise)
    model.form.value.LLM_API_KEY = 'draft-key'
    const saving = model.saveSettings()
    model.form.value.LLM_API_KEY = 'other-key'
    model.form.value.LLM_API_KEY = 'draft-key'
    saved.resolve(settings())
    await saving
    expect(model.form.value.LLM_API_KEY).toBe('draft-key')
    expect(model.saveStatus.value?.msg).toContain('尚未保存')
  })

  it('retains an edit-back key draft when a pending clear completes', async () => {
    const model = await mount()
    const cleared = deferred<any>()
    api.clearSetting.mockReturnValue(cleared.promise)
    model.form.value.LLM_API_KEY = 'draft-key'
    const clearing = model.clearApiKey()
    model.form.value.LLM_API_KEY = 'other-key'
    model.form.value.LLM_API_KEY = 'draft-key'
    cleared.resolve({})
    await clearing
    expect(model.form.value.LLM_API_KEY).toBe('draft-key')
    expect(model.hasStoredKey.value).toBe(false)
  })

  it('prevents a pending test from overwriting a clear or a save', async () => {
    const model = await mount()
    const result = deferred<any>()
    api.testLLMConnection.mockReturnValue(result.promise)
    const testing = model.testConnection()
    await model.clearApiKey()
    await model.saveSettings()
    expect(api.clearSetting).not.toHaveBeenCalled()
    expect(api.saveLLMSettings).not.toHaveBeenCalled()
    result.resolve({ success: true, message: 'test-success' })
    await testing
  })
})
