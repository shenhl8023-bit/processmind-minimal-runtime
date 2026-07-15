<template>
  <div class="extract-view">
    <ExtractPageHeader
      v-if="status !== 'done'"
      title="典型工艺路线规则提炼"
      description="系统先从工艺规程中抽取工艺路线全集，再由你在第二步完成路线归并，归并完成后再进入规则因素分析。"
      badge-text="✨ 规则提炼模式"
    />

    <ExtractStatusCard
      v-if="status === 'idle'"
      variant="idle"
      :message="extractIdleHint"
      @action="() => startExtraction()"
    />

    <RouteProgressCard
      v-if="status === 'loading'"
      :title="extractTaskStageTitle"
      :message="extractTaskMessage || extractLoadingHint"
      :steps="routeProgressSteps"
      :progress="extractTaskProgress"
    />

    <ExtractStatusCard
      v-if="status === 'error'"
      variant="error"
      :message="errorMsg"
      :harness="extractHarness"
      @action="resetRouteRulesError"
    />

    <div v-if="status === 'done'" class="results-area">
      <RouteProgressCard
        v-if="routeWorkspaceLoading"
        title="AI 正在整理第二步结果..."
        message="工序全集已就绪，正在生成归并候选与标准化母路线。"
        :steps="routeProgressSteps"
        indeterminate
      />
      <template v-else>
      <ExtractRouteShellHeader
        :edit-unlocked="routeMergeEditUnlocked"
        :original-count="routeFullSetOperations.length"
        :result-count="routeMergeResultItems.length"
        :pending-count="routeMergePendingCount"
        :can-enter="canEnterRouteFactorAnalysis"
        :status-label="routeMergeStatusLabel"
        :notice="visibleRouteMergeNotice"
        @rerun="() => startExtraction(true)"
      />

      <div class="route-mobile-tabs" role="tablist" aria-label="路线归并面板">
        <button
          type="button"
          role="tab"
          :aria-selected="mobileRoutePane === 'source'"
          :class="{ active: mobileRoutePane === 'source' }"
          @click="mobileRoutePane = 'source'"
        >
          原始工序
        </button>
        <button
          v-if="!routeMergeEditUnlocked"
          type="button"
          role="tab"
          :aria-selected="mobileRoutePane === 'queue'"
          :class="{ active: mobileRoutePane === 'queue' }"
          @click="mobileRoutePane = 'queue'"
        >
          待处理
          <span v-if="routeMergePendingCount" class="route-mobile-tab-count">{{ routeMergePendingCount }}</span>
        </button>
        <button
          type="button"
          role="tab"
          :aria-selected="mobileRoutePane === 'result'"
          :class="{ active: mobileRoutePane === 'result' }"
          @click="mobileRoutePane = 'result'"
        >
          标准路线
        </button>
      </div>

      <div
        class="route-merge-layout"
        :class="[
          { 'route-merge-layout-manual': routeMergeEditUnlocked },
          `route-mobile-pane-${mobileRoutePane}`,
        ]"
      >
        <div class="card route-pane route-pane-left">
          <SourceRoutePanel
            :sections="routeFullSetSections"
            :active-group-id="selectedMergeGroup?.id || ''"
            :active-operation-ids="selectedRouteOperationIds"
            :operation-to-group-id="mergeGroupIdForOperation"
            :operation-display-name="routeOperationDisplayName"
            :operation-duplicate-label="routeOperationDuplicateLabel"
            :format-coverage="formatSampleCoverage"
            @select-operation="selectMergeGroupByOperation"
          />
        </div>

        <div v-if="!routeMergeEditUnlocked" class="card route-pane route-pane-center">
          <MergeQueuePanel
            :groups="routeMergeActionableGroupsSorted"
            :selected-group-id="selectedMergeGroup?.id || ''"
            :pending-count="routeMergePendingCount"
            :busy="routeMergeBatchSubmitting"
            :resolved-count="routeMergeResolvedCount"
            :preview-count="routeMergeResultItems.length"
            :candidate-count="routeMergeCandidateGroups.length"
            :candidate-label="mergeGroupCandidateLabel"
            :source-label="mergeGroupSourceLabel"
            :suggestion-label="mergeSuggestionForGroup"
            :equipment-label="equipmentSupportLabel"
            :tag-class="mergeGroupTagClass"
            :status-label="mergeGroupStatusLabel"
            :rename-editing-group-id="routeMergeRenameGroupId"
            :rename-draft="routeMergeRenameDraft"
            @select="selectMergeGroup"
            @confirm="confirmMergeGroup"
            @reject="rejectMergeGroup"
            @bulk-confirm="confirmAllMergeGroups"
            @bulk-reject="rejectAllMergeGroups"
            @start-rename="startRouteMergeRename"
            @submit-rename="submitRouteMergeRename"
            @cancel-rename="cancelRouteMergeRename"
            @update:rename-draft="routeMergeRenameDraft = $event"
          />
        </div>

        <div class="card route-pane route-pane-right" :class="{ 'route-pane-right-manual': routeMergeEditUnlocked }">
          <NormalizedRoutePanel
            :items="routeMergeResultItems"
            :is-active="isPreviewItemActive"
            :step-groups-for-item="previewItemStepGroups"
            :editable="routeMergeEditUnlocked"
            :selected-item-id="selectedPreviewItem?.id || ''"
            :can-move-up="canMovePreviewItemUp"
            :can-move-down="canMovePreviewItemDown"
            :can-merge-prev="canMergePreviewItemPrev"
            :can-merge-next="canMergePreviewItemNext"
            :can-split="canSplitSelectedPreviewItem"
            :can-insert="canInsertPreviewItem"
            :can-remove="canRemoveSelectedPreviewItem"
            :rename-editing="previewRenameEditing"
            :rename-draft="previewRenameDraft"
            @select="selectPreviewItem"
            @reorder="reorderPreviewItems"
            @move-up="movePreviewItemUp"
            @move-down="movePreviewItemDown"
            @merge-prev="mergePreviewItemToPrevious"
            @merge-next="mergePreviewItemToNext"
            @insert-after="insertPreviewItemAfter"
            @remove="removePreviewItem"
            @split="splitPreviewItem"
            @start-rename="startPreviewRename"
            @submit-rename="submitPreviewRename"
            @cancel-rename="cancelPreviewRename"
            @update:rename-draft="previewRenameDraft = $event"
          />
          <div v-if="routeMergeEditUnlocked && !selectedPreviewItem" class="route-result-editor route-result-editor-ready">
            第三步已开启，点击右侧任一结果工序卡片后，可继续调整顺序、拆开、合并与改名。
          </div>

        </div>
      </div>

      <ExtractRouteActionFooter
        :pending-count="routeMergePendingCount"
        :can-enter="canEnterRouteFactorAnalysis"
        @next="openRouteFactorAnalysis"
      />
      </template>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onBeforeUnmount, onActivated, onDeactivated, defineAsyncComponent, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import ExtractPageHeader from '@/components/extract/ExtractPageHeader.vue'
