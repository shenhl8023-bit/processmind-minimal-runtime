<template>
  <div class="analysis-view">
    <div class="analysis-hero workflow-page-header">
      <div class="analysis-hero-info workflow-page-info">
        <div class="analysis-hero-title workflow-page-title">规则分析</div>
      </div>
      <div class="analysis-actions workflow-page-actions">
        <button
          class="btn-accept-all-global"
          @click="acceptAllRecommendedForAllSegments"
          :disabled="analysisReadOnly || loading || guidanceGenerating || resettingWorkflow || batchAcceptingAll || !analysisGuidance || !savedRoute || !pendingSegmentCount"
        >
          <span v-if="batchAcceptingAll" class="btn-accept-all-spinner" />
          <svg v-else xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="btn-accept-all-global-icon">
            <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 21l-.813-5.096L3 15l5.096-.813L9 9l.813 5.187L15 15l-5.187.904zM18 10.5l-.5 2.5-.5-2.5-2.5-.5 2.5-.5.5-2.5.5 2.5 2.5.5-2.5.5z" />
          </svg>
          {{ batchAcceptingAll ? `正在采纳 (${batchAcceptProgress})...` : '一键采纳全部推荐' }}
          <span v-if="pendingSegmentCount && !batchAcceptingAll" class="btn-accept-all-global-count">{{ pendingSegmentCount }}</span>
        </button>
        <button class="btn btn-outline btn-sm" @click="resetDialogVisible = true" :disabled="loading || guidanceGenerating || resettingWorkflow || !savedRoute">
          重新回答全部
        </button>
      </div>
    </div>

    <div v-if="!projectId" class="analysis-empty">
      <div class="empty-mark">01</div>
      <div class="empty-title">还没有选中任务</div>
      <div class="empty-text">请先回到路线归并页选择任务并保存一版标准化路线。</div>
    </div>

    <div v-else-if="loading" class="analysis-empty">
      <div class="empty-mark">···</div>
      <div class="empty-title">正在装载已保存路线</div>
      <div class="empty-text">系统正在读取最新保存版本和对应证据。</div>
    </div>

    <div v-else-if="!savedRoute && error" class="analysis-empty analysis-empty-error">
      <div class="empty-mark">!</div>
      <div class="empty-title">暂时还没有可分析的已保存路线</div>
      <div class="empty-text">{{ error }}</div>
      <button class="btn btn-primary" @click="goBackToExtract">返回并保存路线</button>
    </div>

    <template v-else-if="savedRoute">
      <div class="analysis-layout">
        <AnalysisRouteList
          :segments="filteredSegments"
          :selected-segment-id="selectedSegmentId"
          :segment-display-name="segmentDisplayName"
          :segment-progress-class="segmentProgressClass"
          :segment-progress-label="segmentProgressLabel"
          :segment-coverage-label="segmentCoverageLabel"
          :segment-phase-label="segmentPhaseLabel"
          :segment-step-count="segmentStepCount"
          :is-segment-steps-expanded="isSegmentStepsExpanded"
          :toggle-segment-steps="toggleSegmentSteps"
          :segment-primary-steps="segmentPrimarySteps"
          :segment-attached-steps="segmentAttachedSteps"
          @select="selectedSegmentId = $event"
        >
          <template #filters>
            <div class="analysis-filter-options" role="group" aria-label="工序筛选">
              <button
                v-for="option in segmentFilterOptions"
                :key="option.value"
                type="button"
                class="analysis-filter-btn"
                :class="{ active: segmentFilter === option.value }"
                :aria-pressed="segmentFilter === option.value"
                @click="segmentFilter = option.value"
              >
                {{ option.label }} <span>{{ option.count }}</span>
              </button>
            </div>
          </template>
        </AnalysisRouteList>

        <section class="analysis-column analysis-column-right" v-if="selectedSegment && filteredSegments.length">
          <div class="detail-hero">
            <div class="detail-hero-row">
              <div class="detail-hero-title-group">
                <div class="detail-title-stack">
                  <h2>{{ segmentDisplayName(selectedSegment) }}</h2>
                </div>
                <div class="detail-tags detail-tags-top">
                  <span class="detail-tag detail-tag-progress" :class="segmentProgressClass(selectedSegment)">
                    {{ segmentProgressLabel(selectedSegment) }}
                  </span>
                  <span class="detail-tag detail-tag-index">第 {{ selectedSegmentIndex + 1 }} / {{ savedRoute.segments.length }}</span>
                </div>
              </div>
              <div class="detail-nav-actions">
                <button class="nav-action-btn" :disabled="selectedSegmentIndex <= 0" @click="goToPrevSegment">上一段</button>
                <button class="nav-action-btn" :disabled="!hasNextPendingSegment" @click="goToNextPendingSegment">下一个待处理</button>
                <button class="nav-action-btn nav-action-btn-primary" :disabled="selectedSegmentIndex >= savedRoute.segments.length - 1" @click="goToNextSegment">下一段</button>
              </div>
            </div>
          </div>

          <QuestionTreePanel
            hide-read-only-notice
            v-if="showQuestionTreePanel"
            :key="`${selectedSegment.id}-${questionTreeCurrentQuestion?.id || 'resolved'}-${questionTreeTrail.length}`"
            :visible="questionTreeVisible"
            :read-only="analysisReadOnly || guidanceGenerating"
            :read-only-reason="guidanceGenerating ? '问答与推荐正在生成，完成后即可回答。' : undefined"
            :empty-reason="questionTreeEmptyReason"
            :current-question="questionTreeCurrentQuestion"
            :source-hint="questionTreeSourceHint"
            :trail="questionTreeTrail"
            :result-summary="questionTreeResultSummary"
            :note-draft="questionTreeNoteDraft"
            :saved-trail="questionTreeSavedTrail"
            @choose-option="chooseQuestionTreeOption"
            @choose-options="chooseQuestionTreeOptions"
            @update-note="updateQuestionTreeNote"
            @reanswer-last="reanswerLastQuestionTree"
            @reset="resetQuestionTree"
            @edit-custom="openCustomEditor"
          />

            <SampleComparePanel
              :expanded="sampleCompareExpanded"
              :hit-documents="hitDocuments"
              :missing-documents="missingDocuments"
              @toggle="sampleCompareExpanded = !sampleCompareExpanded"
              @select-document="openDocumentPreview"
            />

            <EvidenceRowsPanel
              :expanded="evidenceRowsExpanded"
              :rows="selectedSegment.matched_detail_rows"
              @toggle="evidenceRowsExpanded = !evidenceRowsExpanded"
            />


        </section>
        <section v-else class="analysis-column analysis-column-right analysis-filter-empty">
          <div class="empty-mark">0</div>
          <div class="empty-title">没有匹配的工序</div>
          <div class="empty-text">切换审核状态查看，或显示全部工序。</div>
          <button type="button" class="btn btn-outline btn-sm" @click="resetSegmentFilters">清除筛选</button>
        </section>
      </div>

      <div v-if="documentPreviewVisible" class="doc-preview-overlay" @click.self="closeDocumentPreview">
        <div class="doc-preview-dialog">
          <div class="doc-preview-head">
            <div>
              <div class="doc-preview-title">{{ documentPreview?.original_name || '文档预览' }}</div>
              <div class="doc-preview-subtitle">
                {{ (documentPreview?.file_type || '').toLowerCase() === 'pdf' ? '这里直接预览 PDF 原文件。' : '这里展示提取后的文档内容，便于你快速浏览上下文。' }}
              </div>
            </div>
            <div class="doc-preview-actions">
              <button class="btn btn-outline btn-sm" :disabled="!documentPreview" @click="openDocumentOriginal">
                打开原文件
              </button>
              <button class="btn btn-primary btn-sm" @click="closeDocumentPreview">关闭</button>
            </div>
          </div>
          <div v-if="documentPreviewLoading" class="doc-preview-state">正在加载文档内容...</div>
          <div v-else-if="documentPreviewError" class="doc-preview-state doc-preview-state-error">{{ documentPreviewError }}</div>
          <div
            v-else-if="(documentPreview?.file_type || '').toLowerCase() === 'pdf'"
            class="doc-preview-pdf-pages"
          >
            <div v-if="!documentPreviewPdfPageUrls.length" class="doc-preview-state">
              当前 PDF 没有可预览的页面。
            </div>
            <img
              v-for="(pageUrl, idx) in documentPreviewPdfPageUrls"
              :key="pageUrl"
              class="doc-preview-pdf-page"
              :src="pageUrl"
              :alt="`${documentPreview?.original_name || 'PDF'} 第 ${idx + 1} 页`"
              loading="lazy"
            />
          </div>
          <pre v-else class="doc-preview-body">{{ documentPreview?.preview_text || '当前没有可预览的内容。' }}</pre>
        </div>
      </div>
    </template>

    <WorkflowNavFooter
      :summary="analysisNavSummary"
      :notices="analysisNotices"
      previous-label="← 返回路线归并"
      next-label="进入规则定稿 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId || !savedRoute || loading || resettingWorkflow || batchAcceptingAll || guidanceGenerating || (!analysisGuidance && !!guidanceError) || pendingSegmentCount > 0 || inProgressSegmentCount > 0"
      @previous="goBackToExtract"
      @next="goToFinalize"
    />

    <WorkflowResetDialog
      v-model="resetDialogVisible"
      :title="thirdStepResetCopy.title"
      :description="thirdStepResetCopy.description"
      :keep-items="thirdStepResetCopy.keepItems"
      :clear-items="thirdStepResetCopy.clearItems"
      :confirm-label="thirdStepResetCopy.confirmLabel"
      :busy-label="thirdStepResetCopy.busyLabel"
      :busy="resettingWorkflow"
      @confirm="confirmResetAllAnswers"
    />

    <el-dialog v-model="customEditorVisible" title="自行设置工序规则" width="900px" :close-on-click-modal="false" :show-close="false" destroy-on-close>
      <p v-if="customEditorError" role="alert">{{ customEditorError }}</p>
      <ProcessConfigurationEditor v-if="customCandidate && customCard && selectedSegment" v-model="customCandidate" :item="customCard" :display-name="segmentDisplayName(selectedSegment)" :fields="customFields" :processes="customProcesses" :disabled="analysisReadOnly" @save="confirmCustomRule" @cancel="cancelCustomRule" />
      <button v-else type="button" @click="cancelCustomRule">返回问题</button>
    </el-dialog>


  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AnalysisRouteList from '@/components/analysis/AnalysisRouteList.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'
