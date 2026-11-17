import type { ProcessConfiguration, RulePackageCondition, RulePackageInputField, RulePackageRule } from '@/api/rulePackages'
import { readRuleConditionNode } from '@/utils/ruleConditionShape'
import { actualProjectItGrades } from '@/utils/projectConditionFields'

type Condition = RulePackageCondition
type Input = { fields: RulePackageInputField[]; rules: RulePackageRule[]; processConfigurations: ProcessConfiguration[] }
const operationField = /^(project_factor\.operation_[^.]+)\.(features|direction|it|ra)$/
export const sharedFeatureField = /^(project_factor\.feature_[^.]+)\.(present|direction|it|ra)$/

export function featureInputScope(name: string) {
  // Encode the name rather than a sequence number: reorder/export keeps identity.
  return `project_factor.feature_${Array.from(name).map(char => char.codePointAt(0)!.toString(16)).join('_')}`
}

export function featureDisplayName(name: string) {
  return name.replace(/^孔\((通孔|盲孔)\)$/, '$1')
}

export const featureCategories = [
  { id: 'outer', title: '外圆类', names: ['外圆柱面'] },
  { id: 'plane', title: '平面类', names: ['轴端面', '平面'] },
  { id: 'hole', title: '孔类', names: ['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面', '型孔', '螺纹底孔', '顶尖孔'] },
  { id: 'slot', title: '槽类', names: ['U形外环槽', 'U形内环槽', '外环槽', '内环槽', 'V形环槽', '通槽', 'T形截面通槽', '沟槽', 'L形端面环槽', 'U形直槽'] },
  { id: 'edge', title: '倒角／倒圆类', names: ['倒角', '内倒角', '外倒角', '边倒角', '边倒圆', '倒圆', '回转面倒圆'] },
  { id: 'other', title: '其他特征', names: ['内螺纹', '外螺纹', '锥面', '球面'] },
]

function combine(kind: 'all' | 'any', nodes: Condition[]): Condition {
  return nodes.length === 1 ? nodes[0]! : kind === 'all' ? { all: nodes } : { any: nodes }
}

function fieldKeys(node: Condition | null | undefined): string[] {
  if (!node) return []
  if ('field' in node) return [node.field]
  if ('not' in node) return fieldKeys(node.not)
  return ('all' in node ? node.all : node.any).flatMap(fieldKeys)
}

/** Authoring permits a wider threshold range than actual part inputs. Only
 * known IT authoring domains can share the project's actual grade domain.
 * Restrictive/custom metadata stays intact for the server's conflict audit.
 */
function actualInputDefinition(field: RulePackageInputField): RulePackageInputField {
  const validation = field.validation
  const standardOptions = (field.options || []).every(option => {
    const grade = Number(option.value)
    return Number.isInteger(grade) && grade >= -1 && grade <= 18 && option.value === String(grade)
      && option.label === (grade === -1 ? 'IT01' : `IT${grade}`)
  })
  if (field.type !== 'number' || field.unit !== 'IT' || !validation || !standardOptions
    || Object.entries(validation).some(([key, value]) => value != null && !['min', 'max'].includes(key))
    || ![-1, 1, actualProjectItGrades[0]!].includes(validation.min!)
    || ![18, actualProjectItGrades[actualProjectItGrades.length - 1]!].includes(validation.max!)) return field
  return { ...field, validation: { min: actualProjectItGrades[0]!, max: actualProjectItGrades[actualProjectItGrades.length - 1]! }, options: [] }
}

/** Lower the confirmed same-object clauses to ordinary V2 fields/AND/OR.
 * No custom execution operator or export format is introduced. Unsupported
 * custom expressions keep their original fields and audited semantics.
 */
