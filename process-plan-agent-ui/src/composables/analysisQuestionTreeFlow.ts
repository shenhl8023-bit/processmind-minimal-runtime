import type { DocumentOperationDetailItem, SavedNormalizedRouteVersionResult } from '@/api'
import {
  ROOT_REASON_LABELS,
  blankScopePromptForStep,
  isMachiningLogicCategory,
  isPrecisionLogicCategory,
  mergeCoveragePromptForStep,
  questionLogicCategoryForStep,
  questionProfileForStep,
  requirementScopePromptForStep,
  type RootReasonValue,
} from '@/config/analysisQuestionProfiles'
import {
  buildNamedStepTriggerScopePrompt,
} from '@/config/sharedRulePromptTemplates'
import {
  PRECISION_PRIMARY_CONFIGS,
  PRECISION_SECONDARY_CONFIGS,
  type PrecisionNodeConfig,
} from '@/config/precisionQuestionTreeConfigs'
import {
  blankOptionsForSegment,
  buildSegmentSemanticText,
  detailRowMatchesVariant,
  machiningStructureFeatureOptionsForSegment,
  mergeCandidateNamesForSegment,
  matchedTextsForVariant,
  pickMaterialOptionsByBasis,
  requirementOptionsForSegment,
  semanticDominantProcessName,
  segmentVariantNames,
  sizeOptionsForSegment,
} from '@/composables/analysisQuestionEvidence'
import {
  segmentHasRuleDecision,
  segmentNeedsMergeNameQuestion,
} from '@/composables/analysisWorkspaceHelpers'
import type { SegmentTreeState, TreeAnswer } from '@/composables/analysisQuestionTreeState'
import { savedQuestionTrail } from '@/composables/analysisQuestionTreeState'
import {
  createMultiSelectNode,
  directEntryNode,
  finalNode,
  reasonFollowupNode,
  mergeRootNode,
  reasonRootNode,
  resolveAnsweredRootReason,
  rootOtherReasonNode,
  type TreeNode,
} from '@/composables/analysisQuestionTreeNodes'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export type SegmentMode = 'none' | 'merge_name' | 'coverage'

export function classifySegmentMode(segment: Segment | null): SegmentMode {
  if (!segment) return 'none'
  const hit = Number(segment.doc_coverage?.hit_docs || 0)
  const total = Number(segment.doc_coverage?.total_docs || 0)
  const partialCoverage = total > 0 && hit < total
  if (segmentNeedsMergeNameQuestion(segment)) return 'merge_name'
  return partialCoverage ? 'coverage' : 'none'
}

function hasSavedMergeNameTrail(segment: Segment | null) {
  return savedQuestionTrail(segment).some(item => item.nodeId === 'merge_name_root')
}

function shouldReanswerMergeName(segment: Segment | null, isRejudging: boolean) {
  return isRejudging && hasSavedMergeNameTrail(segment)
}

function answerRequiresManualNote(answer: TreeAnswer | null | undefined) {
  const value = String(answer?.value || '')
  const label = String(answer?.label || '')
  return (
    value.includes('other_manual')
    || value.includes('需人工补充')
    || value.includes('未自动识别')
    || /需补充说明|人工补充|未自动识别/.test(label)
  )
}

function answerHasConcreteManualLabel(answer: TreeAnswer | null | undefined) {
  const label = String(answer?.label || '').trim()
  if (!label) return false
  return !/其他|其它|需补充说明|人工补充|未自动识别|等待补充|已在备注/.test(label)
}

function missingRequiredNote(answer: TreeAnswer | null | undefined, note = '') {
  return answerRequiresManualNote(answer) && !String(note || '').trim() && !answerHasConcreteManualLabel(answer)
}

export function segmentReviewLocked(segment: Segment | null) {
  return segmentHasRuleDecision(segment)
}

