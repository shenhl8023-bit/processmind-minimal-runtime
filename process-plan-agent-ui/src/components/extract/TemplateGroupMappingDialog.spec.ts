import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import source from './TemplateGroupMappingDialog.vue?raw'
import treeNodeSource from './TemplateGroupTreeNode.vue?raw'
import * as groupMapping from '@/composables/templateGroupMapping'
import * as stepMapping from '@/composables/templateStepMapping'
import * as processMapping from '@/composables/templateGroupProcessMapping'
import * as templateCheck from '@/composables/projectGroupTemplateCheck'

// Run the actual component setup with deferred API calls, without a DOM.
const script = compileScript(parse(source).descriptor, { id: 'template-dialog-test' })
const template = parse(source).descriptor.template?.content || ''
const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const api = { suggestTemplateStepMappings: vi.fn(), suggestTemplateProcessPrecisions: vi.fn() }
let model: any
const module = { exports: {} as any }
const iconStub = Vue.defineComponent({ setup: () => () => null })
const treeRenderModule = { exports: {} as any }
const treeRenderCode = transformSync(compileScript(parse(treeNodeSource).descriptor, {
  id: 'template-tree-render-test', inlineTemplate: true,
}).content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const renderModule = { exports: {} as any }
const renderCode = transformSync(compileScript(parse(source).descriptor, {
  id: 'template-dialog-render-test', inlineTemplate: true,
}).content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
function testRequire(id: string) {
  if (id === 'vue') return Vue
  if (id === '@/api/extract') return api
  if (id === '@/composables/templateGroupMapping') return groupMapping
  if (id === '@/composables/templateStepMapping') return stepMapping
  if (id === '@/composables/templateGroupProcessMapping') return processMapping
  if (id === '@/composables/projectGroupTemplateCheck') return templateCheck
  if (id === '@/composables/useProjectGroupTemplate') return { useProjectGroupTemplate: () => model }
  if (id === '@element-plus/icons-vue') return new Proxy({}, { get: () => iconStub })
  if (id === '@/components/extract/TemplateGroupTreeNode.vue') return treeRenderModule.exports.default
  if (id.endsWith('.vue')) return iconStub
  throw new Error(`Unexpected dependency: ${id}`)
}
new Function('require', 'module', 'exports', code)(testRequire, module, module.exports)
new Function('require', 'module', 'exports', treeRenderCode)(testRequire, treeRenderModule, treeRenderModule.exports)
treeRenderModule.exports.default.name = 'TemplateGroupTreeNode'
new Function('require', 'module', 'exports', renderCode)(testRequire, renderModule, renderModule.exports)
const teleportTarget: any = { type: 'body', children: [], props: {} }
const renderer = Vue.createRenderer({
  createComment: () => ({}), insert: () => {}, remove: () => {},
  parentNode: () => null, nextSibling: () => null,
} as any)
const renderRenderer = Vue.createRenderer({
  createComment: (text: string) => ({ type: '#comment', text, children: [], props: {} }),
  createText: (text: string) => ({ type: '#text', text, children: [], props: {} }),
  createElement: (type: string) => ({
    type, children: [], props: {}, text: '', value: '', tagName: type.toUpperCase(),
    addEventListener() {}, removeEventListener() {}, dispatchEvent() { return true },
  }),
  setText: (node: any, text: string) => { node.text = text },
  setElementText: (node: any, text: string) => { node.text = text; node.children = [] },
  patchProp: (node: any, key: string, _previous: unknown, next: unknown) => { node.props[key] = next },
  insert: (child: any, parent: any, anchor?: any) => {
    child.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(child)
    else parent.children.splice(index, 0, child)
  },
  remove: (node: any) => {
    if (!node) return
    const parent = node.parent
    if (parent) parent.children.splice(parent.children.indexOf(node), 1)
  },
  parentNode: (node: any) => node.parent || null,
  nextSibling: (node: any) => {
    const siblings = node.parent?.children || []
    return siblings[siblings.indexOf(node) + 1] || null
  },
  querySelector: () => teleportTarget,
} as any)
let app: ReturnType<typeof renderer.createApp> | undefined
function mount(operationCount = 1, operations?: any[]) {
  let state: any
  const emitted: any[] = []
  const props = Vue.reactive({
    modelValue: true, projectId: 28, legacyAliases: {}, embedded: true,
    operations: operations || Array.from({ length: operationCount }, (_, index) => ({
      id: 11 + index, name: '钻孔加工', step_items: ['钻孔'],
    })),
  })
  app = renderer.createApp({
    setup() {
      state = module.exports.default.setup(props, { expose() {}, emit: (...event: any[]) => emitted.push(event) })
      return () => null
    },
  })
  app.mount({})
  return { state, props, emitted }
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
const response = {
  suggestions: [{
    step_key: 'op_11_s01', recommended_group_ids: ['hole'],
    recommended_features_by_group: { hole: ['孔(盲孔)'] }, confidence: 1,
  }], warnings: ['旧推荐警告'],
}
beforeEach(() => {
  vi.resetAllMocks()
  model = {
    template: Vue.ref({
      project_id: 28, template_revision: 1, mappings: [], step_mappings: [],
      tree: [{ key: 'hole', name: '孔', path: ['孔'], children: [], feature_selections: ['孔(盲孔)'] }],
    }),
    state: Vue.ref('workspace'), draftStepMappings: Vue.ref([]), templateRevision: Vue.ref(1),
    saving: Vue.ref(false), loading: Vue.ref(false), error: Vue.ref(''),
    load: vi.fn().mockResolvedValue(true), beginReplacement: vi.fn(), cancelPreview: vi.fn(),
    confirmTemplate: vi.fn().mockResolvedValue(true),
  }
})
afterEach(() => { app?.unmount(); vi.unstubAllGlobals() })

describe('template recommendation request invalidation', () => {
  it.each(['replace', 'confirm'])('discards pending recommendations when templates %s', async (action) => {
    const { state } = mount()
    await Vue.nextTick()
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    const pendingResponse = deferred<typeof response>()
    api.suggestTemplateStepMappings.mockReturnValue(pendingResponse.promise)
    const pending = state.suggestActiveLeaf()
    expect(state.recognizing.value).toBe(true)
    if (action === 'replace') await state.startReplacement()
    else await state.confirmPreview()
    expect(state.recognizing.value).toBe(false)
    pendingResponse.resolve(response)
    await pending
    expect(Object.values(state.draftStepMappings.value)).toEqual([])
    expect(state.mappingWarnings.value).toEqual([])
  })

  it.each(['project', 'close'])('stops remaining batches when the %s changes', async (action) => {
    const { state, props } = mount(31)
    await Vue.nextTick()
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    const pendingResponse = deferred<typeof response>()
    api.suggestTemplateStepMappings.mockReturnValue(pendingResponse.promise)
    const pending = state.suggestActiveLeaf()
    expect(api.suggestTemplateStepMappings).toHaveBeenCalledTimes(3)
    if (action === 'project') props.projectId = 29
    else state.closeDialog()
    await Vue.nextTick()
    pendingResponse.resolve(response)
    await pending
    expect(api.suggestTemplateStepMappings).toHaveBeenCalledTimes(3)
    expect(Object.values(state.draftStepMappings.value)).toEqual([])
    expect(state.mappingWarnings.value).toEqual([])
  })
})

describe('embedded template import dialog', () => {
  it('shows an import entry in the empty state and opens the same dialog on demand', async () => {
    model.template.value = null
    model.state.value = 'empty'
    const { state } = mount()
    await Vue.nextTick()

    expect(state.showEmptyState?.value).toBe(true)
    expect(state.importDialogOpen?.value).toBe(false)
    expect(template).toContain('还没有导入分组模板')

    state.openTemplateDialog?.()

    expect(state.importDialogOpen?.value).toBe(true)
  })

  it('keeps the existing mapping workspace visible while replacing a template', async () => {
    model.beginReplacement = vi.fn(() => { model.state.value = 'preview' })
    model.cancelPreview = vi.fn(() => { model.state.value = 'workspace' })
    const originalTemplate = model.template.value
    const { state } = mount()
    await Vue.nextTick()

    await state.startReplacement()

    expect(state.importDialogOpen?.value).toBe(true)
    expect(state.showMappingWorkspace?.value).toBe(true)
    expect(model.template.value).toBe(originalTemplate)

    state.cancelReplacement()

    expect(state.importDialogOpen?.value).toBe(false)
    expect(model.state.value).toBe('workspace')
    expect(model.template.value).toBe(originalTemplate)
  })

  it('closes the import dialog after a successful preview confirmation', async () => {
    model.state.value = 'preview'
    model.confirmTemplate = vi.fn(async () => {
      model.state.value = 'workspace'
      return true
    })
    const { state } = mount()
    await Vue.nextTick()
    state.importDialogOpen.value = true

    await state.confirmPreview()

    expect(state.importDialogOpen.value).toBe(false)
    expect(state.showMappingWorkspace?.value).toBe(true)
  })
})

describe('mapping save feedback', () => {
  it.each([true, false])('reports a save only after the request succeeds (%s)', async (success) => {
    const pendingSave = deferred<boolean>()
    model.saveStepMappings = () => pendingSave.promise
    const { state } = mount()
    await Vue.nextTick()

    const saving = state.saveStepMappings()
    expect(state.mappingWarnings.value.join('')).not.toContain('已保存')
    expect(state.mappingWarnings.value.join('')).not.toContain('保存。')

    pendingSave.resolve(success)
    await saving

    if (success) expect(state.mappingWarnings.value.join('')).toContain('已保存')
    else expect(state.mappingWarnings.value.join('')).not.toContain('保存')
  })

  it('clears saved feedback when the mapping is edited again', async () => {
    model.saveStepMappings = async () => true
    const { state } = mount()
    await Vue.nextTick()
    await state.saveStepMappings()

    const step = state.stepRefs.value[0]
    state.activeStepKey.value = step.step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    state.linkActiveStep()

    expect(state.dirty.value).toBe(true)
    expect(state.mappingWarnings.value.join('')).not.toContain('保存')
  })

  it('submits existing and newly added group mappings together', async () => {
    const first = {
      source_operation_id: 11,
      source_operation_name: '钻孔加工',
      source_step_order: 1,
      source_step_name: '钻孔',
      scope_template_group_path: [],
      template_group_path: ['孔'],
      candidate_features: ['孔(盲孔)'],
      match_mode: 'any' as const,
      status: 'confirmed' as const,
      confidence: 1,
      source: 'user_confirmed' as const,
    }
    const second = {
      ...first,
      template_group_path: ['槽'],
      candidate_features: ['通槽'],
    }
    model.template.value.tree = [
      model.template.value.tree[0],
      { key: 'slot', source_id: '', name: '槽', path: ['槽'], feature_selections: ['通槽'], params: {}, children: [] },
    ]
    model.draftStepMappings.value = [first]
    model.saveStepMappings = vi.fn(async () => {
      model.template.value.step_mappings = [...model.draftStepMappings.value]
      return true
    })
    const { state } = mount()
    await Vue.nextTick()

    state.draftStepMappings.value = processMapping.mappingRecord([first, second])
    await state.saveStepMappings()

    expect(model.template.value.step_mappings.map((mapping: any) => mapping.template_group_path)).toEqual([
      ['孔'], ['槽'],
    ])
  })
})

const finalOperation = (process_id: string, sourceIds = [11]) => ({
  id: process_id === 'a' ? 101 : 102, process_id, name: '钻孔加工', process_type: '加工工序',
  precision: '粗加工',
  source_operation_ids: sourceIds,
  steps: [{ step_id: `${process_id}.s1`, step_name: '钻孔', kind: 'primary',
    source_operation_id: sourceIds[0], source_step_order: 1, source_step_name: '钻孔',
    source_steps: sourceIds.map(id => ({ source_operation_id: id, source_step_order: 1, source_step_name: '钻孔' })) }],
})

describe('precision completion before saving mappings', () => {
  it('blocks saving with a named missing precision and preserves the draft', async () => {
    model.saveStepMappings = vi.fn().mockResolvedValue(true)
    const operation = { ...finalOperation('a'), name: 'A侧车削', precision: '' }
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    const draft = state.draftStepMappings.value
    expect(await state.saveStepMappings()).toBe(false)
    expect(model.saveStepMappings).not.toHaveBeenCalled()
    expect(state.visibleError.value).toContain('A侧车削')
    expect(state.visibleError.value).toContain('精度')
    expect(state.draftStepMappings.value).toEqual(draft)
  })

  it('only fills missing precision and keeps manual changes made during a request', async () => {
    const a = { ...finalOperation('a'), precision: '' }
    const b = { ...finalOperation('b'), precision: '' }
    const c = { ...finalOperation('c'), id: 103, precision: '精加工' }
    const { state } = mount(3, [a, b, c])
    await Vue.nextTick()
    const pending = deferred<any>()
    api.suggestTemplateProcessPrecisions.mockReturnValue(pending.promise)
    const request = state.suggestPrecisions()
    state.setOperationPrecision(a, '粗加工')
    pending.resolve({ project_id: 28, template_revision: 1, model_used: true, warnings: [], suggestions: [
      { process_id: 'a', precision: '精加工', confidence: .95, reason: '模型建议' },
      { process_id: 'b', precision: '半精加工', confidence: .95, reason: '模型建议' },
      { process_id: 'c', precision: '粗加工', confidence: .95, reason: '模型建议' },
    ] })
    await request
    expect(state.operationPrecision(a)).toBe('粗加工')
    expect(state.operationPrecision(b)).toBe('半精加工')
    expect(state.operationPrecision(c)).toBe('精加工')
    expect(state.dirty.value).toBe(true)
  })

  it.each(['project', 'template', 'close'])('discards precision suggestions after changing the %s', async (change) => {
    const operation = { ...finalOperation('a'), precision: '' }
    const { state, props } = mount(1, [operation])
    await Vue.nextTick()
    const pending = deferred<any>()
    api.suggestTemplateProcessPrecisions.mockReturnValue(pending.promise)
    const request = state.suggestPrecisions()
    if (change === 'project') props.projectId = 29
    else if (change === 'template') { model.templateRevision.value = 2; state.invalidateRecommendations() }
    else state.closeDialog()
    await Vue.nextTick()
    pending.resolve({ project_id: 28, template_revision: 1, suggestions: [{ process_id: 'a', precision: '精加工', confidence: .95 }], warnings: [] })
    await request
    expect(state.operationPrecision(operation)).toBe('')
    expect(state.precisionLoading.value).toBe(false)
  })

  it('keeps a field blank when the user intentionally clears it during a request', async () => {
    const operation = { ...finalOperation('a'), precision: '' }
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    const pending = deferred<any>()
    api.suggestTemplateProcessPrecisions.mockReturnValue(pending.promise)
    const request = state.suggestPrecisions()
    state.setOperationPrecision(operation, '精加工')
    state.setOperationPrecision(operation, '')
    pending.resolve({ project_id: 28, template_revision: 1, suggestions: [{ process_id: 'a', precision: '精加工', confidence: .95 }], warnings: [] })
    await request
    expect(state.operationPrecision(operation)).toBe('')
  })
})

function savedFinalStepMapping() {
  return {
    final_targets: [{ process_id: 'a', step_id: 'a.s1' }],
    source_operation_id: 11,
    source_operation_name: '钻孔加工',
    source_step_order: 1,
    source_step_name: '钻孔',
    scope_template_group_path: [],
    template_group_path: ['孔'],
    candidate_features: ['孔(盲孔)'],
    match_mode: 'any',
    status: 'confirmed',
    confidence: 1,
    source: 'user_confirmed',
  }
}

function nodeText(node: any): string {
  return `${node.text || ''}${(node.children || []).map(nodeText).join('')}`
}

function findMappingAction(root: any) {
  const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
  return visit(root).find(node => node.type === 'button' && /保存工步映射|进入规则定稿|关联工步后继续/.test(nodeText(node)))
}

describe('mapping save edit protection', () => {
  function configureSavedMapping() {
    const mapping = savedFinalStepMapping()
    model.template.value.step_mappings = [mapping]
    model.draftStepMappings.value = [mapping]
    model.template.value.tree.push({
      key: 'slot', name: '环槽', path: ['环槽'], children: [], feature_selections: ['外环槽', '内环槽'],
    })
    const response = deferred<boolean>()
    model.saveStepMappings = async (operations: any[]) => {
      model.saving.value = true
      const mappings = JSON.parse(JSON.stringify(model.draftStepMappings.value))
      const output = JSON.parse(JSON.stringify(operations))
      const saved = await response.promise
      if (saved) {
        model.template.value = { ...model.template.value, step_mappings: mappings, mapping_output: output }
      }
      model.saving.value = false
      return saved
    }
    return response
  }

  it.each(['precision', 'link', 'unlink', 'clear', 'recommendation', 'replacement', 'confirmation', 'cancel', 'close'])(
    'blocks a %s mutation while the submitted mapping is being saved', async (action) => {
      const response = configureSavedMapping()
      const operation = finalOperation('a')
      const { state, emitted } = mount(1, [operation])
      await Vue.nextTick()
      state.selectedFeatureKeys.value = [JSON.stringify(['slot', '外环槽'])]
      state.setOperationPrecision(operation, '半精加工')
      const originalMappings = JSON.parse(JSON.stringify(Object.values(state.draftStepMappings.value)))
      const saving = state.saveStepMappings()
      expect(model.saving.value).toBe(true)

      if (action === 'precision') state.setOperationPrecision(operation, '精加工')
      if (action === 'link') state.linkActiveStep()
      if (action === 'unlink') state.removeStepMapping(originalMappings[0], state.stepRefs.value[0])
      if (action === 'clear') state.clearMappings()
      if (action === 'recommendation') state.applySuggestedMappings([{
        step_key: 'op_11_s01', recommended_group_ids: ['slot'],
        recommended_features_by_group: { slot: ['外环槽'] }, confidence: 1,
      }])
      if (action === 'replacement') await state.startReplacement()
      if (action === 'confirmation') await state.confirmPreview()
      if (action === 'cancel') state.handleCancel()
      if (action === 'close') state.closeDialog()

      expect.soft(state.operationPrecision(operation)).toBe('半精加工')
      expect.soft(Object.values(state.draftStepMappings.value)).toEqual(originalMappings)
      expect.soft(state.importDialogOpen.value).toBe(false)
      expect.soft(emitted.some(event => event[0] === 'cancel')).toBe(false)
      response.resolve(true)
      expect(await saving).toBe(true)
      expect(state.operationPrecision(operation)).toBe('半精加工')
      expect(model.template.value.mapping_output[0].precision).toBe('半精加工')
      expect(state.dirty.value).toBe(false)
    },
  )

  it.each([true, false])('disables editing controls until the save finishes (%s)', async (success) => {
    const response = configureSavedMapping()
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, {
      modelValue: true, projectId: 28, legacyAliases: {}, embedded: true, operations: [finalOperation('a')],
    })
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()
    const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
    const precision = visit(root).find(node => node.type === 'select' && node.props['data-precision-process-id'] === 'a')
    const selectedFeature = visit(root).find(node => node.type === 'input' && node.props['aria-label'] === '选择特征：环槽 / 外环槽')
    selectedFeature.props.onChange()
    precision.props.onChange({ target: { value: '半精加工' } })
    await Vue.nextTick()
    const saving = findMappingAction(root).props.onClick()
    await Vue.nextTick()

    const controls = visit(root).filter(node => node.type === 'select'
      || (node.type === 'input' && node.props.type === 'checkbox')
      || (node.type === 'button' && (
        ['tgmd-command', 'tgmd-link-btn', 'tgmd-clear-all', 'tgmd-current-suggest', 'tgmd-toggle-group-selection', 'tgmd-clear-selection'].includes(node.props.class)
        || node.props['aria-label'] === '解除关联'
      )))
    expect(controls.length).toBeGreaterThan(7)
    for (const control of controls) expect.soft(control.props.disabled).toBe(true)
    precision.props.onChange({ target: { value: '精加工' } })
    selectedFeature.props.onChange()
    const unlink = visit(root).find(node => node.props['aria-label'] === '解除关联')
    unlink.props.onClick({ stopPropagation() {} })
    await Vue.nextTick()
    expect.soft(precision.props.value).toBe('半精加工')
    expect.soft(selectedFeature.props.checked).toBe(true)
    expect.soft(visit(root).filter(node => node.props['aria-label'] === '解除关联')).toHaveLength(1)

    response.resolve(success)
    await saving
    await Vue.nextTick()
    expect(precision.props.disabled).toBe(false)
    expect(precision.props.value).toBe('半精加工')
    expect(visit(root).filter(node => node.props['aria-label'] === '解除关联')).toHaveLength(1)
    if (!success) expect(nodeText(findMappingAction(root))).toContain('保存工步映射')
  })
})

describe('final-step mapping decisions', () => {
  it('enters rule finalization from a clean saved mapping without saving again', async () => {
    const mapping = savedFinalStepMapping()
    model.template.value.step_mappings = [mapping]
    model.draftStepMappings.value = [mapping]
    model.saveStepMappings = vi.fn().mockResolvedValue(true)
    const emitted: string[] = []
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, {
      modelValue: true,
      projectId: 28,
      legacyAliases: {},
      embedded: true,
      operations: [finalOperation('a')],
      onContinue: () => emitted.push('continue'),
    })
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const action = findMappingAction(root)
    expect(nodeText(action)).toContain('进入规则定稿')
    action.props.onClick()
    expect(model.saveStepMappings).not.toHaveBeenCalled()
    expect(emitted).toEqual(['continue'])
  })

  it('saves dirty mappings first and only enters finalization on the next click', async () => {
    const mapping = savedFinalStepMapping()
    model.template.value.step_mappings = [mapping]
    model.draftStepMappings.value = [mapping]
    model.saveStepMappings = vi.fn().mockResolvedValue(true)
    const emitted: string[] = []
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, {
      modelValue: true,
      projectId: 28,
      legacyAliases: {},
      embedded: true,
      operations: [{ ...finalOperation('a'), precision: '' }],
      onContinue: () => emitted.push('continue'),
    })
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
    const precision = visit(root).find(node => node.type === 'select' && node.props['aria-label'] === '钻孔加工工序精度')
    precision.props.onChange({ target: { value: '精加工' } })
    await Vue.nextTick()
    const saveAction = findMappingAction(root)
    expect(nodeText(saveAction)).toContain('保存工步映射')
    await saveAction.props.onClick()
    await Vue.nextTick()

    expect(model.saveStepMappings).toHaveBeenCalledTimes(1)
    expect(emitted).toEqual([])
    const continueAction = findMappingAction(root)
    expect(nodeText(continueAction)).toContain('进入规则定稿')
    continueAction.props.onClick()
    expect(emitted).toEqual(['continue'])
  })

  it('blocks continuation when no valid mapping has been saved', async () => {
    model.template.value.step_mappings = []
    model.draftStepMappings.value = []
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, {
      modelValue: true,
      projectId: 28,
      legacyAliases: {},
      embedded: true,
      operations: [finalOperation('a')],
    })
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const action = findMappingAction(root)
    expect(nodeText(action)).toContain('关联工步后继续')
    expect(action.props.disabled).toBe(true)
  })

  it('renders an editable precision selector for unresolved machining operations', async () => {
    const props = Vue.reactive({
      modelValue: true, projectId: 28, legacyAliases: {}, embedded: true,
      operations: [{ ...finalOperation('precision_unknown'), precision: '' }],
    })
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, props)
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
    const selectors = visit(root).filter(node => node.type === 'select' && node.props['aria-label'] === '钻孔加工工序精度')
    expect(selectors).toHaveLength(1)
    expect(visit(selectors[0]).filter(node => node.type === 'option').map(node => node.props.value)).toEqual([
      '', '粗加工', '半精加工', '精加工',
    ])
  })

  it('marks selected precision as unsaved and includes it in the mapping save payload', async () => {
    const operation = { ...finalOperation('precision_unknown'), precision: '' }
    model.saveStepMappings = vi.fn().mockResolvedValue(true)
    const { state } = mount(1, [operation])
    await Vue.nextTick()

    expect(state.dirty.value).toBe(false)
    state.setOperationPrecision(operation, '半精加工')
    expect(state.dirty.value).toBe(true)

    await state.saveStepMappings()

    expect(model.saveStepMappings).toHaveBeenCalledWith(expect.objectContaining([
      expect.objectContaining({ process_id: 'precision_unknown', precision: '半精加工' }),
    ]))
    expect(state.dirty.value).toBe(false)
  })

  it('restores a saved precision and displays auxiliary precision as read only', async () => {
    const operation = { ...finalOperation('precision_unknown'), precision: '' }
    model.template.value.mapping_output = [{ process_id: 'precision_unknown', precision: '精加工' }]
    const props = Vue.reactive({
      modelValue: true, projectId: 28, legacyAliases: {}, embedded: true,
      operations: [operation, { ...finalOperation('aux', []), id: 103, process_type: '辅助工序', steps: [], precision: '辅助工序' }],
    })
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, props)
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
    const nodes = visit(root)
    const machiningSelector = nodes.find(node => node.type === 'select' && node.props['aria-label'] === '钻孔加工工序精度')
    expect(machiningSelector?.props.value).toBe('精加工')
    expect(nodes.filter(node => node.type === 'select')).toHaveLength(1)
    expect(nodes.some(node => node.text === '辅助工序')).toBe(true)
  })

  it('does not ask users to confirm generic steps', async () => {
    const props = Vue.reactive({
      modelValue: true, projectId: 28, legacyAliases: {}, embedded: true,
      operations: [finalOperation('a')],
    })
    const root: any = { type: 'root', children: [], props: {} }
    app = renderRenderer.createApp(renderModule.exports.default, props)
    app.mount(root)
    await Vue.nextTick()
    await Promise.resolve()
    await Vue.nextTick()

    const visit = (node: any): any[] => [node, ...(node.children || []).flatMap(visit)]
    const actionLabels = visit(root)
      .filter(node => node.type === 'button')
      .map(node => `${node.text || ''}${(node.children || []).map((child: any) => child.text || '').join('')}`)

    expect(actionLabels).not.toContain('确认为通用工步')
    expect(template).not.toContain('撤销通用确认')
    expect(template).toContain('分组覆盖 {{ coveredFeatureGroupCount }}/{{ featureGroupCount }}')
    expect(template).toContain('未覆盖 {{ uncoveredFeatureGroupCount }}')
    expect(template).not.toContain('待审核')
  })

  it('explains machining mapping requirements and auxiliary retention for delivery', () => {
    expect(template).toContain('加工工步只有完成有效特征映射才参与三表交付')
    expect(template).toContain('无映射加工工步不导出')
    expect(template).toContain('未覆盖 {{ uncoveredFeatureGroupCount }}')
    expect(template).not.toContain('待审核')
    expect(template).toContain('辅助工序按规则保留')
  })

  it('keeps the mapping guidance in the top navigation row', () => {
    expect(template).toMatch(/<header class="tgmd-header">[\s\S]*?class="tgmd-review-guidance tgmd-header-guidance"[\s\S]*?class="tgmd-header-actions"/)
    expect(template).not.toMatch(/<section class="tgmd-pane tgmd-operation-pane">[\s\S]*?tgmd-review-guidance/)
  })

  it('does not repeat uncovered groups in the footer when the tree marks them', () => {
    const footer = template.match(/<footer class="tgmd-footer">([\s\S]*?)<\/footer>/)?.[1] || ''
    expect(footer).not.toContain('待映射分组')
    expect(footer).not.toContain('uncoveredFeatureGroupLabels')
    expect(template).toContain(':show-mapping-status="true"')
    expect(treeNodeSource).toContain('待映射')
  })

  it('keeps unmapped feature-dependent steps eligible and does not create a review record', async () => {
    const { state } = mount(1, [finalOperation('a', [11, 12])])
    await Vue.nextTick()

    expect(state.stepRefs.value).toHaveLength(1)
    expect(Object.values(state.draftStepMappings.value)).toHaveLength(0)
    expect(state.operationMappingSummary(state.mappingOperations.value[0])).toContain('未映射')
  })

  it('keeps every final-route operation in sequence and labels its process type', async () => {
    const operations = [
      { ...finalOperation('a'), sequence: 20, name: '钻孔加工' },
      { ...finalOperation('aux', []), sequence: 10, name: '去毛刺', process_type: '辅助工序', steps: [] },
    ]
    const { state } = mount(1, operations)
    await Vue.nextTick()

    expect(state.visibleMappingOperations.value.map((operation: any) => operation.name)).toEqual(['去毛刺', '钻孔加工'])
    expect(state.operationTypeLabel(operations[1])).toBe('辅助工序')
    expect(state.operationTypeLabel(operations[0])).toBe('标准工序')
  })

  it('shows every route step even when it cannot create a feature mapping', async () => {
    const operation = {
      ...finalOperation('a'),
      steps: [{ ...finalOperation('a').steps[0], step_name: '清洗', source_step_name: '清洗' }],
    }
    const { state } = mount(1, [operation])
    await Vue.nextTick()

    expect(state.visibleStepsForOperation(operation).map((step: any) => step.step_name)).toEqual(['清洗'])
    expect(state.eligibleStepKeys.value.has(state.visibleStepsForOperation(operation)[0].step_key)).toBe(false)
  })

  it('restores the old two-pane linking controls and mapped association chips', () => {
    expect(template).toContain('点击选中工步，勾选右侧特征后关联')
    expect(template).toContain('@click="linkActiveStep"')
    expect(template).toContain('multi-select')
    expect(template).toContain('@toggle-feature="toggleSelectedFeature"')
    expect(template).toContain('@click.stop="removeStepMapping(association.mapping, step)"')
    expect(template).not.toContain(':checked="activeLeafStepKeys.has(step.step_key)"')
  })

  it('maps final steps from the selected leaf and preserves independent many-to-many links', async () => {
    model.template.value.tree.push({ key: 'slot', name: '环槽', path: ['环槽'], children: [], feature_selections: ['外环槽'] })
    const { state } = mount(1, [finalOperation('a', [11, 12])])
    await Vue.nextTick()
    const step = state.stepRefs.value[0]
    state.activeStepKey.value = step.step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    expect(state.stepMappings(step)).toEqual([])
    state.linkActiveStep()
    expect(state.leafConfiguration.value.configured.map((leaf: any) => leaf.key)).toEqual(['hole'])
    expect(Object.values(state.draftStepMappings.value).map((mapping: any) => ({
      source_operation_id: mapping.source_operation_id,
      source_step_order: mapping.source_step_order,
      final_targets: mapping.final_targets,
    }))).toEqual([
      { source_operation_id: 11, source_step_order: 1, final_targets: [{ process_id: 'a', step_id: 'a.s1' }] },
      { source_operation_id: 12, source_step_order: 1, final_targets: [{ process_id: 'a', step_id: 'a.s1' }] },
    ])

    state.selectedFeatureKeys.value = [JSON.stringify(['slot', '外环槽'])]
    state.linkActiveStep()
    expect(state.leafConfiguration.value.configured.map((leaf: any) => leaf.key)).toEqual(['hole', 'slot'])

    const holeAssociation = state.displayStepMappings(step).find((association: any) => association.mapping.template_group_path.at(-1) === '孔')
    state.removeStepMapping(holeAssociation.mapping, step)

    expect(state.leafConfiguration.value.configured.map((leaf: any) => leaf.key)).toEqual(['slot'])
    expect(Object.values(state.draftStepMappings.value).every((mapping: any) => mapping.template_group_path.at(-1) === '环槽')).toBe(true)
  })

  it('uses the old select-features-then-link interaction for merged final steps', async () => {
    const operation = finalOperation('a', [11, 12])
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    const step = state.stepRefs.value[0]
    expect(state.activeStepKey).toBeDefined()
    expect(state.selectedFeatureKeys).toBeDefined()
    state.activeStepKey.value = step.step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]

    expect(state.stepMappings(step)).toEqual([])
    expect(state.canLinkActiveStep.value).toBe(true)

    state.linkActiveStep()

    expect(state.stepFeatureMappings(step).map((mapping: any) => ({
      source_operation_id: mapping.source_operation_id,
      final_targets: mapping.final_targets,
      candidate_features: mapping.candidate_features,
    }))).toEqual([
      { source_operation_id: 11, final_targets: [{ process_id: 'a', step_id: 'a.s1' }], candidate_features: ['孔(盲孔)'] },
      { source_operation_id: 12, final_targets: [{ process_id: 'a', step_id: 'a.s1' }], candidate_features: ['孔(盲孔)'] },
    ])
    expect(state.canLinkActiveStep.value).toBe(false)
  })

  it('unlinks one displayed association from a merged target without clearing its split sibling', async () => {
    const { state } = mount(1, [finalOperation('a', [11, 12]), finalOperation('b', [11])])
    await Vue.nextTick()
    const [merged, splitSibling] = state.stepRefs.value
    expect(state.activeStepKey).toBeDefined()
    expect(state.selectedFeatureKeys).toBeDefined()
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    state.activeStepKey.value = splitSibling.step_key
    state.linkActiveStep()
    state.activeStepKey.value = merged.step_key
    state.linkActiveStep()

    const association = state.displayStepMappings(merged)[0]
    expect(association).toBeTruthy()
    state.removeStepMapping(association.mapping, merged)

    expect(state.stepMappings(merged)).toEqual([])
    expect(state.stepMappings(splitSibling)).toHaveLength(1)
  })

  it('repairs a partial lineage link when the selected feature is associated', async () => {
    const operation = finalOperation('a', [11, 12])
    const step = stepMapping.buildTemplateStepRefs(operation as any)[0]!
    model.draftStepMappings.value = [stepMapping.createTemplateStepMapping(step, model.template.value.tree[0])]
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    state.activeStepKey.value = state.stepRefs.value[0].step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    state.linkActiveStep()

    expect(Object.values(state.draftStepMappings.value).map((mapping: any) => mapping.source_operation_id).sort()).toEqual([11, 12])
  })

  it('emits a cancel event from the embedded workbench', async () => {
    const { state, emitted } = mount()
    await Vue.nextTick()
    state.handleCancel()
    expect(emitted).toContainEqual(['cancel'])
  })

  it('keeps all recommended features across merged sources and every split final target', async () => {
    model.template.value.tree[0].feature_selections = ['孔(盲孔)', '孔(通孔)']
    const { state } = mount(1, [finalOperation('a', [11, 12]), finalOperation('b', [11])])
    await Vue.nextTick()
    state.activeGroupKey.value = 'hole'
    state.applySuggestedMappings([
      response.suggestions[0],
      { ...response.suggestions[0], step_key: 'op_12_s01', recommended_features_by_group: { hole: ['孔(通孔)'] } },
    ])
    const a = state.stepRefs.value[0]
    const b = state.stepRefs.value[1]
    expect(state.stepFeatureMappings(a).flatMap((item: any) => item.candidate_features)).toEqual(['孔(盲孔)', '孔(通孔)'])
    expect(state.stepFeatureMappings(b).flatMap((item: any) => item.candidate_features)).toEqual(['孔(盲孔)'])
  })

  it('removes one migrated legacy mapping without affecting a split sibling', async () => {
    const original = stepMapping.buildTemplateStepRefs({ id: 11, name: '钻孔加工', step_items: ['钻孔'] })[0]!
    model.draftStepMappings.value = [stepMapping.createTemplateStepMapping(original, model.template.value.tree[0])]
    const { state } = mount(1, [finalOperation('a'), finalOperation('b')])
    await Vue.nextTick()
    const [a, b] = state.stepRefs.value
    expect(state.stepMappings(a)).toHaveLength(1)
    state.activeStepKey.value = a.step_key
    const association = state.displayStepMappings(a)[0]
    state.removeStepMapping(association.mapping, a)
    expect(state.stepMappings(a)).toHaveLength(0)
    expect(state.stepMappings(b)).toHaveLength(1)
  })

  it('drops legacy general decisions on save and can replace them with a feature mapping', async () => {
    const operation = finalOperation('a', [11, 12])
    const general = stepMapping.createNotApplicableStepMappingsForFinalStep(stepMapping.buildTemplateStepRefs(operation as any)[0]!)
    model.draftStepMappings.value = general
    model.template.value.step_mappings = general
    model.saveStepMappings = vi.fn(async () => {
      model.template.value.step_mappings = [...model.draftStepMappings.value]
      return true
    })
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    const step = state.stepRefs.value[0]
    expect(state.draftStatus.value.invalidCount).toBe(0)
    await state.saveStepMappings()
    expect(model.draftStepMappings.value).toEqual([])
    state.activeGroupKey.value = 'hole'
    state.activeStepKey.value = step.step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    state.linkActiveStep()
    expect(state.stepMappings(step)).toHaveLength(2)
  })

  it('does not allow auxiliary parents to create geometric mappings', async () => {
    const operation = { ...finalOperation('a'), process_type: '辅助工序' }
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    state.activeGroupKey.value = 'hole'
    state.activeStepKey.value = state.stepRefs.value[0].step_key
    state.selectedFeatureKeys.value = [JSON.stringify(['hole', '孔(盲孔)'])]
    expect(state.canLinkActiveStep.value).toBe(false)
  })

  it('exposes stale general lineage and excludes it from the next save', async () => {
    const operation = finalOperation('a')
    const general = stepMapping.createNotApplicableStepMapping(stepMapping.buildTemplateStepRefs(operation as any)[0]!)
    model.draftStepMappings.value = [general]
    operation.steps[0]!.source_step_name = '钻铰孔'
    operation.steps[0]!.source_steps[0]!.source_step_name = '钻铰孔'
    model.saveStepMappings = vi.fn().mockResolvedValue(false)
    const { state } = mount(1, [operation])
    await Vue.nextTick()
    expect(state.draftStatus.value.invalidCount).toBe(1)
    await state.saveStepMappings()
    expect(model.draftStepMappings.value).toEqual([])
  })
})
