import { api } from './client'
import { loadProductStatus, productAccess, trialChecksEnabled } from '@/composables/productStatus'

let pending: Promise<void> | null = null

export function refreshProductStatus() {
  if (!pending) {
    pending = loadProductStatus(async () => {
      const { data } = await api.get('/api/product-status', { timeout: 10000 })
      return data
    }).finally(() => { pending = null })
  }
  return pending
}

/** Recheck the server while open, including after an inactive browser resumes. */
export function startProductStatusSync() {
  if (!trialChecksEnabled) return () => {}
  const refresh = () => { if (productAccess.value !== 'expired') void refreshProductStatus() }
  const timer = window.setInterval(refresh, 30000)
  const onVisible = () => { if (document.visibilityState === 'visible') refresh() }
  window.addEventListener('focus', refresh)
  document.addEventListener('visibilitychange', onVisible)
  return () => {
    window.clearInterval(timer)
    window.removeEventListener('focus', refresh)
    document.removeEventListener('visibilitychange', onVisible)
  }
}
