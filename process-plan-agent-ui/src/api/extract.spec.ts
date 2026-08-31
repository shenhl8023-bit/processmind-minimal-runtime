import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
}))

vi.mock('@/api/client', () => ({
  api: apiMocks,
  apiBaseUrl: '',
}))

import {
  getRouteMergeWorkspace,
  reviewMergeSuggestion,
  saveNormalizedSupersetRoute,
} from './extract'

describe('extract API route merge contracts', () => {
  beforeEach(() => {
    apiMocks.get.mockReset()
    apiMocks.post.mockReset()
  })

  it('loads the route merge workspace through the combined endpoint', async () => {
    apiMocks.get.mockResolvedValueOnce({
      data: {
        project_id: 17,
        superset_route: [],
        merge_suggestions: [],
        normalized_superset_route: [],
        source_signature: 'sig',
        algo_version: 'algo',
      },
    })

    const result = await getRouteMergeWorkspace(17, true)

    expect(apiMocks.get).toHaveBeenCalledWith('/api/extract/route-merge-workspace', {
      params: { project_id: 17 },
    })
    expect(result.source_signature).toBe('sig')
  })

  it('sends workflow revision when saving the normalized route', async () => {
    apiMocks.post.mockResolvedValueOnce({
      data: {
        project_id: 17,
        normalized_superset_route: [],
        saved_route_version: 1,
        source_signature: '',
        algo_version: '',
      },
    })

    await saveNormalizedSupersetRoute({
      project_id: 17,
      expected_workflow_revision: 9,
      normalized_superset_route: [],
    })

    expect(apiMocks.post).toHaveBeenCalledWith('/api/extract/normalized-superset-route/save', {
      project_id: 17,
      expected_workflow_revision: 9,
      normalized_superset_route: [],
    })
  })

  it('sends workflow revision when reviewing a merge suggestion', async () => {
    apiMocks.post.mockResolvedValueOnce({ data: { ok: true } })

    await reviewMergeSuggestion({
      project_id: 17,
      expected_workflow_revision: 9,
      suggestion_id: 'suggestion-1',
      action: 'accept',
    })

    expect(apiMocks.post).toHaveBeenCalledWith('/api/extract/merge-suggestions/review', {
      project_id: 17,
      expected_workflow_revision: 9,
      suggestion_id: 'suggestion-1',
      action: 'accept',
    })
  })
})
