import type { KmaiMappingCreateRequest, KmaiMappingIssue } from '@/api/kmaiFactorMappings'

export type MappingResolution =
  | { mode: 'existing_factor'; factorKey: string }
  | { mode: 'manual_factor'; manualName: string }

export function mergeMappingIssues(issues: Pick<KmaiMappingIssue, 'field' | 'value' | 'occurrences' | 'rule_refs'>[]) {
  const merged = new Map<string, KmaiMappingIssue>()
  for (const issue of issues) {
    const key = `${issue.field}\u0000${issue.value}`
    const current = merged.get(key)
    if (current) {
      current.occurrences += issue.occurrences
      current.rule_refs = [...new Set([...current.rule_refs, ...issue.rule_refs])].sort()
      continue
    }
    merged.set(key, {
      field: issue.field,
      value: issue.value,
      occurrences: issue.occurrences,
      rule_refs: [...new Set(issue.rule_refs)].sort(),
    })
  }
  return [...merged.values()].sort((left, right) => (
    left.field.localeCompare(right.field) || left.value.localeCompare(right.value)
  ))
}

export function buildMappingRequest(
  projectId: number,
  issue: KmaiMappingIssue,
  resolution: MappingResolution,
): KmaiMappingCreateRequest {
  const common = {
    scope: 'project' as const,
    project_id: projectId,
    source_field: issue.field,
    source_value: issue.value,
  }
  if (resolution.mode === 'existing_factor') {
    return {
      ...common,
      mapping_mode: 'existing_factor',
      target_factor_key: resolution.factorKey,
    }
  }
  return {
    ...common,
    mapping_mode: 'manual_factor',
    target_factor_name: resolution.manualName,
  }
}
