<template>
  <article class="detail-card detail-card-wide">
    <button class="detail-collapse-toggle" type="button" @click="$emit('toggle')">
      <span class="detail-card-title">
        原始工序明细
        <span v-if="rows.length" class="detail-card-count">{{ rows.length }}</span>
      </span>
      <span class="detail-collapse-indicator">{{ expanded ? '收起' : '展开' }}</span>
    </button>
    <template v-if="expanded">
      <div v-if="rows.length" class="evidence-table-container">
        <div class="evidence-table">
          <div class="evidence-row evidence-row-head">
            <span>来源</span>
            <span>原始工序</span>
            <span>加工内容明细</span>
          </div>
          <div
            v-for="row in rows"
            :key="`${row.detail_id}-${row.document_id}`"
            class="evidence-row"
          >
            <div class="evidence-source">
              <span class="source-doc-badge">
                <span class="doc-icon">📄</span>
                <span class="doc-text">{{ cleanDocName(row.pdf_name) }}</span>
              </span>
              <span class="source-page-badge">p{{ row.page_no || '-' }} #{{ row.operation_seq }}</span>
            </div>
            <span class="evidence-operation">{{ row.operation_name }}</span>
            <span class="evidence-content">{{ row.operation_content || '—' }}</span>
          </div>
        </div>
      </div>
      <div v-else class="detail-empty">暂无匹配明细。</div>
    </template>
  </article>
</template>

<script setup lang="ts">
import type { MergeMatchedDetailRow } from '@/api'

defineProps<{
  expanded: boolean
  rows: MergeMatchedDetailRow[]
}>()

defineEmits<{
  toggle: []
}>()

function cleanDocName(name?: string) {
  if (!name) return ''
  return name.replace(/\.(pdf|docx|xlsx|doc|xls)$/i, '')
}
</script>

<style scoped>
.detail-card-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.detail-card-count {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  background: #f1f5f9;
  padding: 1px 5px;
  border-radius: 4px;
  margin-left: 6px;
  font-family: ui-monospace, monospace;
}

.detail-collapse-toggle {
  width: 100%;
  border: none;
  background: none;
  padding: 0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  cursor: pointer;
}

.detail-collapse-indicator {
  font-size: 12.5px;
  font-weight: 600;
  color: #6366f1;
}

.evidence-table-container {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #ffffff;
  overflow: hidden;
}

.evidence-table {
  display: flex;
  flex-direction: column;
  width: 100%;
}

.evidence-row {
  display: grid;
  grid-template-columns: 240px 100px minmax(0, 1fr);
  gap: 12px;
  padding: 8px 12px;
  color: #334155;
  font-size: 12.5px;
  border-bottom: 1px solid #f1f5f9;
  align-items: center;
  transition: background-color 0.15s ease;
}

.evidence-row:hover:not(.evidence-row-head) {
  background-color: #fafcff;
}

.evidence-row:last-child {
  border-bottom: none;
}

.evidence-row-head {
  background: #f8fafc;
  padding: 6px 12px;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  border-bottom: 1px solid #e2e8f0;
}

.evidence-source {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.source-doc-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 6px;
  background: #f1f5f9;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  min-width: 0;
}

.source-doc-badge .doc-icon {
  font-size: 10px;
  opacity: 0.65;
}

.source-doc-badge .doc-text {
  font-size: 11px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 600;
  color: #475569;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.source-page-badge {
  font-size: 10.5px;
  color: #94a3b8;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 500;
  flex-shrink: 0;
}

.evidence-operation {
  font-weight: 600;
  color: #0f172a;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.evidence-content {
  color: #475569;
  line-height: 1.5;
  min-width: 0;
  word-break: break-all;
}

.detail-empty {
  font-size: 12px;
  color: #94a3b8;
  padding: 16px;
  text-align: center;
}
</style>