function selectedMergeDisplayName(segment: Segment, answers: Record<string, TreeAnswer>) {
  const mergeAnswer = answers.merge_name_root
  if (!mergeAnswer) return segment.normalized_step_name
  if (mergeAnswer.value === 'other') return mergeAnswer.label || segment.normalized_step_name
  if (mergeAnswer.value.startsWith('merge_name::')) {
    const idx = Number(mergeAnswer.value.split('::')[1] || 0)
    const variants = mergeCandidateNamesForSegment(segment)
    return variants[idx] || mergeAnswer.label || segment.normalized_step_name
  }
  return mergeAnswer.label || segment.normalized_step_name
}

function machiningFeatureMode(stepSemanticText: string, logicCategory: string) {
  const profile = questionProfileForStep(stepSemanticText)
  return profile?.key === 'hole_process_general'
    ? 'hole'
    : profile?.key === 'thread_process'
      ? 'thread'
      : profile?.key === 'end_face_role'
        ? 'end_face'
        : profile?.key === 'outer_surface_general'
          ? 'outer_surface'
          : profile?.key === 'groove_feature'
            ? 'groove'
            : profile?.key === 'flat_feature'
              ? 'flat'
              : profile?.key === 'profile_hole_process'
                ? 'profile_hole'
                : logicCategory.startsWith('turning')
                  ? 'turning'
                  : 'milling'
}

function coarseDirectStructureNode(
  stepSemanticText: string,
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[],
): TreeNode {
  const logicCategory = questionLogicCategoryForStep(stepSemanticText)
  const featureMode = machiningFeatureMode(stepSemanticText, logicCategory)
  const structureFeatureResult = machiningStructureFeatureOptionsForSegment(
    featureMode,
    segment,
    detailRows,
    matchedDocIds,
    matchedDocumentTexts,
  )
  const options = [
    ...structureFeatureResult.options,
    { value: 'machining_feature::other_manual', label: '其他特征（需补充说明）' },
  ]
  const prompt = featureMode === 'hole'
    ? '这道孔加工工序存在的条件，主要依赖以下哪类孔结构或前道孔加工要求？'
    : featureMode === 'thread'
      ? '这道螺纹加工工序存在的条件，主要依赖以下哪类螺纹结构或螺纹加工要求？'
      : featureMode === 'end_face'
        ? '这道端面加工工序存在的条件，主要依赖以下哪类端面角色或端面加工要求？'
        : featureMode === 'outer_surface'
          ? '这道外圆加工工序存在的条件，主要依赖以下哪类外圆表面或回转外形？'
          : featureMode === 'groove'
            ? '这道槽加工工序主要受哪类槽部结构特征触发？'
            : featureMode === 'flat'
              ? '这道平面或扁位加工工序存在的条件，主要依赖以下哪类加工对象？'
              : featureMode === 'profile_hole'
                ? '这道型孔或异形轮廓加工工序存在的条件，主要依赖以下哪类加工对象？'
                : featureMode === 'turning'
                  ? '这道车削工序存在的条件，主要依赖以下哪类回转类加工对象？'
                  : '这道铣削工序存在的条件，主要依赖以下哪类平面或局部轮廓加工对象？'

  return {
    id: 'structure_feature_primary',
    title: '结构类型确认',
    prompt,
    options,
    impliedRootValue: 'coverage_reason::structure',
    sourceHint: structureFeatureResult.usedFallback
      ? '当前工序内容里没有提取到足够明确的结构词，以下为该类工序的默认候选项。'
      : '当前候选项优先来自当前工序内容，并做了基础去重和归并。',
  }
}

function buildPrecisionQuestionNode(config: PrecisionNodeConfig, title: string): TreeNode {
  return {
    id: title === '精度类型确认' ? 'requirement_scene_type' : 'requirement_scope_detail',
    title,
    prompt: config.prompt,
    sourceHint: config.sourceHint,
    options: config.options,
    ...(title === '精度类型确认' ? { impliedRootValue: 'coverage_reason::requirement' as RootReasonValue } : {}),
  }
}

