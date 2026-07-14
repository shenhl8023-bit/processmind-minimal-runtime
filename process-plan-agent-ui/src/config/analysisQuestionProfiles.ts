import {
  classifyCoverageOperationFamily,
  prioritizedCoverageReasons,
} from '@/config/paramQuestionStrategy'
import { normalizeCoverageReasonPriority } from '@/config/questionPriorityPolicy'
import { SHARED_STEP_QUESTION_PROFILE_BY_KEY } from '@/config/sharedStepQuestionProfiles'
import type {
  LocalStepQuestionProfile,
  QuestionLogicCategory,
  RootReasonValue,
  StepQuestionProfile,
  TreeOption,
} from '@/config/analysisQuestionProfileTypes'
import { HEAT_STEP_QUESTION_PROFILES } from '@/config/questionProfiles/heatProfiles'
import { HOLE_STEP_QUESTION_PROFILES } from '@/config/questionProfiles/holeProfiles'
import { PRECISION_STEP_QUESTION_PROFILES } from '@/config/questionProfiles/precisionProfiles'
import { SHAPE_STEP_QUESTION_PROFILES } from '@/config/questionProfiles/shapeProfiles'
import { SUPPORT_STEP_QUESTION_PROFILES } from '@/config/questionProfiles/supportProfiles'
import { buildCurrentProcessTriggerScopePrompt } from '@/config/sharedRulePromptTemplates'

export type { RootReasonValue, StepQuestionProfile, TreeOption } from '@/config/analysisQuestionProfileTypes'

function resolveStepPromptTemplate(prompt: string | undefined, stepName: string) {
  if (!prompt) return undefined
  return prompt.split('{{stepName}}').join(stepName)
}

function profileForPrompt(profileText: string) {
  return questionProfileForStep(profileText)
}

interface StepOptionRule {
  patterns?: RegExp[]
  families?: Array<ReturnType<typeof classifyCoverageOperationFamily>>
  options: TreeOption[]
}

export const ROOT_REASON_LABELS: Record<Exclude<RootReasonValue, 'coverage_reason::other'>, string> = {
  'coverage_reason::material': '与材料相关',
  'coverage_reason::structure': '与结构相关',
  'coverage_reason::size': '与尺寸相关',
  'coverage_reason::blank': '与毛坯或来料相关',
  'coverage_reason::requirement': '与工艺/质量要求相关',
  'coverage_reason::multi': '与多种因素共同相关',
  'coverage_reason::uncertain': '暂时无法判断',
}

export type ThirdStepLogicCategory = QuestionLogicCategory

export function questionLogicCategoryForStep(stepName: string): ThirdStepLogicCategory {
  const profile = questionProfileForStep(stepName)
  if (!profile) return 'generic'
  return profile.logicCategory || 'special'
}

export function isMachiningLogicCategory(category: ThirdStepLogicCategory) {
  return ['turning_coarse', 'turning_precision', 'milling_coarse', 'milling_precision'].includes(category)
}

export function isPrecisionLogicCategory(category: ThirdStepLogicCategory) {
  return ['turning_precision', 'milling_precision'].includes(category)
}

