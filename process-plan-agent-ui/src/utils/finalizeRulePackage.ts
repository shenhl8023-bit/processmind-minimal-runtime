import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import type {
  CanonicalConditionField,
  CompileRulePackageRequest,
  ProcessRelationType,
  RulePackageCondition,
  RulePackageProcessRelation,
  RulePackageRule,
  RuleConditionCandidate,
  StandardFactorDefinition,
} from '@/api/rulePackages'
import type { TemplateGroupAliasBinding } from '@/api'
import {
  factorBindingState,
  matchingStandardFactors,
  ruleConfirmationSignature,
} from '@/utils/standardFactorBindings'

export class FinalizeRulePackageBuildError extends Error {
  readonly sourceSegmentId: string

  constructor(message: string, sourceSegmentId: string) {
    super(message)
    this.name = 'FinalizeRulePackageBuildError'
    this.sourceSegmentId = sourceSegmentId
  }
}

export function normalizeExportProcessName(name: string) {
  const text = String(name || '').trim()
  if (/真空淬火|淬火/.test(text)) return '淬火'
  return text
}

export function isMainlineFinalizeCard(item: any) {
  const coverage = item.segment?.doc_coverage
  if (coverage?.total_docs && coverage.hit_docs === coverage.total_docs) return true
  if ((item.factorNames || []).includes('always=true')) return true
  return /全部样本中稳定出现|标准主线工序|主线工序保留/.test(String(item.conditionText || ''))
}

export function isExplicitMainlineInstruction(value: string) {
  const text = String(value || '').trim()
  if (!text || /(?:可选|视情况|按需|条件满足|不一定|可能)/.test(text)) return false
  return /(?:主工序|主线工序|基础工序|固定工序|必经工序).{0,12}(?:保留|固定|不参与条件|始终|无条件|默认|必经)/.test(text)
    || /(?:设为|设置为|设定为|指定为|作为|标记为|固定为|保留为|调整为|改为).{0,12}(?:主工序|主线工序|基础工序|固定工序|必经工序)/.test(text)
    || /(?:该|此|本)?(?:工序|步骤).{0,10}(?:为|属于|作为).{0,10}(?:主工序|主线工序|基础工序|固定工序|必经工序)/.test(text)
}

export type FinalizeRuleMode = 'mainline' | 'conditional' | 'relation' | 'unresolved'

export function isProcessRelationConditionText(value: string) {
  const text = String(value || '').trim()
  if (!text) return false
  return /(?:后|之后|完成后).{0,80}(?:安排|设置|纳入|加入|添加|增加|出现|检查|释放|进行|执行|实施|处理)/.test(text)
    || /(?:存在|出现).{1,30}工序(?:时|后|之后|的情况下).{0,60}(?:安排|设置|纳入|加入|添加|增加|出现|检查|释放|进行|执行|实施|处理)/.test(text)
    || /(?:前面|此前|之前).{0,30}(?:有|存在|出现).{0,60}(?:安排|设置|纳入|加入|添加|增加|出现|检查|释放|进行|执行|实施|处理)/.test(text)
    || /(?:必须在|应在).{1,40}(?:后|之后)|不得早于/.test(text)
    || /(?:前|之前).{0,20}(?:必须|需要).{0,20}(?:完成|存在|经过)|依赖于|以前置/.test(text)
    || /不能同时|不得同时|互斥|二选一|不可共存/.test(text)
}

export function isActionableConditionText(value: string) {
  const text = String(value || '').trim()
  if (!text) return false
  if (/追溯|编号|批次.{0,6}标识|标识需求/.test(text)) return true
  if (/(?:防护|防腐蚀|绝缘|表面稳定性|表面处理)/.test(text) && /(?:当|如果|若).*(?:纳入|安排|设置|排除|不纳入)/.test(text)) return true
  if (/^当(.{4,45})满足\1(?:时|，)/.test(text)) return false
  const concretePatterns = [
    /IT\s*\d+/i,
    /(?:Ra|粗糙度)[^\d]{0,8}\d/i,
    /(?:材料|材质|牌号)[为是：:\s]*[A-Za-z0-9]/,
    /(?:HRC|硬度)[^\d]{0,8}\d/i,
    /(?:圆度|圆柱度|同轴度|同心度|跳动|位置度|平面度|垂直度)[^\d]{0,12}\d/,
    /存在(?:扁位|平面|槽|普通孔|辅助孔|铰孔|精孔|型孔|顶尖孔|内孔|通孔|中心孔|花键|键)/,
    /(?:渗氮层|铬酸阳极化|硬质阳极化|追溯标印|磁粉检查|烧伤检查)(?:要求|需求)?/,
  ]
  if (concretePatterns.some(pattern => pattern.test(text))) return true
  const vague = /不同结构类型|部分结构|根据.{0,8}决定|视情况|工艺安排存在差异|要求较高|会影响该工序|满足.{1,20}满足/
  return !vague.test(text) && /(?:当|如果|若).*(?:纳入|安排|设置|排除|不纳入)/.test(text)
}

