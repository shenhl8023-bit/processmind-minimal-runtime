/** Opt-in acceptance against prepare_isolated.py's DB clone, never formal data. */
import fs from 'node:fs'
import path from 'node:path'
import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { clearWorkflowProjectDataCache } from '@/composables/workflowDataCache'

const boundary = vi.hoisted(() => ({ route: { path: '/analysis', query: { project_id: '8' } }, push: vi.fn() }))
vi.mock('vue-router', async original => ({ ...await original<typeof import('vue-router')>(),
  useRoute: () => boundary.route, useRouter: () => ({ push: boundary.push, replace: vi.fn() }),
  onBeforeRouteLeave: vi.fn(), onBeforeRouteUpdate: vi.fn(),
}))
vi.mock('element-plus', () => ({ ElMessage: { error: vi.fn(), warning: vi.fn(), success: vi.fn() } }))

type Node = { type: string; props: Record<string, any>; text?: string; children: Node[]; parent?: Node; [key: string]: any }
const node = (type: string, text = ''): Node => ({ type, tagName: type.toUpperCase(), text, props: {}, children: [],
  addEventListener() {}, removeEventListener() {}, setAttribute() {}, removeAttribute() {}, style: {},
  classList: { add() {}, remove() {} }, getAttribute() { return '' } })
function insert(child: Node, parent: Node, anchor?: Node) {
  if (child.parent) child.parent.children.splice(child.parent.children.indexOf(child), 1)
  child.parent = parent
  const index = anchor ? parent.children.indexOf(anchor) : -1
  if (index < 0) parent.children.push(child)
  else parent.children.splice(index, 0, child)
}
const renderer = Vue.createRenderer({ createElement: (type: string) => node(type), createText: (text: string) => node('#text', text),
  createComment: (text: string) => node('#comment', text), insert,
  setText: (n: Node, text: string) => { n.text = text }, setElementText: (n: Node, text: string) => { n.text = text; n.children = [] },
  patchProp: (n: Node, key: string, _prev: unknown, next: unknown) => { n.props[key] = next },
  remove: (n: Node) => { if (n?.parent) n.parent.children.splice(n.parent.children.indexOf(n), 1) },
  parentNode: (n: Node) => n.parent || null, nextSibling: (n: Node) => n.parent?.children[n.parent.children.indexOf(n) + 1] || null,
  insertStaticContent: (text: string, parent: Node, anchor: Node) => { const n = node('#static', text); insert(n, parent, anchor); return [n, n] },
  querySelector: () => node('teleport-target'),
} as any)
const content = (n: Node): string => n.type === '#comment' ? '' : `${n.text || ''}${n.children.map(content).join('')}`
function find(n: Node, predicate: (n: Node) => boolean): Node | undefined { return predicate(n) ? n : n.children.map(c => find(c, predicate)).find(Boolean) }
const cache = new Map<string, any>()
async function compile(source: string, key: string): Promise<any> {
  if (cache.has(key)) return cache.get(key)
  // Expose only in this compiled test copy for actual-input inspection. Actions
  // below still use the page's rendered one-click buttons and real HTTP APIs.
  const exposure = key.endsWith('GenerateView.vue') ? '\ndefineExpose({inputFields,setFieldBoolean,setFieldText,toggleFieldArrayValue,canGenerate,fieldValues,error,result,executableRevision});\n' : ''
  const descriptor = parse(exposure ? source.replace('</script>', exposure + '</script>') : source).descriptor
  const script = compileScript(descriptor, { id: key, inlineTemplate: true })
  const code = transformSync(script.content, { loader: 'ts', format: 'cjs' }).code
    .replace(/import\("([^"]+)"\)/g, 'Promise.resolve(require("$1"))')
  const deps: Record<string, unknown> = { vue: Vue }
  for (const match of code.matchAll(/require\("([^"]+)"\)/g)) {
    const id = match[1]!
    if (id in deps) continue
    deps[id] = id.endsWith('.vue') ? { __esModule: true, default: await compile((await import(`${id}?raw`)).default, id) } : await import(id)
  }
  const module = { exports: {} as any }
  new Function('require', 'module', 'exports', code)((id: string) => deps[id], module, module.exports)
  cache.set(key, module.exports.default)
  return module.exports.default
}
async function mount(name: string) {
  const view = await compile(fs.readFileSync(path.resolve('src/views', name), 'utf8'), name)
  const host = node('root')
  const app = renderer.createApp(view)
  app.component('el-dialog', { render: () => null })
  const instance: any = app.mount(host as any)
  return { host, app, instance: instance.$?.exposed ? Vue.proxyRefs(instance.$.exposed) : instance }
}
async function until(check: () => boolean, host: Node) {
  await vi.waitFor(() => { expect(check(), content(host).slice(0, 2500)).toBe(true) }, { timeout: 15000, interval: 40 })
}
function button(host: Node, label: string) {
  const found = find(host, n => n.type === 'button' && content(n).trim().startsWith(label))
  expect(found, `按钮${label}：${content(host).slice(0, 1000)}`).toBeTruthy()
  expect(found!.props.disabled).not.toBe(true)
  found!.props.onClick({ stopPropagation() {}, preventDefault() {} })
}

