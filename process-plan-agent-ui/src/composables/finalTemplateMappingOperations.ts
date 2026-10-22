import type { OperationItem, SavedNormalizedRouteSegment } from '@/api/extract'
import type { TemplateOperation } from './templateGroupMapping'
import { segmentDisplayName } from './analysisWorkspaceHelpers'
import { buildFinalRouteSteps, finalProcessId, finalProcessMetadata } from './finalRouteSteps'

function numericIdentity(value: string) {
  let hash = 2166136261
  for (const char of value) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619) >>> 0
  return hash || 1
}
export function buildFinalTemplateMappingOperations(
  segments: SavedNormalizedRouteSegment[], sources: OperationItem[],
): TemplateOperation[] {
  const used = new Set<number>()
  return [...segments].sort((a, b) => a.sequence - b.sequence).map(segment => {
    const processId = finalProcessId(segment)
    let id = numericIdentity(processId)
    while (used.has(id)) id += 1
    used.add(id)
    const steps = buildFinalRouteSteps(segment, sources)
    return {
      id, process_id: processId, name: segmentDisplayName(segment),
      sequence: segment.sequence, step_family: segment.step_family,
      source_operation_ids: [...(segment.source_operation_ids || [])], steps,
      step_items: steps.map(step => step.step_name), ...finalProcessMetadata(segment, steps),
      rule_evidence: [...(segment.evidence_excerpt || [])], rule_reasons: [],
    }
  })
}
