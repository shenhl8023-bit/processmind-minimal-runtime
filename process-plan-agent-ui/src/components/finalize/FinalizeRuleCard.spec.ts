import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, describe, expect, it, vi } from 'vitest'
import source from './FinalizeRuleCard.vue?raw'
import * as finalizeRulePackage from '@/utils/finalizeRulePackage'
import * as finalizeRulePresentation from '@/utils/finalizeRulePresentation'
import * as processConfigurationEditor from '@/utils/processConfigurationEditor'
import * as projectConditions from '@/utils/projectConditionFields'
import configurationSource from './ProcessConfigurationEditor.vue?raw'
import conditionSource from './RuleConditionNodeEditor.vue?raw'
import * as guidanceFlow from '@/composables/analysisGuidanceFlow'
import { trailWithGuidanceSnapshot } from '@/composables/analysisQuestionTreeState'
import * as questionTreeState from '@/composables/analysisQuestionTreeState'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'

function compileComponent(source: string) {
const script = compileScript(parse(source).descriptor, { id: 'finalize-rule-card-test', inlineTemplate: true })
const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const componentModule = { exports: {} as any }
new Function('require', 'module', 'exports', code)(
  (id: string) => {
    if (id === 'vue') return Vue
    if (id === '@/utils/finalizeRulePackage') return finalizeRulePackage
    if (id === '@/utils/finalizeRulePresentation') return finalizeRulePresentation
    if (id === '@/utils/processConfigurationEditor') return processConfigurationEditor
    if (id === '@/utils/projectConditionFields') return projectConditions
    if (id === '@/composables/analysisGuidanceFlow') return guidanceFlow
    if (id === '@/composables/analysisQuestionTreeState') return questionTreeState
    if (id === '@/components/finalize/RuleConditionNodeEditor.vue') return conditionComponent
    if (id === '@/components/finalize/ProcessConfigurationEditor.vue') return configurationComponent
    throw new Error(`Unexpected dependency: ${id}`)
  },
  componentModule,
  componentModule.exports,
)
componentModule.exports.default.name = source === conditionSource ? 'RuleConditionNodeEditor' : 'TestRuleComponent'
return componentModule.exports.default
}
const conditionComponent = compileComponent(conditionSource)
const configurationComponent = compileComponent(configurationSource)
const componentModule = { exports: { default: compileComponent(source) } }

describe('PM-068 initial versus edited save state', () => {
  it.each(['draft', 'pending_confirmation', 'confirmed'])('does not label an untouched %s card or an opened editor unsaved', async status => {
    const item: any = relationItem()
    item.conditionReview.status = status
    const before = JSON.stringify(item)
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      expect(textContent(card.host)).not.toContain('未保存')
      expect(findNode(card.host, node => node.props.class === 'rule-evidence') === null).toBe(true)
      expect(textContent(findNode(card.host, node => node.props.class === 'compact-summary-text')!)).not.toBe('')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      openAppearance(card.host)
      await Vue.nextTick()
      expect(textContent(card.host)).not.toContain('未保存')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      expect(JSON.stringify(item)).toBe(before)
    } finally { card.unmount() }
  })

  it('places a real mode-change warning beside the editor actions and retains dirty state until the matching save', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openAppearance(card.host)
      await Vue.nextTick()
      click(buttonByText(card.host, 'Bool 工序'))
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      const header = findNode(card.host, node => node.props.class === 'preview-card-header')!
      expect(textContent(header)).not.toContain('未保存')
      const actions = findNode(card.host, node => node.props.class === 'candidate-footer')!
      expect(textContent(actions)).toContain('未保存')
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      const saved: any = card.configurationEvents[0]?.[1]
      expect(saved.configuration.occurrence).toBe('manual')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      card.state.item.conditionReview = { ...card.state.item.conditionReview, candidate: saved, confirmed: saved }
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      expect(textContent(card.host)).not.toContain('未保存')
    } finally { card.unmount() }
  })
})

type HostNode = {
  type: string
  props: Record<string, any>
  children: HostNode[]
  parent?: HostNode
  text?: string
}

function insert(child: HostNode, parent: HostNode, anchor?: HostNode | null) {
  child.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  if (index < 0) parent.children.push(child)
  else parent.children.splice(index, 0, child)
}

const renderer = Vue.createRenderer({
  createComment: (text: string) => ({ type: '#comment', text, children: [], props: {} }),
  createText: (text: string) => ({ type: '#text', text, children: [], props: {} }),
  createElement: (type: string) => ({
    type, tagName: type.toUpperCase(), children: [], props: {}, text: '', value: '',
    addEventListener() {}, removeEventListener() {},
  }),
  setText: (node: HostNode, text: string) => { node.text = text },
  setElementText: (node: HostNode, text: string) => { node.text = text; node.children = [] },
  patchProp: (node: HostNode, key: string, _previous: unknown, next: unknown) => { node.props[key] = next },
  insert,
  remove: (node: HostNode) => {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  },
  parentNode: (node: HostNode) => node.parent || null,
  nextSibling: (node: HostNode) => {
    const siblings = node.parent?.children || []
    return siblings[siblings.indexOf(node) + 1] || null
  },
  insertStaticContent: (content: string, parent: HostNode, anchor?: HostNode | null) => {
    const node: HostNode = { type: '#static', text: content, children: [], props: {} }
    insert(node, parent, anchor)
    return [node, node]
  },
} as any)

function textContent(node: HostNode): string {
  return `${node.text || ''}${node.children.map(textContent).join('')}`
}

function findNode(node: HostNode, predicate: (candidate: HostNode) => boolean): HostNode | null {
  if (predicate(node)) return node
  for (const child of node.children) {
    const match = findNode(child, predicate)
    if (match) return match
  }
  return null
}

function click(node: HostNode) {
  const handler = node.props.onClick
  const event = { stopPropagation() {} }
  if (Array.isArray(handler)) handler.forEach(callback => callback(event))
  else handler?.(event)
}

// Select explicitly: the full catalog now starts with features for every operation.
async function selectConditionField(host: HostNode, key: string, index = 0) {
  const pickers: HostNode[] = []
  const collect = (node: HostNode) => {
    if (node.type === 'select' && node.props.class === 'rule-control rule-field') pickers.push(node)
    node.children.forEach(collect)
  }
  collect(host)
  pickers[index]!.props.onChange({ target: { value: key } })
  await Vue.nextTick()
}

afterEach(() => vi.unstubAllGlobals())

function relationItem() {
  const candidate = {
    kind: 'process_relation',
    relation: { relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'any' },
    preview: '陈旧摘要：只要有镀铜就纳入除铜',
    field_definitions: [],
  }
  return {
    segment: { id: 'remove_copper', normalized_step_name: '除铜', doc_coverage: { total_docs: 3, hit_docs: 1 } },
    factorNames: [], factorLabels: [], userAnswerLabels: [], userAnswerContextLabels: [],
    systemFactorLabels: [], rawRuleLines: [], availableFactors: [], analysisDraftContext: '',
    conditionText: '镀铜之后安排除铜工序', defaultConditionText: '', edited: false,
    conditionReview: {
      source_text: '镀铜之后安排除铜工序', source_hash: 'hash-relation', status: 'confirmed',
      candidate, confirmed: candidate, confidence: 0.9, issues: [],
      confirmed_by: '审核员', confirmed_at: '2026-10-27T02:00:00Z',
    },
  }
}

function mountCard(item: any, routeSegments: any[] = [item.segment], overrides: Record<string, any> = {}) {
  vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {} })
  const state = Vue.reactive({ item })
  const dirtyEvents: unknown[][] = []
  const confirmedEvents: unknown[][] = []
  const manualEvents: unknown[][] = []
  const configurationEvents: unknown[][] = []
  const parseEvents: unknown[][] = []
  const resetEvents: unknown[][] = []
  const host: HostNode = { type: 'root', children: [], props: {} }
  const app = renderer.createApp({
    render: () => Vue.h(componentModule.exports.default, {
      item: state.item, routeSegments, active: true, displayName: item.segment.normalized_step_name, metaLabel: '', inlineEditing: false,
      inlineEditingText: '', editedBadge: '', editLabel: '', conditionLabel: '',
      conditionFields: [{ key: 'material.grade', label: '材料牌号', category: '材料', type: 'string', operators: ['eq', 'neq'], aliases: [], options: [] }, { key: 'precision.it', label: '尺寸精度', category: '精度', type: 'number', operators: ['lte', 'gte'], aliases: [], options: [] }], processOptions: [
        { process_id: 'remove_copper', display_name: '除铜', main: false },
        { process_id: 'copper', display_name: '镀铜', main: false },
        { process_id: 'nitriding', display_name: '渗氮', main: false },
      ],
      conditionBusy: false, setInlineTextareaRef() {},
      onEditState: (...args: unknown[]) => dirtyEvents.push(args),
      onConfirmCondition: (...args: unknown[]) => confirmedEvents.push(args),
      onSetBoolean: (...args: unknown[]) => manualEvents.push(args),
      onSaveConfiguration: (...args: unknown[]) => configurationEvents.push(args),
      onParseCondition: (...args: unknown[]) => parseEvents.push(args),
      onReset: (...args: unknown[]) => resetEvents.push(args),
      ...overrides,
    }),
  })
  app.mount(host as any)
  return { host, state, dirtyEvents, confirmedEvents, manualEvents, configurationEvents, parseEvents, resetEvents, unmount: () => app.unmount() }
}

