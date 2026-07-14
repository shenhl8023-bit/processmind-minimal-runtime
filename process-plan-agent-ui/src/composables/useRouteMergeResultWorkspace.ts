import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { MergeMatchedDetailRow, OperationItem } from '@/api'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'

export type MergeGroupStatus = 'pending' | 'merged' | 'kept' | 'conflict'

export type RouteMergeGroup = {
  id: string
  sequence: number
  standard_name: string
  operation_ids: number[]
  status: MergeGroupStatus
  coverageLabel: string
  suggestion_type?: string
  recommendation_label?: string
  recommendation_reason?: string
  recommended_target_name?: string
  step_family?: string
  phase?: string
  separator_result?: string
  manual_review_required?: boolean
  reason_codes?: string[]
  evidence_excerpt?: string[]
  matched_detail_rows?: MergeMatchedDetailRow[]
  source_type?: string
  parent_segment?: string
  equipment_child_segment?: string
  equipment_split_applied?: boolean
  equipment_types?: string[]
  equipment_models?: string[]
  equipment_support_result?: string
  equipment_support_reason?: string
  object_chain?: string
  subtype_key?: string
  stage_key?: string
}

export type RouteMergePreviewChildItem = {
  id: string
  groupId: string
  name: string
  operationIds: number[]
  sourceNodes?: string[]
}

export type RouteMergePreviewItem = {
  id: string
  groupId: string
  sequence: number
  name: string
  merged: boolean
  sourceCount: number
  sourceLabel: string
  parentSegment?: string
  status?: MergeGroupStatus
  coverageLabel?: string
  evidenceCount?: number
  operationIds: number[]
  sourceNodes?: string[]
  childItems?: RouteMergePreviewChildItem[]
  manuallyEdited?: boolean
}

type UseRouteMergeResultWorkspaceOptions = {
  projectId: Ref<number | null>
  routeMergeNormalizedSegments: Ref<any[]>
  routeFullSetDisplayOrderedOperations: ComputedRef<OperationItem[]>
  routeFullSetOperations: ComputedRef<OperationItem[]>
  routeMergeGroupsSorted: ComputedRef<RouteMergeGroup[]>
  routeMergeCandidateGroups: ComputedRef<RouteMergeGroup[]>
  selectedMergeGroupId: Ref<string>
  selectedMergeGroup: ComputedRef<RouteMergeGroup | null>
  totalRouteSampleCount: ComputedRef<number>
  routeMergeEditUnlocked: ComputedRef<boolean>
  formatSampleCoverage: (hit: number, total: number) => string
}

const ROUTE_RESULT_DRAFT_VERSION = 'v9'

