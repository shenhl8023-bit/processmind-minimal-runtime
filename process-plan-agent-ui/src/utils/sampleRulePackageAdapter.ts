import type { FinalizedRulePackageResult } from '@/api/extract'
import type { RulePackageInputField, RulePackageCondition, RulePackageRule } from '@/api/rulePackages'
import projectConditions from '../../../process-plan-agent-api/app/assets/project_conditions.json'
import { isMaterialPreparationProcess } from '@/composables/finalRouteSteps'

type Row = Record<string, any>
export type SampleCondition = boolean | Row
export type SampleRulePackageTables = { factor_table: Row[]; full_route_table: Row[]; rule_table: Row[] }
export type PublicRulePackageIdentityRegistry = { processes: Record<string, string>; steps: Record<string, string>; factors: Record<string, string> }

export class SampleRulePackageExportError extends Error {
  readonly code: string
  readonly path: string
  constructor(code: string, path: string, detail: string) {
    super(`无法按样包格式导出：${detail}（${path}）`)
    this.name = 'SampleRulePackageExportError'
    this.code = code
    this.path = path
  }
}

function fail(code: string, path: string, detail: string): never {
  throw new SampleRulePackageExportError(code, path, detail)
}
function rows(value: unknown, path: string): Row[] {
  if (!Array.isArray(value) || value.some(v => !v || typeof v !== 'object' || Array.isArray(v))) {
    fail('invalid_snapshot', path, '冻结快照结构不完整，请重新验证并导出规则包。')
  }
  return value
}
function index(values: Row[], key: string, path: string): Map<string, Row> {
  const result = new Map<string, Row>()
  values.forEach(value => {
    const id = value[key]
    if (typeof id !== 'string' || !id.trim() || result.has(id)) fail('duplicate_identity', path, `存在空或重复的 ${key}，请重新验证规则包。`)
    result.set(id, value)
  })
  return result
}
function join(branch: 'all' | 'any', conditions: SampleCondition[]): SampleCondition {
  const identity = branch === 'all', result: SampleCondition[] = []
  for (const condition of conditions) {
    if (condition === !identity) return !identity
    if (condition === identity) continue
    const children = typeof condition === 'object' && Object.keys(condition).length === 1 && condition[branch]
      ? condition[branch] : [condition]
    children.forEach((child: SampleCondition) => {
      if (!result.some(item => JSON.stringify(item) === JSON.stringify(child))) result.push(child)
    })
  }
  return result.length === 0 ? identity : result.length === 1 ? result[0]! : { [branch]: result }
}
const negate = (condition: SampleCondition): SampleCondition => typeof condition === 'boolean' ? !condition : condition.not ?? { not: condition }
const selected = (id: string): SampleCondition => ({ field: 'selected_processes', op: 'contains', value: id })
const sourcePath = /^[A-Za-z_][A-Za-z0-9_]*(?:\[\])?(?:\.[A-Za-z_][A-Za-z0-9_]*(?:\[\])?)*$/
const canonical = (value: any): any => Array.isArray(value) ? value.map(canonical)
  : value && typeof value === 'object' ? Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key])])) : value
const isIT = (field: RulePackageInputField) => field.unit === 'IT'
  || /^(?:project_factor\.(?:operation|feature)_[^.]+\.it|precision\.(?:dimension|outer_diameter|inner_diameter)_it)$/.test(field.key)
const sharedFeatureParameterScope = (field: RulePackageInputField) => field.key.match(/^(project_factor\.feature_[^.]+)\.(direction|it|ra)$/)?.[1]

