<template>
  <div class="finalize-view">
    <div class="analysis-style-header">
      <div class="ash-left-content">
        <span class="ash-page-title">规则定稿</span>
        <span class="ash-dark-chip">{{ projectName || '未命名任务' }}</span>
        
        <div class="ash-meta-section">
          <span class="ash-meta-item">已保存版本 <strong>V{{ savedRoute?.version || '-' }}</strong></span>
          <span class="ash-meta-item" v-if="lastExportedRulePackageVersion">规则包 <strong>V{{ lastExportedRulePackageVersion }}</strong></span>
          <span class="ash-meta-item ash-meta-stale" v-else-if="outdatedRulePackageVersion">规则包 V{{ outdatedRulePackageVersion }} <strong>已过期</strong></span>
          <span class="ash-meta-item">主线 <strong>{{ mainlineRuleCount }}</strong></span>
          <span class="ash-meta-item">条件 <strong>{{ conditionalRuleCount }}</strong></span>
          <span class="ash-meta-item" v-if="relationRuleCount">关联 <strong>{{ relationRuleCount }}</strong></span>
          <span class="ash-meta-item" v-if="unresolvedRuleCount">待补充 <strong class="warning-text">{{ unresolvedRuleCount }}</strong></span>
          <!-- Recognition progress: simplified when all done -->
          <span class="ash-meta-item ash-meta-progress-item" v-if="reviewableRuleCount > 0">
            <template v-if="confirmedRuleCount === reviewableRuleCount">
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="#16a34a" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/><path d="M22 4L12 14.01l-3-3"/></svg>
              <strong class="text-done">全部已确认</strong>
            </template>
            <template v-else>
              <span>已确认</span>
              <div class="mini-progress-bar">
                <div
                  class="mini-progress-fill"
                  :style="{ width: `${reviewProgressPercent}%` }"
                ></div>
              </div>
              <strong>{{ confirmedRuleCount }}/{{ reviewableRuleCount }}</strong>
            </template>
          </span>
        </div>
      </div>

      <div class="ash-actions">
        <button
          class="ash-btn-outline"
          @click="resetDialogVisible = true"
          :disabled="loading || resettingWorkflow || batchParsing || batchReviewing || publishingRulePackage || downloadingRulePackage || !savedRoute"
        >
          重新识别全部
        </button>
        <button
          class="ash-btn-outline"
          @click="handleRuleReview"
          :disabled="actionDisabled.review"
        >
          {{ reviewButtonLabel }}
        </button>
        <button
          class="ash-btn-primary ash-btn-phase-active"
          @click="publishRulePackage"
          :disabled="actionDisabled.publish"
        >
          {{ publishButtonLabel }}
        </button>
        <button
          class="ash-btn-outline"
          @click="downloadCurrentRulePackage"
          :disabled="actionDisabled.download"
          :title="actionDisabled.download && outdatedRulePackageVersion ? '当前规则已变更，请先重新发布' : '下载当前发布版本'"
        >
          {{ downloadButtonLabel }}
        </button>

        <!-- Toggle switch: only pending -->
        <label class="toggle-filter-wrap" :class="{ 'toggle-filter-disabled': !segmentCards.length }">
          <input
            type="checkbox"
            class="toggle-filter-input"
            :checked="onlyPending"
            :disabled="!segmentCards.length"
            @change="toggleOnlyPending"
          />
          <span class="toggle-filter-track" :class="{ 'toggle-filter-track--on': onlyPending }">
            <span class="toggle-filter-thumb"></span>
          </span>
          <span class="toggle-filter-text">仅看需处理</span>
        </label>

        <!-- Icon: refresh -->
        <button
          class="icon-refresh-btn"
          :class="{ 'icon-refresh-btn--spinning': loading }"
          @click="reloadWorkspace"
          :disabled="loading || resettingWorkflow || !projectId"
          title="刷新结果"
          aria-label="刷新结果"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M23 4v6h-6"/>
            <path d="M1 20v-6h6"/>
            <path d="M3.51 9a9 9 0 0 1 14.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0 0 20.49 15"/>
          </svg>
        </button>
      </div>
    </div>

    <div v-if="batchNotice" class="batch-notice">{{ batchNotice }}</div>
    <div v-if="factorCatalogError" class="batch-notice factor-catalog-error" role="alert">
      <span>{{ factorCatalogError }}</span>
      <button class="ghost-btn" :disabled="conditionRegistryLoading" @click="retryConditionRegistry">
        {{ conditionRegistryLoading ? '正在重试…' : '重试加载' }}
      </button>
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
      <div class="empty-title">{{ workspaceErrorTitle }}</div>
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
      <div class="empty-title">当前没有需要处理的规则</div>
      <div class="empty-text">系统已完成全部规则审核；可以发布规则包，或切换到全部规则浏览。</div>
      <button class="btn btn-outline" @click="onlyPending = false">显示全部规则</button>
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
        :item-needs-pending="itemNeedsPending"
        :only-pending="onlyPending"
        :all-item-count="segmentCards.length"
        @focus="focusSegment"
        @toggle-steps="toggleFinalizeSegmentSteps"
        @toggle-only-pending="toggleOnlyPending"
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
          :condition-fields="conditionFields"
          :standard-factors="standardFactors"
          :factor-catalog-version="factorCatalogVersion"
          :process-options="conditionProcessOptions"
          :condition-busy="conditionBusySegmentIds.has(item.segment.id)"
          :set-inline-textarea-ref="setInlineTextareaRef"
          @reset="handleResetInlineEdit"
          @start-edit="startInlineEdit"
          @cancel="cancelInlineEdit"
          @save="handleSaveInlineEdit"
          @parse-condition="handleParseCondition"
          @confirm-condition="handleConfirmCondition"
          @set-mainline="handleSetMainline"
          @set-boolean="handleSetBoolean"
          @update:inline-editing-text="inlineEditingText = $event"
        />
      </section>
    </div>

    <WorkflowNavFooter
      :summary="finalizeNavSummary"
      previous-label="← 返回规则分析"
      next-label="进入路线生成 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId || !lastExportedRulePackageVersion || !allCurrentRulesConfirmed"
      @previous="goBackToAnalysis"
      @next="goToGenerate"
    />

    <div v-if="rulePackageIssue" class="export-issue-overlay" @click.self="closeRulePackageIssue">
      <section class="export-issue-dialog" role="dialog" aria-modal="true" aria-labelledby="export-issue-title">
        <div class="export-issue-icon" aria-hidden="true">!</div>
        <div class="export-issue-content">
          <span class="export-issue-kicker">{{ rulePackageIssue.context || '规则包处理' }}</span>
          <h2 id="export-issue-title">{{ rulePackageIssue.title }}</h2>
          <p>{{ rulePackageIssue.summary }}</p>
          <details v-if="rulePackageIssue.details" class="export-issue-details">
            <summary>查看检查详情</summary>
            <pre>{{ rulePackageIssue.details }}</pre>
          </details>
          <div class="export-issue-actions">
            <button class="ash-btn-primary" @click="closeRulePackageIssue">知道了</button>
          </div>
        </div>
      </section>
    </div>

    <WorkflowResetDialog
      v-model="resetDialogVisible"
      title="重新识别第四步全部规则？"
      description="系统会保留用户条件原文和人工设定，只重置模型识别结果并重新生成候选。"
      :keep-items="['用户填写的条件原文', '人工主工序', '用户直接设定的 Bool 规则']"
      :clear-items="['普通规则的候选和确认状态', '当前规则包', '第五步已生成路线']"
      confirm-label="重新识别全部"
      busy-label="正在重新识别..."
      :busy="resettingWorkflow"
      @confirm="handleResetAllRecognition"
    />

    <RulePackagePublishReviewDialog
      v-model="publishReviewVisible"
      :review="publishReview"
      @confirmed="completePublishReview(true)"
      @cancelled="completePublishReview(false)"
      @locate="locatePublishBlocker"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FinalizeRouteNav from '@/components/finalize/FinalizeRouteNav.vue'
