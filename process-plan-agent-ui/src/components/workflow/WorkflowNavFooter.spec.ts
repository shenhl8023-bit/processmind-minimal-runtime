import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it, vi } from 'vitest'
import source from './WorkflowNavFooter.vue?raw'

type Node = { type: string; props: Record<string, any>; children: Node[]; text?: string; parent?: Node }
const renderer = Vue.createRenderer<Node, Node>({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: '#text', text, props: {}, children: [] }),
  createComment: text => ({ type: '#comment', text, props: {}, children: [] }),
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, key, _old, value) => { node.props[key] = value },
  insert(node, parent, anchor) { node.parent = parent; const i = anchor ? parent.children.indexOf(anchor) : -1; if (i < 0) parent.children.push(node); else parent.children.splice(i, 0, node) },
  remove(node) { if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1) },
  parentNode: node => node.parent || null,
  nextSibling: node => node.parent?.children[node.parent.children.indexOf(node) + 1] || null,
})
const compiled = transformSync(compileScript(parse(source).descriptor, { id: 'footer-test', inlineTemplate: true }).content, { loader: 'ts', format: 'cjs' }).code
const mod = { exports: {} as any }
new Function('require', 'module', 'exports', compiled)((id: string) => { if (id === 'vue') return Vue; throw new Error(id) }, mod, mod.exports)
const Footer = mod.exports.default
function all(node: Node, test: (node: Node) => boolean): Node[] { return [...(test(node) ? [node] : []), ...node.children.flatMap(child => all(child, test))] }
function text(node: Node): string { return [node.text || '', ...node.children.map(text)].join(' ') }