import WorkflowResetDialog from '@/components/workflow/WorkflowResetDialog.vue'
import { buildProjectRouteQuery } from '@/composables/useCurrentProject'
import { useAnalysisWorkspace } from '@/composables/useAnalysisWorkspace'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { formatRoutePhaseLabel } from '@/composables/routeNameDisplay'
import { startRulePreprocessingForSavedRoute } from '@/composables/rulePreprocessingTrigger'
import { resetCopyForEdition } from '@/composables/workflowResetCopy'
import { templateMappingVisible } from '@/composables/productStatus'
import ProcessConfigurationEditor from '@/components/finalize/ProcessConfigurationEditor.vue'
import { buildFinalizeCards } from '@/composables/finalizeViewHelpers'
import { guidedProcessId } from '@/composables/analysisGuidanceFlow'
import { projectConditionFields } from '@/utils/projectConditionFields'
import { getConditionFieldRegistry, type CanonicalConditionField, type RuleConditionCandidate } from '@/api/rulePackages'

const thirdStepResetCopy = computed(() => resetCopyForEdition('analysis', templateMappingVisible.value))

const EvidenceRowsPanel = defineAsyncComponent(() => import('@/components/analysis/EvidenceRowsPanel.vue'))
const QuestionTreePanel = defineAsyncComponent(() => import('@/components/analysis/QuestionTreePanel.vue'))
const SampleComparePanel = defineAsyncComponent(() => import('@/components/analysis/SampleComparePanel.vue'))

const router = useRouter()

type SegmentFilter = 'all' | 'pending'

const segmentFilter = ref<SegmentFilter>('pending')
const resetDialogVisible = ref(false)
const customEditorVisible = ref(false)
const customCandidate = ref<RuleConditionCandidate | null>(null)
const customFields = ref<CanonicalConditionField[]>([])
const customEditorError = ref('')