import ExtractRouteActionFooter from '@/components/extract/ExtractRouteActionFooter.vue'
import ExtractRouteShellHeader from '@/components/extract/ExtractRouteShellHeader.vue'
import ExtractStatusCard from '@/components/extract/ExtractStatusCard.vue'
import RouteProgressCard from '@/components/extract/RouteProgressCard.vue'
import {
  useRouteMergeResultWorkspace,
  type RouteMergeGroup,
} from '@/composables/useRouteMergeResultWorkspace'
import { useRouteMergeWorkspace } from '@/composables/useRouteMergeWorkspace'
import { useRouteRulesFlow } from '@/composables/useRouteRulesFlow'
import { useRouteMergeInteractionActions } from '@/composables/useRouteMergeInteractionActions'
import { useRouteMergeDisplayHelpers } from '@/composables/useRouteMergeDisplayHelpers'
import {
  buildRouteFullSetSectionsFromTree,
  buildRouteOperationNameCounts,
  filterRouteMergeNotice,
  buildRouteMergeGroupsFromSuggestions as buildRouteMergeGroupsFromSuggestionItems,
  findPreferredMergeGroupId,
  formatSampleCoverage,
  getNextActionableGroupIdFromGroups,
  isMergeGroupActionable,
  isNoiseOperationName,
  routeOperationDisplayName,
  routeOperationDuplicateLabel as getRouteOperationDuplicateLabel,
} from '@/composables/extractViewHelpers'
import {
  resolveCurrentProjectId,
  resolveAvailableProjectId,
} from '@/composables/useCurrentProject'
import {
  listProjects,
  type OperationItem,
  type MergeSuggestion,
} from '@/api'
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'

const MergeQueuePanel = defineAsyncComponent(() => import('@/components/extract/MergeQueuePanel.vue'))
const NormalizedRoutePanel = defineAsyncComponent(() => import('@/components/extract/NormalizedRoutePanel.vue'))
const SourceRoutePanel = defineAsyncComponent(() => import('@/components/extract/SourceRoutePanel.vue'))

defineOptions({
  name: 'ExtractView',
})

type RouteFullSetSection = {
  key: string
  title: string
  kicker: string
  description: string
  order: number
  operations: OperationItem[]
}

