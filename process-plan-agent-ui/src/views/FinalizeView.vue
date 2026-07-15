<template>
  <div class="finalize-view">
    <div class="analysis-style-header">
      <div class="ash-top">
        <div class="ash-titles">
          <h1>{{ FINALIZE_VIEW_COPY.pageTitle }}</h1>
          <p>{{ FINALIZE_VIEW_COPY.pageSubtitle }}</p>
        </div>
        <div class="ash-actions">
          <button class="ash-btn-plain" @click="goBackToAnalysis" :disabled="!projectId">
            {{ FINALIZE_VIEW_COPY.backToAnalysis }}
          </button>
          <button class="ash-btn-outline" @click="downloadRuleDocument" :disabled="exportingRulePackage || !segmentCards.length">
            {{ exportingRulePackage ? '正在导出...' : FINALIZE_VIEW_COPY.exportDocument }}
          </button>
          <button class="ash-btn-plain" @click="downloadRuleDocumentV1Compat" :disabled="exportingRulePackage || !segmentCards.length" title="迁移期兼容：导出 V1">
            {{ FINALIZE_VIEW_COPY.exportDocumentV1 }}
          </button>
          <button class="ash-btn-outline" @click="toggleOnlyEdited" :disabled="!segmentCards.length">
            {{ onlyEdited ? FINALIZE_VIEW_COPY.showAll : FINALIZE_VIEW_COPY.showEditedOnly }}
          </button>
          <button class="ash-btn-primary" @click="reloadWorkspace" :disabled="loading || !projectId">
            {{ FINALIZE_VIEW_COPY.refresh }}
          </button>
        </div>
      </div>
      <div class="ash-meta-bar">
        <span class="ash-dark-chip">{{ projectName || '未命名任务' }}</span>
        <span class="ash-meta-item">已保存版本 <strong>V{{ savedRoute?.version || '-' }}</strong></span>
        <span class="ash-meta-item" v-if="lastExportedRulePackageVersion">规则包 <strong>V{{ lastExportedRulePackageVersion }}</strong></span>
        <span class="ash-meta-item">总工序段 <strong>{{ segmentCards.length }}</strong></span>
        <span class="ash-meta-item" v-if="editedSegmentCount">本页已微调 <strong class="highlight-text">{{ editedSegmentCount }}</strong></span>
      </div>
    </div>

    <div v-if="!projectId" class="empty-state card">
      <div class="empty-mark">04</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.emptyProjectTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.emptyProjectText }}</div>
    </div>

    <div v-else-if="loading" class="empty-state card">
      <div class="empty-mark">···</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.loadingTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.loadingText }}</div>
    </div>

    <div v-else-if="error" class="empty-state card empty-state-error">
      <div class="empty-mark">!</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.errorTitle }}</div>
      <div class="empty-text">{{ error }}</div>
      <button class="btn btn-primary" @click="goBackToAnalysis">{{ FINALIZE_VIEW_COPY.errorBack }}</button>
    </div>

    <div v-else-if="!segmentCards.length" class="empty-state card">
      <div class="empty-mark">∅</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.emptySegmentTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.emptySegmentText }}</div>
    </div>

    <div v-else-if="!visibleSegments.length" class="empty-state card">
      <div class="empty-mark">*</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.emptyEditedTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.emptyEditedText }}</div>
      <button class="btn btn-outline" @click="onlyEdited = false">{{ FINALIZE_VIEW_COPY.showAll }}</button>
    </div>

    <div v-else class="finalize-layout">
      <FinalizeRouteNav
        :title="FINALIZE_VIEW_COPY.routeOverview"
        :items="visibleSegments"
        :active-segment-id="activeSegmentId"
        :display-name="finalizeSegmentDisplayName"
        :meta-label="finalizeSegmentMetaLabel"
        :step-count="finalizeSegmentStepCount"
        :primary-steps="finalizeSegmentPrimarySteps"
        :attached-steps="finalizeSegmentAttachedSteps"
        :is-steps-expanded="isFinalizeSegmentStepsExpanded"
        @focus="focusSegment"
        @toggle-steps="toggleFinalizeSegmentSteps"
      />

      <section class="finalize-results">


        <FinalizeRuleCard
          v-for="item in visibleSegments"
          :key="item.segment.id"
          :item="item"
          :active="activeSegmentId === item.segment.id"
          :display-name="finalizeSegmentDisplayName(item.segment)"
          :meta-label="finalizeSegmentMetaLabel(item.segment)"
          :inline-editing="inlineEditingSegmentId === item.segment.id"
          :inline-editing-text="inlineEditingText"
          :edited-badge="FINALIZE_VIEW_COPY.editedBadge"
          :edit-label="FINALIZE_VIEW_COPY.edit"
          :condition-label="FINALIZE_VIEW_COPY.conditionLabel"
          :set-inline-textarea-ref="setInlineTextareaRef"
          @reset="resetInlineEdit"
          @start-edit="startInlineEdit"
          @cancel="cancelInlineEdit"
          @save="saveInlineEdit"
          @update:inline-editing-text="inlineEditingText = $event"
        />
      </section>
    </div>


  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FinalizeRouteNav from '@/components/finalize/FinalizeRouteNav.vue'