const {
  loading,
  analysisReadOnly,
  analysisGuidance,
  guidanceError,
  guidanceErrorReason,
  guidanceGenerating,
  generationElapsedSeconds,
  recommendationSummary,
  getGuidanceForSegment,
  resettingWorkflow,
  error,
  projectId,
  savedRoute,
  selectedSegmentId,
  supersetOperations,
  sampleCompareExpanded,
  evidenceRowsExpanded,
  documentPreviewLoading,
  documentPreviewError,
  documentPreview,
  documentPreviewVisible,
  documentPreviewPdfPageUrls,
  selectedSegment,
  completedSegmentCount,
  inProgressSegmentCount,
  pendingSegmentCount,
  selectedSegmentIndex,
  hasNextPendingSegment,
  hitDocuments,
  missingDocuments,
  questionTreeVisible,
  showQuestionTreePanel,
  questionTreeEmptyReason,
  questionTreeCurrentQuestion,
  questionTreeSourceHint,
  questionTreeTrail,
  questionTreeResultSummary,
  questionTreeNoteDraft,
  questionTreeSavedTrail,
  loadSavedRoute,
  resetAllAnalysisAnswers,
  goBackToExtract,
  openDocumentPreview,
  closeDocumentPreview,
  openDocumentOriginal,
  segmentCoverageLabel,
  segmentDisplayName,
  segmentProgressClass,
  segmentProgressLabel,
  goToPrevSegment,
  goToNextPendingSegment,
  goToNextSegment,
  chooseQuestionTreeOption,
  chooseQuestionTreeOptions,
  reanswerLastQuestionTree,
  resetQuestionTree,
  updateQuestionTreeNote,
  batchAcceptingAll,
  batchAcceptProgress,
  acceptAllRecommendedForAllSegments,
} = useAnalysisWorkspace()

const recommendationRetryAvailable = computed(() => Object.values(analysisGuidance.value?.operation_guidance || {})
  .some(operation => !operation.recommendation && !!operation.recommendation_issues?.length))

const customCard = computed(() => selectedSegment.value ? buildFinalizeCards([selectedSegment.value], supersetOperations.value, {})[0] || null : null)
const customProcesses = computed(() => {
  const segments = savedRoute.value?.segments || []
  const index = segments.findIndex(s => s.id === selectedSegment.value?.id)
  return segments.slice(0, index + 1).map(s => ({ process_id: guidedProcessId(s), display_name: segmentDisplayName(s), main: false }))
})
async function openCustomEditor() {
  if (!selectedSegment.value || analysisReadOnly.value) return
  const targetId = selectedSegment.value.id, routeId = savedRoute.value?.route_id
  customEditorError.value = ''
  customCandidate.value = null
  customEditorVisible.value = true
  try {
    const registry = await getConditionFieldRegistry({ processId: guidedProcessId(selectedSegment.value), processName: selectedSegment.value.normalized_step_name })
    if (!customEditorVisible.value || selectedSegment.value?.id !== targetId || savedRoute.value?.route_id !== routeId || analysisReadOnly.value) return
    customFields.value = projectConditionFields(guidedProcessId(selectedSegment.value), selectedSegment.value.normalized_step_name, getGuidanceForSegment(selectedSegment.value) || undefined)
    if (!customFields.value.length) customFields.value = registry.fields
    customCandidate.value = { kind: 'process_configuration', configuration: { process_id: guidedProcessId(selectedSegment.value), occurrence: 'always', when: null, relations: [] }, preview: `${selectedSegment.value.normalized_step_name}固定安排。`, field_definitions: [] }
  } catch { customEditorError.value = '规则字段加载失败，请返回后重试。' }
}
function confirmCustomRule(candidate: RuleConditionCandidate) {
  if (analysisReadOnly.value) return
  chooseQuestionTreeOption({ value: JSON.stringify(candidate), label: candidate.preview || '已自行设置并确认规则' })
  customEditorVisible.value = false
  customCandidate.value = null
}
function cancelCustomRule() {
  customEditorVisible.value = false
  customCandidate.value = null
  reanswerLastQuestionTree()
}

const {
  isSegmentStepsExpanded,
  segmentAttachedSteps,
  segmentPrimarySteps,
  segmentStepCount,
  toggleSegmentSteps,
} = useRouteSegmentSteps(supersetOperations)

const filteredSegments = computed(() => {
  return (savedRoute.value?.segments || []).filter((segment) => {
    const progressClass = segmentProgressClass(segment)
    return segmentFilter.value === 'all'
      || (segmentFilter.value === 'pending' && progressClass !== 'is-completed')
  })
})

const segmentFilterOptions = computed(() => [
  { value: 'all' as const, label: '全部', count: savedRoute.value?.segments.length || 0 },
  { value: 'pending' as const, label: '待处理', count: pendingSegmentCount.value + inProgressSegmentCount.value },
])
const analysisNotices = computed<WorkflowNotice[]>(() => {
  const notices: WorkflowNotice[] = []
  const retry = () => loadSavedRoute(true, true)
  const retryDisabled = loading.value || guidanceGenerating.value || analysisReadOnly.value || resettingWorkflow.value
  if (error.value && savedRoute.value) notices.push({ id: 'analysis-error', level: 'error', summary: '规则分析操作未完成', detail: error.value, actions: [{ label: '关闭提示', run: () => { error.value = '' } }] })
  if (guidanceGenerating.value) notices.push({ id: 'generation', level: 'progress', summary: `正在生成问答与推荐 · ${generationElapsedSeconds.value}秒`, detail: '生成并校验完成后即可回答，可以先查看工序与样本依据。' })
  else if (guidanceError.value) notices.push({ id: 'generation-failed', level: 'error', summary: guidanceError.value, detail: guidanceErrorReason.value, actions: [{ label: '重新生成问答', run: retry, disabled: retryDisabled }] })
  else {
    if (recommendationRetryAvailable.value && !analysisReadOnly.value) notices.push({ id: 'recommendation-missing', level: 'warning', summary: '部分工序暂无有效推荐', detail: '可手动回答或重试。已开始回答的工序保持原问答版本。', actions: [{ label: '重试推荐', run: retry, disabled: retryDisabled }] })
    if (recommendationSummary.value) notices.push({ id: 'adoption', level: 'success', summary: recommendationSummary.value })
    else if (!recommendationRetryAvailable.value && analysisGuidance.value && !analysisReadOnly.value) notices.push({ id: 'ready', level: 'info', summary: '问答与推荐已就绪', detail: analysisNavSummary.value })
  }
  if (analysisReadOnly.value) notices.push({ id: 'readonly', level: 'info', summary: '已进入规则定稿，当前仅供查看', detail: '请到规则定稿页调整，或使用“重新回答全部”重新分析。' })
  return notices
})

