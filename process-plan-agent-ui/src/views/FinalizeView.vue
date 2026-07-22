<template>
  <div class="finalize-view">
    <div class="analysis-style-header">
      <div class="ash-left-content">
        <span class="ash-page-title">规则定稿</span>
        <span class="ash-dark-chip">{{ projectName || '未命名任务' }}</span>
        
        <div class="ash-meta-section">
          <span class="ash-meta-item">已保存版本 <strong>V{{ savedRoute?.version || '-' }}</strong></span>
          <span class="ash-meta-item" v-if="lastExportedRulePackageVersion">规则包 <strong>V{{ lastExportedRulePackageVersion }}</strong></span>
          <span class="ash-meta-item">主线 <strong>{{ mainlineRuleCount }}</strong></span>
          <span class="ash-meta-item">条件 <strong>{{ conditionalRuleCount }}</strong></span>
          <span class="ash-meta-item" v-if="relationRuleCount">关联 <strong>{{ relationRuleCount }}</strong></span>
          <span class="ash-meta-item" v-if="unresolvedRuleCount">待补充 <strong class="warning-text">{{ unresolvedRuleCount }}</strong></span>
          <!-- Progress bar review indicator -->
          <span class="ash-meta-item ash-meta-progress-item" v-if="reviewableRuleCount > 0">
            <span>审核</span>
            <div class="mini-progress-bar">
              <div
                class="mini-progress-fill"
                :class="{ 'mini-progress-fill--done': confirmedRuleCount === reviewableRuleCount }"
                :style="{ width: `${reviewProgressPercent}%` }"
              ></div>
            </div>
            <strong :class="{ 'text-done': confirmedRuleCount === reviewableRuleCount }">
              {{ confirmedRuleCount }}/{{ reviewableRuleCount }}
            </strong>
          </span>
        </div>
      </div>

      <div class="ash-actions">
        <!-- 更新候选规则 (phase-highlighted when it's the active step) -->
        <button
          class="ash-btn-primary"
          :class="{ 'ash-btn-phase-active': currentPhaseAction === 'parse' }"
          @click="() => handleBatchParseConditions()"
          :disabled="batchParsing || !batchEligibleCards.length"
        >
          {{ batchParsing ? `生成中 ${batchParseCompleted}/${batchParseTotal}` : `更新候选规则${batchEligibleCards.length ? ` (${batchEligibleCards.length})` : ''}` }}
        </button>

        <!-- 完成审核 (phase-highlighted when it's the active step) -->
        <button
          class="ash-btn-primary ash-btn-review"
          :class="{ 'ash-btn-phase-active': currentPhaseAction === 'review' }"
          @click="handleCompleteReview"
          :disabled="batchReviewing || !pendingReviewCards.length"
        >
          {{ batchReviewing ? `审核中 ${batchReviewCompleted}/${batchReviewTotal}` : `完成审核${pendingReviewCards.length ? ` (${pendingReviewCards.length})` : ''}` }}
        </button>

        <!-- 导出规则包 (phase-highlighted when it's the final step) -->
        <button
          class="ash-btn-outline"
          :class="{ 'ash-btn-phase-active': currentPhaseAction === 'export' }"
          @click="downloadRuleDocument"
          :disabled="exportingRulePackage || !segmentCards.length"
        >
          {{ exportingRulePackage ? '正在导出...' : FINALIZE_VIEW_COPY.exportDocument }}
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
          <span class="toggle-filter-text">审核重点</span>
        </label>

        <!-- Icon: refresh -->
        <button
          class="icon-refresh-btn"
          :class="{ 'icon-refresh-btn--spinning': loading }"
          @click="reloadWorkspace"
          :disabled="loading || !projectId"
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

    <!-- All-done banner -->
    <Transition name="banner-slide">
      <div v-if="allReviewDone && !lastExportedRulePackageVersion" class="all-done-banner">
        <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
          <path d="M22 4L12 14.01l-3-3"/>
        </svg>
        <span>所有规则已审核完成，可以导出规则包了</span>
        <button class="banner-export-btn" @click="downloadRuleDocument" :disabled="exportingRulePackage">
          {{ exportingRulePackage ? '导出中…' : '立即导出 →' }}
        </button>
      </div>
    </Transition>

    <div v-if="batchNotice" class="batch-notice">{{ batchNotice }}</div>

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
      <div class="empty-title">当前没有审核重点</div>
      <div class="empty-text">没有关联规则、动态字段或待补充条件需要重点查看；可切换到全部规则浏览。</div>
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
          :process-options="conditionProcessOptions"
          :condition-busy="conditionBusySegmentIds.has(item.segment.id)"
          :set-inline-textarea-ref="setInlineTextareaRef"
          @reset="handleResetInlineEdit"
          @start-edit="startInlineEdit"
          @cancel="cancelInlineEdit"
          @save="handleSaveInlineEdit"
          @parse-condition="handleParseCondition"
          @confirm-condition="handleConfirmCondition"
          @update:inline-editing-text="inlineEditingText = $event"
        />
      </section>
    </div>

    <WorkflowNavFooter
      :summary="finalizeNavSummary"
      previous-label="← 返回规则分析"
      next-label="进入路线生成 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId || !lastExportedRulePackageVersion"
      @previous="goBackToAnalysis"
      @next="goToGenerate"
    />

    <div v-if="blockedExportCards.length" class="export-blocker-overlay" @click.self="closeBlockedExportDialog">
      <section class="export-blocker-dialog" role="dialog" aria-modal="true" aria-labelledby="export-blocker-title">
        <div class="export-blocker-header">
          <div>
            <span class="export-blocker-kicker">规则包导出</span>
            <h2 id="export-blocker-title">还有 {{ blockedExportCards.length }} 道工序需要处理</h2>
          </div>
          <button class="export-blocker-close" aria-label="关闭提示" @click="closeBlockedExportDialog">关闭</button>
        </div>
        <p class="export-blocker-copy">请先完成候选规则审核，或为待补充项补全判断依据。完成后即可导出规则包。</p>
        <ol class="export-blocker-list">
          <li v-for="item in blockedExportCards.slice(0, 6)" :key="item.segment.id">
            <span>{{ item.segment.sequence }}</span>
            <strong>{{ finalizeSegmentDisplayName(item.segment) }}</strong>
            <em>{{ finalizeRuleMode(item) === 'relation' ? '关联待审核' : finalizeRuleMode(item) === 'unresolved' ? '待补充条件' : '条件待审核' }}</em>
          </li>
        </ol>
        <p v-if="blockedExportCards.length > 6" class="export-blocker-more">另有 {{ blockedExportCards.length - 6 }} 道工序待处理。</p>
        <div class="export-blocker-actions">
          <button class="ash-btn-outline" @click="closeBlockedExportDialog">暂不处理</button>
          <button class="ash-btn-primary" @click="showBlockedExportCards">查看待处理</button>
        </div>
      </section>
    </div>

    <div v-if="exportIssue" class="export-issue-overlay" @click.self="closeExportIssue">
      <section class="export-issue-dialog" role="dialog" aria-modal="true" aria-labelledby="export-issue-title">
        <div class="export-issue-icon" aria-hidden="true">!</div>
        <div class="export-issue-content">
          <span class="export-issue-kicker">{{ exportIssue.context || '规则包导出' }}</span>
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

  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onActivated, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import FinalizeRouteNav from '@/components/finalize/FinalizeRouteNav.vue'
import FinalizeRuleCard from '@/components/finalize/FinalizeRuleCard.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
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
  confirmRuleCondition,
  getConditionFieldRegistry,
  parseRuleCondition,
  saveRuleConditionDraft,
  type CanonicalConditionField,
  type RuleConditionCandidate,
  type RuleConditionProcessOption,
  type RuleConditionReview,
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
import { useFinalizeRulePackageExport } from '@/composables/useFinalizeRulePackageExport'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { buildProjectRouteQuery, resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'
import {
  exportProcessIdForItem,
  finalizeRuleMode,
  hasCurrentConfirmedUserRule,
  normalizeExportProcessName,
} from '@/utils/finalizeRulePackage'

const route = useRoute()
const router = useRouter()
let finalizeViewActive = false
let initialLoadFinished = false
let loadedDataRevision = -1

const loading = ref(false)
const error = ref('')
const projectId = ref<number | null>(null)
const projectName = ref('')
const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
const operations = ref<OperationItem[]>([])
const supersetOperations = ref<OperationItem[]>([])
const onlyPending = ref(true)
const activeSegmentId = ref('')
const lastExportedRulePackageVersion = ref<number | null>(null)
const conditionFields = ref<CanonicalConditionField[]>([])
const conditionBusySegmentIds = ref(new Set<string>())
const batchParsing = ref(false)
const batchParseCompleted = ref(0)
const batchParseTotal = ref(0)
const batchReviewing = ref(false)
const batchReviewCompleted = ref(0)
const batchReviewTotal = ref(0)
const batchNotice = ref('')
const blockedExportCards = ref<FinalizeCard[]>([])
const exportIssue = ref<{ title: string; summary: string; details?: string; context?: string } | null>(null)
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

const mainlineRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'mainline').length)
const conditionalCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'conditional'))
const relationCards = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'relation'))
const reviewableCards = computed(() => [...conditionalCards.value, ...relationCards.value])
const conditionalRuleCount = computed(() => conditionalCards.value.length)
const relationRuleCount = computed(() => relationCards.value.length)
const reviewableRuleCount = computed(() => reviewableCards.value.length)
const confirmedRuleCount = computed(() => reviewableCards.value.filter(hasCurrentConfirmedUserRule).length)
const unresolvedRuleCount = computed(() => segmentCards.value.filter(item => finalizeRuleMode(item) === 'unresolved').length)
const reviewFocusCards = computed(() => segmentCards.value.filter(itemNeedsPending))
const visibleSegments = computed(() => onlyPending.value ? reviewFocusCards.value : segmentCards.value)
const batchEligibleCards = computed(() => reviewableCards.value.filter((item) => {
  if (hasCurrentConfirmedUserRule(item)) return false
  const review = item.conditionReview
  const sourceMatches = review?.source_text?.trim() === item.conditionText.trim()
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  const hasCurrentCandidate = sourceMatches
    && review?.status === 'pending_confirmation'
    && (review.candidate?.kind || 'condition') === expectedKind
  return !hasCurrentCandidate
}))
const pendingReviewCards = computed(() => reviewableCards.value.filter((item) => {
  const review = item.conditionReview
  const expectedKind = finalizeRuleMode(item) === 'relation' ? 'process_relation' : 'condition'
  return review?.status === 'pending_confirmation'
    && review.source_text.trim() === item.conditionText.trim()
    && (review.candidate?.kind || 'condition') === expectedKind
}))
const conditionProcessOptions = computed<RuleConditionProcessOption[]>(() => {
  const options = new Map<string, RuleConditionProcessOption>()
  segmentCards.value.forEach((item) => {
    const processId = exportProcessIdForItem(item)
    if (!processId || options.has(processId)) return
    options.set(processId, {
      process_id: processId,
      display_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
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
    return `规则已审核 ${confirmedRuleCount.value}/${reviewableRuleCount.value}，请完成剩余条件和关联工序审核。`
  }
  if (!lastExportedRulePackageVersion.value) return '请先导出规则包，导出后即可进入路线生成。'
  return `规则包 V${lastExportedRulePackageVersion.value} 已就绪，可进入路线生成。`
})

/** Progress percent for the mini progress bar */
const reviewProgressPercent = computed(() =>
  reviewableRuleCount.value === 0 ? 0 : Math.round((confirmedRuleCount.value / reviewableRuleCount.value) * 100)
)

/** Which action is the current recommended phase */
const currentPhaseAction = computed(() => {
  if (batchEligibleCards.value.length > 0) return 'parse'
  if (pendingReviewCards.value.length > 0) return 'review'
  return 'export'
})

/** True when all reviewable rules have been confirmed */
const allReviewDone = computed(() =>
  reviewableRuleCount.value > 0 && confirmedRuleCount.value === reviewableRuleCount.value
)

/** Whether a given nav item needs attention */
function itemNeedsPending(item: FinalizeCard): boolean {
  const mode = finalizeRuleMode(item)
  if (mode === 'unresolved') return true
  if (mode === 'relation' || mode === 'conditional') return !hasCurrentConfirmedUserRule(item)
  return false
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

function closeBlockedExportDialog() {
  blockedExportCards.value = []
}

function closeExportIssue() {
  exportIssue.value = null
}

function showFinalizeNotice(title: string, summary: string, details = '') {
  exportIssue.value = { title, summary, details, context: '规则定稿' }
}

async function showBlockedExportCards() {
  const first = blockedExportCards.value[0]
  onlyPending.value = false
  blockedExportCards.value = []
  await nextTick()
  if (first) focusSegment(first.segment.id)
}

function setConditionBusy(segmentId: string, busy: boolean) {
  const next = new Set(conditionBusySegmentIds.value)
  if (busy) next.add(segmentId)
  else next.delete(segmentId)
  conditionBusySegmentIds.value = next
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

async function persistConditionDraft(item: ReturnType<typeof buildFinalizeCards>[number], sourceText: string) {
  if (!projectId.value || !savedRoute.value) return
  const response = await saveRuleConditionDraft({
    project_id: projectId.value,
    route_id: savedRoute.value.route_id,
    segment_id: item.segment.id,
    source_text: sourceText,
  })
  applyConditionReview(item.segment.id, response.review)
}

async function handleSaveInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  const sourceText = inlineEditingText.value.trim()
  saveInlineEdit(item)
  setConditionBusy(item.segment.id, true)
  try {
    await persistConditionDraft(item, sourceText)
    await nextTick()
    await parseConditionItem(item, true, sourceText)
  } catch (err: any) {
    showFinalizeNotice('条件保存失败', '条件文字尚未保存，请检查后重试。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleResetInlineEdit(item: ReturnType<typeof buildFinalizeCards>[number]) {
  resetInlineEdit(item)
  setConditionBusy(item.segment.id, true)
  try {
    await persistConditionDraft(item, item.defaultConditionText)
    await nextTick()
    await parseConditionItem(item, false, item.defaultConditionText)
  } catch (err: any) {
    showFinalizeNotice('条件重置失败', '默认条件尚未恢复，请检查后重试。', conditionErrorMessage(err))
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function parseConditionItem(
  item: ReturnType<typeof buildFinalizeCards>[number],
  showError = false,
  sourceText = item.conditionText,
) {
  if (!projectId.value || !savedRoute.value) return
  setConditionBusy(item.segment.id, true)
  try {
    const response = await parseRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      segment_id: item.segment.id,
      source_text: sourceText,
      process_id: exportProcessIdForItem(item),
      process_name: normalizeExportProcessName(finalizeSegmentDisplayName(item.segment)),
      processes: conditionProcessOptions.value,
    })
    applyConditionReview(item.segment.id, response.review)
    return response.review.status !== 'invalid'
  } catch (err: any) {
    if (showError) {
      console.error('条件候选规则生成失败', err)
      showFinalizeNotice('暂时无法生成候选规则', '请补充明确的判断字段、比较关系或取值后重新解析。', conditionErrorMessage(err))
    }
    return false
  } finally {
    setConditionBusy(item.segment.id, false)
  }
}

async function handleParseCondition(item: ReturnType<typeof buildFinalizeCards>[number]) {
  await parseConditionItem(item, true)
}

async function handleBatchParseConditions(automatic = false) {
  if (batchParsing.value || !batchEligibleCards.value.length) return
  const queue = [...batchEligibleCards.value]
  batchParsing.value = true
  batchParseCompleted.value = 0
  batchParseTotal.value = queue.length
  batchNotice.value = ''
  let cursor = 0
  let successCount = 0

  async function worker() {
    while (cursor < queue.length) {
      const item = queue[cursor++]
      if (!item) continue
      if (await parseConditionItem(item)) successCount += 1
      batchParseCompleted.value += 1
    }
  }

  try {
    await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
    const failedCount = queue.length - successCount
    batchNotice.value = failedCount
      ? `${automatic ? '已自动生成' : '已生成'} ${successCount} 条候选规则；${failedCount} 条条件还需要补充后再生成。`
      : `${automatic ? '已自动生成' : '已生成'} ${successCount} 条候选规则，请核对后完成本次审核。`
    onlyPending.value = true
  } finally {
    batchParsing.value = false
  }
}

async function handleCompleteReview() {
  if (batchReviewing.value || !pendingReviewCards.value.length || !projectId.value || !savedRoute.value) return
  const queue = [...pendingReviewCards.value]
  batchReviewing.value = true
  batchReviewCompleted.value = 0
  batchReviewTotal.value = queue.length
  batchNotice.value = ''
  let cursor = 0
  let successCount = 0

  async function worker() {
    while (cursor < queue.length) {
      const item = queue[cursor++]
      const review = item?.conditionReview
      if (!item || !review?.candidate || !review.source_hash) continue
      setConditionBusy(item.segment.id, true)
      try {
        const response = await confirmRuleCondition({
          project_id: projectId.value!,
          route_id: savedRoute.value!.route_id,
          segment_id: item.segment.id,
          source_text: item.conditionText,
          source_hash: review.source_hash,
          candidate: review.candidate,
          processes: conditionProcessOptions.value,
          confirmed_by: '审核通过',
        })
        applyConditionReview(item.segment.id, response.review)
        successCount += 1
      } catch (err: any) {
        console.error(`规则审核失败：${item.segment.id}`, err)
      } finally {
        setConditionBusy(item.segment.id, false)
        batchReviewCompleted.value += 1
      }
    }
  }

  try {
    await Promise.all(Array.from({ length: Math.min(3, queue.length) }, () => worker()))
    const failedCount = queue.length - successCount
    batchNotice.value = failedCount
      ? `已完成 ${successCount} 道工序审核；${failedCount} 道未完成，请检查后重试。`
      : `已完成 ${successCount} 道工序审核。`
  } finally {
    batchReviewing.value = false
  }
}

async function handleConfirmCondition(
  item: ReturnType<typeof buildFinalizeCards>[number],
  candidate: RuleConditionCandidate,
) {
  if (!projectId.value || !savedRoute.value || !item.conditionReview?.source_hash) return
  setConditionBusy(item.segment.id, true)
  try {
    const response = await confirmRuleCondition({
      project_id: projectId.value,
      route_id: savedRoute.value.route_id,
      segment_id: item.segment.id,
      source_text: item.conditionText,
      source_hash: item.conditionReview.source_hash,
      candidate,
      processes: conditionProcessOptions.value,
      confirmed_by: '默认用户',
    })
    applyConditionReview(item.segment.id, response.review)
  } catch (err: any) {
    showFinalizeNotice('规则确认失败', '候选规则尚未确认，请检查条件和目标工序后重试。', conditionErrorMessage(err))
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
  conditionFields,
  onBlockedCards: (cards) => {
    blockedExportCards.value = cards
  },
  onExportIssue: (issue) => {
    exportIssue.value = { ...issue, context: '规则包导出' }
  },
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

function goToGenerate() {
  router.push({
    path: '/generate',
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
    const [routeResult, operationList, supersetResult, latestPackage, fieldRegistry] = await Promise.all([
      getSavedNormalizedRoute(projectId.value, forceRefresh),
      listOperations(projectId.value, forceRefresh),
      getSupersetRoute(projectId.value, forceRefresh),
      getLatestFinalizedRulePackage(projectId.value, forceRefresh).catch(() => null),
      getConditionFieldRegistry(),
    ])
    savedRoute.value = routeResult
    operations.value = operationList
    supersetOperations.value = supersetResult.superset_route || []
    projectName.value = currentProject?.name || `任务 #${projectId.value}`
    lastExportedRulePackageVersion.value = latestPackage?.version || null
    conditionFields.value = fieldRegistry.fields || []
    readDrafts()
    activeSegmentId.value = routeResult.segments[0]?.id || ''
    await nextTick()
    if (batchEligibleCards.value.length && !batchParsing.value) {
      void handleBatchParseConditions(true)
    }
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
    loadedDataRevision = getWorkflowDataRevision()
  }
}

async function reloadWorkspace() {
  await loadWorkspace(true)
}

watch(() => route.query.project_id, () => {
  if (!finalizeViewActive) return
  void loadWorkspace()
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
  if (!projectChanged && loadedDataRevision === getWorkflowDataRevision()) return
  void loadWorkspace()
})

onDeactivated(() => {
  finalizeViewActive = false
  loadedDataRevision = getWorkflowDataRevision()
})
</script>

<style scoped>
.finalize-view {
  --workflow-nav-right-inset: 0px;
  padding: 0;
  min-height: calc(100vh - 128px);
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
  background: #0f172a;
  color: #f1f5f9;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 700;
  flex-shrink: 0;
}

.ash-meta-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: 12px;
  border-left: 1px solid #cbd5e1;
  padding-left: 16px;
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
  border: 1px solid #cbd5e1;
  color: #475569;
  padding: 3px 12px;
  border-radius: 7px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.ash-btn-outline:hover { background: #f8fafc; border-color: #cbd5e1; color: #0f172a; }
.ash-btn-outline:disabled { opacity: 0.5; cursor: not-allowed; }

.ash-btn-primary {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  padding: 4px 12px;
  border: 1px solid #405987;
  border-radius: 7px;
  background: #405987;
  color: #fff;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: background .15s ease, border-color .15s ease;
}
.ash-btn-primary:hover { background: #334a75; border-color: #334a75; }
.ash-btn-primary:disabled { opacity: .48; cursor: not-allowed; }

.export-blocker-overlay {
  position: fixed;
  inset: 0;
  z-index: 60;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.42);
}

.export-blocker-dialog {
  width: min(540px, 100%);
  max-height: min(680px, calc(100vh - 48px));
  overflow: auto;
  border: 1px solid #d8e1ec;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 20px 55px rgba(15, 23, 42, 0.22);
}

.export-blocker-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 22px 24px 15px;
  border-bottom: 1px solid #e7edf4;
}

.export-blocker-kicker {
  display: block;
  margin-bottom: 5px;
  color: #667991;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0;
}

.export-blocker-header h2 {
  margin: 0;
  color: #1e334c;
  font-size: 19px;
  line-height: 1.35;
}

.export-blocker-close {
  flex: none;
  border: 0;
  background: transparent;
  color: #697b90;
  font-size: 12px;
  cursor: pointer;
  padding: 4px 0;
}

.export-blocker-close:hover { color: #263b54; }

.export-blocker-copy {
  margin: 0;
  padding: 16px 24px 12px;
  color: #566a82;
  font-size: 13px;
  line-height: 1.65;
}

.export-blocker-list {
  display: grid;
  gap: 6px;
  margin: 0;
  padding: 0 24px;
  list-style: none;
}

.export-blocker-list li {
  display: grid;
  grid-template-columns: 38px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  min-height: 38px;
  padding: 0 10px;
  border: 1px solid #e3eaf2;
  border-radius: 5px;
  background: #f8fafc;
}

.export-blocker-list span {
  color: #71839a;
  font-size: 12px;
  font-variant-numeric: tabular-nums;
}

.export-blocker-list strong {
  overflow: hidden;
  color: #2c4058;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.export-blocker-list em {
  color: #a35436;
  font-size: 11px;
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
  gap: 8px;
  margin-top: 18px;
  padding: 14px 24px;
  border-top: 1px solid #e7edf4;
  background: #fbfcfe;
}

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

.highlight-text { color: #ea580c !important; }

/* ===== Phase-active button highlight ===== */
.ash-btn-primary.ash-btn-phase-active {
  box-shadow: 0 0 0 2px rgba(64, 89, 135, 0.35), 0 4px 12px rgba(64, 89, 135, 0.22);
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
  border: 1px solid #e2e8f0; border-radius: 7px;
  background: #ffffff; color: #64748b;
  cursor: pointer; transition: all 0.15s ease;
  flex-shrink: 0;
}
.icon-refresh-btn:hover:not(:disabled) { background: #f8fafc; border-color: #94a3b8; color: #334155; }
.icon-refresh-btn:disabled { opacity: 0.45; cursor: not-allowed; }
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

/* ===== All-done banner ===== */
.all-done-banner {
  display: flex; align-items: center; gap: 10px;
  margin-bottom: 10px;
  padding: 10px 16px;
  border: 1px solid #bbf7d0;
  border-radius: 9px;
  background: linear-gradient(135deg, #f0fdf4, #ecfdf5);
  color: #15803d;
  font-size: 13px; font-weight: 600;
}
.banner-export-btn {
  margin-left: auto;
  flex-shrink: 0;
  padding: 5px 14px;
  border: 1px solid #16a34a; border-radius: 7px;
  background: #16a34a; color: #ffffff;
  font-size: 12px; font-weight: 700; cursor: pointer;
  transition: all 0.15s ease;
}
.banner-export-btn:hover:not(:disabled) { background: #15803d; border-color: #15803d; }
.banner-export-btn:disabled { opacity: 0.55; cursor: not-allowed; }

/* banner transition */
.banner-slide-enter-active { transition: all 0.3s cubic-bezier(0.34, 1.56, 0.64, 1); }
.banner-slide-leave-active { transition: all 0.2s ease-in; }
.banner-slide-enter-from { opacity: 0; transform: translateY(-8px); }
.banner-slide-leave-to   { opacity: 0; transform: translateY(-4px); }

.finalize-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  height: calc(100vh - 178px);
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

.export-issue-overlay {
  position: fixed;
  z-index: 40;
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