function buttonByText(host: HostNode, text: string) {
  return findNode(host, node => node.type === 'button' && textContent(node).trim() === text)!
}

function openAppearance(host: HostNode) {
  click(buttonByText(host, '规则修改'))
}

describe('PM-074 simplified secondary actions', () => {
  it('retains restore-default for an edited rule and hides an otherwise empty menu', async () => {
    const item = { ...relationItem(), edited: true }
    const card = mountCard(item)
    try {
      openAppearance(card.host)
      await Vue.nextTick()
      expect(buttonByText(card.host, '修改原始描述') === null).toBe(true)
      expect(buttonByText(card.host, '重新识别') === null).toBe(true)
      click(buttonByText(card.host, '恢复默认'))
      expect(card.resetEvents).toHaveLength(1)
      expect((card.resetEvents[0]![0] as any).segment.id).toBe('remove_copper')
      card.state.item.edited = false
      await Vue.nextTick()
      expect(findNode(card.host, node => node.type === 'details' && node.props.class === 'configuration-more')).toBeNull()
    } finally { card.unmount() }
  })

  it('retains retry recognition when parsing failed without a candidate', async () => {
    const item: any = relationItem()
    item.conditionReview = { ...item.conditionReview, candidate: null, confirmed: null, status: 'invalid' }
    const card = mountCard(item, [item.segment], { conditionError: '识别失败，请重试' })
    try {
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('识别失败，请重试')
      expect(findNode(card.host, node => node.props.class === 'rule-evidence') === null).toBe(true)
      click(buttonByText(card.host, '重试识别'))
      expect(card.parseEvents).toHaveLength(1)
      expect((card.parseEvents[0]![0] as any).segment.id).toBe('remove_copper')
    } finally { card.unmount() }
  })
})

function frozenDrillingItem(direction = '所有方位') {
  const item: any = relationItem()
  item.segment = { ...item.segment, id: 'drill', normalized_step_name: '钻孔', sequence: 1 }
  const config: AnalysisGuidanceConfiguration = {
    schema_version: '1.0', revision: 4, guidance: '', materials: ['冻结牌号'],
    feature_mappings: { '孔/内孔': ['孔(盲孔)', '孔(通孔)'] }, directions: ['背面', '所有方位'],
    operation_guidance: { 钻孔: { feature_group: '孔/内孔' } },
  }
  const answers = Object.fromEntries(Object.entries({ guided_mode: 'condition', guided_basis: 'feature', guided_features: '孔(盲孔)', guided_direction: direction }).map(([nodeId, value]) => [nodeId, { nodeId, value, label: value }]))
  const draft = guidanceFlow.buildGuidedDraft(item.segment, config, answers, [item.segment])!
  expect(draft.status).toBe('confirmed')
  item.segment.rule_review = { question_trail: trailWithGuidanceSnapshot(Object.values(answers), config) }
  item.conditionReview = { ...item.conditionReview, candidate: draft.candidate, confirmed: draft.candidate }
  return { item, config }
}