import FinalizeRuleCard from '@/components/finalize/FinalizeRuleCard.vue'
import {
  getSavedNormalizedRoute,
  getLatestFinalizedRulePackage,
  getSupersetRoute,
  listOperations,
  listProjects,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  segmentDisplayMetaLabel,
  segmentDisplayName,
} from '@/composables/analysisWorkspaceHelpers'
import {
  buildFinalizeCards,
  resolveFinalizePhase,
} from '@/composables/finalizeViewHelpers'
import { useFinalizeDrafts } from '@/composables/useFinalizeDrafts'
import { useFinalizeRulePackageExport } from '@/composables/useFinalizeRulePackageExport'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { buildProjectRouteQuery, resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'

const route = useRoute()
const router = useRouter()

const loading = ref(false)
const error = ref('')
const projectId = ref<number | null>(null)
const projectName = ref('')
const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
const operations = ref<OperationItem[]>([])
const supersetOperations = ref<OperationItem[]>([])
const onlyEdited = ref(false)
const activeSegmentId = ref('')
const lastExportedRulePackageVersion = ref<number | null>(null)
const {
  segmentAttachedSteps: finalizeSegmentAttachedSteps,
  segmentPrimarySteps: finalizeSegmentPrimarySteps,
  segmentStepCount: finalizeSegmentStepCount,
  isSegmentStepsExpanded: isFinalizeSegmentStepsExpanded,
  toggleSegmentSteps: toggleFinalizeSegmentSteps,
} = useRouteSegmentSteps(supersetOperations)
const {
  cancelInlineEdit,
  drafts,
  inlineEditingSegmentId,
  inlineEditingText,
  persistDrafts,
  readDrafts,
  resetInlineEdit,
  saveInlineEdit,
  setInlineTextareaRef,
  startInlineEdit,
} = useFinalizeDrafts(projectId)

const segmentCards = computed(() => {
  const routeData = savedRoute.value
  if (!routeData) return []
  return buildFinalizeCards(routeData.segments, operations.value, drafts.value)
})

const visibleSegments = computed(() =>
  onlyEdited.value ? segmentCards.value.filter(item => item.edited) : segmentCards.value,
)

const editedSegmentCount = computed(() =>
  segmentCards.value.filter(item => item.edited).length,
)

function syncActiveSegment() {
  const currentExists = visibleSegments.value.some(item => item.segment.id === activeSegmentId.value)
  if (currentExists) return
  activeSegmentId.value = visibleSegments.value[0]?.segment.id || ''
}

function focusSegment(segmentId: string) {
  activeSegmentId.value = segmentId
  const el = document.getElementById(`finalize-card-${segmentId}`)
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' })
  }
}



function toggleOnlyEdited() {
  onlyEdited.value = !onlyEdited.value
}

function finalizeSegmentDisplayName(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayName(segment)
}

function finalizeSegmentMetaLabel(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayMetaLabel(segment)
}

const {
  exportingRulePackage,
  downloadRuleDocument,
  downloadRuleDocumentV1Compat,
} = useFinalizeRulePackageExport({
  projectId,
  projectName,
  savedRoute,
  segmentCards,
  displayName: finalizeSegmentDisplayName,
  metaLabel: finalizeSegmentMetaLabel,
  phaseLabel: resolveFinalizePhase,
  primarySteps: finalizeSegmentPrimarySteps,
  attachedSteps: finalizeSegmentAttachedSteps,
  onExportedVersion: (version, meta) => {
    lastExportedRulePackageVersion.value = version
    console.info(`规则包 V${version} 已导出，可用于第 5 步。`, meta)
  },
})

