import { coverageFamilyLabel } from '@/config/paramQuestionStrategy'
import {
  ROOT_REASON_LABELS,
  blankTypeOptionsForStep,
  blankTypePromptForStep,
  materialTypeOptionsForStep,
  materialTypePromptForStep,
  mergeRootPromptForStep,
  questionLogicCategoryForStep,
  questionProfileForStep,
  requirementTypeOptionsForStep,
  rootPromptForStep,
  rootReasonOptionsForStep,
  isMachiningLogicCategory,
  sizeTypeOptionsForStep,
  structureTypeOptionsForStep,
  structureTypePromptForStep,
  type RootReasonValue,
  type TreeOption,
} from '@/config/analysisQuestionProfiles'
import { SHARED_QUESTION_TREE_TITLES } from '@/config/sharedRuleLanguage'
import { buildFinalizeActionSentence } from '@/config/finalizeRulePresentation'
import type { TreeAnswer } from '@/composables/analysisQuestionTreeState'

export interface TreeNode {
  id: string
  title: string
  prompt: string
  options: TreeOption[]
  impliedRootValue?: RootReasonValue
  multiple?: boolean
  minSelections?: number
  confirmLabel?: string
  sourceHint?: string
}

export function resolveAnsweredRootReason(answers: Record<string, TreeAnswer>) {
  const root = answers.rule_reason_root
  if (!root) return null
  if (root.value === 'coverage_reason::other') {
    return answers.rule_reason_other || null
  }
  return root
}

export function createMultiSelectNode(
  id: string,
  title: string,
  prompt: string,
  options: TreeOption[],
  confirmLabel: string,
  fallbackPrefix: string,
  fallbackLabel: string,
  sourceHint = '结构候选项优先来自当前工序内容；尺寸和精度问题按标准工艺知识给出，系统已做去重和基础过滤。',
  minSelections = 1,
): TreeNode {
  return {
    id,
    title,
    prompt,
    options: options.length ? options : fallbackDynamicOptions(fallbackPrefix, fallbackLabel),
    multiple: true,
    minSelections,
    confirmLabel,
    sourceHint,
  }
}

function fallbackDynamicOptions(prefix: string, kindLabel: string) {
  return [
    { value: `${prefix}::未自动识别`, label: `当前样本里暂未自动识别出明确${kindLabel}` },
    { value: `${prefix}::需人工补充`, label: `需要人工补充${kindLabel}范围` },
  ]
}

export function rootOtherReasonNode(stepName: string): TreeNode {
  const logicCategory = questionLogicCategoryForStep(stepName)
  if (isMachiningLogicCategory(logicCategory)) {
    return {
      id: 'rule_reason_other',
      title: SHARED_QUESTION_TREE_TITLES.otherCaseConfirm,
      prompt: `如果“${stepName}”不属于前面的结构、尺寸或精度方向，请在下方备注里补充说明，再点这里确认。`,
      options: [
        { value: 'coverage_reason::other_manual', label: '已在备注中补充其他情况' },
      ],
    }
  }

  const { hidden } = rootReasonOptionsForStep(stepName)
  return {
    id: 'rule_reason_other',
    title: SHARED_QUESTION_TREE_TITLES.otherCaseConfirm,
    prompt: `如果“${stepName}”不属于前面优先展示的原因，更接近下面哪一种补充情况？`,
    options: hidden.map((value) => ({ value, label: ROOT_REASON_LABELS[value] })),
  }
}

export function reasonRootNode(stepName: string, profileText = stepName): TreeNode {
  const { family, options } = rootReasonOptionsForStep(profileText)
  const profile = questionProfileForStep(profileText)
  const logicCategory = questionLogicCategoryForStep(profileText)
  return {
    id: 'rule_reason_root',
    title: SHARED_QUESTION_TREE_TITLES.questionFollowup,
    prompt: isMachiningLogicCategory(logicCategory)
      ? `“${stepName}”这个工序存在的条件，主要依赖以下哪类工艺特征？`
      : (profile
        ? (rootPromptForStep(stepName, profileText) || profile.rootPrompt)
        : `系统先把“${stepName}”归到${coverageFamilyLabel(family)}里。请确认它未覆盖所有样本时，存在的条件主要依赖以下哪类因素？`),
    options,
  }
}