function factor(field: RulePackageInputField, dynamicFeatureScopes: Set<string>): Row {
  const path = `input_schema.fields.${field.key}`
  if (field.key === 'cad.features') fail('automatic_reader_factor', path, '读取器会自动全选 cad.features，无法保留人工选值；请先在对接端解除该固定行为。')
  const kinds = { boolean: 'bool', single_select: 'enum', multi_select: 'multi_enum', number: 'number', string: 'string' }
  if (!(field.type in kinds)) fail('unsupported_factor_type', path, `因素“${field.label}”类型不受样包支持，请核对因素定义。`)
  // An explicit source path belongs to the external system. Do not rewrite it.
  const source = field.source && sourcePath.test(field.source) ? field.source : `manual_defaults.${field.key}`
  if (!sourcePath.test(source)) fail('unsupported_source', `${path}.source`, `因素“${field.label}”缺少合法输入路径，请在因素定义中提供接收端 source。`)
  if (source.includes('[]')) fail('repeated_source', `${path}.source`, `因素“${field.label}”使用数组来源 ${source}，聚合取值会改变同一加工对象判断；请先明确逐对象取值协议。`)
  if (field.options?.some(option => option.aliases?.length)) fail('option_aliases', `${path}.options`, `因素“${field.label}”包含选项别名，样包无法执行原生输入归一化；请先统一接收端规范选值。`)
  const label = field.unit && !field.label.includes(field.unit) ? `${field.label}（${field.unit}）` : field.label
  const result: Row = { key: field.key, label, type: kinds[field.type], source, visible: true }
  if (field.type === 'single_select' || field.type === 'multi_select') {
    if (!field.allow_custom) result.options = (field.options || []).map(option => option.value)
  }
  if (field.required) result.required = true
  if (sharedFeatureParameterScope(field) && dynamicFeatureScopes.has(sharedFeatureParameterScope(field)!)) {
    fail('dynamic_required_input', path, `因素“${field.label}”在选择对应特征后才必填，但当前样包协议只能表达静态 required；为避免下游静默漏掉路线，请先使用支持动态必填的接收端或调整规则。`)
  }
  // Native missing fields never implicitly become False, an empty string or [].
  result.default = null
  const validation: Row = {}
  Object.entries(field.validation || {}).forEach(([key, value]) => {
    if (value == null) return
    const supported = field.type === 'number' ? ['min', 'max'] : ['string', 'single_select', 'multi_select'].includes(field.type) ? ['min_length', 'max_length'] : []
    if (!supported.includes(key)) fail('unsupported_validation', `${path}.validation`, `因素“${field.label}”有类型不适用的限制 ${key}，请核对输入约束。`)
    validation[key] = value
  })
  if (isIT(field)) {
    // Native input validation additionally restricts these fields to actual IT grades.
    const grades = projectConditions.actual_it_grades
    if (grades.some((grade, i) => grade !== grades[0]! + i)) fail('unsupported_it_domain', path, '当前 IT 离散范围无法用样包整数区间表达，请核对对接协议。')
    result.type = 'int'
    validation.min = Math.max(validation.min ?? -Infinity, grades[0]!)
    validation.max = Math.min(validation.max ?? Infinity, grades[grades.length - 1]!)
  }
  if (/^project_factor\.(?:operation_[^.]+|feature_[^.]+)\.ra$/.test(field.key)) {
    // JSON numbers in both runtimes are finite doubles. This closed lower bound
    // accepts every representable positive value while rejecting zero.
    validation.min = Math.max(validation.min ?? -Infinity, Number.MIN_VALUE)
  }
  if (/^project_factor\.operation_[^.]+\.hardness_(min|max)$/.test(field.key)) {
    fail('cross_factor_validation', path, `因素“${field.label}”含硬度上下限的跨因素校验，样包无法表达；请先核对接收端输入校验。`)
  }
  if (Object.keys(validation).length) result.validation = validation
  return result
}

function normalized(value: string, path: string): string {
  // JS lowercasing is not Python casefold for every Unicode script. Refuse such domains.
  if ([...value].some(c => c.charCodeAt(0) > 127 && c.toUpperCase() !== c.toLowerCase())) {
    fail('unicode_casefold', path, '条件含特殊 Unicode 大小写字符，不能保证原生归一化等价；请使用规范选项后重新验证。')
  }
  return value.trim().toLowerCase()
}

function referencedFields(condition: RulePackageCondition): string[] {
  if ('field' in condition) return [condition.field]
  if ('not' in condition) return referencedFields(condition.not)
  return ('all' in condition ? condition.all : condition.any).flatMap(referencedFields)
}

