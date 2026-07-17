<template>
  <div class="analysis-view">
    <div class="analysis-hero">
      <div class="analysis-hero-info">
        <div class="analysis-hero-title">规则分析</div>
        <span class="analysis-hero-sep">·</span>
        <div class="analysis-hero-desc">已保存路线版本一览，左侧选工序、右侧看证据。</div>
      </div>
      <div class="analysis-actions">
        <button class="btn btn-outline btn-sm" @click="loadSavedRoute(true)" :disabled="loading || !projectId">
          刷新路线
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

    <div v-else-if="error" class="analysis-empty analysis-empty-error">
      <div class="empty-mark">!</div>
      <div class="empty-title">暂时还没有可分析的已保存路线</div>
      <div class="empty-text">{{ error }}</div>
      <button class="btn btn-primary" @click="goBackToExtract">返回并保存路线</button>
    </div>

    <template v-else-if="savedRoute">
      <div class="analysis-filter-bar">
        <label class="analysis-search">
          <span class="analysis-search-icon" aria-hidden="true">⌕</span>
          <input
            v-model="segmentSearch"
            type="search"
            placeholder="搜索工序名称"
            aria-label="搜索工序名称"
          />
        </label>
        <div class="analysis-filter-options" aria-label="工序审核状态筛选">
          <button
            v-for="option in segmentFilterOptions"
            :key="option.value"
            type="button"
            class="analysis-filter-btn"
            :class="{ active: segmentFilter === option.value }"
            @click="segmentFilter = option.value"
          >
            {{ option.label }}
            <span>{{ option.count }}</span>
          </button>
        </div>
        <div class="analysis-filter-result">
          显示 {{ filteredSegments.length }} / {{ savedRoute.segments.length }} 道工序
        </div>
      </div>

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
        />

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
                  <span v-if="selectedSegment.step_family" class="detail-tag">{{ selectedSegment.step_family }}</span>
                  <span v-if="segmentPhaseLabel(selectedSegment)" class="detail-tag">{{ segmentPhaseLabel(selectedSegment) }}</span>
                </div>
              </div>
              <div class="detail-nav-actions">
                <button class="nav-action-btn" :disabled="selectedSegmentIndex <= 0" @click="goToPrevSegment">上一段</button>
                <button class="nav-action-btn" :disabled="!hasNextPendingSegment" @click="goToNextPendingSegment">下一个待处理</button>
                <button class="nav-action-btn nav-action-btn-primary" :disabled="selectedSegmentIndex >= savedRoute.segments.length - 1" @click="goToNextSegment">下一段</button>
              </div>
            </div>
            <div class="detail-hero-row detail-hero-row-actions">
              <div class="detail-stats">
                <span>文档 <strong>{{ selectedSegment.doc_coverage.hit_docs }}/{{ selectedSegment.doc_coverage.total_docs }}</strong></span>
                <span>明细 <strong>{{ selectedSegment.detail_coverage.matched_rows }}</strong></span>
                <span>覆盖 <strong>{{ formatRatio(selectedSegment.doc_coverage.ratio) }}</strong></span>
                <span v-if="selectedSegment.source_nodes.length">来源 <strong>{{ selectedSegment.source_nodes.join(', ') }}</strong></span>
              </div>
            </div>
          </div>

          <QuestionTreePanel
            v-if="showQuestionTreePanel"
            :key="`${selectedSegment.id}-${questionTreeCurrentQuestion?.id || 'resolved'}-${questionTreeTrail.length}`"
            :visible="questionTreeVisible"
            :empty-reason="questionTreeEmptyReason"
            :current-question="questionTreeCurrentQuestion"
            :source-hint="questionTreeSourceHint"
            :trail="questionTreeTrail"
            :result-summary="questionTreeResultSummary"
            :note-draft="questionTreeNoteDraft"
            :saved-summary-lines="questionTreeSavedSummaryLines"
            :saved-trail="questionTreeSavedTrail"
            @choose-option="chooseQuestionTreeOption"
            @choose-options="chooseQuestionTreeOptions"
            @update-note="updateQuestionTreeNote"
            @reanswer-last="reanswerLastQuestionTree"
            @reset="resetQuestionTree"
          />

            <SampleComparePanel
              :expanded="sampleCompareExpanded"
              :hit-documents="hitDocuments"
              :missing-documents="missingDocuments"
              :hit-highlights="hitDocOperationHighlights"
              :missing-highlights="missingDocOperationHighlights"
              :variant-names="selectedSegmentVariantNames"
              @toggle="sampleCompareExpanded = !sampleCompareExpanded"
              @select-document="openDocumentPreview"
            />

            <EvidenceExcerptPanel
              :expanded="evidenceExcerptExpanded"
              :excerpts="selectedSegment.evidence_excerpt"
              @toggle="evidenceExcerptExpanded = !evidenceExcerptExpanded"
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
          <div class="empty-text">调整搜索词或审核状态后再试。</div>
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
      previous-label="← 返回路线归并"
      next-label="进入规则定稿 →"
      :previous-disabled="!projectId"
      :next-disabled="!projectId"
      @previous="goBackToExtract"
      @next="goToFinalize"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, defineAsyncComponent, ref, watch } from 'vue'
