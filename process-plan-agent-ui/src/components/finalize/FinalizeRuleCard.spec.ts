import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, describe, expect, it, vi } from 'vitest'
import source from './FinalizeRuleCard.vue?raw'
import * as finalizeRulePackage from '@/utils/finalizeRulePackage'
import * as finalizeRulePresentation from '@/utils/finalizeRulePresentation'
import * as processConfigurationEditor from '@/utils/processConfigurationEditor'
import configurationSource from './ProcessConfigurationEditor.vue?raw'
import conditionSource from './RuleConditionNodeEditor.vue?raw'

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

function mountCard(item: any) {
  vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {} })
  const state = Vue.reactive({ item })
  const dirtyEvents: unknown[][] = []
  const confirmedEvents: unknown[][] = []
  const manualEvents: unknown[][] = []
  const configurationEvents: unknown[][] = []
  const host: HostNode = { type: 'root', children: [], props: {} }
  const app = renderer.createApp({
    render: () => Vue.h(componentModule.exports.default, {
      item: state.item, active: true, displayName: '除铜', metaLabel: '', inlineEditing: false,
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
    }),
  })
  app.mount(host as any)
  return { host, state, dirtyEvents, confirmedEvents, manualEvents, configurationEvents, unmount: () => app.unmount() }
}

function buttonByText(host: HostNode, text: string) {
  return findNode(host, node => node.type === 'button' && textContent(node).trim() === text)!
}

function openAppearance(host: HostNode) {
  click(buttonByText(host, '设置出现方式'))
}

function openRelations(host: HostNode) {
  click(buttonByText(host, '设置工序关联'))
}

function relationTypeSelect(host: HostNode) {
  return findNode(host, node => node.type === 'select' && node.props.class === 'relation-select')!
}

