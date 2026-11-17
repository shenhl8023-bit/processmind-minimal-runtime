import axios from 'axios'
import { markTrialExpired, productAccess } from '@/composables/productStatus'

export const apiBaseUrl = (() => {
  const explicitBase = import.meta.env.VITE_API_BASE_URL?.trim()
  if (explicitBase) {
    return explicitBase
  }
  return ''
})()

export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 300000,
})

function trialExpiredError() {
  return { response: { status: 403, data: { detail: {
    code: 'trial_expired', message: '试用已到期，请联系供应方。',
  } } } }
}

const isProductStatusRequest = (url?: string) => url?.split('?')[0] === '/api/product-status'

api.interceptors.request.use(config => {
  if (productAccess.value === 'expired' && !isProductStatusRequest(config.url)) {
    return Promise.reject(trialExpiredError())
  }
  return config
})

api.interceptors.response.use(response => {
  if (productAccess.value === 'expired' && !isProductStatusRequest(response.config.url)) {
    return Promise.reject(trialExpiredError())
  }
  return response
}, error => {
  if (error?.response?.status === 403 && error?.response?.data?.detail?.code === 'trial_expired') {
    markTrialExpired()
  }
  return Promise.reject(error)
})