import FinalizeRuleCard from '@/components/finalize/FinalizeRuleCard.vue'
import RulePackagePublishReviewDialog from '@/components/finalize/RulePackagePublishReviewDialog.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import WorkflowResetDialog from '@/components/workflow/WorkflowResetDialog.vue'
import {
  type SaveFinalizedRulePackageResponse,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  type RuleConditionProcessOption,
} from '@/api/rulePackages'
import {
  segmentDisplayMetaLabel,
  segmentDisplayName,
} from '@/composables/analysisWorkspaceHelpers'
import {
  buildFinalizeCards,
  resolveFinalizePhase,
} from '@/composables/finalizeViewHelpers'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { useFinalizeDrafts } from '@/composables/useFinalizeDrafts'
import {
  useFinalizeRulePackagePublish,
  type RulePackagePublishReview,
} from '@/composables/useFinalizeRulePackagePublish'
import {
  buildPublishReviewFocusCards,
  locatePublishBlocker as locatePublishBlockerInReview,
  useRulePackagePublishReview,
} from '@/composables/useRulePackagePublishReview'
import { useFinalizedRulePackageDownload } from '@/composables/useFinalizedRulePackageDownload'
import { useFinalizeWorkspace } from '@/composables/useFinalizeWorkspace'
import { useConditionReviewQueue } from '@/composables/useConditionReviewQueue'
import { useFinalizeWorkflowConflict } from '@/composables/useFinalizeWorkflowConflict'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { buildProjectRouteQuery } from '@/composables/useCurrentProject'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'
import { workflowResetSignal } from '@/composables/workflowResetState'
import {
  exportProcessIdForItem,
  buildCompileRequestFromCards,
  finalizeRuleMode,
  isSafeForBatchRuleConfirmation,
  needsFinalizeRuleReview,
  normalizeExportProcessName,
  requiresServerRuleConditionRefresh,
} from '@/utils/finalizeRulePackage'
import {
  downloadActionLabel,
  publishActionLabel,
  reviewActionLabel,
  rulePackageActionDisabled,
} from '@/utils/finalizeRulePackageActionState'

