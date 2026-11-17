import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import viewSource from './FinalizeView.vue?raw'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { workflowResetSignal } from '@/composables/workflowResetState'

const boundary = vi.hoisted(() => ({
  listProjects: vi.fn(), getSavedNormalizedRoute: vi.fn(), listOperations: vi.fn(),
  getSupersetRoute: vi.fn(), enterRuleFinalization: vi.fn(), getConditionFieldRegistry: vi.fn(),
  startRulePreprocessing: vi.fn(), getRulePreprocessingStatus: vi.fn(),
  getLatestExecutableRuleRevision: vi.fn(), leave: vi.fn(), update: vi.fn(), replace: vi.fn(),
}))
let route: { path: string; query: { project_id?: string } }
vi.mock('vue-router', async importOriginal => ({
  ...await importOriginal<typeof import('vue-router')>(),
  useRoute: () => route,
  useRouter: () => ({ replace: boundary.replace, push: vi.fn() }),
  onBeforeRouteLeave: (guard: unknown) => boundary.leave(guard),
  onBeforeRouteUpdate: (guard: unknown) => boundary.update(guard),
}))
vi.mock('@/api', async importOriginal => ({
  ...await importOriginal<typeof import('@/api')>(),
  listProjects: boundary.listProjects, getSavedNormalizedRoute: boundary.getSavedNormalizedRoute,
  listOperations: boundary.listOperations, getSupersetRoute: boundary.getSupersetRoute,
  enterRuleFinalization: boundary.enterRuleFinalization,
}))
vi.mock('@/api/rulePackages', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/rulePackages')>(),
  getConditionFieldRegistry: boundary.getConditionFieldRegistry,
  startRulePreprocessing: boundary.startRulePreprocessing,
  getRulePreprocessingStatus: boundary.getRulePreprocessingStatus,
}))
vi.mock('@/api/executableRules', async importOriginal => ({
  ...await importOriginal<typeof import('@/api/executableRules')>(),
  getLatestExecutableRuleRevision: boundary.getLatestExecutableRuleRevision,
}))
// Route navigation/layout have a separate owner. Keep the view, cards, editors,
// dirty tracking, request ownership and actual Vue KeepAlive lifecycle real.
vi.mock('@/components/finalize/FinalizeRouteNav.vue', () => ({ default: { render: () => null } }))
vi.mock('@/components/workflow/WorkflowResetDialog.vue', () => ({ default: { render: () => null } }))

async function compileComponent(source: string): Promise<any> {
  const script = compileScript(parse(source).descriptor, { id: 'finalize-lifecycle', inlineTemplate: true })
  const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
  const dependencies: Record<string, unknown> = { vue: Vue }
  for (const match of code.matchAll(/require\("([^"]+)"\)/g)) {
    const id = match[1]!
    if (id in dependencies) continue
    if (id.endsWith('FinalizeRouteNav.vue') || id.endsWith('WorkflowResetDialog.vue')) {
      dependencies[id] = { __esModule: true, default: { render: () => null } }
    } else if (id.endsWith('.vue')) {
      dependencies[id] = { __esModule: true, default: await compileComponent((await import(`${id}?raw`)).default) }
    } else dependencies[id] = await import(id)
  }
  const module = { exports: {} as any }
  new Function('require', 'module', 'exports', code)((id: string) => dependencies[id], module, module.exports)
  return module.exports.default
}
const FinalizeView = await compileComponent(viewSource)

