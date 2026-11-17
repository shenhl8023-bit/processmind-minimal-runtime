<template>
  <main class="result-panel" :class="{ 'has-result': result }">
    <section v-if="error" class="error-panel" role="alert">
      <span class="error-mark">!</span>
      <div>
        <strong>规则包验证或路线生成未完成</strong>
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
            <span>{{ hasRulePackage ? '已加载当前可验证规则' : '等待第4步保存规则定稿' }}</span>
          </div>
          <div class="readiness-action-cell">
            <span class="readiness-state">{{ hasRulePackage ? '就绪' : '待处理' }}</span>
            <button v-if="!hasRulePackage" class="readiness-link-btn" type="button" @click="emit('go-finalize')">去定稿 →</button>
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
      <div class="output-head">
        <div class="output-head-left">
          <span class="output-title">工序工步树</span>
          <span class="output-stats-inline">
            <span class="stat-inline-item">共 <strong>{{ result.steps.length }}</strong> 工序</span>
            <span class="stat-inline-sep">·</span>
            <span class="stat-inline-item">主线 <strong>{{ mainStepCount }}</strong> / 条件 <strong>{{ branchStepCount }}</strong></span>
            <span class="stat-inline-sep">·</span>
            <span class="stat-inline-item">工步 <strong>{{ processStepCount }}</strong> 项</span>
          </span>
        </div>
      </div>

      <div class="route-tree">
        <div v-for="(step, index) in result.steps" :key="step.process_id || `${step.name}-${index}`" class="route-node">
          <div class="route-track">
            <div class="route-dot" :class="{ 'route-dot--active': step.op_type === 'MAIN' }"></div>
            <span v-if="index < result.steps.length - 1" class="route-line"></span>
          </div>
          <article class="route-card" :class="{ branch: step.op_type !== 'MAIN' }">
            <div class="route-name-row">
              <div class="route-title-group">
                <span class="route-seq" :class="{ 'route-seq--active': step.op_type === 'MAIN' }">{{ displayStepSequence(step, index) }}</span>
                <h3 :title="step.name">{{ step.name }}</h3>
              </div>
              <span class="route-kind" :class="{ branch: step.op_type !== 'MAIN' }">
                {{ step.op_type === 'MAIN' ? '主线工序' : '条件工序' }}
              </span>
              <button
                v-if="normalizedProcessSteps(step).length"
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
            </div>
            <Transition name="process-steps-expand">
              <div
                v-if="normalizedProcessSteps(step).length && isProcessStepsExpanded(step, index)"
                :id="processStepRegionId(index)"
                class="route-step-area process-step-chips"
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
  isStale?: boolean
  currentPackageVersion?: number | null
}>()

const emit = defineEmits<{
  (event: 'go-finalize'): void
  (event: 'fill-example'): void
}>()

const mainStepCount = computed(() => props.result?.steps.filter(step => step.op_type === 'MAIN').length || 0)
const branchStepCount = computed(() => props.result?.steps.filter(step => step.op_type !== 'MAIN').length || 0)
const processStepCount = computed(() => (
  props.result?.steps.reduce((total, step) => total + normalizedProcessSteps(step).length, 0) || 0
))

type GeneratedStep = NonNullable<GenerateRouteResult['steps']>[number]

const expandedProcessStepKeys = ref<Set<string>>(new Set())

function processStepKey(step: GeneratedStep, index: number) {
  return `${displayStepSequence(step, index)}:${step.name}:${index}`
}

function processStepRegionId(index: number) {
  return `generated-process-steps-${index}`
}

function isProcessStepsExpanded(step: GeneratedStep, index: number) {
  return expandedProcessStepKeys.value.has(processStepKey(step, index))
}

function toggleProcessSteps(step: GeneratedStep, index: number) {
  const key = processStepKey(step, index)
  const next = new Set(expandedProcessStepKeys.value)
  if (next.has(key)) next.delete(key)
  else next.add(key)
  expandedProcessStepKeys.value = next
}

