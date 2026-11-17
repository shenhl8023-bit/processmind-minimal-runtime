import { getCurrentScope, onScopeDispose, ref, watch, type ComputedRef, type Ref } from 'vue'
import {
  saveSegmentRuleReview,
  type SavedNormalizedRouteVersionResult,
  type SegmentRuleReviewSaveResult,
} from '@/api'
import { applyRuleReviewUpdateToRoute } from '@/composables/analysisWorkspaceHelpers'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

type UseAnalysisReviewPersistenceOptions = {
  projectId: Ref<number | null>
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  selectedSegment: ComputedRef<Segment | null>
  selectedSegmentId: Ref<string>
  ruleReviewNote: Ref<string>
  error: Ref<string>
  ruleCandidateSummary: ComputedRef<string[]>
  questionTreeTrail: ComputedRef<any[]>
  getAnalysisDraft?: (segment: Segment) => import('@/api/extract').SegmentRuleReview['analysis_draft'] | undefined
  getQuestionTrail?: (segment: Segment) => any[]
  isSaveAllowed?: () => boolean
  clearQuestionTreeRejudging: (segmentId: string) => void
  goToNextPendingSegment: () => void
  onWorkflowConflict?: () => void | Promise<void>
  onRuleReviewSaved?: () => void | Promise<void>
}

