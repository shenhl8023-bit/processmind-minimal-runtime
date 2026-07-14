<template>
  <div class="action-footer">
    <div class="summary-text">
      <slot name="summary">{{ summary }}</slot>
    </div>
    <div :class="actionContainerClass">
      <slot name="actions" />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = withDefaults(defineProps<{
  summary?: string
  blocked?: boolean
}>(), {
  summary: '',
  blocked: false,
})

const actionContainerClass = computed(() => props.blocked ? 'footer-blocked' : 'footer-action')
</script>

<style scoped>
.action-footer { display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 8px 16px; background: var(--bg-card); border-radius: var(--radius-md, 8px); border: 1px solid var(--border-light); margin-top: 8px; }
.summary-text { font-size: 12.5px; color: var(--text-secondary); line-height: 1.5; flex: 1; min-width: 0; }
.footer-action { display: flex; align-items: center; flex-shrink: 0; }
.footer-blocked { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }

@media (max-width: 900px) {
  .action-footer {
    position: sticky;
    bottom: 8px;
    z-index: 20;
    flex-direction: column;
    align-items: stretch;
    padding: 10px 12px;
    box-shadow: 0 8px 24px rgba(15, 23, 42, 0.12);
  }
  .footer-blocked { flex-direction: column; align-items: flex-start; }
}
</style>