function compileCondition(condition: RulePackageCondition, definitions: Map<string, Row>, publicFactors: Map<string, Row>, path: string): SampleCondition {
  if (!condition || typeof condition !== 'object') fail('invalid_condition', path, '条件不是原生条件对象，请重新确认规则。')
  if ('all' in condition || 'any' in condition) {
    const branch = 'all' in condition ? 'all' : 'any'
    return join(branch, (condition as Row)[branch].map((child: RulePackageCondition, i: number) => compileCondition(child, definitions, publicFactors, `${path}.${branch}[${i}]`)))
  }
  if ('not' in condition) {
    const optional = referencedFields(condition.not).filter(key => !definitions.get(key)?.required)
    if (optional.length) fail('optional_negation', path, `取反引用非必填因素 ${optional.join('、')}，缺失输入的判断与样包不同；请改为必填或明确的正向条件。`)
    return negate(compileCondition(condition.not, definitions, publicFactors, `${path}.not`))
  }
  const { field: key, op, value } = condition, field = definitions.get(key)
  if (!field) fail('unknown_factor', path, `因素 ${key} 未在活动输入表定义，请重新验证规则。`)
  const leaf = (operator: string, expected: unknown): SampleCondition => ({ field: key, op: operator, value: expected })
  if (op === 'exists' || op === 'not_exists') return leaf('exists', op === 'exists')
  if (op === 'neq' && !field.required) fail('optional_inequality', path, `非必填因素“${field.label}”使用不等于，缺失输入时不能等价；请改为必填或正向判断。`)
  if (field.type === 'multi_select' && ['eq', 'neq', 'in'].includes(op)) fail('collection_equality', path, `多选因素“${field.label}”使用整体相等比较，样包是逐元素比较；请改用包含条件。`)
  if (field.type === 'string' || (['single_select', 'multi_select'].includes(field.type) && (field.allow_custom || !field.options?.length))) {
    fail('open_text_comparison', path, `开放文本因素“${field.label}”的大小写和空白归一化无法用样包表达；请先审定有限枚举选项。`)
  }
  if (field.type === 'number') {
    if (['eq', 'neq', 'in'].includes(op) && publicFactors.get(key)?.type !== 'int') fail('numeric_tolerance', path, `数值因素“${field.label}”的相等判断带原生容差；请改为明确数值区间。`)
    if (op === 'between') {
      if (!Array.isArray(value) || value.length !== 2) fail('invalid_condition', path, 'between 需要两个数值，请重新确认阈值。')
      return join('all', [leaf('gte', value[0]), leaf('lte', value[1])])
    }
    if (!['eq', 'neq', 'in', 'gt', 'gte', 'lt', 'lte'].includes(op)) fail('unsupported_operator', path, `数值条件 ${op} 不可导出，请核对阈值。`)
    return leaf(op, value)
  }
  if (field.type === 'boolean') {
    if (!['eq', 'neq', 'in'].includes(op)) fail('unsupported_operator', path, `Bool 条件 ${op} 不可导出，请核对条件。`)
    return leaf(op, value)
  }
  const options: string[] = field.options.map((option: Row) => option.value)
  const domain = field.type === 'single_select' ? [...options, ''] : options
  const matching = (wanted: unknown, contains = false): string[] => {
    if (typeof wanted !== 'string') fail('invalid_condition_value', path, `枚举因素“${field.label}”的条件值必须为字符串，请重新确认。`)
    const needle = normalized(wanted, path)
    return domain.filter(actual => contains ? normalized(actual, path).includes(needle) : normalized(actual, path) === needle)
  }
  const accepts = (values: string[]): SampleCondition => field.type === 'multi_select'
    ? join('any', values.map(v => leaf('contains', v))) : values.length ? leaf('in', [...new Set(values)]) : false
  if (op === 'contains_any' || op === 'contains_all') {
    if (!Array.isArray(value)) fail('invalid_condition_value', path, '包含条件必须是选值数组，请重新确认。')
    if (!value.length && op === 'contains_all' && !field.required) fail('empty_optional_collection', path, `非必填因素“${field.label}”的空全部包含条件不能无损导出；请至少选择一个值。`)
    return join(op === 'contains_any' ? 'any' : 'all', value.map(v => accepts(matching(v, field.type === 'single_select'))))
  }
  if (op === 'contains') return accepts(matching(value, field.type === 'single_select'))
  if (op === 'eq' || op === 'neq') {
    const expression = accepts(matching(value))
    return op === 'neq' ? negate(expression) : expression
  }
  if (op === 'in' && Array.isArray(value)) return accepts(value.flatMap(v => matching(v)))
  fail('unsupported_operator', path, `因素“${field.label}”使用不支持的 ${op}，请核对条件。`)
}

function mutuallyExclusive(left: RulePackageCondition, right: RulePackageCondition): boolean {
  if (!('field' in left) || !('field' in right) || left.field !== right.field) return false
  const equal = (a: unknown, b: unknown) => typeof a === 'string' && typeof b === 'string'
    ? normalized(a, 'route_rules') === normalized(b, 'route_rules') : a === b
  if (left.op === 'eq' && right.op === 'neq' || left.op === 'neq' && right.op === 'eq') return equal(left.value, right.value)
  if (!['eq', 'in'].includes(left.op) || !['eq', 'in'].includes(right.op)) return false
  const a = left.op === 'in' ? left.value as unknown[] : [left.value]
  const b = right.op === 'in' ? right.value as unknown[] : [right.value]
  return !a.some(x => b.some(y => equal(x, y)))
}

