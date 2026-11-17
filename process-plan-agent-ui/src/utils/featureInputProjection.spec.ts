import { describe, expect, it } from 'vitest'
import { lowerFeatureInputs, featureInputScope } from './featureInputProjection'
import type { RulePackageInputField, RulePackageCondition } from '@/api/rulePackages'
import sharedProjectionCases from '../../../process-plan-agent-api/tests/fixtures/shared_feature_projection.json'
import { buildSharedFeatureCompileCases } from './__fixtures__/sharedFeatureCompile'
import actualCompileCases from '../../../process-plan-agent-api/tests/fixtures/shared_feature_compile_requests.json'

const scope = 'project_factor.operation_drill'
function fixture() {
  const fields: RulePackageInputField[] = [
    { key: `${scope}.features`, label: '加工对象的特征', type: 'multi_select', options: ['孔(通孔)', '孔(盲孔)', '内圆柱面'].map(value => ({ value, label: value })) },
    { key: `${scope}.direction`, label: '方位', type: 'single_select', options: ['A侧', 'B侧', '中间', '周边', '所有方位'].map(value => ({ value, label: value })) },
    { key: `${scope}.it`, label: '实际精度', type: 'number', unit: 'IT', validation: { min: 5, max: 10 } },
  ]
  return { fields, rules: [], processConfigurations: [{ process_id: 'drill', occurrence: 'conditional' as const, when: { all: [
    { field: `${scope}.features`, op: 'contains_any', value: ['孔(通孔)', '孔(盲孔)'] },
    { field: `${scope}.direction`, op: 'eq', value: 'A侧' },
    { field: `${scope}.it`, op: 'lte', value: 7 },
  ] } as RulePackageCondition, relations: [] }] }
}
// Evaluate the standard output contract, independent of the lowering algorithm.
function matches(node: RulePackageCondition, facts: Record<string, any>): boolean {
  if ('all' in node) return node.all.every(child => matches(child, facts))
  if ('any' in node) return node.any.some(child => matches(child, facts))
  if ('not' in node) return !matches(node.not, facts)
  const actual = facts[node.field]
  if (actual === undefined) return false
  if (node.op === 'eq') return actual === node.value
  if (node.op === 'in') return (node.value as any[]).includes(actual)
  if (node.op === 'lte') return actual <= Number(node.value)
  if (node.op === 'contains_any') return (node.value as any[]).some(value => actual.includes(value))
  return false
}