export function finalizeRuleMode(item: any): FinalizeRuleMode {
  if (isExplicitMainlineInstruction(item.conditionText)) return 'mainline'
  if (isMainlineFinalizeCard(item) && !item.edited) return 'mainline'
  if (isProcessRelationConditionText(item.conditionText)) return 'relation'
  return isActionableConditionText(item.conditionText) ? 'conditional' : 'unresolved'
}

export function isMainlineRule(item: any) {
  return finalizeRuleMode(item) === 'mainline'
}

export function requiresConfirmedUserRule(item: any) {
  return finalizeRuleMode(item) !== 'mainline'
}

export function hasCurrentConfirmedUserRule(item: any, registryVersion?: string) {
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  const currentRegistryVersion = registryVersion ?? review?.field_registry_version ?? ''
  return Boolean(
    review?.status === 'confirmed'
    && review?.candidate
    && review?.confirmed
    && String(review.source_text || '').trim() === String(item.conditionText || '').trim()
    && (!registryVersion || review.field_registry_version === registryVersion)
    && (review.candidate.kind || 'condition') === expectedKind
    && (review.confirmed.kind || 'condition') === expectedKind
    && ruleConfirmationSignature(review.candidate, review.source_text, currentRegistryVersion)
      === ruleConfirmationSignature(review.confirmed, review.source_text, currentRegistryVersion)
  )
}

export function needsFinalizeRuleReview(item: any, registryVersion?: string) {
  return requiresConfirmedUserRule(item)
    && !hasCurrentConfirmedUserRule(item, registryVersion)
}

const ADVISORY_PARSE_ISSUE_PATTERNS = [
  /^AI 返回的规则结构未通过格式校验，已尝试使用本地解析器。$/,
  /^已使用内置规则解析器生成候选结果，请重点核对。$/,
  /^模型候选与明确的工序关系语义不一致，已改用关联工序候选。$/,
  /^模型候选与明确的特殊要求语义不一致，已改用特殊要求候选。$/,
]

export function isAdvisoryParserIssue(issue: unknown) {
  const text = String(issue || '').trim()
  return Boolean(text) && ADVISORY_PARSE_ISSUE_PATTERNS.some(pattern => pattern.test(text))
}

export function isSafeForBatchRuleConfirmation(
  item: any,
  factors: StandardFactorDefinition[] = [],
  registryVersion = '',
) {
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  const issues = Array.isArray(review?.issues) ? review.issues : []
  const hasOnlyAdvisoryFallbackIssues = issues.length > 0 && issues.every(isAdvisoryParserIssue)
  const confidence = Number(review?.confidence || 0)
  const candidateKind = review?.candidate?.kind || 'condition'
  const completeBinding = candidateKind === 'process_relation'
    || Boolean(review?.candidate?.when && factorBindingState(review.candidate.when, factors).complete)
  return Boolean(
    review?.status === 'pending_confirmation'
    && review?.candidate
    && String(review.source_text || '').trim() === String(item.conditionText || '').trim()
    && candidateKind === expectedKind
    && Boolean(registryVersion)
    && review.field_registry_version === registryVersion
    && completeBinding
    && (
      (confidence >= 0.85 && issues.length === 0)
      || (confidence >= 0.65 && hasOnlyAdvisoryFallbackIssues)
    ),
  )
}

// The server owns parser and field-registry freshness. Every unconfirmed
// candidate must pass through its version-aware cache before batch confirmation.
export function requiresServerRuleConditionRefresh(item: any, registryVersion?: string) {
  return !hasCurrentConfirmedUserRule(item, registryVersion)
}

function manualProcessFieldKey(processId: string) {
  let hash = 0x811c9dc5
  for (let index = 0; index < processId.length; index += 1) {
    hash ^= processId.charCodeAt(index)
    hash = Math.imul(hash, 0x01000193)
  }
  return `project_factor.manual_process_${(hash >>> 0).toString(16).padStart(8, '0')}`
}

