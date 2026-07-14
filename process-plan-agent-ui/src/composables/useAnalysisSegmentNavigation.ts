import { computed, type Ref } from 'vue'
import { isSegmentCompleted, isSegmentStarted } from '@/composables/analysisWorkspaceHelpers'
import type { SavedNormalizedRouteVersionResult } from '@/api'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export function useAnalysisSegmentNavigation(args: {
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  selectedSegment: Ref<Segment | null>
  selectedSegmentId: Ref<string>
}) {
  const completedSegmentCount = computed(() =>
    args.savedRoute.value?.segments.filter(segment => isSegmentCompleted(segment)).length || 0,
  )

  const inProgressSegmentCount = computed(() =>
    args.savedRoute.value?.segments.filter(segment => !isSegmentCompleted(segment) && isSegmentStarted(segment)).length || 0,
  )

  const pendingSegmentCount = computed(() =>
    args.savedRoute.value?.segments.filter(segment => !isSegmentCompleted(segment) && !isSegmentStarted(segment)).length || 0,
  )

  const selectedSegmentIndex = computed(() =>
    args.savedRoute.value?.segments.findIndex(segment => segment.id === args.selectedSegment.value?.id) ?? -1,
  )

  const nextPendingSegmentIndex = computed(() =>
    args.savedRoute.value?.segments.findIndex((segment, index) => index > selectedSegmentIndex.value && !isSegmentCompleted(segment)) ?? -1,
  )

  const hasNextPendingSegment = computed(() => nextPendingSegmentIndex.value >= 0)

  function goToSegmentByIndex(index: number) {
    const target = args.savedRoute.value?.segments[index]
    if (!target) return
    args.selectedSegmentId.value = target.id
  }

  function goToPrevSegment() {
    if (selectedSegmentIndex.value <= 0) return
    goToSegmentByIndex(selectedSegmentIndex.value - 1)
  }

  function goToNextSegment() {
    if (!args.savedRoute.value || selectedSegmentIndex.value >= args.savedRoute.value.segments.length - 1) return
    goToSegmentByIndex(selectedSegmentIndex.value + 1)
  }

  function goToNextPendingSegment() {
    if (nextPendingSegmentIndex.value < 0) return
    goToSegmentByIndex(nextPendingSegmentIndex.value)
  }

  return {
    completedSegmentCount,
    inProgressSegmentCount,
    pendingSegmentCount,
    selectedSegmentIndex,
    hasNextPendingSegment,
    goToPrevSegment,
    goToNextSegment,
    goToNextPendingSegment,
  }
}
