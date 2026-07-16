import { computed, onActivated, onDeactivated, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import type { FactorCandidate } from '@/components/analysis/types'
import type { SegmentFactorReview } from '@/api'
import {
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
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'

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
    loadSavedRoute,
    resolveProjectId,
  } = useAnalysisWorkspaceData({
    getRouteProjectId: () => route.query.project_id as string | undefined,
  })
  const ruleReviewNote = ref('')
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
  } = useAnalysisDocumentTextCache({
    selectedDocIds: selectedSegmentMatchedDocIds,
  })

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
    reanswerLastQuestionTree,
    resetQuestionTree,
    updateQuestionTreeNote,
    clearQuestionTreeRejudging,
  } = useAnalysisQuestionTree({
    projectId: computed(() => projectId.value),
    selectedSegment,
    detailRows: computed(() => detailRows.value),
    selectedSegmentMatchedDocIds,
    matchedDocumentTexts: selectedSegmentMatchedDocTexts,
  })
  const questionTreeInProgress = computed(() =>
    questionTreeVisible.value && !!questionTreeCurrentQuestion.value,
  )
  const regeneratedQuestionTreeSavedConclusion = computed(() => {
    if (questionTreeIsRejudging.value || hideLegacySavedQuestionTreeReview.value) return ''
    const segment = selectedSegment.value
    if (!segment) return ''
    const trail = savedQuestionTrail(segment)
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
      : (currentRuleReview.value?.question_trail || []),
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

  async function reloadSavedRouteWorkspace(forceRefresh = false) {
    clearDocumentPreviewTexts()
    await loadSavedRoute(forceRefresh)
    loadedDataRevision = getWorkflowDataRevision()
  }

  const {
    savingRuleReview,
    autoPersistingRuleSegmentId,
    persistRuleReview,
  } = useAnalysisReviewPersistence({
    projectId,
    savedRoute,
    selectedSegment,
    selectedSegmentId,
    ruleReviewNote,
    error,
    ruleCandidateSummary,
    questionTreeTrail,
    clearQuestionTreeRejudging,
    goToNextPendingSegment,
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

  watch(selectedSegment, async () => {
    resetAnalysisPanelState()
    void ensureMatchedDocumentPreviewTexts()
  })

  const autoRuleDecision = computed<'accepted' | 'rejected' | null>(() => {
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

  watch(
    [selectedSegmentId, autoRuleDecision, currentRuleReview],
    async ([segmentId, nextDecision, review]) => {
      if (!segmentId || !nextDecision) return
      if (savingRuleReview.value) return
      if (review?.decision === nextDecision) return
      if (autoPersistingRuleSegmentId.value === segmentId) return
      autoPersistingRuleSegmentId.value = segmentId
      try {
        await persistRuleReview(nextDecision, { autoAdvance: false })
      } finally {
        if (autoPersistingRuleSegmentId.value === segmentId) {
          autoPersistingRuleSegmentId.value = ''
        }
      }
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
    void reloadSavedRouteWorkspace().then(resetAnalysisPanelState)
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
    loading,
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
  }
}
