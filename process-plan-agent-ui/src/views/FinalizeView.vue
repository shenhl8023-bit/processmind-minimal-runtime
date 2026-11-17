<template>
  <div class="finalize-view">
    <div class="analysis-style-header workflow-page-header">
      <div class="ash-left-content workflow-page-info">
        <span class="ash-page-title workflow-page-title">规则定稿</span>
        <span class="ash-dark-chip" :title="projectName || '未命名任务'">{{ projectName || '未命名任务' }}</span>
        
        <div class="ash-meta-section">
          <span class="ash-meta-item">路线版本 <strong>V{{ savedRoute?.version || '-' }}</strong></span>
          <span class="ash-meta-item" v-if="lastExportedRulePackageVersion">可验证规则 <strong>V{{ lastExportedRulePackageVersion }}</strong></span>
          <span class="ash-meta-item ash-meta-stale" v-else-if="outdatedRulePackageVersion">规则已有修改，请重新生成路线验证</span>
          <span v-if="hasUnsavedEdits" class="ash-meta-item ash-meta-stale"><strong>未保存 {{ unsavedCards.length }} 项</strong></span>
          <span v-if="reviewableRuleCount" class="ash-review-progress">
            <span>已确认 <strong>{{ confirmedRuleCount }}/{{ reviewableRuleCount }}</strong></span>
          </span>
          <span v-else class="ash-meta-item">无需确认条件规则</span>
          <span v-if="pendingReviewCards.length" class="ash-meta-item ash-selection-count">待确认 <strong>{{ pendingReviewCards.length }}</strong> · 已选 <strong>{{ selectedReviewCards.length }}</strong></span>
        </div>

        <button
          v-if="precheckResult && canOpenPrecheck"
          type="button"
          class="ash-publish-state ash-publish-state--clickable"
          :class="{ 'ash-publish-state--blocked': !precheckResult.ok }"
          title="查看发布预检明细"
          @click="openPrecheckDialog"
        >
          <span class="ash-publish-state-dot" aria-hidden="true"></span>
          <strong v-if="!precheckResult.ok">预检待修复 {{ precheckBlockerCount }} 项</strong>
          <strong v-else>查看交付明细</strong>
        </button>
      </div>

      <div class="ash-actions workflow-page-actions">
        <div v-if="pendingReviewCards.length" class="ash-selection-actions" role="group" aria-label="批量选择规则">
          <button class="ash-quiet-action" type="button" :disabled="loading || !visiblePendingReviewCards.length || batchReviewing || batchParsing || resettingWorkflow || exportingRulePackage" @click="toggleSelectAllPending">{{ allPendingSelected ? '取消全选' : '全选当前项' }}</button>
          <button class="ash-btn-outline" type="button" :disabled="loading || !selectedReviewCards.length || batchReviewing || batchParsing || resettingWorkflow || exportingRulePackage" @click="handleConfirmSelectedCandidates">确认已选（{{ selectedReviewCards.length }}）</button>
        </div>
        <button
          class="ash-quiet-action"
          type="button"
          title="重新识别尚未确认的工序规则"
          aria-label="重新识别尚未确认的工序规则"
          @click="openResetDialog"
          :disabled="loading || resettingWorkflow || batchParsing || batchReviewing || exportingRulePackage || !savedRoute"
        >重新识别</button>
        <button
          class="ash-btn-outline"
          type="button"
          @click="handleConfirmAllCandidates"
          :disabled="loading || Boolean(error) || resettingWorkflow || reviewAndExporting || batchParsing || batchReviewing || exportingRulePackage || !segmentCards.length"
        >
          {{ batchReviewing ? `正在确认 ${batchReviewCompleted}/${batchReviewTotal}` : '确认全部规则' }}
        </button>
      </div>
    </div>

    <div v-if="workspaceLoading" class="empty-state card" role="status">
      <div class="empty-mark">···</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.loadingTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.loadingText }}</div>
    </div>

    <div v-else-if="!projectId" class="empty-state card">
      <div class="empty-mark">04</div>
      <div class="empty-title">{{ FINALIZE_VIEW_COPY.emptyProjectTitle }}</div>
      <div class="empty-text">{{ FINALIZE_VIEW_COPY.emptyProjectText }}</div>
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

    <div v-else class="finalize-layout" :aria-busy="loading">
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
        :pending-item-count="reviewFocusCards.length"
        @focus="focusSegment"
        @toggle-steps="toggleFinalizeSegmentSteps"
        @filter-change="onlyPending = $event"
      />

      <section class="finalize-results">
        <div v-if="!visibleSegments.length" class="finalize-empty-state">
          <span>暂无待处理工序</span>
          <button class="ash-template-link" type="button" @click="onlyPending = false">查看全部规则</button>
        </div>


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
          :route-segments="savedRoute?.segments || []"
          :process-options="conditionProcessOptions"
          :condition-busy="conditionBusySegmentIds.has(item.segment.id)"
          :actions-disabled="loading || batchParsing || batchReviewing || resettingWorkflow || exportingRulePackage"
          :condition-error="conditionErrors[item.segment.id]"
          :selectable="pendingReviewCards.some(card => card.segment.id === item.segment.id)"
          :selected="selectedRuleIds.has(item.segment.id)"
          @toggle-selected="toggleRuleSelection"
          :set-inline-textarea-ref="setInlineTextareaRef"
          @reset="handleResetInlineEdit"
          @start-edit="handleStartInlineEdit"
          @cancel="cancelInlineEdit"
          @save="handleSaveInlineEdit"
          @parse-condition="handleParseCondition"
          @confirm-condition="handleConfirmCondition"
          @edit-state="setRuleEditState"
          @set-mainline="handleSetMainline"
          @set-boolean="handleSetBoolean"
          @save-configuration="handleSaveConfiguration"
          @update:inline-editing-text="inlineEditingText = $event"
        />
      </section>
    </div>

    <WorkflowNavFooter
      :summary="finalizeNavSummary"
      :notices="finalizeNotices"
      previous-label="← 返回规则分析"
      next-label="保存并进入路线验证 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId || loading || Boolean(error) || resettingWorkflow || reviewAndExporting || batchParsing || batchReviewing || exportingRulePackage || !segmentCards.length || hasUnsavedEdits || publishBlockingCount > 0"
      @previous="goBackToAnalysis"
      @next="handleReviewAndExport"
    />

    <div v-if="blockedExportCards.length" class="export-blocker-overlay" @click.self="closeBlockedExportDialog">
      <section class="export-blocker-dialog" role="dialog" aria-modal="true" aria-labelledby="export-blocker-title">
        <div class="export-blocker-header">
          <div>
            <span class="export-blocker-kicker">规则定稿检查</span>
            <h2 id="export-blocker-title">还有 {{ blockedExportCards.length }} 道规则需要确认</h2>
          </div>
          <button class="export-blocker-close" aria-label="关闭提示" @click="closeBlockedExportDialog">✕</button>
        </div>
        <p class="export-blocker-copy">请先核对并确认候选规则，补齐缺失条件后再发布。</p>
        <div v-for="group in blockedExportGroups" :key="group.key" class="export-blocker-group">
          <div class="export-blocker-group-head">
            <strong>{{ group.label }}</strong>
            <span>{{ group.cards.length }} 项</span>
          </div>
          <ol class="export-blocker-list">
            <li v-for="item in group.cards" :key="item.segment.id" class="export-blocker-list-item export-blocker-list-item--clickable" @click="locateBlockedCard(item.segment.id)">
              <span>{{ item.segment.sequence }}</span>
              <strong>{{ finalizeSegmentDisplayName(item.segment) }}</strong>
              <em>{{ exportBlockedReasonLabel(item) }}</em>
            </li>
          </ol>
        </div>
        <div class="export-blocker-actions">
          <button class="ash-btn-outline" @click="closeBlockedExportDialog">暂不处理</button>
          <button class="ash-btn-primary" @click="handleBlockedExportPrimaryAction">{{ blockedExportPrimaryActionLabelText }}</button>
        </div>
      </section>
    </div>

    <div v-if="exportIssue" class="export-issue-overlay" @click.self="closeExportIssue">
      <section class="export-issue-dialog" role="dialog" aria-modal="true" aria-labelledby="export-issue-title">
        <div class="export-issue-icon" aria-hidden="true">!</div>
        <div class="export-issue-content">
          <span class="export-issue-kicker">{{ exportIssue.context || '规则包发布' }}</span>
          <h2 id="export-issue-title">{{ exportIssue.title }}</h2>
          <p>{{ exportIssue.summary }}</p>
          <details v-if="exportIssue.details" class="export-issue-details">
            <summary>查看检查详情</summary>
            <pre>{{ exportIssue.details }}</pre>
          </details>
          <div class="export-issue-actions">
            <button class="ash-btn-primary" @click="closeExportIssue">知道了</button>
          </div>
        </div>
      </section>
    </div>

    <FinalizePublishPrecheckDialog
      v-if="showPrecheckDialog && precheckResult"
      :result="precheckResult"
      @close="showPrecheckDialog = false"
      @open-template-mapping="handlePrecheckTemplateMapping"
      @open-rule-review="handlePrecheckRuleReview"
    />

    <WorkflowResetDialog
      v-model="resetDialogVisible"
      :title="ruleFinalizeResetCopy.title"
      :description="ruleFinalizeResetCopy.description"
      :keep-items="ruleFinalizeResetCopy.keepItems"
      :clear-items="ruleFinalizeResetCopy.clearItems"
      :confirm-label="ruleFinalizeResetCopy.confirmLabel"
      :busy-label="ruleFinalizeResetCopy.busyLabel"
      :busy="resettingWorkflow"
      @confirm="handleResetAllRecognition"
    />

  </div>
</template>

<script setup lang="ts">
import { resetCopyForEdition } from '@/composables/workflowResetCopy'
import { templateMappingVisible } from '@/composables/productStatus'
import { validateAuthoredCandidate } from '@/utils/processConfigurationEditor'

const ruleFinalizeResetCopy = computed(() => resetCopyForEdition('finalize', templateMappingVisible.value))