const route = useRoute()
const router = useRouter()
let finalizeViewActive = false
let initialLoadFinished = false
const onlyPending = ref(true)
const activeSegmentId = ref('')
const locatedPublishBlockerId = ref('')

const {
  loading,
  error,
  workspaceErrorTitle,
  projectId,
  projectName,
  savedRoute,
  operations,
  supersetOperations,
  currentPublishedPackage,
  outdatedRulePackageVersion,
  conditionFields,
  standardFactors,
  factorCatalogVersion,
  factorCatalogError,
  conditionRegistryLoading,
  factorCatalogReady,
  loadedDataRevision,
  loadWorkspace,
  retryConditionRegistry,
  markPublishedRulePackageOutdated,
} = useFinalizeWorkspace({
  requestedProjectId: () => String(route.query.project_id || ''),
  onProjectResolved: projectIdValue => {
    void router.replace({
      path: route.path,
      query: { ...route.query, project_id: projectIdValue },
    })
  },
  readDrafts: () => readDrafts(),
  onRouteLoaded: routeResult => {
    activeSegmentId.value = routeResult.segments[0]?.id || ''
  },
  segmentCards: computed(() => segmentCards.value),
  allCurrentRulesConfirmed: computed(() => allCurrentRulesConfirmed.value),
  buildCompileRequest: context => buildCompileRequestFromCards({
    projectId: context.projectId,
    packageName: context.packageName,
    routeVersionId: context.routeVersionId,
    cards: context.cards,
    displayName: finalizeSegmentDisplayName,
    phaseLabel: resolveFinalizePhase,
    primarySteps: finalizeSegmentPrimarySteps,
    attachedSteps: finalizeSegmentAttachedSteps,
    conditionFields: context.conditionFields,
    standardFactors: context.standardFactors,
  }),
})

const rulePackageIssue = ref<{ title: string; summary: string; details?: string; context?: string } | null>(null)
const {
  visible: publishReviewVisible,
  review: publishReview,
  request: requestPublishReview,
  complete: completePublishReview,
} = useRulePackagePublishReview()
const {
  segmentAttachedSteps: finalizeSegmentAttachedSteps,
  segmentPrimarySteps: finalizeSegmentPrimarySteps,
  segmentStepCount: finalizeSegmentStepCount,
  isSegmentStepsExpanded: isFinalizeSegmentStepsExpanded,
  toggleSegmentSteps: toggleFinalizeSegmentSteps,
} = useRouteSegmentSteps(supersetOperations)
const {
  cancelInlineEdit,
  clearAllDrafts,
  drafts,
  inlineEditingSegmentId,
  inlineEditingText,
  persistDrafts,
  readDrafts,
  resetInlineEdit,
  saveInlineEdit,
  setConditionTextDraft,
  setInlineTextareaRef,
  startInlineEdit,
} = useFinalizeDrafts(projectId)