type HostNode = { type: string; props: Record<string, any>; text?: string; children: HostNode[]; parent?: HostNode }
function insert(child: HostNode, parent: HostNode, anchor?: HostNode | null) {
  if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1)
  child.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  if (index < 0) parent.children.push(child)
  else parent.children.splice(index, 0, child)
}
const renderer = Vue.createRenderer({
  createElement: (type: string) => ({ type, props: {}, children: [] }),
  createText: (text: string) => ({ type: '#text', text, props: {}, children: [] }),
  createComment: (text: string) => ({ type: '#comment', text, props: {}, children: [] }),
  setText: (node: HostNode, text: string) => { node.text = text },
  setElementText: (node: HostNode, text: string) => { node.text = text; node.children = [] },
  patchProp: (node: HostNode, key: string, _previous: unknown, next: unknown) => { node.props[key] = next },
  insert,
  remove: (node: HostNode) => { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1) },
  parentNode: (node: HostNode) => node.parent || null,
  nextSibling: (node: HostNode) => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
  insertStaticContent: (text: string, parent: HostNode, anchor?: HostNode | null) => {
    const node = { type: '#static', text, props: {}, children: [] }
    insert(node, parent, anchor)
    return [node, node]
  },
} as any)
function find(node: HostNode, predicate: (node: HostNode) => boolean): HostNode | undefined {
  return predicate(node) ? node : node.children.map(child => find(child, predicate)).find(Boolean)
}
function textContent(node: HostNode): string {
  return node.type === '#comment' ? '' : `${node.text || ''}${node.children.map(textContent).join('')}`
}
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
async function settle() {
  for (let i = 0; i < 15; i++) { await Promise.resolve(); await Vue.nextTick() }
}
function savedRoute(project = 12, conditional = false) {
  return {
    project_id: project, route_id: project * 10, version: 1, workflow_revision: 3,
    analysis_locked: true, segments: [{
      id: `prepare-${project}`, sequence: 1, normalized_step_name: '研外圆',
      source_operation_ids: [], source_nodes: [], matched_detail_rows: [], factor_reviews: [],
      doc_coverage: { hit_docs: conditional ? 1 : 3, total_docs: 3 },
      rule_review: { id: 1, decision: 'accepted', note: '', question_trail: [], summary_lines: [], created_at: '', updated_at: '',
        ...(conditional ? { condition_review: { source_text: '当材料为6061时，纳入研外圆工序。', status: 'draft', candidate: null, confirmed: null, source_hash: '', confidence: 0, issues: [] } } : {}),
      },
    }],
  }
}
const cleanups: Array<() => void> = []
let pageEvents: Map<string, (event: any) => void>
function mount(keepAlive = true) {
  const host: HostNode = { type: 'root', props: {}, children: [] }
  const active = Vue.ref(true)
  const app = renderer.createApp({ render: () => keepAlive
    ? Vue.h(Vue.KeepAlive, null, { default: () => active.value ? Vue.h(FinalizeView) : Vue.h('aside', 'away') })
    : Vue.h(FinalizeView) })
  app.mount(host as any)
  cleanups.push(() => app.unmount())
  return { host, active }
}
const card = (host: HostNode) => find(host, node => node.type === 'article')
const button = (host: HostNode, label: string) => find(host, node => node.type === 'button' && textContent(node).trim() === label)!

beforeEach(() => {
  vi.clearAllMocks()
  workflowResetSignal.value = null
  route = Vue.reactive({ path: '/finalize', query: { project_id: '12' } })
  const storage = new Map<string, string>()
  const localStorage = { getItem: (key: string) => storage.get(key) || null, setItem: (key: string, value: string) => storage.set(key, value), removeItem: (key: string) => storage.delete(key) }
  vi.stubGlobal('localStorage', localStorage)
  vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {}, getElementById: () => null })
  pageEvents = new Map()
  vi.stubGlobal('window', {
    addEventListener: (event: string, handler: (event: any) => void) => pageEvents.set(event, handler),
    removeEventListener: (event: string) => pageEvents.delete(event), setTimeout, clearTimeout,
    localStorage,
  })
  boundary.listProjects.mockResolvedValue([{ id: 12, name: '隔离任务12' }, { id: 28, name: '隔离任务28' }])
  boundary.getSavedNormalizedRoute.mockImplementation(async (project: number) => savedRoute(project))
  boundary.listOperations.mockResolvedValue([])
  boundary.getSupersetRoute.mockResolvedValue({ superset_route: [] })
  boundary.getConditionFieldRegistry.mockResolvedValue({ fields: [] })
  boundary.getLatestExecutableRuleRevision.mockResolvedValue(null)
  boundary.enterRuleFinalization.mockResolvedValue({ analysis_locked: true, analysis_locked_at: '' })
  boundary.startRulePreprocessing.mockResolvedValue({ task_status: 'completed' })
  boundary.replace.mockImplementation(async location => { route.query = location.query })
})
afterEach(async () => {
  cleanups.splice(0).forEach(cleanup => cleanup())
  await Vue.nextTick()
  vi.unstubAllGlobals()
})