function goBackToAnalysis() {
  router.push({
    path: '/analysis',
    query: buildProjectRouteQuery(projectId.value),
  })
}

async function loadWorkspace(forceRefresh = false) {
  loading.value = true
  error.value = ''

  try {
    const projectList = await listProjects(forceRefresh)
    const resolvedProjectId = resolveAvailableProjectId(String(route.query.project_id || ''), projectList)
    if (!resolvedProjectId) {
      projectId.value = null
      projectName.value = ''
      savedRoute.value = null
      operations.value = []
      supersetOperations.value = []
      lastExportedRulePackageVersion.value = null
      error.value = ''
      return
    }

    projectId.value = Number(resolvedProjectId)
    if (String(route.query.project_id || '') !== resolvedProjectId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: resolvedProjectId },
      })
    }
    const currentProject = projectList.find(project => project.id === projectId.value)
    const [routeResult, operationList, supersetResult, latestPackage] = await Promise.all([
      getSavedNormalizedRoute(projectId.value, forceRefresh),
      listOperations(projectId.value, forceRefresh),
      getSupersetRoute(projectId.value, forceRefresh),
      getLatestFinalizedRulePackage(projectId.value, forceRefresh).catch(() => null),
    ])
    savedRoute.value = routeResult
    operations.value = operationList
    supersetOperations.value = supersetResult.superset_route || []
    projectName.value = currentProject?.name || `任务 #${projectId.value}`
    lastExportedRulePackageVersion.value = latestPackage?.version || null
    readDrafts()
    activeSegmentId.value = routeResult.segments[0]?.id || ''
  } catch (err: any) {
    console.error(err)
    projectId.value = null
    savedRoute.value = null
    operations.value = []
    supersetOperations.value = []
    lastExportedRulePackageVersion.value = null
    error.value = err?.response?.data?.detail || '当前任务还没有第三步可预览的已保存结果，请先回到第三步完成分析。'
  } finally {
    loading.value = false
  }
}

async function reloadWorkspace() {
  await loadWorkspace(true)
}

watch(() => route.query.project_id, () => {
  void loadWorkspace()
})

watch(drafts, () => {
  persistDrafts()
}, { deep: true })

watch([visibleSegments, onlyEdited], () => {
  syncActiveSegment()
}, { deep: true })

onMounted(async () => {
  await loadWorkspace()
})
</script>

<style scoped>
.finalize-view {
  padding: 0;
  min-height: calc(100vh - 128px);
  background: #f8fafc;
}

.analysis-style-header {
  margin-bottom: 12px;
}

