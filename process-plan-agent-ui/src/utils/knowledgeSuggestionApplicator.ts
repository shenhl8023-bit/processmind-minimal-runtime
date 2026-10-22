import type { KnowledgeSuggestion } from '@/api/knowledge'
import {
  parseRuleCondition,
  saveRuleConditionDraft,
  type RuleConditionProcessOption,
  type RuleConditionReview,
} from '@/api/rulePackages'

export type KnowledgeSuggestionContext = {
  projectId: number
  routeVersionId: number
  segmentId: string
}

export function knowledgeSuggestionSourceText(suggestion: KnowledgeSuggestion): string {
  return suggestion.suggestion_text.trim()
}

export function canApplyKnowledgeSuggestion(
  suggestion: KnowledgeSuggestion,
  context: KnowledgeSuggestionContext,
): boolean {
  return suggestion.status === 'confirmed'
    && suggestion.project_id === context.projectId
    && suggestion.route_version_id === context.routeVersionId
    && suggestion.segment_id === context.segmentId
    && knowledgeSuggestionSourceText(suggestion).length > 0
}

export async function applyKnowledgeSuggestionToCondition(
  suggestion: KnowledgeSuggestion,
  context: KnowledgeSuggestionContext & {
    workflowRevision: number
    processId: string
    processName: string
    processes: RuleConditionProcessOption[]
  },
  onReview: (review: RuleConditionReview) => void,
  isCurrent = () => true,
): Promise<RuleConditionReview | null> {
  if (!canApplyKnowledgeSuggestion(suggestion, context)) {
    throw new Error('仅可带入当前项目、路线和工序的已确认建议')
  }
  if (!isCurrent()) return null
  const request = {
    project_id: context.projectId,
    route_id: context.routeVersionId,
    expected_workflow_revision: context.workflowRevision,
    segment_id: context.segmentId,
    source_text: knowledgeSuggestionSourceText(suggestion),
  }
  const draft = await saveRuleConditionDraft({
    ...request,
    knowledge_suggestion_id: suggestion.id,
  })
  if (!isCurrent()) return null
  // Saving first clears any earlier confirmation before a new candidate is parsed.
  onReview(draft.review)
  const parsed = await parseRuleCondition({
    ...request,
    process_id: context.processId,
    process_name: context.processName,
    processes: context.processes,
  })
  if (!isCurrent()) return null
  onReview(parsed.review)
  return parsed.review
}
