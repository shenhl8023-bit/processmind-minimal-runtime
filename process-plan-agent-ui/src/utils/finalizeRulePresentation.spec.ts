import { describe, expect, it } from 'vitest'
import { formatRuleCondition, nextPendingSegmentId } from './finalizeRulePresentation'
const fields: any[] = [
  { key: 'precision', label: '精度', type: 'number', unit: 'mm' },
  { key: 'material', label: '材料', options: [{ value: 'steel', label: '钢' }] },
  { key: 'manual', label: '是否需要检验', type: 'boolean' },
]
describe('finalize readable decisions', () => {
  it('renders the current nested AST with field labels, units, options and negation', () => {
    expect(formatRuleCondition({ all: [
      { field: 'precision', op: 'between', value: [1, 3] },
      { any: [{ field: 'material', op: 'eq', value: 'steel' }, { not: { field: 'manual', op: 'eq', value: true } }] },
    ] }, fields)).toBe('同时满足（精度 介于 1 至 3 mm；满足任一（材料 等于 钢；不满足（是否需要检验 等于 是）））')
  })
  it('shows existence without an undefined value and preserves unknown field names', () => {
    expect(formatRuleCondition({ field: 'custom', op: 'exists' }, fields)).toBe('custom 存在')
  })
  it('accepts serialized leaf conditions whose unused union branches are null', () => {
    expect(formatRuleCondition({ all: null, any: null, not: null, field: 'manual', op: 'eq', value: true } as any, fields)).toBe('是否需要检验 等于 是')
  })
  it('finds the next pending card in route order, wraps and handles an empty queue', () => {
    const cards = ['a', 'b', 'c', 'd'].map(id => ({ segment: { id } }))
    expect(nextPendingSegmentId(cards, [cards[0]!, cards[3]!], 'b')).toBe('d')
    expect(nextPendingSegmentId(cards, [cards[0]!], 'd')).toBe('a')
    expect(nextPendingSegmentId(cards, [], 'a')).toBe('')
  })
})
