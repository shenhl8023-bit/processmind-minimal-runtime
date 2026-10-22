import type { OperationItem } from '@/api/extract'
import { buildRouteFullSetDisplayOperations, normalizeOperationName } from './extractViewHelpers'

export type FinalStepSource = { source_operation_id: number; source_operation_name?: string; source_step_order: number; source_step_name: string }
export type FinalRouteStep = FinalStepSource & {
  step_id: string; step_name: string; kind: 'primary' | 'attached'; source_steps: FinalStepSource[]
}
export function finalProcessId(segment: any) {
  return String(segment?.export_process_id || segment?.id || '').trim()
}
export function finalStepId(processId: string, kind: 'primary' | 'attached', index: number, source?: FinalStepSource) {
  return source?.source_operation_id && source.source_step_order
    ? `${processId}.${kind}.op_${source.source_operation_id}_s${source.source_step_order}`
    : `${processId}.${kind}.s${index + 1}`
}
// The third-step tree, mapping tree and publication catalog use the same final steps.
// Equal steps from different source documents merge, while repeated occurrences remain distinct.
export function buildFinalRouteSteps(segment: any, sources: OperationItem[]): FinalRouteStep[] {
  const ids = new Set<number>((segment?.source_operation_ids || []).map(Number))
  const originals = new Map(sources.map(source => [Number(source.source_operation_id || source.id), source]))
  const display = buildRouteFullSetDisplayOperations(sources).filter(source => ids.has(Number(source.source_operation_id || source.id)))
  return (['primary', 'attached'] as const).flatMap(kind => {
    const nodes: FinalRouteStep[] = []
    const byOccurrence = new Map<string, FinalRouteStep>()
    const occurrences = new Map<number, Map<string, number>>()
    for (const operation of display) {
      const sourceId = Number(operation.source_operation_id || operation.id)
      const original = originals.get(sourceId)
      const counts = occurrences.get(sourceId) || new Map<string, number>()
      occurrences.set(sourceId, counts)
      const key = kind === 'primary' ? 'step_items' : 'attached_step_items'
      for (const raw of operation[key] || []) {
        const name = normalizeOperationName(String(raw || '').trim())
        if (!name) continue
        const occurrence = (counts.get(name) || 0) + 1
        counts.set(name, occurrence)
        const sourceItems = original?.[key] || []
        const sourceIndex = sourceItems.map(value => normalizeOperationName(String(value || '').trim()))
          .flatMap((value, index) => value === name ? [index] : [])[occurrence - 1]
        const order = sourceIndex === undefined ? 0 : sourceIndex + 1 + (kind === 'attached' ? (original?.step_items || []).length : 0)
        const source: FinalStepSource = {
          source_operation_id: sourceId,
          source_operation_name: String(original?.source_operation_name || original?.name || operation.source_operation_name || operation.name || '').trim(),
          source_step_order: order,
          source_step_name: sourceIndex === undefined ? name : String(sourceItems[sourceIndex]).trim(),
        }
        const mergeKey = JSON.stringify([name, occurrence])
        const existing = byOccurrence.get(mergeKey)
        if (existing) { if (order) existing.source_steps.push(source); continue }
        const node: FinalRouteStep = {
          ...source, step_id: finalStepId(finalProcessId(segment), kind, nodes.length, source),
          step_name: name, kind, source_steps: order ? [source] : [],
        }
        nodes.push(node); byOccurrence.set(mergeKey, node)
      }
    }
    return nodes
  })
}
export function finalProcessMetadata(segment: any, steps: FinalRouteStep[]) {
  const phase = String(segment?.phase || '')
  const family = String(segment?.step_family || '')
  const auxiliary = ['auxiliary', 'inspection', 'heat_treatment', 'surface_treatment', 'surface_or_heat_treatment'].includes(phase)
    || ['heat', 'surface', 'inspection', 'release'].includes(family)
  const machining = !auxiliary && (['shape', 'hole', 'feature', 'finish', '孔加工类', '特征加工类', '车削类', '车削/成形类'].includes(family)
    || /车|铣|钻|镗|铰|攻丝|磨|研|珩|切槽|挖槽|倒角|倒圆|成形|割型|打型|打孔|割扁|刻线|电火花|线切割|平端面/.test(String(segment?.normalized_step_name || '') + steps.map(step => step.step_name).join(' ')))
  return {
    process_type: machining ? '加工工序' : '辅助工序',
    precision: !machining ? '辅助工序' : ({ rough: '粗加工', semi_finish: '半精加工', finish: '精加工', roughing: '粗加工', finishing: '精加工' } as Record<string, string>)[phase] || '',
  }
}
