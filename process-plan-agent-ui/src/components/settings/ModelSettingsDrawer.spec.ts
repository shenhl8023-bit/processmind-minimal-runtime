import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import source from './ModelSettingsDrawer.vue?raw'

const api = { listSettings: vi.fn(), saveLLMSettings: vi.fn(), updateSetting: vi.fn(), clearSetting: vi.fn(), testLLMConnection: vi.fn(), getAvailableModels: vi.fn() }
const renderTemplate = Vue.compile(parse(source).descriptor.template!.content) as (...args: any[]) => any
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
function mount(initiallyOpen = false) {
  const props = Vue.reactive({ modelValue: initiallyOpen, projectId: 1 })
  let model: any
  let view: any
  app = renderer.createApp({
    components: { ElDialog: { render: () => null } },
    setup() {
      model = module.exports.default.setup(props, { expose() {}, emit() {} })
      return () => { view = renderTemplate(Vue.proxyRefs(model), []); return null }
    },
  })
  app.mount({})
  return { model, props, button: (label: string) => {
    const walk = (node: any): any[] => {
      if (Array.isArray(node)) return node.flatMap(walk)
      if (!node || typeof node !== 'object') return []
      const children = typeof node.children === 'object' && !Array.isArray(node.children)
        ? Object.values(node.children || {}).filter(value => typeof value === 'function').flatMap((slot: any) => walk(slot()))
        : walk(node.children)
      return [node, ...children]
    }
    return walk(view).find(node => node.type === 'button' && (node.props?.title === label || walk(node.children).some(child => String(child.children).includes(label))))
  } }
}
async function flush() { for (let i = 0; i < 8; i++) await Vue.nextTick() }
async function open() {
  const mounted = mount()
  mounted.props.modelValue = true
  await flush()
  return mounted
}
function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((done, fail) => { resolve = done; reject = fail })
  return { resolve, reject, promise }
}
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
  api.saveLLMSettings.mockResolvedValue(settings('https://example.test/v1'))
  api.clearSetting.mockResolvedValue({})
})
afterEach(() => { app?.unmount(); vi.useRealTimers() })