function resolvePrecisionPrimaryConfig(stepName: string, stepSemanticText: string): PrecisionNodeConfig {
  const profile = questionProfileForStep(stepSemanticText)
  const key = profile?.key
  const fallbackKey: keyof typeof PRECISION_PRIMARY_CONFIGS = /端面/.test(stepName) ? 'face_grinding' : 'hole_default'
  if (key && key in PRECISION_PRIMARY_CONFIGS) {
    const matchedConfig = PRECISION_PRIMARY_CONFIGS[key as keyof typeof PRECISION_PRIMARY_CONFIGS]
    if (matchedConfig) return matchedConfig
  }
  const fallbackConfig = PRECISION_PRIMARY_CONFIGS[fallbackKey]
  if (fallbackConfig) return fallbackConfig
  const defaultConfig = PRECISION_PRIMARY_CONFIGS.hole_default
  if (defaultConfig) return defaultConfig
  throw new Error('缺少精加工问题树默认配置')
}

function precisionPrimaryNode(stepName: string, stepSemanticText: string): TreeNode {
  return buildPrecisionQuestionNode(resolvePrecisionPrimaryConfig(stepName, stepSemanticText), '精度类型确认')
}

function precisionSecondaryNode(selectedValue: string, stepName: string): TreeNode | null {
  const config = PRECISION_SECONDARY_CONFIGS[selectedValue]
  if (!config) return null
  const normalizedConfig = (
    /外圆/.test(stepName) && selectedValue === 'precision_primary::hole_fit'
      ? { ...config, options: config.options.map(option => option.value === 'precision_scope::fit::guide_or_seal' ? { ...option, label: '密封或导向配合' } : option) }
      : config
  )
  const title = selectedValue.includes('_tolerance') ? '尺寸等级确认'
    : selectedValue.includes('_roughness') ? '粗糙度等级确认'
      : selectedValue.includes('_fit') ? (selectedValue === 'precision_primary::face_fit' ? '贴合类型确认' : selectedValue === 'precision_primary::groove_fit' ? '功能类型确认' : '配合类型确认')
        : '几何公差项目确认'
  return buildPrecisionQuestionNode(normalizedConfig, title)
}

function buildMergeModeQuestion(
  segment: Segment,
  stepName: string,
  stepProfileText: string,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[],
  state: SegmentTreeState,
): TreeNode | null {
  const nameAnswer = state.answers.merge_name_root
  if (!nameAnswer) return mergeRootNode(stepName, () => mergeCandidateNamesForSegment(segment))
  const hit = Number(segment.doc_coverage?.hit_docs || 0)
  const total = Number(segment.doc_coverage?.total_docs || 0)
  if (total > 0 && hit >= total) return null
  const selectedName = selectedMergeDisplayName(segment, state.answers)
  const root = resolveAnsweredRootReason(state.answers)
  if (root) return null
  const mergeCoveragePrompt = mergeCoveragePromptForStep(stepName, selectedName)
  const directNode = directEntryNode(selectedName, stepProfileText)
  if (directNode) {
    return {
      ...directNode,
      prompt: mergeCoveragePrompt || directNode.prompt,
    }
  }
  const logicCategory = questionLogicCategoryForStep(stepProfileText)
  if (isMachiningLogicCategory(logicCategory)) {
    return buildInitialEntryQuestion(
      segment,
      selectedName,
      stepProfileText,
      detailRows,
      matchedDocIds,
      matchedDocumentTexts,
    )
  }
  return {
    ...reasonRootNode(selectedName, stepProfileText),
    prompt: mergeCoveragePrompt || `对于已归并为“${selectedName}”的工序，请确认它在不同样本中主要受哪类条件影响？`,
  }
}

function buildInitialEntryQuestion(
  segment: Segment,
  stepName: string,
  stepProfileText: string,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[],
): TreeNode | null {
  const logicCategory = questionLogicCategoryForStep(stepProfileText)
  if (isMachiningLogicCategory(logicCategory)) {
    if (isPrecisionLogicCategory(logicCategory)) {
      return precisionPrimaryNode(stepName, stepProfileText)
    }
    return coarseDirectStructureNode(
      stepProfileText,
      segment,
      detailRows,
      matchedDocIds,
      matchedDocumentTexts,
    )
  }
  return directEntryNode(stepName, stepProfileText) || reasonRootNode(stepName, stepProfileText)
}

