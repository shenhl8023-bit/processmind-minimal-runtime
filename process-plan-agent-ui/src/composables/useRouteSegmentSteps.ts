import { computed, ref, type Ref } from 'vue'
import type { OperationItem } from '@/api'
import { buildRouteFullSetDisplayOperations, normalizeOperationName } from '@/composables/extractViewHelpers'

function collectUniqueSteps(operations: any[], key: 'step_items' | 'attached_step_items') {
  const unique = new Set<string>()
  const items: string[] = []
  operations.forEach((operation) => {
    ;(Array.isArray(operation[key]) ? operation[key] : []).forEach((step: unknown) => {
      const text = normalizeOperationName(String(step || '').trim())
      if (!text || unique.has(text)) return
      unique.add(text)
      items.push(text)
    })
  })
  return items
}

export function useRouteSegmentSteps(supersetOperations: Ref<OperationItem[]>) {
  const expandedSegmentStepIds = ref<Set<string>>(new Set())
  const displayOperations = computed(() => buildRouteFullSetDisplayOperations(supersetOperations.value))

  function segmentDisplayOperations(segment: any) {
    const sourceIds = new Set((segment?.source_operation_ids || []).map((id: unknown) => Number(id || 0)).filter((id: number) => id > 0))
    return displayOperations.value.filter((operation: any) => {
      const sourceOperationId = Number(operation?.source_operation_id || operation?.id || 0)
      return sourceOperationId > 0 && sourceIds.has(sourceOperationId)
    })
  }

  function segmentPrimarySteps(segment: any) {
    return collectUniqueSteps(segmentDisplayOperations(segment), 'step_items')
  }

  function segmentAttachedSteps(segment: any) {
    return collectUniqueSteps(segmentDisplayOperations(segment), 'attached_step_items')
  }

  function segmentStepCount(segment: any) {
    return segmentPrimarySteps(segment).length + segmentAttachedSteps(segment).length
  }

  function isSegmentStepsExpanded(segmentId: string) {
    return expandedSegmentStepIds.value.has(segmentId)
  }

  function toggleSegmentSteps(segmentId: string) {
    const next = new Set(expandedSegmentStepIds.value)
    if (next.has(segmentId)) next.delete(segmentId)
    else next.add(segmentId)
    expandedSegmentStepIds.value = next
  }

  return {
    isSegmentStepsExpanded,
    segmentAttachedSteps,
    segmentDisplayOperations,
    segmentPrimarySteps,
    segmentStepCount,
    toggleSegmentSteps,
  }
}
