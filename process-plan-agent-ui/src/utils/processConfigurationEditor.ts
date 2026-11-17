import type { CanonicalConditionField, ProcessConfiguration, ProcessRelationCandidate, RuleConditionCandidate, RuleConditionProcessOption, RulePackageCondition } from '@/api/rulePackages'
import { formatRuleCondition } from '@/utils/finalizeRulePresentation'
import { readRuleConditionNode } from '@/utils/ruleConditionShape'

export function conditionIsComplete(condition: RulePackageCondition | null | undefined): boolean {
  condition = readRuleConditionNode(condition)
  if (!condition) return false
  if ('all' in condition && Array.isArray(condition.all)) return condition.all.length > 0 && condition.all.every(conditionIsComplete)
  if ('any' in condition && Array.isArray(condition.any)) return condition.any.length > 0 && condition.any.every(conditionIsComplete)
  if ('not' in condition && condition.not) return conditionIsComplete(condition.not)
  const leaf = condition as {field?: string; op?: string; value?: unknown}
  if (!leaf.field?.trim() || !leaf.op?.trim()) return false
  if (['exists', 'not_exists'].includes(leaf.op)) return true
  const complete = (value: unknown) => typeof value === 'boolean' || (typeof value === 'string' && Boolean(value.trim())) || (typeof value === 'number' && Number.isFinite(value))
  if (['in', 'not_in', 'contains_any', 'contains_all', 'between'].includes(leaf.op) && !Array.isArray(leaf.value)) return false
  return Array.isArray(leaf.value)
    ? leaf.value.length > 0 && leaf.value.every(complete) && (leaf.op !== 'between' || leaf.value.length === 2)
    : complete(leaf.value)
}

export function conditionTriples(condition: RulePackageCondition | null): RulePackageCondition[] | null {
  if (!condition) return []
  condition = readRuleConditionNode(condition)
  if (!condition) return null
  if ('any' in condition) {
    // This is the execution form of the single A/B choice, not a general OR
    // editor. Collapse only the exact range so frozen candidate domains survive.
    const sides = condition.any
    const first = sides[0]
    if (sides.length === 2 && first && 'field' in first
      && /^project_factor\.operation_[^.]+\.direction$/.test(first.field)
      && sides.every(side => 'field' in side && side.field === first.field && side.op === 'eq')
      && new Set(sides.map(side => 'field' in side ? side.value : null)).size === 2
      && sides.every(side => 'field' in side && ['A侧', 'B侧'].includes(String(side.value)))) {
      return [{ field: first.field, op: 'eq', value: '所有方位' }]
    }
    return null
  }
  if ('not' in condition && condition.not != null) return null
  if ('all' in condition && condition.all != null && (!Array.isArray(condition.all) || ('field' in condition && Boolean(condition.field)))) return null
  if ('all' in condition && Array.isArray(condition.all)) {
    const children = condition.all.map(conditionTriples)
    return children.some(child => child === null) ? null : children.flatMap(child => child || [])
  }
  return [condition]
}

export function configurationNeedsReset(configuration: ProcessConfiguration): boolean {
  if (!['always', 'manual', 'conditional', 'associated'].includes(configuration.occurrence)) return true
  if (configuration.occurrence === 'associated') return Boolean(configuration.when)
    || configuration.relations.length > 1
    || configuration.relations.some(relation => relation.relation_type !== 'trigger_after' || relation.source_process_ids.length > 1 || relation.target_process_ids.join() !== configuration.process_id)
  if (configuration.relations.length) return true
  if (configuration.occurrence === 'always') return Boolean(configuration.when)
  return configuration.occurrence === 'conditional' && conditionTriples(configuration.when) === null
}

export function configurationError(configuration: ProcessConfiguration, manualLabel = ''): string {
  if (configurationNeedsReset(configuration)) return '此规则包含当前出现模式不支持的内容，请选择一种出现模式重新设置。'
  if (configuration.relations.some(relation => !relation.source_process_ids.length || !relation.target_process_ids.length)) return '请选择每一行的关联工序。'
  if (configuration.relations.some(relation => relation.source_process_ids.includes(configuration.process_id))) return '工序不能关联自身。'
  if (configuration.occurrence === 'associated' && !configuration.relations.length) return '请选择一个跟随工序。'
  if (configuration.occurrence === 'manual' && !manualLabel.trim()) return '请填写生成时询问的名称。'
  if (configuration.when && !conditionIsComplete(configuration.when)) return '请补全每一项条件的字段、判断关系和条件值。'
  if (configuration.occurrence === 'conditional' && !conditionTriples(configuration.when)?.length) return '尚未设置出现条件，请自行添加至少一条条件。'
  return ''
}

