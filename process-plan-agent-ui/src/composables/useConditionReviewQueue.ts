import { nextTick, ref, type ComputedRef, type Ref } from 'vue'
import {
  confirmRuleCondition,
  parseRuleCondition,
  saveRuleConditionDraft,
  setManualRuleCondition,
  type RuleConditionCandidate,
  type RuleConditionProcessOption,
  type RuleConditionReview,
  type StandardFactorDefinition,
} from '@/api/rulePackages'
import type { SavedNormalizedRouteVersionResult, SegmentRuleReview } from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import {
  buildManualBooleanRuleCandidate,
  exportProcessIdForItem,
  normalizeExportProcessName,
} from '@/utils/finalizeRulePackage'
import { factorBindingState } from '@/utils/standardFactorBindings'

export type FinalizeIssueHandler = (title: string, summary: string, details?: string) => void

export type ConditionReviewQueueOptions = {
  projectId: Ref<number | null>
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  segmentCards: ComputedRef<FinalizeCard[]>
  batchEligibleCards: ComputedRef<FinalizeCard[]>
  autoConfirmableReviewCards: ComputedRef<FinalizeCard[]>
  pendingRuleCards: ComputedRef<FinalizeCard[]>
  conditionProcessOptions: ComputedRef<RuleConditionProcessOption[]>
  factorCatalogReady: ComputedRef<boolean>
  standardFactors: Ref<StandardFactorDefinition[]>
  factorCatalogError: Ref<string>
  onlyPending: Ref<boolean>
  activeSegmentId: Ref<string>
  displayName: (segment: SavedNormalizedRouteVersionResult['segments'][number]) => string
  onPublishedRuleOutdated: () => void
  onPersistedStatusChanged?: () => void
  onConditionTextDraft: (item: FinalizeCard, sourceText: string) => void
  onNotice: FinalizeIssueHandler
  onWorkflowConflict: (error: unknown) => Promise<boolean>
}

function asErrorMessage(error: unknown) {
  const detail = (error as { response?: { data?: { detail?: unknown } } } | null)?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) {
    return detail.map(item => {
      if (item && typeof item === 'object') {
        const value = item as { msg?: unknown; message?: unknown }
        return value.msg || value.message || String(item)
      }
      return String(item)
    }).join('\n')
  }
  if (detail && typeof detail === 'object' && 'issues' in detail) {
    const structured = detail as { message?: unknown; issues?: unknown[] }
    return [structured.message, ...(structured.issues || [])].filter(Boolean).join('\n')
  }
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: unknown }).message || '')
  }
  return String((error as { message?: unknown } | null)?.message || '规则条件处理失败')
}

function isConditionSourceConflict(error: unknown) {
  return Number((error as { response?: { status?: unknown } } | null)?.response?.status) === 409
    && /条件文字已经发生变化|重新解析后再确认/.test(asErrorMessage(error))
}

