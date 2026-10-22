import { describe, expect, it } from 'vitest'
import { resolveRouteWorkspaceDisplayState } from './extractViewHelpers'

describe('extract view display state', () => {
  it('keeps the route workspace mounted while the template mapping dialog is open', () => {
    expect(resolveRouteWorkspaceDisplayState({
      routeWorkspaceLoading: true,
      templateGroupMappingVisible: true,
    })).toBe('workspace')
  })

  it('shows route loading progress when no template mapping dialog is open', () => {
    expect(resolveRouteWorkspaceDisplayState({
      routeWorkspaceLoading: true,
      templateGroupMappingVisible: false,
    })).toBe('loading')
  })
})

import { buildRouteMergeGroupsFromSuggestions } from './extractViewHelpers'

it('preserves model provenance and evidence when building merge cards', () => {
  const [group] = buildRouteMergeGroupsFromSuggestions([{
    target_group_id: 'g1', normalized_step_name: '下料/备料', source_operation_ids: [1, 2],
    advice_source: 'model', advice_action: 'keep_separate', advice_confidence: 0.72,
    advice_evidence_ids: ['op:1', 'op:2'], recommendation_reason: '阶段不同',
  } as any])
  expect(group).toMatchObject({
    advice_source: 'model', advice_action: 'keep_separate', advice_confidence: 0.72,
    advice_evidence_ids: ['op:1', 'op:2'], recommendation_reason: '阶段不同',
  })
})
