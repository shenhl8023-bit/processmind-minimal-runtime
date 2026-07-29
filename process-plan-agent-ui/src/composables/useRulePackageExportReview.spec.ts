import { describe, expect, it } from 'vitest'

import type { RulePackageExportReview } from './useFinalizeRulePackageExport'
import { useRulePackageExportReview } from './useRulePackageExportReview'

const readyReview = { status: 'ready', projectName: '项目 A' } as RulePackageExportReview
const blockedReview = { status: 'blocked', projectName: '项目 A' } as RulePackageExportReview

describe('useRulePackageExportReview', () => {
  it('resolves the active review and clears its state', async () => {
    const state = useRulePackageExportReview()
    const pending = state.request(readyReview)

    expect(state.review.value).toStrictEqual(readyReview)
    expect(state.visible.value).toBe(true)

    state.complete(true)

    await expect(pending).resolves.toBe(true)
    expect(state.visible.value).toBe(false)
    expect(state.review.value).toBeNull()
  })

  it('cancels an older pending review before opening the next one', async () => {
    const state = useRulePackageExportReview()
    const first = state.request(readyReview)
    const second = state.request(blockedReview)

    await expect(first).resolves.toBe(false)
    expect(state.review.value).toStrictEqual(blockedReview)

    state.complete(false)
    await expect(second).resolves.toBe(false)
  })
})
