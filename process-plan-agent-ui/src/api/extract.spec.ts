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
import * as extractApi from './extract'
import {
  getOptionalLatestFinalizedRulePackage,
  reviewMergeSuggestion,
  saveNormalizedSupersetRoute,
} from './extract'

const apiGetMock = vi.mocked(api.get)
const apiPostMock = vi.mocked(api.post)

describe('getOptionalLatestFinalizedRulePackage', () => {
  beforeEach(() => {
    apiGetMock.mockReset()
    apiPostMock.mockReset()
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

  it('forwards the workflow revision for route merge writes', async () => {
    apiPostMock.mockResolvedValue({ data: { ok: true } } as never)

    await saveNormalizedSupersetRoute({
      project_id: 7,
      expected_workflow_revision: 12,
      normalized_superset_route: [],
    })
    await reviewMergeSuggestion({
      project_id: 7,
      expected_workflow_revision: 12,
      suggestion_id: 'suggestion-1',
      action: 'rename',
      manual_label: '车外圆',
    })

    expect(apiPostMock).toHaveBeenNthCalledWith(
      1,
      '/api/extract/normalized-superset-route/save',
      expect.objectContaining({ project_id: 7, expected_workflow_revision: 12 }),
    )
    expect(apiPostMock).toHaveBeenNthCalledWith(
      2,
      '/api/extract/merge-suggestions/review',
      expect.objectContaining({ project_id: 7, expected_workflow_revision: 12 }),
    )
  })

  it('loads the complete route merge workspace in one request', async () => {
    const getRouteMergeWorkspace = (extractApi as any).getRouteMergeWorkspace
    expect(getRouteMergeWorkspace).toBeTypeOf('function')
    apiGetMock.mockResolvedValue({ data: { project_id: 7 } } as never)

    await getRouteMergeWorkspace(7, true)

    expect(apiGetMock).toHaveBeenCalledOnce()
    expect(apiGetMock).toHaveBeenCalledWith('/api/extract/route-merge-workspace', {
      params: { project_id: 7 },
    })
  })
})