describe('PM-068 finalize loading lifecycle', () => {
  it('shows loading, rather than a missing-project message, before project discovery returns', async () => {
    const projects = deferred<any[]>()
    boundary.listProjects.mockReturnValue(projects.promise)
    const view = mount()
    expect(textContent(view.host)).toContain(FINALIZE_VIEW_COPY.loadingTitle)
    expect(textContent(view.host)).not.toContain(FINALIZE_VIEW_COPY.emptyProjectTitle)
    projects.resolve([{ id: 12 }])
    await settle()
  })

  it('starts one initial project discovery when mounted inside the application KeepAlive', async () => {
    const projects = deferred<any[]>()
    boundary.listProjects.mockReturnValue(projects.promise)
    const view = mount()
    expect(boundary.listProjects).toHaveBeenCalledTimes(1)
    projects.resolve([{ id: 12 }])
    await settle()
    expect(textContent(view.host)).toContain('规则定稿')
  })

  it('preserves the card instance while refreshing after KeepAlive reactivation', async () => {
    const view = mount()
    await settle()
    // Full-coverage rules are initially filtered out; show the complete route.
    const filter = find(view.host, node => node.type === 'button' && textContent(node).trim() === '查看全部规则')
    filter?.props.onClick()
    await settle()
    const original = card(view.host)
    expect(original).toBeDefined()
    button(view.host, '规则修改').props.onClick()
    await Vue.nextTick()
    view.active.value = false
    await Vue.nextTick()
    const projects = deferred<any[]>()
    boundary.listProjects.mockReturnValueOnce(projects.promise)
    view.active.value = true
    await Vue.nextTick()
    expect(card(view.host) === original).toBe(true)
    expect(textContent(view.host)).not.toContain(FINALIZE_VIEW_COPY.loadingTitle)
    expect(button(view.host, '保存并确认').props.disabled).toBe(true)
    expect(button(view.host, '确认全部规则').props.disabled).toBe(true)
    expect(button(view.host, '保存并进入路线验证 →').props.disabled).toBe(true)
    projects.resolve([{ id: 12 }])
    await settle()
    expect(card(view.host) === original).toBe(true)
    expect(button(view.host, '规则修改').props.disabled).toBe(false)
  })

  it('preserves the visible card when immediate preprocessing completion reloads its server result', async () => {
    boundary.getSavedNormalizedRoute.mockResolvedValue(savedRoute(12, true))
    const recognition = deferred<any>()
    boundary.startRulePreprocessing.mockReturnValue(recognition.promise)
    const view = mount()
    await settle()
    const original = card(view.host)
    expect(original).toBeDefined()
    expect(boundary.startRulePreprocessing).toHaveBeenCalledTimes(1)
    const refresh = deferred<any>()
    boundary.getSavedNormalizedRoute.mockReturnValueOnce(refresh.promise)
    recognition.resolve({ task_status: 'completed' })
    await settle()
    expect(boundary.getSavedNormalizedRoute).toHaveBeenCalledTimes(2)
    expect(card(view.host) === original).toBe(true)
    expect(textContent(view.host)).not.toContain(FINALIZE_VIEW_COPY.loadingTitle)
    refresh.resolve(savedRoute(12, true))
    await settle()
    expect(card(view.host) === original).toBe(true)
  })

  it('starts required preprocessing on a normal mount outside KeepAlive', async () => {
    boundary.getSavedNormalizedRoute.mockResolvedValue(savedRoute(12, true))
    mount(false)
    await settle()
    expect(boundary.startRulePreprocessing).toHaveBeenCalledTimes(1)
  })

  it('ignores a late load after deactivation and loads the current project on return', async () => {
    const old = deferred<any>()
    boundary.getSavedNormalizedRoute.mockReturnValue(old.promise)
    const view = mount()
    await settle()
    view.active.value = false
    await Vue.nextTick()
    old.resolve(savedRoute(12, true))
    await settle()
    expect(boundary.enterRuleFinalization).not.toHaveBeenCalled()
    expect(boundary.startRulePreprocessing).not.toHaveBeenCalled()
    route.query.project_id = '28'
    boundary.getSavedNormalizedRoute.mockResolvedValue(savedRoute(28, true))
    view.active.value = true
    await settle()
    expect(card(view.host)?.props.id).toBe('finalize-card-prepare-28')
    expect(boundary.enterRuleFinalization.mock.calls.every(([payload]) => payload.project_id === 28)).toBe(true)
  })

  it('does not expose the old route while a different project is loading', async () => {
    const view = mount()
    await settle()
    button(view.host, '查看全部规则').props.onClick()
    await Vue.nextTick()
    expect(card(view.host)?.props.id).toBe('finalize-card-prepare-12')
    const next = deferred<any>()
    boundary.getSavedNormalizedRoute.mockReturnValue(next.promise)
    route.query.project_id = '28'
    await settle()
    expect(card(view.host)).toBeUndefined()
    expect(textContent(view.host)).toContain(FINALIZE_VIEW_COPY.loadingTitle)
    next.resolve(savedRoute(28, true))
    await settle()
    expect(card(view.host)?.props.id).toBe('finalize-card-prepare-28')
  })

  it('retains real dirty edits, blocked navigation and unload protection across KeepAlive', async () => {
    const view = mount()
    await settle()
    button(view.host, '查看全部规则').props.onClick()
    await Vue.nextTick()
    button(view.host, '规则修改').props.onClick()
    await Vue.nextTick()
    button(view.host, 'Bool 工序').props.onClick()
    await Vue.nextTick()
    expect(textContent(view.host)).toContain('未保存 1 项')
    const leave = boundary.leave.mock.calls[0]![0]
    const update = boundary.update.mock.calls[0]![0]
    expect(await leave()).toBe(false)
    expect(await update({ query: { project_id: '28' } }, { query: { project_id: '12' } })).toBe(false)
    const event = { preventDefault: vi.fn(), returnValue: undefined }
    pageEvents.get('beforeunload')!(event)
    expect(event.preventDefault).toHaveBeenCalledOnce()
    const loadsBefore = boundary.listProjects.mock.calls.length
    const original = card(view.host)
    view.active.value = false
    await Vue.nextTick()
    view.active.value = true
    await settle()
    expect(card(view.host) === original).toBe(true)
    expect(boundary.listProjects).toHaveBeenCalledTimes(loadsBefore)
    expect(textContent(view.host)).toContain('未保存 1 项')
    button(view.host, '取消').props.onClick()
    await Vue.nextTick()
    expect(textContent(view.host)).not.toContain('未保存 1 项')
    expect(await leave()).toBe(true)
    expect(await update({ query: { project_id: '28' } }, { query: { project_id: '12' } })).toBe(true)
  })

  it('shows an empty project state only after discovery establishes there are no projects', async () => {
    const projects = deferred<any[]>()
    boundary.listProjects.mockReturnValue(projects.promise)
    const view = mount()
    expect(textContent(view.host)).toContain(FINALIZE_VIEW_COPY.loadingTitle)
    projects.resolve([])
    await settle()
    expect(textContent(view.host)).toContain(FINALIZE_VIEW_COPY.emptyProjectTitle)
    expect(textContent(view.host)).not.toContain(FINALIZE_VIEW_COPY.loadingTitle)
  })

  it('keeps the initial request when project discovery fills the missing route query', async () => {
    delete route.query.project_id
    mount()
    await settle()
    expect(route.query.project_id).toBe('12')
    expect(boundary.listProjects).toHaveBeenCalledTimes(1)
    expect(boundary.getSavedNormalizedRoute).toHaveBeenCalledTimes(1)
    expect(boundary.enterRuleFinalization).toHaveBeenCalledTimes(1)
  })
})
