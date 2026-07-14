<template>
  <article class="detail-card detail-card-wide">
    <button class="detail-collapse-toggle" type="button" @click="$emit('toggle')">
      <span class="detail-card-title">差异样本</span>
      <span class="detail-collapse-indicator">{{ expanded ? '收起' : '展开' }}</span>
    </button>
    <template v-if="expanded">
      <p class="detail-helper-text">用途：帮助你判断这道工序出现时通常伴随什么，不出现时又更像哪类路线。</p>
      
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

      <div class="sample-summary-grid">
        <div class="sample-summary-card">
          <div class="sample-summary-title">出现这道工序时，常一起出现</div>
          <div v-if="hitHighlights.length" class="sample-summary-list">
            <div v-for="item in hitHighlights" :key="`hit-op-${item.name}`" class="sample-summary-item">
              <span class="summary-item-name">{{ item.name }}</span>
              <span class="summary-item-badge">{{ item.docCount }}</span>
            </div>
          </div>
          <div v-else class="detail-empty">暂时还没有足够信息。</div>
        </div>

        <div class="sample-summary-card">
          <div class="sample-summary-title">不出现这道工序时，常见什么</div>
          <div v-if="missingHighlights.length" class="sample-summary-list">
            <div v-for="item in missingHighlights" :key="`miss-op-${item.name}`" class="sample-summary-item">
              <span class="summary-item-name">{{ item.name }}</span>
              <span class="summary-item-badge">{{ item.docCount }}</span>
            </div>
          </div>
          <div v-else class="detail-empty">当前没有形成明显对照。</div>
        </div>

        <div class="sample-summary-card">
          <div class="sample-summary-title">原始文件里怎么称呼它</div>
          <div v-if="variantNames.length" class="sample-summary-list">
            <div v-for="item in variantNames" :key="`variant-${item.name}`" class="sample-summary-item">
              <span class="summary-item-name">{{ item.name }}</span>
              <span class="summary-item-badge summary-item-badge--accent">{{ item.count }}</span>
            </div>
          </div>
          <div v-else class="detail-empty">暂时还没有匹配到原始叫法。</div>
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
  hitHighlights: Array<{ name: string; docCount: number }>
  missingHighlights: Array<{ name: string; docCount: number }>
  variantNames: Array<{ name: string; count: number }>
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
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
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
  font-size: 12.5px;
  font-weight: 600;
  color: #6366f1;
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
  background: rgba(34, 197, 94, 0.08);
  color: #16a34a;
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
  background: #eef2ff;
  border-color: #cbd5e1;
  color: #4f46e5;
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

.sample-summary-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin-top: 10px;
}

.sample-summary-card {
  border-radius: 8px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  padding: 10px 12px;
}

.sample-summary-title {
  font-size: 11px;
  font-weight: 600;
  color: #475569;
  margin-bottom: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f1f5f9;
}

.sample-summary-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.sample-summary-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 3px 6px;
  background: #fafafb;
  border-radius: 4px;
  border: 1px solid #f8fafc;
}

.summary-item-name {
  font-size: 11.5px;
  color: #334155;
  font-weight: 500;
}

.summary-item-badge {
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 700;
  color: #64748b;
  background: #e2e8f0;
  padding: 1px 5px;
  border-radius: 3px;
  font-family: ui-monospace, monospace;
}

.summary-item-badge--accent {
  color: #4f46e5;
  background: rgba(99, 102, 241, 0.08);
}
</style>
