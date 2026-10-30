import type { CanonicalConditionField, ProcessConfiguration, ProcessRelationCandidate, RuleConditionProcessOption, RulePackageCondition } from '@/api/rulePackages'
import { formatRuleCondition } from '@/utils/finalizeRulePresentation'

export function conditionIsComplete(condition: RulePackageCondition | null | undefined): boolean {
  if (!condition) return false
  if ('all' in condition && Array.isArray(condition.all)) return condition.all.length > 0 && condition.all.every(conditionIsComplete)
  if ('any' in condition && Array.isArray(condition.any)) return condition.any.length > 0 && condition.any.every(conditionIsComplete)
  if ('not' in condition && condition.not) return conditionIsComplete(condition.not)
  const leaf = condition as {field?: string; op?: string; value?: unknown}
  if (!leaf.field || !leaf.op) return false
  if (['exists', 'not_exists'].includes(leaf.op)) return true
  const complete = (value: unknown) => value !== null && value !== undefined && !(typeof value === 'string' && !value.trim()) && !(typeof value === 'number' && !Number.isFinite(value))
  return Array.isArray(leaf.value)
    ? leaf.value.length > 0 && leaf.value.every(complete) && (leaf.op !== 'between' || leaf.value.length === 2)
    : complete(leaf.value)
}

export function configurationError(configuration: ProcessConfiguration, manualLabel = ''): string {
  if (configuration.relations.some(relation => !relation.source_process_ids.length || !relation.target_process_ids.length)) return '请选择每一行的关联工序。'
  if (configuration.relations.some(relation => relation.source_process_ids.includes(configuration.process_id))) return '工序不能关联自身。'
  if (configuration.occurrence === 'manual' && !manualLabel.trim()) return '请填写生成时询问的名称。'
  if (configuration.when && !conditionIsComplete(configuration.when)) return '请补全每一项条件的字段、判断关系和条件值。'
  if (configuration.occurrence === 'conditional' && !configuration.when && !configuration.relations.some(relation => relation.relation_type === 'trigger_after')) return '仅调整顺序不会带出本工序，请点击“设置出现方式”选择条件工序或人工选择。'
  return ''
}

export function configurationSummary(configuration: ProcessConfiguration, name: string, fields: CanonicalConditionField[], processes: RuleConditionProcessOption[]): string {
  const display = (id: string) => processes.find(process => process.process_id === id)?.display_name || id
  const triggerRelations = configuration.relations.filter(relation => relation.relation_type === 'trigger_after')
  const triggerPath = triggerRelations.map(relation => {
    const names = relation.source_process_ids.map(display)
    return names.length > 1 && relation.source_match !== 'all'
      ? `${names.join('或')}任一出现`
      : `${names.join('、')}全部出现`
  }).join('，且')
  const fieldPath = configuration.occurrence === 'conditional' && configuration.when
    ? formatRuleCondition(configuration.when, fields)
    : ''
  const manualPath = configuration.occurrence === 'manual'
    ? `用户选择“${fields.find(field => field.key === (configuration.when && 'field' in configuration.when ? configuration.when.field : ''))?.label || `是否需要${name}`}”为是`
    : ''
  const appearanceParts = [configuration.occurrence === 'manual' ? manualPath : fieldPath, triggerPath].filter(Boolean)
  const inclusionPath = configuration.occurrence === 'always' ? `始终生成${name}`
    : appearanceParts.length ? `${appearanceParts.join('，且')}时生成${name}` : `尚未设置${name}的出现方式`
  const relations = configuration.relations.map(relation => {
    const sources = relation.source_process_ids.map(display).join('、') || '待选择工序'
    if (relation.relation_type === 'trigger_after') return `排在${sources}之后`
    if (relation.relation_type === 'order_after') return `两者都生成时，${name}排在${sources}之后`
    if (relation.relation_type === 'requires') return `${name}生成时，需要先安排${sources}`
    return `${name}不能与${sources}同时生成`
  })
  return [inclusionPath, ...relations].join('；')
}

export function processRelationDescription(
  relation: ProcessRelationCandidate,
  currentName: string,
  processes: RuleConditionProcessOption[],
): string {
  const display = (id: string) => processes.find(process => process.process_id === id)?.display_name || id
  const names = relation.source_process_ids.map(display)
  const linked = names.join('、') || '关联工序'
  if (relation.relation_type === 'trigger_after') {
    const subject = names.length > 1
      ? linked + (relation.source_match === 'all' ? '全部' : '中的任一工序')
      : linked
    return subject + '纳入路线时，系统会自动纳入' + currentName + '，并排在' + linked + '后；单独设置此关联即可触发，若另设出现条件则需同时满足。'
  }
  if (relation.relation_type === 'order_after') {
    return '只管顺序：' + linked + '和' + currentName + '都纳入路线时，' + currentName + '排在' + linked + '后；不会因此自动纳入工序。'
  }
  if (relation.relation_type === 'requires') {
    const prerequisite = names.length > 1 ? linked + '都' : linked
    return currentName + '纳入路线时，' + prerequisite + '必须先纳入；系统会尝试补上' + linked + '，否则提示依赖未满足。'
  }
  return currentName + '和' + linked + '不能同时纳入；若两者都被选中，系统会提示冲突。'
}