export function directEntryNode(stepName: string, profileText = stepName): TreeNode | null {
  const profile = questionProfileForStep(profileText)
  if (!profile?.directRootValue) return null
  if (isMachiningLogicCategory(questionLogicCategoryForStep(profileText))) return null
  const directNode = reasonFollowupNode(stepName, profile.directRootValue, profileText)
  if (!directNode) return null
  return {
    ...directNode,
    title: SHARED_QUESTION_TREE_TITLES.questionFollowup,
    prompt: rootPromptForStep(stepName, profileText) || profile.rootPrompt,
    impliedRootValue: profile.directRootValue,
  }
}

export function mergeRootNode(stepName: string, nameCandidates: () => string[]): TreeNode {
  return {
    id: 'merge_name_root',
    title: SHARED_QUESTION_TREE_TITLES.normalizedNameConfirm,
    prompt: mergeRootPromptForStep(stepName) || `请确认这组归并工序“${stepName}”以后统一使用哪个名称？`,
    options: nameCandidates().map((name, index) => ({
      value: `merge_name::${index}`,
      label: name,
    })).concat([{ value: 'other', label: '其他（请补充）' }]),
  }
}

export function reasonFollowupNode(stepName: string, rootValue: string, profileText = stepName): TreeNode | null {
  switch (rootValue) {
    case 'coverage_reason::material': {
      const materialTypeOptions = materialTypeOptionsForStep(profileText)
      return {
        id: 'material_basis_type',
        title: SHARED_QUESTION_TREE_TITLES.materialScopeConfirm,
        prompt: materialTypePromptForStep(stepName, profileText) || `“${stepName}”工序主要按哪类材料信息区分是否纳入路线？`,
        options: materialTypeOptions || [
          { value: 'material_basis::grade', label: '按材料牌号' },
          { value: 'material_basis::class', label: '按材料分类' },
        ],
      }
    }
    case 'coverage_reason::structure':
      return {
        id: 'structure_scene_type',
        title: SHARED_QUESTION_TREE_TITLES.structureFeatureConfirm,
        prompt: structureTypePromptForStep(stepName, profileText) || `“${stepName}”工序存在的条件，主要依赖以下哪类结构或特征差异触发？`,
        options: structureTypeOptionsForStep(profileText),
      }
    case 'coverage_reason::size':
      return {
        id: 'size_driver_type',
        title: SHARED_QUESTION_TREE_TITLES.sizeBoundaryConfirm,
        prompt: `“${stepName}”工序存在的条件，主要依赖以下哪类尺寸或尺度指标触发？`,
        options: sizeTypeOptionsForStep(profileText),
      }
    case 'coverage_reason::blank':
      return {
        id: 'blank_basis_type',
        title: SHARED_QUESTION_TREE_TITLES.blankMaterialConfirm,
        prompt: blankTypePromptForStep(stepName, profileText) || `“${stepName}”工序存在的条件，主要依赖以下哪类毛坯或来料状态差异触发？`,
        options: blankTypeOptionsForStep(profileText),
      }
    case 'coverage_reason::requirement': {
      const profile = questionProfileForStep(profileText)
      return {
        id: 'requirement_scene_type',
        title: SHARED_QUESTION_TREE_TITLES.requirementTypeConfirm,
        prompt: profile?.requirementTypePrompt || `“${stepName}”工序存在的条件，主要依赖以下哪类加工要求差异触发？`,
        options: requirementTypeOptionsForStep(profileText),
      }
    }
    case 'coverage_reason::multi':
      return {
        id: 'coverage_multi_pair',
        title: SHARED_QUESTION_TREE_TITLES.multiFactorConfirm,
        prompt: `如果不是单一因素决定，“${stepName}”工序最主要的两个触发条件是什么？`,
        options: [
          { value: 'multi::material+structure', label: '材质 + 结构' },
          { value: 'multi::material+size', label: '材质 + 尺寸' },
          { value: 'multi::material+requirement', label: '材质 + 要求' },
          { value: 'multi::structure+size', label: '结构 + 尺寸' },
          { value: 'multi::structure+requirement', label: '结构 + 要求' },
          { value: 'multi::other', label: '其他组合' },
        ],
      }
    case 'coverage_reason::uncertain':
      return {
        id: 'coverage_uncertain_missing',
        title: SHARED_QUESTION_TREE_TITLES.missingEvidenceConfirm,
        prompt: `当前需要判断“${stepName}”工序的触发条件，最缺少以下哪类信息？`,
        options: [
          { value: 'missing::material', label: '材质信息缺失' },
          { value: 'missing::structure', label: '结构信息缺失' },
          { value: 'missing::size', label: '尺寸信息缺失' },
          { value: 'missing::blank', label: '毛坯信息缺失' },
          { value: 'missing::requirement', label: '加工要求缺失' },
          { value: 'missing::sample', label: '样本数量不足' },
        ],
      }
    default:
      return null
  }
}

