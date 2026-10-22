<script setup lang="ts">
import { computed } from 'vue'
import type { KnowledgeEvidence, KnowledgeSuggestion, KnowledgeSuggestionStatus } from '@/api/knowledge'
import { canApplyKnowledgeSuggestion } from '@/utils/knowledgeSuggestionApplicator'

const props = withDefaults(defineProps<{
  suggestions: KnowledgeSuggestion[]
  evidence: KnowledgeEvidence[]
  projectId: number
  routeVersionId: number
  segmentId: string
  busy?: boolean
}>(), { busy: false })

const emit = defineEmits<{ apply: [suggestion: KnowledgeSuggestion] }>()

const statusLabels: Record<KnowledgeSuggestionStatus, string> = {
  draft: '建议草稿',
  pending_review: '建议待审核',
  confirmed: '已确认建议',
  rejected: '建议已拒绝',
  stale: '建议已过期',
}
const statusReasons: Record<KnowledgeSuggestionStatus, string> = {
  draft: '建议尚未提交审核，请先在工艺知识库中完成审核。',
  pending_review: '建议尚未确认，完成审核后才能带入条件。',
  confirmed: '',
  rejected: '已拒绝的建议不能带入条件。',
  stale: '建议已过期，请基于当前路线重新检索并审核。',
}
const context = computed(() => ({
  projectId: props.projectId,
  routeVersionId: props.routeVersionId,
  segmentId: props.segmentId,
}))
const currentEvidence = computed(() => new Map(props.evidence
  .filter(item => item.project_id === props.projectId
    && item.route_version_id === props.routeVersionId
    && item.segment_id === props.segmentId)
  .map(item => [item.id, item])))
const rows = computed(() => props.suggestions.map(suggestion => {
  const ids = [...new Set(suggestion.evidence_ids)]
  const evidenceRows = ids.map(id => currentEvidence.value.get(id))
    .filter((item): item is KnowledgeEvidence => Boolean(item))
  const missingEvidenceIds = ids.filter(id => !currentEvidence.value.has(id))
  const matchesContext = suggestion.project_id === props.projectId
    && suggestion.route_version_id === props.routeVersionId
    && suggestion.segment_id === props.segmentId
  const completeEvidence = ids.length > 0 && missingEvidenceIds.length === 0
  const applicable = canApplyKnowledgeSuggestion(suggestion, context.value)
    && completeEvidence && !props.busy
  const reason = !matchesContext
    ? '建议不属于当前项目、路线和工序，不能带入。'
    : statusReasons[suggestion.status]
      || (!suggestion.suggestion_text.trim() ? '建议正文为空，不能带入。' : '')
  return { suggestion, evidenceRows, missingEvidenceIds, completeEvidence, applicable, reason }
}))

function sourceDocument(item: KnowledgeEvidence): string {
  return item.document_name?.trim() || item.document_id?.trim() || '未提供来源文档'
}

function handleApply(suggestion: KnowledgeSuggestion) {
  const current = rows.value.find(row => row.suggestion.id === suggestion.id)
  if (current?.applicable) emit('apply', suggestion)
}
</script>

<template>
  <section class="knowledge-suggestion-panel" aria-label="企业知识规则建议">
    <header class="panel-heading">
      <div>
        <span class="panel-eyebrow">企业知识依据</span>
        <h3>规则建议 <span class="suggestion-count">{{ suggestions.length }}</span></h3>
      </div>
      <span class="review-chain-note">带入条件 → 重新识别 → 人工确认</span>
    </header>

    <p v-if="!rows.length" class="panel-empty">当前工序暂无知识建议，可前往工艺知识库查询并采纳依据。</p>
    <article v-for="row in rows" :key="row.suggestion.id" class="suggestion-row">
      <div class="suggestion-topline">
        <h4>{{ row.suggestion.title || '企业知识规则建议' }}</h4>
        <span class="suggestion-status" :class="`status-${row.suggestion.status}`">
          {{ statusLabels[row.suggestion.status] }}
        </span>
      </div>
      <p class="suggestion-text">{{ row.suggestion.suggestion_text }}</p>
      <div class="suggestion-review-meta">
        <span>更新人 {{ row.suggestion.updated_by || row.suggestion.created_by || '未记录' }}</span>
        <time :datetime="row.suggestion.updated_at">{{ row.suggestion.updated_at }}</time>
      </div>

      <details class="evidence-details">
        <summary>知识依据 <span>{{ row.suggestion.evidence_ids.length }} 条</span></summary>
        <div v-for="item in row.evidenceRows" :key="item.id" class="evidence-item">
          <div class="evidence-source">
            <strong>{{ sourceDocument(item) }}</strong>
            <span v-if="item.page_no && item.page_no > 0" class="source-page">第 {{ item.page_no }} 页</span>
            <span v-else class="source-unavailable">来源页码定位不可用</span>
          </div>
          <p class="evidence-content">{{ item.content }}</p>
          <div class="evidence-identity">
            <span>依据 #{{ item.id }}</span>
            <code v-if="item.identity">{{ item.identity }}</code>
          </div>
        </div>
        <p v-if="!row.completeEvidence" class="evidence-warning" role="alert">
          依据缺失或不属于当前项目、路线和工序<template v-if="row.missingEvidenceIds.length">（#{{ row.missingEvidenceIds.join('、#') }}）</template>，请重新核对后再带入。
        </p>
      </details>

      <div class="suggestion-footer">
        <p v-if="row.reason" class="application-note application-note--blocked">{{ row.reason }}</p>
        <p v-else class="application-note">带入后旧确认将失效，仍需核对并确认新识别结果。</p>
        <button type="button" class="apply-suggestion-btn" :disabled="!row.applicable" @click="handleApply(row.suggestion)">
          带入当前条件
        </button>
      </div>
    </article>
  </section>
