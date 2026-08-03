import { describe, expect, it } from 'vitest'
import {
  downloadActionLabel,
  publishActionLabel,
  reviewActionLabel,
  rulePackageActionDisabled,
} from './finalizeRulePackageActionState'

const idle = {
  resetting: false,
  parsing: false,
  reviewing: false,
  publishing: false,
  downloading: false,
  hasSegments: true,
  factorCatalogReady: true,
  hasReviewWork: true,
  allRulesConfirmed: false,
  currentVersion: null,
}

describe('finalizeRulePackageActionState', () => {
  it('uses the confirmed action labels', () => {
    expect(reviewActionLabel(idle, 0, 0)).toBe('规则审核')
    expect(publishActionLabel(idle)).toBe('发布规则包')
    expect(downloadActionLabel(idle)).toBe('下载当前版本')
  })

  it('marks a matching published package as downloadable', () => {
    const state = { ...idle, hasReviewWork: false, allRulesConfirmed: true, currentVersion: 3 }
    expect(reviewActionLabel(state, 0, 0)).toBe('规则已审核')
    expect(publishActionLabel(state)).toBe('已发布 V3')
    expect(rulePackageActionDisabled(state)).toEqual({ review: true, publish: true, download: false })
  })

  it('keeps stale confirmed content publishable but not downloadable', () => {
    const state = { ...idle, hasReviewWork: false, allRulesConfirmed: true, currentVersion: null }
    expect(rulePackageActionDisabled(state)).toEqual({ review: true, publish: false, download: true })
  })
})
