import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { afterEach, describe, expect, it, vi } from 'vitest'
import source from './FinalizeRuleCard.vue?raw'
import * as finalizeRulePackage from '@/utils/finalizeRulePackage'
import * as finalizeRulePresentation from '@/utils/finalizeRulePresentation'

const script = compileScript(parse(source).descriptor, {
  id: 'finalize-rule-card-test',
  inlineTemplate: true,
})
const code = transformSync(script.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const componentModule = { exports: {} as any }
const conditionEditorStub = Vue.defineComponent({ render: () => null })
new Function('require', 'module', 'exports', code)(
  (id: string) => {
    if (id === 'vue') return Vue
    if (id === '@/utils/finalizeRulePackage') return finalizeRulePackage
    if (id === '@/utils/finalizeRulePresentation') return finalizeRulePresentation
    if (id === '@/components/finalize/RuleConditionNodeEditor.vue') return conditionEditorStub
    throw new Error(`Unexpected dependency: ${id}`)
  },
  componentModule,
  componentModule.exports,
)

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
  createElement: (type: string) => ({ type, children: [], props: {}, text: '' }),
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

describe('finalize rule card process IDs', () => {
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
                then: { include_process_ids: ['process-007'], exclude_process_ids: [] },
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
