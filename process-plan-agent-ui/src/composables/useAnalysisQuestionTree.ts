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
    updateQuestionTreeNote: updateNote,
    clearQuestionTreeRejudging: clearRejudging,
  }
}
