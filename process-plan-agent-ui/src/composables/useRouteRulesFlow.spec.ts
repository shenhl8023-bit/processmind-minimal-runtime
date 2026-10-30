import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ getExtractTaskStatus: vi.fn(), startExtraction: vi.fn() }))
vi.mock('@/api', () => mocks)
import { useRouteRulesFlow } from './useRouteRulesFlow'

function createFlow() {
  const options = {
    projectId: ref<number | null>(12), workflowRevision: ref(3), routeWorkspaceLoading: ref(false),
    routes: ref<any[]>([{ id: 12 }]), routeMergeGroups: ref<any[]>([]), routeMergeSuggestions: ref<any[]>([]),
    routeMergeNormalizedSegments: ref<any[]>([]), selectedMergeGroupId: ref(''), routeMergeNotice: ref(''),
    loadRouteMergeWorkspaceFromBackend: vi.fn(async () => true),
    clearRouteResultDraftStorage: vi.fn(), clearPreviewHighlight: vi.fn(),
  }
  return { options, flow: useRouteRulesFlow(options) }
}

describe('route extraction task boundaries', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.stubGlobal('window', { setTimeout, clearTimeout })
    mocks.getExtractTaskStatus.mockReset()
    mocks.startExtraction.mockReset()
  })
  afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals() })

  it('does not restart polling after cancelling an in-flight status request', async () => {
    let finish!: (value: any) => void
    mocks.getExtractTaskStatus.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getExtractTaskStatus.mockResolvedValue({ project_id: 12, task_status: 'running', progress: 20 })
    const { flow } = createFlow()
    const pending = flow.pollExtractionTask()
    flow.stopExtractTaskPolling()
    finish({ project_id: 12, task_status: 'running', progress: 20 })
    await pending
    await vi.advanceTimersByTimeAsync(4000)

    expect(flow.extractTask.value).toBeNull()
    expect(mocks.getExtractTaskStatus).toHaveBeenCalledTimes(1)
  })

  it('does not clear a new task when a previous start request finishes', async () => {
    let finish!: (value: any) => void
    mocks.startExtraction.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getExtractTaskStatus.mockResolvedValue({ project_id: 99, task_status: 'running' })
    const { flow, options } = createFlow()
    const pending = flow.startExtraction()
    options.projectId.value = 99
    options.routes.value = [{ id: 99 }]
    finish({ project_id: 12, workflow_revision: 8, stage: 'queued', message: 'old' })
    await pending

    expect(options.routes.value).toEqual([{ id: 99 }])
    expect(options.workflowRevision.value).toBe(3)
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
    expect(mocks.getExtractTaskStatus).not.toHaveBeenCalled()
  })

  it('does not report an obsolete overlapping initialization as a workspace failure', async () => {
    let finishOld!: (value: boolean) => void
    const { flow, options } = createFlow()
    options.loadRouteMergeWorkspaceFromBackend.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
    const old = flow.loadRouteRulesResults()
    await flow.loadRouteRulesResults()
    finishOld(false)
    await old

    expect(flow.status.value).toBe('done')
    expect(flow.errorMsg.value).toBe('')
  })
})
