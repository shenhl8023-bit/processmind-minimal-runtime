import { computed, ref } from 'vue'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ reviewMergeSuggestion: vi.fn() }))
vi.mock('@/api', () => mocks)
import { useRouteMergeInteractionActions } from './useRouteMergeInteractionActions'

function createActions() {
  const groups = ref<any[]>([{ id: 'group-1', standard_name: '车削', operation_ids: [1] }])
  const options = {
    projectId: ref(12), workflowRevision: ref(3), routeMergeGroups: groups,
    routeMergeSuggestions: ref<any[]>([{ suggestion_id: 'suggestion-1', target_group_id: 'group-1' }]),
    routeMergeCandidateGroups: computed(() => groups.value), routeMergeResultItems: computed(() => []),
    selectedMergeGroupId: ref('group-1'), selectedPreviewItemId: ref(''), routeMergeBatchSubmitting: ref(false),
    routeMergeNotice: ref(''), applyMergeSuggestionAction: vi.fn(), refreshRouteMergeWorkspace: vi.fn(async () => true),
    triggerPreviewHighlight: vi.fn(), mergeGroupCandidateLabel: (group: any) => group.standard_name,
    setError: vi.fn(), cancelPreviewRenameBase: vi.fn(), startPreviewRenameBase: vi.fn(), submitPreviewRenameBase: vi.fn(),
    movePreviewItemUpBase: vi.fn(), movePreviewItemDownBase: vi.fn(), reorderPreviewItemsBase: vi.fn(),
    mergePreviewItemToPreviousBase: vi.fn(), mergePreviewItemToNextBase: vi.fn(), splitPreviewItemBase: vi.fn(),
    insertPreviewItemAfterBase: vi.fn(), removePreviewItemBase: vi.fn(),
  }
  const actions = useRouteMergeInteractionActions(options)
  actions.startRouteMergeRename('group-1')
  actions.routeMergeRenameDraft.value = '新车削'
  return { actions, options }
}

describe('route merge rename request boundaries', () => {
  beforeEach(() => mocks.reviewMergeSuggestion.mockReset())
  afterEach(() => vi.restoreAllMocks())

  it('does not rename the next task when an earlier rename finishes', async () => {
    let finish!: (value: any) => void
    mocks.reviewMergeSuggestion.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { actions, options } = createActions()
    const pending = actions.submitRouteMergeRename('group-1')
    options.projectId.value = 99
    options.routeMergeGroups.value = [{ id: 'group-1', standard_name: '另一任务', operation_ids: [99] }]
    finish({ ok: true })
    await pending

    expect(options.routeMergeGroups.value[0].standard_name).toBe('另一任务')
    expect(options.refreshRouteMergeWorkspace).not.toHaveBeenCalled()
    expect(options.routeMergeNotice.value).toBe('')
  })

  it('reports a refresh failure after rename instead of announcing a completed update', async () => {
    mocks.reviewMergeSuggestion.mockResolvedValue({ ok: true })
    const { actions, options } = createActions()
    options.refreshRouteMergeWorkspace.mockResolvedValue(false)
    await actions.submitRouteMergeRename('group-1')

    expect(options.setError).toHaveBeenCalledWith(expect.stringContaining('刷新'))
    expect(options.routeMergeNotice.value).toBe('')
  })

  it('submits only once while a rename is already in flight', async () => {
    let finish!: (value: any) => void
    mocks.reviewMergeSuggestion.mockReturnValue(new Promise(resolve => { finish = resolve }))
    const { actions } = createActions()
    const first = actions.submitRouteMergeRename('group-1')
    const second = actions.submitRouteMergeRename('group-1')
    finish({ ok: true })
    await Promise.all([first, second])

    expect(mocks.reviewMergeSuggestion).toHaveBeenCalledTimes(1)
  })
})
