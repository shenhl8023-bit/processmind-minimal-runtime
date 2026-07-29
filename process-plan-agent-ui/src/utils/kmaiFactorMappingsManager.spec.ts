import { describe, expect, it } from 'vitest'

import type { KmaiMapping } from '@/api/kmaiFactorMappings'
import {
  filterKmaiMappingManagerRows,
  isKmaiMappingLoadCurrent,
  toKmaiMappingManagerRows,
} from './kmaiFactorMappingsManager'

function mapping(overrides: Partial<KmaiMapping>): KmaiMapping {
  return {
    mapping_id: 1,
    mapping_identity: 'project:1',
    revision: 2,
    scope: 'project',
    project_id: 12,
    source_field: 'cad.features',
    source_value: 'custom slot',
    mapping_mode: 'existing_factor',
    target_factor_key: 'has_slot_feature',
    target_factor_name: 'Slot feature',
    target_factor_category: 'geometry',
    status: 'active',
    promoted_from_id: null,
    created_by: 'creator',
    updated_by: 'reviewer',
    overridden: false,
    read_only: false,
    reference_count: 0,
    ...overrides,
  }
}

describe('KmAI mapping manager rows', () => {
  it('presents scope, status, immutability, and reference-aware actions', () => {
    const rows = toKmaiMappingManagerRows([
      mapping({
        mapping_id: null,
        mapping_identity: 'builtin:slot',
        scope: 'builtin',
        project_id: null,
        read_only: true,
        revision: 1,
      }),
      mapping({ mapping_id: 2, mapping_identity: 'global:2', scope: 'global', project_id: null }),
      mapping({ mapping_id: 3, mapping_identity: 'project:3', status: 'inactive', reference_count: 2 }),
    ], 12)

    expect(rows.map(row => ({
      scope: row.scopeLabel,
      status: row.statusLabel,
      inactive: row.isInactive,
      edit: row.canEdit,
      delete: row.canDelete,
      promote: row.canPromote,
    }))).toEqual([
      { scope: '内置', status: '启用', inactive: false, edit: false, delete: false, promote: false },
      { scope: '全局', status: '启用', inactive: false, edit: true, delete: true, promote: false },
      { scope: '项目', status: '停用', inactive: true, edit: true, delete: false, promote: true },
    ])
  })

  it('presents the lower-precedence target on the effective project override row', () => {
    const rows = toKmaiMappingManagerRows([
      mapping({
        mapping_id: 2,
        mapping_identity: 'global:2',
        scope: 'global',
        project_id: null,
        target_factor_key: 'has_slot_feature',
        target_factor_name: 'Slot feature',
        overridden: true,
      }),
      mapping({
        mapping_id: 3,
        mapping_identity: 'project:3',
        target_factor_key: 'has_hole_feature',
        target_factor_name: 'Hole feature',
      }),
      mapping({
        mapping_id: null,
        mapping_identity: 'builtin:tolerance',
        scope: 'builtin',
        project_id: null,
        source_field: 'precision.grades',
        source_value: 'tight tolerance',
        target_factor_key: 'standard_tolerance',
        target_factor_name: 'Standard tolerance',
        read_only: true,
        overridden: true,
      }),
      mapping({
        mapping_id: 4,
        mapping_identity: 'project:4',
        source_field: 'precision.grades',
        source_value: 'tight tolerance',
        target_factor_key: 'precision_grade',
        target_factor_name: 'Precision grade',
      }),
    ], 12)

    expect(rows[0]?.overriddenTarget).toBeNull()
    expect(rows[1]?.overriddenTarget).toEqual({
      factorKey: 'has_slot_feature',
      factorName: 'Slot feature',
    })
    expect(rows[2]?.overriddenTarget).toBeNull()
    expect(rows[3]?.overriddenTarget).toEqual({
      factorKey: 'standard_tolerance',
      factorName: 'Standard tolerance',
    })
  })

  it('disables project promotion without project context', () => {
    const [row] = toKmaiMappingManagerRows([
      mapping({ mapping_id: 3, mapping_identity: 'project:3' }),
    ], null)

    expect(row?.canPromote).toBe(false)
  })

  it('disables every mutation for a project row from another project context', () => {
    const [staleProject, global] = toKmaiMappingManagerRows([
      mapping({ mapping_id: 13, mapping_identity: 'project:13', project_id: 13 }),
      mapping({ mapping_id: 2, mapping_identity: 'global:2', scope: 'global', project_id: null }),
    ], 12)

    expect({
      edit: staleProject?.canEdit,
      deactivate: staleProject?.canDeactivate,
      delete: staleProject?.canDelete,
      promote: staleProject?.canPromote,
    }).toEqual({ edit: false, deactivate: false, delete: false, promote: false })
    expect({
      edit: global?.canEdit,
      deactivate: global?.canDeactivate,
      delete: global?.canDelete,
    }).toEqual({ edit: true, deactivate: true, delete: true })
  })

  it('accepts only the active latest load for the requested project context', () => {
    const request = { version: 4, projectId: 12 }

    expect(isKmaiMappingLoadCurrent(request, { active: true, version: 4, projectId: 12 })).toBe(true)
    expect(isKmaiMappingLoadCurrent(request, { active: true, version: 5, projectId: 12 })).toBe(false)
    expect(isKmaiMappingLoadCurrent(request, { active: true, version: 4, projectId: 13 })).toBe(false)
    expect(isKmaiMappingLoadCurrent(request, { active: false, version: 4, projectId: 12 })).toBe(false)
  })

  it('combines search, source, scope, and status filters', () => {
    const rows = toKmaiMappingManagerRows([
      mapping({ mapping_id: 2, mapping_identity: 'global:2', scope: 'global', project_id: null }),
      mapping({
        mapping_id: 3,
        mapping_identity: 'project:3',
        source_field: 'precision.grades',
        source_value: 'tight tolerance',
        target_factor_key: 'precision_grade',
        target_factor_name: 'Precision grade',
        status: 'inactive',
      }),
    ], 12)

    expect(filterKmaiMappingManagerRows(rows, {
      search: 'precision',
      sourceField: 'precision.grades',
      scope: 'project',
      status: 'inactive',
    }).map(row => row.mapping.mapping_id)).toEqual([3])

    expect(filterKmaiMappingManagerRows(rows, {
      search: 'reviewer',
      sourceField: 'all',
      scope: 'all',
      status: 'all',
    })).toHaveLength(2)
  })
})
