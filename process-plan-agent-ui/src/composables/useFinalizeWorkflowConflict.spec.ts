import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  resetWorkflow: vi.fn(),
}))

vi.mock('@/api', () => ({
  resetWorkflow: mocks.resetWorkflow,
}))

import { workflowResetSignal } from './workflowResetState'
import { useFinalizeWorkflowConflict } from './useFinalizeWorkflowConflict'

function workflowConflict() {
  return {
    response: {
      status: 409,
      data: { detail: { message: '当前页面已过期，请刷新后再操作。' } },
    },
  }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

function createConflict(loadWorkspace = vi.fn().mockResolvedValue(undefined)) {
  const projectId = ref<number | null>(12)
  const savedRoute = ref<any>({ route_id: 120, workflow_revision: 7 })
  const workspaceError = ref('')
  const onlyPending = ref(false)
  const clearAllDrafts = vi.fn()
  const cancelPendingRequests = vi.fn()
  const recognitionQueue = [{ segment: { id: 'segment_turn' } }] as any[]
  const runRecognitionQueue = vi.fn().mockResolvedValue(undefined)
  const showIssue = vi.fn()
  const setBatchNotice = vi.fn()
  const state = useFinalizeWorkflowConflict({
    projectId,
    savedRoute,
    workspaceError,
    onlyPending,
    loadWorkspace,
    clearAllDrafts,
    cancelPendingRequests,
    getRecognitionQueue: () => recognitionQueue,
    runRecognitionQueue,
    showIssue,
    setBatchNotice,
    errorMessage: error => String((error as Error)?.message || error),
  })
  return {
    cancelPendingRequests,
    clearAllDrafts,
    loadWorkspace,
    onlyPending,
    projectId,
    runRecognitionQueue,
    savedRoute,
    setBatchNotice,
    showIssue,
    state,
    workspaceError,
  }
}

describe('useFinalizeWorkflowConflict', () => {
  beforeEach(() => {
    mocks.resetWorkflow.mockReset()
    workflowResetSignal.value = null
  })

  it('coalesces simultaneous revision conflicts into one cleanup and reload', async () => {
    const pendingLoad = deferred<void>()
    const loadWorkspace = vi.fn().mockReturnValue(pendingLoad.promise)
    const context = createConflict(loadWorkspace)

    const first = context.state.handleWorkflowRevisionConflict(workflowConflict())
    const second = context.state.handleWorkflowRevisionConflict(workflowConflict())
    pendingLoad.resolve()

    await expect(Promise.all([first, second])).resolves.toEqual([true, true])
    expect(context.cancelPendingRequests).toHaveBeenCalledOnce()
    expect(loadWorkspace).toHaveBeenCalledOnce()
    expect(loadWorkspace).toHaveBeenCalledWith(true)
    expect(context.showIssue).toHaveBeenCalledWith(
      '页面状态已过期',
      '上游步骤已经重新处理，系统正在加载最新结果。',
    )
  })

  it('clears drafts and pending requests before loading an external upstream reset', async () => {
    const context = createConflict()

    await context.state.handleWorkflowResetSignal({
      projectId: 12,
      fromStep: 3,
      workflowRevision: 9,
      emittedAt: 100,
    })

    expect(context.cancelPendingRequests).toHaveBeenCalledOnce()
    expect(context.clearAllDrafts).toHaveBeenCalledOnce()
    expect(context.loadWorkspace).toHaveBeenCalledWith(true)
  })

  it('resets recognition and restarts only against the returned workflow revision', async () => {
    const context = createConflict()
    mocks.resetWorkflow.mockResolvedValue({
      project_id: 12,
      from_step: 4,
      workflow_revision: 8,
    })
    context.loadWorkspace.mockImplementation(async () => {
      context.savedRoute.value = { route_id: 120, workflow_revision: 8 }
    })

    await context.state.handleResetAllRecognition()
    await vi.waitFor(() => expect(context.runRecognitionQueue).toHaveBeenCalledOnce())

    expect(mocks.resetWorkflow).toHaveBeenCalledWith({
      project_id: 12,
      from_step: 4,
      expected_workflow_revision: 7,
    })
    expect(context.onlyPending.value).toBe(true)
    expect(context.runRecognitionQueue).toHaveBeenCalledWith(
      expect.any(Array),
      expect.any(Function),
    )
    expect(context.cancelPendingRequests).toHaveBeenCalledOnce()
    expect(context.clearAllDrafts).not.toHaveBeenCalled()
  })
})
