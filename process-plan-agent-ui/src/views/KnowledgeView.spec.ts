import * as Vue from 'vue'
import { createRenderer, h, nextTick, reactive } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import source from './KnowledgeView.vue?raw'
import guidanceSource from '@/components/knowledge/KnowledgeGuidanceCard.vue?raw'
import catalogSource from '@/components/knowledge/KnowledgeCatalogPanel.vue?raw'

if (typeof document === 'undefined') {
  ;(globalThis as any).document = { activeElement: null }
}

const mocks = vi.hoisted(() => ({
  saveKnowledgeEvidence: vi.fn(),
  searchKnowledge: vi.fn(),
  listKnowledgeCatalog: vi.fn(),
  getKnowledgeCatalogRecord: vi.fn(),
}))

const routeState = vi.hoisted(() => ({ current: null as any }))

vi.mock('@/api/knowledge', () => mocks)
vi.mock('vue-router', () => ({ useRoute: () => routeState.current }))

const guidanceScript = compileScript(parse(guidanceSource).descriptor, { id: 'knowledge-guidance-test', inlineTemplate: true })
const guidanceCode = transformSync(guidanceScript.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const guidanceModule = { exports: {} as Record<string, any> }
new Function('require', 'module', 'exports', guidanceCode)(
  (id: string) => {
    if (id === 'vue') return Vue
    throw new Error(`Unexpected KnowledgeGuidanceCard dependency: ${id}`)
  }, guidanceModule, guidanceModule.exports,
)

const catalogScript = compileScript(parse(catalogSource).descriptor, { id: 'knowledge-catalog-test', inlineTemplate: true })
const catalogCode = transformSync(catalogScript.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const catalogModule = { exports: {} as Record<string, any> }
new Function('require', 'module', 'exports', catalogCode)(
  (id: string) => {
    if (id === 'vue') return Vue
    if (id === '@/api/knowledge') return mocks
    if (id === '@/components/knowledge/KnowledgeGuidanceCard.vue') return guidanceModule.exports
    throw new Error(`Unexpected catalog dependency: ${id}`)
  }, catalogModule, catalogModule.exports,
)

// Vitest's default Node transform uses the SSR SFC branch. Compile the template
// for the host renderer so the setup logic is exercised by these behavior tests.
const { descriptor } = parse(source)
const script = compileScript(descriptor, { id: 'knowledge-view-test', inlineTemplate: true })
const scriptCode = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const scriptModule = { exports: {} as Record<string, any> }
new Function('require', 'module', 'exports', scriptCode)(
  (id: string) => {
    if (id === 'vue') return Vue
    if (id === 'vue-router') return { useRoute: () => routeState.current }
    if (id === '@/api/knowledge') return mocks
    if (id === '@/components/knowledge/KnowledgeGuidanceCard.vue') return guidanceModule.exports
    if (id === '@/components/knowledge/KnowledgeCatalogPanel.vue') return catalogModule.exports
    throw new Error(`Unexpected KnowledgeView dependency: ${id}`)
  },
  scriptModule,
  scriptModule.exports,
)
const KnowledgeView = scriptModule.exports.default

type HostNode = {
  kind: 'element' | 'text' | 'comment'
  type: string
  props: Record<string, any>
  children: HostNode[]
  parent: HostNode | null
  text?: string
  value?: any
  checked?: boolean
  tagName?: string
  listeners?: Record<string, (event: any) => void>
  addEventListener?: (name: string, listener: (event: any) => void) => void
  removeEventListener?: (name: string) => void
  options?: HostNode[]
  selectedIndex?: number
  multiple?: boolean
}

const renderer = createRenderer({
  createElement(type: string) {
    const node = {
      kind: 'element',
      type,
      tagName: type.toUpperCase(),
      props: {},
      children: [],
      style: {},
      parent: null,
      listeners: {},
      addEventListener(name: string, listener: (event: any) => void) {
        this.listeners![name] = listener
      },
      removeEventListener(name: string) {
        delete this.listeners![name]
      },
    } as HostNode
    if (type === 'select') {
      Object.defineProperty(node, 'options', { get: () => node.children.filter(child => child.type === 'option') })
      node.selectedIndex = -1
      node.multiple = false
    }
    return node
  },
  createText(text: string) {
    return { kind: 'text', type: '#text', props: {}, children: [], parent: null, text }
  },
  createComment(text: string) {
    return { kind: 'comment', type: '#comment', props: {}, children: [], parent: null, text }
  },
  setText(node: HostNode, text: string) {
    node.text = text
  },
  setElementText(node: HostNode, text: string) {
    node.children = [{ kind: 'text', type: '#text', props: {}, children: [], parent: node, text }]
  },
  parentNode(node: HostNode) {
    return node.parent
  },
  nextSibling(node: HostNode) {
    if (!node.parent) return null
    const index = node.parent.children.indexOf(node)
    return index >= 0 ? node.parent.children[index + 1] || null : null
  },
  insert(node: HostNode, parent: HostNode, anchor: HostNode | null = null) {
    node.parent = parent
    if (anchor) {
      const index = parent.children.indexOf(anchor)
      parent.children.splice(index < 0 ? parent.children.length : index, 0, node)
    } else {
      parent.children.push(node)
    }
  },
  remove(node: HostNode) {
    if (!node.parent) return
    const index = node.parent.children.indexOf(node)
    if (index >= 0) node.parent.children.splice(index, 1)
    node.parent = null
  },
  patchProp(node: HostNode, key: string, _previous: unknown, value: unknown) {
    node.props[key] = value
    if (key === 'value') node.value = value
    if (key === 'checked') node.checked = Boolean(value)
  },
  // v-model directives from Vue's runtime-dom expect browser-like controls.
  // The behavior tests only invoke update handlers directly, so a lightweight
  // listener registry is sufficient for the custom renderer.
  insertBefore() {},
  createTextNode() {},
  setTextContent() {},
  parentElement() { return null },
  forcePatchProp() { return false },
  insertStaticContent() {
    return []
  },
  querySelector() {
    return null
  },
  setScopeId() {},
  cloneNode(node: HostNode) {
    return node
  },
} as any)

const mountedApps: Array<{ unmount: () => void }> = []

function textContent(node: HostNode): string {
  if (node.kind === 'text') return node.text || ''
  return node.children.map(textContent).join('')
}

function elements(node: HostNode): HostNode[] {
  return node.kind !== 'element' ? [] : [node, ...node.children.flatMap(elements)]
}

function findByText(root: HostNode, type: string, text: string): HostNode {
  const result = elements(root).find(node => node.type === type && textContent(node).includes(text))
  if (!result) throw new Error(`Unable to find ${type} containing ${text}`)
  return result
}

function findInput(root: HostNode, id: string): HostNode {
  const result = elements(root).find(node => node.type === 'input' && node.props.id === id)
  if (!result) throw new Error(`Unable to find input ${id}`)
  return result
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((resolvePromise, rejectPromise) => {
    resolve = resolvePromise
    reject = rejectPromise
  })
  return { promise, resolve, reject }
}

async function settle() {
  await Promise.resolve()
  await nextTick()
  await Promise.resolve()
  await nextTick()
}

function mountKnowledge(route: {
  project_id?: string
  q?: string
  route_version_id?: string
  operation_context?: string
} = {
  project_id: '1',
  q: 'old',
  route_version_id: '1',
  operation_context: JSON.stringify({ segment_id: 'op-1' }),
}) {
  routeState.current = reactive({
    fullPath: `/knowledge?project_id=${route.project_id || ''}&q=${route.q || ''}`,
    query: route,
  })
  const root = { kind: 'element', type: 'root', props: {}, children: [], parent: null } as HostNode
  const app = renderer.createApp(h(KnowledgeView))
  // The Node transform wraps scoped SFC setup with useSSRContext(). Provide the
  // same small context it expects even though the client template is rendered.
  app.provide(Vue.ssrContextKey, { modules: new Set<string>() })
  app.mount(root)
  mountedApps.push(app)
  return root
}

const itemFixture = {
  id: 'item-1',
  content: '工序依据内容',
  score: 0.9,
  retrieval_method: 'hybrid',
  source: { document_id: 'doc-1', document_name: '工艺规程', page_no: 2, identity: 'doc-1:2' },
}

beforeEach(() => {
  mountedApps.splice(0).forEach(app => app.unmount())
  vi.clearAllMocks()
  mocks.searchKnowledge.mockResolvedValue({ status: 'ok', message: '', answer: '', items: [] })
  mocks.listKnowledgeCatalog.mockReset().mockResolvedValue(catalogFixture())
  mocks.getKnowledgeCatalogRecord.mockReset().mockResolvedValue(detailFixture())
})

describe('knowledge presentation', () => {
  it('keeps Word allowance conditions, zero bounds and growth direction visible when the model is unavailable', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'llm_unavailable', message: '已找到本地知识依据，但大模型暂时不可用。', answer: '', intent: 'process_guidance',
      items: [{
        ...itemFixture, id: 'WD05-P040', category: 'process_guidance', title: '硬阳化前内孔余量',
        content: '不应重复显示的展平工艺说明',
        source: { document_id: 'WD05', document_name: '有色金属硬阳化类衬套典型工艺说明.docx', page_no: null, identity: '05-JB50-21 · §3.3 · P040' },
        guidance: {
          kind: 'allowance', applicability: '有色金属硬阳化类衬套', part_family: '衬套', typical_part: '2219.002F',
          materials: ['6061-T6'], topics: ['内孔', '硬阳化'], conditions: '半精加工后、硬阳化前',
          conclusion: '考虑膜层向内孔增长，内孔需过加工。', exceptions: '具体尺寸以图纸要求为准。',
          verification_status: 'verified', original_excerpt: '内孔单边过加工0～0.005mm。',
          metrics: [{ name: '内孔过加工量', min: 0, max: 0.005, unit: 'mm', basis: '单边', direction: '膜层向内孔增长' }],
        },
      }],
    })
    const root = mountKnowledge({ q: '6061-T6硬阳化衬套内孔如何留余量？' })
    await settle()
    const panel = elements(root).find(node => node.props.class === 'guidance-panel')
    expect(panel).toBeDefined()
    const rendered = textContent(panel!)
    for (const value of ['工艺说明', '6061-T6', '半精加工后、硬阳化前', '考虑膜层向内孔增长', '具体尺寸以图纸要求为准', '0–0.005 mm', '单边', '已核对原文']) {
      expect(rendered).toContain(value)
    }
    expect(textContent(root)).toContain('05-JB50-21 · §3.3 · P040')
    expect(textContent(root)).not.toContain('第 null 页')
    expect(textContent(root)).not.toContain('不应重复显示的展平工艺说明')
    expect(textContent(root)).toContain('已找到本地知识依据，但大模型暂时不可用。')
  })

  it('distinguishes a typical stage overview and virtual or conditional operations from historical execution', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '这是组件类的典型指导。', intent: 'typical_route',
      items: [{
        ...itemFixture, id: 'WD03-route', category: 'typical_route', title: '组件典型路线概要',
        source: { document_id: 'WD03', document_name: '典型工艺说明（活门衬套组件类）.docx', page_no: null, identity: '69-JB20-21 · §3.2' },
        guidance: {
          kind: 'stage_overview', applicability: '活门衬套组件类', part_family: '组件', typical_part: 'RT34(03)-100',
          materials: [], topics: ['组件'], conditions: '', conclusion: '按结构条件选取工序。', exceptions: '',
          verification_status: 'pending', original_excerpt: '低温灵活性试验为虚拟工序。', completeness: 'stage_overview',
          operations: [
            { id: 'step-a', sequence: 1, number: '10', name: '冲洗', execution_status: 'conditional', condition: '深长孔结构', source: { identity: 'WD03 · P029' } },
            { id: 'step-b', sequence: 2, number: '20', name: '低温灵活性试验', execution_status: 'virtual', condition: '典型零件未执行', source: { identity: 'WD03 · 附图image1' } },
            { id: 'step-c', sequence: 3, number: '', name: '检验', execution_status: 'unspecified', condition: '', source: { identity: 'WD03 · P031' } },
          ],
        },
      }],
    })
    const root = mountKnowledge({ q: '组件典型路线包含什么？' })
    await settle()
    const steps = elements(root).filter(node => node.props.class === 'guidance-operation')
    expect(steps).toHaveLength(3)
    expect(textContent(steps[0]!)).toContain('按需')
    expect(textContent(steps[0]!)).toContain('深长孔结构')
    expect(textContent(steps[1]!)).toContain('虚拟')
    expect(textContent(steps[1]!)).toContain('典型零件未执行')
    expect(textContent(steps[1]!)).toContain('WD03 · 附图image1')
    expect(textContent(steps[2]!)).toContain('未说明')
    expect(textContent(root)).toContain('阶段概要')
    expect(textContent(root)).toContain('待核对')
    expect(textContent(root)).not.toContain('份历史工艺路线')
    expect(elements(root).some(node => node.props.class === 'history-route-panel')).toBe(false)
  })

  it('shows both conflicting Word values and source anchors without presenting an approval', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'insufficient_evidence', message: '资料存在冲突，暂无足够依据确定。', answer: '', intent: 'process_guidance',
      items: ['22–32', '27–35'].map((value, index) => ({
        ...itemFixture, id: `WD01-hardness-${index}`, category: 'process_guidance', title: '钢件衬套调质硬度',
        source: { document_id: 'WD01', document_name: '典型工艺说明(钢件类衬套）.docx', page_no: null, identity: index === 0 ? '§3.4 · P058' : '附件 · image3' },
        guidance: {
          kind: 'quality', applicability: '钢件衬套', part_family: '衬套', typical_part: '2219.026F', materials: ['9Cr18'],
          topics: ['调质', '硬度'], conditions: '调质后', conclusion: `${value} HRC`, exceptions: '',
          verification_status: 'conflict', original_excerpt: `${value} HRC`,
        },
      })),
    })
    const root = mountKnowledge({ q: '钢件衬套调质硬度是多少？' })
    await settle()
    expect(textContent(root)).toContain('资料存在冲突，暂无足够依据确定。')
    const panels = elements(root).filter(node => node.props.class === 'guidance-panel')
    expect(panels).toHaveLength(2)
    expect(textContent(panels[0]!)).toContain('22–32 HRC')
    expect(textContent(panels[1]!)).toContain('27–35 HRC')
    expect(panels.every(panel => textContent(panel).includes('存在冲突'))).toBe(true)
    expect(textContent(root)).toContain('§3.4 · P058')
    expect(textContent(root)).toContain('附件 · image3')
    expect(textContent(root)).toContain('不代表文件现行有效或业务批准')
  })

  it('preserves Word formula variables and source resource identities without presenting a generic capability', async () => {
    const source = { document_id: 'WD01', document_name: '典型工艺说明(钢件类衬套）.docx', page_no: null, identity: '05-JB50-21 · 附件 · image3' }
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '原文提供如下资料。', intent: 'process_guidance',
      items: [{
        ...itemFixture, id: 'WD01-image3-resource', category: 'process_guidance', title: '珩孔原文资源', source,
        guidance: {
          kind: 'resource', applicability: '钢件衬套', part_family: '衬套', typical_part: '2219.026F',
          materials: ['9Cr18'], topics: ['珩孔'], conditions: '附件珩孔工序', conclusion: '原文记录珩磨机与专用工装。', exceptions: '',
          verification_status: 'verified', original_excerpt: '珩磨机 MC1805',
          resources: [{ category: 'equipment', name: '珩磨机', model: 'MC1805', identifier: '原文设备图号未提供', basis: '附件珩孔工序明确列出' }],
        },
      }, {
        ...itemFixture, id: 'WD01-formula', category: 'process_guidance', title: '配研计算公式', source,
        guidance: {
          kind: 'formula', applicability: '配套衬套', part_family: '衬套', typical_part: '2219.026F',
          materials: ['9Cr18'], topics: ['配研'], conditions: '已知配套间隙', conclusion: 'D = d + δ；D为孔径，d为轴径，δ为配套间隙。', exceptions: '',
          verification_status: 'verified', original_excerpt: 'D = d + δ',
        },
      }],
    })
    const root = mountKnowledge({ q: '珩孔设备和配研公式是什么？' })
    await settle()
    const rendered = textContent(root)
    for (const value of ['MC1805', '附件珩孔工序明确列出', '未自动关联主数据', 'D = d + δ', 'D为孔径', '不提供自动计算', '记录 ID：WD01-image3-resource']) {
      expect(rendered).toContain(value)
    }
    expect(elements(root).some(node => node.props.class === 'capability-panel')).toBe(false)
  })

  it('renders every operation of a historical route in supplied order with per-operation sources', async () => {
    const operations = [
      ['0', '下料'], ['5', '调质'], ['10', '车外形'], ['15', '车外形'], ['20', '铣扁'],
      ['25', '钻铰孔'], ['30', '去毛刺'], ['35', '清洗'], ['40', '去应力'], ['45', '磨孔'],
      ['50', '去毛刺'], ['55', '清洗'], ['60', '检验'], ['65', '真空淬火'], ['70', '磨孔'],
      ['75', '去毛刺'], ['80', '磨外圆'], ['85', '去毛刺'], ['90', '清洗'], ['95', '磁粉检查'],
      ['100', '烧伤检查'], ['105', '割扁、割型孔'], ['110', '去毛刺'], ['115', '研孔'],
      ['120', '清洗'], ['125', '检验'], ['130', '包装'],
    ].map(([number, name], index) => ({
      id: `route-a-operation-${number}`, number, name,
      source: { document_name: 'JRT145-13-02.json', page_no: index + 1, identity: `JRT145-13-02:工序${number}` },
    }))
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '找到一份历史工艺路线 [1]。', intent: 'history_route',
      resource_summary: null,
      items: [{
        ...itemFixture, id: 'route-a', category: 'history', title: '计量活门衬套1历史工艺路线',
        retrieval_method: 'local_keyword_route', content: '不应重复显示的展平路线内容',
        route: {
          part_id: 'J/RT145-13-02', part_name: '计量活门衬套1', material: '9Cr18',
          process_id: 'PROCESS-A', version: 'A', operation_count: 27, operations,
        },
      }],
    })
    const root = mountKnowledge({ q: '9Cr18 衬套的历史工艺路线有哪些？' })
    await settle()
    const panel = elements(root).find(node => node.props.class === 'history-route-panel')
    expect(panel).toBeDefined()
    const steps = elements(panel!).filter(node => node.props.class === 'history-route-operation')
    expect(steps).toHaveLength(27)
    expect(steps.map(step => textContent(elements(step).find(node => node.props.class === 'history-route-operation-label')!))).toEqual([
      '0下料', '5调质', '10车外形', '15车外形', '20铣扁', '25钻铰孔', '30去毛刺', '35清洗', '40去应力',
      '45磨孔', '50去毛刺', '55清洗', '60检验', '65真空淬火', '70磨孔', '75去毛刺', '80磨外圆',
      '85去毛刺', '90清洗', '95磁粉检查', '100烧伤检查', '105割扁、割型孔', '110去毛刺', '115研孔', '120清洗', '125检验', '130包装',
    ])
    expect(textContent(panel!)).toContain('共 27 道工序')
    expect(textContent(panel!)).toContain('按原始规程顺序展示')
    expect(textContent(panel!)).toContain('PROCESS-A')
    expect(textContent(panel!)).toContain('版本 A')
    expect(textContent(steps[0]!)).toContain('JRT145-13-02:工序0')
    expect(textContent(steps[26]!)).toContain('第 27 页')
    expect(textContent(steps[26]!)).toContain('JRT145-13-02:工序130')
    expect(textContent(root)).toContain('基于 1 份历史工艺路线')
    expect(textContent(root)).toContain('每份路线独立展示，工序按原始规程顺序排列。')
    expect(textContent(root)).not.toContain('不应重复显示的展平路线内容')
    expect(elements(root).some(node => node.props.class === 'result-content')).toBe(false)
  })

  it('keeps historical route cases and versions separate without merging repeated operation names', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '找到两份历史规程 [1][2]。', intent: 'history_route',
      resource_summary: null,
      items: [
        {
          ...itemFixture, id: 'route-a', category: 'history', title: '衬套规程 A',
          retrieval_method: 'local_keyword_route',
          route: {
            part_id: 'PART-1', part_name: '衬套', material: '9Cr18', process_id: 'PROC-1', version: 'A', operation_count: 3,
            operations: [
              { id: 'a-0', number: '0', name: '下料', source: { identity: 'A:工序0' } },
              { id: 'a-5', number: '5', name: '车外形', source: { identity: 'A:工序5' } },
              { id: 'a-10', number: '10', name: '车外形', source: { identity: 'A:工序10' } },
            ],
          },
        },
        {
          ...itemFixture, id: 'route-b', category: 'history', title: '衬套规程 B',
          retrieval_method: 'local_keyword_route',
          route: {
            part_id: 'PART-1', part_name: '衬套', material: '9Cr18', process_id: 'PROC-1', version: 'B', operation_count: 3,
            operations: [
              { id: 'b-0', number: '0', name: '下料', source: { identity: 'B:工序0' } },
              { id: 'b-15', number: '15', name: '检验', source: { identity: 'B:工序15' } },
              { id: 'b-100', number: '100', name: '包装', source: { identity: 'B:工序100' } },
            ],
          },
        },
      ],
    })
    const root = mountKnowledge({ q: '衬套历史工艺路线' })
    await settle()
    const panels = elements(root).filter(node => node.props.class === 'history-route-panel')
    expect(panels).toHaveLength(2)
    expect(textContent(panels[0]!)).toContain('版本 A')
    expect(textContent(panels[0]!)).not.toContain('B:工序')
    expect(textContent(panels[1]!)).toContain('版本 B')
    expect(textContent(panels[1]!)).not.toContain('A:工序')
    expect(elements(panels[0]!).filter(node => node.props.class === 'history-route-operation-label').map(textContent)).toEqual([
      '0下料', '5车外形', '10车外形',
    ])
    expect(textContent(root)).toContain('基于 2 份历史工艺路线')
  })

  it('keeps operation resource evidence inspectable when the model fails and labels empty requested resources', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'llm_unavailable', message: '已找到本地知识依据，但大模型暂时不可用。', answer: '', intent: 'history_route',
      resource_summary: null,
      items: [{
        ...itemFixture, id: 'route-resources', category: 'history', title: '衬套历史规程', retrieval_method: 'local_keyword_route',
        route: {
          part_id: 'PART-1', part_name: '衬套', material: '9Cr18', process_id: 'PROC-1', version: 'A', operation_count: 2,
          operations: [
            { id: 'op-10', number: '10', name: '车外形', source: { identity: 'PROC-1:10' }, equipment: [{ 设备类型: '数控车床', 设备型号: 'QUEST8/51' }], tool: [] },
            { id: 'op-15', number: '15', name: '检验', source: { identity: 'PROC-1:15' }, equipment: [], tool: [] },
          ],
        },
      }],
    })
    const root = mountKnowledge({ q: '衬套完整工艺路线和设备刀具有哪些？' })
    await settle()
    const resources = elements(root).filter(node => node.props.class === 'history-route-resources')
    expect(resources).toHaveLength(2)
    expect(textContent(resources[0]!)).toContain('工序资源记录')
    expect(textContent(resources[0]!)).toContain('设备')
    expect(textContent(resources[0]!)).toContain('数控车床')
    expect(textContent(resources[0]!)).toContain('QUEST8/51')
    expect(textContent(resources[0]!)).toContain('刀具样例未提供')
    expect(textContent(resources[1]!)).toContain('设备样例未提供')
    expect(textContent(resources[1]!)).not.toContain('QUEST8/51')
    expect(textContent(resources[0]!)).not.toContain('量具')
    expect(textContent(root)).toContain('已找到本地知识依据，但大模型暂时不可用。')
    expect(textContent(root)).not.toContain('知识库回答')
  })

  it('renders answer emphasis as safe text and preserves evidence numbering and source locations', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '',
      answer: '推荐 **精镗** [1]。\n<script>alert(1)</script>',
      items: [{ ...itemFixture, title: '内孔精加工', source: {
        ...itemFixture.source, worksheet: '加工能力', row_no: 12, cell_range: 'A12:H12',
      } }],
    })
    const root = mountKnowledge()
    await settle()
    expect(textContent(findByText(root, 'strong', '精镗'))).toBe('精镗')
    expect(textContent(root)).toContain('[1]')
    expect(textContent(root)).toContain('第 12 行')
    expect(textContent(root)).toContain('第 2 页')
    expect(textContent(root)).toContain('A12:H12')
    expect(textContent(root)).toContain('\n<script>alert(1)</script>')
    expect(elements(root).some(node => node.type === 'script')).toBe(false)
  })

  it('runs the selected example question and shows a useful no-evidence state', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({ status: 'no_evidence', message: '样例库没有依据', answer: '', items: [] })
    const root = mountKnowledge({ q: '' })
    ;(findByText(root, 'button', '轴套内孔和外圆有哪些加工方法？').props.onClick as Function)()
    await settle()
    expect(mocks.searchKnowledge).toHaveBeenCalledWith(expect.objectContaining({ query: '轴套内孔和外圆有哪些加工方法？' }))
    expect(textContent(root)).toContain('没有找到相关知识')
    expect(textContent(root)).toContain('样例库没有依据')
    expect(textContent(root)).not.toContain('知识库回答')
  })

  it('keeps the example list compact until the user expands it', async () => {
    const root = mountKnowledge({ q: '' })
    await settle()

    const sampleList = elements(root).find(node => node.props.class === 'sample-questions')!
    expect(elements(sampleList).filter(node => node.type === 'button')).toHaveLength(6)

    const toggle = findByText(root, 'button', '更多示例问题')
    ;(toggle.props.onClick as Function)()
    await nextTick()
    expect(elements(sampleList).filter(node => node.type === 'button')).toHaveLength(16)
    expect(textContent(toggle)).toContain('收起示例')

    ;(toggle.props.onClick as Function)()
    await nextTick()
    expect(elements(sampleList).filter(node => node.type === 'button')).toHaveLength(6)
  })

  it('offers clickable query suggestions when search returns no results', async () => {
    mocks.searchKnowledge.mockResolvedValue({ status: 'no_evidence', message: '没有匹配记录', answer: '', items: [] })
    const root = mountKnowledge({ q: '未知问题' })
    await settle()

    const recoverySuggestions = elements(root).find(node => node.props.class === 'empty-suggestions')
    expect(recoverySuggestions).toBeDefined()
    expect(textContent(recoverySuggestions!)).toContain('内孔精加工有哪些加工方法，能达到什么精度和粗糙度？')
    expect(textContent(recoverySuggestions!)).toContain('9Cr18 衬套的历史工艺路线有哪些？')
    expect(textContent(recoverySuggestions!)).toContain('CL6134A 车床的加工范围和精度参数是什么？')

    ;(findByText(recoverySuggestions!, 'button', '9Cr18 衬套的历史工艺路线有哪些？').props.onClick as Function)()
    await settle()
    expect(mocks.searchKnowledge).toHaveBeenLastCalledWith(expect.objectContaining({ query: '9Cr18 衬套的历史工艺路线有哪些？' }))
  })

  it('shows a compact adopted state after evidence is saved', async () => {
    mocks.searchKnowledge.mockResolvedValue({ status: 'ok', message: '', answer: '', items: [itemFixture] })
    mocks.saveKnowledgeEvidence.mockResolvedValueOnce({ ...itemFixture, id: 91, snapshot_hash: 'hash', retrieved_at: '2026-10-15T00:00:00Z' })
    const root = mountKnowledge()
    await settle()

    ;(findByText(root, 'button', '采纳为依据').props.onClick as Function)()
    await settle()

    expect(textContent(root)).toContain('已采纳')
    expect(textContent(root)).toContain('#91')
    expect(elements(root).some(node => node.type === 'button' && textContent(node).includes('采纳为依据'))).toBe(false)
  })

  it('shows capability metrics in groups and labels relationship evidence precisely', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '找到一条孔加工能力记录。', intent: 'capability',
      relationship_gaps: ['gauge'],
      items: [{
        ...itemFixture,
        category: 'capability',
        title: '精铰孔能力',
        content: '原始能力记录',
        source: { ...itemFixture.source, document_name: '加工能力表.xlsx', worksheet: '能力数据', row_no: 18, cell_range: 'A18:Q18' },
        capability: {
          feature: '内孔', method: '精铰', stage: '精加工',
          precision: { type: 'IT', min_grade: 'IT6', max_grade: 'IT7', code: 'IT6-IT7', bounds_valid: true },
          roughness: { min_um: 0.8, max_um: 1.6, bounds_valid: true },
          allowance: { min_mm: 0.1, max_mm: 0.2, basis: '直径余量', bounds_valid: true },
          material: '钢', material_state: 'specified',
          size: { type: '孔径', min_mm: 20, max_mm: 25 },
          conditions: '淬硬前', tool_material: '硬质合金',
          other_metrics: { 经济精度: 'IT7' },
        },
        relationships: {
          equipment: { status: 'linked', basis: 'id', items: [{ id: 'EQ-1', name: '卧式镗床', model: 'T611', record_level: 'equipment_model', fields: { 型号: 'T611' } }] },
          tool: { status: 'category_hint', basis: 'record_text', items: [{ name: '镗刀', entity_category: 'boring_tool' }] },
          gauge: { status: 'not_provided', basis: 'missing', items: [] },
        },
      }],
    })
    const root = mountKnowledge({ q: '孔精铰能力' })
    await settle()

    const rendered = textContent(root)
    for (const expected of [
      '加工特征', '内孔', '加工方法', '精铰', '阶段', '精加工',
      '精度', 'IT6-IT7', '粗糙度', '0.8–1.6 μm', '余量', '0.1–0.2 mm',
      '适用条件', '淬硬前', '材料', '钢', '尺寸范围', '20–25 mm',
      '设备', '已关联', 'ID：EQ-1', '型号：T611', 'equipment_model', 'T611', '刀具', '仅有类别线索',
      '镗刀', '量具', '样例未提供', '样例库未提供该能力与量具的明确关联',
      '加工能力表.xlsx', '能力数据', '第 18 行', 'A18:Q18',
    ]) expect(rendered).toContain(expected)
  })

  it('shows the cross-operation history resource summary separately from capability relationships', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '历史记录中的设备和量具见下方汇总。', intent: 'general',
      items: [{ ...itemFixture, category: 'history', title: '轴套车加工历史工序' }],
      resource_summary: {
        scope: 'history', record_count: 7, unique_count: 5,
        equipment_count: 2,
        equipment: [
          { name: '数控车床', model: 'CL6134A', count: 3, sources: ['history:op-10', 'history:op-12'] },
          { name: '卧式车床', model: 'CA6140', unique_count: 1, sources: ['history:op-14'] },
        ],
        tool_count: 1,
        tool: [{ name: '高速钢麻花钻', count: 2, sources: ['history:op-10'] }],
        gauge_count: 1,
        gauge: [{ name: '外径千分尺', count: 4, sources: ['history:op-10', 'history:op-12'] }],
      },
    })
    const root = mountKnowledge({ q: '某历史轴套类工序使用了哪些设备和量具？' })
    await settle()
    const rendered = textContent(root)
    for (const expected of [
      '历史资源汇总', '覆盖 7 条历史记录', '去重 5 项',
      '设备', '去重 2 项', '数控车床', 'CL6134A', '出现 3 次', 'history:op-10',
      '刀具', '高速钢麻花钻', '量具', '外径千分尺', 'history:op-12',
    ]) expect(rendered).toContain(expected)
  })

  it('renders history catalog entries and their sources without mislabeling them as gauges', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '', intent: 'history',
      items: [{ ...itemFixture, category: 'history', title: '已展示的历史工序' }],
      resource_summary: {
        scope: 'catalog', record_count: 12, unique_count: 12, history_count: 12,
        history: [
          { id: 'HIST-001', name: '9Cr18 衬套完整工艺路线', count: 1, sources: ['sample-a.json:工序10'] },
          { id: 'HIST-002', name: '套筒内孔精加工案例', count: 1, sources: ['sample-b.json:工序20'] },
        ],
      },
    })
    const root = mountKnowledge({ q: '历史案例有哪些？' })
    await settle()
    const summary = elements(root).find(node => node.props.class === 'resource-summary card')
    expect(summary).toBeDefined()
    const rendered = textContent(summary!)
    for (const expected of [
      '历史案例目录', '共找到 12 条历史案例', '去重 12 项',
      '9Cr18 衬套完整工艺路线', '套筒内孔精加工案例', 'HIST-001',
      'sample-a.json:工序10', 'sample-b.json:工序20',
    ]) expect(rendered).toContain(expected)
    expect(rendered).not.toContain('量具')
    expect(rendered).not.toContain('主数据汇总')
  })

  it('distinguishes raw equipment records from unique entries in a catalog', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'ok', message: '', answer: '', intent: 'equipment', items: [],
      resource_summary: {
        scope: 'catalog', record_count: 370, unique_count: 250, equipment_count: 250,
        equipment: [
          {
            id: 'EQ-001', name: '卧式车床', model: 'CL6134A', count: 3,
            fields: { 最大加工直径: '400 mm', 主轴转速: '16–1600 r/min' },
            sources: [
              'equipment.xlsx:设备:第18行',
              ...Array.from({ length: 9 }, (_, index) => ({
                document_name: '机械加工能力表.xlsx', worksheet: '设备参数',
                row_no: 31 + index, cell_range: `A${31 + index}:Q${31 + index}`, identity: `EQ-001:source-${index}`,
              })),
            ],
          },
        ],
      },
    })
    const root = mountKnowledge({ q: '设备有哪些？' })
    await settle()
    const summary = elements(root).find(node => node.props.class === 'resource-summary card')
    expect(summary).toBeDefined()
    const rendered = textContent(summary!)
    for (const expected of [
      '主数据汇总', '原始记录 370 条', '去重 250 项', '设备记录',
      '卧式车床', 'CL6134A', '出现 3 次', 'equipment.xlsx:设备:第18行',
      '名称、型号与参数去重项', '参数与规格', '最大加工直径', '400 mm', '主轴转速',
      '来源依据', '机械加工能力表.xlsx', '设备参数', '第 31 行', 'A31:Q31',
      '第 39 行', 'A39:Q39', 'EQ-001:source-8',
    ]) expect(rendered).toContain(expected)
    expect(rendered).not.toContain('370 台设备')
    expect(elements(summary!).filter(node => node.type === 'details')).toHaveLength(2)
  })

  it('offers natural-language questions for the planned machining capability queries after expansion', async () => {
    const root = mountKnowledge({ q: '' })
    ;(findByText(root, 'button', '更多示例问题').props.onClick as Function)()
    await nextTick()
    const rendered = textContent(root)
    for (const expected of [
      '轴套内孔精加工有哪些加工方法，能达到什么精度和粗糙度？',
      '内孔目标 IT7、Ra1.6，样例库有哪些工艺方法？',
      '钻孔、扩孔、铰孔分别适合什么加工阶段和精度范围？',
      '加工外圆时，哪些车床类别有对应的能力记录？',
      '孔加工可以使用哪些刀具，各自的经济精度是多少？',
      '内径 20～25 mm 的孔，可以查到哪些量具？',
      '某历史轴套类工序使用了哪些设备和量具？',
    ]) expect(rendered).toContain(expected)
  })

  it('shows source-data warnings on evidence and catalog entries without displaying invalid bounds as capabilities', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'insufficient_evidence', message: '范围异常，需核对原始数据。', answer: '', intent: 'capability',
      items: [{
        ...itemFixture, category: 'capability', title: '待核验能力记录',
        data_warnings: ['粗糙度上下限反向，需核对原始数据'],
        capability: {
          feature: '内孔', method: '精铰',
          precision: { type: 'IT', min_grade: null, max_grade: null, code: 'IT9–IT6', bounds_valid: false },
          roughness: { min_um: null, max_um: null, bounds_valid: false },
          allowance: { min_mm: null, max_mm: null, bounds_valid: false },
          size: { type: '孔径', min_mm: null, max_mm: null, bounds_valid: false },
        },
      }],
      resource_summary: {
        scope: 'catalog', record_count: 1, gauge_count: 1,
        gauge: [{
          id: 'GA-001', name: '内径量具',
          fields: { 量程下限: 50, 量程上限: 20 },
          data_warnings: ['量程上下限反向，不能据此判断适用尺寸'],
        }],
      },
    })
    const root = mountKnowledge({ q: '内孔能力和量具' })
    await settle()
    const warnings = elements(root).filter(node => node.props.class === 'knowledge-alert data-warning')
    expect(warnings).toHaveLength(2)
    expect(warnings.every(node => node.props.role === 'status')).toBe(true)
    expect(textContent(root)).toContain('粗糙度上下限反向，需核对原始数据')
    expect(textContent(root)).toContain('量程上下限反向，不能据此判断适用尺寸')
    const panel = elements(root).find(node => node.props.class === 'capability-panel')
    expect(panel).toBeDefined()
    expect(textContent(panel!)).not.toContain('IT9–IT6')
    expect(textContent(panel!)).not.toContain('null')
    expect(textContent(panel!)).not.toContain('0 μm')
    expect(textContent(panel!)).not.toContain('0 mm')
  })

  it('clears evidence markers when a new search starts', () => {
    expect(source).toContain('savedEvidenceIds.value = {}')
    expect(source).toContain('const requestId = ++searchRequestId.value')
  })

  it('does not render the rule suggestion draft module', async () => {
    const root = mountKnowledge()
    await settle()

    expect(textContent(root)).not.toContain('规则建议草稿')
  })
})

