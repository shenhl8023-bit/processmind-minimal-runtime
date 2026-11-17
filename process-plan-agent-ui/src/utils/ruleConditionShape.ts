import type { RulePackageCondition } from '@/api/rulePackages'

/** Validate the active branch; backend JSON includes nulls for inactive branches. */
export function readRuleConditionNode(value: unknown): RulePackageCondition | null {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null
  const node = value as Record<string, unknown>
  const branches = [node.all != null, node.any != null, node.not != null, node.field != null || node.op != null]
  if (branches.filter(Boolean).length !== 1) return null
  if (node.all != null || node.any != null) {
    const children = node.all != null ? node.all : node.any
    if (!Array.isArray(children)) return null
    const normalized: RulePackageCondition[] = []
    for (const child of children) {
      const condition = readRuleConditionNode(child)
      if (!condition) return null
      normalized.push(condition)
    }
    return node.all != null ? { all: normalized } : { any: normalized }
  }
  if (node.not != null) {
    const condition = readRuleConditionNode(node.not)
    return condition ? { not: condition } : null
  }
  if (typeof node.field !== 'string' || !node.field.trim() || typeof node.op !== 'string' || !node.op.trim()) return null
  return { field: node.field, op: node.op, ...('value' in node ? { value: node.value } : {}) }
}