import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import FinalizeRouteNav from '@/components/finalize/FinalizeRouteNav.vue'
import FinalizePublishPrecheckDialog from '@/components/finalize/FinalizePublishPrecheckDialog.vue'
import { nextPendingSegmentId } from '@/utils/finalizeRulePresentation'
import FinalizeRuleCard from '@/components/finalize/FinalizeRuleCard.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'
import WorkflowResetDialog from '@/components/workflow/WorkflowResetDialog.vue'
import {
  getSavedNormalizedRoute,
  getSupersetRoute,
  listOperations,
  listProjects,
  type RulePackagePrecheckResult,
  resetWorkflow,
  enterRuleFinalization,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  confirmRuleCondition,
  getConditionFieldRegistry,
  getRulePreprocessingStatus,
  parseRuleCondition,
  saveRuleConditionDraft,
  startRulePreprocessing,
  setManualRuleCondition,
  saveProcessConfiguration,
  type CanonicalConditionField,
  type RuleConditionCandidate,
  type RuleConditionProcessOption,
  type RuleConditionReview,
  type RulePreprocessStatus,
} from '@/api/rulePackages'
import {
  segmentDisplayMetaLabel,
  segmentDisplayName,
} from '@/composables/analysisWorkspaceHelpers'
import {
  buildFinalizeCards,
  resolveFinalizePhase,
} from '@/composables/finalizeViewHelpers'
import { openFinalizePrecheckDialog } from '@/composables/finalizePrecheckDialog'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { confirmFinalizeBatch, type FinalizeBatchResult } from '@/composables/finalizeBatchConfirmation'
import { useFinalizeDrafts } from '@/composables/useFinalizeDrafts'
import { useFinalizeUnsavedEdits } from '@/composables/useFinalizeUnsavedEdits'
import { useFinalizeRuleRevision } from '@/composables/useFinalizeRuleRevision'
import { getLatestExecutableRuleRevision, saveExecutableRuleRevision } from '@/api/executableRules'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { buildRulePreprocessFailureSummary, buildRulePreprocessingTriggerKey } from '@/composables/rulePreprocessingTrigger'
import { buildProjectRouteQuery, resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { clearWorkflowProjectDataCache, createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'
import { isWorkflowRevisionConflict, publishWorkflowReset, workflowResetSignal } from '@/composables/workflowResetState'
import { createBackgroundTaskGuard } from '@/composables/runBackgroundTask'
import {
  buildManualBooleanRuleCandidate,
  exportProcessIdForItem,
  exportBlockingCards,
  blockedExportPrimaryActionLabel,
  exportBlockedReasonLabel,
  groupExportBlockedCards,
  finalizeRuleMode,
  isExplicitMainlineInstruction,
  hasCurrentConfirmedUserRule,
  normalizeExportProcessName,
  requiresServerRuleConditionRefresh,
  requiresConfirmedUserRule,
} from '@/utils/finalizeRulePackage'

const route = useRoute()
const router = useRouter()
let finalizeViewActive = false
let locallyHandledResetAt = 0
const workspaceRequestGuard = createLatestWorkflowRequestGuard()
let loadingProjectId = ''

const loading = ref(true)
const error = ref('')
const workspaceErrorTitle = ref<string>(FINALIZE_VIEW_COPY.errorTitle)
const projectId = ref<number | null>(null)
const projectName = ref('')
const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
// Same-project refreshes keep mounted cards and their disclosure state. A new
// project must never display the previous project's route while it is loading.
const workspaceLoading = computed(() => loading.value && (!savedRoute.value
  || savedRoute.value.project_id !== Number(route.query.project_id || projectId.value)))
const operations = ref<OperationItem[]>([])
const supersetOperations = ref<OperationItem[]>([])
const onlyPending = ref(true)
const selectedRuleIds = ref(new Set<string>())
const conditionErrors = ref<Record<string, string>>({})
const activeSegmentId = ref('')
const executableRevisionCounter = ref(0)
const lastExportedRulePackageVersion = ref<number | null>(null)
const outdatedRulePackageVersion = ref<number | null>(null)
const conditionFields = ref<CanonicalConditionField[]>([])
const conditionBusySegmentIds = ref(new Set<string>())
const conditionBusyCounts = new Map<string, number>()
const batchParsing = ref(false)
const batchReviewing = ref(false)
const batchReviewCompleted = ref(0)
const batchReviewTotal = ref(0)
const batchConfirmationResult = ref<FinalizeBatchResult | null>(null)
const batchConfirmationIssues = computed(() => batchConfirmationResult.value?.items.filter(item => item.status !== 'confirmed') || [])
const preprocessStatus = ref<RulePreprocessStatus | null>(null)
const preprocessFailureSummary = computed(() => buildRulePreprocessFailureSummary(preprocessStatus.value))
const precheckResult = ref<RulePackagePrecheckResult | null>(null)
const showPrecheckDialog = ref(false)
let preprocessPollTimer: ReturnType<typeof window.setTimeout> | null = null
let preprocessRefreshInFlight: symbol | null = null
let preprocessEpoch = 0
let lastRulePreprocessTriggerKey = ''
const reviewAndExporting = ref(false)
const batchNotice = ref('')
const validationIssue = ref('')
const resetDialogVisible = ref(false)
const resettingWorkflow = ref(false)
let batchNoticeTimer: ReturnType<typeof setTimeout> | null = null
let workflowConflictReload: Promise<void> | null = null
const recognitionTaskGuard = createBackgroundTaskGuard()

function setBatchNotice(msg: string) {
  batchNotice.value = msg
  if (batchNoticeTimer) clearTimeout(batchNoticeTimer)
  if (msg) {
    batchNoticeTimer = setTimeout(() => { batchNotice.value = '' }, 4000)
  }
}
const blockedExportCards = ref<FinalizeCard[]>([])
const blockedExportGroups = computed(() => {
  const grouped = groupExportBlockedCards(blockedExportCards.value)
  return [
    { key: 'pending_candidate', label: '待审核候选', cards: grouped.pendingCandidateCards },
    { key: 'missing_condition', label: '待补充条件', cards: grouped.missingConditionCards },
    { key: 'rebuild_required', label: '需要重新识别', cards: grouped.rebuildRequiredCards },
  ].filter(group => group.cards.length)
})
const blockedExportPrimaryActionLabelText = computed(() => blockedExportPrimaryActionLabel(blockedExportCards.value))
const exportIssue = ref<{ title: string; summary: string; details?: string; context?: string } | null>(null)
const {
  segmentAttachedSteps: finalizeSegmentAttachedSteps,
  segmentPrimarySteps: finalizeSegmentPrimarySteps,
  segmentStepNodes: finalizeSegmentStepNodes,
  segmentStepCount: finalizeSegmentStepCount,
  isSegmentStepsExpanded: isFinalizeSegmentStepsExpanded,
  toggleSegmentSteps: toggleFinalizeSegmentSteps,
} = useRouteSegmentSteps(supersetOperations)
const {
  cancelInlineEdit,
  clearAllDrafts,
  clearPersistedDraft,
  drafts,
  inlineEditingSegmentId,
  inlineEditingText,
  persistDrafts,
  readDrafts,
  resetInlineEdit,
  setInlineTextareaRef,
  startInlineEdit,
} = useFinalizeDrafts(projectId)

const segmentCards = computed(() => {
  const routeData = savedRoute.value
  if (!routeData) return []
  return buildFinalizeCards(routeData.segments, operations.value, drafts.value)
})

const { unsavedCards, hasUnsavedEdits, setRuleEditState, clearRuleEditStates } = useFinalizeUnsavedEdits(
  segmentCards, inlineEditingSegmentId, inlineEditingText,
)

const reviewableCards = computed(() => segmentCards.value.filter(requiresConfirmedUserRule))
const reviewableRuleCount = computed(() => reviewableCards.value.length)
const unresolvedRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'unresolved').length)
const reviewFocusCards = computed(() => {
  const pendingIds = new Set([
    ...exportBlockingCards(segmentCards.value).map(item => item.segment.id),
    ...unsavedCards.value.map(item => item.segment.id),
  ])
  return segmentCards.value.filter(item => pendingIds.has(item.segment.id))
})
const visibleSegments = computed(() => onlyPending.value ? reviewFocusCards.value : segmentCards.value)
const batchEligibleCards = computed(() => reviewableCards.value.filter((item) => {
  return requiresServerRuleConditionRefresh(item)
}))
const pendingReviewCards = computed(() => reviewableCards.value.filter((item) => {
  const review = item.conditionReview
  return !unsavedCards.value.some(card => card.segment.id === item.segment.id)
    && review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && Boolean(review.candidate && review.source_hash)
    && !requiresServerRuleConditionRefresh(item)
}))
const publishBlockingCount = computed(() => reviewFocusCards.value.length)
const precheckBlockerCount = computed(() => {
  if (!precheckResult.value) return 0
  return precheckResult.value.ok ? 0 : (precheckResult.value.blockers?.length || 1)
})
const canOpenPrecheck = computed(() => publishBlockingCount.value === 0 && Boolean(precheckResult.value))
const selectedReviewCards = computed(() => pendingReviewCards.value.filter(item => selectedRuleIds.value.has(item.segment.id)))
const visiblePendingReviewCards = computed(() => {
  const visibleIds = new Set(visibleSegments.value.map(item => item.segment.id))
  return pendingReviewCards.value.filter(item => visibleIds.has(item.segment.id))
})
const allPendingSelected = computed(() => visiblePendingReviewCards.value.length > 0 && visiblePendingReviewCards.value.every(item => selectedRuleIds.value.has(item.segment.id)))
const confirmedRuleCount = computed(() => reviewableCards.value.filter(item => (
  hasCurrentConfirmedUserRule(item) && !unsavedCards.value.some(card => card.segment.id === item.segment.id)
)).length)
function toggleRuleSelection(item: FinalizeCard) {
  const ids = new Set(selectedRuleIds.value)
  if (ids.has(item.segment.id)) ids.delete(item.segment.id)
  else ids.add(item.segment.id)
  selectedRuleIds.value = ids
}
function toggleSelectAllPending() {
  if (loading.value) return
  const ids = new Set(selectedRuleIds.value)
  if (allPendingSelected.value) {
    visiblePendingReviewCards.value.forEach(item => ids.delete(item.segment.id))
  } else {
    visiblePendingReviewCards.value.forEach(item => ids.add(item.segment.id))
  }
  selectedRuleIds.value = ids
}
const readyRuleCount = computed(() => reviewableCards.value.filter((item) => {
  if (hasCurrentConfirmedUserRule(item)) return true
  const review = item.conditionReview
  return review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && !requiresServerRuleConditionRefresh(item)
}).length)
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
const finalizeNotices = computed<WorkflowNotice[]>(() => {
  const notices: WorkflowNotice[] = []
  if (validationIssue.value) notices.push({ id: 'validation', level: 'error', summary: validationIssue.value, actions: [{ label: '关闭', run: () => { validationIssue.value = '' } }] })
  if (batchNotice.value) notices.push({ id: 'batch', level: 'info', summary: batchNotice.value })
  if (batchConfirmationResult.value) {
    const result = batchConfirmationResult.value
    notices.push({ id: 'confirmation', level: result.remainingCount ? 'warning' : 'success', summary: `本次已确认 ${result.successCount} 项，剩余 ${result.remainingCount} 项待处理`, detail: batchConfirmationIssues.value.map(item => `${item.sequence} · ${item.name}：${item.reason}`).join('\n') })
  }
  if (preprocessFailureSummary.value) {
    const failure = preprocessFailureSummary.value
    notices.push({ id: 'preprocess', level: 'error', summary: failure.title, detail: [failure.message, ...failure.lines, ...(failure.overflowCount ? [`另有 ${failure.overflowCount} 条失败记录`] : [])].join('\n'), actions: [{ label: '刷新结果', run: reloadWorkspace, disabled: loading.value || resettingWorkflow.value }] })
  }
  return notices
})

