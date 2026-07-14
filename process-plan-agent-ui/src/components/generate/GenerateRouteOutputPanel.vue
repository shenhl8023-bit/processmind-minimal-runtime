<template>
  <main class="result-panel" :class="{ 'has-result': result }">
    <section v-if="error" class="error-panel" role="alert">
      <span class="error-mark">!</span>
      <div>
        <strong>路线生成未完成</strong>
        <p>{{ error }}</p>
      </div>
    </section>

    <section v-if="generating" class="route-placeholder generating-state" aria-live="polite">
      <div class="generation-loader"><span></span><span></span><span></span></div>
      <span class="placeholder-eyebrow">正在推演</span>
      <h2>正在组合工序与工步</h2>
      <p>系统正在根据当前参数匹配已定稿规则，请保持此页面打开。</p>
    </section>

    <section v-else-if="!result" class="route-placeholder">
      <div class="placeholder-heading">
        <div class="panel-index">02</div>
        <div>
          <span class="placeholder-eyebrow">结果工作区</span>
          <h2>等待生成路线</h2>
        </div>
      </div>
      <p class="placeholder-copy">完成左侧条件输入后，这里将呈现可审查的工艺路线、工序工步树与导出结果。</p>

      <div class="readiness-list">
        <div class="readiness-item" :class="{ ready: hasRulePackage }">
          <span class="readiness-index">01</span>
          <div>
            <strong>规则包</strong>
            <span>{{ hasRulePackage ? '已加载最终定稿规则' : '等待第4步导出规则包' }}</span>
          </div>
          <span class="readiness-state">{{ hasRulePackage ? '就绪' : '待处理' }}</span>
        </div>
        <div class="readiness-item" :class="{ ready: canGenerate }">
          <span class="readiness-index">02</span>
          <div>
            <strong>零件条件</strong>
            <span>已填写 {{ filledFieldCount }} / {{ inputFieldCount }} 个输入字段</span>
          </div>
          <span class="readiness-state">{{ canGenerate ? '就绪' : '待补全' }}</span>
        </div>
        <div class="readiness-item">
          <span class="readiness-index">03</span>
          <div>
            <strong>生成路线</strong>
            <span>系统将输出工序顺序与下级工步</span>
          </div>
          <span class="readiness-state">等待</span>
        </div>
      </div>
    </section>

    <section v-else class="route-output">
      <div class="output-head">
        <div>
          <span class="placeholder-eyebrow">生成结果</span>
          <h2>工序工步树</h2>
          <p>{{ projectName || '当前任务' }} · 已生成 {{ result.steps.length }} 道工序</p>
        </div>
        <button class="export-button" type="button" @click="emit('download')" :disabled="!result.output_json_text">导出 JSON</button>
      </div>

      <p v-if="result.summary" class="route-summary">{{ result.summary }}</p>

      <div class="route-stats">
        <div>
          <span>工序</span>
          <strong>{{ result.steps.length }}</strong>
        </div>
        <div>
          <span>主线工序</span>
          <strong>{{ mainStepCount }}</strong>
        </div>
        <div>
          <span>条件工序</span>
          <strong>{{ branchStepCount }}</strong>
        </div>
        <div>
          <span>工步</span>
          <strong>{{ processStepCount }}</strong>
        </div>
      </div>

      <div class="route-tree">
        <div v-for="(step, index) in result.steps" :key="`${step.name}-${index}`" class="route-node">
          <div class="route-track">
            <span class="route-dot" :class="{ branch: step.op_type !== 'MAIN' }">{{ displayStepSequence(step, index) }}</span>
            <span v-if="index < result.steps.length - 1" class="route-line"></span>
          </div>
          <article class="route-card" :class="{ branch: step.op_type !== 'MAIN' }">
            <div class="route-name-row">
              <div class="route-title-group">
                <span class="route-seq-inline">{{ displayStepSequence(step, index) }}</span>
                <h3>{{ step.name }}</h3>
              </div>
              <span class="route-kind" :class="{ branch: step.op_type !== 'MAIN' }">{{ step.op_type === 'MAIN' ? '主线工序' : '条件工序' }}</span>
            </div>
            <div v-if="normalizedProcessSteps(step).length" class="route-step-area">
              <div class="route-step-summary">
                <span>工步明细</span>
                <strong>{{ normalizedProcessSteps(step).length }}</strong>
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
          </article>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { GenerateRouteResult } from '@/api'
