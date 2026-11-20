import { computed, getCurrentScope, onActivated, onDeactivated, onMounted, onScopeDispose, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { ElMessage } from 'element-plus'
import type { FactorCandidate } from '@/components/analysis/types'
import { resetWorkflow, saveSegmentRuleReview, type SegmentFactorReview } from '@/api'
import {
  applyRuleReviewUpdateToRoute,
  buildDocOperationHighlights,
  buildFactorCandidates,
  buildRuleCandidateSummary,
  canAutoAcceptSegmentReview,
  displayFactorLabel,
  extractOperationNotes,
  formatDateTimeLabel,
  formatPercentLabel,
  segmentDisplayName,
  segmentCanDefaultComplete,
  segmentHasRuleDecision,
  segmentNeedsMergeNameQuestion,
  segmentCoverageLabel,
  segmentProgressClass,
  segmentProgressLabel,
} from '@/composables/analysisWorkspaceHelpers'
import { buildProjectRouteQuery } from '@/composables/useCurrentProject'
import { useAnalysisDocumentTextCache } from '@/composables/useAnalysisDocumentTextCache'
import { useAnalysisDocumentPreview } from '@/composables/useAnalysisDocumentPreview'
import { useAnalysisSegmentNavigation } from '@/composables/useAnalysisSegmentNavigation'
import { useAnalysisQuestionTree } from '@/composables/useAnalysisQuestionTree'
import { classifySegmentMode } from '@/composables/analysisQuestionTreeFlow'
import { buildResultSummary } from '@/composables/analysisQuestionTreeNodes'
import { answersFromTrail, savedQuestionTrail } from '@/composables/analysisQuestionTreeState'
import { useAnalysisReviewPersistence } from '@/composables/useAnalysisReviewPersistence'
import { useAnalysisWorkspaceData } from '@/composables/useAnalysisWorkspaceData'
import { startRulePreprocessingForSavedRoute } from '@/composables/rulePreprocessingTrigger'
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'
import { publishWorkflowReset, workflowResetSignal } from '@/composables/workflowResetState'

export function useAnalysisWorkspace() {
  const route = useRoute()
  const router = useRouter()
  let analysisViewActive = false
  let initialLoadFinished = false
  let loadedDataRevision = -1
  const {
    loading,
    error,
    projectId,
    savedRoute,
    selectedSegmentId,
    operations,
    supersetOperations,
    documents,
    detailRows,
    analysisGuidance,
    guidanceError,
    guidanceErrorReason,
    guidanceGenerating,
    generationElapsedSeconds,
    loadSavedRoute,
    resolveProjectId,
  } = useAnalysisWorkspaceData({
    getRouteProjectId: () => route.query.project_id as string | undefined,
  })
  const ruleReviewNote = ref('')
  const recommendationSummary = ref('')
  const analysisReadOnly = computed(() => Boolean(savedRoute.value?.analysis_locked))
  const resettingWorkflow = ref(false)
  let disposed = false
  let adoptionContext = 0
  // Transient feedback belongs to one operation in one route/workflow context.
  // A context counter also catches a switch away and back before a save returns.
  watch([
    projectId, () => savedRoute.value?.route_id, () => savedRoute.value?.workflow_revision,
    analysisReadOnly, loading, guidanceGenerating, resettingWorkflow,
  ], () => {
    adoptionContext++
    recommendationSummary.value = ''
  }, { flush: 'sync' })
  watch(savedRoute, () => { recommendationSummary.value = '' }, { flush: 'sync' })
  if (getCurrentScope()) onScopeDispose(() => {
    disposed = true
    adoptionContext++
  })
  let locallyHandledResetAt = 0
  const sampleCompareExpanded = ref(false)
  const evidenceExcerptExpanded = ref(false)
  const evidenceRowsExpanded = ref(false)

  const selectedSegment = computed(() =>
    savedRoute.value?.segments.find(segment => segment.id === selectedSegmentId.value)
    || savedRoute.value?.segments[0]
    || null,
  )

  const {
    documentPreviewLoading,
    documentPreviewError,
    documentPreview,
    documentPreviewVisible,
    documentPreviewFileUrl,
    documentPreviewPdfPageUrls,
    openDocumentPreview,
    closeDocumentPreview,
    openDocumentOriginal,
    clearDocumentPreviewPdfPages,
  } = useAnalysisDocumentPreview()

  const {
    completedSegmentCount,
    inProgressSegmentCount,
    pendingSegmentCount,
    selectedSegmentIndex,
    hasNextPendingSegment,
    goToPrevSegment,
    goToNextSegment,
    goToNextPendingSegment,
  } = useAnalysisSegmentNavigation({
    savedRoute,
    selectedSegment,
    selectedSegmentId,
    isSegmentRejudging: (s) => isSegmentRejudging(s),
  })

  const selectedSegmentOperations = computed(() => {
    if (!selectedSegment.value) return []
    const opIds = new Set(selectedSegment.value.source_operation_ids || [])
    return operations.value.filter(operation => opIds.has(operation.id))
  })

  const selectedSegmentReviewMap = computed(() => {
    const pairs = (selectedSegment.value?.factor_reviews || []).map(review => [review.factor_name, review] as const)
    return new Map<string, SegmentFactorReview>(pairs)
  })

  const selectedSegmentMatchedDocIds = computed(() => {
    const ids = new Set<number>()
    ;(selectedSegment.value?.matched_detail_rows || []).forEach((row) => {
      const docId = Number(row.document_id || 0)
      if (docId > 0) ids.add(docId)
    })
    return ids
  })

  const {
    documentPreviewTextMap,
    clearDocumentPreviewTexts,
    ensureMatchedDocumentPreviewTexts,
    ensureDocumentPreviewTextsForDocIds,
  } = useAnalysisDocumentTextCache({
    selectedDocIds: selectedSegmentMatchedDocIds,
  })

  function getDocumentTextsForDocIds(docIds: Set<number>): string[] {
    return Array.from(docIds)
      .map(docId => documentPreviewTextMap.value[docId] || '')
      .filter(Boolean)
  }

  const selectedSegmentMatchedDocTexts = computed(() =>
    Array.from(selectedSegmentMatchedDocIds.value)
      .map(docId => documentPreviewTextMap.value[docId] || '')
      .filter(Boolean),
  )

  const hitDocuments = computed(() =>
    documents.value.filter(doc => selectedSegmentMatchedDocIds.value.has(doc.id)),
  )

  const missingDocuments = computed(() =>
    documents.value.filter(doc => !selectedSegmentMatchedDocIds.value.has(doc.id)),
  )

  const selectedSegmentSourceNameSet = computed(() => {
    const bucket = new Set<string>()
    const pushName = (value?: string | null) => {
      const text = (value || '').trim()
      if (text) bucket.add(text)
    }
    pushName(selectedSegment.value?.normalized_step_name)
    ;(selectedSegment.value?.source_nodes || []).forEach(pushName)
    ;(selectedSegment.value?.matched_detail_rows || []).forEach((row) => {
      pushName(row.operation_name)
    })
    return bucket
  })

  const selectedSegmentVariantNames = computed(() => {
    const counter = new Map<string, number>()
    ;(selectedSegment.value?.matched_detail_rows || []).forEach((row) => {
      const name = (row.operation_name || '').trim()
      if (!name) return
      counter.set(name, (counter.get(name) || 0) + 1)
    })
    return Array.from(counter.entries())
      .map(([name, count]) => ({ name, count }))
      .sort((a, b) => {
        if (a.count !== b.count) return b.count - a.count
        return a.name.localeCompare(b.name)
      })
  })

  const hitDocOperationHighlights = computed(() =>
    buildDocOperationHighlights(
      detailRows.value,
      hitDocuments.value.map(doc => doc.id),
      selectedSegmentSourceNameSet.value,
    ),
  )

  const missingDocOperationHighlights = computed(() =>
    buildDocOperationHighlights(
      detailRows.value,
      missingDocuments.value.map(doc => doc.id),
      selectedSegmentSourceNameSet.value,
    ),
  )

  const rawFactorCandidates = computed<FactorCandidate[]>(() => {
    return buildFactorCandidates({
      operations: selectedSegmentOperations.value,
      reviewMap: selectedSegmentReviewMap.value,
      segment: selectedSegment.value,
      documents: documents.value,
      variantNames: selectedSegmentVariantNames.value.map(item => item.name),
    })
  })

  const defaultAcceptedSegment = computed(() => {
    if (!selectedSegment.value || currentRuleReview.value) return false
    const mode = classifySegmentMode(selectedSegment.value)
    if (mode === 'merge_name') return false
    return segmentCanDefaultComplete(selectedSegment.value)
  })

  const factorCandidates = computed<FactorCandidate[]>(() => rawFactorCandidates.value)

  const confirmedFactorLabels = computed(() =>
    factorCandidates.value
      .filter(factor => factor.review?.decision === 'confirmed')
      .map(factor => displayFactorLabel(factor.name)),
  )

  const excludedFactorLabels = computed(() =>
    factorCandidates.value
      .filter(factor => factor.review?.decision === 'excluded')
      .map(factor => displayFactorLabel(factor.name)),
  )

  const operationReviewNotes = computed(() =>
    extractOperationNotes(selectedSegmentOperations.value),
  )

  const ruleCandidateSummary = computed(() => {
    return buildRuleCandidateSummary({
      segment: selectedSegment.value,
      documents: documents.value,
      hitCount: hitDocuments.value.length,
      missCount: missingDocuments.value.length,
      confirmedFactorLabels: confirmedFactorLabels.value,
      excludedFactorLabels: excludedFactorLabels.value,
      hitHighlights: hitDocOperationHighlights.value,
      missingHighlights: missingDocOperationHighlights.value,
      variantNames: selectedSegmentVariantNames.value,
      operationNotes: operationReviewNotes.value,
    })
  })

  const currentRuleReview = computed(() =>
    segmentHasRuleDecision(selectedSegment.value) ? (selectedSegment.value?.rule_review || null) : null,
  )
  const hideLegacySavedQuestionTreeReview = computed(() => {
    if (!segmentNeedsMergeNameQuestion(selectedSegment.value)) return false
    const trail = currentRuleReview.value?.question_trail || []
    return !trail.some(item => String(item?.nodeId || '') === 'merge_name_root')
  })
  const confirmedFactorCount = computed(() =>
    factorCandidates.value.filter(factor => factor.review?.decision === 'confirmed').length,
  )
  const excludedFactorCount = computed(() =>
    factorCandidates.value.filter(factor => factor.review?.decision === 'excluded').length,
  )
  const pendingFactorCount = computed(() =>
    factorCandidates.value.filter(factor => !factor.review).length,
  )
  function resetAnalysisPanelState() {
    ruleReviewNote.value = selectedSegment.value?.rule_review?.note || ''
    sampleCompareExpanded.value = false
    evidenceExcerptExpanded.value = false
    evidenceRowsExpanded.value = false
  }
  const {
    questionTreeVisible,
    questionTreeEmptyReason,
    questionTreeCurrentQuestion,
    questionTreeSourceHint,
    questionTreeTrail,
    questionTreeResultSummary,
    questionTreeNoteDraft,
    questionTreeIsRejudging,
    chooseQuestionTreeOption,
    chooseQuestionTreeOptions,
    reanswerLastQuestionTree: reanswerLastTreeQuestion,
    resetQuestionTree: resetSelectedQuestionTree,
    resetAllQuestionTrees,
    updateQuestionTreeNote,
    acceptAllRecommendedQuestionTree,
    acceptAllRecommendedForAllSegments: acceptAllRecommendedTreeAnswers,
    clearQuestionTreeRejudging,
    isSegmentRejudging,
    getTrailForSegment,
    getResultSummaryForSegment,
    getNoteDraftForSegment,
    getAnalysisDraftForSegment,
    getMissingAnswerForSegment,
    getGuidanceForSegment,
  } = useAnalysisQuestionTree({
    guidance: computed(() => analysisGuidance.value),
    segments: computed(() => savedRoute.value?.segments || []),
    readOnly: analysisReadOnly,
    projectId: computed(() => projectId.value),
    routeId: computed(() => savedRoute.value?.route_id ?? null),
    workflowRevision: computed(() => savedRoute.value?.workflow_revision ?? null),
    selectedSegment,
    detailRows: computed(() => detailRows.value),
    selectedSegmentMatchedDocIds,
    matchedDocumentTexts: selectedSegmentMatchedDocTexts,
    getDocumentTextsForDocIds,
    documents: computed(() => documents.value),
  })
  function clearAdoptionFeedbackForReanswer() {
    adoptionContext++
    recommendationSummary.value = ''
  }
  function reanswerLastQuestionTree() {
    if (disposed || analysisReadOnly.value || !selectedSegment.value) return
    clearAdoptionFeedbackForReanswer()
    reanswerLastTreeQuestion()
  }
  function resetQuestionTree() {
    if (disposed || analysisReadOnly.value || !selectedSegment.value) return
    clearAdoptionFeedbackForReanswer()
    resetSelectedQuestionTree()
  }
  const questionTreeInProgress = computed(() =>
    questionTreeVisible.value && !!questionTreeCurrentQuestion.value,
  )
  const regeneratedQuestionTreeSavedConclusion = computed(() => {
    if (questionTreeIsRejudging.value || hideLegacySavedQuestionTreeReview.value) return ''
    const segment = selectedSegment.value
    if (!segment) return ''
    const trail = savedQuestionTrail(segment)
    if (segment.rule_review?.analysis_draft?.status === 'confirmed') return segment.rule_review.analysis_draft.condition_text
    if (!trail.length) return ''
    return buildResultSummary(
      segment.normalized_step_name,
      answersFromTrail(trail),
      currentRuleReview.value?.note || '',
    )
  })
  const questionTreeSavedSummaryLines = computed(() => {
    if (questionTreeIsRejudging.value || hideLegacySavedQuestionTreeReview.value) return []
    const lines = [
      regeneratedQuestionTreeSavedConclusion.value,
      ...(currentRuleReview.value?.summary_lines || []),
    ]
      .map(line => String(line || '').trim())
      .filter(Boolean)
      .filter(line => !/目前可先确认|主要因为|目前可先统一/.test(line))
    return Array.from(new Set(lines))
  })
  const questionTreeSavedTrail = computed(() =>
    questionTreeIsRejudging.value || hideLegacySavedQuestionTreeReview.value
      ? []
      : savedQuestionTrail(selectedSegment.value),
  )
  const showQuestionTreePanel = computed(() => {
    if (questionTreeIsRejudging.value) return true
    if (defaultAcceptedSegment.value) return false
    return (
      questionTreeVisible.value
      || questionTreeSavedSummaryLines.value.length > 0
      || questionTreeSavedTrail.value.length > 0
    )
  })

  async function reloadSavedRouteWorkspace(forceRefresh = false, retryRecommendations = false) {
    clearDocumentPreviewTexts()
    await loadSavedRoute(forceRefresh, retryRecommendations)
    loadedDataRevision = getWorkflowDataRevision()
  }

  async function applyAnalysisWorkflowReset() {
    resetAllQuestionTrees()
    ruleReviewNote.value = ''
    await reloadSavedRouteWorkspace(true)
    const firstPending = savedRoute.value?.segments.find(segment => !segmentHasRuleDecision(segment))
    selectedSegmentId.value = firstPending?.id || savedRoute.value?.segments[0]?.id || ''
    resetAnalysisPanelState()
  }

  async function resetAllAnalysisAnswers(onResetApplied?: () => void) {
    if (disposed || resettingWorkflow.value || !projectId.value || !savedRoute.value) return false
    resettingWorkflow.value = true
    error.value = ''
    const resetProjectId = projectId.value
    const resetRoute = savedRoute.value
    const resetRevision = resetRoute.workflow_revision
    let resetInvalidated = false
    const stopResetWatch = watch([projectId, savedRoute, () => savedRoute.value?.route_id,
      () => savedRoute.value?.workflow_revision], () => {
      resetInvalidated = true
    }, { flush: 'sync' })
    const isCurrentReset = () => !disposed && !resetInvalidated
    try {
      const result = await resetWorkflow({
        project_id: resetProjectId,
        from_step: 3,
        expected_workflow_revision: resetRevision,
      })
      if (!isCurrentReset() || result.project_id !== resetProjectId) return false
      // Reloading after our own successful reset deliberately replaces the route.
      stopResetWatch()
      publishWorkflowReset({
        projectId: result.project_id,
        fromStep: 3,
        workflowRevision: result.workflow_revision,
      })
      locallyHandledResetAt = workflowResetSignal.value?.emittedAt || 0
      onResetApplied?.()
      await applyAnalysisWorkflowReset()
      return !disposed && projectId.value === resetProjectId
    } catch (e: any) {
      if (!isCurrentReset()) return false
      console.error('重新回答全部失败', e)
      error.value = e?.response?.data?.detail?.message
        || e?.response?.data?.detail
        || '重新回答全部失败，请刷新页面后重试。'
      return false
    } finally {
      stopResetWatch()
      resettingWorkflow.value = false
    }
  }

  function triggerRulePreprocessing() {
    void startRulePreprocessingForSavedRoute({
      projectId: projectId.value,
      savedRoute: savedRoute.value,
      supersetOperations: supersetOperations.value,
      segmentDisplayName,
    })
  }

  const {
    persistRuleReview,
    cancelPendingRuleReviews,
    waitForPendingRuleReviews,
  } = useAnalysisReviewPersistence({
    projectId,
    savedRoute,
    selectedSegment,
    selectedSegmentId,
    ruleReviewNote,
    error,
    ruleCandidateSummary,
    questionTreeTrail,
    getAnalysisDraft: getAnalysisDraftForSegment,
    getQuestionTrail: getTrailForSegment,
    isSaveAllowed: () => !resettingWorkflow.value && !loading.value
      && !guidanceGenerating.value && !!analysisGuidance.value,
    clearQuestionTreeRejudging,
    goToNextPendingSegment,
    onWorkflowConflict: () => applyAnalysisWorkflowReset(),
    onRuleReviewSaved: triggerRulePreprocessing,
  })

  function goBackToExtract() {
    router.push({
      path: '/extract',
      query: buildProjectRouteQuery(projectId.value, { resume: 'route_merge', from: 'analysis' }),
    })
  }

  function handleKeydown(e: KeyboardEvent) {
    if (!savedRoute.value?.segments.length) return
    const segments = savedRoute.value.segments
    const idx = segments.findIndex(s => s.id === selectedSegmentId.value)
    if (idx === -1) return
    if (e.key === 'ArrowDown' || e.key === 'j') {
      e.preventDefault()
      const next = Math.min(idx + 1, segments.length - 1)
      const nextSegment = segments[next]
      if (nextSegment) selectedSegmentId.value = nextSegment.id
    } else if (e.key === 'ArrowUp' || e.key === 'k') {
      e.preventDefault()
      const prev = Math.max(idx - 1, 0)
      const prevSegment = segments[prev]
      if (prevSegment) selectedSegmentId.value = prevSegment.id
    }
  }

  watch(() => route.query.project_id, async () => {
    if (!analysisViewActive) return
    resolveProjectId()
    await reloadSavedRouteWorkspace()
  })

  watch(workflowResetSignal, (signal) => {
    if (!signal || signal.emittedAt === locallyHandledResetAt) return
    if (signal.projectId !== projectId.value || signal.fromStep > 3) return
    locallyHandledResetAt = signal.emittedAt
    if (!analysisViewActive) {
      resetAllQuestionTrees()
      ruleReviewNote.value = ''
      loadedDataRevision = -1
      return
    }
    void applyAnalysisWorkflowReset()
  })

  watch(selectedSegment, async () => {
    resetAnalysisPanelState()
    void ensureMatchedDocumentPreviewTexts()
  })

  const autoRuleDecision = computed<'accepted' | 'rejected' | null>(() => {
    if (loading.value || guidanceGenerating.value || !analysisGuidance.value) return null
    if (!selectedSegment.value) return null
    if (canAutoAcceptSegmentReview({
      hasQuestionTree: questionTreeVisible.value,
      questionTreeInProgress: questionTreeInProgress.value,
      questionTreeResultSummary: questionTreeResultSummary.value,
      confirmedFactorCount: confirmedFactorCount.value,
      excludedFactorCount: excludedFactorCount.value,
      pendingFactorCount: pendingFactorCount.value,
      allowDefaultAccept: defaultAcceptedSegment.value,
    })) {
      return 'accepted'
    }
    return null
  })

  const batchAcceptingAll = ref(false)
  const batchAcceptProgress = ref('')

  async function handleAcceptAllRecommendedForAllSegments() {
    if (disposed || analysisReadOnly.value || resettingWorkflow.value || guidanceGenerating.value || loading.value) return
    if (!analysisGuidance.value) return
    if (!savedRoute.value || !projectId.value || batchAcceptingAll.value) return
    batchAcceptingAll.value = true
    recommendationSummary.value = ''
    error.value = ''
    batchAcceptProgress.value = '正在保存已完成的回答...'
    const batchProjectId = projectId.value
    let batchRouteSnapshot = savedRoute.value
    const batchRouteId = savedRoute.value.route_id
    const batchWorkflowRevision = savedRoute.value.workflow_revision
    const batchContext = adoptionContext
    const isCurrentBatch = () => !disposed && adoptionContext === batchContext
      && projectId.value === batchProjectId
      && !analysisReadOnly.value
      && !resettingWorkflow.value
      && !guidanceGenerating.value
      && !loading.value
      && savedRoute.value === batchRouteSnapshot
      && savedRoute.value?.route_id === batchRouteId
      && savedRoute.value?.workflow_revision === batchWorkflowRevision

    let adopted = 0
    try {
      // Stop new autosaves first, then let captured answers finish. Our own
      // autosaves replace the route object, so take batch ownership afterward.
      if (!await waitForPendingRuleReviews()) return
      if (projectId.value !== batchProjectId || savedRoute.value?.route_id !== batchRouteId
          || savedRoute.value?.workflow_revision !== batchWorkflowRevision) return
      batchRouteSnapshot = savedRoute.value
      if (!isCurrentBatch()) return
      const segments = savedRoute.value.segments || []
      const targets = segments.filter(s => !segmentHasRuleDecision(s) || isSegmentRejudging(s))
      if (!targets.length) return
      recommendationSummary.value = ''
      const needsAnswer: string[] = []
      batchAcceptProgress.value = '正在加载样本依据...'
      const allTargetDocIds = new Set<number>()
      targets.forEach((seg) => {
        ;(seg.matched_detail_rows || []).forEach((row: any) => {
          const docId = Number(row.document_id || 0)
          if (docId > 0) allTargetDocIds.add(docId)
        })
      })
      if (!allTargetDocIds.size) {
        documents.value.forEach((doc) => {
          if (doc.id > 0) allTargetDocIds.add(doc.id)
        })
      }
      await ensureDocumentPreviewTextsForDocIds(Array.from(allTargetDocIds))
      if (!isCurrentBatch()) return

      acceptAllRecommendedTreeAnswers(segments)

      batchAcceptProgress.value = `0/${targets.length}`
      for (let i = 0; i < targets.length; i++) {
        if (!isCurrentBatch()) return
        const seg = targets[i]
        if (!seg || !savedRoute.value) continue

        const hitCount = seg.doc_coverage?.hit_docs || 0
        const missCount = Math.max(0, (documents.value.length || 0) - hitCount)
        const baseSummaryLines = buildRuleCandidateSummary({
          segment: seg,
          documents: documents.value,
          hitCount,
          missCount,
          confirmedFactorLabels: [],
          excludedFactorLabels: [],
          hitHighlights: [],
          missingHighlights: [],
          variantNames: [],
          operationNotes: [],
        })

        const trail = getTrailForSegment(seg)
        const note = getNoteDraftForSegment(seg)
        const conclusion = getResultSummaryForSegment(seg)
        const analysisDraft = getAnalysisDraftForSegment(seg)
        if (analysisDraft === null && !segmentCanDefaultComplete(seg)) {
          needsAnswer.push(`${seg.normalized_step_name}（缺少${getMissingAnswerForSegment(seg)}）`)
          continue
        }
        const summaryLines = [
          ...(conclusion ? [conclusion] : []),
          ...baseSummaryLines,
        ]

        let result
        try {
          result = await saveSegmentRuleReview({
            project_id: batchProjectId,
            route_id: batchRouteId,
            expected_workflow_revision: batchWorkflowRevision,
            segment_id: seg.id,
            decision: 'accepted',
            note,
            summary_lines: summaryLines,
            question_trail: trail,
            ...(analysisDraft ? { analysis_draft: analysisDraft } : {}),
          })
        } catch (err: any) {
          if (!isCurrentBatch()) return
          const detail = err?.response?.data?.detail
          if (detail?.code !== 'stale_object_reuse') throw err
          needsAnswer.push(`${seg.normalized_step_name}（${detail.message || '前序加工对象需重新确认'}）`)
          continue
        }

        if (!isCurrentBatch()) return
        if (result?.project_id !== batchProjectId || result.route_id !== batchRouteId
            || result.segment_id !== seg.id || result.rule_review?.decision !== 'accepted'
            || !savedRoute.value.segments.some(segment => segment.id === seg.id)) {
          throw new Error('采纳保存结果与当前工序不一致。')
        }
        savedRoute.value = applyRuleReviewUpdateToRoute(savedRoute.value, result)
        batchRouteSnapshot = savedRoute.value!
        for (const id of result.invalidated_segment_ids || []) {
          const dependent = batchRouteSnapshot.segments.find(item => item.id === id)
          if (dependent && !targets.some(item => item.id === id)) targets.push(dependent)
        }
        if (result.invalidated_segment_ids?.length) acceptAllRecommendedTreeAnswers(batchRouteSnapshot.segments)
        clearQuestionTreeRejudging(seg.id)
        adopted += 1
        batchAcceptProgress.value = `${adopted}/${targets.length}`
      }

      resetAnalysisPanelState()
      const remaining = needsAnswer.length ? `${needsAnswer.length} 道还需手动回答或重试：${needsAnswer.join('、')}。` : ''
      if (!adopted) {
        error.value = `尚无完整推荐可采纳；${remaining}`
        return
      }
      recommendationSummary.value = remaining
        ? `已采纳 ${adopted} 道工序推荐；${remaining}`
        : `已采纳 ${adopted} 道工序推荐。`

      Promise.resolve(triggerRulePreprocessing()).catch((err) => {
        console.warn('一键采纳后触发预处理失败', err)
      })
    } catch (err: any) {
      if (!isCurrentBatch()) return
      if (err?.response?.data?.detail?.code === 'analysis_locked') {
        await applyAnalysisWorkflowReset()
        return
      }
      console.error('批量采纳推荐失败', err)
      error.value = adopted
        ? `批量采纳失败，已保存 ${adopted} 道工序推荐，其余尚未保存，请重试。`
        : '批量采纳失败，未保存任何工序推荐，请重试。'
      ElMessage.error(error.value)
    } finally {
      batchAcceptingAll.value = false
      batchAcceptProgress.value = ''
    }
  }

  watch(
    [selectedSegmentId, autoRuleDecision, currentRuleReview, questionTreeIsRejudging, questionTreeTrail],
    async ([segmentId, nextDecision, review]) => {
      if (!segmentId) return
      if (!nextDecision) {
        cancelPendingRuleReviews(segmentId)
        return
      }
      if (analysisReadOnly.value || resettingWorkflow.value) return
      if (batchAcceptingAll.value) return
      if (review?.decision === nextDecision && !questionTreeIsRejudging.value) return
      await persistRuleReview(nextDecision, { autoAdvance: false })
    },
    { flush: 'post' },
  )

  onMounted(async () => {
    resolveProjectId()
    try {
      await reloadSavedRouteWorkspace()
      resetAnalysisPanelState()
    } finally {
      initialLoadFinished = true
    }
  })

  onActivated(() => {
    analysisViewActive = true
    window.addEventListener('keydown', handleKeydown)
    if (!initialLoadFinished || loading.value) return

    const routeProjectId = Number(route.query.project_id || 0)
    const projectChanged = routeProjectId > 0 && routeProjectId !== projectId.value
    if (!projectChanged && loadedDataRevision === getWorkflowDataRevision()) return

    resolveProjectId()
    void reloadSavedRouteWorkspace(true).then(resetAnalysisPanelState)
  })

  onDeactivated(() => {
    analysisViewActive = false
    loadedDataRevision = getWorkflowDataRevision()
    window.removeEventListener('keydown', handleKeydown)
  })

  onUnmounted(() => {
    analysisViewActive = false
    clearDocumentPreviewPdfPages()
    window.removeEventListener('keydown', handleKeydown)
  })

  return {
    analysisGuidance,
    guidanceError,
    guidanceErrorReason,
    guidanceGenerating,
    generationElapsedSeconds,
    recommendationSummary,
    getGuidanceForSegment,
    getAnalysisDraftForSegment,
    loading,
    analysisReadOnly,
    resettingWorkflow,
    error,
    projectId,
    savedRoute,
    selectedSegmentId,
    supersetOperations,
    sampleCompareExpanded,
    evidenceExcerptExpanded,
    evidenceRowsExpanded,
    documentPreviewLoading,
    documentPreviewError,
    documentPreview,
    documentPreviewVisible,
    documentPreviewFileUrl,
    documentPreviewPdfPageUrls,
    selectedSegment,
    completedSegmentCount,
    inProgressSegmentCount,
    pendingSegmentCount,
    selectedSegmentIndex,
    hasNextPendingSegment,
    hitDocuments,
    missingDocuments,
    selectedSegmentVariantNames,
    hitDocOperationHighlights,
    missingDocOperationHighlights,
    factorCandidates,
    currentRuleReview,
    questionTreeVisible,
    showQuestionTreePanel,
    questionTreeEmptyReason,
    questionTreeCurrentQuestion,
    questionTreeSourceHint,
    questionTreeTrail,
    questionTreeResultSummary,
    questionTreeNoteDraft,
    questionTreeSavedSummaryLines,
    questionTreeSavedTrail,
    confirmedFactorCount,
    excludedFactorCount,
    pendingFactorCount,
    loadSavedRoute: reloadSavedRouteWorkspace,
    resetAllAnalysisAnswers,
    goBackToExtract,
    openDocumentPreview,
    closeDocumentPreview,
    openDocumentOriginal,
    formatDate: formatDateTimeLabel,
    formatRatio: formatPercentLabel,
    segmentCoverageLabel,
    segmentDisplayName,
    segmentProgressClass,
    segmentProgressLabel,
    goToPrevSegment,
    goToNextPendingSegment,
    goToNextSegment,
    chooseQuestionTreeOption,
    chooseQuestionTreeOptions,
    reanswerLastQuestionTree,
    resetQuestionTree,
    updateQuestionTreeNote,
    acceptAllRecommendedQuestionTree,
    batchAcceptingAll,
    batchAcceptProgress,
    acceptAllRecommendedForAllSegments: handleAcceptAllRecommendedForAllSegments,
  }
}
