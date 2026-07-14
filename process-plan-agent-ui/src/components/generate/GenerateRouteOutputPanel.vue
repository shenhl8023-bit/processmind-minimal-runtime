<template>
  <main class="result-panel">
    <section v-if="error" class="error-panel">
      {{ error }}
    </section>

    <section v-if="!result" class="route-placeholder">
      <div class="placeholder-mark">05</div>
      <h2>等待生成</h2>
      <p>左侧填写参数后，右侧会显示最终工艺路线。</p>
    </section>

    <section v-else class="route-output">
      <div class="output-head">
        <div>
          <span class="panel-kicker">输出结果</span>
          <h2>工序工步树</h2>
          <p>共生成 {{ result.steps.length }} 道工序，按定稿规则包带出工步。</p>
        </div>
        <button class="btn btn-outline" type="button" @click="emit('download')" :disabled="!result.output_json_text">导出 JSON</button>
      </div>

      <div class="route-tree">
        <div v-for="(step, index) in result.steps" :key="`${step.name}-${index}`" class="route-node">
          <div class="route-track">
            <span class="route-dot" :class="{ branch: step.op_type !== 'MAIN' }">{{ displayStepSequence(step, index) }}</span>
            <span v-if="index < result.steps.length - 1" class="route-line"></span>
          </div>
          <div class="route-card">
            <div class="route-name-row">
              <div class="route-title-group">
                <span class="route-seq-inline">{{ displayStepSequence(step, index) }}</span>
                <h3>{{ step.name }}</h3>
              </div>
              <span class="route-kind" :class="{ branch: step.op_type !== 'MAIN' }">{{ step.op_type === 'MAIN' ? '主线' : '条件' }}</span>
            </div>
            <div v-if="normalizedProcessSteps(step).length" class="route-step-area">
              <div class="route-step-summary">
                <span class="route-step-label">工步</span>
                <span class="route-step-count">{{ normalizedProcessSteps(step).length }}</span>
              </div>
              <div class="process-step-chips">
                <span
                  v-for="(processStep, stepIndex) in normalizedProcessSteps(step)"
                  :key="`${step.name}-${stepIndex}`"
                  class="process-step-chip"
                >
                  {{ processStep }}
                </span>
              </div>
            </div>
            <p v-else class="no-process-steps">该工序暂无下级工步</p>
          </div>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import type { GenerateRouteResult } from '@/api'
import {
  displayStepSequence,
  normalizedProcessSteps,
} from '@/utils/generateRouteOutput'

defineProps<{
  error: string
  result: GenerateRouteResult | null
}>()

const emit = defineEmits<{
  (event: 'download'): void
}>()
</script>

<style scoped>
.result-panel {
  min-height: 560px;
  padding: 14px;
  background: #ffffff;
  border: 1px solid #e4e7ec;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.error-panel {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 12px;
  border-radius: 6px;
  margin-bottom: 12px;
  font-size: 12px;
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}

.route-placeholder {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 28px;
}

.placeholder-mark {
  height: 34px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  color: #667085;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 12px;
}

.panel-kicker {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 8px;
  margin-bottom: 8px;
  border-radius: 999px;
  background: #eff6ff;
  color: #1d4ed8;
  font-size: 11px;
  font-weight: 800;
}

.route-placeholder h2,
.output-head h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0;
}

.route-placeholder p,
.output-head p {
  margin: 4px 0 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.55;
}

.output-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 12px;
}

.route-tree {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.route-node {
  display: grid;
  grid-template-columns: 36px minmax(0, 1fr);
  gap: 8px;
}

.route-track {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.route-dot {
  width: 22px;
  height: 22px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #101828;
  color: #ffffff;
  font-size: 0;
  font-weight: 800;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  box-shadow: 0 0 0 4px #ffffff;
}

.route-dot.branch {
  background: #4f46e5;
}

.route-line {
  flex: 1;
  width: 2px;
  min-height: 20px;
  background: #e4e7ec;
}

.route-card {
  border: 1px solid #e4e7ec;
  border-radius: 7px;
  padding: 10px 12px 9px;
  margin-bottom: 8px;
  background: #ffffff;
  transition: border-color 0.16s ease, box-shadow 0.16s ease, background 0.16s ease;
}

.route-card:hover {
  border-color: #c7d2fe;
  box-shadow: 0 6px 18px rgba(15, 23, 42, 0.05);
}

.route-name-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
}

.route-title-group {
  min-width: 0;
  display: inline-flex;
  align-items: center;
  gap: 8px;
}

.route-seq-inline {
  flex-shrink: 0;
  min-width: 34px;
  height: 20px;
  padding: 0 7px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
  font-weight: 800;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
}

.route-name-row h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  letter-spacing: 0;
  color: #1e293b;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.route-kind {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 5px;
  background: #ecfdf3;
  color: #027a48;
  font-size: 10px;
  font-weight: 800;
}

.route-kind.branch {
  background: #eef2ff;
  color: #3730a3;
}

.route-step-area {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
}

.route-step-summary {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  margin-bottom: 7px;
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.route-step-count {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 18px;
  height: 18px;
  padding: 0 6px;
  border-radius: 999px;
  background: #e2e8f0;
  color: #475569;
  font-size: 10px;
  font-weight: 800;
}

.process-step-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 5px;
}

.process-step-chip {
  display: inline-flex;
  align-items: center;
  min-height: 24px;
  padding: 3px 7px;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  background: #f8fafc;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.35;
}

.no-process-steps {
  margin: 7px 0 0;
  padding-top: 7px;
  border-top: 1px dashed #e2e8f0;
  color: #98a2b3;
  font-size: 11px;
}

@media (max-width: 900px) {
  .output-head {
    flex-direction: column;
  }
}
</style>