const finalizeNavSummary = computed(() => {
  if (loading.value) return '正在装载第四步定稿结果。'
  if (!projectId.value) return '请先完成第三步规则分析，再进入规则定稿。'
  if (error.value) return '当前没有可预览的定稿结果，请返回规则分析。'
  if (!segmentCards.value.length) return '当前没有可展示的工序，请先在第三步完成至少一版规则分析结果。'
  if (hasUnsavedEdits.value) return `有 ${unsavedCards.value.length} 项未保存，请先保存或取消修改后再进入验证。`
  if (unresolvedRuleCount.value) return `还有 ${unresolvedRuleCount.value} 道工序需要补充具体条件。`
  if (readyRuleCount.value < reviewableRuleCount.value) {
    if (batchParsing.value) {
      return `正在识别规则；当前 ${readyRuleCount.value}/${reviewableRuleCount.value} 条已识别。`
    }
    return `还有 ${reviewableRuleCount.value - readyRuleCount.value} 条规则待处理，可在对应卡片中补充条件或设置出现规则。`
  }
  if (reviewFocusCards.value.length) return `已确认 ${confirmedRuleCount.value}/${reviewableRuleCount.value} 条规则，请核对剩余待处理项。`
  if (precheckResult.value && !precheckResult.value.ok) return `发布预检有 ${precheckBlockerCount.value} 项待修复，请查看预检结果并处理。`
  if (outdatedRulePackageVersion.value) return '规则已修改，请保存后使用当前规则重新生成路线验证。'
  if (!lastExportedRulePackageVersion.value) return '规则已全部确认，可保存并进入路线验证。'
  return `可验证规则 V${lastExportedRulePackageVersion.value} 已就绪，可进入工艺路线验证。`
})

/** Whether a given nav item needs attention */
function itemNeedsPending(item: FinalizeCard): boolean {
  return reviewFocusCards.value.some(card => card.segment.id === item.segment.id)
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



function closeBlockedExportDialog() {
  blockedExportCards.value = []
}

async function locateBlockedCard(segmentId: string) {
  onlyPending.value = true
  blockedExportCards.value = []
  await nextTick()
  focusSegment(segmentId)
}
async function handleBlockedExportPrimaryAction() {
  const groups = groupExportBlockedCards(blockedExportCards.value)
  const first = groups.missingConditionCards[0] || groups.rebuildRequiredCards[0] || groups.pendingCandidateCards[0]
  if (first) await locateBlockedCard(first.segment.id)
}

function closeExportIssue() {
  exportIssue.value = null
}

function showFinalizeNotice(title: string, summary: string, details = '') {
  exportIssue.value = { title, summary, details, context: '规则定稿' }
}


function setConditionBusy(segmentId: string, busy: boolean) {
  const current = conditionBusyCounts.get(segmentId) || 0
  const nextCount = busy ? current + 1 : Math.max(0, current - 1)
  if (nextCount) conditionBusyCounts.set(segmentId, nextCount)
  else conditionBusyCounts.delete(segmentId)
  conditionBusySegmentIds.value = new Set(conditionBusyCounts.keys())
}

function hasCurrentConditionText(segmentId: string, sourceText: string, reviewToken?: string) {
  const current = segmentCards.value.find(item => item.segment.id === segmentId)
  return current?.conditionText.trim() === sourceText.trim()
    && (reviewToken === undefined || (current.conditionReview?.review_token ?? '') === reviewToken)
}

function isRuleWorkspaceCurrent(requestProject: number, requestRoute: number, requestRevision: number) {
  const reset = workflowResetSignal.value
  return projectId.value === requestProject
    && savedRoute.value?.route_id === requestRoute
    && savedRoute.value?.workflow_revision === requestRevision
    && (!reset || reset.projectId !== requestProject || reset.workflowRevision <= requestRevision)
}

function applyConditionReview(segmentId: string, review: RuleConditionReview) {
  const segment = savedRoute.value?.segments.find(item => item.id === segmentId)
  if (!segment) return
  if (!segment.rule_review) {
    segment.rule_review = {
      id: 0,
      decision: 'accepted',
      note: '',
      summary_lines: [],
      question_trail: [],
      created_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    }
  }
  segment.rule_review.condition_review = review
}

function conditionErrorMessage(err: any) {
  const detail = err?.response?.data?.detail
  if (typeof detail === 'string') return detail
  if (Array.isArray(detail)) return detail.map(item => item?.msg || item?.message || String(item)).join('\n')
  if (detail?.issues) return [detail.message, ...detail.issues].filter(Boolean).join('\n')
  return detail?.message || err?.message || '规则条件处理失败'
}

function isConditionSourceConflict(err: any) {
  return Number(err?.response?.status) === 409
    && /条件文字已经发生变化|重新解析后再确认/.test(conditionErrorMessage(err))
}

async function handleWorkflowRevisionConflict(err: any) {
  if (!isWorkflowRevisionConflict(err)) return false
  if (hasUnsavedEdits.value) {
    showFinalizeNotice('页面状态已过期', '上游步骤已经重新处理。当前未保存修改仍保留，请先复制备份或取消修改，再刷新结果。')
    return true
  }
  showFinalizeNotice('页面状态已过期', '上游步骤已经重新处理，系统正在加载最新结果。')
  if (!workflowConflictReload) {
    workflowConflictReload = loadWorkspace(true).finally(() => {
      workflowConflictReload = null
    })
  }
  await workflowConflictReload
  return true
}

function markExportedRulePackageOutdated() {
  precheckResult.value = null
  if (lastExportedRulePackageVersion.value) {
    outdatedRulePackageVersion.value = lastExportedRulePackageVersion.value
  }
  lastExportedRulePackageVersion.value = null
}

async function handleSaveInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  if (!projectId.value || !savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
  const sourceText = inlineEditingText.value.trim()
  if (sourceText === item.conditionText.trim()) { cancelInlineEdit(); return }
  if (!sourceText) return
  validationIssue.value = ''
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  delete conditionErrors.value[item.segment.id]
  setConditionBusy(item.segment.id, true)
  try {
    const response = await saveRuleConditionDraft({
      project_id: requestProject,
      route_id: requestRoute,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      source_text: sourceText,
    })
    if (!requestIsCurrent()) return
    markExportedRulePackageOutdated()
    applyConditionReview(item.segment.id, response.review)
    clearPersistedDraft(item.segment.id)
    if (inlineEditingSegmentId.value === item.segment.id && inlineEditingText.value.trim() === sourceText) cancelInlineEdit()
    if (isExplicitMainlineInstruction(sourceText, normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)))) {
      setBatchNotice('主线安排已保存，有未发布修改。')
      return
    }
    await nextTick()
    const parsed = await parseConditionItem(item, false, sourceText, () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision), response.review.review_token ?? '')
    setBatchNotice(parsed ? '修改已保存并识别，请核对后确认规则。' : '原文已保存，识别尚未完成，请稍后重试。')
  } catch (err: any) {
    if (!requestIsCurrent()) return
    if (await handleWorkflowRevisionConflict(err)) return
    conditionErrors.value[item.segment.id] = `保存失败，修改尚未保存：${conditionErrorMessage(err)}`
    showFinalizeNotice('规则保存失败', '修改内容仍在编辑框中，请重试保存。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleStartInlineEdit(item: FinalizeCard) {
  validationIssue.value = ''
  const editingAnotherItem = inlineEditingSegmentId.value && inlineEditingSegmentId.value !== item.segment.id
  if (editingAnotherItem && unsavedCards.value.some(card => card.segment.id === inlineEditingSegmentId.value)) {
    setBatchNotice('请先保存或取消正在编辑的原文，再修改另一条规则。')
    await locateBlockedCard(inlineEditingSegmentId.value!)
    return
  }
  startInlineEdit(item)
}

async function handleResetInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  if (!projectId.value || !savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
  validationIssue.value = ''
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  setConditionBusy(item.segment.id, true)
  try {
    const response = await saveRuleConditionDraft({
      project_id: requestProject,
      route_id: requestRoute,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      source_text: item.defaultConditionText,
    })
    if (!requestIsCurrent()) return
    resetInlineEdit(item)
    applyConditionReview(item.segment.id, response.review)
    markExportedRulePackageOutdated()
    if (isExplicitMainlineInstruction(item.defaultConditionText, normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)))) {
      setBatchNotice('默认主线安排已恢复，请重新发布规则包。')
      return
    }
    await nextTick()
    await parseConditionItem(item, false, item.defaultConditionText, () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision), response.review.review_token ?? '')
  } catch (err: any) {
    if (!requestIsCurrent()) return
    if (await handleWorkflowRevisionConflict(err)) return
    showFinalizeNotice('恢复默认失败', '请稍后重试，当前修改仍然保留。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function parseConditionItem(
  item: ReturnType<typeof buildFinalizeCards>[number],
  showError = false,
  sourceText = item.conditionText,
  isCurrent = () => true,
  expectedReviewToken = item.conditionReview?.review_token ?? '',
) {
  if (!isCurrent() || !projectId.value || !savedRoute.value) return false
  delete conditionErrors.value[item.segment.id]
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = expectedReviewToken
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, sourceText, requestReviewToken)
  setConditionBusy(item.segment.id, true)
  try {
    const response = await parseRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      source_text: sourceText,
      process_id: exportProcessIdForItem(item),
      process_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
      processes: conditionProcessOptions.value,
    })
    if (!isCurrent() || !requestIsCurrent() || !hasCurrentConditionText(item.segment.id, sourceText)) return false
    applyConditionReview(item.segment.id, response.review)
    return response.review.status !== 'invalid'
  } catch (err: any) {
    if (!isCurrent() || !requestIsCurrent()) return false
    if (await handleWorkflowRevisionConflict(err)) return false
    if (isCurrent() && projectId.value === requestProject && hasCurrentConditionText(item.segment.id, sourceText)) {
      conditionErrors.value[item.segment.id] = `识别失败，已保存的原文仍然保留：${conditionErrorMessage(err)}`
    }
    if (showError) {
      console.error('条件候选规则生成失败', err)
      showFinalizeNotice('暂时无法识别规则', '请补充明确的判断条件、比较关系或取值后重试。', conditionErrorMessage(err))
    }
    return false
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleParseCondition(item: ReturnType<typeof buildFinalizeCards>[number]) {
  validationIssue.value = ''
  await parseConditionItem(item, false)
}

async function handleConfirmAllCandidates() {
  if (batchReviewing.value || loading.value || error.value || resettingWorkflow.value || reviewAndExporting.value || batchParsing.value || exportingRulePackage.value || !projectId.value || !savedRoute.value) return
  validationIssue.value = ''
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  batchReviewing.value = true
  batchConfirmationResult.value = null
  try {
    const result = await confirmFinalizeBatch({
      cards: () => segmentCards.value,
      unsavedIds: () => new Set(unsavedCards.value.map(card => card.segment.id)),
      busyIds: () => conditionBusySegmentIds.value,
      isCurrent: () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision),
      displayName: card => finalizeSegmentDisplayName(card.segment),
      confirm: (card, candidate) => handleConfirmCondition(card, candidate, false, false),
      errorFor: id => conditionErrors.value[id],
      errorMessage: conditionErrorMessage,
      onProgress: (completed, total) => {
        batchReviewCompleted.value = completed
        batchReviewTotal.value = total
      },
    })
    if (result) {
      batchConfirmationResult.value = result
      setBatchNotice(`已确认 ${result.successCount} 项，剩余 ${result.remainingCount} 项待处理。`)
    }
  } finally {
    batchReviewing.value = false
  }
}

