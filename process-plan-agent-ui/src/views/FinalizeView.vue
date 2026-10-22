<template>
  <div class="finalize-view">
    <div class="analysis-style-header">
      <div class="ash-left-content">
        <span class="ash-page-title">规则定稿</span>
        <span class="ash-dark-chip">{{ projectName || '未命名任务' }}</span>
        
        <div class="ash-meta-section">
          <span class="ash-meta-item">路线版本 <strong>V{{ savedRoute?.version || '-' }}</strong></span>
          <span class="ash-meta-item" v-if="lastExportedRulePackageVersion">规则包 <strong>V{{ lastExportedRulePackageVersion }}</strong></span>
          <span class="ash-meta-item ash-meta-stale" v-else-if="outdatedRulePackageVersion">规则包 V{{ outdatedRulePackageVersion }} <strong>已过期</strong></span>
          <span v-if="reviewableRuleCount" class="ash-review-progress">
            <span>已确认 <strong>{{ confirmedRuleCount }}/{{ reviewableRuleCount }}</strong></span>
          </span>
          <span v-else class="ash-meta-item">无需确认条件规则</span>
        </div>

        <button
          v-if="precheckResult && !precheckResult.ok && canOpenPrecheck"
          type="button"
          class="ash-publish-state ash-publish-state--blocked ash-publish-state--clickable"
          title="查看发布预检明细"
          @click="openPrecheckDialog"
        >
          <span class="ash-publish-state-dot" aria-hidden="true"></span>
          <strong>预检待修复 {{ precheckBlockerCount }} 项</strong>
        </button>
      </div>

      <div class="ash-actions">
        <button class="ash-template-link" type="button" @click="goToTemplateMapping">
          模板映射
        </button>
        <button
          class="ash-quiet-action"
          type="button"
          title="重新识别全部工序规则"
          aria-label="重新识别全部工序规则"
          @click="openResetDialog"
          :disabled="loading || resettingWorkflow || batchParsing || batchReviewing || exportingRulePackage || !savedRoute"
        >重新识别</button>
        <button
          class="ash-icon-action"
          type="button"
          title="刷新结果"
          aria-label="刷新结果"
          @click="reloadWorkspace"
          :disabled="loading || resettingWorkflow || !projectId"
        >
          <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">
            <path d="M20 7v5h-5" />
            <path d="M4 17v-5h5" />
            <path d="M5.7 9a7 7 0 0 1 11.6-2.1L20 12M4 12l2.7 5.1A7 7 0 0 0 18.3 15" />
          </svg>
        </button>
        <button
          class="ash-btn-primary ash-btn-phase-active"
          @click="handleReviewAndExport"
          :disabled="resettingWorkflow || reviewAndExporting || batchParsing || batchReviewing || exportingRulePackage || !segmentCards.length"
        >
          {{ reviewAndExportButtonLabel }}
        </button>
      </div>
    </div>

    <!-- 轻量级浮动提示，不挤占页面主体结构 -->
    <transition name="toast-fade">
      <div v-if="batchNotice" class="batch-toast" role="status">
        <span>{{ batchNotice }}</span>
      </div>
    </transition>

    <section v-if="preprocessFailureSummary" class="preprocess-failure-panel" role="alert">
      <div class="preprocess-failure-head">
        <span class="preprocess-failure-icon">!</span>
        <div>
          <strong>{{ preprocessFailureSummary.title }}</strong>
          <p>{{ preprocessFailureSummary.message }}</p>
        </div>
      </div>
      <ul v-if="preprocessFailureSummary.lines.length" class="preprocess-failure-list">
        <li v-for="line in preprocessFailureSummary.lines" :key="line">{{ line }}</li>
      </ul>
      <p v-if="preprocessFailureSummary.overflowCount" class="preprocess-failure-more">
        另有 {{ preprocessFailureSummary.overflowCount }} 条失败记录，修复后可刷新或重新识别。
      </p>
    </section>



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
        <div v-if="pendingReviewCards.length" class="rule-review-toolbar">
          <span>待确认 {{ pendingReviewCards.length }} 项 · 已选 {{ selectedReviewCards.length }} 项</span>
          <div class="rule-review-actions">
            <button
              class="ash-btn-outline"
              :disabled="batchReviewing || batchParsing || resettingWorkflow || exportingRulePackage"
              @click="toggleSelectAllPending"
            >
              {{ allPendingSelected ? '取消全选' : '一键全选' }}
            </button>
            <button class="ash-btn-outline" :disabled="!selectedReviewCards.length || batchReviewing || batchParsing || resettingWorkflow || exportingRulePackage" @click="handleConfirmSelectedCandidates">
              {{ batchReviewing ? `正在确认 ${batchReviewCompleted}/${batchReviewTotal}` : '确认选中规则' }}
            </button>
          </div>
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
          :process-options="conditionProcessOptions"
          :condition-busy="conditionBusySegmentIds.has(item.segment.id)"
          :actions-disabled="batchReviewing || resettingWorkflow || exportingRulePackage"
          :condition-error="conditionErrors[item.segment.id]"
          :selectable="pendingReviewCards.some(card => card.segment.id === item.segment.id)"
          :selected="selectedRuleIds.has(item.segment.id)"
          @toggle-selected="toggleRuleSelection"
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
      previous-label="← 返回模板映射"
      next-label="进入规则包验证 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId || !lastExportedRulePackageVersion"
      @previous="goToTemplateMapping"
      @next="goToGenerate"
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
import { getCurrentGroupTemplate } from '@/api/extract'
import { getTemplateMappingStatus } from '@/composables/projectGroupTemplateCheck'
import { buildFinalTemplateMappingOperations } from '@/composables/finalTemplateMappingOperations'
import { ruleFinalizeResetCopy } from '@/composables/workflowResetCopy'

