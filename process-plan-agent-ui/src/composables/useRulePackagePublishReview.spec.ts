import { computed, ref, watch } from 'vue'
import { describe, expect, it, vi } from 'vitest'

import type { CompileRulePackageResponse, RulePackageV2 } from '@/api'
import {
  buildPublishReview,
  type RulePackagePublishReview,
} from './useFinalizeRulePackagePublish'
import {
  buildPublishReviewFocusCards,
  locatePublishBlocker,
  useRulePackagePublishReview,
} from './useRulePackagePublishReview'

const rulePackage: RulePackageV2 = {
  manifest: {},
  input_schema: { schema_version: '2.0', fields: [] },
  route_catalog: {
    schema_version: '2.0',
    processes: [{ process_id: 'process_hone', display_name: '珩孔' }],
  },
  route_rules: {
    schema_version: '2.0',
    rules: [{
      rule_id: 'rule_hone',
      source: 'user_confirmed',
      source_segment_id: 'process_hone',
      source_text: '当需要珩孔时，安排珩孔工序',
      when: { field: 'cad.features', op: 'contains', value: '珩孔', factor_id: null },
      then: { include_process_ids: ['process_hone'] },
    }],
  },
  test_cases: [],
}

function compiled(options: {
  validationValid: boolean
  kmaiValid: boolean
  errors?: Array<{ code: string; path?: string; message: string }>
}): CompileRulePackageResponse {
  return {
    package: rulePackage,
    content_hash: 'review',
    validation: { valid: options.validationValid, errors: [], warnings: [], test_results: [] },
    kmai_compatibility: {
      format: 'kmai-v1',
      valid: options.kmaiValid,
      target_directory: 'rules',
      errors: options.errors || [],
      warnings: [],
      files: {},
      factor_catalog_version: '2026.11',
    },
  }
}

const readyReview = { status: 'ready', projectName: '项目 A' } as RulePackagePublishReview
const blockedReview = { status: 'blocked', projectName: '项目 A' } as RulePackagePublishReview

describe('useRulePackagePublishReview', () => {
  it('keeps a confirmed export blocker visible and focused until it scrolls', async () => {
    const cards = ref([
      { segment: { id: 'process_pending' }, pending: true },
      { segment: { id: 'process_hone' }, pending: false },
    ])
    const onlyPending = ref(false)
    const activeSegmentId = ref('process_pending')
    const locatedSegmentId = ref('')
    const reviewState = useRulePackagePublishReview()
    const reviewFocusCards = computed(() => buildPublishReviewFocusCards(
      cards.value,
      card => card.pending,
      locatedSegmentId.value,
    ))
    const visibleCards = computed(() => onlyPending.value ? reviewFocusCards.value : cards.value)
    watch([visibleCards, onlyPending], () => {
      if (!visibleCards.value.some(card => card.segment.id === activeSegmentId.value)) {
        activeSegmentId.value = visibleCards.value[0]?.segment.id || ''
      }
    }, { deep: true })
    const scrollIntoView = vi.fn()
    const pendingReview = reviewState.request(blockedReview)

    await locatePublishBlocker({
      sourceSegmentId: 'process_hone',
      onlyPending,
      activeSegmentId,
      locatedSegmentId,
      completeReview: reviewState.complete,
      getElementById: id => visibleCards.value.some(card => `finalize-card-${card.segment.id}` === id)
        ? { scrollIntoView }
        : null,
    })

    await expect(pendingReview).resolves.toBe(false)
    expect(onlyPending.value).toBe(true)
    expect(visibleCards.value.map(card => card.segment.id)).toEqual(['process_pending', 'process_hone'])
    expect(activeSegmentId.value).toBe('process_hone')
    expect(scrollIntoView).toHaveBeenCalledWith({ block: 'center' })
  })

  it('closes a generic blocked review before skipping card focus', async () => {
    const onlyPending = ref(false)
    const activeSegmentId = ref('process_pending')
    const locatedSegmentId = ref('')
    const reviewState = useRulePackagePublishReview()
    const getElementById = vi.fn()
    const pendingReview = reviewState.request(blockedReview)

    await locatePublishBlocker({
      sourceSegmentId: '',
      onlyPending,
      activeSegmentId,
      locatedSegmentId,
      completeReview: reviewState.complete,
      getElementById,
    })

    const reviewResult = await Promise.race([
      pendingReview,
      Promise.resolve('still-pending' as const),
    ])
    expect(reviewResult).toBe(false)
    expect(reviewState.visible.value).toBe(false)
    expect(onlyPending.value).toBe(false)
    expect(activeSegmentId.value).toBe('process_pending')
    expect(locatedSegmentId.value).toBe('')
    expect(getElementById).not.toHaveBeenCalled()
  })

  it('has only ready and blocked states', () => {
    const ready = buildPublishReview(compiled({ validationValid: true, kmaiValid: true }), '项目 A')
    const blocked = buildPublishReview(compiled({
      validationValid: true,
      kmaiValid: false,
      errors: [{
        code: 'standard_factor_unbound',
        path: 'route_rules.rules[0].when',
        message: '未绑定标准因子',
      }],
    }), '项目 A')

    expect(ready.status).toBe('ready')
    expect(blocked.status).toBe('blocked')
    expect(['ready', 'blocked']).toContain(ready.status)
    expect(['ready', 'blocked']).toContain(blocked.status)
  })

  it('maps a backend rule error back to its fourth-step card', () => {
    const review = buildPublishReview(compiled({
      validationValid: true,
      kmaiValid: false,
      errors: [{
        code: 'standard_factor_unbound',
        path: 'route_rules.rules[0].when',
        message: '未绑定标准因子',
      }],
    }), '项目 A')

    expect(review.details).toEqual([{
      code: 'standard_factor_unbound',
      message: '未绑定标准因子',
      processName: '珩孔',
      sourceText: '当需要珩孔时，安排珩孔工序',
      sourceSegmentId: 'process_hone',
    }])
  })

  it('resolves the active review and clears its state', async () => {
    const state = useRulePackagePublishReview()
    const pending = state.request(readyReview)

    expect(state.review.value).toStrictEqual(readyReview)
    expect(state.visible.value).toBe(true)

    state.complete(true)

    await expect(pending).resolves.toBe(true)
    expect(state.visible.value).toBe(false)
    expect(state.review.value).toBeNull()
  })

  it('cancels an older pending review before opening the next one', async () => {
    const state = useRulePackagePublishReview()
    const first = state.request(readyReview)
    const second = state.request(blockedReview)

    await expect(first).resolves.toBe(false)
    expect(state.review.value).toStrictEqual(blockedReview)

    state.complete(false)
    await expect(second).resolves.toBe(false)
  })
})
