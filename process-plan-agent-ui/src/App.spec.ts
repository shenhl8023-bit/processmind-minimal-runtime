import * as Vue from 'vue'
import * as VueRouter from 'vue-router'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import * as currentProject from './composables/useCurrentProject'
import * as workflowSteps from './composables/workflowSteps'
import * as productState from './composables/productStatus'
import source from './App.vue?raw'

const workflowProgress = Vue.ref<any>(null)
const blockedNotice = Vue.ref('')
const resetSignal = Vue.ref<any>(null)
const { productAccess } = productState
const retryProductStatus = vi.fn()
const messageWarning = vi.fn()
const refreshWorkflowNavigation = vi.fn(async (projectId: number) => {
  const progress = workflowProgress.value?.project_id === projectId
    ? workflowProgress.value
    : { project_id: projectId, completed_steps: 1, max_available_step: 2, workflow_revision: 1 }
  workflowProgress.value = progress
  return progress
})

const compiled = compileScript(parse(source).descriptor, { id: 'app-navigation-test', inlineTemplate: true })
const module = { exports: {} as Record<string, any> }
new Function('require', 'module', 'exports', transformSync(compiled.content, { loader: 'ts', format: 'cjs' }).code)(
  (id: string) => {
    if (id === 'vue') return Vue
    if (id === 'vue-router') return VueRouter
    if (id === 'element-plus') return { ElMessage: { warning: messageWarning, closeAll: vi.fn() }, ElMessageBox: { close: vi.fn() } }
    if (id.endsWith('/message/style/css')) return {}
    if (id === '@/components/settings/ModelSettingsDrawer.vue') return { __esModule: true, default: Vue.defineComponent(() => () => null) }
    if (id === '@/composables/useCurrentProject') return currentProject
    if (id === '@/composables/workflowNavigation') return {
      refreshWorkflowNavigation,
      workflowBlockedNotice: blockedNotice,
      workflowNavigationProgress: workflowProgress,
    }
    if (id === '@/composables/workflowResetState') return { workflowResetSignal: resetSignal }
    if (id === '@/router') return { workflowRouteLoaders: [] }
    if (id === '@/composables/productStatus') return productState
    if (id === '@/composables/workflowSteps') return workflowSteps
    if (id === '@/api/productStatus') return { refreshProductStatus: retryProductStatus }
    throw new Error(`Unexpected App dependency: ${id}`)
  }, module, module.exports,
)

type HostNode = { type: string; props: Record<string, any>; text: string; children: HostNode[]; parent: HostNode | null }
const node = (type: string, text = ''): HostNode => ({ type, props: {}, text, children: [], parent: null })
const renderer = Vue.createRenderer<HostNode, HostNode>({
  createElement: type => node(type),
  createText: text => node('#text', text),
  createComment: text => node('#comment', text),
  setText: (element, text) => { element.text = text },
  setElementText: (element, text) => { element.text = text; element.children = [] },
  parentNode: element => element.parent,
  nextSibling: element => element.parent?.children[element.parent.children.indexOf(element) + 1] ?? null,
  insert(element, parent, anchor = null) {
    if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
  },
  remove(element) {
    if (element.parent) element.parent.children.splice(element.parent.children.indexOf(element), 1)
    element.parent = null
  },
  patchProp: (element, key, _old, value) => { element.props[key] = value },
  insertStaticContent(content, parent, anchor) {
    const element = node('#static', content)
    element.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    parent.children.splice(index < 0 ? parent.children.length : index, 0, element)
    return [element, element]
  },
})