it('retains the frozen A/B direction choice through the real third-step draft and fourth-step save controls', async () => {
  const { item } = frozenDrillingItem()
  expect(item.conditionReview.confirmed.field_definitions.map((field: any) => field.key)).toEqual(['project_factor.operation_1a78c49e.features', 'project_factor.operation_1a78c49e.direction'])
  let card = mountCard(item)
  try {
    openAppearance(card.host); await Vue.nextTick()
    // The execution range reopens as one choice within its original frozen domain.
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    expect((card.configurationEvents[0]?.[1] as any).configuration.when).toEqual({ all: [
      { field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(盲孔)'] },
      { field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '所有方位' },
    ] })
    card.unmount()
    card = mountCard(item)
    openAppearance(card.host); await Vue.nextTick()
    const rows = findNode(card.host, node => node.props.class === 'configuration-conditions')!
    const conditionRows = rows.children.filter(node => node.props.class === 'configuration-condition-row')
    const newRow = conditionRows[conditionRows.length - 1]!
    const picker = findNode(newRow, node => node.type === 'select' && node.props.class === 'rule-control rule-value')!
    expect(picker.children.filter(node => node.type === 'option').map(node => node.props.value)).toEqual(['', '背面', '所有方位'])
    picker.props.onChange({ target: { value: '背面' } }); await Vue.nextTick()
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    const saved = card.configurationEvents[0]?.[1] as any
    expect(saved.configuration.when.all).toEqual([
      { field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(盲孔)'] },
      { field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '背面' },
    ])
    expect(saved.field_definitions.find((field: any) => field.key.endsWith('.direction')).options.map((option: any) => option.value)).toEqual(['背面', '所有方位'])
  } finally { card.unmount() }
})

it('keeps referenced rule definitions ahead of a newer saved guidance snapshot', async () => {
  const { item, config } = frozenDrillingItem('背面')
  config.directions = ['新版正面', '所有方位']
  item.segment.rule_review.question_trail = trailWithGuidanceSnapshot([], config)
  const card = mountCard(item)
  try {
    openAppearance(card.host); await Vue.nextTick()
    const picker = findNode(card.host, node => node.type === 'select' && node.props.class === 'rule-control rule-value')!
    expect(picker.children.filter(node => node.type === 'option').map(node => node.props.value)).toEqual(['', '背面', '所有方位'])
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    const saved = card.configurationEvents[0]?.[1] as any
    expect(saved.field_definitions.find((field: any) => field.key.endsWith('.direction')).options.map((option: any) => option.value)).toEqual(['背面', '所有方位'])
  } finally { card.unmount() }
})

it.each(['stable binding', 'exact merged occurrence', 'same-name occurrence', 'ambiguous merged identity'])('restores frozen candidates using %s rather than a generic same-name definition', async identity => {
  const { item, config } = frozenDrillingItem()
  config.feature_mappings = { 孔: ['错误同名特征'], 冻结组: ['正确冻结特征'] }
  config.operation_guidance = { 钻孔: { feature_group: '孔' } }
  const original = { feature_group: '冻结组' }
  const merge = { nodeId: 'merge_name_root', value: '钻孔', label: '钻孔' }
  const trail = identity.includes('merged') ? [merge] : []
  let routeSegments = [item.segment]
  if (identity === 'stable binding') config.operation_guidance['__segment__:drill'] = original
  if (identity === 'exact merged occurrence' || identity === 'ambiguous merged identity') {
    config.operation_guidance['钻孔/钻铰孔#1'] = { feature_group: '孔' }
    config.operation_guidance['钻孔/钻铰孔#2'] = original
    item.segment.source_operation_names = ['钻孔', '钻铰孔']
    item.segment.source_nodes = identity === 'exact merged occurrence' ? ['钻孔/钻铰孔#2'] : ['钻孔', '钻铰孔']
  }
  if (identity === 'same-name occurrence') {
    config.operation_guidance['钻孔#1'] = { feature_group: '孔' }
    config.operation_guidance['钻孔#2'] = original
    routeSegments = [{ ...item.segment, id: 'first' }, item.segment]
  }
  item.segment.rule_review.question_trail = trailWithGuidanceSnapshot(trail, config)
  const candidate = { kind: 'process_configuration', preview: '', field_definitions: [], configuration: { process_id: 'drill', occurrence: 'always', when: null, relations: [] } }
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const card = mountCard(item, routeSegments)
  try {
    openAppearance(card.host); await Vue.nextTick()
    click(buttonByText(card.host, '条件工序')); await Vue.nextTick()
    const add = buttonByText(card.host, '＋ 添加条件')
    if (identity === 'ambiguous merged identity') {
      expect(add.props.disabled).toBe(true)
    } else {
      click(add); await Vue.nextTick()
      const picker = findNode(card.host, node => node.type === 'select' && node.props.multiple != null)!
      expect(textContent(picker)).toContain('正确冻结特征')
      expect(textContent(picker)).not.toContain('错误同名特征')
    }
  } finally { card.unmount() }
})

it('offers every project condition immediately with no catalog toggle, preserving all-direction semantics', async () => {
  const item: any = relationItem()
  item.segment.id = 'drill'
  item.segment.normalized_step_name = '钻孔'
  const candidate = { kind: 'process_configuration', configuration: { process_id: 'drill', occurrence: 'conditional', when: { all: [
    { field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(盲孔)', '孔(通孔)'] },
    { field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '周边' },
  ] }, relations: [] }, field_definitions: [] }
  item.conditionReview.candidate = candidate
  item.conditionReview.confirmed = candidate
  const card = mountCard(item)
  openAppearance(card.host)
  await Vue.nextTick()
  const fieldSelect = findNode(card.host, node => node.type === 'select' && String(node.props.class).includes('rule-field'))!
  expect(textContent(fieldSelect)).toContain('加工对象的特征')
  expect(textContent(fieldSelect)).toContain('材料牌号')
  expect(textContent(fieldSelect)).toContain('目标硬度制')
  expect(textContent(fieldSelect)).not.toContain('钻孔加工对象')
  const multiselect = findNode(card.host, node => node.type === 'select' && node.props.multiple != null)!
  expect(multiselect).toBeTruthy()
  expect(textContent(multiselect)).toContain('内圆柱面')
  expect(textContent(multiselect)).toContain('孔(盲孔)')
  expect(textContent(card.host)).toContain('同一加工对象')
  expect(findNode(card.host, node => node.type === 'button' && /本项目全部条件|收起全部条件/.test(textContent(node)))).toBeNull()
  expect(textContent(fieldSelect)).toContain('材料牌号')
  expect(textContent(fieldSelect)).toContain('明确钻孔要求')
  const direction = findNode(card.host, node => node.type === 'select' && node.props.class === 'rule-control rule-value')!
  direction.props.onChange({ target: { value: '所有方位' } })
  await Vue.nextTick()
  click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
  const saved: any = card.configurationEvents[0]?.[1]
  expect(saved.configuration.when).toEqual({ all: [
    { field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(盲孔)', '孔(通孔)'] },
    { field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '所有方位' },
  ] })
  card.unmount()
})

describe.each(['process_configuration', 'condition'])('frozen field summaries for %s', kind => {
it.each([
  ['features', '钻孔加工对象的特征', '加工对象的特征', 'contains_any', ['冻结孔'], ['冻结槽']],
  ['direction', '钻孔同一加工对象的方位', '同一加工对象的方位', 'eq', '冻结侧', '冻结端'],
  ['it', '钻孔 · 冻结孔的实际尺寸精度等级', '冻结孔的实际尺寸精度等级', 'lte', 7, 6],
  ['ra', '钻孔 · 冻结孔的实际Ra要求值', '冻结孔的实际Ra要求值', 'lte', 0.8, 0.4],
])('keeps frozen %s summaries neutral after editing, cancel and save without mutating the source', async (suffix, oldLabel, label, op, value, editedValue) => {
  const item: any = relationItem()
  item.segment.id = 'drill'; item.segment.normalized_step_name = '钻孔'
  item.conditionText = '当加工对象符合要求时，纳入钻孔工序'
  item.conditionReview.source_text = item.conditionText
  const base = projectConditions.projectConditionFields('drill', '钻孔').find(field => field.key.endsWith(`.${suffix}`))!
  const field = { ...base, label: oldLabel, options: suffix === 'features' ? [{ value: '冻结孔', label: '冻结孔' }, { value: '冻结槽', label: '冻结槽' }] : suffix === 'direction' ? [{ value: '冻结侧', label: '冻结侧' }, { value: '冻结端', label: '冻结端' }] : base.options }
  const when = { field: field.key, op, value }
  const candidate = kind === 'process_configuration'
    ? { kind, preview: '', field_definitions: [field], configuration: { process_id: 'drill', occurrence: 'conditional', relations: [], when } }
    : { kind, preview: '', field_definitions: [field], when, then: { include_process_ids: ['drill'], exclude_process_ids: [] } }
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const before = JSON.stringify(item)
  const card = mountCard(item)
  const editValue = async () => {
    const control = findNode(card.host, node => node.props.class === (suffix === 'features' ? 'rule-control rule-values' : 'rule-control rule-value'))!
    const target = Array.isArray(editedValue) ? { selectedOptions: editedValue.map(value => ({ value })) } : { value: String(editedValue) }
    control.props[control.type === 'select' ? 'onChange' : 'onInput']({ target })
    await Vue.nextTick()
  }
  const expectNeutralSummary = () => {
    const summary = findNode(card.host, node => node.props.class === 'compact-summary-text')!
    expect(summary).not.toBeNull()
    expect(textContent(summary)).toContain(label)
    expect(textContent(summary)).not.toContain(oldLabel)
  }
  try {
    openAppearance(card.host); await Vue.nextTick()
    const picker = findNode(card.host, node => node.type === 'select' && String(node.props.class).includes('rule-field'))!
    const option = findNode(picker, node => node.type === 'option' && node.props.value === field.key)!
    expect(textContent(option)).toContain(label)
    expect(textContent(option)).not.toContain('钻孔')
    expect(textContent(findNode(card.host, node => node.props.class === 'configuration-result')!)).not.toContain(oldLabel)
    await editValue()
    expect(textContent(card.host)).toContain('未保存')
    expect(JSON.stringify(item)).toBe(before)
    click(buttonByText(card.host, '取消')); await Vue.nextTick()
    expect(card.configurationEvents).toHaveLength(0)
    expect(textContent(card.host)).not.toContain('未保存')
    expect(JSON.stringify(item)).toBe(before)
    expectNeutralSummary()

    openAppearance(card.host); await Vue.nextTick()
    const restored = findNode(card.host, node => node.props.class === (suffix === 'features' ? 'rule-control rule-values' : 'rule-control rule-value'))!
    if (Array.isArray(value)) expect(restored.children.filter(node => node.props.selected).map(node => node.props.value)).toEqual(value)
    else expect(String(restored.props.value)).toBe(String(value))
    await editValue()
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    expect(card.configurationEvents).toHaveLength(1)
    const saved: any = card.configurationEvents[0]?.[1]
    expect(saved.field_definitions).toEqual([field])
    expect(saved.configuration.when).toEqual({ field: field.key, op, value: editedValue })
    expect(JSON.stringify(item)).toBe(before)
    // Apply the parent's save response so the assertion exercises the card,
    // rather than the still-open editor's already-neutral result preview.
    card.state.item = { ...card.state.item, conditionReview: { ...card.state.item.conditionReview, candidate: saved, confirmed: saved } }
    await Vue.nextTick()
    expect(findNode(card.host, node => node.props.class === 'configuration-result')).toBeNull()
    expectNeutralSummary()
    expect(JSON.stringify(item)).toBe(before)
  } finally { card.unmount() }
})
})

it.each([
  ['features', '钻孔加工对象的特征', '加工对象的特征', 'contains_any', ['冻结孔'], ['冻结槽']],
  ['direction', '钻孔同一加工对象的方位', '同一加工对象的方位', 'eq', '冻结侧', '冻结端'],
  ['it', '钻孔 · 冻结孔的实际尺寸精度等级', '冻结孔的实际尺寸精度等级', 'lte', 7, 6],
  ['ra', '钻孔 · 冻结孔的实际Ra要求值', '冻结孔的实际Ra要求值', 'lte', 0.8, 0.4],
  ['hardness_unit', '钻孔目标硬度制', '目标硬度制', 'eq', 'HRC', 'HBW'],
  ['hardness_min', '钻孔目标硬度下限（含）', '目标硬度下限（含）', 'gte', 40, 45],
  ['hardness_max', '钻孔目标硬度上限（含）', '目标硬度上限（含）', 'lte', 60, 55],
])('renders legacy exclude %s labels as display copies and preserves frozen source and save semantics', async (suffix, oldLabel, label, op, value, editedValue) => {
  const item: any = relationItem()
  item.segment.id = 'drill'; item.segment.normalized_step_name = '钻孔'
  item.conditionText = '当加工对象符合要求时，排除钻孔工序'
  item.conditionReview.source_text = item.conditionText
  const key = `project_factor.operation_1a78c49e.${suffix}`
  const base = projectConditions.projectConditionFields('drill', '钻孔').find(field => field.key === key)!
  const field = { ...base, label: oldLabel, options: suffix === 'features' ? [{ value: '冻结孔', label: '冻结孔' }, { value: '冻结槽', label: '冻结槽' }] : suffix === 'direction' ? [{ value: '冻结侧', label: '冻结侧' }, { value: '冻结端', label: '冻结端' }] : base.options }
  const candidate = { kind: 'condition', preview: '', field_definitions: [field], when: { field: key, op, value }, then: { include_process_ids: [], exclude_process_ids: ['drill'] } }
  const original = JSON.parse(JSON.stringify(candidate))
  const freeze = (value: any) => {
    if (value && typeof value === 'object') {
      Object.values(value).forEach(freeze)
      Object.freeze(value)
    }
  }
  freeze(candidate)
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const before = JSON.stringify(item)
  const card = mountCard(item)
  const valueControl = () => findNode(card.host, node => node.props.class === (suffix === 'features' ? 'rule-control rule-values' : 'rule-control rule-value'))!
  const editValue = async () => {
    const control = valueControl()
    const target = Array.isArray(editedValue) ? { selectedOptions: editedValue.map(value => ({ value })) } : { value: String(editedValue) }
    control.props[control.type === 'select' ? 'onChange' : 'onInput']({ target })
    await Vue.nextTick()
  }
  try {
    openAppearance(card.host); await Vue.nextTick()
    expect(findNode(card.host, node => node.props.class === 'candidate-editor')).not.toBeNull()
    expect(findNode(card.host, node => node.props.class === 'configuration-result')).toBeNull()
    const picker = findNode(card.host, node => node.props.class === 'rule-control rule-field')!
    expect(picker.props.value).toBe(key)
    const option = findNode(picker, node => node.type === 'option' && node.props.value === key)!
    expect(textContent(option)).toContain(label)
    if (oldLabel !== label) expect(textContent(option)).not.toContain(oldLabel)
    const summary = findNode(card.host, node => node.props.class === 'compact-summary-text')!
    expect(textContent(summary)).toContain(label)
    expect(textContent(summary)).toContain('排除 drill')
    expect(textContent(card.host)).not.toContain('未保存')
    expect(JSON.stringify(item)).toBe(before)

    // Historical exclusion remains unsupported for authoring; display changes
    // must neither enable saving nor emit a rewritten inclusion candidate.
    expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    expect(card.confirmedEvents).toHaveLength(0)
    expect(card.configurationEvents).toHaveLength(0)
    await editValue()
    expect(textContent(card.host)).toContain('未保存')
    expect(JSON.stringify(item)).toBe(before)
    click(buttonByText(card.host, '取消修改')); await Vue.nextTick()
    expect(findNode(card.host, node => node.props.class === 'candidate-editor')).toBeNull()
    expect(textContent(card.host)).not.toContain('未保存')
    expect(card.confirmedEvents).toHaveLength(0)
    expect(JSON.stringify(item)).toBe(before)

    openAppearance(card.host); await Vue.nextTick()
    const restored = valueControl()
    if (Array.isArray(value)) expect(restored.children.filter(node => node.props.selected).map(node => node.props.value)).toEqual(value)
    else expect(String(restored.props.value)).toBe(String(value))
    await editValue()
    expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    expect(card.confirmedEvents).toHaveLength(0)
    expect(card.configurationEvents).toHaveLength(0)
    expect(candidate).toEqual(original)
    expect(JSON.stringify(item)).toBe(before)
  } finally { card.unmount() }
})

it('saves frozen definitions unchanged after an explicit legacy exclude to include choice', async () => {
  const item: any = relationItem()
  item.segment.id = 'drill'; item.segment.normalized_step_name = '钻孔'
  item.conditionText = '当加工对象符合要求时，排除钻孔工序'
  item.conditionReview.source_text = item.conditionText
  const field = { ...projectConditions.projectConditionFields('drill', '钻孔')[0]!, label: '钻孔加工对象的特征' }
  const candidate = { kind: 'condition', preview: '', field_definitions: [field], when: { field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(盲孔)'] }, then: { include_process_ids: [], exclude_process_ids: ['drill'] } }
  Object.freeze(field)
  Object.freeze(candidate.field_definitions)
  Object.freeze(candidate)
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const before = JSON.stringify(item)
  const original = JSON.parse(JSON.stringify(candidate))
  const card = mountCard(item)
  try {
    openAppearance(card.host); await Vue.nextTick()
    const option = findNode(card.host, node => node.type === 'option' && node.props.value === 'project_factor.operation_1a78c49e.features')!
    expect(textContent(option)).toBe('加工对象的特征')
    expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
    click(buttonByText(card.host, '纳入')); await Vue.nextTick()
    expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(false)
    click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
    expect(card.confirmedEvents).toHaveLength(1)
    expect(card.confirmedEvents[0]?.[1]).toEqual({ ...original, then: { include_process_ids: ['drill'], exclude_process_ids: [] } })
    expect(card.configurationEvents).toHaveLength(0)
    expect(JSON.stringify(item)).toBe(before)
  } finally { card.unmount() }
})

it('renders and saves an actual backend composite with nullable inactive fields', async () => {
  const item: any = relationItem()
  item.segment.id = 'drill'; item.segment.normalized_step_name = '钻孔'
  const fields = projectConditions.projectConditionFields('drill', '钻孔')
  const candidate = { kind: 'process_configuration', preview: '', field_definitions: fields, configuration: { process_id: 'drill', occurrence: 'conditional', relations: [], when: { all: [
    { all: null, any: null, not: null, field: 'project_factor.operation_1a78c49e.features', op: 'contains_any', value: ['孔(通孔)', '孔(盲孔)'] },
    { all: null, any: null, not: null, field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '周边' },
  ], any: null, not: null, field: null, op: null, value: null } } }
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const card = mountCard(item)
  openAppearance(card.host); await Vue.nextTick()
  expect(textContent(card.host)).toContain('孔(盲孔)')
  expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(false)
  click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
  const saved: any = card.configurationEvents[0]?.[1]
  expect(saved.configuration.when.all).toHaveLength(2)
  expect(saved.field_definitions.map((field: any) => field.key)).toEqual(['project_factor.operation_1a78c49e.features', 'project_factor.operation_1a78c49e.direction'])
  card.unmount()
})

it('retains a manually entered material grade in its confirmed input definition', async () => {
  const item: any = relationItem()
  const definition = projectConditions.projectConditionFields('remove_copper', '除铜').find(field => field.key === 'project_factor.material_grade')!
  const candidate = { kind: 'process_configuration', preview: '', field_definitions: [definition], configuration: { process_id: 'remove_copper', occurrence: 'conditional', relations: [], when: { field: definition.key, op: 'eq', value: '自定义牌号X99' } } }
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const card = mountCard(item)
  openAppearance(card.host); await Vue.nextTick()
  click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
  const saved: any = card.configurationEvents[0]?.[1]
  expect(saved.field_definitions[0].options.some((option: any) => option.value === '自定义牌号X99')).toBe(true)
  card.unmount()
})

it('keeps the A/B range as a meaningful direction-only condition', async () => {
  const item: any = relationItem()
  item.segment.id = 'drill'; item.segment.normalized_step_name = '钻孔'
  const candidate = { kind: 'process_configuration', preview: '', field_definitions: [], configuration: { process_id: 'drill', occurrence: 'conditional', relations: [], when: { field: 'project_factor.operation_1a78c49e.direction', op: 'eq', value: '所有方位' } } }
  item.conditionReview.candidate = candidate; item.conditionReview.confirmed = candidate
  const card = mountCard(item)
  openAppearance(card.host); await Vue.nextTick()
  expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(false)
  click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
  expect((card.configurationEvents[0]?.[1] as any).configuration.when).toEqual(candidate.configuration.when)
  card.unmount()
})

it('offers a direct rule editor when a generated condition cannot be recognized', async () => {
  const item = relationItem()
  Object.assign(item.conditionReview, { status: 'invalid', candidate: null, confirmed: null,
    issues: ['关联工序只支持跟随一个来源并排在其后；请重新选择出现模式和来源工序。'] })
  const card = mountCard(item)
  const repair = buttonByText(card.host, '设置出现规则')
  expect(repair).toBeTruthy()
  click(repair)
  await Vue.nextTick()
  expect(textContent(card.host)).toContain('出现模式')
  expect(card.configurationEvents).toHaveLength(0)
  card.unmount()
})

function openRelations(host: HostNode) {
  click(buttonByText(host, '规则修改'))
}

function relationTypeSelect(host: HostNode) {
  return findNode(host, node => node.type === 'select' && node.props.class === 'relation-select')!
}

describe('four-mode authoring regressions', () => {
  it.each(['always', 'manual', 'conditional', 'associated'] as const)('can confirm the third-step %s configuration directly', async (occurrence) => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration',
      configuration: {
        process_id: 'remove_copper', occurrence,
        when: occurrence === 'conditional'
          ? { field: 'precision.it', op: 'lte', value: 7 }
          : occurrence === 'manual' ? { field: 'project_factor.manual_process_copper', op: 'eq', value: true } : null,
        relations: occurrence === 'associated'
          ? [{ relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'any' }] : [],
      },
      field_definitions: occurrence === 'manual'
        ? [{ key: 'project_factor.manual_process_copper', label: '是否安排除铜', category: '可选工序', type: 'boolean', operators: ['eq'], aliases: [], options: [], source: '用户直接设定' }] : [],
      preview: '',
    }
    item.conditionReview = { ...item.conditionReview, status: 'pending_confirmation', candidate, confirmed: null }
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      const confirm = buttonByText(card.host, '确认规则')
      expect(confirm).toBeTruthy()
      expect(confirm.props.disabled).toBeFalsy()
      click(confirm)
      expect(card.confirmedEvents).toHaveLength(1)
      expect(card.confirmedEvents[0]?.[1]).toEqual(candidate)
    } finally { card.unmount() }
  })

  it('lets an unsupported exclusion be reconstructed only after choosing a mode', async () => {
    const item: any = relationItem()
    const candidate = { kind: 'condition', when: { field: 'material.grade', op: 'eq', value: '6061' }, then: { include_process_ids: [], exclude_process_ids: ['remove_copper'] }, field_definitions: [], preview: '' }
    item.conditionText = '当材料为6061时排除除铜'
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, candidate, confirmed: candidate }
    const card = mountCard(item)
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      const rebuild = buttonByText(card.host, '选择出现模式重新设置')
      expect(rebuild).not.toBeNull()
      click(rebuild); await Vue.nextTick()
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host, 'Bool 工序')); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect(card.configurationEvents[0]?.[1]).toMatchObject({ configuration: { occurrence: 'manual', when: { op: 'eq', value: true }, relations: [] } })
      expect(item.conditionReview.confirmed).toEqual(candidate)
    } finally { card.unmount() }
  })

  it('shows a single cancel action in the header while a legacy exclusion is edited', async () => {
    const item: any = relationItem()
    const candidate = { kind: 'condition', when: { field: 'material.grade', op: 'eq', value: '6061' }, then: { include_process_ids: [], exclude_process_ids: ['remove_copper'] }, field_definitions: [], preview: '' }
    item.conditionText = '当材料为6061时排除除铜'
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, candidate, confirmed: candidate }
    const before = JSON.stringify(item)
    const card = mountCard(item)
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      const actions = findNode(card.host, node => node.props.class === 'card-edit-slot')!
      expect(buttonByText(actions, '取消修改')).not.toBeNull()
      expect(buttonByText(actions, '规则修改')).toBeNull()
      click(buttonByText(actions, '取消修改')); await Vue.nextTick()
      expect(findNode(card.host, node => node.props.class === 'candidate-editor')).toBeNull()
      expect(buttonByText(card.host, '规则修改')).not.toBeNull()
      expect(JSON.stringify(item)).toBe(before)
    } finally { card.unmount() }
  })
  it.each([
    { any: [{ field: 'material.grade', op: 'eq', value: '6061' }, { field: 'precision.it', op: 'lte', value: 8 }] },
    { not: { field: 'material.grade', op: 'eq', value: '6061' } },
    { field: 'special.requirements', op: 'contains_all', value: [] },
  ])('blocks quick confirmation of unsupported or incomplete conditions: %j', async when => {
    const item: any = relationItem()
    const candidate = { kind: 'condition', when, then: { include_process_ids: ['remove_copper'], exclude_process_ids: [] }, field_definitions: [], preview: '' }
    item.conditionText = '当材料为6061或尺寸精度达到IT8时纳入除铜'
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, status: 'pending_confirmation', candidate, confirmed: null }
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      expect(textContent(findNode(card.host, n => n.props.class === 'compact-summary-text')!)).not.toBe('')
      const confirm = buttonByText(card.host, '确认规则')
      expect(confirm.props.disabled).toBe(true)
      click(confirm); await Vue.nextTick()
      expect(card.confirmedEvents).toHaveLength(0)
      openAppearance(card.host); await Vue.nextTick()
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      expect(textContent(card.host)).not.toContain('旧版组合')
      click(buttonByText(card.host, '主工序')); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect(card.configurationEvents[0]?.[1]).toMatchObject({ configuration: { occurrence: 'always', when: null, relations: [] } })
      expect(item.conditionReview.candidate).toEqual(candidate)
    } finally { card.unmount() }
  })

  it('keeps an exclusion-to-inclusion edit dirty when transferred to configuration until the server saves it', async () => {
    const item: any = relationItem()
    const original = { kind: 'condition', when: { field: 'material.grade', op: 'eq', value: '6061' }, then: { include_process_ids: [], exclude_process_ids: ['remove_copper'] }, field_definitions: [], preview: '' }
    item.conditionText = '当材料为6061时排除除铜'
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, candidate: original, confirmed: original }
    const card = mountCard(item)
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host, '纳入')); await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      click(buttonByText(card.host, '调整出现方式')); await Vue.nextTick()
      expect(buttonByText(card.host, '条件工序')).not.toBeNull()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      expect(textContent(card.host)).toContain('未保存')
      expect(textContent(card.host)).not.toContain('✓ 已确认')
      card.state.item = JSON.parse(JSON.stringify(card.state.item)); await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect(card.state.item.conditionReview.confirmed.then.exclude_process_ids).toEqual(['remove_copper'])
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      const saved: any = card.configurationEvents[0]?.[1]
      expect(saved.configuration).toMatchObject({ occurrence: 'conditional', when: original.when, relations: [] })
      card.state.item.conditionReview.candidate = saved
      card.state.item.conditionReview.confirmed = saved
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
    } finally { card.unmount() }
  })

  it('retains custom field options through edits and mode switches and prunes only the saved payload', async () => {
    const item: any = relationItem()
    const field = { key: 'project_factor.finish', label: '表面类别', category: '项目', type: 'single_select', operators: ['eq'], options: [{ value: 'A', label: 'A类' }], allow_custom: true }
    const candidate = { kind: 'process_configuration', field_definitions: [field], preview: '', configuration: { process_id: 'remove_copper', occurrence: 'conditional', when: { field: field.key, op: 'eq', value: 'A' }, relations: [] } }
    item.conditionReview = { ...item.conditionReview, candidate, confirmed: candidate }
    const card = mountCard(item)
    const fieldSelect = () => findNode(card.host, n => n.type === 'select' && n.props.class === 'rule-control rule-field')!
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      fieldSelect().props.onChange({ target: { value: 'project_factor.material_grade' } }); await Vue.nextTick()
      expect(findNode(fieldSelect(), n => n.type === 'option' && n.props.value === field.key)).not.toBeNull()
      click(buttonByText(card.host, 'Bool 工序')); await Vue.nextTick()
      click(buttonByText(card.host, '条件工序')); await Vue.nextTick()
      expect(findNode(fieldSelect(), n => n.type === 'option' && n.props.value === field.key)).not.toBeNull()
      fieldSelect().props.onChange({ target: { value: field.key } }); await Vue.nextTick()
      findNode(card.host, n => n.type === 'select' && n.props.class === 'rule-control rule-value')!.props.onChange({ target: { value: 'A' } }); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).field_definitions).toEqual([field])
      fieldSelect().props.onChange({ target: { value: 'project_factor.material_grade' } }); await Vue.nextTick()
      findNode(card.host, n => n.type === 'input' && n.props.class === 'rule-control rule-value')!.props.onInput({ target: { value: '6061' } }); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[1]?.[1] as any).field_definitions.map((field: any) => field.key)).toEqual(['project_factor.material_grade'])
      expect(findNode(fieldSelect(), n => n.type === 'option' && n.props.value === field.key)).not.toBeNull()
    } finally { card.unmount() }
  })
})

