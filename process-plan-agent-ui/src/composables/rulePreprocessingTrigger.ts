import {
  startRulePreprocessing,
  type RulePreprocessStatus,
  type RuleConditionProcessOption,
  type RulePreprocessItem,
} from '@/api/rulePackages'
import type { OperationItem, SavedNormalizedRouteSegment, SavedNormalizedRouteVersionResult } from '@/api'
import { buildFinalizeCards } from '@/composables/finalizeViewHelpers'
import {
  exportProcessIdForItem,
  finalizeRuleMode,
  normalizeExportProcessName,
} from '@/utils/finalizeRulePackage'

export type StartRulePreprocessingForSavedRouteOptions = {
  projectId: number | null
  savedRoute: SavedNormalizedRouteVersionResult | null
  supersetOperations: OperationItem[]
  segmentDisplayName: (segment: SavedNormalizedRouteSegment) => string
}

export type RulePreprocessFailureSummary = {
  title: string
  message: string
  lines: string[]
  overflowCount: number
}

export function buildRulePreprocessFailureSummary(
  status: RulePreprocessStatus | null | undefined,
  maxLines = 3,
): RulePreprocessFailureSummary | null {
  if (!status || !status.failed_count) return null
  const lines = String(status.error || '')
    .split(/\r?\n/)
    .map(line => line.trim())
    .filter(Boolean)
  const visibleLines = lines.slice(0, Math.max(0, maxLines))
  return {
    title: `规则候选预处理失败 ${status.failed_count} 条`,
    message: status.message || `已有 ${status.failed_count} 条预处理失败`,
    lines: visibleLines,
    overflowCount: Math.max(0, lines.length - visibleLines.length),
  }
}

export function buildRulePreprocessingPayload(args: StartRulePreprocessingForSavedRouteOptions): {
  items: RulePreprocessItem[]
  processes: RuleConditionProcessOption[]
} {
  if (!args.savedRoute) {
    return { items: [], processes: [] }
  }
  const cards = buildFinalizeCards(args.savedRoute.segments, args.supersetOperations, {})
  const processes = cards
    .map((item): RuleConditionProcessOption => ({
      process_id: exportProcessIdForItem(item),
      display_name: normalizeExportProcessName(args.segmentDisplayName(item.segment)),
      main: finalizeRuleMode(item) === 'mainline',
    }))
    .filter(item => item.process_id && item.display_name)
  const items = cards
    .filter(item => ['conditional', 'relation'].includes(finalizeRuleMode(item)))
    .map((item): RulePreprocessItem => ({
      segment_id: item.segment.id,
      process_id: exportProcessIdForItem(item),
      process_name: normalizeExportProcessName(args.segmentDisplayName(item.segment)),
      source_text: item.conditionText,
    }))
    .filter(item => item.process_id && item.source_text.trim())
  return { items, processes }
}

export function buildRulePreprocessingTriggerKey(args: StartRulePreprocessingForSavedRouteOptions) {
  if (!args.projectId || !args.savedRoute) return ''
  const { items, processes } = buildRulePreprocessingPayload(args)
  if (!items.length) return ''
  return JSON.stringify({
    project_id: args.projectId,
    route_id: args.savedRoute.route_id,
    workflow_revision: args.savedRoute.workflow_revision,
    items,
    processes,
  })
}

export async function startRulePreprocessingForSavedRoute(args: StartRulePreprocessingForSavedRouteOptions) {
  if (!args.projectId || !args.savedRoute) return
  const { items, processes } = buildRulePreprocessingPayload(args)
  if (!items.length) return
  await startRulePreprocessing({
    project_id: args.projectId,
    route_id: args.savedRoute.route_id,
    expected_workflow_revision: args.savedRoute.workflow_revision,
    items,
    processes,
  })
}