describe('shared feature inputs in the executable package', () => {
  it('keeps real question/editor compiler requests in sync with API integration cases', () => {
    expect(buildSharedFeatureCompileCases()).toEqual(actualCompileCases.cases)
  })
  it('normalizes compatible guided/editor IT ranges to the actual input domain without editing originals', () => {
    const fixture = buildSharedFeatureCompileCases().find(test => test.id === 'mixed-guided-editor-it')!
    const field = fixture.request.fields.find(field => field.key === `${featureInputScope('孔(通孔)')}.it`)!
    expect(field.validation).toEqual({ min: 5, max: 10 })
    expect(fixture.cards.map(card => card.conditionReview.confirmed.field_definitions.find((field: any) => field.key.endsWith('.it')).validation)).toEqual([
      { min: 1, max: 18 }, { min: -1, max: 18 },
    ])
  })
  it.each(sharedProjectionCases.cases)('keeps the cross-language projection contract: $id', ({ input, expected }) => {
    expect(lowerFeatureInputs(input as unknown as Parameters<typeof lowerFeatureInputs>[0])).toEqual(expected)
  })
  it('keeps direction and precision on the same selected feature', () => {
    const result = lowerFeatureInputs(fixture())
    const through = featureInputScope('孔(通孔)'), blind = featureInputScope('孔(盲孔)')
    expect(result.fields.map(f => f.key)).not.toContain(`${scope}.it`)
    expect(result.fields.some(f => f.label.includes('内圆柱面'))).toBe(false)
    const when = result.processConfigurations[0]!.when!
    const facts = { [`${through}.present`]: true, [`${through}.direction`]: 'A侧', [`${through}.it`]: 9,
      [`${blind}.present`]: true, [`${blind}.direction`]: 'B侧', [`${blind}.it`]: 6 }
    expect(matches(when, facts)).toBe(false)
    expect(matches(when, { ...facts, [`${through}.it`]: 7 })).toBe(true)
    expect(matches(when, { ...facts, [`${blind}.direction`]: 'A侧' })).toBe(true)
    expect(matches(when, { ...facts, [`${through}.present`]: false, [`${blind}.present`]: false })).toBe(false)
  })
  it('shares one actual requirement while preserving separate operation thresholds', () => {
    const input = fixture(), next = 'project_factor.operation_grind'
    input.fields.push(...input.fields.map(f => ({ ...f, key: f.key.replace(scope, next) })))
    input.processConfigurations.push({ process_id: 'grind', occurrence: 'conditional', relations: [], when: { all: [
      { field: `${next}.features`, op: 'contains_any', value: ['孔(通孔)'] },
      { field: `${next}.it`, op: 'lte', value: 6 },
    ] } })
    const result = lowerFeatureInputs(input), through = featureInputScope('孔(通孔)')
    expect(result.fields.filter(f => f.key === `${through}.it`)).toHaveLength(1)
    const facts = { [`${through}.present`]: true, [`${through}.direction`]: 'A侧', [`${through}.it`]: 7 }
    expect(matches(result.processConfigurations[0]!.when!, facts)).toBe(true)
    expect(matches(result.processConfigurations[1]!.when!, facts)).toBe(false)
    expect(input.fields.map(f => f.key)).toContain(`${scope}.it`)
  })
  it('preserves A/B alternatives and lets the actual two-side choice satisfy A or B', () => {
    const input = fixture()
    input.processConfigurations[0]!.when = { all: [
      { field: `${scope}.features`, op: 'contains_any', value: ['孔(通孔)'] },
      { any: ['A侧', 'B侧'].map(value => ({ field: `${scope}.direction`, op: 'eq', value })) },
    ] }
    const result = lowerFeatureInputs(input), through = featureInputScope('孔(通孔)')
    const when = result.processConfigurations[0]!.when!
    for (const direction of ['A侧', 'B侧', '所有方位']) expect(matches(when, { [`${through}.present`]: true, [`${through}.direction`]: direction })).toBe(true)
    for (const direction of ['中间', '周边']) expect(matches(when, { [`${through}.present`]: true, [`${through}.direction`]: direction })).toBe(false)
  })
  it('retains legacy precision-only and custom negated rules without guessing feature identity', () => {
    const input = fixture()
    input.processConfigurations[0]!.when = { field: `${scope}.it`, op: 'lte', value: 7 }
    expect(lowerFeatureInputs(input).processConfigurations).toEqual(input.processConfigurations)
    expect(lowerFeatureInputs(input).fields.some(f => f.key === `${scope}.it`)).toBe(true)
  })
  it('unions the frozen direction options of the same feature across operations', () => {
    const input = fixture(), other = 'project_factor.operation_grind'
    input.fields.find(f => f.key.endsWith('.direction'))!.options = [{ value: 'A侧', label: 'A侧' }]
    input.fields.push(...input.fields.map(f => ({ ...f, key: f.key.replace(scope, other), ...(f.key.endsWith('.direction') ? { options: [{ value: 'B侧', label: 'B侧' }] } : {}) })))
    input.processConfigurations.push({ ...input.processConfigurations[0]!, process_id: 'grind', when: { all: [
      { field: `${other}.features`, op: 'contains_any', value: ['孔(通孔)'] },
      { field: `${other}.direction`, op: 'eq', value: 'B侧' },
    ] } })
    const result = lowerFeatureInputs(input)
    expect(result.fields.find(f => f.key === `${featureInputScope('孔(通孔)')}.direction`)!.options!.map(o => o.value)).toEqual(['A侧', 'B侧'])
    expect(input.fields.find(f => f.key === `${scope}.direction`)!.options).toHaveLength(1)
  })
  it('lowers actual backend JSON with nulls on inactive condition branches', () => {
    const input = fixture()
    const serialized = (node: RulePackageCondition): any => 'field' in node
      ? { all: null, any: null, not: null, ...node }
      : 'all' in node ? { any: null, not: null, field: null, op: null, value: null, all: node.all.map(serialized) } : node
    input.processConfigurations[0]!.when = serialized(input.processConfigurations[0]!.when!)
    const result = lowerFeatureInputs(input)
    expect(result.fields.filter(field => field.key.endsWith('.present'))).toHaveLength(2)
    expect(matches(result.processConfigurations[0]!.when!, { [`${featureInputScope('孔(通孔)')}.present`]: true, [`${featureInputScope('孔(通孔)')}.direction`]: 'A侧', [`${featureInputScope('孔(通孔)')}.it`]: 7 })).toBe(true)
  })
  it('preserves multiple feature predicates instead of silently intersecting their options', () => {
    const input = fixture()
    input.processConfigurations[0]!.when = { all: [
      { field: `${scope}.features`, op: 'contains_any', value: ['孔(通孔)', '孔(盲孔)'] },
      { field: `${scope}.features`, op: 'contains_any', value: ['孔(通孔)', '内圆柱面'] },
    ] }
    expect(lowerFeatureInputs(input).processConfigurations).toEqual(input.processConfigurations)
  })
})
