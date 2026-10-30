import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import source from './ModelSettingsDrawer.vue?raw'

const api = { listSettings: vi.fn(), updateSetting: vi.fn(), clearSetting: vi.fn(), testLLMConnection: vi.fn(), getAvailableModels: vi.fn() }
const script = compileScript(parse(source).descriptor, { id: 'model-settings-qa' })
const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
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
function mount() {
  const props = Vue.reactive({ modelValue: false, projectId: 1 })
  let model: any
  app = renderer.createApp({ setup() { model = module.exports.default.setup(props, { expose() {}, emit() {} }); return () => null } })
  app.mount({})
  return { model, props }
}
function deferred<T>() { let resolve!: (v: T) => void; const promise = new Promise<T>(r => { resolve = r }); return { resolve, promise } }
function settings(url: string) { return [
  { key: 'LLM_API_URL', value: url }, { key: 'LLM_MODEL', value: 'demo' },
  { key: 'LLM_API_KEY', value: '', is_secret: true, is_configured: true },
] }
beforeEach(() => {
  vi.resetAllMocks()
  vi.useFakeTimers()
  api.listSettings.mockResolvedValue(settings('https://example.test/v1'))
  api.getAvailableModels.mockResolvedValue([])
  api.updateSetting.mockResolvedValue({})
})
afterEach(() => { app?.unmount(); vi.useRealTimers() })

describe('model settings sessions', () => {
  it('waits for every setting write even when one request fails early', async () => {
    const slowModel = deferred<any>()
    api.updateSetting.mockImplementation((key: string) => key === 'LLM_API_URL' ? Promise.reject(new Error('offline')) : slowModel.promise)
    const { model, props } = mount()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick(); await Vue.nextTick()
    const saving = model.saveSettings()
    await Vue.nextTick(); await Vue.nextTick()
    props.modelValue = false
    await Vue.nextTick()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick()
    expect(model.settingsLoaded.value).toBe(false)
    expect(api.listSettings).toHaveBeenCalledTimes(1)
    slowModel.resolve({})
    await saving
    await Vue.nextTick(); await Vue.nextTick()
    expect(api.listSettings).toHaveBeenCalledTimes(2)
  })
  it('waits for an earlier save before loading a reopened form', async () => {
    const saved = deferred<any>()
    api.updateSetting.mockReturnValue(saved.promise)
    const { model, props } = mount()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick(); await Vue.nextTick()
    const saving = model.saveSettings()
    props.modelValue = false
    await Vue.nextTick()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick()
    expect(model.settingsLoaded.value).toBe(false)
    expect(api.listSettings).toHaveBeenCalledTimes(1)
    api.listSettings.mockResolvedValue(settings('https://new.test/v1'))
    saved.resolve({})
    await saving
    await Vue.nextTick(); await Vue.nextTick(); await Vue.nextTick()
    expect(model.form.value.LLM_API_URL).toBe('https://new.test/v1')
  })
  it('discards an unsaved secret on close and blocks saving when the reopened load fails', async () => {
    const { model, props } = mount()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick(); await Vue.nextTick()
    model.form.value.LLM_API_KEY = 'unsaved-secret'
    model.showKey.value = true
    model.handleClose()
    props.modelValue = false
    await Vue.nextTick()
    api.listSettings.mockRejectedValue(new Error('offline'))
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick()
    expect(model.form.value.LLM_API_KEY).toBe('')
    expect(model.showKey.value).toBe(false)
    await model.saveSettings()
    expect(api.updateSetting).not.toHaveBeenCalled()
  })
  it('keeps a newly reopened form when the previous load completes last', async () => {
    const old = deferred<any[]>()
    api.listSettings.mockReturnValueOnce(old.promise).mockResolvedValueOnce(settings('https://new.test/v1'))
    const { model, props } = mount()
    props.modelValue = true
    await Vue.nextTick()
    props.modelValue = false
    await Vue.nextTick()
    props.modelValue = true
    await Vue.nextTick()
    await Vue.nextTick()
    old.resolve(settings('https://old.test/v1'))
    await Vue.nextTick()
    await Vue.nextTick()
    expect(model.form.value.LLM_API_URL).toBe('https://new.test/v1')
  })

  it('does not close a reopened form from an earlier save timer', async () => {
    const { model, props } = mount()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick(); await Vue.nextTick()
    await model.saveSettings()
    props.modelValue = false
    await Vue.nextTick()
    props.modelValue = true
    await Vue.nextTick(); await Vue.nextTick()
    await vi.advanceTimersByTimeAsync(1600)
    expect(model.visible.value).toBe(true)
  })

  it('rejects a URL without a hostname before sending a model request', async () => {
    const { model } = mount()
    await model.loadSettings()
    model.form.value = { LLM_API_URL: 'https://?bad', LLM_API_KEY: 'test-key', LLM_MODEL: 'demo' }
    await model.testConnection()
    expect(model.errors.value.LLM_API_URL).not.toBe('')
    expect(api.testLLMConnection).not.toHaveBeenCalled()
  })

  it('shows a recoverable error when loading settings fails', async () => {
    api.listSettings.mockRejectedValue(new Error('offline'))
    const { model } = mount()
    await model.loadSettings()
    expect(model.saveStatus.value?.type).toBe('error')
  })
})
