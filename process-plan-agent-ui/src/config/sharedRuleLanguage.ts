export const SHARED_RULE_TERMS = {
  settingBasis: '存在条件',
  triggerCondition: '触发条件',
  normalizedName: '统一名称',
  questionTrail: '问题树确认轨迹',
} as const

export const SHARED_QUESTION_TREE_TITLES = {
  questionFollowup: '问题树追问',
  normalizedNameConfirm: '统一名称确认',
  namingUnificationConfirm: '名称统一确认',
  coverageRelationConfirm: '覆盖关系确认',
  mergeGroupingCheck: '归并分组检查',
  settingBasisTypeConfirm: '存在条件类型确认',
  structureFeatureConfirm: '结构特征确认',
  materialScopeConfirm: '材料范围确认',
  sizeBoundaryConfirm: '尺寸边界确认',
  blankMaterialConfirm: '毛坯来料确认',
  requirementTypeConfirm: '技术要求类型确认',
  requirementScopeConfirm: '技术要求范围确认',
  multiFactorConfirm: '联合因素确认',
  missingEvidenceConfirm: '边界待定确认',
  primaryFactorConfirm: '主因素确认',
  otherCaseConfirm: '补充说明确认',
} as const

export function questionTreeTitleForNode(nodeId: string) {
  const normalized = String(nodeId || '').trim()
  if (normalized === 'merge_name_root') return SHARED_QUESTION_TREE_TITLES.normalizedNameConfirm
  if (normalized === 'rule_reason_root') return SHARED_QUESTION_TREE_TITLES.settingBasisTypeConfirm
  if (normalized === 'rule_reason_other') return SHARED_QUESTION_TREE_TITLES.otherCaseConfirm
  if (normalized.startsWith('structure_')) return SHARED_QUESTION_TREE_TITLES.structureFeatureConfirm
  if (normalized.startsWith('requirement_scene_')) return SHARED_QUESTION_TREE_TITLES.requirementTypeConfirm
  if (normalized.startsWith('requirement_scope_')) return SHARED_QUESTION_TREE_TITLES.requirementScopeConfirm
  if (normalized.startsWith('material_')) return SHARED_QUESTION_TREE_TITLES.materialScopeConfirm
  if (normalized.startsWith('size_')) return SHARED_QUESTION_TREE_TITLES.sizeBoundaryConfirm
  if (normalized.startsWith('blank_')) return SHARED_QUESTION_TREE_TITLES.blankMaterialConfirm
  if (normalized.startsWith('multi_')) return SHARED_QUESTION_TREE_TITLES.multiFactorConfirm
  if (normalized.startsWith('uncertain_')) return SHARED_QUESTION_TREE_TITLES.missingEvidenceConfirm
  if (normalized.includes('other_note')) return SHARED_QUESTION_TREE_TITLES.otherCaseConfirm
  return SHARED_QUESTION_TREE_TITLES.questionFollowup
}