it.skipIf(process.env.PROCESSMIND_ISOLATED_CHAIN !== '1')('real 41-operation step3 adopt → step4 confirm/save → refresh → step5 actual generation', async () => {
  api.defaults.baseURL = 'http://127.0.0.1:8011'
  const requests: any[] = []
  const errors: string[] = []
  const interceptor = api.interceptors.response.use(response => {
    requests.push({ method: response.config.method, url: response.config.url, status: response.status })
    return response
  })
  const storage = new Map<string, string>()
  const localStorage = { getItem: (k: string) => storage.get(k) || null, setItem: (k: string, v: string) => storage.set(k, v), removeItem: (k: string) => storage.delete(k), get length() { return storage.size }, key: (i: number) => [...storage.keys()][i] }
  vi.stubGlobal('window', { localStorage, addEventListener() {}, removeEventListener() {}, setTimeout, clearTimeout, scrollTo() {} })
  vi.stubGlobal('localStorage', localStorage)
  vi.stubGlobal('document', { addEventListener() {}, removeEventListener() {}, getElementById: () => null })
  const apps: any[] = []
  const evidence: any = { engine: 'actual Vue page/component host + real HTTP APIs + cloned project DB', requests }
  try {
    const initial = (await api.get('/api/extract/saved-normalized-route', { params: { project_id: 8 } })).data
    expect(initial.segments).toHaveLength(41)
    expect(initial.analysis_locked).toBe(false)
    const analysis = await mount('AnalysisView.vue'); apps.push(analysis.app)
    await until(() => !!find(analysis.host, n => n.type === 'button' && content(n).trim().startsWith('一键采纳全部推荐') && !n.props.disabled), analysis.host)
    button(analysis.host, '一键采纳全部推荐')
    await until(() => content(analysis.host).includes('已采纳 41 道工序推荐。'), analysis.host)
    const adopted = (await api.get('/api/extract/saved-normalized-route', { params: { project_id: 8 } })).data
    expect(adopted.segments.filter((s: any) => s.rule_review?.decision === 'accepted')).toHaveLength(41)
    evidence.adopted = adopted.segments.length
    evidence.inherited = adopted.segments.filter((s: any) => s.rule_review?.question_trail.some((a: any) => a.nodeId === '__object_reuse')).map((s: any) => ({ id: s.id, name: s.normalized_step_name, draft: s.rule_review.analysis_draft }))
    button(analysis.host, '全部')
    await until(() => content(analysis.host).includes('当前判定结论'), analysis.host)
    const simplifiedText = content(analysis.host)
    evidence.simplified_question_ui = { answered_content_visible: simplifiedText.includes('本轮已确认的工序判定链'),
      reanswer_available: !!find(analysis.host, n => n.type === 'button' && content(n).includes('重新判断这道工序') && !n.props.disabled),
      removed_blocks: ['出现这道工序时，常一起出现', '不出现这道工序时，常见什么', '原始文件里怎么称呼它', '内容证据摘录', '已保存判定结论'] }
    expect(evidence.simplified_question_ui.answered_content_visible).toBe(true)
    expect(evidence.simplified_question_ui.reanswer_available).toBe(true)
    for (const text of evidence.simplified_question_ui.removed_blocks) expect(simplifiedText).not.toContain(text)
    analysis.app.unmount(); apps.pop()
    boundary.route.path = '/finalize'
    clearWorkflowProjectDataCache(8)
    const finalize = await mount('FinalizeView.vue'); apps.push(finalize.app)
    await until(() => !!find(finalize.host, n => n.type === 'button' && /确认全部/.test(content(n)) && !n.props.disabled), finalize.host)
    const confirm = find(finalize.host, n => n.type === 'button' && /确认全部/.test(content(n)) && !n.props.disabled)!
    confirm.props.onClick({ stopPropagation() {}, preventDefault() {} })
    await until(() => !!find(finalize.host, n => n.type === 'button' && content(n).trim().startsWith('保存并进入路线验证') && !n.props.disabled), finalize.host)
    button(finalize.host, '保存并进入路线验证')
    await until(() => boundary.push.mock.calls.some(call => call[0]?.path === '/generate'), finalize.host)
    const saved = (await api.get('/api/extract/executable-rule-revisions/latest', { params: { project_id: 8 } })).data
    expect(saved.generation_ready).toBe(true)
    evidence.saved_revision = { id: saved.id, revision: saved.revision, content_hash: saved.content_hash, processes: saved.package.route_catalog.processes.length }
    const confirmed = (await api.get('/api/extract/saved-normalized-route', { params: { project_id: 8 } })).data
    evidence.confirmed = confirmed.segments.filter((s: any) => s.rule_review?.condition_review?.status === 'confirmed').length
    // Nine fully covered mainline entries require no extra condition review;
    // all 32 explicit conditional/manual/associated configurations are saved.
    expect(evidence.confirmed).toBe(32)
    finalize.app.unmount(); apps.pop()
    // A cold page instance reads from the persisted backend revision, not the
    // view's optimistic state or a synthetic API response.
    storage.clear(); clearWorkflowProjectDataCache(8)
    boundary.route.path = '/generate'
    const generate = await mount('GenerateView.vue'); apps.push(generate.app)
    await until(() => generate.instance.inputFields.length > 0, generate.host)
    expect(generate.instance.executableRevision.content_hash).toBe(saved.content_hash)
    for (const field of generate.instance.inputFields) {
      if (field.type === 'boolean') generate.instance.setFieldBoolean(field.key, true)
      else if (field.type === 'number') generate.instance.setFieldText(field.key, field.key.endsWith('.it') ? '6' : field.key.endsWith('.ra') ? '0.4' : '45')
      else if (field.type === 'multi_select' || field.type === 'array') {
        for (const value of field.allowed_values || []) generate.instance.toggleFieldArrayValue(field.key, value)
      } else generate.instance.setFieldText(field.key, field.key.endsWith('.direction') ? '所有方位' : String(field.allowed_values?.[0] || '9Cr18'))
    }
    await Vue.nextTick()
    expect(generate.instance.canGenerate, content(generate.host).slice(0, 1500)).toBe(true)
    const run = find(generate.host, n => n.type === 'button' && /生成工艺路线/.test(content(n)) && !n.props.disabled)!
    expect(run).toBeTruthy(); run.props.onClick({ preventDefault() {} })
    await until(() => !!generate.instance.result || !!generate.instance.error, generate.host)
    expect(generate.instance.error).toBe('')
    evidence.actual_inputs = generate.instance.fieldValues
    evidence.generated = generate.instance.result
    expect(evidence.generated.executable_revision_id).toBe(saved.id)
    expect(evidence.generated.executable_content_hash).toBe(saved.content_hash)
    expect(evidence.generated.output_mode).toBe('executable_rule_revision_v2')
    expect(evidence.generated.steps.length).toBeGreaterThan(20)
    expect(evidence.generated.selected_process_ids).toHaveLength(evidence.generated.steps.length)
  } catch (error: any) { errors.push(String(error?.stack || error)); throw error }
  finally {
    evidence.errors = errors
    fs.writeFileSync(path.resolve('../.scratch/system-improvements/evidence/pm-066-070/real-chain.json'), JSON.stringify(evidence, null, 2))
    apps.forEach(app => app.unmount())
    api.interceptors.response.eject(interceptor)
    vi.unstubAllGlobals()
  }
}, 120000)
