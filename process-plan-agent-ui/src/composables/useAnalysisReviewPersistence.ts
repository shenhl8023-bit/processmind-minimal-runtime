import { ref, type ComputedRef, type Ref } from 'vue'
import {
  saveSegmentRuleReview,
  type SavedNormalizedRouteVersionResult,
  type SegmentRuleReviewSaveResult,
} from '@/api'
import { applyRuleReviewUpdateToRoute } from '@/composables/analysisWorkspaceHelpers'

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
}

export function useAnalysisReviewPersistence(options: UseAnalysisReviewPersistenceOptions) {
  const savingRuleReview = ref(false)
  const autoPersistingRuleSegmentId = ref('')

  function applyRuleReviewUpdate(result: SegmentRuleReviewSaveResult) {
    options.savedRoute.value = applyRuleReviewUpdateToRoute(options.savedRoute.value, result)
    options.ruleReviewNote.value = result.rule_review?.note || ''
    if (result.rule_review) {
      options.clearQuestionTreeRejudging(result.segment_id)
    }
  }

  async function persistRuleReview(
    decision: 'accepted' | 'rejected' | 'pending',
    persistOptions?: { autoAdvance?: boolean },
  ) {
    if (!options.projectId.value || !options.savedRoute.value || !options.selectedSegment.value) return
    savingRuleReview.value = true
    const segmentId = options.selectedSegment.value.id
    try {
      const result = await saveSegmentRuleReview({
        project_id: options.projectId.value,
        route_id: options.savedRoute.value.route_id,
        segment_id: segmentId,
        decision,
        note: options.ruleReviewNote.value.trim(),
        summary_lines: options.ruleCandidateSummary.value,
        question_trail: options.questionTreeTrail.value,
      })
      applyRuleReviewUpdate(result)
      if (persistOptions?.autoAdvance && options.selectedSegmentId.value === segmentId) {
        options.goToNextPendingSegment()
      }
    } catch (e) {
      console.error('保存规则候选判断失败', e)
      options.error.value = '保存规则候选判断失败，请稍后重试。'
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