import {
  displayStepSequence,
  normalizedProcessSteps,
} from '@/utils/generateRouteOutput'

const props = defineProps<{
  error: string
  result: GenerateRouteResult | null
  projectName: string
  inputFieldCount: number
  filledFieldCount: number
  hasRulePackage: boolean
  canGenerate: boolean
  generating: boolean
}>()

const emit = defineEmits<{
  (event: 'download'): void
}>()

const mainStepCount = computed(() => props.result?.steps.filter(step => step.op_type === 'MAIN').length || 0)
const branchStepCount = computed(() => props.result?.steps.filter(step => step.op_type !== 'MAIN').length || 0)
const processStepCount = computed(() => (
  props.result?.steps.reduce((total, step) => total + normalizedProcessSteps(step).length, 0) || 0
))
</script>

<style scoped>
.result-panel {
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --panel: #f8fafc;
  --accent: #4f46e5;
  --accent-soft: #eef2ff;
  min-height: 610px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background-color: #ffffff;
  box-shadow: var(--shadow-sm);
  overflow: hidden;
}

.route-placeholder {
  min-height: 604px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  max-width: 620px;
  margin: 0 auto;
  padding: 42px 32px;
}

.placeholder-heading {
  display: flex;
  align-items: center;
  gap: 12px;
}

.panel-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 8px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: #ffffff;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 11px;
  font-weight: 800;
}

.placeholder-eyebrow {
  display: block;
  margin-bottom: 3px;
  color: var(--accent);
  font-size: 11px;
  font-weight: 800;
}

.route-placeholder h2,
.output-head h2 {
  margin: 0;
  color: var(--ink);
  font-size: 20px;
  line-height: 1.25;
  font-weight: 750;
}

.placeholder-copy {
  margin: 16px 0 20px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
}

.readiness-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--line);
}

.readiness-item {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr) auto;
  align-items: center;
  gap: 10px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}

.readiness-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 25px;
  height: 25px;
  border: 1px solid #c7d2fe;
  border-radius: 50%;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  font-weight: 800;
}

.readiness-item.ready .readiness-index {
  border-color: #6366f1;
  background: #6366f1;
  color: #ffffff;
}

.readiness-item div {
  min-width: 0;
}

.readiness-item strong,
.readiness-item span:not(.readiness-index):not(.readiness-state) {
  display: block;
}

.readiness-item strong {
  color: var(--ink);
  font-size: 12px;
  font-weight: 750;
}

.readiness-item div span {
  margin-top: 2px;
  color: var(--muted);
  font-size: 11px;
  line-height: 1.45;
}

.readiness-state {
  color: #84918f;
  font-size: 10px;
  font-weight: 800;
}

.readiness-item.ready .readiness-state {
  color: var(--accent);
}

.generating-state {
  align-items: center;
  text-align: center;
}

.generation-loader {
  display: inline-flex;
  gap: 5px;
  margin-bottom: 15px;
}

.generation-loader span {
  width: 8px;
  height: 8px;
  background: var(--accent);
  animation: pulse 1s ease-in-out infinite;
}

.generation-loader span:nth-child(2) { animation-delay: 0.15s; }
.generation-loader span:nth-child(3) { animation-delay: 0.3s; }

.generating-state p {
  max-width: 300px;
  margin: 8px 0 0;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.65;
}

.error-panel {
  display: grid;
  grid-template-columns: 28px minmax(0, 1fr);
  gap: 10px;
  margin: 14px 14px -2px;
  padding: 11px 12px;
  border: 1px solid #f3c6c6;
  border-radius: 8px;
  background: #fff4f4;
  color: #9f1d1d;
}

.error-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: #c43b3b;
  color: #ffffff;
  font-family: Georgia, serif;
  font-weight: 800;
}

.error-panel strong {
  display: block;
  font-size: 12px;
}

.error-panel p {
  margin: 2px 0 0;
  font-size: 12px;
  line-height: 1.5;
}

