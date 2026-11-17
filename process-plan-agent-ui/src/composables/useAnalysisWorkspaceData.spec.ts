import { effectScope } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getDocumentOperationDetails: vi.fn(), getSavedNormalizedRoute: vi.fn(), getSupersetRoute: vi.fn(),
  listDocuments: vi.fn(), listOperations: vi.fn(), listProjects: vi.fn(), getAnalysisGuidance: vi.fn(), generateAnalysisGuidance: vi.fn(),
}))
vi.mock('@/api', () => mocks)
vi.mock('@/composables/useCurrentProject', () => ({
  resolveCurrentProjectId: () => null, clearStoredCurrentProjectId: vi.fn(), setStoredCurrentProjectId: vi.fn(),
}))
import { useAnalysisWorkspaceData } from './useAnalysisWorkspaceData'
import { clearWorkflowProjectDataCache } from './workflowDataCache'

describe('analysis workspace task isolation', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset())
    mocks.listProjects.mockResolvedValue([{ id: 1 }, { id: 2 }])
    mocks.getSavedNormalizedRoute.mockResolvedValue({ route_id: 10, segments: [{ id: 'seg-1' }] })
    mocks.listOperations.mockResolvedValue([])
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [] })
    mocks.listDocuments.mockResolvedValue([])
    mocks.getDocumentOperationDetails.mockResolvedValue({ items: [] })
    mocks.getAnalysisGuidance.mockResolvedValue({ configuration: { revision: 4 } })
    mocks.generateAnalysisGuidance.mockResolvedValue({ configuration: { revision: 4 } })
  })

  it('loads project guidance with route data and clears it when the task changes', async () => {
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    await data.loadSavedRoute()
    expect(mocks.getAnalysisGuidance).toHaveBeenCalledWith(1)
    expect(data.analysisGuidance.value).toEqual({ revision: 4 })
    data.projectId.value = 2
    expect(data.analysisGuidance.value).toBeNull()
    scope.stop()
  })

  it.each(['route', 'revision', 'revision cycle', 'lock'] as const)('ignores generation success after a same-project %s change', async (change) => {
    let finish!: (value: any) => void
    mocks.getSavedNormalizedRoute.mockResolvedValueOnce({ project_id: 1, route_id: 10, workflow_revision: 5, segments: [] })
    mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    try {
      data.projectId.value = 1
      const pending = data.loadSavedRoute()
      await vi.waitFor(() => expect(data.guidanceGenerating.value).toBe(true))
      if (change === 'route') data.savedRoute.value = { ...data.savedRoute.value!, route_id: 20 }
      if (change === 'revision') data.savedRoute.value!.workflow_revision = 6
      if (change === 'revision cycle') { data.savedRoute.value!.workflow_revision = 6; data.savedRoute.value!.workflow_revision = 5 }
      if (change === 'lock') data.savedRoute.value!.analysis_locked = true
      finish({ configuration: { revision: 999 } })
      await pending
      expect(data.analysisGuidance.value).toBeNull()
      expect(data.guidanceError.value).toBe('')
      expect(data.guidanceGenerating.value).toBe(false)
    } finally { scope.stop() }
  })

  it('rejects generated guidance explicitly bound to a different route', async () => {
    mocks.generateAnalysisGuidance.mockResolvedValueOnce({ configuration: { revision: 999, generation_route_id: 99 } })
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    try {
      data.projectId.value = 1
      await data.loadSavedRoute()
      expect(data.analysisGuidance.value).toBeNull()
      expect(data.guidanceError.value).toContain('路线')
    } finally { scope.stop() }
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
  it('keeps the route available but does not silently use old guidance after generation failure', async () => {
    mocks.generateAnalysisGuidance.mockRejectedValueOnce({ response: { data: { detail: { message: '请重试问答生成' } } } })
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    await data.loadSavedRoute()
    expect(data.savedRoute.value?.route_id).toBe(10)
    expect(data.analysisGuidance.value).toBeNull()
    expect(data.guidanceError.value).toBe('请重试问答生成')
    scope.stop()
  })
  it('does not regenerate a locked route or apply generation returned to a different task', async () => {
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    mocks.getSavedNormalizedRoute.mockResolvedValueOnce({ route_id: 10, analysis_locked: true, segments: [] })
    await data.loadSavedRoute()
    expect(mocks.generateAnalysisGuidance).not.toHaveBeenCalled()
    let finish!: (value: any) => void
    mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const pending = data.loadSavedRoute()
    await vi.waitFor(() => expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(1))
    data.projectId.value = 2
    finish({ configuration: { revision: 999 } })
    await pending
    expect(data.analysisGuidance.value).toBeNull()
    scope.stop()
  })

  it('retries recommendations once, keeps the usable guide on failure, and ignores late retry results', async () => {
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    await data.loadSavedRoute()
    let reject!: (reason: unknown) => void
    mocks.generateAnalysisGuidance.mockImplementationOnce((_id, retry) => {
      if (!retry) return Promise.resolve({ configuration: { revision: 999 } })
      return new Promise((_resolve, fail) => { reject = fail })
    })
    const running = data.loadSavedRoute(true, true)
    await vi.waitFor(() => expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(2))
    await data.loadSavedRoute(true, true)
    expect(data.analysisGuidance.value).toEqual({ revision: 4 })
    expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(2)
    reject({ response: { data: { detail: { message: '推荐重试暂不可用' } } } })
    await running
    expect(data.analysisGuidance.value).toEqual({ revision: 4 })
    expect(data.guidanceError.value).toBe('推荐重试暂不可用')
    let finish!: (value: any) => void
    mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const late = data.loadSavedRoute(true, true)
    await vi.waitFor(() => expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(3))
    data.projectId.value = 2
    finish({ configuration: { revision: 999 } })
    await late
    expect(data.analysisGuidance.value).toBeNull()
    scope.stop()
  })

  it('shows the loaded route while guidance is generating and blocks duplicate refreshes', async () => {
    let finish!: (value: any) => void
    mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    const pending = data.loadSavedRoute()
    await vi.waitFor(() => expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(1))
    expect(data.savedRoute.value?.route_id).toBe(10)
    expect(data.loading.value).toBe(false)
    expect(data.guidanceGenerating.value).toBe(true)
    await data.loadSavedRoute(true)
    expect(mocks.generateAnalysisGuidance).toHaveBeenCalledTimes(1)
    finish({ configuration: { revision: 5 } })
    await pending
    expect(data.guidanceGenerating.value).toBe(false)
    expect(data.analysisGuidance.value?.revision).toBe(5)
    scope.stop()
  })

  it.each(['resolve', 'reject'] as const)('releases generation state and timer after cache invalidation when generation will %s, allowing reload', async (outcome) => {
    vi.useFakeTimers()
    let finish!: (value: any) => void
    let reject!: (reason: unknown) => void
    mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise((resolve, fail) => {
      finish = resolve
      reject = fail
    }))
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    try {
      data.projectId.value = 1
      const pending = data.loadSavedRoute()
      await vi.waitFor(() => expect(data.guidanceGenerating.value).toBe(true))
      vi.advanceTimersByTime(2000)
      expect(data.generationElapsedSeconds.value).toBe(2)

      // A mutation in another project changes the shared workflow revision.
      clearWorkflowProjectDataCache(2)
      if (outcome === 'resolve') finish({ configuration: { revision: 999 } })
      else reject({ response: { data: { detail: { message: '过期失败', reason: '过期原因' } } } })
      await pending

      expect(data.analysisGuidance.value).toBeNull()
      expect(data.guidanceError.value).toBe('')
      expect(data.guidanceErrorReason.value).toBe('')
      expect(data.loading.value).toBe(false)
      expect(data.guidanceGenerating.value).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
      vi.advanceTimersByTime(3000)
      expect(data.generationElapsedSeconds.value).toBe(2)

      mocks.getSavedNormalizedRoute.mockResolvedValueOnce({ route_id: 20, segments: [{ id: 'refreshed' }] })
      mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
      const reload = data.loadSavedRoute(true)
      await vi.waitFor(() => expect(data.guidanceGenerating.value).toBe(true))
      expect(data.savedRoute.value?.route_id).toBe(20)
      expect(data.selectedSegmentId.value).toBe('refreshed')
      expect(data.generationElapsedSeconds.value).toBe(0)
      vi.advanceTimersByTime(1000)
      expect(data.generationElapsedSeconds.value).toBe(1)
      finish({ configuration: { revision: 6 } })
      await reload
      expect(data.analysisGuidance.value?.revision).toBe(6)
      expect(data.guidanceGenerating.value).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      scope.stop()
      vi.useRealTimers()
    }
  })

  it('does not let a previous project generation clear the current project busy state or timer', async () => {
    vi.useFakeTimers()
    let finishPrevious!: (value: any) => void
    let finishCurrent!: (value: any) => void
    mocks.generateAnalysisGuidance
      .mockReturnValueOnce(new Promise(resolve => { finishPrevious = resolve }))
      .mockReturnValueOnce(new Promise(resolve => { finishCurrent = resolve }))
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    try {
      data.projectId.value = 1
      const previous = data.loadSavedRoute()
      await vi.waitFor(() => expect(data.guidanceGenerating.value).toBe(true))
      vi.advanceTimersByTime(2000)
      data.projectId.value = 2
      const current = data.loadSavedRoute()
      await vi.waitFor(() => expect(data.guidanceGenerating.value).toBe(true))
      vi.advanceTimersByTime(1000)
      expect(data.generationElapsedSeconds.value).toBe(1)

      finishPrevious({ configuration: { revision: 999 } })
      await previous
      expect(data.analysisGuidance.value).toBeNull()
      expect(data.guidanceGenerating.value).toBe(true)
      expect(data.generationElapsedSeconds.value).toBe(1)
      expect(vi.getTimerCount()).toBe(1)
      vi.advanceTimersByTime(1000)
      expect(data.generationElapsedSeconds.value).toBe(2)

      finishCurrent({ configuration: { revision: 6 } })
      await current
      expect(data.analysisGuidance.value?.revision).toBe(6)
      expect(data.guidanceGenerating.value).toBe(false)
      expect(vi.getTimerCount()).toBe(0)
    } finally {
      scope.stop()
      vi.useRealTimers()
    }
  })

  it('makes an Axios timeout actionable and releases the generation timer for retry', async () => {
    vi.useFakeTimers()
    mocks.generateAnalysisGuidance.mockRejectedValueOnce({ code: 'ECONNABORTED' })
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    try {
      data.projectId.value = 1
      await data.loadSavedRoute()
      expect(data.guidanceGenerating.value).toBe(false)
      expect(data.guidanceErrorReason.value).toContain('超时')
      expect(vi.getTimerCount()).toBe(0)
      await data.loadSavedRoute(true)
      expect(data.analysisGuidance.value?.revision).toBe(4)
      expect(data.guidanceError.value).toBe('')
      expect(data.guidanceErrorReason.value).toBe('')
      expect(data.guidanceGenerating.value).toBe(false)
    } finally {
      scope.stop()
      vi.useRealTimers()
    }
  })

  it('keeps a separate actionable generation failure reason and clears it on project switch', async () => {
    mocks.generateAnalysisGuidance.mockRejectedValueOnce({ response: { data: { detail: {
      message: '问答生成未完成，请重试。', reason: '工序项目铣削的特征条件分支缺少有效分组和候选',
    } } } })
    const scope = effectScope()
    const data = scope.run(() => useAnalysisWorkspaceData({ getRouteProjectId: () => undefined }))!
    data.projectId.value = 1
    await data.loadSavedRoute()
    expect(data.guidanceErrorReason.value).toContain('缺少有效分组')
    expect(data.guidanceGenerating.value).toBe(false)
    data.projectId.value = 2
    expect(data.guidanceErrorReason.value).toBe('')
    scope.stop()
  })
})
