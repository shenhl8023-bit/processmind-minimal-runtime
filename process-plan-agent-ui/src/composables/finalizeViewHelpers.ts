import { displayFactorLabel, buildFactorCandidates } from '@/composables/analysisWorkspaceHelpers'
import { answersFromTrail, normalizeQuestionNodeId } from '@/composables/analysisQuestionTreeState'
import { buildResultSummary } from '@/composables/analysisQuestionTreeNodes'
import type { FactorCandidate } from '@/components/analysis/types'
import type { OperationItem, SavedNormalizedRouteSegment } from '@/api'
import type { RuleConditionReview } from '@/api/rulePackages'
import {
  buildFinalizeMainlineSentence,
  buildFinalizeTriggerSentence,
  resolveFinalizeFactorPhrase,
} from '@/config/finalizeRulePresentation'
import { formatRouteDisplayName, formatRoutePhaseLabel } from '@/composables/routeNameDisplay'

export type FinalizeDraft = {
  factorNames: string[]
  conditionText: string
  userAnswerLabels: string[]
  userAnswerContextLabels: string[]
}

export type FinalizeCard = {
  segment: SavedNormalizedRouteSegment
  factorNames: string[]
  factorLabels: string[]
  userAnswerLabels: string[]
  userAnswerContextLabels: string[]
  systemFactorLabels: string[]
  conditionText: string
  defaultConditionText: string
  conditionReview: RuleConditionReview | null
  edited: boolean
  rawRuleLines: string[]
  availableFactors: FactorCandidate[]
}

export function dedupeLabels(values: string[]) {
  return Array.from(new Set(values.map(value => String(value || '').trim()).filter(Boolean)))
}

export function parseLabelDraft(text: string) {
  return dedupeLabels(
    String(text || '')
      .split(/[\n；;]+/)
      .map(value => value.trim()),
  )
}

function naturalFactorPhrase(value: string) {
  return resolveFinalizeFactorPhrase(value, displayFactorLabel(value))
}

function formatReasonList(values: string[]) {
  const cleaned = dedupeLabels(values)
    .map(value => normalizeFinalizeReasonLabel(value))
    .map(value => String(value || '').trim().replace(/[。；;]+$/g, ''))
    .filter(Boolean)
  if (!cleaned.length) return ''
  const materialPhrase = formatMaterialReason(cleaned)
  if (materialPhrase) return materialPhrase
  const first = cleaned[0] || ''
  const second = cleaned[1] || ''
  const third = cleaned[2] || ''
  if (cleaned.length === 1) return first
  if (cleaned.length === 2) return `${first}，以及${second}`
  return `${cleaned.slice(0, 2).join('，')}，以及${third}`
}

function isMaterialBasisLabel(value: string) {
  return /^(与材料相关|材料相关|按材料牌号|材料牌号|按材料|材料)$/.test(String(value || '').trim())
}

function isMaterialValueLabel(value: string) {
  const text = String(value || '').trim()
  return /^[A-Za-z0-9][A-Za-z0-9+\-_/]*$/.test(text) && /[A-Za-z]/.test(text) && /\d/.test(text)
}

function formatMaterialReason(values: string[]) {
  const hasMaterialBasis = values.some(isMaterialBasisLabel)
  if (!hasMaterialBasis) return ''
  const materialValues = values.filter(value => !isMaterialBasisLabel(value) && isMaterialValueLabel(value))
  if (!materialValues.length) return ''
  const joined = dedupeLabels(materialValues).join('、')
  return `材料牌号为 ${joined}`
}

