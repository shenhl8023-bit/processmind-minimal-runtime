import { computed, ref, type Ref } from 'vue'
import type { OperationItem } from '@/api'
import { buildRouteFullSetDisplayOperations } from '@/composables/extractViewHelpers'

import { buildFinalRouteSteps } from './finalRouteSteps'

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

  function segmentStepNodes(segment: any) { return buildFinalRouteSteps(segment, supersetOperations.value) }

  function segmentPrimarySteps(segment: any) {
    return segmentStepNodes(segment).filter(step => step.kind === 'primary').map(step => step.step_name)
  }

  function segmentAttachedSteps(segment: any) {
    return segmentStepNodes(segment).filter(step => step.kind === 'attached').map(step => step.step_name)
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
    segmentStepNodes,
    toggleSegmentSteps,
  }
}
