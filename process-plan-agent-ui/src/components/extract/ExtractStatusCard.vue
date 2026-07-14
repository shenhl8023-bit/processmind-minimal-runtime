<template>
  <div class="card action-card">
    <div class="action-content">
      <div class="action-icon">
        <svg v-if="variant === 'idle'" width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="m12 3-1.912 5.813a2 2 0 0 1-1.275 1.275L3 12l5.813 1.912a2 2 0 0 1 1.275 1.275L12 21l1.912-5.813a2 2 0 0 1 1.275-1.275L21 12l-5.813-1.912a2 2 0 0 1-1.275-1.275L12 3Z"/>
          <path d="M5 3v4"/>
          <path d="M19 17v4"/>
          <path d="M3 5h4"/>
          <path d="M17 19h4"/>
        </svg>
        <svg v-else width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
          <line x1="12" y1="9" x2="12" y2="13"/>
          <line x1="12" y1="17" x2="12.01" y2="17"/>
        </svg>
      </div>
      <div>
        <h3>{{ title }}</h3>
        <p>{{ message }}</p>
      </div>
      <button :class="buttonClass" @click="$emit('action')">{{ actionLabel }}</button>
    </div>

    <div v-if="variant === 'error' && harness" class="harness-error-panel">
      <div class="harness-error-head">
        <span class="harness-error-kicker">Harness 校验</span>
        <span class="harness-error-stage">{{ harness.stage || '未知阶段' }}</span>
      </div>
      <div class="harness-issue-list">
        <div
          v-for="issue in harness.errors || []"
          :key="`${issue.code}-${issue.target || issue.message}`"
          class="harness-issue"
        >
          <div class="harness-issue-code">{{ issue.code }}</div>
          <div class="harness-issue-body">
            <div class="harness-issue-message">{{ issue.message }}</div>
            <div v-if="issue.target || issue.suggested_action" class="harness-issue-meta">
              <span v-if="issue.target">对象：{{ issue.target }}</span>
              <span v-if="issue.suggested_action">建议：{{ issue.suggested_action }}</span>
            </div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type HarnessIssue = {
  code: string
  message: string
  target?: string
  suggested_action?: string
}

type HarnessPayload = {
  stage?: string
  errors?: HarnessIssue[]
}

const props = defineProps<{
  variant: 'idle' | 'error'
  message: string
  harness?: HarnessPayload | null
}>()

defineEmits<{
  action: []
}>()

const title = computed(() => props.variant === 'idle' ? '准备就绪' : '分析出错')
const actionLabel = computed(() => props.variant === 'idle' ? '开始 AI 智能提炼' : '重试')
const buttonClass = computed(() => props.variant === 'idle' ? 'btn btn-primary' : 'btn btn-outline')
</script>

<style scoped>
.action-card {
  margin-bottom: 20px;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.03);
  background: #ffffff;
}

.action-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
}

.action-content > div:not(.action-icon) {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  justify-content: center;
}

.action-content h3 {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  margin-bottom: 4px;
  letter-spacing: -0.01em;
  line-height: 1.4;
}

.action-content p {
  font-size: 13px;
  color: #64748b;
  line-height: 1.5;
  margin: 0;
}

.action-icon {
  width: 36px;
  height: 36px;
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  background: #eef2ff;
  color: #4f46e5;
  border-radius: 10px;
  box-shadow: inset 0 0 0 1px rgba(99, 102, 241, 0.15);
}

.action-icon svg {
  width: 20px;
  height: 20px;
}

.harness-error-panel {
  margin-top: 16px;
  border-top: 1px solid #fee2e2;
  padding: 16px 20px 0;
}

.harness-error-head {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 10px;
}

.harness-error-kicker {
  font-size: 12px;
  font-weight: 800;
  color: #b91c1c;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.harness-error-stage {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  color: #991b1b;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 6px;
  padding: 4px 8px;
}

.harness-issue-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  padding-bottom: 16px;
}

.harness-issue {
  display: grid;
  grid-template-columns: minmax(120px, 220px) minmax(0, 1fr);
  gap: 12px;
  border: 1px solid #fecaca;
  border-radius: 10px;
  background: #fffafa;
  padding: 12px;
}

.harness-issue-code {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 12px;
  font-weight: 800;
  color: #b91c1c;
  word-break: break-word;
}

.harness-issue-body {
  min-width: 0;
}

.harness-issue-message {
  font-size: 13px;
  font-weight: 700;
  color: #7f1d1d;
  line-height: 1.6;
}

.harness-issue-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px 14px;
  margin-top: 4px;
  font-size: 12px;
  color: #991b1b;
  line-height: 1.6;
}

@media (max-width: 900px) {
  .action-content {
    flex-direction: column;
    align-items: stretch;
  }
}
</style>
