import { nextTick, ref, type ComputedRef, type Ref } from 'vue'
import { reviewMergeSuggestion, type MergeSuggestion } from '@/api'
import type { MergeGroupStatus, RouteMergeGroup, RouteMergePreviewItem } from '@/composables/useRouteMergeResultWorkspace'

type UseRouteMergeInteractionActionsOptions = {
  projectId: Ref<number | null>
  routeMergeGroups: Ref<RouteMergeGroup[]>
  routeMergeSuggestions: Ref<MergeSuggestion[]>
  routeMergeCandidateGroups: ComputedRef<RouteMergeGroup[]>
  routeMergeResultItems: ComputedRef<RouteMergePreviewItem[]>
  selectedMergeGroupId: Ref<string>
  selectedPreviewItemId: Ref<string>
  routeMergeBatchSubmitting: Ref<boolean>
  routeMergeNotice: Ref<string>
  applyMergeSuggestionAction: (groupId: string, action: 'accept' | 'reject', setError: (message: string) => void) => Promise<boolean>
  refreshRouteMergeWorkspace: (preferredGroupId?: string, syncPreviewDraft?: boolean) => Promise<boolean>
  triggerPreviewHighlight: (payload: { groupIds?: string[]; operationIds?: number[] }) => void
  mergeGroupCandidateLabel: (group: RouteMergeGroup) => string
  setError: (message: string) => void
  cancelPreviewRenameBase: () => void
  startPreviewRenameBase: () => void
  submitPreviewRenameBase: () => void
  movePreviewItemUpBase: (itemId: string) => void
  movePreviewItemDownBase: (itemId: string) => void
  reorderPreviewItemsBase: (payload: { draggedId: string; targetId: string }) => void
  mergePreviewItemToPreviousBase: (itemId: string) => void
  mergePreviewItemToNextBase: (itemId: string) => void
  splitPreviewItemBase: (itemId: string) => void
  insertPreviewItemAfterBase: (itemId: string) => void
  removePreviewItemBase: (itemId: string) => void
}