function buildMachiningQuestion(
  root: TreeAnswer,
  segment: Segment,
  stepName: string,
  stepProfileText: string,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[],
  state: SegmentTreeState,
): TreeNode | null {
  const logicCategory = questionLogicCategoryForStep(stepProfileText)
  if (!isMachiningLogicCategory(logicCategory)) return null

  if (root.value === 'coverage_reason::structure') {
    if (state.answers.structure_feature_primary?.value === 'machining_feature::other_manual') {
      if (!missingRequiredNote(state.answers.structure_feature_primary, state.note)) return null
      return {
        id: 'structure_other_note_prompt',
        title: '补充说明',
        prompt: '请补充说明该工序对应的其他结构特征；补充后系统将直接作为规则因素记录。',
        options: [
          { value: 'structure_other_note_prompt::pending', label: '等待补充说明' },
        ],
      }
    }
    if (!state.answers.structure_feature_primary) {
      return coarseDirectStructureNode(
        stepProfileText,
        segment,
        detailRows,
        matchedDocIds,
        matchedDocumentTexts,
      )
    }
    return null
  }

  if (!isPrecisionLogicCategory(logicCategory) || root.value !== 'coverage_reason::requirement') return null

  if (!state.answers.requirement_scene_type) {
    return precisionPrimaryNode(stepName, stepProfileText)
  }
  if (state.answers.requirement_scene_type.value === 'precision_primary::other_manual') {
    if (!missingRequiredNote(state.answers.requirement_scene_type, state.note)) return null
    return {
      id: 'requirement_other_note_prompt',
      title: '补充说明',
      prompt: '请补充说明触发该工序的其他技术要求；补充内容将直接作为规则因素记录。',
      options: [
        { value: 'requirement_other_note_prompt::pending', label: '等待补充说明' },
      ],
    }
  }
  if (!state.answers.requirement_scope_detail) {
    return precisionSecondaryNode(state.answers.requirement_scene_type.value, stepName)
  }
  if (missingRequiredNote(state.answers.requirement_scope_detail, state.note)) {
    return precisionSecondaryNode(state.answers.requirement_scene_type.value, stepName)
  }
  return null
}