export function finalNode(stepName: string, rootValue: string): TreeNode | null {
  switch (rootValue) {
    case 'coverage_reason::multi':
      return {
        id: 'coverage_multi_primary',
        title: SHARED_QUESTION_TREE_TITLES.primaryFactorConfirm,
        prompt: `“${stepName}”工序在已选联合因素中，哪一类条件起主导作用？`,
        options: [
          { value: 'multi_primary::first', label: '前者是主因素' },
          { value: 'multi_primary::second', label: '后者是主因素' },
          { value: 'multi_primary::equal', label: '两者缺一不可' },
          { value: 'multi_primary::uncertain', label: '还不能确定' },
        ],
      }
    default:
      return null
  }
}

export function hasCoverageResolution(
  rootValue: string,
  answers: Record<string, TreeAnswer>,
  note = '',
) {
  const noteResolved = Boolean(String(note || '').trim())

  switch (rootValue) {
    case 'coverage_reason::material':
      return !!answers.material_scope_detail
    case 'coverage_reason::structure':
      if (answers.structure_feature_primary?.value === 'machining_feature::other_manual') return noteResolved
      return !!answers.structure_feature_primary || !!answers.structure_scene_type
    case 'coverage_reason::size':
      return !!answers.size_scope_detail
    case 'coverage_reason::blank':
      return !!answers.blank_scope_detail
    case 'coverage_reason::requirement':
      if (answers.requirement_scene_type?.value === 'precision_primary::other_manual') return noteResolved
      return !!answers.requirement_scope_detail
    case 'coverage_reason::multi':
      return !!answers.coverage_multi_primary
    case 'coverage_reason::uncertain':
      return !!answers.coverage_uncertain_missing
    case 'coverage_reason::other':
      return !!answers.rule_reason_other
    default:
      return false
  }
}

function cleanSummaryLabel(value?: string) {
  return String(value || '').trim().replace(/[。；;]+$/g, '')
}

function formatSummaryStep(value: string) {
  return `“${cleanSummaryLabel(value)}”`
}

function joinSummaryList(value: string) {
  return cleanSummaryLabel(value)
    .split(/[、|｜]/)
    .map(item => cleanSummaryLabel(item))
    .filter(Boolean)
    .join('、')
}

function buildApplySentence(targetStepName: string, conditionPhrase: string) {
  return buildFinalizeActionSentence(cleanSummaryLabel(targetStepName), cleanSummaryLabel(conditionPhrase))
}