const analysisNavSummary = computed(() => {
  if (!projectId.value) return '请先完成第二步路线归并并保存标准化母路线。'
  if (loading.value) return '正在装载规则分析工作区。'
  if (error.value && !savedRoute.value) return '当前没有可分析的已保存路线，请返回路线归并。'
  const total = savedRoute.value?.segments.length || 0
  return `规则分析进度：已确认 ${completedSegmentCount.value}/${total}，确认中 ${inProgressSegmentCount.value}，待确认 ${pendingSegmentCount.value}。`
})

watch(filteredSegments, (segments) => {
  if (!segments.length) return
  if (!segments.some(segment => String(segment.id) === selectedSegmentId.value)) {
    selectedSegmentId.value = String(segments[0]?.id || '')
  }
}, { immediate: true })

function resetSegmentFilters() {
  segmentFilter.value = 'all'
}

async function confirmResetAllAnswers() {
  await resetAllAnalysisAnswers(() => {
    resetDialogVisible.value = false
    segmentFilter.value = 'pending'
  })
}

function segmentPhaseLabel(segment: any) {
  return formatRoutePhaseLabel(segment?.phase)
}

function goToFinalize() {
  void startRulePreprocessingForSavedRoute({
    projectId: projectId.value,
    savedRoute: savedRoute.value,
    supersetOperations: supersetOperations.value,
    segmentDisplayName,
  }).catch((error) => {
    console.warn('进入第4步前启动规则预处理失败', error)
  })
  router.push({
    path: '/finalize',
    query: buildProjectRouteQuery(projectId.value),
  })
}
</script>

<style scoped>
.analysis-generation-status {
  padding: 12px 16px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-card);
  background: var(--pm-surface);
  color: var(--pm-text-muted);
}
.analysis-generation-steps { display: flex; align-items: center; flex-wrap: wrap; gap: 8px 20px; font-size: 13px; }
.analysis-generation-steps strong { color: var(--pm-primary); font-weight: 600; }
.analysis-generation-progress { display: block; width: 100%; height: 5px; margin: 10px 0 8px; accent-color: var(--pm-primary); }
.analysis-generation-status small { font-size: 12px; }
.analysis-guidance-notice details { font-size: 12px; overflow-wrap: anywhere; }
.analysis-guidance-notice summary { cursor: pointer; }
.analysis-readonly-notice {
  margin: 0 0 8px;
  padding: 8px 12px;
  color: var(--pm-text-secondary);
  background: var(--pm-primary-soft);
  border: 1px solid var(--pm-primary-border);
  border-radius: 8px;
  font-size: 13px;
}

.analysis-view {
  padding: 0;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  background: var(--pm-surface-subtle);
}

.analysis-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 12px;
  border: 1px solid var(--pm-border);
  border-radius: 8px;
  background: var(--pm-surface);
  box-shadow: 0 1.5px 5px rgba(15, 23, 42, 0.02);
  margin-bottom: 6px;
  flex-shrink: 0;
}

.analysis-hero-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.analysis-hero-sep {
  color: var(--pm-border-strong);
  font-size: 12px;
  flex-shrink: 0;
}

.analysis-hero-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--pm-text);
  white-space: nowrap;
  flex-shrink: 0;
}

.analysis-hero-desc {
  font-size: 13px;
  color: var(--pm-text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.analysis-actions {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-shrink: 0;
}

.btn-accept-all-global {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 5px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-surface);
  background: var(--pm-primary);
  border: none;
  border-radius: 7px;
  cursor: pointer;
  transition: all 0.2s ease;
  box-shadow: 0 1px 4px rgba(36, 95, 168, 0.3);
  white-space: nowrap;
}

.btn-accept-all-global:hover:not(:disabled) {
  background: var(--pm-primary);
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.4);
  transform: none;
}

.btn-accept-all-global:active:not(:disabled) {
  transform: translateY(0);
  box-shadow: 0 1px 2px rgba(36, 95, 168, 0.3);
}

.btn-accept-all-global:disabled {
  opacity: 0.5;
  cursor: not-allowed;
  transform: none;
}

.btn-accept-all-global-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.btn-accept-all-spinner {
  width: 13px;
  height: 13px;
  border: 2px solid rgba(255, 255, 255, 0.35);
  border-top-color: var(--pm-surface);
  border-radius: 50%;
  animation: btn-spin 0.75s linear infinite;
  flex-shrink: 0;
}

@keyframes btn-spin {
  to { transform: rotate(360deg); }
}

.btn-accept-all-global-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 16px;
  padding: 0 5px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.25);
  color: var(--pm-surface);
  font-size: 12px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
}

.analysis-hero-stats {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-right: 4px;
}

.analysis-hero-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid var(--pm-border);
  background: rgba(255, 255, 255, 0.86);
  font-size: 12px;
  color: var(--pm-text-muted);
  white-space: nowrap;
}

.analysis-hero-stat strong {
  font-size: 12px;
  font-weight: 700;
  color: var(--pm-text);
}

.analysis-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  flex: 1;
  min-height: 0;
  height: auto;
}

.analysis-inline-error {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  margin-bottom: 10px;
  background: var(--pm-danger-soft);
  border: 1px solid var(--pm-danger-border);
  border-left: 4px solid var(--pm-danger);
  border-radius: 8px;
  color: var(--pm-danger);
  font-size: 13px;
}

.btn-clear-error {
  background: transparent;
  border: none;
  color: var(--pm-danger);
  font-size: 16px;
  font-weight: bold;
  cursor: pointer;
  padding: 0 4px;
}

.analysis-filter-options {
  display: inline-flex;
  align-items: center;
  flex: 0 0 auto;
  gap: 2px;
  padding: 2px;
  border-radius: 7px;
  background: var(--pm-surface-subtle);
}