/** Pure projection of the server-validated frozen snapshot. No ID rewriting or storage. */
export function sampleRulePackageTables(saved: FinalizedRulePackageResult, registry?: PublicRulePackageIdentityRegistry): SampleRulePackageTables {
  const sources = saved.export_sources, snapshot = sources?.native_snapshot, pkg = snapshot?.rule_package
  if (saved.export_error) fail('invalid_snapshot', 'export_sources', saved.export_error)
  if (sources?.compiler_version !== 'native-v2/1' || snapshot?.schema_version !== '2.0' || !pkg) fail('invalid_snapshot', 'native_snapshot', '缺少已验证的 Native V2 快照，请重新验证规则。')
  const catalog = index(rows(pkg.route_catalog?.processes, 'route_catalog.processes'), 'process_id', 'route_catalog.processes')
  if (!catalog.size) fail('empty_route', 'route_catalog', '母路线为空，请先保存路线。')
  const fields = rows(pkg.input_schema?.fields, 'input_schema.fields')
  const definitions = index(fields, 'key', 'input_schema.fields')
  const dynamicFeatureScopes = new Set(fields
    .map(field => String(field.key || '').match(/^(project_factor\.feature_[^.]+)\.present$/)?.[1])
    .filter((scope): scope is string => Boolean(scope)))
  const factors = fields.map(field => factor(field as RulePackageInputField, dynamicFeatureScopes))
  const publicFactors = index(factors, 'key', 'factor_table')
  const configurations = index(rows(pkg.route_rules?.process_configurations || [], 'process_configurations').filter(c => c.enabled !== false), 'process_id', 'process_configurations')
  const rules = rows(pkg.route_rules?.rules, 'route_rules.rules').filter(r => r.enabled !== false) as RulePackageRule[]
  const decisions = new Map<string, { rule: RulePackageRule; action: string; condition: SampleCondition; manual: boolean }[]>()
  const known = (pid: string, path: string) => {
    if (!catalog.has(pid)) fail('unknown_process', path, `引用不存在的工序 ${pid}，请刷新并验证规则。`)
  }
  for (const rule of rules) {
    const condition = compileCondition(rule.when, definitions, publicFactors, `route_rules.${rule.rule_id}.when`)
    for (const [action, ids] of [['include', rule.then.include_process_ids || []], ['exclude', rule.then.exclude_process_ids || []]] as const) {
      ids.forEach(pid => {
        known(pid, `route_rules.${rule.rule_id}`)
        const field = 'field' in rule.when ? definitions.get(rule.when.field) : undefined
        const manual = action === 'exclude' && rule.source === 'user_confirmed' && field?.type === 'boolean'
          && field.source === '用户直接设定' && field.key.startsWith('project_factor.manual_process_')
          && 'op' in rule.when && rule.when.op === 'eq' && rule.when.value === false
        const items = decisions.get(pid) || []
        items.push({ rule, action, condition, manual }); decisions.set(pid, items)
      })
    }
  }
  const expressions = new Map<string, SampleCondition>(), rejections = new Map<string, SampleCondition>(), manualRejections = new Map<string, SampleCondition>()
  catalog.forEach((process, pid) => {
    let higher: SampleCondition = false
    const accepted: SampleCondition[] = [], rejected: SampleCondition[] = [], manual: SampleCondition[] = []
    const items = decisions.get(pid) || []
    const priorities = [...new Set(items.map(item => item.rule.priority ?? 0))].sort((a, b) => b - a)
    priorities.forEach(priority => {
      const group = items.filter(item => (item.rule.priority ?? 0) === priority)
      group.forEach(left => group.forEach(right => {
        if (left.action !== right.action && !mutuallyExclusive(left.rule.when, right.rule.when)) fail('action_conflict', `route_rules.${pid}`, `工序“${process.display_name}”的同优先级规则可能冲突，样包无法报告该运行时错误；请统一规则优先级或条件。`)
      }))
      group.forEach(item => {
        const winner = join('all', [item.condition, negate(higher)])
        if (item.action === 'include') accepted.push(winner)
        else { rejected.push(winner); if (item.manual) manual.push(winner) }
      })
      higher = join('any', [higher, ...group.map(item => item.condition)])
    })
    rejections.set(pid, join('any', rejected)); manualRejections.set(pid, join('any', manual))
    expressions.set(pid, process.main ? negate(join('any', manual)) : join('any', accepted))
  })
  configurations.forEach((config, pid) => {
    known(pid, 'process_configurations')
    if (!['always', 'manual', 'conditional', 'associated'].includes(config.occurrence)) fail('unsupported_occurrence', `process_configurations.${pid}`, `工序“${catalog.get(pid)!.display_name}”的出现方式未定义，请重新确认规则。`)
    const predicate = config.when == null ? true : compileCondition(config.when, definitions, publicFactors, `process_configurations.${pid}.when`)
    const triggers = rows(config.relations || [], `process_configurations.${pid}.relations`).filter(r => r.relation_type === 'trigger_after')
    const gates = triggers.map(r => join(r.source_match === 'any' ? 'any' : 'all', r.source_process_ids.map(selected)))
    expressions.set(pid, join('all', [predicate, ...gates, negate(rejections.get(pid)!)]))
  })
  const relations: Row[] = [
    ...rows(pkg.route_rules?.process_relations || [], 'process_relations').filter(r => r.enabled !== false).map(r => ({ ...r, configured: false })),
    ...[...configurations.values()].flatMap(config => rows(config.relations || [], 'process_configurations.relations').map((r, i) => ({ ...r, configured: true, relation_id: `${config.process_id}.${i}` }))),
  ]
  const edges = new Map([...catalog.keys()].map(pid => [pid, new Set<string>()]))
  const prerequisites: { before: string; after: string; path: string }[] = []
  const edge = (before: string, after: string, path: string) => {
    known(before, path); known(after, path)
    if (before === after) fail('dependency_cycle', path, '工序关联引用自身，请修正关联。')
    edges.get(before)!.add(after)
  }
  catalog.forEach((process, pid) => {
    const c = process.constraints || {}, path = `route_catalog.${pid}.constraints`
    if (c.conflicts_with?.length) fail('runtime_conflict', path, `工序“${process.display_name}”存在互斥约束，样包无法表达运行时冲突报错；请先审定互斥工序的出现条件。`)
    ;(c.requires || []).forEach((before: string) => { edge(before, pid, path); prerequisites.push({ before, after: pid, path }) })
    ;(c.must_run_after || []).forEach((before: string) => edge(before, pid, path))
    ;(c.must_run_before || []).forEach((after: string) => edge(pid, after, path))
  })
  relations.forEach(relation => {
    const path = `process_relations.${relation.relation_id}`
    if (!['trigger_after', 'order_after', 'requires', 'conflicts'].includes(relation.relation_type)) fail('unknown_relation', path, '工序关联类型不受支持，请核对关联。')
    if (relation.relation_type === 'conflicts') fail('runtime_conflict', path, `关系 ${relation.relation_id} 需要运行时互斥报错，样包无法表达；请先审定互斥工序的出现条件。`)
    relation.source_process_ids.forEach((before: string) => relation.target_process_ids.forEach((after: string) => {
      edge(before, after, path)
      if (relation.relation_type === 'requires') prerequisites.push({ before, after, path })
    }))
    if (relation.relation_type !== 'trigger_after' || relation.configured) return
    const trigger = join(relation.source_match === 'all' ? 'all' : 'any', relation.source_process_ids.map(selected))
    relation.target_process_ids.forEach((pid: string) => {
      if (configurations.has(pid)) return
      if ((decisions.get(pid) || []).some(d => d.action === 'exclude' && !d.manual)) fail('trigger_exclusion', path, `被带出工序“${catalog.get(pid)!.display_name}”含排除规则，原生会报冲突；请先统一关联与排除条件。`)
      if (expressions.get(pid) === true) return
      expressions.set(pid, join('all', [join('any', [expressions.get(pid)!, trigger]), negate(manualRejections.get(pid)!)]))
    })
  })
  prerequisites.forEach(({ before, after, path }) => {
    if (expressions.get(before) === true) return
    if (configurations.has(before) || (decisions.get(before) || []).some(d => d.action === 'exclude')) {
      fail('conditional_prerequisite', path, `工序“${catalog.get(after)!.display_name}”的前置“${catalog.get(before)!.display_name}”可能被条件或人工选择排除，原生会报错；请核对前置规则，样包不能静默关闭目标。`)
    }
    // An unconfigured, non-excluded prerequisite is pulled in by native planning.
    expressions.set(before, join('any', [expressions.get(before)!, selected(after)]))
  })
  const degree = new Map([...catalog.keys()].map(pid => [pid, 0]))
  edges.forEach(targets => targets.forEach(target => degree.set(target, degree.get(target)! + 1)))
  const order: string[] = [], ready = [...catalog.keys()].filter(pid => degree.get(pid) === 0)
  const compare = (a: string, b: string) => (catalog.get(a)!.default_sequence ?? 0) - (catalog.get(b)!.default_sequence ?? 0) || (a < b ? -1 : a > b ? 1 : 0)
  while (ready.length) {
    ready.sort(compare)
    const pid = ready.shift()!; order.push(pid)
    edges.get(pid)!.forEach(target => { degree.set(target, degree.get(target)! - 1); if (degree.get(target) === 0) ready.push(target) })
  }
  if (order.length !== catalog.size) fail('dependency_cycle', 'route_catalog', '工序排序约束存在循环，请修正前后置关联。')

  const delivery = snapshot.template_mapping_catalog ? index(rows(snapshot.template_mapping_catalog.processes, 'template_mapping_catalog'), 'process_id', 'template_mapping_catalog') : catalog
  if (delivery.size !== catalog.size || [...delivery.keys()].some(pid => !catalog.has(pid))) fail('stale_mapping', 'template_mapping_catalog', '映射工序与冻结母路线不一致，请重新保存映射。')
  const mapped = snapshot.template_mapping_route ? index(rows(snapshot.template_mapping_route, 'template_mapping_route'), 'process_id', 'template_mapping_route') : new Map<string, Row>()
  // Catalog phases may be presentation labels (热前/热后). Resolve their
  // precision from the same frozen normalized route, never from live project data.
  const normalizedPhases = new Map(rows(snapshot.normalized_route, 'normalized_route').map(segment =>
    [String(segment.export_process_id || segment.id || '').trim(), segment.phase] as const))
  const precisionByPhase: Row = { rough: '粗加工', roughing: '粗加工', semi_finish: '半精加工', finish: '精加工', finishing: '精加工' }
  const fullRoute = order.map(pid => {
    const process = catalog.get(pid)!, projected = delivery.get(pid)!, meta = mapped.get(pid)
    if (projected.display_name !== process.display_name || meta && meta.process_name !== process.display_name) fail('stale_mapping', `template_mapping_catalog.${pid}`, '映射工序名称与冻结核心不一致，请重新保存映射。')
    const authority = sources?.mother_route?.[pid], phase = process.phase
    // Preparation used to inherit the legacy turning family. Correct only its
    // delivery classification; retained instructions still pass the guard below.
    const preparation = isMaterialPreparationProcess(process)
    const auxiliary = preparation || (typeof authority?.auxiliary === 'boolean' ? authority.auxiliary
      : meta ? meta.process_type === '辅助工序' : ['auxiliary', 'inspection', 'heat_treatment', 'surface_treatment', 'surface_or_heat_treatment'].includes(phase))
    const precision = preparation ? '辅助工序' : meta?.precision ?? (auxiliary ? '辅助工序' : precisionByPhase[phase] || precisionByPhase[normalizedPhases.get(pid)])
    if (!precision) fail('missing_precision', `route_catalog.${pid}.phase`, `工序“${process.display_name}”缺少已确认加工精度，请在模板映射中确认分类和精度后导出。`)
    const coreSteps = index(rows(process.steps || [], `route_catalog.${pid}.steps`), 'step_id', `route_catalog.${pid}.steps`)
    const motherSteps = authority ? index(rows(authority.steps, `mother_route.${pid}.steps`), 'step_id', `mother_route.${pid}.steps`) : coreSteps
    // Native execution restores auxiliary mother instructions in its catalog.
    // The frozen external mapping row is the authoritative auxiliary delivery.
    const projectedSteps: Row[] = auxiliary && meta
      ? rows(meta.steps, `template_mapping_route.${pid}.steps`).map(step => ({ ...step, name: step.step_name }))
      : rows(projected.steps || [], `template_mapping_catalog.${pid}.steps`)
    const steps = projectedSteps.map(step => {
      const original = coreSteps.get(step.step_id) || motherSteps.get(step.step_id)
      if (!original || original.name !== step.name) fail('stale_mapping', `template_mapping_catalog.${pid}.${step.step_id}`, '映射工步身份或名称与母路线不一致，请重新保存映射。')
      return { step_name: step.name, candidates: step.candidates ?? {}, step_id: step.step_id }
    })
    if (auxiliary && steps.length) fail('auxiliary_instructions', `template_mapping_catalog.${pid}.steps`, `辅助工序“${process.display_name}”有需保留的工步，样包规定辅助工序 steps 为空；请先核对交付方式，不能静默删除工步。`)
    if (meta && JSON.stringify(canonical(meta.steps)) !== JSON.stringify(canonical(steps))) fail('stale_mapping', `template_mapping_route.${pid}.steps`, '冻结映射交付表与工步删除、排序或候选不一致，请重新保存映射。')
    return { process_name: process.display_name, process_type: auxiliary ? '辅助工序' : '加工工序', precision, steps, process_id: pid }
  })
  const tables: SampleRulePackageTables = { factor_table: factors, full_route_table: fullRoute,
    rule_table: order.map(pid => ({ target: pid, ...(expressions.get(pid) === true ? { required: true } : { when: expressions.get(pid)! }) })) }
  validateSampleRulePackageTables(tables)
  const generatedSources = fields.filter(field => !field.source || !sourcePath.test(field.source)).map(field => field.key)
  return registry ? compactSampleRulePackageTables(tables, registry, generatedSources) : tables
}

