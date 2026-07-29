<template>
  <Teleport to="body">
    <div v-if="modelValue" class="workflow-reset-overlay" @click.self="close">
      <section class="workflow-reset-dialog" role="dialog" aria-modal="true" :aria-labelledby="titleId">
        <header class="workflow-reset-header">
          <span class="workflow-reset-icon" aria-hidden="true"><WarningFilled /></span>
          <div>
            <h2 :id="titleId">{{ title }}</h2>
            <p>{{ description }}</p>
          </div>
          <button type="button" class="workflow-reset-close" aria-label="关闭" :disabled="busy" @click="close">
            <Close />
          </button>
        </header>

        <div class="workflow-reset-impact">
          <div v-if="keepItems.length" class="workflow-reset-column workflow-reset-keep">
            <strong>继续保留</strong>
            <ul><li v-for="item in keepItems" :key="item">{{ item }}</li></ul>
          </div>
          <div class="workflow-reset-column workflow-reset-clear">
            <strong>重新处理</strong>
            <ul><li v-for="item in clearItems" :key="item">{{ item }}</li></ul>
          </div>
        </div>

        <footer class="workflow-reset-actions">
          <button type="button" class="workflow-reset-secondary" :disabled="busy" @click="close">取消</button>
          <button type="button" class="workflow-reset-primary" :disabled="busy" @click="$emit('confirm')">
            <Loading v-if="busy" class="workflow-reset-spinner" />
            <RefreshRight v-else />
            {{ busy ? busyLabel : confirmLabel }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Close, Loading, RefreshRight, WarningFilled } from '@element-plus/icons-vue'

const props = withDefaults(defineProps<{
  modelValue: boolean
  title: string
  description: string
  keepItems?: string[]
  clearItems: string[]
  confirmLabel: string
  busyLabel?: string
  busy?: boolean
}>(), {
  keepItems: () => [],
  busyLabel: '正在处理...',
  busy: false,
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

const titleId = `workflow-reset-title-${Math.random().toString(36).slice(2)}`

function close() {
  if (!props.busy) emit('update:modelValue', false)
}
</script>

<style scoped>
.workflow-reset-overlay {
  position: fixed;
  inset: 0;
  z-index: 2200;
  display: grid;
  place-items: center;
  padding: 20px;
  background: rgba(15, 23, 42, 0.38);
  backdrop-filter: blur(2px);
}

.workflow-reset-dialog {
  width: min(460px, 100%);
  overflow: hidden;
  border-radius: 10px;
  background: #fff;
  box-shadow: 0 16px 40px rgba(15, 23, 42, 0.18);
}

/* ── Header ── */
.workflow-reset-header {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) 24px;
  gap: 10px;
  align-items: start;
  padding: 16px 16px 0;
}

.workflow-reset-icon {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border-radius: 7px;
  color: #4f46e5;
  background: #eef2ff;
}

.workflow-reset-icon svg { width: 15px; height: 15px; }
.workflow-reset-close svg { width: 14px; height: 14px; }
.workflow-reset-primary svg { width: 14px; height: 14px; }

.workflow-reset-header h2 {
  margin: 0;
  color: #1e293b;
  font-size: 14.5px;
  font-weight: 700;
  line-height: 28px;
}

.workflow-reset-header p {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 12px;
  line-height: 1.6;
}

.workflow-reset-close {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 0;
  border-radius: 5px;
  color: #94a3b8;
  background: transparent;
  cursor: pointer;
  margin-top: 2px;
}

.workflow-reset-close:hover:not(:disabled) { color: #475569; background: #f1f5f9; }

/* ── Impact columns ── */
.workflow-reset-impact {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  margin: 12px 16px 0;
  padding: 10px 12px;
  background: #f8fafc;
  border-radius: 6px;
}

.workflow-reset-column { min-width: 0; padding: 0 8px 0 0; }
.workflow-reset-column + .workflow-reset-column { padding: 0 0 0 12px; border-left: 1px solid #e5eaf0; }

.workflow-reset-keep > strong { display: block; margin-bottom: 4px; color: #059669; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }
.workflow-reset-clear > strong { display: block; margin-bottom: 4px; color: #6366f1; font-size: 11px; font-weight: 700; text-transform: uppercase; letter-spacing: 0.3px; }

.workflow-reset-column ul { margin: 0; padding-left: 15px; color: #475569; font-size: 11.5px; line-height: 1.7; }
.workflow-reset-keep li::marker { color: #059669; }
.workflow-reset-clear li::marker { color: #6366f1; }

/* ── Footer actions ── */
.workflow-reset-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 14px 16px;
}

.workflow-reset-actions button {
  display: inline-flex;
  min-height: 30px;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 14px;
  border-radius: 7px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.workflow-reset-secondary { border: 1px solid #e2e8f0; color: #64748b; background: #fff; }
.workflow-reset-secondary:hover:not(:disabled) { background: #f8fafc; border-color: #cbd5e1; color: #475569; }
.workflow-reset-primary { border: 1px solid #4f46e5; color: #fff; background: #4f46e5; }
.workflow-reset-primary:hover:not(:disabled) { background: #4338ca; border-color: #4338ca; }
.workflow-reset-actions button:disabled { opacity: 0.55; cursor: wait; }
.workflow-reset-spinner { animation: workflow-reset-spin 0.8s linear infinite; }

@keyframes workflow-reset-spin { to { transform: rotate(360deg); } }

@media (max-width: 560px) {
  .workflow-reset-impact { grid-template-columns: 1fr; }
  .workflow-reset-column + .workflow-reset-column { margin-top: 8px; padding: 8px 0 0; border-top: 1px solid #e5eaf0; border-left: 0; }
}
</style>
