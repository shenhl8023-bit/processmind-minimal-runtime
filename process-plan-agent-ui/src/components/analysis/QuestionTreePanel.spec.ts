import * as Vue from 'vue'
import { createRenderer, h } from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it, vi } from 'vitest'
import source from './QuestionTreePanel.vue?raw'
import * as editableOther from '@/composables/useEditableOtherOption'
import * as materialRows from '@/composables/useQuestionTreeMaterialRows'

const script = compileScript(parse(source).descriptor, { id: 'question-tree-test', inlineTemplate: true })
const compiled = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const componentModule = { exports: {} as any }
new Function('require', 'module', 'exports', compiled)((id: string) => {
  if (id === 'vue') return Vue
  if (id === '@/composables/useEditableOtherOption') return editableOther
  if (id === '@/composables/useQuestionTreeMaterialRows') return materialRows
  throw new Error(`Unexpected dependency: ${id}`)
}, componentModule, componentModule.exports)
const QuestionTreePanel = componentModule.exports.default

type Node = { type: string; props: Record<string, any>; children: Node[]; text?: string; parent?: Node }
const renderer = createRenderer<Node, Node>({
  createElement: type => ({ type, props: {}, children: [] }),
  createText: text => ({ type: '#text', text, props: {}, children: [] }),
  createComment: text => ({ type: '#comment', text, props: {}, children: [] }),
  setText: (node, text) => { node.text = text },
  setElementText: (node, text) => { node.text = text; node.children = [] },
  patchProp: (node, key, _prev, value) => { node.props[key] = value },
  insert(node, parent, anchor) {
    node.parent = parent
    const index = anchor ? parent.children.indexOf(anchor) : -1
    if (index < 0) parent.children.push(node)
    else parent.children.splice(index, 0, node)
  },
  remove(node) {
    if (node.parent) node.parent.children.splice(node.parent.children.indexOf(node), 1)
  },
  parentNode: node => node.parent || null,
  nextSibling(node) { return node.parent?.children[(node.parent?.children.indexOf(node) ?? -1) + 1] || null },
})

function all(node: Node, predicate: (node: Node) => boolean): Node[] {
  return [...(predicate(node) ? [node] : []), ...node.children.flatMap(child => all(child, predicate))]
}

