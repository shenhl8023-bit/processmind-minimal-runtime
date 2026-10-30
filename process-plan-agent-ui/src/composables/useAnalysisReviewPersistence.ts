import { ref, type ComputedRef, type Ref } from 'vue'
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
  clearQuestionTreeRejudging: (segmentId: string) => void
  goToNextPendingSegment: () => void
  onWorkflowConflict?: () => void | Promise<void>
  onRuleReviewSaved?: () => void | Promise<void>
}

export function useAnalysisReviewPersistence(options: UseAnalysisReviewPersistenceOptions) {
  const savingRuleReview = ref(false)
  const autoPersistingRuleSegmentId = ref('')

  function applyRuleReviewUpdate(result: SegmentRuleReviewSaveResult, originalNote: string) {
    options.savedRoute.value = applyRuleReviewUpdateToRoute(options.savedRoute.value, result)
    if (options.selectedSegmentId.value === result.segment_id && options.ruleReviewNote.value === originalNote) {
      options.ruleReviewNote.value = result.rule_review?.note || ''
    }
    if (result.rule_review) {
      options.clearQuestionTreeRejudging(result.segment_id)
    }
  }

  async function persistRuleReview(
    decision: 'accepted' | 'rejected' | 'pending',
    persistOptions?: { autoAdvance?: boolean },
  ) {
    if (savingRuleReview.value || !options.projectId.value || !options.savedRoute.value || !options.selectedSegment.value) return
    savingRuleReview.value = true
    const projectId = options.projectId.value
    const routeSnapshot = options.savedRoute.value
    const routeId = options.savedRoute.value.route_id
    const workflowRevision = options.savedRoute.value.workflow_revision
    const originalNote = options.ruleReviewNote.value
    const isCurrent = () => options.projectId.value === projectId
      && options.savedRoute.value === routeSnapshot
      && options.savedRoute.value?.route_id === routeId
      && options.savedRoute.value?.workflow_revision === workflowRevision
    const segmentId = options.selectedSegment.value.id
    try {
      const result = await saveSegmentRuleReview({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
        segment_id: segmentId,
        decision,
        note: options.ruleReviewNote.value.trim(),
        summary_lines: options.ruleCandidateSummary.value,
        question_trail: options.questionTreeTrail.value,
      })
      if (!isCurrent()) return
      applyRuleReviewUpdate(result, originalNote)
      Promise.resolve(options.onRuleReviewSaved?.()).catch((err) => {
        console.warn('保存规则判断后启动规则预处理失败', err)
      })
      if (persistOptions?.autoAdvance && options.selectedSegmentId.value === segmentId) {
        options.goToNextPendingSegment()
      }
    } catch (e) {
      if (!isCurrent()) return
      console.error('保存规则候选判断失败', e)
      if (isWorkflowRevisionConflict(e)) {
        options.error.value = '当前页面已过期，正在加载最新工作流状态。'
        await options.onWorkflowConflict?.()
      } else {
        options.error.value = '保存规则候选判断失败，请稍后重试。'
      }
    } finally {
      savingRuleReview.value = false
    }
  }

  return {
    savingRuleReview,
    autoPersistingRuleSegmentId,
    persistRuleReview,
  }
}