const segmentCards = computed(() => {
  const routeData = savedRoute.value
  if (!routeData) return []
  return buildFinalizeCards(routeData.segments, operations.value, drafts.value)
})

const mainlineRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'mainline').length)
const conditionalCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'conditional'))
const relationCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'relation'))
const reviewableCards = computed(() => [...conditionalCards.value, ...relationCards.value])
const conditionalRuleCount = computed(() => conditionalCards.value.length)
const relationRuleCount = computed(() => relationCards.value.length)
const reviewableRuleCount = computed(() => reviewableCards.value.length)
const unresolvedRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'unresolved').length)
const pendingRuleCards = computed(() => segmentCards.value.filter(item => (
  needsFinalizeRuleReview(item, factorCatalogVersion.value)
)))
const reviewFocusCards = computed(() => buildPublishReviewFocusCards(
  segmentCards.value,
  itemNeedsPending,
  locatedPublishBlockerId.value,
))
const lastExportedRulePackageVersion = computed(() => currentPublishedPackage.value?.version || null)
const currentPublishedPackageId = computed(() => currentPublishedPackage.value?.id || null)
const visibleSegments = computed(() => onlyPending.value ? reviewFocusCards.value : segmentCards.value)
const batchEligibleCards = computed(() => reviewableCards.value.filter((item) => {
  return requiresServerRuleConditionRefresh(item, factorCatalogVersion.value)
}))
const pendingReviewCards = computed(() => reviewableCards.value.filter((item) => {
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  return review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && (review.candidate?.kind || 'condition') === expectedKind
}))
const autoConfirmableReviewCards = computed(() => pendingReviewCards.value.filter(item => (
  isSafeForBatchRuleConfirmation(item, standardFactors.value, factorCatalogVersion.value)
)))
const confirmedRuleCount = computed(() => reviewableCards.value.filter(item => (
  !needsFinalizeRuleReview(item, factorCatalogVersion.value)
)).length)
const allCurrentRulesConfirmed = computed(() =>
  factorCatalogReady.value
  && pendingRuleCards.value.length === 0,
)
const conditionProcessOptions = computed<RuleConditionProcessOption[]>(() => {
  const options = new Map<string, RuleConditionProcessOption>()
  segmentCards.value.forEach((item) => {
    const processId = exportProcessIdForItem(item)
    if (!processId || options.has(processId)) return
    options.set(processId, {
      process_id: processId,
      display_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
      main: finalizeRuleMode(item) === 'mainline',
    })
  })
  return Array.from(options.values())
})

const finalizeNavSummary = computed(() => {
  if (!projectId.value) return '请先完成第三步规则分析，再进入规则定稿。'
  if (loading.value) return '正在装载第四步定稿结果。'
  if (error.value) return '当前没有可预览的定稿结果，请返回规则分析。'
  if (!segmentCards.value.length) return '当前没有可展示的工序，请先在第三步完成至少一版规则分析结果。'
  if (unresolvedRuleCount.value) return `还有 ${unresolvedRuleCount.value} 道工序需要补充具体条件。`
  if (confirmedRuleCount.value < reviewableRuleCount.value) {
    return `还有 ${reviewableRuleCount.value - confirmedRuleCount.value} 条规则待人工审核，请先完成规则审核。`
  }
  if (!allCurrentRulesConfirmed.value) return '存在需要人工处理的规则，请完成规则审核。'
  if (outdatedRulePackageVersion.value) return `规则内容已有变化，原规则包 V${outdatedRulePackageVersion.value} 已过期，请重新发布。`
  if (!lastExportedRulePackageVersion.value) return '规则审核已完成，可以发布规则包。'
  return `规则包 V${lastExportedRulePackageVersion.value} 已发布，可以下载或进入路线生成。`
})