describe('finalized question tree controls', () => {
  it('validates an editable roughness threshold before submitting it', async () => {
    const root: Node = { type: 'root', props: {}, children: [] }
    const choose = vi.fn()
    const app = renderer.createApp({ render: () => h(QuestionTreePanel, {
      visible: true, emptyReason: '', currentQuestion: { id: 'guided_ra', title: 'Ra', prompt: '实际Ra小于等于多少？', options: [{ value: '0.8', label: '0.8 μm' }], recommendedValues: ['0.8'], numeric: { min: 0, exclusiveMin: true, unit: 'μm' } },
      trail: [], resultSummary: '', noteDraft: '', 'onChoose-option': choose,
    }) })
    app.mount(root)
    try {
      const input = all(root, n => n.type === 'input' && n.props.type === 'number')[0]!
      expect(input).toBeDefined()
      const submit = () => all(root, n => n.type === 'button' && n.props['data-testid'] === 'confirm-numeric-threshold')[0]!
      input.props.onInput({ target: { value: '0' } })
      await Vue.nextTick()
      expect(submit().props.disabled).toBe(true)
      submit().props.onClick()
      expect(choose).not.toHaveBeenCalled()
      input.props.onInput({ target: { value: '0.4' } })
      await Vue.nextTick()
      expect(submit().props.disabled).toBe(false)
      submit().props.onClick()
      expect(choose).toHaveBeenCalledWith({ value: '0.4', label: '0.4 μm' })
    } finally { app.unmount() }
  })
  it.each([true, false])('keeps history visible and hides unavailable reanswer controls (show question: %s)', (showQuestion) => {
    const root: Node = { type: 'root', props: {}, children: [] }
    const choose = vi.fn()
    const app = renderer.createApp({ render: () => h(QuestionTreePanel, {
      readOnly: true, visible: true, emptyReason: '',
      currentQuestion: showQuestion ? {
        id: 'rule_reason_root', title: '安排方式', prompt: '这道工序，什么情况下需要做？',
        options: [{ value: 'manual', label: '每次人工选择' }],
      } : null,
      trail: [{ nodeId: 'rule_reason_root', value: 'manual', label: '每次人工选择' }],
      resultSummary: '由用户决定是否安排', noteDraft: '',
      'onChoose-option': choose,
    }) })
    app.mount(root)
    try {
      const buttons = all(root, node => node.type === 'button')
      expect(buttons.filter(node => ['重答最后一题', '重新判断这道工序'].includes(node.text?.trim() || ''))).toHaveLength(0)
      expect(buttons.every(node => node.props.disabled)).toBe(true)
      expect(all(root, node => node.text?.includes('每次人工选择') ?? false).length).toBeGreaterThan(0)
      for (const radio of all(root, node => node.props.role === 'radio')) {
        expect(radio.props['aria-disabled']).toBe(true)
        expect(radio.props.tabindex).toBe(-1)
        radio.props.onClick()
      }
      expect(choose).not.toHaveBeenCalled()
    } finally { app.unmount() }
  })
  it('keeps completed-result actions available only while editable without losing the conclusion', async () => {
    const root: Node = { type: 'root', props: {}, children: [] }
    const readOnly = Vue.ref(true)
    const reanswer = vi.fn()
    const reset = vi.fn()
    const app = renderer.createApp({ render: () => h(QuestionTreePanel, {
      readOnly: readOnly.value, visible: true, emptyReason: '', currentQuestion: null,
      trail: [{ nodeId: 'guided_mode', value: 'manual', label: '每次人工选择' }],
      resultSummary: '由用户决定是否安排', noteDraft: '按现场需要安排',
      'onReanswer-last': reanswer, onReset: reset,
    }) })
    app.mount(root)
    try {
      expect(all(root, node => node.type === 'button')).toHaveLength(0)
      readOnly.value = false
      await Vue.nextTick()
      const buttons = all(root, node => node.type === 'button')
      expect(buttons).toHaveLength(2)
      buttons.find(node => node.text?.trim() === '重答最后一题')!.props.onClick()
      buttons.find(node => node.text?.trim() === '重新判断这道工序')!.props.onClick()
      expect(reanswer).toHaveBeenCalledOnce()
      expect(reset).toHaveBeenCalledOnce()
      readOnly.value = true
      await Vue.nextTick()
      expect(all(root, node => node.type === 'button')).toHaveLength(0)
      const texts = all(root, node => !!node.text).map(node => node.text).join(' ')
      expect(texts).toContain('由用户决定是否安排')
      expect(texts).toContain('按现场需要安排')
      expect(texts).toContain('每次人工选择')
    } finally { app.unmount() }
  })
  it('omits unavailable history actions on the first question and restores them after an answer', async () => {
    const root: Node = { type: 'root', props: {}, children: [] }
    const trail = Vue.ref<Array<{ nodeId: string; value: string; label: string }>>([])
    const app = renderer.createApp({ render: () => h(QuestionTreePanel, {
      visible: true, emptyReason: '', currentQuestion: {
        id: 'guided_mode', title: '安排方式', prompt: '这道工序如何安排？',
        options: [{ value: 'manual', label: '人工选择' }],
      }, trail: trail.value, resultSummary: '', noteDraft: '',
    }) })
    app.mount(root)
    try {
      expect(all(root, node => node.type === 'button')).toHaveLength(0)
      trail.value = [{ nodeId: 'guided_mode', value: 'manual', label: '人工选择' }]
      await Vue.nextTick()
      const buttons = all(root, node => node.type === 'button')
      expect(buttons.map(node => node.text?.trim())).toEqual(['重答最后一题', '重新判断这道工序'])
      expect(buttons.every(node => !node.props.disabled)).toBe(true)
    } finally { app.unmount() }
  })
})

it('explains temporary generation blocking without claiming that finalization has started', () => {
  const root: Node = { type: 'root', props: {}, children: [] }
  const app = renderer.createApp({ render: () => h(QuestionTreePanel, {
    readOnly: true, readOnlyReason: '问答与推荐正在生成，完成后即可回答。',
    visible: true, emptyReason: '', currentQuestion: {
      id: 'guided_mode', title: '安排方式', prompt: '这道工序怎么安排？',
      options: [{ value: 'manual', label: '由用户决定是否出现' }],
    }, trail: [], resultSummary: '', noteDraft: '',
  }) })
  app.mount(root)
  try {
    const texts = all(root, node => !!node.text).map(node => node.text).join(' ')
    expect(texts).toContain('问答与推荐正在生成，完成后即可回答。')
    expect(texts).not.toContain('已进入规则定稿')
    expect(all(root, node => node.props.role === 'radio').every(node => node.props['aria-disabled'])).toBe(true)
  } finally { app.unmount() }
})
