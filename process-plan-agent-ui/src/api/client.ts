import axios from 'axios'

export const apiBaseUrl = (() => {
  const explicitBase = import.meta.env.VITE_API_BASE_URL?.trim()
  if (explicitBase) {
    return explicitBase
  }
  if (import.meta.env.DEV && typeof window !== 'undefined') {
    return `http://${window.location.hostname}:8000`
  }
  return ''
})()

export const api = axios.create({
  baseURL: apiBaseUrl,
  timeout: 300000,
})
