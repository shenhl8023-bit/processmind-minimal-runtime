<template>
  <Teleport to="body">
    <div v-if="modelValue" class="template-mapping-required-overlay" @click.self="close">
      <section class="template-mapping-required-dialog" role="dialog" aria-modal="true" aria-labelledby="template-mapping-required-title">
        <header class="template-mapping-required-header">
          <span class="template-mapping-required-icon" aria-hidden="true">
            <WarningFilled />
          </span>
          <div class="template-mapping-required-header-info">
            <span class="template-mapping-required-kicker">前置要求检查</span>
            <h2 id="template-mapping-required-title">{{ title }}</h2>
          </div>
          <button type="button" class="template-mapping-required-close" aria-label="关闭" @click="close">
            <Close />
          </button>
        </header>

        <div class="template-mapping-required-body">
          <p class="template-mapping-required-main-msg">
            {{ description }}
          </p>
          <div class="template-mapping-required-hint">
            <strong>为什么需要完成分组模板映射？</strong>
            <p>第三步“规则分析”以及第四步“规则定稿与发布”均依赖标准工序与分组模板的映射关系。未完成映射将导致规则包无法通过校验和发布。</p>
          </div>
        </div>

        <footer class="template-mapping-required-actions">
          <button type="button" class="btn-cancel" @click="close">
            {{ cancelLabel }}
          </button>
          <button type="button" class="btn-confirm" @click="handleConfirm">
            <Connection class="btn-icon" />
            {{ confirmLabel }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { Close, Connection, WarningFilled } from '@element-plus/icons-vue'

withDefaults(defineProps<{
  modelValue: boolean
  title?: string
  description?: string
  confirmLabel?: string
  cancelLabel?: string
}>(), {
  title: '请先完成分组模板映射',
  description: '当前任务尚未完成工序分组模板映射。必须先完成映射后方可进入规则分析。',
  confirmLabel: '立即去映射',
  cancelLabel: '稍后处理',
})

const emit = defineEmits<{
  'update:modelValue': [value: boolean]
  confirm: []
}>()

function close() {
  emit('update:modelValue', false)
}

function handleConfirm() {
  emit('confirm')
  close()
}
</script>

<style scoped>
.template-mapping-required-overlay {
  position: fixed;
  inset: 0;
  z-index: 1000;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: rgba(15, 23, 42, 0.55);
  backdrop-filter: blur(4px);
}

.template-mapping-required-dialog {
  width: min(480px, 100%);
  background: #ffffff;
  border-radius: 14px;
  box-shadow: 0 20px 25px -5px rgba(15, 23, 42, 0.18), 0 8px 10px -6px rgba(15, 23, 42, 0.08);
  border: 1px solid #e2e8f0;
  overflow: hidden;
  animation: dialog-pop 0.18s ease-out;
}

@keyframes dialog-pop {
  from {
    opacity: 0;
    transform: scale(0.96) translateY(6px);
  }
  to {
    opacity: 1;
    transform: scale(1) translateY(0);
  }
}

.template-mapping-required-header {
  display: flex;
  align-items: flex-start;
  gap: 14px;
  padding: 20px 22px 14px;
  border-bottom: 1px solid #f1f5f9;
}

.template-mapping-required-icon {
  width: 38px;
  height: 38px;
  border-radius: 10px;
  background: #fff7ed;
  color: #ea580c;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 20px;
  flex-shrink: 0;
}

.template-mapping-required-header-info {
  flex: 1;
}

.template-mapping-required-kicker {
  display: block;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.04em;
  color: #ea580c;
  text-transform: uppercase;
  margin-bottom: 3px;
}

.template-mapping-required-header-info h2 {
  margin: 0;
  font-size: 17px;
  font-weight: 700;
  color: #0f172a;
  line-height: 1.35;
}

.template-mapping-required-close {
  border: none;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  padding: 4px;
  border-radius: 6px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 16px;
  transition: all 0.15s ease;
}

.template-mapping-required-close:hover {
  background: #f1f5f9;
  color: #475569;
}

.template-mapping-required-body {
  padding: 16px 22px;
}

.template-mapping-required-main-msg {
  margin: 0;
  font-size: 14px;
  color: #334155;
  line-height: 1.6;
}

.template-mapping-required-hint {
  margin-top: 14px;
  padding: 12px 14px;
  background: #f8fafc;
  border-radius: 8px;
  border: 1px solid #e2e8f0;
}

.template-mapping-required-hint strong {
  display: block;
  font-size: 12px;
  color: #475569;
  margin-bottom: 4px;
}

.template-mapping-required-hint p {
  margin: 0;
  font-size: 12px;
  color: #64748b;
  line-height: 1.55;
}

.template-mapping-required-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 10px;
  padding: 14px 22px 18px;
  border-top: 1px solid #f1f5f9;
  background: #fafbfc;
}

.btn-cancel {
  padding: 8px 16px;
  font-size: 13px;
  font-weight: 500;
  color: #475569;
  background: #ffffff;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.btn-cancel:hover {
  background: #f8fafc;
  border-color: #94a3b8;
}

.btn-confirm {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 18px;
  font-size: 13px;
  font-weight: 600;
  color: #ffffff;
  background: linear-gradient(135deg, #ea580c 0%, #c2410c 100%);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  box-shadow: 0 1px 3px rgba(234, 88, 12, 0.3);
  transition: all 0.15s ease;
}

.btn-confirm:hover {
  background: linear-gradient(135deg, #f97316 0%, #ea580c 100%);
  box-shadow: 0 2px 6px rgba(234, 88, 12, 0.45);
  transform: translateY(-0.5px);
}

.btn-icon {
  width: 14px;
  height: 14px;
}
</style>