describe('four independent process modes', () => {
  it.each([
    ['always', '主工序'], ['manual', 'Bool 工序'],
    ['conditional', '条件工序'], ['associated', '关联工序'],
  ])('labels saved %s configurations consistently with the editor', async (occurrence, label) => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration', preview: '', field_definitions: [],
      configuration: { process_id: 'remove_copper', occurrence, when: null, relations: [] },
    }
    item.conditionReview.candidate = candidate
    item.conditionReview.confirmed = candidate
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      const badge = findNode(card.host, node => String(node.props.class || '').includes('card-mode-badge'))
      expect(textContent(badge!)).toBe(label)
    } finally { card.unmount() }
  })

  it('uses one entry and a single-source association with no extra relation choices', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      click(buttonByText(card.host, '规则修改')); await Vue.nextTick()
      for (const label of ['主工序', 'Bool 工序', '条件工序', '关联工序']) expect(buttonByText(card.host, label)).not.toBeNull()
      expect(buttonByText(card.host, '设置工序关联')).toBeNull()
      expect(relationTypeSelect(card.host)).toBeNull()
      expect(textContent(card.host)).toContain('允许穿插其他工序')
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({
        occurrence: 'associated', when: null,
        relations: [{relation_type:'trigger_after',source_process_ids:['copper'],target_process_ids:['remove_copper']}],
      })
    } finally { card.unmount() }
  })

  it('uses only all triples, warns when empty and restores drafts across mode changes', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick(); click(buttonByText(card.host, '规则修改')); await Vue.nextTick()
      click(buttonByText(card.host, '条件工序')); await Vue.nextTick()
      expect(textContent(card.host)).toContain('请自行添加至少一条条件')
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host, '＋ 添加条件')); await Vue.nextTick()
      await selectConditionField(card.host, 'project_factor.material_grade')
      findNode(card.host, node => node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}})
      await Vue.nextTick(); click(buttonByText(card.host, '＋ 添加条件')); await Vue.nextTick()
      await selectConditionField(card.host, 'project_factor.material_grade', 1)
      const values:HostNode[]=[]; const collect=(n:HostNode)=>{if(n.type==='input'&&n.props.class==='rule-control rule-value')values.push(n);n.children.forEach(collect)};collect(card.host)
      values[1]!.props.onInput({target:{value:'9Cr18'}}); await Vue.nextTick()
      expect(findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='条件满足方式')).toBeNull()
      click(buttonByText(card.host, '关联工序')); await Vue.nextTick()
      click(buttonByText(card.host, '条件工序')); await Vue.nextTick()
      expect(textContent(card.host)).toContain('全部满足才安排')
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({
        occurrence:'conditional', relations:[], when:{all:[{field:'project_factor.material_grade',op:'eq',value:'6061'},{field:'project_factor.material_grade',op:'eq',value:'9Cr18'}]},
      })
    } finally {card.unmount()}
  })

  it('does not retain association gates or hidden conditions when selecting Bool or mainline', async () => {
    const card=mountCard(relationItem())
    try {
      await Vue.nextTick();click(buttonByText(card.host,'规则修改'));await Vue.nextTick()
      click(buttonByText(card.host,'Bool 工序'));await Vue.nextTick()
      expect(textContent(card.host)).toContain('不选就是否')
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({occurrence:'manual',when:{op:'eq',value:true},relations:[]})
      click(buttonByText(card.host,'主工序'));await Vue.nextTick()
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      expect((card.configurationEvents[1]?.[1] as any).configuration).toMatchObject({occurrence:'always',when:null,relations:[]})
    } finally {card.unmount()}
  })

  it('requires explicit replacement of mixed legacy rules before saving', async () => {
    const item:any=relationItem()
    const candidate={kind:'process_configuration',preview:'',field_definitions:[],configuration:{process_id:'remove_copper',occurrence:'conditional',when:{any:[{field:'material.grade',op:'eq',value:'6061'}]},relations:[item.conditionReview.candidate.relation]}}
    item.conditionReview.candidate=candidate;item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();click(buttonByText(card.host,'规则修改'));await Vue.nextTick()
      expect(textContent(card.host)).toContain('请选择一种出现模式重新设置')
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host,'条件工序'));await Vue.nextTick()
      expect(textContent(card.host)).toContain('请自行添加至少一条条件')
      expect(item.conditionReview.confirmed).toEqual(candidate)
    } finally {card.unmount()}
  })
})