/** Rewrite identities and references together; names and explicit external source paths stay intact. */
export function compactSampleRulePackageTables(tables: SampleRulePackageTables, registry: PublicRulePackageIdentityRegistry, generatedSources: string[] = []): SampleRulePackageTables {
  const used = new Set<string>()
  const resolve = (kind: keyof PublicRulePackageIdentityRegistry, id: string): string => {
    const map = registry?.[kind]
    const result = map && Object.prototype.hasOwnProperty.call(map, id) ? map[id] : undefined
    const prefix = { processes: 'P', steps: 'S', factors: 'F' }[kind]
    if (typeof result !== 'string' || !new RegExp(`^${prefix}[0-9]{3,}$`).test(result)) fail('missing_public_identity', `public_identities.${kind}.${id}`, '系统保存的对外编号不完整，请重新分配编号后导出。')
    if (used.has(result)) fail('duplicate_public_identity', `public_identities.${kind}.${id}`, '系统保存的对外编号重复，请检查编号表。')
    used.add(result)
    return result
  }
  const processIds = new Map(tables.full_route_table.map(p => [p.process_id, resolve('processes', p.process_id)]))
  const factorIds = new Map(tables.factor_table.map(f => [f.key, resolve('factors', f.key)]))
  const rewrite = (c: SampleCondition): SampleCondition => {
    if (typeof c === 'boolean') return c
    if ('all' in c || 'any' in c) {
      const branch = 'all' in c ? 'all' : 'any'
      return { [branch]: c[branch].map(rewrite) }
    }
    if ('not' in c) return { not: rewrite(c.not) }
    return c.field === 'selected_processes' ? { ...c, value: processIds.get(c.value) }
      : { ...c, field: factorIds.get(c.field) }
  }
  const result = {
    factor_table: tables.factor_table.map(f => ({ ...f, key: factorIds.get(f.key), source: generatedSources.includes(f.key) ? `manual_defaults.${factorIds.get(f.key)}` : f.source })),
    full_route_table: tables.full_route_table.map(p => ({ ...p, process_id: processIds.get(p.process_id), steps: p.steps.map((s: Row) => ({ ...s, step_id: resolve('steps', s.step_id) })) })),
    rule_table: tables.rule_table.map(rule => ({ ...rule, target: processIds.get(rule.target), ...('when' in rule ? { when: rewrite(rule.when) } : {}) })),
  }
  validateSampleRulePackageTables(result)
  return result
}