.ash-top {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.ash-titles {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.ash-titles h1 {
  margin: 0;
  font-size: 20px;
  font-weight: 700;
  line-height: 1.25;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.ash-titles p {
  margin: 4px 0 0;
  font-size: 13px;
  line-height: 1.6;
  color: #94a3b8;
  font-weight: 400;
}

.ash-actions {
  display: flex;
  align-items: center;
  gap: 12px;
}

.ash-btn-plain {
  background: transparent;
  border: none;
  color: #64748b;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  padding: 5px 8px;
  transition: color 0.2s;
}
.ash-btn-plain:hover { color: #0f172a; }

.ash-btn-outline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border: 1px solid #c7d2fe;
  color: #4f46e5;
  padding: 5px 12px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.ash-btn-outline:hover { background: #f8fafc; border-color: #a5b4fc; }
.ash-btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }

.ash-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #4f46e5;
  color: #ffffff;
  border: none;
  padding: 5px 14px;
  border-radius: 7px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s;
}
.ash-btn-primary:hover:not(:disabled) { background: #4338ca; box-shadow: 0 4px 12px -2px rgba(79, 70, 229, 0.4); }
.ash-btn-primary:disabled { opacity: 0.5; cursor: not-allowed; }

.ash-meta-bar {
  display: flex;
  align-items: center;
  gap: 20px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  padding: 10px 14px;
}

.ash-dark-chip {
  background: #0f172a;
  color: #f1f5f9;
  padding: 4px 10px;
  border-radius: 6px;
  font-size: 13px;
  font-weight: 600;
}

.ash-meta-item {
  font-size: 13px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 4px;
}

.ash-meta-item strong {
  color: #0f172a;
  font-weight: 600;
}

.highlight-text {
  color: #ea580c !important;
}

.finalize-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  height: calc(100vh - 200px);
}

.finalize-results {
  min-width: 0;
  overflow-y: auto;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.finalize-results {
  padding: 12px 16px;
}

.finalize-results {
  min-width: 0;
}

@media (max-width: 900px) {
  .ash-top {
    align-items: stretch;
    flex-direction: column;
    gap: 14px;
  }

  .ash-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    gap: 8px;
    width: 100%;
  }

  .ash-actions button {
    min-height: 36px;
    width: 100%;
  }

  .ash-meta-bar {
    flex-wrap: wrap;
    gap: 8px 14px;
  }

  .finalize-layout {
    grid-template-columns: minmax(0, 1fr);
    height: auto;
  }

  .finalize-results {
    max-height: none;
    overflow: visible;
  }

  :deep(.route-nav) {
    max-height: 420px;
  }
}

@media (max-width: 520px) {
  .ash-titles h1 {
    font-size: 18px;
  }

  .ash-dark-chip {
    max-width: 100%;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
  }
}



/* ===== Drawer Overlay & Modal ===== */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.52);
  backdrop-filter: blur(12px) saturate(120%);
  -webkit-backdrop-filter: blur(12px) saturate(120%);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 24px;
}

.edit-drawer {
  width: min(520px, 100%);
  max-height: calc(100vh - 80px);
  background: linear-gradient(180deg, #ffffff 0%, #fbfcfe 100%);
  border-radius: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow:
    0 32px 64px -16px rgba(15, 23, 42, 0.22),
    0 0 0 1px rgba(148, 163, 184, 0.1),
    0 0 0 4px rgba(99, 102, 241, 0.04);
}

/* --- Header --- */
.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px 20px;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04) 0%, rgba(255, 255, 255, 0.9) 100%);
  border-bottom: 1px solid rgba(226, 232, 240, 0.7);
  flex-shrink: 0;
}

.drawer-head-info {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawer-kicker-badge {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  color: #ffffff;
  width: fit-content;
}

.drawer-title {
  font-size: 19px;
  line-height: 1.3;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.02em;
}

.drawer-title-meta {
  margin-top: -2px;
  font-size: 12px;
  line-height: 1.45;
  color: #94a3b8;
}

.drawer-close-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  color: #94a3b8;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.drawer-close-btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
  color: #475569;
  transform: scale(1.05);
}

/* --- Scrollable Body --- */
.drawer-body {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px 20px;
}

/* --- Sections --- */
.drawer-section {
  margin-bottom: 0;
}

.drawer-divider {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, #e2e8f0 20%, #e2e8f0 80%, transparent 100%);
  margin: 20px 0;
}

.drawer-factor-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.drawer-section-title {
  font-size: 13px;
  font-weight: 600;
  color: #4f46e5;
  margin-bottom: 10px;
  display: flex;
  align-items: center;
  gap: 6px;
  letter-spacing: 0.01em;
}

.drawer-section-title::before {
  content: '';
  display: inline-block;
  width: 3px;
  height: 14px;
  border-radius: 2px;
  background: linear-gradient(180deg, #6366f1 0%, #a5b4fc 100%);
  flex-shrink: 0;
}

/* --- Textarea --- */
.drawer-textarea {
  width: 100%;
  resize: vertical;
  border-radius: 10px;
  border: 1.5px solid #e2e8f0;
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: #0f172a;
  background: #fafbfc;
  outline: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  font-family: inherit;
}

.drawer-textarea::placeholder {
  color: #94a3b8;
  font-weight: 400;
}

.drawer-textarea:hover {
  border-color: #c7d2fe;
  background: #ffffff;
}

.drawer-textarea:focus {
  border-color: #818cf8;
  background: #ffffff;
  box-shadow:
    0 0 0 3px rgba(99, 102, 241, 0.1),
    0 2px 8px rgba(99, 102, 241, 0.06);
}

/* --- Factor Checkbox Items --- */
.drawer-factor-item {
  display: flex;
  gap: 12px;
  align-items: center;
  padding: 11px 14px;
  border-radius: 10px;
  background: #fafbfc;
  border: 1.5px solid #e8ecf1;
  color: #334155;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-factor-item:hover {
  border-color: #c7d2fe;
  background: #f8faff;
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.06);
}

