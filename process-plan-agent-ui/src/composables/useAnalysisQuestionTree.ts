import { computed, ref, watch, type ComputedRef } from 'vue'
import type { DocumentOperationDetailItem, SavedNormalizedRouteVersionResult } from '@/api'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import { applyGuidedAnswer, buildGuidedDraft, buildGuidedQuestion, recommendedGuidedOptions, resolveGuidanceOperation, guidedOperationKey, confirmedGuidedObject, resolveGuidedObject } from './analysisGuidanceFlow'
import { OBJECT_REUSE_NODE, supplementFrozenObjectRecommendation, type ConfirmedMachiningObject } from './analysisGuidedObjects'
import { mergeRootNode, type TreeNode } from './analysisQuestionTreeNodes'
import { mergeCandidateNamesForSegment } from './analysisQuestionEvidence'
import { type TreeOption } from '@/config/analysisQuestionProfiles'
import {
  answersFromTrail,
  createEmptySegmentTreeState,
  loadPersistedTreeState as loadPersistedQuestionTreeState,
  persistTreeState as persistQuestionTreeState,
  savedQuestionTrail,
  savedGuidanceSnapshot,
  segmentGuidanceKey,
  trailWithGuidanceSnapshot,
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
const frozenIdentityMessage = '无法唯一恢复此工序原来的问答配置。原回答和已有草稿仍保留，暂不能重答或重新生成规则，请核对原工序配置。'

export function useAnalysisQuestionTree(args: {
  guidance?: ComputedRef<AnalysisGuidanceConfiguration | null>
  segments?: ComputedRef<Segment[]>
  readOnly?: ComputedRef<boolean>
  projectId?: ComputedRef<number | null>
  routeId?: ComputedRef<number | null>
  workflowRevision?: ComputedRef<number | null>
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
  const recommendationGapMap = ref<Record<string, string>>({})
  // Segment IDs survive upstream route rebuilds. A project-only cache can
  // otherwise replay answers frozen against another route/workflow version.
  const storageKey = computed(() => args.routeId
    ? `processmind_analysis_question_tree_v11_route_${args.routeId.value ?? 'pending'}_${args.workflowRevision?.value ?? 'unknown'}_${args.projectId?.value || 'unknown'}`
    : `processmind_analysis_question_tree_v10_${args.projectId?.value || 'unknown'}`)

  function isSegmentRejudging(segment: Segment | null) {
    return !!(segment?.id && rejudgingSegmentMap.value[segment.id])
  }

  function loadPersistedTreeState() {
    return loadPersistedQuestionTreeState(storageKey.value)
  }

  function persistTreeState(value: Record<string, SegmentTreeState>) {
    if (args.readOnly?.value) return
    persistQuestionTreeState(storageKey.value, value)
  }

  function ensureState(segmentId: string): SegmentTreeState {
    let state = treeStateMap.value[segmentId]
    const segment = args.segments?.value?.find(s => s.id === segmentId) || (args.selectedSegment.value?.id === segmentId ? args.selectedSegment.value : null)
    const localEmpty = state && !Object.keys(state.answers).length && !state.note.trim()
    const snapshot = !state?.rejudging && (!state?.guidanceSnapshot || localEmpty) ? savedGuidanceSnapshot(segment) : undefined
    if (!state || snapshot) {
      state = snapshot ? {
        ...createEmptySegmentTreeState(), guidanceSnapshot: snapshot,
        answers: answersFromTrail(savedQuestionTrail(segment)),
        note: state?.note || segment?.rule_review?.note || '',
      } : createEmptySegmentTreeState()
      treeStateMap.value = {
        ...treeStateMap.value,
        [segmentId]: state,
      }
    }
    if (segment && state.guidanceSnapshot) freezeGuidance(state, segment)
    return state
  }

  function guidanceForState(state: SegmentTreeState) {
    return state.guidanceSnapshot || args.guidance?.value
  }
  function operationForState(segment: Segment, state: SegmentTreeState, guidance: AnalysisGuidanceConfiguration) {
    return resolveGuidanceOperation(segment, guidance, state.answers, args.segments?.value || [segment], !!state.guidanceSnapshot)
  }
  function freezeGuidance(state: SegmentTreeState, segment: Segment) {
    if (!state.guidanceSnapshot && args.guidance?.value) state.guidanceSnapshot = JSON.parse(JSON.stringify(args.guidance.value))
    const snapshot = state.guidanceSnapshot
    if (!snapshot || snapshot.operation_guidance[segmentGuidanceKey(segment.id)]) return
    const original = operationForState(segment, state, snapshot)
    if (original !== null) snapshot.operation_guidance[segmentGuidanceKey(segment.id)] = JSON.parse(JSON.stringify(original || {}))
  }
  function hasUnresolvedFrozenIdentity(segment: Segment, state: SegmentTreeState) {
    return !!state.guidanceSnapshot && operationForState(segment, state, state.guidanceSnapshot) === null
  }
  let checkingFrozenCompletion = false
  function frozenObjectSupplement(segment: Segment, state: SegmentTreeState, guidance: AnalysisGuidanceConfiguration,
    operation: AnalysisGuidanceConfiguration['operation_guidance'][string]) {
    const source = args.guidance?.value
    const recommendation = operation.recommendation
    if (checkingFrozenCompletion || !state.guidanceSnapshot || !source || !Object.keys(state.answers).length ||
        recommendation?.mode !== 'condition' || !['precision', 'roughness'].includes(recommendation.basis || '') ||
        (recommendation.features?.length && recommendation.direction) ||
        (segmentReviewLocked(segment) && !isSegmentRejudging(segment))) return operation
    const segments = args.segments?.value || [segment]
    const target = state.answers.merge_name_root?.label ? { ...segment, normalized_step_name: state.answers.merge_name_root.label } : segment
    const frozenView = { ...guidance, operation_guidance: { ...guidance.operation_guidance,
      [target.normalized_step_name]: operation, [guidedOperationKey(target, segments)]: operation } }
    // Test completion using the existing frozen answers/reuse, without also
    // adapting every earlier draft during this read (or recursively rechecking it).
    checkingFrozenCompletion = true
    try {
      if (!buildGuidedQuestion(target, frozenView, state.answers, segments, objectsBefore(segment))) return operation
    } finally { checkingFrozenCompletion = false }
    const identity = segment.export_process_id || segment.id
    const identities = guidance.generation_operation_ids
    const keys = identities ? Object.keys(identities).filter(key => identities[key] === identity) : []
    const indexed = guidedOperationKey(segment, segments)
    const key = identities ? (keys.length === 1 ? keys[0] : undefined) : state.answers.merge_name_root ? undefined :
      guidance.operation_guidance[indexed] ? indexed :
        segments.filter(item => item.normalized_step_name === segment.normalized_step_name).length === 1 ? segment.normalized_step_name : undefined
    return key ? supplementFrozenObjectRecommendation(guidance, source, key, identity, operation, state.answers) : operation
  }
  function applyRecommendedAnswer(segment: Segment, state: SegmentTreeState, answer: Parameters<typeof applyGuidedAnswer>[1]) {
    const snapshot = state.guidanceSnapshot
    const original = snapshot && operationForState(segment, state, snapshot)
    // Adding a newly required object answer to a compatible old draft must not
    // clear the user's already answered direction or IT/Ra from the old order.
    if (original && !state.answers[answer.nodeId] && ['guided_features', 'guided_direction'].includes(answer.nodeId) &&
        frozenObjectSupplement(segment, state, snapshot!, original) !== original) {
      return { ...state.answers, [answer.nodeId]: answer }
    }
    return applyGuidedAnswer(state.answers, answer)
  }
  function namedGuidance(segment: Segment, state: SegmentTreeState) {
    const guidance = guidanceForState(state)
    const selectedName = state.answers.merge_name_root?.label
    if (!guidance) return guidance
    const original = operationForState(segment, state, guidance)
    if (original === null) return null
    if (!original) return guidance
    const operation = frozenObjectSupplement(segment, state, guidance, original)
    const target = selectedName ? { ...segment, normalized_step_name: selectedName } : segment
    return { ...guidance, operation_guidance: { ...guidance.operation_guidance,
      [target.normalized_step_name]: operation,
      [guidedOperationKey(target, args.segments?.value || [segment])]: operation,
    } }
  }

  function objectsBefore(segment: Segment) {
    const segments = args.segments?.value || [segment]
    const index = segments.findIndex(item => item.id === segment.id)
    const prior = index >= 0 ? segments.slice(0, index) : segments.filter(item => item.sequence < segment.sequence)
    const objects: ConfirmedMachiningObject[] = []
    for (const source of prior) {
      if (source.rule_review?.decision === 'rejected' && !isSegmentRejudging(source)) continue
      const state = normalizeStateForSegment(source, ensureState(source.id))
      const guidance = namedGuidance(source, state)
      if (!guidance || hasUnresolvedFrozenIdentity(source, state)) continue
      const name = state.answers.merge_name_root?.label
      const object = confirmedGuidedObject(name ? { ...source, normalized_step_name: name } : source, guidance, state.answers, segments, objects)
      if (object) objects.push(object)
    }
    return objects
  }

  function markSegmentDirty(segmentId: string) {
    const nextHydrated = new Set(hydratedSegmentIds.value)
    nextHydrated.delete(segmentId)
    hydratedSegmentIds.value = nextHydrated
  }

  function setSegmentState(segmentId: string, state: SegmentTreeState) {
    delete recommendationGapMap.value[segmentId]
    treeStateMap.value = {
      ...treeStateMap.value,
      [segmentId]: { ...state, rejudging: !!rejudgingSegmentMap.value[segmentId] },
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
    if (state.guidanceSnapshot) return false
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

  function questionForSegment(segment: Segment | null, state: SegmentTreeState, isRejudging: boolean, matchedDocIds: Set<number>, matchedDocumentTexts: string[]): TreeNode | null {
    const guidance = segment ? namedGuidance(segment, state) : guidanceForState(state)
    if (segment && guidance === null && hasUnresolvedFrozenIdentity(segment, state)) {
      return { id: 'guidance_identity_unresolved', title: '原问答配置待核对', prompt: frozenIdentityMessage, options: [] }
    }
    if (guidance === null || (args.guidance && !guidance)) return null
    if (guidance && segment) {
      if (segmentReviewLocked(segment) && !isRejudging) return null
      if (segmentNeedsMergeNameQuestion(segment) && !state.answers.merge_name_root) return mergeRootNode(segment.normalized_step_name, () => mergeCandidateNamesForSegment(segment))
      const selectedName = state.answers.merge_name_root?.label
      if (selectedName && !isRejudging && segment.doc_coverage.total_docs > 0 && segment.doc_coverage.hit_docs >= segment.doc_coverage.total_docs) return null
      return buildGuidedQuestion(selectedName ? { ...segment, normalized_step_name: selectedName } : segment, guidance, state.answers, args.segments?.value || [segment], objectsBefore(segment))
    }
    return buildCurrentQuestion({ segment, state, isRejudging, detailRows: args.detailRows.value, matchedDocIds, matchedDocumentTexts })
  }

  const currentQuestion = computed(() => questionForSegment(
    (() => {
      const segment = args.selectedSegment.value
      if (segmentCanDefaultComplete(segment) && !isSegmentRejudging(segment) && !shouldBypassDefaultComplete(segment)) return null
      return segment
    })(),
    args.selectedSegment.value
      ? normalizeStateForSegment(args.selectedSegment.value, ensureState(args.selectedSegment.value.id))
      : createEmptySegmentTreeState(),
    isSegmentRejudging(args.selectedSegment.value), args.selectedSegmentMatchedDocIds.value, args.matchedDocumentTexts.value,
  ))

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
    return getAnalysisDraftForSegment(segment)?.condition_text || (args.guidance?.value ? '' : buildResultSummary(segment.normalized_step_name, state.answers, state.note))
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

  const emptyReason = computed(() => {
    const segment = args.selectedSegment.value
    if (!segment) return ''
    if (hasUnresolvedFrozenIdentity(segment, ensureState(segment.id))) {
      return frozenIdentityMessage
    }
    return buildQuestionTreeIdleReason()
  })

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
    if (args.readOnly?.value) return
    const segment = args.selectedSegment.value
    const question = currentQuestion.value
    if (!segment || !question) return
    const state = ensureState(segment.id)
    if (hasUnresolvedFrozenIdentity(segment, state)) return
    freezeGuidance(state, segment)
    markSegmentDirty(segment.id)
    const nextAnswers = applyGuidedAnswer(state.answers, { nodeId: question.id, value: option.value, label: option.label })
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
    if (args.readOnly?.value) return
    const segment = args.selectedSegment.value
    const question = currentQuestion.value
    if (!segment || !question || !question.multiple) return
    const state = ensureState(segment.id)
    freezeGuidance(state, segment)
    markSegmentDirty(segment.id)
    const filtered = options.filter(option => option && option.value)
    if (!filtered.length) return
    state.answers = applyGuidedAnswer(state.answers, {
        nodeId: question.id,
        value: filtered.map(option => option.value).join('|'),
        label: filtered.map(option => option.label).join('、'),
    })
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
    if (args.readOnly?.value) return
    const segment = args.selectedSegment.value
    if (!segment) return
    const state = ensureState(segment.id)
    if (hasUnresolvedFrozenIdentity(segment, state)) return
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
    const state = treeStateMap.value[id]
    if (state) setSegmentState(id, state)
  }

  function reset() {
    if (args.readOnly?.value) return
    const segment = args.selectedSegment.value
    if (!segment) return
    if (hasUnresolvedFrozenIdentity(segment, ensureState(segment.id))) return
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
    recommendationGapMap.value = {}
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(storageKey.value)
    }
  }

  function updateNote(value: string) {
    if (args.readOnly?.value) return
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
    if (question.id?.startsWith('guided_')) return recommendedGuidedOptions(question as any)
    const preferred = question.options.filter(option => !isFallbackOption(option))
    const ordered = preferred.length ? preferred : question.options
    if (question.id?.includes('material_scope') && preferred.length > 0) {
      return preferred
    }
    if (!question.multiple) return ordered.slice(0, 1)
    return ordered.slice(0, question.minSelections || 1)
  }

  function acceptAllRecommendedForSegment(targetSegment: Segment) {
    if (args.readOnly?.value) return
    const isRejudging = isSegmentRejudging(targetSegment)
    if (segmentReviewLocked(targetSegment) && !isRejudging) return
    if (args.guidance) {
      const original = ensureState(targetSegment.id)
      if (!guidanceForState(original) || hasUnresolvedFrozenIdentity(targetSegment, original)) return
      const trial: SegmentTreeState = JSON.parse(JSON.stringify(original))
      freezeGuidance(trial, targetSegment)
      for (let step = 0; step < 20; step++) {
        if (segmentCanDefaultComplete(targetSegment) && !isRejudging && !shouldBypassDefaultComplete(targetSegment)) return
        const q = questionForSegment(targetSegment, trial, isRejudging, new Set(), [])
        if (!q) {
          markSegmentDirty(targetSegment.id)
          setSegmentState(targetSegment.id, trial)
          return
        }
        const recommended = pickRecommendedOptions(q)
        if (!recommended.length || ((q as any).recommendedValues?.length && recommended.length !== (q as any).recommendedValues.length)) {
          recommendationGapMap.value[targetSegment.id] = q.id
          return
        }
        trial.answers = applyRecommendedAnswer(targetSegment, trial, {
          nodeId: q.id, value: q.multiple ? recommended.map(o => o.value).join('|') : recommended[0]!.value,
          label: q.multiple ? recommended.map(o => o.label).join('、') : recommended[0]!.label,
        })
      }
      return
    }
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
      const question = questionForSegment(
        (() => {
          if (segmentCanDefaultComplete(targetSegment) && !isRejudging && !shouldBypassDefaultComplete(targetSegment)) return null
          return targetSegment
        })(), state, isRejudging, matchedDocIds, matchedDocumentTexts,
      )
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
    recommendationGapMap.value = {}
    const loaded = loadPersistedTreeState()
    treeStateMap.value = loaded
    hydratedSegmentIds.value = new Set(Object.keys(loaded))
    rejudgingSegmentMap.value = Object.fromEntries(
      Object.entries(loaded).filter(([, state]) => state.rejudging).map(([id]) => [id, true]),
    )
  }, { immediate: true, flush: 'sync' })

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
    const guidance = namedGuidance(segment, state)
    const selectedName = state.answers.merge_name_root?.label
    const reuse = guidance ? resolveGuidedObject(selectedName ? { ...segment, normalized_step_name: selectedName } : segment, guidance, state.answers, args.segments?.value || [segment], objectsBefore(segment)).reuse : undefined
    const trail = Object.values(state.answers)
    if (reuse) trail.push({ nodeId: OBJECT_REUSE_NODE, value: JSON.stringify(reuse), label: '沿用已确认加工对象' })
    return trailWithGuidanceSnapshot(trail, state.guidanceSnapshot)
  }

  function getResultSummaryForSegment(segment: Segment) {
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    if (!Object.keys(state.answers).length) return ''
    return getAnalysisDraftForSegment(segment)?.condition_text || (args.guidance?.value ? '' : buildResultSummary(segment.normalized_step_name, state.answers, state.note))
  }

  function getAnalysisDraftForSegment(segment: Segment) {
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    const guidance = namedGuidance(segment, state)
    if (guidance === null) return null
    if (!guidance) return args.guidance && !segmentCanDefaultComplete(segment) ? null : undefined
    if (!Object.keys(state.answers).length && segmentCanDefaultComplete(segment) && !isSegmentRejudging(segment)) return undefined
    const selectedName = state.answers.merge_name_root?.label
    const fullMergedRoute = selectedName && !state.answers.guided_mode && !isSegmentRejudging(segment) && segment.doc_coverage.total_docs > 0 && segment.doc_coverage.hit_docs >= segment.doc_coverage.total_docs
    const answers = fullMergedRoute ? { ...state.answers, guided_mode: { nodeId: 'guided_mode', value: 'mainline', label: '全覆盖主工序' } } : state.answers
    return buildGuidedDraft(selectedName ? { ...segment, normalized_step_name: selectedName } : segment, guidance, answers, args.segments?.value || [segment], objectsBefore(segment))
  }

  function getMissingAnswerForSegment(segment: Segment) {
    const state = normalizeStateForSegment(segment, ensureState(segment.id))
    const guidance = namedGuidance(segment, state)
    if (!guidance) return hasUnresolvedFrozenIdentity(segment, state) ? frozenIdentityMessage : '问答配置尚未就绪'
    const selectedName = state.answers.merge_name_root?.label
    const question = buildGuidedQuestion(selectedName ? { ...segment, normalized_step_name: selectedName } : segment, guidance, state.answers, args.segments?.value || [segment], objectsBefore(segment))
    const labels: Record<string, string> = { guided_features: '加工特征', guided_direction: '加工方位', guided_basis: '判断依据', guided_it: 'IT阈值', guided_ra: 'Ra阈值', guided_mode: '安排方式' }
    const gap = recommendationGapMap.value[segment.id]
    return gap && labels[gap] ? labels[gap]! : question ? labels[question.id] || question.prompt : '规则草稿待核对'
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
    getAnalysisDraftForSegment,
    getMissingAnswerForSegment,
    getGuidanceForSegment: (segment: Segment) => namedGuidance(segment, ensureState(segment.id)),
  }
}
