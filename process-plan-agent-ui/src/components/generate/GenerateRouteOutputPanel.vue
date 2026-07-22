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
        <span class="placeholder-eyebrow">结果工作区</span>
        <h2>等待生成路线</h2>
      </div>
      <p class="placeholder-copy">完成左侧条件输入后，这里将呈现可审查的工艺路线、工序工步树与导出结果。</p>

      <div class="readiness-list">
        <!-- Step 1: Rule Package -->
        <div class="readiness-item" :class="{ ready: hasRulePackage }">
          <span class="readiness-index">
            <svg v-if="hasRulePackage" width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span v-else>01</span>
          </span>
          <div>
            <strong>规则包</strong>
            <span>{{ hasRulePackage ? '已加载最终定稿规则' : '等待第4步导出规则包' }}</span>
          </div>
          <div class="readiness-action-cell">
            <span class="readiness-state">{{ hasRulePackage ? '就绪' : '待处理' }}</span>
            <button v-if="!hasRulePackage" class="readiness-link-btn" type="button" @click="emit('go-finalize')">去导出 →</button>
          </div>
        </div>

        <!-- Step 2: Part Conditions -->
        <div class="readiness-item" :class="{ ready: canGenerate }">
          <span class="readiness-index">
            <svg v-if="canGenerate" width="12" height="12" viewBox="0 0 16 16" fill="none">
              <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
            <span v-else>02</span>
          </span>
          <div>
            <strong>零件条件</strong>
            <span>已填写 {{ filledFieldCount }} / {{ inputFieldCount }} 个输入字段</span>
          </div>
          <div class="readiness-action-cell">
            <span class="readiness-state">{{ canGenerate ? '就绪' : '待补全' }}</span>
            <button v-if="!canGenerate && hasRulePackage" class="readiness-link-btn" type="button" @click="emit('fill-example')">填示例 →</button>
          </div>
        </div>

        <!-- Step 3: Route Generation -->
        <div class="readiness-item" :class="{ ready: false }">
          <span class="readiness-index">03</span>
          <div>
            <strong>生成路线</strong>
            <span>系统将输出工序顺序与下级工步</span>
          </div>
          <div class="readiness-action-cell">
            <span class="readiness-state">等待</span>
          </div>
        </div>
      </div>
    </section>

    <section v-else class="route-output">
      <!-- Result Summary Banner -->
      <div class="result-summary-banner">
        <div class="banner-left">
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"/>
            <path d="M22 4L12 14.01l-3-3"/>
          </svg>
          <span>工艺路线生成成功！包含 <strong>{{ result.steps.length }}</strong> 道工序（主线 <strong>{{ mainStepCount }}</strong> / 条件 <strong>{{ branchStepCount }}</strong>），工步累计 <strong>{{ processStepCount }}</strong> 项。</span>
        </div>
      </div>

      <div class="output-head">
        <div class="output-head-left">
          <span class="output-title">工序工步树</span>
        </div>
        <div class="output-actions">
          <button class="copy-button" type="button" @click="copyJson" :disabled="!result.output_json_text">
            {{ copied ? '已复制 ✓' : '复制 JSON' }}
          </button>
          <button class="export-button" type="button" @click="emit('download')" :disabled="!result.output_json_text">导出 JSON</button>
        </div>
      </div>

      <div class="route-tree">
        <div v-for="(step, index) in result.steps" :key="`${step.name}-${index}`" class="route-node">
          <div class="route-track">
            <div class="route-dot" :class="{ 'route-dot--active': step.op_type === 'MAIN' }"></div>
            <span v-if="index < result.steps.length - 1" class="route-line"></span>
          </div>
          <article class="route-card" :class="{ branch: step.op_type !== 'MAIN' }">
            <div class="route-name-row">
              <div class="route-title-group">
                <span class="route-seq" :class="{ 'route-seq--active': step.op_type === 'MAIN' }">{{ displayStepSequence(step, index) }}</span>
                <h3>{{ step.name }}</h3>
              </div>
              <span class="route-kind" :class="{ branch: step.op_type !== 'MAIN' }">
                {{ step.op_type === 'MAIN' ? '主线工序' : '条件工序' }}
              </span>
            </div>
            <div v-if="normalizedProcessSteps(step).length" class="route-step-area">
              <button
                type="button"
                class="route-step-summary"
                :aria-expanded="isProcessStepsExpanded(step, index)"
                :aria-controls="processStepRegionId(index)"
                :title="isProcessStepsExpanded(step, index) ? '收起工步' : '展开工步'"
                @click="toggleProcessSteps(step, index)"
              >
                <svg
                  class="route-step-caret"
                  :class="{ 'route-step-caret--open': isProcessStepsExpanded(step, index) }"
                  viewBox="0 0 16 16"
                  width="10"
                  height="10"
                  fill="none"
                  aria-hidden="true"
                >
                  <path
                    d="M6 4l4 4-4 4"
                    stroke="currentColor"
                    stroke-width="1.8"
                    stroke-linecap="round"
                    stroke-linejoin="round"
                  />
                </svg>
                <span>工步</span>
                <span class="route-step-count">{{ normalizedProcessSteps(step).length }}</span>
              </button>
              <Transition name="process-steps-expand">
                <div
                  v-if="isProcessStepsExpanded(step, index)"
                  :id="processStepRegionId(index)"
                  class="process-step-chips"
                >
                  <span
                    v-for="(processStep, stepIndex) in normalizedProcessSteps(step)"
                    :key="`${step.name}-${stepIndex}`"
                    class="process-step-chip"
                  >
                    {{ processStep }}
                  </span>
                </div>
              </Transition>
            </div>
            <p v-else class="no-process-steps">该工序暂无下级工步</p>
          </article>
        </div>
      </div>
    </section>
  </main>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
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
  (event: 'go-finalize'): void
  (event: 'fill-example'): void
}>()

