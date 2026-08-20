import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { describe, expect, it } from 'vitest'

import type { RulePackageCondition, StandardFactorDefinition } from '@/api/rulePackages'
import StandardFactorPicker from './StandardFactorPicker.vue'
import RuleConditionNodeEditor from './RuleConditionNodeEditor.vue'
import FinalizeRuleCard from './FinalizeRuleCard.vue'

const factors: StandardFactorDefinition[] = [
  {
    factor_id: 'feature.center_hole_location',
    label: '顶尖孔定位',
    category: '精度要求',
    source_field: 'cad.features',
    source_field_aliases: [],
    canonical_value: '顶尖孔',
    allowed_operators: ['contains', 'eq'],
    kmai_factor_key: 'uses_center_hole_location',
    kmai_value_mode: 'presence',
    runtime_source: 'computed',
  },
  {
    factor_id: 'precision.hole_finish',
    label: '孔精加工',
    category: '精度要求',
    source_field: 'precision.grades',
    source_field_aliases: [],
    canonical_value: '孔精加工',
    allowed_operators: ['contains', 'eq'],
    kmai_factor_key: 'has_hole_finish_machining',
    kmai_value_mode: 'presence',
    runtime_source: 'computed',
  },
]

async function renderPicker(props: {
  modelValue: RulePackageCondition
  factors: StandardFactorDefinition[]
}) {
  return renderToString(createSSRApp(StandardFactorPicker, props))
}

async function renderRecognizedRuleCard() {
  const sourceText = '当零件存在顶尖孔时，安排研顶尖孔工序'
  const candidate = {
    kind: 'condition' as const,
    when: { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
    then: { include_process_ids: ['process_center_hole'], exclude_process_ids: [] },
    preview: '结构条件',
  }
  return renderToString(createSSRApp(FinalizeRuleCard, {
    item: {
      segment: {
        id: 'process_center_hole',
        sequence: 30,
        normalized_step_name: '研顶尖孔',
        doc_coverage: { total_docs: 3, hit_docs: 1 },
      },
      conditionText: sourceText,
      defaultConditionText: sourceText,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'a'.repeat(64),
        status: 'confirmed',
        candidate,
        confirmed: candidate,
        confidence: 0.95,
        issues: [],
        field_registry_version: '2026.11',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-30T02:00:00Z',
      },
      factorNames: [],
      factorLabels: [],
      userAnswerLabels: [],
      userAnswerContextLabels: [],
      systemFactorLabels: [],
      edited: true,
      rawRuleLines: [],
      availableFactors: [],
    },
    active: false,
    displayName: '研顶尖孔',
    metaLabel: '',
    inlineEditing: false,
    inlineEditingText: '',
    editedBadge: '已编辑',
    editLabel: '编辑',
    conditionLabel: '条件',
    conditionFields: [],
    standardFactors: factors,
    factorCatalogVersion: '2026.11',
    processOptions: [{ process_id: 'process_center_hole', display_name: '研顶尖孔' }],
    conditionBusy: false,
    setInlineTextareaRef: () => undefined,
  }))
}