function buildReasonScopeQuestion(
  root: TreeAnswer,
  segment: Segment,
  stepName: string,
  stepProfileText: string,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[],
  state: SegmentTreeState,
): TreeNode | null {
  if (root.value === 'coverage_reason::material') {
    const materialBasis = state.answers.material_basis_type
    const materialScope = state.answers.material_scope_detail
    if (materialBasis && (!materialScope || missingRequiredNote(materialScope, state.note))) {
      const options = pickMaterialOptionsByBasis(
        materialBasis.value,
        segment,
        detailRows,
        matchedDocIds,
        matchedDocumentTexts,
      )
      const basisLabel = materialBasis.label || '材料'
      return createMultiSelectNode(
        'material_scope_detail',
        '材料范围确认',
        buildNamedStepTriggerScopePrompt(stepName, basisLabel),
        options,
        '确认这些材料',
        'material_scope',
        basisLabel,
      )
    }
    return null
  }

  if (root.value === 'coverage_reason::size') {
    const sizeType = state.answers.size_driver_type
    const sizeScope = state.answers.size_scope_detail
    if (sizeType && (!sizeScope || missingRequiredNote(sizeScope, state.note))) {
      const options = sizeOptionsForSegment(
        sizeType.value,
        segment,
        detailRows,
        matchedDocIds,
        matchedDocumentTexts,
      )
      return createMultiSelectNode(
        'size_scope_detail',
        '尺寸范围确认',
        buildNamedStepTriggerScopePrompt(stepName, '尺寸表达'),
        options,
        '确认这些尺寸',
        'size_scope',
        '尺寸表达',
      )
    }
    return null
  }

  if (root.value === 'coverage_reason::blank') {
    const blankType = state.answers.blank_basis_type
    const blankScope = state.answers.blank_scope_detail
    if (blankType && (!blankScope || missingRequiredNote(blankScope, state.note))) {
      const options = blankOptionsForSegment(
        segment,
        detailRows,
        matchedDocIds,
        matchedDocumentTexts,
      )
      return createMultiSelectNode(
        'blank_scope_detail',
        '毛坯/来料范围确认',
        blankScopePromptForStep(stepName, stepProfileText) || buildNamedStepTriggerScopePrompt(stepName, '毛坯或来料状态'),
        options,
        '确认这些毛坯/来料',
        'blank_scope',
        '毛坯或来料状态',
      )
    }
    return null
  }

  if (root.value === 'coverage_reason::requirement') {
    const requirementType = state.answers.requirement_scene_type
    const profile = questionProfileForStep(stepProfileText)
    if (requirementType && profile?.skipRequirementScopeAfterType) {
      return null
    }
    const requirementScope = state.answers.requirement_scope_detail
    if (requirementType && (!requirementScope || missingRequiredNote(requirementScope, state.note))) {
      const options = requirementOptionsForSegment(
        requirementType.value,
        segment,
        detailRows,
        matchedDocIds,
        matchedDocumentTexts,
      )
      const prompt = requirementScopePromptForStep(stepName, requirementType.value, stepProfileText) || buildNamedStepTriggerScopePrompt(stepName, '加工要求')
      return createMultiSelectNode(
        'requirement_scope_detail',
        '加工要求范围确认',
        prompt,
        options,
        '确认这些要求',
        'requirement_scope',
        '加工要求',
      )
    }
    return null
  }

  return null
}

