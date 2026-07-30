import { describe, expect, it } from 'vitest'

import {
  buildCompileRequestFromCards,
  buildManualBooleanRuleCandidate,
  finalizeRuleMode,
  hasCurrentConfirmedUserRule,
  isActionableConditionText,
  isSafeForBatchRuleConfirmation,
  manualRuleModeActionState,
  requiresServerRuleConditionRefresh,
} from './finalizeRulePackage'
import { nestFactorValues } from '@/composables/useGenerateInputFields'
import type {
  RuleConditionReview,
  RulePackageCondition,
  StandardFactorDefinition,
} from '@/api/rulePackages'


function finalizeItem(overrides: Record<string, any> = {}) {
  return {
    segment: {
      id: 'process_prepare',
      sequence: 10,
      normalized_step_name: '准备',
      step_family: 'prepare',
      source_nodes: [],
      doc_coverage: { total_docs: 2, hit_docs: 2 },
      ...overrides,
    },
    conditionText: '全部样本中稳定出现',
    factorNames: ['always=true'],
    userAnswerLabels: [],
    userAnswerContextLabels: [],
    systemFactorLabels: [],
  }
}

function baseConditionFields() {
  return [
    { key: 'material.grade', label: '材料牌号', category: '材料', type: 'single_select', operators: ['eq', 'neq', 'in'], aliases: [], source: 'CAD/PLM', options: [{ value: '9Cr18', label: '9Cr18' }], required: true, allow_custom: true },
    { key: 'cad.features', label: 'CAD 特征集合', category: '结构特征', type: 'multi_select', operators: ['contains'], aliases: [], source: 'CAD', options: [{ value: '扁位/平面', label: '扁位/平面' }, { value: '槽类特征', label: '槽类特征' }], required: true, allow_custom: true },
    { key: 'precision.grades', label: '精度/表面要求集合', category: '精度要求', type: 'multi_select', operators: ['contains'], aliases: [], source: 'CAD/工艺要求', options: [{ value: '孔精加工', label: '孔精加工' }], required: true, allow_custom: true },
    { key: 'special.requirements', label: '特殊要求', category: '特殊要求', type: 'multi_select', operators: ['contains'], aliases: [], source: '人工补充/图样技术要求', options: [{ value: '渗氮层要求', label: '渗氮层要求' }, { value: '无损检测要求', label: '无损检测要求' }, { value: '磁粉检查要求', label: '磁粉检查要求' }], required: false, allow_custom: true },
  ] as any
}

function presenceFactor(
  factorId: string,
  label: string,
  category: string,
  sourceField: string,
  canonicalValue: string,
): StandardFactorDefinition {
  return {
    factor_id: factorId,
    label,
    category,
    source_field: sourceField,
    source_field_aliases: [],
    canonical_value: canonicalValue,
    allowed_operators: ['contains', 'eq'],
    kmai_factor_key: factorId.replace(/\./g, '_'),
    kmai_value_mode: 'presence',
    runtime_source: 'computed',
  }
}

function scalarFactor(
  factorId: string,
  label: string,
  category: string,
  sourceField: string,
): StandardFactorDefinition {
  return {
    factor_id: factorId,
    label,
    category,
    source_field: sourceField,
    source_field_aliases: [],
    canonical_value: null,
    allowed_operators: ['eq', 'gt', 'gte', 'lt', 'lte', 'between'],
    kmai_factor_key: sourceField.replace(/\./g, '_'),
    kmai_value_mode: 'condition_value',
    runtime_source: 'manual_override',
  }
}

const factors: StandardFactorDefinition[] = [
  {
    factor_id: 'material.grade',
    label: '材料牌号',
    category: '材料',
    source_field: 'material.grade',
    source_field_aliases: [],
    canonical_value: null,
    allowed_operators: ['eq', 'neq', 'in'],
    kmai_factor_key: 'material_grade',
    kmai_value_mode: 'condition_value',
    runtime_source: 'computed',
  },
  presenceFactor('feature.flat_or_plane', '扁位/平面', '结构特征', 'cad.features', '扁位/平面'),
  presenceFactor('feature.slot', '槽类特征', '结构特征', 'cad.features', '槽类特征'),
  presenceFactor('feature.standard_or_aux_hole', '普通孔/辅助孔', '结构特征', 'cad.features', '普通孔/辅助孔'),
  presenceFactor('feature.reamed_or_precision_hole', '铰孔/精孔', '结构特征', 'cad.features', '铰孔/精孔'),
  presenceFactor('feature.shaped_hole_or_cut_flat', '型孔/割扁', '结构特征', 'cad.features', '型孔/割扁'),
  presenceFactor('feature.center_hole_location', '顶尖孔定位', '精度要求', 'cad.features', '顶尖孔'),
  presenceFactor('precision.hole_finish', '孔精加工', '精度要求', 'precision.grades', '孔精加工'),
  presenceFactor('precision.honing', '珩孔要求', '精度要求', 'precision.grades', '珩孔要求'),
  presenceFactor('precision.hole_lapping', '研孔要求', '精度要求', 'precision.grades', '研孔要求'),
  presenceFactor('precision.outer_diameter_grinding', '外圆磨削', '精度要求', 'precision.grades', '外圆磨削'),
  presenceFactor('precision.end_face_grinding', '端面磨削', '精度要求', 'precision.grades', '端面磨削'),
  presenceFactor('precision.slot_grinding', '槽磨削', '精度要求', 'precision.grades', '槽磨削'),
  presenceFactor('precision.outer_diameter_lapping', '研外圆', '精度要求', 'precision.grades', '研外圆'),
  presenceFactor('requirement.nitrided_layer', '渗氮层要求', '热处理', 'special.requirements', '渗氮层要求'),
  presenceFactor('requirement.chromic_acid_anodizing', '铬酸阳极化要求', '表面处理', 'special.requirements', '铬酸阳极化要求'),
  presenceFactor('requirement.hard_anodizing', '硬质阳极化要求', '表面处理', 'special.requirements', '硬质阳极化要求'),
  presenceFactor('requirement.traceability_marking', '追溯标印', '检验与标识', 'special.requirements', '追溯标印'),
  presenceFactor('requirement.nondestructive_testing', '无损检测要求', '检验与标识', 'special.requirements', '无损检测要求'),
  presenceFactor('requirement.magnetic_particle_inspection', '磁粉检查要求', '检验与标识', 'special.requirements', '磁粉检查要求'),
  presenceFactor('requirement.burn_inspection', '烧伤检查要求', '检验与标识', 'special.requirements', '烧伤检查要求'),
  scalarFactor('measurement.outer_diameter_it', '外圆尺寸精度 IT', '尺寸精度', 'precision.outer_diameter_it'),
  scalarFactor('measurement.inner_diameter_it', '内孔尺寸精度 IT', '尺寸精度', 'precision.inner_diameter_it'),
  scalarFactor('measurement.dimension_it', '尺寸精度 IT', '尺寸精度', 'precision.dimension_it'),
]