function normalizeFinalizeReasonLabel(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  if (/^(孔|孔结构|一般孔)$/.test(text)) return '零件存在孔类结构或孔加工要求'
  if (/^(型孔|异形孔|异型孔)$/.test(text)) return '零件存在型孔或异形孔加工要求'
  if (/^(螺纹孔|螺孔)$/.test(text)) return '零件存在螺纹孔加工要求'
  if (/^(底孔|预孔|预钻孔)$/.test(text)) return '零件存在底孔或预孔加工要求'
  if (/^(销孔|铆孔|铰孔)$/.test(text)) return `零件存在${text}加工要求`
  if (/^(槽|槽类特征|一般槽|一般环槽)$/.test(text)) return '存在槽类结构'
  if (/^(退刀槽|越程槽|密封槽|卡簧槽|键槽|花键槽)$/.test(text)) return `存在${text}结构`
  if (/^(内孔|通孔|盲孔|孔口|孔类特征)$/.test(text)) return `存在${text}结构`
  if (/^(外圆|主外圆|台阶外圆|基准外圆)$/.test(text)) return `存在${text}加工对象`
  if (/^(端面|平端面|基准端面|总长控制端面|装夹定位端面)$/.test(text)) return `存在${text}加工对象`
  if (/^(平面|扁位|削平面|铣扁)$/.test(text)) return `存在${text}加工对象`
  if (/^(倒角|孔口倒角|锐边|毛刺)$/.test(text)) return `需要处理${text}`
  if (/^IT\d/.test(text)) return `尺寸精度达到${text}`
  if (/^Ra\s*\d/i.test(text)) return `表面粗糙度达到${text}`
  if (/^(圆度|圆柱度|同轴度|跳动|位置度|平面度|垂直度|对称度|平行度)$/.test(text)) return `存在${text}要求`
  return text
}

function isNamingStyleReason(value: string) {
  const text = String(value || '').trim()
  return /多种叫法|不同叫法|统一名称|统一名称|结合上下文判断|命名/.test(text)
}

function pickPrimaryReasonLabels(values: string[]) {
  const cleaned = dedupeLabels(values)
  const primary = cleaned.filter(value => !isNamingStyleReason(value))
  return primary
}

export function buildReadableCondition(segmentName: string, factorNames: string[]) {
  const displaySegmentName = formatRouteDisplayName(segmentName)
  const names = factorNames.filter(name => Boolean(name) && name !== 'naming_variant=true')
  if (!names.length) {
    return buildFinalizeMainlineSentence(displaySegmentName, false)
  }
  if (names.length === 1 && names[0] === 'always=true') {
    return buildFinalizeMainlineSentence(displaySegmentName, true)
  }
  const phrases = names
    .filter(name => name !== 'always=true')
    .map(naturalFactorPhrase)
  if (!phrases.length) {
    return buildFinalizeMainlineSentence(displaySegmentName, true)
  }
  return buildFinalizeTriggerSentence(displaySegmentName, formatReasonList(phrases))
}

export function extractUserAnswerGroups(segment: SavedNormalizedRouteSegment) {
  const trail = Array.isArray(segment.rule_review?.question_trail) ? segment.rule_review?.question_trail || [] : []
  const detailLabels = dedupeLabels(
    trail
      .filter(item => !['rule_reason_root', 'rule_reason_other', 'merge_name_root'].includes(normalizeQuestionNodeId(String(item?.nodeId || ''))))
      .map(item => String(item?.label || '')),
  )
  const contextLabels = dedupeLabels(
    trail
      .filter(item => ['rule_reason_root', 'rule_reason_other', 'merge_name_root'].includes(normalizeQuestionNodeId(String(item?.nodeId || ''))))
      .map(item => String(item?.label || '')),
  )
  return { detailLabels, contextLabels }
}

export function buildUserFirstCondition(
  segmentName: string,
  userAnswerLabels: string[],
  userAnswerContextLabels: string[],
  factorNames: string[],
  segment?: SavedNormalizedRouteSegment,
) {
  const displaySegmentName = formatRouteDisplayName(segmentName)
  const trail = Array.isArray(segment?.rule_review?.question_trail) ? segment.rule_review.question_trail : []
  if (trail.length) {
    const regenerated = buildResultSummary(
      segmentName,
      answersFromTrail(trail.map(item => ({
        nodeId: normalizeQuestionNodeId(String(item?.nodeId || '')),
        value: String(item?.value || ''),
        label: String(item?.label || ''),
      }))),
      segment?.rule_review?.note || '',
    )
    if (regenerated) return regenerated
  }
  const primaryUserLabels = pickPrimaryReasonLabels(userAnswerLabels)
  const primaryContextLabels = pickPrimaryReasonLabels(userAnswerContextLabels)
  if (primaryUserLabels.length) {
    return buildFinalizeTriggerSentence(displaySegmentName, formatReasonList(primaryUserLabels))
  }
  if (primaryContextLabels.length) {
    return buildFinalizeTriggerSentence(displaySegmentName, formatReasonList(primaryContextLabels))
  }
  return buildReadableCondition(displaySegmentName, factorNames)
}

