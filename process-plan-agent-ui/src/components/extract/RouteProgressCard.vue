<template>
  <div class="card route-progress-card">
    <div class="route-progress-content">
      <div class="route-progress-body">
        <div class="route-progress-title-row">
          <div class="route-progress-spinner"></div>
          <h3>{{ title }}</h3>
          <span v-if="message" class="route-progress-message">{{ message }}</span>
        </div>
        <div class="route-progress-steps">
          <div
            v-for="(step, idx) in steps"
            :key="step.key"
            class="route-progress-step"
            :class="`is-${step.status}`"
          >
            <div class="route-progress-dot"></div>
            <span class="route-progress-label">{{ step.title }}</span>
            <span v-if="idx < steps.length - 1" class="route-progress-sep"></span>
          </div>
        </div>
      </div>
    </div>
    <div v-if="showProgressBar" class="route-progress-top">
      <div
        class="route-progress-fill"
        :class="{ 'route-progress-fill-indeterminate': indeterminate }"
        :style="indeterminate ? undefined : { width: `${progress}%` }"
      ></div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

type ProgressStep = {
  key: string
  title: string
  status: string
}

const props = withDefaults(defineProps<{
  title: string
  message?: string
  steps: ProgressStep[]
  progress?: number
  indeterminate?: boolean
}>(), {
  message: '',
  progress: 0,
  indeterminate: false,
})

const showProgressBar = computed(() => props.indeterminate || props.progress > 0)
</script>

<style scoped>
.route-progress-card {
  margin-bottom: 24px;
  overflow: hidden;
  position: relative;
  border: 1px solid #e0e7ff;
  border-radius: 16px;
  background: linear-gradient(180deg, #fcfdff 0%, #ffffff 100%);
  box-shadow: 0 8px 32px -8px rgba(79, 70, 229, 0.08);
}
.route-progress-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 16px 20px;
}
.route-progress-body {
  display: flex;
  flex: 1;
  flex-direction: column;
  gap: 10px;
  min-width: 0;
  padding: 6px 4px;
}
.route-progress-title-row {
  display: flex;
  align-items: center;
  gap: 12px;
  flex-wrap: wrap;
}
.route-progress-title-row h3 {
  margin: 0;
  font-size: 15px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: 0.01em;
}
.route-progress-message {
  margin-left: auto;
  padding: 4px 10px;
  border-radius: 8px;
  background: #f1f5f9;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 13px;
}
.route-progress-spinner {
  width: 18px;
  height: 18px;
  border: 2px solid #e2e8f0;
  border-top-color: #4f46e5;
  border-radius: 50%;
  animation: route-progress-spin 0.8s linear infinite;
}
.route-progress-steps {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-top: 6px;
}
.route-progress-step {
  display: flex;
  align-items: center;
  gap: 8px;
}
.route-progress-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #e2e8f0;
  transition: all 0.2s ease;
}
.route-progress-label {
  color: #94a3b8;
  font-size: 12px;
  font-weight: 600;
  transition: all 0.2s ease;
}
.route-progress-sep {
  width: 32px;
  height: 1px;
  background: #e2e8f0;
}
.route-progress-step.is-active .route-progress-dot {
  background: var(--accent, #6366f1);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
.route-progress-step.is-active .route-progress-label {
  color: var(--accent, #6366f1);
  font-weight: 700;
}
.route-progress-step.is-done .route-progress-dot {
  background: #10b981;
}
.route-progress-step.is-done .route-progress-label {
  color: #059669;
}
.route-progress-top {
  position: absolute;
  top: 0;
  right: 0;
  left: 0;
  height: 3px;
  overflow: hidden;
  background: #eef2ff;
}
.route-progress-fill {
  height: 100%;
  border-radius: 0 3px 3px 0;
  background: linear-gradient(90deg, #818cf8, #4f46e5);
  box-shadow: 0 0 8px rgba(99, 102, 241, 0.6);
  transition: width 0.4s ease;
}
.route-progress-fill-indeterminate {
  width: 38%;
  animation: route-progress-indeterminate 1.4s ease-in-out infinite;
}
@keyframes route-progress-spin {
  to { transform: rotate(360deg); }
}
@keyframes route-progress-indeterminate {
  0% { transform: translateX(-110%); }
  100% { transform: translateX(290%); }
}
</style>