describe('knowledge context race behavior', () => {
  it('does not restart the same pending query on repeated Enter presses', async () => {
    const pending = deferred<any>()
    mocks.searchKnowledge.mockReturnValueOnce(pending.promise)
    const root = mountKnowledge({ q: '重复查询' })
    const submit = findInput(root, 'knowledge-query-input').props.onKeyup
    submit({ key: 'Enter' })
    submit({ key: 'Enter' })
    expect(mocks.searchKnowledge).toHaveBeenCalledTimes(1)
    pending.resolve({ status: 'ok', message: '', answer: '当前回答', items: [itemFixture] })
    await settle()
    expect(textContent(root)).toContain('当前回答')
  })

  it('saves evidence with the submitted question after the query draft changes', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({ status: 'ok', message: '', answer: '', items: [itemFixture] })
    mocks.saveKnowledgeEvidence.mockResolvedValueOnce({ id: 91 })
    const root = mountKnowledge({ project_id: '1', q: '原始检索问题' })
    await settle()
    findInput(root, 'knowledge-query-input').props['onUpdate:modelValue']('尚未检索的新问题')
    await nextTick()
    findByText(root, 'button', '采纳为依据').props.onClick()
    await settle()
    expect(mocks.saveKnowledgeEvidence).toHaveBeenCalledWith(expect.objectContaining({ query: '原始检索问题' }))
  })

  it('prevents repeated evidence adoption before the save response', async () => {
    const pending = deferred<any>()
    mocks.searchKnowledge.mockResolvedValueOnce({ status: 'ok', message: '', answer: '', items: [itemFixture] })
    mocks.saveKnowledgeEvidence.mockReturnValueOnce(pending.promise)
    const root = mountKnowledge()
    await settle()
    const adopt = findByText(root, 'button', '采纳为依据').props.onClick
    const first = adopt()
    const second = adopt()
    expect(mocks.saveKnowledgeEvidence).toHaveBeenCalledTimes(1)
    pending.resolve({ id: 91 })
    await Promise.all([first, second])
  })

  it('does not mark an item adopted when its save resolves after a new search', async () => {
    const firstSearch = deferred<any>()
    const secondSearch = deferred<any>()
    const save = deferred<any>()
    mocks.searchKnowledge.mockReturnValueOnce(firstSearch.promise).mockReturnValueOnce(secondSearch.promise)
    mocks.saveKnowledgeEvidence.mockReturnValueOnce(save.promise)
    const root = mountKnowledge()

    firstSearch.resolve({ status: 'ok', message: '', items: [itemFixture] })
    await settle()
    ;(findByText(root, 'button', '采纳为依据').props.onClick as Function)()
    await settle()

    const queryInput = findInput(root, 'knowledge-query-input')
    queryInput.props['onUpdate:modelValue']('new query')
    await nextTick()
    const searchButton = findByText(root, 'button', '查询')
    ;(searchButton.props.onClick as Function)()
    await settle()
    expect(textContent(searchButton)).toContain('回答生成中')

    save.resolve({ ...itemFixture, id: 91, snapshot_hash: 'hash', retrieved_at: '2026-10-15T00:00:00Z' })
    secondSearch.resolve({ status: 'ok', message: '', items: [itemFixture] })
    await settle()
    expect(textContent(root)).not.toContain('已保存为依据 #91')
    expect(textContent(findByText(root, 'button', '采纳为依据'))).toContain('采纳为依据')
  })

  it('does not surface an old save error or busy state after the route changes', async () => {
    const firstSearch = deferred<any>()
    const save = deferred<any>()
    mocks.searchKnowledge.mockReturnValueOnce(firstSearch.promise)
    mocks.saveKnowledgeEvidence.mockReturnValueOnce(save.promise)
    const root = mountKnowledge()
    firstSearch.resolve({ status: 'ok', message: '', items: [itemFixture] })
    await settle()
    ;(findByText(root, 'button', '采纳为依据').props.onClick as Function)()
    await settle()

    routeState.current.query = { project_id: '2', q: '' }
    routeState.current.fullPath = '/knowledge?project_id=2'
    await settle()
    save.reject(new Error('old save failed'))
    await settle()
    expect(textContent(root)).not.toContain('保存知识依据失败')
    expect(textContent(root)).not.toContain('保存中')
  })

  it('shows an empty result for a searched project and keeps the result area out of an unrelated project', async () => {
    const search = deferred<any>()
    mocks.searchKnowledge.mockReturnValueOnce(search.promise)
    const root = mountKnowledge()
    search.resolve({ status: 'ok', message: '', items: [] })
    await settle()
    expect(textContent(root)).toContain('没有找到相关知识')

    const rootWithoutProject = mountKnowledge({ project_id: '', q: '' })
    expect(textContent(rootWithoutProject)).not.toContain('没有找到相关知识')
  })

  it('keeps local evidence visible when the LLM is unavailable', async () => {
    mocks.searchKnowledge.mockResolvedValueOnce({
      status: 'llm_unavailable',
      message: '已找到本地知识依据，但大模型暂时不可用。',
      answer: '',
      items: [itemFixture],
    })
    const root = mountKnowledge()
    await settle()

    expect(textContent(root)).toContain('已找到本地知识依据，但大模型暂时不可用。')
    expect(textContent(root)).toContain('工序依据内容')
    expect(textContent(root)).toContain('工艺规程')
  })
})

