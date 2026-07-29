import { ref } from 'vue'

import type { RulePackageExportReview } from './useFinalizeRulePackageExport'

export function useRulePackageExportReview() {
  const visible = ref(false)
  const review = ref<RulePackageExportReview | null>(null)
  let resolvePending: ((confirmed: boolean) => void) | null = null

  function request(nextReview: RulePackageExportReview): Promise<boolean> {
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
