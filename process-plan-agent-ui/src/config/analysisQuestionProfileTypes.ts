export interface TreeOption {
  value: string
  label: string
  countLabel?: string
  docCount?: number
  totalCount?: number
}

export type RootReasonValue =
  | 'coverage_reason::material'
  | 'coverage_reason::structure'
  | 'coverage_reason::size'
  | 'coverage_reason::blank'
  | 'coverage_reason::requirement'
  | 'coverage_reason::multi'
  | 'coverage_reason::uncertain'
  | 'coverage_reason::other'

export type QuestionLogicCategory =
  | 'turning_coarse'
  | 'turning_precision'
  | 'milling_coarse'
  | 'milling_precision'
  | 'special'
  | 'generic'

export interface StepQuestionProfile {
  key: 'outer_grinding' | 'face_grinding' | 'outer_finish_turning' | 'hole_grinding' | 'groove_grinding' | 'center_hole_process'
    | 'thread_process'
    | 'profile_hole_process'
    | 'generic_inspection'
    | 'generic_outer_shape'
    | 'heat_process_generic'
    | 'prep_merge'
    | 'prep_single'
    | 'heat_name_merge'
    | 'heat_single'
    | 'stress_relief_single'
    | 'chamfer_edge'
    | 'inspection_gate'
    | 'hffm_degrease'
    | 'hffm_alodine'
    | 'hffm_tube_assembly'
    | 'hffm_leak_test'
    | 'hffm_tube_kitting'
    | 'hffm_tube_cleaning'
    | 'hffm_paint'
    | 'hffm_inspection'
    | 'end_face_role'
    | 'cleanup_stage'
    | 'trace_mark'
    | 'groove_feature'
    | 'flat_feature'
    | 'outer_surface_general'
    | 'hole_process_general'
    | 'package_release'
    | 'surface_treat_generic'
    | 'surface_treat_single'
  rootPrompt: string
  rootReasonOrder: Array<Exclude<RootReasonValue, 'coverage_reason::other' | 'coverage_reason::uncertain'>>
  directRootValue?: RootReasonValue
  requirementTypePrompt?: string
  requirementTypeOptions?: TreeOption[]
  skipRequirementScopeAfterType?: boolean
  requirementScopePrompt?: string
  requirementScopeFallbacks?: TreeOption[]
  requirementScopePromptsByType?: Record<string, string>
  requirementScopeFallbacksByType?: Record<string, TreeOption[]>
  structureTypePrompt?: string
  structureTypeOptions?: TreeOption[]
  structureScopeFallbacks?: TreeOption[]
  blankTypePrompt?: string
  blankTypeOptions?: TreeOption[]
  blankScopePrompt?: string
  blankScopeFallbacks?: TreeOption[]
  mergeRootPrompt?: string
  mergeCoveragePrompt?: string
  materialTypePrompt?: string
  materialTypeOptions?: TreeOption[]
  logicCategory?: QuestionLogicCategory
}

export interface LocalStepQuestionProfile {
  pattern: RegExp
  profile: StepQuestionProfile
}