import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FinalizeRouteNav from '@/components/finalize/FinalizeRouteNav.vue'
import FinalizePublishPrecheckDialog from '@/components/finalize/FinalizePublishPrecheckDialog.vue'
import { nextPendingSegmentId } from '@/utils/finalizeRulePresentation'
import FinalizeRuleCard from '@/components/finalize/FinalizeRuleCard.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import WorkflowResetDialog from '@/components/workflow/WorkflowResetDialog.vue'
import {
  getSavedNormalizedRoute,
  getLatestFinalizedRulePackage,
  getSupersetRoute,
  listOperations,
  listProjects,
  type RulePackagePrecheckResult,
  resetWorkflow,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  confirmRuleCondition,
  getConditionFieldRegistry,
  getRulePreprocessingStatus,
  compileRulePackage,
  parseRuleCondition,
  saveRuleConditionDraft,
  startRulePreprocessing,
  setManualRuleCondition,
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
import { useFinalizeDrafts } from '@/composables/useFinalizeDrafts'
import { useFinalizeRulePackageExport } from '@/composables/useFinalizeRulePackageExport'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { buildRulePreprocessFailureSummary, buildRulePreprocessingTriggerKey } from '@/composables/rulePreprocessingTrigger'
import { buildProjectRouteQuery, resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { createLatestWorkflowRequestGuard, getWorkflowDataRevision } from '@/composables/workflowDataCache'
import { isWorkflowRevisionConflict, publishWorkflowReset, workflowResetSignal } from '@/composables/workflowResetState'
import { createBackgroundTaskGuard, runBackgroundTask } from '@/composables/runBackgroundTask'
import {
  buildManualBooleanRuleCandidate,
  exportProcessIdForItem,
  exportBlockingCards,
  buildCompileRequestFromCards,
  blockedExportPrimaryActionLabel,
  exportBlockedReasonLabel,
  groupExportBlockedCards,
  finalizeRuleMode,
  hasCurrentConfirmedUserRule,
  normalizeExportProcessName,
  requiresServerRuleConditionRefresh,
} from '@/utils/finalizeRulePackage'

const route = useRoute()
const router = useRouter()
let finalizeViewActive = false
let initialLoadFinished = false
let loadedDataRevision = -1
let locallyHandledResetAt = 0
const workspaceRequestGuard = createLatestWorkflowRequestGuard()

const loading = ref(false)
const error = ref('')
const workspaceErrorTitle = ref<string>(FINALIZE_VIEW_COPY.errorTitle)
const projectId = ref<number | null>(null)
const projectName = ref('')
const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
const operations = ref<OperationItem[]>([])
const supersetOperations = ref<OperationItem[]>([])
const onlyPending = ref(true)
const selectedRuleIds = ref(new Set<string>())
const conditionErrors = ref<Record<string, string>>({})
const activeSegmentId = ref('')
const lastExportedRulePackageVersion = ref<number | null>(null)
const outdatedRulePackageVersion = ref<number | null>(null)
const conditionFields = ref<CanonicalConditionField[]>([])
const conditionBusySegmentIds = ref(new Set<string>())
const conditionBusyCounts = new Map<string, number>()
const batchParsing = ref(false)
const batchParseCompleted = ref(0)
const batchParseTotal = ref(0)
const batchReviewing = ref(false)
const batchReviewCompleted = ref(0)
const batchReviewTotal = ref(0)
const preprocessStatus = ref<RulePreprocessStatus | null>(null)
const preprocessFailureSummary = computed(() => buildRulePreprocessFailureSummary(preprocessStatus.value))
const precheckResult = ref<RulePackagePrecheckResult | null>(null)
const showPrecheckDialog = ref(false)
let preprocessPollTimer: ReturnType<typeof window.setTimeout> | null = null
let preprocessRefreshInFlight = false
let lastRulePreprocessTriggerKey = ''
const reviewAndExporting = ref(false)
const batchNotice = ref('')
const resetDialogVisible = ref(false)
const resettingWorkflow = ref(false)
let batchNoticeTimer: ReturnType<typeof setTimeout> | null = null
let workflowConflictReload: Promise<void> | null = null
let batchParseExecutionId = 0
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

const conditionalCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'conditional'))
const relationCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'relation'))
const reviewableCards = computed(() => [...conditionalCards.value, ...relationCards.value])
const reviewableRuleCount = computed(() => reviewableCards.value.length)
const unresolvedRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'unresolved').length)
const reviewFocusCards = computed(() => exportBlockingCards(segmentCards.value))
const visibleSegments = computed(() => onlyPending.value ? reviewFocusCards.value : segmentCards.value)
const batchEligibleCards = computed(() => reviewableCards.value.filter((item) => {
  return requiresServerRuleConditionRefresh(item)
}))
const pendingReviewCards = computed(() => reviewableCards.value.filter((item) => {
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  return review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && Boolean(review.candidate && review.source_hash)
    && (review.candidate?.kind || 'condition') === expectedKind
}))
const publishBlockingCount = computed(() => reviewFocusCards.value.length)
const precheckBlockerCount = computed(() => {
  if (!precheckResult.value) return 0
  return precheckResult.value.ok ? 0 : (precheckResult.value.blockers?.length || 1)
})
const canOpenPrecheck = computed(() => publishBlockingCount.value === 0 && Boolean(precheckResult.value))
const selectedReviewCards = computed(() => pendingReviewCards.value.filter(item => selectedRuleIds.value.has(item.segment.id)))
const allPendingSelected = computed(() => pendingReviewCards.value.length > 0 && selectedReviewCards.value.length === pendingReviewCards.value.length)
const confirmedRuleCount = computed(() => reviewableCards.value.filter(hasCurrentConfirmedUserRule).length)
function toggleRuleSelection(item: FinalizeCard) {
  const ids = new Set(selectedRuleIds.value)
  if (ids.has(item.segment.id)) ids.delete(item.segment.id)
  else ids.add(item.segment.id)
  selectedRuleIds.value = ids
}
function toggleSelectAllPending() {
  const ids = new Set(selectedRuleIds.value)
  if (allPendingSelected.value) {
    pendingReviewCards.value.forEach(item => ids.delete(item.segment.id))
  } else {
    pendingReviewCards.value.forEach(item => ids.add(item.segment.id))
  }
  selectedRuleIds.value = ids
}
const readyRuleCount = computed(() => reviewableCards.value.filter((item) => {
  if (hasCurrentConfirmedUserRule(item)) return true
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  return review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && (review.candidate?.kind || 'condition') === expectedKind
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
const finalizeNavSummary = computed(() => {
  if (!projectId.value) return '请先完成第三步规则分析，再进入规则定稿。'
  if (loading.value) return '正在装载第四步定稿结果。'
  if (error.value) return '当前没有可预览的定稿结果，请返回规则分析。'
  if (!segmentCards.value.length) return '当前没有可展示的工序，请先在第三步完成至少一版规则分析结果。'
  if (unresolvedRuleCount.value) return `还有 ${unresolvedRuleCount.value} 道工序需要补充具体条件。`
  if (readyRuleCount.value < reviewableRuleCount.value) {
    if (batchParsing.value) {
      return `正在识别规则；当前 ${readyRuleCount.value}/${reviewableRuleCount.value} 条已识别。`
    }
    return `还有 ${reviewableRuleCount.value - readyRuleCount.value} 条规则待识别，可在对应卡片中重试识别。`
  }
  if (reviewFocusCards.value.length) return `已确认 ${confirmedRuleCount.value}/${reviewableRuleCount.value} 条规则，请核对剩余待处理项。`
  if (precheckResult.value && !precheckResult.value.ok) return `发布预检有 ${precheckBlockerCount.value} 项待修复，请查看预检结果并处理。`
  if (outdatedRulePackageVersion.value) return `规则内容已有变化，原规则包 V${outdatedRulePackageVersion.value} 已过期，请重新完成定稿并发布。`
  if (!lastExportedRulePackageVersion.value) return '规则已全部确认，可发布规则包。'
  return `规则包 V${lastExportedRulePackageVersion.value} 已就绪，可进入规则包验证与路线生成。`
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

function hasCurrentConditionText(segmentId: string, sourceText: string) {
  const current = segmentCards.value.find(item => item.segment.id === segmentId)
  return current?.conditionText.trim() === sourceText.trim()
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
  const sourceText = inlineEditingText.value.trim()
  const changed = saveInlineEdit(item)
  if (!changed) return
  markExportedRulePackageOutdated()
  setConditionBusy(item.segment.id, true)
  try {
    await nextTick()
    const parsed = await parseConditionItem(item, false, sourceText)
    if (parsed) setBatchNotice('修改已保存并识别，请核对后确认规则。')
  } catch (err: any) {
    showFinalizeNotice('规则识别失败', '修改内容已保存在本机草稿，请稍后重试识别。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleResetInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  resetInlineEdit(item)
  markExportedRulePackageOutdated()
  setConditionBusy(item.segment.id, true)
  try {
    await nextTick()
    await parseConditionItem(item, false, item.defaultConditionText)
  } catch (err: any) {
    showFinalizeNotice('规则识别失败', '默认条件已恢复，请稍后重试识别。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function parseConditionItem(
  item: ReturnType<typeof buildFinalizeCards>[number],
  showError = false,
  sourceText = item.conditionText,
  isCurrent = () => true,
) {
  if (!isCurrent() || !projectId.value || !savedRoute.value) return false
  delete conditionErrors.value[item.segment.id]
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  setConditionBusy(item.segment.id, true)
  try {
    const response = await parseRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: savedRoute.value.workflow_revision,
      segment_id: item.segment.id,
      source_text: sourceText,
      process_id: exportProcessIdForItem(item),
      process_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
      processes: conditionProcessOptions.value,
    })
    if (!isCurrent() || projectId.value !== requestProject || savedRoute.value?.route_id !== requestRoute || !hasCurrentConditionText(item.segment.id, sourceText)) return false
    applyConditionReview(item.segment.id, response.review)
    return response.review.status !== 'invalid'
  } catch (err: any) {
    if (await handleWorkflowRevisionConflict(err)) return false
    if (isCurrent() && projectId.value === requestProject && hasCurrentConditionText(item.segment.id, sourceText)) {
      conditionErrors.value[item.segment.id] = `识别失败，描述保留为本机草稿：${conditionErrorMessage(err)}`
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
  await parseConditionItem(item, false)
}

async function handleBatchParseConditions(
  queue = [...batchEligibleCards.value],
  isCurrent = () => true,
) {
  if (batchParsing.value || !queue.length || !isCurrent()) return
  const executionId = ++batchParseExecutionId
  batchParsing.value = true
  batchParseCompleted.value = 0
  batchParseTotal.value = queue.length
  batchNotice.value = ''
  let cursor = 0
  let successCount = 0

  async function worker() {
    while (cursor < queue.length && isCurrent()) {
      const item = queue[cursor++]
      if (!item) continue
      if (await parseConditionItem(item, false, item.conditionText, isCurrent)) successCount += 1
      if (!isCurrent()) return
      batchParseCompleted.value += 1
    }
  }

  try {
    await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
    if (!isCurrent()) return
    const failedCount = queue.length - successCount
    if (failedCount > 0) {
      setBatchNotice(`已识别 ${successCount} 条规则；${failedCount} 条还需要补充。`)
      onlyPending.value = true
    }

  } finally {
    if (executionId === batchParseExecutionId) batchParsing.value = false
  }
}


async function handleConfirmSelectedCandidates() {
  if (batchReviewing.value || !selectedReviewCards.value.length || !projectId.value || !savedRoute.value) return
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
) {
  if (!projectId.value || !savedRoute.value || !item.conditionReview?.source_hash) return
  // A quick confirm and a background candidate refresh must not submit two
  // versions of the same card at once.
  if (conditionBusySegmentIds.value.has(item.segment.id)) return
  markExportedRulePackageOutdated()
  delete conditionErrors.value[item.segment.id]
  const requestProject = projectId.value
  const requestRoute = savedRoute.value.route_id
  const requestSource = item.conditionText
  setConditionBusy(item.segment.id, true)
  try {
    const response = await confirmRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: savedRoute.value.workflow_revision,
      segment_id: item.segment.id,
      source_text: item.conditionText,
      source_hash: item.conditionReview.source_hash,
      candidate,
      processes: conditionProcessOptions.value,
      confirmed_by: '默认用户',
    })
    if (projectId.value !== requestProject || savedRoute.value?.route_id !== requestRoute || !hasCurrentConditionText(item.segment.id, requestSource)) return false
    applyConditionReview(item.segment.id, response.review)
    if (response.review.status !== 'confirmed') {
      conditionErrors.value[item.segment.id] = '规则尚未确认，请核对后重试。'
      return false
    }
    selectedRuleIds.value.delete(item.segment.id)
    if (advance) {
      const nextId = nextPendingSegmentId(segmentCards.value, reviewFocusCards.value, item.segment.id)
      await nextTick()
      if (nextId) focusSegment(nextId)
    }
    return true
  } catch (err: any) {
    if (await handleWorkflowRevisionConflict(err)) return
    if (isConditionSourceConflict(err)) {
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

async function handleSetMainline(item: ReturnType<typeof buildFinalizeCards>[number]) {
  if (!projectId.value || !savedRoute.value || conditionBusySegmentIds.value.has(item.segment.id)) return
  const processName = normalizeExportProcessName(finalizeSegmentDisplayName(item.segment))
  const sourceText = `设置为主工序，始终纳入“${processName}”工序。`
  markExportedRulePackageOutdated()
  setConditionBusy(item.segment.id, true)
  try {
    const response = await saveRuleConditionDraft({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: savedRoute.value.workflow_revision,
      segment_id: item.segment.id,
      source_text: sourceText,
    })
    setConditionTextDraft(item, sourceText)
    applyConditionReview(item.segment.id, response.review)
    setBatchNotice(`"「${processName}」"已转为主工序。`)
  } catch (err: any) {
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
  const processName = normalizeExportProcessName(finalizeSegmentDisplayName(item.segment))
  const switchLabel = label.trim()
  if (!switchLabel) return
  const sourceText = `当用户选择“${switchLabel}”为是时，纳入“${processName}”工序。`
  const candidate = buildManualBooleanRuleCandidate(item, switchLabel)
  markExportedRulePackageOutdated()
  setConditionBusy(item.segment.id, true)
  try {
    const response = await setManualRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: savedRoute.value.workflow_revision,
      segment_id: item.segment.id,
      process_id: exportProcessIdForItem(item),
      source_text: sourceText,
      candidate,
      processes: conditionProcessOptions.value,
      confirmed_by: '用户直接设定',
    })
    setConditionTextDraft(item, sourceText)
    applyConditionReview(item.segment.id, response.review)
    setBatchNotice(`"「${processName}」"已转为用户控制的 Bool 条件。`)
  } catch (err: any) {
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

const {
  exportingRulePackage,
  downloadRuleDocument,
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
  finalSteps: finalizeSegmentStepNodes,
  conditionFields,
  onBlockedCards: (cards) => {
    setBatchNotice(`还有 ${cards.length} 项待处理，请先核对规则。`)
    if (cards[0]) void locateBlockedCard(cards[0].segment.id)
  },
  onExportIssue: (issue) => {
    if (precheckResult.value && !precheckResult.value.ok) return
    exportIssue.value = { ...issue, context: '规则包发布' }
  },
  onPrecheck: (result) => {
    precheckResult.value = result
    if (!result.ok) {
      openPrecheckDialog()
    }
  },
  onExportedVersion: (version, meta) => {
    lastExportedRulePackageVersion.value = version
    outdatedRulePackageVersion.value = null
    console.info(`规则包 V${version} 已发布，可用于第 5 步验证生成。`, meta)
  },
  onWorkflowConflict: () => loadWorkspace(true),
})

const reviewAndExportButtonLabel = computed(() => {
  if (batchParsing.value) return `正在识别 ${batchParseCompleted.value}/${batchParseTotal.value}`
  if (batchReviewing.value) return `正在审核 ${batchReviewCompleted.value}/${batchReviewTotal.value}`
  if (exportingRulePackage.value) return '正在发布规则包...'
  return '发布规则包'
})

async function handleReviewAndExport() {
  if (reviewAndExporting.value || batchParsing.value || batchReviewing.value || exportingRulePackage.value) return
  reviewAndExporting.value = true
  try {
    const remaining = exportBlockingCards(segmentCards.value)
    if (remaining.length) {
      setBatchNotice(`还有 ${remaining.length} 项待处理，请核对并确认后再发布。`)
      await locateBlockedCard(remaining[0].segment.id)
      return
    }
    await downloadRuleDocument()
  } finally {
    reviewAndExporting.value = false
  }
}

const validMappingCount = ref(0)
function goToTemplateMapping() {
  router.push({ path: '/template-mapping', query: buildProjectRouteQuery(projectId.value) })
}

function openPrecheckDialog() {
  openFinalizePrecheckDialog(showPrecheckDialog)
}

function openResetDialog() {
  resetDialogVisible.value = true
}

function handlePrecheckTemplateMapping() {
  showPrecheckDialog.value = false
  goToTemplateMapping()
}

async function handlePrecheckRuleReview(blocker: Record<string, any>) {
  showPrecheckDialog.value = false
  const processName = String(blocker.process_name || '').trim()
  const matchingCard = processName
    ? reviewFocusCards.value.find(item => finalizeSegmentDisplayName(item.segment) === processName)
    : undefined
  const target = matchingCard || reviewFocusCards.value[0] || segmentCards.value[0]
  onlyPending.value = reviewFocusCards.value.length > 0
  if (!target) return
  await nextTick()
  focusSegment(target.segment.id)
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

async function pollRulePreprocessing() {
  if (!projectId.value || !savedRoute.value || preprocessRefreshInFlight) return
  preprocessRefreshInFlight = true
  try {
    const next = await getRulePreprocessingStatus(projectId.value, savedRoute.value.route_id)
    const previous = preprocessStatus.value?.task_status
    preprocessStatus.value = next
    if (next.task_status === 'running' || next.task_status === 'queued') {
      stopPreprocessPolling()
      preprocessPollTimer = window.setTimeout(() => {
        preprocessPollTimer = null
        void pollRulePreprocessing()
      }, 1200)
    } else {
      stopPreprocessPolling()
      if (previous && previous !== next.task_status && next.task_status === 'completed') {
        await loadWorkspace(true)
      }
    }
  } catch (err) {
    console.warn('读取规则预处理状态失败', err)
  } finally {
    preprocessRefreshInFlight = false
  }
}

async function startRulePreprocessingForWorkspace() {
  if (!projectId.value || !savedRoute.value || !reviewableCards.value.length) return
  const triggerKey = buildRulePreprocessingTriggerKey({
    projectId: projectId.value,
    savedRoute: savedRoute.value,
    supersetOperations: supersetOperations.value,
    segmentDisplayName: finalizeSegmentDisplayName,
  })
  if (!triggerKey || triggerKey === lastRulePreprocessTriggerKey) return
  const items = reviewableCards.value.map(item => ({
    segment_id: item.segment.id,
    process_id: exportProcessIdForItem(item),
    process_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
    source_text: item.conditionText,
  })).filter(item => item.process_id && item.source_text.trim())
  if (!items.length) return
  try {
    lastRulePreprocessTriggerKey = triggerKey
    preprocessStatus.value = await startRulePreprocessing({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      expected_workflow_revision: savedRoute.value.workflow_revision,
      items,
      processes: conditionProcessOptions.value,
    })
    if (preprocessStatus.value.task_status === 'running' || preprocessStatus.value.task_status === 'queued') {
      void pollRulePreprocessing()
    }
  } catch (err) {
    lastRulePreprocessTriggerKey = ''
    console.warn('启动规则预处理失败', err)
  }
}

async function loadWorkspace(forceRefresh = false) {
  const request = workspaceRequestGuard.start()
  precheckResult.value = null
  validMappingCount.value = 0
  loading.value = true
  conditionErrors.value = {}
  selectedRuleIds.value = new Set()
  error.value = ''
  workspaceErrorTitle.value = FINALIZE_VIEW_COPY.errorTitle
  try {
    const projectList = await listProjects(forceRefresh)
    if (!request.isCurrent()) return
    const resolvedProjectId = resolveAvailableProjectId(String(route.query.project_id || ''), projectList)
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
    if (String(route.query.project_id || '') !== resolvedProjectId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: resolvedProjectId },
      })
    }
    const currentProject = projectList.find(project => project.id === projectId.value)
    projectName.value = currentProject?.name || `任务 #${projectId.value}`
    const [routeResult, operationList, supersetResult, latestPackage, fieldRegistry, groupTemplate] = await Promise.all([
      getSavedNormalizedRoute(projectId.value, forceRefresh),
      listOperations(projectId.value, forceRefresh),
      getSupersetRoute(projectId.value, forceRefresh),
      getLatestFinalizedRulePackage(projectId.value, forceRefresh).catch(() => null),
      getConditionFieldRegistry(),
      getCurrentGroupTemplate(projectId.value).catch((cause: any) => { if (cause?.response?.status === 404) return null; throw cause }),
    ])
    if (!request.isCurrent()) return
    const mappingStatus = getTemplateMappingStatus(groupTemplate, buildFinalTemplateMappingOperations(routeResult.segments, supersetResult.superset_route || []))
    validMappingCount.value = mappingStatus.validCount
    if (!mappingStatus.validCount) {
      savedRoute.value = null
      await router.replace({ path: '/template-mapping', query: buildProjectRouteQuery(projectId.value) })
      return
    }
    savedRoute.value = routeResult
    operations.value = operationList
    supersetOperations.value = supersetResult.superset_route || []
    conditionFields.value = fieldRegistry.fields || []
    readDrafts()
    activeSegmentId.value = routeResult.segments[0]?.id || ''
    await nextTick()
    lastExportedRulePackageVersion.value = null
    outdatedRulePackageVersion.value = null
    if (latestPackage) {
      const routeMatches = latestPackage.schema_version === '2.0'
        && latestPackage.route_version_id === routeResult.route_id
      if (!routeMatches || !latestPackage.content_hash) {
        outdatedRulePackageVersion.value = latestPackage.version
      } else {
        try {
          const currentPackage = await compileRulePackage(buildCompileRequestFromCards({
            projectId: projectId.value,
            packageName: latestPackage.package_name,
            routeVersionId: routeResult.route_id,
            cards: segmentCards.value,
            displayName: finalizeSegmentDisplayName,
            phaseLabel: resolveFinalizePhase,
            primarySteps: finalizeSegmentPrimarySteps,
            attachedSteps: finalizeSegmentAttachedSteps,
            finalSteps: finalizeSegmentStepNodes,
            conditionFields: conditionFields.value,
          }))
          if (!request.isCurrent()) return
          if (currentPackage.content_hash === latestPackage.content_hash) {
            lastExportedRulePackageVersion.value = latestPackage.version
          } else {
            outdatedRulePackageVersion.value = latestPackage.version
          }
        } catch (hashCheckError) {
          console.warn('无法校验现有规则包是否为最新版本', hashCheckError)
          outdatedRulePackageVersion.value = latestPackage.version
        }
      }
    }
  } catch (err: any) {
    if (!request.isCurrent()) return
    if (Number(err?.response?.status) !== 404) console.error(err)
    savedRoute.value = null
    operations.value = []
    supersetOperations.value = []
    lastExportedRulePackageVersion.value = null
    outdatedRulePackageVersion.value = null
    workspaceErrorTitle.value = Number(err?.response?.status) === 404
      ? '当前任务尚未完成第三步保存'
      : FINALIZE_VIEW_COPY.errorTitle
    error.value = err?.response?.data?.detail || '当前任务还没有第三步可预览的已保存结果，请先回到第三步完成分析。'
  } finally {
    if (!request.isLatest()) return
    loading.value = false
    loadedDataRevision = getWorkflowDataRevision()
    if (savedRoute.value && !error.value) {
      void startRulePreprocessingForWorkspace()
    }
  }
}

async function reloadWorkspace() {
  await loadWorkspace(true)
}

async function handleResetAllRecognition() {
  if (resettingWorkflow.value || !projectId.value || !savedRoute.value) return
  resettingWorkflow.value = true
  batchNotice.value = ''
  try {
    const result = await resetWorkflow({
      project_id: projectId.value,
      from_step: 4,
      expected_workflow_revision: savedRoute.value.workflow_revision,
    })
    publishWorkflowReset({
      projectId: result.project_id,
      fromStep: 4,
      workflowRevision: result.workflow_revision,
    })
    locallyHandledResetAt = workflowResetSignal.value?.emittedAt || 0
    resetDialogVisible.value = false
    onlyPending.value = true
    setBatchNotice('重置完成，正在后台准备重新识别。')
    const task = recognitionTaskGuard.start()
    const context = {
      projectId: result.project_id,
      workflowRevision: result.workflow_revision,
      isCurrent: task.isCurrent,
    }
    runBackgroundTask(() => restartAllRecognitionInBackground(context), (err) => {
      showFinalizeNotice(
        '重新识别失败',
        '现有条件原文仍然保留，请刷新页面后重试。',
        conditionErrorMessage(err),
      )
    })
  } catch (err: any) {
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
  await nextTick()
  const queue = [...batchEligibleCards.value]
  if (!queue.length) {
    setBatchNotice('没有需要重新识别的普通规则；人工设定保持不变。')
    return
  }
  await handleBatchParseConditions(queue, context.isCurrent)
}

watch(() => route.query.project_id, () => {
  if (!finalizeViewActive) return
  stopPreprocessPolling()
  preprocessStatus.value = null
  recognitionTaskGuard.cancel()
  batchParseExecutionId += 1
  batchParsing.value = false
  void loadWorkspace()
})

watch(workflowResetSignal, (signal) => {
  if (!signal || signal.emittedAt === locallyHandledResetAt) return
  if (signal.projectId !== projectId.value || signal.fromStep > 4) return
  locallyHandledResetAt = signal.emittedAt
  recognitionTaskGuard.cancel()
  batchParseExecutionId += 1
  batchParsing.value = false
  if (signal.fromStep <= 3) clearAllDrafts()
  void loadWorkspace(true)
})

// Selection is tied to the candidate source, so refreshed/edited candidates need a new explicit selection.
watch(() => pendingReviewCards.value.map(item => [item.segment.id, `${item.conditionReview?.source_hash}:${JSON.stringify(item.conditionReview?.candidate)}`] as const), (current, previous) => {
  const before = new Map(previous || [])
  selectedRuleIds.value = new Set(current.filter(([id, signature]) => selectedRuleIds.value.has(id) && before.get(id) === signature).map(([id]) => id))
})
watch(() => projectId.value, () => { conditionErrors.value = {}; selectedRuleIds.value = new Set() })

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
  if (!projectChanged && loadedDataRevision === getWorkflowDataRevision()) {
    const pid = projectId.value
    if (pid && savedRoute.value) void getCurrentGroupTemplate(pid).then(template => {
      if (!finalizeViewActive || projectId.value !== pid || !savedRoute.value) return
      validMappingCount.value = getTemplateMappingStatus(template, buildFinalTemplateMappingOperations(savedRoute.value.segments, supersetOperations.value)).validCount
      if (!validMappingCount.value) goToTemplateMapping()
    }).catch(() => { if (finalizeViewActive && projectId.value === pid) goToTemplateMapping() })
    return
  }
  void loadWorkspace()
})

onDeactivated(() => {
  finalizeViewActive = false
  stopPreprocessPolling()
  recognitionTaskGuard.cancel()
  batchParseExecutionId += 1
  batchParsing.value = false
  loadedDataRevision = getWorkflowDataRevision()
})
</script>

<style scoped>
.rule-review-toolbar { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 12px; padding: 10px 14px; border: 1px solid #e2e8f0; border-radius: 8px; background: #fff; color: #64748b; font-size: 12px; }
.rule-review-actions { display: flex; align-items: center; gap: 8px; }

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
  flex-wrap: wrap;
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
  gap: 12px;
  margin-left: 4px;
  border-left: 1px solid #cbd5e1;
  padding-left: 12px;
  min-width: 0;
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

.ash-review-progress {
  display: inline-flex;
  align-items: center;
  gap: 7px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}

.ash-review-progress strong { color: #0f172a; font-weight: 700; }

.ash-publish-state {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  padding: 4px 9px;
  border: 1px solid #bbf7d0;
  border-radius: 999px;
  color: #166534;
  background: #f0fdf4;
  font-size: 12px;
  line-height: 1;
  font-family: inherit;
  text-align: left;
  cursor: default;
}

.ash-publish-state:disabled { opacity: 1; cursor: default; }

.ash-publish-state--blocked {
  border-color: #fed7aa;
  color: #9a3412;
  background: #fff7ed;
}

.ash-publish-state-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  background: #22c55e;
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
  color: #4f46e5;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  cursor: pointer;
}

.ash-template-link:hover { color: #3730a3; text-decoration: underline; }

.ash-quiet-action,
.ash-icon-action {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-height: 30px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: transparent;
  color: #64748b;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: color .15s ease, background-color .15s ease, border-color .15s ease;
}

.ash-quiet-action { padding: 5px 7px; white-space: nowrap; }
.ash-quiet-action:hover:not(:disabled) { background: #f1f5f9; color: #334155; }
.ash-icon-action { width: 30px; padding: 0; }
.ash-icon-action:hover:not(:disabled) { border-color: #e2e8f0; background: #f8fafc; color: #334155; }
.ash-quiet-action:disabled,
.ash-icon-action:disabled { color: #94a3b8; cursor: not-allowed; }
.ash-quiet-action:focus-visible,
.ash-icon-action:focus-visible { outline: 2px solid #818cf8; outline-offset: 2px; }

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

.export-blocker-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(2px);
}

.export-blocker-dialog {
  width: min(520px, 100%);
  max-height: min(680px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  background: #ffffff;
  box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.12), 0 8px 10px -6px rgba(15, 23, 42, 0.08);
}

.export-blocker-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 20px 24px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.export-blocker-kicker {
  display: inline-block;
  margin-bottom: 4px;
  color: #64748b;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.export-blocker-header h2 {
  margin: 0;
  color: #0f172a;
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
  color: #64748b;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.15s, color 0.15s;
}

.export-blocker-close:hover {
  background: #f1f5f9;
  color: #1e293b;
}

.export-blocker-copy {
  margin: 0;
  padding: 14px 24px;
  color: #475569;
  font-size: 14px;
  line-height: 1.7;
  font-weight: 400;
  background: #f8fafc;
  border-bottom: 1px solid #f1f5f9;
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
  color: #334155;
}

.export-blocker-group-head span {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 500;
  color: #64748b;
  background: #f1f5f9;
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
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  transition: border-color 0.15s ease, background-color 0.15s ease, box-shadow 0.15s ease;
}

.export-blocker-list-item--clickable {
  cursor: pointer;
}

.export-blocker-list-item--clickable:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.export-blocker-list span {
  display: inline-block;
  min-width: 28px;
  color: #64748b;
  font-size: 13px;
  font-weight: 500;
  font-variant-numeric: tabular-nums;
  letter-spacing: 0;
}

.export-blocker-list strong {
  flex: 1;
  overflow: hidden;
  color: #1e293b;
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
  background: #fff7ed;
  color: #c2410c;
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
  border-top: 1px solid #e2e8f0;
  background: #ffffff;
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
  background: #1e293b;
  color: #f8fafc;
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
  border: 1px solid #fed7aa;
  border-radius: 10px;
  background: linear-gradient(135deg, #fff7ed 0%, #fffaf5 100%);
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
  color: #fff;
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
  color: #9a3412;
  font-size: 12px;
  line-height: 1.45;
}

.preprocess-failure-list {
  margin: 10px 0 0 30px;
  padding: 0;
  color: #9a3412;
  font-size: 12px;
  line-height: 1.5;
}

.preprocess-failure-list li {
  margin: 2px 0;
  word-break: break-word;
}

.preprocess-failure-more {
  margin: 8px 0 0 30px;
  color: #c2410c;
  font-size: 12px;
  line-height: 1.45;
}

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

.finalize-empty-state {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 36px;
  color: #64748b;
  font-size: 12.5px;
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

  .ash-actions > .ash-template-link { width: auto; justify-self: start; }
  .ash-actions > .ash-btn-primary { grid-column: 1 / -1; }
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
  padding: 34px 28px 38px;
  background: linear-gradient(180deg, #ffffff 0%, #fbfcff 100%);
}

.empty-mark {
  font-size: 28px;
  font-weight: 700;
  color: #94a3b8;
  margin-bottom: 12px;
}

.empty-mark--success {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  margin: 0 auto 12px;
  border-radius: 50%;
  color: #15803d;
  background: #dcfce7;
  font-size: 22px;
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

.empty-mark--warning {
  display: grid;
  place-items: center;
  width: 36px;
  height: 36px;
  margin: 0 auto 12px;
  border-radius: 50%;
  color: #c2410c;
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
  transform: translateY(-1px);
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
</style>