export function defaultManualBooleanLabel(item: any) {
  const name = normalizeExportProcessName(String(item.segment?.normalized_step_name || '当前工序'))
  return `是否需要${name}`
}

export function isManualBooleanFinalizeCard(item: any) {
  if (!hasCurrentConfirmedUserRule(item)) return false
  const confirmed = item.conditionReview?.confirmed
  if ((confirmed?.kind || 'condition') !== 'condition') return false
  const manualField = confirmed.field_definitions?.find((field: CanonicalConditionField) =>
    field.type === 'boolean'
    && field.source === '用户直接设定'
    && field.key.startsWith('project_factor.manual_process_'),
  )
  return Boolean(
    manualField
    && confirmed.when?.field === manualField.key
    && confirmed.when?.op === 'eq'
    && confirmed.when?.value === true,
  )
}

export function manualRuleModeActionState(item: any, inlineEditing: boolean) {
  return {
    visible: !inlineEditing,
    mainlineActive: finalizeRuleMode(item) === 'mainline',
    booleanActive: isManualBooleanFinalizeCard(item),
  }
}

export function buildManualBooleanRuleCandidate(item: any, label: string): RuleConditionCandidate {
  const processId = exportProcessIdForItem(item)
  const switchLabel = String(label || '').trim() || defaultManualBooleanLabel(item)
  const fieldKey = manualProcessFieldKey(processId)
  return {
    kind: 'condition',
    when: { field: fieldKey, op: 'eq', value: true },
    then: {
      include_process_ids: [processId],
      exclude_process_ids: [],
      reason: `用户选择“${switchLabel}”时纳入当前工序`,
    },
    field_definitions: [{
      key: fieldKey,
      label: switchLabel,
      category: '可选工序',
      type: 'boolean',
      operators: ['eq', 'neq'],
      aliases: [],
      required: false,
      source: '用户直接设定',
      options: [],
      allow_custom: false,
    }],
    preview: `${switchLabel} 等于 是`,
    evidence: '用户直接设定',
  }
}

export function exportProcessIdForItem(item: any) {
  const serverProcessId = String(item.segment?.export_process_id || '').trim()
  if (serverProcessId) return serverProcessId
  const rawProcessId = String(item.segment?.id || '').trim()
  if (rawProcessId.startsWith('process_')) return rawProcessId
  // Compatibility for route responses produced before export_process_id was
  // added. New responses always take the server-owned branch above.
  if (/真空淬火|淬火/.test(String(item.segment?.normalized_step_name || ''))) return 'process_quench'
  return rawProcessId
}

function stableProcessId(rawId: string, displayName: string) {
  const text = String(rawId || '').trim()
  if (text) return text
  const slug = String(displayName || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9一-鿿]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return slug ? `process_${slug}` : 'process_unknown'
}

function slugStepId(processId: string, stepName: string, index: number, kind: 'primary' | 'attached') {
  const base = String(stepName || '')
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9一-鿿]+/g, '_')
    .replace(/^_+|_+$/g, '')
  return `${processId}.${kind}.${base || index + 1}`
}

function normalizeTemplateGroupAliases(value: unknown): TemplateGroupAliasBinding[] {
  if (!Array.isArray(value)) return []
  return value.map((item) => {
    if (!item || typeof item !== 'object') return null
    const sourceOperationId = Number((item as any).source_operation_id || 0)
    const alias = String((item as any).alias || '').trim()
    const templateGroupId = String((item as any).template_group_id || '').trim()
    const templateGroupPath = Array.isArray((item as any).template_group_path)
      ? (item as any).template_group_path.map((part: unknown) => String(part || '').trim()).filter(Boolean)
      : []
    if (sourceOperationId <= 0 || !alias || !templateGroupId || !templateGroupPath.length) return null
    return {
      source_operation_id: sourceOperationId,
      alias,
      template_group_id: templateGroupId,
      template_group_path: templateGroupPath,
    }
  }).filter((item): item is TemplateGroupAliasBinding => Boolean(item))
}

function mergeTemplateGroupAliases(target: TemplateGroupAliasBinding[], incoming: TemplateGroupAliasBinding[]) {
  const seen = new Set(target.map(item => Number(item?.source_operation_id || 0)).filter(Boolean))
  incoming.forEach((item) => {
    const sourceOperationId = Number(item?.source_operation_id || 0)
    if (!sourceOperationId || seen.has(sourceOperationId)) return
    target.push(item)
    seen.add(sourceOperationId)
  })
}

function leafCondition(field: string, op: string, value: unknown, factorId?: string): RulePackageCondition {
  return { field, op, value, ...(factorId ? { factor_id: factorId } : {}) }
}