export function lowerFeatureInputs(input: Input): Input {
  const definitions = new Map(input.fields.map(field => [field.key, field]))
  const shared = new Map<string, RulePackageInputField>()
  function register(name: string, suffix: string, oldKey?: string) {
    const key = `${featureInputScope(name)}.${suffix}`
    const authored = oldKey ? definitions.get(oldKey) : undefined
    const original = authored && suffix === 'it' ? actualInputDefinition(authored) : authored
    if (!shared.has(key)) {
      shared.set(key, suffix === 'present'
        ? { key, label: name, type: 'boolean', required: false, source: '本项目特征输入', allow_custom: false }
        : { ...original!, key, label: `${name}${suffix === 'direction' ? '的方位' : suffix === 'it' ? '的实际尺寸精度等级' : '的实际Ra要求值'}`, required: false, source: '本项目特征输入' })
    } else if (original?.options?.length) {
      const field = shared.get(key)!
      field.options = [...new Map([...(field.options || []), ...original.options].map(option => [option.value, option])).values()]
    }
    return key
  }
  function scopeOf(node: Condition): string | null {
    if ('field' in node) return operationField.exec(node.field)?.[1] || null
    if ('not' in node) return null
    const scopes = [...new Set(('all' in node ? node.all : node.any).map(scopeOf))]
    return scopes.length === 1 && scopes[0] ? scopes[0] : null
  }
  function flatten(node: Condition): Condition[] {
    return 'all' in node ? node.all.flatMap(flatten) : [node]
  }
  function substitute(node: Condition, name: string): Condition {
    if ('field' in node) {
      const match = operationField.exec(node.field)!
      if (match[2] === 'features') return { field: register(name, 'present'), op: 'eq', value: true }
      const key = register(name, match[2]!, node.field)
      if (match[2] === 'direction' && node.op === 'eq' && ['A侧', 'B侧', '所有方位'].includes(String(node.value))) {
        return { field: key, op: 'in', value: node.value === '所有方位' ? ['A侧', 'B侧', '所有方位'] : [node.value, '所有方位'] }
      }
      return { ...node, field: key }
    }
    if ('not' in node) return node
    return combine('all' in node ? 'all' : 'any', ('all' in node ? node.all : node.any).map(child => substitute(child, name)))
  }
  function lower(node: Condition): Condition {
    if ('not' in node) return node
    if ('any' in node) return combine('any', node.any.map(lower))
    const nodes = flatten(node), byScope = new Map<string, Condition[]>()
    for (const item of nodes) {
      const scope = scopeOf(item)
      if (scope) byScope.set(scope, [...(byScope.get(scope) || []), item])
    }
    const replacements = new Map<Condition, Condition>(), consumed = new Set<Condition>()
    for (const clauses of byScope.values()) {
      const selections = clauses.filter((item): item is Extract<Condition, { field: string }> => 'field' in item && item.field.endsWith('.features'))
      // Multiple feature predicates/custom Boolean shapes have broader object
      // semantics than this one-instance UI. Preserve their audited input shape.
      if (selections.length !== 1 || selections.some(item => !['contains_any', 'contains'].includes(item.op))) continue
      if (clauses.some(item => !('field' in item) && !('any' in item && item.any.length === 2 && item.any.every(child => 'field' in child && child.field.endsWith('.direction') && child.op === 'eq') && new Set(item.any.map(child => 'field' in child ? child.value : null)).size === 2 && item.any.every(child => 'field' in child && ['A侧', 'B侧'].includes(String(child.value)))))) continue
      // Leave unknown/dynamic definitions intact rather than inventing a domain.
      if (clauses.some(item => fieldKeys(item).some(key => !definitions.has(key)))) continue
      const values = selections.map(item => Array.isArray(item.value) ? item.value.map(String) : [String(item.value)])
      const names = [...new Set(values[0])].filter(name => values.every(list => list.includes(name)))
      if (!names.length) continue
      replacements.set(clauses[0]!, combine('any', names.map(name => combine('all', clauses.map(item => substitute(item, name))))))
      clauses.slice(1).forEach(item => consumed.add(item))
    }
    return combine('all', nodes.filter(item => !consumed.has(item)).map(item => replacements.get(item) || ('field' in item ? item : lower(item))))
  }
  const rules = input.rules.map(rule => ({ ...rule, when: lower(readRuleConditionNode(rule.when) || rule.when) }))
  const processConfigurations = input.processConfigurations.map(configuration => ({ ...configuration, when: configuration.when ? lower(readRuleConditionNode(configuration.when) || configuration.when) : configuration.when }))
  const referenced = new Set([...rules.map(rule => rule.when), ...processConfigurations.map(configuration => configuration.when)].flatMap(fieldKeys))
  const fields = [...input.fields.filter(field => referenced.has(field.key)), ...shared.values()].filter(field => referenced.has(field.key))
  return { fields, rules, processConfigurations }
}