export function useAnalysisReviewPersistence(options: UseAnalysisReviewPersistenceOptions) {
  const savingRuleReview = ref(false)
  type SaveJob = {
    payload: Parameters<typeof saveSegmentRuleReview>[0]
    routeSnapshot: SavedNormalizedRouteVersionResult
    context: number
    originalNote: string
    autoAdvance: boolean
    signature: string
    promise: Promise<void>
    finish: () => void
  }
  const pendingSaves: SaveJob[] = []
  let activeSave: SaveJob | undefined
  let context = 0
  let applyingReview = false
  let disposed = false
  const canSave = () => !disposed && !options.savedRoute.value?.analysis_locked
    && (options.isSaveAllowed?.() ?? true)

  function cancelPendingRuleReviews(segmentId?: string) {
    for (let i = pendingSaves.length - 1; i >= 0; i--) {
      if (!segmentId || pendingSaves[i]!.payload.segment_id === segmentId) {
        pendingSaves.splice(i, 1)[0]!.finish()
      }
    }
  }

  watch([options.projectId, options.savedRoute, canSave], () => {
    if (applyingReview) return
    context++
    cancelPendingRuleReviews()
  }, { flush: 'sync' })
  if (getCurrentScope()) onScopeDispose(() => {
    disposed = true
    context++
    cancelPendingRuleReviews()
  })

  const isCurrent = (job: SaveJob) => canSave() && context === job.context
    && options.projectId.value === job.payload.project_id
    && options.savedRoute.value === job.routeSnapshot
    && options.savedRoute.value?.route_id === job.payload.route_id
    && options.savedRoute.value?.workflow_revision === job.payload.expected_workflow_revision

  function applyRuleReviewUpdate(result: SegmentRuleReviewSaveResult, originalNote: string, answersUnchanged: boolean) {
    options.savedRoute.value = applyRuleReviewUpdateToRoute(options.savedRoute.value, result)
    if (options.selectedSegmentId.value === result.segment_id && options.ruleReviewNote.value === originalNote) {
      options.ruleReviewNote.value = result.rule_review?.note || ''
    }
    if (result.rule_review && answersUnchanged) {
      options.clearQuestionTreeRejudging(result.segment_id)
    }
  }

  async function persistRuleReview(
    decision: 'accepted' | 'rejected' | 'pending',
    persistOptions?: { autoAdvance?: boolean },
  ) {
    if (!canSave() || !options.projectId.value || !options.savedRoute.value || !options.selectedSegment.value) return
    const analysisDraft = options.getAnalysisDraft?.(options.selectedSegment.value)
    if (decision === 'accepted' && analysisDraft === null) {
      options.error.value = '请先完成当前工序的必答问题并确认规则。'
      return
    }
    const payload: SaveJob['payload'] = JSON.parse(JSON.stringify({
      project_id: options.projectId.value,
      route_id: options.savedRoute.value.route_id,
      expected_workflow_revision: options.savedRoute.value.workflow_revision,
      segment_id: options.selectedSegment.value.id,
      decision,
      note: options.ruleReviewNote.value.trim(),
      summary_lines: options.ruleCandidateSummary.value,
      question_trail: options.getQuestionTrail?.(options.selectedSegment.value) || options.questionTreeTrail.value,
      ...(analysisDraft ? { analysis_draft: analysisDraft } : {}),
    }))
    const signature = JSON.stringify(payload)
    const duplicate = [activeSave, ...pendingSaves].find(job => job?.context === context && job.signature === signature)
    if (duplicate) return duplicate.promise
    let finish!: () => void
    const promise = new Promise<void>(resolve => { finish = resolve })
    pendingSaves.push({ payload, signature, promise, finish, context,
      routeSnapshot: options.savedRoute.value, originalNote: options.ruleReviewNote.value,
      autoAdvance: Boolean(persistOptions?.autoAdvance) })
    void drainPendingSaves()
    return promise
  }

  async function saveSnapshot(job: SaveJob) {
    const { payload, originalNote } = job
    const segmentId = payload.segment_id
    try {
      const result = await saveSegmentRuleReview(payload)
      if (!isCurrent(job)) return
      const segment = options.savedRoute.value!.segments.find(item => item.id === segmentId)
      const answersUnchanged = Boolean(segment)
        && JSON.stringify(options.getAnalysisDraft?.(segment!)) === JSON.stringify(payload.analysis_draft)
        && (!options.getQuestionTrail || JSON.stringify(options.getQuestionTrail(segment!)) === JSON.stringify(payload.question_trail))
      applyingReview = true
      try {
        applyRuleReviewUpdate(result, originalNote, answersUnchanged)
      } finally {
        applyingReview = false
      }
      // Applying our own response replaces the route object. Forward only jobs
      // captured from that exact object; external reloads invalidate the queue.
      for (const queued of pendingSaves) {
        if (queued.context === job.context && queued.routeSnapshot === job.routeSnapshot) {
          queued.routeSnapshot = options.savedRoute.value!
        }
      }
      Promise.resolve(options.onRuleReviewSaved?.()).catch((err) => {
        console.warn('保存规则判断后启动规则预处理失败', err)
      })
      if (job.autoAdvance && answersUnchanged && options.selectedSegmentId.value === segmentId) {
        options.goToNextPendingSegment()
      }
    } catch (e) {
      if (!isCurrent(job)) return
      console.error('保存规则候选判断失败', e)
      if ((e as any)?.response?.data?.detail?.code === 'analysis_locked') {
        await options.onWorkflowConflict?.()
      } else if (isWorkflowRevisionConflict(e)) {
        options.error.value = '当前页面已过期，正在加载最新工作流状态。'
        await options.onWorkflowConflict?.()
      } else {
        options.error.value = '保存规则候选判断失败，请稍后重试。'
      }
    }
  }

  async function drainPendingSaves() {
    if (savingRuleReview.value) return
    savingRuleReview.value = true
    try {
      while (pendingSaves.length) {
        activeSave = pendingSaves.shift()!
        try {
          if (isCurrent(activeSave)) await saveSnapshot(activeSave)
        } finally {
          activeSave.finish()
          activeSave = undefined
        }
      }
    } finally {
      savingRuleReview.value = false
    }
  }

  async function waitForPendingRuleReviews() {
    const expectedContext = context
    while (activeSave) await activeSave.promise
    return context === expectedContext && canSave()
  }

  return {
    savingRuleReview,
    cancelPendingRuleReviews,
    waitForPendingRuleReviews,
    persistRuleReview,
  }
}
