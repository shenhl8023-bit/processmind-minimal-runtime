import { nextTick, ref, type ComputedRef, type Ref } from 'vue'
import {
  getMergeSuggestions,
  getNormalizedSupersetRoute,
  getSupersetRoute,
  reviewMergeSuggestion,
  saveNormalizedSupersetRoute,
  type MergeSuggestion,
  type OperationItem,
} from '@/api'
import type { RouteMergeGroup, RouteMergePreviewItem } from '@/composables/useRouteMergeResultWorkspace'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'
import {
  clearWorkflowDataCache,
  clearWorkflowProjectDataCache,
  getWorkflowDataCache,
  setWorkflowDataCache,
} from '@/composables/workflowDataCache'

type UseRouteMergeWorkspaceOptions = {
  projectId: Ref<number | null>
  routes: Ref<OperationItem[]>
  routeMergeGroups: Ref<RouteMergeGroup[]>
  routeMergeSuggestions: Ref<MergeSuggestion[]>
  routeMergeNormalizedSegments: Ref<any[]>
  selectedMergeGroupId: Ref<string>
  selectedPreviewItemId: Ref<string>
  routeMergeActionableGroupsSorted: ComputedRef<RouteMergeGroup[]>
  routeMergeCandidateGroups: ComputedRef<RouteMergeGroup[]>
  selectedMergeGroup: ComputedRef<RouteMergeGroup | null>
  selectedMergeSuggestionItem: ComputedRef<MergeSuggestion | null>
  routeMergeResultItems: ComputedRef<RouteMergePreviewItem[]>
  routeMergePreviewItems: ComputedRef<RouteMergePreviewItem[]>
  routeMergeEditUnlocked: ComputedRef<boolean>
  buildRouteMergeGroupsFromSuggestions: (suggestions: MergeSuggestion[]) => RouteMergeGroup[]
  buildRoutePreviewStats: (group: RouteMergeGroup) => { coverageLabel: string; evidenceCount: number }
  findPreferredMergeGroupId: (groups: RouteMergeGroup[]) => string
  isMergeGroupActionable: (group?: RouteMergeGroup | null) => boolean
  getNextActionableGroupId: (currentId: string) => string
  mergeGroupCandidateLabel: (group: RouteMergeGroup) => string
  syncRouteMergePreviewDraft: (preferredItemId?: string) => void
  clearLegacyRouteMergeStorage: () => void
  clearRouteResultDraftStorage: () => void
  saveRouteResultDraftToStorage: () => void
  triggerPreviewHighlight: (payload: { groupIds?: string[]; operationIds?: number[] }) => void
  focusMergeGroup: (groupId: string) => Promise<void>
  cancelRouteMergeRename: () => void
  cancelPreviewRename: () => void
}

type RouteMergeWorkspaceSnapshot = {
  supersetResult: Awaited<ReturnType<typeof getSupersetRoute>>
  mergeResult: Awaited<ReturnType<typeof getMergeSuggestions>>
  normalizedResult: Awaited<ReturnType<typeof getNormalizedSupersetRoute>>
}

function routeMergeWorkspaceCacheKey(projectId: number | string) {
  return `workflow:route-merge:v1:${projectId}`
}