async function handleConfirmSelectedCandidates() {
  if (loading.value || batchReviewing.value || !selectedReviewCards.value.length || !projectId.value || !savedRoute.value) return
  validationIssue.value = ''
  const queue = [...selectedReviewCards.value]
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  batchReviewing.value = true
  batchReviewCompleted.value = 0
  batchReviewTotal.value = queue.length
  let successCount = 0
  try {
    for (const item of queue) {
      if (projectId.value !== requestProject || savedRoute.value?.route_id !== requestRoute || savedRoute.value?.workflow_revision !== requestRevision) break
      if (conditionBusySegmentIds.value.has(item.segment.id)) continue
      const current = selectedReviewCards.value.find(card => card.segment.id === item.segment.id)
      if (!current || current.conditionText !== item.conditionText || current.conditionReview?.source_hash !== item.conditionReview?.source_hash) continue
      if (await handleConfirmCondition(current, current.conditionReview!.candidate!, false)) successCount += 1
      batchReviewCompleted.value += 1
    }
  } finally {
    batchReviewing.value = false
    if (projectId.value === requestProject) {
      setBatchNotice(`已确认 ${successCount} 项，${queue.length - successCount} 项未完成。未完成项保留在待处理列表。`)
    }
  }
}

async function handleConfirmCondition(
  item: ReturnType<typeof buildFinalizeCards>[number],
  candidate: RuleConditionCandidate,
  advance = true,
  refreshOnConflict = true,
) {
  if (!projectId.value || !savedRoute.value || !item.conditionReview?.source_hash) return
  // A quick confirm and a background candidate refresh must not submit two
  // versions of the same card at once.
  if (conditionBusySegmentIds.value.has(item.segment.id)) return
  validationIssue.value = ''
  const authoringIssues = validateAuthoredCandidate(candidate, exportProcessIdForItem(item))
  if (authoringIssues.length) {
    conditionErrors.value[item.segment.id] = authoringIssues.join('；')
    return false
  }
  delete conditionErrors.value[item.segment.id]
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  setConditionBusy(item.segment.id, true)
  try {
    const response = await confirmRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      source_text: item.conditionText,
      source_hash: item.conditionReview.source_hash,
      candidate,
      processes: conditionProcessOptions.value,
      confirmed_by: '默认用户',
    })
    if (!requestIsCurrent() || !hasCurrentConditionText(item.segment.id, requestSource)) return false
    applyConditionReview(item.segment.id, response.review)
    if (response.review.status !== 'confirmed') {
      conditionErrors.value[item.segment.id] = '规则尚未确认，请核对后重试。'
      return false
    }
    markExportedRulePackageOutdated()
    selectedRuleIds.value.delete(item.segment.id)
    if (advance) {
      const nextId = nextPendingSegmentId(segmentCards.value, reviewFocusCards.value, item.segment.id)
      await nextTick()
      if (nextId) focusSegment(nextId)
    }
    return true
  } catch (err: any) {
    if (!requestIsCurrent()) return false
    if (!refreshOnConflict && isWorkflowRevisionConflict(err)) {
      const reason = conditionErrorMessage(err)
      conditionErrors.value[item.segment.id] = reason
      return { status: 'workflow_conflict' as const, reason }
    }
    if (await handleWorkflowRevisionConflict(err)) return
    if (isConditionSourceConflict(err)) {
      if (!refreshOnConflict) {
        conditionErrors.value[item.segment.id] = '规则内容已经变化，请核对最新内容后重试。'
        return false
      }
      const refreshed = await parseConditionItem(item, false)
      setBatchNotice(refreshed
          ? `"「${finalizeSegmentDisplayName(item.segment)}」"的候选已按最新条件更新，请核对后再审核。`
          : `"「${finalizeSegmentDisplayName(item.segment)}」"的条件已更新，请先补充条件后重新生成候选。`)
      return
    }
    conditionErrors.value[item.segment.id] = `确认失败，规则未生效：${conditionErrorMessage(err)}`
    return false
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleSaveConfiguration(
  item: ReturnType<typeof buildFinalizeCards>[number],
  candidate: RuleConditionCandidate,
) {
  if (!projectId.value || !savedRoute.value || !candidate.configuration || conditionBusySegmentIds.value.has(item.segment.id)) return
  validationIssue.value = ''
  const authoringIssues = validateAuthoredCandidate(candidate, exportProcessIdForItem(item))
  if (authoringIssues.length) {
    conditionErrors.value[item.segment.id] = authoringIssues.join('；')
    return false
  }
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  delete conditionErrors.value[item.segment.id]
  setConditionBusy(item.segment.id, true)
  try {
    const response = await saveProcessConfiguration({
      project_id: requestProject, route_id: requestRoute, expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id, process_id: exportProcessIdForItem(item),
      source_text: candidate.preview || item.conditionText, candidate, processes: conditionProcessOptions.value, confirmed_by: '用户直接设定',
    })
    if (!requestIsCurrent() || !hasCurrentConditionText(item.segment.id, requestSource)) return false
    if (response.review.status !== 'confirmed') {
      conditionErrors.value[item.segment.id] = '规则尚未保存，请核对后重试。'
      return false
    }
    applyConditionReview(item.segment.id, response.review)
    clearPersistedDraft(item.segment.id)
    markExportedRulePackageOutdated()
    selectedRuleIds.value.delete(item.segment.id)
    setBatchNotice(`“${finalizeSegmentDisplayName(item.segment)}”规则已保存。`)
    return true
  } catch (err: any) {
    if (!requestIsCurrent()) return false
    if (await handleWorkflowRevisionConflict(err)) return false
    conditionErrors.value[item.segment.id] = `保存失败，规则未生效：${conditionErrorMessage(err)}`
    return false
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleSetMainline(item: ReturnType<typeof buildFinalizeCards>[number]) {
  if (!projectId.value || !savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
  validationIssue.value = ''
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  const processName = normalizeExportProcessName(finalizeSegmentDisplayName(item.segment))
  const sourceText = `设置为主工序，始终纳入“${processName}”工序。`
  setConditionBusy(item.segment.id, true)
  try {
    const response = await saveRuleConditionDraft({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      source_text: sourceText,
    })
    if (!requestIsCurrent()) return
    applyConditionReview(item.segment.id, response.review)
    clearPersistedDraft(item.segment.id)
    markExportedRulePackageOutdated()
    setBatchNotice(`"「${processName}」"已转为主工序。`)
  } catch (err: any) {
    if (!requestIsCurrent()) return
    if (await handleWorkflowRevisionConflict(err)) return
    showFinalizeNotice('转换主工序失败', '当前工序尚未改变，请稍后重试。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleSetBoolean(
  item: ReturnType<typeof buildFinalizeCards>[number],
  label: string,
) {
  if (!projectId.value || !savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
  validationIssue.value = ''
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const requestReviewToken = item.conditionReview?.review_token ?? ''
  const requestSource = item.conditionText
  const requestIsCurrent = () => isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
    && hasCurrentConditionText(item.segment.id, requestSource, requestReviewToken)
  const processName = normalizeExportProcessName(finalizeSegmentDisplayName(item.segment))
  const switchLabel = label.trim()
  if (!switchLabel) return
  const sourceText = `当用户选择“${switchLabel}”为是时，纳入“${processName}”工序。`
  const candidate = buildManualBooleanRuleCandidate(item, switchLabel)
  setConditionBusy(item.segment.id, true)
  try {
    const response = await setManualRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: requestRevision,
      expected_review_token: requestReviewToken,
      segment_id: item.segment.id,
      process_id: exportProcessIdForItem(item),
      source_text: sourceText,
      candidate,
      processes: conditionProcessOptions.value,
      confirmed_by: '用户直接设定',
    })
    if (!requestIsCurrent()) return
    applyConditionReview(item.segment.id, response.review)
    clearPersistedDraft(item.segment.id)
    markExportedRulePackageOutdated()
    setBatchNotice(`"「${processName}」"已转为用户控制的 Bool 条件。`)
  } catch (err: any) {
    if (!requestIsCurrent()) return
    if (await handleWorkflowRevisionConflict(err)) return
    showFinalizeNotice('转换 Bool 条件失败', '当前工序尚未改变，请检查开关名称后重试。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

function finalizeSegmentDisplayName(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayName(segment)
}

function finalizeSegmentMetaLabel(segment: SavedNormalizedRouteVersionResult['segments'][number]) {
  return segmentDisplayMetaLabel(segment)
}

const { preparingValidation: exportingRulePackage, prepareValidation } = useFinalizeRuleRevision({
  projectId, projectName, savedRoute, cards: segmentCards, unsavedCards,
  savingRuleIds: conditionBusySegmentIds, displayName: finalizeSegmentDisplayName,
  phaseLabel: resolveFinalizePhase, primarySteps: finalizeSegmentPrimarySteps,
  attachedSteps: finalizeSegmentAttachedSteps, finalSteps: finalizeSegmentStepNodes,
  conditionFields, saveRevision: (payload) => saveExecutableRuleRevision(payload, executableRevisionCounter.value),
  onSaved: (revision) => {
    executableRevisionCounter.value = revision.revision
    lastExportedRulePackageVersion.value = revision.revision
    outdatedRulePackageVersion.value = null
    goToGenerate()
  },
  onIssue: (message) => { validationIssue.value = message },
  onBlocked: async (cards) => { if (cards[0]) await locateBlockedCard(cards[0].segment.id) },
})

async function handleReviewAndExport() {
  if (reviewAndExporting.value || batchParsing.value || batchReviewing.value || exportingRulePackage.value) return
  validationIssue.value = ''
  if (unsavedCards.value.length) {
    setBatchNotice(`有 ${unsavedCards.value.length} 项未保存，请先保存或取消修改后再进入验证。`)
    await locateBlockedCard(unsavedCards.value[0]!.segment.id)
    return
  }
  if (conditionBusySegmentIds.value.size) {
    setBatchNotice('请等待当前规则保存或识别完成后再发布。')
    return
  }
  reviewAndExporting.value = true
  precheckResult.value = null
  showPrecheckDialog.value = false
  exportIssue.value = null
  try {
    const remaining = exportBlockingCards(segmentCards.value)
    if (remaining.length) {
      setBatchNotice(`还有 ${remaining.length} 项待处理，请核对并确认后再发布。`)
      await locateBlockedCard(remaining[0].segment.id)
      return
    }
    await prepareValidation()
  } finally {
    reviewAndExporting.value = false
  }
}

function goToTemplateMapping() {
  if (templateMappingVisible.value) router.push({ path: '/template-mapping', query: buildProjectRouteQuery(projectId.value) })
}

function openPrecheckDialog() {
  openFinalizePrecheckDialog(showPrecheckDialog)
}

async function openResetDialog() {
  if (!await ensureRuleEditsSaved()) return
  resetDialogVisible.value = true
}

function handlePrecheckTemplateMapping() {
  showPrecheckDialog.value = false
  goToTemplateMapping()
}

async function handlePrecheckRuleReview(blocker: Record<string, any>) {
  showPrecheckDialog.value = false
  const segmentIds = [
    String(blocker.source_segment_id || '').trim(),
    ...(Array.isArray(blocker.segment_ids) ? blocker.segment_ids.map((id: unknown) => String(id).trim()) : []),
  ].filter(Boolean)
  const processIds = [
    String(blocker.process_id || '').trim(),
    ...(Array.isArray(blocker.target_process_ids) ? blocker.target_process_ids.map((id: unknown) => String(id).trim()) : []),
  ].filter(Boolean)
  const processName = String(blocker.process_name || '').trim()
  const matchingCard = segmentCards.value.find(item =>
    segmentIds.includes(item.segment.id)
      || processIds.some(id => id === item.segment.id || id === item.segment.export_process_id),
  ) || (processName
    ? segmentCards.value.find(item => finalizeSegmentDisplayName(item.segment) === processName)
    : undefined)
  if (!matchingCard) {
    setBatchNotice(processName
      ? `当前规则列表中找不到“${processName}”，请刷新规则后再试。`
      : '当前规则列表中找不到对应工序，请刷新规则后再试。')
    return
  }
  onlyPending.value = false
  await nextTick()
  focusSegment(matchingCard.segment.id)
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

function stopPreprocessPolling() {
  if (preprocessPollTimer !== null) {
    window.clearTimeout(preprocessPollTimer)
    preprocessPollTimer = null
  }
}

function invalidateRulePreprocessing() {
  preprocessEpoch += 1
  preprocessRefreshInFlight = null
  batchParsing.value = false
  stopPreprocessPolling()
}

function isPreprocessWorkspaceCurrent(epoch: number, requestProject: number, requestRoute: number, requestRevision: number) {
  return finalizeViewActive && epoch === preprocessEpoch
    && isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)
}

async function pollRulePreprocessing() {
  if (!finalizeViewActive || !projectId.value || !savedRoute.value || preprocessRefreshInFlight !== null) return
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const epoch = preprocessEpoch
  const owner = Symbol()
  preprocessRefreshInFlight = owner
  try {
    const next = await getRulePreprocessingStatus(requestProject, requestRoute)
    if (!isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) return
    const previous = preprocessStatus.value?.task_status
    preprocessStatus.value = next
    batchParsing.value = next.task_status === 'running' || next.task_status === 'queued'
    if (next.task_status === 'running' || next.task_status === 'queued') {
      stopPreprocessPolling()
      preprocessPollTimer = window.setTimeout(() => {
        preprocessPollTimer = null
        if (isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) void pollRulePreprocessing()
      }, 1200)
    } else {
      stopPreprocessPolling()
      if (previous && previous !== next.task_status && next.task_status === 'completed') {
        if (hasUnsavedEdits.value || conditionBusySegmentIds.value.size) {
          setBatchNotice('后台识别已完成，请保存或取消当前修改后刷新结果。')
        } else {
          await loadWorkspace(true, false)
        }
      }
    }
  } catch (err) {
    if (!isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) return
    console.warn('读取规则预处理状态失败', err)
    stopPreprocessPolling()
    preprocessPollTimer = window.setTimeout(() => {
      preprocessPollTimer = null
      if (isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) void pollRulePreprocessing()
    }, 1200)
  } finally {
    if (preprocessRefreshInFlight === owner) preprocessRefreshInFlight = null
  }
}

async function startRulePreprocessingForWorkspace() {
  if (!finalizeViewActive || !projectId.value || !savedRoute.value || !reviewableCards.value.length) return
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const epoch = preprocessEpoch
  const triggerKey = buildRulePreprocessingTriggerKey({
    projectId: projectId.value,
    savedRoute: savedRoute.value,
    supersetOperations: supersetOperations.value,
    segmentDisplayName: finalizeSegmentDisplayName,
  })
  if (!triggerKey) return
  if (triggerKey === lastRulePreprocessTriggerKey) {
    const status = preprocessStatus.value?.task_status
    if (status === 'running' || status === 'queued') {
      batchParsing.value = true
      void pollRulePreprocessing()
      return
    }
    if (status === 'completed' || status === 'failed') return
  }
  const items = batchEligibleCards.value.map(item => ({
    segment_id: item.segment.id,
    process_id: exportProcessIdForItem(item),
    process_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
    source_text: item.conditionText,
  })).filter(item => item.process_id && item.source_text.trim())
  if (!items.length) return
  try {
    lastRulePreprocessTriggerKey = triggerKey
    preprocessStatus.value = null
    batchParsing.value = true
    const next = await startRulePreprocessing({
      project_id: requestProject,
      route_id: requestRoute,
      expected_workflow_revision: requestRevision,
      items,
      processes: conditionProcessOptions.value,
    })
    if (!isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) return
    preprocessStatus.value = next
    batchParsing.value = next.task_status === 'running' || next.task_status === 'queued'
    if (next.task_status === 'running' || next.task_status === 'queued') {
      void pollRulePreprocessing()
    } else if (next.task_status === 'completed') {
      if (hasUnsavedEdits.value || conditionBusySegmentIds.value.size) {
        setBatchNotice('后台识别已完成，请保存或取消当前修改后刷新结果。')
      } else {
        await loadWorkspace(true, false)
      }
    }
  } catch (err) {
    if (!isPreprocessWorkspaceCurrent(epoch, requestProject, requestRoute, requestRevision)) return
    batchParsing.value = false
    lastRulePreprocessTriggerKey = ''
    console.warn('启动规则预处理失败', err)
  }
}

async function loadWorkspace(forceRefresh = false, autoPreprocess = true) {
  if (hasUnsavedEdits.value) {
    setBatchNotice('有未保存的修改，当前编辑仍保留。请先保存或取消修改后再刷新结果。')
    return
  }
  invalidateRulePreprocessing()
  let request = workspaceRequestGuard.start()
  const requestedProjectId = String(route.query.project_id || '')
  loadingProjectId = requestedProjectId
  let workspaceProjectId: number | null = null
  const isCurrent = () => request.isCurrent()
    && (String(route.query.project_id || '') === requestedProjectId
      || String(route.query.project_id || '') === String(workspaceProjectId))
    && (workspaceProjectId === null || projectId.value === workspaceProjectId)
  precheckResult.value = null
  loading.value = true
  lastExportedRulePackageVersion.value = null
  outdatedRulePackageVersion.value = null
  conditionErrors.value = {}
  selectedRuleIds.value = new Set()
  error.value = ''
  workspaceErrorTitle.value = FINALIZE_VIEW_COPY.errorTitle
  try {
    const projectList = await listProjects(forceRefresh)
    if (!isCurrent()) return
    const resolvedProjectId = resolveAvailableProjectId(requestedProjectId, projectList)
    if (!resolvedProjectId) {
      projectId.value = null
      projectName.value = ''
      savedRoute.value = null
      operations.value = []
      supersetOperations.value = []
      lastExportedRulePackageVersion.value = null
      outdatedRulePackageVersion.value = null
      error.value = ''
      return
    }

    projectId.value = Number(resolvedProjectId)
    workspaceProjectId = projectId.value
    loadingProjectId = resolvedProjectId
    if (String(route.query.project_id || '') !== resolvedProjectId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: resolvedProjectId },
      })
    }
    const currentProject = projectList.find(project => project.id === projectId.value)
    projectName.value = currentProject?.name || `任务 #${projectId.value}`
    const [routeResult, operationList, supersetResult, fieldRegistry, executableRevision] = await Promise.all([
      getSavedNormalizedRoute(projectId.value, forceRefresh),
      listOperations(projectId.value, forceRefresh),
      getSupersetRoute(projectId.value, forceRefresh),
      getConditionFieldRegistry(),
      getLatestExecutableRuleRevision(projectId.value),
    ])
    if (!isCurrent()) return
    const analysisLock = await enterRuleFinalization({
      project_id: projectId.value,
      route_id: routeResult.route_id,
      expected_workflow_revision: routeResult.workflow_revision,
    })
    if (!isCurrent()) return
    if (!routeResult.analysis_locked) {
      clearWorkflowProjectDataCache(projectId.value)
      request = workspaceRequestGuard.start()
    }
    Object.assign(routeResult, {
      analysis_locked: analysisLock.analysis_locked,
      analysis_locked_at: analysisLock.analysis_locked_at,
    })
    savedRoute.value = routeResult
    operations.value = operationList
    supersetOperations.value = supersetResult.superset_route || []
    conditionFields.value = fieldRegistry.fields || []
    executableRevisionCounter.value = executableRevision?.revision || 0
    clearRuleEditStates()
    cancelInlineEdit()
    const skippedLocalDrafts = readDrafts(routeResult.segments)
    if (skippedLocalDrafts) {
      setBatchNotice('已使用服务端最新规则，旧的本机草稿未自动恢复。')
    }
    activeSegmentId.value = routeResult.segments[0]?.id || ''
    await nextTick()
    if (!isCurrent()) return
    lastExportedRulePackageVersion.value = null
    outdatedRulePackageVersion.value = null
  } catch (err: any) {
    if (!isCurrent()) return
    if (Number(err?.response?.status) !== 404) console.error(err)
    savedRoute.value = null
    operations.value = []
    supersetOperations.value = []
    lastExportedRulePackageVersion.value = null
    outdatedRulePackageVersion.value = null
    workspaceErrorTitle.value = Number(err?.response?.status) === 404
      ? '当前任务尚未完成第三步保存' : FINALIZE_VIEW_COPY.errorTitle
    error.value = err?.response?.data?.detail?.message || err?.response?.data?.detail
      || '当前任务还没有第三步可预览的已保存结果，请先回到第三步完成分析。'
  } finally {
    if (!request.isLatest()) return
    loading.value = false
    if (isCurrent() && savedRoute.value && !error.value && autoPreprocess) {
      await startRulePreprocessingForWorkspace()
    }
  }
}

async function reloadWorkspace() {
  validationIssue.value = ''
  if (!await ensureRuleEditsSaved()) return
  await loadWorkspace(true)
}

async function ensureRuleEditsSaved() {
  if (unsavedCards.value.length) {
    setBatchNotice('有未保存的修改，请先保存或取消修改后再离开或刷新。')
    await locateBlockedCard(unsavedCards.value[0]!.segment.id)
    return false
  }
  if (conditionBusySegmentIds.value.size) {
    setBatchNotice('请等待当前规则保存或识别完成。')
    return false
  }
  return true
}

function protectUnsavedPage(event: BeforeUnloadEvent) {
  if (!finalizeViewActive || (!hasUnsavedEdits.value && !conditionBusySegmentIds.value.size)) return
  event.preventDefault()
  event.returnValue = ''
}

onBeforeRouteLeave(() => ensureRuleEditsSaved())
onBeforeRouteUpdate((to, from) => (
  to.query.project_id === from.query.project_id ? true : ensureRuleEditsSaved()
))

async function handleResetAllRecognition() {
  if (resettingWorkflow.value || loading.value || batchParsing.value || batchReviewing.value
    || reviewAndExporting.value || exportingRulePackage.value || !finalizeViewActive
    || !projectId.value || !savedRoute.value) return
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestRevision = savedRoute.value.workflow_revision
  const task = recognitionTaskGuard.start()
  const isCurrent = () => task.isCurrent() && finalizeViewActive
    && projectId.value === requestProject && Number(route.query.project_id) === requestProject
  validationIssue.value = ''
  resettingWorkflow.value = true
  batchNotice.value = ''
  try {
    if (!await ensureRuleEditsSaved() || !isCurrent()) return
    invalidateRulePreprocessing()
    const result = await resetWorkflow({
      project_id: requestProject,
      from_step: 4,
      expected_workflow_revision: requestRevision,
    })
    if (!isCurrent() || result.project_id !== requestProject
      || !isRuleWorkspaceCurrent(requestProject, requestRoute, requestRevision)) return
    publishWorkflowReset({
      projectId: result.project_id,
      fromStep: 4,
      workflowRevision: result.workflow_revision,
    })
    locallyHandledResetAt = workflowResetSignal.value?.emittedAt || 0
    resetDialogVisible.value = false
    onlyPending.value = true
    setBatchNotice('重置完成，正在后台准备重新识别。')
    const context = {
      projectId: result.project_id,
      workflowRevision: result.workflow_revision,
      isCurrent,
    }
    await restartAllRecognitionInBackground(context)
  } catch (err: any) {
    if (!isCurrent()) return
    showFinalizeNotice(
      '重新识别失败',
      '现有条件原文仍然保留，请刷新页面后重试。',
      conditionErrorMessage(err),
    )
  } finally {
    resettingWorkflow.value = false
  }
}

async function restartAllRecognitionInBackground(context: {
  projectId: number
  workflowRevision: number
  isCurrent: () => boolean
}) {
  if (!context.isCurrent()) return
  await loadWorkspace(true)
  if (
    !context.isCurrent()
    || projectId.value !== context.projectId
    || savedRoute.value?.workflow_revision !== context.workflowRevision
  ) {
    return
  }
  if (error.value) {
    throw new Error(error.value)
  }
  if (!batchEligibleCards.value.length && !batchParsing.value) {
    setBatchNotice('没有需要重新识别的规则；有效的已确认规则已保留。')
  }
}

watch(() => route.query.project_id, () => {
  if (!finalizeViewActive) return
  // Project discovery may canonicalize a missing/stale query via replace().
  // That changes the URL for the existing load, rather than starting a new one.
  if (String(route.query.project_id || '') === loadingProjectId) return
  invalidateRulePreprocessing()
  preprocessStatus.value = null
  recognitionTaskGuard.cancel()
  batchParsing.value = false
  void loadWorkspace()
})

function handleExternalWorkflowReset(signal: typeof workflowResetSignal.value) {
  if (!signal || signal.emittedAt === locallyHandledResetAt) return
  if (signal.projectId !== projectId.value || signal.fromStep > 4) return
  locallyHandledResetAt = signal.emittedAt
  invalidateRulePreprocessing()
  recognitionTaskGuard.cancel()
  batchParsing.value = false
  markExportedRulePackageOutdated()
  if (hasUnsavedEdits.value || conditionBusySegmentIds.value.size) {
    setBatchNotice('上游步骤已重新处理，当前编辑仍保留。请先复制备份或取消修改，再刷新结果。')
    return
  }
  if (signal.fromStep <= 3) clearAllDrafts()
  if (!finalizeViewActive) return
  void loadWorkspace(true)
}

watch(workflowResetSignal, handleExternalWorkflowReset)

// Selection is tied to the candidate source, so refreshed/edited candidates need a new explicit selection.
watch(() => pendingReviewCards.value.map(item => [item.segment.id, `${item.conditionReview?.source_hash}:${JSON.stringify(item.conditionReview?.candidate)}`] as const), (current, previous) => {
  const before = new Map(previous || [])
  selectedRuleIds.value = new Set(current.filter(([id, signature]) => selectedRuleIds.value.has(id) && before.get(id) === signature).map(([id]) => id))
})
watch(() => projectId.value, () => { conditionErrors.value = {}; selectedRuleIds.value = new Set() })
watch(() => [projectId.value, savedRoute.value?.route_id, savedRoute.value?.workflow_revision], () => {
  batchConfirmationResult.value = null
})

watch(drafts, () => {
  persistDrafts()
}, { deep: true })

watch([visibleSegments, onlyPending], () => {
  syncActiveSegment()
}, { deep: true })

onMounted(() => {
  finalizeViewActive = true
  window.addEventListener('beforeunload', protectUnsavedPage)
  void loadWorkspace()
})

onBeforeUnmount(() => {
  finalizeViewActive = false
  workspaceRequestGuard.start()
  invalidateRulePreprocessing()
  recognitionTaskGuard.cancel()
  window.removeEventListener('beforeunload', protectUnsavedPage)
})

onActivated(() => {
  finalizeViewActive = true
  if (hasUnsavedEdits.value || conditionBusySegmentIds.value.size) {
    void startRulePreprocessingForWorkspace()
    return
  }
  // Initial activation follows mounting before discovery has resolved an ID;
  // the mounted request already owns that load.
  if (loading.value && loadingProjectId === String(route.query.project_id || '')) return
  // Mapping writes and changes from another window can retire the package
  // without changing this mounted view's cached route or rules.
  void loadWorkspace(true)
})

onDeactivated(() => {
  finalizeViewActive = false
  workspaceRequestGuard.start()
  loading.value = false
  invalidateRulePreprocessing()
  recognitionTaskGuard.cancel()
  batchParsing.value = false
})
</script>

<style scoped>
.batch-confirmation-result {
  flex-shrink: 0;
  max-height: 180px;
  overflow-y: auto;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 8px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-size: 12px;
  overflow-wrap: anywhere;
}
.batch-confirmation-result ul { margin: 8px 0 0; padding-left: 20px; }
.batch-confirmation-result li + li { margin-top: 4px; }

.ash-selection-actions { display: flex; align-items: center; gap: 6px; padding-right: 8px; margin-right: 2px; border-right: 1px solid var(--pm-border); }
.ash-selection-count { white-space: nowrap; }

.finalize-view {
  --workflow-nav-right-inset: 0px;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  padding: 0;
  overflow: hidden;
  background: var(--pm-surface-subtle);
}

.analysis-style-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  border-radius: 8px;
  padding: 5px 12px;
  box-shadow: 0 1.5px 5px rgba(15, 23, 42, 0.02);
  margin-bottom: 12px;
}

.ash-meta-stale {
  color: var(--pm-warning);
  background: var(--pm-warning-soft);
  border-color: var(--pm-warning-border);
}

.ash-left-content {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
  flex-wrap: wrap;
}

.ash-page-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--pm-text);
  white-space: nowrap;
  flex-shrink: 0;
}

.ash-dark-chip {
  background: #e8ecf4;
  color: #3d4f6a;
  border: 1px solid #c9d3e3;
  padding: 2px 8px;
  border-radius: 5px;
  font-size: 12px;
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
  gap: 12px;
  margin-left: 4px;
  border-left: 1px solid var(--pm-border-strong);
  padding-left: 12px;
  min-width: 0;
}

.ash-meta-item {
  font-size: 13px;
  color: var(--pm-text-muted);
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.ash-meta-item strong {
  color: var(--pm-text);
  font-weight: 700;
}

.ash-review-progress {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: var(--pm-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

.ash-review-progress strong { color: var(--pm-text); font-weight: 700; }

.ash-publish-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px 9px;
  border: 1px solid var(--pm-success-border);
  border-radius: 999px;
  color: var(--pm-success);
  background: var(--pm-success-soft);
  font-size: 12px;
  line-height: 1;
  font-family: inherit;
  text-align: left;
  cursor: default;
}

.ash-publish-state:disabled { opacity: 1; cursor: default; }

.ash-publish-state--blocked {
  border-color: var(--pm-warning-border);
  color: var(--pm-warning);
  background: var(--pm-warning-soft);
}

.ash-publish-state-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: var(--pm-success);
  box-shadow: 0 0 0 3px rgba(34, 197, 94, 0.12);
}

.ash-publish-state--blocked .ash-publish-state-dot {
  background: #f97316;
  box-shadow: 0 0 0 3px rgba(249, 115, 22, 0.12);
}

.ash-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.ash-template-link {
  padding: 7px 4px;
  border: 0;
  background: transparent;
  color: var(--pm-primary);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.ash-template-link:hover { color: var(--pm-primary); text-decoration: underline; }

.ash-quiet-action,
.ash-icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: var(--pm-text-muted);
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: color .15s ease, background-color .15s ease, border-color .15s ease;
}

.ash-quiet-action { padding: 5px 7px; white-space: nowrap; }
.ash-quiet-action:hover:not(:disabled) { background: var(--pm-surface-subtle); color: var(--pm-text-secondary); }
.ash-icon-action { width: 30px; padding: 0; }
.ash-icon-action:hover:not(:disabled) { border-color: var(--pm-border); background: var(--pm-surface-subtle); color: var(--pm-text-secondary); }
.ash-quiet-action:disabled,
.ash-icon-action:disabled { color: var(--pm-text-muted); cursor: not-allowed; }
.ash-quiet-action:focus-visible,
.ash-icon-action:focus-visible { outline: 2px solid var(--pm-primary-border); outline-offset: 2px; }

.ash-btn-outline {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--pm-surface);
  border: 1px solid var(--pm-primary);
  color: var(--pm-primary);
  padding: 3px 12px;
  border-radius: 8px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.ash-btn-outline:hover:not(:disabled) { background: var(--pm-primary-soft); border-color: var(--pm-primary); color: var(--pm-primary); }
.ash-btn-outline:disabled { opacity: 0.45; cursor: not-allowed; border-color: var(--pm-border-strong); color: var(--pm-text-muted); }

.ash-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 12px;
  border: 1px solid var(--pm-primary);
  border-radius: 8px;
  background: var(--pm-primary);
  color: var(--pm-surface);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease, box-shadow .15s ease;
}
.ash-btn-primary:hover:not(:disabled) { background: var(--pm-primary-hover); border-color: var(--pm-primary-hover); }
.ash-btn-primary:disabled { opacity: .45; cursor: not-allowed; }

.export-blocker-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);

}