export function resolveFinalizePhase(segment: Pick<SavedNormalizedRouteSegment, 'phase' | 'normalized_step_name' | 'sequence'>) {
  const rawPhase = String(segment.phase || '').trim()
  if (rawPhase) {
    return formatRoutePhaseLabel(rawPhase) || '未分类'
  }
  const name = String(segment.normalized_step_name || '').trim()
  if (/(包装|标印|标记|放行)/.test(name)) return '放行'
  if (/(磁粉|烧伤|裂纹|荧光)/.test(name)) return '专项检查'
  if (/(调质|正常化|正火|淬火|真空淬火|回火|去应力|热处理|渗氮|氰化|时效|钝化)/.test(name)) return '热处理'
  if (/(终检|检验)/.test(name)) return '终检'
  if (/(磨|研|珩|精|热后)/.test(name)) return '热后'
  if (Number(segment.sequence || 0) >= 200) return '终检'
  return '热前'
}

export function buildRawRuleLines(
  segment: SavedNormalizedRouteSegment,
  factorNames: string[],
  userAnswerLabels: string[],
  userAnswerContextLabels: string[],
) {
  const lines: string[] = []
  lines.push(`系统工序名：${formatRouteDisplayName(segment.normalized_step_name)}`)
  if (userAnswerContextLabels.length) {
    lines.push(`上层判断口径：${userAnswerContextLabels.join('、')}`)
  }
  if (userAnswerLabels.length) {
    lines.push(`用户已确认规则因素：${userAnswerLabels.join('、')}`)
  }
  if (segment.rule_review?.summary_lines?.length) {
    lines.push(...segment.rule_review.summary_lines.map(line => `已保存结论：${line}`))
  }
  if (factorNames.length) {
    lines.push(`规则因素字段：${factorNames.join(' AND ')}`)
  }
  if (segment.source_nodes?.length) {
    lines.push(`原始工序来源：${segment.source_nodes.map(name => formatRouteDisplayName(name)).join('、')}`)
  }
  if (segment.doc_coverage?.total_docs) {
    lines.push(`样本覆盖：${segment.doc_coverage.hit_docs}/${segment.doc_coverage.total_docs}`)
  }
  return lines
}

export function buildFinalizeCards(
  segments: SavedNormalizedRouteSegment[],
  operations: OperationItem[],
  drafts: Record<string, FinalizeDraft>,
) {
  return segments.map((segment): FinalizeCard => {
    const sourceOperationIds = new Set(segment.source_operation_ids || [])
    const sourceOperations = operations.filter(operation => sourceOperationIds.has(operation.id))
    const reviewMap = new Map(segment.factor_reviews.map(review => [review.factor_name, review] as const))
    const variantNames = Array.from(
      new Set(
        (segment.matched_detail_rows || [])
          .map(row => (row.operation_name || '').trim())
          .filter(Boolean),
      ),
    )
    const availableFactors = buildFactorCandidates({
      operations: sourceOperations,
      reviewMap,
      segment,
      documents: [],
      variantNames,
    })
    const defaultFactorNames = segment.factor_reviews
      .filter(review => review.decision === 'confirmed')
      .map(review => review.factor_name)
    const fallbackFactorNames = defaultFactorNames.length
      ? defaultFactorNames
      : availableFactors.slice(0, 3).map(factor => factor.name)
    const draft = drafts[segment.id]
    const factorNames = draft?.factorNames?.length ? draft.factorNames : fallbackFactorNames
    const factorLabels = factorNames.map(name => displayFactorLabel(name)).filter(Boolean)
    const { detailLabels, contextLabels } = extractUserAnswerGroups(segment)
    const userAnswerLabels = draft ? draft.userAnswerLabels : detailLabels
    const userAnswerContextLabels = draft ? draft.userAnswerContextLabels : contextLabels
    const systemFactorLabels = factorLabels.filter(label => !userAnswerLabels.includes(label))
    const defaultConditionText = buildUserFirstCondition(segment.normalized_step_name, userAnswerLabels, userAnswerContextLabels, factorNames, segment)
    const conditionReview = segment.rule_review?.condition_review || null
    return {
      segment,
      factorNames,
      factorLabels,
      userAnswerLabels,
      userAnswerContextLabels,
      systemFactorLabels,
      conditionText: (draft?.conditionText || '').trim() || conditionReview?.source_text?.trim() || defaultConditionText,
      defaultConditionText,
      conditionReview,
      edited: !!draft,
      rawRuleLines: buildRawRuleLines(segment, factorNames, userAnswerLabels, userAnswerContextLabels),
      availableFactors,
    }
  })
}