const route = useRoute()
const router = useRouter()
const routes = ref<OperationItem[]>([])
const projectId = ref<number | null>(null)
const routeMergeGroups = ref<RouteMergeGroup[]>([])
const routeMergeSuggestions = ref<MergeSuggestion[]>([])
const routeMergeNormalizedSegments = ref<any[]>([])
const selectedMergeGroupId = ref('')
const mobileRoutePane = ref<'source' | 'queue' | 'result'>('source')
const routeFullSetOperations = computed(() =>
  [...visibleRoutes.value].sort((a, b) => a.sequence - b.sequence || a.id - b.id)
)
const routeFullSetSections = computed<RouteFullSetSection[]>(() => {
  return buildRouteFullSetSectionsFromTree(routeFullSetOperations.value) as RouteFullSetSection[]
})
const routeFullSetLeftDisplayOperations = computed(() =>
  routeFullSetSections.value.flatMap(section => section.operations)
)
const routeOperationNameCounts = computed(() => {
  return buildRouteOperationNameCounts(routeFullSetLeftDisplayOperations.value)
})
const routeFullSetDisplayOrderedOperations = computed(() =>
  [...routeFullSetOperations.value]
)
function routeOperationDuplicateLabel(operation: Record<string, any>) {
  return getRouteOperationDuplicateLabel(operation, routeOperationNameCounts.value)
}
const routeMergeGroupsSorted = computed(() =>
  [...routeMergeGroups.value].sort((a, b) => a.sequence - b.sequence || a.id.localeCompare(b.id))
)
const routeMergeCandidateGroups = computed(() =>
  routeMergeGroupsSorted.value.filter(group =>
    group.operation_ids.length > 1 && group.suggestion_type !== 'keep_separate'
  )
)
const routeMergeActionableGroupsSorted = computed(() =>
  routeMergeCandidateGroups.value.filter(group => isMergeGroupActionable(group))
)
const selectedMergeGroup = computed(() => {
  const byId = routeMergeCandidateGroups.value.find(group => group.id === selectedMergeGroupId.value)
  if (byId) return byId
  // 微调模式下，用户明确点击了 preview item，selectedMergeGroupId 可能被清空，
  // 此时不应 fallback，否则左侧会始终高亮第一个候选归并组。
  if (routeMergeEditUnlocked.value && !selectedMergeGroupId.value) return null
  return routeMergeActionableGroupsSorted.value[0]
    || routeMergeCandidateGroups.value[0]
    || null
})
const routeMergePendingCount = computed(() => routeMergeActionableGroupsSorted.value.length)
const routeMergeResolvedCount = computed(() =>
  routeMergeCandidateGroups.value.filter(group => group.status === 'merged' || group.status === 'kept').length
)
const routeRulesAutoRefreshRunning = ref(false)
const routeRulesAutoRefreshAt = ref(0)
const extractViewActive = ref(true)
const lastInitializedDataRevision = ref(-1)
const canEnterRouteFactorAnalysis = computed(() =>
  routeMergeGroupsSorted.value.length > 0
  && routeMergePendingCount.value === 0
)
const routeMergeEditUnlocked = computed(() => canEnterRouteFactorAnalysis.value)

watch(routeMergeEditUnlocked, (unlocked) => {
  if (unlocked && mobileRoutePane.value === 'queue') {
    mobileRoutePane.value = 'result'
  }
})
const routeMergeStatusLabel = computed(() => {
  if (!routeMergeCandidateGroups.value.length) return '无需归并'
  if (routeMergePendingCount.value > 0) return '待处理'
  return '可进入规则分析'
})
const visibleRouteMergeNotice = computed(() => filterRouteMergeNotice(routeMergeNotice.value))
const selectedMergeSuggestionItem = computed(() =>
  routeMergeSuggestions.value.find(item => item.target_group_id === selectedMergeGroup.value?.id) || null
)
const totalRouteSampleCount = computed(() =>
  routeFullSetOperations.value.reduce((best, item) => {
    const total = Number(item.sample_count || 0)
    return total > best ? total : best
  }, 0)
)

const {
  buildRoutePreviewStats,
  routeMergePreviewDraftItems,
  selectedPreviewItemId,
  previewRenameEditing,
  previewRenameDraft,
  routeMergePreviewItems,
  routeMergeResultItems,
  selectedPreviewItem,
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
  syncRouteMergePreviewDraft,
  resetRouteMergePreviewDraft,
  syncRouteMergePreviewDraftFromNormalizedRoute,
  clearPreviewHighlight,
  triggerPreviewHighlight,
  isPreviewItemActive,
  movePreviewItemUp: movePreviewItemUpBase,
  movePreviewItemDown: movePreviewItemDownBase,
  reorderPreviewItems: reorderPreviewItemsBase,
  mergePreviewItemToPrevious: mergePreviewItemToPreviousBase,
  mergePreviewItemToNext: mergePreviewItemToNextBase,
  splitPreviewItem: splitPreviewItemBase,
  insertPreviewItemAfter: insertPreviewItemAfterBase,
  removePreviewItem: removePreviewItemBase,
  startPreviewRename: startPreviewRenameBase,
  cancelPreviewRename: cancelPreviewRenameBase,
  submitPreviewRename: submitPreviewRenameBase,
} = useRouteMergeResultWorkspace({
  projectId,
  routeMergeNormalizedSegments,
  routeFullSetDisplayOrderedOperations,
  routeFullSetOperations,
  routeMergeGroupsSorted,
  routeMergeCandidateGroups,
  selectedMergeGroupId,
  selectedMergeGroup,
  totalRouteSampleCount,
  routeMergeEditUnlocked,
  formatSampleCoverage,
})

