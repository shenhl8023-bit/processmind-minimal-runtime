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
  const sourceIds = new Set(sources.map(source => Number(source.source_operation_id || source.id)))
  const requestedSourceIds = segments.flatMap(segment => segment.source_operation_ids || []).map(Number)
  if (requestedSourceIds.some(id => !sourceIds.has(id))) {
    throw new Error('当前保存路线与最新工序数据不一致，请返回路线归并，核对并保存最新路线后再进行模板映射。')
  }
  const used = new Set<number>()
  const operations = [...segments].sort((a, b) => a.sequence - b.sequence).map(segment => {
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
  if (requestedSourceIds.length && !operations.some(operation => operation.steps?.length)) {
    throw new Error('当前路线缺少工步明细，无法进行模板映射。请先检查上传资料和工序明细，再重新加载。')
  }
  return operations
}
