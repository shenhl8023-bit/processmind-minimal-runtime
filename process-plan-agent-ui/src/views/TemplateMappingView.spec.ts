import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import source from './TemplateMappingView.vue?raw'
import * as currentProject from '@/composables/useCurrentProject'
import * as finalOperations from '@/composables/finalTemplateMappingOperations'

// Exercise the real setup logic with controlled network responses. Compile the
// script without a DOM so tests do not depend on browser timing or layout.
const script = compileScript(parse(source).descriptor, { id: 'template-mapping-test' })
const template = parse(source).descriptor.template?.content || ''
const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const api = { getSavedNormalizedRoute: vi.fn(), getSupersetRoute: vi.fn() }
const router = { push: vi.fn() }
let route: any
const module = { exports: {} as any }
new Function('require', 'module', 'exports', code)((id: string) => {
  if (id === 'vue') return Vue
  if (id === 'vue-router') return { useRoute: () => route, useRouter: () => router }
  if (id === '@/api/extract') return api
  if (id === '@/composables/useCurrentProject') return currentProject
  if (id === '@/composables/finalTemplateMappingOperations') return finalOperations
  if (id.endsWith('.vue')) return { default: {} }
  throw new Error(`Unexpected dependency: ${id}`)
}, module, module.exports)
const renderer = Vue.createRenderer({
  createComment: () => ({}), insert: () => {}, remove: () => {},
  parentNode: () => null, nextSibling: () => null,
} as any)
let app: ReturnType<typeof renderer.createApp> | undefined
function mount() {
  let state: any
  app = renderer.createApp({
    setup() {
      state = module.exports.default.setup({}, { expose() {} })
      return () => null
    },
  })
  app.mount({})
  return state
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  vi.resetAllMocks()
  route = Vue.reactive({ path: '/template-mapping', query: { project_id: '28' } })
  api.getSavedNormalizedRoute.mockResolvedValue({ segments: [{ id: 'one', source_operation_ids: [11] }] })
  api.getSupersetRoute.mockResolvedValue({ superset_route: [] })
})
afterEach(() => app?.unmount())

describe('template mapping workbench', () => {
  it('uses the original mapping workbench chrome without an extra page header or workflow footer', () => {
    expect(template).toContain('<TemplateGroupMappingDialog')
    expect(template).toContain('embedded :model-value="true"')
    expect(template).toContain('@cancel="go(\'/analysis\')"')
    expect(template).toContain('@continue="continueToFinalize"')
    expect(template).not.toContain('class="mapping-header"')
    expect(template).not.toContain('<WorkflowNavFooter')
  })

  it('clears loading when the project disappears during a load', async () => {
    const model = mount()
    const saved = deferred<any>()
    api.getSavedNormalizedRoute.mockReturnValueOnce(saved.promise)
    const pending = model.load()
    expect(model.loading.value).toBe(true)
    route.query.project_id = ''
    await Vue.nextTick()
    saved.resolve({ segments: [] })
    await pending
    expect(model.loading.value).toBe(false)
  })

  it('returns to rule analysis with the current project when cancelled', () => {
    const model = mount()
    model.go('/analysis')
    expect(router.push).toHaveBeenCalledWith({ path: '/analysis', query: { project_id: '28' } })
  })

  it('opens rule finalization with the current project when continuing', () => {
    const model = mount()
    expect(typeof model.continueToFinalize).toBe('function')
    model.continueToFinalize()
    expect(router.push).toHaveBeenCalledWith({ path: '/finalize', query: { project_id: '28' } })
  })
})