const {
  routeMergeNotice,
  routeWorkspaceLoading,
  routeMergeBatchSubmitting,
  loadRouteMergeWorkspaceFromBackend: loadRouteMergeWorkspaceFromBackendBase,
  refreshRouteMergeWorkspace: refreshRouteMergeWorkspaceBase,
  applyMergeSuggestionAction: applyMergeSuggestionActionBase,
  confirmAllMergeGroups: confirmAllMergeGroupsBase,
  rejectAllMergeGroups: rejectAllMergeGroupsBase,
  saveRouteMergeWorkspace: saveRouteMergeWorkspaceBase,
} = useRouteMergeWorkspace({
  projectId,
  routes,
  routeMergeGroups,
  routeMergeSuggestions,
  routeMergeNormalizedSegments,
  selectedMergeGroupId,
  selectedPreviewItemId,
  routeMergeActionableGroupsSorted,
  routeMergeCandidateGroups,
  selectedMergeGroup,
  selectedMergeSuggestionItem,
  routeMergeResultItems,
  routeMergePreviewItems,
  routeMergeEditUnlocked,
  buildRouteMergeGroupsFromSuggestions,
  buildRoutePreviewStats,
  findPreferredMergeGroupId,
  isMergeGroupActionable,
  getNextActionableGroupId,
  mergeGroupCandidateLabel: (group: RouteMergeGroup) => mergeGroupCandidateLabel(group),
  syncRouteMergePreviewDraft,
  clearLegacyRouteMergeStorage,
  clearRouteResultDraftStorage,
  saveRouteResultDraftToStorage,
  triggerPreviewHighlight,
  focusMergeGroup: async (groupId: string) => {
    await focusMergeGroup(groupId)
  },
  cancelRouteMergeRename: () => {
    cancelRouteMergeRename()
  },
  cancelPreviewRename: () => {
    cancelPreviewRename()
  },
})

const {
  status,
  errorMsg,
  extractHarness,
  extractTaskProgress,
  extractTaskMessage,
  extractIdleHint,
  extractLoadingHint,
  extractTaskStageTitle,
  routeProgressSteps,
  resetRouteRulesError,
  stopExtractTaskPolling,
  loadRouteRulesResults,
  pollExtractionTask,
  startExtraction,
} = useRouteRulesFlow({
  projectId,
  routeWorkspaceLoading,
  routes,
  routeMergeGroups,
  routeMergeSuggestions,
  routeMergeNormalizedSegments,
  selectedMergeGroupId,
  routeMergeNotice,
  loadRouteMergeWorkspaceFromBackend: loadRouteMergeWorkspaceFromBackendBase,
  clearRouteResultDraftStorage,
  clearPreviewHighlight,
})

const {
  mergeSuggestionForGroup,
  equipmentSupportLabel,
  mergeGroupCandidateLabel,
  mergeGroupSourceLabel,
  mergeGroupIdForOperation,
  mergeGroupStatusLabel,
  mergeGroupTagClass,
  previewItemStepGroups,
} = useRouteMergeDisplayHelpers({
  routeFullSetOperations,
  routeFullSetDisplayOperations: routeFullSetLeftDisplayOperations,
  routeMergeCandidateGroups,
})

const {
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
} = useRouteMergeInteractionActions({
  projectId,
  routeMergeGroups,
  routeMergeSuggestions,
  routeMergeCandidateGroups,
  routeMergeResultItems,
  selectedMergeGroupId,
  selectedPreviewItemId,
  routeMergeBatchSubmitting,
  routeMergeNotice,
  applyMergeSuggestionAction: applyMergeSuggestionActionBase,
  refreshRouteMergeWorkspace: refreshRouteMergeWorkspaceBase,
  triggerPreviewHighlight,
  mergeGroupCandidateLabel,
  setError: (message) => {
    errorMsg.value = message
    routeMergeNotice.value = message
  },
  cancelPreviewRenameBase,
  startPreviewRenameBase,
  submitPreviewRenameBase,
  movePreviewItemUpBase,
  movePreviewItemDownBase,
  reorderPreviewItemsBase,
  mergePreviewItemToPreviousBase,
  mergePreviewItemToNextBase,
  splitPreviewItemBase,
  insertPreviewItemAfterBase,
  removePreviewItemBase,
})

const visibleRoutes = computed(() => routes.value.filter(route => !isNoiseOperationName(route.name)))
function getNextActionableGroupId(currentId: string) {
  return getNextActionableGroupIdFromGroups(routeMergeActionableGroupsSorted.value, currentId)
}

function buildRouteMergeGroupsFromSuggestions(suggestions: MergeSuggestion[]) {
  return buildRouteMergeGroupsFromSuggestionItems(
    suggestions,
    group => buildRoutePreviewStats(group).coverageLabel,
  )
}

async function refreshRouteRulesSnapshotOnResume(force = false) {
  if (!extractViewActive.value) return
  if (!projectId.value) return
  if (status.value === 'loading') return
  if (routeRulesAutoRefreshRunning.value) return
  if (!force && Date.now() - routeRulesAutoRefreshAt.value < 3000) return

  routeRulesAutoRefreshRunning.value = true
  try {
    await loadRouteRulesResults(true)
    const resumeRouteMerge = String(route.query.resume || '').trim() === 'route_merge' || String(route.query.from || '').trim() === 'analysis'
    if (resumeRouteMerge && routeMergePendingCount.value === 0) {
      syncRouteMergePreviewDraftFromNormalizedRoute()
    } else if (resumeRouteMerge) {
      resetRouteMergePreviewDraft()
    }
    routeRulesAutoRefreshAt.value = Date.now()
  } catch (e) {
    console.error('回到页面后刷新工艺路线全集失败', e)
  } finally {
    routeRulesAutoRefreshRunning.value = false
  }
}

function handleWindowFocusRefresh() {
  if (!extractViewActive.value) return
  void refreshRouteRulesSnapshotOnResume()
}

function handleVisibilityRefresh() {
  if (!extractViewActive.value) return
  if (document.visibilityState !== 'visible') return
  void refreshRouteRulesSnapshotOnResume()
}

