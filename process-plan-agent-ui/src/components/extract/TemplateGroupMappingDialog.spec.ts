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
const api = { suggestTemplateStepMappings: vi.fn() }
let model: any
const module = { exports: {} as any }
const iconStub = Vue.defineComponent({ setup: () => () => null })
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
  if (id.endsWith('.vue')) return iconStub
  throw new Error(`Unexpected dependency: ${id}`)
}
new Function('require', 'module', 'exports', code)(testRequire, module, module.exports)
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
})

const finalOperation = (process_id: string, sourceIds = [11]) => ({
  id: process_id === 'a' ? 101 : 102, process_id, name: '钻孔加工', process_type: '加工工序',
  source_operation_ids: sourceIds,
  steps: [{ step_id: `${process_id}.s1`, step_name: '钻孔', kind: 'primary',
    source_operation_id: sourceIds[0], source_step_order: 1, source_step_name: '钻孔',
    source_steps: sourceIds.map(id => ({ source_operation_id: id, source_step_order: 1, source_step_name: '钻孔' })) }],
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

  it('explains that only feature-dependent steps need mapping and others follow process rules', () => {
    expect(template).toContain('只映射依赖零件特征')
    expect(template).toContain('其余工步无需映射')
    expect(template).toContain('未覆盖 {{ uncoveredFeatureGroupCount }}')
    expect(template).not.toContain('待审核')
    expect(template).toContain('最终是否纳入由所属工序规则决定')
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
