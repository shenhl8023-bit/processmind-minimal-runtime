/** Null means that the condition needs the full option domain. */
export function referencedRequirementOptions(conditions: unknown[]): Set<string> | null {
  const values = new Set<string>()
  let needsFullDomain = false
  function visit(condition: unknown) {
    if (!condition || typeof condition !== 'object') return
    const node = condition as Record<string, unknown>
    if (node.field === 'special.requirements') {
      const operands = Array.isArray(node.value) ? node.value : [node.value]
      if (
        !['contains', 'contains_any', 'contains_all'].includes(String(node.op))
        || !operands.length
        || operands.some(value => typeof value !== 'string' || !value.trim())
      ) {
        needsFullDomain = true
      } else {
        operands.forEach(value => values.add((value as string).trim()))
      }
    }
    if (Array.isArray(node.all)) node.all.forEach(visit)
    if (Array.isArray(node.any)) node.any.forEach(visit)
    if (node.not) visit(node.not)
  }
  conditions.forEach(visit)
  return needsFullDomain ? null : values
}