function resolveMaterialConditionName(answers: Record<string, TreeAnswer>) {
  const basis = cleanSummaryLabel(answers.material_basis_type?.label)
  if (/技术条件|热处理/.test(basis)) return '热处理技术条件'
  if (/类别|分类|大类/.test(basis)) return '材料类别'
  if (/材料/.test(basis)) return '材料牌号'
  return '材料信息'
}

function normalizeStructureCondition(value: string) {
  return joinSummaryList(value)
    .split('、')
    .map((item) => {
      if (/^(孔|孔结构|一般孔|孔类特征)$/.test(item)) return '孔类结构或孔加工要求'
      if (/^(型孔|异形孔|异型孔)$/.test(item)) return '型孔或异形孔加工要求'
      if (/^(槽|槽类特征|一般槽|一般环槽)$/.test(item)) return '槽类结构'
      if (/^(外圆|主外圆|台阶外圆|基准外圆)$/.test(item)) return `${item}加工对象`
      if (/^(端面|平端面|基准端面|总长控制端面|装夹定位端面)$/.test(item)) return `${item}加工对象`
      if (/^(平面|扁位|削平面|铣扁)$/.test(item)) return `${item}加工对象`
      if (/^(倒角|孔口倒角|锐边|毛刺)$/.test(item)) return `${item}处理要求`
      return item
    })
    .filter(Boolean)
    .join('、')
}

function buildRequirementConditionPhrase(value: string, answers: Record<string, TreeAnswer>) {
  const detail = joinSummaryList(value)
  const scene = cleanSummaryLabel(answers.requirement_scene_type?.label)
  if (!detail) return ''
  const subject = scene
    .replace(/的/g, '')
    .replace(/要求$/, '要求')
    .trim()
  const formattedDetail = detail
    .replace(/\b(IT\d+)(及更高)?\b/g, (_match, grade, suffix) => suffix ? `${grade}及更高精度等级` : grade)
    .replace(/\b(Ra\d+(?:\.\d+)?)(及更高)?\b/gi, (_match, grade, suffix) => suffix ? `${grade}及更高表面质量` : grade)
  if (/尺寸精度/.test(scene)) return `${subject || '尺寸精度要求'}达到${formattedDetail}`
  if (/粗糙度|表面粗糙/.test(scene)) return `${subject || '表面粗糙度要求'}达到${formattedDetail}`
  if (/几何|形位|公差|同轴|圆度|圆柱度|跳动|位置度|平面度|垂直度/.test(scene)) {
    const base = (subject || '几何公差要求').replace(/要求$/, '')
    return `${base}需控制${formattedDetail}`
  }
  if (/配合|贴合|功能/.test(scene)) {
    if (/外圆/.test(scene)) return `该外圆为${formattedDetail}面`
    if (/孔/.test(scene)) return `该孔为${formattedDetail}孔`
    if (/端面/.test(scene)) return `该端面满足${formattedDetail}`
    if (/槽/.test(scene)) return `该槽满足${formattedDetail}`
    return `${subject || '配合或功能要求'}满足${formattedDetail}`
  }
  if (scene) return `${subject}满足${formattedDetail}`
  return `加工精度、表面质量或技术要求满足${formattedDetail}`
}

function buildMultiFactorCondition(answers: Record<string, TreeAnswer>) {
  const pair = cleanSummaryLabel(answers.coverage_multi_pair?.label)
  const primary = cleanSummaryLabel(answers.coverage_multi_primary?.label)
  return [pair, primary].filter(Boolean).join('，')
}

type SummarySentenceContext = {
  targetStepName: string
  rootValue?: string
  detailValue: string
  noteValue: string
  answers: Record<string, TreeAnswer>
}

