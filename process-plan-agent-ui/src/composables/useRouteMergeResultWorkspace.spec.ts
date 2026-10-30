import { computed, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useRouteMergeResultWorkspace } from './useRouteMergeResultWorkspace'

function createWorkspace(sourceOperationIds = [900006]) {
  const sourceOperation = {
    id: 900006,
    name: '车削加工（B侧）',
    sequence: 70,
    source_nodes: ['攻螺纹', '车外圆', '车端面', '镗孔', '车槽'],
    step_items: ['攻螺纹', '车外圆', '车端面', '镗孔', '车槽'],
    factors: [],
  }
  const secondOperation = {
    id: 900007,
    name: '铣扁',
    sequence: 90,
    source_nodes: ['铣扁'],
    step_items: ['铣扁'],
    factors: [],
  }
  const sourceOperations = [sourceOperation, secondOperation]
  const entries = new Map<string, string>()
  const localStorage = {
    getItem: vi.fn((key: string) => entries.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => entries.set(key, value)),
    removeItem: vi.fn((key: string) => entries.delete(key)),
  }
  vi.stubGlobal('localStorage', localStorage)
  vi.stubGlobal('window', {
    setTimeout: vi.fn(() => 1),
    clearTimeout: vi.fn(),
  })

  const workspace = useRouteMergeResultWorkspace({
    projectId: ref(3),
    routeMergeNormalizedSegments: ref([{
      id: 'split-900006',
      normalized_step_name: '车削加工（B侧）',
      source_operation_ids: sourceOperationIds,
      source_nodes: sourceOperations.flatMap(operation => operation.source_nodes),
      source_operation_names: [],
      review_status: 'kept',
      source_type: 'split_from_reject',
    }]),
    routeFullSetDisplayOrderedOperations: computed(() => sourceOperations as any),
    routeFullSetOperations: computed(() => sourceOperations as any),
    routeMergeGroupsSorted: computed(() => []),
    routeMergeCandidateGroups: computed(() => []),
    selectedMergeGroupId: ref(''),
    selectedMergeGroup: computed(() => null),
    totalRouteSampleCount: computed(() => 20),
    routeMergeEditUnlocked: computed(() => true),
    formatSampleCoverage: (hit, total) => `${hit}/${total}`,
  })

  return workspace
}

describe('useRouteMergeResultWorkspace', () => {
  afterEach(() => { vi.unstubAllGlobals(); vi.restoreAllMocks() })
  it('does not split one source operation into its individual source steps', () => {
    const workspace = createWorkspace()

    workspace.syncRouteMergePreviewDraftFromNormalizedRoute()
    const current = workspace.routeMergeResultItems.value[0]
    expect(current?.childItems).toHaveLength(1)

    workspace.splitPreviewItem(current!.id)

    expect(workspace.routeMergeResultItems.value).toHaveLength(1)
    expect(workspace.routeMergeResultItems.value[0]?.name).toBe('车削加工（B侧）')
    expect(workspace.routeMergeResultItems.value[0]?.childItems).toHaveLength(1)
  })

  it('splits a merged segment back into source operations, not source steps', () => {
    const workspace = createWorkspace([900006, 900007])

    workspace.syncRouteMergePreviewDraftFromNormalizedRoute()
    const current = workspace.routeMergeResultItems.value[0]
    expect(current?.childItems).toHaveLength(2)

    workspace.splitPreviewItem(current!.id)

    expect(workspace.routeMergeResultItems.value.map(item => item.name)).toEqual(['车削加工（B侧）', '铣扁'])
    expect(workspace.routeMergeResultItems.value.flatMap(item => item.operationIds)).toEqual([900006, 900007])
    expect(workspace.routeMergeResultItems.value.map(item => item.sourceNodes)).toEqual([
      ['攻螺纹', '车外圆', '车端面', '镗孔', '车槽'],
      ['铣扁'],
    ])
  })

  it('preserves a renamed source operation through merge, restore and split', () => {
    const workspace = createWorkspace([900006, 900007])
    workspace.syncRouteMergePreviewDraftFromNormalizedRoute()
    workspace.splitPreviewItem(workspace.routeMergeResultItems.value[0]!.id)
    const firstId = workspace.routeMergeResultItems.value[0]!.id
    workspace.renamePreviewItem({ itemId: firstId, name: '已确认车削名称' })
    workspace.mergePreviewItemToNext(firstId)
    workspace.syncRouteMergePreviewDraft()
    workspace.splitPreviewItem(workspace.routeMergeResultItems.value[0]!.id)

    expect(workspace.routeMergeResultItems.value.map(item => item.name)).toEqual(['已确认车削名称', '铣扁'])
    expect(workspace.routeMergeResultItems.value.flatMap(item => item.operationIds)).toEqual([900006, 900007])
  })

  it('keeps distinct inserted rows when two inserts happen in the same millisecond', () => {
    vi.spyOn(Date, 'now').mockReturnValue(1000)
    const workspace = createWorkspace()
    workspace.syncRouteMergePreviewDraftFromNormalizedRoute()
    const baseId = workspace.routeMergeResultItems.value[0]!.id
    workspace.insertPreviewItemAfter(baseId)
    workspace.insertPreviewItemAfter(baseId)
    const inserted = workspace.routeMergeResultItems.value.filter(item => item.id !== baseId)
    workspace.renamePreviewItem({ itemId: inserted[0]!.id, name: '只改这一行' })
    workspace.movePreviewItemDown(inserted[0]!.id)
    workspace.syncRouteMergePreviewDraft()

    expect(new Set(workspace.routeMergeResultItems.value.map(item => item.id)).size).toBe(3)
    expect(workspace.routeMergeResultItems.value.map(item => item.name)).toEqual(['车削加工（B侧）', '新增工序', '只改这一行'])
  })
})
