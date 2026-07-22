import { describe, expect, it } from 'vitest'

import {
  buildCompileRequestFromCards,
  buildV2InputFields,
  finalizeRuleMode,
  hasCurrentConfirmedUserRule,
  isActionableConditionText,
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
      ...finalizeItem({ id: 'process_mark', normalized_step_name: '标记', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当零件需要追溯、编号或批次标识时，安排标记工序',
      factorNames: [],
    })).toBe('conditional')
    expect(finalizeRuleMode({
      ...finalizeItem({ id: 'process_copper', normalized_step_name: '镀铜', doc_coverage: { total_docs: 3, hit_docs: 1 } }),
      conditionText: '当防护、防腐蚀、绝缘或表面稳定性要求满足时，安排镀铜工序',
      factorNames: [],
    })).toBe('conditional')
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

  it('builds four-slot V2 fields and stable process catalog', () => {
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

    expect(request.fields.map(field => field.key)).toEqual([
      'material.grade',
      'cad.features',
      'precision.grades',
      'special.requirements',
    ])
    expect(request.processes.some(item => item.process_id === 'process_quench')).toBe(true)
    expect(request.processes.some(item => item.main)).toBe(true)
    expect(request.rules!.length).toBeGreaterThan(0)
    expect(request.test_cases).toHaveLength(1)
    expect(request.test_cases![0]!.case_id).toBe('default-smoke')
    expect(request.test_cases![0]!.expect.included_process_ids!.length).toBeGreaterThan(0)
    expect(request.test_cases![0]!.input).toEqual({
      material: { grade: '9Cr18' },
      cad: { features: ['扁位/平面'] },
      precision: { grades: ['孔精加工'] },
      special: { requirements: ['渗氮层要求'] },
    })
    expect(buildV2InputFields(baseConditionFields())[0]!.type).toBe('single_select')
  })

  it('includes nondestructive testing as a special requirement and maps it to the normalized process', () => {
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'ndt_rules',
      routeVersionId: 3,
      cards: [finalizeItem({ id: 'process_ndt', sequence: 30, normalized_step_name: '无损检查' })],
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
      rule_id: 'special.无损检测要求',
      when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' },
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
    })

    expect(request.processes).toEqual([expect.objectContaining({ process_id: 'process_clean', main: true })])
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
    expect(request.processes.find(process => process.process_id === 'process_grind_outer')?.main).toBe(false)
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
    expect(specialRequirements?.options?.map(option => option.value)).toEqual(expect.arrayContaining([
      '渗氮层要求',
      '磁粉检查要求',
    ]))
    expect(request.rules?.some(rule => rule.rule_id === 'special.追溯标印')).toBe(true)
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
    expect(request.rules?.find(rule => rule.source === 'user_confirmed' && 'field' in rule.when)?.when).toEqual({
      field: 'precision.dimension_it', op: 'lte', value: 7,
    })
  })
})