const mounted: Array<() => void> = []
beforeEach(() => {
  productAccess.value = 'ready'
  productState.productStatus.value = {
    edition: 'full', template_mapping_enabled: true,
    expires_at: null, expired: false, server_time: '2026-10-30T10:00:00+08:00',
  }
  workflowProgress.value = null
  blockedNotice.value = ''
  resetSignal.value = null
  messageWarning.mockClear()
  refreshWorkflowNavigation.mockClear()
})
afterEach(() => mounted.splice(0).forEach(unmount => unmount()))
function descendants(root: HostNode): HostNode[] { return [root, ...root.children.flatMap(descendants)] }
function text(root: HostNode): string { return root.text + root.children.map(text).join('') }
async function mountApp(path: string) {
  const router = VueRouter.createRouter({
    history: VueRouter.createMemoryHistory(),
    routes: ['/upload', '/knowledge', '/extract', '/analysis', '/finalize', '/generate', '/settings'].map(path => ({
      path, component: Vue.defineComponent(() => () => Vue.h('div', path)),
    })),
  })
  await router.push(path)
  const root = node('root')
  const app = renderer.createApp(module.exports.default)
  app.use(router)
  app.mount(root)
  mounted.push(() => app.unmount())
  const step = (number: number) => descendants(root).filter(item => String(item.props.class || '').split(' ').includes('step'))[number - 1]!
  const button = (label: string) => descendants(root).find(item => item.type === 'button' && text(item).includes(label))
  async function activate(element: HostNode, event = 'onClick') {
    element.props[event]({ key: 'Enter' })
    await Vue.nextTick()
    await new Promise(resolve => setTimeout(resolve, 0))
    await Vue.nextTick()
  }
  return { root, router, step, button, activate }
}

describe('product access shell', () => {
  it('hides and restores full mapping navigation without removing full knowledge access', async () => {
    productState.productStatus.value = { ...productState.productStatus.value!, template_mapping_enabled: false }
    const app = await mountApp('/generate?project_id=17')
    const steps = () => descendants(app.root).filter(item => String(item.props.class || '').split(' ').includes('step'))
    expect(steps()).toHaveLength(5)
    expect(app.button('工艺知识库')).toBeDefined()
    expect(text(app.root)).not.toContain('模板映射（可选）')
    productState.productStatus.value = { ...productState.productStatus.value!, template_mapping_enabled: true }
    await Vue.nextTick()
    expect(steps()).toHaveLength(6)
    expect(text(app.step(6))).toContain('6模板映射（可选）')
  })

  it('hides the knowledge entry in the basic edition while keeping model settings available', async () => {
    productState.productStatus.value = {
      edition: 'basic-trial', template_mapping_enabled: false,
      expires_at: '2026-12-31T00:00:00+08:00', expired: false, server_time: '2026-10-30T10:00:00+08:00',
    }
    const app = await mountApp('/upload')
    expect(app.button('工艺知识库')).toBeUndefined()
    expect(app.button('模型设置')).toBeDefined()
  })

  it('numbers basic steps one through five while checking internal finalize and generate progress', async () => {
    productState.productStatus.value = {
      edition: 'basic-trial', template_mapping_enabled: false,
      expires_at: '2026-12-31T00:00:00+08:00', expired: false, server_time: '2026-10-30T10:00:00+08:00',
    }
    workflowProgress.value = { project_id: 17, completed_steps: 3, max_available_step: 4, workflow_revision: 1 }
    const app = await mountApp('/analysis?project_id=17')
    expect(descendants(app.root).filter(item => String(item.props.class || '').split(' ').includes('step'))).toHaveLength(5)
    expect(text(app.step(4))).toContain('4规则定稿')
    expect(app.step(4).props.class).toContain('available')
    expect(app.step(5).props.class).toContain('locked')
    await app.activate(app.step(4))
    expect(app.router.currentRoute.value.path).toBe('/finalize')
    workflowProgress.value = { project_id: 17, completed_steps: 4, max_available_step: 5, workflow_revision: 1 }
    await Vue.nextTick()
    expect(app.step(5).props.class).toContain('available')
    await app.activate(app.step(5))
    expect(app.router.currentRoute.value.path).toBe('/generate')
  })

  it.each(['/upload', '/settings', '/knowledge', '/generate'])('shows only expiry information for %s', async path => {
    productAccess.value = 'expired'
    const app = await mountApp(`${path}?project_id=17`)
    expect(text(app.root)).toContain('试用已到期，请联系供应方。')
    expect(app.button('模型设置')).toBeUndefined()
    expect(app.button('工艺知识库')).toBeUndefined()
    expect(text(app.root)).not.toContain(path)
    expect(refreshWorkflowNavigation).not.toHaveBeenCalled()
  })

  it('unmounts cached business content and settings when an open session expires', async () => {
    const app = await mountApp('/generate?project_id=17')
    await app.activate(app.button('模型设置')!)
    productAccess.value = 'expired'
    await Vue.nextTick()
    expect(text(app.root)).toContain('试用已到期，请联系供应方。')
    expect(text(app.root)).not.toContain('/generate')
    expect(descendants(app.root).some(item => String(item.props.class || '').includes('top-bar'))).toBe(false)
  })

  it('blocks business content on status failure and offers a retry', async () => {
    productAccess.value = 'error'
    const app = await mountApp('/upload?project_id=17')
    expect(text(app.root)).toContain('无法确认产品状态')
    expect(text(app.root)).not.toContain('/upload')
    expect(refreshWorkflowNavigation).not.toHaveBeenCalled()
    await app.activate(app.button('重试')!)
    expect(retryProductStatus).toHaveBeenCalled()
  })
})