async function renderPendingRuleCard(options: { safe: boolean }) {
  const sourceText = '当零件存在内孔、通孔或中心孔时，纳入割型孔工序'
  const candidate = {
    kind: 'condition' as const,
    when: {
      any: [
        { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
        { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
      ],
    },
    then: { include_process_ids: ['process_shaped_hole'], exclude_process_ids: [] },
    preview: '孔类条件',
  }
  return renderToString(createSSRApp(FinalizeRuleCard, {
    item: {
      segment: {
        id: 'process_shaped_hole',
        sequence: 30,
        normalized_step_name: '割型孔',
        doc_coverage: { total_docs: 3, hit_docs: 1 },
      },
      conditionText: sourceText,
      defaultConditionText: sourceText,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'b'.repeat(64),
        status: 'pending_confirmation',
        candidate,
        confirmed: null,
        confidence: 0.95,
        issues: options.safe ? [] : ['原文中的结构差异尚未形成可执行条件。'],
        field_registry_version: '2026.11',
        confirmed_by: '',
        confirmed_at: '',
      },
      factorNames: [],
      factorLabels: [],
      userAnswerLabels: [],
      userAnswerContextLabels: [],
      systemFactorLabels: [],
      edited: false,
      rawRuleLines: [],
      availableFactors: [],
    },
    active: true,
    displayName: '割型孔',
    metaLabel: '',
    inlineEditing: false,
    inlineEditingText: '',
    editedBadge: '已编辑',
    editLabel: '编辑',
    conditionLabel: '条件',
    conditionFields: [
      { key: 'cad.features', label: 'CAD 特征集合', category: '结构特征', type: 'multi_select', operators: ['contains'], aliases: [], options: [] },
      { key: 'precision.grades', label: '精度要求', category: '精度要求', type: 'multi_select', operators: ['contains'], aliases: [], options: [] },
    ],
    standardFactors: factors,
    factorCatalogVersion: '2026.11',
    processOptions: [{ process_id: 'process_shaped_hole', display_name: '割型孔' }],
    conditionBusy: false,
    setInlineTextareaRef: () => undefined,
  }))
}

describe('StandardFactorPicker', () => {
  it('shows the Chinese factor name and category while keeping the technical id secondary', async () => {
    const html = await renderPicker({
      modelValue: {
        field: 'cad.features',
        op: 'contains',
        value: '顶尖孔',
        factor_id: 'feature.center_hole_location',
      },
      factors,
    })

    expect(html).toContain('顶尖孔定位')
    expect(html).toContain('精度要求')
    expect(html).toContain('feature.center_hole_location')
    expect(html).not.toContain('uses_center_hole_location')
  })

  it('directs an unbound standard leaf to factor selection or manual creation', async () => {
    const html = await renderPicker({
      modelValue: { field: 'precision.grades', op: 'contains', value: '未知精加工' },
      factors,
    })

    expect(html).toContain('请选择标准因子或创建手工因子')
    expect(html).toContain('创建手工布尔因子')
  })

  it('explains that an explicit manual Boolean leaf is not computed from CAD', async () => {
    const html = await renderPicker({
      modelValue: { field: 'project_factor.manual_process_deadbeef', op: 'eq', value: true },
      factors,
    })

    expect(html).toContain('该因子不能由 CAD 自动得出')
    expect(html).not.toContain('uses_center_hole_location')
  })

  it('renders factor pickers for every leaf through the recursive condition editor', async () => {
    const html = await renderToString(createSSRApp(RuleConditionNodeEditor, {
      modelValue: {
        all: [
          { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
          { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
        ],
      },
      fields: [
        { key: 'cad.features', label: 'CAD 特征集合', category: '结构特征', type: 'multi_select', operators: ['contains'], aliases: [], options: [] },
        { key: 'precision.grades', label: '精度要求', category: '精度要求', type: 'multi_select', operators: ['contains'], aliases: [], options: [] },
      ],
      factors,
    }))

    expect(html).toContain('顶尖孔定位')
    expect(html).toContain('孔精加工')
  })

  it('renders an API leaf even when inactive logical branches are null', async () => {
    const html = await renderToString(createSSRApp(RuleConditionNodeEditor, {
      modelValue: {
        all: null,
        any: null,
        not: null,
        field: 'cad.features',
        op: 'contains',
        value: '顶尖孔',
        factor_id: 'feature.center_hole_location',
      } as any,
      fields: [
        { key: 'cad.features', label: 'CAD 特征集合', category: '结构特征', type: 'multi_select', operators: ['contains'], aliases: [], options: [] },
      ],
      factors,
    }))

    expect(html).toContain('顶尖孔定位')
    expect(html).toContain('feature.center_hole_location')
    expect(html).not.toContain('同时满足')
  })

  it('keeps an AI-prefilled value visible when it is outside the field option catalog', async () => {
    const html = await renderToString(createSSRApp(RuleConditionNodeEditor, {
      modelValue: {
        field: 'special.requirements',
        op: 'contains',
        value: 'surface protection requirement',
      },
      fields: [
        {
          key: 'special.requirements',
          label: 'Special requirements',
          category: 'Requirements',
          type: 'multi_select',
          operators: ['contains'],
          aliases: [],
          options: [{ value: 'known-requirement', label: 'Known requirement' }],
        },
      ],
      factors: [],
    }))

    expect(html).toContain('value="surface protection requirement"')
    expect(html).toContain('>surface protection requirement</option>')
  })

  it('shows the Chinese factor and category beside a compact recognized rule', async () => {
    const html = await renderRecognizedRuleCard()

    expect(html).toContain('顶尖孔定位 · 精度要求')
    expect(html).toContain('feature.center_hole_location')
    expect(html).not.toContain('uses_center_hole_location')
  })

  it('groups complete rule action labels for narrow viewport layout', async () => {
    const html = await renderRecognizedRuleCard()

    expect(html).toContain('class="preview-card-action-buttons"')
    expect(html).toContain('role="group"')
    expect(html).toContain('aria-label="规则操作"')
    expect(html).toContain('恢复默认')
    expect(html).toContain('转主工序')
    expect(html).toContain('转Bool')
    expect(html).toContain('编辑')
  })

  it('keeps the prefilled candidate editor collapsed for a rule that still needs manual review', async () => {
    const html = await renderPendingRuleCard({ safe: false })

    expect(html).toContain('需要人工审核')
    expect(html).not.toContain('class="candidate-editor"')
    expect(html).toContain('顶尖孔定位')
    expect(html).toContain('孔精加工')
    expect(html).toContain('修改规则')
  })

  it('keeps a safely auto-confirmable candidate collapsed', async () => {
    const html = await renderPendingRuleCard({ safe: true })

    expect(html).not.toContain('class="candidate-editor"')
    expect(html).toContain('修改规则')
  })
})