async function confirmAllMergeGroups() {
  await confirmAllMergeGroupsBase((message) => {
    errorMsg.value = message
    routeMergeNotice.value = message
  })
}

async function rejectAllMergeGroups() {
  await rejectAllMergeGroupsBase((message) => {
    errorMsg.value = message
    routeMergeNotice.value = message
  })
}

async function openRouteFactorAnalysis() {
  if (!canEnterRouteFactorAnalysis.value || !projectId.value) return
  const saved = await saveRouteMergeWorkspaceBase((message) => {
    errorMsg.value = message
    routeMergeNotice.value = message
  })
  if (!saved) return
  await router.push({
    path: '/analysis',
    query: { project_id: String(projectId.value) },
  })
}

function handleMergeKeydown(e: KeyboardEvent) {
  if (!extractViewActive.value) return
  const target = e.target as HTMLElement
  if (target && ['INPUT', 'TEXTAREA'].includes(target.tagName)) return

  if (routeMergeEditUnlocked.value) {
    if (!selectedPreviewItemId.value) return
    const previewItems = routeMergePreviewDraftItems.value
    const idx = previewItems.findIndex(i => i.id === selectedPreviewItemId.value)
    if (idx === -1) return
    if (e.key === 'ArrowDown') {
      e.preventDefault()
      const nextItem = previewItems[idx + 1]
      if (nextItem) selectPreviewItem(nextItem.id)
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      const prevItem = previewItems[idx - 1]
      if (prevItem) selectPreviewItem(prevItem.id)
    }
    return
  }

  if (!selectedMergeGroupId.value) return
  const groups = routeMergeActionableGroupsSorted.value
  const currentIndex = groups.findIndex(g => g.id === selectedMergeGroupId.value)
  if (currentIndex === -1) return

  if (e.key === 'Enter') {
    e.preventDefault()
    if (routeMergeRenameGroupId.value) return
    void confirmMergeGroup(selectedMergeGroupId.value)
  } else if (e.key === 'Backspace') {
    e.preventDefault()
    if (routeMergeRenameGroupId.value) return
    void rejectMergeGroup(selectedMergeGroupId.value)
  } else if (e.key === 'ArrowDown') {
    e.preventDefault()
    const nextItem = groups[currentIndex + 1]
    if (nextItem) {
      selectedMergeGroupId.value = nextItem.id
      void focusMergeGroup(nextItem.id)
    }
  } else if (e.key === 'ArrowUp') {
    e.preventDefault()
    const prevItem = groups[currentIndex - 1]
    if (prevItem) {
      selectedMergeGroupId.value = prevItem.id
      void focusMergeGroup(prevItem.id)
    }
  }
}

async function initializeExtractView() {
  const routeProjectId = String(route.query.project_id || '')
  const resumeRouteMerge = String(route.query.resume || '').trim() === 'route_merge' || String(route.query.from || '').trim() === 'analysis'
  const preferredProjectId = resolveCurrentProjectId(routeProjectId)
  const currentDataRevision = getWorkflowDataRevision()
  const alreadyInitialized = Boolean(
    preferredProjectId
    && projectId.value === Number(preferredProjectId)
    && lastInitializedDataRevision.value === currentDataRevision
    && (status.value === 'idle' || status.value === 'loading' || status.value === 'done')
  )

  if (!resumeRouteMerge && alreadyInitialized) {
    return
  }

  try {
    const projects = await listProjects()
    const savedId = resolveAvailableProjectId(routeProjectId, projects)
    if (!savedId) {
      errorMsg.value = '请先在第一步创建或选择任务'
      status.value = 'error'
      return
    }
    projectId.value = Number(savedId)
    if (routeProjectId !== savedId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: savedId },
      })
    }
    const current = projects.find((item) => item.id === projectId.value)
    if (!current) {
      projectId.value = null
      errorMsg.value = '当前任务已不存在，请回到第一步重新创建任务。'
      status.value = 'error'
      return
    }
    if (resumeRouteMerge) {
      await loadRouteRulesResults()
      lastInitializedDataRevision.value = getWorkflowDataRevision()
      if (routeMergePendingCount.value === 0) {
        syncRouteMergePreviewDraftFromNormalizedRoute()
      } else {
        resetRouteMergePreviewDraft()
      }
      return
    }
    if (current?.status === 'EXTRACTING') {
      status.value = 'loading'
      lastInitializedDataRevision.value = getWorkflowDataRevision()
      void pollExtractionTask()
      return
    }
    if (current?.status === 'ROUTE_SET_READY' || current?.status === 'GENERATED') {
      await loadRouteRulesResults()
      lastInitializedDataRevision.value = getWorkflowDataRevision()
      return
    }
  } catch (e) {
    console.error('加载任务模式失败', e)
  }

  try {
    status.value = 'idle'
    lastInitializedDataRevision.value = getWorkflowDataRevision()
  } catch (e) {
    console.error(e)
  }
}

onMounted(async () => {
  extractViewActive.value = true
  window.addEventListener('keydown', handleMergeKeydown)
  window.addEventListener('focus', handleWindowFocusRefresh)
  document.addEventListener('visibilitychange', handleVisibilityRefresh)
  await initializeExtractView()
})

