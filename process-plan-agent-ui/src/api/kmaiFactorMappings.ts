import { api } from './client'
import type { RulePackageV2 } from './rulePackages'

export type KmaiMappingScope = 'global' | 'project'
export type KmaiMappingSnapshotScope = 'builtin' | KmaiMappingScope
export type KmaiMappingMode = 'existing_factor' | 'manual_factor'

export type KmaiMappingSnapshot = {
  mapping_id: number | null
  mapping_identity: string
  revision: number
  scope: KmaiMappingSnapshotScope
  project_id: number | null
  source_field: string
  source_value: string
  mapping_mode: KmaiMappingMode
  target_factor_key: string
  target_factor_name: string
  target_factor_category: string
}

export type KmaiFactorCatalogItem = {
  factor_key: string
  factor_name: string
  factor_category: string
  value_type: 'boolean' | 'enum'
  source_mode: string
  read_only: boolean
}

export type KmaiMapping = KmaiMappingSnapshot & {
  status: 'active' | 'inactive'
  promoted_from_id: number | null
  created_by: string
  updated_by: string
  overridden: boolean
  read_only: boolean
  reference_count: number
}

type KmaiMappingScopeRequest =
  | { scope: 'global'; project_id?: null }
  | { scope: 'project'; project_id: number }

type KmaiMappingCreateBase = {
  source_field: string
  source_value: string
  target_factor_name?: string
  actor?: string
}

type KmaiExistingFactorCreateRequest = KmaiMappingCreateBase & {
  mapping_mode: 'existing_factor'
  target_factor_key: string
}

type KmaiManualFactorCreateRequest = KmaiMappingCreateBase & {
  mapping_mode: 'manual_factor'
  target_factor_key?: never
}

export type KmaiMappingCreateRequest = KmaiMappingScopeRequest & (
  | KmaiExistingFactorCreateRequest
  | KmaiManualFactorCreateRequest
)

type KmaiMappingUpdateBase = {
  expected_revision: number
  target_factor_name?: string
  status?: 'active' | 'inactive'
  actor?: string
}

export type KmaiMappingUpdateRequest = KmaiMappingUpdateBase & (
  | { mapping_mode: 'existing_factor'; target_factor_key: string }
  | { mapping_mode: 'manual_factor'; target_factor_key?: never }
  | { mapping_mode?: undefined; target_factor_key?: never }
)

export type KmaiMappingIssue = {
  field: string
  value: string
  occurrences: number
  rule_refs: string[]
  suggested_existing_factors?: string[]
  can_create_manual_factor?: boolean
}

export type KmaiCompatibilityIssue = {
  code: string
  path?: string
  message: string
  field?: string | null
  value?: string | null
  occurrences?: number | null
  rule_refs?: string[]
  suggested_existing_factors?: string[]
  can_create_manual_factor?: boolean | null
}

export type KmaiExportFiles = Record<string, Record<string, unknown>>

export type KmaiCompatibilityExport = {
  format: 'kmai-v1'
  valid: boolean
  target_directory: string
  errors: KmaiCompatibilityIssue[]
  warnings: KmaiCompatibilityIssue[]
  files: KmaiExportFiles
  mapping_signature: string
  mapping_usages: Array<Record<string, unknown>>
}

export type KmaiMappingBatchRequest = {
  mappings: KmaiMappingCreateRequest[]
}

export type KmaiMappingPreview = {
  valid: boolean
  issues: KmaiMappingIssue[]
  mappings: KmaiMappingSnapshot[]
}

export async function getKmaiFactorCatalog() {
  const { data } = await api.get('/api/kmai-factor-mappings/catalog')
  return data as KmaiFactorCatalogItem[]
}

export async function listKmaiFactorMappings(projectId?: number | null) {
  const { data } = await api.get('/api/kmai-factor-mappings', {
    params: projectId == null ? undefined : { project_id: projectId },
  })
  return data as KmaiMapping[]
}

export async function createKmaiFactorMapping(body: KmaiMappingCreateRequest) {
  const { data } = await api.post('/api/kmai-factor-mappings', body)
  return data as KmaiMapping
}

export async function createKmaiFactorMappingBatch(body: KmaiMappingBatchRequest) {
  const { data } = await api.post('/api/kmai-factor-mappings/batch', body)
  return data as KmaiMapping[]
}

export async function updateKmaiFactorMapping(
  mappingId: number,
  body: KmaiMappingUpdateRequest,
) {
  const { data } = await api.put(`/api/kmai-factor-mappings/${mappingId}`, body)
  return data as KmaiMapping
}

export async function promoteKmaiFactorMapping(
  mappingId: number,
  expectedRevision: number,
  actor?: string,
) {
  const { data } = await api.post(
    `/api/kmai-factor-mappings/${mappingId}/promote`,
    undefined,
    {
      params: {
        expected_revision: expectedRevision,
        ...(actor ? { actor } : {}),
      },
    },
  )
  return data as KmaiMapping
}

export async function deleteKmaiFactorMapping(
  mappingId: number,
  options: { expectedRevision: number; delete?: boolean; actor?: string },
) {
  const { data } = await api.delete(`/api/kmai-factor-mappings/${mappingId}`, {
    params: {
      expected_revision: options.expectedRevision,
      ...(options.delete ? { delete: true } : {}),
      ...(options.actor ? { actor: options.actor } : {}),
    },
  })
  return data as { deleted: boolean; mapping: KmaiMapping | null }
}

export async function previewKmaiFactorMappings(projectId: number | null | undefined, packageValue: RulePackageV2) {
  const { data } = await api.post('/api/kmai-factor-mappings/resolve-preview', {
    ...(projectId == null ? {} : { project_id: projectId }),
    package: packageValue,
  })
  return data as KmaiMappingPreview
}

export const createKmaiFactorMappings = createKmaiFactorMappingBatch
export const deactivateOrDeleteKmaiFactorMapping = (
  mappingId: number,
  expectedRevision: number,
  remove = false,
) => deleteKmaiFactorMapping(mappingId, { expectedRevision, delete: remove })