export function useRouteMergeResultWorkspace(options: UseRouteMergeResultWorkspaceOptions) {
  const routeMergePreviewDraftItems = ref<RouteMergePreviewItem[]>([])
  const selectedPreviewItemId = ref('')
  const previewRenameEditing = ref(false)
  const previewRenameDraft = ref('')
  const previewHighlightGroupIds = ref<string[]>([])
  const previewHighlightOperationIds = ref<number[]>([])

  let previewHighlightTimer: number | null = null

  function buildRoutePreviewStats(group: RouteMergeGroup) {
    const detailRows = Array.isArray(group.matched_detail_rows) ? group.matched_detail_rows : []
    const docKeys = new Set<string>()
    detailRows.forEach((row) => {
      const docId = Number(row.document_id || 0)
      if (docId > 0) {
        docKeys.add(`doc:${docId}`)
        return
      }
      const pdfName = String(row.pdf_name || '').trim()
      if (pdfName) docKeys.add(`pdf:${pdfName}`)
    })

    const matched = options.routeFullSetOperations.value
      .filter(item => group.operation_ids.includes(item.id))
      .sort((a, b) => a.sequence - b.sequence || a.id - b.id)
    const maxCoverage = matched.reduce((best, item) => {
      const current = Number(item.coverage_count || 0)
      return current > best.coverage ? { coverage: current, total: Number(item.sample_count || 0) } : best
    }, { coverage: 0, total: 0 })

    const hit = docKeys.size || maxCoverage.coverage
    const total = options.totalRouteSampleCount.value || maxCoverage.total
    return {
      coverageLabel: options.formatSampleCoverage(hit, total),
      evidenceCount: detailRows.length,
    }
  }

  function normalizeSourceNodes(sourceNodes: unknown, fallbackName = '') {
    const unique = new Set<string>()
    const normalized: string[] = []
    ;(Array.isArray(sourceNodes) ? sourceNodes : []).forEach((node) => {
      const text = formatRouteDisplayName(String(node || ''))
      if (!text || unique.has(text)) return
      unique.add(text)
      normalized.push(text)
    })
    const fallback = formatRouteDisplayName(String(fallbackName || ''))
    if (!normalized.length && fallback) normalized.push(fallback)
    return normalized
  }

  function createPreviewChildItem(item: Pick<RouteMergePreviewItem, 'id' | 'groupId' | 'name' | 'operationIds' | 'sourceNodes'>): RouteMergePreviewChildItem {
    return {
      id: item.id,
      groupId: item.groupId,
      name: formatRouteDisplayName(item.name),
      operationIds: [...item.operationIds],
      sourceNodes: normalizeSourceNodes(item.sourceNodes, formatRouteDisplayName(item.name)),
    }
  }

  function clonePreviewItem(item: RouteMergePreviewItem): RouteMergePreviewItem {
    return {
      ...item,
      name: formatRouteDisplayName(item.name),
      sourceLabel: formatRouteDisplayName(item.sourceLabel),
      parentSegment: formatRouteDisplayName(item.parentSegment || ''),
      operationIds: [...item.operationIds],
      sourceNodes: normalizeSourceNodes(item.sourceNodes, item.name),
      childItems: (item.childItems || []).map(child => ({
        ...child,
        name: formatRouteDisplayName(child.name),
        operationIds: [...child.operationIds],
        sourceNodes: normalizeSourceNodes(child.sourceNodes, child.name),
      })),
    }
  }

  function mergedPreviewSequence(parts: RouteMergePreviewItem[]) {
    const sequences = parts
      .map(item => Number(item.sequence || 0))
      .filter(sequence => sequence > 0)
    return sequences.length ? Math.min(...sequences) : 0
  }

  function reindexPreviewItems(items: RouteMergePreviewItem[]) {
    return items.map((item, index) => ({
      ...item,
      sequence: (index + 1) * 10,
    }))
  }

  const hasNormalizedRouteSegments = computed(() =>
    options.routeMergeNormalizedSegments.value.length > 0
  )

  function buildNormalizedPreviewItems() {
    return reindexPreviewItems(options.routeMergeNormalizedSegments.value.map((segment: any, index: number) => ({
      id: String(segment.id || `normalized-${index + 1}`),
      groupId: String(segment.id || `normalized-${index + 1}`),
      sequence: Number(segment.sequence || (index + 1) * 10),
      name: formatRouteDisplayName(String(segment.normalized_step_name || '未命名工序段')),
      merged: Array.isArray(segment.source_operation_ids) ? segment.source_operation_ids.length > 1 : false,
      sourceCount: Array.isArray(segment.source_operation_ids) ? segment.source_operation_ids.length : 0,
      sourceLabel: normalizeSourceNodes(
        Array.isArray(segment.source_operation_names) && segment.source_operation_names.length
          ? segment.source_operation_names
          : segment.source_nodes,
        formatRouteDisplayName(String(segment.normalized_step_name || '')),
      ).join(' / '),
      parentSegment: formatRouteDisplayName(String(segment.parent_segment || '')),
      status: (segment.review_status || 'merged') as MergeGroupStatus,
      coverageLabel: String(segment.coverage_label || ''),
      evidenceCount: Array.isArray(segment.matched_detail_rows) ? segment.matched_detail_rows.length : 0,
      operationIds: Array.isArray(segment.source_operation_ids) ? segment.source_operation_ids.map((id: number) => Number(id)).filter(Boolean) : [],
      sourceNodes: normalizeSourceNodes(segment.source_nodes, formatRouteDisplayName(String(segment.normalized_step_name || ''))),
      childItems: normalizeSourceNodes(
        Array.isArray(segment.source_operation_names) && segment.source_operation_names.length
          ? segment.source_operation_names
          : segment.source_nodes,
      ).map((name: string, childIdx: number) => ({
            id: `${String(segment.id || `normalized-${index + 1}`)}-child-${childIdx + 1}`,
            groupId: `${String(segment.id || `normalized-${index + 1}`)}-child-${childIdx + 1}`,
            name: formatRouteDisplayName(String(name || '未命名工序')),
            operationIds: Array.isArray(segment.source_operation_ids) && segment.source_operation_ids[childIdx]
              ? [Number(segment.source_operation_ids[childIdx])]
              : [],
            sourceNodes: [formatRouteDisplayName(String(name || '未命名工序'))],
          })),
      manuallyEdited: /^manual/.test(String(segment.source_type || '')),
    })))
  }

  function buildBasePreviewItems() {
    const displayOrderedOperations = options.routeFullSetDisplayOrderedOperations.value
    const previewItems: RouteMergePreviewItem[] = []

    displayOrderedOperations.forEach((operation) => {
      const sourceNodes = normalizeSourceNodes(operation.source_nodes, operation.name || '未命名工序')
      previewItems.push({
        id: `preview-op-${operation.id}`,
        groupId: `route-${operation.id}`,
        sequence: Number(operation.sequence || 0),
        name: formatRouteDisplayName(operation.name || '未命名工序'),
        merged: false,
        sourceCount: 1,
        sourceLabel: sourceNodes.join(' / '),
        status: 'kept',
        coverageLabel: options.formatSampleCoverage(Number(operation.coverage_count || 0), Number(operation.sample_count || 0)),
        evidenceCount: 0,
        operationIds: [operation.id],
        sourceNodes,
        childItems: [{
          id: `preview-op-${operation.id}`,
          groupId: `route-${operation.id}`,
          name: formatRouteDisplayName(operation.name || '未命名工序'),
          operationIds: [operation.id],
          sourceNodes,
        }],
      })
    })

    return reindexPreviewItems(previewItems)
  }

  // 第二步待确认阶段右侧先保持与左侧工序全集一致；
  // 中间卡片确认后，再通过草稿把对应节点合并或拆开。
  const routeMergePreviewItems = computed<RouteMergePreviewItem[]>(() =>
    !options.routeMergeEditUnlocked.value
      ? buildBasePreviewItems()
      : hasNormalizedRouteSegments.value
      ? buildNormalizedPreviewItems()
      : buildBasePreviewItems()
  )

  function routeResultDraftStorageKey() {
    if (!options.projectId.value) return ''
    return `processmind_route_result_draft_${ROUTE_RESULT_DRAFT_VERSION}_${options.projectId.value}`
  }

  function buildPreviewDraftFingerprint(items: RouteMergePreviewItem[]) {
    return items.map(item => `${item.groupId}:${item.operationIds.join(',')}`).join('|')
  }

  function saveRouteResultDraftToStorage() {
    const key = routeResultDraftStorageKey()
    if (!key) return
    localStorage.setItem(key, JSON.stringify({
      fingerprint: buildPreviewDraftFingerprint(routeMergePreviewItems.value),
      items: routeMergePreviewDraftItems.value,
    }))
  }

  function clearRouteResultDraftStorage() {
    const key = routeResultDraftStorageKey()
    if (!key) return
    localStorage.removeItem(key)
  }

  function restoreRouteResultDraftFromStorage() {
    const key = routeResultDraftStorageKey()
    if (!key) return false
    const raw = localStorage.getItem(key)
    if (!raw) return false
    try {
      const parsed = JSON.parse(raw)
      if (parsed?.fingerprint !== buildPreviewDraftFingerprint(routeMergePreviewItems.value)) {
        localStorage.removeItem(key)
        return false
      }
      if (!Array.isArray(parsed?.items)) return false
      const validItems = parsed.items.filter((item: RouteMergePreviewItem) =>
        item
        && typeof item.id === 'string'
        && typeof item.groupId === 'string'
        && typeof item.name === 'string'
        && Array.isArray(item.operationIds),
      )
      if (!validItems.length) {
        localStorage.removeItem(key)
        return false
      }
      routeMergePreviewDraftItems.value = validItems.map((item: RouteMergePreviewItem) => clonePreviewItem(item))
      selectedPreviewItemId.value = routeMergePreviewDraftItems.value[0]?.id || ''
      return true
    } catch (error) {
      console.error('恢复结果路线草稿失败', error)
      localStorage.removeItem(key)
      return false
    }
  }

  function clearLegacyRouteMergeStorage() {
    if (!options.projectId.value) return
    const prefixes = [
      `processmind_route_merge_v5_${options.projectId.value}`,
      `processmind_route_merge_v6_${options.projectId.value}`,
      `processmind_route_merge_v7_${options.projectId.value}`,
      `processmind_route_merge_v8_${options.projectId.value}`,
      `processmind_route_merge_v9_${options.projectId.value}`,
      `processmind_route_merge_v10_${options.projectId.value}`,
      `processmind_route_merge_v11_${options.projectId.value}`,
      `processmind_route_merge_v12_${options.projectId.value}`,
      `processmind_route_merge_v13_${options.projectId.value}`,
      `processmind_route_merge_v14_${options.projectId.value}`,
      `processmind_route_result_draft_v1_${options.projectId.value}`,
      `processmind_route_result_draft_v2_${options.projectId.value}`,
      `processmind_route_result_draft_v8_${options.projectId.value}`,
    ]
    for (let idx = localStorage.length - 1; idx >= 0; idx -= 1) {
      const key = localStorage.key(idx)
      if (!key) continue
      if (prefixes.some(prefix => key.startsWith(prefix))) {
        localStorage.removeItem(key)
      }
    }
  }

  function syncRouteMergePreviewDraft(preferredItemId = '') {
    const nextItems = routeMergePreviewItems.value.map(clonePreviewItem)
    const nextSelectedId = preferredItemId && nextItems.some(item => item.id === preferredItemId)
      ? preferredItemId
      : nextItems[0]?.id || ''
    if (restoreRouteResultDraftFromStorage()) return
    routeMergePreviewDraftItems.value = nextItems
    selectedPreviewItemId.value = nextSelectedId
  }

  function resetRouteMergePreviewDraft(preferredItemId = '') {
    const nextItems = routeMergePreviewItems.value.map(clonePreviewItem)
    const nextSelectedId = preferredItemId && nextItems.some(item => item.id === preferredItemId)
      ? preferredItemId
      : nextItems[0]?.id || ''
    routeMergePreviewDraftItems.value = nextItems
    selectedPreviewItemId.value = nextSelectedId
    saveRouteResultDraftToStorage()
  }

  function syncRouteMergePreviewDraftFromNormalizedRoute(preferredItemId = '') {
    const normalizedItems = buildNormalizedPreviewItems()
    if (!normalizedItems.length) {
      resetRouteMergePreviewDraft(preferredItemId)
      return
    }
    routeMergePreviewDraftItems.value = normalizedItems.map(clonePreviewItem)
    selectedPreviewItemId.value = preferredItemId && normalizedItems.some(item => item.id === preferredItemId)
      ? preferredItemId
      : normalizedItems[0]?.id || ''
    saveRouteResultDraftToStorage()
  }

  const routeMergeResultItems = computed<RouteMergePreviewItem[]>(() =>
    reindexPreviewItems(routeMergePreviewDraftItems.value.length ? routeMergePreviewDraftItems.value : routeMergePreviewItems.value)
  )

  const selectedPreviewItem = computed<RouteMergePreviewItem | null>(() =>
    routeMergeResultItems.value.find(item => item.id === selectedPreviewItemId.value)
    || routeMergeResultItems.value.find(item => item.groupId === options.selectedMergeGroupId.value)
    || routeMergeResultItems.value[0]
    || null
  )
  const selectedPreviewItemIndex = computed(() =>
    selectedPreviewItem.value ? routeMergeResultItems.value.findIndex(item => item.id === selectedPreviewItem.value?.id) : -1
  )
  const canMovePreviewItemUp = computed(() => selectedPreviewItemIndex.value > 0)
  const canMovePreviewItemDown = computed(() =>
    selectedPreviewItemIndex.value >= 0 && selectedPreviewItemIndex.value < routeMergeResultItems.value.length - 1
  )
  const canMergePreviewItemPrev = computed(() => canMovePreviewItemUp.value)
  const canMergePreviewItemNext = computed(() => canMovePreviewItemDown.value)
  const canSplitSelectedPreviewItem = computed(() =>
    Boolean(selectedPreviewItem.value && selectedPreviewItem.value.childItems && selectedPreviewItem.value.childItems.length > 1)
  )
  const canInsertPreviewItem = computed(() => Boolean(selectedPreviewItem.value))
  const canRemoveSelectedPreviewItem = computed(() => routeMergeResultItems.value.length > 1)
  const selectedRouteOperationIds = computed(() =>
    selectedPreviewItem.value?.operationIds
    || options.selectedMergeGroup.value?.operation_ids
    || previewHighlightOperationIds.value
  )

  function clearPreviewHighlight() {
    previewHighlightGroupIds.value = []
    previewHighlightOperationIds.value = []
    if (previewHighlightTimer !== null) {
      window.clearTimeout(previewHighlightTimer)
      previewHighlightTimer = null
    }
  }

  function triggerPreviewHighlight(payload: { groupIds?: string[], operationIds?: number[] }) {
    clearPreviewHighlight()
    previewHighlightGroupIds.value = payload.groupIds || []
    previewHighlightOperationIds.value = payload.operationIds || []
    previewHighlightTimer = window.setTimeout(() => {
      previewHighlightGroupIds.value = []
      previewHighlightOperationIds.value = []
      previewHighlightTimer = null
    }, 1600)
  }

  function isPreviewItemActive(item: RouteMergePreviewItem) {
    if (selectedPreviewItem.value?.id === item.id) return true
    if (options.selectedMergeGroup.value?.id === item.groupId) return true
    if (previewHighlightGroupIds.value.includes(item.groupId)) return true
    return item.operationIds.some(id => previewHighlightOperationIds.value.includes(id))
  }

  function updateRouteMergePreviewDraft(mutator: (items: RouteMergePreviewItem[]) => { nextSelectedId?: string, highlightOperationIds?: number[] } | void) {
    const working = routeMergeResultItems.value.map(clonePreviewItem)
    const result = mutator(working) || {}
    routeMergePreviewDraftItems.value = reindexPreviewItems(working)
    saveRouteResultDraftToStorage()
    selectedPreviewItemId.value = result.nextSelectedId || routeMergePreviewDraftItems.value[0]?.id || ''
    if (result.highlightOperationIds?.length) {
      triggerPreviewHighlight({ operationIds: result.highlightOperationIds })
    }
  }

  function movePreviewItemUp(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index <= 0) return
      const previousItem = items[index - 1]
      const currentItem = items[index]
      if (!previousItem || !currentItem) return
      ;[items[index - 1], items[index]] = [currentItem, previousItem]
      return { nextSelectedId: itemId, highlightOperationIds: currentItem.operationIds }
    })
  }

  function movePreviewItemDown(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index < 0 || index >= items.length - 1) return
      const currentItem = items[index]
      const nextItem = items[index + 1]
      if (!currentItem || !nextItem) return
      ;[items[index], items[index + 1]] = [nextItem, currentItem]
      return { nextSelectedId: itemId, highlightOperationIds: currentItem.operationIds }
    })
  }

  function reorderPreviewItems(payload: { draggedId: string, targetId: string }) {
    if (!options.routeMergeEditUnlocked.value) return
    updateRouteMergePreviewDraft((items) => {
      const draggedIndex = items.findIndex(item => item.id === payload.draggedId)
      const targetIndex = items.findIndex(item => item.id === payload.targetId)
      if (draggedIndex < 0 || targetIndex < 0 || draggedIndex === targetIndex) return
      const [draggedItem] = items.splice(draggedIndex, 1)
      if (!draggedItem) return
      const nextTargetIndex = items.findIndex(item => item.id === payload.targetId)
      items.splice(nextTargetIndex < 0 ? items.length : nextTargetIndex, 0, draggedItem)
      return { nextSelectedId: draggedItem.id, highlightOperationIds: draggedItem.operationIds }
    })
  }

  function buildMergedPreviewItem(parts: RouteMergePreviewItem[], manuallyEdited = true) {
    const operationIds = Array.from(new Set(parts.flatMap(item => item.operationIds)))
    const childItems = parts.flatMap(item => (item.childItems?.length ? item.childItems : [createPreviewChildItem(item)]))
    const uniqueNames = Array.from(new Set(parts.map(item => item.name).filter(Boolean)))
    const sourceNodes = normalizeSourceNodes(parts.flatMap(item => item.sourceNodes || []), uniqueNames.join(' / '))
    const sourceDisplayNames = normalizeSourceNodes(
      childItems.length ? childItems.map(child => child.name) : uniqueNames,
      uniqueNames.join(' / '),
    )
    return {
      id: `preview-manual-${operationIds.join('-')}-${Date.now()}`,
      groupId: `manual-${operationIds.join('-')}`,
      sequence: mergedPreviewSequence(parts),
      name: uniqueNames.join(' / ') || '未命名工序段',
      merged: true,
      sourceCount: operationIds.length,
      sourceLabel: sourceDisplayNames.join(' / '),
      status: 'merged' as MergeGroupStatus,
      operationIds,
      sourceNodes,
      childItems,
      manuallyEdited,
    } as RouteMergePreviewItem
  }

  function mergePreviewItemToPrevious(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index <= 0) return
      const previousItem = items[index - 1]
      const currentItem = items[index]
      if (!previousItem || !currentItem) return
      const merged = buildMergedPreviewItem([previousItem, currentItem])
      items.splice(index - 1, 2, merged)
      options.selectedMergeGroupId.value = ''
      return { nextSelectedId: merged.id, highlightOperationIds: merged.operationIds }
    })
  }

  function mergePreviewItemToNext(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index < 0 || index >= items.length - 1) return
      const currentItem = items[index]
      const nextItem = items[index + 1]
      if (!currentItem || !nextItem) return
      const merged = buildMergedPreviewItem([currentItem, nextItem])
      items.splice(index, 2, merged)
      options.selectedMergeGroupId.value = ''
      return { nextSelectedId: merged.id, highlightOperationIds: merged.operationIds }
    })
  }

  function splitPreviewItem(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index < 0) return
      const current = items[index]
      if (!current || !current.childItems || current.childItems.length <= 1) return
      const splitItems = current.childItems.map((child) => ({
        id: child.id,
        groupId: child.groupId,
        sequence: 0,
        name: child.name,
        merged: false,
        sourceCount: child.operationIds.length,
        sourceLabel: normalizeSourceNodes(child.sourceNodes, child.name).join(' / '),
        status: 'kept' as MergeGroupStatus,
        operationIds: [...child.operationIds],
        sourceNodes: normalizeSourceNodes(child.sourceNodes, child.name),
        childItems: [{
          ...child,
          operationIds: [...child.operationIds],
          sourceNodes: normalizeSourceNodes(child.sourceNodes, child.name),
        }],
        manuallyEdited: true,
      }))
      items.splice(index, 1, ...splitItems)
      options.selectedMergeGroupId.value = ''
      return { nextSelectedId: splitItems[0]?.id, highlightOperationIds: current.operationIds }
    })
  }

  function insertPreviewItemAfter(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      const index = items.findIndex(item => item.id === itemId)
      if (index < 0) return
      const base = items[index]
      const timestamp = Date.now()
      const inserted: RouteMergePreviewItem = {
        id: `preview-manual-insert-${timestamp}`,
        groupId: `manual-insert-${timestamp}`,
        sequence: 0,
        name: '新增工序',
        merged: false,
        sourceCount: 0,
        sourceLabel: '',
        status: 'kept',
        operationIds: [],
        sourceNodes: [],
        childItems: [],
        parentSegment: base?.parentSegment || '',
        manuallyEdited: true,
      }
      items.splice(index + 1, 0, inserted)
      options.selectedMergeGroupId.value = ''
      return { nextSelectedId: inserted.id }
    })
  }

  function removePreviewItem(itemId: string) {
    updateRouteMergePreviewDraft((items) => {
      if (items.length <= 1) return
      const index = items.findIndex(item => item.id === itemId)
      if (index < 0) return
      const [removed] = items.splice(index, 1)
      if (!removed) return
      options.selectedMergeGroupId.value = ''
      const nextSelected = items[index] || items[index - 1] || items[0]
      return {
        nextSelectedId: nextSelected?.id,
        highlightOperationIds: removed.operationIds,
      }
    })
  }

  function renamePreviewItem(payload: { itemId: string, name: string }) {
    updateRouteMergePreviewDraft((items) => {
      const target = items.find(item => item.id === payload.itemId)
      if (!target) return
      target.name = payload.name
      target.name = formatRouteDisplayName(target.name)
      target.manuallyEdited = true
      return { nextSelectedId: payload.itemId, highlightOperationIds: target.operationIds }
    })
  }

  function startPreviewRename() {
    if (!selectedPreviewItem.value) return
    previewRenameEditing.value = true
    previewRenameDraft.value = selectedPreviewItem.value.name
  }

  function cancelPreviewRename() {
    previewRenameEditing.value = false
    previewRenameDraft.value = ''
  }

  function submitPreviewRename() {
    if (!selectedPreviewItem.value || !previewRenameDraft.value) return
    renamePreviewItem({ itemId: selectedPreviewItem.value.id, name: previewRenameDraft.value })
    cancelPreviewRename()
  }

  return {
    buildRoutePreviewStats,
    routeMergePreviewDraftItems,
    selectedPreviewItemId,
    previewRenameEditing,
    previewRenameDraft,
    previewHighlightGroupIds,
    previewHighlightOperationIds,
    routeMergePreviewItems,
    routeMergeResultItems,
    selectedPreviewItem,
    selectedPreviewItemIndex,
    canMovePreviewItemUp,
    canMovePreviewItemDown,
    canMergePreviewItemPrev,
    canMergePreviewItemNext,
    canSplitSelectedPreviewItem,
    canInsertPreviewItem,
    canRemoveSelectedPreviewItem,
    selectedRouteOperationIds,
    clearLegacyRouteMergeStorage,
    clearRouteResultDraftStorage,
    saveRouteResultDraftToStorage,
    restoreRouteResultDraftFromStorage,
    syncRouteMergePreviewDraft,
    resetRouteMergePreviewDraft,
    syncRouteMergePreviewDraftFromNormalizedRoute,
    clearPreviewHighlight,
    triggerPreviewHighlight,
    isPreviewItemActive,
    movePreviewItemUp,
    movePreviewItemDown,
    reorderPreviewItems,
    mergePreviewItemToPrevious,
    mergePreviewItemToNext,
    splitPreviewItem,
    insertPreviewItemAfter,
    removePreviewItem,
    renamePreviewItem,
    startPreviewRename,
    cancelPreviewRename,
    submitPreviewRename,
  }
}
