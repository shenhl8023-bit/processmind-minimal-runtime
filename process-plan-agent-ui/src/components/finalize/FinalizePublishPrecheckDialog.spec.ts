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
  it('shows exported counts and explains unmapped machining exclusions', async () => {
    const { app, host } = mount({
      project_id: 9, ok: true, checklist: [], blockers: [],
      export_summary: {
        original_process_count: 3, exported_process_count: 2,
        original_step_count: 4, exported_step_count: 2,
        excluded_processes: [{ process_id: 'internal-lap', process_name: '研顶尖孔', reason: '加工工序没有可导出的已映射工步' }],
        excluded_steps: [{ process_id: 'internal-turn', process_name: '车削', step_id: 'internal-thread', step_name: '攻螺纹', reason: '加工工步没有有效特征映射' }],
        removed_factor_keys: [],
      },
    })
    await Vue.nextTick()
    const text = textContent(host)
    expect(text).toContain('本次交付 2 道工序、2 个工步')
    expect(text).toContain('研顶尖孔')
    expect(text).toContain('车削 / 攻螺纹')
    expect(text).toContain('没有有效特征映射')
    expect(text).not.toContain('internal-')
    app.unmount()
  })

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

  it('shows named dependency context and offers to locate its target process', async () => {
    const blocker = {
      code: 'unsupported_requires',
      path: 'route_rules.process_configurations.segment-nondestructive_inspection_merge.relations[0]',
      process_id: 'segment-nondestructive_inspection_merge',
      process_name: '无损检查',
      prerequisite_process_ids: ['split-900025'],
      prerequisite_process_names: ['淬火'],
      relation_index: 0,
      message: '前置工序按当前规则可能不出现，请检查第 1 项“前置要求”关联。',
    }
    const { app, emitted, host } = mount({ project_id: 9, ok: false, checklist: [], blockers: [blocker] })
    await Vue.nextTick()

    const fullText = textContent(host)
    expect(fullText).toContain('无损检查')
    expect(fullText).toContain('淬火')
    expect(fullText).toContain('第 1 项“前置要求”')
    expect(fullText).not.toContain('segment-nondestructive_inspection_merge')
    expect(fullText).not.toContain('split-900025')

    const repairButton = findNode(host, node => node.type === 'button' && textContent(node).includes('定位“无损检查”'))
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