.export-blocker-dialog {
  width: min(520px, 100%);
  max-height: min(680px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid var(--pm-border);
  border-radius: 12px;
  background: var(--pm-surface);
  box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08);
}

.export-blocker-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid var(--pm-surface-subtle);
}

.export-blocker-kicker {
  display: inline-block;
  margin-bottom: 4px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.export-blocker-header h2 {
  margin: 0;
  color: var(--pm-text);
  font-size: 19px;
  font-weight: 650;
  line-height: 1.4;
  letter-spacing: -0.01em;
}

.export-blocker-close {
  flex: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--pm-text-muted);
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.export-blocker-close:hover {
  background: var(--pm-surface-subtle);
  color: var(--pm-text);
}

.export-blocker-copy {
  margin: 0;
  padding: 14px 24px;
  color: var(--pm-text-secondary);
  font-size: 14px;
  line-height: 1.7;
  font-weight: 400;
  background: var(--pm-surface-subtle);
  border-bottom: 1px solid var(--pm-surface-subtle);
}

.export-blocker-group {
  padding: 16px 24px 4px;
}

.export-blocker-group-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 10px;
}

.export-blocker-group-head strong {
  font-size: 13px;
  font-weight: 600;
  color: var(--pm-text-secondary);
}

.export-blocker-group-head span {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 500;
  color: var(--pm-text-muted);
  background: var(--pm-surface-subtle);
  border-radius: 9999px;
  font-variant-numeric: tabular-nums;
}