.analysis-filter-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  min-height: 28px;
  padding: 3px 6px;
  border: 1px solid transparent;
  border-radius: 5px;
  background: transparent;
  color: var(--pm-text-secondary);
  font: inherit;
  font-size: 12px;
  line-height: 1.55;
  white-space: nowrap;
  cursor: pointer;
  transition: background-color .15s ease, color .15s ease, border-color .15s ease;
}

.analysis-filter-btn span {
  min-width: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: var(--pm-disabled-bg);
  color: var(--pm-text-secondary);
  font-size: 12px;
  line-height: 1.4;
}

.analysis-filter-btn.active {
  border-color: var(--pm-primary-border);
  background: var(--pm-surface);
  color: var(--pm-primary);
  font-weight: 650;
  box-shadow: none;
}

.analysis-filter-btn.active span {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.analysis-filter-btn:focus-visible {
  outline: 2px solid var(--pm-primary);
  outline-offset: 2px;
}

.analysis-filter-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
}

.analysis-column {
  min-width: 0;
  overflow-y: auto;
}

.analysis-column::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.analysis-column::-webkit-scrollbar-track {
  background: var(--pm-surface-subtle);
  border-radius: 6px;
}

.analysis-column::-webkit-scrollbar-thumb {
  background: var(--pm-border-strong);
  border-radius: 6px;
}

.analysis-column::-webkit-scrollbar-thumb:hover {
  background: var(--pm-text-muted);
}

.analysis-column-left,
.analysis-column-right {
  border-radius: 14px;
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.analysis-column-left {
  padding: 14px;
}

.analysis-column-right {
  padding: 20px;
}

.tree-recommend-text {
  font-size: 12px;
  line-height: 1.4;
  font-weight: 500;
  color: var(--pm-text-secondary);
}

.tree-recommend-reason {
  font-size: 12px;
  line-height: 1.4;
  color: var(--pm-text-muted);
  margin-top: 2px;
}

.detail-card-evidence-overview {
  background: var(--pm-surface-subtle);
  border: 1px solid var(--pm-border);
}

.evidence-overview-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.evidence-overview-text {
  margin-top: 4px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--pm-text-muted);
}

.detail-hero {
  padding-bottom: 8px;
  margin-bottom: 8px;
  border-bottom: 1px solid var(--pm-border);
}

.detail-hero-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-hero h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  line-height: 1.25;
  color: var(--pm-text);
  letter-spacing: -0.01em;
}

.detail-hero-title-group {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
}

.detail-title-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-hero-subtitle {
  font-size: 13px;
  color: var(--pm-text-muted);
  line-height: 1.5;
}

.detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-tag {
  border-radius: 6px;
  padding: 3px 7px;
  font-size: 12px;
  font-weight: 600;
  background: rgba(15, 23, 42, 0.06);
  color: var(--pm-text-secondary);
}

.detail-tag-progress.is-completed {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.detail-tag-progress.is-started {
  background: rgba(36, 95, 168, 0.12);
  color: var(--pm-primary-hover);
}

.detail-tag-progress.is-pending {
  background: var(--pm-border);
  color: var(--pm-text-muted);
}

.detail-tag-index {
  background: rgba(15, 23, 42, 0.06);
  color: var(--pm-text-secondary);
}

.detail-nav-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.nav-action-btn {
  border: 1px solid var(--pm-border-strong);
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.nav-action-btn:hover:not(:disabled) {
  border-color: var(--pm-primary);
  color: var(--pm-primary-hover);
}

.nav-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-action-btn-primary {
  background: var(--pm-primary);
  border-color: var(--pm-primary);
  color: var(--pm-surface);
}

.nav-action-btn-primary:hover:not(:disabled) {
  background: var(--pm-primary);
  color: var(--pm-surface);
}

.detail-card {
  padding: 12px;
  border-radius: 12px;
  background: var(--pm-surface-subtle);
  border: 1px solid var(--pm-border);
}

.detail-card-wide {
  margin-top: 12px;
}

.detail-collapse-toggle {
  width: 100%;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 0;
  margin: 0;
  border: none;
  background: transparent;
  cursor: pointer;
  text-align: left;
  outline: none;
}

.detail-collapse-toggle:focus-visible {
  border-radius: 4px;
  box-shadow: 0 0 0 2px rgba(36, 95, 168, 0.4);
}

.detail-collapse-toggle + * {
  margin-top: 10px;
}

.detail-collapse-toggle .detail-card-title {
  margin-bottom: 0;
}

.detail-collapse-indicator {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--pm-primary);
  background: rgba(36, 95, 168, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
}

.detail-card-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--pm-text);
  margin-bottom: 12px;
  text-transform: none;
  letter-spacing: normal;
  display: flex;
  align-items: center;
  gap: 8px;
}

.detail-card-title::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 14px;
  background: var(--accent, var(--pm-primary));
  border-radius: 2px;
  opacity: 0.8;
}

.detail-helper-text {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: var(--pm-text-muted);
  font-weight: 400;
}

.detail-card-focus {
  background: var(--pm-primary-soft);
  border-color: #dbe4f4;
}

.focus-kicker {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--pm-primary);
}

.focus-summary {
  margin-top: 8px;
  font-size: 16px;
  line-height: 1.7;
  color: var(--pm-text);
  font-weight: 700;
}

.focus-chip-row {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 12px;
}

.factor-progress-row {
  margin-top: 0;
  margin-bottom: 8px;
}

.focus-chip {
  display: inline-flex;
  align-items: center;
  padding: 4px 10px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}

.focus-chip-confirmed {
  background: rgba(34, 197, 94, 0.14);
  color: var(--pm-success);
}

.focus-chip-excluded {
  background: rgba(239, 68, 68, 0.12);
  color: var(--pm-danger);
}

.focus-chip-pending {
  background: #eef2f7;
  color: var(--pm-text-secondary);
}

/* 紧凑版因素分析与结论样式 */
.factor-progress-summary { margin-bottom: 12px; }
.factor-progress-track-mini { height: 4px; background: var(--pm-border); border-radius: 2px; overflow: hidden; display: flex; margin-bottom: 6px; }
.factor-progress-fill-mini { height: 100%; transition: width 0.3s ease; }
.factor-progress-fill-mini.is-confirmed { background: var(--pm-success); }
.factor-progress-fill-mini.is-excluded { background: var(--pm-danger); }
.factor-progress-badges { display: flex; gap: 12px; }
.badge-mini { font-size: 12px; color: var(--pm-text-muted); }
.badge-mini strong { color: var(--pm-text); margin-left: 2px; }

