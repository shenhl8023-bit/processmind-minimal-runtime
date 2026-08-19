import { ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getExtractTaskStatus: vi.fn(),
  startExtraction: vi.fn(),
}))

vi.mock('@/api', () => ({
  getExtractTaskStatus: mocks.getExtractTaskStatus,
  startExtraction: mocks.startExtraction,
}))

import { useRouteRulesFlow } from './useRouteRulesFlow'

function createFlow() {
  const workflowRevision = ref(0)
  const projectStatus = ref('UPLOADED')
  const loadRouteMergeWorkspaceFromBackend = vi.fn().mockResolvedValue(true)
  const flow = useRouteRulesFlow({
    projectId: ref<number | null>(7),
    projectStatus,
    workflowRevision,
    routeWorkspaceLoading: ref(false),
    routes: ref([]),
    routeMergeGroups: ref([]),
    routeMergeSuggestions: ref([]),
    routeMergeNormalizedSegments: ref([]),
    selectedMergeGroupId: ref(''),
    routeMergeNotice: ref(''),
    loadRouteMergeWorkspaceFromBackend,
    clearRouteResultDraftStorage: vi.fn(),
    clearPreviewHighlight: vi.fn(),
  })
  return {
    flow,
    loadRouteMergeWorkspaceFromBackend,
    projectStatus,
    workflowRevision,
  }
}

describe('useRouteRulesFlow', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset())
    vi.stubGlobal('window', {
      clearTimeout: vi.fn(),
      setTimeout: vi.fn(),
    })
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('uses the workflow revision returned when extraction starts', async () => {
    mocks.startExtraction.mockResolvedValue({
      ok: true,
      project_id: 7,
      task_status: 'running',
      stage: 'queued',
      message: '已进入后台提炼队列',
      workflow_revision: 1,
    })
    mocks.getExtractTaskStatus.mockResolvedValue({
      project_id: 7,
      task_status: 'completed',
      stage: 'completed',
      message: '工艺路线全集已生成',
      progress: 100,
      project_status: 'ROUTE_SET_READY',
      local_execution_active: false,
      lease_valid: false,
    })
    const state = createFlow()
    let revisionWhenWorkspaceLoaded = -1
    state.loadRouteMergeWorkspaceFromBackend.mockImplementationOnce(async () => {
      revisionWhenWorkspaceLoaded = state.workflowRevision.value
      return true
    })

    await state.flow.startExtraction()

    expect(state.workflowRevision.value).toBe(1)
    expect(revisionWhenWorkspaceLoaded).toBe(1)
    expect(state.projectStatus.value).toBe('ROUTE_SET_READY')
    expect(state.loadRouteMergeWorkspaceFromBackend).toHaveBeenCalledWith(true, false)
  })
})