import { useRouter } from 'vue-router'
import AnalysisRouteList from '@/components/analysis/AnalysisRouteList.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import { buildProjectRouteQuery } from '@/composables/useCurrentProject'
import { useAnalysisWorkspace } from '@/composables/useAnalysisWorkspace'
import { useRouteSegmentSteps } from '@/composables/useRouteSegmentSteps'
import { formatRoutePhaseLabel } from '@/composables/routeNameDisplay'

const EvidenceExcerptPanel = defineAsyncComponent(() => import('@/components/analysis/EvidenceExcerptPanel.vue'))
const EvidenceRowsPanel = defineAsyncComponent(() => import('@/components/analysis/EvidenceRowsPanel.vue'))
const QuestionTreePanel = defineAsyncComponent(() => import('@/components/analysis/QuestionTreePanel.vue'))
const SampleComparePanel = defineAsyncComponent(() => import('@/components/analysis/SampleComparePanel.vue'))

const router = useRouter()

type SegmentFilter = 'all' | 'pending' | 'started' | 'completed'

const segmentSearch = ref('')
const segmentFilter = ref<SegmentFilter>('pending')


const {
  loading,
  error,
  projectId,
  savedRoute,
  selectedSegmentId,
  supersetOperations,
  sampleCompareExpanded,
  evidenceExcerptExpanded,
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
  selectedSegmentVariantNames,
  hitDocOperationHighlights,
  missingDocOperationHighlights,
  questionTreeVisible,
  showQuestionTreePanel,
  questionTreeEmptyReason,
  questionTreeCurrentQuestion,
  questionTreeSourceHint,
  questionTreeTrail,
  questionTreeResultSummary,
  questionTreeNoteDraft,
  questionTreeSavedSummaryLines,
  questionTreeSavedTrail,
  loadSavedRoute,
  goBackToExtract,
  openDocumentPreview,
  closeDocumentPreview,
  openDocumentOriginal,
  formatRatio,
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
} = useAnalysisWorkspace()

const {
  isSegmentStepsExpanded,
  segmentAttachedSteps,
  segmentPrimarySteps,
  segmentStepCount,
  toggleSegmentSteps,
} = useRouteSegmentSteps(supersetOperations)

const filteredSegments = computed(() => {
  const query = segmentSearch.value.trim().toLocaleLowerCase()
  return (savedRoute.value?.segments || []).filter((segment) => {
    const progressClass = segmentProgressClass(segment)
    const statusMatches = segmentFilter.value === 'all'
      || (segmentFilter.value === 'completed' && progressClass === 'is-completed')
      || (segmentFilter.value === 'started' && progressClass === 'is-started')
      || (segmentFilter.value === 'pending' && progressClass === 'is-pending')
    if (!statusMatches) return false
    if (!query) return true
    return [
      segmentDisplayName(segment),
      ...(segment.source_operation_names || []),
      ...(segment.source_nodes || []),
    ].some(value => String(value || '').toLocaleLowerCase().includes(query))
  })
})

