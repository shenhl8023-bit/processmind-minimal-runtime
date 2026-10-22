import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it } from 'vitest'
import source from './FinalizePublishPrecheckDialog.vue?raw'

const componentModule = { exports: {} as any }
const compiled = compileScript(parse(source).descriptor, {
  id: 'finalize-precheck-dialog-test',
  inlineTemplate: true,
})
const code = transformSync(compiled.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
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

function mount(result: any) {
  const emitted: unknown[][] = []
  const host = { type: 'root', children: [], props: {} } as any
  const app = renderer.createApp({
    setup() {
      return () => Vue.h(componentModule.exports.default, {
        result,
        onClose: () => emitted.push(['close']),
        onOpenTemplateMapping: () => emitted.push(['open-template-mapping']),
        onOpenRuleReview: (blocker: unknown) => emitted.push(['open-rule-review', blocker]),
      })
    },
  })
  app.mount(host)
  return { app, emitted, host }
}

describe('finalize publish precheck dialog', () => {
  it('shows each blocker once, collapses passed checks, and routes mapping repair', async () => {
    const blocker = {
      code: 'group_template_mapping_missing',
      message: '请保存至少一条有效确认映射。',
      required_by_labels: ['模板分组映射'],
    }
    const { app, emitted, host } = mount({
      project_id: 9,
      ok: false,
      checklist: [
        { code: 'schema_valid', label: '规则包结构校验', status: 'passed', message: '结构校验通过。' },
        { code: 'template_mapping', label: '分组模板映射', status: 'blocking', message: blocker.message },
      ],
      blockers: [blocker],
    })
    await Vue.nextTick()

    const fullText = textContent(host)
    expect(fullText.match(/请保存至少一条有效确认映射。/g)).toHaveLength(1)
    expect(fullText).toContain('修复映射')
    const passedChecks = findNode(host, node => node.type === 'details')
    expect(passedChecks).not.toBeNull()
    expect(passedChecks.props.open).toBeUndefined()

    const repairButton = findNode(host, node => node.type === 'button' && textContent(node).includes('修复映射'))
    repairButton.props.onClick()
    expect(emitted).toEqual([['open-template-mapping']])
    app.unmount()
  })

  it('keeps a rule-source blocker on the rule-review path', async () => {
    const blocker = {
      code: 'user_rule_sources_unconfirmed',
      message: '人工规则来源尚未确认。',
      rule_ids: ['rule-1'],
    }
    const { app, emitted, host } = mount({ project_id: 9, ok: false, checklist: [], blockers: [blocker] })
    await Vue.nextTick()

    const repairButton = findNode(host, node => node.type === 'button' && textContent(node).includes('查看待处理规则'))
    expect(repairButton).not.toBeNull()
    repairButton.props.onClick()
    expect(emitted).toEqual([['open-rule-review', blocker]])
    app.unmount()
  })

  it('routes step-feature mapping blockers to template mapping based on the repair message', async () => {
    const blocker = {
      code: 'unresolved_step_candidates',
      message: '工步尚未审定候选特征，请到模板映射页完成映射。',
    }
    const { app, emitted, host } = mount({ project_id: 9, ok: false, checklist: [], blockers: [blocker] })
    await Vue.nextTick()

    const repairButton = findNode(host, node => node.type === 'button' && textContent(node).includes('修复映射'))
    expect(repairButton).not.toBeNull()
    repairButton.props.onClick()
    expect(emitted).toEqual([['open-template-mapping']])
    app.unmount()
  })
})
