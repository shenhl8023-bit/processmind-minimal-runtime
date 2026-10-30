import { describe, expect, it } from 'vitest'
import { buildCompileRequestFromCards, buildManualBooleanRuleCandidate } from './finalizeRulePackage'

function sample(when: any, field: any, caseId = 'rule-user.finish') {
  const text = '当指定条件满足时，安排精整工序'
  const card = {
    segment: { id: 'finish', normalized_step_name: '精整', sequence: 20, doc_coverage: { total_docs: 2, hit_docs: 1 } },
    conditionText: text, edited: true, factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [], systemFactorLabels: [],
    conditionReview: { status: 'confirmed', source_text: text, confirmed: {
      kind: 'condition', when, then: { include_process_ids: ['finish'] }, field_definitions: [field],
    } },
  }
  const request = buildCompileRequestFromCards({
    projectId: 1, packageName: 'sample-regression', cards: [card],
    displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [],
    conditionFields: [],
  })
  return (request.test_cases!.find(test => test.case_id === caseId)!.input as any).project_factor.value
}

const numberField = { key: 'project_factor.value', label: '尺寸', category: '项目', type: 'number', operators: ['gt', 'lt', 'between'], validation: { min: 0, max: 1 } }
const leaf = (op: string, value: any) => ({ field: 'project_factor.value', op, value })
const optionalChoice = { key: 'project_factor.value', label: '类别', category: '项目', type: 'single_select', operators: ['eq', 'neq', 'exists'], required: false, allow_custom: false, options: ['A', 'B', 'C'].map(value => ({ value, label: value })) }