describe('finalize rule card process IDs', () => {
  it.each(['always', 'conditional'])('removes unused manual factors when switching to %s', async (mode) => {
    const item:any=relationItem(); const bool=finalizeRulePackage.buildManualBooleanRuleCandidate(item,'是否除铜')
    const candidate={kind:'process_configuration',preview:'',field_definitions:bool.field_definitions,configuration:{process_id:'remove_copper',occurrence:'manual',when:bool.when,relations:[]}}
    item.conditionReview.candidate=candidate; item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      click(buttonByText(card.host,mode==='always'?'始终出现（主工序）':'条件判断'));await Vue.nextTick()
      if(mode==='conditional') {
        click(buttonByText(card.host,'＋ 添加条件'));await Vue.nextTick()
        findNode(card.host,node=>node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}});await Vue.nextTick()
        openRelations(card.host);await Vue.nextTick()
        click(buttonByText(card.host,'＋ 添加工序关联'));await Vue.nextTick()
        findNode(card.host,node=>node.type==='select' && node.props['aria-label']==='第1项关联工序')!.props.onChange({target:{value:'copper',multiple:false}});await Vue.nextTick()
      }
      click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      const saved=card.configurationEvents[0]?.[1] as any
      expect(saved.field_definitions).toEqual([])
      expect(saved.configuration.occurrence).toBe(mode)
    } finally {card.unmount()}
  })

  it('removes dynamic definitions after deleting their last condition and preserves custom scalar values', async () => {
    const item:any=relationItem()
    const dynamic={key:'project_factor.test_requirement',label:'特殊要求',category:'要求',type:'single_select',operators:['eq'],aliases:[],allow_custom:true,options:[{value:'标准要求',label:'标准要求'}]}
    const candidate={kind:'process_configuration',preview:'',field_definitions:[dynamic],configuration:{process_id:'remove_copper',occurrence:'conditional',when:{all:null,any:null,not:null,field:dynamic.key,op:'eq',value:'除铜要求'},relations:[{relation_type:'trigger_after',source_process_ids:['copper'],target_process_ids:['remove_copper'],source_match:'all'}]}}
    item.conditionReview.candidate=candidate;item.conditionReview.confirmed=candidate
    const card=mountCard(item)
    try {
      await Vue.nextTick();openAppearance(card.host);await Vue.nextTick()
      const select=findNode(card.host,node=>node.type==='select' && node.props.class==='rule-control rule-value')!
      expect(findNode(select,node=>node.type==='option' && node.props.value==='除铜要求')).not.toBeNull()
      click(buttonByText(card.host,'删除'));await Vue.nextTick();click(buttonByText(card.host,'保存并确认'));await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).field_definitions).toEqual([])
      expect((card.configurationEvents[0]?.[1] as any).configuration.when).toBeNull()
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
      expect(findNode(card.host,node=>node.type==='select' && node.props['aria-label']==='条件满足方式')!.props.value).toBe('all')
    } finally {card.unmount()}
  })
  it('requires an appearance condition before saving a legacy ordering-only rule', async () => {
    const item=relationItem(); item.conditionReview.candidate.relation.relation_type='order_after'
    const card=mountCard(item)
    try {
      await Vue.nextTick(); openRelations(card.host); await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件')); await Vue.nextTick()
      findNode(card.host,node=>node.type==='input' && node.props.class==='rule-control rule-value')!.props.onInput({target:{value:'6061'}})
      await Vue.nextTick()
      click(buttonByText(card.host,'保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({
        occurrence: 'conditional',
        when: { field: 'material.grade', op: 'eq', value: '6061' },
        relations: [{ relation_type: 'order_after' }],
      })
    } finally {card.unmount()}
  })

  it('keeps a cleared numeric condition empty and blocks saving', async () => {
    const card=mountCard(relationItem())
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加条件')); await Vue.nextTick()
      findNode(card.host,node=>node.type==='select' && node.props.class==='rule-control rule-field')!.props.onChange({target:{value:'precision.it'}})
      await Vue.nextTick()
      const input=findNode(card.host,node=>node.type==='input' && node.props.type==='number')!
      input.props.onInput({target:{value:''}}); await Vue.nextTick()
      expect(input.props.value).toBe('')
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
    } finally {card.unmount()}
  })

  it('blocks a missing manual label and saves the renamed bool with independent order', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host, '人工选择')); await Vue.nextTick()
      const input = findNode(card.host, node => node.type === 'input' && node.props.id === 'manual-bool-label-remove_copper')!
      input.props.onInput({target:{value:''}}); await Vue.nextTick()
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
      input.props.onInput({target:{value:'是否除铜'}}); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({ occurrence:'manual', when:{op:'eq',value:true}, relations:[{relation_type:'order_after'}] })
    } finally {card.unmount()}
  })

  it('keeps all linked factors and the any group after a matching save and reopen', async () => {
    const item:any = relationItem()
    const config:any = {kind:'process_configuration',preview:'',field_definitions:[],configuration:{process_id:'remove_copper',occurrence:'conditional',when:{any:[{field:'material.grade',op:'eq',value:'6061'},{not:{field:'material.grade',op:'eq',value:'9Cr18'}}]},relations:[{relation_type:'trigger_after',source_process_ids:['copper'],target_process_ids:['remove_copper'],source_match:'all'}]}}
    item.conditionReview.candidate=config; item.conditionReview.confirmed=config
    const card = mountCard(item)
    try {
      await Vue.nextTick(); openRelations(card.host); await Vue.nextTick()
      click(buttonByText(card.host,'＋ 添加工序关联')); await Vue.nextTick()
      expect(buttonByText(card.host,'保存并确认').props.disabled).toBe(true)
      findNode(card.host,node=>node.type==='select' && node.props['aria-label']==='第2项关联工序')!.props.onChange({target:{value:'nitriding',multiple:false}})
      await Vue.nextTick(); click(buttonByText(card.host,'保存并确认')); await Vue.nextTick()
      const saved=card.configurationEvents[0]?.[1] as any
      expect(saved.configuration.when).toEqual(config.configuration.when)
      expect(saved.configuration.relations).toHaveLength(2)
      expect(saved.configuration.relations[1]).toMatchObject({source_process_ids:['nitriding'],source_match:'all'})
      card.state.item.conditionReview.candidate=saved;card.state.item.conditionReview.confirmed=saved; await Vue.nextTick()
      expect(textContent(card.host)).not.toContain('未保存')
      openAppearance(card.host); await Vue.nextTick()
      expect(findNode(card.host,node=>node.type==='select' && node.props['aria-label']==='条件满足方式')!.props.value).toBe('any')
    } finally {card.unmount()}
  })

  it('adds and removes conditions, saves any matching and keeps numeric blanks invalid', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick(); openAppearance(card.host); await Vue.nextTick()
      click(buttonByText(card.host, '＋ 添加条件')); await Vue.nextTick()
      findNode(card.host, node => node.type === 'input' && node.props.class === 'rule-control rule-value')!.props.onInput({ target: { value: '6061' } })
      await Vue.nextTick(); click(buttonByText(card.host, '＋ 添加条件')); await Vue.nextTick()
      const logic = findNode(card.host, node => node.type === 'select' && node.props['aria-label'] === '条件满足方式')
      expect(logic).not.toBeNull()
      logic!.props.onChange({ target: { value: 'any' } }); await Vue.nextTick()
      const values: HostNode[] = []; const collect = (node: HostNode) => { if (node.type === 'input' && node.props.class === 'rule-control rule-value') values.push(node); node.children.forEach(collect) }; collect(card.host)
      values[1]!.props.onInput({ target: { value: '9Cr18' } }); await Vue.nextTick()
      click(buttonByText(card.host, '保存并确认')); await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration.when).toEqual({ any: [{ field: 'material.grade', op: 'eq', value: '6061' }, { field: 'material.grade', op: 'eq', value: '9Cr18' }] })
      click(buttonByText(card.host, '删除条件')); await Vue.nextTick()
      expect(findNode(card.host, node => node.type === 'select' && node.props['aria-label'] === '条件满足方式')!.props.value).toBe('any')
    } finally { card.unmount() }
  })

  it('opens one rule entry and changes modes locally until saving', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      const edit = buttonByText(card.host, '设置出现方式')
      expect(edit).not.toBeNull()
      click(edit)
      await Vue.nextTick()
      click(buttonByText(card.host, '始终出现（主工序）'))
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
      expect(textContent(host)).toContain('人工选择')
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

  it('uses the exported process ID when saving an exclusion from the card editor', async () => {
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

    expect((emitted[0]?.[1] as any)?.then?.exclude_process_ids).toEqual(['process-007'])
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
      expect((card.confirmedEvents[0]?.[1] as any)?.relation.target_process_ids).toEqual(['remove_copper', 'nitriding'])
    } finally { card.unmount() }
  })

  it('reloads the latest saved rule after cancelling a stale configuration draft', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      relationTypeSelect(card.host).props.onChange({ target: { value: 'requires' } })
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
      expect((card.confirmedEvents[0]?.[1] as any)?.then).toEqual({
        include_process_ids: [], exclude_process_ids: ['remove_copper'],
      })
    } finally { card.unmount() }
  })

  it('separates relationship editing and lets a previous process trigger inclusion by itself', async () => {
    const item: any = relationItem()
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      expect(buttonByText(card.host, '设置出现方式')).not.toBeNull()
      click(buttonByText(card.host, '设置工序关联'))
      await Vue.nextTick()

      expect(relationTypeSelect(card.host).children.map(textContent)).toContain('前序出现后自动带出')
      expect(findNode(card.host, node => node.type === 'button' && textContent(node).trim() === '始终出现（主工序）')).toBeNull()
      expect(findNode(card.host, node => node.type === 'button' && textContent(node).trim() === '＋ 添加条件')).toBeNull()
      expect(textContent(card.host)).toContain('单独设置此关联即可触发，若另设出现条件则需同时满足。')

      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      expect((card.configurationEvents[0]?.[1] as any).configuration).toMatchObject({
        occurrence: 'conditional', when: null,
        relations: [{ relation_type: 'trigger_after', source_process_ids: ['copper'] }],
      })
    } finally { card.unmount() }
  })

  it('explains that ordering alone does not make an optional process appear', async () => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration', preview: '', field_definitions: [],
      configuration: {
        process_id: 'remove_copper', occurrence: 'conditional', when: null,
        relations: [{ relation_type: 'order_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'all' }],
      },
    }
    item.conditionReview.candidate = candidate
    item.conditionReview.confirmed = candidate
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      click(buttonByText(card.host, '设置工序关联'))
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('仅调整顺序不会带出本工序，请点击“设置出现方式”选择条件工序或人工选择。')
      expect(buttonByText(card.host, '保存并确认').props.disabled).toBe(true)
    } finally { card.unmount() }
  })

  it('shows plain-language relationship choices and explains their effect between named processes', async () => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration', preview: '', field_definitions: [],
      configuration: {
        process_id: 'remove_copper', occurrence: 'conditional',
        when: { field: 'material.grade', op: 'eq', value: '6061' },
        relations: [{ relation_type: 'order_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'all' }],
      },
    }
    item.conditionReview.candidate = candidate
    item.conditionReview.confirmed = candidate
    const card = mountCard(item)
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      const select = relationTypeSelect(card.host)
      expect(select.children.map(textContent)).toEqual([
        '前序出现后自动带出', '仅调整先后顺序', '关联工序是前置要求', '不能同时安排',
      ])
      const help = findNode(card.host, node => node.type === 'p' && node.props.class === 'configuration-relation-help')!
      expect(textContent(help)).toBe('只管顺序：镀铜和除铜都纳入路线时，除铜排在镀铜后；不会因此自动纳入工序。')
      select.props.onChange({ target: { value: 'requires' } })
      await Vue.nextTick()
      expect(textContent(help)).toBe('除铜纳入路线时，镀铜必须先纳入；系统会尝试补上镀铜，否则提示依赖未满足。')
      select.props.onChange({ target: { value: 'conflicts' } })
      await Vue.nextTick()
      expect(textContent(help)).toBe('除铜和镀铜不能同时纳入；若两者都被选中，系统会提示冲突。')
    } finally { card.unmount() }
  })

  it('marks a changed confirmed relationship unsaved, reports it and restores it on cancel', async () => {
    const card = mountCard(relationItem())
    try {
      await Vue.nextTick()
      openRelations(card.host)
      await Vue.nextTick()
      relationTypeSelect(card.host).props.onChange({ target: { value: 'order_after' } })
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(textContent(card.host)).not.toContain('✓ 已确认')
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', true])
      expect(buttonByText(card.host, '修改原始描述').props.disabled).toBe(true)
      click(buttonByText(card.host, '取消'))
      await Vue.nextTick()
      expect(card.dirtyEvents[card.dirtyEvents.length - 1]).toEqual(['remove_copper', false])
      expect(textContent(card.host)).toContain('✓ 已确认')
      expect(textContent(card.host)).not.toContain('未保存')
      openRelations(card.host)
      await Vue.nextTick()
      expect(relationTypeSelect(card.host).props.value).toBe('trigger_after')
    } finally { card.unmount() }
  })

  it('keeps an unsaved local relationship across background refreshes and clears it only after saving that relationship', async () => {
    const item: any = relationItem()
    const candidate = {
      kind: 'process_configuration', preview: '', field_definitions: [],
      configuration: {
        process_id: 'remove_copper', occurrence: 'conditional',
        when: { field: 'material.grade', op: 'eq', value: '6061' },
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
      relationTypeSelect(card.host).props.onChange({ target: { value: 'order_after' } })
      await Vue.nextTick()
      card.state.item = JSON.parse(JSON.stringify(card.state.item))
      card.state.item.conditionReview.confirmed_by = '另一位审核员'
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(relationTypeSelect(card.host).props.value).toBe('order_after')
      click(buttonByText(card.host, '保存并确认'))
      await Vue.nextTick()
      const saved = card.configurationEvents[card.configurationEvents.length - 1]?.[1] as any
      expect(saved.configuration.relations[0].relation_type).toBe('order_after')
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
      relationTypeSelect(card.host).props.onChange({ target: { value: 'requires' } })
      await Vue.nextTick()
      card.state.item.conditionText = '渗氮之后安排除铜工序'
      await Vue.nextTick()
      expect(textContent(card.host)).toContain('未保存')
      expect(relationTypeSelect(card.host).props.value).toBe('requires')
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
