import type {
  RuleConditionCandidate,
  RulePackageCondition,
  StandardFactorDefinition,
} from '@/api/rulePackages'

export type FactorBindingIssue = {
  code: 'factor_unbound' | 'factor_ambiguous' | 'factor_mismatch'
  path: string
  message: string
  candidate_factor_ids: string[]
}

export type SelectedStandardFactor = {
  path: string
  factor: StandardFactorDefinition
}

type RulePackageConditionLeaf = Extract<RulePackageCondition, { field: string }>

function isConditionLeaf(condition: RulePackageCondition): condition is RulePackageConditionLeaf {
  const node = condition as unknown as Record<string, unknown>
  return typeof node.field === 'string'
}

function normalizeCanonicalValue(value: unknown): unknown {
  if (typeof value !== 'string') return value
  return value.normalize('NFKC').trim().split(/\s+/u).filter(Boolean).join(' ')
}

function equalCanonicalValue(left: unknown, right: unknown) {
  if (typeof left === 'string' || typeof right === 'string') {
    return normalizeCanonicalValue(left) === normalizeCanonicalValue(right)
  }
  return stableSerialize(left) === stableSerialize(right)
}

export function matchingStandardFactors(
  leaf: RulePackageCondition,
  factors: StandardFactorDefinition[],
) {
  if (!isConditionLeaf(leaf)) return []
  return factors.filter(factor => (
    [factor.source_field, ...(factor.source_field_aliases || [])].includes(leaf.field)
    && factor.allowed_operators.includes(leaf.op)
    && (
      factor.canonical_value === null
      || equalCanonicalValue(leaf.value, factor.canonical_value)
    )
  ))
}

function isManualProcessLeaf(leaf: RulePackageCondition) {
  return isConditionLeaf(leaf)
    && leaf.field.startsWith('project_factor.manual_process_')
    && leaf.op === 'eq'
    && typeof leaf.value === 'boolean'
}

function childPath(path: string, branch: string, index?: number) {
  const suffix = index === undefined ? branch : `${branch}[${index}]`
  return path ? `${path}.${suffix}` : suffix
}

function bindingIssue(
  code: FactorBindingIssue['code'],
  path: string,
  matches: StandardFactorDefinition[],
): FactorBindingIssue {
  const messages = {
    factor_unbound: '条件尚未绑定标准因子',
    factor_ambiguous: '标准因子存在多个候选',
    factor_mismatch: '条件与指定的标准因子不匹配',
  }
  return {
    code,
    path,
    message: messages[code],
    candidate_factor_ids: matches.map(item => item.factor_id),
  }
}

export function factorBindingState(
  condition: RulePackageCondition,
  factors: StandardFactorDefinition[],
) {
  const issues: FactorBindingIssue[] = []
  const selected: SelectedStandardFactor[] = []

  function visit(node: RulePackageCondition, path: string) {
    if (isConditionLeaf(node)) {
      if (isManualProcessLeaf(node)) {
        if (node.factor_id != null) issues.push(bindingIssue('factor_mismatch', path, []))
        return
      }
      const matches = matchingStandardFactors(node, factors)
      if (matches.length > 1) {
        issues.push(bindingIssue('factor_ambiguous', path, matches))
        return
      }
      if (matches.length === 0) {
        issues.push(bindingIssue(node.factor_id ? 'factor_mismatch' : 'factor_unbound', path, matches))
        return
      }
      const factor = matches[0]!
      if (node.factor_id !== factor.factor_id) {
        issues.push(bindingIssue(node.factor_id ? 'factor_mismatch' : 'factor_unbound', path, matches))
        return
      }
      selected.push({ path, factor })
      return
    }
    const compound = node as unknown as Record<string, unknown>
    if (Array.isArray(compound.all)) {
      compound.all.forEach((child, index) => {
        visit(child as RulePackageCondition, childPath(path, 'all', index))
      })
      return
    }
    if (Array.isArray(compound.any)) {
      compound.any.forEach((child, index) => {
        visit(child as RulePackageCondition, childPath(path, 'any', index))
      })
      return
    }
    if (compound.not && typeof compound.not === 'object') {
      visit(compound.not as RulePackageCondition, childPath(path, 'not'))
    }
  }

  visit(condition, '')
  return {
    complete: issues.length === 0,
    ambiguous: issues.some(issue => issue.code === 'factor_ambiguous'),
    issues,
    selected,
  }
}

export function filterStandardFactors(
  factors: StandardFactorDefinition[],
  query: string,
) {
  const normalizedQuery = String(normalizeCanonicalValue(query) || '').toLowerCase()
  if (!normalizedQuery) return factors
  return factors.filter((factor) => {
    const searchable = [factor.label, factor.category, factor.source_field, factor.factor_id]
      .map(value => String(normalizeCanonicalValue(value) || '').toLowerCase())
    return searchable.some(value => value.includes(normalizedQuery))
  })
}

export function applyStandardFactor(
  leaf: RulePackageCondition,
  factor: StandardFactorDefinition,
): RulePackageCondition {
  if (!isConditionLeaf(leaf)) return leaf
  const op = factor.allowed_operators.includes(leaf.op)
    ? leaf.op
    : factor.allowed_operators[0] || leaf.op
  return {
    field: factor.source_field,
    op,
    ...(factor.canonical_value !== null
      ? { value: factor.canonical_value }
      : Object.prototype.hasOwnProperty.call(leaf, 'value') ? { value: leaf.value } : {}),
    factor_id: factor.factor_id,
  }
}

export function withConditionValue(
  leaf: RulePackageCondition,
  value: unknown,
): RulePackageCondition {
  if (!isConditionLeaf(leaf)) return leaf
  return { field: leaf.field, op: leaf.op, value }
}

function stableValue(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(stableValue)
  if (value && typeof value === 'object') {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>)
        .filter(([, item]) => item !== undefined)
        .sort(([left], [right]) => left.localeCompare(right))
        .map(([key, item]) => [key, stableValue(item)]),
    )
  }
  return value
}

function stableSerialize(value: unknown) {
  return JSON.stringify(stableValue(value))
}

export function ruleConfirmationSignature(
  candidate: RuleConditionCandidate | null | undefined,
  sourceText: string,
  registryVersion: string,
) {
  return stableSerialize({
    source_text: String(sourceText || '').trim(),
    field_registry_version: registryVersion,
    candidate: candidate
      ? {
          kind: candidate.kind || 'condition',
          when: candidate.when ?? null,
          then: candidate.then ?? null,
          relation: candidate.relation ?? null,
        }
      : null,
  })
}
