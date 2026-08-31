import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  saveSegmentRuleReview: vi.fn(),
}))

vi.mock('@/api', () => ({
  saveSegmentRuleReview: mocks.saveSegmentRuleReview,
}))

import { useAnalysisReviewPersistence } from './useAnalysisReviewPersistence'

function createPersistence(onRuleReviewSaved = vi.fn()) {
  const selectedSegment = ref({ id: 'seg-1', rule_review: null })
  const savedRoute = ref({
    route_id: 9,
    workflow_revision: 3,
    segments: [selectedSegment.value],
  } as any)
  const persistence = useAnalysisReviewPersistence({
    projectId: ref(12),
    savedRoute,
    selectedSegment: computed(() => selectedSegment.value as any),
    selectedSegmentId: ref('seg-1'),
    ruleReviewNote: ref('note'),
    error: ref(''),
    ruleCandidateSummary: computed(() => ['summary']),
    questionTreeTrail: computed(() => []),
    clearQuestionTreeRejudging: vi.fn(),
    goToNextPendingSegment: vi.fn(),
    onRuleReviewSaved,
  })
  return { persistence, onRuleReviewSaved }
}

describe('useAnalysisReviewPersistence', () => {
  beforeEach(() => {
    mocks.saveSegmentRuleReview.mockReset()
    mocks.saveSegmentRuleReview.mockResolvedValue({
      project_id: 12,
      route_id: 9,
      segment_id: 'seg-1',
      analysis_status: 'accepted',
      rule_review: {
        id: 1,
        decision: 'accepted',
        note: 'note',
        summary_lines: ['summary'],
        question_trail: [],
        created_at: '',
        updated_at: '',
      },
    })
  })

  it('notifies after a rule review is saved so preprocessing can start in the background', async () => {
    const { persistence, onRuleReviewSaved } = createPersistence()

    await persistence.persistRuleReview('accepted')

    expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
    expect(onRuleReviewSaved).toHaveBeenCalledTimes(1)
  })

  it('does not fail the save flow when the background preprocessing trigger fails', async () => {
    const consoleWarn = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { persistence, onRuleReviewSaved } = createPersistence(
      vi.fn().mockRejectedValue(new Error('preprocess unavailable')),
    )

    await persistence.persistRuleReview('accepted')

    expect(onRuleReviewSaved).toHaveBeenCalledTimes(1)
    await Promise.resolve()
    expect(persistence.savingRuleReview.value).toBe(false)
    expect(consoleWarn).toHaveBeenCalledWith('保存规则判断后启动规则预处理失败', expect.any(Error))
    consoleWarn.mockRestore()
  })
})