.factor-grid-compact { display: flex; flex-direction: column; gap: 4px; }
.factor-card-mini { padding: 8px 12px; border-radius: 8px; background: var(--pm-surface-subtle); border: 1px solid transparent; transition: all 0.2s ease; }
.factor-card-mini:hover { background: var(--pm-surface-subtle); border-color: var(--pm-border); }
.factor-card-mini.is-confirmed { border-left: 3px solid var(--pm-success); background: rgba(34, 197, 94, 0.03); }
.factor-card-mini.is-excluded { border-left: 3px solid var(--pm-danger); background: rgba(239, 68, 68, 0.02); opacity: 0.8; }

.factor-info-mini { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.factor-main-mini { flex: 1; min-width: 0; }
.factor-name-mini { font-size: 13px; font-weight: 700; color: var(--pm-text); margin-bottom: 2px; }
.factor-meta-mini { font-size: 12px; color: var(--pm-text-muted); display: flex; gap: 8px; align-items: center; }
.tag-mini { background: rgba(15, 23, 42, 0.04); padding: 1px 6px; border-radius: 4px; }

.factor-ops-mini { display: flex; align-items: center; gap: 6px; }
.btn-mini { padding: 3px 10px; font-size: 12px; font-weight: 700; border-radius: 6px; border: 1px solid var(--pm-border); background: var(--pm-surface); color: var(--pm-text-secondary); cursor: pointer; transition: all 0.15s ease; }
.btn-mini:hover { border-color: var(--pm-primary); color: var(--pm-primary-hover); }
.btn-mini.active { background: var(--pm-primary); border-color: var(--pm-primary); color: var(--pm-surface); }
.btn-confirm.active { background: var(--pm-success); border-color: var(--pm-success); }
.btn-exclude.active { background: var(--pm-danger); border-color: var(--pm-danger); }
.btn-mini-text { font-size: 12px; color: var(--pm-text-muted); background: none; border: none; cursor: pointer; padding: 2px 4px; }
.btn-mini-text:hover { color: var(--pm-text-muted); text-decoration: underline; }

.detail-card-focus-compact { background: var(--pm-surface); border: 1px solid var(--pm-primary-soft); box-shadow: 0 4px 12px rgba(36, 95, 168, 0.04); }
.focus-header-row { display: flex; align-items: center; justify-content: space-between; padding-bottom: 8px; border-bottom: 1px dashed var(--pm-surface-subtle); margin-bottom: 10px; }
.focus-kicker-mini { font-size: 12px; font-weight: 700; color: var(--pm-primary); text-transform: uppercase; letter-spacing: 0.05em; }
.focus-status-badge { font-size: 12px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }

.focus-content-compact { display: flex; flex-direction: column; gap: 8px; }
.focus-summary-text { font-size: 14px; font-weight: 700; color: var(--pm-text); line-height: 1.6; }
.focus-next-tip { font-size: 12px; color: var(--pm-text-muted); display: flex; align-items: center; gap: 6px; background: var(--pm-surface-subtle); padding: 6px 10px; border-radius: 6px; }
.tip-icon { font-size: 14px; }

.focus-next-step {
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: var(--pm-text-muted);
}

/* 极致精简版因素分析样式 */
.section-compact-slim { padding: 12px 14px; }
.factor-mini-status { display: flex; align-items: center; gap: 10px; margin-left: auto; font-size: 12px; font-weight: 700; color: var(--pm-text-muted); }
.m-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 2px; vertical-align: middle; }
.m-dot.c { background: var(--pm-success); }
.m-dot.e { background: var(--pm-danger); }
.m-dot.p { background: var(--pm-border); }

.factor-list-slim { display: flex; flex-direction: column; gap: 4px; }
.factor-row-slim { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: 8px; background: var(--pm-surface-subtle); border: 1px solid transparent; transition: all 0.15s ease; gap: 12px; }
.factor-row-slim:hover { background: var(--pm-surface-subtle); border-color: var(--pm-border); }
.factor-row-slim.is-c { border-left: 3px solid var(--pm-success); background: rgba(34, 197, 94, 0.03); }
.factor-row-slim.is-e { border-left: 3px solid var(--pm-danger); background: rgba(239, 68, 68, 0.02); opacity: 0.7; }