// Current authoring is stricter than reading an existing rule package. Keep
// unsupported candidates intact so the user can review and explicitly rebuild.
export function validateAuthoredCandidate(candidate: RuleConditionCandidate | null | undefined, processId: string): string[] {
  const reset = '此规则包含当前出现模式不支持的内容，请选择一种出现模式重新设置。'
  if (!candidate || !processId.trim()) return ['请补全当前工序的规则。']
  const objectFields: Array<{scope: string; kind: string}> = []
  const leaves: Array<{ field: string; op: string; value?: unknown }> = []
  function collectObjects(when: RulePackageCondition | null | undefined) {
    if (!when) return
    if ('field' in when) {
      leaves.push(when)
      const match = when.field.match(/^(project_factor\.operation_[^.]+)\.(features|direction)$/)
      if (match) objectFields.push({ scope: match[1]!, kind: match[2]! })
    }
    if ('all' in when && Array.isArray(when.all)) when.all.forEach(collectObjects)
  }
  for (const condition of conditionTriples(candidate.configuration?.when || candidate.when || null) || []) collectObjects(condition)
  if (new Set(objectFields.map(item => item.kind)).size === 2 && new Set(objectFields.map(item => item.scope)).size > 1) return ['加工特征与方位必须属于同一加工对象，不能分别匹配不同对象。']
  for (const leaf of leaves) {
    if (/^project_factor\.operation_[^.]+\.it$/.test(leaf.field) && (typeof leaf.value !== 'number' || !Number.isInteger(leaf.value) || leaf.value < -1 || leaf.value > 18)) return ['尺寸精度阈值必须是 IT01、IT0 或 IT1～IT18 等级，不能使用小数。']
  }
  const intervals = new Map<string, Map<string, typeof leaves[number]>>()
  for (const leaf of leaves) {
    const match = leaf.field.match(/^(project_factor\.operation_[^.]+)\.(hardness_unit|hardness_min|hardness_max)$/)
    if (match) { const interval = intervals.get(match[1]!) || new Map(); interval.set(match[2]!, leaf); intervals.set(match[1]!, interval) }
  }
  for (const interval of intervals.values()) {
    if (!['hardness_unit', 'hardness_min', 'hardness_max'].every(key => interval.has(key))) return ['目标硬度必须同时设置硬度制、下限及上限，判断完整图纸区间。']
    const low = interval.get('hardness_min')!, high = interval.get('hardness_max')!, unit = interval.get('hardness_unit')!
    if (low.op !== 'gte' || high.op !== 'lte' || unit.op !== 'eq') return ['目标硬度完整区间须按下限≥、上限≤并使用相同硬度制判断。']
    if (Number(low.value) > Number(high.value)) return ['目标硬度完整区间下限不能大于上限。']
  }
  const manualError = (when: RulePackageCondition | null | undefined) => {
    when = readRuleConditionNode(when)
    if (!when || !('field' in when) || !when.field.startsWith('project_factor.manual_process_') || when.op !== 'eq' || when.value !== true) return '请重新设置 Bool 工序，默认不勾选，不选就是否。'
    const field = candidate.field_definitions?.find(field => field.key === when.field)
    return field?.type === 'boolean' && field.source === '用户直接设定' && field.required !== true && Boolean(field.label?.trim())
      ? '' : '请重新设置 Bool 工序的名称和选择字段。'
  }
  const conditionError = (when: RulePackageCondition | null | undefined) => {
    if (when && conditionTriples(when) === null) return reset
    return conditionIsComplete(when) ? '' : '请补全每一项条件的字段、判断关系和条件值。'
  }
  const relationError = (relation: ProcessRelationCandidate | null | undefined) => {
    if (!relation || relation.relation_type !== 'trigger_after' || relation.source_process_ids.length !== 1 || !relation.source_process_ids[0]?.trim()
      || relation.target_process_ids.length !== 1 || relation.target_process_ids[0] !== processId) return reset
    return relation.source_process_ids[0] === processId ? '工序不能关联自身。' : ''
  }
  let error = ''
  const kind = candidate.kind || 'condition'
  if (kind === 'process_configuration') {
    const config = candidate.configuration
    if (!config || config.process_id !== processId || candidate.when || candidate.then || candidate.relation) return [reset]
    const when = config.when
    const label = when && 'field' in when ? candidate.field_definitions?.find(field => field.key === when.field)?.label || '' : ''
    error = configurationError(config, label)
    if (!error && config.occurrence === 'manual') error = manualError(config.when)
    if (!error && config.occurrence === 'conditional') error = conditionError(config.when)
    if (!error && config.occurrence === 'associated') error = relationError(config.relations[0])
  } else if (kind === 'process_relation') {
    if (candidate.configuration || candidate.when || candidate.then) return [reset]
    error = relationError(candidate.relation)
  } else if (kind === 'condition') {
    if (candidate.configuration || candidate.relation) return [reset]
    const action = candidate.then
    if (action?.include_process_ids?.length !== 1 || action.include_process_ids[0] !== processId || action.exclude_process_ids?.length) return ['当前编写的条件只能纳入当前工序，请选择出现模式重新设置动作。']
    error = conditionError(candidate.when)
    const when = readRuleConditionNode(candidate.when)
    if (!error && when && 'field' in when && when.field.startsWith('project_factor.manual_process_')) error = manualError(when)
  } else error = reset
  return error ? [error] : []
}

export function configurationSummary(configuration: ProcessConfiguration, name: string, fields: CanonicalConditionField[], processes: RuleConditionProcessOption[]): string {
  const display = (id: string) => processes.find(process => process.process_id === id)?.display_name || id
  if (configuration.occurrence === 'associated') {
    const source = configuration.relations[0]?.source_process_ids[0]
    return source ? `${display(source)}纳入路线时，自动生成${name}，并排在${display(source)}之后；允许穿插其他工序，支持连续带出。` : '请选择一个跟随工序。'
  }
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
