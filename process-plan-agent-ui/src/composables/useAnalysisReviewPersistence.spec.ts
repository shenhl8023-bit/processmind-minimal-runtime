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
  const options = {
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
  }
  const persistence = useAnalysisReviewPersistence(options)
  return { persistence, onRuleReviewSaved, options, selectedSegment, savedRoute }
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

  it('preserves the newly selected segment note when an earlier save resolves', async () => {
    let finish!: (value: any) => void
    const response = await mocks.saveSegmentRuleReview()
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { persistence, options, selectedSegment, savedRoute } = createPersistence()
    const pending = persistence.persistRuleReview('accepted')
    selectedSegment.value = { id: 'seg-2', rule_review: null }
    options.selectedSegmentId.value = 'seg-2'
    options.ruleReviewNote.value = 'new segment draft'
    finish(response)
    await pending

    expect(options.ruleReviewNote.value).toBe('new segment draft')
    expect(savedRoute.value.segments[0].rule_review?.decision).toBe('accepted')
  })

  it('discards save responses for a replaced route even when segment ids are reused', async () => {
    let finish!: (value: any) => void
    const response = await mocks.saveSegmentRuleReview()
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { persistence, options, savedRoute, onRuleReviewSaved } = createPersistence()
    const pending = persistence.persistRuleReview('accepted')
    options.projectId.value = 99
    savedRoute.value = { route_id: 90, workflow_revision: 7, segments: [{ id: 'seg-1', rule_review: null }] }
    options.ruleReviewNote.value = 'new task draft'
    finish(response)
    await pending

    expect(savedRoute.value.segments[0].rule_review).toBeNull()
    expect(options.ruleReviewNote.value).toBe('new task draft')
    expect(onRuleReviewSaved).not.toHaveBeenCalled()
  })

  it('discards an old save after returning to the same task and route revision', async () => {
    let finish!: (value: any) => void
    const response = await mocks.saveSegmentRuleReview()
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { persistence, options, savedRoute, onRuleReviewSaved } = createPersistence()
    const pending = persistence.persistRuleReview('accepted', { autoAdvance: true })
    options.projectId.value = 99
    savedRoute.value = { route_id: 90, workflow_revision: 7, segments: [{ id: 'seg-1', rule_review: null }] }
    options.projectId.value = 12
    savedRoute.value = { route_id: 9, workflow_revision: 3, segments: [{ id: 'seg-1', rule_review: null }] }
    options.ruleReviewNote.value = 'returned task draft'
    finish(response)
    await pending

    expect(savedRoute.value.segments[0].rule_review).toBeNull()
    expect(options.ruleReviewNote.value).toBe('returned task draft')
    expect(options.clearQuestionTreeRejudging).not.toHaveBeenCalled()
    expect(options.goToNextPendingSegment).not.toHaveBeenCalled()
    expect(onRuleReviewSaved).not.toHaveBeenCalled()
  })
})
