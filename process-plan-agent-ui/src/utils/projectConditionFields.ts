import type { CanonicalConditionField, RuleConditionCandidate, RulePackageCondition } from '@/api/rulePackages'
import catalog from '../../../process-plan-agent-api/app/assets/project_conditions.json'
import legacyFields from '../../../process-plan-agent-api/app/assets/legacy_condition_fields.json'
import { readRuleConditionNode } from '@/utils/ruleConditionShape'

/** The same source supplies backend candidates and the current project's actual IT domain. */
export const projectConditionExpressions = catalog.expressions
export const actualProjectItGrades = catalog.actual_it_grades
export type ProjectConditionConfiguration = {
  feature_mappings?: Record<string, string[]>
  directions?: string[]
  materials?: string[]
  operation_guidance?: Record<string, { feature_group?: string; recommendation?: unknown }>
}

export function projectConditionScope(processId: string) {
  let hash = 2166136261
  for (const char of processId) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return `project_factor.operation_${(hash >>> 0).toString(16).padStart(8, '0')}`
}

export function projectRequirementKind(name: string) {
  const patterns: [RegExp, string][] = [[/去毛刺/, 'deburr'], [/清洗/, 'clean'], [/检验|检查|检测|探伤/, 'inspection'], [/阳极|镀|除铜|氧化|钝化|磷化|发黑|表面处理/, 'surface'], [/淬火|回火|调质|退火|正火|渗|去应力|时效|热处理/, 'heat']]
  return patterns.find(([pattern]) => pattern.test(name))?.[1] || ''
}

export function projectConditionFields(processId: string, processName: string, configuration: ProjectConditionConfiguration = {}): CanonicalConditionField[] {
  const scope = projectConditionScope(processId)
  const mappings: Record<string, string[]> = configuration.feature_mappings || catalog.feature_mappings
  const aliases: Record<string, string[]> = { 扁位: ['铣扁', '割扁'], '倒圆/边缘圆角': ['倒圆', '磨圆'] }
  const explicit = configuration.operation_guidance?.[processName]?.feature_group
  const group = explicit && mappings[explicit] ? explicit : Object.keys(mappings).map(key => ({ key, score: Math.max(0, ...[...key.split('/'), ...(aliases[key] || [])].filter(alias => processName.includes(alias)).map(alias => alias.length)) })).filter(item => item.score).sort((a, b) => b.score - a.score)[0]?.key
  const features = group ? mappings[group]! : [...new Set(Object.values(mappings).flat())]
  const object = group ? features.join('、') : '加工对象'
  const fields: CanonicalConditionField[] = []
  function add(suffix: string, label: string, type: CanonicalConditionField['type'], operators: string[], options: string[] = [], extra: Partial<CanonicalConditionField> = {}) {
    fields.push({ key: suffix === 'material_grade' ? 'project_factor.material_grade' : `${scope}.${suffix}`, label, category: '本项目条件', type, operators, aliases: [], source: `项目问答配置；同一加工对象；工序=${processId}`, options: options.map(value => ({ value, label: value })), allow_custom: false, required: false, ...extra })
  }
  add('features', '加工对象的特征', 'multi_select', ['contains_any'], features)
  add('direction', '同一加工对象的方位', 'single_select', ['eq'], configuration.directions || catalog.directions)
  add('it', `${object}的实际尺寸精度等级`, 'number', ['lte'], [], { unit: 'IT', validation: { min: -1, max: 18 }, options: Array.from({ length: 20 }, (_, index) => ({ value: String(index - 1), label: index === 0 ? 'IT01' : `IT${index - 1}` })) })
  add('ra', `${object}的实际Ra要求值`, 'number', ['lte'], [], { unit: 'μm', validation: { min: 0 } })
  add('material_grade', '材料牌号', 'single_select', ['eq', 'in'], configuration.materials || catalog.materials, { allow_custom: true })
  add('hardness_unit', '目标硬度制', 'single_select', ['eq'], ['HRC', 'HBW', 'HV', 'HRB'])
  add('hardness_min', '目标硬度下限（含）', 'number', ['gte'], [], { validation: { min: 0 } })
  add('hardness_max', '目标硬度上限（含）', 'number', ['lte'], [], { validation: { min: 0 } })
  // R03/B02/M01/Q01/Y01 share one Boolean shape, scoped to this exact node.
  // They are business expressions, not five generic flags for other operations.
  add('requirement', `当前部位是否有明确${processName}要求`, 'boolean', ['eq'])
  return fields
}

export function referencedConditionKeys(condition: RulePackageCondition | null | undefined): Set<string> {
  condition = readRuleConditionNode(condition)
  if (!condition) return new Set()
  if ('field' in condition) return new Set([condition.field])
  if ('all' in condition && Array.isArray(condition.all)) return new Set(condition.all.flatMap(child => [...referencedConditionKeys(child)]))
  if ('any' in condition && Array.isArray(condition.any)) return new Set(condition.any.flatMap(child => [...referencedConditionKeys(child)]))
  return 'not' in condition ? referencedConditionKeys(condition.not) : new Set()
}

/** Candidate-owned definitions win, including old definitions removed from new candidates. */
export function mergeProjectConditionFields(processId: string, processName: string, definitions: CanonicalConditionField[], candidates: Array<RuleConditionCandidate | null | undefined>, configuration?: ProjectConditionConfiguration | null) {
  const used = new Set(candidates.flatMap(candidate => [...referencedConditionKeys(candidate?.configuration?.when || candidate?.when)]))
  // null means a saved identity could not be recovered; do not invent a domain.
  const projectFields = configuration === null ? [] : projectConditionFields(processId, processName, configuration)
  const projectKeys = new Set(projectFields.map(field => field.key))
  const inheritedFields = [
    ...(legacyFields as CanonicalConditionField[]).filter(field => used.has(field.key)),
    ...definitions.filter(field => projectKeys.has(field.key) || used.has(field.key)),
  ]
  return [...new Map([
    ...(configuration ? [...inheritedFields, ...projectFields] : [...projectFields, ...inheritedFields]),
    ...candidates.flatMap(candidate => (candidate?.field_definitions || []).filter(field => used.has(field.key))),
  ].map(field => [field.key, field])).values()]
}

/** Strip only known generated prefixes for display; never rewrite frozen definitions. */
export function projectConditionDisplayLabel(field: CanonicalConditionField, processName: string) {
  if (!/^project_factor\.operation_[^.]+\./.test(field.key)) return field.label
  const suffix = field.key.split('.').pop()
  const oldLabels: Record<string, string[]> = {
    features: ['加工对象的特征'], direction: ['同一加工对象的方位'],
    hardness_unit: ['目标硬度制', '目标硬度单位'],
    hardness_min: ['目标硬度下限（含）'], hardness_max: ['目标硬度上限（含）'],
  }
  const neutral = oldLabels[suffix || '']?.find(label => field.label === `${processName}${label}`)
  if (neutral) return neutral
  if (['it', 'ra'].includes(suffix || '') && field.label.startsWith(`${processName} · `)) return field.label.slice(processName.length + 3)
  return field.label
}

export function isActualProjectItField(field: { key: string; unit?: string | null; name?: string }) {
  return field.unit === 'IT' || /^project_factor\.operation_[^.]+\.it$/.test(field.key)
    || /^precision\.(?:dimension|outer_diameter|inner_diameter)_it$/.test(field.key)
}