describe('finalize rule card process IDs', () => {
  it.each(['always', 'conditional'])('removes unused manual factors when switching to %s', async (mode) => {
    const item:any=relationItem(); const bool=finalizeRulePackage.buildManualBooleanRuleCandidate(item,'是否除铜')
    const candidate={kind:'process_configuration',preview:'',field_definitions:bool.field_definitions,configuration:{process_id:'remove_copper',occurrence:'manual',when:bool.when,relations:[]}}
    item.conditionReview.candidate=candidate; item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      click(buttonByText(card.host,mode==='always'?'主工序':'条件工序'));await Vue.nextTick()
      if(mode==='conditional') {
        click(buttonByText(card.host,'＋ 添加条件'));await Vue.nextTick()
        await selectConditionField(card.host, 'project_factor.material_grade')
        findNode(card.host,node=>node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}});await Vue.nextTick()
      }
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      const saved=card.configurationEvents[0]?.[1] as any
      expect(saved.field_definitions.map((field: any) => field.key)).toEqual(mode === 'conditional' ? ['project_factor.material_grade'] : [])
      expect(saved.configuration.occurrence).toBe(mode)
    } finally {card.unmount()}
  })

  it('removes dynamic definitions after deleting their last condition and preserves custom scalar values', async () => {
    const item:any=relationItem()
    const dynamic={key:'project_factor.test_requirement',label:'特殊要求',category:'要求',type:'single_select',operators:['eq'],aliases:[],allow_custom:true,options:[{value:'标准要求',label:'标准要求'}]}
    const candidate={kind:'process_configuration',preview:'',field_definitions:[dynamic],configuration:{process_id:'remove_copper',occurrence:'conditional',when:{all:null,any:null,not:null,field:dynamic.key,op:'eq',value:'除铜要求'},relations:[]}}
    item.conditionReview.candidate=candidate;item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      const select=findNode(card.host,node=>node.type==='select' && node.props.class==='rule-control rule-value')!
      expect(findNode(select,node=>node.type==='option' && node.props.value==='除铜要求')).not.toBeNull()
      click(buttonByText(card.host,'删除条件'));await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host,'＋ 添加条件'));await Vue.nextTick()
      await selectConditionField(card.host, 'project_factor.material_grade')
      findNode(card.host,node=>node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}});await Vue.nextTick()
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).field_definitions.map((field: any) => field.key)).toEqual(['project_factor.material_grade'])
    } finally {card.unmount()}
  })

  it('opens nullable backend conditions and adds a new condition without losing their values', async () => {
    const item:any=relationItem()
    const leaf={all:null,any:null,not:null,field:'material.grade',op:'eq',value:'6061'}
    const candidate={kind:'condition',when:leaf,then:{include_process_ids:['remove_copper'],exclude_process_ids:[]},preview:'',field_definitions:[]}
    item.conditionReview.candidate=candidate; item.conditionReview.confirmed=candidate
    item.conditionText='当材料6061时纳入除铜'; item.conditionReview.source_text=item.conditionText
    const card=mountCard(item)
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(false)
      click(buttonByText(card.host,'＋ 添加条件')); await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      expect(findNode(card.host,node=>node.type==='select' && node.props['aria-label']==='条件满足方式')).toBeNull()
    } finally {card.unmount()}
  })
  it('requires an appearance condition before saving a legacy ordering-only rule', async () => {
    const item=relationItem(); item.conditionReview.candidate.relation.relation_type='order_after'
    const card=mountCard(item)
    try {
      await Vue.nextTick(); openRelations(card.host); await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host,'条件工序')); await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件')); await Vue.nextTick()
      await selectConditionField(card.host, 'project_factor.material_grade')
      findNode(card.host,node=>node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}})
      await Vue.nextTick()
      click(buttonByText(card.host,'保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({
        occurrence: 'conditional',
        when: { field: 'project_factor.material_grade', op: 'eq', value: '6061' },
        relations: [],
      })
    } finally {card.unmount()}
  })

  it('keeps a cleared numeric condition empty and blocks saving', async () => {
    const card=mountCard(relationItem())
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host,'条件工序'));await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件')); await Vue.nextTick()
      const fieldSelect = findNode(card.host,node=>node.type==='select' && node.props.class==='rule-control rule-field')!
      const ra = findNode(fieldSelect, node => node.type === 'option' && String(node.props.value).endsWith('.ra'))!
      fieldSelect.props.onChange({target:{value:ra.props.value}})
      await Vue.nextTick()
      const input=findNode(card.host,node=>node.type==='input' && node.props.type==='number')!
      input.props.onInput({target:{value:''}}); await Vue.nextTick()
      expect(input.props.value).toBe('')
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
    } finally {card.unmount()}
  })

  it('blocks a missing manual label and saves the renamed bool without hidden associations', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host, 'Bool 工序')); await Vue.nextTick()
      const input = findNode(card.host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')!
      input.props.onInput({target:{value:''}}); await Vue.nextTick()
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      input.props.onInput({target:{value:'是否除铜'}}); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({ occurrence:'manual', when:{op:'eq',value:true}, relations:[] })
    } finally {card.unmount()}
  })

  it('leaves legacy any groups untouched until a new mode is explicitly selected', async () => {
    const item:any = relationItem()
    const original:any = {kind:'process_configuration',preview:'',field_definitions:[],configuration:{process_id:'remove_copper',occurrence:'conditional',when:{any:[{field:'material.grade',op:'eq',value:'6061'}]},relations:[]}}
    item.conditionReview.candidate=original;item.conditionReview.confirmed=original
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      expect(findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='条件满足方式')).toBeNull()
      click(buttonByText(card.host,'关联工序'));await Vue.nextTick()
      findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.onChange({target:{value:'nitriding'}});await Vue.nextTick()
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      const saved=card.configurationEvents[0]?.[1] as any
      expect(saved.configuration).toMatchObject({occurrence:'associated',when:null,relations:[{source_process_ids:['nitriding']}]})
      expect(item.conditionReview.confirmed).toEqual(original)
    } finally {card.unmount()}
  })

  it('adds all-match triples and removing the last one prevents saving', async () => {
    const card=mountCard(relationItem())
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      click(buttonByText(card.host,'条件工序'));await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件'));await Vue.nextTick()
      await selectConditionField(card.host, 'project_factor.material_grade')
      findNode(card.host,n=>n.type==='input'&&n.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}});await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件'));await Vue.nextTick()
      click(buttonByText(card.host,'删除条件'));await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      click(buttonByText(card.host,'删除条件'));await Vue.nextTick()
      expect(textContent(card.host)).toContain('请自行添加至少一条条件')
      expect(card.configurationEvents).toHaveLength(0)
    } finally {card.unmount()}
  })

  it('opens one rule entry and changes modes locally until saving', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      const edit = buttonByText(card.host, '规则修改')
      expect(edit).not.toBeNull()
      click(edit)
      await Vue.nextTick()
      click(buttonByText(card.host, '主工序'))
      await Vue.nextTick()
      expect(card.configurationEvents).toHaveLength(0)
      expect(card.manualEvents).toHaveLength(0)
      expect(textContent(card.host)).toContain('未保存')
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      expect(card.configurationEvents[0]?.[1]).toMatchObject({ kind: 'process_configuration', configuration: { process_id: 'remove_copper', occurrence: 'always' } })
    } finally { card.unmount() }
  })

  it('reopens a saved manual choice with its label and saves it again as a manual confirmation', async () => {
    vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {} })
    const label = '前面出现镀铜时，安排除铜'
    const item: any = {
      segment: { id: 'remove_copper', normalized_step_name: '除铜', doc_coverage: { total_docs: 3, hit_docs: 1 } },
      factorNames: [], factorLabels: [], userAnswerLabels: [], userAnswerContextLabels: [],
      systemFactorLabels: [], rawRuleLines: [], availableFactors: [], analysisDraftContext: '',
      conditionText: `当用户选择“${label}”为是时，纳入“除铜”工序。`, edited: true,
    }
    const candidate = finalizeRulePackage.buildManualBooleanRuleCandidate(item, label)
    item.conditionReview = {
      source_text: item.conditionText, status: 'confirmed', candidate, confirmed: candidate,
      confirmed_by: '用户直接设定', confirmed_at: '2026-10-27T02:00:00Z',
    }
    const emitted: unknown[][] = []
    const host: HostNode = { type: 'root', children: [], props: {} }
    const app = renderer.createApp({
      render: () => Vue.h(componentModule.exports.default, {
        item, active: true, displayName: '除铜', metaLabel: '', inlineEditing: false,
        inlineEditingText: '', editedBadge: '', editLabel: '', conditionLabel: '',
        conditionFields: [], processOptions: [{ process_id: 'remove_copper', display_name: '除铜', main: false }],
        conditionBusy: false, setInlineTextareaRef() {},
        onSaveConfiguration: (...args: unknown[]) => emitted.push(args),
      }),
    })
    try {
      app.mount(host as any)
      await Vue.nextTick()
      expect(textContent(host)).toContain('Bool 工序')
      expect(textContent(host)).toContain('✓ 已确认')
      click(findNode(host, node => node.type === 'button' && node.props.class === 'preview-edit-btn')!)
      await Vue.nextTick()
      const input = findNode(host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')
      expect(input).not.toBeNull()
      expect(input!.props.value).toBe(label)
      input!.props.onInput({ target: { value: '是否需要除铜' } })
      await Vue.nextTick()
      const save = findNode(host, node => node.type === 'button' && textContent(node).trim() === '保存并确认')
      expect(save).not.toBeNull()
      click(save!)
      expect((emitted[0]?.[1] as any).field_definitions[0].label).toBe('是否需要除铜')
    } finally { app.unmount() }
  })

  it('uses the exported process ID when replacing an unsupported exclusion with inclusion', async () => {
    vi.stubGlobal('document', {
      addEventListener() {},
      removeEventListener() {},
    })

    const emitted: unknown[][] = []
    const host: HostNode = { type: 'root', children: [], props: {} }
    const app = renderer.createApp({
      setup() {
        return () => Vue.h(componentModule.exports.default, {
          item: {
            segment: {
              id: 'segment-internal-42',
              export_process_id: 'process-007',
              normalized_step_name: '磨外圆',
              doc_coverage: { total_docs: 3, hit_docs: 1 },
              source_operation_ids: [],
              factor_reviews: [],
            },
            factorNames: [],
            factorLabels: [],
            userAnswerLabels: [],
            userAnswerContextLabels: [],
            systemFactorLabels: [],
            conditionText: '当外圆粗糙度 Ra1.6 时纳入磨外圆工序',
            defaultConditionText: '',
            conditionReview: {
              status: 'pending_confirmation',
              source_text: '当外圆粗糙度 Ra1.6 时纳入磨外圆工序',
              source_hash: 'hash-42',
              confidence: 0.9,
              issues: [],
              candidate: {
                kind: 'condition',
                when: { field: 'surface.roughness', op: 'lte', value: 1.6 },
                then: { include_process_ids: [], exclude_process_ids: ['process-007'] },
                field_definitions: [],
                preview: '粗糙度不大于 1.6 时纳入磨外圆工序',
              },
            },
            edited: false,
            rawRuleLines: [],
            availableFactors: [],
            analysisDraftContext: '',
          },
          active: false,
          displayName: '磨外圆',
          metaLabel: '',
          inlineEditing: false,
          inlineEditingText: '',
          editedBadge: '',
          editLabel: '',
          conditionLabel: '',
          conditionFields: [],
          processOptions: [{ process_id: 'process-007', display_name: '磨外圆', main: false }],
          conditionBusy: false,
          setInlineTextareaRef: () => {},
          onConfirmCondition: (...args: unknown[]) => emitted.push(args),
        })
      },
    })
    app.mount(host as any)
    await Vue.nextTick()

    const editButton = findNode(host, node => node.type === 'button' && node.props.class === 'preview-edit-btn')
    expect(editButton).not.toBeNull()
    click(editButton!)
    await Vue.nextTick()

    const excludeButton = findNode(host, node => node.type === 'button' && textContent(node).trim() === '排除')
    expect(excludeButton).not.toBeNull()
    click(excludeButton!)
    await Vue.nextTick()

    const saveButton = findNode(host, node => node.type === 'button' && textContent(node).trim() === '保存并确认')
    expect(saveButton).not.toBeNull()
    click(saveButton!)

    expect(saveButton!.props.disabled).toBe(true)
    expect(emitted).toHaveLength(0)
    click(buttonByText(host, '纳入')); await Vue.nextTick()
    click(buttonByText(host, '保存并确认'))
    expect((emitted[0]?.[1] as any)?.then).toMatchObject({ include_process_ids: ['process-007'], exclude_process_ids: [] })
    app.unmount()
  })
})