const PROCESS_CAPABILITY_ALIASES: Record<string, string[]> = {
  无损检查: ['磁粉检查', '裂纹检查', '荧光检查', '磁粉探伤', '裂纹探伤'],
  标记: ['标印', '标刻'],
}

function resolveProcessIdsByName(
  processName: string,
  processes: Array<{ process_id: string; display_name: string }>,
) {
  const names = [processName, ...(PROCESS_CAPABILITY_ALIASES[processName] || [])]
    .map(normalizeExportProcessName)
  return processes
    .filter((item) => {
      const display = normalizeExportProcessName(item.display_name)
      return names.some(name => display === name || display.includes(name) || name.includes(display))
    })
    .map((item) => item.process_id)
}

function buildStaticV2Rules(
  processes: Array<{ process_id: string; display_name: string }>,
  standardFactors: StandardFactorDefinition[],
) {
  const rules: RulePackageRule[] = []

  const boundStaticLeaf = (
    field: string,
    op: string,
    value: unknown,
    expectedFactorId?: string,
  ) => {
    const leaf = leafCondition(field, op, value)
    const matches = matchingStandardFactors(leaf, standardFactors)
    if (matches.length !== 1 || (expectedFactorId && matches[0]?.factor_id !== expectedFactorId)) {
      throw new Error(`静态条件「${String(value)}」无法唯一绑定标准因子`)
    }
    return leafCondition(field, op, value, matches[0]!.factor_id)
  }

  const pushNamed = (
    ruleId: string,
    priority: number,
    when: RulePackageCondition,
    processNames: string[],
    reason: string,
  ) => {
    const includeIds = Array.from(
      new Set(processNames.flatMap((name) => resolveProcessIdsByName(name, processes))),
    )
    if (!includeIds.length) return
    rules.push({
      rule_id: ruleId,
      priority,
      enabled: true,
      source: 'system_static',
      when,
      then: {
        include_process_ids: includeIds,
        exclude_process_ids: [],
        reason,
      },
    })
  }

  pushNamed(
    'material.9Cr18.heat',
    100,
    boundStaticLeaf('material.grade', 'in', ['9Cr18', '95Cr18'], 'material.grade'),
    ['调质', '淬火'],
    '9Cr18 材料规则',
  )
  pushNamed(
    'material.4Cr14.normalize',
    100,
    boundStaticLeaf('material.grade', 'in', ['4Cr14Ni14W2Mo'], 'material.grade'),
    ['正常化'],
    '4Cr14 材料规则',
  )

  const featureRules: Array<[string, string[]]> = [
    ['扁位/平面', ['铣扁', '割扁']],
    ['槽类特征', ['铣槽', '磨槽']],
    ['普通孔/辅助孔', ['钻孔', '打孔']],
    ['铰孔/精孔', ['钻铰孔']],
    ['型孔/割扁', ['割型孔', '打型孔']],
    ['顶尖孔', ['研顶尖孔']],
  ]
  featureRules.forEach(([feature, processNames]) => {
    pushNamed(
      `feature.${feature}`,
      90,
      boundStaticLeaf('cad.features', 'contains', feature),
      processNames,
      `CAD 特征 ${feature}`,
    )
  })

  const precisionRules: Array<[string, string[]]> = [
    ['孔精加工', ['磨孔']],
    ['珩孔要求', ['珩孔']],
    ['研孔要求', ['研孔']],
    ['外圆磨削', ['磨外圆']],
    ['端面磨削', ['磨端面']],
    ['槽磨削', ['磨槽']],
    ['研外圆', ['研外圆']],
  ]
  precisionRules.forEach(([precision, processNames]) => {
    pushNamed(
      `precision.${precision}`,
      80,
      boundStaticLeaf('precision.grades', 'contains', precision),
      processNames,
      `精度要求 ${precision}`,
    )
  })

  const specialRules: Array<[string, string[]]> = [
    ['渗氮层要求', ['镀铜', '渗氮', '除铜']],
    ['铬酸阳极化要求', ['铬酸阳极化']],
    ['硬质阳极化要求', ['硬质阳极化']],
    ['追溯标印', ['标记']],
    ['无损检测要求', ['无损检查', '磁粉检查', '裂纹检查', '荧光检查']],
    ['磁粉检查要求', ['磁粉检查', '荧光检查']],
    ['烧伤检查要求', ['烧伤检查']],
  ]
  specialRules.forEach(([requirement, processNames]) => {
    pushNamed(
      `special.${requirement}`,
      70,
      boundStaticLeaf('special.requirements', 'contains', requirement),
      processNames,
      `特殊要求 ${requirement}`,
    )
  })

  return rules
}

