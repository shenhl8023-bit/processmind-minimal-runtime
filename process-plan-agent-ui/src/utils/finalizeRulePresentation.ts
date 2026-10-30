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

export function formatProcessConfiguration(
  configuration: import('@/api/rulePackages').ProcessConfiguration,
  fields: CanonicalConditionField[],
  processes: Array<{ process_id: string; display_name: string }>,
): string {
  const name = (id: string) => processes.find(process => process.process_id === id)?.display_name || id
  const current = name(configuration.process_id)
  const triggers = configuration.relations.filter(relation => relation.relation_type === 'trigger_after')
  const parts: string[] = []
  if (configuration.occurrence === 'always') parts.push('始终出现（主工序）')
  else {
    if (configuration.when) parts.push(formatRuleCondition(configuration.when, fields))
    triggers.forEach(relation => {
      const sources = relation.source_process_ids.map(name).join('、')
      const match = relation.source_process_ids.length > 1 ? (relation.source_match === 'any' ? '任一' : '全部') : ''
      parts.push(match + sources + '出现后，生成' + current + '并排在其后')
    })
    if (!parts.length) parts.push('判断条件待补充')
  }
  const appearance = configuration.occurrence === 'conditional' && parts.length > 1
    ? '全部满足：' + parts.join('；') : parts.join('；')
  const independent = configuration.relations.filter(relation => relation.relation_type !== 'trigger_after').map(relation => {
    const sources = relation.source_process_ids.map(name).join('、')
    const targets = relation.target_process_ids.map(name).join('、')
    if (relation.relation_type === 'order_after') return '两者均出现时，' + targets + '排在' + sources + '之后'
    if (relation.relation_type === 'requires') return targets + '出现时，必须先安排' + sources
    return sources + '与' + targets + '不能同时出现'
  })
  return [appearance, ...independent].join('；')
}
