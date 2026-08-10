import { describe, expect, expectTypeOf, it } from 'vitest'

import { saveNormalizedSupersetRoute, saveSegmentRuleReview } from './extract'

import {
  CONDITION_REVIEW_STATUS_VALUES,
  EXTRACTION_TASK_STATUS_VALUES,
  PROJECT_STATUS_VALUES,
  RULE_PACKAGE_STATUS_VALUES,
  isConditionReviewStatus,
  isExtractionTaskStatus,
  isProjectStatus,
  isRulePackageStatus,
} from './dto'
import type { RouteMergeReviewStatus, RouteReviewDecision } from './dto'

type SaveNormalizedRouteItem = Parameters<
  typeof saveNormalizedSupersetRoute
>[0]['normalized_superset_route'][number]
type SaveSegmentRuleReviewBody = Parameters<typeof saveSegmentRuleReview>[0]

describe('shared API status DTOs', () => {
  it('keeps workflow status values aligned with the backend contract', () => {
    expect(PROJECT_STATUS_VALUES).toEqual([
      'CREATED',
      'UPLOADED',
      'EXTRACTING',
      'ROUTE_SET_READY',
      'GENERATED',
      'EXTRACT_ERROR',
      'FAILED',
    ])
    expect(EXTRACTION_TASK_STATUS_VALUES).toEqual(['idle', 'running', 'completed', 'failed'])
    expect(CONDITION_REVIEW_STATUS_VALUES).toEqual([
      'draft',
      'parsing',
      'pending_confirmation',
      'confirmed',
      'invalid',
    ])
    expect(RULE_PACKAGE_STATUS_VALUES).toEqual(['draft', 'published', 'superseded', 'archived'])
  })

  it('rejects unknown API status values instead of widening them to string', () => {
    expect(isProjectStatus('ROUTE_SET_READY')).toBe(true)
    expect(isProjectStatus('READY')).toBe(false)
    expect(isExtractionTaskStatus('completed')).toBe(true)
    expect(isExtractionTaskStatus('done')).toBe(false)
    expect(isConditionReviewStatus('confirmed')).toBe(true)
    expect(isConditionReviewStatus('approved')).toBe(false)
    expect(isRulePackageStatus('published')).toBe(true)
    expect(isRulePackageStatus('active')).toBe(false)
  })

  it('reuses shared status contracts in workflow write requests', () => {
    expectTypeOf<SaveNormalizedRouteItem['review_status']>().toEqualTypeOf<
      RouteMergeReviewStatus | undefined
    >()
    expectTypeOf<SaveSegmentRuleReviewBody['decision']>().toEqualTypeOf<RouteReviewDecision>()
  })
})