/** Progress percent for the mini progress bar */
const reviewProgressPercent = computed(() =>
  reviewableRuleCount.value === 0 ? 0 : Math.round((confirmedRuleCount.value / reviewableRuleCount.value) * 100)
)
/** Whether a given nav item needs attention */
function itemNeedsPending(item: FinalizeCard): boolean {
  return needsFinalizeRuleReview(item, factorCatalogVersion.value)
}

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



function toggleOnlyPending() {
  onlyPending.value = !onlyPending.value
}

function blockedPublishStatusLabel(item: FinalizeCard) {
  if (finalizeRuleMode(item) === 'unresolved') return '待补充条件'
  if (item.conditionReview?.status === 'invalid') return '未能识别'
  if (
    item.conditionReview?.status === 'pending_confirmation'
    && item.conditionReview.candidate
    && item.conditionReview.source_text.trim() === item.conditionText.trim()
  ) {
    return '待审核候选'
  }
  return '需要重新识别'
}

function createBlockedPublishReview(cards: FinalizeCard[]): RulePackagePublishReview {
  return {
    status: 'blocked',
    projectName: projectName.value || '未命名任务',
    processCount: segmentCards.value.length,
    ruleCount: reviewableRuleCount.value,
    validation: null,
    kmaiCompatibility: null,
    manualFactors: [],
    rulePackage: null,
    details: cards.map(item => ({
      code: 'fourth_step_rule_incomplete',
      message: blockedPublishStatusLabel(item),
      processName: finalizeSegmentDisplayName(item.segment),
      sourceText: item.conditionText,
      sourceSegmentId: item.segment.id,
    })),
  }
}

async function locatePublishBlocker(sourceSegmentId: string) {
  await locatePublishBlockerInReview({
    sourceSegmentId,
    onlyPending,
    activeSegmentId,
    locatedSegmentId: locatedPublishBlockerId,
    completeReview: completePublishReview,
    getElementById: id => document.getElementById(id),
  })
}

function closeRulePackageIssue() {
  rulePackageIssue.value = null
}

function showFinalizeNotice(title: string, summary: string, details = '') {
  rulePackageIssue.value = { title, summary, details, context: '规则定稿' }
}

let handleWorkflowConflict = async (_error: unknown) => false

const conditionReviewQueue = useConditionReviewQueue({
  projectId,
  savedRoute,
  segmentCards,
  batchEligibleCards,
  autoConfirmableReviewCards,
  pendingRuleCards,
  conditionProcessOptions,
  factorCatalogReady,
  standardFactors,
  factorCatalogError,
  onlyPending,
  activeSegmentId,
  displayName: finalizeSegmentDisplayName,
  onPublishedRuleOutdated: markPublishedRulePackageOutdated,
  onConditionTextDraft: setConditionTextDraft,
  onNotice: showFinalizeNotice,
  onWorkflowConflict: errorValue => handleWorkflowConflict(errorValue),
})

const {
  conditionBusySegmentIds,
  batchParsing,
  batchParseCompleted,
  batchParseTotal,
  batchReviewing,
  batchReviewCompleted,
  batchReviewTotal,
  reviewingRules,
  batchNotice,
  beginConditionBusy,
  setBatchNotice,
  asErrorMessage: conditionErrorMessage,
  parseConditionItem,
  handleParseCondition,
  handleBatchParseConditions,
  handleConfirmCondition,
  handleSetMainline,
  handleSetBoolean,
  handleRuleReview: runRuleReview,
  cancelPendingRequests,
} = conditionReviewQueue

const workflowConflict = useFinalizeWorkflowConflict({
  projectId,
  savedRoute,
  workspaceError: error,
  onlyPending,
  loadWorkspace,
  clearAllDrafts,
  cancelPendingRequests,
  getRecognitionQueue: () => [...batchEligibleCards.value],
  runRecognitionQueue: (queue, isCurrent) => handleBatchParseConditions(queue, isCurrent),
  showIssue: showFinalizeNotice,
  setBatchNotice,
  errorMessage: conditionErrorMessage,
})

handleWorkflowConflict = workflowConflict.handleWorkflowRevisionConflict

const {
  resetDialogVisible,
  resettingWorkflow,
  cancelInFlightWork,
  handleWorkflowResetSignal,
  handleResetAllRecognition,
} = workflowConflict