.export-blocker-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin: 0;
  padding: 0;
  list-style: none;
}

.export-blocker-list li {
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 42px;
  padding: 0 12px 0 14px;
  border: 1px solid var(--pm-border);
  border-radius: 8px;
  background: var(--pm-surface);
  transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}

.export-blocker-list-item--clickable {
  cursor: pointer;
}

.export-blocker-list-item--clickable:hover {
  border-color: var(--pm-border-strong);
  background: var(--pm-surface-subtle);
}

.export-blocker-list span {
  display: inline-block;
  min-width: 28px;
  color: var(--pm-text-muted);
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.export-blocker-list strong {
  flex: 1;
  overflow: hidden;
  color: var(--pm-text);
  font-size: 14px;
  font-weight: 600;
  line-height: 1.45;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.export-blocker-list em {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  border-radius: 4px;
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  border: 1px solid #ffedd5;
  font-size: 12px;
  font-weight: 600;
  font-style: normal;
  white-space: nowrap;
}

.export-blocker-more {
  margin: 10px 24px 0;
  color: #71839a;
  font-size: 12px;
}

.export-blocker-actions {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  margin-top: 16px;
  padding: 14px 24px;
  border-top: 1px solid var(--pm-border);
  background: var(--pm-surface);
}

.batch-toast {
  position: fixed;
  bottom: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 9px 16px;
  background: var(--pm-text);
  color: var(--pm-surface-subtle);
  font-size: 13px;
  font-weight: 500;
  border-radius: 8px;
  box-shadow: 0 4px 16px rgba(0, 0, 0, 0.2);
  pointer-events: none;
}

.toast-fade-enter-active,
.toast-fade-leave-active {
  transition: opacity 0.2s ease, transform 0.2s ease;
}

.toast-fade-enter-from,
.toast-fade-leave-to {
  opacity: 0;
  transform: translateY(6px);
}

.preprocess-failure-panel {
  margin: -2px 0 12px;
  padding: 12px 14px;
  border: 1px solid var(--pm-warning-border);
  border-radius: 10px;
  background: var(--pm-warning-soft);
  color: #7c2d12;
  box-shadow: 0 8px 18px rgba(251, 146, 60, 0.10);
}

.preprocess-failure-head {
  display: flex;
  align-items: flex-start;
  gap: 10px;
}

.preprocess-failure-icon {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  flex: 0 0 20px;
  border-radius: 50%;
  background: #fb923c;
  color: var(--pm-surface);
  font-size: 12px;
  font-weight: 800;
  line-height: 1;
}

.preprocess-failure-head strong {
  display: block;
  font-size: 13px;
  line-height: 1.3;
}

.preprocess-failure-head p {
  margin: 3px 0 0;
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.45;
}

.preprocess-failure-list {
  margin: 10px 0 0 30px;
  padding: 0;
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.5;
}

.preprocess-failure-list li {
  margin: 2px 0;
  word-break: break-word;
}

.preprocess-failure-more {
  margin: 8px 0 0 30px;
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.45;
}

.highlight-text { color: #ea580c !important; }

/* ===== Phase-active button highlight ===== */
.ash-btn-primary.ash-btn-phase-active {
  box-shadow: 0 0 0 2px rgba(36, 95, 168, 0.30), 0 4px 12px rgba(36, 95, 168, 0.25);
  transform: none;
}
.ash-btn-outline.ash-btn-phase-active {
  border-color: var(--pm-primary);
  color: var(--pm-primary-hover);
  background: var(--pm-primary-soft);
  box-shadow: 0 0 0 2px rgba(36, 95, 168, 0.22), 0 4px 12px rgba(36, 95, 168, 0.12);
  transform: none;
}

.text-done { color: var(--pm-success) !important; }

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
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
  padding: 12px 16px;
}

.finalize-empty-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  color: var(--pm-text-muted);
  font-size: 13px;
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
  border: 1px solid var(--pm-border);
  border-radius: 8px;
  background: var(--pm-surface);
  box-shadow: 0 20px 46px rgba(15, 23, 42, 0.24);
}

.export-issue-icon {
  display: grid;
  place-items: center;
  width: 32px;
  height: 32px;
  border-radius: 50%;
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  font-size: 18px;
  font-weight: 800;
}

.export-issue-kicker {
  display: block;
  margin-bottom: 4px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 700;
}

.export-issue-dialog h2 {
  margin: 0;
  color: var(--pm-text);
  font-size: 18px;
  line-height: 1.4;
}

.export-issue-dialog p {
  margin: 8px 0 0;
  color: var(--pm-text-secondary);
  font-size: 14px;
  line-height: 1.65;
}

.export-issue-details {
  margin-top: 14px;
  border-top: 1px solid var(--pm-border);
  color: var(--pm-text-secondary);
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
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
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

  .ash-actions > .ash-template-link { width: auto; justify-self: start; }
  .ash-actions > .ash-btn-primary { grid-column: 1 / -1; }
}



/* ===== Drawer Overlay & Modal ===== */
.drawer-overlay {
  position: fixed;
  inset: 0;
  background: rgba(15, 23, 42, 0.52);


  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 200;
  padding: 24px;
}

.edit-drawer {
  width: min(520px, 100%);
  max-height: calc(100vh - 80px);
  background: var(--pm-surface);
  border-radius: 20px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  box-shadow:
    0 32px 64px -16px rgba(15, 23, 42, 0.22),
    0 0 0 1px rgba(148, 163, 184, 0.1),
    0 0 0 4px rgba(36, 95, 168, 0.04);
}

/* --- Header --- */
.drawer-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 24px 28px 20px;
  background: var(--pm-primary-soft);
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
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  background: var(--pm-primary);
  color: var(--pm-surface);
  width: fit-content;
}