/** Fail closed on shape, domains, typed expressions, references and dependency cycles. */
export function validateSampleRulePackageTables(tables: SampleRulePackageTables): void {
  const exact = (row: Row, required: string[], optional: string[], path: string) => {
    if (required.some(key => !(key in row)) || Object.keys(row).some(key => ![...required, ...optional].includes(key))) fail('invalid_public_shape', path, '存在缺失或协议之外的字段，请重新验证规则。')
  }
  const factors = index(rows(tables.factor_table, 'factor_table'), 'key', 'factor_table')
  factors.forEach((f, key) => {
    const path = `factor_table.${key}`
    exact(f, ['key', 'label', 'type', 'source', 'visible'], ['options', 'required', 'default', 'validation'], path)
    if (key === 'selected_processes' || !['bool', 'int', 'number', 'string', 'enum', 'multi_enum'].includes(f.type)
      || typeof f.label !== 'string' || !f.label.trim() || !sourcePath.test(f.source) || typeof f.visible !== 'boolean'
      || f.required != null && typeof f.required !== 'boolean') fail('invalid_public_factor', path, '因素类型、标签或来源无效，请核对因素定义。')
    if (f.options && (!['enum', 'multi_enum'].includes(f.type) || !Array.isArray(f.options) || f.options.some((v: unknown) => typeof v !== 'string') || new Set(f.options).size !== f.options.length)) fail('invalid_public_options', path, '枚举选项不是唯一字符串数组，请核对选项。')
    const limits = f.validation || {}, numeric = ['number', 'int'].includes(f.type)
    const allowed = numeric ? ['min', 'max'] : ['string', 'enum', 'multi_enum'].includes(f.type) ? ['min_length', 'max_length'] : []
    if (Object.entries(limits).some(([name, value]) => !allowed.includes(name) || typeof value !== 'number' || !Number.isFinite(value) || !numeric && (!Number.isInteger(value) || value < 0))
      || (limits.min != null && limits.max != null && limits.min > limits.max)
      || (limits.min_length != null && limits.max_length != null && limits.min_length > limits.max_length)) fail('invalid_public_validation', path, '输入限制不是合法范围，请核对输入约束。')
  })
  const processes = index(rows(tables.full_route_table, 'full_route_table'), 'process_id', 'full_route_table'), nodes = new Set(processes.keys())
  processes.forEach((p, pid) => {
    exact(p, ['process_name', 'process_type', 'precision', 'steps', 'process_id'], [], `full_route_table.${pid}`)
    if (typeof p.process_name !== 'string' || !p.process_name.trim() || !['加工工序', '辅助工序'].includes(p.process_type)
      || !(p.process_type === '加工工序' ? ['粗加工', '半精加工', '精加工'] : ['辅助工序']).includes(p.precision)) fail('invalid_public_process', pid, '工序名称、分类或精度无效，请重新确认。')
    const steps = rows(p.steps, `${pid}.steps`)
    if (p.process_type === '辅助工序' && steps.length) fail('invalid_public_steps', pid, '辅助工序不得携带工步，请核对交付协议。')
    steps.forEach(s => {
      exact(s, ['step_name', 'candidates', 'step_id'], [], `${pid}.steps`)
      if (typeof s.step_id !== 'string' || !s.step_id.trim() || nodes.has(s.step_id) || typeof s.step_name !== 'string' || !s.step_name.trim()) fail('duplicate_identity', pid, '工步身份或名称无效，请重新验证。')
      nodes.add(s.step_id)
      if (!s.candidates || typeof s.candidates !== 'object' || Array.isArray(s.candidates)
        || Object.entries(s.candidates).some(([path, names]) => !path.trim() || path.includes('\\') || path.endsWith('/') || !Array.isArray(names) || names.some(v => typeof v !== 'string' || !v.trim()) || new Set(names).size !== names.length)) fail('invalid_public_candidates', s.step_id, '模板候选必须是分组路径到唯一特征名数组的映射，请重新保存映射。')
    })
  })
  const targets = new Set<string>(), dependencies = new Map([...processes.keys()].map(pid => [pid, new Set<string>()]))
  const condition = (c: SampleCondition, path: string, deps: Set<string>) => {
    if (typeof c === 'boolean') return
    if (!c || typeof c !== 'object' || Array.isArray(c)) fail('invalid_public_condition', path, '条件格式无效，请重新验证。')
    for (const branch of ['all', 'any', 'not']) {
      if (!(branch in c)) continue
      if (Object.keys(c).length !== 1) fail('invalid_public_condition', path, '组合条件含多余字段，请重新验证。')
      if (branch === 'not') condition(c.not, path, deps)
      else {
        if (!Array.isArray(c[branch]) || !c[branch].length) fail('invalid_public_condition', path, '组合条件必须为非空数组，请重新确认。')
        c[branch].forEach((child: SampleCondition) => condition(child, path, deps))
      }
      return
    }
    exact(c, ['field', 'op', 'value'], [], path)
    const { field, op, value } = c
    if (field === 'selected_processes') {
      if (op !== 'contains' || !processes.has(value)) fail('unknown_process', path, '规则引用未知工序，请重新验证。')
      deps.add(value); return
    }
    const f = factors.get(field)
    if (!f) fail('unknown_factor', path, `规则引用未知因素 ${field}，请重新验证。`)
    const scalar = (v: unknown) => f.type === 'bool' ? typeof v === 'boolean' : ['int', 'number'].includes(f.type) ? typeof v === 'number' && Number.isFinite(v) && (f.type !== 'int' || Number.isInteger(v)) : typeof v === 'string'
    const valid = op === 'exists' ? typeof value === 'boolean' : ['gt', 'gte', 'lt', 'lte'].includes(op) ? ['int', 'number'].includes(f.type) && typeof value === 'number' && Number.isFinite(value)
      : op === 'in' ? f.type !== 'multi_enum' && Array.isArray(value) && value.every(scalar)
        : op === 'contains' ? ['string', 'enum', 'multi_enum'].includes(f.type) && typeof value === 'string'
          : ['eq', 'neq'].includes(op) && scalar(value)
    if (!valid) fail('invalid_public_condition_type', path, `因素 ${field} 的条件值与类型不匹配，请重新确认。`)
  }
  rows(tables.rule_table, 'rule_table').forEach(rule => {
    const path = `rule_table.${rule.target}`
    exact(rule, ['target'], ['required', 'when'], path)
    if (!processes.has(rule.target) || targets.has(rule.target) || rule.required != null && typeof rule.required !== 'boolean' || !rule.required && !('when' in rule)) fail('invalid_public_rule', path, '工序规则重复、缺失或引用无效，请重新验证。')
    targets.add(rule.target)
    if ('when' in rule) condition(rule.when, path, dependencies.get(rule.target)!)
  })
  if (targets.size !== processes.size) fail('missing_public_rule', 'rule_table', '母路线工序缺少出现规则，请重新验证。')
  const active = new Set<string>(), visited = new Set<string>()
  const visit = (pid: string) => {
    if (active.has(pid)) fail('dependency_cycle', `rule_table.${pid}`, `工序 ${pid} 的带出或前置出现判断存在循环，样包不能执行；请修正关联。`)
    if (visited.has(pid)) return
    active.add(pid); dependencies.get(pid)!.forEach(visit); active.delete(pid); visited.add(pid)
  }
  processes.forEach((_, pid) => visit(pid))
}