describe('finalized rule sample witnesses', () => {
  it.each([false, true])('keeps a positive collection member alongside exists, reversed=%s', reversed => {
    const conditions = [leaf('contains', 'B'), leaf('exists', undefined)]
    const value = sample({ all: reversed ? conditions.reverse() : conditions }, { ...optionalChoice, type: 'multi_select', required: true, operators: ['contains', 'exists'] })
    expect(value).toContain('B')
    expect(value.every((item: string) => ['A', 'B', 'C'].includes(item))).toBe(true)
  })

  it.each([false, true])('keeps a required enum value alongside exists, reversed=%s', reversed => {
    const conditions = [leaf('eq', 'B'), leaf('exists', undefined)]
    expect(sample({ all: reversed ? conditions.reverse() : conditions }, optionalChoice)).toBe('B')
  })

  it.each([false, true])('finds an allowed enum value outside all exclusions, reversed=%s', reversed => {
    const conditions = [leaf('neq', 'A'), leaf('neq', 'B')]
    expect(sample({ all: reversed ? conditions.reverse() : conditions }, optionalChoice)).toBe('C')
  })

  it.each(['single_select', 'number', 'boolean'])('keeps an explicit absent value for negated exists on %s', type => {
    const field = { ...optionalChoice, type, operators: ['exists'], options: type === 'single_select' ? optionalChoice.options : [] }
    // Backend NOT treats a missing-field trace as false. Null is absent but
    // explicitly supplied, so NOT(exists) can truthfully cover the rule.
    expect(sample({ not: leaf('exists', undefined) }, field)).toBeNull()
  })

  it('does not add an opposite action to a saved false-valued manual field condition', () => {
    const text = '当用户选择否时，安排精整工序'
    const card: any = { segment: { id: 'finish', normalized_step_name: '精整', sequence: 20, doc_coverage: { total_docs: 2, hit_docs: 1 } }, conditionText: text, edited: true, factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [], systemFactorLabels: [] }
    const confirmed = buildManualBooleanRuleCandidate(card, '是否精整')
    if (confirmed.when && 'value' in confirmed.when) confirmed.when.value = false
    card.conditionReview = { status: 'confirmed', source_text: text, confirmed }
    const request = buildCompileRequestFromCards({ projectId: 1, packageName: 'false-manual', cards: [card], displayName: segment => segment.normalized_step_name, phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], conditionFields: [] })
    const rules = (request.rules || []).filter(rule => rule.source === 'user_confirmed')
    expect(rules).toHaveLength(1)
    expect(rules[0]!.when).toMatchObject({ value: false })
    expect(rules[0]!.then.include_process_ids).toEqual(['finish'])
    expect(rules[0]!.then.exclude_process_ids).toEqual([])
  })
  it('keeps the default smoke collection within declared length bounds', () => {
    const field = { key: 'project_factor.value', label: '要求', category: '项目', type: 'multi_select', operators: ['contains'], allow_custom: false, validation: { min_length: 2, max_length: 2 }, options: ['A', 'B', 'C'].map(value => ({ value, label: value })) }
    expect(sample(leaf('contains', 'A'), field, 'default-smoke')).toEqual(['A', 'B'])
  })
  it('finds a strict numeric witness inside the declared maximum', () => {
    const value = sample(leaf('gt', 0.9), numberField)
    expect(value).toBeGreaterThan(0.9)
    expect(value).toBeLessThanOrEqual(1)
  })

  it.each([false, true])('satisfies both sides of a narrow numeric interval, reversed=%s', reversed => {
    const conditions = [leaf('gt', 0), leaf('lt', 0.5)]
    const value = sample({ all: reversed ? conditions.reverse() : conditions }, numberField)
    expect(value).toBeGreaterThan(0)
    expect(value).toBeLessThan(0.5)
  })

  it('tries the next any branch when the first contradicts a sibling condition', () => {
    const field = { key: 'project_factor.value', label: '类别', category: '项目', type: 'single_select', operators: ['eq', 'neq'], allow_custom: false, options: [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }] }
    const value = sample({ all: [{ any: [leaf('eq', 'A'), leaf('eq', 'B')] }, leaf('neq', 'A')] }, field)
    expect(value).toBe('B')
  })

  it('does not let a later any group overwrite a required sibling value', () => {
    const field = { key: 'project_factor.value', label: '类别', category: '项目', type: 'single_select', operators: ['eq'], allow_custom: false, options: [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }] }
    const value = sample({ all: [leaf('eq', 'B'), { any: [leaf('eq', 'A'), leaf('eq', 'B')] }] }, field)
    expect(value).toBe('B')
  })

  it('chooses a satisfiable negated-all branch after an earlier positive sibling', () => {
    const field = { key: 'project_factor.value', label: '要求', category: '项目', type: 'multi_select', operators: ['contains'], allow_custom: false, options: [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }] }
    const value = sample({ all: [leaf('contains', 'A'), { not: { all: [leaf('contains', 'A'), leaf('contains', 'B')] } }] }, field)
    expect(value).toContain('A')
    expect(value).not.toContain('B')
  })

  it('backtracks a negated all group when its first choice contradicts a sibling', () => {
    const field = { key: 'project_factor.value', label: '要求', category: '项目', type: 'multi_select', operators: ['contains'], allow_custom: false, options: [{ value: 'A', label: 'A' }, { value: 'B', label: 'B' }] }
    const value = sample({ all: [{ not: { all: [leaf('contains', 'A'), leaf('contains', 'B')] } }, leaf('contains', 'A')] }, field)
    expect(value).toContain('A')
    expect(value).not.toContain('B')
  })

  it('fills a legal collection to its minimum length without reintroducing an excluded option', () => {
    const field = { key: 'project_factor.value', label: '要求', category: '项目', type: 'multi_select', operators: ['contains'], allow_custom: false, validation: { min_length: 2 }, options: ['A', 'B', 'C'].map(value => ({ value, label: value })) }
    const value = sample({ not: leaf('contains', 'B') }, field)
    expect(value).toHaveLength(2)
    expect(value).not.toContain('B')
    expect(value.every((item: string) => ['A', 'C'].includes(item))).toBe(true)
  })

  it('chooses only one contains-any option when the collection maximum is one', () => {
    const field = { key: 'project_factor.value', label: '要求', category: '项目', type: 'multi_select', operators: ['contains_any'], allow_custom: false, validation: { max_length: 1 }, options: ['A', 'B'].map(value => ({ value, label: value })) }
    const value = sample(leaf('contains_any', ['A', 'B']), field)
    expect(value).toHaveLength(1)
    expect(['A', 'B']).toContain(value[0])
  })
})