const segmentFilterOptions = computed(() => [
  { value: 'pending' as const, label: '待确认', count: pendingSegmentCount.value },
  { value: 'started' as const, label: '确认中', count: inProgressSegmentCount.value },
  { value: 'completed' as const, label: '已确认', count: completedSegmentCount.value },
  { value: 'all' as const, label: '全部', count: savedRoute.value?.segments.length || 0 },
])
const analysisNavSummary = computed(() => {
  if (!projectId.value) return '请先完成第二步路线归并并保存标准化母路线。'
  if (loading.value) return '正在装载规则分析工作区。'
  if (error.value) return '当前没有可分析的已保存路线，请返回路线归并。'
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
  segmentSearch.value = ''
  segmentFilter.value = 'all'
}

function segmentPhaseLabel(segment: any) {
  return formatRoutePhaseLabel(segment?.phase)
}



function goToFinalize() {
  router.push({
    path: '/finalize',
    query: buildProjectRouteQuery(projectId.value),
  })
}
</script>

<style scoped>
.analysis-view {
  padding: 0;
  display: flex;
  flex-direction: column;
  /* 与第4步一致：填满 main-area（topbar 48 + pad-top 14 + pad-bottom 92） */
  height: calc(100vh - 118px);
  min-height: 0;
  overflow: hidden;
  background: #f8fafc;
}

.analysis-hero {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
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
  color: #cbd5e1;
  font-size: 12px;
  flex-shrink: 0;
}

.analysis-hero-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  flex-shrink: 0;
}

.analysis-hero-desc {
  font-size: 13px;
  color: #94a3b8;
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
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.86);
  font-size: 10.5px;
  color: #64748b;
  white-space: nowrap;
}

.analysis-hero-stat strong {
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
}

.analysis-layout {
  display: grid;
  grid-template-columns: 300px minmax(0, 1fr);
  gap: 14px;
  flex: 1;
  min-height: 0;
  height: auto;
}

.analysis-filter-bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 8px 0 10px;
  padding: 5px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 10px;
  background: #ffffff;
  flex-shrink: 0;
}

.analysis-search {
  display: flex;
  align-items: center;
  gap: 7px;
  width: 289px;
  flex-shrink: 0;
  height: 28px;
  padding: 0 10px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  background: #ffffff;
}

.analysis-search:focus-within {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}

.analysis-search-icon {
  color: #64748b;
  font-size: 16px;
}

.analysis-search input {
  width: 100%;
  min-width: 0;
  border: 0;
  outline: 0;
  background: transparent;
  color: #0f172a;
  font: inherit;
  font-size: 12.5px;
}

.analysis-filter-options {
  display: flex;
  align-items: center;
  gap: 4px;
}

.analysis-filter-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid transparent;
  border-radius: 7px;
  background: #f8fafc;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.analysis-filter-btn:hover:not(.active) {
  background: #f1f5f9;
  color: #0f172a;
}

.analysis-filter-btn:hover:not(.active) span {
  background: #cbd5e1;
  color: #0f172a;
}

.analysis-filter-btn span {
  min-width: 18px;
  padding: 1px 5px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 10px;
  text-align: center;
}

.analysis-filter-btn.active {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #4338ca;
}

.analysis-filter-btn.active span {
  background: #4f46e5;
  color: #ffffff;
}

.analysis-filter-result {
  margin-left: auto;
  color: #64748b;
  font-size: 11.5px;
  white-space: nowrap;
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
  background: #f8fafc;
  border-radius: 6px;
}

.analysis-column::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 6px;
}

.analysis-column::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

.analysis-column-left,
.analysis-column-right {
  border-radius: 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}

.analysis-column-left {
  padding: 14px;
}

.analysis-column-right {
  padding: 20px;
}

.tree-recommend-text {
  font-size: 11px;
  line-height: 1.4;
  font-weight: 500;
  color: #475569;
}

.tree-recommend-reason {
  font-size: 10.5px;
  line-height: 1.4;
  color: #94a3b8;
  margin-top: 2px;
}