.route-output {
  padding: 20px;
}

.output-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 14px;
}

.output-head p {
  margin: 5px 0 0;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.5;
}

.export-button {
  flex-shrink: 0;
  height: 34px;
  padding: 0 11px;
  border: 1px solid #c7d2fe;
  border-radius: 7px;
  background: #ffffff;
  color: #4f46e5;
  font: inherit;
  font-size: 12px;
  font-weight: 750;
  cursor: pointer;
}

.export-button:hover:not(:disabled) {
  border-color: #6366f1;
  background: var(--accent-soft);
}

.export-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

.route-summary {
  margin: 16px 0 0;
  padding: 10px 12px;
  border-left: 3px solid #6366f1;
  border-radius: 6px;
  background: var(--panel);
  color: #40504f;
  font-size: 12px;
  line-height: 1.65;
}

.route-stats {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 1px;
  margin: 16px 0 22px;
  background: var(--line);
  border: 1px solid var(--line);
  border-radius: 8px;
  overflow: hidden;
}

.route-stats div {
  padding: 10px 12px;
  background: #ffffff;
}

.route-stats span,
.route-stats strong {
  display: block;
}

.route-stats span {
  color: var(--muted);
  font-size: 10px;
  font-weight: 750;
}

.route-stats strong {
  margin-top: 3px;
  color: var(--ink);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 18px;
}

.route-tree {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.route-node {
  display: grid;
  grid-template-columns: 40px minmax(0, 1fr);
  gap: 9px;
}

.route-track {
  display: flex;
  flex-direction: column;
  align-items: center;
}

.route-dot {
  z-index: 1;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  border-radius: 50%;
  background: #6366f1;
  color: #ffffff;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  font-weight: 800;
}

.route-dot.branch {
  background: #8b5cf6;
}

.route-line {
  flex: 1;
  width: 1px;
  min-height: 20px;
  background: #bdcac7;
}

.route-card {
  margin-bottom: 10px;
  padding: 12px 13px;
  border: 1px solid var(--line);
  border-left: 3px solid #6366f1;
  border-radius: 10px;
  background: #ffffff;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.route-card.branch {
  border-left-color: #8b5cf6;
}

.route-card:hover {
  border-color: #c7d2fe;
  box-shadow: 0 7px 18px rgba(31, 45, 51, 0.06);
}

.route-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
}

.route-title-group {
  display: flex;
  align-items: center;
  min-width: 0;
  gap: 8px;
}

.route-seq-inline {
  display: inline-flex;
  flex-shrink: 0;
  align-items: center;
  justify-content: center;
  min-width: 38px;
  height: 22px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--panel);
  color: #40504f;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  font-weight: 800;
}

.route-name-row h3 {
  overflow: hidden;
  margin: 0;
  color: var(--ink);
  font-size: 14px;
  font-weight: 750;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.route-kind {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 7px;
  border-radius: 999px;
  background: var(--accent-soft);
  color: #4338ca;
  font-size: 10px;
  font-weight: 800;
}

.route-kind.branch {
  background: #f3e8ff;
  color: #7e22ce;
}

.route-step-area,
.no-process-steps {
  margin-top: 10px;
  padding-top: 9px;
  border-top: 1px dashed #d5dfdc;
}

.route-step-summary {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
  color: var(--muted);
  font-size: 11px;
  font-weight: 750;
}

.route-step-summary strong {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 19px;
  height: 19px;
  border-radius: 4px;
  background: var(--panel);
  color: #40504f;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
}

.process-step-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.process-step-chip {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 3px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: #f8faf9;
  color: #40504f;
  font-size: 11px;
  font-weight: 650;
  line-height: 1.35;
}

.no-process-steps {
  margin-bottom: 0;
  color: #84918f;
  font-size: 11px;
}

@keyframes pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-4px); }
}

@media (max-width: 700px) {
  .route-placeholder,
  .route-output {
    padding: 24px 16px;
  }

  .route-stats {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }

  .output-head,
  .route-name-row {
    align-items: flex-start;
    flex-direction: column;
  }

  .route-kind {
    align-self: flex-start;
  }
}
</style>
