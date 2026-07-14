export type CoverageReasonKey =
  | 'coverage_reason::material'
  | 'coverage_reason::structure'
  | 'coverage_reason::size'
  | 'coverage_reason::blank'
  | 'coverage_reason::requirement'

const SIZE_REASON_DISABLED_PROFILE_KEYS = new Set<string>([
  'prep_merge',
  'prep_single',
  'heat_process_generic',
  'heat_name_merge',
  'heat_single',
  'stress_relief_single',
  'generic_inspection',
  'inspection_gate',
  'hffm_degrease',
  'hffm_alodine',
  'hffm_tube_assembly',
  'hffm_leak_test',
  'hffm_tube_kitting',
  'hffm_tube_cleaning',
  'hffm_paint',
  'hffm_inspection',
  'cleanup_stage',
  'trace_mark',
  'package_release',
  'surface_treat_generic',
  'surface_treat_single',
  'chamfer_edge',
])

const SIZE_REASON_DISABLED_FAMILIES = new Set<string>([
  'blank_prep',
  'heat_treat',
  'surface_check',
])

export function shouldSuppressLegacySizeReason(profileKey?: string | null, family?: string | null) {
  if (profileKey && SIZE_REASON_DISABLED_PROFILE_KEYS.has(profileKey)) return true
  if (family && SIZE_REASON_DISABLED_FAMILIES.has(family)) return true
  return false
}

export function normalizeCoverageReasonPriority<T extends string>(
  reasons: T[],
  options?: {
    profileKey?: string | null
    family?: string | null
  },
) {
  const filtered = reasons.filter((value, index) => {
    if (reasons.indexOf(value) !== index) return false
    if (
      value === 'coverage_reason::size'
      && shouldSuppressLegacySizeReason(options?.profileKey, options?.family)
    ) return false
    return true
  })

  return filtered.length ? filtered : reasons
}