.detail-card-evidence-overview {
  background: linear-gradient(135deg, #fafbff 0%, #f8fafc 100%);
  border: 1px solid #e2e8f0;
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
  color: #64748b;
}

.detail-hero {
  padding-bottom: 14px;
  margin-bottom: 16px;
  border-bottom: 1px solid #f1f5f9;
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
  color: #0f172a;
  letter-spacing: -0.01em;
}

.detail-hero-title-group {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}

.detail-title-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.detail-hero-subtitle {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
}

.detail-hero-row-actions {
  margin-top: 14px;
  align-items: flex-start;
}

.detail-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: #94a3b8;
}

.detail-stats strong {
  color: #0f172a;
  font-weight: 700;
  margin-left: 2px;
}

.detail-tags {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
}

.detail-tag {
  border-radius: 6px;
  padding: 3px 7px;
  font-size: 11px;
  font-weight: 600;
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
}

.detail-tag-progress.is-completed {
  background: rgba(34, 197, 94, 0.14);
  color: #15803d;
}

.detail-tag-progress.is-started {
  background: rgba(99, 102, 241, 0.12);
  color: #4338ca;
}

.detail-tag-progress.is-pending {
  background: #e2e8f0;
  color: #64748b;
}

.detail-tag-index {
  background: rgba(15, 23, 42, 0.06);
  color: #334155;
}

.detail-nav-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.nav-action-btn {
  border: 1px solid #cbd5e1;
  background: #fff;
  color: #334155;
  border-radius: 6px;
  padding: 4px 12px;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.nav-action-btn:hover:not(:disabled) {
  border-color: #6366f1;
  color: #4338ca;
}

.nav-action-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

.nav-action-btn-primary {
  background: #6366f1;
  border-color: #4f46e5;
  color: #fff;
}

.nav-action-btn-primary:hover:not(:disabled) {
  background: #4f46e5;
  color: #fff;
}

.detail-card {
  padding: 12px;
  border-radius: 12px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
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
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.4);
}

.detail-collapse-toggle + * {
  margin-top: 10px;
}

.detail-collapse-toggle .detail-card-title {
  margin-bottom: 0;
}

.detail-collapse-indicator {
  flex-shrink: 0;
  font-size: 11px;
  font-weight: 700;
  color: #6366f1;
  background: rgba(99, 102, 241, 0.08);
  padding: 2px 8px;
  border-radius: 999px;
}

.detail-card-title {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
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
  background: var(--accent, #6366f1);
  border-radius: 2px;
  opacity: 0.8;
}

.detail-helper-text {
  margin: 0 0 12px;
  font-size: 12px;
  line-height: 1.6;
  color: #94a3b8;
  font-weight: 400;
}

.detail-card-focus {
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.04), rgba(255, 255, 255, 0.95));
  border-color: #dbe4f4;
}

.focus-kicker {
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: #6366f1;
}

.focus-summary {
  margin-top: 8px;
  font-size: 16px;
  line-height: 1.7;
  color: #0f172a;
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
  color: #15803d;
}

.focus-chip-excluded {
  background: rgba(239, 68, 68, 0.12);
  color: #b91c1c;
}

.focus-chip-pending {
  background: #eef2f7;
  color: #475569;
}