async function handleSaveInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  const sourceText = inlineEditingText.value.trim()
  const changed = saveInlineEdit(item)
  if (!changed) return
  markPublishedRulePackageOutdated()
  const finishBusy = beginConditionBusy(item.segment.id)
  try {
    await nextTick()
    await parseConditionItem(item, true, sourceText)
  } catch (errorValue: unknown) {
    showFinalizeNotice('规则识别失败', '修改内容已保存在本机草稿，请稍后重试识别。', conditionErrorMessage(errorValue))
  } finally {
    finishBusy()
  }
}

async function handleResetInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  resetInlineEdit(item)
  markPublishedRulePackageOutdated()
  const finishBusy = beginConditionBusy(item.segment.id)
  try {
    await nextTick()
    await parseConditionItem(item, false, item.defaultConditionText)
  } catch (errorValue: unknown) {
    showFinalizeNotice('规则识别失败', '默认条件已恢复，请稍后重试识别。', conditionErrorMessage(errorValue))
  } finally {
    finishBusy()
  }
}

function finalizeSegmentDisplayName(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayName(segment)
}

function finalizeSegmentMetaLabel(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayMetaLabel(segment)
}

const {
  publishingRulePackage,
  publishRulePackage,
} = useFinalizeRulePackagePublish({
  projectId,
  projectName,
  savedRoute,
  segmentCards,
  displayName: finalizeSegmentDisplayName,
  metaLabel: finalizeSegmentMetaLabel,
  phaseLabel: resolveFinalizePhase,
  primarySteps: finalizeSegmentPrimarySteps,
  attachedSteps: finalizeSegmentAttachedSteps,
  conditionFields,
  standardFactors,
  factorCatalogVersion,
  onBlockedCards: async (cards) => {
    onlyPending.value = true
    await requestPublishReview(createBlockedPublishReview(cards))
  },
  onPublishIssue: (issue) => {
    rulePackageIssue.value = { ...issue, context: '规则包发布' }
  },
  onPublishReviewRequired: requestPublishReview,
  onPublished: (packageValue: SaveFinalizedRulePackageResponse) => {
    currentPublishedPackage.value = packageValue
    outdatedRulePackageVersion.value = null
    setBatchNotice(`规则包 V${packageValue.version} 已发布。`)
  },
  onWorkflowConflict: () => workflowConflict.reloadAfterKnownConflict(),
})

const {
  downloadingRulePackage,
  downloadCurrentRulePackage,
} = useFinalizedRulePackageDownload({
  packageId: currentPublishedPackageId,
  packageVersion: lastExportedRulePackageVersion,
  projectName,
  onDownloadIssue: (issue) => {
    rulePackageIssue.value = { ...issue, context: '规则包下载' }
  },
})

const rulePackageActionState = computed(() => ({
  resetting: resettingWorkflow.value,
  parsing: batchParsing.value,
  reviewing: batchReviewing.value || reviewingRules.value,
  publishing: publishingRulePackage.value,
  downloading: downloadingRulePackage.value,
  hasSegments: Boolean(segmentCards.value.length),
  factorCatalogReady: factorCatalogReady.value,
  hasReviewWork: Boolean(batchEligibleCards.value.length || autoConfirmableReviewCards.value.length),
  allRulesConfirmed: allCurrentRulesConfirmed.value,
  currentVersion: lastExportedRulePackageVersion.value,
}))
const actionDisabled = computed(() => rulePackageActionDisabled(rulePackageActionState.value))
const reviewButtonLabel = computed(() => reviewActionLabel(
  rulePackageActionState.value,
  batchParsing.value ? batchParseCompleted.value : batchReviewCompleted.value,
  batchParsing.value ? batchParseTotal.value : batchReviewTotal.value,
))
const publishButtonLabel = computed(() => publishActionLabel(rulePackageActionState.value))
const downloadButtonLabel = computed(() => downloadActionLabel(rulePackageActionState.value))

async function handleRuleReview() {
  if (
    publishingRulePackage.value
    || downloadingRulePackage.value
  ) return
  await runRuleReview()
}

function goBackToAnalysis() {
  router.push({
    path: '/analysis',
    query: buildProjectRouteQuery(projectId.value),
  })
}