watch(() => props.result, () => {
  expandedProcessStepKeys.value = new Set()
})
</script>

<style scoped>
.result-panel {
  --ink: var(--pm-text);
  --muted: var(--pm-text-muted);
  --line: var(--pm-border);
  --panel: var(--pm-surface-subtle);
  --accent: var(--pm-primary);
  --accent-soft: var(--pm-primary-soft);
  height: 100%;
  overflow-y: auto;
  border: 1px solid var(--line);
  border-radius: var(--pm-radius-card);
  background-color: var(--pm-surface);
  box-shadow: var(--shadow-sm);
}

.result-panel::-webkit-scrollbar { width: 6px; height: 6px; }
.result-panel::-webkit-scrollbar-track { background: var(--pm-surface-subtle); border-radius: 6px; }
.result-panel::-webkit-scrollbar-thumb { background: var(--pm-border-strong); border-radius: 6px; }
.result-panel::-webkit-scrollbar-thumb:hover { background: var(--pm-text-muted); }

.route-placeholder {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  justify-content: center;
  max-width: 620px;
  margin: 0 auto;
  padding: 24px;
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
  font-size: 16px;
  line-height: 24px;
  font-weight: 600;
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
  padding: 10px 0;
  border-bottom: 1px solid var(--line);
}

.readiness-index {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid var(--pm-primary-border);
  border-radius: 50%;
  color: var(--muted);
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 12px;
  font-weight: 700;
  transition: all 0.2s ease;
}

.readiness-item.ready .readiness-index {
  border-color: var(--pm-success);
  background: var(--pm-success);
  color: var(--pm-surface);
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
  font-size: 13px;
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
  color: var(--pm-success);
}

.readiness-link-btn {
  padding: 2px 8px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 5px;
  background: var(--pm-surface);
  color: var(--pm-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.readiness-link-btn:hover {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary);
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
  border: 1px solid var(--pm-danger-border);
  border-radius: 8px;
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
}

.error-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border-radius: 50%;
  background: var(--pm-danger);
  color: var(--pm-surface);
  font-family: Georgia, serif;
  font-weight: 800;
}

.error-panel strong { display: block; font-size: 12px; }
.error-panel p { margin: 2px 0 0; font-size: 12px; line-height: 1.5; }

.route-output { min-width: 0; }

.output-head {
  position: sticky;
  top: 0;
  z-index: 2;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 2px 8px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--line);
  background: var(--pm-surface-subtle);
}

.output-head-left {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.output-title {
  font-size: 13px;
  line-height: 20px;
  font-weight: 700;
  color: var(--ink);
  white-space: nowrap;
  flex-shrink: 0;
}

.output-stats-inline {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px 6px;
  margin-left: 6px;
  padding-left: 8px;
  border-left: 1px solid var(--pm-border);
  font-size: 12px;
  color: var(--muted);
  min-width: 0;
}

.stat-inline-item strong {
  color: var(--ink);
  font-weight: 700;
}

.stat-inline-sep {
  color: var(--pm-border-strong);
}

.output-stale-banner {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  margin: 10px 0 14px;
  background: var(--pm-warning-soft);
  border: 1px solid var(--pm-warning-border);
  border-left: 4px solid var(--pm-warning);
  border-radius: 8px;
  font-size: 13px;
  color: var(--pm-warning);
}

.stale-dot {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--pm-warning);
  color: var(--pm-surface);
  font-weight: 700;
  font-size: 12px;
  flex-shrink: 0;
}

.stale-text {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.stale-text strong {
  color: var(--pm-warning);
  font-size: 13px;
}

.stale-text span {
  color: var(--pm-warning);
  font-size: 12px;
}

.route-tree {
  display: flex;
  flex-direction: column;
  gap: 0;
  padding: 8px 12px 12px;
}

.route-node {
  display: grid;
  grid-template-columns: 16px minmax(0, 1fr);
  gap: 8px;
}

.route-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 16px;
  padding-top: 12px;
}

