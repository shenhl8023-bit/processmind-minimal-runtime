import axios from 'axios'

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
