import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { KnowledgeSuggestion } from '@/api/knowledge'
import type { RuleConditionReview } from '@/api/rulePackages'

const conditionApi = vi.hoisted(() => ({ saveRuleConditionDraft: vi.fn(), parseRuleCondition: vi.fn() }))
vi.mock('@/api/rulePackages', () => conditionApi)

import {
  applyKnowledgeSuggestionToCondition,
  canApplyKnowledgeSuggestion,
  knowledgeSuggestionSourceText,
} from './knowledgeSuggestionApplicator'

const suggestion: KnowledgeSuggestion = {
  id: 7,
  project_id: 17,
  route_version_id: 42,
  segment_id: 'heat-treatment',
  title: '热处理硬度要求',
  suggestion_text: '真空淬火后硬度不低于 56 HRC。',
  candidate: null,
  evidence_ids: [3],
  status: 'confirmed',
  created_by: '审核人',
  updated_by: '审核人',
  created_at: '2026-10-15T00:00:00Z',
  updated_at: '2026-10-15T00:00:00Z',
}

describe('knowledge suggestion applicator', () => {
  beforeEach(() => {
    conditionApi.saveRuleConditionDraft.mockReset()
    conditionApi.parseRuleCondition.mockReset()
  })

  it('allows only a confirmed suggestion in the exact current project route segment', () => {
    expect(canApplyKnowledgeSuggestion(suggestion, {
      projectId: 17,
      routeVersionId: 42,
      segmentId: 'heat-treatment',
    })).toBe(true)
  })

  it('rejects unconfirmed suggestions and mismatched route context', () => {
    expect(canApplyKnowledgeSuggestion({ ...suggestion, status: 'pending_review' }, {
      projectId: 17,
      routeVersionId: 42,
      segmentId: 'heat-treatment',
    })).toBe(false)
    expect(canApplyKnowledgeSuggestion(suggestion, {
      projectId: 17,
      routeVersionId: 43,
      segmentId: 'heat-treatment',
    })).toBe(false)
    expect(canApplyKnowledgeSuggestion(suggestion, {
      projectId: 17,
      routeVersionId: 42,
      segmentId: 'other-segment',
    })).toBe(false)
  })

  it('uses the reviewed suggestion text as the condition draft input', () => {
    expect(knowledgeSuggestionSourceText(suggestion)).toBe('真空淬火后硬度不低于 56 HRC。')
    expect(knowledgeSuggestionSourceText({ ...suggestion, suggestion_text: '  ' })).toBe('')
  })

  it('saves a confirmed suggestion as a draft before reparsing with the current workflow revision', async () => {
    const events: string[] = []
    const draftReview = { source_text: suggestion.suggestion_text, status: 'draft', confirmed: null } as RuleConditionReview
    const parsedReview = { ...draftReview, status: 'pending_confirmation' } as RuleConditionReview
    conditionApi.saveRuleConditionDraft.mockImplementation(async () => {
      events.push('saved')
      return { review: draftReview }
    })
    conditionApi.parseRuleCondition.mockImplementation(async () => {
      events.push('parsed')
      return { review: parsedReview }
    })

    const result = await applyKnowledgeSuggestionToCondition(suggestion, {
      projectId: 17,
      routeVersionId: 42,
      segmentId: 'heat-treatment',
      workflowRevision: 5,
      processId: 'heat-treatment',
      processName: '真空淬火',
      processes: [],
    }, (review) => { events.push(review.status) })

    expect(events).toEqual(['saved', 'draft', 'parsed', 'pending_confirmation'])
    expect(result).toEqual(parsedReview)
    expect(conditionApi.saveRuleConditionDraft).toHaveBeenCalledWith({
      project_id: 17,
      route_id: 42,
      expected_workflow_revision: 5,
      segment_id: 'heat-treatment',
      source_text: suggestion.suggestion_text,
      knowledge_suggestion_id: 7,
    })
    expect(conditionApi.parseRuleCondition).toHaveBeenCalledWith(expect.objectContaining({
      project_id: 17,
      route_id: 42,
      expected_workflow_revision: 5,
      segment_id: 'heat-treatment',
      source_text: suggestion.suggestion_text,
    }))
  })

  it('refuses to save or parse an unreviewed or mismatched suggestion', async () => {
    const context = {
      projectId: 17, routeVersionId: 42, segmentId: 'heat-treatment', workflowRevision: 5,
      processId: 'heat-treatment', processName: '真空淬火', processes: [],
    }
    await expect(applyKnowledgeSuggestionToCondition({ ...suggestion, status: 'draft' }, context, () => {}))
      .rejects.toThrow('仅可带入当前项目、路线和工序的已确认建议')
    await expect(applyKnowledgeSuggestionToCondition(suggestion, { ...context, routeVersionId: 43 }, () => {}))
      .rejects.toThrow('仅可带入当前项目、路线和工序的已确认建议')
    expect(conditionApi.saveRuleConditionDraft).not.toHaveBeenCalled()
    expect(conditionApi.parseRuleCondition).not.toHaveBeenCalled()
  })

  it('does not parse or apply the response after the workflow context changes', async () => {
    let current = true
    const appliedReviews: RuleConditionReview[] = []
    conditionApi.saveRuleConditionDraft.mockImplementation(async () => {
      current = false
      return { review: { status: 'draft' } }
    })

    await applyKnowledgeSuggestionToCondition(suggestion, {
      projectId: 17, routeVersionId: 42, segmentId: 'heat-treatment', workflowRevision: 5,
      processId: 'heat-treatment', processName: '真空淬火', processes: [],
    }, review => appliedReviews.push(review), () => current)

    expect(appliedReviews).toEqual([])
    expect(conditionApi.parseRuleCondition).not.toHaveBeenCalled()
  })
})
