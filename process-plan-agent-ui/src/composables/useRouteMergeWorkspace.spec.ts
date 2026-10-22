import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getRouteMergeWorkspace: vi.fn(),
  reviewMergeSuggestion: vi.fn(),
}))

vi.mock('@/api', () => ({
  getRouteMergeWorkspace: mocks.getRouteMergeWorkspace,
  reviewMergeSuggestion: mocks.reviewMergeSuggestion,
  saveNormalizedSupersetRoute: vi.fn(),
}))

vi.mock('@/composables/workflowDataCache', () => ({
  clearWorkflowDataCache: vi.fn(),
  clearWorkflowProjectDataCache: vi.fn(),
  getWorkflowDataCache: vi.fn(),
  getWorkflowDataRevision: vi.fn(() => 1),
  setWorkflowDataCache: vi.fn(),
}))

import { useRouteMergeWorkspace } from './useRouteMergeWorkspace'

function createWorkspace({
  projectId = 12,
  groups = [{ id: 'group-1', operation_ids: [101], status: 'pending', standard_name: '车削' }],
  suggestions = [{ suggestion_id: 'suggestion-1', target_group_id: 'group-1' }],
}: {
  projectId?: number | null
  groups?: Array<Record<string, any>>
  suggestions?: Array<Record<string, any>>
} = {}) {
  const groupRef = ref(groups as any[])
  const suggestionRef = ref(suggestions as any[])
  const options = {
    projectId: ref(projectId),
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
    mocks.getRouteMergeWorkspace.mockReset()
    mocks.reviewMergeSuggestion.mockReset()
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
})
