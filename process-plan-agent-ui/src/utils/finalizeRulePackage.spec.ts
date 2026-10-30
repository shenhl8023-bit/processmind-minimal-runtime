import { describe, expect, it } from 'vitest'

import {
  buildCompileRequestFromCards,
  blockedExportPrimaryActionLabel,
  buildManualBooleanRuleCandidate,
  exportBlockedReason,
  exportBlockingCards,
  exportBlockedReasonLabel,
  groupExportBlockedCards,
  finalizeRuleMode,
  hasCurrentConfirmedUserRule,
  isActionableConditionText,
  isExplicitMainlineInstruction,
  isSafeForBatchRuleConfirmation,
  manualRuleModeActionState,
  requiresManualRuleAttention,
  requiresServerRuleConditionRefresh,
} from './finalizeRulePackage'
import { nestFactorValues } from '@/composables/useGenerateInputFields'


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


describe('V2 compile DTO from finalize cards', () => {
  it.each(['contains', 'contains_any', 'contains_all'])('keeps positive collection requirements when adding a negative %s test', (op) => {
    const text = '当有A要求且没有B要求时，安排当前工序'
    const key = 'special.requirements'
    const positive = { field: key, op: 'contains', value: 'A要求' }
    const negative = { not: { field: key, op, value: op === 'contains' ? 'B要求' : ['A要求', 'B要求'].slice(op === 'contains_any' ? 1 : 0) } }
    const card = { ...finalizeItem({ id: 'process_finish', normalized_step_name: '精整', doc_coverage: { total_docs: 3, hit_docs: 1 } }), conditionText: text, edited: true, conditionReview: { status: 'confirmed', source_text: text, confirmed: { kind: 'condition', when: { all: [positive, negative] }, then: { include_process_ids: ['process_finish'] } } } }
    const fields = baseConditionFields().map((field: any) => field.key === key ? { ...field, options: [{ value: 'A要求', label: 'A要求' }, { value: 'B要求', label: 'B要求' }] } : field)
    const request = buildCompileRequestFromCards({ projectId: 12, packageName: 'collection-conjunction', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: fields })
    const sample = request.test_cases!.find(test => test.case_id !== 'default-smoke')!.input as any
    expect(sample.special.requirements).toContain('A要求')
    expect(sample.special.requirements).not.toContain('B要求')
  })
  it.each([false, true])('builds conjunction samples independently of negative clause order: %s', (negativeFirst) => {
    const key = 'special.requirements'
    const text = '当没有同时要求A和B且有B要求时，安排当前工序'
    const negative = { not: { field: key, op: 'contains_all', value: ['A要求', 'B要求'] } }
    const positive = { field: key, op: 'contains', value: 'B要求' }
    const card = { ...finalizeItem({ id: 'process_finish', normalized_step_name: '精整', doc_coverage: { total_docs: 3, hit_docs: 1 } }), conditionText: text, edited: true, conditionReview: { status: 'confirmed', source_text: text, confirmed: { kind: 'condition', when: { all: negativeFirst ? [negative, positive] : [positive, negative] }, then: { include_process_ids: ['process_finish'] } } } }
    const fields = baseConditionFields().map((field: any) => field.key === key ? { ...field, options: [{ value: 'A要求', label: 'A要求' }, { value: 'B要求', label: 'B要求' }] } : field)
    const request = buildCompileRequestFromCards({ projectId: 12, packageName: 'negative-first', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: fields })
    const sample = request.test_cases!.find(test => test.case_id !== 'default-smoke')!.input as any
    expect(sample.special.requirements).toEqual(['B要求'])
  })

  it.each([['special.requirements', false], ['cad.features', true]])('builds a valid negative collection case for %s', (key, required) => {
    const text = '当零件不包含指定要求时，安排当前工序'
    const value = key === 'special.requirements' ? '无损检测要求' : '扁位/平面'
    const card = { ...finalizeItem({ id: 'process_finish', normalized_step_name: '精整', doc_coverage: { total_docs: 3, hit_docs: 1 } }), conditionText: text, edited: true, conditionReview: { status: 'confirmed', source_text: text, confirmed: { kind: 'condition', when: { not: { field: key, op: 'contains', value } }, then: { include_process_ids: ['process_finish'] } } } }
    const request = buildCompileRequestFromCards({ projectId: 12, packageName: 'negative-collection', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: baseConditionFields() })
    const field = request.fields.find(field => field.key === key)!
    const sample = request.test_cases!.find(test => test.case_id !== 'default-smoke')!.input
    const [category, name] = key.split('.')
    const values = (sample as any)[category!][name!] as string[]
    expect(values).not.toContain(value)
    expect(values.every(item => field.options?.some(option => option.value === item))).toBe(true)
    if (required) expect(values.length).toBeGreaterThan(0)
  })

  it.each([
    ['eq', true, false], ['eq', false, true],
    ['neq', true, true], ['neq', false, false],
  ])('preserves legacy requirement polarity for %s %s', (op, value, negated) => {
    const field = { key: 'custom.requirements.traceability_marking_required', label: '是否需要追溯标识', category: '特殊要求', type: 'boolean', operators: ['eq', 'neq'], options: [] }
    const text = '当零件有标识条件时，安排标记工序'
    const card = { ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }), edited: true, conditionText: text, conditionReview: { status: 'confirmed', source_text: text, confirmed: { kind: 'condition', when: { field: field.key, op, value }, then: { include_process_ids: ['process_mark'] }, field_definitions: [field] } } }
    const request = buildCompileRequestFromCards({ projectId: 12, packageName: 'legacy-polarity', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: baseConditionFields() })
    const leaf = { field: 'special.requirements', op: 'contains', value: '追溯标印' }
    expect(request.rules?.find(rule => rule.source === 'user_confirmed')?.when).toEqual(negated ? { not: leaf } : leaf)
  })

  it.each(['single_select', 'multi_select'])('preserves the full confirmed legacy %s definition', (type) => {
    const field = { key: 'project_factor.surface_class', label: '表面类别', category: '项目', type, operators: [type === 'single_select' ? 'eq' : 'contains'], options: [{ value: 'A', label: 'A类' }, { value: 'B', label: 'B类' }], allow_custom: true }
    const text = '当表面类别为A时，安排当前工序'
    const card = { ...finalizeItem({ id: 'process_finish', normalized_step_name: '精整', doc_coverage: { total_docs: 3, hit_docs: 1 } }), edited: true, conditionText: text, conditionReview: { status: 'confirmed', source_text: text, confirmed: { kind: 'condition', when: { field: field.key, op: field.operators[0], value: 'A' }, then: { include_process_ids: ['process_finish'] }, field_definitions: [field] } } }
    const request = buildCompileRequestFromCards({ projectId: 12, packageName: 'legacy-definition', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: baseConditionFields() })
    expect(request.fields.find(item => item.key === field.key)?.options).toEqual(field.options)
    expect(request.factor_dictionary?.fields.find(item => item.key === field.key)?.options).toEqual(field.options)
  })

  it.each([
    '不得设置为主工序，应当按材料牌号决定。',
    '设置为主工序，仅当材料牌号为9Cr18时纳入。',
    '设置为主工序，始终纳入“淬火”工序，但仅在有要求时保留。',
    '如果客户需要，把该工序改为主线工序。',
    '此工序不属于必经工序。',
    '固定为主工序，默认保留。后续按条件排除。',
  ])('requires confirmation for qualified or negated mainline text: %s', (conditionText) => {
    const card = {
      ...finalizeItem({ id: 'process_quench', normalized_step_name: '淬火' }),
      conditionText,
      edited: true,
    }
    expect(isExplicitMainlineInstruction(conditionText, '淬火')).toBe(false)
    expect(finalizeRuleMode(card)).not.toBe('mainline')
    expect(exportBlockingCards([card])).toEqual([card])
  })

  it('only accepts the canonical mainline instruction for the current process', () => {
    const conditionText = '设置为主工序，始终纳入“淬火”工序。'
    expect(isExplicitMainlineInstruction(conditionText, '淬火')).toBe(true)
    expect(isExplicitMainlineInstruction(conditionText, '除铜')).toBe(false)
    expect(isExplicitMainlineInstruction(conditionText)).toBe(false)
    const otherProcess = {
      ...finalizeItem({ id: 'process_remove_copper', normalized_step_name: '除铜' }),
      conditionText,
      edited: true,
    }
    expect(finalizeRuleMode(otherProcess)).not.toBe('mainline')
    expect(exportBlockingCards([otherProcess])).toEqual([otherProcess])
  })

  it.each([
    ['真空淬火', '淬火'],
    ['标印', '标记'],
    ['车削加工（第1次）', '车削加工（A侧）'],
  ])('matches canonical mainline names using route display aliases: %s', (routeName, displayName) => {
    const conditionText = `设置为主工序，始终纳入“${displayName}”工序。`
    expect(isExplicitMainlineInstruction(conditionText, routeName)).toBe(true)
    expect(finalizeRuleMode({
      ...finalizeItem({ normalized_step_name: routeName }), conditionText, edited: true,
    })).toBe('mainline')
  })

  it.each([
    '设置为主工序，始终纳入“淬火”工序',
    '将其设置为主工序，始终保留在路线中',
    '把该工序改为主线工序',
    '作为基础工序无条件进入路线',
    '此工序属于必经工序',
    '固定为主工序，默认保留',
  ])('accepts entire known mainline instructions with optional surrounding whitespace and one period: %s', (text) => {
    expect(isExplicitMainlineInstruction(` \n${text}\t `, '淬火')).toBe(true)
    expect(isExplicitMainlineInstruction(` \n${text}。\t `, '淬火')).toBe(true)
    expect(isExplicitMainlineInstruction(`${text}。。`, '淬火')).toBe(false)
  })

  it.each([
    '前面出现镀铜时，安排除铜',
    '设置为主工序，始终保留',
    '根据不同结构类型决定是否安排该工序',
  ])('honors the saved manual switch instead of interpreting its label: %s', (label) => {
    const card: any = {
      ...finalizeItem({ id: 'process_remove_copper', normalized_step_name: '除铜' }),
      conditionText: `当用户选择“${label}”为是时，纳入“除铜”工序。`,
      edited: true,
    }
    const candidate = buildManualBooleanRuleCandidate(card, label)
    card.conditionReview = {
      source_text: card.conditionText, status: 'confirmed',
      confirmed: candidate, candidate, confirmed_by: '用户直接设定',
      confirmed_at: '2026-10-27T02:00:00Z',
    }

    expect(finalizeRuleMode(card)).toBe('conditional')
    expect(hasCurrentConfirmedUserRule(card)).toBe(true)
    expect(manualRuleModeActionState(card, false).booleanActive).toBe(true)
    expect(exportBlockingCards([card])).toEqual([])
    const request = buildCompileRequestFromCards({
      projectId: 12, packageName: 'manual_switch', cards: [card],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'surface_treatment', primarySteps: () => [], attachedSteps: () => [],
    })
    expect(request.processes[0]?.main).toBe(false)
    expect(request.process_relations).toEqual([])
    const fieldKey = candidate.field_definitions?.[0]?.key
    expect(request.rules?.map(rule => rule.when)).toEqual([
      { field: fieldKey, op: 'eq', value: true },
      { field: fieldKey, op: 'eq', value: false },
    ])

    card.conditionText = '前面出现镀铜时，安排除铜'
    expect(finalizeRuleMode(card)).toBe('relation')
    expect(hasCurrentConfirmedUserRule(card)).toBe(false)
  })

  it('requires re-review when the confirmed rule kind no longer matches the user text', () => {
    const relationCard: any = {
      ...finalizeItem({ id: 'process_ndt', normalized_step_name: '无损检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '淬火工序之后设置该工序',
      factorNames: [],
      conditionReview: {
        source_text: '淬火工序之后设置该工序',
        status: 'confirmed',
        confirmed: {
          kind: 'condition',
          when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' },
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
          when: { field: 'special.requirements', op: 'contains', value: '追溯标印' },
          then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
        },
      },
    }

    expect(isSafeForBatchRuleConfirmation(item)).toBe(true)
    item.conditionReview.confidence = 0.79
    expect(isSafeForBatchRuleConfirmation(item)).toBe(false)
    item.conditionReview.confidence = 0.95
    item.conditionReview.issues = ['模型候选需要重点核对']
    expect(isSafeForBatchRuleConfirmation(item)).toBe(false)
    item.conditionReview.confidence = 0.65
    item.conditionReview.issues = [
      'AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。',
      '已使用内置规则解析器生成候选结果，请重点核对。',
    ]
    expect(isSafeForBatchRuleConfirmation(item)).toBe(true)
    item.conditionReview.issues = [
      '已使用内置规则解析器生成候选结果，请重点核对。',
      '条件无法可靠映射到标准字段，请补充字段、比较关系和阈值。',
    ]
    expect(isSafeForBatchRuleConfirmation(item)).toBe(false)
    item.conditionReview.issues = []
    item.conditionReview.source_text = '旧条件'
    expect(isSafeForBatchRuleConfirmation(item)).toBe(false)
  })

  it('keeps unsafe pending candidates visible in the pending filter', () => {
    const item: any = {
      ...finalizeItem({ id: 'process_drill', normalized_step_name: '钻孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当零件存在内孔时，纳入钻孔工序',
      factorNames: [],
      conditionReview: {
        source_text: '当零件存在内孔时，纳入钻孔工序',
        status: 'pending_confirmation',
        confidence: 0.75,
        issues: ['已忽略原文中的泛化模板描述，请重点核对具体结构条件。'],
        candidate: {
          kind: 'condition',
          when: { field: 'cad.features', op: 'contains', value: '普通孔/辅助孔' },
          then: { include_process_ids: ['process_drill'], exclude_process_ids: [] },
        },
      },
    }

    expect(requiresManualRuleAttention(item)).toBe(true)
    item.conditionReview.confidence = 0.9
    item.conditionReview.issues = []
    expect(requiresManualRuleAttention(item)).toBe(false)
  })

  it('only refreshes missing or stale candidates before batch confirmation', () => {
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

    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(false)
    pendingItem.conditionReview.source_text = '旧条件'
    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(true)
    pendingItem.conditionReview.source_text = pendingItem.conditionText
    pendingItem.conditionReview.candidate = null
    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(true)
    pendingItem.conditionReview.candidate = {
      kind: 'process_relation',
      relation: { relation_type: 'trigger_after', source_process_ids: ['a'], target_process_ids: ['process_mark'] },
    }
    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(true)
    pendingItem.conditionReview.candidate = {
      kind: 'condition',
      when: { field: 'special.requirements', op: 'contains', value: '追溯标印' },
      then: { include_process_ids: ['process_mark'], exclude_process_ids: [] },
    }
    pendingItem.conditionReview.status = 'confirmed'
    pendingItem.conditionReview.confirmed = pendingItem.conditionReview.candidate
    expect(requiresServerRuleConditionRefresh(pendingItem)).toBe(false)
  })

  it('classifies export blockers by the kind of remaining work', () => {
    const pendingCandidate: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当需要追溯标印时，安排标记工序',
      factorNames: [],
      conditionReview: {
        source_text: '当需要追溯标印时，安排标记工序',
        status: 'pending_confirmation',
        candidate: { kind: 'condition' },
      },
    }
    const missingCondition: any = {
      ...finalizeItem({ id: 'process_check', normalized_step_name: '检验', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当终检、入库或交付前综合检验点满足终检、入库或交付前综合检验点时，设置“检验”作为质量确认节点。',
      factorNames: [],
    }
    const rebuildRequired: any = {
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当需要追溯标印时，安排标记工序',
      factorNames: [],
      conditionReview: {
        source_text: '旧条件',
        status: 'pending_confirmation',
        candidate: { kind: 'condition' },
      },
    }

    expect(exportBlockedReason(pendingCandidate)).toBe('pending_candidate')
    expect(exportBlockedReasonLabel(pendingCandidate)).toBe('待审核候选')
    expect(exportBlockedReason(missingCondition)).toBe('missing_condition')
    expect(exportBlockedReasonLabel(missingCondition)).toBe('待补充条件')
    expect(exportBlockedReason(rebuildRequired)).toBe('rebuild_required')
    expect(exportBlockedReasonLabel(rebuildRequired)).toBe('需要重新识别')

    expect(groupExportBlockedCards([pendingCandidate, missingCondition, rebuildRequired])).toEqual({
      pendingCandidateCards: [pendingCandidate],
      missingConditionCards: [missingCondition],
      rebuildRequiredCards: [rebuildRequired],
      total: 3,
    })
    expect(blockedExportPrimaryActionLabel([pendingCandidate])).toBe('去确认规则')
    expect(blockedExportPrimaryActionLabel([missingCondition])).toBe('去处理待补充项')
    expect(blockedExportPrimaryActionLabel([rebuildRequired])).toBe('去处理首项')
  })

  it('blocks publishing for every pending candidate including high confidence rules', () => {
    const candidate = {
      ...finalizeItem({ id: 'process_slot', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当零件存在槽时，纳入铣槽工序',
      factorNames: [],
      conditionReview: {
        status: 'pending_confirmation',
        source_text: '当零件存在槽时，纳入铣槽工序',
        candidate: { kind: 'condition', when: { field: 'cad.features', op: 'contains', value: '槽' } },
      },
    }
    const unresolved = {
      ...finalizeItem({ id: 'process_ambiguous', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '根据不同结构类型决定是否安排该工序',
      factorNames: [],
    }
    const stale = {
      ...candidate,
      conditionReview: { ...candidate.conditionReview, source_text: '旧条件' },
    }
    const wrongKind = {
      ...candidate,
      conditionText: '淬火之后安排铣槽工序',
      conditionReview: {
        ...candidate.conditionReview,
        source_text: '淬火之后安排铣槽工序',
      },
    }

    expect(exportBlockingCards([candidate])).toEqual([candidate])
    expect(exportBlockingCards([candidate, unresolved, stale])).toEqual([candidate, unresolved, stale])
    expect(exportBlockingCards([wrongKind])).toEqual([wrongKind])
  })

  it('does not publish static rules for an unconfirmed candidate process', () => {
    const text = '当零件存在槽时，纳入铣槽工序'
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'pending_slot',
      routeVersionId: 3,
      cards: [
        finalizeItem(),
        {
          ...finalizeItem({ id: 'process_slot', normalized_step_name: '铣槽', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
          conditionText: text,
          factorNames: [],
          conditionReview: {
            status: 'pending_confirmation',
            source_text: text,
            candidate: { kind: 'condition', when: { field: 'cad.features', op: 'contains', value: '槽类特征' } },
          },
        },
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => [],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
    })

    expect(request.processes.map(process => process.process_id)).toContain('process_slot')
    expect(request.rules?.flatMap(rule => rule.then.include_process_ids || [])).not.toContain('process_slot')
  })

  it('keeps a candidate blocking when a confirmed rule explicitly includes its process', () => {
    const text = '当零件存在槽时，纳入铣槽工序'
    const pending = {
      ...finalizeItem({ id: 'process_slot', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: text,
      factorNames: [],
      conditionReview: {
        source_text: text,
        status: 'pending_confirmation',
        candidate: { kind: 'condition' },
      },
    }
    const confirmedText = '当材料为9Cr18时，纳入热处理和铣槽'
    const confirmed = {
      ...finalizeItem({ id: 'process_heat', normalized_step_name: '热处理', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: confirmedText,
      factorNames: [],
      conditionReview: {
        source_text: confirmedText,
        status: 'confirmed',
        confirmed: {
          kind: 'condition',
          when: { field: 'material.grade', op: 'eq', value: '9Cr18' },
          then: { include_process_ids: ['process_heat', 'process_slot'], exclude_process_ids: [] },
        },
      },
    }

    expect(exportBlockingCards([pending, confirmed])).toEqual([pending])
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
    })

    expect(request.fields.map(field => field.key)).toEqual([])
    expect(request.processes.some(item => item.process_id === 'quench-a')).toBe(true)
    expect(request.processes.some(item => item.main)).toBe(true)
    expect(request.rules).toEqual([])
    expect(request.test_cases).toHaveLength(1)
    expect(request.test_cases![0]!.case_id).toBe('default-smoke')
    expect(request.test_cases![0]!.expect.included_process_ids!.length).toBeGreaterThan(0)
    expect(request.test_cases![0]!.input).toEqual({})
  })

  it('exports all factor definitions separately from active rule inputs', () => {
    const geometryLength = {
      key: 'geometry.length_mm',
      label: '特征长度',
      category: '几何尺寸',
      type: 'number',
      operators: ['eq', 'gt', 'gte', 'lt', 'lte', 'between'],
      aliases: ['长度'],
      source: 'CAD',
      options: [],
      allow_custom: false,
      unit: 'mm',
    }
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'factor_dictionary',
      routeVersionId: 3,
      cards: [finalizeItem()],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: [...baseConditionFields(), geometryLength],
    })

    expect(request.fields.map(field => field.key)).toEqual([])
    expect(request.factor_dictionary.fields.map(field => field.key)).toContain('geometry.length_mm')
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
          confirmed: {
            kind: 'condition',
            when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' },
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
    })

    expect(request.fields.find(field => field.key === 'special.requirements')?.options).toContainEqual({
      value: '无损检测要求', label: '无损检测要求',
    })
    expect(request.rules).toContainEqual(expect.objectContaining({
      rule_id: 'user.process_ndt',
      when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' },
      then: expect.objectContaining({ include_process_ids: ['process_ndt'] }),
    }))
    expect(request.test_cases).toContainEqual(expect.objectContaining({
      input: { special: { requirements: ['无损检测要求'] } },
      expect: { included_process_ids: ['process_ndt'], excluded_process_ids: [] },
    }))
  })

  it('merges repeated collection-field leaves when generating a positive rule test case', () => {
    const sourceText = '当存在通孔、盲孔或一般孔结构需求，以及零件存在内孔、通孔或中心孔时，纳入打孔工序'
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'merged_feature_test_case',
      routeVersionId: 3,
      cards: [{
        ...finalizeItem({ id: 'process_drill', sequence: 30, normalized_step_name: '打孔', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
        conditionText: sourceText,
        factorNames: [],
        edited: true,
        conditionReview: {
          source_text: sourceText,
          status: 'confirmed',
          confirmed: {
            kind: 'condition',
            when: {
              all: [
                { field: 'cad.features', op: 'contains', value: '普通孔/辅助孔' },
                { field: 'cad.features', op: 'contains_any', value: ['顶尖孔', '普通孔/辅助孔'] },
              ],
            },
            then: { include_process_ids: ['process_drill'], exclude_process_ids: [] },
          },
          confidence: 0.9,
          issues: [],
          field_registry_version: '2026.09',
          confirmed_by: '测试用户',
          confirmed_at: '2026-07-21T02:00:00Z',
        },
      }],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => [],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
    })

    expect(request.test_cases).toContainEqual(expect.objectContaining({
      input: { cad: { features: ['普通孔/辅助孔', '顶尖孔'] } },
      expect: { included_process_ids: ['process_drill'], excluded_process_ids: [] },
    }))
  })

  it('keeps generated test case IDs unique when rule IDs collapse to the same safe slug', () => {
    const ndtText = '当零件有无损检测要求时，安排无损检查工序'
    const markText = '当零件需要追溯、编号或批次标识时，安排标记工序'
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'case_id_collision',
      routeVersionId: 3,
      cards: [
        finalizeItem(),
        {
          ...finalizeItem({ id: 'special#1', sequence: 30, normalized_step_name: '无损检查', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
          conditionText: ndtText,
          edited: true,
          conditionReview: {
            source_text: ndtText,
            status: 'confirmed',
            confirmed: {
              kind: 'condition',
              when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' },
              then: { include_process_ids: ['process_ndt'], exclude_process_ids: [], reason: '用户审核' },
              preview: '特殊要求 包含 无损检测要求',
            },
            confidence: 0.9,
            issues: [],
            field_registry_version: '2026.08',
            confirmed_by: '测试用户',
            confirmed_at: '2026-07-21T02:00:00Z',
          },
        },
        {
          ...finalizeItem({ id: 'special@1', sequence: 40, normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
          conditionText: markText,
          edited: true,
          conditionReview: {
            source_text: markText,
            status: 'confirmed',
            confirmed: {
              kind: 'condition',
              when: { field: 'special.requirements', op: 'contains', value: '追溯标印' },
              then: { include_process_ids: ['process_mark'], exclude_process_ids: [], reason: '用户审核' },
              preview: '特殊要求 包含 追溯标印',
            },
            confidence: 0.9,
            issues: [],
            field_registry_version: '2026.08',
            confirmed_by: '测试用户',
            confirmed_at: '2026-07-21T02:00:00Z',
          },
        },
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
    })

    const caseIds = request.test_cases!.map(testCase => testCase.case_id)
    expect(caseIds).toContain('default-smoke')
    expect(caseIds).toContain('rule-user.special_1')
    expect(caseIds).toContain('rule-user.special_1-2')
    expect(new Set(caseIds).size).toBe(caseIds.length)
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
          source_operation_ids: [80],
          template_group_aliases: [{
            source_operation_id: 80,
            alias: '钻孔（A侧/孔）',
            template_group_id: 'grp_blind_hole',
            template_group_key: 'grp_blind_hole',
            template_group_name: '孔',
            template_group_path: ['A侧', '孔'],
            feature_selections: ['孔(盲孔)'],
          }],
        }),
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['钻孔'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
    })

    const process = request.processes[0]!
    expect(process.display_name).toBe('钻孔')
    expect(process.source_operation_ids).toEqual([80])
    expect(process.template_group_aliases).toEqual([{
      source_operation_id: 80,
      alias: '钻孔（A侧/孔）',
      template_group_id: 'grp_blind_hole',
      template_group_key: 'grp_blind_hole',
      template_group_name: '孔',
      template_group_path: ['A侧', '孔'],
      feature_selections: ['孔(盲孔)'],
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
        candidate: null,
        confirmed: {
          when: { field: 'precision.outer_diameter_it', op: 'lte', value: 8 },
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
    })

    const userRule = request.rules!.find(rule => rule.source === 'user_confirmed')!
    expect(userRule.priority).toBeGreaterThan(100)
    expect(userRule.when).toEqual({ field: 'precision.outer_diameter_it', op: 'lte', value: 8 })
    expect(userRule.source_segment_id).toBe('process_grind_outer')
    expect(request.fields.some(field => field.key === 'precision.outer_diameter_it')).toBe(true)
    expect(request.fields.find(field => field.key === 'precision.outer_diameter_it')?.validation).toEqual({ min: 5, max: 10 })
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
        candidate: null,
        confirmed: {
          kind: 'condition',
          when: {
            all: [
              { all: null, any: null, not: null, field: 'cad.features', op: 'contains', value: '孔类特征' },
              { all: null, any: null, not: null, field: 'precision.grades', op: 'contains', value: '孔精加工' },
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
    })

    expect(request.fields.map(field => field.key)).toContain('precision.grades')
    expect(request.rules!.find(rule => rule.source_segment_id === 'process_drill')?.when).toEqual({
      all: [
        { field: 'cad.features', op: 'contains', value: '孔类特征' },
        { field: 'precision.grades', op: 'contains', value: '孔精加工' },
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
        candidate: null,
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
        candidate: null,
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
    })

    expect(request.fields.some(field => field.key === 'custom.requirements.traceability_marking_required')).toBe(false)
    const specialRequirements = request.fields.find(field => field.key === 'special.requirements')
    expect(specialRequirements?.options?.map(option => option.value)).toContain('追溯标印')
    expect(specialRequirements?.options?.map(option => option.value)).toEqual(['追溯标印'])
    expect(request.rules?.some(rule => rule.rule_id === 'special.追溯标印')).toBe(false)
    expect(request.rules?.find(rule => rule.source === 'user_confirmed')?.when).toEqual({
      field: 'special.requirements', op: 'contains', value: '追溯标印',
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
        candidate: null,
        confirmed: {
          when: { field: 'precision.dimension_it', op: 'lte', value: 7 },
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
        candidate: null,
        confirmed: {
          when: { field: 'precision.inner_diameter_it', op: 'lte', value: 5 },
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
    })

    expect(request.fields.find(field => field.key === 'precision.dimension_it')?.label).toBe('其他尺寸精度 IT')
    expect(request.fields.find(field => field.key === 'precision.inner_diameter_it')?.label).toBe('内孔尺寸精度 IT')
    expect(request.fields.find(field => field.key === 'precision.dimension_it')?.validation).toEqual({ min: 5, max: 10 })
    expect(request.fields.find(field => field.key === 'precision.inner_diameter_it')?.validation).toEqual({ min: 5, max: 10 })
    expect(request.rules?.find(rule => rule.source === 'user_confirmed' && 'field' in rule.when)?.when).toEqual({
      field: 'precision.dimension_it', op: 'lte', value: 7,
    })
  })

  it('adds user-authored feature tags to the exported input options', () => {
    const sourceText = '当零件存在异形凸台结构时，安排铣凸台工序'
    const card = {
      ...finalizeItem({ id: 'process_mill_boss', sequence: 30, normalized_step_name: '铣凸台', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: sourceText,
      edited: true,
      conditionReview: {
        source_text: sourceText,
        source_hash: 'f'.repeat(64),
        status: 'confirmed',
        confirmed: {
          kind: 'condition',
          when: { field: 'cad.features', op: 'contains', value: '异形凸台' },
          then: { include_process_ids: ['process_mill_boss'], exclude_process_ids: [], reason: '用户审核' },
          preview: 'CAD 特征集合 包含 异形凸台',
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
    })

    expect(request.fields.find(field => field.key === 'cad.features')?.options).toContainEqual({
      value: '异形凸台', label: '异形凸台',
    })
  })

  it('derives material options from final rules and suppresses covered static rules', () => {
    const materialCondition = '当材料牌号为9Cr18时，纳入当前工序。'
    const confirmedRule = (segmentId: string, processId: string) => ({
      source_text: materialCondition,
      source_hash: '1'.repeat(64),
      status: 'confirmed',
      confirmed: {
        kind: 'condition',
        when: { field: 'material.grade', op: 'eq', value: '9Cr18' },
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
    })

    const materialField = request.fields.find(field => field.key === 'material.grade')
    expect(materialField?.options?.map(option => option.value)).toEqual(['9Cr18'])
    expect(request.rules?.some(rule => rule.rule_id === 'material.9Cr18.heat')).toBe(false)
  })

  it('merges all user-authored values for the same project factor', () => {
    const fieldKey = 'project_factor.material_category'
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
          confirmed: {
            kind: 'condition',
            when: { field: fieldKey, op: 'eq', value },
            then: { include_process_ids: [processId], exclude_process_ids: [], reason: '用户审核' },
            field_definitions: [{
              key: fieldKey,
              label: '材料类别',
              category: '材料',
              type: 'single_select',
              operators: ['eq', 'neq', 'in'],
              aliases: [],
              source: '用户条件',
              options: [{ value, label: value }],
              allow_custom: true,
            }],
            preview: `材料类别 等于 ${value}`,
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
        dynamicCard('process_nitriding', '渗氮', '不锈钢', 20),
        dynamicCard('process_solution', '固溶处理', '高温合金', 30),
      ],
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'heat_treatment',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
      conditionFields: baseConditionFields(),
    })

    expect(request.fields.find(field => field.key === fieldKey)).toEqual(expect.objectContaining({
      label: '材料类别',
      type: 'single_select',
      allow_custom: true,
      options: [
        { value: '不锈钢', label: '不锈钢' },
        { value: '高温合金', label: '高温合金' },
      ],
    }))
  })
})

describe('atomic process configuration export', () => {
  function configured(occurrence: string, when: any, relations: any[] = [], definitions: any[] = []) {
    const card: any = { ...finalizeItem({ id: 'remove_copper', normalized_step_name: '除铜' }), conditionText: '全部样本中稳定出现', edited: true }
    const candidate = { kind: 'process_configuration', configuration: { process_id: 'remove_copper', occurrence, when, relations }, field_definitions: definitions, preview: '用户配置' }
    card.conditionReview = { source_text: card.conditionText, source_hash: 'configuration-hash', status: 'confirmed', confirmed: candidate, candidate, issues: [], confidence: 1, confirmed_by: '用户直接设定', confirmed_at: '2026-10-27T08:00:00Z' }
    return card
  }
  const compile = (cards: any[]) => buildCompileRequestFromCards({ projectId: 11, packageName: 'configuration-test', cards, displayName: segment => segment.normalized_step_name, phaseLabel: () => 'surface', primarySteps: () => [], attachedSteps: () => [], conditionFields: baseConditionFields() }) as any
  it('uses the saved configuration before coverage and prose heuristics', () => {
    const card = configured('conditional', { field: 'material.grade', op: 'eq', value: '4Cr14Ni14W2Mo' })
    expect(finalizeRuleMode(card)).toBe('conditional')
    expect(hasCurrentConfirmedUserRule(card)).toBe(true)
    expect(requiresManualRuleAttention(card)).toBe(false)
    expect(requiresServerRuleConditionRefresh(card)).toBe(false)
    expect(exportBlockingCards([card])).toEqual([])
  })
  it('exports condition and trigger rows atomically without a parallel include path', () => {
    const when = { all: [{ field: 'material.grade', op: 'eq', value: '4Cr14Ni14W2Mo' }, { not: { field: 'special.requirements', op: 'contains', value: '禁止除铜' } }] }
    const relations = [{ relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'all' }, { relation_type: 'order_after', source_process_ids: ['check'], target_process_ids: ['remove_copper'], source_match: 'any' }]
    const request = compile([configured('conditional', when, relations)])
    expect(request.process_configurations).toEqual([{ process_id: 'remove_copper', occurrence: 'conditional', when, relations, enabled: true, source: 'user_confirmed', source_segment_id: 'remove_copper', source_text: '全部样本中稳定出现', confirmed_by: '用户直接设定', confirmed_at: '2026-10-27T08:00:00Z' }])
    expect(request.processes[0].main).toBe(false)
    expect(request.rules.flatMap((rule: any) => rule.then.include_process_ids || [])).not.toContain('remove_copper')
    expect(request.process_relations).toEqual([])
    expect(request.fields.map((field: any) => field.key)).toEqual(['material.grade', 'special.requirements'])
    expect(request.fields[0].options).toContainEqual({ value: '4Cr14Ni14W2Mo', label: '4Cr14Ni14W2Mo' })
  })
  it('keeps a trigger-only conditional optional even with full sample coverage', () => {
    const request = compile([configured('conditional', null, [{ relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'all' }])])
    expect(request.processes[0].main).toBe(false)
    expect(request.process_configurations[0].when).toBeNull()
    expect(request.rules).toEqual([])
  })
  it('collects manual question definitions without creating legacy include rules', () => {
    const manual = buildManualBooleanRuleCandidate(finalizeItem({ id: 'remove_copper', normalized_step_name: '除铜' }), '是否需要除铜')
    const card = configured('manual', manual.when, [], manual.field_definitions)
    expect(manualRuleModeActionState(card, false).booleanActive).toBe(true)
    const request = compile([card])
    expect(request.fields).toHaveLength(1)
    expect(request.fields[0]).toMatchObject({ type: 'boolean', label: '是否需要除铜', source: '用户直接设定' })
    expect(request.process_configurations[0].occurrence).toBe('manual')
    expect(request.rules).toEqual([])
  })
  it('retains mainline ordering relations as an audited configuration', () => {
    const relations = [{ relation_type: 'order_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'], source_match: 'any' }]
    const request = compile([configured('always', null, relations)])
    expect(request.processes[0].main).toBe(true)
    expect(request.process_configurations[0].relations).toEqual(relations)
  })
  it.each([['single_select', 'eq'], ['multi_select', 'contains']])('preserves the confirmed %s options for arbitrary process configurations', (type, op) => {
    const definition = { key: 'project_factor.surface_class', label: '表面处理类别', category: '项目', type, operators: [op], options: [{ value: 'A', label: 'A类' }, { value: 'B', label: 'B类' }], allow_custom: true, source: '用户直接设定' }
    const card = configured('conditional', { field: definition.key, op, value: 'A' }, [], [definition])
    card.segment.id = 'custom_finishing_17'
    card.segment.normalized_step_name = '表面精整'
    card.conditionReview.confirmed.configuration.process_id = 'custom_finishing_17'
    const request = compile([card])
    expect(request.process_configurations[0].process_id).toBe('custom_finishing_17')
    expect(request.fields.find((field: any) => field.key === definition.key).options).toEqual([{ value: 'A', label: 'A类' }, { value: 'B', label: 'B类' }])
    expect(request.factor_dictionary.fields.find((field: any) => field.key === definition.key).options).toEqual([{ value: 'A', label: 'A类' }, { value: 'B', label: 'B类' }])
  })
  it('does not alter an authoritative field definition when a custom condition value is used', () => {
    const definition = { key: 'project_factor.surface_class', label: '表面处理类别', category: '项目', type: 'single_select', operators: ['eq'], options: [{ value: 'A', label: 'A类' }], allow_custom: true, source: '用户直接设定' }
    const request = compile([configured('conditional', { field: definition.key, op: 'eq', value: 'custom' }, [], [definition])])
    expect(request.fields.find((field: any) => field.key === definition.key).options).toEqual([{ value: 'A', label: 'A类' }])
    expect(request.factor_dictionary.fields.find((field: any) => field.key === definition.key).options).toEqual([{ value: 'A', label: 'A类' }])
  })
  it('keeps nonmatching registry options available for configuration inputs', () => {
    const fields = baseConditionFields()
    fields[0].allow_custom = false
    fields[0].options = [{ value: '9Cr18', label: '9Cr18' }, { value: 'other', label: '其他' }]
    const request = buildCompileRequestFromCards({ projectId: 11, packageName: 'generic-config', cards: [configured('conditional', { field: 'material.grade', op: 'eq', value: '9Cr18' })], displayName: segment => segment.normalized_step_name, phaseLabel: () => 'surface', primarySteps: () => [], attachedSteps: () => [], conditionFields: fields })
    expect(request.fields.find(field => field.key === 'material.grade')?.options).toEqual([{ value: '9Cr18', label: '9Cr18' }, { value: 'other', label: '其他' }])
  })
  it('removes unused requirement tags when another process uses a manual switch', () => {
    const manual = configured('manual', null)
    manual.segment.id = 'process_ndt'
    manual.segment.normalized_step_name = '无损检查'
    const definition = { key: 'project_factor.manual_process_ndt', label: '是否需要无损检查', category: '项目', type: 'boolean', operators: ['eq'], options: [], source: '用户直接设定' }
    manual.conditionReview.confirmed.configuration = { process_id: 'process_ndt', occurrence: 'manual', when: { field: definition.key, op: 'eq', value: true }, relations: [] }
    manual.conditionReview.confirmed.field_definitions = [definition]
    const request = compile([
      configured('conditional', { not: { field: 'special.requirements', op: 'contains', value: '禁止除铜' } }),
      manual,
    ])
    expect(request.fields.find((field: any) => field.key === 'special.requirements')?.options).toEqual([{ value: '禁止除铜', label: '禁止除铜' }])
    expect(request.fields.find((field: any) => field.key === definition.key)?.label).toBe('是否需要无损检查')
    expect(request.factor_dictionary.fields.find((field: any) => field.key === 'special.requirements')?.options).toEqual([{ value: '禁止除铜', label: '禁止除铜' }])
  })
  it('rejects confirmation recognition when configuration controls a different process', () => {
    const card = configured('conditional', { field: 'material.grade', op: 'eq', value: '9Cr18' })
    card.conditionReview.confirmed.configuration.process_id = 'another-process'
    expect(hasCurrentConfirmedUserRule(card)).toBe(false)
    expect(exportBlockingCards([card])).toEqual([card])
  })
})

it('includes configured conditions and relationships in the published rule document', async () => {
  const { buildRuleReportFromV2Package } = await import('./finalizeRulePackage')
  const report = buildRuleReportFromV2Package({ projectName: '测试', packageName: '规则', contentHash: 'hash', processes: [{ process_id: 'copper', display_name: '镀铜' }, { process_id: 'strip', display_name: '除铜' }], rules: [], processConfigurations: [{ process_id: 'strip', occurrence: 'conditional', when: { field: 'material.grade', op: 'eq', value: '9Cr18' }, relations: [{ relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['strip'], source_match: 'all' }] }], conditionFields: baseConditionFields() } as any)
  expect(report).toContain('工序规则配置：1')
  expect(report).toContain('材料牌号 等于 9Cr18')
  expect(report).toContain('镀铜出现后，生成除铜并排在其后')
})