function setNestedInputValue(target: Record<string, any>, key: string, value: unknown) {
  const parts = String(key || '').split('.').filter(Boolean)
  if (!parts.length) return
  let current = target
  parts.slice(0, -1).forEach((part) => {
    if (!current[part] || typeof current[part] !== 'object' || Array.isArray(current[part])) {
      current[part] = {}
    }
    current = current[part]
  })
  current[parts[parts.length - 1]!] = value
}

function defaultInputValueForField(field: CompileRulePackageRequest['fields'][number]) {
  if (field.source === '用户直接设定' && field.type === 'boolean') return false
  const firstOption = field.options?.[0]?.value || '样例值'
  if (field.type === 'multi_select') return [firstOption]
  if (field.type === 'single_select') return firstOption
  if (field.type === 'number') {
    const min = field.validation?.min
    const max = field.validation?.max
    if (typeof min === 'number' && typeof max === 'number') return (min + max) / 2
    if (typeof min === 'number') return min
    if (typeof max === 'number') return max
    return 1
  }
  if (field.type === 'boolean') return true
  return firstOption
}

function buildDefaultV2TestCases(
  fields: CompileRulePackageRequest['fields'],
  processes: CompileRulePackageRequest['processes'],
): CompileRulePackageRequest['test_cases'] {
  const input: Record<string, any> = {}
  fields.forEach((field) => {
    setNestedInputValue(input, field.key, defaultInputValueForField(field))
  })
  const mainProcessIds = processes
    .filter((process) => process.main)
    .map((process) => process.process_id)
  return [
    {
      case_id: 'default-smoke',
      input,
      expect: {
        included_process_ids: mainProcessIds,
        excluded_process_ids: [],
      },
    },
  ]
}

function collectConditionFields(condition: RulePackageCondition, target: Set<string>) {
  const node = condition as unknown as Record<string, unknown>
  if (typeof node.field === 'string' && node.field) {
    target.add(node.field)
    return
  }
  if (Array.isArray(node.all)) node.all.forEach(child => collectConditionFields(child as RulePackageCondition, target))
  if (Array.isArray(node.any)) node.any.forEach(child => collectConditionFields(child as RulePackageCondition, target))
  if (node.not && typeof node.not === 'object') collectConditionFields(node.not as RulePackageCondition, target)
}

function registryFieldToInputField(field: CanonicalConditionField): CompileRulePackageRequest['fields'][number] {
  return {
    key: field.key,
    label: field.label,
    type: field.type,
    required: field.required || false,
    source: field.source || '',
    options: field.options || [],
    allow_custom: field.allow_custom ?? true,
    unit: field.unit || null,
    validation: field.validation || null,
  }
}

function normalizeConditionForCompile(condition: RulePackageCondition): RulePackageCondition {
  const node = condition as unknown as Record<string, unknown>
  if (typeof node.field === 'string' && node.field) {
    return {
      field: node.field,
      op: typeof node.op === 'string' ? node.op : 'eq',
      ...(Object.prototype.hasOwnProperty.call(node, 'value') && node.value !== null
        ? { value: node.value }
        : {}),
      ...(typeof node.factor_id === 'string' && node.factor_id
        ? { factor_id: node.factor_id }
        : {}),
    }
  }
  if (Array.isArray(node.all)) {
    return { all: node.all.map(item => normalizeConditionForCompile(item as RulePackageCondition)) }
  }
  if (Array.isArray(node.any)) {
    return { any: node.any.map(item => normalizeConditionForCompile(item as RulePackageCondition)) }
  }
  if (node.not && typeof node.not === 'object') {
    return { not: normalizeConditionForCompile(node.not as RulePackageCondition) }
  }
  return condition
}

function collectCustomTagValues(
  condition: RulePackageCondition,
  target: Map<string, Set<string>>,
) {
  const node = condition as unknown as Record<string, unknown>
  if (typeof node.field === 'string' && node.field) {
    if (
      ['eq', 'in', 'contains', 'contains_any', 'contains_all'].includes(String(node.op || ''))
    ) {
      const values = Array.isArray(node.value) ? node.value : [node.value]
      const fieldValues = target.get(node.field) || new Set<string>()
      values.forEach((value) => {
        if (typeof value === 'string' && value.trim()) fieldValues.add(value.trim())
      })
      target.set(node.field, fieldValues)
    }
    return
  }
  if (Array.isArray(node.all)) node.all.forEach(item => collectCustomTagValues(item as RulePackageCondition, target))
  if (Array.isArray(node.any)) node.any.forEach(item => collectCustomTagValues(item as RulePackageCondition, target))
  if (node.not && typeof node.not === 'object') collectCustomTagValues(node.not as RulePackageCondition, target)
}

