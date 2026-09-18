import { computed, ref, watch, type ComputedRef } from 'vue'
import type { DocumentOperationDetailItem, SavedNormalizedRouteVersionResult } from '@/api'
import { type TreeOption } from '@/config/analysisQuestionProfiles'
import {
  answersFromTrail,
  createEmptySegmentTreeState,
  loadPersistedTreeState as loadPersistedQuestionTreeState,
  persistTreeState as persistQuestionTreeState,
  savedQuestionTrail,
  type SegmentTreeState,
} from '@/composables/analysisQuestionTreeState'
import {
  buildResultSummary,
} from '@/composables/analysisQuestionTreeNodes'
import {
  buildCurrentQuestion,
  buildImpliedRootAnswer,
  buildQuestionTreeIdleReason,
  classifySegmentMode,
  segmentReviewLocked,
} from '@/composables/analysisQuestionTreeFlow'
import {
  segmentCanDefaultComplete,
  segmentHasRuleDecision,
  segmentNeedsMergeNameQuestion,
} from '@/composables/analysisWorkspaceHelpers'
type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export function useAnalysisQuestionTree(args: {
  projectId?: ComputedRef<number | null>
  selectedSegment: ComputedRef<Segment | null>
  detailRows: ComputedRef<DocumentOperationDetailItem[]>
  selectedSegmentMatchedDocIds: ComputedRef<Set<number>>
  matchedDocumentTexts: ComputedRef<string[]>
  getDocumentTextsForDocIds?: (docIds: Set<number>) => string[]
  documents?: ComputedRef<Array<{ id: number; original_name?: string; filename?: string }>>
}) {
  const treeStateMap = ref<Record<string, SegmentTreeState>>({})
  const hydratedSegmentIds = ref<Set<string>>(new Set())
  const rejudgingSegmentMap = ref<Record<string, boolean>>({})
  const storageKey = computed(() => `processmind_analysis_question_tree_v10_${args.projectId?.value || 'unknown'}`)

  function isSegmentRejudging(segment: Segment | null) {
    return !!(segment?.id && rejudgingSegmentMap.value[segment.id])
  }

  function loadPersistedTreeState() {
    return loadPersistedQuestionTreeState(storageKey.value)
  }

  function persistTreeState(value: Record<string, SegmentTreeState>) {
    persistQuestionTreeState(storageKey.value, value)
  }

  function ensureState(segmentId: string): SegmentTreeState {
    let state = treeStateMap.value[segmentId]
    if (!state) {
      state = createEmptySegmentTreeState()
      treeStateMap.value = {
        ...treeStateMap.value,
        [segmentId]: state,
      }
    }
    return state
  }

  function markSegmentDirty(segmentId: string) {
    const nextHydrated = new Set(hydratedSegmentIds.value)
    nextHydrated.delete(segmentId)
    hydratedSegmentIds.value = nextHydrated
  }

  function setSegmentState(segmentId: string, state: SegmentTreeState) {
    treeStateMap.value = {
      ...treeStateMap.value,
      [segmentId]: { ...state },
    }
  }

  function hasSavedMergeNameTrail(segment: Segment | null) {
    return savedQuestionTrail(segment).some(item => item.nodeId === 'merge_name_root')
  }

  function currentMode(segment: Segment | null, isRejudging = false) {
    if (isRejudging && hasSavedMergeNameTrail(segment)) return 'merge_name'
    return classifySegmentMode(segment)
  }

  function isLegacyMergeReviewWithoutNameTrail(segment: Segment | null) {
    if (!segmentNeedsMergeNameQuestion(segment)) return false
    if (!segment?.rule_review) return false
    const rawDecision = String(segment.rule_review.decision || '')
    if (!['accepted', 'rejected'].includes(rawDecision)) return false
    const trail = savedQuestionTrail(segment)
    return !trail.some(item => item.nodeId === 'merge_name_root')
  }

  function normalizeStateForSegment(segment: Segment | null, state: SegmentTreeState) {
    if (!segment) return state
    if (!isLegacyMergeReviewWithoutNameTrail(segment)) return state
    if (!Object.keys(state.answers).length && !state.note.trim()) return state
    return createEmptySegmentTreeState()
  }

  function shouldDropHydratedState(segment: Segment | null, state: SegmentTreeState) {
    if (!segment?.id) return false
    if (!hydratedSegmentIds.value.has(segment.id)) return false
    if (!segmentNeedsMergeNameQuestion(segment)) return false
    if (segmentHasRuleDecision(segment)) return false
    return Object.keys(state.answers).length > 0 || !!state.note.trim()
  }

  function shouldBypassDefaultComplete(segment: Segment | null) {
    const mode = currentMode(segment, isSegmentRejudging(segment))
    return mode === 'merge_name'
  }

  const currentQuestion = computed(() => buildCurrentQuestion({
    segment: (() => {
      const segment = args.selectedSegment.value
      if (segmentCanDefaultComplete(segment) && !isSegmentRejudging(segment) && !shouldBypassDefaultComplete(segment)) return null
      return segment
    })(),
    isRejudging: isSegmentRejudging(args.selectedSegment.value),
    detailRows: args.detailRows.value,
    matchedDocIds: args.selectedSegmentMatchedDocIds.value,
    matchedDocumentTexts: args.matchedDocumentTexts.value,
    state: args.selectedSegment.value
      ? normalizeStateForSegment(args.selectedSegment.value, ensureState(args.selectedSegment.value.id))
      : createEmptySegmentTreeState(),
  }))

  const trail = computed(() => {
    const segment = args.selectedSegment.value
    if (!segment) return []
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    return Object.values(state.answers)
  })

  const resultSummary = computed(() => {
    const segment = args.selectedSegment.value
    if (!segment || currentQuestion.value) return ''
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    if (!Object.keys(state.answers).length) return ''
    return buildResultSummary(segment.normalized_step_name, state.answers, state.note)
  })

  const noteDraft = computed(() => {
    const segment = args.selectedSegment.value
    if (!segment) return ''
    return normalizeStateForSegment(segment, ensureState(segment.id)).note
  })

  const visible = computed(() => {
    const segment = args.selectedSegment.value
    if (segmentReviewLocked(segment) && !isSegmentRejudging(segment)) return false
    if (segmentCanDefaultComplete(segment) && !isSegmentRejudging(segment) && !shouldBypassDefaultComplete(segment)) return false
    const mode = currentMode(segment, isSegmentRejudging(segment))
    return mode !== 'none'
  })

  const emptyReason = computed(() => (args.selectedSegment.value ? buildQuestionTreeIdleReason() : ''))

  const sourceHint = computed(() => {
    const question = currentQuestion.value
    if (!question) return ''
    if (question.sourceHint) return question.sourceHint
    if (question.id === 'requirement_scope_detail') {
      return '这里会根据上一题的选择，继续确认精度等级、粗糙度等级、几何公差项目或配合类型。'
    }
    if (question.id === 'structure_feature_primary') {
      return '结构候选项优先来自当前工序内容，系统已做去重和基础归并。'
    }
    if (!question.multiple) return ''
    return '当前候选项优先来自工序内容抽取，再结合少量标准化归并给出。'
  })

  function chooseOption(option: TreeOption) {
    const segment = args.selectedSegment.value
    const question = currentQuestion.value
    if (!segment || !question) return
    const state = ensureState(segment.id)
    markSegmentDirty(segment.id)
    const nextAnswers = { ...state.answers }
    if (question.impliedRootValue && !nextAnswers.rule_reason_root) {
      nextAnswers.rule_reason_root = buildImpliedRootAnswer(question.impliedRootValue)
    }
    nextAnswers[question.id] = {
      nodeId: question.id,
      value: option.value,
      label: option.label,
    }
    state.answers = nextAnswers
    setSegmentState(segment.id, state)
  }

  function chooseMultiOptions(options: TreeOption[]) {
    const segment = args.selectedSegment.value
    const question = currentQuestion.value
    if (!segment || !question || !question.multiple) return
    const state = ensureState(segment.id)
    markSegmentDirty(segment.id)
    const filtered = options.filter(option => option && option.value)
    if (!filtered.length) return
    state.answers = {
      ...state.answers,
      [question.id]: {
        nodeId: question.id,
        value: filtered.map(option => option.value).join('|'),
        label: filtered.map(option => option.label).join('、'),
      },
    }
    setSegmentState(segment.id, state)
  }

  function popLastAnswer(segment: Segment, state: SegmentTreeState) {
    let nextAnswers = { ...state.answers }
    if (!Object.keys(nextAnswers).length) {
      nextAnswers = answersFromTrail(savedQuestionTrail(segment))
    }
    const keys = Object.keys(nextAnswers)
    if (!keys.length) return null
    const lastKey = keys[keys.length - 1]
    if (!lastKey) return null
    delete nextAnswers[lastKey]
    return nextAnswers
  }

  function restartLockedSegmentRejudging(segment: Segment) {
    markSegmentDirty(segment.id)
    rejudgingSegmentMap.value = {
      ...rejudgingSegmentMap.value,
      [segment.id]: true,
    }
    setSegmentState(segment.id, createEmptySegmentTreeState())
  }

  function reanswerLastQuestion() {
    const segment = args.selectedSegment.value
    if (!segment) return
    const state = ensureState(segment.id)
    markSegmentDirty(segment.id)
    if (segmentReviewLocked(segment) && !Object.keys(state.answers).length) {
      restartLockedSegmentRejudging(segment)
      return
    }
    const nextAnswers = popLastAnswer(segment, state)
    if (!nextAnswers) return
    if (segmentReviewLocked(segment)) {
      rejudgingSegmentMap.value = {
        ...rejudgingSegmentMap.value,
        [segment.id]: true,
      }
    }
    setSegmentState(segment.id, { ...state, answers: nextAnswers })
  }

  function clearRejudging(segmentId?: string) {
    const id = segmentId || args.selectedSegment.value?.id
    if (!id || !rejudgingSegmentMap.value[id]) return
    const next = { ...rejudgingSegmentMap.value }
    delete next[id]
    rejudgingSegmentMap.value = next
  }

  function reset() {
    const segment = args.selectedSegment.value
    if (!segment) return
    markSegmentDirty(segment.id)
    rejudgingSegmentMap.value = {
      ...rejudgingSegmentMap.value,
      [segment.id]: true,
    }
    setSegmentState(segment.id, createEmptySegmentTreeState())
  }

  function resetAllQuestionTrees() {
    treeStateMap.value = {}
    hydratedSegmentIds.value = new Set()
    rejudgingSegmentMap.value = {}
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(storageKey.value)
    }
  }

  function updateNote(value: string) {
    const segment = args.selectedSegment.value
    if (!segment) return
    const state = ensureState(segment.id)
    markSegmentDirty(segment.id)
    setSegmentState(segment.id, {
      ...state,
      note: value,
    })
  }

  function isFallbackOption(option: TreeOption) {
    const value = String(option.value || '').trim().toLowerCase()
    const label = String(option.label || '').trim()
    return (
      value === 'other'
      || value.includes('other')
      || value.includes('uncertain')
      || value.includes('manual')
      || label.includes('其他')
      || label.includes('暂时无法判断')
      || label.includes('需要人工补充')
      || label.includes('未自动识别')
    )
  }

  function pickRecommendedOptions(question: { id?: string; options: TreeOption[]; multiple?: boolean; minSelections?: number }) {
    const preferred = question.options.filter(option => !isFallbackOption(option))
    const ordered = preferred.length ? preferred : question.options
    if (question.id?.includes('material_scope') && preferred.length > 0) {
      return preferred
    }
    if (!question.multiple) return ordered.slice(0, 1)
    return ordered.slice(0, question.minSelections || 1)
  }

  function acceptAllRecommendedForSegment(targetSegment: Segment) {
    const isRejudging = isSegmentRejudging(targetSegment)
    if (segmentReviewLocked(targetSegment) && !isRejudging) return
    const mode = currentMode(targetSegment, isRejudging)
    if (mode === 'none' && !shouldBypassDefaultComplete(targetSegment)) {
      if (segmentCanDefaultComplete(targetSegment) && !isRejudging) return
    }

    const isCurrentSegment = targetSegment.id === args.selectedSegment.value?.id
    const matchedDocIds = (() => {
      if (isCurrentSegment && args.selectedSegmentMatchedDocIds.value.size) {
        return args.selectedSegmentMatchedDocIds.value
      }
      const ids = new Set<number>()
      ;(targetSegment.matched_detail_rows || []).forEach((row: any) => {
        const docId = Number(row.document_id || 0)
        if (docId > 0) ids.add(docId)
      })
      if (!ids.size && targetSegment.matched_detail_rows?.length && args.documents?.value) {
        const pdfNames = new Set(
          targetSegment.matched_detail_rows
            .map((row: any) => String(row.pdf_name || '').trim())
            .filter(Boolean),
        )
        if (pdfNames.size) {
          args.documents.value.forEach((doc) => {
            if (pdfNames.has(doc.original_name || '') || pdfNames.has(doc.filename || '')) {
              ids.add(doc.id)
            }
          })
        }
      }
      return ids
    })()
    const matchedDocumentTexts = args.getDocumentTextsForDocIds
      ? args.getDocumentTextsForDocIds(matchedDocIds)
      : (isCurrentSegment ? args.matchedDocumentTexts.value : [])

    const maxIterations = 20
    let iterations = 0

    while (iterations < maxIterations) {
      iterations++
      const state = normalizeStateForSegment(targetSegment, ensureState(targetSegment.id))
      const question = buildCurrentQuestion({
        segment: (() => {
          if (segmentCanDefaultComplete(targetSegment) && !isRejudging && !shouldBypassDefaultComplete(targetSegment)) return null
          return targetSegment
        })(),
        isRejudging,
        detailRows: args.detailRows.value,
        matchedDocIds,
        matchedDocumentTexts,
        state,
      })
      if (!question) break
      const recommended = pickRecommendedOptions(question)
      if (!recommended.length) break
      markSegmentDirty(targetSegment.id)
      const nextAnswers = { ...state.answers }
      if (question.impliedRootValue && !nextAnswers.rule_reason_root) {
        nextAnswers.rule_reason_root = buildImpliedRootAnswer(question.impliedRootValue)
      }
      if (question.multiple && recommended.length > 0) {
        nextAnswers[question.id] = {
          nodeId: question.id,
          value: recommended.map(o => o.value).join('|'),
          label: recommended.map(o => o.label).join('、'),
        }
      } else {
        nextAnswers[question.id] = {
          nodeId: question.id,
          value: recommended[0]!.value,
          label: recommended[0]!.label,
        }
      }
      setSegmentState(targetSegment.id, { ...state, answers: nextAnswers })
    }
  }

  function acceptAllRecommended() {
    const segment = args.selectedSegment.value
    if (!segment) return
    acceptAllRecommendedForSegment(segment)
  }

  function acceptAllRecommendedForAllSegments(segments: Segment[]) {
    for (const segment of segments) {
      if (segmentHasRuleDecision(segment) && !isSegmentRejudging(segment)) continue
      acceptAllRecommendedForSegment(segment)
    }
  }

  watch(storageKey, () => {
    const loaded = loadPersistedTreeState()
    treeStateMap.value = loaded
    hydratedSegmentIds.value = new Set(Object.keys(loaded))
  }, { immediate: true })

  watch(() => args.selectedSegment.value, (segment) => {
    if (!segment?.id) return
    const current = treeStateMap.value[segment.id]
    if (!current) return
    if (shouldDropHydratedState(segment, current)) {
      markSegmentDirty(segment.id)
      setSegmentState(segment.id, createEmptySegmentTreeState())
      return
    }
    const normalized = normalizeStateForSegment(segment, current)
    if (normalized === current) return
    setSegmentState(segment.id, normalized)
  }, { immediate: true })

  watch(treeStateMap, (value) => {
    persistTreeState(value)
  }, { deep: true })

  function getTrailForSegment(segment: Segment) {
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    return Object.values(state.answers)
  }

  function getResultSummaryForSegment(segment: Segment) {
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    if (!Object.keys(state.answers).length) return ''
    return buildResultSummary(segment.normalized_step_name, state.answers, state.note)
  }

  function getNoteDraftForSegment(segment: Segment) {
    return normalizeStateForSegment(segment, ensureState(segment.id)).note || ''
  }

  return {
    questionTreeVisible: visible,
    questionTreeEmptyReason: emptyReason,
    questionTreeCurrentQuestion: currentQuestion,
    questionTreeSourceHint: sourceHint,
    questionTreeTrail: trail,
    questionTreeResultSummary: resultSummary,
    questionTreeNoteDraft: noteDraft,
    questionTreeIsRejudging: computed(() => isSegmentRejudging(args.selectedSegment.value)),
    chooseQuestionTreeOption: chooseOption,
    chooseQuestionTreeOptions: chooseMultiOptions,
    reanswerLastQuestionTree: reanswerLastQuestion,
    resetQuestionTree: reset,
    resetAllQuestionTrees,
    updateQuestionTreeNote: updateNote,
    acceptAllRecommendedQuestionTree: acceptAllRecommended,
    acceptAllRecommendedForAllSegments,
    clearQuestionTreeRejudging: clearRejudging,
    isSegmentRejudging,
    getTrailForSegment,
    getResultSummaryForSegment,
    getNoteDraftForSegment,
  }
}
