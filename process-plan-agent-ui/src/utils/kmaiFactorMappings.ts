import type {
  KmaiFactorCatalogItem,
  KmaiMappingBatchRequest,
  KmaiMappingCreateRequest,
  KmaiMappingIssue,
  KmaiMappingMode,
  KmaiMappingScope,
} from '@/api/kmaiFactorMappings'

type KmaiUnmappedIssue = Pick<
  KmaiMappingIssue,
  'field' | 'value' | 'occurrences' | 'rule_refs' | 'suggested_existing_factors' | 'can_create_manual_factor'
>

export type KmaiMappingDraftResolution =
  | { mode: 'existing_factor'; factorKey: string }
  | { mode: 'manual_factor'; displayName: string }

export type KmaiMappingDraft = {
  issue: KmaiMappingIssue
  scope: KmaiMappingScope
  projectId: number | null
  resolution: KmaiMappingDraftResolution | null
}

export type KmaiMappingDraftValidationIssue = {
  index: number
  code:
    | 'resolution_required'
    | 'project_id_required'
    | 'global_project_id_forbidden'
    | 'global_scope_forbidden'
    | 'target_factor_key_required'
    | 'target_factor_name_required'
    | 'manual_factor_forbidden'
  message: string
}

export type KmaiMappingDraftValidation = {
  canContinue: boolean
  issues: KmaiMappingDraftValidationIssue[]
}

export type KmaiMappingDraftValidationOptions = {
  allowGlobal?: boolean
}

export function filterBooleanKmaiFactorCatalog(
  catalog: KmaiFactorCatalogItem[],
): KmaiFactorCatalogItem[] {
  return catalog.filter(factor => factor.value_type === 'boolean')
}

export function groupKmaiUnmappedIssues(
  issues: KmaiUnmappedIssue[],
): KmaiMappingIssue[] {
  const grouped = new Map<string, KmaiMappingIssue>()
  for (const issue of issues) {
    const key = `${issue.field}\u0000${issue.value}`
    const current = grouped.get(key)
    if (current) {
      current.occurrences += issue.occurrences
      current.rule_refs = mergeRuleRefs(current.rule_refs, issue.rule_refs)
      current.suggested_existing_factors = mergeSuggestedExistingFactors(
        current.suggested_existing_factors,
        issue.suggested_existing_factors,
      )
      current.can_create_manual_factor = mergeManualFactorCapability(
        current.can_create_manual_factor,
        issue.can_create_manual_factor,
      )
      continue
    }
    grouped.set(key, {
      field: issue.field,
      value: issue.value,
      occurrences: issue.occurrences,
      rule_refs: mergeRuleRefs([], issue.rule_refs),
      ...(issue.suggested_existing_factors?.length
        ? { suggested_existing_factors: mergeSuggestedExistingFactors([], issue.suggested_existing_factors) }
        : {}),
      ...(issue.can_create_manual_factor !== undefined
        ? { can_create_manual_factor: issue.can_create_manual_factor }
        : {}),
    })
  }
  return [...grouped.values()].sort(compareIssues)
}

export function createKmaiMappingDrafts(
  issues: KmaiUnmappedIssue[],
  context: { scope: KmaiMappingScope; projectId?: number | null },
): KmaiMappingDraft[] {
  return groupKmaiUnmappedIssues(issues).map(issue => ({
    issue,
    scope: context.scope,
    projectId: context.scope === 'global' ? null : context.projectId ?? null,
    resolution: null,
  }))
}