export function useRouteMergeWorkspace(options: UseRouteMergeWorkspaceOptions) {
  const routeMergeNotice = ref('')
  const routeWorkspaceLoading = ref(false)
  const routeMergeBatchSubmitting = ref(false)
  const ROUTE_MERGE_SNAPSHOT_META_VERSION = 'v1'

  function routeMergeSnapshotMetaStorageKey() {
    if (!options.projectId.value) return ''
    return `processmind_route_merge_snapshot_meta_${ROUTE_MERGE_SNAPSHOT_META_VERSION}_${options.projectId.value}`
  }

  function readRouteMergeSnapshotMeta() {
    const key = routeMergeSnapshotMetaStorageKey()
    if (!key) return null
    try {
      const raw = localStorage.getItem(key)
      if (!raw) return null
      const parsed = JSON.parse(raw)
      return {
        algo_version: String(parsed?.algo_version || ''),
        source_signature: String(parsed?.source_signature || ''),
      }
    } catch (error) {
      console.error('读取路线归并快照元信息失败', error)
      return null
    }
  }

  function writeRouteMergeSnapshotMeta(meta: { algo_version: string; source_signature: string }) {
    const key = routeMergeSnapshotMetaStorageKey()
    if (!key) return
    localStorage.setItem(key, JSON.stringify(meta))
  }

  function buildRouteMergeSnapshotNotice(
    previousMeta: { algo_version: string; source_signature: string } | null,
    currentMeta: { algo_version: string; source_signature: string },
  ) {
    if (!previousMeta) return ''
    const previousAlgo = String(previousMeta.algo_version || '')
    const currentAlgo = String(currentMeta.algo_version || '')
    const previousSignature = String(previousMeta.source_signature || '')
    const currentSignature = String(currentMeta.source_signature || '')
    if (previousAlgo && currentAlgo && previousAlgo !== currentAlgo) {
      return `第二步规则已从 ${previousAlgo} 更新为 ${currentAlgo}，当前结果已按新规则重建，请复核并按需重新提炼。`
    }
    if (previousSignature && currentSignature && previousSignature !== currentSignature) {
      return '当前项目的第二步归并结果已更新，请复核并按需重新提炼。'
    }
    return ''
  }

  function findPreviewItemIdForGroupId(groupId: string) {
    if (!groupId) return ''
    const exact = options.routeMergeResultItems.value.find(item => item.groupId === groupId)
    if (exact) return exact.id
    const matchedGroup = options.routeMergeCandidateGroups.value.find(group => group.id === groupId)
    if (!matchedGroup) return ''
    const targetIds = new Set(matchedGroup.operation_ids.map(id => Number(id)).filter(Boolean))
    if (!targetIds.size) return ''
    const overlapping = options.routeMergeResultItems.value
      .map(item => ({
        item,
        overlap: item.operationIds.filter(id => targetIds.has(Number(id))).length,
      }))
      .filter(entry => entry.overlap > 0)
      .sort((a, b) => b.overlap - a.overlap || a.item.sequence - b.item.sequence)
    return overlapping[0]?.item.id || ''
  }

  async function applyRouteMergeWorkspaceSnapshot(
    snapshot: RouteMergeWorkspaceSnapshot,
    syncPreviewDraft: boolean,
  ) {
    const previousSnapshotMeta = readRouteMergeSnapshotMeta()
    options.clearLegacyRouteMergeStorage()
    const { supersetResult, mergeResult, normalizedResult } = snapshot
    const currentSnapshotMeta = {
      algo_version: String(normalizedResult.algo_version || mergeResult.algo_version || ''),
      source_signature: String(normalizedResult.source_signature || mergeResult.source_signature || ''),
    }
    const snapshotChanged = Boolean(
      previousSnapshotMeta
      && (
        String(previousSnapshotMeta.algo_version || '') !== currentSnapshotMeta.algo_version
        || String(previousSnapshotMeta.source_signature || '') !== currentSnapshotMeta.source_signature
      ),
    )
    if (snapshotChanged) {
      options.clearRouteResultDraftStorage()
    }
    options.routes.value = supersetResult.superset_route || []
    options.routeMergeSuggestions.value = mergeResult.merge_suggestions || []
    options.routeMergeNormalizedSegments.value = normalizedResult.normalized_superset_route || []
    options.routeMergeGroups.value = options.buildRouteMergeGroupsFromSuggestions(options.routeMergeSuggestions.value)
    options.selectedMergeGroupId.value = options.findPreferredMergeGroupId(options.routeMergeGroups.value)
    await nextTick()
    if (syncPreviewDraft) {
      options.syncRouteMergePreviewDraft(
        findPreviewItemIdForGroupId(options.selectedMergeGroupId.value),
      )
    }
    routeMergeNotice.value = buildRouteMergeSnapshotNotice(previousSnapshotMeta, currentSnapshotMeta)
    writeRouteMergeSnapshotMeta(currentSnapshotMeta)
    return true
  }

  async function fetchRouteMergeWorkspace(projectId: number, forceRefresh = false) {
    const [supersetResult, mergeResult, normalizedResult] = await Promise.all([
      getSupersetRoute(projectId, forceRefresh),
      getMergeSuggestions(projectId, forceRefresh),
      getNormalizedSupersetRoute(projectId, forceRefresh),
    ])
    return {
      supersetResult,
      mergeResult,
      normalizedResult,
    }
  }

  async function loadRouteMergeWorkspaceFromBackend(syncPreviewDraft = true, forceRefresh = false) {
    if (!options.projectId.value) return false
    const projectId = options.projectId.value
    const cacheKey = routeMergeWorkspaceCacheKey(projectId)
    try {
      const cachedSnapshot = forceRefresh
        ? null
        : getWorkflowDataCache<RouteMergeWorkspaceSnapshot>(cacheKey)
      if (cachedSnapshot) {
        return await applyRouteMergeWorkspaceSnapshot(cachedSnapshot, syncPreviewDraft)
      }

      const snapshot = await fetchRouteMergeWorkspace(projectId, forceRefresh)
      setWorkflowDataCache(cacheKey, snapshot)
      return await applyRouteMergeWorkspaceSnapshot(snapshot, syncPreviewDraft)
    } catch (error) {
      console.error('加载后端路线归并工作台失败', error)
      return false
    }
  }

  async function refreshRouteMergeWorkspace(preferredGroupId?: string, syncPreviewDraft = true) {
    const loaded = await loadRouteMergeWorkspaceFromBackend(syncPreviewDraft, true)
    if (!loaded) return false
    if (
      preferredGroupId
      && options.routeMergeGroups.value.some(group => group.id === preferredGroupId)
      && options.isMergeGroupActionable(options.routeMergeGroups.value.find(group => group.id === preferredGroupId) || null)
    ) {
      options.selectedMergeGroupId.value = preferredGroupId
    } else {
      options.selectedMergeGroupId.value = options.findPreferredMergeGroupId(options.routeMergeGroups.value)
    }
    options.selectedPreviewItemId.value = findPreviewItemIdForGroupId(options.selectedMergeGroupId.value)
      || options.routeMergeResultItems.value[0]?.id
      || ''
    return true
  }

  async function applyMergeSuggestionAction(groupId: string, action: 'accept' | 'reject', setError: (message: string) => void) {
    const current = options.routeMergeCandidateGroups.value.find(group => group.id === groupId)
    if (!current || !options.projectId.value) return false
    const suggestion = options.routeMergeSuggestions.value.find(item => item.target_group_id === current.id)
    if (!suggestion?.suggestion_id) return false
    const affectedOperationIds = [...current.operation_ids]
    const nextGroupId = options.getNextActionableGroupId(groupId)

    try {
      await reviewMergeSuggestion({
        project_id: options.projectId.value,
        suggestion_id: suggestion.suggestion_id,
        action,
      })
      clearWorkflowProjectDataCache(options.projectId.value)
      options.clearRouteResultDraftStorage()
      await refreshRouteMergeWorkspace(nextGroupId, true)
      options.triggerPreviewHighlight({
        groupIds: action === 'accept' ? [groupId] : [],
        operationIds: affectedOperationIds,
      })
      if (options.selectedMergeGroupId.value) await options.focusMergeGroup(options.selectedMergeGroupId.value)
      routeMergeNotice.value = action === 'accept'
        ? `已确认将「${options.mergeGroupCandidateLabel(current)}」归并为当前标准化母路线名称。`
        : `已确认「${options.mergeGroupCandidateLabel(current)}」不合并。`
      return true
    } catch (error) {
      console.error('调用后端保存归并动作失败', error)
      setError(action === 'accept' ? '保存归并结果失败，请稍后重试。' : '保存不合并结果失败，请稍后重试。')
      return false
    }
  }

  async function confirmAllMergeGroups(setError: (message: string) => void) {
    if (routeMergeBatchSubmitting.value || !options.routeMergeActionableGroupsSorted.value.length) return
    routeMergeBatchSubmitting.value = true
    options.cancelRouteMergeRename()
    options.cancelPreviewRename()
    try {
      const pendingIds = options.routeMergeActionableGroupsSorted.value.map(group => group.id)
      for (const groupId of pendingIds) {
        const ok = await applyMergeSuggestionAction(groupId, 'accept', setError)
        if (!ok) break
      }
      routeMergeNotice.value = '已按系统建议完成全部合并。'
    } finally {
      routeMergeBatchSubmitting.value = false
    }
  }

  async function rejectAllMergeGroups(setError: (message: string) => void) {
    if (routeMergeBatchSubmitting.value || !options.routeMergeActionableGroupsSorted.value.length) return
    routeMergeBatchSubmitting.value = true
    options.cancelRouteMergeRename()
    options.cancelPreviewRename()
    try {
      const pendingIds = options.routeMergeActionableGroupsSorted.value.map(group => group.id)
      for (const groupId of pendingIds) {
        const ok = await applyMergeSuggestionAction(groupId, 'reject', setError)
        if (!ok) break
      }
      routeMergeNotice.value = '已将全部候选归并组设为不合并。'
    } finally {
      routeMergeBatchSubmitting.value = false
    }
  }

  async function saveRouteMergeWorkspace(setError: (message: string) => void) {
    options.saveRouteResultDraftToStorage()
    routeMergeNotice.value = '当前结果路线草稿已保存。'
    if (options.projectId.value && options.routeMergeEditUnlocked.value) {
      try {
        const normalizeStringList = (values: unknown, fallbackValues: string[] = []) => {
          const unique = new Set<string>()
          const normalized: string[] = []
          ;(Array.isArray(values) ? values : []).forEach((value) => {
            const text = formatRouteDisplayName(String(value || ''))
            if (!text || unique.has(text)) return
            unique.add(text)
            normalized.push(text)
          })
          if (!normalized.length) {
            fallbackValues.forEach((value) => {
              const text = formatRouteDisplayName(String(value || ''))
              if (!text || unique.has(text)) return
              unique.add(text)
              normalized.push(text)
            })
          }
          return normalized
        }
        const payload = options.routeMergeResultItems.value.map((item) => ({
          id: item.id,
          normalized_step_name: formatRouteDisplayName(item.name),
          source_operation_ids: [...item.operationIds],
          source_nodes: normalizeStringList(
            item.sourceNodes,
            (item.childItems || []).flatMap(child => child.sourceNodes || []),
          ),
          source_operation_names: normalizeStringList((item.childItems || []).map(child => child.name)),
          review_status: item.status || 'merged',
          source_type: item.manuallyEdited ? 'manual_adjusted' : 'system_generated',
        }))
        const saved = await saveNormalizedSupersetRoute({
          project_id: options.projectId.value,
          normalized_superset_route: payload,
        })
        clearWorkflowProjectDataCache(options.projectId.value)
        options.routeMergeNormalizedSegments.value = saved.normalized_superset_route || []
        routeMergeNotice.value = '第三步结果路线已保存到后端。'
        return true
      } catch (error) {
        console.error('调用后端保存结果路线失败', error)
        setError('保存结果路线失败，请稍后重试。')
        return false
      }
    }
    const current = options.selectedMergeGroup.value
    const suggestion = options.selectedMergeSuggestionItem.value
    if (options.projectId.value && current && suggestion?.suggestion_id) {
      try {
        clearWorkflowDataCache(routeMergeWorkspaceCacheKey(options.projectId.value))
        await reviewMergeSuggestion({
          project_id: options.projectId.value,
          suggestion_id: suggestion.suggestion_id,
          action: 'rename',
          manual_label: current.standard_name,
        })
        await refreshRouteMergeWorkspace(current.id)
        routeMergeNotice.value = '当前路线归并结果已保存到后端工作台状态。'
        return true
      } catch (error) {
        console.error('调用后端保存归并名称失败', error)
        setError('保存归并名称失败，请稍后重试。')
        return false
      }
    }
    return false
  }

  return {
    routeMergeNotice,
    routeWorkspaceLoading,
    routeMergeBatchSubmitting,
    loadRouteMergeWorkspaceFromBackend,
    refreshRouteMergeWorkspace,
    applyMergeSuggestionAction,
    confirmAllMergeGroups,
    rejectAllMergeGroups,
    saveRouteMergeWorkspace,
  }
}