function compactV2InputSchema(args: {
  fields: CompileRulePackageRequest['fields']
  customTagValues: Map<string, Set<string>>
}) {
  const fields = args.fields.map(field => ({
    ...field,
    options: field.options ? [...field.options] : [],
  }))
  args.customTagValues.forEach((values, fieldKey) => {
    const field = fields.find(item => item.key === fieldKey)
    if (!field || !['single_select', 'multi_select'].includes(field.type)) return
    const knownValues = new Set((field.options || []).map(option => option.value))
    field.options = (field.options || []).filter(option => values.has(option.value))
    values.forEach((value) => {
      if (knownValues.has(value)) return
      field.options = [...(field.options || []), { value, label: value }]
      knownValues.add(value)
    })
  })

  const hasSpecificDimensionIt = fields.some(field =>
    field.key === 'precision.inner_diameter_it' || field.key === 'precision.outer_diameter_it',
  )
  if (hasSpecificDimensionIt) {
    const genericDimensionIt = fields.find(field => field.key === 'precision.dimension_it')
    if (genericDimensionIt) genericDimensionIt.label = '其他尺寸精度 IT'
  }

  return {
    fields,
  }
}

export function buildCompileRequestFromCards(args: {
  projectId: number
  packageName: string
  routeVersionId?: number | null
  cards: any[]
  displayName: (segment: any) => string
  phaseLabel: (segment: any) => string
  primarySteps: (segment: any) => string[]
  attachedSteps: (segment: any) => string[]
  conditionFields?: CanonicalConditionField[]
  standardFactors: StandardFactorDefinition[]
}): CompileRulePackageRequest {
  const processMap = new Map<string, any>()
  args.cards.forEach((item) => {
    const displayName = normalizeExportProcessName(args.displayName(item.segment))
    const processId = stableProcessId(exportProcessIdForItem(item), displayName)
    const templateGroupAliases = normalizeTemplateGroupAliases(item.segment?.template_group_aliases)
    const primary = args.primarySteps(item.segment).map((name, index) => ({
      step_id: slugStepId(processId, name, index, 'primary'),
      name,
      kind: 'primary' as const,
    }))
    const attached = args.attachedSteps(item.segment).map((name, index) => ({
      step_id: slugStepId(processId, name, index, 'attached'),
      name,
      kind: 'attached' as const,
    }))
    const existing = processMap.get(processId)
    if (!existing) {
      processMap.set(processId, {
        process_id: processId,
        process_code: processId.replace(/^process_/, '').toUpperCase(),
        display_name: displayName,
        phase: args.phaseLabel(item.segment) || item.segment?.phase || '',
        default_sequence: Number(item.segment?.sequence || 0) * 10,
        main: isMainlineRule(item),
        template_group_aliases: templateGroupAliases,
        steps: [...primary, ...attached],
        constraints: {
          requires: [],
          must_run_after: [],
          must_run_before: [],
          conflicts_with: [],
        },
      })
      return
    }
    existing.main = existing.main || isMainlineRule(item)
    existing.default_sequence = Math.min(existing.default_sequence, Number(item.segment?.sequence || 0) * 10)
    mergeTemplateGroupAliases(existing.template_group_aliases, templateGroupAliases)
    const known = new Set(existing.steps.map((step: any) => step.name))
    ;[...primary, ...attached].forEach((step) => {
      if (!known.has(step.name)) {
        existing.steps.push(step)
        known.add(step.name)
      }
    })
  })

  const processes = Array.from(processMap.values()).sort(
    (a, b) => Number(a.default_sequence || 0) - Number(b.default_sequence || 0),
  )
  const staticRules = buildStaticV2Rules(
    processes.map((item) => ({ process_id: item.process_id, display_name: item.display_name })),
    args.standardFactors,
  )
  const confirmedCards = args.cards.filter(item => hasCurrentConfirmedUserRule(item))
  const confirmedFieldDefinitions = new Map<string, CanonicalConditionField>()
  confirmedCards.forEach((item) => {
    item.conditionReview.confirmed.field_definitions?.forEach((field: CanonicalConditionField) => {
      const existing = confirmedFieldDefinitions.get(field.key)
      if (!existing) {
        confirmedFieldDefinitions.set(field.key, field)
        return
      }
      const optionMap = new Map(
        [...(existing.options || []), ...(field.options || [])]
          .map(option => [option.value, option] as const),
      )
      confirmedFieldDefinitions.set(field.key, {
        ...existing,
        aliases: Array.from(new Set([...(existing.aliases || []), ...(field.aliases || [])])),
        operators: Array.from(new Set([...(existing.operators || []), ...(field.operators || [])])),
        options: Array.from(optionMap.values()),
      })
    })
  })
  const userRules: RulePackageRule[] = confirmedCards
    .filter(item => (item.conditionReview.confirmed.kind || 'condition') === 'condition')
    .flatMap((item) => {
      const confirmed = item.conditionReview.confirmed
      const normalizedWhen = normalizeConditionForCompile(confirmed.when!)
      const binding = factorBindingState(normalizedWhen, args.standardFactors)
      if (!binding.complete) {
        const issue = binding.issues[0]!
        throw new FinalizeRulePackageBuildError(
          `工序 ${String(item.segment.id || item.segment.sequence)} 的条件 ${issue.path || '根节点'}：${issue.message}`,
          String(item.segment.id || ''),
        )
      }
      const baseRule = {
        rule_id: `user.${String(item.segment.id || item.segment.sequence).replace(/[^a-zA-Z0-9_.-]+/g, '_')}`,
        priority: 1000 + Math.max(0, 1000 - Number(item.segment.sequence || 0)),
        enabled: true,
        source: 'user_confirmed' as const,
        source_segment_id: item.segment.id,
        source_text: item.conditionText,
        confirmed_by: item.conditionReview.confirmed_by || '默认用户',
        confirmed_at: item.conditionReview.confirmed_at,
        when: normalizedWhen,
        then: {
          include_process_ids: confirmed.then?.include_process_ids || [],
          exclude_process_ids: confirmed.then?.exclude_process_ids || [],
          reason: confirmed.then?.reason || `用户确认条件：${item.conditionText}`,
        },
      }
      const manualField = confirmed.field_definitions?.find((field: CanonicalConditionField) =>
        field.type === 'boolean' && field.source === '用户直接设定' && field.key.startsWith('project_factor.manual_process_'),
      )
      if (!manualField || confirmed.when?.field !== manualField.key || confirmed.when.op !== 'eq') {
        return [baseRule]
      }
      return [
        {
          ...baseRule,
          rule_id: `${baseRule.rule_id}.manual.true`,
          priority: Math.max(baseRule.priority, 2000),
        },
        {
          ...baseRule,
          rule_id: `${baseRule.rule_id}.manual.false`,
          priority: Math.max(baseRule.priority, 2000),
          when: { field: manualField.key, op: 'eq', value: false },
          then: {
            include_process_ids: [],
            exclude_process_ids: baseRule.then.include_process_ids || [],
            reason: `用户选择“否”时排除${baseRule.then.reason || '当前工序'}`,
          },
        },
      ]
    })
  const processRelations: RulePackageProcessRelation[] = confirmedCards
    .filter(item => item.conditionReview.confirmed.kind === 'process_relation' && item.conditionReview.confirmed.relation)
    .map((item) => {
      const relation = item.conditionReview.confirmed.relation!
      return {
        relation_id: `relation.${String(item.segment.id || item.segment.sequence).replace(/[^a-zA-Z0-9_.-]+/g, '_')}`,
        relation_type: relation.relation_type,
        source_process_ids: relation.source_process_ids,
        target_process_ids: relation.target_process_ids,
        source_match: relation.source_match || 'any',
        enabled: true,
        source: 'user_confirmed',
        source_segment_id: item.segment.id,
        source_text: item.conditionText,
        confirmed_by: item.conditionReview.confirmed_by || '默认用户',
        confirmed_at: item.conditionReview.confirmed_at,
        reason: item.conditionReview.confirmed.preview || `用户确认关联工序：${item.conditionText}`,
      }
    })
  const protectedProcessIds = new Set<string>([
    ...processes.filter(item => item.main).map(item => item.process_id),
    ...userRules.flatMap(rule => [
      ...(rule.then.include_process_ids || []),
      ...(rule.then.exclude_process_ids || []),
    ]),
  ])
  const filteredStaticRules = staticRules.flatMap((rule) => {
    const includeProcessIds = (rule.then.include_process_ids || [])
      .filter(processId => !protectedProcessIds.has(processId))
    return includeProcessIds.length
      ? [{ ...rule, then: { ...rule.then, include_process_ids: includeProcessIds } }]
      : []
  })
  const finalRules = [...userRules, ...filteredStaticRules]
  const referencedFieldKeys = new Set<string>()
  finalRules.forEach(rule => collectConditionFields(rule.when, referencedFieldKeys))
  const registryMap = new Map((args.conditionFields || []).map(field => [field.key, field] as const))
  const fieldMap = new Map<string, CompileRulePackageRequest['fields'][number]>()
  referencedFieldKeys.forEach((key) => {
    const definition = registryMap.get(key) || confirmedFieldDefinitions.get(key)
    if (definition) fieldMap.set(key, registryFieldToInputField(definition))
  })
  const customTagValues = new Map<string, Set<string>>()
  finalRules.forEach(rule => collectCustomTagValues(rule.when, customTagValues))
  const compacted = compactV2InputSchema({
    fields: Array.from(fieldMap.values()),
    customTagValues,
  })
  const fields = compacted.fields

  return {
    project_id: args.projectId,
    package_name: args.packageName,
    route_version_id: args.routeVersionId ?? null,
    applicability: {
      part_families: [],
      manufacturing_modes: ['machining'],
    },
    fields,
    processes,
    rules: finalRules,
    process_relations: processRelations,
    test_cases: buildDefaultV2TestCases(fields, processes),
  }
}

