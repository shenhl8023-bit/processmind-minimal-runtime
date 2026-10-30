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
  function mockCurrentMergedRoute() {
    api.getSavedNormalizedRoute.mockResolvedValue({ segments: [{
      id: 'turning_a', sequence: 10, normalized_step_name: '车削加工（A侧）',
      phase: 'rough', source_operation_ids: [11, 12],
    }] })
    api.getSupersetRoute.mockResolvedValue({ superset_route: [
      { id: 11, name: '车外圆', step_items: ['平端面', '车外圆'], attached_step_items: ['倒角'] },
      { id: 12, name: '车槽', step_items: ['平端面', '切槽'], attached_step_items: [] },
    ] })
  }

  it('loads the saved merged route with current source steps and their lineage', async () => {
    mockCurrentMergedRoute()
    api.getSavedNormalizedRoute.mockResolvedValue({
      ...await api.getSavedNormalizedRoute(), workflow_revision: 12,
    })
    const model = mount()
    await model.load()

    expect(model.error.value).toBe('')
    expect(model.loading.value).toBe(false)
    expect(model.workflowRevision.value).toBe(12)
    expect(template).toContain(':workflow-revision="workflowRevision"')
    expect(api.getSavedNormalizedRoute).toHaveBeenCalledWith(28, true)
    expect(api.getSupersetRoute).toHaveBeenCalledWith(28, true)
    expect(model.operations.value).toHaveLength(1)
    expect(model.operations.value[0]).toMatchObject({
      process_id: 'turning_a', source_operation_ids: [11, 12],
      step_items: ['平端面', '车外圆', '切槽', '倒角'],
    })
    expect(model.operations.value[0].steps[0].source_steps).toEqual([
      { source_operation_id: 11, source_operation_name: '车外圆', source_step_order: 1, source_step_name: '平端面' },
      { source_operation_id: 12, source_operation_name: '车槽', source_step_order: 1, source_step_name: '平端面' },
    ])
  })

  it('removes a previous mapping tree when refreshed source identities no longer match the saved route', async () => {
    mockCurrentMergedRoute()
    const model = mount()
    await model.load()
    expect(model.operations.value).toHaveLength(1)

    api.getSupersetRoute.mockResolvedValue({ superset_route: [
      { id: 9011, name: '车外圆', step_items: ['平端面', '车外圆'] },
      { id: 9012, name: '车槽', step_items: ['平端面', '切槽'] },
    ] })
    await model.load()

    expect(model.operations.value).toEqual([])
    expect(model.error.value).toContain('当前保存路线与最新工序数据不一致')
    expect(model.loading.value).toBe(false)
  })

  it('removes a previous mapping tree and reports missing details when every source loses its steps', async () => {
    mockCurrentMergedRoute()
    const model = mount()
    await model.load()
    expect(model.operations.value).toHaveLength(1)

    api.getSupersetRoute.mockResolvedValue({ superset_route: [
      { id: 11, name: '车外圆', step_items: [], attached_step_items: [] },
      { id: 12, name: '车槽', step_items: [], attached_step_items: [] },
    ] })
    await model.load()

    expect(model.operations.value).toEqual([])
    expect(model.error.value).toContain('当前路线缺少工步明细')
    expect(model.loading.value).toBe(false)
  })

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