export function useConditionReviewQueue(options: ConditionReviewQueueOptions) {
  const conditionBusySegmentIds = ref(new Set<string>())
  const batchParsing = ref(false)
  const batchParseCompleted = ref(0)
  const batchParseTotal = ref(0)
  const batchReviewing = ref(false)
  const batchReviewCompleted = ref(0)
  const batchReviewTotal = ref(0)
  const reviewingRules = ref(false)
  const batchNotice = ref('')
  const conditionBusyCounts = new Map<string, Set<number>>()
  const busyTokens = new Map<number, string>()
  let nextBusyToken = 0
  let batchNoticeTimer: ReturnType<typeof setTimeout> | null = null
  let requestGeneration = 0
  let batchParseExecutionId = 0
  let batchReviewExecutionId = 0

  function updateBusySegments() {
    conditionBusySegmentIds.value = new Set(conditionBusyCounts.keys())
  }

  function beginConditionBusy(segmentId: string) {
    const token = ++nextBusyToken
    const tokens = conditionBusyCounts.get(segmentId) || new Set<number>()
    tokens.add(token)
    conditionBusyCounts.set(segmentId, tokens)
    busyTokens.set(token, segmentId)
    updateBusySegments()
    return () => {
      const currentSegmentId = busyTokens.get(token)
      if (!currentSegmentId) return
      busyTokens.delete(token)
      const currentTokens = conditionBusyCounts.get(currentSegmentId)
      currentTokens?.delete(token)
      if (!currentTokens?.size) conditionBusyCounts.delete(currentSegmentId)
      updateBusySegments()
    }
  }

  function setBatchNotice(message: string) {
    batchNotice.value = message
    if (batchNoticeTimer) clearTimeout(batchNoticeTimer)
    if (message) {
      batchNoticeTimer = setTimeout(() => { batchNotice.value = '' }, 4000)
    }
  }

  function applyConditionReview(segmentId: string, review: RuleConditionReview) {
    const segment = options.savedRoute.value?.segments.find(item => item.id === segmentId)
    if (!segment) return
    const ruleReview: SegmentRuleReview = segment.rule_review || {
        id: 0,
        decision: 'accepted',
        note: '',
        summary_lines: [],
        question_trail: [],
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
      }
    segment.rule_review = ruleReview
    ruleReview.condition_review = review
    options.onPersistedStatusChanged?.()
  }

  function hasCurrentConditionText(segmentId: string, sourceText: string) {
    const current = options.segmentCards.value.find(item => item.segment.id === segmentId)
    return current?.conditionText.trim() === sourceText.trim()
  }

  function isCurrent(generation: number, external: () => boolean) {
    return generation === requestGeneration && external()
  }

  function cancelPendingRequests() {
    requestGeneration += 1
    batchParseExecutionId += 1
    batchReviewExecutionId += 1
    batchParsing.value = false
    batchReviewing.value = false
    reviewingRules.value = false
    conditionBusyCounts.clear()
    busyTokens.clear()
    if (batchNoticeTimer) clearTimeout(batchNoticeTimer)
    batchNoticeTimer = null
    batchNotice.value = ''
    updateBusySegments()
  }

  async function parseConditionItem(
    item: FinalizeCard,
    showError = false,
    sourceText = item.conditionText,
    externalIsCurrent = () => true,
  ) {
    const generation = requestGeneration
    if (!isCurrent(generation, externalIsCurrent) || !options.projectId.value || !options.savedRoute.value) return false
    const finishBusy = beginConditionBusy(item.segment.id)
    try {
      const response = await parseRuleCondition({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
        segment_id: item.segment.id,
        source_text: sourceText,
        process_id: exportProcessIdForItem(item),
        process_name: normalizeExportProcessName(options.displayName(item.segment)),
        processes: options.conditionProcessOptions.value,
      })
      if (!isCurrent(generation, externalIsCurrent) || !hasCurrentConditionText(item.segment.id, sourceText)) return false
      applyConditionReview(item.segment.id, response.review)
      return response.review.status !== 'invalid'
    } catch (error: unknown) {
      if (!isCurrent(generation, externalIsCurrent)) return false
      if (await options.onWorkflowConflict(error)) return false
      if (showError && isCurrent(generation, externalIsCurrent)) {
        console.error('条件候选规则生成失败', error)
        options.onNotice('暂时无法识别规则', '请补充明确的判断条件、比较关系或取值后重试。', asErrorMessage(error))
      }
      return false
    } finally {
      finishBusy()
    }
  }

  async function handleBatchParseConditions(
    queue = [...options.batchEligibleCards.value],
    externalIsCurrent = () => true,
  ) {
    if (batchParsing.value || !queue.length || !externalIsCurrent()) return
    const executionId = ++batchParseExecutionId
    const generation = requestGeneration
    batchParsing.value = true
    batchParseCompleted.value = 0
    batchParseTotal.value = queue.length
    batchNotice.value = ''
    let cursor = 0
    let successCount = 0

    async function worker() {
      while (cursor < queue.length && isCurrent(generation, externalIsCurrent)) {
        const item = queue[cursor++]
        if (!item) continue
        if (await parseConditionItem(item, false, item.conditionText, externalIsCurrent)) successCount += 1
        if (!isCurrent(generation, externalIsCurrent)) return
        batchParseCompleted.value += 1
      }
    }

    try {
      await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
      if (!isCurrent(generation, externalIsCurrent)) return
      const failedCount = queue.length - successCount
      setBatchNotice(failedCount
        ? `已识别 ${successCount} 条规则；${failedCount} 条还需要补充。`
        : `已识别 ${successCount} 条规则。`)
      options.onlyPending.value = true
    } finally {
      if (executionId === batchParseExecutionId) batchParsing.value = false
    }
  }

  async function handleCompleteReview() {
    if (batchReviewing.value || !options.autoConfirmableReviewCards.value.length || !options.projectId.value || !options.savedRoute.value) return
    const queue = [...options.autoConfirmableReviewCards.value]
    const executionId = ++batchReviewExecutionId
    const generation = requestGeneration
    batchReviewing.value = true
    batchReviewCompleted.value = 0
    batchReviewTotal.value = queue.length
    batchNotice.value = ''
    let cursor = 0
    let successCount = 0

    async function worker() {
      while (cursor < queue.length && isCurrent(generation, () => true)) {
        const item = queue[cursor++]
        const review = item?.conditionReview
        if (!item || !review?.candidate || !review.source_hash) continue
        const finishBusy = beginConditionBusy(item.segment.id)
        try {
          const response = await confirmRuleCondition({
            project_id: options.projectId.value!,
            route_id: options.savedRoute.value!.route_id,
            expected_workflow_revision: options.savedRoute.value!.workflow_revision,
            segment_id: item.segment.id,
            source_text: item.conditionText,
            source_hash: review.source_hash,
            candidate: review.candidate,
            processes: options.conditionProcessOptions.value,
            confirmed_by: '规则包整体审核',
          })
          if (!isCurrent(generation, () => true)) return
          applyConditionReview(item.segment.id, response.review)
          successCount += 1
        } catch (error: unknown) {
          if (!isCurrent(generation, () => true)) return
          if (await options.onWorkflowConflict(error)) return
          if (isCurrent(generation, () => true)) console.error(`规则审核失败：${item.segment.id}`, error)
        } finally {
          finishBusy()
          if (executionId === batchReviewExecutionId) batchReviewCompleted.value += 1
        }
      }
    }

    try {
      await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
      if (!isCurrent(generation, () => true)) return
      const failedCount = queue.length - successCount
      setBatchNotice(failedCount
        ? `已自动审核 ${successCount} 条规则；${failedCount} 条需要检查。`
        : '')
    } finally {
      if (executionId === batchReviewExecutionId) batchReviewing.value = false
    }
  }

  async function handleConfirmCondition(item: FinalizeCard, candidate: RuleConditionCandidate) {
    if (!options.projectId.value || !options.savedRoute.value || !item.conditionReview?.source_hash) return
    if (!options.factorCatalogReady.value) {
      options.factorCatalogError.value ||= '标准因子目录尚未加载，请重试后再确认规则。'
      return
    }
    if ((candidate.kind || 'condition') === 'condition' && candidate.when) {
      const binding = factorBindingState(candidate.when, options.standardFactors.value)
      if (!binding.complete) {
        options.onNotice(
          '规则尚未完整绑定标准因子',
          '请在条件编辑器中处理所有未绑定或冲突的条件后再保存。',
          binding.issues.map(issue => `${issue.path || '条件'}：${issue.message}`).join('\n'),
        )
        return
      }
    }
    if (conditionBusySegmentIds.value.has(item.segment.id)) return
    const generation = requestGeneration
    options.onPublishedRuleOutdated()
    const finishBusy = beginConditionBusy(item.segment.id)
    try {
      const response = await confirmRuleCondition({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
        segment_id: item.segment.id,
        source_text: item.conditionText,
        source_hash: item.conditionReview.source_hash,
        candidate,
        processes: options.conditionProcessOptions.value,
        confirmed_by: '默认用户',
      })
      if (!isCurrent(generation, () => true)) return
      applyConditionReview(item.segment.id, response.review)
    } catch (error: unknown) {
      if (!isCurrent(generation, () => true)) return
      if (await options.onWorkflowConflict(error)) return
      if (isConditionSourceConflict(error)) {
        const refreshed = await parseConditionItem(item, false)
        setBatchNotice(refreshed
          ? `"「${options.displayName(item.segment)}」"的候选已按最新条件更新，请核对后再审核。`
          : `"「${options.displayName(item.segment)}」"的条件已更新，请先补充条件后重新生成候选。`)
        return
      }
      options.onNotice('规则确认失败', '候选规则尚未确认，请检查条件和目标工序后重试。', asErrorMessage(error))
    } finally {
      finishBusy()
    }
  }

  async function handleSetMainline(item: FinalizeCard) {
    if (!options.projectId.value || !options.savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
    const processName = normalizeExportProcessName(options.displayName(item.segment))
    const sourceText = `设置为主工序，始终纳入“${processName}”工序。`
    const generation = requestGeneration
    options.onPublishedRuleOutdated()
    const finishBusy = beginConditionBusy(item.segment.id)
    try {
      const response = await saveRuleConditionDraft({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
        segment_id: item.segment.id,
        source_text: sourceText,
      })
      if (!isCurrent(generation, () => true)) return
      options.onConditionTextDraft(item, sourceText)
      applyConditionReview(item.segment.id, response.review)
      setBatchNotice(`"「${processName}」"已转为主工序。`)
    } catch (error: unknown) {
      if (!isCurrent(generation, () => true)) return
      if (await options.onWorkflowConflict(error)) return
      options.onNotice('转换主工序失败', '当前工序尚未改变，请稍后重试。', asErrorMessage(error))
    } finally {
      finishBusy()
    }
  }

  async function handleSetBoolean(item: FinalizeCard, label: string) {
    if (!options.projectId.value || !options.savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
    const processName = normalizeExportProcessName(options.displayName(item.segment))
    const switchLabel = label.trim()
    if (!switchLabel) return
    const sourceText = `当用户选择“${switchLabel}”为是时，纳入“${processName}”工序。`
    const candidate = buildManualBooleanRuleCandidate(item, switchLabel)
    const generation = requestGeneration
    options.onPublishedRuleOutdated()
    const finishBusy = beginConditionBusy(item.segment.id)
    try {
      const response = await setManualRuleCondition({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
        segment_id: item.segment.id,
        process_id: exportProcessIdForItem(item),
        source_text: sourceText,
        candidate,
        processes: options.conditionProcessOptions.value,
        confirmed_by: '用户直接设定',
      })
      if (!isCurrent(generation, () => true)) return
      options.onConditionTextDraft(item, sourceText)
      applyConditionReview(item.segment.id, response.review)
      setBatchNotice(`"「${processName}」"已转为用户控制的 Bool 条件。`)
    } catch (error: unknown) {
      if (!isCurrent(generation, () => true)) return
      if (await options.onWorkflowConflict(error)) return
      options.onNotice('转换 Bool 条件失败', '当前工序尚未改变，请检查开关名称后重试。', asErrorMessage(error))
    } finally {
      finishBusy()
    }
  }

  async function handleRuleReview() {
    if (
      reviewingRules.value
      || batchParsing.value
      || batchReviewing.value
    ) return
    if (!options.factorCatalogReady.value) {
      options.factorCatalogError.value ||= '标准因子目录尚未加载，请重试后再进行规则审核。'
      return
    }
    const generation = requestGeneration
    reviewingRules.value = true
    batchNotice.value = ''
    try {
      if (options.batchEligibleCards.value.length) {
        await handleBatchParseConditions([...options.batchEligibleCards.value])
        await nextTick()
      }
      if (!isCurrent(generation, () => true)) return
      if (options.autoConfirmableReviewCards.value.length) {
        await handleCompleteReview()
        await nextTick()
      }
      if (!isCurrent(generation, () => true)) return
      const remaining = [...options.pendingRuleCards.value]
      options.onlyPending.value = Boolean(remaining.length)
      if (remaining.length) {
        options.activeSegmentId.value = remaining[0]?.segment.id || options.activeSegmentId.value
        batchNotice.value = `系统已自动处理可安全确认的规则；还有 ${remaining.length} 道工序需要人工处理。`
      } else {
        setBatchNotice('规则审核完成。')
      }
    } finally {
      if (generation === requestGeneration) reviewingRules.value = false
    }
  }

  return {
    conditionBusySegmentIds,
    batchParsing,
    batchParseCompleted,
    batchParseTotal,
    batchReviewing,
    batchReviewCompleted,
    batchReviewTotal,
    reviewingRules,
    batchNotice,
    beginConditionBusy,
    setBatchNotice,
    asErrorMessage,
    applyConditionReview,
    parseConditionItem,
    handleParseCondition: (item: FinalizeCard) => parseConditionItem(item, true),
    handleBatchParseConditions,
    handleCompleteReview,
    handleConfirmCondition,
    handleSetMainline,
    handleSetBoolean,
    handleRuleReview,
    cancelPendingRequests,
  }
}