.f-info-slim { flex: 1; min-width: 0; }
.f-name-slim { font-size: 13px; font-weight: 600; color: var(--pm-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.f-tag-mini { font-size: 12px; background: rgba(15, 23, 42, 0.05); padding: 1px 6px; border-radius: 4px; color: var(--pm-text-muted); margin-left: 8px; font-weight: 500; }

.f-ops-slim { display: flex; align-items: center; gap: 6px; }
.btn-xs-slim { padding: 2px 10px; font-size: 12px; font-weight: 700; border-radius: 6px; border: 1.5px solid #eef2f7; background: var(--pm-surface); color: var(--pm-text-secondary); cursor: pointer; transition: all 0.1s ease; }
.btn-xs-slim:hover { border-color: var(--pm-border-strong); background: var(--pm-surface-subtle); }
.btn-xs-slim.active { border-color: transparent; color: var(--pm-surface); }
.btn-xs-slim.confirm.active { background: var(--pm-success); }
.btn-xs-slim.exclude.active { background: var(--pm-danger); }
.action-btn-text { font-size: 12px; color: var(--pm-text-muted); background: none; border: none; cursor: pointer; padding: 2px 4px; }

.f-ev-slim { position: relative; }
.f-ev-slim summary { list-style: none; font-size: 12px; font-weight: 700; color: var(--pm-primary); cursor: pointer; opacity: 0.8; padding: 2px 6px; background: rgba(36, 95, 168, 0.05); border-radius: 4px; }
.f-ev-slim summary:hover { opacity: 1; background: rgba(36, 95, 168, 0.1); }
.f-ev-slim[open] summary { margin-bottom: 8px; }

.detail-helper-text-tight {
  margin-top: 0;
}

.detail-card-count {
  font-size: 12px;
  font-weight: 700;
  color: var(--pm-text-muted);
  margin-left: 4px;
}

.excerpt-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 0;
}

.excerpt-item {
  padding: 6px 0 6px 12px;
  border-left: 2px solid var(--pm-border);
  color: var(--pm-text-secondary);
  font-size: 13px;
  line-height: 1.6;
}

.excerpt-item + .excerpt-item {
  margin-top: 2px;
}

.evidence-table {
  display: flex;
  flex-direction: column;
  gap: 0;
}

.evidence-row {
  display: grid;
  grid-template-columns: 200px 80px minmax(0, 1fr);
  gap: 8px;
  padding: 6px 8px;
  color: var(--pm-text-secondary);
  font-size: 13px;
  border-bottom: 1px solid var(--pm-surface-subtle);
}

.evidence-row:last-child {
  border-bottom: none;
}

.evidence-row-head {
  background: transparent;
  padding: 0 8px 4px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 700;
  border-bottom: 1px solid var(--pm-border);
}

.evidence-source,
.evidence-operation,
.evidence-content {
  min-width: 0;
  word-break: break-word;
  overflow: hidden;
  text-overflow: ellipsis;
}

.evidence-source {
  font-size: 12px;
  color: var(--pm-text-secondary);
}

.evidence-source small {
  color: var(--pm-text-muted);
  font-size: 12px;
}

.evidence-operation {
  font-weight: 600;
}

.detail-note,
.detail-empty,
.empty-text {
  color: var(--pm-text-muted);
  line-height: 1.75;
}

.detail-empty-danger {
  color: var(--pm-danger);
}

.factor-stack {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

.factor-row {
  padding: 10px 12px;
  border-radius: 8px;
  background: rgba(15, 23, 42, 0.03);
}

.factor-top,
.factor-tags {
  display: flex;
  justify-content: space-between;
  gap: 6px;
  align-items: center;
}

.factor-tags {
  flex-wrap: wrap;
  justify-content: flex-end;
}

.factor-name {
  font-size: 13px;
  font-weight: 700;
  color: var(--pm-text);
}

.factor-tag {
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 12px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-weight: 600;
}

.factor-tag-strong {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.factor-tag-confirmed {
  background: rgba(34, 197, 94, 0.12);
  color: var(--pm-success);
}

.factor-tag-excluded {
  background: rgba(239, 68, 68, 0.1);
  color: var(--pm-danger);
}

.factor-source {
  margin-top: 4px;
  font-size: 12px;
  color: var(--pm-text-muted);
}

.analysis-empty {
  margin-top: 24px;
  padding: 36px 28px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.86);
  border: 1px solid rgba(148, 163, 184, 0.16);
  text-align: center;
  box-shadow: 0 24px 50px -34px rgba(15, 23, 42, 0.42);
}

.analysis-empty-error {
  border-color: rgba(239, 68, 68, 0.18);
}

.analysis-empty-warning {
  border-color: rgba(234, 88, 12, 0.2);
  background: var(--pm-warning-soft);
}

.empty-mark {
  font-size: 36px;
  font-weight: 700;
  color: var(--pm-primary);
}

.empty-mark--warning {
  color: #ea580c;
}

.empty-title {
  margin-top: 12px;
  font-size: 22px;
  font-weight: 700;
  color: var(--pm-text);
}

.empty-text {
  max-width: 560px;
  margin: 10px auto 0;
}

.doc-preview-overlay {
  position: fixed;
  inset: 0;
  z-index: 50;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.45);

}

.doc-preview-dialog {
  width: min(1160px, 100%);
  height: 88vh;
  max-height: 88vh;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  border-radius: 16px;
  border: 1px solid rgba(255, 255, 255, 0.15);
  background: var(--pm-surface);
  box-shadow: 0 25px 80px -12px rgba(0, 0, 0, 0.4);
}

.doc-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid var(--pm-border);
  background: var(--pm-surface);
  flex-shrink: 0;
}

.doc-preview-title {
  font-size: 17px;
  font-weight: 700;
  color: var(--pm-text);
  line-height: 1.4;
}

.doc-preview-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: var(--pm-text-muted);
}

.doc-preview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-preview-state {
  padding: 32px 24px;
  font-size: 14px;
  color: var(--pm-text-muted);
  flex: 1;
}

.doc-preview-state-error {
  color: var(--pm-danger);
}

.doc-preview-body {
  margin: 0;
  padding: 20px 24px 24px;
  flex: 1;
  overflow: auto;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
  line-height: 1.75;
  color: var(--pm-text);
  background: #fcfdff;
}

.doc-preview-pdf-pages {
  flex: 1;
  overflow: auto;
  padding: 18px 20px 28px;
  background: #323639;
}

.doc-preview-pdf-page {
  display: block;
  width: min(100%, 920px);
  height: auto;
  margin: 0 auto 18px;
  background: var(--pm-surface);
  box-shadow: 0 12px 32px rgba(0, 0, 0, 0.32);
}

.doc-preview-pdf-page:last-child {
  margin-bottom: 0;
}