function buildRootSummarySentence(context: SummarySentenceContext) {
  const { targetStepName, rootValue, detailValue, noteValue, answers } = context
  const targetStep = formatSummaryStep(targetStepName)
  const detailText = joinSummaryList(detailValue)
  const noteDetail = cleanSummaryLabel(noteValue)
  const preferredDetail = detailText || noteDetail
  switch (rootValue) {
    case 'coverage_reason::material':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? `${resolveMaterialConditionName(answers)}为${preferredDetail}` : '材料条件满足当前样本中的适用范围',
      )
    case 'coverage_reason::structure':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? `零件存在${normalizeStructureCondition(preferredDetail)}` : '零件结构或加工特征满足该工序适用条件',
      )
    case 'coverage_reason::size':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? `尺寸或尺度条件满足${preferredDetail}` : '尺寸边界达到该工序适用范围',
      )
    case 'coverage_reason::blank':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? `毛坯或来料状态为${preferredDetail}` : '毛坯或来料状态满足该工序适用条件',
      )
    case 'coverage_reason::requirement':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? buildRequirementConditionPhrase(preferredDetail, answers) : '加工要求达到该工序适用范围',
      )
    case 'coverage_reason::multi': {
      const condition = buildMultiFactorCondition(answers)
      return buildApplySentence(
        targetStepName,
        condition ? `${condition}共同决定路线安排` : '多类工艺因素共同满足适用条件',
      )
    }
    case 'coverage_reason::other':
      return buildApplySentence(
        targetStepName,
        preferredDetail ? `满足${preferredDetail}` : '满足已补充的特殊工艺条件',
      )
    case 'coverage_reason::uncertain':
      if (preferredDetail) return `${targetStep}工序的适用条件暂不能稳定确认，需补充${preferredDetail}后再定规则。`
      return `${targetStep}工序的适用条件暂不能稳定确认，需补充材料、结构、尺寸或要求等证据后再定规则。`
    default:
      if (preferredDetail) return buildApplySentence(targetStepName, `满足${preferredDetail}`)
      return `${targetStep}工序已完成当前判断，后续可按样本证据继续细化适用条件。`
  }
}

function resolveSummaryDetail(answers: Record<string, TreeAnswer>, note: string) {
  const filteredAnswers = Object.values(answers)
    .filter(answer => answer.nodeId !== 'merge_name_root' && answer.nodeId !== 'rule_reason_root')
  const detail = filteredAnswers.length ? filteredAnswers[filteredAnswers.length - 1] : undefined
  const detailLabel = cleanSummaryLabel(detail?.label)
  const noteText = cleanSummaryLabel(note)
  const shouldPreferNote = (
    !!noteText
    && (
      (detailLabel && /其他|需补充说明|未自动识别|人工补充/.test(detailLabel))
      || answers.rule_reason_root?.value === 'coverage_reason::other'
      || !!answers.rule_reason_other
    )
  )
  return {
    detailLabel,
    noteText,
    conditionDetail: shouldPreferNote ? noteText : detailLabel,
  }
}

export function buildResultSummary(stepName: string, answers: Record<string, TreeAnswer>, note = '') {
  const { detailLabel, noteText, conditionDetail } = resolveSummaryDetail(answers, note)
  const resolvedRoot = resolveAnsweredRootReason(answers)
  const root = answers.merge_name_root || resolvedRoot || answers.rule_reason_root
  if (!root) return ''
  if (root.nodeId === 'merge_name_root') {
    const mergedName = root.label || stepName
    const coverageRoot = resolvedRoot
    if (!coverageRoot) {
      return `建议将该组合工序统一命名为${formatSummaryStep(mergedName)}。`
    }
    return `建议将该组合工序统一命名为${formatSummaryStep(mergedName)}；${buildRootSummarySentence({
      targetStepName: mergedName,
      rootValue: coverageRoot.value,
      detailValue: conditionDetail,
      noteValue: noteText,
      answers,
    })}`
  }

  return buildRootSummarySentence({
    targetStepName: stepName,
    rootValue: root.value,
    detailValue: conditionDetail || detailLabel,
    noteValue: noteText,
    answers,
  })
}
