import { computed, ref } from 'vue'

export interface ProductStatus {
  edition: 'full' | 'basic-trial'
  template_mapping_enabled: boolean
  expires_at: string | null
  expired: boolean
  server_time: string
}

// Only an explicitly delivered trial needs remote expiry checks. Full builds
// must stay usable when the optional product-status endpoint is unavailable.
export const trialChecksEnabled = typeof document !== 'undefined'
  && document.querySelector?.('meta[name="processmind-edition"]')?.getAttribute('content') === 'basic-trial'
export const productStatus = ref<ProductStatus | null>(trialChecksEnabled ? null : {
  edition: 'full', template_mapping_enabled: true,
  expires_at: null, expired: false, server_time: new Date().toISOString(),
})
export const productAccess = ref<'loading' | 'ready' | 'error' | 'expired'>(trialChecksEnabled ? 'loading' : 'ready')
// Keep data, import and publication behavior tied to the license, not UI visibility.
export const templateMappingEnabled = computed(() => productStatus.value?.edition === 'full')
export const templateMappingVisible = computed(() => templateMappingEnabled.value
  && (productStatus.value?.template_mapping_enabled ?? true))
export const knowledgeLibraryEnabled = computed(() => productStatus.value?.edition === 'full')

let requestId = 0
let expiryTimer: ReturnType<typeof setTimeout> | undefined
const isExpired = () => productAccess.value === 'expired'

export function markTrialExpired() {
  if (!trialChecksEnabled) return
  productAccess.value = 'expired'
  if (expiryTimer !== undefined) clearTimeout(expiryTimer)
  expiryTimer = undefined
}

function isProductStatus(value: unknown): value is ProductStatus {
  if (!value || typeof value !== 'object') return false
  const status = value as ProductStatus
  return ['full', 'basic-trial'].includes(status.edition)
    && typeof status.template_mapping_enabled === 'boolean'
    && typeof status.expired === 'boolean'
    && typeof status.server_time === 'string' && Number.isFinite(Date.parse(status.server_time))
    && (status.expires_at === null || (typeof status.expires_at === 'string' && Number.isFinite(Date.parse(status.expires_at))))
    && (status.edition !== 'basic-trial' || (!status.template_mapping_enabled && status.expires_at !== null))
}

/** Trials fail closed; full deliveries read optional UI features without expiry checks. */
export async function loadProductStatus(loader: () => Promise<unknown>) {
  if (isExpired()) return
  const request = ++requestId
  const startedAt = performance.now()
  if (trialChecksEnabled && productAccess.value !== 'ready') productAccess.value = 'loading'
  try {
    const status = await loader()
    if (request !== requestId || isExpired()) return
    if (!isProductStatus(status)) throw new Error('Invalid product status')
    if (!trialChecksEnabled) {
      if (status.edition === 'full' && status.expires_at === null && !status.expired) productStatus.value = status
      return
    }
    productStatus.value = status
    if (expiryTimer !== undefined) clearTimeout(expiryTimer)
    expiryTimer = undefined
    const remaining = status.expires_at === null ? Infinity
      : Date.parse(status.expires_at) - Date.parse(status.server_time) - (performance.now() - startedAt)
    if (status.expired || remaining <= 0) {
      markTrialExpired()
      return
    }
    productAccess.value = 'ready'
    if (Number.isFinite(remaining)) {
      const deadline = performance.now() + remaining
      const checkExpiry = () => {
        const delay = deadline - performance.now()
        if (delay <= 0) markTrialExpired()
        else expiryTimer = setTimeout(checkExpiry, Math.min(delay, 2147483647))
      }
      checkExpiry()
    }
  } catch {
    if (trialChecksEnabled && request === requestId && !isExpired()) productAccess.value = 'error'
  }
}
