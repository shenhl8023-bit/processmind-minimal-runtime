import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getDocumentOperationDetails: vi.fn(), getSavedNormalizedRoute: vi.fn(), getSupersetRoute: vi.fn(),
  listDocuments: vi.fn(), listOperations: vi.fn(), listProjects: vi.fn(),
}))
vi.mock('@/api', () => mocks)
vi.mock('@/composables/useCurrentProject', () => ({
  resolveCurrentProjectId: () => null, clearStoredCurrentProjectId: vi.fn(), setStoredCurrentProjectId: vi.fn(),
}))
import { useAnalysisWorkspaceData } from './useAnalysisWorkspaceData'

describe('analysis workspace task isolation', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset())
    mocks.listProjects.mockResolvedValue([{ id: 1 }, { id: 2 }])
    mocks.getSavedNormalizedRoute.mockResolvedValue({ route_id: 10, segments: [{ id: 'seg-1' }] })
    mocks.listOperations.mockResolvedValue([])
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [] })
    mocks.listDocuments.mockResolvedValue([])
    mocks.getDocumentOperationDetails.mockResolvedValue({ items: [] })
  })

  it('clears old route immediately and ignores pending load when no task remains', async () => {
    let finish!: (value: any) => void
    mocks.getSavedNormalizedRoute.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    data.savedRoute.value = { route_id: 10, segments: [{ id: 'old' }] } as any
    const pending = data.loadSavedRoute()
    await vi.waitFor(() => expect(mocks.getSavedNormalizedRoute).toHaveBeenCalledTimes(1))
    data.projectId.value = null

    expect(data.savedRoute.value).toBeNull()
    finish({ route_id: 10, segments: [{ id: 'old' }] })
    await pending
    expect(data.savedRoute.value).toBeNull()
    expect(data.loading.value).toBe(false)
    scope.stop()
  })
})