describe('bottom navigation notices', () => {
  it('fits inline details inside the intersection of real clipping ancestors', async () => {
    const windowEvents = Object.assign(new EventTarget(), { innerWidth: 800, innerHeight: 600 })
    const documentEvents = new EventTarget()
    vi.stubGlobal('window', windowEvents)
    vi.stubGlobal('document', documentEvents)
    vi.stubGlobal('getComputedStyle', (element: any) => element.computedStyle)
    const root: Node = { type: 'root', props: {}, children: [] }
    const app = renderer.createApp({ render: () => Vue.h(Footer, { inline: true, nextLabel: '保存', notices: [{ id: 'error', level: 'error', summary: '映射失败', detail: '详情\n'.repeat(100) }] }) })
    app.mount(root)
    const outer = { parentElement: null, computedStyle: { overflowX: 'hidden', overflowY: 'auto' }, clientTop: 0, clientLeft: 0, clientWidth: 700, clientHeight: 450, getBoundingClientRect: () => ({ left: 40, top: 80 }) }
    const inner = { parentElement: outer, computedStyle: { overflowX: 'hidden', overflowY: 'hidden' }, clientTop: 0, clientLeft: 0, clientWidth: 280, clientHeight: 240, getBoundingClientRect: () => ({ left: 120, top: 140 }) }
    const anchor = all(root, node => node.props.class === 'workflow-nav-summary')[0]!
    Object.assign(anchor, { parentElement: inner, getBoundingClientRect: () => ({ left: 140, top: 320 }) })
    try {
      all(root, node => node.type === 'button' && text(node) === '查看详情')[0]!.props.onClick()
      await Vue.nextTick()
      const popover = all(root, node => node.type === 'section')[0]!
      const style = popover.props.style || {}
      // The popup bottom is 16px above the anchor. CSS alone allows 420px.
      const height = Number.parseFloat(style.maxHeight || '420')
      const width = Number.parseFloat(style.width || '520')
      const left = 140 + Number.parseFloat(style.left || '0')
      expect(304 - height).toBeGreaterThanOrEqual(140)
      expect(height).toBeGreaterThan(0)
      expect(left).toBeGreaterThanOrEqual(120)
      expect(left + width).toBeLessThanOrEqual(400)
    } finally { app.unmount(); vi.unstubAllGlobals() }
  })

  it('recomputes inline space after ancestor scrolling and window resizing', async () => {
    const windowEvents = Object.assign(new EventTarget(), { innerWidth: 800, innerHeight: 600 })
    const documentEvents = new EventTarget()
    vi.stubGlobal('window', windowEvents)
    vi.stubGlobal('document', documentEvents)
    vi.stubGlobal('getComputedStyle', (element: any) => element.computedStyle)
    const root: Node = { type: 'root', props: {}, children: [] }
    const app = renderer.createApp({ render: () => Vue.h(Footer, { inline: true, nextLabel: '保存', notices: [{ id: 'error', level: 'error', summary: '映射失败' }] }) })
    app.mount(root)
    let top = 80
    const clip = { parentElement: null, computedStyle: { overflowX: 'visible', overflowY: 'hidden' }, clientTop: 0, clientLeft: 0, clientWidth: 700, clientHeight: 450, getBoundingClientRect: () => ({ left: 0, top }) }
    const anchor = all(root, node => node.props.class === 'workflow-nav-summary')[0]!
    Object.assign(anchor, { parentElement: clip, getBoundingClientRect: () => ({ left: 20, top: 320 }) })
    const height = () => Number.parseFloat(all(root, node => node.type === 'section')[0]!.props.style?.maxHeight || '420')
    try {
      all(root, node => node.type === 'button' && text(node) === '查看详情')[0]!.props.onClick()
      await Vue.nextTick()
      top = 220
      documentEvents.dispatchEvent(new Event('scroll'))
      await Vue.nextTick()
      expect(304 - height()).toBeGreaterThanOrEqual(220)
      top = 120
      windowEvents.dispatchEvent(new Event('resize'))
      await Vue.nextTick()
      expect(304 - height()).toBeGreaterThanOrEqual(120)
      expect(height()).toBeGreaterThan(100)
    } finally { app.unmount(); vi.unstubAllGlobals() }
  })

  it('shows the error summary first and keeps reasons/actions behind one detail entry', async () => {
    const root: Node = { type: 'root', props: {}, children: [] }
    const retry = vi.fn()
    const notices = Vue.ref([
      { id: 'success', level: 'success', summary: '已采纳2道工序推荐' },
      { id: 'failure', level: 'error', summary: '问答生成失败', detail: '模型未返回有效推荐', actions: [{ label: '重新生成问答', run: retry }] },
    ])
    const app = renderer.createApp({ render: () => Vue.h(Footer, { nextLabel: '下一步', summary: '正常统计', notices: notices.value }) })
    app.mount(root)
    try {
      expect(text(root)).toContain('问答生成失败')
      expect(text(root)).not.toContain('模型未返回有效推荐')
      expect(text(root)).not.toContain('已采纳2道工序推荐')
      const details = all(root, node => node.type === 'button' && text(node).includes('查看详情'))[0]!
      expect(details).toBeDefined()
      details.props.onClick(); await Vue.nextTick()
      expect(text(root)).toContain('模型未返回有效推荐')
      const action = all(root, node => node.type === 'button' && text(node).includes('重新生成问答'))[0]!
      action.props.onClick(); expect(retry).toHaveBeenCalledOnce()
      const close = all(root, node => node.type === 'button' && node.props['aria-label'] === '关闭消息详情')[0]!
      close.props.onClick(); await Vue.nextTick()
      expect(text(root)).not.toContain('模型未返回有效推荐')
      notices.value = []; await Vue.nextTick()
      expect(text(root)).toContain('正常统计')
      expect(all(root, node => node.type === 'button' && text(node).includes('查看详情'))).toHaveLength(0)
    } finally { app.unmount() }
  })
  it('preserves navigation actions while notices are visible', () => {
    const root: Node = { type: 'root', props: {}, children: [] }; const next = vi.fn()
    const app = renderer.createApp({ render: () => Vue.h(Footer, { nextLabel: '继续', onNext: next, notices: [{ id: 'info', summary: '正在生成', level: 'info' }] }) })
    app.mount(root)
    all(root, n => n.type === 'button' && text(n).includes('继续'))[0]!.props.onClick()
    expect(next).toHaveBeenCalledOnce(); app.unmount()
  })
})