</template>

<style scoped>
.knowledge-suggestion-panel {
  background: #fff;
  border: 1px solid #dce5ef;
  border-radius: 10px;
  color: #243449;
  overflow: hidden;
}
.panel-heading {
  align-items: center;
  background: #f7faff;
  border-bottom: 1px solid #e2eaf3;
  display: flex;
  gap: 16px;
  justify-content: space-between;
  padding: 15px 18px;
}
.panel-eyebrow { color: #5e7694; display: block; font-size: 10px; font-weight: 700; letter-spacing: .08em; margin-bottom: 5px; }
.panel-heading h3 { align-items: center; display: flex; font-size: 14px; gap: 8px; margin: 0; }
.suggestion-count { background: #e7effa; border-radius: 4px; color: #3f6698; font-size: 11px; padding: 2px 6px; }
.review-chain-note { color: #6c8099; font-size: 11px; line-height: 1.6; text-align: right; }
.panel-empty { color: #6b7c91; font-size: 12px; line-height: 1.7; margin: 0; padding: 20px 18px; }
.suggestion-row { padding: 17px 18px; }
.suggestion-row + .suggestion-row { border-top: 1px solid #e7edf4; }
.suggestion-topline { align-items: flex-start; display: flex; gap: 12px; justify-content: space-between; }
.suggestion-topline h4 { font-size: 13px; line-height: 1.6; margin: 0; }
.suggestion-status { background: #edf2f8; border: 1px solid #dee6f0; border-radius: 4px; color: #62748b; flex: 0 0 auto; font-size: 10px; font-weight: 700; padding: 3px 6px; }
.status-confirmed { background: #edf7f3; border-color: #d3e9dd; color: #2a785a; }
.status-pending_review { background: #fff8e8; border-color: #efe2bd; color: #976d19; }
.status-rejected, .status-stale { background: #fbf0f0; border-color: #efdbdb; color: #a55959; }
.suggestion-text { color: #35475d; font-size: 13px; line-height: 1.8; margin: 11px 0 8px; overflow-wrap: anywhere; white-space: pre-wrap; }
.suggestion-review-meta { color: #7d8da1; display: flex; flex-wrap: wrap; font-size: 10px; gap: 6px 14px; }
.evidence-details { background: #fafbfd; border: 1px solid #e5ebf3; border-radius: 6px; margin-top: 13px; }
.evidence-details summary { color: #4f6887; cursor: pointer; font-size: 11px; font-weight: 700; padding: 9px 11px; }
.evidence-details summary span { color: #8796a8; font-weight: 400; margin-left: 5px; }
.evidence-details summary:focus-visible { border-radius: 5px; outline: 2px solid #5794da; outline-offset: 2px; }
.evidence-item { border-top: 1px solid #e8edf4; padding: 11px; }
.evidence-source { align-items: baseline; display: flex; flex-wrap: wrap; font-size: 11px; gap: 6px 10px; overflow-wrap: anywhere; }
.evidence-source strong { color: #5b708b; font-weight: 600; }
.source-page { color: #527cae; }
.source-unavailable { color: #9a7d4d; }
.evidence-content { color: #5b6b7e; font-size: 12px; line-height: 1.8; margin: 7px 0; overflow-wrap: anywhere; white-space: pre-wrap; }
.evidence-identity { align-items: baseline; color: #8a99ab; display: flex; flex-wrap: wrap; font-size: 10px; gap: 10px; overflow-wrap: anywhere; }
.evidence-identity code { color: #7c8fa6; font-size: 10px; }
.evidence-warning { background: #fffaf0; border-top: 1px solid #f1e5ce; color: #9b742e; font-size: 11px; line-height: 1.7; margin: 0; padding: 9px 11px; }
.suggestion-footer { align-items: center; display: flex; gap: 14px; justify-content: space-between; margin-top: 12px; }
.application-note { color: #74869d; font-size: 11px; line-height: 1.7; margin: 0; }
.application-note--blocked { color: #8a7d67; }
.apply-suggestion-btn { background: #edf4ff; border: 1px solid #c6d9f1; border-radius: 5px; color: #396baf; cursor: pointer; flex: 0 0 auto; font: inherit; font-size: 11px; font-weight: 700; padding: 7px 10px; }
.apply-suggestion-btn:hover:not(:disabled) { background: #e0ecfd; border-color: #a9c5e9; }
.apply-suggestion-btn:focus-visible { outline: 2px solid #5794da; outline-offset: 2px; }
.apply-suggestion-btn:disabled { background: #f4f6f9; border-color: #e2e7ee; color: #a0adbd; cursor: not-allowed; }
@media (max-width: 640px) {
  .panel-heading { align-items: flex-start; flex-direction: column; gap: 6px; padding: 13px 14px; }
  .review-chain-note { text-align: left; }
  .suggestion-row { padding: 14px; }
  .suggestion-footer { align-items: flex-start; flex-direction: column; gap: 9px; }
  .apply-suggestion-btn { align-self: flex-end; }
}
</style>