.drawer-title {
  font-size: 19px;
  line-height: 1.3;
  font-weight: 700;
  color: var(--pm-text);
  letter-spacing: -0.02em;
}

.drawer-title-meta {
  margin-top: -2px;
  font-size: 12px;
  line-height: 1.45;
  color: var(--pm-text-muted);
}

.drawer-close-btn {
  flex-shrink: 0;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  border: 1px solid var(--pm-border);
  background: var(--pm-surface);
  color: var(--pm-text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s ease;
}

.drawer-close-btn:hover {
  background: var(--pm-surface-subtle);
  border-color: var(--pm-border-strong);
  color: var(--pm-text-secondary);
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
  background: var(--pm-border);
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
  color: var(--pm-primary);
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
  background: var(--pm-primary);
  flex-shrink: 0;
}

/* --- Textarea --- */
.drawer-textarea {
  width: 100%;
  resize: vertical;
  border-radius: 10px;
  border: 1.5px solid var(--pm-border);
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pm-text);
  background: #fafbfc;
  outline: none;
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  font-family: inherit;
}

.drawer-textarea::placeholder {
  color: var(--pm-text-muted);
  font-weight: 400;
}

.drawer-textarea:hover {
  border-color: var(--pm-primary-border);
  background: var(--pm-surface);
}

