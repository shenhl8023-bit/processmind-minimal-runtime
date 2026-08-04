import { beforeEach, describe, expect, it, vi } from 'vitest'

vi.mock('./client', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/composables/workflowDataCache', () => ({
  clearAllWorkflowDataCache: vi.fn(),
  clearWorkflowProjectDataCache: vi.fn(),
  getWorkflowDataCache: vi.fn(() => null),
  getWorkflowDataRevision: vi.fn(() => 0),
  setWorkflowDataCache: vi.fn(),
}))

import { api } from './client'
import { getOptionalLatestFinalizedRulePackage } from './extract'

const apiGetMock = vi.mocked(api.get)

describe('getOptionalLatestFinalizedRulePackage', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
  })

  it('returns null when the latest finalized rule package is absent', async () => {
    apiGetMock.mockRejectedValue({ response: { status: 404 } })

    await expect(getOptionalLatestFinalizedRulePackage(42)).resolves.toBeNull()
  })

  it('rethrows a server error unchanged', async () => {
    const error = { response: { status: 500 } }
    apiGetMock.mockRejectedValue(error)

    await expect(getOptionalLatestFinalizedRulePackage(42)).rejects.toBe(error)
  })

  it('rethrows a network error unchanged', async () => {
    const error = new Error('network unavailable')
    apiGetMock.mockRejectedValue(error)

    await expect(getOptionalLatestFinalizedRulePackage(42)).rejects.toBe(error)
  })
})