describe('finalize rule card save protection', () => {
  it('keeps a historical multi-target relationship in its lossless editor', async () => {
    const item: any = relationItem()
    item.conditionReview.confirmed.relation.target_process_ids = ['remove_copper', 'nitriding']
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      expect(card.configurationEvents).toHaveLength(0)
      expect(card.confirmedEvents).toHaveLength(0)
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      expect(card.state.item.conditionReview.confirmed.relation.target_process_ids).toEqual(['remove_copper', 'nitriding'])
    } finally { card.unmount() }
  })

  it('reloads the latest saved rule after cancelling a stale configuration draft', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.onChange({target:{value:'nitriding'}})
      await Vue.nextTick()
      const latest = JSON.parse(JSON.stringify(card.state.item.conditionReview.confirmed))
      latest.relation.source_process_ids = ['nitriding']
      card.state.item.conditionReview.confirmed = latest
      card.state.item.conditionReview.candidate = latest
      await Vue.nextTick()
      click(buttonByText(card.host, '取消'))
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any)?.configuration.relations[0].source_process_ids).toEqual(['nitriding'])
    } finally { card.unmount() }
  })

  it('preserves an exclusion when opening its relationship settings and saving', async () => {
    const item: any = relationItem()
    item.conditionText = '当材料为6061时排除除铜工序'
    item.conditionReview.source_text = item.conditionText
    const candidate = {
      kind: 'condition', preview: '', field_definitions: [],
      when: { field: 'material.grade', op: 'eq', value: '6061' },
      then: { include_process_ids: [], exclude_process_ids: ['remove_copper'] },
    }
    item.conditionReview.candidate = candidate
    item.conditionReview.confirmed = candidate
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      expect(card.configurationEvents).toHaveLength(0)
      expect(card.confirmedEvents).toHaveLength(0)
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      expect(card.state.item.conditionReview.confirmed.then).toEqual({
        include_process_ids: [], exclude_process_ids: ['remove_copper'],
      })
    } finally { card.unmount() }
  })

  it('reopens a saved associated mode and preserves its one source', async () => {
    const item:any=relationItem()
    const candidate={kind:'process_configuration',preview:'',field_definitions:[],configuration:{process_id:'remove_copper',occurrence:'associated',when:null,relations:[item.conditionReview.candidate.relation]}}
    item.conditionReview.candidate=candidate;item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      expect(buttonByText(card.host,'关联工序').props['aria-pressed']).toBe(true)
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toEqual(candidate.configuration)
    } finally {card.unmount()}
  })

  it('asks to reset a historical ordering-only configuration instead of dropping its rule', async () => {
    const item:any=relationItem()
    const candidate={kind:'process_configuration',preview:'',field_definitions:[],configuration:{process_id:'remove_copper',occurrence:'conditional',when:null,relations:[{...item.conditionReview.candidate.relation,relation_type:'order_after'}]}}
    item.conditionReview.candidate=candidate;item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      expect(textContent(card.host)).toContain('请选择一种出现模式重新设置')
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      expect(item.conditionReview.confirmed).toEqual(candidate)
    } finally {card.unmount()}
  })

  it('only offers one source and excludes the current process', async () => {
    const card=mountCard(relationItem())
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      const select=findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!
      expect(select.props.multiple).toBeUndefined()
      expect(findNode(select,n=>n.type==='option'&&n.props.value==='remove_copper')).toBeNull()
      select.props.onChange({target:{value:'nitriding'}});await Vue.nextTick()
      expect(textContent(card.host)).toContain('渗氮纳入路线时，自动生成除铜')
      expect(relationTypeSelect(card.host)).toBeNull()
    } finally {card.unmount()}
  })

  it('marks a changed confirmed relationship unsaved, reports it and restores it on cancel', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.onChange({target:{value:'nitriding'}})
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(textContent(card.host)).not.toContain('✓ 已确认')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      expect(buttonByText(card.host, '修改原始描述')).toBeNull()
      expect(buttonByText(card.host, '重新识别')).toBeNull()
      click(buttonByText(card.host, '取消'))
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      expect(textContent(card.host)).toContain('✓ 已确认')
      expect(textContent(card.host)).not.toContain('未保存')
      openRelations(card.host)
      await Vue.nextTick()
      expect(findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.value).toBe('copper')
    } finally { card.unmount() }
  })

  it('keeps an unsaved local relationship across background refreshes and clears it only after saving that relationship', async () => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration', preview: '', field_definitions: [],
      configuration: {
        process_id: 'remove_copper', occurrence: 'associated',
        when: null,
        relations: [item.conditionReview.candidate.relation],
      },
    }
    item.conditionReview.candidate = candidate
    item.conditionReview.confirmed = candidate
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.onChange({target:{value:'nitriding'}})
      await Vue.nextTick()
      card.state.item = JSON.parse(JSON.stringify(card.state.item))
      card.state.item.conditionReview.confirmed_by = '另一位审核员'
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.value).toBe('nitriding')
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      const saved = card.configurationEvents[card.configurationEvents.length - 1]?.[1] as any
      expect(saved.configuration.relations[0]).toMatchObject({relation_type:'trigger_after',source_process_ids:['nitriding']})
      card.state.item.conditionReview.candidate = saved
      card.state.item.conditionReview.confirmed = saved
      await Vue.nextTick()
      expect(textContent(card.host)).not.toContain('未保存')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
    } finally { card.unmount() }
  })

  it('does not erase unsaved relationship changes when the source text changes in a refresh', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.onChange({target:{value:'nitriding'}})
      await Vue.nextTick()
      card.state.item.conditionText = '渗氮之后安排除铜工序'
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(findNode(card.host,n=>n.type==='select'&&n.props['aria-label']==='跟随工序')!.props.value).toBe('nitriding')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
    } finally { card.unmount() }
  })

  it('reports manual choice label edits and restores the saved label on cancel', async () => {
    const item: any = relationItem()
    item.conditionText = '当用户选择“是否需要除铜”为是时，纳入“除铜”工序。'
    item.edited = true
    const candidate = finalizeRulePackage.buildManualBooleanRuleCandidate(item, '是否需要除铜')
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, candidate, confirmed: candidate }
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openAppearance(card.host)
      await Vue.nextTick()
      const input = findNode(card.host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')!
      input.props.onInput({ target: { value: '是否安排除铜' } })
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(textContent(card.host)).not.toContain('✓ 已确认')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      click(buttonByText(card.host, '取消'))
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      openAppearance(card.host)
      await Vue.nextTick()
      const restored = findNode(card.host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')!
      expect(restored.props.value).toBe('是否需要除铜')
    } finally { card.unmount() }
  })

  it('ignores stale preview text and explains ordering only when both processes are present', async () => {
    const item = relationItem()
    item.conditionReview.candidate.relation.relation_type = 'order_after'
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      const summary = findNode(card.host, node => node.type === 'span' && node.props.class === 'compact-summary')!
      expect(textContent(summary)).toContain('都进入路线')
      expect(textContent(summary)).not.toContain('陈旧摘要')
      expect(textContent(summary)).toContain('不自动纳入')
    } finally { card.unmount() }
  })

  it('explains all required predecessors even when legacy source_match is any', async () => {
    const item = relationItem()
    item.conditionReview.candidate.relation.relation_type = 'requires'
    item.conditionReview.candidate.relation.source_process_ids = ['copper', 'nitriding']
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      const summary = findNode(card.host, node => node.type === 'span' && node.props.class === 'compact-summary')!
      expect(textContent(summary)).toContain('镀铜、渗氮')
      expect(textContent(summary)).toContain('全部')
      expect(textContent(summary)).toContain('之前')
      expect(textContent(summary)).not.toContain('或')
    } finally { card.unmount() }
  })

  it('keeps a manual label draft during refresh and clears it after the matching save response', async () => {
    const item: any = relationItem()
    item.conditionText = '当用户选择“是否需要除铜”为是时，纳入“除铜”工序。'
    item.edited = true
    const candidate = finalizeRulePackage.buildManualBooleanRuleCandidate(item, '是否需要除铜')
    item.conditionReview = { ...item.conditionReview, source_text: item.conditionText, candidate, confirmed: candidate }
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openAppearance(card.host)
      await Vue.nextTick()
      const input = findNode(card.host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')!
      input.props.onInput({ target: { value: '是否安排除铜' } })
      await Vue.nextTick()
      card.state.item = JSON.parse(JSON.stringify(card.state.item))
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      const saved = card.configurationEvents[0]?.[1] as any
      expect(saved.field_definitions[0].label).toBe('是否安排除铜')
      card.state.item.conditionText = '当用户选择“是否安排除铜”为是时，纳入“除铜”工序。'
      card.state.item.conditionReview = {
        ...card.state.item.conditionReview, source_text: card.state.item.conditionText, candidate: saved, confirmed: saved,
      }
      await Vue.nextTick()
      expect(textContent(card.host)).not.toContain('未保存')
      expect(textContent(card.host)).toContain('✓ 已确认')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
    } finally { card.unmount() }
  })
})
