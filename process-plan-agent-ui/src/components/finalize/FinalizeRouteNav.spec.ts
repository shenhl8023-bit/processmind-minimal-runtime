import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it } from 'vitest'
import source from './FinalizeRouteNav.vue?raw'

const compiled = compileScript(parse(source).descriptor, {
  id: 'finalize-route-nav-test',
  inlineTemplate: true,
})
const code = transformSync(compiled.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const componentModule = { exports: {} as any }
new Function('require', 'module', 'exports', code)(
  (id: string) => {
    if (id === 'vue') return Vue
    throw new Error(`Unexpected dependency: ${id}`)
  },
  componentModule,
  componentModule.exports,
)

const renderer = Vue.createRenderer({
  createComment: (text: string) => ({ type: '#comment', text, children: [], props: {} }),
  createText: (text: string) => ({ type: '#text', text, children: [], props: {} }),
  createElement: (type: string) => ({ type, children: [], props: {}, text: '' }),
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
    if (node?.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  },
  parentNode: (node: any) => node.parent || null,
  nextSibling: (node: any) => {
    const siblings = node.parent?.children || []
    return siblings[siblings.indexOf(node) + 1] || null
  },
} as any)

function textContent(node: any): string {
  return `${node.text || ''}${(node.children || []).map(textContent).join('')}`
}

function findNode(node: any, predicate: (candidate: any) => boolean): any {
  if (predicate(node)) return node
  for (const child of node.children || []) {
    const match = findNode(child, predicate)
    if (match) return match
  }
  return null
}

function mount() {
  const emitted: boolean[] = []
  const props = {
    title: '工序顺序',
    items: [{ segment: { id: 'segment-1', sequence: 10 }, conditionText: '', edited: false }],
    activeSegmentId: 'segment-1',
    displayName: () => '车外圆',
    metaLabel: () => '',
    stepCount: () => 0,
    primarySteps: () => [],
    attachedSteps: () => [],
    isStepsExpanded: () => false,
    itemNeedsPending: () => true,
    onlyPending: true,
    allItemCount: 3,
    pendingItemCount: 1,
  }
  const host = { type: 'root', children: [], props: {} } as any
  const app = renderer.createApp({
    setup() {
      return () => Vue.h(componentModule.exports.default, {
        ...props,
        onFilterChange: (onlyPending: boolean) => emitted.push(onlyPending),
      })
    },
  })
  app.mount(host)
  return { app, emitted, host }
}

function mountEmptyPending() {
  const host = { type: 'root', children: [], props: {} } as any
  const app = renderer.createApp({
    setup() {
      return () => Vue.h(componentModule.exports.default, {
        title: '工序顺序',
        items: [],
        activeSegmentId: '',
        displayName: () => '',
        metaLabel: () => '',
        stepCount: () => 0,
        primarySteps: () => [],
        attachedSteps: () => [],
        isStepsExpanded: () => false,
        itemNeedsPending: () => false,
        onlyPending: true,
        allItemCount: 3,
        pendingItemCount: 0,
      })
    },
  })
  app.mount(host)
  return { app, host }
}

describe('finalize route navigation filters', () => {
  it('shows both counts beside the route list and emits the selected filter', async () => {
    const { app, emitted, host } = mount()
    await Vue.nextTick()

    const allButton = findNode(host, node => node.type === 'button' && textContent(node).includes('全部'))
    const pendingButton = findNode(host, node => node.type === 'button' && textContent(node).includes('待处理'))
    expect(allButton).not.toBeNull()
    expect(pendingButton).not.toBeNull()
    expect(textContent(allButton)).toContain('3')
    expect(textContent(pendingButton)).toContain('1')

    allButton.props.onClick()
    pendingButton.props.onClick()
    expect(emitted).toEqual([false, true])

    app.unmount()
  })

  it('keeps the route filter available after every pending item is resolved', async () => {
    const { app, host } = mountEmptyPending()
    await Vue.nextTick()

    const allButton = findNode(host, node => node.type === 'button' && textContent(node).includes('全部'))
    const pendingButton = findNode(host, node => node.type === 'button' && textContent(node).includes('待处理'))
    expect(allButton).not.toBeNull()
    expect(pendingButton).not.toBeNull()
    expect(textContent(host)).not.toContain('所有工序均已处理完成')

    app.unmount()
  })
})
