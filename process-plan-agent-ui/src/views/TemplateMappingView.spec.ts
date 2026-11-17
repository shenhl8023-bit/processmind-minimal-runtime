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
const executable = { getLatestExecutableRuleRevision: vi.fn(), exportExecutableRuleRevision: vi.fn() }
const downloadValidatedRulePackage = vi.fn()
const router = { push: vi.fn() }
let leaveGuard: () => boolean
let updateGuard: (to: any, from: any) => boolean
let route: any
const module = { exports: {} as any }
new Function('require', 'module', 'exports', code)((id: string) => {
  if (id === 'vue') return Vue
  if (id === 'vue-router') return {
    useRoute: () => route, useRouter: () => router,
    onBeforeRouteLeave: (guard: typeof leaveGuard) => { leaveGuard = guard },
    onBeforeRouteUpdate: (guard: typeof updateGuard) => { updateGuard = guard },
  }
  if (id === '@/api/extract') return api
  if (id === '@/api/executableRules') return executable
  if (id === '@/utils/validatedRulePackageDownload') return { downloadValidatedRulePackage }
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
  executable.getLatestExecutableRuleRevision.mockResolvedValue({ id: 7, revision: 1, generation_ready: true, has_current_generation: true, route_version_id: 31, content_hash: 'core', package: { manifest: { package_name: '测试' } } })
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

  it('uses the workbench chrome with a shared return footer while it cannot be mounted', () => {
    expect(template).toContain('<TemplateGroupMappingDialog')
    expect(template).toContain('embedded :model-value="true"')
    expect(template).toContain('@cancel="requestReturnToValidation"')
    expect(template).toContain('@continue="continueToFinalize"')
    expect(template).not.toContain('class="mapping-header"')
    expect(template).toContain('<WorkflowNavFooter v-if="loading || error || !projectId"')
    expect(template).toContain(':show-next="false"')
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

  it('returns to route validation with the current project when continuing', () => {
    const model = mount()
    expect(typeof model.continueToFinalize).toBe('function')
    model.continueToFinalize()
    expect(router.push).toHaveBeenCalledWith({ path: '/generate', query: { project_id: '28' } })
  })

  it('blocks step navigation and project switches while mappings have unsaved changes', () => {
    const model = mount()
    model.updateMappingStatus({ dirty: true, busy: false })
    expect(leaveGuard()).toBe(false)
    expect(updateGuard({ query: { project_id: '29' } }, route)).toBe(false)
    expect(model.mappingNotice.value).toContain('未保存')
    expect(template).toContain('@status="updateMappingStatus"')
  })

  it('blocks navigation during a mapping save without offering to discard the request', () => {
    const model = mount()
    model.updateMappingStatus({ dirty: false, busy: true })
    expect(leaveGuard()).toBe(false)
    expect(model.mappingNotice.value).toContain('等待')
    expect(model.mappingStatus.value.busy).toBe(true)
  })

  it('allows leaving again after mappings are saved or explicitly discarded', () => {
    const model = mount()
    model.updateMappingStatus({ dirty: true, busy: false })
    expect(leaveGuard()).toBe(false)
    model.updateMappingStatus({ dirty: false, busy: false })
    expect(leaveGuard()).toBe(true)
    expect(model.mappingNotice.value).toBe('')
  })

  it('returns directly to validation when there are no unsaved changes', () => {
    const model = mount()
    model.requestReturnToValidation()
    expect(model.returnDialogVisible.value).toBe(false)
    expect(router.push).toHaveBeenCalledWith({ path: '/generate', query: { project_id: '28' } })
  })

  it('opens a return confirmation without discarding the current mapping draft', () => {
    const model = mount()
    const discardChanges = vi.fn()
    model.mappingDialog.value = { discardChanges }
    model.updateMappingStatus({ dirty: true, busy: false })
    model.requestReturnToValidation()
    expect(model.returnDialogVisible.value).toBe(true)
    expect(discardChanges).not.toHaveBeenCalled()
    expect(router.push).not.toHaveBeenCalled()
    // Closing the confirmation means continuing to edit, with the draft intact.
    model.returnDialogVisible.value = false
    expect(model.mappingStatus.value.dirty).toBe(true)
    expect(leaveGuard()).toBe(false)
  })

  it('discards only after confirmation and waits for the clean status before returning', async () => {
    const model = mount()
    const discardChanges = vi.fn(() => {
      void Vue.nextTick(() => model.updateMappingStatus({ dirty: false, busy: false }))
    })
    model.mappingDialog.value = { discardChanges }
    model.updateMappingStatus({ dirty: true, busy: false })
    model.requestReturnToValidation()
    await model.confirmReturnToValidation()
    expect(discardChanges).toHaveBeenCalledOnce()
    expect(model.returnDialogVisible.value).toBe(false)
    expect(leaveGuard()).toBe(true)
    expect(router.push).toHaveBeenCalledWith({ path: '/generate', query: { project_id: '28' } })
  })

  it('does not discard a mapping operation that became busy while the confirmation was open', async () => {
    const model = mount()
    const discardChanges = vi.fn()
    model.mappingDialog.value = { discardChanges }
    model.updateMappingStatus({ dirty: true, busy: false })
    model.requestReturnToValidation()
    model.updateMappingStatus({ dirty: true, busy: true })
    await model.confirmReturnToValidation()
    expect(discardChanges).not.toHaveBeenCalled()
    expect(router.push).not.toHaveBeenCalled()
    expect(model.returnDialogVisible.value).toBe(true)
    expect(model.mappingNotice.value).toContain('等待')
  })

  it('keeps the return confirmation open if the mapping draft was not actually discarded', async () => {
    const model = mount()
    model.mappingDialog.value = { discardChanges: vi.fn() }
    model.updateMappingStatus({ dirty: true, busy: false })
    model.requestReturnToValidation()
    await model.confirmReturnToValidation()
    expect(router.push).not.toHaveBeenCalled()
    expect(model.returnDialogVisible.value).toBe(true)
    expect(model.mappingStatus.value.dirty).toBe(true)
  })
})


describe('optional final mapping export', () => {
  it('saves and exports the exact validated revision atomically and adopts the frozen mapping snapshot', async () => {
    const model = mount()
    await model.load()
    const snapshot = { template_revision: 5, step_mappings: [], mapping_output: [], hidden_step_keys: ['p:s'], waived_group_paths: [['A']] }
    const saved = { version: 1, export_sources: { template_mapping: snapshot } }
    executable.exportExecutableRuleRevision.mockResolvedValue(saved)
    const mapping = { project_id: 28, expected_template_revision: 4, expected_workflow_revision: 0, mappings: [], operations: [], replace_all: true, hidden_step_keys: ['p:s'], waived_group_paths: [['A']] }
    expect(await model.saveAndExportMapping(mapping)).toEqual(snapshot)
    expect(executable.exportExecutableRuleRevision).toHaveBeenCalledWith(7, { project_id: 28, expected_workflow_revision: 0, expected_content_hash: 'core', include_template_mapping: true, template_mapping: mapping })
    expect(downloadValidatedRulePackage).toHaveBeenCalledWith(saved, '测试', { isCurrent: expect.any(Function) })
    expect(template).toContain(':before-save="saveAndExportMapping"')
  })
  it('keeps a successful save when browser download fails and offers retry of the same frozen package', async () => {
    const model = mount()
    await model.load()
    const snapshot = { template_revision: 5, step_mappings: [], mapping_output: [], hidden_step_keys: [], waived_group_paths: [] }
    const saved = { version: 1, export_sources: { template_mapping: snapshot } }
    executable.exportExecutableRuleRevision.mockResolvedValue(saved)
    downloadValidatedRulePackage.mockImplementationOnce(() => { throw new Error('download failed') })
    expect(await model.saveAndExportMapping({ project_id: 28 })).toEqual(snapshot)
    expect(model.downloadNotice.value).toContain('已保存')
    await model.retryPackageDownload()
    expect(downloadValidatedRulePackage).toHaveBeenCalledTimes(2)
    expect(executable.exportExecutableRuleRevision).toHaveBeenCalledOnce()
  })
  it('keeps the frozen package available when asynchronous download preparation fails', async () => {
    const model = mount()
    await model.load()
    const snapshot = { template_revision: 5, step_mappings: [], mapping_output: [], hidden_step_keys: [], waived_group_paths: [] }
    const saved = { version: 1, export_sources: { template_mapping: snapshot } }
    executable.exportExecutableRuleRevision.mockResolvedValue(saved)
    const failure = Promise.reject(new Error('编号分配暂不可用'))
    void failure.catch(() => {})
    downloadValidatedRulePackage.mockReturnValueOnce(failure)
    expect(await model.saveAndExportMapping({ project_id: 28 })).toEqual(snapshot)
    expect(model.downloadNotice.value).toContain('已保存')
    await model.retryPackageDownload()
    expect(downloadValidatedRulePackage).toHaveBeenNthCalledWith(2, saved, '测试', { isCurrent: expect.any(Function) })
    expect(executable.exportExecutableRuleRevision).toHaveBeenCalledOnce()
    expect(model.downloadNotice.value).toBe('')
  })
  it('cancels pending identity download when mapping context changes', async () => {
    const model = mount()
    await model.load()
    const snapshot = { template_revision: 5, step_mappings: [], mapping_output: [], hidden_step_keys: [], waived_group_paths: [] }
    executable.exportExecutableRuleRevision.mockResolvedValue({ version: 1, export_sources: { template_mapping: snapshot } })
    const allocation = deferred<void>()
    const delivered = vi.fn()
    downloadValidatedRulePackage.mockImplementationOnce(async (_saved, _name, options) => {
      await allocation.promise
      if (!options?.isCurrent || options.isCurrent()) delivered()
    })
    const pending = model.saveAndExportMapping({ project_id: 28 })
    await Promise.resolve()
    await model.load()
    allocation.resolve()
    await pending
    expect(delivered).not.toHaveBeenCalled()
  })

})