function escapeAttributeSelector(value: string) {
  return value.replace(/\\/g, '\\\\').replace(/"/g, '\\"')
}

export function useRouteMergeInteractionActions(options: UseRouteMergeInteractionActionsOptions) {
  const routeMergeRenameGroupId = ref('')
  const routeMergeRenameDraft = ref('')

  function findPreviewItemByOperationIds(operationIds: number[]) {
    const targetIds = new Set((operationIds || []).map(id => Number(id)).filter(Boolean))
    if (!targetIds.size) return null
    const exact = options.routeMergeResultItems.value.find(item => {
      const itemIds = new Set(item.operationIds.map(id => Number(id)).filter(Boolean))
      if (itemIds.size !== targetIds.size) return false
      return [...targetIds].every(id => itemIds.has(id))
    })
    if (exact) return exact
    const overlapping = options.routeMergeResultItems.value
      .map((item) => ({
        item,
        overlap: item.operationIds.filter(id => targetIds.has(Number(id))).length,
      }))
      .filter(entry => entry.overlap > 0)
      .sort((a, b) => b.overlap - a.overlap || a.item.sequence - b.item.sequence)
    return overlapping[0]?.item || null
  }

  async function focusMergeGroup(groupId: string) {
    if (!groupId) return
    await nextTick()
    const selector = `[data-merge-group-id="${escapeAttributeSelector(groupId)}"]`
    const targets = [
      document.querySelector(`.route-pane-left ${selector}`) as HTMLElement | null,
      document.querySelector(`.route-pane-center ${selector}`) as HTMLElement | null,
      document.querySelector(`.route-pane-right ${selector}`) as HTMLElement | null,
    ]
    targets.forEach((target) => {
      target?.scrollIntoView({ behavior: 'smooth', block: 'nearest', inline: 'nearest' })
    })
  }

  function cancelRouteMergeRename() {
    routeMergeRenameGroupId.value = ''
    routeMergeRenameDraft.value = ''
  }

  async function confirmMergeGroup(groupId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.selectedMergeGroupId.value = groupId
    await focusMergeGroup(groupId)
    await options.applyMergeSuggestionAction(groupId, 'accept', options.setError)
  }

  async function rejectMergeGroup(groupId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.selectedMergeGroupId.value = groupId
    await focusMergeGroup(groupId)
    await options.applyMergeSuggestionAction(groupId, 'reject', options.setError)
  }

  function selectPreviewItem(itemId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.selectedPreviewItemId.value = itemId
    const item = options.routeMergeResultItems.value.find(entry => entry.id === itemId)
    if (!item) return
    const matchedGroup = options.routeMergeCandidateGroups.value.find(group => group.id === item.groupId)
    options.selectedMergeGroupId.value = matchedGroup?.id || ''
    options.triggerPreviewHighlight({
      groupIds: matchedGroup ? [matchedGroup.id] : [],
      operationIds: item.operationIds,
    })
    void focusMergeGroup(matchedGroup?.id || item.groupId)
  }

  function movePreviewItemUp(itemId: string) {
    cancelRouteMergeRename()
    options.movePreviewItemUpBase(itemId)
  }

  function movePreviewItemDown(itemId: string) {
    cancelRouteMergeRename()
    options.movePreviewItemDownBase(itemId)
  }

  function reorderPreviewItems(payload: { draggedId: string; targetId: string }) {
    cancelRouteMergeRename()
    options.reorderPreviewItemsBase(payload)
  }

  function mergePreviewItemToPrevious(itemId: string) {
    cancelRouteMergeRename()
    options.mergePreviewItemToPreviousBase(itemId)
  }

  function mergePreviewItemToNext(itemId: string) {
    cancelRouteMergeRename()
    options.mergePreviewItemToNextBase(itemId)
  }

  function splitPreviewItem(itemId: string) {
    cancelRouteMergeRename()
    options.splitPreviewItemBase(itemId)
  }

  function insertPreviewItemAfter(itemId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.insertPreviewItemAfterBase(itemId)
    options.startPreviewRenameBase()
  }

  function removePreviewItem(itemId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.removePreviewItemBase(itemId)
  }

  function startPreviewRename() {
    cancelRouteMergeRename()
    options.startPreviewRenameBase()
  }

  function cancelPreviewRename() {
    options.cancelPreviewRenameBase()
  }

  function submitPreviewRename() {
    options.submitPreviewRenameBase()
  }

  function startRouteMergeRename(groupId: string) {
    options.cancelPreviewRenameBase()
    const current = options.routeMergeCandidateGroups.value.find(group => group.id === groupId)
    if (!current) return
    routeMergeRenameGroupId.value = groupId
    routeMergeRenameDraft.value = options.mergeGroupCandidateLabel(current) || current.standard_name || ''
    options.selectedMergeGroupId.value = groupId
  }

  async function submitRouteMergeRename(groupId: string) {
    const current = options.routeMergeCandidateGroups.value.find(group => group.id === groupId)
    if (!current || !options.projectId.value || !routeMergeRenameDraft.value.trim()) return
    const suggestion = options.routeMergeSuggestions.value.find(item => item.target_group_id === current.id)
    if (!suggestion?.suggestion_id) {
      options.setError('保存改名失败：未找到对应的后端归并建议，请刷新后重试。')
      return
    }
    options.routeMergeBatchSubmitting.value = true
    try {
      const nextLabel = routeMergeRenameDraft.value.trim()
      await reviewMergeSuggestion({
        project_id: options.projectId.value,
        suggestion_id: suggestion.suggestion_id,
        action: 'rename',
        manual_label: nextLabel,
      })
      options.routeMergeGroups.value = options.routeMergeGroups.value.map(group =>
        group.id === groupId
          ? { ...group, standard_name: nextLabel, source_type: 'manual_adjusted' }
          : group,
      )
      cancelRouteMergeRename()
      await options.refreshRouteMergeWorkspace(groupId, false)
      options.triggerPreviewHighlight({
        groupIds: [groupId],
        operationIds: [...current.operation_ids],
      })
      options.routeMergeNotice.value = `已将候选归并名称改为「${nextLabel}」，待你确认后再执行合并。`
    } catch (error) {
      console.error('调用后端保存归并改名失败', error)
      options.setError('保存改名失败，请稍后重试。')
    } finally {
      options.routeMergeBatchSubmitting.value = false
    }
  }

  function selectMergeGroup(groupId: string) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    options.selectedMergeGroupId.value = groupId
    const matchedGroup = options.routeMergeCandidateGroups.value.find(group => group.id === groupId)
    const previewItem = options.routeMergeResultItems.value.find(item => item.groupId === groupId)
      || findPreviewItemByOperationIds(matchedGroup?.operation_ids || [])
    options.selectedPreviewItemId.value = previewItem?.id || ''
    if (previewItem) {
      options.triggerPreviewHighlight({
        groupIds: previewItem.groupId ? [previewItem.groupId] : [],
        operationIds: previewItem.operationIds,
      })
    }
    void focusMergeGroup(groupId)
  }

  function selectMergeGroupByOperation(operationId: number) {
    cancelRouteMergeRename()
    options.cancelPreviewRenameBase()
    const matched = options.routeMergeCandidateGroups.value.find(group => group.operation_ids.includes(operationId))
    if (matched) {
      options.selectedMergeGroupId.value = matched.id
      const previewItem = options.routeMergeResultItems.value.find(item => item.groupId === matched.id)
        || findPreviewItemByOperationIds(matched.operation_ids)
      options.selectedPreviewItemId.value = previewItem?.id || ''
      options.triggerPreviewHighlight({
        groupIds: previewItem?.groupId ? [previewItem.groupId] : [],
        operationIds: previewItem?.operationIds?.length ? previewItem.operationIds : matched.operation_ids,
      })
      void focusMergeGroup(matched.id)
      return
    }
    const previewItem = options.routeMergeResultItems.value.find(item => item.operationIds.includes(operationId))
    if (previewItem) {
      options.selectedPreviewItemId.value = previewItem.id
      options.selectedMergeGroupId.value = ''
      options.triggerPreviewHighlight({ operationIds: previewItem.operationIds })
    }
  }

  function mergeGroupStatusLabel(status: MergeGroupStatus) {
    if (status === 'merged') return '已归并'
    if (status === 'kept') return '保持独立'
    if (status === 'conflict') return '待定'
    return '待归并'
  }

  function mergeGroupTagClass(status: MergeGroupStatus) {
    if (status === 'merged') return 'tag-success'
    if (status === 'kept') return 'tag-neutral'
    if (status === 'conflict') return 'tag-danger'
    return 'tag-warning'
  }

  return {
    routeMergeRenameGroupId,
    routeMergeRenameDraft,
    focusMergeGroup,
    confirmMergeGroup,
    rejectMergeGroup,
    selectPreviewItem,
    movePreviewItemUp,
    movePreviewItemDown,
    reorderPreviewItems,
    mergePreviewItemToPrevious,
    mergePreviewItemToNext,
    splitPreviewItem,
    insertPreviewItemAfter,
    removePreviewItem,
    startPreviewRename,
    cancelPreviewRename,
    submitPreviewRename,
    startRouteMergeRename,
    cancelRouteMergeRename,
    submitRouteMergeRename,
    selectMergeGroup,
    selectMergeGroupByOperation,
    mergeGroupStatusLabel,
    mergeGroupTagClass,
  }
}