describe('model settings sessions', () => {
  it('waits for an earlier save before loading a reopened form', async () => {
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
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
    saved.resolve(settings('https://new.test/v1'))
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
    expect(api.saveLLMSettings).not.toHaveBeenCalled()
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


describe('draft model suggestions and independent feedback', () => {
  it('opens without fetching suggestions or waiting for a model service', async () => {
    api.getAvailableModels.mockReturnValue(new Promise(() => {}))
    const { model } = await open()
    expect(api.getAvailableModels).not.toHaveBeenCalled()
    expect(model.settingsLoaded.value).toBe(true)
    expect(model.loadingSettings.value).toBe(false)
  })

  it('uses the current URL and typed key, then the saved-key sentinel', async () => {
    const { model } = await open()
    model.form.value.LLM_API_URL = ' https://draft.test/v1 '
    model.form.value.LLM_API_KEY = ' draft-key '
    await model.fetchModels()
    expect(api.getAvailableModels).toHaveBeenLastCalledWith({ api_url: 'https://draft.test/v1', api_key: 'draft-key' })
    model.form.value.LLM_API_KEY = ''
    await model.fetchModels()
    expect(api.getAvailableModels).toHaveBeenLastCalledWith({ api_url: 'https://draft.test/v1', api_key: '__use_saved__' })
  })

  it('keeps test and save buttons enabled during a slow model-list request', async () => {
    const { model, button } = await open()
    const list = deferred<any[]>()
    api.getAvailableModels.mockReturnValue(list.promise)
    const fetching = model.fetchModels()
    await flush()
    expect(button('测试连接')?.props.disabled).toBe(false)
    expect(button('保存设置')?.props.disabled).toBe(false)
    list.resolve([])
    await fetching
  })

  it('allows a test during a list request and keeps its feedback after a list failure', async () => {
    const { model } = await open()
    const list = deferred<any[]>()
    api.getAvailableModels.mockReturnValue(list.promise)
    const fetching = model.fetchModels()
    api.testLLMConnection.mockResolvedValue({ success: true, message: 'current-test-passed' })
    await model.testConnection()
    list.resolve([])
    await fetching
    expect(model.saveStatus.value?.msg).toBe('current-test-passed')
    expect(model.modelsStatus.value?.type).toBe('error')
  })

  it.each(['LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL'])('discards an in-flight list after %s changes and returns to its old value', async field => {
    const { model } = await open()
    const list = deferred<any[]>()
    api.getAvailableModels.mockReturnValue(list.promise)
    const fetching = model.fetchModels()
    const original = model.form.value[field]
    model.form.value[field] = 'changed'
    model.form.value[field] = original
    list.resolve([{ id: 'obsolete', name: 'Obsolete' }])
    await fetching
    expect(model.availableModels.value).toEqual([])
    expect(model.loadingModels.value).toBe(false)
  })
})

describe('test results belong to one draft generation', () => {
  it.each(['LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL'])('invalidates a successful test immediately after editing %s', async field => {
    const { model } = await open()
    api.testLLMConnection.mockResolvedValue({ success: true, message: 'old-success' })
    await model.testConnection()
    expect(model.saveStatus.value?.msg).toBe('old-success')
    model.form.value[field] += '-edited'
    expect(model.saveStatus.value).toBeNull()
  })

  it.each(['LLM_API_URL', 'LLM_API_KEY', 'LLM_MODEL'])('ignores an in-flight test after %s is edited and changed back synchronously', async field => {
    const { model } = await open()
    const test = deferred<any>()
    api.testLLMConnection.mockReturnValue(test.promise)
    const testing = model.testConnection()
    const original = model.form.value[field]
    model.form.value[field] = 'changed'
    model.form.value[field] = original
    test.resolve({ success: true, message: 'obsolete-success' })
    await testing
    expect(model.saveStatus.value).toBeNull()
    expect(model.testing.value).toBe(false)
  })

  it('does not unlock or overwrite a newer test when an obsolete test ends', async () => {
    const { model } = await open()
    const old = deferred<any>()
    const current = deferred<any>()
    api.testLLMConnection.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const first = model.testConnection()
    model.form.value.LLM_MODEL = 'new-model'
    const second = model.testConnection()
    old.resolve({ success: true, message: 'obsolete-success' })
    await first
    expect(api.testLLMConnection).toHaveBeenCalledTimes(2)
    expect(model.testing.value).toBe(true)
    expect(model.saveStatus.value).toBeNull()
    current.resolve({ success: true, message: 'current-success' })
    await second
    expect(model.saveStatus.value?.msg).toBe('current-success')
  })

  it.each(['TLS failed', { code: 'tls_error', message: 'TLS failed' }])('renders a safe string from error detail %j', async detail => {
    const { model } = await open()
    api.testLLMConnection.mockRejectedValue({ response: { data: { detail } } })
    await model.testConnection()
    expect(model.saveStatus.value).toEqual({ type: 'error', msg: 'TLS failed' })
  })
})

describe('atomic saves and credential boundaries', () => {
  it('saves a captured configuration in one request while a list is pending', async () => {
    const { model } = await open()
    model.form.value = { LLM_API_URL: ' https://draft.test/v1 ', LLM_MODEL: ' draft-model ', LLM_API_KEY: ' draft-key ' }
    api.getAvailableModels.mockReturnValue(new Promise(() => {}))
    void model.fetchModels()
    expect(model.loadingModels.value).toBe(true)
    await model.saveSettings()
    expect(api.saveLLMSettings.mock.calls).toEqual([[{ api_url: 'https://draft.test/v1', model: 'draft-model', api_key: 'draft-key' }]])
    expect(api.updateSetting).not.toHaveBeenCalled()
  })

  it('preserves the stored key by omitting an empty replacement', async () => {
    const { model } = await open()
    await model.saveSettings()
    expect(api.saveLLMSettings).toHaveBeenCalledWith({ api_url: 'https://example.test/v1', model: 'demo' })
  })

  it('leaves the draft and unconfigured-key state untouched when atomic saving fails', async () => {
    api.listSettings.mockResolvedValue(settings('https://example.test/v1').map(item => ({ ...item, is_configured: false })))
    const { model } = await open()
    model.form.value.LLM_API_KEY = 'unsaved-key'
    api.saveLLMSettings.mockRejectedValue({ response: { data: { detail: { code: 'save_failed', message: 'Atomic save failed' } } } })
    api.updateSetting.mockRejectedValue(new Error('legacy save failed'))
    await model.saveSettings()
    expect(model.keyConfigured.value).toBe(false)
    expect(model.form.value.LLM_API_KEY).toBe('unsaved-key')
    expect(model.saveStatus.value).toEqual({ type: 'error', msg: 'Atomic save failed' })
  })

  it('preserves newer edits and keeps the drawer open when an older save completes', async () => {
    const { model } = await open()
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    api.updateSetting.mockReturnValue(saved.promise)
    model.form.value.LLM_API_KEY = 'submitted-key'
    const saving = model.saveSettings()
    model.form.value.LLM_API_KEY = 'new-key'
    model.form.value.LLM_MODEL = 'unsaved-model'
    saved.resolve(settings('https://example.test/v1'))
    await saving
    await vi.advanceTimersByTimeAsync(1600)
    expect(model.form.value.LLM_API_KEY).toBe('new-key')
    expect(model.form.value.LLM_MODEL).toBe('unsaved-model')
    expect(model.visible.value).toBe(true)
    expect(model.saveStatus.value?.msg).toContain('尚未保存')
  })

  it('cancels a pending close when editing after a successful save', async () => {
    const { model } = await open()
    await model.saveSettings()
    model.form.value.LLM_MODEL = 'unsaved-model'
    await vi.advanceTimersByTimeAsync(1600)
    expect(model.visible.value).toBe(true)
    expect(model.saveStatus.value).toBeNull()
  })

  it('retains an edit-back credential draft when a saved key is cleared', async () => {
    const { model } = await open()
    const cleared = deferred<any>()
    api.clearSetting.mockReturnValue(cleared.promise)
    model.form.value.LLM_API_KEY = 'draft-key'
    const clearing = model.clearApiKey()
    model.form.value.LLM_API_KEY = 'new-draft'
    model.form.value.LLM_API_KEY = 'draft-key'
    cleared.resolve({})
    await clearing
    expect(model.form.value.LLM_API_KEY).toBe('draft-key')
    expect(model.keyConfigured.value).toBe(false)
    expect(model.errors.value.LLM_API_KEY).toBe('')
  })

  it('waits for a pending clear before loading a reopened form', async () => {
    const { model, props } = await open()
    const cleared = deferred<any>()
    api.clearSetting.mockReturnValue(cleared.promise)
    const clearing = model.clearApiKey()
    props.modelValue = false
    await flush()
    props.modelValue = true
    await flush()
    expect(api.listSettings).toHaveBeenCalledTimes(1)
    expect(model.settingsLoaded.value).toBe(false)
    cleared.resolve({})
    await clearing
    await flush()
    expect(api.listSettings).toHaveBeenCalledTimes(2)
    expect(model.settingsLoaded.value).toBe(true)
  })
})


describe('completion boundaries between primary and auxiliary actions', () => {
  it.each(['testConnection', 'saveSettings'])('keeps %s feedback when an auxiliary list request fails later', async action => {
    const { model } = await open()
    const list = deferred<any[]>()
    api.getAvailableModels.mockReturnValue(list.promise)
    const fetching = model.fetchModels()
    api.testLLMConnection.mockResolvedValue({ success: true, message: 'current-success' })
    await model[action]()
    const status = { ...model.saveStatus.value }
    list.reject({ response: { data: { detail: { code: 'models_failed', message: 'Suggestions unavailable' } } } })
    await fetching
    expect(model.saveStatus.value).toEqual(status)
    expect(model.modelsStatus.value).toEqual({ type: 'error', msg: 'Suggestions unavailable' })
  })

  it('ignores an obsolete list failure without unlocking a newer list request', async () => {
    const { model } = await open()
    const old = deferred<any[]>()
    const current = deferred<any[]>()
    api.getAvailableModels.mockReturnValueOnce(old.promise).mockReturnValueOnce(current.promise)
    const first = model.fetchModels()
    model.form.value.LLM_API_URL = 'https://new.test/v1'
    const second = model.fetchModels()
    old.reject({ response: { data: { detail: 'Old list failed' } } })
    await first
    expect(model.loadingModels.value).toBe(true)
    expect(model.modelsStatus.value).toBeNull()
    current.resolve([{ id: 'new', name: 'New model' }])
    await second
    expect(model.availableModels.value).toEqual([{ id: 'new', name: 'New model' }])
  })

  it('keeps the drawer open for a new test after a successful save', async () => {
    const { model } = await open()
    await model.saveSettings()
    const result = deferred<any>()
    api.testLLMConnection.mockReturnValue(result.promise)
    const testing = model.testConnection()
    await vi.advanceTimersByTimeAsync(1600)
    expect(model.visible.value).toBe(true)
    result.resolve({ success: true, message: 'current-success' })
    await testing
    expect(model.saveStatus.value?.msg).toBe('current-success')
  })

  it('waits for a failed atomic save before reloading the reopened drawer', async () => {
    const { model, props } = await open()
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    const saving = model.saveSettings()
    props.modelValue = false
    await flush()
    props.modelValue = true
    await flush()
    expect(api.listSettings).toHaveBeenCalledTimes(1)
    expect(model.settingsLoaded.value).toBe(false)
    saved.reject({ response: { data: { detail: 'Save failed' } } })
    await saving
    await flush()
    expect(api.listSettings).toHaveBeenCalledTimes(2)
    expect(model.settingsLoaded.value).toBe(true)
    expect(model.saveStatus.value).toBeNull()
  })

  it('does not clear an edit-back credential or close the drawer after saving an older generation', async () => {
    const { model } = await open()
    const saved = deferred<any>()
    api.saveLLMSettings.mockReturnValue(saved.promise)
    model.form.value.LLM_API_KEY = 'draft-key'
    const saving = model.saveSettings()
    model.form.value.LLM_API_KEY = 'another-key'
    model.form.value.LLM_API_KEY = 'draft-key'
    saved.resolve(settings('https://example.test/v1'))
    await saving
    await vi.advanceTimersByTimeAsync(1600)
    expect(model.form.value.LLM_API_KEY).toBe('draft-key')
    expect(model.visible.value).toBe(true)
    expect(model.saveStatus.value?.msg).toContain('尚未保存')
  })
})