watch(() => [route.path, route.query.project_id, route.query.resume, route.query.from], () => {
  if (!route.path.startsWith('/extract')) return
  void initializeExtractView()
})

onActivated(() => {
  extractViewActive.value = true
})

onDeactivated(() => {
  extractViewActive.value = false
})

onBeforeUnmount(() => {
  stopExtractTaskPolling()
  window.removeEventListener('keydown', handleMergeKeydown)
  window.removeEventListener('focus', handleWindowFocusRefresh)
  document.removeEventListener('visibilitychange', handleVisibilityRefresh)
})

</script>

<style scoped>
.page-header-divider { display: none; }
.card-desc { font-size: 13px; color: var(--text-muted); margin-bottom: 16px; }
.card-title { display: flex; align-items: center; gap: 8px; }
.card-title-icon { display: inline-flex; align-items: center; justify-content: center; width: 28px; height: 28px; border-radius: 8px; background: #eef2ff; color: var(--accent, #6366f1); flex-shrink: 0; }

.module-grid { display: flex; flex-direction: column; gap: 24px; }
.module-dual { display: grid; grid-template-columns: minmax(0, 1.08fr) minmax(0, 0.92fr); gap: 24px; }
.module-card { overflow: hidden; }
.module-card-primary { background: linear-gradient(180deg, #fcfdff, #f7f9ff); border-color: #dfe5f6; }
.module-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
.module-stats { display: flex; gap: 8px; flex-wrap: wrap; justify-content: flex-end; }

.tag-neutral { background: #eef2f7; color: #475569; }

.results-area > .card { margin-bottom: 24px; }
.results-toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.blocked-text { font-size: 13px; color: var(--text-muted); }
.empty-hint { text-align: center; padding: 20px; color: var(--text-muted); font-size: 14px; }
.module-empty { background: #fafbfc; border-radius: 12px; }

.step-flow-arrow { display: flex; align-items: center; justify-content: center; color: #cbd5e1; flex-shrink: 0; padding: 0 4px; }

.route-merge-layout {
  display: grid;
  grid-template-columns: minmax(220px, 0.8fr) minmax(360px, 1.2fr) minmax(280px, 1.0fr);
  gap: 16px;
  align-items: stretch;
  height: calc(100vh - 240px);
}
.route-merge-layout-manual {
  grid-template-columns: minmax(300px, 0.88fr) minmax(420px, 1.12fr);
  height: calc(100vh - 240px);
}

.route-mobile-tabs {
  display: none;
}
.route-pane {
  padding: 0 !important;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  height: 100%;
  max-height: 100%;
  border: 1px solid #e5e7eb;
  border-radius: 14px;
  background: #ffffff;
  box-shadow: 0 4px 20px rgba(0, 0, 0, 0.02);
}
.route-pane > :deep(*) { flex: 1; display: flex; flex-direction: column; overflow: hidden; min-height: 0; }
:deep(.route-pane ::-webkit-scrollbar) { width: 6px; height: 6px; }
:deep(.route-pane ::-webkit-scrollbar-track) { background: #f8fafc; border-radius: 6px; }
:deep(.route-pane ::-webkit-scrollbar-thumb) { background: #e2e8f0; border-radius: 6px; }
:deep(.route-pane ::-webkit-scrollbar-thumb:hover) { background: #94a3b8; }
.route-pane-left { border-top: 2px solid #0f766e; }
.route-pane-center { border-top: 2px solid #4f46e5; }
.route-pane-right { border-top: 2px solid #ea580c; }
.route-pane-right-manual {
  min-height: 0;
  box-shadow: 0 12px 32px rgba(234, 88, 12, 0.08);
}
.route-pane-right-manual .route-result-editor {
  position: sticky;
  bottom: 0;
  z-index: 3;
  margin-top: 8px;
  border-top-color: #fed7aa;
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(12px);
  box-shadow: 0 -8px 20px rgba(15, 23, 42, 0.05);
}
.route-stage-switch-card {
  margin-bottom: 16px;
  padding: 16px 20px;
  border: 1px solid #fed7aa;
  border-radius: 14px;
  background:
    radial-gradient(circle at top right, rgba(251, 146, 60, 0.12), transparent 36%),
    linear-gradient(180deg, #fffaf4 0%, #ffffff 100%);
  box-shadow: 0 10px 24px rgba(251, 146, 60, 0.08);
}
.route-stage-switch-kicker {
  margin-bottom: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #ea580c;
}
.route-stage-switch-title {
  font-size: 22px;
  font-weight: 900;
  line-height: 1.2;
  color: #7c2d12;
}
.route-stage-switch-desc {
  margin-top: 6px;
  max-width: 760px;
  font-size: 14px;
  line-height: 1.7;
  color: #9a3412;
}
.route-result-editor { flex-shrink: 0; border-top: 1px solid #f1f5f9; padding: 14px 24px 18px; display: flex; flex-direction: column; gap: 10px; background: #fafbfc; }
.route-result-editor-locked { color: #94a3b8; font-size: 13px; line-height: 1.6; }
.route-result-editor-ready {
  color: #475569;
  font-size: 13px;
  line-height: 1.7;
  background: linear-gradient(180deg, #fff7ed 0%, #fafbfc 100%);
}
.route-result-editor-name { font-size: 13px; color: #64748b; }
.route-result-editor-name strong { color: #0f172a; font-weight: 700; }
.route-result-editor-actions { display: flex; flex-wrap: wrap; gap: 6px; }
.route-result-editor-actions .btn { border-color: transparent; background: transparent; color: #64748b; font-weight: 600; padding: 6px 12px; box-shadow: none; transition: all 0.15s ease; }
.route-result-editor-actions .btn:hover:not(:disabled) { background: #f1f5f9; color: #0f172a; }
.route-result-editor-actions .btn:disabled { opacity: 0.35; cursor: not-allowed; }
.route-result-editor-rename { display: flex; gap: 8px; align-items: center; }
.route-result-editor-input { flex: 1; min-width: 0; border: 1px solid #818cf8; border-radius: 8px; padding: 6px 10px; font-size: 14px; font-weight: 600; color: #0f172a; background: #fff; outline: none; box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12); }

.route-stage-board {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 16px;
}
.btn-xs {
  padding: 4px 10px;
  font-size: 12px;
  border-radius: 6px;
}
.merge-action-confirm {
  padding: 6px 14px;
  font-size: 13px;
  border-radius: 8px;
  font-weight: 700;
}
.merge-action-reject {
  padding: 6px 12px;
  font-size: 13px;
  border-radius: 8px;
  border: none;
  background: transparent;
  color: #64748b;
  cursor: pointer;
  font-weight: 600;
  transition: color 0.15s ease, background 0.15s ease;
}
.merge-action-reject:hover { background: #f1f5f9; color: #334155; }

.loading-text-block { display: flex; flex-direction: column; gap: 6px; flex: 1; }
.loading-text-block-horizontal { display: flex; flex-direction: row; align-items: center; flex-wrap: wrap; gap: 12px; flex: 1; }
.loading-text-block-horizontal h3 { margin: 0; white-space: nowrap; }
.loading-text-block-horizontal p { margin: 0; white-space: nowrap; }
.loading-progress-wrap { display: flex; align-items: center; gap: 10px; margin-top: 8px; }
.loading-progress-wrap-horizontal { margin-top: 0; flex: 1; min-width: 120px; }
.loading-progress-track { flex: 1; height: 6px; background: #e2e8f0; border-radius: 3px; overflow: hidden; max-width: 280px; }
.loading-progress-fill { height: 100%; background: linear-gradient(90deg, var(--accent, #6366f1), #818cf8); border-radius: 3px; transition: width 0.4s ease; }
.loading-progress-label { font-size: 12px; font-weight: 700; color: var(--accent, #6366f1); min-width: 32px; }
.step-flow-inline { display: flex; align-items: center; flex-wrap: wrap; gap: 6px; margin-top: 8px; }
.step-flow-inline-horizontal { margin-top: 0; }
.step-flow-item { display: flex; align-items: center; gap: 6px; }
.step-flow-dot { width: 8px; height: 8px; border-radius: 50%; background: #cbd5e1; flex-shrink: 0; transition: background 0.2s ease, box-shadow 0.2s ease; }
.step-flow-label { font-size: 13px; font-weight: 600; color: #94a3b8; transition: color 0.2s ease; }
.step-flow-arrow { color: #e2e8f0; flex-shrink: 0; }
.step-flow-item.is-active .step-flow-dot { background: var(--accent, #6366f1); box-shadow: 0 0 0 3px rgba(99,102,241,0.15); }
.step-flow-item.is-active .step-flow-label { color: var(--accent, #6366f1); font-weight: 700; }
.step-flow-item.is-done .step-flow-dot { background: #10b981; box-shadow: 0 0 0 3px rgba(16,185,129,0.12); }
.step-flow-item.is-done .step-flow-label { color: #059669; }
.loading-progress-track-indeterminate { max-width: 340px; position: relative; overflow: hidden; }
.route-stage-block {
  border: none;
  border-radius: 0;
  padding: 0 0 8px;
  background: transparent;
}
.route-stage-block + .route-stage-block {
  border-top: 1px solid #f0f0f0;
  padding-top: 10px;
}
.route-stage-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 8px;
  padding: 0 4px;
}
.route-stage-kicker {
  font-size: 10px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: var(--accent, #6366f1);
  margin-bottom: 2px;
}
.route-stage-title {
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  margin-bottom: 2px;
}
.route-stage-desc {
  font-size: 12px;
  line-height: 1.5;
  color: #94a3b8;
  display: none;
}
.route-stage-stats {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 6px;
}
.route-stage-grid {
  display: grid;
  grid-template-columns: 1fr;
  gap: 6px;
}
.route-stage-chip {
  width: 100%;
  text-align: left;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 12px;
  background: #ffffff;
  cursor: pointer;
  transition: border-color 0.15s ease, background 0.15s ease, box-shadow 0.15s ease;
}
.route-stage-chip:hover {
  border-color: #c7d2fe;
  background: #fafbff;
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.06);
}
.route-stage-chip.active {
  border-color: #818cf8;
  background: #eef2ff;
  box-shadow: 0 0 0 1px #818cf8;
}
.route-stage-chip-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}
.route-stage-chip-name {
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.4;
}
.route-stage-chip-seq {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: #4f46e5;
  background: #eef2ff;
  border: none;
  border-radius: 4px;
  padding: 2px 7px;
}
.route-stage-chip-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.merge-focus-card {
  padding: 16px;
  border-radius: 10px;
  border: 1px solid #e0e7ff;
  background: #f8faff;
  box-shadow: none;
  margin-top: 12px;
}
.merge-focus-card-compact {
  margin-top: 8px;
  padding: 14px 16px;
}
.merge-focus-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6366f1;
  margin-bottom: 4px;
}
.merge-focus-name {
  font-size: 22px;
  font-weight: 700;
  line-height: 1.2;
  color: #1e293b;
  margin-bottom: 8px;
}
.merge-focus-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}
.merge-focus-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 34px;
  height: 28px;
  padding: 0 10px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4f46e5;
  font-size: 12px;
  font-weight: 700;
}
.merge-focus-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.merge-ops-row,
.merge-suggestion-card,
.merge-edit-block {
  margin-top: 12px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}
.merge-ops-title,
.merge-suggestion-title {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
}
.merge-ops-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}
.merge-suggestion-card {
  border-color: #e0e7ff;
  background: #fafaff;
}
.merge-suggestion-text {
  font-size: 14px;
  line-height: 1.7;
  color: #334155;
  font-weight: 600;
}
.merge-brief-card {
  margin-top: 12px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
}
.merge-brief-block + .merge-brief-block {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}
.merge-brief-label {
  margin-bottom: 8px;
  font-size: 11px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.06em;
  color: #94a3b8;
}
.merge-brief-inline {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 10px;
}
.merge-edit-card {
  background: #fbfcff;
}
.merge-edit-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.merge-edit-head-compact {
  margin-bottom: 12px;
}
.merge-inline-name {
  font-size: 13px;
  font-weight: 700;
  color: #64748b;
}
.merge-primary-actions {
  display: grid;
  gap: 8px;
}
.merge-neighbors {
  display: grid;
  gap: 8px;
  margin-top: 12px;
}
.merge-neighbor-btn {
  width: 100%;
  text-align: left;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 10px 14px;
  background: #ffffff;
  color: #1e293b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.merge-neighbor-btn-primary {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #3730a3;
}
.merge-neighbor-name {
  display: block;
  margin-top: 2px;
  font-size: 12px;
  font-weight: 600;
  color: #6366f1;
}
.merge-neighbor-btn:hover {
  border-color: #818cf8;
  background: #f5f3ff;
  color: #4338ca;
}
.merge-name-input {
  width: 100%;
  height: 40px;
  border-radius: 8px;
  border: 1px solid #d1d5db;
  padding: 0 12px;
  font-size: 14px;
  font-weight: 600;
  color: #1e293b;
  background: #fff;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.merge-name-input:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.merge-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}
.merge-action-row-compact {
  margin-top: 12px;
}
.merge-action-row .btn {
  min-width: 120px;
}
.merge-advanced {
  margin-top: 12px;
  border-top: 1px solid #e5e7eb;
  padding-top: 12px;
}
.merge-advanced summary {
  cursor: pointer;
  font-size: 13px;
  font-weight: 700;
  color: #475569;
}
.merge-advanced-body {
  display: grid;
  gap: 10px;
  margin-top: 10px;
}

@media (max-width: 900px) {
  .route-mobile-tabs {
    display: flex;
    gap: 4px;
    margin: 0 0 8px;
    padding: 4px;
    overflow-x: auto;
    border: 1px solid #e2e8f0;
    border-radius: 9px;
    background: #ffffff;
  }

  .route-mobile-tabs button {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    gap: 5px;
    min-width: 94px;
    height: 32px;
    padding: 0 10px;
    border: 0;
    border-radius: 6px;
    background: transparent;
    color: #64748b;
    font-size: 12px;
    font-weight: 700;
    white-space: nowrap;
    cursor: pointer;
  }

  .route-mobile-tabs button.active {
    background: #eef2ff;
    color: #4338ca;
  }

  .route-mobile-tab-count {
    min-width: 18px;
    padding: 1px 5px;
    border-radius: 999px;
    background: #fef3c7;
    color: #b45309;
    font-size: 10px;
    text-align: center;
  }

  .route-merge-layout,
  .route-merge-layout-manual {
    grid-template-columns: 1fr;
    height: auto !important;
  }
  .module-dual { grid-template-columns: 1fr; }
  .merge-minimal-summary { grid-template-columns: 1fr; }
  .module-head { flex-direction: column; align-items: stretch; }
  .module-stats { justify-content: flex-start; }
  .route-pane { min-height: unset; max-height: 500px !important; }
  .route-merge-layout.route-mobile-pane-source .route-pane:not(.route-pane-left),
  .route-merge-layout.route-mobile-pane-queue .route-pane:not(.route-pane-center),
  .route-merge-layout.route-mobile-pane-result .route-pane:not(.route-pane-right) {
    display: none;
  }

  .route-merge-layout.route-mobile-pane-source .route-pane-left,
  .route-merge-layout.route-mobile-pane-queue .route-pane-center,
  .route-merge-layout.route-mobile-pane-result .route-pane-right {
    max-height: calc(100vh - 280px) !important;
    min-height: 420px;
  }
  .merge-focus-name { font-size: 24px; }
  .merge-edit-head { flex-direction: column; align-items: stretch; }
  .merge-action-row .btn { width: 100%; }
}
</style>
