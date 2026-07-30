import { describe, expect, it } from 'vitest'

import type {
  RuleConditionCandidate,
  StandardFactorDefinition,
} from '@/api/rulePackages'
import {
  applyStandardFactor,
  factorBindingState,
  filterStandardFactors,
  matchingStandardFactors,
  ruleConfirmationSignature,
  withConditionValue,
} from './standardFactorBindings'

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
  {
    factor_id: 'measurement.hardness_hrc',
    label: '目标硬度 HRC',
    category: '性能要求',
    source_field: 'mechanical.hardness_hrc',
    source_field_aliases: ['target_hardness_hrc'],
    canonical_value: null,
    allowed_operators: ['eq', 'gte', 'lte', 'between'],
    kmai_factor_key: 'mechanical_hardness_hrc',
    kmai_value_mode: 'condition_value',
    runtime_source: 'manual_override',
  },
]

function conditionCandidate(overrides: Partial<RuleConditionCandidate> = {}): RuleConditionCandidate {
  return {
    kind: 'condition',
    when: {
      field: 'precision.grades',
      op: 'contains',
      value: '孔精加工',
      factor_id: 'precision.hole_finish',
    },
    then: {
      include_process_ids: ['process_hone'],
      exclude_process_ids: [],
      reason: '用户确认',
    },
    preview: '孔精加工 → 珩孔',
    ...overrides,
  }
}

describe('standard factor bindings', () => {
  it('matches canonical semantics and read-only legacy aliases exactly', () => {
    expect(matchingStandardFactors({
      field: 'cad.features', op: 'contains', value: '  顶尖孔\u3000',
    }, factors).map(item => item.factor_id)).toEqual(['feature.center_hole_location'])
    expect(matchingStandardFactors({
      field: 'target_hardness_hrc', op: 'gte', value: 58,
    }, factors).map(item => item.factor_id)).toEqual(['measurement.hardness_hrc'])
    expect(matchingStandardFactors({
      field: 'cad.features', op: 'contains', value: '顶尖孔定位',
    }, factors)).toEqual([])
  })

  it('marks every leaf of a compound condition independently', () => {
    const state = factorBindingState({ all: [
      { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
      { field: 'precision.grades', op: 'contains', value: '未知精加工' },
    ] }, factors)

    expect(state.complete).toBe(false)
    expect(state.ambiguous).toBe(false)
    expect(state.issues).toEqual([expect.objectContaining({
      code: 'factor_unbound',
      path: 'all[1]',
    })])
    expect(state.selected.map(item => item.factor.factor_id)).toEqual(['feature.center_hole_location'])
  })

  it('requires a unique matching id while accepting explicit manual Boolean leaves', () => {
    const duplicate = { ...factors[0]!, factor_id: 'feature.center_hole_location.duplicate' }
    expect(factorBindingState({
      field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location',
    }, [...factors, duplicate])).toEqual(expect.objectContaining({ complete: false, ambiguous: true }))
    expect(factorBindingState({
      field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'precision.hole_finish',
    }, factors).issues[0]?.code).toBe('factor_mismatch')
    expect(factorBindingState({
      field: 'project_factor.manual_process_deadbeef', op: 'eq', value: false,
    }, factors)).toEqual(expect.objectContaining({ complete: true, ambiguous: false, issues: [] }))
  })

  it('replacing a factor writes canonical semantics and condition edits clear it', () => {
    expect(applyStandardFactor(
      { field: 'precision.grades', op: 'contains', value: '未知值' },
      factors.find(item => item.factor_id === 'precision.hole_finish')!,
    )).toEqual({
      field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
    })
    expect(applyStandardFactor(
      { field: 'target_hardness_hrc', op: 'contains', value: 58 },
      factors.find(item => item.factor_id === 'measurement.hardness_hrc')!,
    )).toEqual({
      field: 'mechanical.hardness_hrc', op: 'eq', value: 58, factor_id: 'measurement.hardness_hrc',
    })
    expect(withConditionValue(
      { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
      '珩孔要求',
    )).not.toHaveProperty('factor_id')
  })

  it.each(['顶尖孔', '精度要求', 'feature.center_hole_location'])(
    'finds the Chinese-first factor catalog entry by %s',
    (query) => {
      expect(filterStandardFactors(factors, query).map(item => item.factor_id))
        .toContain('feature.center_hole_location')
    },
  )

  it('changes confirmation signatures for semantic edits but not object-key order', () => {
    const sourceText = '当存在孔精加工要求时，纳入珩孔工序'
    const version = '2026.11'
    const original = conditionCandidate()
    const baseline = ruleConfirmationSignature(original, sourceText, version)
    const reordered = {
      preview: original.preview,
      then: {
        reason: original.then?.reason,
        exclude_process_ids: original.then?.exclude_process_ids,
        include_process_ids: original.then?.include_process_ids,
      },
      when: {
        factor_id: 'precision.hole_finish',
        value: '孔精加工',
        op: 'contains',
        field: 'precision.grades',
      },
      kind: 'condition' as const,
    }

    expect(ruleConfirmationSignature(reordered, sourceText, version)).toBe(baseline)
    expect(ruleConfirmationSignature(conditionCandidate({
      when: { field: 'precision.grades', op: 'contains', value: '珩孔要求', factor_id: 'precision.honing' },
    }), sourceText, version)).not.toBe(baseline)
    expect(ruleConfirmationSignature(conditionCandidate({
      then: { include_process_ids: ['process_grind'], exclude_process_ids: [], reason: '用户确认' },
    }), sourceText, version)).not.toBe(baseline)
    expect(ruleConfirmationSignature(conditionCandidate({
      when: { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'feature.center_hole_location' },
    }), sourceText, version)).not.toBe(baseline)

    const relation = {
      kind: 'process_relation' as const,
      relation: {
        relation_type: 'trigger_after' as const,
        source_process_ids: ['process_quench'],
        target_process_ids: ['process_burn_inspect'],
        source_match: 'any' as const,
      },
      preview: '淬火后烧伤检查',
    }
    expect(ruleConfirmationSignature({
      ...relation,
      relation: { ...relation.relation, target_process_ids: ['process_ndt'] },
    }, sourceText, version)).not.toBe(ruleConfirmationSignature(relation, sourceText, version))
  })
})