function catalogFixture(title = '配套孔加工余量', total = 45) {
  return { section: 'knowledge', total, raw_count: total, page: 1, page_size: 20,
    categories: [{ value: 'process_guidance', label: '工艺说明', count: total }],
    topics: [{ value: 'allowance', label: '加工余量', count: total }],
    columns: [{ key: 'title', label: '知识条目' }, { key: 'status', label: '核对状态' }],
    items: [{ id: 'WD/01', title, category: 'process_guidance', source_label: '规程资料',
      source_kind: 'process_document', verification_status: 'conflict', data_warnings: ['原文数值冲突'],
      values: { title, status: '存在冲突' } }],
  }
}
function detailFixture() {
  return { ...catalogFixture().items[0], fields: { '余量下限': 0, '前提条件': '半精加工后' },
    sources: [{ document_name: '钢件衬套.docx', identity: '第3.3节' }], original_records: [], guidance: null }
}

describe('read-only knowledge catalog', () => {
  it('shows only topics that belong to the selected catalog category', async () => {
    mocks.listKnowledgeCatalog.mockReset()
      .mockResolvedValueOnce({
        ...catalogFixture(),
        categories: [
          { value: 'process_guidance', label: '工艺说明', count: 1 },
          { value: 'typical_route', label: '典型路线', count: 1 },
        ],
        topics: [
          { value: 'allowance', label: '加工余量', count: 1 },
          { value: 'stage_overview', label: '阶段概要', count: 1 },
        ],
      })
      .mockResolvedValueOnce({
        ...catalogFixture(),
        categories: [
          { value: 'process_guidance', label: '工艺说明', count: 1 },
          { value: 'typical_route', label: '典型路线', count: 1 },
        ],
        topics: [
          { value: 'allowance', label: '加工余量', count: 0 },
          { value: 'stage_overview', label: '阶段概要', count: 1 },
        ],
      })
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    findByText(root, 'button', '典型路线').props.onClick()
    await settle()
    const topicSelect = elements(root).find(node => node.type === 'select' && node.props['aria-label'] === '工艺主题')!
    expect(textContent(topicSelect)).toContain('阶段概要')
    expect(textContent(topicSelect)).not.toContain('加工余量')
  })

  it('separates ordinary verification notes from actionable warnings', async () => {
    const note = '已核对原文仅表示提取一致，不代表业务批准。'
    mocks.getKnowledgeCatalogRecord.mockResolvedValueOnce({ ...detailFixture(), data_warnings: [note, '原文数值冲突'] })
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    const warning = elements(root).find(n => n.props.class === 'catalog-detail-warnings')!
    expect(textContent(warning)).toContain('原文数值冲突')
    expect(textContent(warning)).not.toContain(note)
    expect(textContent(root)).toContain(note)
  })

  it('shows readable resource parameters and retains collapsed original fields and zero values', async () => {
    mocks.getKnowledgeCatalogRecord.mockResolvedValueOnce({ ...detailFixture(), values: { title: '测试设备', model: 'CA6140', range: '0–100 mm', status: '参考资料' }, fields: { spindle_min: 0, original_model: 'CA6140' } })
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺资源').props.onClick()
    await settle()
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    const summary = elements(root).find(n => n.props.class === 'catalog-key-fields')
    expect(summary).toBeDefined()
    expect(textContent(summary!)).toContain('型号 / 规格CA6140')
    expect(textContent(summary!)).toContain('范围 / 能力0–100 mm')
    const raw = elements(root).find(n => n.type === 'details' && n.props.class === 'catalog-raw-fields')!
    expect(raw.props.open).toBe(false)
    expect(textContent(raw)).toContain('spindle_min0')
    expect(textContent(root)).toContain('钢件衬套.docx')
  })

  it('opens three sidebar entries and preserves the question while browsing', async () => {
    const root = mountKnowledge({ q: '' })
    expect(textContent(root)).toContain('工艺知识')
    expect(textContent(root)).toContain('工艺资源')
    const input = findInput(root, 'knowledge-query-input')
    input.props['onUpdate:modelValue']('尚未提交的问题')
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    expect(textContent(root)).toContain('配套孔加工余量')
    expect(textContent(root)).toContain('存在冲突')
    expect(textContent(root)).toContain('原文数值冲突')
    expect(mocks.searchKnowledge).not.toHaveBeenCalled()
    findByText(root, 'button', '知识问答').props.onClick()
    await settle()
    expect(findInput(root, 'knowledge-query-input').value).toBe('尚未提交的问题')
  })

  it('paginates, searches and opens literal values with sources', async () => {
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    expect(textContent(root)).toContain('45')
    findByText(root, 'button', '下一页').props.onClick()
    await settle()
    expect(mocks.listKnowledgeCatalog).toHaveBeenLastCalledWith(expect.objectContaining({ section: 'knowledge', page: 2, page_size: 20 }))
    const search = elements(root).find(n => n.type === 'input' && n.props.placeholder === '搜索当前目录')!
    search.props['onUpdate:modelValue']('内孔')
    findByText(root, 'button', '搜索').props.onClick({ preventDefault() {} })
    await settle()
    expect(mocks.listKnowledgeCatalog).toHaveBeenLastCalledWith(expect.objectContaining({ q: '内孔', page: 1 }))
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    expect(textContent(root)).toContain('钢件衬套.docx')
    expect(textContent(root)).toContain('第3.3节')
    expect(textContent(root)).toContain('余量下限0')
    expect(elements(root).some(n => n.props.contenteditable)).toBe(false)
  })

  it('ignores a stale list response after a new search', async () => {
    const old = deferred<any>()
    mocks.listKnowledgeCatalog.mockReturnValueOnce(old.promise)
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    const search = elements(root).find(n => n.type === 'input' && n.props.placeholder === '搜索当前目录')!
    search.props['onUpdate:modelValue']('新条件')
    mocks.listKnowledgeCatalog.mockResolvedValueOnce(catalogFixture('新结果'))
    findByText(root, 'button', '搜索').props.onClick({ preventDefault() {} })
    await settle()
    old.resolve(catalogFixture('过期结果'))
    await settle()
    expect(textContent(root)).toContain('新结果')
    expect(textContent(root)).not.toContain('过期结果')
  })

  it('offers retry after list failure and clears stale detail on errors', async () => {
    mocks.listKnowledgeCatalog.mockRejectedValueOnce(new Error('offline'))
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    expect(textContent(root)).toContain('目录加载失败')
    findByText(root, 'button', '重试').props.onClick()
    await settle()
    mocks.getKnowledgeCatalogRecord.mockRejectedValueOnce(new Error('detail offline'))
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    expect(textContent(root)).toContain('详情加载失败')
    expect(textContent(root)).not.toContain('钢件衬套.docx')
  })
})


