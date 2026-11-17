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
  padding: 16px;
  background: var(--el-mask-color);
}

.workflow-reset-dialog {
  display: flex;
  flex-direction: column;
  width: min(620px, 100%);
  max-height: calc(100vh - 32px);
  overflow: hidden;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-dialog);
  color: var(--pm-text);
  background: var(--pm-surface);
  box-shadow: var(--pm-shadow-popup);
}

/* ── Header ── */
.workflow-reset-header {
  display: grid;
  grid-template-columns: 32px minmax(0, 1fr) 24px;
  gap: 10px;
  align-items: start;
  flex-shrink: 0;
  padding: 16px 16px 0;
}

.workflow-reset-icon {
  display: grid;
  width: 32px;
  height: 32px;
  place-items: center;
  border: 1px solid var(--pm-primary-border);
  border-radius: var(--pm-radius-control);
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
}

.workflow-reset-icon svg { width: 15px; height: 15px; }
.workflow-reset-close svg { width: 14px; height: 14px; }
.workflow-reset-primary svg { width: 14px; height: 14px; }

.workflow-reset-header h2 {
  margin: 0;
  color: var(--pm-text);
  font-size: 16px;
  font-weight: 600;
  line-height: 24px;
}

.workflow-reset-header p {
  margin: 6px 0 0;
  color: var(--pm-text-secondary);
  font-size: 13px;
  line-height: 1.6;
  overflow-wrap: anywhere;
}

.workflow-reset-close {
  display: grid;
  width: 24px;
  height: 24px;
  place-items: center;
  border: 0;
  border-radius: var(--pm-radius-control);
  color: var(--pm-text-muted);
  background: transparent;
  cursor: pointer;
  margin-top: 2px;
}

.workflow-reset-close:hover:not(:disabled) { color: var(--pm-text); background: var(--pm-surface-subtle); }

.workflow-reset-dialog button:focus-visible {
  outline: 2px solid var(--pm-primary);
  outline-offset: 2px;
}

/* ── Impact columns ── */
.workflow-reset-impact {
  display: grid;
  grid-template-columns: minmax(0, 0.85fr) minmax(0, 1.35fr);
  gap: 0;
  min-height: 0;
  overflow-y: auto;
  margin: 16px;
  padding: 12px;
  border: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
  border-radius: var(--pm-radius-card);
}

.workflow-reset-column { min-width: 0; padding: 0 8px 0 0; }
.workflow-reset-column + .workflow-reset-column { padding: 0 0 0 12px; border-left: 1px solid var(--pm-border); }

.workflow-reset-column > strong { display: block; margin-bottom: 6px; font-size: 13px; font-weight: 600; line-height: 20px; }
.workflow-reset-keep > strong { color: var(--pm-success); }
.workflow-reset-clear > strong { color: var(--pm-primary); }

.workflow-reset-column ul { margin: 0; padding-left: 16px; color: var(--pm-text-secondary); font-size: 13px; line-height: 1.6; overflow-wrap: anywhere; }
.workflow-reset-column li + li { margin-top: 4px; }
.workflow-reset-keep li::marker { color: var(--pm-success); }
.workflow-reset-clear li::marker { color: var(--pm-primary); }

/* ── Footer actions ── */
.workflow-reset-actions {
  display: flex;
  flex-shrink: 0;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 16px;
  border-top: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
}

.workflow-reset-actions button {
  display: inline-flex;
  min-height: var(--pm-control-height);
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 14px;
  border-radius: var(--pm-radius-control);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  cursor: pointer;
  transition: var(--transition);
}

.workflow-reset-secondary { border: 1px solid var(--pm-border-strong); color: var(--pm-text-secondary); background: var(--pm-surface); }
.workflow-reset-secondary:hover:not(:disabled) { background: var(--pm-surface-subtle); border-color: var(--pm-primary); color: var(--pm-primary); }
.workflow-reset-primary { border: 1px solid var(--pm-primary); color: var(--pm-surface); background: var(--pm-primary); }
.workflow-reset-primary:hover:not(:disabled) { background: var(--pm-primary-hover); border-color: var(--pm-primary-hover); }
.workflow-reset-actions button:disabled { opacity: 0.55; cursor: wait; }
.workflow-reset-spinner { animation: workflow-reset-spin 0.8s linear infinite; }

@keyframes workflow-reset-spin { to { transform: rotate(360deg); } }

@media (max-width: 560px) {
  .workflow-reset-impact { grid-template-columns: 1fr; }
  .workflow-reset-column + .workflow-reset-column { margin-top: 12px; padding: 12px 0 0; border-top: 1px solid var(--pm-border); border-left: 0; }
}
</style>