function goToGenerate() {
  router.push({
    path: '/generate',
    query: buildProjectRouteQuery(projectId.value),
  })
}

async function reloadWorkspace() {
  await loadWorkspace(true)
}

watch(() => route.query.project_id, () => {
  if (!finalizeViewActive) return
  cancelInFlightWork()
  void loadWorkspace()
})

watch(workflowResetSignal, (signal) => {
  void handleWorkflowResetSignal(signal)
})

watch(drafts, () => {
  persistDrafts()
}, { deep: true })

watch([visibleSegments, onlyPending], () => {
  syncActiveSegment()
}, { deep: true })

onMounted(async () => {
  try {
    await loadWorkspace()
  } finally {
    initialLoadFinished = true
  }
})

onActivated(() => {
  finalizeViewActive = true
  if (!initialLoadFinished || loading.value) return

  const routeProjectId = Number(route.query.project_id || 0)
  const projectChanged = routeProjectId > 0 && routeProjectId !== projectId.value
  if (!projectChanged && loadedDataRevision.value === getWorkflowDataRevision()) return
  void loadWorkspace()
})

onDeactivated(() => {
  finalizeViewActive = false
  cancelInFlightWork()
  loadedDataRevision.value = getWorkflowDataRevision()
})
</script>

<style scoped>
.finalize-view {
  --workflow-nav-right-inset: 0px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: #f8fafc;
}

.analysis-style-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 5px 12px;
  box-shadow: 0 1.5px 5px rgba(15, 23, 42, 0.02);
  margin-bottom: 12px;
}

.ash-meta-stale {
  color: #9a3412;
  background: #fff7ed;
  border-color: #fed7aa;
}

.ash-left-content {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.ash-page-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  flex-shrink: 0;
}