function confirmedReview(
  when: RulePackageCondition,
  overrides: Partial<RuleConditionReview> = {},
): RuleConditionReview {
  const candidate = {
    kind: 'condition' as const,
    when,
    then: { include_process_ids: ['process_hone'], exclude_process_ids: [], reason: '用户确认' },
    preview: '标准因子条件',
  }
  return {
    source_text: '当存在孔精加工要求时，纳入珩孔工序',
    source_hash: 'a'.repeat(64),
    status: 'confirmed',
    candidate,
    confirmed: JSON.parse(JSON.stringify(candidate)),
    confidence: 0.95,
    issues: [],
    field_registry_version: '2026.11',
    confirmed_by: '测试用户',
    confirmed_at: '2026-07-30T02:00:00Z',
    ...overrides,
  }
}

function compileArgs(cards: any[], standardFactors = factors) {
  return {
    projectId: 12,
    packageName: 'factor_bound_rules',
    routeVersionId: 3,
    cards,
    displayName: (segment: any) => segment.normalized_step_name,
    phaseLabel: () => 'machining',
    primarySteps: () => ['主工步'],
    attachedSteps: () => [],
    conditionFields: baseConditionFields(),
    standardFactors,
  }
}


describe('V2 compile DTO from finalize cards', () => {
  it('treats an in-card semantic edit as pending until candidate and confirmed signatures match', () => {
    const sourceText = '当存在孔精加工要求时，纳入珩孔工序'
    const item: any = {
      ...finalizeItem({ id: 'process_hone', normalized_step_name: '珩孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      factorNames: [],
      conditionReview: confirmedReview({
        field: 'precision.grades',
        op: 'contains',
        value: '孔精加工',
        factor_id: 'precision.hole_finish',
      }),
    }

    expect(hasCurrentConfirmedUserRule(item, '2026.11')).toBe(true)
    item.conditionReview.candidate.when = {
      field: 'precision.grades',
      op: 'contains',
      value: '珩孔要求',
      factor_id: 'precision.honing',
    }
    expect(hasCurrentConfirmedUserRule(item, '2026.11')).toBe(false)
    item.conditionReview.candidate = JSON.parse(JSON.stringify(item.conditionReview.confirmed))
    expect(hasCurrentConfirmedUserRule(item, '2026.12')).toBe(false)
  })

  it('batch-confirms only current uniquely bound candidates, with relation and manual Boolean exceptions', () => {
    const sourceText = '当需要追溯标印时，安排标记工序'
    const item: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      factorNames: [],
      conditionReview: {
        ...confirmedReview({
          field: 'special.requirements',
          op: 'contains',
          value: '追溯标印',
          factor_id: 'requirement.traceability_marking',
        }, { source_text: sourceText, status: 'pending_confirmation', confirmed: null }),
      },
    }

    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(true)
    delete item.conditionReview.candidate.when.factor_id
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(false)
    item.conditionReview.candidate.when.factor_id = 'requirement.traceability_marking'
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.12')).toBe(false)

    const relationItem: any = {
      ...item,
      conditionText: '淬火工序之后设置该工序',
      conditionReview: {
        ...item.conditionReview,
        source_text: '淬火工序之后设置该工序',
        field_registry_version: '2026.11',
        candidate: {
          kind: 'process_relation',
          relation: {
            relation_type: 'trigger_after',
            source_process_ids: ['process_quench'],
            target_process_ids: ['process_mark'],
          },
          preview: '淬火后标记',
        },
      },
    }
    expect(isSafeForBatchRuleConfirmation(relationItem, factors, '2026.11')).toBe(true)

    const manualItem: any = {
      ...item,
      conditionReview: {
        ...item.conditionReview,
        candidate: {
          kind: 'condition',
          when: { field: 'project_factor.manual_process_deadbeef', op: 'eq', value: true },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
          preview: '用户手工决定是否标记',
        },
      },
    }
    expect(isSafeForBatchRuleConfirmation(manualItem, factors, '2026.11')).toBe(true)
  })

  it('preserves standard factor ids in the V2 compile request and binds generated static leaves', () => {
    const userItem: any = {
      ...finalizeItem({ id: 'process_hone', sequence: 50, normalized_step_name: '珩孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当存在孔精加工要求时，纳入珩孔工序',
      factorNames: [],
      edited: true,
      conditionReview: confirmedReview({
        field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
      }),
    }
    const manualCandidate = buildManualBooleanRuleCandidate({
      ...finalizeItem({ id: 'process_manual', sequence: 60, normalized_step_name: '手工检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
    }, '是否需要手工检查')
    const manualSourceText = '当用户选择“是否需要手工检查”为是时，纳入“手工检查”工序。'
    const manualItem: any = {
      ...finalizeItem({ id: 'process_manual', sequence: 60, normalized_step_name: '手工检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: manualSourceText,
      factorNames: [],
      edited: true,
      conditionReview: confirmedReview(manualCandidate.when!, {
        source_text: manualSourceText,
        candidate: manualCandidate,
        confirmed: JSON.parse(JSON.stringify(manualCandidate)),
        confirmed_by: '用户直接设定',
      }),
    }
    const staticItems = [
      ['process_heat', '调质'],
      ['process_center', '研顶尖孔'],
      ['process_grind_hole', '磨孔'],
      ['process_mark_static', '标记'],
    ].map(([id, normalized_step_name], index) => ({
      ...finalizeItem({ id, sequence: 100 + index, normalized_step_name, doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '根据不同结构类型决定是否安排该工序',
      factorNames: [],
      edited: true,
    }))

    const request = buildCompileRequestFromCards(compileArgs([userItem, manualItem, ...staticItems]))
    const userRule = request.rules!.find(rule => rule.source === 'user_confirmed' && rule.source_segment_id === 'process_hone')!
    expect(userRule.when).toEqual({
      field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
    })

    const leaves: Array<{ source?: string; leaf: any }> = []
    function collectLeaves(condition: RulePackageCondition, source?: string) {
      if ('field' in condition) {
        leaves.push({ source, leaf: condition })
        return
      }
      if ('all' in condition) condition.all.forEach(child => collectLeaves(child, source))
      else if ('any' in condition) condition.any.forEach(child => collectLeaves(child, source))
      else collectLeaves(condition.not, source)
    }
    request.rules!.forEach(rule => collectLeaves(rule.when, rule.source))

    expect(leaves.some(item => item.source === 'system_static')).toBe(true)
    leaves.forEach(({ leaf }) => {
      if (leaf.field.startsWith('project_factor.manual_process_')) {
        expect(leaf).not.toHaveProperty('factor_id')
      } else {
        expect(leaf.factor_id).toEqual(expect.any(String))
      }
    })
  })

  it('blocks locally when a code-owned static leaf has no unique catalog match', () => {
    const centerHoleItem = {
      ...finalizeItem({ id: 'process_center', normalized_step_name: '研顶尖孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '根据不同结构类型决定是否安排该工序',
      factorNames: [],
      edited: true,
    }
    const withoutCenterHole = factors.filter(item => item.factor_id !== 'feature.center_hole_location')

    expect(() => buildCompileRequestFromCards(compileArgs([centerHoleItem], withoutCenterHole)))
      .toThrow(/顶尖孔.*标准因子/)
  })

  it('blocks locally when a confirmed user leaf is still unbound', () => {
    const sourceText = '当存在孔精加工要求时，纳入珩孔工序'
    const unbound = {
      kind: 'condition' as const,
      when: { field: 'precision.grades', op: 'contains', value: '孔精加工' },
      then: { include_process_ids: ['process_hone'], exclude_process_ids: [] },
      preview: '孔精加工',
    }
    const item: any = {
      ...finalizeItem({ id: 'process_hone', normalized_step_name: '珩孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      factorNames: [],
      edited: true,
      conditionReview: confirmedReview(unbound.when, {
        source_text: sourceText,
        candidate: unbound,
        confirmed: JSON.parse(JSON.stringify(unbound)),
      }),
    }

    expect(() => buildCompileRequestFromCards(compileArgs([item])))
      .toThrow(/process_hone.*条件.*标准因子/)
  })

  it('requires re-review when the confirmed rule kind no longer matches the user text', () => {
    const relationCard: any = {
      ...finalizeItem({ id: 'process_ndt', normalized_step_name: '无损检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '淬火工序之后设置该工序',
      factorNames: [],
      conditionReview: {
        source_text: '淬火工序之后设置该工序',
        status: 'confirmed',
        candidate: {
          kind: 'condition',
          when: { field: 'special.requirements', op: 'contains', value: '无损检测要求', factor_id: 'requirement.nondestructive_testing' },
          then: { include_process_ids: ['process_ndt'], exclude_process_ids: [] },
          preview: '特殊要求 包含 无损检测要求',
        },
        confirmed: {
          kind: 'condition',
          when: { field: 'special.requirements', op: 'contains', value: '无损检测要求', factor_id: 'requirement.nondestructive_testing' },
          then: { include_process_ids: ['process_ndt'], exclude_process_ids: [] },
          preview: '特殊要求 包含 无损检测要求',
        },
      },
    }

    expect(finalizeRuleMode(relationCard)).toBe('relation')
    expect(hasCurrentConfirmedUserRule(relationCard)).toBe(false)

    relationCard.conditionReview.confirmed.kind = 'process_relation'
    relationCard.conditionReview.confirmed.when = null
    relationCard.conditionReview.confirmed.then = null
    relationCard.conditionReview.confirmed.relation = {
      relation_type: 'trigger_after',
      source_process_ids: ['process_quench'],
      target_process_ids: ['process_ndt'],
    }
    relationCard.conditionReview.candidate = JSON.parse(JSON.stringify(relationCard.conditionReview.confirmed))
    expect(hasCurrentConfirmedUserRule(relationCard)).toBe(true)
  })

  it('classifies mainline, actionable, and unresolved cards before parsing', () => {
    const mainline = finalizeItem()
    ;(mainline as any).conditionReview = {
      source_text: mainline.conditionText,
      status: 'invalid',
      issues: ['旧解析状态'],
    }
    expect(finalizeRuleMode(mainline)).toBe('mainline')
    expect(isActionableConditionText('当外圆尺寸精度达到 IT8 时，纳入磨外圆工序')).toBe(true)
    expect(finalizeRuleMode({
      ...finalizeItem({ doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '根据不同结构类型决定是否安排该工序',
      factorNames: [],
    })).toBe('unresolved')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_burn_inspect', normalized_step_name: '烧伤检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '前面存在淬火工序，就出现烧伤检查',
      factorNames: [],
    })).toBe('relation')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_copper_remove', normalized_step_name: '除铜', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '前面有镀铜时，安排此工序',
      factorNames: [],
    })).toBe('relation')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_stress_relief', normalized_step_name: '去应力', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当粗加工后释放应力，避免后续精加工变形',
      factorNames: [],
    })).toBe('relation')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_copper_remove', normalized_step_name: '除铜', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '前面出现镀铜这个工序时，需要安排此工序',
      factorNames: [],
    })).toBe('relation')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_burn_inspect', normalized_step_name: '烧伤检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '淬火之后，需要加入该工序',
      factorNames: [],
    })).toBe('relation')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当零件需要追溯、编号或批次标识时，安排标记工序',
      factorNames: [],
    })).toBe('conditional')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_copper', normalized_step_name: '镀铜', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当防护、防腐蚀、绝缘或表面稳定性要求满足时，安排镀铜工序',
      factorNames: [],
    })).toBe('conditional')
    ;['镀铜', '铬酸阳极化', '除铜'].forEach((processName) => {
      expect(finalizeRuleMode({
        ...finalizeItem({ id: `process_${processName}`, normalized_step_name: processName, doc_coverage: { total_docs: 3, hit_docs: 1 } }),
        conditionText: `当只有部分结构或工艺要求下才会出现时，安排“${processName}”工序满足表面处理或防护要求。`,
        factorNames: [],
      })).toBe('conditional')
    })
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_clean', normalized_step_name: '清洗', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '将其设置为主工序，始终保留在路线中',
      factorNames: [],
      edited: true,
    })).toBe('mainline')
    ;[
      '把该工序改为主线工序',
      '作为基础工序无条件进入路线',
      '此工序属于必经工序',
      '固定为主工序，默认保留',
    ].forEach((conditionText) => {
      expect(finalizeRuleMode({
        ...finalizeItem({ id: 'process_clean', normalized_step_name: '清洗', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
        conditionText,
        factorNames: [],
        edited: true,
      })).toBe('mainline')
    })
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_clean', normalized_step_name: '清洗', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '视情况将该工序作为主线处理',
      factorNames: [],
      edited: true,
    })).not.toBe('mainline')
  })

  it('only batch-confirms current high-confidence candidates or trusted local fallbacks', () => {
    const item: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当需要追溯标印时，安排标记工序',
      factorNames: [],
      conditionReview: {
        source_text: '当需要追溯标印时，安排标记工序',
        status: 'pending_confirmation',
        confidence: 0.9,
        issues: [],
        candidate: {
          kind: 'condition',
          when: { field: 'special.requirements', op: 'contains', value: '追溯标印', factor_id: 'requirement.traceability_marking' },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
        },
        field_registry_version: '2026.11',
      },
    }

    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(true)
    item.conditionReview.confidence = 0.79
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(false)
    item.conditionReview.confidence = 0.95
    item.conditionReview.issues = ['模型候选需要重点核对']
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(false)
    item.conditionReview.confidence = 0.65
    item.conditionReview.issues = [
      'AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。',
      '已使用内置规则解析器生成候选结果，请重点核对。',
    ]
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(true)
    item.conditionReview.issues = [
      '已使用内置规则解析器生成候选结果，请重点核对。',
      '条件无法可靠映射到标准字段，请补充字段、比较关系和阈值。',
    ]
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(false)
    item.conditionReview.issues = []
    item.conditionReview.source_text = '旧条件'
    expect(isSafeForBatchRuleConfirmation(item, factors, '2026.11')).toBe(false)
  })

  it('refreshes pending candidates through the server before batch confirmation', () => {
    const pendingItem: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当需要追溯标印时，安排标记工序',
      factorNames: [],
      conditionReview: {
        source_text: '当需要追溯标印时，安排标记工序',
        status: 'pending_confirmation',
        confidence: 0.95,
        issues: [],
        parser_version: 'older-parser',
        field_registry_version: 'older-registry',
        candidate: {
          kind: 'condition',
          when: { field: 'special.requirements', op: 'contains', value: '追溯标印' },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
        },
      },
    }

    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(true)
    pendingItem.conditionReview.status = 'confirmed'
    pendingItem.conditionReview.confirmed = pendingItem.conditionReview.candidate
    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(false)
  })

  it('builds a stable user-controlled boolean switch for the target process', () => {
    const item: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '是否标记由用户决定',
      factorNames: [],
    }

    const first = buildManualBooleanRuleCandidate(item, '是否标记')
    const second = buildManualBooleanRuleCandidate(item, '是否需要标记')

    expect(first.when).toEqual({
      field: first.field_definitions?.[0]?.key,
      op: 'eq',
      value: true,
    })
    expect(first.then?.include_process_ids).toEqual(['process_mark'])
    expect(first.then?.exclude_process_ids).toEqual([])
    expect(first.field_definitions?.[0]).toMatchObject({
      label: '是否标记',
      category: '可选工序',
      type: 'boolean',
      operators: ['eq', 'neq'],
      source: '用户直接设定',
      required: false,
      allow_custom: false,
    })
    expect(second.field_definitions?.[0]?.key).toBe(first.field_definitions?.[0]?.key)

    const sourceText = '当用户选择“是否标记”为是时，纳入“标记”工序。'
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'manual_boolean',
      routeVersionId: 3,
      cards: [
        finalizeItem(),
        {
          ...item,
          conditionText: sourceText,
          edited: true,
          conditionReview: {
            source_text: sourceText,
            source_hash: 'a'.repeat(64),
            status: 'confirmed',
            candidate: first,
            confirmed: first,
            confidence: 1,
            issues: [],
            field_registry_version: '2026.09',
            confirmed_by: '用户直接设定',
            confirmed_at: '2026-07-27T03:00:00Z',
          },
        },
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields).toContainEqual(expect.objectContaining({
      key: first.field_definitions?.[0]?.key,
      label: '是否标记',
      type: 'boolean',
      required: false,
    }))
    expect(request.rules).toContainEqual(expect.objectContaining({
      source: 'user_confirmed',
      when: first.when,
      then: expect.objectContaining({ include_process_ids: ['process_mark'] }),
    }))
    expect(request.rules).toContainEqual(expect.objectContaining({
      source: 'user_confirmed',
      when: { field: 'project_factor.manual_process_487e1c0a', op: 'eq', value: false },
      then: expect.objectContaining({ exclude_process_ids: ['process_mark'], include_process_ids: [] }),
    }))
  })

  it('keeps manual mode actions available on every non-editing card', () => {
    const mainline: any = finalizeItem()
    const conditional: any = {
      ...finalizeItem({ id: 'process_grind', normalized_step_name: '磨外圆', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当外圆尺寸精度达到 IT8 时，纳入磨外圆工序',
      factorNames: [],
    }
    const manualBoolean: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当用户选择“是否需要标记”为是时，纳入“标记”工序。',
      factorNames: [],
      conditionReview: {
        source_text: '当用户选择“是否需要标记”为是时，纳入“标记”工序。',
        status: 'confirmed',
        candidate: {
          kind: 'condition',
          when: { field: 'project_factor.manual_process_487e1c0a', op: 'eq', value: true },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
          field_definitions: [{
            key: 'project_factor.manual_process_487e1c0a',
            label: '是否需要标记',
            category: '可选工序',
            type: 'boolean',
            operators: ['eq', 'neq'],
            aliases: [],
            source: '用户直接设定',
            options: [],
            allow_custom: false,
          }],
        },
        confirmed: {
          kind: 'condition',
          when: { field: 'project_factor.manual_process_487e1c0a', op: 'eq', value: true },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
          field_definitions: [{
            key: 'project_factor.manual_process_487e1c0a',
            label: '是否需要标记',
            category: '可选工序',
            type: 'boolean',
            operators: ['eq', 'neq'],
            aliases: [],
            source: '用户直接设定',
            options: [],
            allow_custom: false,
          }],
        },
      },
    }

    expect(manualRuleModeActionState(mainline, false)).toEqual({
      visible: true,
      mainlineActive: true,
      booleanActive: false,
    })
    expect(manualRuleModeActionState(conditional, false)).toEqual({
      visible: true,
      mainlineActive: false,
      booleanActive: false,
    })
    expect(manualRuleModeActionState(manualBoolean, false)).toEqual({
      visible: true,
      mainlineActive: false,
      booleanActive: true,
    })
    expect(manualRuleModeActionState(conditional, true).visible).toBe(false)
  })

  it('builds a stable process catalog without unreferenced condition fields', () => {
    const cards = [
      finalizeItem(),
      finalizeItem({ id: 'process_mill_slot', sequence: 20, normalized_step_name: '铣槽' }),
      finalizeItem({ id: 'quench-a', sequence: 30, normalized_step_name: '淬火' }),
    ]
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'demo_rules',
      routeVersionId: 3,
      cards,
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.map(field => field.key)).toEqual([])
    expect(request.processes.some(item => item.process_id === 'process_quench')).toBe(true)
    expect(request.processes.some(item => item.main)).toBe(true)
    expect(request.rules).toEqual([])
    expect(request.test_cases).toHaveLength(1)
    expect(request.test_cases![0]!.case_id).toBe('default-smoke')
    expect(request.test_cases![0]!.expect.included_process_ids!.length).toBeGreaterThan(0)
    expect(request.test_cases![0]!.input).toEqual({})
  })

  it('includes nondestructive testing as a special requirement and maps it to the normalized process', () => {
    const sourceText = '当零件有无损检测要求时，安排无损检查工序'
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'ndt_rules',
      routeVersionId: 3,
      cards: [{
        ...finalizeItem({ id: 'process_ndt', sequence: 30, normalized_step_name: '无损检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
        conditionText: sourceText,
        edited: true,
        conditionReview: {
          source_text: sourceText,
          source_hash: 'a'.repeat(64),
          status: 'confirmed',
          candidate: {
            kind: 'condition',
            when: { field: 'special.requirements', op: 'contains', value: '无损检测要求', factor_id: 'requirement.nondestructive_testing' },
            then: { include_process_ids: ['process_ndt'], exclude_process_ids: [], reason: '用户审核' },
            preview: '特殊要求 包含 无损检测要求',
          },
          confirmed: {
            kind: 'condition',
            when: { field: 'special.requirements', op: 'contains', value: '无损检测要求', factor_id: 'requirement.nondestructive_testing' },
            then: { include_process_ids: ['process_ndt'], exclude_process_ids: [], reason: '用户审核' },
            preview: '特殊要求 包含 无损检测要求',
          },
          confidence: 0.9,
          issues: [],
          field_registry_version: '2026.09',
          confirmed_by: '规则包整体审核',
          confirmed_at: '2026-07-23T02:00:00Z',
        },
      }],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'inspection',
      primarySteps: () => [],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.find(field => field.key === 'special.requirements')?.options).toContainEqual({
      value: '无损检测要求', label: '无损检测要求',
    })
    expect(request.rules).toContainEqual(expect.objectContaining({
      rule_id: 'user.process_ndt',
      when: { field: 'special.requirements', op: 'contains', value: '无损检测要求', factor_id: 'requirement.nondestructive_testing' },
      then: expect.objectContaining({ include_process_ids: ['process_ndt'] }),
    }))
  })

  it('exports an explicit main-process instruction as main=true', () => {
    const mainCard = {
      ...finalizeItem({ id: 'process_clean', sequence: 20, normalized_step_name: '清洗', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '将其设置为主工序，始终保留在路线中',
      factorNames: [],
      edited: true,
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'main_process_instruction',
      routeVersionId: 3,
      cards: [mainCard],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'auxiliary',
      primarySteps: () => ['清洗'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.processes).toEqual([expect.objectContaining({ process_id: 'process_clean', main: true })])
  })

  it('carries template aliases as hidden metadata without changing process display names', () => {
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'template_alias_metadata',
      routeVersionId: 3,
      cards: [
        finalizeItem({
          id: 'process_drill',
          sequence: 70,
          normalized_step_name: '钻孔',
          template_group_aliases: [{
            source_operation_id: 80,
            alias: '钻孔（A侧/外环槽）',
            template_group_id: '3358f0f62d04abb99d35dec48ef73e1',
            template_group_path: ['A侧', '外环槽'],
          }],
        }),
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['钻孔'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    const process = request.processes[0]!
    expect(process.display_name).toBe('钻孔')
    expect(process.template_group_aliases).toEqual([{
      source_operation_id: 80,
      alias: '钻孔（A侧/外环槽）',
      template_group_id: '3358f0f62d04abb99d35dec48ef73e1',
      template_group_path: ['A侧', '外环槽'],
    }])
  })

  it('nests dotted factor keys for expression engine', () => {
    expect(nestFactorValues({
      'material.grade': '9Cr18',
      'cad.features': ['槽类特征'],
      target_hardness_hrc: 58,
    })).toEqual({
      material: { grade: '9Cr18' },
      cad: { features: ['槽类特征'] },
      target_hardness_hrc: 58,
    })
  })

  it('exports a confirmed user AST with higher priority and its referenced field', () => {
    const sourceText = '当外圆尺寸精度达到 IT8 时，纳入“磨外圆”工序'
    const card = {
      ...finalizeItem({ id: 'process_grind_outer', sequence: 30, normalized_step_name: '磨外圆', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'a'.repeat(64),
        status: 'confirmed',
        candidate: {
          when: { field: 'precision.outer_diameter_it', op: 'lte', value: 8, factor_id: 'measurement.outer_diameter_it' },
          then: { include_process_ids: ['process_grind_outer'], exclude_process_ids: [], reason: '用户确认' },
          preview: '外圆尺寸精度 IT ≤ 8',
        },
        confirmed: {
          when: { field: 'precision.outer_diameter_it', op: 'lte', value: 8, factor_id: 'measurement.outer_diameter_it' },
          then: { include_process_ids: ['process_grind_outer'], exclude_process_ids: [], reason: '用户确认' },
          preview: '外圆尺寸精度 IT ≤ 8',
        },
        confidence: 0.95,
        issues: [],
        field_registry_version: '2026.07',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-21T02:00:00Z',
      },
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'confirmed_rules',
      routeVersionId: 3,
      cards: [finalizeItem(), card],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: [...baseConditionFields(), {
        key: 'precision.outer_diameter_it', label: '外圆尺寸精度 IT', category: '尺寸精度', type: 'number',
        operators: ['lte'], aliases: ['外圆精度'], required: false, source: 'CAD', options: [], allow_custom: true,
        unit: null, validation: { min: 1, max: 18 },
      }],
      standardFactors: factors,
    })

    const userRule = request.rules!.find(rule => rule.source === 'user_confirmed')!
    expect(userRule.priority).toBeGreaterThan(100)
    expect(userRule.when).toEqual({ field: 'precision.outer_diameter_it', op: 'lte', value: 8, factor_id: 'measurement.outer_diameter_it' })
    expect(userRule.source_segment_id).toBe('process_grind_outer')
    expect(request.fields.some(field => field.key === 'precision.outer_diameter_it')).toBe(true)
    expect(request.processes.find(process => process.process_id === 'process_grind_outer')?.main).toBe(false)
  })

  it('keeps fields from Pydantic condition nodes that include null branch keys', () => {
    const sourceText = '当零件存在孔类结构并且精度要求满足时，纳入钻孔工序'
    const card = {
      ...finalizeItem({ id: 'process_drill', sequence: 30, normalized_step_name: '钻孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'a'.repeat(64),
        status: 'confirmed',
        candidate: {
          kind: 'condition',
          when: {
            all: [
              { all: null, any: null, not: null, field: 'cad.features', op: 'contains', value: '普通孔/辅助孔', factor_id: 'feature.standard_or_aux_hole' },
              { all: null, any: null, not: null, field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
            ],
            any: null,
            not: null,
            field: null,
            op: null,
            value: null,
          },
          then: { include_process_ids: ['process_drill'], exclude_process_ids: [], reason: '用户确认' },
          preview: '孔类特征 且 精度/表面要求集合包含孔精加工',
        },
        confirmed: {
          kind: 'condition',
          when: {
            all: [
              { all: null, any: null, not: null, field: 'cad.features', op: 'contains', value: '普通孔/辅助孔', factor_id: 'feature.standard_or_aux_hole' },
              { all: null, any: null, not: null, field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
            ],
            any: null,
            not: null,
            field: null,
            op: null,
            value: null,
          },
          then: { include_process_ids: ['process_drill'], exclude_process_ids: [], reason: '用户确认' },
          preview: '孔类特征 且 精度/表面要求集合包含孔精加工',
        },
        confidence: 0.9,
        issues: [],
        field_registry_version: '2026.10',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-27T05:00:00Z',
      },
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'compound_null_keys',
      routeVersionId: 3,
      cards: [finalizeItem(), card],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.map(field => field.key)).toContain('precision.grades')
    expect(request.rules!.find(rule => rule.source_segment_id === 'process_drill')?.when).toEqual({
      all: [
        { field: 'cad.features', op: 'contains', value: '普通孔/辅助孔', factor_id: 'feature.standard_or_aux_hole' },
        { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
      ],
    })
  })

  it('writes a confirmed process relation into the V2 compile request', () => {
    const sourceText = '前面存在淬火工序，就出现烧伤检查'
    const relationCard = {
      ...finalizeItem({
        id: 'process_burn_inspect',
        sequence: 30,
        normalized_step_name: '烧伤检查',
        doc_coverage: { total_docs: 3, hit_docs: 1 },
      }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'b'.repeat(64),
        status: 'confirmed',
        candidate: {
          kind: 'process_relation',
          relation: {
            relation_type: 'trigger_after',
            source_process_ids: ['process_quench'],
            target_process_ids: ['process_burn_inspect'],
            source_match: 'any',
          },
          preview: '淬火进入路线 → 纳入烧伤检查，并排在淬火之后',
        },
        confirmed: {
          kind: 'process_relation',
          relation: {
            relation_type: 'trigger_after',
            source_process_ids: ['process_quench'],
            target_process_ids: ['process_burn_inspect'],
            source_match: 'any',
          },
          preview: '淬火进入路线 → 纳入烧伤检查，并排在淬火之后',
        },
        confidence: 0.9,
        issues: [],
        field_registry_version: '2026.07',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-21T02:00:00Z',
      },
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'relation_rules',
      routeVersionId: 3,
      cards: [
        finalizeItem(),
        finalizeItem({ id: 'process_quench', sequence: 20, normalized_step_name: '淬火' }),
        relationCard,
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.process_relations).toEqual([expect.objectContaining({
      relation_id: 'relation.process_burn_inspect',
      relation_type: 'trigger_after',
      source_process_ids: ['process_quench'],
      target_process_ids: ['process_burn_inspect'],
      source: 'user_confirmed',
    })])
  })

  it('converts a reviewed legacy Bool requirement into the existing special requirement', () => {
    const sourceText = '当零件需要追溯、编号或批次标识时，安排标记工序'
    const card = {
      ...finalizeItem({ id: 'process_mark', sequence: 30, normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'c'.repeat(64),
        status: 'confirmed',
        candidate: {
          kind: 'condition',
          when: { field: 'custom.requirements.traceability_marking_required', op: 'eq', value: true },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [], reason: '用户审核' },
          field_definitions: [{
            key: 'custom.requirements.traceability_marking_required',
            label: '是否需要追溯标识',
            category: '特殊要求',
            type: 'boolean',
            operators: ['eq', 'neq'],
            aliases: ['追溯', '编号', '批次标识'],
            source: '人工补充/图样技术要求',
            options: [],
            allow_custom: false,
          }],
          preview: '是否需要追溯标识 等于 是',
        },
        confirmed: {
          kind: 'condition',
          when: { field: 'custom.requirements.traceability_marking_required', op: 'eq', value: true },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [], reason: '用户审核' },
          field_definitions: [{
            key: 'custom.requirements.traceability_marking_required',
            label: '是否需要追溯标识',
            category: '特殊要求',
            type: 'boolean',
            operators: ['eq', 'neq'],
            aliases: ['追溯', '编号', '批次标识'],
            source: '人工补充/图样技术要求',
            options: [],
            allow_custom: false,
          }],
          preview: '是否需要追溯标识 等于 是',
        },
        confidence: 0.9,
        issues: [],
        field_registry_version: '2026.08',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-21T02:00:00Z',
      },
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'boolean_requirement_rules',
      routeVersionId: 3,
      cards: [finalizeItem(), card],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.some(field => field.key === 'custom.requirements.traceability_marking_required')).toBe(false)
    const specialRequirements = request.fields.find(field => field.key === 'special.requirements')
    expect(specialRequirements?.options?.map(option => option.value)).toContain('追溯标印')
    expect(specialRequirements?.options?.map(option => option.value)).toEqual(['追溯标印'])
    expect(request.rules?.some(rule => rule.rule_id === 'special.追溯标印')).toBe(false)
    expect(request.rules?.find(rule => rule.source === 'user_confirmed')?.when).toEqual({
      field: 'special.requirements', op: 'contains', value: '追溯标印', factor_id: 'requirement.traceability_marking',
    })
  })

  it('clarifies the generic IT field when a specific dimensional IT field is also required', () => {
    const sourceText = '尺寸精度达到 IT7 时，纳入精加工工序'
    const genericItCard = {
      ...finalizeItem({ id: 'process_finish', sequence: 30, normalized_step_name: '精加工', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'd'.repeat(64),
        status: 'confirmed',
        candidate: {
          when: { field: 'precision.dimension_it', op: 'lte', value: 7, factor_id: 'measurement.dimension_it' },
          then: { include_process_ids: ['process_finish'], exclude_process_ids: [], reason: '用户审核' },
          preview: '尺寸精度 IT ≤ 7',
        },
        confirmed: {
          when: { field: 'precision.dimension_it', op: 'lte', value: 7, factor_id: 'measurement.dimension_it' },
          then: { include_process_ids: ['process_finish'], exclude_process_ids: [], reason: '用户审核' },
          preview: '尺寸精度 IT ≤ 7',
        },
        confidence: 0.9,
        issues: [],
        field_registry_version: '2026.08',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-21T02:00:00Z',
      },
    }
    const innerItCard = {
      ...finalizeItem({ id: 'process_hone', sequence: 40, normalized_step_name: '珩孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '内孔尺寸精度达到 IT5 时，纳入珩孔工序',
      edited: true,
      conditionReview: {
        source_text: '内孔尺寸精度达到 IT5 时，纳入珩孔工序',
        source_hash: 'e'.repeat(64),
        status: 'confirmed',
        candidate: {
          when: { field: 'precision.inner_diameter_it', op: 'lte', value: 5, factor_id: 'measurement.inner_diameter_it' },
          then: { include_process_ids: ['process_hone'], exclude_process_ids: [], reason: '用户审核' },
          preview: '内孔尺寸精度 IT ≤ 5',
        },
        confirmed: {
          when: { field: 'precision.inner_diameter_it', op: 'lte', value: 5, factor_id: 'measurement.inner_diameter_it' },
          then: { include_process_ids: ['process_hone'], exclude_process_ids: [], reason: '用户审核' },
          preview: '内孔尺寸精度 IT ≤ 5',
        },
        confidence: 0.9,
        issues: [],
        field_registry_version: '2026.08',
        confirmed_by: '测试用户',
        confirmed_at: '2026-07-21T02:00:00Z',
      },
    }
    const conditionFields = [
      {
        key: 'precision.dimension_it', label: '尺寸精度 IT', category: '尺寸精度', type: 'number' as const,
        operators: ['lte'], aliases: ['尺寸精度'], required: false, source: 'CAD/PLM', options: [], allow_custom: true,
        unit: null, validation: { min: 1, max: 18 },
      },
      {
        key: 'precision.inner_diameter_it', label: '内孔尺寸精度 IT', category: '尺寸精度', type: 'number' as const,
        operators: ['lte'], aliases: ['内孔精度'], required: false, source: 'CAD/PLM', options: [], allow_custom: true,
        unit: null, validation: { min: 1, max: 18 },
      },
    ]
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'clarified_dimension_it',
      routeVersionId: 3,
      cards: [genericItCard, innerItCard],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: [...baseConditionFields(), ...conditionFields],
      standardFactors: factors,
    })

    expect(request.fields.find(field => field.key === 'precision.dimension_it')?.label).toBe('其他尺寸精度 IT')
    expect(request.fields.find(field => field.key === 'precision.inner_diameter_it')?.label).toBe('内孔尺寸精度 IT')
    expect(request.rules?.find(rule => rule.source === 'user_confirmed' && 'field' in rule.when)?.when).toEqual({
      field: 'precision.dimension_it', op: 'lte', value: 7, factor_id: 'measurement.dimension_it',
    })
  })

  it('adds a bound catalog feature value to the exported input options', () => {
    const sourceText = '当零件存在顶尖孔时，安排研顶尖孔工序'
    const card = {
      ...finalizeItem({ id: 'process_center_hole', sequence: 30, normalized_step_name: '研顶尖孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'f'.repeat(64),
        status: 'confirmed',
        candidate: {
          kind: 'condition',
          when: { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
          then: { include_process_ids: ['process_center_hole'], exclude_process_ids: [], reason: '用户审核' },
          preview: 'CAD 特征集合 包含 顶尖孔',
        },
        confirmed: {
          kind: 'condition',
          when: { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
          then: { include_process_ids: ['process_center_hole'], exclude_process_ids: [], reason: '用户审核' },
          preview: 'CAD 特征集合 包含 顶尖孔',
        },
        confidence: 0.65,
        issues: [],
        field_registry_version: '2026.09',
        confirmed_by: '规则包整体审核',
        confirmed_at: '2026-07-23T02:00:00Z',
      },
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'custom_feature_tag',
      routeVersionId: 3,
      cards: [finalizeItem(), card],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.find(field => field.key === 'cad.features')?.options).toContainEqual({
      value: '顶尖孔', label: '顶尖孔',
    })
  })

  it('derives material options from final rules and suppresses covered static rules', () => {
    const materialCondition = '当材料牌号为9Cr18时，纳入当前工序。'
    const confirmedRule = (segmentId: string, processId: string) => ({
      source_text: materialCondition,
      source_hash: '1'.repeat(64),
      status: 'confirmed',
      candidate: {
        kind: 'condition',
        when: { field: 'material.grade', op: 'eq', value: '9Cr18', factor_id: 'material.grade' },
        then: { include_process_ids: [processId], exclude_process_ids: [], reason: '用户审核' },
        preview: '材料牌号 等于 9Cr18',
      },
      confirmed: {
        kind: 'condition',
        when: { field: 'material.grade', op: 'eq', value: '9Cr18', factor_id: 'material.grade' },
        then: { include_process_ids: [processId], exclude_process_ids: [], reason: '用户审核' },
        preview: '材料牌号 等于 9Cr18',
      },
      confidence: 0.9,
      issues: [],
      field_registry_version: '2026.09',
      confirmed_by: '规则包整体审核',
      confirmed_at: '2026-07-23T02:00:00Z',
      segmentId,
    })
    const temperCard = {
      ...finalizeItem({ id: 'process_temper', sequence: 20, normalized_step_name: '调质', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: materialCondition,
      edited: true,
      conditionReview: confirmedRule('process_temper', 'process_temper'),
    }
    const quenchCard = {
      ...finalizeItem({ id: 'process_quench', sequence: 30, normalized_step_name: '淬火', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: materialCondition,
      edited: true,
      conditionReview: confirmedRule('process_quench', 'process_quench'),
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'dynamic_material_inputs',
      routeVersionId: 3,
      cards: [finalizeItem(), temperCard, quenchCard],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'heat_treatment',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields().map((field: any) => field.key === 'material.grade'
        ? {
            ...field,
            options: [
              { value: '9Cr18', label: '9Cr18' },
              { value: '95Cr18', label: '95Cr18' },
              { value: '4Cr14Ni14W2Mo', label: '4Cr14Ni14W2Mo' },
              { value: '6061', label: '6061' },
            ],
          }
        : field),
      standardFactors: factors,
    })

    const materialField = request.fields.find(field => field.key === 'material.grade')
    expect(materialField?.options?.map(option => option.value)).toEqual(['9Cr18'])
    expect(request.rules?.some(rule => rule.rule_id === 'material.9Cr18.heat')).toBe(false)
  })

  it('merges all user-authored values for the same bound standard factor', () => {
    const fieldKey = 'material.grade'
    const dynamicCard = (processId: string, processName: string, value: string, sequence: number) => {
      const sourceText = `当材料类别为${value}时，纳入${processName}工序`
      return {
        ...finalizeItem({ id: processId, sequence, normalized_step_name: processName, doc_coverage: { total_docs: 3, hit_docs: 1 } }),
        conditionText: sourceText,
        edited: true,
        conditionReview: {
          source_text: sourceText,
          source_hash: String(sequence).repeat(64).slice(0, 64),
          status: 'confirmed',
          candidate: {
            kind: 'condition',
            when: { field: fieldKey, op: 'eq', value, factor_id: 'material.grade' },
            then: { include_process_ids: [processId], exclude_process_ids: [], reason: '用户审核' },
            field_definitions: [{
              key: fieldKey,
              label: '材料牌号',
              category: '材料',
              type: 'single_select',
              operators: ['eq', 'neq', 'in'],
              aliases: [],
              source: 'CAD/PLM',
              options: [{ value, label: value }],
              allow_custom: true,
            }],
            preview: `材料牌号 等于 ${value}`,
          },
          confirmed: {
            kind: 'condition',
            when: { field: fieldKey, op: 'eq', value, factor_id: 'material.grade' },
            then: { include_process_ids: [processId], exclude_process_ids: [], reason: '用户审核' },
            field_definitions: [{
              key: fieldKey,
              label: '材料牌号',
              category: '材料',
              type: 'single_select',
              operators: ['eq', 'neq', 'in'],
              aliases: [],
              source: 'CAD/PLM',
              options: [{ value, label: value }],
              allow_custom: true,
            }],
            preview: `材料牌号 等于 ${value}`,
          },
          confidence: 0.9,
          issues: [],
          field_registry_version: '2026.09',
          confirmed_by: '规则包整体审核',
          confirmed_at: '2026-07-24T02:00:00Z',
        },
      }
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'dynamic_material_categories',
      routeVersionId: 3,
      cards: [
        finalizeItem(),
        dynamicCard('process_nitriding', '渗氮', '9Cr18', 20),
        dynamicCard('process_solution', '固溶处理', '95Cr18', 30),
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'heat_treatment',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
      standardFactors: factors,
    })

    expect(request.fields.find(field => field.key === fieldKey)).toEqual(expect.objectContaining({
      label: '材料牌号',
      type: 'single_select',
      allow_custom: true,
      options: [
        { value: '9Cr18', label: '9Cr18' },
        { value: '95Cr18', label: '95Cr18' },
      ],
    }))
  })
})
