import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  confirmRuleCondition: vi.fn(),
  parseRuleCondition: vi.fn(),
  saveRuleConditionDraft: vi.fn(),
  setManualRuleCondition: vi.fn(),
}))

vi.mock('@/api/rulePackages', () => ({
  confirmRuleCondition: mocks.confirmRuleCondition,
  parseRuleCondition: mocks.parseRuleCondition,
  saveRuleConditionDraft: mocks.saveRuleConditionDraft,
  setManualRuleCondition: mocks.setManualRuleCondition,
}))

import { useConditionReviewQueue } from './useConditionReviewQueue'

function review(sourceText: string, status: 'pending_confirmation' | 'confirmed' = 'pending_confirmation') {
  return {
    source_text: sourceText,
    source_hash: `hash:${sourceText}`,
    status,
    candidate: {
      kind: 'condition',
      when: { field: 'material.grade', op: 'eq', value: '45' },
      then: { include_process_ids: ['process_turn'], exclude_process_ids: [] },
      preview: sourceText,
    },
    confirmed: status === 'confirmed' ? { preview: sourceText } : null,
    issues: [],
    field_registry_version: '2026.08',
    confirmed_by: '',
    confirmed_at: '',
  } as any
}

function routeResult() {
  return {
    route_id: 120,
    project_id: 12,
    workflow_revision: 7,
    segments: [{ id: 'segment_turn', rule_review: null }],
  } as any
}

function card(savedRoute: ReturnType<typeof ref<any>>, sourceText = '材料为45钢时车削') {
  return {
    segment: savedRoute.value.segments[0],
    conditionText: sourceText,
    defaultConditionText: sourceText,
    conditionReview: savedRoute.value.segments[0].rule_review?.condition_review || null,
  } as any
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason?: unknown) => void
  const promise = new Promise<T>((done, fail) => {
    resolve = done
    reject = fail
  })
  return { promise, reject, resolve }
}

function createQueue() {
  const projectId = ref<number | null>(12)
  const savedRoute = ref<any>(routeResult())
  const cards = computed(() => [card(savedRoute)])
  const onlyPending = ref(false)
  const activeSegmentId = ref('')
  const factorCatalogError = ref('')
  const onNotice = vi.fn()
  const onPublishedRuleOutdated = vi.fn()
  const onWorkflowConflict = vi.fn().mockResolvedValue(false)
  const queue = useConditionReviewQueue({
    projectId,
    savedRoute,
    segmentCards: cards,
    batchEligibleCards: cards,
    autoConfirmableReviewCards: computed(() => []),
    pendingRuleCards: cards,
    conditionProcessOptions: computed(() => [{ process_id: 'process_turn', display_name: '车削' }]),
    factorCatalogReady: computed(() => true),
    standardFactors: ref([{ factor_id: 'material.grade' }] as any),
    factorCatalogError,
    onlyPending,
    activeSegmentId,
    displayName: () => '车削',
    onPublishedRuleOutdated,
    onConditionTextDraft: vi.fn(),
    onNotice,
    onWorkflowConflict,
  })
  return {
    activeSegmentId,
    cards,
    factorCatalogError,
    onNotice,
    onPublishedRuleOutdated,
    onWorkflowConflict,
    onlyPending,
    projectId,
    queue,
    savedRoute,
  }
}

describe('useConditionReviewQueue', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset())
  })

  it('does not apply a parse response after pending requests are cancelled', async () => {
    const pending = deferred<any>()
    mocks.parseRuleCondition.mockReturnValueOnce(pending.promise)
    const { cards, queue, savedRoute } = createQueue()

    const parsing = queue.parseConditionItem(cards.value[0]!)
    expect(queue.conditionBusySegmentIds.value.has('segment_turn')).toBe(true)
    queue.setBatchNotice('旧提示')
    queue.cancelPendingRequests()
    pending.resolve({ review: review('材料为45钢时车削') })

    await expect(parsing).resolves.toBe(false)
    expect(savedRoute.value.segments[0].rule_review).toBeNull()
    expect(queue.conditionBusySegmentIds.value.size).toBe(0)
    expect(queue.batchNotice.value).toBe('')
  })

  it('applies only current batch parse results and reports completed progress', async () => {
    mocks.parseRuleCondition.mockResolvedValue({ review: review('材料为45钢时车削') })
    const { cards, onlyPending, queue, savedRoute } = createQueue()

    await queue.handleBatchParseConditions([...cards.value])

    expect(savedRoute.value.segments[0].rule_review.condition_review.status).toBe('pending_confirmation')
    expect(queue.batchParseCompleted.value).toBe(1)
    expect(queue.batchParseTotal.value).toBe(1)
    expect(queue.batchNotice.value).toBe('已识别 1 条规则。')
    expect(onlyPending.value).toBe(true)
  })

  it('routes workflow revision conflicts through the shared conflict handler', async () => {
    const conflict = {
      response: {
        status: 409,
        data: { detail: { message: '当前页面已过期，请刷新后再操作。' } },
      },
    }
    mocks.parseRuleCondition.mockRejectedValueOnce(conflict)
    const state = createQueue()
    state.onWorkflowConflict.mockResolvedValueOnce(true)

    await expect(state.queue.parseConditionItem(state.cards.value[0]!, true)).resolves.toBe(false)

    expect(state.onWorkflowConflict).toHaveBeenCalledWith(conflict)
    expect(state.onNotice).not.toHaveBeenCalled()
  })

  it('applies a current manual confirmation and invalidates the published package', async () => {
    const state = createQueue()
    const pendingReview = review('材料为45钢时车削')
    pendingReview.candidate = {
      kind: 'process_relation',
      relation: {
        relation_type: 'requires',
        source_process_ids: ['process_turn'],
        target_process_ids: ['process_grind'],
      },
      preview: '车削依赖磨削',
    }
    state.savedRoute.value.segments[0].rule_review = {
      condition_review: pendingReview,
    }
    mocks.confirmRuleCondition.mockResolvedValueOnce({
      review: review('材料为45钢时车削', 'confirmed'),
    })

    const currentCard = state.cards.value[0]!
    await state.queue.handleConfirmCondition(currentCard, pendingReview.candidate)

    expect(state.savedRoute.value.segments[0].rule_review.condition_review.status).toBe('confirmed')
    expect(state.onPublishedRuleOutdated).toHaveBeenCalledOnce()
  })

  it('ignores a stale conflict after the request has been cancelled', async () => {
    const pending = deferred<any>()
    mocks.parseRuleCondition.mockReturnValueOnce(pending.promise)
    const state = createQueue()

    const parsing = state.queue.parseConditionItem(state.cards.value[0]!, true)
    state.queue.cancelPendingRequests()
    pending.reject({
      response: {
        status: 409,
        data: { detail: { message: '当前页面已过期，请刷新后再操作。' } },
      },
    })
    await parsing

    expect(state.onWorkflowConflict).not.toHaveBeenCalled()
    expect(state.onNotice).not.toHaveBeenCalled()
  })
})