/* 紧凑版因素分析与结论样式 */
.factor-progress-summary { margin-bottom: 12px; }
.factor-progress-track-mini { height: 4px; background: #e2e8f0; border-radius: 2px; overflow: hidden; display: flex; margin-bottom: 6px; }
.factor-progress-fill-mini { height: 100%; transition: width 0.3s ease; }
.factor-progress-fill-mini.is-confirmed { background: #22c55e; }
.factor-progress-fill-mini.is-excluded { background: #ef4444; }
.factor-progress-badges { display: flex; gap: 12px; }
.badge-mini { font-size: 11px; color: #64748b; }
.badge-mini strong { color: #0f172a; margin-left: 2px; }

.factor-grid-compact { display: flex; flex-direction: column; gap: 4px; }
.factor-card-mini { padding: 8px 12px; border-radius: 8px; background: #f8fafc; border: 1px solid transparent; transition: all 0.2s ease; }
.factor-card-mini:hover { background: #f1f5f9; border-color: #e2e8f0; }
.factor-card-mini.is-confirmed { border-left: 3px solid #22c55e; background: rgba(34, 197, 94, 0.03); }
.factor-card-mini.is-excluded { border-left: 3px solid #ef4444; background: rgba(239, 68, 68, 0.02); opacity: 0.8; }

.factor-info-mini { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.factor-main-mini { flex: 1; min-width: 0; }
.factor-name-mini { font-size: 13px; font-weight: 700; color: #1e293b; margin-bottom: 2px; }
.factor-meta-mini { font-size: 11px; color: #94a3b8; display: flex; gap: 8px; align-items: center; }
.tag-mini { background: rgba(15, 23, 42, 0.04); padding: 1px 6px; border-radius: 4px; }

.factor-ops-mini { display: flex; align-items: center; gap: 6px; }
.btn-mini { padding: 3px 10px; font-size: 11px; font-weight: 700; border-radius: 6px; border: 1px solid #e2e8f0; background: #fff; color: #475569; cursor: pointer; transition: all 0.15s ease; }
.btn-mini:hover { border-color: #6366f1; color: #4338ca; }
.btn-mini.active { background: #6366f1; border-color: #4f46e5; color: #fff; }
.btn-confirm.active { background: #22c55e; border-color: #16a34a; }
.btn-exclude.active { background: #ef4444; border-color: #dc2626; }
.btn-mini-text { font-size: 11px; color: #94a3b8; background: none; border: none; cursor: pointer; padding: 2px 4px; }
.btn-mini-text:hover { color: #64748b; text-decoration: underline; }

.detail-card-focus-compact { background: #fff; border: 1px solid #e0e7ff; box-shadow: 0 4px 12px rgba(99, 102, 241, 0.04); }
.focus-header-row { display: flex; align-items: center; justify-content: space-between; padding-bottom: 8px; border-bottom: 1px dashed #f1f5f9; margin-bottom: 10px; }
.focus-kicker-mini { font-size: 11px; font-weight: 700; color: #6366f1; text-transform: uppercase; letter-spacing: 0.05em; }
.focus-status-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 999px; }

.focus-content-compact { display: flex; flex-direction: column; gap: 8px; }
.focus-summary-text { font-size: 14px; font-weight: 700; color: #0f172a; line-height: 1.6; }
.focus-next-tip { font-size: 12px; color: #64748b; display: flex; align-items: center; gap: 6px; background: #f8fafc; padding: 6px 10px; border-radius: 6px; }
.tip-icon { font-size: 14px; }

.focus-next-step {
  margin-top: 12px;
  font-size: 13px;
  line-height: 1.7;
  color: #64748b;
}

/* 极致精简版因素分析样式 */
.section-compact-slim { padding: 12px 14px; }
.factor-mini-status { display: flex; align-items: center; gap: 10px; margin-left: auto; font-size: 11px; font-weight: 700; color: #64748b; }
.m-dot { width: 6px; height: 6px; border-radius: 50%; display: inline-block; margin-right: 2px; vertical-align: middle; }
.m-dot.c { background: #22c55e; }
.m-dot.e { background: #ef4444; }
.m-dot.p { background: #e2e8f0; }

.factor-list-slim { display: flex; flex-direction: column; gap: 4px; }
.factor-row-slim { display: flex; align-items: center; justify-content: space-between; padding: 6px 10px; border-radius: 8px; background: #f8fafc; border: 1px solid transparent; transition: all 0.15s ease; gap: 12px; }
.factor-row-slim:hover { background: #f1f5f9; border-color: #e2e8f0; }
.factor-row-slim.is-c { border-left: 3px solid #22c55e; background: rgba(34, 197, 94, 0.03); }
.factor-row-slim.is-e { border-left: 3px solid #ef4444; background: rgba(239, 68, 68, 0.02); opacity: 0.7; }

.f-info-slim { flex: 1; min-width: 0; }
.f-name-slim { font-size: 13px; font-weight: 600; color: #1e293b; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
.f-tag-mini { font-size: 10px; background: rgba(15, 23, 42, 0.05); padding: 1px 6px; border-radius: 4px; color: #64748b; margin-left: 8px; font-weight: 500; }

.f-ops-slim { display: flex; align-items: center; gap: 6px; }
.btn-xs-slim { padding: 2px 10px; font-size: 11px; font-weight: 700; border-radius: 6px; border: 1.5px solid #eef2f7; background: #fff; color: #475569; cursor: pointer; transition: all 0.1s ease; }
.btn-xs-slim:hover { border-color: #cbd5e1; background: #f8fafc; }
.btn-xs-slim.active { border-color: transparent; color: #fff; }
.btn-xs-slim.confirm.active { background: #22c55e; }
.btn-xs-slim.exclude.active { background: #ef4444; }
.action-btn-text { font-size: 11px; color: #94a3b8; background: none; border: none; cursor: pointer; padding: 2px 4px; }

.f-ev-slim { position: relative; }
.f-ev-slim summary { list-style: none; font-size: 11px; font-weight: 700; color: #6366f1; cursor: pointer; opacity: 0.8; padding: 2px 6px; background: rgba(99, 102, 241, 0.05); border-radius: 4px; }
.f-ev-slim summary:hover { opacity: 1; background: rgba(99, 102, 241, 0.1); }
.f-ev-slim[open] summary { margin-bottom: 8px; }

.detail-helper-text-tight {
  margin-top: 0;
}

.detail-card-count {
  font-size: 11px;
  font-weight: 700;
  color: #94a3b8;
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
  border-left: 2px solid #e2e8f0;
  color: #334155;
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
  color: #334155;
  font-size: 13px;
  border-bottom: 1px solid #f1f5f9;
}

.evidence-row:last-child {
  border-bottom: none;
}

.evidence-row-head {
  background: transparent;
  padding: 0 8px 4px;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 700;
  border-bottom: 1px solid #e2e8f0;
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
  color: #475569;
}

.evidence-source small {
  color: #94a3b8;
  font-size: 11px;
}

.evidence-operation {
  font-weight: 600;
}

.detail-note,
.detail-empty,
.empty-text {
  color: #64748b;
  line-height: 1.75;
}

.detail-empty-danger {
  color: #b91c1c;
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
  color: #0f172a;
}

.factor-tag {
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  background: #f1f5f9;
  color: #475569;
  font-weight: 600;
}

.factor-tag-strong {
  background: rgba(124, 58, 237, 0.1);
  color: #6d28d9;
}

.factor-tag-confirmed {
  background: rgba(34, 197, 94, 0.12);
  color: #15803d;
}

.factor-tag-excluded {
  background: rgba(239, 68, 68, 0.1);
  color: #b91c1c;
}

.factor-source {
  margin-top: 4px;
  font-size: 11px;
  color: #94a3b8;
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

.empty-mark {
  font-size: 36px;
  font-weight: 700;
  color: #8b5cf6;
}

.empty-title {
  margin-top: 12px;
  font-size: 22px;
  font-weight: 700;
  color: #0f172a;
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
  backdrop-filter: blur(8px);
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
  background: #ffffff;
  box-shadow: 0 25px 80px -12px rgba(0, 0, 0, 0.4);
}

.doc-preview-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
  padding: 18px 24px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
  flex-shrink: 0;
}

.doc-preview-title {
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.4;
}

.doc-preview-subtitle {
  margin-top: 6px;
  font-size: 13px;
  color: #64748b;
}

.doc-preview-actions {
  display: flex;
  align-items: center;
  gap: 10px;
}

.doc-preview-state {
  padding: 32px 24px;
  font-size: 14px;
  color: #64748b;
  flex: 1;
}

.doc-preview-state-error {
  color: #b91c1c;
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
  color: #1e293b;
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
  background: #ffffff;
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

  .analysis-filter-bar {
    align-items: stretch;
    flex-direction: column;
  }

  .analysis-search {
    width: 100%;
  }

  .analysis-filter-options {
    width: 100%;
    overflow-x: auto;
    padding-bottom: 2px;
  }

  .analysis-filter-btn {
    flex: 0 0 auto;
  }

  .analysis-filter-result {
    margin-left: 0;
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

  .detail-hero-row-actions {
    flex-direction: column;
    align-items: stretch;
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
</style>