.drawer-textarea:focus {
  border-color: var(--pm-primary-border);
  background: var(--pm-surface);
  box-shadow:
    0 0 0 3px rgba(36, 95, 168, 0.1),
    0 2px 8px rgba(36, 95, 168, 0.06);
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
  color: var(--pm-text-secondary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}

.drawer-factor-item:hover {
  border-color: var(--pm-primary-border);
  background: var(--pm-primary-soft);
  transform: none;
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.06);
}

.drawer-factor-item.is-active {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
  color: var(--pm-primary);
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.08);
}

.drawer-factor-item input {
  display: none;
}

.factor-checkbox {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
  border-radius: 5px;
  border: 1.5px solid var(--pm-border-strong);
  background: var(--pm-surface);
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.25s cubic-bezier(0.34, 1.56, 0.64, 1);
}

.drawer-factor-item.is-active .factor-checkbox {
  background: var(--pm-primary);
  border-color: var(--pm-primary);
  transform: scale(1.05);
  box-shadow: 0 2px 6px rgba(36, 95, 168, 0.3);
}

.factor-checkbox svg {
  width: 11px;
  height: 11px;
  fill: none;
  stroke: var(--pm-surface);
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
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
  border: 1px solid var(--pm-primary-soft);
  border-radius: 999px;
  padding: 5px 12px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.drawer-action-chip:hover:not(:disabled) {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
  transform: none;
  box-shadow: 0 2px 6px rgba(36, 95, 168, 0.12);
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
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  border: 1px solid var(--pm-border-strong);
}

.drawer-foot-btn-reset:hover {
  background: var(--pm-surface-subtle);
  border-color: var(--pm-text-muted);
  color: var(--pm-text);
}

.drawer-foot-btn-save {
  background: var(--pm-primary);
  color: var(--pm-surface);
  border: none;
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.25);
}

.drawer-foot-btn-save:hover {
  background: var(--pm-primary);
  transform: none;
  box-shadow: 0 4px 14px rgba(36, 95, 168, 0.35);
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
  padding: 34px 28px 38px;
  background: var(--pm-surface);
}

.empty-mark {
  font-size: 28px;
  font-weight: 700;
  color: var(--pm-text-muted);
  margin-bottom: 12px;
}

.empty-mark--success {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  margin: 0 auto 12px;
  border-radius: 50%;
  color: var(--pm-success);
  background: var(--pm-success-soft);
  font-size: 22px;
}

.empty-title {
  font-size: 18px;
  font-weight: 700;
  color: var(--pm-text);
  margin-bottom: 8px;
  letter-spacing: -0.01em;
}

.empty-text {
  font-size: 14px;
  line-height: 1.8;
  color: var(--pm-text-muted);
  font-weight: 400;
  max-width: 620px;
  margin: 0 auto 18px;
}

.empty-state-error {
  border-color: var(--pm-danger-border);
  background: var(--pm-danger-soft);
}

.empty-mark--warning {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  margin: 0 auto 12px;
  border-radius: 50%;
  color: var(--pm-warning);
  background: #ffedd5;
  font-size: 20px;
  font-weight: bold;
}

/* 扁平化紧凑 Alert Banner 样式 */
.ash-publish-state--clickable {
  cursor: pointer;
  transition: transform 0.15s ease, filter 0.15s ease;
}

.ash-publish-state--clickable:hover {
  transform: none;
  filter: brightness(0.96);
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

/* PM016: typography, surfaces and actions share the global compact theme. */
.finalize-view { background: transparent; }
.analysis-style-header { flex-wrap: wrap; gap: 8px 12px; padding: 10px 12px; border-radius: var(--pm-radius-card); box-shadow: var(--pm-shadow-card); }
.ash-left-content, .ash-meta-section, .ash-actions, .rule-review-toolbar, .rule-review-actions { flex-wrap: wrap; min-width: 0; }
.ash-page-title { font-size: 20px; font-weight: 600; line-height: 28px; }
.ash-dark-chip { background: var(--pm-surface-subtle); border: 1px solid var(--pm-border); color: var(--pm-text-secondary); font-weight: 500; }
.ash-meta-section { gap: 6px 12px; }
.ash-actions { gap: 6px; }
.ash-btn-primary, .ash-btn-outline { min-height: var(--pm-control-height); height: auto; padding: 5px 12px; border-radius: var(--pm-radius-control); font-size: 13px; line-height: 20px; font-weight: 500; box-shadow: none; }
.ash-btn-primary, .ash-btn-primary.ash-btn-phase-active { background: var(--pm-primary); border-color: var(--pm-primary); }
.ash-btn-primary:hover:not(:disabled) { background: var(--pm-primary-hover); border-color: var(--pm-primary-hover); box-shadow: none; transform: none; }
.ash-btn-outline.ash-btn-phase-active { background: var(--pm-primary-soft); border-color: var(--pm-primary); box-shadow: none; }
.ash-meta-stale { color: var(--pm-warning); }
.finalize-layout { gap: 12px; }
/* FinalizeRouteNav keeps its own geometry and events; adapt its legacy palette. */
.finalize-view :deep(.route-nav) { border-color: var(--pm-border); border-radius: var(--pm-radius-card); background: var(--pm-surface); box-shadow: var(--pm-shadow-card); padding: 12px; }
.finalize-view :deep(.route-nav-head) { flex-wrap: wrap; }
.finalize-view :deep(.section-title) { color: var(--pm-text); font-weight: 600; }
.finalize-view :deep(.route-filter) { background: var(--pm-surface-subtle); }
.finalize-view :deep(.route-filter-option) { min-height: 28px; font-size: 12px; color: var(--pm-text-secondary); }
.finalize-view :deep(.route-filter-option span) { font-size: 12px; color: var(--pm-text-secondary); background: var(--pm-disabled-bg); }
.finalize-view :deep(.route-filter-option--active) { border-color: var(--pm-primary-border); background: var(--pm-surface); color: var(--pm-primary); box-shadow: none; }
.finalize-view :deep(.route-filter-option--active span) { background: var(--pm-primary-soft); color: var(--pm-primary); }
.finalize-view :deep(.phase-dot) { background: var(--pm-border-strong); box-shadow: 0 0 0 1px var(--pm-border-strong); }
.finalize-view :deep(.phase-dot--active) { background: var(--pm-primary); box-shadow: 0 0 0 1px var(--pm-primary), 0 0 0 3px rgba(36, 95, 168, .16); }
.finalize-view :deep(.phase-line) { background: var(--pm-border); }
.finalize-view :deep(.phase-item) { min-width: 0; background: var(--pm-surface); border-color: var(--pm-border); }
.finalize-view :deep(.phase-item:hover) { background: var(--pm-surface-subtle); border-color: var(--pm-border-strong); box-shadow: none; }
.finalize-view :deep(.phase-item.active) { background: var(--pm-primary-soft); border-color: var(--pm-primary-border); box-shadow: none; }
.finalize-view :deep(.phase-item.active::after) { background: var(--pm-primary); }
.finalize-view :deep(.phase-item-seq) { min-height: 20px; font-size: 12px; background: var(--pm-surface-subtle); color: var(--pm-text-secondary); border-color: var(--pm-border); }
.finalize-view :deep(.phase-item.active .phase-item-seq) { background: var(--pm-primary); color: #fff; border-color: var(--pm-primary); }
.finalize-view :deep(.phase-item-name) { color: var(--pm-text); }
.finalize-view :deep(.phase-item-meta) { font-size: 12px; color: var(--pm-text-muted); }
.finalize-view :deep(.phase-steps-btn) { min-height: 28px; font-size: 12px; color: var(--pm-text-secondary); }
.finalize-view :deep(.phase-steps-btn:hover) { color: var(--pm-primary); }
.finalize-view :deep(.phase-steps-count), .finalize-view :deep(.phase-item-step-chip) { font-size: 12px; color: var(--pm-text-secondary); background: var(--pm-surface-subtle); border-color: var(--pm-border); }
.finalize-view :deep(.phase-steps-btn:hover .phase-steps-count) { color: var(--pm-primary); background: var(--pm-primary-soft); border-color: var(--pm-primary-border); }
.finalize-view :deep(.phase-item-edited) { font-size: 12px; color: var(--pm-warning); background: var(--pm-warning-soft); }
.finalize-view :deep(.route-filter-option:focus-visible), .finalize-view :deep(.phase-item:focus-visible), .finalize-view :deep(.phase-steps-btn:focus-visible) { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.finalize-results { border-radius: var(--pm-radius-card); padding: 10px; box-shadow: var(--pm-shadow-card); }
.ash-actions { flex-wrap: wrap; justify-content: flex-end; }
.ash-actions .ash-btn-outline { min-height: var(--pm-control-height-small); padding: 3px 9px; font-size: 12px; }
.batch-confirmation-result { max-height: 180px; border-color: var(--pm-warning-border); color: var(--pm-warning); background: var(--pm-warning-soft); line-height: 20px; }
.drawer-overlay { background: rgba(35, 53, 74, .35); }
.edit-drawer, .export-issue-dialog { border-radius: var(--pm-radius-dialog); border-color: var(--pm-border); box-shadow: var(--pm-shadow-popup); }
.drawer-head, .drawer-foot { flex-shrink: 0; }
.drawer-body { min-width: 0; min-height: 0; }
.drawer-foot { flex-wrap: wrap; gap: 8px; }
.finalize-view button:focus-visible, .drawer-overlay button:focus-visible, .drawer-overlay summary:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
@media (min-width: 901px) and (max-width: 1080px) { .finalize-layout { grid-template-columns: 260px minmax(0, 1fr); } }
@media (max-width: 900px) { .ash-actions button { min-height: 32px; } }
@media (prefers-reduced-motion: reduce) { .finalize-view button, .edit-drawer { transition: none; } }
</style>
