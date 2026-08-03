import { nextTick, ref, type Ref } from 'vue'

import type { RulePackagePublishReview } from './useFinalizeRulePackagePublish'

export function buildPublishReviewFocusCards<T>(
  cards: T[],
  isPending: (card: T) => boolean,
  locatedSegmentId: string,
): T[] {
  return cards.filter((card: any) => (
    isPending(card) || card?.segment?.id === locatedSegmentId
  ))
}

export async function locatePublishBlocker(options: {
  sourceSegmentId: string
  onlyPending: Ref<boolean>
  activeSegmentId: Ref<string>
  locatedSegmentId: Ref<string>
  completeReview: (confirmed: boolean) => void
  getElementById: (id: string) => Pick<Element, 'scrollIntoView'> | null
}) {
  options.completeReview(false)
  if (!options.sourceSegmentId) return
  options.locatedSegmentId.value = options.sourceSegmentId
  options.onlyPending.value = true
  options.activeSegmentId.value = options.sourceSegmentId
  await nextTick()
  options.getElementById(`finalize-card-${options.sourceSegmentId}`)?.scrollIntoView({ block: 'center' })
}

export function useRulePackagePublishReview() {
  const visible = ref(false)
  const review = ref<RulePackagePublishReview | null>(null)
  let resolvePending: ((confirmed: boolean) => void) | null = null

  function request(nextReview: RulePackagePublishReview): Promise<boolean> {
    resolvePending?.(false)
    review.value = nextReview
    visible.value = true
    return new Promise((resolve) => {
      resolvePending = resolve
    })
  }

  function complete(confirmed: boolean) {
    const resolve = resolvePending
    resolvePending = null
    visible.value = false
    review.value = null
    resolve?.(confirmed)
  }

  return {
    visible,
    review,
    request,
    complete,
  }
}
