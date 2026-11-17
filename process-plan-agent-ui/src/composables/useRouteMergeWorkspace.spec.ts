import { computed, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getRouteMergeWorkspace: vi.fn(),
  reviewMergeSuggestion: vi.fn(),
  saveNormalizedSupersetRoute: vi.fn(),
  refreshWorkflowNavigation: vi.fn(),
}))

vi.mock('@/api', () => ({
  getRouteMergeWorkspace: mocks.getRouteMergeWorkspace,
  reviewMergeSuggestion: mocks.reviewMergeSuggestion,
  saveNormalizedSupersetRoute: mocks.saveNormalizedSupersetRoute,
}))

vi.mock('@/composables/workflowNavigation', () => ({
  refreshWorkflowNavigation: mocks.refreshWorkflowNavigation,
}))

import { clearAllWorkflowDataCache } from './workflowDataCache'
import { useRouteMergeWorkspace } from './useRouteMergeWorkspace'
import { buildRouteMergeGroupsFromSuggestions, findPreferredMergeGroupId, isMergeGroupActionable } from './extractViewHelpers'

function createWorkspace({
  projectId = 12,
  projectCreatedAt = '2026-11-02T06:00:00.000000',
  groups = [{ id: 'group-1', operation_ids: [101], status: 'pending', standard_name: '车削' }],
  suggestions = [{ suggestion_id: 'suggestion-1', target_group_id: 'group-1' }],
}: {
  projectId?: number | null
  projectCreatedAt?: string
  groups?: Array<Record<string, any>>
  suggestions?: Array<Record<string, any>>
} = {}) {
  const groupRef = ref(groups as any[])
  const suggestionRef = ref(suggestions as any[])
  const options = {
    projectId: ref(projectId),
    projectCreatedAt: ref(projectCreatedAt),
    workflowRevision: ref(3),
    routes: ref([]),
    routeMergeGroups: groupRef,
    routeMergeSuggestions: suggestionRef,
    routeMergeNormalizedSegments: ref([]),
    selectedMergeGroupId: ref('group-1'),
    selectedPreviewItemId: ref(''),
    routeMergeActionableGroupsSorted: computed(() => groupRef.value as any),
    routeMergeCandidateGroups: computed(() => groupRef.value as any),
    selectedMergeGroup: computed(() => groupRef.value[0] as any || null),
    selectedMergeSuggestionItem: computed(() => suggestionRef.value[0] as any || null),
    routeMergeResultItems: computed(() => []),
    routeMergePreviewItems: computed(() => []),
    routeMergeEditUnlocked: computed(() => false),
    templateGroupAliasesForItem: vi.fn(() => []),
    buildRouteMergeGroupsFromSuggestions: vi.fn(() => []),
    buildRoutePreviewStats: vi.fn(() => ({ coverageLabel: '', evidenceCount: 0 })),
    findPreferredMergeGroupId: vi.fn(() => ''),
    isMergeGroupActionable: vi.fn(() => true),
    getNextActionableGroupId: vi.fn(() => ''),
    mergeGroupCandidateLabel: vi.fn(() => '车削'),
    syncRouteMergePreviewDraft: vi.fn(),
    clearLegacyRouteMergeStorage: vi.fn(),
    clearRouteResultDraftStorage: vi.fn(),
    saveRouteResultDraftToStorage: vi.fn(),
    triggerPreviewHighlight: vi.fn(),
    focusMergeGroup: vi.fn(),
    cancelRouteMergeRename: vi.fn(),
    cancelPreviewRename: vi.fn(),
  } as any
  return { workspace: useRouteMergeWorkspace(options), options }
}

