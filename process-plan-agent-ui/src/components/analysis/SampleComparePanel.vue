<template>
  <article class="detail-card detail-card-wide">
    <button class="detail-collapse-toggle" type="button" @click="$emit('toggle')">
      <span class="detail-card-title">差异样本</span>
      <span class="detail-collapse-indicator">
        <span>{{ expanded ? '收起' : '展开' }}</span>
        <svg
          class="detail-collapse-chevron"
          :class="{ 'detail-collapse-chevron--open': expanded }"
          viewBox="0 0 16 16"
          width="9"
          height="9"
          fill="none"
        >
          <path
            d="M6 4l4 4-4 4"
            stroke="currentColor"
            stroke-width="1.8"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </span>
    </button>
    <template v-if="expanded">
      <p class="detail-helper-text">点击样本查看 PDF 原文。</p>
      
      <div class="sample-compare-grid">
        <div class="sample-compare-card">
          <div class="sample-compare-head">
            <span class="compare-title-text">出现这道工序的样本</span>
            <span class="compare-count-badge compare-count-badge--success">{{ hitDocuments.length }}</span>
          </div>
          <div v-if="hitDocuments.length" class="sample-doc-list">
            <button
              v-for="doc in hitDocuments"
              :key="`hit-${doc.id}`"
              type="button"
              class="sample-doc-button"
              @click="$emit('select-document', doc)"
            >
              <span class="doc-icon">📄</span>
              <span class="doc-text">{{ cleanDocName(doc.original_name) }}</span>
            </button>
          </div>
          <div v-else class="detail-empty">当前还没有找到包含这道工序的样本。</div>
        </div>

        <div class="sample-compare-card">
          <div class="sample-compare-head">
            <span class="compare-title-text">不出现这道工序的样本</span>
            <span class="compare-count-badge compare-count-badge--muted">{{ missingDocuments.length }}</span>
          </div>
          <div v-if="missingDocuments.length" class="sample-doc-list">
            <button
              v-for="doc in missingDocuments"
              :key="`miss-${doc.id}`"
              type="button"
              class="sample-doc-button sample-doc-button--miss"
              @click="$emit('select-document', doc)"
            >
              <span class="doc-icon">📄</span>
              <span class="doc-text">{{ cleanDocName(doc.original_name) }}</span>
            </button>
          </div>
          <div v-else class="detail-empty">当前样本里这道工序全部都出现了。</div>
        </div>
      </div>

    </template>
  </article>
</template>

<script setup lang="ts">
import type { DocumentItem } from '@/api'

defineProps<{
  expanded: boolean
  hitDocuments: DocumentItem[]
  missingDocuments: DocumentItem[]
}>()

defineEmits<{
  toggle: []
  'select-document': [doc: DocumentItem]
}>()

function cleanDocName(name?: string) {
  if (!name) return ''
  return name.replace(/\.(pdf|docx|xlsx|doc|xls)$/i, '')
}
</script>

<style scoped>
.detail-card-title {
  font-size: 13px;
  line-height: 20px;
  font-weight: 600;
  color: var(--pm-text);
}

.detail-helper-text {
  font-size: 12px;
  color: #64748b;
  margin-top: 4px;
  margin-bottom: 12px;
}

.detail-empty {
  font-size: 11.5px;
  color: #94a3b8;
  padding: 12px;
  text-align: center;
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
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  color: var(--pm-primary);
}

.detail-collapse-chevron {
  transition: transform 0.2s ease;
}

.detail-collapse-chevron--open {
  transform: rotate(90deg);
}

.sample-compare-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}

.sample-compare-card {
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
}

.sample-compare-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}

.compare-title-text {
  font-size: 11.5px;
  font-weight: 600;
  color: #475569;
}

.compare-count-badge {
  font-size: 10.5px;
  font-weight: 700;
  padding: 1px 6px;
  border-radius: 4px;
  font-family: ui-monospace, monospace;
}

.compare-count-badge--success {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.compare-count-badge--muted {
  background: #f1f5f9;
  color: #64748b;
}

.sample-doc-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
  padding-right: 4px;
}

/* Chrome scrollbar optimization */
.sample-doc-list::-webkit-scrollbar {
  width: 4px;
}
.sample-doc-list::-webkit-scrollbar-track {
  background: transparent;
}
.sample-doc-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 10px;
}

.sample-doc-button {
  width: 100%;
  text-align: left;
  background: #fafafb;
  border: 1px solid #f1f5f9;
  border-radius: 4px;
  padding: 4px 8px;
  cursor: pointer;
  display: flex;
  align-items: center;
  gap: 6px;
  transition: all 0.12s ease;
  min-width: 0;
}

.sample-doc-button:hover {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
  color: var(--pm-primary);
}

.doc-icon {
  font-size: 11px;
  flex-shrink: 0;
  opacity: 0.65;
}

.doc-text {
  font-size: 11.5px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}

.sample-doc-button--miss .doc-text {
  color: #64748b;
}

</style>