describe('catalog detail race and category state', () => {
  it('does not reopen a detail after it was closed while loading', async () => {
    const pending = deferred<any>()
    mocks.getKnowledgeCatalogRecord.mockReturnValueOnce(pending.promise)
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    findByText(root, 'button', '关闭').props.onClick()
    pending.resolve(detailFixture())
    await settle()
    expect(textContent(root)).not.toContain('钢件衬套.docx')
    expect(elements(root).some(n => n.props['aria-label'] === '工艺知识记录详情')).toBe(false)
  })

  it('keeps the selected category and ignores stale detail after filtering', async () => {
    const pending = deferred<any>()
    mocks.getKnowledgeCatalogRecord.mockReturnValueOnce(pending.promise)
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    findByText(root, 'button', '配套孔加工余量').props.onClick()
    await settle()
    findByText(root, 'button', '工艺说明').props.onClick()
    await settle()
    pending.resolve(detailFixture())
    await settle()
    expect(textContent(root)).not.toContain('钢件衬套.docx')
    expect(mocks.listKnowledgeCatalog).toHaveBeenLastCalledWith(expect.objectContaining({ category: 'process_guidance', page: 1 }))
    findByText(root, 'button', '知识问答').props.onClick()
    findByText(root, 'button', '工艺知识').props.onClick()
    await settle()
    expect(findByText(root, 'button', '工艺说明').props['aria-pressed']).toBe(true)
  })
})

describe('contextual knowledge navigation', () => {
  it('reveals QA for an incoming question while retaining catalog filters', async () => {
    const root = mountKnowledge({ q: '' })
    findByText(root, 'button', '工艺资源').props.onClick()
    await settle()
    const qa = elements(root).find(n => n.props.class === 'knowledge-qa')!
    expect((qa as any).style.display).toBe('none')
    routeState.current.query = { project_id: '1', q: '内孔加工', operation_context: JSON.stringify({ segment_id: 'op-2' }) }
    routeState.current.fullPath = '/knowledge?project_id=1&q=内孔加工'
    await settle()
    expect((qa as any).style.display).not.toBe('none')
    expect(findByText(root, 'button', '知识问答').props['aria-pressed']).toBe(true)
    expect(mocks.searchKnowledge).toHaveBeenLastCalledWith(expect.objectContaining({ query: '内孔加工' }))
  })
})