describe('useRouteMergeWorkspace merge review feedback', () => {
  beforeEach(() => {
    const storage = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: vi.fn((key: string) => storage.get(key) ?? null),
      setItem: vi.fn((key: string, value: string) => storage.set(key, value)),
    })
    clearAllWorkflowDataCache()
    mocks.getRouteMergeWorkspace.mockReset()
    mocks.reviewMergeSuggestion.mockReset()
    mocks.saveNormalizedSupersetRoute.mockReset()
    mocks.refreshWorkflowNavigation.mockReset()
    mocks.refreshWorkflowNavigation.mockResolvedValue({})
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12,
      superset_route: [],
      merge_suggestions: [],
      normalized_superset_route: [],
      source_signature: 'signature',
      algo_version: 'v1',
    })
    mocks.reviewMergeSuggestion.mockResolvedValue({ ok: true })
  })
  afterEach(() => vi.unstubAllGlobals())

  it('loads a new project without an update notice or clearing its draft', async () => {
    const { workspace, options } = createWorkspace()

    expect(await workspace.loadRouteMergeWorkspaceFromBackend()).toBe(true)
    expect(workspace.routeMergeNotice.value).toBe('')
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
  })

  it('ignores legacy snapshot metadata whose project identity is unknown', async () => {
    localStorage.setItem('processmind_route_merge_snapshot_meta_v1_12', JSON.stringify({
      algo_version: 'v37', source_signature: 'previous-installation',
    }))
    const { workspace, options } = createWorkspace()

    expect(await workspace.loadRouteMergeWorkspaceFromBackend()).toBe(true)
    expect(workspace.routeMergeNotice.value).toBe('')
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
  })

  it('does not report an upgrade or clear the draft when a new database reuses a project id', async () => {
    const oldProject = createWorkspace({ projectCreatedAt: '2026-10-30T03:00:00.000000' })
    await oldProject.workspace.loadRouteMergeWorkspaceFromBackend()
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, superset_route: [{ id: 1201, name: '新项目工序' }],
      source_signature: 'new-project', algo_version: 'v38',
    })
    const { workspace, options } = createWorkspace()

    expect(await workspace.loadRouteMergeWorkspaceFromBackend(true, true)).toBe(true)
    expect(options.routes.value).toEqual([{ id: 1201, name: '新项目工序' }])
    expect(workspace.routeMergeNotice.value).toBe('')
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
  })

  it('does not reuse the in-memory workspace of a different project with the same id', async () => {
    const oldProject = createWorkspace({ projectCreatedAt: '2026-10-30T03:00:00.000000' })
    await oldProject.workspace.loadRouteMergeWorkspaceFromBackend()
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, superset_route: [{ id: 1201, name: '新项目工序' }],
      source_signature: 'new-project', algo_version: 'v38',
    })
    const { workspace, options } = createWorkspace()

    expect(await workspace.loadRouteMergeWorkspaceFromBackend()).toBe(true)
    expect(mocks.getRouteMergeWorkspace).toHaveBeenCalledTimes(2)
    expect(options.routes.value).toEqual([{ id: 1201, name: '新项目工序' }])
  })

  it('invalidates a changed algorithm in the same project with a readable result notice', async () => {
    const { workspace, options } = createWorkspace()
    await workspace.loadRouteMergeWorkspaceFromBackend()
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, superset_route: [{ id: 1201, name: '更新工序' }],
      source_signature: 'updated-signature', algo_version: 'v38',
    })

    expect(await workspace.loadRouteMergeWorkspaceFromBackend(true, true)).toBe(true)
    expect(options.clearRouteResultDraftStorage).toHaveBeenCalledTimes(1)
    expect(workspace.routeMergeNotice.value).toBe('当前项目的第二步归并结果已更新，请复核并按需重新提炼。')
    expect(options.routes.value).toEqual([{ id: 1201, name: '更新工序' }])
  })

  it('still invalidates a changed source in the same project and stays quiet on repeated loads', async () => {
    const { workspace, options } = createWorkspace()
    await workspace.loadRouteMergeWorkspaceFromBackend()
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, source_signature: 'changed-documents', algo_version: 'v1',
    })

    await workspace.loadRouteMergeWorkspaceFromBackend(true, true)
    expect(options.clearRouteResultDraftStorage).toHaveBeenCalledTimes(1)
    expect(workspace.routeMergeNotice.value).toContain('归并结果已更新')
    await workspace.loadRouteMergeWorkspaceFromBackend()
    expect(options.clearRouteResultDraftStorage).toHaveBeenCalledTimes(1)
    expect(workspace.routeMergeNotice.value).toBe('')
  })

  it('ignores a late response after project identity changes while the numeric id stays the same', async () => {
    let finish!: (value: any) => void
    mocks.getRouteMergeWorkspace.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { workspace, options } = createWorkspace()
    const pending = workspace.loadRouteMergeWorkspaceFromBackend()
    options.projectCreatedAt.value = '2026-11-02T07:00:00.000000'
    options.routes.value = [{ id: 9901, name: '新项目工序' }]
    finish({ project_id: 12, superset_route: [{ id: 1201, name: '旧项目工序' }] })

    expect(await pending).toBe(false)
    expect(options.routes.value).toEqual([{ id: 9901, name: '新项目工序' }])
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
  })

  it('refreshes workflow access and uses the new revision after saving a changed route', async () => {
    mocks.saveNormalizedSupersetRoute.mockResolvedValue({
      project_id: 12,
      normalized_superset_route: [],
      saved_route_version: 2,
      workflow_revision: 4,
      source_signature: 'signature',
      algo_version: 'v1',
    })
    const { workspace, options } = createWorkspace()
    options.routeMergeEditUnlocked = computed(() => true)

    const saved = await workspace.saveRouteMergeWorkspace(vi.fn())

    expect(saved).toBe(true)
    expect(options.workflowRevision.value).toBe(4)
    expect(mocks.refreshWorkflowNavigation).toHaveBeenCalledWith(12)
  })

  it('reports a missing candidate group without calling the review API', async () => {
    const { workspace } = createWorkspace({ groups: [] })
    const setError = vi.fn()

    const result = await workspace.applyMergeSuggestionAction('missing', 'accept', setError)

    expect(result).toBe(false)
    expect(mocks.reviewMergeSuggestion).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledWith(expect.stringContaining('候选'))
  })

  it('reports a missing project without calling the review API', async () => {
    const { workspace } = createWorkspace({ projectId: null })
    const setError = vi.fn()

    const result = await workspace.applyMergeSuggestionAction('group-1', 'accept', setError)

    expect(result).toBe(false)
    expect(mocks.reviewMergeSuggestion).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledWith(expect.stringContaining('项目'))
  })

  it('reports a missing backend suggestion without calling the review API', async () => {
    const { workspace } = createWorkspace({ suggestions: [] })
    const setError = vi.fn()

    const result = await workspace.applyMergeSuggestionAction('group-1', 'accept', setError)

    expect(result).toBe(false)
    expect(mocks.reviewMergeSuggestion).not.toHaveBeenCalled()
    expect(setError).toHaveBeenCalledWith(expect.stringContaining('建议'))
  })

  it('reports workspace refresh failure after review and does not claim success', async () => {
    mocks.getRouteMergeWorkspace.mockRejectedValue(new Error('offline'))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    const { workspace } = createWorkspace()
    const setError = vi.fn()

    const result = await workspace.applyMergeSuggestionAction('group-1', 'accept', setError)

    expect(mocks.reviewMergeSuggestion).toHaveBeenCalledTimes(1)
    expect(mocks.getRouteMergeWorkspace).toHaveBeenCalledTimes(1)
    expect(result).toBe(false)
    expect(setError).toHaveBeenCalledWith(expect.stringContaining('刷新'))
    consoleError.mockRestore()
  })

  it('stops a batch on its first failed review and does not show completion', async () => {
    mocks.reviewMergeSuggestion.mockRejectedValue(new Error('revision conflict'))
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.stubGlobal('localStorage', { getItem: vi.fn(() => null), setItem: vi.fn() })
    const { workspace } = createWorkspace({
      groups: [
        { id: 'group-1', operation_ids: [101], status: 'pending', standard_name: '车削' },
        { id: 'group-2', operation_ids: [102], status: 'pending', standard_name: '钻孔' },
      ],
      suggestions: [
        { suggestion_id: 'suggestion-1', target_group_id: 'group-1' },
        { suggestion_id: 'suggestion-2', target_group_id: 'group-2' },
      ],
    })
    const setError = vi.fn()

    await workspace.confirmAllMergeGroups(setError)

    expect(mocks.reviewMergeSuggestion).toHaveBeenCalledTimes(1)
    expect(setError).toHaveBeenCalledWith(expect.stringContaining('失败'))
    expect(workspace.routeMergeNotice.value).not.toContain('完成全部合并')
    vi.unstubAllGlobals()
    consoleError.mockRestore()
  })

  it('shows batch completion only after every review succeeds', async () => {
    vi.stubGlobal('localStorage', { getItem: vi.fn(() => null), setItem: vi.fn() })
    const { workspace } = createWorkspace()
    const setError = vi.fn()

    await workspace.confirmAllMergeGroups(setError)

    expect(mocks.reviewMergeSuggestion).toHaveBeenCalledTimes(1)
    expect(setError).not.toHaveBeenCalled()
    expect(workspace.routeMergeNotice.value).toBe('已确认全部候选归并组。')
    vi.unstubAllGlobals()
  })

  it('does not accept the previous candidates while rerun results are loading', async () => {
    const { workspace } = createWorkspace({
      groups: [{ id: 'group-1', operation_ids: [900005, 900045], status: 'pending', standard_name: '车削加工（A侧）' }],
    })
    workspace.routeWorkspaceLoading.value = true

    await workspace.confirmAllMergeGroups(vi.fn())

    expect(mocks.reviewMergeSuggestion).not.toHaveBeenCalled()
    expect(workspace.routeMergeNotice.value).not.toBe('已确认全部候选归并组。')
  })

  it('does not carry accept-all into the next inference when candidate ids are reused', async () => {
    // Reruns retain these deterministic candidate ids even when model advice changes.
    const turningId = 'segment-slot_deburr_into_turning-turning_internal_bore_into_turning-turning_internal_face_into_turning-900005-900011-900045-900046'
    const suggestions = [
      {
        suggestion_id: 'suggestion-segment-blank_prep', target_group_id: 'segment-blank_prep',
        source_operation_ids: [900001, 900002], normalized_step_name: '下料/备料',
        sequence: 10, status: 'pending', suggestion_type: 'direct_merge',
      },
      {
        suggestion_id: `suggestion-${turningId}`, target_group_id: turningId,
        source_operation_ids: [900005, 900011, 900045, 900046], normalized_step_name: '车削加工（A侧）',
        recommended_target_name: '车削加工（A侧）', sequence: 50, status: 'pending',
        suggestion_type: 'absorb_into_parent', advice_source: 'local_rules',
      },
    ]
    const { workspace, options } = createWorkspace({
      groups: buildRouteMergeGroupsFromSuggestions(suggestions as any), suggestions,
    })
    options.buildRouteMergeGroupsFromSuggestions = buildRouteMergeGroupsFromSuggestions
    options.findPreferredMergeGroupId = findPreferredMergeGroupId
    options.routeMergeActionableGroupsSorted = computed(() => options.routeMergeGroups.value.filter(isMergeGroupActionable))
    const reviewedSuggestions = [{ ...suggestions[0], status: 'merged' }, suggestions[1]]
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, superset_route: [], merge_suggestions: reviewedSuggestions,
      normalized_superset_route: [], source_signature: 'signature', algo_version: 'v1',
    })
    const nextInference = [{
      ...suggestions[1], advice_source: 'model', advice_action: 'absorb_into_parent',
      // Controlled model response, not a claim about the historical model output.
      recommended_target_name: '车削加工（A侧，含钻镗孔、平端面及挖槽去毛刺）',
    }]
    options.focusMergeGroup.mockImplementationOnce(() => {
      // Finish the first review, then deliver the rerun before the batch resumes.
      queueMicrotask(() => queueMicrotask(() => {
        options.workflowRevision.value = 4
        options.routeMergeSuggestions.value = nextInference
        options.routeMergeGroups.value = buildRouteMergeGroupsFromSuggestions(nextInference as any)
        workspace.routeMergeNotice.value = '新一轮推理结果待确认'
      }))
      return Promise.resolve()
    })

    await workspace.confirmAllMergeGroups(vi.fn())

    expect(mocks.reviewMergeSuggestion.mock.calls.map(([body]) => body)).toEqual([{
      project_id: 12, expected_workflow_revision: 3,
      suggestion_id: 'suggestion-segment-blank_prep', action: 'accept',
    }])
    expect(options.routeMergeGroups.value[0].status).toBe('pending')
    expect(options.routeMergeGroups.value[0].recommended_target_name)
      .toBe('车削加工（A侧，含钻镗孔、平端面及挖槽去毛刺）')
    expect(workspace.routeMergeNotice.value).toBe('新一轮推理结果待确认')

    // A new explicit accept-all may accept that advice unchanged in revision 4.
    const acceptedRoute = [{
      id: turningId, source_operation_ids: [900005, 900011, 900045, 900046],
      normalized_step_name: '车削加工（A侧，含钻镗孔、平端面及挖槽去毛刺）', review_status: 'merged',
    }]
    mocks.getRouteMergeWorkspace.mockResolvedValue({
      project_id: 12, superset_route: [], normalized_superset_route: acceptedRoute,
      merge_suggestions: [{ ...nextInference[0], status: 'merged' }],
      source_signature: 'signature', algo_version: 'v1',
    })
    await workspace.confirmAllMergeGroups(vi.fn())

    expect(mocks.reviewMergeSuggestion.mock.calls.map(([body]) => body.expected_workflow_revision)).toEqual([3, 4])
    expect(options.routeMergeNormalizedSegments.value).toEqual(acceptedRoute)
    expect(workspace.routeMergeNotice.value).toBe('已确认全部候选归并组。')
  })

  it('ignores a workspace response after switching tasks', async () => {
    let finish!: (value: any) => void
    mocks.getRouteMergeWorkspace.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { workspace, options } = createWorkspace()
    const pending = workspace.loadRouteMergeWorkspaceFromBackend()
    options.projectId.value = 99
    options.routes.value = [{ id: 9901, name: '新任务' }]
    finish({ project_id: 12, superset_route: [{ id: 1201, name: '旧任务' }] })

    expect(await pending).toBe(false)
    expect(options.routes.value).toEqual([{ id: 9901, name: '新任务' }])
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
  })

  it('keeps the newer refresh when requests resolve in reverse order', async () => {
    vi.stubGlobal('localStorage', { getItem: vi.fn(() => null), setItem: vi.fn() })
    let finishOld!: (value: any) => void
    mocks.getRouteMergeWorkspace.mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
    mocks.getRouteMergeWorkspace.mockResolvedValueOnce({ project_id: 12, superset_route: [{ id: 2 }] })
    const { workspace, options } = createWorkspace()
    const old = workspace.loadRouteMergeWorkspaceFromBackend(true, true)
    await workspace.loadRouteMergeWorkspaceFromBackend(true, true)
    finishOld({ project_id: 12, superset_route: [{ id: 1 }] })

    expect(await old).toBe(false)
    expect(options.routes.value).toEqual([{ id: 2 }])
    vi.unstubAllGlobals()
  })

  it('does not clear the new task draft when an old merge review finishes', async () => {
    let finish!: (value: any) => void
    mocks.reviewMergeSuggestion.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { workspace, options } = createWorkspace()
    const pending = workspace.applyMergeSuggestionAction('group-1', 'accept', vi.fn())
    options.projectId.value = 99
    finish({ ok: true })

    expect(await pending).toBe(false)
    expect(options.clearRouteResultDraftStorage).not.toHaveBeenCalled()
    expect(mocks.getRouteMergeWorkspace).not.toHaveBeenCalled()
  })
})