describe('knowledge page workflow navigation', () => {
  it('allows a first-time user to return to upload after opening knowledge', async () => {
    const app = await mountApp('/upload')
    await app.activate(app.button('工艺知识库')!)
    expect(app.router.currentRoute.value.path).toBe('/knowledge')
    expect(app.step(1).props.role).toBe('button')
    expect(app.step(1).props.tabindex).toBe(0)
    await app.activate(app.step(1))
    expect(app.router.currentRoute.value.path).toBe('/upload')
  })

  it('offers a direct return button when knowledge is opened without browser history', async () => {
    const app = await mountApp('/knowledge')
    const returnButton = app.button('返回第一步')
    expect(returnButton).toBeDefined()
    await app.activate(returnButton!)
    expect(app.router.currentRoute.value.path).toBe('/upload')
    expect(app.button('工艺知识库')).toBeDefined()
  })

  it('keeps later workflow steps locked when no project has been created', async () => {
    const app = await mountApp('/knowledge')
    for (const number of [2, 3, 4, 5, 6]) {
      expect(app.step(number).props.class).toContain('locked')
      await app.activate(app.step(number))
      expect(app.router.currentRoute.value.path).toBe('/knowledge')
    }
  })

  it('locks later steps from the navigation bar until the current milestone is complete', async () => {
    const app = await mountApp('/upload?project_id=17')
    expect(app.step(2).props.class).toContain('available')
    expect(app.step(3).props.class).toContain('locked')
    await app.activate(app.step(3))
    expect(app.router.currentRoute.value.path).toBe('/upload')
    expect(messageWarning).toHaveBeenCalledWith(expect.stringContaining('路线归并'))
  })

  it('preserves the project when returning with the keyboard', async () => {
    const app = await mountApp('/knowledge?project_id=17')
    await app.activate(app.step(1), 'onKeydown')
    expect(app.router.currentRoute.value.path).toBe('/upload')
    expect(app.router.currentRoute.value.query).toEqual({ project_id: '17' })
  })

  it('keeps the project but drops knowledge-only query parameters on direct return', async () => {
    const app = await mountApp('/knowledge?project_id=17&q=allowance&route_version_id=9')
    const returnButton = app.button('返回第一步')
    expect(returnButton).toBeDefined()
    await app.activate(returnButton!)
    expect(app.router.currentRoute.value.path).toBe('/upload')
    expect(app.router.currentRoute.value.query).toEqual({ project_id: '17' })
  })
})