const mainStepCount = computed(() => props.result?.steps.filter(step => step.op_type === 'MAIN').length || 0)
const branchStepCount = computed(() => props.result?.steps.filter(step => step.op_type !== 'MAIN').length || 0)
const processStepCount = computed(() => (
  props.result?.steps.reduce((total, step) => total + normalizedProcessSteps(step).length, 0) || 0
))

type GeneratedStep = NonNullable<GenerateRouteResult['steps']>[number]

const collapsedProcessStepKeys = ref<Set<string>>(new Set())
const copied = ref(false)

function processStepKey(step: GeneratedStep, index: number) {
  return `${displayStepSequence(step, index)}:${step.name}:${index}`
}

function processStepRegionId(index: number) {
  return `generated-process-steps-${index}`
}

function isProcessStepsExpanded(step: GeneratedStep, index: number) {
  return !collapsedProcessStepKeys.value.has(processStepKey(step, index))
}

function toggleProcessSteps(step: GeneratedStep, index: number) {
  const key = processStepKey(step, index)
  const next = new Set(collapsedProcessStepKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  collapsedProcessStepKeys.value = next
}

async function copyJson() {
  if (!props.result?.output_json_text) return
  try {
    await navigator.clipboard.writeText(props.result.output_json_text)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch (e) {
    console.error('Failed to copy json', e)
  }
}

watch(() => props.result, () => {
  collapsedProcessStepKeys.value = new Set()
  copied.value = false
})
</script>

<style scoped>
.result-panel {
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --panel: #f8fafc;
  --accent: #4f46e5;
  --accent-soft: #eef2ff;
  height: 100%;
  overflow-y: auto;
  border: 1px solid var(--line);
  border-radius: 14px;
  background-color: #ffffff;
  box-shadow: var(--shadow-sm);
}

.result-panel::-webkit-scrollbar { width: 6px; height: 6px; }
.result-panel::-webkit-scrollbar-track { background: #f8fafc; border-radius: 6px; }
.result-panel::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 6px; }
.result-panel::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

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
  flex-direction: column;
  align-items: center;
  text-align: center;
  gap: 4px;
}

.placeholder-eyebrow {
  display: block;
  margin-bottom: 4px;
  color: var(--accent);
  font-size: 14px;
  font-weight: 600;
  letter-spacing: 0.02em;
}

.route-placeholder h2,
.output-head h2 {
  margin: 0;
  color: var(--ink);
  font-size: 20px;
  line-height: 1.25;
  font-weight: 700;
}

.placeholder-copy {
  margin: 16px 0 20px;
  color: var(--muted);
  font-size: 13px;
  line-height: 1.7;
  text-align: center;
}

.readiness-list {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--line);
}

.readiness-item {
  display: grid;
  grid-template-columns: 24px minmax(0, 1fr) auto;
  align-items: center;
  gap: 12px;
  padding: 13px 0;
  border-bottom: 1px solid var(--line);
}

.readiness-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid #c7d2fe;
  border-radius: 50%;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  font-weight: 700;
  transition: all 0.2s ease;
}

.readiness-item.ready .readiness-index {
  border-color: #22c55e;
  background: #22c55e;
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
  font-size: 13.5px;
  font-weight: 600;
}

.readiness-item div span {
  margin-top: 2px;
  color: var(--muted);
  font-size: 12px;
  line-height: 1.45;
}

.readiness-action-cell {
  display: flex;
  align-items: center;
  gap: 8px;
}

.readiness-state {
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}

.readiness-item.ready .readiness-state {
  color: #16a34a;
}