.ash-dark-chip {
  background: #e8ecf4;
  color: #3d4f6a;
  border: 1px solid #c9d3e3;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 11.5px;
  font-weight: 600;
  flex-shrink: 0;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.ash-meta-section {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-left: 10px;
  border-left: 1px solid #cbd5e1;
  padding-left: 12px;
}

.ash-meta-item {
  font-size: 12.5px;
  color: #64748b;
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.ash-meta-item strong {
  color: #0f172a;
  font-weight: 700;
}

.ash-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ash-btn-outline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border: 1px solid #6366f1;
  color: #6366f1;
  padding: 3px 12px;
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.ash-btn-outline:hover:not(:disabled) { background: #f5f3ff; border-color: #4f46e5; color: #4f46e5; }
.ash-btn-outline:disabled { opacity: 0.45; cursor: not-allowed; border-color: #cbd5e1; color: #94a3b8; }

.ash-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 12px;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  background: #4f46e5;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.ash-btn-primary:hover:not(:disabled) { background: #4338ca; border-color: #4338ca; }
.ash-btn-primary:disabled { opacity: .45; cursor: not-allowed; }

.warning-text { color: #b4532f !important; }
.batch-notice {
  margin: -4px 0 10px;
  padding: 8px 12px;
  border: 1px solid #cbd8e8;
  border-radius: 8px;
  background: #f4f7fb;
  color: #4d607b;
  font-size: 12px;
  line-height: 1.5;
}
.factor-catalog-error { display: flex; align-items: center; justify-content: space-between; border-color: #e6bd7a; background: #fff8e8; color: #7a5314; }

.highlight-text { color: #ea580c !important; }

/* ===== Phase-active button highlight ===== */
.ash-btn-primary.ash-btn-phase-active {
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.30), 0 4px 12px rgba(79, 70, 229, 0.25);
  transform: translateY(-1px);
}
.ash-btn-outline.ash-btn-phase-active {
  border-color: #4f46e5;
  color: #4338ca;
  background: #eef2ff;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.22), 0 4px 12px rgba(99, 102, 241, 0.12);
  transform: translateY(-1px);
}

/* ===== Toggle filter (审核重点 switch) ===== */
.toggle-filter-wrap {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  cursor: pointer;
  user-select: none;
  padding: 3px 0;
}
.toggle-filter-input { display: none; }
.toggle-filter-track {
  position: relative;
  width: 32px; height: 18px;
  background: #cbd5e1;
  border-radius: 999px;
  transition: background 0.22s ease;
  flex-shrink: 0;
}
.toggle-filter-track--on { background: #6366f1; }
.toggle-filter-thumb {
  position: absolute;
  top: 2px; left: 2px;
  width: 14px; height: 14px;
  background: #ffffff;
  border-radius: 50%;
  box-shadow: 0 1px 3px rgba(0,0,0,0.18);
  transition: transform 0.22s ease;
}
.toggle-filter-track--on .toggle-filter-thumb { transform: translateX(14px); }
.toggle-filter-text {
  font-size: 12px; font-weight: 600; color: #64748b; white-space: nowrap;
}
.toggle-filter-track--on ~ .toggle-filter-text { color: #4f46e5; }
.toggle-filter-disabled { opacity: 0.45; cursor: not-allowed; }

/* ===== Icon refresh button ===== */
.icon-refresh-btn {
  display: inline-flex; align-items: center; justify-content: center;
  width: 30px; height: 30px;
  border: 1px solid #6366f1; border-radius: 8px;
  background: #ffffff; color: #6366f1;
  cursor: pointer; transition: all 0.15s ease;
  flex-shrink: 0;
}
.icon-refresh-btn:hover:not(:disabled) { background: #f5f3ff; border-color: #4f46e5; color: #4f46e5; }
.icon-refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; border-color: #cbd5e1; color: #94a3b8; }
.icon-refresh-btn--spinning svg { animation: spin 1s linear infinite; }
@keyframes spin { from { transform: rotate(0deg); } to { transform: rotate(360deg); } }

/* ===== Mini progress bar (in meta section) ===== */
.ash-meta-progress-item { gap: 6px !important; align-items: center; }
.mini-progress-bar {
  width: 52px; height: 4px;
  background: #e2e8f0; border-radius: 2px; overflow: hidden;
  flex-shrink: 0;
}
.mini-progress-fill {
  height: 100%; background: #6366f1; border-radius: 2px;
  transition: width 0.45s ease;
}
.mini-progress-fill--done { background: #22c55e; }
.text-done { color: #16a34a !important; }

.finalize-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  flex: 1;
  min-height: 0;
  height: auto;
}

.finalize-results {
  min-width: 0;
  overflow-y: auto;
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 12px 16px;
}

.export-issue-overlay {
  position: fixed;
  z-index: 50;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.48);
}

.export-issue-dialog {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 14px;
  width: min(560px, 100%);
  padding: 22px;
  border: 1px solid #d8e0eb;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 20px 46px rgba(15, 23, 42, 0.24);
}

.export-issue-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: #fff0e7;
  color: #b54708;
  font-size: 18px;
  font-weight: 800;
}

.export-issue-kicker {
  display: block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 12px;
  font-weight: 700;
}

.export-issue-dialog h2 {
  margin: 0;
  color: #0f172a;
  font-size: 18px;
  line-height: 1.4;
}

.export-issue-dialog p {
  margin: 8px 0 0;
  color: #475569;
  font-size: 14px;
  line-height: 1.65;
}

.export-issue-details {
  margin-top: 14px;
  border-top: 1px solid #e2e8f0;
  color: #475569;
  font-size: 12px;
}

.export-issue-details summary {
  padding-top: 12px;
  cursor: pointer;
  font-weight: 700;
}

.export-issue-details pre {
  max-height: 130px;
  overflow: auto;
  margin: 8px 0 0;
  padding: 10px;
  border-radius: 6px;
  background: #f8fafc;
  color: #475569;
  font: 12px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace;
  white-space: pre-wrap;
}

.export-issue-actions {
  display: flex;
  justify-content: flex-end;
  margin-top: 20px;
}

@media (max-width: 900px) {
  .finalize-view {
    --workflow-nav-right-inset: 0px;
    height: auto;
    min-height: 100%;
    overflow: visible;
  }

  .analysis-style-header {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 12px;
  }

  .ash-left-content {
    flex-wrap: wrap;
    gap: 8px 12px;
  }

  .ash-meta-section {
    margin-left: 0;
    border-left: none;
    padding-left: 0;
    width: 100%;
    flex-wrap: wrap;
    gap: 6px 12px;
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