.route-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: var(--pm-border-strong);
  border: 2px solid var(--pm-surface);
  box-shadow: 0 0 0 1px var(--pm-border-strong);
  flex-shrink: 0;
  transition: all 0.15s ease;
  z-index: 1;
}

.route-dot--active {
  background: var(--pm-primary);
  box-shadow: 0 0 0 1px var(--pm-primary), 0 0 0 3px rgba(36, 95, 168, 0.25);
}

.route-line {
  flex: 1;
  width: 1px;
  min-height: 16px;
  background: var(--pm-border-strong);
}

.route-card {
  min-width: 0;
  margin-bottom: 2px;
  padding: 5px 10px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: var(--pm-surface);
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.route-card.branch {
  border-left-color: var(--pm-primary);
  background: var(--pm-primary-soft);
}

.route-card:hover {
  border-color: var(--pm-primary-border);
  box-shadow: none;
}

.route-name-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 24px;
  gap: 2px 8px;
}

.route-title-group {
  flex: 1 1 120px;
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
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-weight: 700;
  font-size: 12px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  flex-shrink: 0;
  border: 1px solid var(--pm-border);
  transition: all 0.15s ease;
}

.route-seq--active {
  background: var(--pm-primary);
  color: var(--pm-surface);
  border-color: var(--pm-primary);
}

.route-name-row h3 {
  min-width: 0;
  margin: 0;
  color: var(--ink);
  font-size: 13px;
  font-weight: 600;
  line-height: 18px;
  overflow-wrap: anywhere;
}

.route-kind {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 7px;
  border-radius: 4px;
  background: var(--accent-soft);
  color: var(--pm-primary-hover);
  font-size: 12px;
  font-weight: 600;
}

.route-kind.branch {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.route-step-area {
  margin-top: 4px;
  padding-top: 4px;
  border-top: 1px solid var(--pm-border);
}

.route-step-summary {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex: 0 0 auto;
  min-height: 24px;
  white-space: nowrap;
  margin: 0;
  padding: 0;
  border: 0;
  background: transparent;
  color: var(--muted);
  cursor: pointer;
  font-family: inherit;
  font-size: 12px;
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
  outline: 2px solid rgba(36, 95, 168, 0.35);
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
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 12px;
  font-weight: 700;
  border: 1px solid var(--pm-border);
  transition: color 0.15s ease, background 0.15s ease, border-color 0.15s ease;
}

.route-step-summary:hover .route-step-count {
  border-color: rgba(36, 95, 168, 0.18);
  background: rgba(36, 95, 168, 0.08);
  color: var(--accent);
}

.process-step-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}

.process-step-chip {
  display: inline-flex;
  align-items: center;
  max-width: 100%;
  overflow-wrap: anywhere;
  min-height: 20px;
  padding: 1px 6px;
  border: 1px solid var(--pm-border);
  border-radius: 4px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-size: 12px;
  font-weight: 500;
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
  font-size: 12px;
}

@keyframes pulse {
  0%, 100% { opacity: 0.25; transform: translateY(0); }
  50% { opacity: 1; transform: translateY(-4px); }
}

@media (max-width: 700px) {
  .route-placeholder { padding: 24px 16px; }
  .output-head { align-items: center; flex-wrap: wrap; }
}

.readiness-link-btn { min-height: var(--pm-control-height-small); height: auto; padding: 3px 10px; line-height: 20px; }
.output-head-left, .route-name-row { flex-wrap: wrap; }
.output-stats-inline { margin-left: 0; }
.route-seq { min-height: 20px; height: auto; }
.route-step-summary:focus-visible { outline-color: var(--pm-primary); }
@media (prefers-reduced-motion: reduce) {
  .generation-loader span { animation: none; }
  .route-dot, .route-card, .route-seq, .route-step-caret, .route-step-count { transition: none; }
}
</style>