export function buildCurrentQuestion(args: {
  segment: Segment | null
  isRejudging: boolean
  detailRows: DocumentOperationDetailItem[]
  matchedDocIds: Set<number>
  matchedDocumentTexts: string[]
  state: SegmentTreeState
}): TreeNode | null {
  const { segment, isRejudging, detailRows, matchedDocIds, matchedDocumentTexts, state } = args
  if (!segment) return null
  if (segmentReviewLocked(segment) && !isRejudging) return null
  const mode = shouldReanswerMergeName(segment, isRejudging)
    ? 'merge_name'
    : classifySegmentMode(segment)
  if (mode === 'none') return null
  const selectedName = mode === 'merge_name' && state.answers.merge_name_root
    ? selectedMergeDisplayName(segment, state.answers)
    : ''
  const scopedDetailRows = selectedName
    ? detailRows.filter(row => detailRowMatchesVariant(row, selectedName))
    : detailRows
  const scopedMatchedDocumentTexts = selectedName
    ? matchedTextsForVariant(matchedDocumentTexts, selectedName)
    : matchedDocumentTexts
  const effectiveDetailRows = scopedDetailRows.length ? scopedDetailRows : detailRows
  const effectiveMatchedDocumentTexts = scopedMatchedDocumentTexts.length ? scopedMatchedDocumentTexts : matchedDocumentTexts
  const reanswerMergeNames = shouldReanswerMergeName(segment, isRejudging)
    ? mergeCandidateNamesForSegment(segment)
    : []
  const stepName = mode === 'merge_name' && reanswerMergeNames.length >= 2
    ? reanswerMergeNames.join('/')
    : segment.normalized_step_name
  const semanticDominant = semanticDominantProcessName(segment)
  const preferredSpecialVariant = !selectedName
    ? segmentVariantNames(segment).find((name) => {
      const profile = questionProfileForStep(name)
      return !!profile && !isMachiningLogicCategory(questionLogicCategoryForStep(name))
    }) || ''
    : ''
  const preferredProfileText = selectedName || preferredSpecialVariant || semanticDominant || stepName
  const stepSemanticText = selectedName
    ? [selectedName, ...effectiveMatchedDocumentTexts.map(text => String(text || '').trim()).filter(Boolean)].join('\n')
    : buildSegmentSemanticText(
      segment,
      detailRows,
      matchedDocIds,
      matchedDocumentTexts,
    )
  const stepProfileText = questionProfileForStep(preferredProfileText)
    ? preferredProfileText
    : stepSemanticText

  if (mode === 'merge_name') {
    const mergeQuestion = buildMergeModeQuestion(
      segment,
      stepName,
      stepProfileText,
      effectiveDetailRows,
      matchedDocIds,
      effectiveMatchedDocumentTexts,
      state,
    )
    if (mergeQuestion) return mergeQuestion
    const hit = Number(segment.doc_coverage?.hit_docs || 0)
    const total = Number(segment.doc_coverage?.total_docs || 0)
    if (state.answers.merge_name_root && total > 0 && hit >= total) return null
  }

  const root = resolveAnsweredRootReason(state.answers) || state.answers.rule_reason_root
  if (!root) {
    return buildInitialEntryQuestion(
      segment,
      stepName,
      stepProfileText,
      effectiveDetailRows,
      matchedDocIds,
      effectiveMatchedDocumentTexts,
    )
  }
  if (state.answers.rule_reason_root?.value === 'coverage_reason::other' && !state.answers.rule_reason_other) {
    return rootOtherReasonNode(stepName)
  }
  if (
    state.answers.rule_reason_other?.value === 'coverage_reason::other_manual'
    && missingRequiredNote(state.answers.rule_reason_other, state.note)
  ) {
    return rootOtherReasonNode(stepName)
  }

  const logicCategory = questionLogicCategoryForStep(stepProfileText)
  const machiningLogic = isMachiningLogicCategory(logicCategory)
  const machiningQuestion = buildMachiningQuestion(
    root,
    segment,
    stepName,
    stepProfileText,
    effectiveDetailRows,
    matchedDocIds,
    effectiveMatchedDocumentTexts,
    state,
  )
  if (machiningQuestion) return machiningQuestion

  if (
    machiningLogic
    && isPrecisionLogicCategory(logicCategory)
    && root.value === 'coverage_reason::requirement'
    && state.answers.requirement_scene_type?.value.startsWith('precision_primary::')
  ) {
    if (
      state.answers.requirement_scene_type.value === 'precision_primary::other_manual'
      && !missingRequiredNote(state.answers.requirement_scene_type, state.note)
    ) {
      return null
    }
    if (state.answers.requirement_scope_detail) return null
  }

  if (machiningLogic && root.value === 'coverage_reason::structure' && state.answers.structure_feature_primary) {
    return null
  }

  const followup = reasonFollowupNode(stepName, root.value, stepProfileText)
  if (followup && !state.answers[followup.id]) return followup

  if (root.value === 'coverage_reason::structure') {
    const structureResolved = state.answers.structure_feature_primary || state.answers.structure_scene_type
    if (structureResolved) return finalNode(stepName, root.value)
  }
  const scopeQuestion = buildReasonScopeQuestion(
    root,
    segment,
    stepName,
    stepProfileText,
    effectiveDetailRows,
    matchedDocIds,
    effectiveMatchedDocumentTexts,
    state,
  )
  if (
    scopeQuestion
    && (!state.answers[scopeQuestion.id] || missingRequiredNote(state.answers[scopeQuestion.id], state.note))
  ) return scopeQuestion

  const final = finalNode(stepName, root.value)
  if (final && !state.answers[final.id]) return final
  return null
}

export function buildQuestionTreeIdleReason() {
  return '这道工序当前样本表现已经比较清楚，暂时不需要继续展开问题树补充判断。'
}

export function buildImpliedRootAnswer(value: RootReasonValue): TreeAnswer {
  return {
    nodeId: 'rule_reason_root',
    value,
    label: ROOT_REASON_LABELS[value as Exclude<RootReasonValue, 'coverage_reason::other'>] || value,
  }
}
