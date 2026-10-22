import type { CanonicalConditionField, RulePackageCondition } from '@/api/rulePackages'

const operatorLabels: Record<string, string> = {
  eq: '等于', ne: '不等于', neq: '不等于', in: '属于', not_in: '不属于',
  contains: '包含', contains_any: '包含任一', contains_all: '包含全部',
  gt: '大于', gte: '大于等于', lt: '小于', lte: '小于等于',
  between: '介于', exists: '存在', not_exists: '不存在',
}

export function formatRuleCondition(condition: RulePackageCondition | null | undefined, fields: CanonicalConditionField[]): string {
  if (!condition) return '判断条件待补充'
  if ('all' in condition && Array.isArray(condition.all)) return `同时满足（${condition.all.map(child => formatRuleCondition(child, fields)).join('；')}）`
  if ('any' in condition && Array.isArray(condition.any)) return `满足任一（${condition.any.map(child => formatRuleCondition(child, fields)).join('；')}）`
  if ('not' in condition && condition.not) return `不满足（${formatRuleCondition(condition.not, fields)}）`
  const leaf = condition as { field: string; op: string; value?: unknown }
  const field = fields.find(item => item.key === leaf.field)
  const prefix = `${field?.label || leaf.field} ${operatorLabels[leaf.op] || leaf.op}`
  if (['exists', 'not_exists'].includes(leaf.op)) return prefix
  const valueLabel = (value: unknown) => typeof value === 'boolean'
    ? (value ? '是' : '否')
    : field?.options?.find(option => option.value === String(value))?.label || String(value ?? '待填写')
  const value = Array.isArray(leaf.value)
    ? leaf.value.map(valueLabel).join(leaf.op === 'between' ? ' 至 ' : '、')
    : valueLabel(leaf.value)
  return `${prefix} ${value}${field?.unit ? ` ${field.unit}` : ''}`
}

export function nextPendingSegmentId(
  cards: { segment: { id: string } }[], pending: { segment: { id: string } }[], currentId: string,
) {
  const pendingIds = new Set(pending.map(item => item.segment.id))
  const index = cards.findIndex(item => item.segment.id === currentId)
  const ordered = [...cards.slice(index + 1), ...cards.slice(0, index + 1)]
  return ordered.find(item => pendingIds.has(item.segment.id))?.segment.id || ''
}
