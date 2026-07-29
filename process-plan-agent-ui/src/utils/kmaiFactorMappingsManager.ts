import type { KmaiMapping, KmaiMappingSnapshotScope } from '@/api/kmaiFactorMappings'

export type KmaiMappingManagerScopeFilter = 'all' | KmaiMappingSnapshotScope
export type KmaiMappingManagerStatusFilter = 'all' | KmaiMapping['status']

export type KmaiMappingManagerFilters = {
  search: string
  sourceField: 'all' | string
  scope: KmaiMappingManagerScopeFilter
  status: KmaiMappingManagerStatusFilter
}

export type KmaiMappingLoadIdentity = {
  version: number
  projectId: number | null
}

export type KmaiMappingManagerRow = {
  mapping: KmaiMapping
  scopeLabel: '内置' | '全局' | '项目'
  statusLabel: '启用' | '停用'
  isInactive: boolean
  overriddenTarget: { factorKey: string; factorName: string } | null
  canEdit: boolean
  canDeactivate: boolean
  canDelete: boolean
  canPromote: boolean
}

const scopeLabels: Record<KmaiMappingSnapshotScope, KmaiMappingManagerRow['scopeLabel']> = {
  builtin: '内置',
  global: '全局',
  project: '项目',
}

function sameSource(left: KmaiMapping, right: KmaiMapping) {
  return left.source_field === right.source_field && left.source_value === right.source_value
}

export function isKmaiMappingLoadCurrent(
  request: KmaiMappingLoadIdentity,
  current: KmaiMappingLoadIdentity & { active: boolean },
) {
  return current.active && request.version === current.version && request.projectId === current.projectId
}

export function toKmaiMappingManagerRows(
  mappings: KmaiMapping[],
  projectId: number | null,
): KmaiMappingManagerRow[] {
  return mappings.map((mapping) => {
    const inCurrentContext = mapping.scope !== 'project' || mapping.project_id === projectId
    const mutable = mapping.mapping_id !== null && !mapping.read_only && inCurrentContext
    const lowerPrecedence = (
      mapping.scope === 'project'
      && mapping.status === 'active'
      && !mapping.overridden
      && inCurrentContext
    )
      ? mappings.find(candidate => (
          candidate.scope === 'global'
          && sameSource(candidate, mapping)
          && candidate.status === 'active'
        )) ?? mappings.find(candidate => (
          candidate.scope === 'builtin'
          && sameSource(candidate, mapping)
          && candidate.status === 'active'
        ))
      : undefined

    return {
      mapping,
      scopeLabel: scopeLabels[mapping.scope],
      statusLabel: mapping.status === 'active' ? '启用' : '停用',
      isInactive: mapping.status === 'inactive',
      overriddenTarget: lowerPrecedence
        ? { factorKey: lowerPrecedence.target_factor_key, factorName: lowerPrecedence.target_factor_name }
        : null,
      canEdit: mutable,
      canDeactivate: mutable && mapping.status === 'active',
      canDelete: mutable && mapping.reference_count === 0,
      canPromote: mutable && mapping.scope === 'project' && projectId !== null,
    }
  })
}

export function filterKmaiMappingManagerRows(
  rows: KmaiMappingManagerRow[],
  filters: KmaiMappingManagerFilters,
) {
  const query = filters.search.trim().toLocaleLowerCase()
  return rows.filter((row) => {
    const mapping = row.mapping
    if (filters.sourceField !== 'all' && mapping.source_field !== filters.sourceField) return false
    if (filters.scope !== 'all' && mapping.scope !== filters.scope) return false
    if (filters.status !== 'all' && mapping.status !== filters.status) return false
    if (!query) return true
    return [
      mapping.source_field,
      mapping.source_value,
      mapping.target_factor_key,
      mapping.target_factor_name,
      mapping.target_factor_category,
      mapping.updated_by,
      row.scopeLabel,
      row.statusLabel,
    ].some(value => value.toLocaleLowerCase().includes(query))
  })
}