const STRUCTURE_OPTION_RULES: StepOptionRule[] = [
  {
    patterns: [/(倒角|倒圆|去毛刺|锐边)/],
    options: [
      { value: 'structure::step_face', label: '边缘/端部类特征' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    patterns: [/(清洗|检验|探伤)/],
    options: [
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    patterns: [/(端面|台阶|止口|肩部)/],
    options: [
      { value: 'structure::step_face', label: '台阶/端面类特征' },
      { value: 'structure::solid_hollow', label: '中空/实心差异' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    patterns: [/(外圆|车外形|车外圆|外形)/],
    options: [
      { value: 'structure::step_face', label: '外圆/台阶轮廓类特征' },
      { value: 'structure::solid_hollow', label: '中空/实心差异' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    families: ['turning_shape'],
    options: [
      { value: 'structure::step_face', label: '台阶/端面类特征' },
      { value: 'structure::solid_hollow', label: '中空/实心差异' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    families: ['hole_process'],
    options: [
      { value: 'structure::hole', label: '孔类特征' },
      { value: 'structure::thread', label: '螺纹类特征' },
      { value: 'structure::solid_hollow', label: '中空/实心差异' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
  {
    families: ['heat_treat'],
    options: [
      { value: 'structure::solid_hollow', label: '中空/实心差异' },
      { value: 'structure::other', label: '其他结构特征' },
    ],
  },
]

const DEFAULT_STRUCTURE_OPTIONS: TreeOption[] = [
  { value: 'structure::hole', label: '孔类特征' },
  { value: 'structure::slot', label: '槽类特征' },
  { value: 'structure::step_face', label: '台阶/端面类特征' },
  { value: 'structure::thread', label: '螺纹类特征' },
  { value: 'structure::solid_hollow', label: '中空/实心差异' },
  { value: 'structure::other', label: '其他结构特征' },
]

const SIZE_OPTION_RULES: StepOptionRule[] = [
  {
    patterns: [/(倒角|倒圆|去毛刺|锐边)/],
    options: [
      { value: 'size::diameter', label: '直径/边缘尺寸' },
      { value: 'size::length', label: '长度' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
  {
    patterns: [/(端面|台阶|止口|肩部)/],
    options: [
      { value: 'size::diameter', label: '端面直径' },
      { value: 'size::length', label: '长度/端面距' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
  {
    patterns: [/(外圆|车外形|车外圆|外形)/],
    options: [
      { value: 'size::diameter', label: '直径' },
      { value: 'size::length', label: '长度' },
      { value: 'size::ratio', label: '长径比' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
  {
    families: ['turning_shape'],
    options: [
      { value: 'size::diameter', label: '直径' },
      { value: 'size::length', label: '长度' },
      { value: 'size::section', label: '最大截面' },
      { value: 'size::ratio', label: '长径比' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
  {
    families: ['hole_process'],
    options: [
      { value: 'size::diameter', label: '直径/孔径' },
      { value: 'size::length', label: '长度/孔深' },
      { value: 'size::wall', label: '壁厚' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
  {
    families: ['heat_treat'],
    options: [
      { value: 'size::section', label: '最大截面' },
      { value: 'size::wall', label: '壁厚' },
      { value: 'size::ratio', label: '长径比' },
      { value: 'size::other', label: '其他尺寸' },
    ],
  },
]

const DEFAULT_SIZE_OPTIONS: TreeOption[] = [
  { value: 'size::diameter', label: '直径' },
  { value: 'size::length', label: '长度' },
  { value: 'size::wall', label: '壁厚' },
  { value: 'size::section', label: '最大截面' },
  { value: 'size::ratio', label: '长径比' },
  { value: 'size::other', label: '其他尺寸' },
]

const BLANK_OPTION_RULES: StepOptionRule[] = [
  {
    families: ['heat_treat'],
    options: [
      { value: 'blank::forging', label: '锻件' },
      { value: 'blank::bar', label: '棒料' },
      { value: 'blank::tube', label: '管料' },
      { value: 'blank::casting', label: '铸件' },
      { value: 'blank::other', label: '其他来料状态' },
    ],
  },
  {
    families: ['turning_shape', 'hole_process', 'surface_check', 'blank_prep'],
    options: [
      { value: 'blank::bar', label: '棒料' },
      { value: 'blank::tube', label: '管料' },
      { value: 'blank::forging', label: '锻件' },
      { value: 'blank::casting', label: '铸件' },
      { value: 'blank::purchased', label: '采购成品料' },
      { value: 'blank::other', label: '其他来料状态' },
    ],
  },
]

const DEFAULT_BLANK_OPTIONS: TreeOption[] = [
  { value: 'blank::bar', label: '棒料' },
  { value: 'blank::tube', label: '管料' },
  { value: 'blank::forging', label: '锻件' },
  { value: 'blank::casting', label: '铸件' },
  { value: 'blank::purchased', label: '采购成品料' },
  { value: 'blank::other', label: '其他来料状态' },
]

const REQUIREMENT_OPTION_RULES: StepOptionRule[] = [
  {
    patterns: [/(倒角|倒圆|去毛刺|锐边)/],
    options: [
      { value: 'requirement::surface', label: '表面质量要求' },
      { value: 'requirement::roughness', label: '粗糙度要求' },
      { value: 'requirement::other', label: '其他要求' },
    ],
  },
  {
    patterns: [/(清洗|检验|探伤)/],
    options: [
      { value: 'requirement::surface', label: '表面质量要求' },
      { value: 'requirement::performance', label: '热处理/性能要求' },
      { value: 'requirement::other', label: '其他要求' },
    ],
  },
  {
    families: ['turning_shape'],
    options: [
      { value: 'requirement::tolerance', label: '尺寸精度要求' },
      { value: 'requirement::gd&t', label: '形位公差要求' },
      { value: 'requirement::roughness', label: '粗糙度要求' },
      { value: 'requirement::surface', label: '表面质量要求' },
      { value: 'requirement::other', label: '其他要求' },
    ],
  },
  {
    families: ['hole_process'],
    options: [
      { value: 'requirement::tolerance', label: '尺寸精度要求' },
      { value: 'requirement::gd&t', label: '形位公差要求' },
      { value: 'requirement::roughness', label: '粗糙度要求' },
      { value: 'requirement::other', label: '其他要求' },
    ],
  },
  {
    families: ['heat_treat'],
    options: [
      { value: 'requirement::performance', label: '热处理/性能要求' },
      { value: 'requirement::tolerance', label: '尺寸精度要求' },
      { value: 'requirement::gd&t', label: '形位公差要求' },
      { value: 'requirement::other', label: '其他要求' },
    ],
  },
]

const DEFAULT_REQUIREMENT_OPTIONS: TreeOption[] = [
  { value: 'requirement::tolerance', label: '尺寸精度要求' },
  { value: 'requirement::roughness', label: '粗糙度要求' },
  { value: 'requirement::gd&t', label: '形位公差要求' },
  { value: 'requirement::surface', label: '表面质量要求' },
  { value: 'requirement::performance', label: '热处理/性能要求' },
  { value: 'requirement::other', label: '其他要求' },
]

const LOCAL_STEP_QUESTION_PROFILES: LocalStepQuestionProfile[] = [
  ...PRECISION_STEP_QUESTION_PROFILES,
  ...HOLE_STEP_QUESTION_PROFILES,
  ...HEAT_STEP_QUESTION_PROFILES,
  ...SHAPE_STEP_QUESTION_PROFILES,
  ...SUPPORT_STEP_QUESTION_PROFILES,
]

function applySharedQuestionProfile(profile: StepQuestionProfile): StepQuestionProfile {
  const shared = SHARED_STEP_QUESTION_PROFILE_BY_KEY.get(profile.key)
  if (!shared) return profile
  return {
    ...profile,
    directRootValue: (shared.directRootValue as RootReasonValue | undefined) ?? profile.directRootValue,
    rootPrompt: shared.rootPrompt,
    rootReasonOrder: shared.rootReasonOrder as Array<Exclude<RootReasonValue, 'coverage_reason::other' | 'coverage_reason::uncertain'>>,
  }
}

const STEP_QUESTION_PROFILES = LOCAL_STEP_QUESTION_PROFILES.map(({ pattern, profile }) => {
  const shared = SHARED_STEP_QUESTION_PROFILE_BY_KEY.get(profile.key)
  return {
    pattern: shared ? new RegExp(shared.pattern) : pattern,
    profile: applySharedQuestionProfile(profile),
  }
})

const STEP_QUESTION_PROFILE_BY_KEY = new Map(
  STEP_QUESTION_PROFILES.map(({ profile }) => [profile.key, profile] as const),
)

function inferQuestionProfileKeyBySignature(stepName: string): StepQuestionProfile['key'] | null {
  const text = String(stepName || '').trim()
  if (!text) return null

  const has = (pattern: RegExp) => pattern.test(text)
  const hasMethod = {
    grind: has(/(磨|研|珩|光整)/),
    turn: has(/(车|精车|粗车|半精车)/),
    hole: has(/(孔|镗|钻|铰|攻螺纹|攻丝|内圆)/),
    groove: has(/(槽|键槽|花键|环槽|退刀槽|越程槽)/),
    flat: has(/(扁|平面|对边|削平)/),
    face: has(/(端面|平端面)/),
    heat: has(/(热处理|调质|正常化|正火|淬火|真空淬火|渗氮|去应力|时效)/),
    surface: has(/(表面处理|镀铜|除铜|阳极化|钝化)/),
    inspect: has(/(检查|检验|探伤|磁粉|烧伤|裂纹|荧光|渗透)/),
    clean: has(/(清洗|去毛刺)/),
    mark: has(/(标印|打标|标记)/),
    package: has(/(包装|封存|防护包装)/),
    chamfer: has(/(倒角|倒圆|孔口倒角)/),
    profileHole: has(/(型孔|异形孔|打型孔|割型孔)/),
  }

  if (hasMethod.heat) {
    if (has(/\//) && has(/(调质|正常化|正火)/)) return 'heat_name_merge'
    if (has(/(终热处理|预热处理)/)) return 'heat_process_generic'
    if (/^(终热处理|预热处理|热处理)$/.test(text)) return 'heat_process_generic'
    if (/^(去应力|去应力退火|时效)$/.test(text)) return 'stress_relief_single'
    return 'heat_single'
  }
  if (hasMethod.surface) {
    if (/^表面处理$/.test(text)) return 'surface_treat_generic'
    return 'surface_treat_single'
  }
  if (hasMethod.inspect) {
    if (/^(检验|终检)$/.test(text)) return 'generic_inspection'
    return 'inspection_gate'
  }
  if (hasMethod.clean) return 'cleanup_stage'
  if (hasMethod.mark) return 'trace_mark'
  if (hasMethod.package) return 'package_release'
  if (hasMethod.chamfer) return 'chamfer_edge'
  if (hasMethod.profileHole) return 'profile_hole_process'
  if (has(/(研顶尖孔|研顶尖|修中心孔|精整中心孔)/)) return 'center_hole_process'
  if (hasMethod.face && hasMethod.grind) return 'face_grinding'
  if (hasMethod.groove && hasMethod.grind) return 'groove_grinding'
  if (hasMethod.groove) return 'groove_feature'
  if (hasMethod.flat) return 'flat_feature'
  if (hasMethod.hole && hasMethod.grind) return 'hole_grinding'
  if (has(/(攻螺纹|车螺纹|铣螺纹|套螺纹|螺纹加工)/)) return 'thread_process'
  if (hasMethod.hole) return 'hole_process_general'
  if (has(/(精车外圆|精车.*外圆|外圆精车|精车A侧外圆|精车B侧外圆)/)) return 'outer_finish_turning'
  if (has(/(磨外圆|研外圆|精磨外圆|外圆磨|无心磨)/)) return 'outer_grinding'
  if (has(/(车外圆|车外形|车零件|粗车外圆|半精车外圆|外圆车削|外形车削)/)) return 'outer_surface_general'
  return null
}

export function questionProfileForStep(stepName: string): StepQuestionProfile | null {
  const text = String(stepName || '').trim()
  if (!text) return null

  const candidates = Array.from(
    new Set(
      text
        .split(/\r?\n/)
        .map(part => String(part || '').trim())
        .filter(Boolean),
    ),
  )

  for (const candidate of candidates) {
    const explicitMatched = STEP_QUESTION_PROFILES.find(({ pattern }) => pattern.test(candidate))?.profile
    if (explicitMatched) return explicitMatched
  }

  const explicitMatched = STEP_QUESTION_PROFILES.find(({ pattern }) => pattern.test(text))?.profile
  if (explicitMatched) return explicitMatched

  const inferredFromWhole = inferQuestionProfileKeyBySignature(text)
  if (inferredFromWhole) return STEP_QUESTION_PROFILE_BY_KEY.get(inferredFromWhole) || null

  for (const candidate of candidates) {
    const inferredKey = inferQuestionProfileKeyBySignature(candidate)
    if (inferredKey) return STEP_QUESTION_PROFILE_BY_KEY.get(inferredKey) || null
  }

  return null
}

export function rootReasonOptionsForStep(stepName: string) {
  const family = classifyCoverageOperationFamily(stepName)
  const profile = questionProfileForStep(stepName)
  const logicCategory = questionLogicCategoryForStep(stepName)

  if (isMachiningLogicCategory(logicCategory)) {
    const machiningPreferred = isPrecisionLogicCategory(logicCategory)
      ? ['coverage_reason::requirement', 'coverage_reason::size', 'coverage_reason::structure']
      : ['coverage_reason::structure', 'coverage_reason::size', 'coverage_reason::requirement']

    const machiningLabels: Record<string, string> = {
      'coverage_reason::structure': '与结构相关',
      'coverage_reason::size': '与尺寸相关',
      'coverage_reason::requirement': '与精度相关',
      'coverage_reason::other': '其他',
    }

    return {
      family,
      preferred: machiningPreferred as Array<Exclude<RootReasonValue, 'coverage_reason::other' | 'coverage_reason::uncertain'>>,
      hidden: [] as Array<Exclude<RootReasonValue, 'coverage_reason::other'>>,
      options: [
        ...machiningPreferred.map((value) => ({
          value,
          label: machiningLabels[value] ?? ROOT_REASON_LABELS[value as Exclude<RootReasonValue, 'coverage_reason::other'>] ?? '其他',
        })),
        { value: 'coverage_reason::other' as const, label: machiningLabels['coverage_reason::other'] ?? '其他' },
      ] as TreeOption[],
    }
  }

  const preferred = normalizeCoverageReasonPriority(
    profile?.rootReasonOrder || prioritizedCoverageReasons(stepName),
    { profileKey: profile?.key, family },
  )
  const allReasons = Object.keys(ROOT_REASON_LABELS) as Array<Exclude<RootReasonValue, 'coverage_reason::other'>>
  const preferredSet = new Set<string>(preferred)
  const hidden = allReasons.filter(reason => !preferredSet.has(reason) && reason !== 'coverage_reason::uncertain')
  const allowLegacyOther = !profile

  return {
    family,
    preferred,
    hidden,
    options: [
      ...preferred.map((value) => ({ value, label: ROOT_REASON_LABELS[value] })),
      ...(allowLegacyOther && hidden.length ? [{ value: 'coverage_reason::other' as const, label: '其他原因' }] : []),
      { value: 'coverage_reason::uncertain' as const, label: ROOT_REASON_LABELS['coverage_reason::uncertain'] },
    ],
  }
}

function matchesStepOptionRule(text: string, family: ReturnType<typeof classifyCoverageOperationFamily>, rule: StepOptionRule) {
  if (rule.patterns?.some(pattern => pattern.test(text))) return true
  if (rule.families?.includes(family)) return true
  return false
}

function pickScopedStepOptions(
  stepName: string,
  rules: StepOptionRule[],
  fallback: TreeOption[],
): TreeOption[] {
  const family = classifyCoverageOperationFamily(stepName)
  const text = String(stepName || '').trim()
  const matched = rules.find(rule => matchesStepOptionRule(text, family, rule))
  return matched?.options || fallback
}

export function structureTypeOptionsForStep(stepName: string): TreeOption[] {
  const profileOptions = structureTypeOptionsForStepProfile(stepName)
  if (profileOptions) return profileOptions
  return pickScopedStepOptions(stepName, STRUCTURE_OPTION_RULES, DEFAULT_STRUCTURE_OPTIONS)
}

export function sizeTypeOptionsForStep(stepName: string): TreeOption[] {
  return pickScopedStepOptions(stepName, SIZE_OPTION_RULES, DEFAULT_SIZE_OPTIONS)
}

export function blankTypeOptionsForStep(stepName: string): TreeOption[] {
  const profile = questionProfileForStep(stepName)
  if (profile?.blankTypeOptions) return profile.blankTypeOptions
  return pickScopedStepOptions(stepName, BLANK_OPTION_RULES, DEFAULT_BLANK_OPTIONS)
}

export function requirementTypeOptionsForStep(stepName: string): TreeOption[] {
  const profile = questionProfileForStep(stepName)
  if (profile?.requirementTypeOptions) return profile.requirementTypeOptions
  return pickScopedStepOptions(stepName, REQUIREMENT_OPTION_RULES, DEFAULT_REQUIREMENT_OPTIONS)
}

export function requirementScopePromptForStep(stepName: string, requirementType?: string, profileText = stepName) {
  const profile = profileForPrompt(profileText)
  if (!profile) return undefined
  if (requirementType?.startsWith('precision_type::')) {
    if (requirementType === 'precision_type::tolerance') return buildCurrentProcessTriggerScopePrompt('尺寸精度档位或相关证据')
    if (requirementType === 'precision_type::roughness') return buildCurrentProcessTriggerScopePrompt('表面粗糙度档位或相关证据')
    if (requirementType === 'precision_type::gdt') return buildCurrentProcessTriggerScopePrompt('几何公差项目或相关证据')
  }
  if (requirementType && profile.requirementScopePromptsByType?.[requirementType]) {
    return resolveStepPromptTemplate(profile.requirementScopePromptsByType[requirementType], stepName)
  }
  return resolveStepPromptTemplate(profile.requirementScopePrompt, stepName)
}

export function rootPromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.rootPrompt, stepName)
}

export function mergeRootPromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.mergeRootPrompt, stepName)
}

export function mergeCoveragePromptForStep(stepName: string, selectedName: string, profileText = stepName) {
  const prompt = resolveStepPromptTemplate(profileForPrompt(profileText)?.mergeCoveragePrompt, stepName)
  return prompt?.replace('{{name}}', selectedName)
}

export function materialTypePromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.materialTypePrompt, stepName)
}

export function materialTypeOptionsForStep(stepName: string): TreeOption[] | null {
  return questionProfileForStep(stepName)?.materialTypeOptions || null
}

export function structureTypePromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.structureTypePrompt, stepName)
}

function structureTypeOptionsForStepProfile(stepName: string): TreeOption[] | null {
  return questionProfileForStep(stepName)?.structureTypeOptions || null
}

export function blankTypePromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.blankTypePrompt, stepName)
}

export function blankScopePromptForStep(stepName: string, profileText = stepName) {
  return resolveStepPromptTemplate(profileForPrompt(profileText)?.blankScopePrompt, stepName)
}

function mapGenericPrecisionTypeToLegacyRequirementTypes(profile: StepQuestionProfile, requirementType?: string) {
  if (!requirementType?.startsWith('precision_type::')) return requirementType ? [requirementType] : []
  const suffix = requirementType.replace('precision_type::', '')
  const mapping: Record<string, string[]> = {
    outer_grinding: suffix === 'tolerance'
      ? ['requirement_driver::outer_precision']
      : suffix === 'roughness'
        ? ['requirement_driver::outer_roughness']
        : ['requirement_driver::outer_gdt'],
    outer_finish_turning: suffix === 'tolerance'
      ? ['requirement_driver::turn_precision']
      : suffix === 'roughness'
        ? ['requirement_driver::turn_roughness']
        : ['requirement_driver::turn_gdt'],
    hole_grinding: suffix === 'tolerance'
      ? ['requirement_driver::hole_precision']
      : suffix === 'roughness'
        ? ['requirement_driver::hole_roughness']
        : ['requirement_driver::hole_gdt'],
    face_grinding: suffix === 'tolerance'
      ? ['requirement_driver::face_length']
      : suffix === 'roughness'
        ? ['requirement_driver::face_roughness']
        : ['requirement_driver::face_flatness'],
    groove_grinding: suffix === 'tolerance'
      ? ['requirement_driver::groove_precision']
      : suffix === 'roughness'
        ? ['requirement_driver::groove_roughness']
        : ['requirement_driver::groove_gdt'],
  }
  return mapping[profile.key] || []
}

export function buildThresholdRequirementScopeOptions(
  profile: StepQuestionProfile,
  texts: string[],
  requirementType?: string,
): TreeOption[] {
  const joined = texts.join('\n')
  const options: TreeOption[] = []
  const mappedRequirementTypes = mapGenericPrecisionTypeToLegacyRequirementTypes(profile, requirementType)
  const fallbackOptions = (
    requirementType
      ? profile.requirementScopeFallbacksByType?.[requirementType]
      : null
  ) || mappedRequirementTypes.flatMap((type) => profile.requirementScopeFallbacksByType?.[type] || []) || profile.requirementScopeFallbacks || []

  const push = (value: string, label: string) => {
    if (options.some(option => option.label === label)) return
    options.push({ value, label })
  }

  const matchesRequirementType = (...allowedTypes: string[]) => {
    if (!requirementType) return true
    if (allowedTypes.includes(requirementType)) return true
    return mappedRequirementTypes.some(type => allowedTypes.includes(type))
  }
  const pushPrecisionGradeOptions = (
    prefix: string,
    allowedLevels: number[],
    scopedFallbackOptions: Array<{ value: string; label: string }> = [],
    minCount = 3,
  ) => {
    const matchedLevels = new Set<number>()
    const patterns = [
      /\bIT\s*([0-9]{1,2})\b/gi,
      /精度等级[^。\n]{0,12}([0-9]{1,2})级/g,
      /([0-9]{1,2})级/g,
    ]
    patterns.forEach((pattern) => {
      pattern.lastIndex = 0
      let match: RegExpExecArray | null
      while ((match = pattern.exec(joined)) !== null) {
        const level = Number(match[1] || 0)
        if (allowedLevels.includes(level)) matchedLevels.add(level)
      }
    })

    Array.from(matchedLevels)
      .sort((a, b) => a - b)
      .forEach((level) => {
        push(`${prefix}::IT${level}`, `IT${level} 精度等级`)
      })

    scopedFallbackOptions.forEach((option, index) => {
      if (options.length >= minCount) return
      push(option.value || `${prefix}::fallback_${index}`, option.label)
    })
  }

  if (profile.key === 'outer_grinding') {
    if (matchesRequirementType('requirement_driver::outer_precision')) {
      pushPrecisionGradeOptions(
        'requirement_scope::outer_precision_grade',
        [5, 6, 7],
        [
          { value: 'requirement_scope::outer_precision_grade::IT7', label: 'IT7 精度等级' },
          { value: 'requirement_scope::outer_precision_grade::IT6', label: 'IT6 精度等级' },
          { value: 'requirement_scope::outer_precision_grade::IT5+', label: 'IT5 及更高精度等级' },
        ],
      )
    }
    if (matchesRequirementType('requirement_driver::outer_gdt') && /(圆度|圆柱度|跳动|同轴度|位置度)/.test(joined)) {
      push('requirement_scope::outer_gdt', '圆度、圆柱度或跳动要求较高')
    }
    if (matchesRequirementType('requirement_driver::outer_roughness') && /(?:Ra\s*(?:1\.6|0\.8|0\.4|0\.2)|粗糙度|表面质量|光整|光洁度)/i.test(joined)) {
      push('requirement_scope::outer_roughness', '粗糙度要求达到 Ra1.6 或更高表面质量')
    }
    if (matchesRequirementType('requirement_driver::outer_heat_finish') && /(淬火|真空淬火|渗氮|热处理|热后|磨前)/.test(joined)) {
      push('requirement_scope::outer_heat_finish', '前面有热处理，需要热后精整恢复尺寸和形位')
    }
    if (matchesRequirementType('requirement_driver::outer_fit') && /(配合|定尺寸|密封面|贴合面)/.test(joined)) {
      push('requirement_scope::outer_fit', '该外圆属于关键配合面或定尺寸面')
    }
  }

  if (profile.key === 'face_grinding') {
    if (matchesRequirementType('requirement_driver::face_flatness') && /(平面度|垂直度|端面跳动|跳动)/.test(joined)) {
      push('requirement_scope::face_flatness', '端面平面度、垂直度或端面跳动要求较高')
    }
    if (matchesRequirementType('requirement_driver::face_length') && /(端面距|总长|尺寸链|长度控制)/.test(joined)) {
      push('requirement_scope::face_length', '端面距、总长或尺寸链控制要求较高')
    }
    if (matchesRequirementType('requirement_driver::face_roughness') && /(Ra1\.6|Ra0\.8|贴合|密封|端面粗糙度|表面质量)/.test(joined)) {
      push('requirement_scope::face_roughness', '端面粗糙度或贴合表面质量要求较高')
    }
    if (matchesRequirementType('requirement_driver::face_heat_finish') && /(热处理|淬火后|热后|精整)/.test(joined)) {
      push('requirement_scope::face_heat_finish', '热处理后需要磨端面恢复尺寸和贴合状态')
    }
  }

  if (profile.key === 'outer_finish_turning') {
    if (matchesRequirementType('requirement_driver::turn_precision')) {
      pushPrecisionGradeOptions(
        'requirement_scope::turn_precision_grade',
        [8, 9, 10, 11, 12],
        [
          { value: 'requirement_scope::turn_precision_grade::IT9', label: 'IT9 精度等级' },
          { value: 'requirement_scope::turn_precision_grade::IT8', label: 'IT8 精度等级' },
          { value: 'requirement_scope::turn_precision_grade::IT7+', label: 'IT7 及更高精度等级' },
        ],
      )
    }
    if (matchesRequirementType('requirement_driver::turn_fit') && /(配合|定尺寸|基准外圆|关键外圆)/.test(joined)) {
      push('requirement_scope::turn_fit', '属于关键配合外圆或定尺寸外圆')
    }
    if (matchesRequirementType('requirement_driver::turn_roughness') && /(?:Ra\s*(?:3\.2|1\.6|0\.8)|粗糙度|表面质量)/i.test(joined)) {
      push('requirement_scope::turn_roughness', '粗糙度要求已高于半精车稳定能力')
    }
    if (matchesRequirementType('requirement_driver::turn_gdt') && /(同轴度|跳动|圆度|圆柱度)/.test(joined)) {
      push('requirement_scope::turn_gdt', '同轴度、跳动等形位要求已明显提高')
    }
  }

  if (profile.key === 'hole_grinding') {
    if (matchesRequirementType('requirement_driver::hole_precision')) {
      pushPrecisionGradeOptions(
        'requirement_scope::hole_precision_grade',
        [5, 6, 7],
        [
          { value: 'requirement_scope::hole_precision_grade::IT7', label: 'IT7 精度等级' },
          { value: 'requirement_scope::hole_precision_grade::IT6', label: 'IT6 精度等级' },
          { value: 'requirement_scope::hole_precision_grade::IT5+', label: 'IT5 及更高精度等级' },
        ],
      )
    }
    if (matchesRequirementType('requirement_driver::hole_gdt') && /(圆度|圆柱度|位置度|同轴度|跳动)/.test(joined)) {
      push('requirement_scope::hole_gdt', '孔圆度、圆柱度或位置精度要求较高')
    }
    if (matchesRequirementType('requirement_driver::hole_fit') && /(配合|定尺寸|配合孔|导向孔)/.test(joined)) {
      push('requirement_scope::hole_fit', '该孔属于关键配合孔或定尺寸孔')
    }
    if (matchesRequirementType('requirement_driver::hole_roughness') && /(?:Ra\s*(?:1\.6|0\.8|0\.4|0\.2)|粗糙度|表面质量|光整|光洁度)/i.test(joined)) {
      push('requirement_scope::hole_roughness', '孔表面粗糙度要求较高，需要进一步光整')
    }
  }

  if (profile.key === 'inspection_gate') {
    if (/(车削后|车后|周边加工后|过程检验|中间检验)/.test(joined)) {
      push('requirement_scope::process_check', '用于车削后或周边加工后的过程检验')
    }
    if (/(淬火|烧伤)/.test(joined)) {
      push('requirement_scope::burn_check', '用于淬火后烧伤风险检查')
    }
    if (/(磁粉|裂纹|荧光|无损)/.test(joined)) {
      push('requirement_scope::ndt_mt', '用于磁粉、裂纹等专项无损检测')
    }
    if (/(渗氮|渗透检验|表面缺陷)/.test(joined)) {
      push('requirement_scope::penetrant', '用于渗氮后渗透检验或表面缺陷检查')
    }
    if (/(终检|最终检验|交付|完工)/.test(joined)) {
      push('requirement_scope::final_check', '用于终检或交付前综合检验')
    }
  }

  if (profile.key === 'end_face_role') {
    if (/(总长|端面距|保证总长)/.test(joined)) {
      push('requirement_scope::length_control', '需要控制总长、端面距或相关尺寸链')
    }
    if (/(平面度|垂直度|跳动)/.test(joined)) {
      push('requirement_scope::perpendicularity', '需要保证平面度、垂直度或端面跳动')
    }
    if (/(贴合|密封|配合端面)/.test(joined)) {
      push('requirement_scope::assembly_fit', '需要满足装配贴合、密封或贴靠要求')
    }
  }

  if (profile.key === 'groove_feature') {
    if (/(槽宽|槽深|公差|配合尺寸)/.test(joined)) {
      push('requirement_scope::fit_groove', '需要控制槽宽、槽深或相关配合尺寸')
    }
    if (/(密封|卡簧|限位)/.test(joined)) {
      push('requirement_scope::seal_function', '需要满足密封、卡簧或限位功能')
    }
    if (/(传动|定位|联接|键|花键)/.test(joined)) {
      push('requirement_scope::transmission', '需要满足传动、定位或联接功能')
    }
  }

  if (profile.key === 'flat_feature') {
    if (/(对边|宽度|尺寸|平面尺寸|削平)/.test(joined)) {
      push('requirement_scope::flat_size', '需要控制对边尺寸、平面尺寸或平面余量')
    }
    if (/(定位|检测|装夹|基准平面)/.test(joined)) {
      push('requirement_scope::flat_datum', '需要建立定位、检测或装夹基准平面')
    }
    if (/(让位|避让|清根|局部清根)/.test(joined)) {
      push('requirement_scope::flat_clearance', '需要满足让位、避让或局部清根')
    }
  }

  if (profile.key === 'heat_single') {
    if (/(硬度|HRC|强度|组织)/.test(joined)) {
      push('requirement_scope::hardness', '主要由硬度、强度或组织性能目标驱动')
    }
    if (/(去应力|消除应力|稳定尺寸|尺寸稳定)/.test(joined)) {
      push('requirement_scope::stress_relief', '主要由消除应力、控制变形或稳定尺寸驱动')
    }
    if (/(渗氮|表面强化|热后|硬态精加工|淬火后)/.test(joined)) {
      push('requirement_scope::surface_heat', '主要由表面强化或后续硬态精加工链驱动')
    }
  }

  if (profile.key === 'hole_process_general') {
    if (/(孔径|孔深|孔位|位置度|垂直度|同轴度)/.test(joined)) {
      push('requirement_scope::hole_precision', '需要控制孔径、孔深或孔位精度')
    }
    if (/(配合孔|导向孔|定尺寸孔|配合)/.test(joined)) {
      push('requirement_scope::hole_fit', '需要满足配合孔、导向孔或定尺寸孔要求')
    }
    if (/(排屑|可达性|双向加工|让刀|钻镗|反向)/.test(joined)) {
      push('requirement_scope::hole_access', '需要满足排屑、可达性或双向加工边界')
    }
  }

  if (profile.key === 'package_release') {
    if (/(交付|转运|入库|发运|终检后)/.test(joined)) {
      push('requirement_scope::delivery', '主要用于终检后交付、转运或入库')
    }
    if (/(防锈|防碰伤|保护|涂油|防护包装)/.test(joined)) {
      push('requirement_scope::surface_protect', '主要用于防锈、防碰伤或表面保护')
    }
    if (/(标识|配套|交接|装箱单|包装前)/.test(joined)) {
      push('requirement_scope::trace_release', '主要用于包装前标识、配套或交接')
    }
  }

  if (profile.key === 'surface_treat_single') {
    if (/(防护|防腐|绝缘|稳定性|钝化|阳极化)/.test(joined)) {
      push('requirement_scope::surface_protect', '主要用于防护、防腐蚀、绝缘或表面稳定性处理')
    }
    if (/(镀铜|屏蔽|局部保护|选择性处理|渗氮前)/.test(joined)) {
      push('requirement_scope::process_masking', '主要用于渗氮、选择性处理或局部屏蔽辅助')
    }
    if (/(除铜|返工|后续处理|清除辅助层)/.test(joined)) {
      push('requirement_scope::surface_chain', '主要用于后续表面处理链、返工链或清除辅助层')
    }
  }

  if (profile.key === 'center_hole_process') {
    if (/(跳动|同轴度|重复精度|回转)/.test(joined)) {
      push('requirement_scope::center_runout', '需要控制回转跳动、同轴度或装夹重复精度')
    }
    if (/(转序|多次装夹|热后再定位|重新定位)/.test(joined)) {
      push('requirement_scope::center_transfer', '需要满足多次装夹转序或热后再定位')
    }
    if (/(修复|磨损|损伤|顶尖孔修整)/.test(joined)) {
      push('requirement_scope::center_repair', '需要修复中心孔磨损、损伤或精度状态')
    }
  }

  if (profile.key === 'cleanup_stage') {
    if (/(车削后|加工后|周边加工后|去毛刺)/.test(joined)) {
      push('requirement_scope::after_turning', '主要安排在车削或机械加工后做清理')
    }
    if (/(检查前|检验前|专项检查前)/.test(joined)) {
      push('requirement_scope::before_check', '主要安排在检验或专项检查前做清理')
    }
    if (/(热处理后|渗氮后|表面处理后|除铜后)/.test(joined)) {
      push('requirement_scope::after_special', '主要安排在热处理、渗氮或表面处理后做清理')
    }
    if (/(终检前|交付前|最终清洗)/.test(joined)) {
      push('requirement_scope::before_release', '主要安排在终检前或交付前做最终清理')
    }
  }

  if (profile.key === 'trace_mark') {
    if (/(追溯|编号|序号|批次)/.test(joined)) {
      push('requirement_scope::trace', '主要用于零件追溯、编号或批次标识')
    }
    if (/(装配|方向|安装位置|配对)/.test(joined)) {
      push('requirement_scope::assembly', '主要用于装配方向、安装位置或配对标识')
    }
    if (/(状态|热处理状态|检验状态|工艺状态)/.test(joined)) {
      push('requirement_scope::process', '主要用于工艺状态、热处理状态或检验状态标识')
    }
  }

  if (!options.length) {
    fallbackOptions.forEach((option: TreeOption) => {
      if (options.length >= Math.max(4, fallbackOptions.length)) return
      push(option.value, option.label)
    })
  }

  return options
}

export function buildProfileStructureScopeOptions(
  profile: StepQuestionProfile,
  texts: string[],
): TreeOption[] {
  const joined = texts.join('\n')
  const options: TreeOption[] = []
  const fallbackOptions = profile.structureScopeFallbacks || []

  const push = (value: string, label: string) => {
    if (options.some(option => option.label === label)) return
    options.push({ value, label })
  }

  if (profile.key === 'chamfer_edge') {
    if (/(锐边|毛刺|倒角|倒圆|边缘过渡)/.test(joined)) {
      push('structure_scope::sharp_edge', '主要是在去除锐边、毛刺或做边缘过渡')
    }
    if (/(孔口|导入|孔口倒角)/.test(joined)) {
      push('structure_scope::hole_entry', '主要是在处理孔口导入或孔口倒角')
    }
    if (/(装配|导向|防划伤|防磕碰)/.test(joined)) {
      push('structure_scope::assembly_entry', '主要是在满足装配导入或防划伤要求')
    }
    if (/(密封|贴合|保护边缘)/.test(joined)) {
      push('structure_scope::seal_edge', '主要是在保护密封口或贴合边缘')
    }
  }

  if (profile.key === 'end_face_role') {
    if (/(基准|定位)/.test(joined)) {
      push('structure_scope::datum_face', '主要是在建立基准端面或定位端面')
    }
    if (/(贴合|配合端面|密封)/.test(joined)) {
      push('structure_scope::fit_face', '主要是在形成贴合端面或配合端面')
    }
    if (/(孔口|沉台)/.test(joined)) {
      push('structure_scope::hole_mouth_face', '主要是在处理孔口端面或沉台端面')
    }
    if (/(总长|端面距)/.test(joined)) {
      push('structure_scope::length_face', '主要是在控制总长或关键端面距')
    }
  }

  if (profile.key === 'groove_feature') {
    if (/(退刀槽|越程槽|让刀槽)/.test(joined)) {
      push('structure_scope::relief_groove', '主要是在加工退刀槽、越程槽或让刀槽')
    }
    if (/(密封槽|卡簧槽)/.test(joined)) {
      push('structure_scope::seal_groove', '主要是在加工密封槽、卡簧槽或功能环槽')
    }
    if (/(键槽|花键|传动槽)/.test(joined)) {
      push('structure_scope::key_slot', '主要是在加工键槽、花键槽或传动槽')
    }
    if (/(环槽|内环槽|外环槽|凹槽|车槽|切槽)/.test(joined)) {
      push('structure_scope::common_ring_groove', '主要是在加工一般内外环槽或局部凹槽')
    }
  }

  if (profile.key === 'flat_feature') {
    if (/(防转|夹持|装夹平面)/.test(joined)) {
      push('structure_scope::anti_rotation_flat', '主要是在加工防转扁位、夹持扁位或装夹平面')
    }
    if (/(对边|削平|外形平面|扁位)/.test(joined)) {
      push('structure_scope::across_flat', '主要是在控制对边尺寸、局部削平或外形平面')
    }
    if (/(定位|检测|基准平面)/.test(joined)) {
      push('structure_scope::datum_flat', '主要是在建立定位平面、检测平面或工艺基准平面')
    }
    if (/(让位|避让|清根)/.test(joined)) {
      push('structure_scope::clearance_flat', '主要是在加工让位平面、避让平面或局部清根平面')
    }
  }

  if (profile.key === 'center_hole_process') {
    if (/(定位|装夹|基准中心孔)/.test(joined)) {
      push('structure_scope::center_datum', '主要是在建立装夹定位中心孔或回转基准中心孔')
    }
    if (/(转序|粗加工后|修中心孔)/.test(joined)) {
      push('structure_scope::center_transfer', '主要是在粗加工后修复或转序使用中心孔')
    }
    if (/(高精度|顶尖孔|中心孔精整)/.test(joined)) {
      push('structure_scope::center_precision', '主要是在做高精度顶尖孔或中心孔精整')
    }
    if (/(损伤|偏摆|重复装夹误差)/.test(joined)) {
      push('structure_scope::center_protect', '主要是在避免中心孔损伤、偏摆或重复装夹误差')
    }
  }

  if (profile.key === 'outer_surface_general') {
    if (/(主外圆|外圆|外形|回转)/.test(joined)) {
      push('structure_scope::main_outer', '主要是在加工主外圆或回转主形面')
    }
    if (/(台阶|轴肩|局部轮廓)/.test(joined)) {
      push('structure_scope::step_outer', '主要是在加工台阶外圆、轴肩或局部轮廓外圆')
    }
    if (/(基准|定位|检测基准)/.test(joined)) {
      push('structure_scope::datum_outer', '主要是在建立定位基准外圆或检测基准外圆')
    }
    if (/(配合|定尺寸|贴合)/.test(joined)) {
      push('structure_scope::fit_outer', '主要是在加工关键配合外圆或定尺寸外圆')
    }
  }

  if (profile.key === 'hole_process_general') {
    if (/(通孔|普通孔|一般孔)/.test(joined)) {
      push('structure_scope::through_hole', '主要是在加工通孔、普通孔或一般孔结构')
    }
    if (/(深孔|长孔|可达性受限)/.test(joined)) {
      push('structure_scope::deep_hole', '主要是在加工深孔、长孔或可达性受限孔')
    }
    if (/(中心孔|定位孔|装夹基准孔)/.test(joined)) {
      push('structure_scope::center_hole', '主要是在加工中心孔、定位孔或装夹基准孔')
    }
    if (/(阶梯孔|复合孔|孔口|沉台)/.test(joined)) {
      push('structure_scope::compound_hole', '主要是在加工阶梯孔、复合孔或带孔口特征的孔')
    }
  }

  fallbackOptions.forEach((option: TreeOption) => {
    if (options.length >= Math.max(4, fallbackOptions.length)) return
    push(option.value, option.label)
  })

  return options
}

export function buildProfileBlankScopeOptions(
  profile: StepQuestionProfile,
  texts: string[],
): TreeOption[] {
  const joined = texts.join('\n')
  const options: TreeOption[] = []
  const fallbackOptions = profile.blankScopeFallbacks || []

  const push = (value: string, label: string) => {
    if (options.some(option => option.label === label)) return
    options.push({ value, label })
  }

  if (profile.key === 'prep_single') {
    if (/(棒料|管料|型材)/.test(joined)) {
      push('blank_scope::bar', '主要由棒料、管料或型材来料驱动')
    }
    if (/(锻件|铸件|毛坯)/.test(joined)) {
      push('blank_scope::forging', '主要由锻件、铸件或近净成形毛坯驱动')
    }
    if (/(采购|成品料|半成品)/.test(joined)) {
      push('blank_scope::purchased', '主要由采购成品料或半成品来料驱动')
    }
    if (/(下料|切断|定尺|锯料)/.test(joined)) {
      push('blank_scope::cutting', '主要由按图下料、定尺切断或预下料方式驱动')
    }
  }

  fallbackOptions.forEach((option: TreeOption) => {
    if (options.length >= Math.max(4, fallbackOptions.length)) return
    push(option.value, option.label)
  })

  return options
}
