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
  background: rgba(15, 23, 42, 0.42);
  backdrop-filter: blur(2px);
}

.workflow-reset-dialog {
  width: min(520px, 100%);
  overflow: hidden;
  border: 1px solid #d7dee8;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 20px 48px rgba(15, 23, 42, 0.2);
}

.workflow-reset-header {
  display: grid;
  grid-template-columns: 34px minmax(0, 1fr) 28px;
  gap: 10px;
  align-items: start;
  padding: 18px 18px 15px;
  border-bottom: 1px solid #e5eaf0;
}

.workflow-reset-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 7px;
  color: #a16207;
  background: #fef3c7;
}

.workflow-reset-icon svg,
.workflow-reset-close svg,
.workflow-reset-primary svg { width: 16px; height: 16px; }

.workflow-reset-header h2 {
  margin: 0;
  color: #172033;
  font-size: 16px;
  line-height: 1.4;
  letter-spacing: 0;
}

.workflow-reset-header p {
  margin: 5px 0 0;
  color: #64748b;
  font-size: 12.5px;
  line-height: 1.65;
}

.workflow-reset-close {
  display: grid;
  width: 28px;
  height: 28px;
  place-items: center;
  border: 0;
  border-radius: 5px;
  color: #64748b;
  background: transparent;
  cursor: pointer;
}

.workflow-reset-close:hover:not(:disabled) { color: #0f172a; background: #f1f5f9; }

.workflow-reset-impact {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0;
  padding: 14px 18px;
}

.workflow-reset-column { min-width: 0; padding: 2px 14px 2px 0; }
.workflow-reset-column + .workflow-reset-column { padding: 2px 0 2px 16px; border-left: 1px solid #e5eaf0; }
.workflow-reset-column strong { display: block; margin-bottom: 7px; color: #475569; font-size: 12px; }
.workflow-reset-column ul { margin: 0; padding-left: 17px; color: #475569; font-size: 12px; line-height: 1.75; }
.workflow-reset-keep li::marker { color: #15803d; }
.workflow-reset-clear li::marker { color: #c2410c; }

.workflow-reset-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  padding: 12px 18px;
  border-top: 1px solid #e5eaf0;
  background: #f8fafc;
}

.workflow-reset-actions button {
  display: inline-flex;
  min-height: 32px;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 0 13px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
}

.workflow-reset-secondary { border: 1px solid #cbd5e1; color: #475569; background: #fff; }
.workflow-reset-primary { border: 1px solid #b45309; color: #fff; background: #b45309; }
.workflow-reset-primary:hover:not(:disabled) { background: #92400e; border-color: #92400e; }
.workflow-reset-actions button:disabled { opacity: 0.55; cursor: wait; }
.workflow-reset-spinner { animation: workflow-reset-spin 0.8s linear infinite; }

@keyframes workflow-reset-spin { to { transform: rotate(360deg); } }

@media (max-width: 560px) {
  .workflow-reset-impact { grid-template-columns: 1fr; }
  .workflow-reset-column + .workflow-reset-column { margin-top: 10px; padding: 12px 0 2px; border-top: 1px solid #e5eaf0; border-left: 0; }
}
</style>