@media (max-width: 1180px) {
  .analysis-summary-grid,
  .detail-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .analysis-layout {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 760px) {
  .analysis-view {
    height: auto;
    overflow: visible;
    padding: 20px 16px 28px;
  }

  .analysis-hero {
    flex-direction: column;
  }

  .analysis-actions,
  .analysis-summary-grid,
  .detail-grid {
    width: 100%;
  }

  .analysis-summary-grid,
  .detail-grid {
    grid-template-columns: 1fr;
  }

  .analysis-layout {
    display: block;
    height: auto;
  }

  .analysis-column-left {
    max-height: 440px;
    margin-bottom: 12px;
    overflow-y: auto;
  }

  .analysis-column-right {
    overflow: visible;
  }

  .doc-preview-overlay {
    padding: 12px;
  }

  .doc-preview-head {
    flex-direction: column;
  }

  .doc-preview-actions {
    width: 100%;
    justify-content: flex-end;
  }

  .detail-nav-actions {
    justify-content: flex-start;
  }
}

.btn-sm {
  padding: 3px 12px;
  font-size: 13px;
  border-radius: 7px;
  font-weight: 600;
}

/* PM016: retain the workspace scroll/diagram geometry and theme named UI only. */
.analysis-view { background: transparent; }
.analysis-hero { flex-wrap: wrap; gap: 8px 12px; padding: 10px 12px; margin-bottom: 12px; box-shadow: var(--pm-shadow-card); border-color: var(--pm-border); }
.analysis-hero-info, .analysis-actions { flex-wrap: wrap; min-width: 0; }
.analysis-hero-info { flex: 1 1 240px; }
.analysis-hero-title { font-size: 20px; font-weight: 600; line-height: 28px; }
.analysis-actions { gap: 6px; }
.analysis-hero-stats { flex-wrap: wrap; }
.analysis-hero-stat { border-radius: 4px; line-height: 20px; }
.analysis-layout { gap: 12px; }
.btn-accept-all-global { min-height: 32px; padding: 5px 12px; border-radius: var(--pm-radius-control); background: var(--pm-primary); box-shadow: none; font-size: 13px; line-height: 20px; font-weight: 500; }
.btn-accept-all-global:hover:not(:disabled), .btn-accept-all-global:active:not(:disabled) { background: var(--pm-primary-hover); box-shadow: none; transform: none; }
.analysis-view :deep(.tree-question-prompt::before), .analysis-view :deep(.tree-recommend-icon) { background: var(--pm-primary-soft); color: var(--pm-primary); }
.analysis-view :deep(.tree-option-btn.active .tree-option-radio) { background: var(--pm-primary); border-color: var(--pm-primary); }
.analysis-view :deep(.tree-saved-list li::before) { color: var(--pm-primary); }
.analysis-view :deep(.tree-option-btn.active) { background: var(--pm-primary-soft); border-color: var(--pm-primary); }
.analysis-view :deep(.tree-option-btn.active .tree-option-label), .analysis-view :deep(.tree-count-pill), .analysis-view :deep(.tree-table-add-btn) { color: var(--pm-primary); }
.analysis-view :deep(.tree-option-btn:focus-visible) { outline: 2px solid var(--pm-primary); outline-offset: 2px; border-color: var(--pm-primary); }
.analysis-view :deep(.tree-recommend-row) { background: var(--pm-surface-subtle); border-color: var(--pm-border); border-radius: var(--pm-radius-control); }
.analysis-view :deep(.tree-recommend-text), .analysis-view :deep(.tree-recommend-reason), .analysis-view :deep(.tree-prompt-source) { font-size: 12px; line-height: 18px; }
.analysis-view :deep(.tree-recommend-reason) { color: var(--pm-text-muted); }
.analysis-view :deep(.tree-table-checkbox) { accent-color: var(--pm-primary); }
.analysis-view :deep(.tree-table-input:focus), .analysis-view :deep(.tree-table-select:focus), .analysis-view :deep(.tree-note-input:focus) { border-color: var(--pm-primary); box-shadow: var(--pm-focus-ring); }
.analysis-view :deep(.tree-action-btn-accent) { color: var(--pm-primary); background: var(--pm-primary-soft); border-color: var(--pm-primary-border); }
.analysis-view :deep(.tree-action-btn-primary) { background: var(--pm-primary); border-color: var(--pm-primary); box-shadow: none; }
.analysis-view :deep(.tree-action-btn-primary:hover:not(:disabled)) { background: var(--pm-primary-hover); }

/* PM-066: match the saved-route navigator to Step 2's compact summaries.
   Keep metadata and the step toggle on one row; expansion spans the full card. */
.analysis-view :deep(.analysis-column-left) {
  padding: 0;
  min-width: 0;
  border-radius: var(--pm-radius-card);
}
.analysis-view :deep(.panel-head) {
  gap: 6px;
  flex-wrap: wrap;
  position: sticky;
  top: 0;
  z-index: 2;
  flex-shrink: 0;
  min-height: 34px;
  margin: 0;
  padding: 6px 12px;
  border-bottom: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
}
.analysis-view :deep(.panel-title) { font-size: 13px; line-height: 20px; }
.analysis-view :deep(.route-list) { padding: 8px 12px 12px; }
.analysis-view :deep(.route-item-wrap) { min-width: 0; flex-shrink: 0; gap: 8px; }
.analysis-view :deep(.route-track) { padding-top: 12px; }
.analysis-view :deep(.route-item) {
  min-width: 0;
  display: grid;
  grid-template-columns: minmax(0, 1fr) auto;
  gap: 2px 6px;
  padding: 5px 8px;
  margin-bottom: 2px;
}
.analysis-view :deep(.route-header-row) { grid-column: 1 / -1; min-height: 24px; gap: 6px; }
.analysis-view :deep(.route-title-group) { flex: 1; gap: 6px; }
.analysis-view :deep(.route-name) { min-width: 0; font-size: 13px; line-height: 18px; overflow-wrap: anywhere; }
.analysis-view :deep(.route-main), .analysis-view :deep(.route-steps) { display: contents; }
.analysis-view :deep(.route-meta-row) {
  grid-column: 1;
  margin-top: 0;
  justify-content: flex-start;
  gap: 0 6px;
  font-size: 11px;
  line-height: 18px;
}
.analysis-view :deep(.route-meta-details) { margin-left: 0; font-size: 11px; }
.analysis-view :deep(.route-steps-btn) { grid-column: 2; grid-row: 2; min-height: 24px; gap: 4px; white-space: nowrap; }
.analysis-view :deep(.route-step-chips) { grid-column: 1 / -1; margin-top: 2px; padding-top: 4px; border-top: 1px solid var(--pm-border); }
.analysis-view :deep(.route-step-chip) { max-width: 100%; overflow-wrap: anywhere; }
.analysis-view :deep(.route-state-badge) { font-size: 11px; line-height: 18px; padding: 0 5px; }
.analysis-view :deep(.route-item:focus-visible), .analysis-view :deep(.route-steps-btn:focus-visible) { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.doc-preview-head { flex-wrap: wrap; }
@media (min-width: 901px) and (max-width: 1180px) { .analysis-layout { grid-template-columns: 260px minmax(0, 1fr); } }
@media (max-width: 900px) {
  .analysis-view { height: auto; min-height: 100%; overflow: visible; padding: 0; }
  .analysis-layout { grid-template-columns: minmax(0, 1fr); }
  .analysis-column { max-height: none; overflow: visible; }
}
@media (prefers-reduced-motion: reduce) { .analysis-view button { transition: none; } }
</style>