export function buildRuleReportFromV2Package(args: {
  projectName: string
  packageName: string
  contentHash: string
  processes: Array<{ process_id: string; display_name: string; main?: boolean; default_sequence?: number }>
  rules: Array<{ rule_id: string; then?: { reason?: string; include_process_ids?: string[] } }>
  processRelations?: Array<{
    relation_id: string
    relation_type: ProcessRelationType
    source_process_ids: string[]
    target_process_ids: string[]
    source_match?: 'any' | 'all'
    reason?: string
  }>
  validation?: { valid?: boolean; errors?: Array<{ message?: string }>; warnings?: Array<{ message?: string }> }
}) {
  const lines: string[] = []
  lines.push(`# ${FINALIZE_EXPORT_COPY.documentTitle}`)
  lines.push('')
  lines.push(`- 任务名称：${args.projectName || '未命名任务'}`)
  lines.push(`- 规则包：${args.packageName}`)
  lines.push(`- schema_version：2.0`)
  lines.push(`- content_hash：${args.contentHash || '-'}`)
  lines.push(`- 导出时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`)
  lines.push(`- 工序数量：${args.processes.length}`)
  lines.push(`- 规则数量：${args.rules.length}`)
  lines.push(`- 关联工序规则：${args.processRelations?.length || 0}`)
  lines.push(`- 校验：${args.validation?.valid === false ? '未通过' : '通过'}`)
  lines.push('')
  lines.push('## 工序目录')
  lines.push('')
  args.processes
    .slice()
    .sort((a, b) => Number(a.default_sequence || 0) - Number(b.default_sequence || 0))
    .forEach((process) => {
      lines.push(`- ${process.default_sequence ?? '-'} · ${process.display_name} (\`${process.process_id}\`)${process.main ? ' · 主线' : ''}`)
    })
  lines.push('')
  lines.push('## 规则摘要')
  lines.push('')
  args.rules.forEach((rule) => {
    const includes = (rule.then?.include_process_ids || []).join(', ')
    lines.push(`- ${rule.rule_id}：${rule.then?.reason || ''} → ${includes}`)
  })
  if (args.processRelations?.length) {
    lines.push('')
    lines.push('## 关联工序规则')
    lines.push('')
    args.processRelations.forEach((relation) => {
      const source = relation.source_process_ids.join(', ')
      const target = relation.target_process_ids.join(', ')
      const mode = relation.source_match === 'all' ? '全部来源满足' : '任一来源满足'
      lines.push(`- ${relation.relation_id}：${relation.relation_type} · ${source} → ${target} · ${mode}${relation.reason ? ` · ${relation.reason}` : ''}`)
    })
  }
  if (args.validation?.errors?.length) {
    lines.push('')
    lines.push('## 校验错误')
    lines.push('')
    args.validation.errors.forEach((issue) => lines.push(`- ${issue.message || ''}`))
  }
  if (args.validation?.warnings?.length) {
    lines.push('')
    lines.push('## 校验警告')
    lines.push('')
    args.validation.warnings.forEach((issue) => lines.push(`- ${issue.message || ''}`))
  }
  lines.push('')
  return lines.join('\n')
}