.readiness-link-btn {
  padding: 2px 8px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #ffffff;
  color: #4f46e5;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.readiness-link-btn:hover {
  background: #eef2ff;
  border-color: #6366f1;
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

.error-panel strong { display: block; font-size: 12px; }
.error-panel p { margin: 2px 0 0; font-size: 12px; line-height: 1.5; }

.route-output { padding: 16px; }

/* Result Summary Banner */
.result-summary-banner {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  margin-bottom: 12px;
  border: 1px solid #bbf7d0;
  border-radius: 8px;
  background: linear-gradient(135deg, #f0fdf4, #ecfdf5);
  color: #166534;
  font-size: 12.5px;
}
.banner-left {
  display: flex;
  align-items: center;
  gap: 8px;
}
.banner-left svg { flex-shrink: 0; color: #16a34a; }

.output-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 14px;
  min-height: 28px;
  padding: 0 4px 12px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 12px;
  box-sizing: content-box;
}

.output-head-left {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 28px;
  gap: 8px;
}

.output-title {
  font-size: 15px;
  font-weight: 700;
  line-height: 28px;
  color: var(--ink);
  white-space: nowrap;
}

.output-stats-inline {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-left: 10px;
  padding-left: 10px;
  border-left: 1px solid var(--line);
  font-size: 12.5px;
  line-height: 28px;
  color: var(--muted);
}

.stat-inline-item strong { color: var(--ink); font-weight: 700; }
.stat-inline-sep { color: #cbd5e1; }

.output-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.copy-button {
  flex-shrink: 0;
  height: 28px;
  padding: 0 11px;
  border: 1px solid #cbd5e1;
  border-radius: 7px;
  background: #ffffff;
  color: #475569;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.copy-button:hover:not(:disabled) {
  background: #f8fafc;
  border-color: #94a3b8;
  color: #0f172a;
}

.export-button {
  flex-shrink: 0;
  height: 28px;
  padding: 0 11px;
  border: 1px solid #c7d2fe;
  border-radius: 7px;
  background: #ffffff;
  color: #4f46e5;
  font: inherit;
  font-size: 12px;
  font-weight: 750;
  line-height: 1;
  cursor: pointer;
  transition: all 0.15s ease;
}
.export-button:hover:not(:disabled) {
  border-color: #6366f1;
  background: var(--accent-soft);
}
.export-button:disabled, .copy-button:disabled {
  cursor: not-allowed;
  opacity: 0.45;
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
  flex-shrink: 0;
  width: 14px;
  padding-top: 14px;
}

.route-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #cbd5e1;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 1px #cbd5e1;
  flex-shrink: 0;
  transition: all 0.15s ease;
  z-index: 1;
}

.route-dot--active {
  background: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 0 0 3px rgba(99, 102, 241, 0.25);
}

.route-line {
  flex: 1;
  width: 1px;
  min-height: 20px;
  background: #cbd5e1;
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
  background: #faf8ff;
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

.route-seq {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 22px;
  height: 16px;
  padding: 0 5px;
  border-radius: 3px;
  background: #f1f5f9;
  color: #475569;
  font-weight: 700;
  font-size: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
  border: 1px solid #e2e8f0;
  transition: all 0.15s ease;
}

.route-seq--active {
  background: #6366f1;
  color: #ffffff;
  border-color: #6366f1;
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
  display: inline-flex;
  align-items: center;
  gap: 6px;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
  font-size: 11.5px;
  font-weight: 500;
  line-height: 1.4;
  text-align: left;
  transition: color 0.15s ease;
}

.route-step-summary:hover {
  color: var(--accent);
}

.route-step-summary:focus-visible {
  border-radius: 3px;
  outline: 2px solid rgba(79, 70, 229, 0.35);
  outline-offset: 3px;
}

.route-step-caret {
  flex-shrink: 0;
  color: currentColor;
  transition: transform 0.2s ease;
}

.route-step-caret--open {
  transform: rotate(90deg);
}

.route-step-count {
  background: #f1f5f9;
  color: #475569;
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  border: 1px solid #e2e8f0;
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.route-step-summary:hover .route-step-count {
  border-color: rgba(79, 70, 229, 0.18);
  background: rgba(79, 70, 229, 0.08);
  color: var(--accent);
}

.process-step-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
}

.process-step-chip {
  display: inline-flex;
  align-items: center;
  min-height: 25px;
  padding: 3px 8px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: #f8faf9;
  color: #334155;
  font-size: 11px;
  font-weight: 600;
  line-height: 1.35;
}

.process-steps-expand-enter-active,
.process-steps-expand-leave-active {
  overflow: hidden;
  max-height: 320px;
  transition: opacity 0.2s ease, max-height 0.25s ease;
}

.process-steps-expand-enter-from,
.process-steps-expand-leave-to {
  opacity: 0;
  max-height: 0;
}

.no-process-steps {
  margin-bottom: 0;
  color: var(--muted);
  font-size: 11px;
}

@keyframes pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-4px); }
}

@media (max-width: 700px) {
  .route-placeholder { padding: 24px 16px; }
  .route-output { padding: 16px; }
  .output-head { align-items: center; flex-wrap: wrap; }
  .route-name-row { align-items: flex-start; flex-direction: column; }
  .route-kind { align-self: flex-start; }
}
</style>
