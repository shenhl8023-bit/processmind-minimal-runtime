<template>
  <div class="workflow-nav-footer" role="navigation" aria-label="流程导航">
    <div class="workflow-nav-inner">
      <div class="workflow-nav-summary">
        <slot name="summary">{{ summary }}</slot>
      </div>
      <div class="workflow-nav-actions">
        <button
          v-if="showPrevious"
          class="workflow-nav-btn workflow-nav-btn-prev"
          type="button"
          :disabled="previousDisabled"
          @click="$emit('previous')"
        >
          {{ previousLabel }}
        </button>
        <button
          class="workflow-nav-btn workflow-nav-btn-next"
          type="button"
          :disabled="nextDisabled"
          @click="$emit('next')"
        >
          {{ nextLabel }}
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
withDefaults(defineProps<{
  summary?: string
  previousLabel?: string
  nextLabel: string
  showPrevious?: boolean
  previousDisabled?: boolean
  nextDisabled?: boolean
}>(), {
  summary: '',
  previousLabel: '← 上一步',
  showPrevious: true,
  previousDisabled: false,
  nextDisabled: false,
})

defineEmits<{
  previous: []
  next: []
}>()
</script>

<style scoped>
.workflow-nav-footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 45;
  border-top: 1px solid rgba(226, 232, 240, 0.9);
  background: rgba(248, 250, 252, 0.97);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  pointer-events: none;
}

.workflow-nav-inner {
  /* 与 App.vue .main-area 同一最大宽度与左右内边距，保证按钮右缘对齐上方模块 */
  max-width: var(--page-max-width, 1280px);
  width: 100%;
  height: 48px;
  margin: 0 auto;
  padding: 0 var(--page-padding-x, 24px);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  pointer-events: auto;
}

.workflow-nav-summary {
  flex: 1;
  min-width: 0;
  color: var(--text-secondary, #475569);
  font-size: 12.5px;
  line-height: 1.5;
}

.workflow-nav-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

.workflow-nav-btn {
  min-width: 148px;
  height: 36px;
  padding: 0 16px;
  border-radius: 8px;
  border: 1px solid #c7d2fe;
  font: inherit;
  font-size: 12.5px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

.workflow-nav-btn-prev {
  background: #ffffff;
  color: #4f46e5;
}

.workflow-nav-btn-prev:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #818cf8;
  color: #4338ca;
}

.workflow-nav-btn-next {
  border-color: #4f46e5;
  background: #4f46e5;
  color: #ffffff;
}

.workflow-nav-btn-next:hover:not(:disabled) {
  background: #4338ca;
  border-color: #4338ca;
  box-shadow: 0 8px 18px rgba(79, 70, 229, 0.25);
  transform: translateY(-1px);
}

.workflow-nav-btn:disabled {
  cursor: not-allowed;
  opacity: 0.5;
  box-shadow: none;
  transform: none;
}

@media (max-width: 900px) {
  .workflow-nav-footer {
    padding: 8px var(--page-padding-x, 16px) 10px;
  }

  .workflow-nav-inner {
    align-items: stretch;
    flex-direction: column;
    height: auto;
    gap: 8px;
    padding: 10px 0;
  }

  .workflow-nav-actions {
    display: grid;
    grid-template-columns: repeat(2, minmax(0, 1fr));
    width: 100%;
  }

  .workflow-nav-btn {
    min-width: 0;
    width: 100%;
  }

  .workflow-nav-btn:only-child {
    grid-column: 1 / -1;
  }
}
</style>
