import { computed, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useRouteMergeResultWorkspace } from './useRouteMergeResultWorkspace'

function createWorkspace(sourceOperationIds = [900006], {
  entries = new Map<string, string>(),
  projectCreatedAt = '2026-11-02T06:00:00.000000',
} = {}) {
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
    projectCreatedAt: ref(projectCreatedAt),
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
  it('restores a saved draft for the same project identity', () => {
    const entries = new Map<string, string>()
    const original = createWorkspace([900006], { entries })
    original.syncRouteMergePreviewDraftFromNormalizedRoute()
    original.renamePreviewItem({ itemId: original.routeMergeResultItems.value[0]!.id, name: '人工确认名称' })
    original.saveRouteResultDraftToStorage()
    const restored = createWorkspace([900006], { entries })

    restored.syncRouteMergePreviewDraft()
    expect(restored.routeMergeResultItems.value[0]?.name).toBe('人工确认名称')
  })

  it('does not restore or delete another project draft when project and operation ids are reused', () => {
    const entries = new Map<string, string>()
    const old = createWorkspace([900006], { entries, projectCreatedAt: '2026-10-30T03:00:00.000000' })
    old.syncRouteMergePreviewDraftFromNormalizedRoute()
    old.renamePreviewItem({ itemId: old.routeMergeResultItems.value[0]!.id, name: '旧项目人工名称' })
    old.saveRouteResultDraftToStorage()
    const current = createWorkspace([900006], { entries })

    current.syncRouteMergePreviewDraft()
    expect(current.routeMergeResultItems.value[0]?.name).toBe('车削加工（B侧）')
    current.clearRouteResultDraftStorage()
    old.syncRouteMergePreviewDraft()
    expect(old.routeMergeResultItems.value[0]?.name).toBe('旧项目人工名称')
  })

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
