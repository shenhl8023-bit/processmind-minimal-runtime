<template>
  <article class="detail-card detail-card-wide">
    <button class="detail-collapse-toggle" type="button" @click="$emit('toggle')">
      <span class="detail-card-title">
        内容证据摘录
        <span v-if="excerpts.length" class="detail-card-count">{{ excerpts.length }}</span>
      </span>
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
      <div v-if="excerpts.length" class="excerpt-list">
        <div v-for="excerpt in excerpts" :key="excerpt" class="excerpt-item">
          <span class="excerpt-quote-icon">“</span>
          <div class="excerpt-content">{{ excerpt }}</div>
        </div>
      </div>
      <div v-else class="detail-empty">暂无摘录证据。</div>
    </template>
  </article>
</template>

<script setup lang="ts">
defineProps<{
  expanded: boolean
  excerpts: string[]
}>()

defineEmits<{
  toggle: []
}>()
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
  display: inline-flex;
  align-items: center;
  gap: 4px;
  font-size: 12.5px;
  font-weight: 600;
  color: #6366f1;
}

.detail-collapse-chevron {
  transition: transform 0.2s ease;
}

.detail-collapse-chevron--open {
  transform: rotate(90deg);
}

.excerpt-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 12px;
}

.excerpt-item {
  position: relative;
  padding: 10px 12px 10px 24px;
  border-radius: 6px;
  background: linear-gradient(to right, #fafafb 0%, #ffffff 100%);
  border: 1px solid #e2e8f0;
  border-left: 3px solid #6366f1;
  display: flex;
  align-items: flex-start;
  gap: 6px;
  transition: all 0.15s ease;
}

.excerpt-item:hover {
  border-color: #cbd5e1;
  border-left-color: #4f46e5;
  box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03);
}

.excerpt-quote-icon {
  position: absolute;
  left: 6px;
  top: 4px;
  font-size: 20px;
  line-height: 1;
  font-family: Georgia, serif;
  color: #818cf8;
  opacity: 0.4;
  user-select: none;
}

.excerpt-content {
  font-size: 12.5px;
  color: #334155;
  line-height: 1.6;
  font-weight: 500;
}

.detail-empty {
  font-size: 12px;
  color: #94a3b8;
  padding: 16px;
  text-align: center;
}
</style>