.drawer-factor-item.is-active {
  background: linear-gradient(135deg, #eef2ff 0%, #f0f3ff 100%);
  border-color: #818cf8;
  color: #3730a3;
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.08);
}

.drawer-factor-item input {
  display: none;
}

.factor-checkbox {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1.5px solid #cbd5e1;
  background: #ffffff;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.drawer-factor-item.is-active .factor-checkbox {
  background: linear-gradient(135deg, #6366f1 0%, #818cf8 100%);
  border-color: #6366f1;
  transform: scale(1.05);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}

.factor-checkbox svg {
  width: 11px;
  height: 11px;
  fill: none;
  stroke: #ffffff;
  stroke-width: 2.5;
  stroke-linecap: round;
  stroke-linejoin: round;
  opacity: 0;
  transform: scale(0.5) rotate(-10deg);
  transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.drawer-factor-item.is-active .factor-checkbox svg {
  opacity: 1;
  transform: scale(1) rotate(0deg);
}

.factor-text {
  flex: 1;
  min-width: 0;
  line-height: 1.5;
}

/* --- Action Row --- */
.drawer-action-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.drawer-action-chip {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  font-weight: 600;
  color: #4f46e5;
  background: #eef2ff;
  border: 1px solid #e0e7ff;
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.drawer-action-chip:hover:not(:disabled) {
  background: #e0e7ff;
  border-color: #c7d2fe;
  transform: translateY(-1px);
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.12);
}

.drawer-action-chip:disabled {
  opacity: 0.5;
  cursor: wait;
}

/* --- Sticky Footer --- */
.drawer-foot {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  padding: 16px 28px;
  border-top: 1px solid rgba(226, 232, 240, 0.7);
  background: rgba(248, 250, 252, 0.9);
  backdrop-filter: blur(8px);
  flex-shrink: 0;
}

.drawer-foot-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 8px 20px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-foot-btn-reset {
  background: #ffffff;
  color: #475569;
  border: 1px solid #cbd5e1;
}

.drawer-foot-btn-reset:hover {
  background: #f1f5f9;
  border-color: #94a3b8;
  color: #1e293b;
}

.drawer-foot-btn-save {
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  color: #ffffff;
  border: none;
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.25);
}

.drawer-foot-btn-save:hover {
  background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
  transform: translateY(-1px);
  box-shadow: 0 4px 14px rgba(79, 70, 229, 0.35);
}

/* --- Drawer Transitions --- */
.drawer-fade-enter-active,
.drawer-fade-leave-active {
  transition: opacity 0.25s ease;
}
.drawer-fade-enter-from,
.drawer-fade-leave-to {
  opacity: 0;
}

.drawer-slide-enter-active {
  transition: all 0.35s cubic-bezier(0.34, 1.56, 0.64, 1);
}
.drawer-slide-leave-active {
  transition: all 0.2s ease-in;
}
.drawer-slide-enter-from {
  opacity: 0;
  transform: scale(0.92) translateY(20px);
}
.drawer-slide-leave-to {
  opacity: 0;
  transform: scale(0.96) translateY(8px);
}

.empty-state {
  text-align: center;
  padding: 56px 28px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
}

.empty-mark {
  font-size: 28px;
  font-weight: 700;
  color: #94a3b8;
  margin-bottom: 12px;
}

.empty-title {
  font-size: 18px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 8px;
  letter-spacing: -0.01em;
}

.empty-text {
  font-size: 14px;
  line-height: 1.8;
  color: #64748b;
  font-weight: 400;
  max-width: 620px;
  margin: 0 auto 18px;
}

.empty-state-error {
  border-color: #fecaca;
  background: linear-gradient(180deg, #ffffff 0%, #fff8f8 100%);
}

.btn-sm {
  padding: 7px 12px;
  font-size: 12px;
  border-radius: 8px;
}

@media (max-width: 1080px) {
  .finalize-layout {
    grid-template-columns: 1fr;
  }

  .preview-grid {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 720px) {
  .finalize-header,
  .drawer-foot,
  .ash-actions {
    flex-direction: column;
  }

  .header-actions {
    justify-content: flex-start;
    margin-top: 12px;
  }
}
</style>