export function validateKmaiMappingDrafts(
  drafts: KmaiMappingDraft[],
  options: KmaiMappingDraftValidationOptions = {},
): KmaiMappingDraftValidation {
  const issues: KmaiMappingDraftValidationIssue[] = []
  drafts.forEach((draft, index) => {
    if (draft.scope === 'project' && !isProjectId(draft.projectId)) {
      issues.push({
        index,
        code: 'project_id_required',
        message: 'Project mappings require a project id.',
      })
    }
    if (draft.scope === 'global' && draft.projectId != null) {
      issues.push({
        index,
        code: 'global_project_id_forbidden',
        message: 'Global mappings cannot have a project id.',
      })
    }
    if (draft.scope === 'global' && options.allowGlobal === false) {
      issues.push({
        index,
        code: 'global_scope_forbidden',
        message: 'Global mappings are not available in this context.',
      })
    }
    if (!draft.resolution) {
      issues.push({ index, code: 'resolution_required', message: 'Choose a factor resolution.' })
      return
    }
    if (draft.resolution.mode === 'existing_factor' && !draft.resolution.factorKey.trim()) {
      issues.push({
        index,
        code: 'target_factor_key_required',
        message: 'Existing-factor mappings require a factor key.',
      })
    }
    if (draft.resolution.mode === 'manual_factor' && !draft.resolution.displayName.trim()) {
      issues.push({
        index,
        code: 'target_factor_name_required',
        message: 'Manual-factor mappings require a display name.',
      })
    }
    if (draft.resolution.mode === 'manual_factor' && draft.issue.can_create_manual_factor === false) {
      issues.push({
        index,
        code: 'manual_factor_forbidden',
        message: 'This value must be mapped to an existing factor.',
      })
    }
  })
  return { canContinue: issues.length === 0, issues }
}

export function toKmaiMappingBatchRequest(
  drafts: KmaiMappingDraft[],
  options: KmaiMappingDraftValidationOptions = {},
): KmaiMappingBatchRequest {
  const validation = validateKmaiMappingDrafts(drafts, options)
  if (!validation.canContinue) {
    throw new Error(validation.issues.map(issue => issue.message).join(' '))
  }
  return { mappings: drafts.map(toKmaiMappingCreateRequest) }
}

function toKmaiMappingCreateRequest(draft: KmaiMappingDraft): KmaiMappingCreateRequest {
  const resolution = draft.resolution!
  if (resolution.mode === 'existing_factor') {
    return draft.scope === 'project'
      ? {
          scope: 'project',
          project_id: draft.projectId!,
          source_field: draft.issue.field,
          source_value: draft.issue.value,
          mapping_mode: resolution.mode satisfies KmaiMappingMode,
          target_factor_key: resolution.factorKey.trim(),
        }
      : {
          scope: 'global',
          source_field: draft.issue.field,
          source_value: draft.issue.value,
          mapping_mode: resolution.mode satisfies KmaiMappingMode,
          target_factor_key: resolution.factorKey.trim(),
        }
  }
  const target = {
    mapping_mode: resolution.mode satisfies KmaiMappingMode,
    target_factor_name: resolution.displayName.trim(),
  }
  return draft.scope === 'project'
    ? {
        scope: 'project',
        project_id: draft.projectId!,
        source_field: draft.issue.field,
        source_value: draft.issue.value,
        ...target,
      }
    : {
        scope: 'global',
        source_field: draft.issue.field,
        source_value: draft.issue.value,
        ...target,
      }
}

function mergeRuleRefs(left: string[], right: string[]): string[] {
  return [...new Set([...left, ...right])].sort((a, b) => a.localeCompare(b))
}

function mergeSuggestedExistingFactors(left: string[] = [], right: string[] = []): string[] | undefined {
  const suggestions = [...new Set([...left, ...right])].sort((a, b) => a.localeCompare(b))
  return suggestions.length ? suggestions : undefined
}

function mergeManualFactorCapability(left?: boolean | null, right?: boolean | null): boolean | undefined {
  if (left === false || right === false) return false
  if (left === true || right === true) return true
  return undefined
}

function compareIssues(left: KmaiMappingIssue, right: KmaiMappingIssue): number {
  return left.field.localeCompare(right.field) || left.value.localeCompare(right.value)
}

function isProjectId(value: number | null): value is number {
  return typeof value === 'number' && Number.isInteger(value) && value > 0
}
