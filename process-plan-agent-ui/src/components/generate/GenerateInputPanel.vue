<template>
  <aside class="input-panel">
    <!-- Header with progress bar -->
    <div class="input-panel-head">
      <div class="panel-head-left">
        <span class="panel-title">输入条件</span>
        <span class="panel-subtitle">描述新零件</span>
      </div>
      <div v-if="inputFields.length" class="panel-head-right">
        <span class="progress-label" :class="{ 'progress-label--done': canGenerate }">
          {{ filledFieldCount }}/{{ inputFieldCount ?? inputFields.length }}
        </span>
        <div class="head-progress-track">
          <div
            class="head-progress-fill"
            :class="{ 'head-progress-fill--done': canGenerate }"
            :style="{ width: (inputFieldCount ?? inputFields.length) ? `${Math.round(filledFieldCount / (inputFieldCount ?? inputFields.length) * 100)}%` : '0%' }"
          ></div>
        </div>
      </div>
    </div>

    <div v-if="inputFields.length" class="field-list">
      <section v-for="section in factorSections" :key="section.id" class="factor-section">
        <h3 class="factor-section-title">{{ section.title }}</h3>
        <div v-for="group in section.groups" :key="group.id" class="factor-object-group" :class="{ 'manual-switch-grid': section.id === 'manual' }">
          <h4 v-if="group.title" class="factor-object-title">{{ group.title }}</h4>
          <p v-if="group.context" class="factor-object-context">{{ group.context }}</p>
          <div v-if="group.features?.length" class="feature-input-grid">
            <div v-for="feature in group.features || []" :key="feature.presenceKey" class="feature-input" :class="{ 'feature-input--selected': fieldValues[feature.presenceKey] === true }">
              <label class="feature-toggle">
                <input type="checkbox" :aria-label="featureLabel(feature.name)" :checked="fieldValues[feature.presenceKey] === true" @change="setFieldBoolean(feature.presenceKey, ($event.target as HTMLInputElement).checked)" />
                <span>{{ featureLabel(feature.name) }}</span>
              </label>
              <div v-if="fieldValues[feature.presenceKey] === true && feature.fields.length" class="feature-parameters">
                <label v-for="parameter in feature.fields" :key="parameter.key" class="feature-parameter">
                  <span>{{ parameter.key.endsWith('.direction') ? '方位' : isActualProjectItField(parameter) ? '尺寸精度' : '粗糙度 Ra（μm）' }}</span>
                  <select v-if="isActualProjectItField(parameter)" class="text-input" :aria-label="parameter.name" :value="fieldValues[parameter.key] ?? ''" @change="setFieldText(parameter.key, inputValue($event))">
                    <option value="" disabled>选择精度</option>
                    <option v-for="grade in actualProjectItGrades" :key="grade" :value="grade">IT{{ grade }}</option>
                  </select>
                  <select v-else-if="parameter.key.endsWith('.direction')" class="text-input" :aria-label="parameter.name" :value="fieldValues[parameter.key] ?? ''" @change="setFieldText(parameter.key, inputValue($event))">
                    <option value="" disabled>选择方位</option>
                    <option v-for="direction in parameter.allowed_values || []" :key="direction" :value="direction">{{ direction }}</option>
                  </select>
                  <input v-else class="text-input" type="number" step="any" min="0" :aria-label="parameter.name" placeholder="填写实际要求" :value="fieldValues[parameter.key] ?? ''" @input="setFieldText(parameter.key, inputValue($event))" />
                </label>
              </div>
            </div>
          </div>
          <template v-for="field in group.fields" :key="field.key">
            <label v-if="isManualProcessSwitch(field)" class="process-switch">
              <input type="checkbox" :aria-label="manualProcessName(field.name || field.key)" :checked="fieldValues[field.key] === true" @change="setFieldBoolean(field.key, ($event.target as HTMLInputElement).checked)" />
              <span>{{ manualProcessName(field.name || field.key) }}</span>
            </label>
      <div
        v-else
        class="field-block"
        :class="{ complete: isConfirmedField(field), invalid: isInvalidConfirmedFieldValue(field), optional: !field.required }"
      >
        <div class="field-label-row">
          <div class="field-name-line">
            <span class="field-label">{{ field.name || field.key }}</span>
            <svg v-if="isConfirmedField(field)" class="field-complete-icon" width="13" height="13" viewBox="0 0 16 16" fill="none">
              <circle cx="8" cy="8" r="7" fill="#22c55e" opacity="0.15"/>
              <path d="M5 8l2.5 2.5L11 5.5" stroke="#16a34a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
            </svg>
          </div>
          <div class="field-meta">
            <span v-if="!isMaterialInput(field)" class="field-source" :class="`field-source-${fieldSourceKind(field.source)}`">
              {{ fieldSourceLabel(field.source) }}
            </span>
            <span v-if="!isMaterialInput(field)" class="field-type">{{ fieldTypeLabel(field) }}</span>
            <span v-if="field.unit" class="field-unit">{{ field.unit }}</span>
            <span v-if="field.required" class="field-required">必填</span>
            <span
              v-if="!isMaterialInput(field) || !isConfirmedField(field) || isInvalidConfirmedFieldValue(field)"
              class="field-value-status"
              :class="[`field-value-status--${fieldValueOrigin(field.key)}`, { 'field-value-status--invalid': isInvalidConfirmedFieldValue(field) }]"
            >
              {{ fieldValueStatusLabel(field.key) }}
            </span>
          </div>
        </div>

        <div v-if="isActualProjectItField(field)" class="actual-it-field">
          <select class="text-input actual-it-select" :aria-label="field.name || field.key" :value="fieldValues[field.key] ?? ''" @change="setFieldText(field.key, inputValue($event))">
            <option disabled value="">请选择实际精度等级</option>
            <option v-for="grade in actualProjectItGrades" :key="grade" :value="grade">IT{{ grade }}</option>
          </select>
        </div>
        <input
          v-else-if="isTextField(field)"
          class="text-input"
          type="text"
          :value="fieldTextValue(field.key)"
          :placeholder="fieldPlaceholder(field)"
          @input="setFieldText(field.key, inputValue($event))"
        />

        <div v-else-if="isSingleSelectField(field)">
          <div v-if="field.allowed_values?.length" class="chip-grid" :class="{ compact: field.allowed_values.length > 9 }">
            <button
              v-for="item in field.allowed_values"
              :key="item"
              type="button"
              class="select-chip"
              :class="{ active: fieldValues[field.key] === item }"
              @click="setFieldText(field.key, item)"
            >
              {{ item }}
            </button>
          </div>
          <input
            v-else-if="!isMaterialInput(field)"
            class="text-input"
            type="text"
            :value="fieldTextValue(field.key)"
            :placeholder="fieldPlaceholder(field)"
            @input="setFieldText(field.key, inputValue($event))"
          />
          <p v-else class="material-empty">当前没有已配置的材料牌号，请返回规则审核补充材料候选。</p>
          <div v-if="field.allow_custom" class="custom-row">
            <input
              class="text-input custom-input"
              type="text"
              placeholder="自定义输入"
              :value="customInputValues[field.key] || ''"
              @input="setCustomInput(field.key, inputValue($event))"
              @keydown.enter.prevent="addCustomSingleValue(field.key)"
            />
            <button class="custom-add-btn" type="button" @click="addCustomSingleValue(field.key)">+ 添加</button>
          </div>
        </div>

        <div v-else-if="isArrayField(field)">
          <div v-if="field.allowed_values?.length" class="chip-grid" :class="{ compact: field.allowed_values.length > 9 }">
            <button
              v-for="item in field.allowed_values"
              :key="item"
              type="button"
              class="select-chip"
              :class="{ active: arrayFieldValues(field.key).includes(item) }"
              @click="toggleFieldArrayValue(field.key, item)"
            >
              {{ item }}
            </button>
          </div>
          <div v-if="field.allow_custom" class="custom-row">
            <input
              class="text-input custom-input"
              type="text"
              :placeholder="field.examples?.[0] ? `补充输入 (例 ${field.examples[0]})` : '补充输入'"
              :value="customInputValues[field.key] || ''"
              @input="setCustomInput(field.key, inputValue($event))"
              @keydown.enter.prevent="addCustomArrayValue(field.key)"
            />
            <button class="custom-add-btn" type="button" @click="addCustomArrayValue(field.key)">+ 添加</button>
          </div>
        </div>

        <div v-else-if="isBooleanField(field)" class="boolean-choice" role="radiogroup" :aria-label="field.name">
          <button type="button" class="select-chip" :class="{ active: fieldValues[field.key] === true }" @click="setFieldBoolean(field.key, true)">是</button>
          <button type="button" class="select-chip" :class="{ active: fieldValues[field.key] === false }" @click="setFieldBoolean(field.key, false)">否</button>
        </div>

        <input
          v-else
          class="text-input"
          :type="isNumberField(field) ? 'number' : 'text'"
          :min="isNumberField(field) ? field.validation?.min ?? undefined : undefined"
          :max="isNumberField(field) ? field.validation?.max ?? undefined : undefined"
          :value="fieldTextValue(field.key)"
          :placeholder="fieldPlaceholder(field)"
          @input="setFieldText(field.key, inputValue($event))"
        />
      </div>
          </template>
        </div>
      </section>
    </div>

    <div v-if="!hasRulePackage || !inputFields.length" class="schema-empty">
      <strong>{{ canGenerate ? '无需填写参数' : '无法配置生成参数' }}</strong>
      <span>{{ schemaStatusText }}</span>
      <button v-if="!canGenerate" class="mini-btn schema-action" type="button" @click="emit('go-finalize')">返回第{{ finalizeStepNumber ?? 5 }}步</button>
    </div>

    <div class="generate-submit">
      <div class="submit-actions">
        <button class="secondary-action" type="button" @click="clearAllFields" :disabled="generating || !inputFields.length">清空</button>
        <button class="secondary-action secondary-action-example" type="button" @click="fillExampleValues" :disabled="generating || !inputFields.length">填入示例</button>
      </div>
      <button class="generate-cta" type="button" @click="emit('generate')" :disabled="generating || !canGenerate">
        <span>{{ generating ? '正在生成路线' : '生成工艺路线' }}</span>
        <span aria-hidden="true">{{ generating ? '···' : '→' }}</span>
      </button>

    </div>
  </aside>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { groupGenerateFields, isMaterialInput, actualProjectItGrades, isActualProjectItField, type FactorProcessDefinition } from '@/composables/generateFactorGroups'
const props = defineProps<{
  projectId: number | null
  projectName: string
  finalizeStepNumber?: number
  inputFields: any[]
  inputFieldCount?: number
  processDefinitions?: FactorProcessDefinition[]
  filledFieldCount: number
  canGenerate: boolean
  hasRulePackage: boolean
  generating: boolean
  schemaStatusText: string
  generateHintText: string
  fieldValues: Record<string, any>
  fieldValueOrigin: (key: string) => 'unset' | 'extracted' | 'manual' | 'example'
  customInputValues: Record<string, string>
  isConfirmedFieldValue: (field: any) => boolean
  isInvalidConfirmedFieldValue: (field: any) => boolean
  fieldTypeLabel: (field: any) => string
  isTextField: (field: any) => boolean
  isSingleSelectField: (field: any) => boolean
  isArrayField: (field: any) => boolean
  isBooleanField: (field: any) => boolean
  isNumberField: (field: any) => boolean
  fieldTextValue: (key: string) => string
  fieldPlaceholder: (field: any) => string
  inputValue: (event: Event) => string
  arrayFieldValues: (key: string) => string[]
  setFieldText: (key: string, value: string) => void
  setFieldBoolean: (key: string, value: boolean) => void
  toggleFieldArrayValue: (key: string, value: string) => void
  setCustomInput: (key: string, value: string) => void
  addCustomArrayValue: (key: string) => void
  addCustomSingleValue: (key: string) => void
  clearAllFields: () => void
  fillExampleValues: () => void
}>()

const factorSections = computed(() => groupGenerateFields(props.inputFields, props.processDefinitions))
const featureLabel = (name: string) => name.replace(/^孔\((通孔|盲孔)\)$/, '$1')
const manualProcessName = (name: string) => name.replace(/^(?:是否需要|是否)/, '')

const emit = defineEmits<{
  (event: 'generate'): void
  (event: 'go-finalize'): void
}>()

function fieldSourceKind(source: string | undefined) {
  const text = String(source || '')
  if (/人工|手工/.test(text)) return 'manual'
  if (/CAD|PLM/i.test(text)) return 'cad'
  if (/图样|图纸/.test(text)) return 'drawing'
  return 'package'
}

function fieldSourceLabel(source: string | undefined) {
  const kind = fieldSourceKind(source)
  if (kind === 'manual') return '人工补充 / 图样技术要求'
  if (kind === 'cad') return 'CAD / PLM 建议来源'
  if (kind === 'drawing') return '图样技术要求'
  return '规则包输入'
}

function fieldValueStatusLabel(key: string) {
  const field = props.inputFields.find(item => item.key === key)
  if (field && props.isInvalidConfirmedFieldValue(field)) return '需修正'
  const origin = props.fieldValueOrigin(key)
  if (origin === 'extracted') return '已提取'
  if (origin === 'manual') return '已确认'
  if (origin === 'example') return '示例值'
  if (field && isManualProcessSwitch(field) && props.fieldValues[key] === false) return '默认否'
  return '待填写'
}

function isManualProcessSwitch(field: any) {
  return props.isBooleanField(field)
    && field.key.startsWith('project_factor.manual_process_')
    && field.source === '用户直接设定'
}

function isConfirmedField(field: any) {
  return props.isConfirmedFieldValue(field)
}
</script>

<style scoped>
.actual-it-field { display: grid; gap: 6px; }
.actual-it-select { width: 100%; }
.factor-section + .factor-section { margin-top: 4px; border-top: 1px solid var(--pm-border); padding-top: 12px; }
.factor-section-title { font-size: 14px; color: var(--pm-text); margin: 0 0 8px; }
.factor-object-group + .factor-object-group { margin-top: 10px; }
.factor-object-title { margin: 0 0 6px; color: var(--pm-text-secondary); font-size: 13px; }
.factor-object-context,.material-empty { color: var(--pm-text-muted); font-size: 12px; line-height: 1.6; }
.manual-switch-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, max(118px, calc((100% - 24px) / 3))), 1fr)); gap: 8px 12px; }
.feature-input-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(min(100%, max(220px, calc((100% - 8px) / 2))), 1fr)); gap: 8px; align-items: start; }
.feature-input { min-width: 0; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-card); padding: 8px; background: var(--pm-surface); }
.feature-input--selected { border-color: var(--pm-primary-border); background: var(--pm-primary-soft); }
.feature-toggle { display: flex; align-items: center; gap: 6px; min-height: 20px; cursor: pointer; font-size: 13px; font-weight: 500; line-height: 20px; color: var(--pm-text); }
.feature-toggle span { min-width: 0; overflow-wrap: anywhere; }
.feature-toggle input { width: 16px; height: 16px; margin: 0; accent-color: var(--pm-primary); flex-shrink: 0; }
.feature-parameters { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 100px), 1fr)); gap: 8px; padding-top: 8px; }
.feature-parameter { display: grid; align-content: start; gap: 4px; min-width: 0; color: var(--pm-text-secondary); font-size: 12px; line-height: 18px; }
.feature-parameter .text-input { min-width: 0; width: 100%; }
.input-panel {
  --ink: var(--pm-text);
  --muted: var(--pm-text-muted);
  --line: var(--pm-border);
  --surface: var(--pm-surface);
  --panel: var(--pm-surface-subtle);
  --accent: var(--pm-primary);
  --accent-soft: var(--pm-primary-soft);
  height: 100%;
  overflow-y: auto;
  padding: 12px;
  border: 1px solid var(--line);
  border-radius: var(--pm-radius-card);
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.input-panel::-webkit-scrollbar { width: 6px; height: 6px; }
.input-panel::-webkit-scrollbar-track { background: var(--pm-surface-subtle); border-radius: 6px; }
.input-panel::-webkit-scrollbar-thumb { background: var(--pm-border-strong); border-radius: 6px; }
.input-panel::-webkit-scrollbar-thumb:hover { background: var(--pm-text-muted); }

.process-switch { display: flex; align-items: flex-start; min-height: 26px; gap: 6px; cursor: pointer; font-size: 13px; line-height: 20px; color: var(--ink); overflow-wrap: anywhere; }
.process-switch input { flex-shrink: 0; margin: 2px 0 0; }
.process-switch input { width: 16px; height: 16px; accent-color: var(--accent); }

/* ===== Header ===== */
.input-panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
  padding: 0 4px 12px;
  border-bottom: 1px solid var(--line);
  margin-bottom: 12px;
  box-sizing: content-box;
}

.panel-head-left {
  display: flex;
  align-items: center;
  min-width: 0;
  min-height: 28px;
}
.panel-title {
  font-size: 15px;
  font-weight: 700;
  line-height: 28px;
  color: var(--ink);
}
.panel-subtitle {
  font-size: 13px;
  line-height: 28px;
  color: var(--muted);
  margin-left: 8px;
  font-weight: 500;
}

/* ===== Header progress ===== */
.panel-head-right {
  display: flex;
  align-items: center;
  gap: 7px;
  flex-shrink: 0;
}
.progress-label {
  font-size: 12px;
  font-weight: 700;
  color: var(--muted);
  white-space: nowrap;
  transition: color 0.25s ease;
}
.progress-label--done { color: var(--pm-success); }
.head-progress-track {
  width: 56px; height: 5px;
  background: var(--pm-border); border-radius: 999px; overflow: hidden;
}
.head-progress-fill {
  height: 100%; background: var(--pm-primary); border-radius: 999px;
  transition: width 0.4s ease, background 0.3s ease;
}
.head-progress-fill--done { background: var(--pm-success); }

/* ===== Onboarding banner ===== */
.onboarding-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border: 1px solid var(--pm-primary-border);
  border-radius: 8px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  font-size: 12px;
  font-weight: 500;
}
.banner-fill-btn {
  margin-left: auto;
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid var(--pm-primary);
  border-radius: 6px;
  background: var(--pm-primary);
  color: var(--pm-surface);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}
.banner-fill-btn:hover { background: var(--pm-primary); border-color: var(--pm-primary); }

.banner-fade-enter-active { transition: all 0.3s ease; }
.banner-fade-leave-active { transition: all 0.2s ease; }
.banner-fade-enter-from { opacity: 0; transform: translateY(-6px); }
.banner-fade-leave-to   { opacity: 0; transform: translateY(-4px); }

/* ===== Field list ===== */
.field-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-top: 10px;
}

.field-block {
  padding: 8px;
  border: 1px solid var(--line);
  border-radius: var(--pm-radius-card);
  background: var(--pm-surface);
  transition: border-color 0.16s ease, background 0.16s ease;
}
.field-block:focus-within {
  border-color: var(--accent);
}
.field-block.complete {
  border-color: var(--pm-border);
  background: var(--pm-surface);
}
.field-block.invalid {
  border-color: var(--pm-danger-border);
  background: var(--pm-danger-soft);
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 4px;
}
.field-name-line {
  display: flex;
  align-items: center;
  gap: 6px;
}
.field-label {
  display: inline;
  color: var(--ink);
  font-size: 13px;
  font-weight: 700;
}
.field-complete-icon { flex-shrink: 0; }

.field-source {
  display: inline-flex;
  align-items: center;
  border-radius: 3px;
  padding: 0 4px;
  font-size: 12px;
  line-height: 1.35;
}
.field-source-manual  { background: #fff2e8; color: #a6542e; }
.field-source-cad     { background: #ebf3fb; color: #3b6689; }
.field-source-drawing { background: #f1edf9; color: #665080; }
.field-source-package { background: #edf1f5; color: #677588; }

.field-meta {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  flex-shrink: 0;
}
.field-type,
.field-unit,
.field-required {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 700;
}
.field-type     { border: 1px solid var(--pm-border); color: var(--muted); }
.field-unit     { border: 1px solid #d8e3ec; color: #4b6478; background: #f5f9fc; }
.field-required { background: var(--pm-warning-soft); color: var(--pm-warning); }

.field-value-status {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}
.field-value-status--unset { background: var(--pm-surface-subtle); color: var(--pm-text-muted); }
.field-value-status--manual { background: var(--pm-success-soft); color: var(--pm-success); }
.field-value-status--extracted { background: var(--pm-primary-soft); color: var(--pm-primary); }
.field-value-status--example { background: var(--pm-warning-soft); color: var(--pm-warning); }
.field-value-status--invalid { background: var(--pm-danger-soft); color: var(--pm-danger); }

/* ===== Inputs ===== */
.text-input {
  width: 100%; height: var(--pm-control-height);
  padding: 0 8px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 5px;
  background: var(--pm-surface);
  color: var(--ink);
  font: inherit; font-size: 12px;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}
.text-input:focus {
  border-color: var(--accent);
  box-shadow: var(--pm-focus-ring);
}

.chip-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 5px;
}
.chip-grid.compact { grid-template-columns: repeat(4, minmax(0, 1fr)); }

.select-chip {
  height: auto;
  padding: 3px 8px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 5px;
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  font: inherit; font-size: 12px; font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}
.select-chip:hover { border-color: var(--accent); }
.select-chip.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: var(--pm-primary-hover);
}

.custom-row {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 6px;
}
.custom-input { min-height: 28px; height: auto; font-size: 12px; }
.custom-add-btn {
  min-height: 28px; height: auto;
  padding: 0 9px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 5px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  flex-shrink: 0;
}
.custom-add-btn:hover { background: var(--pm-primary-soft); border-color: var(--pm-primary); color: var(--pm-primary); }

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: var(--pm-text-secondary);
  font-size: 13px;
  font-weight: 600;
}
.check-row input { width: 16px; height: 16px; accent-color: var(--accent); }

/* ===== Schema empty ===== */
.schema-empty {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: 7px;
  margin-top: 14px;
  padding: 12px;
  border: 1px solid var(--pm-warning-border);
  border-radius: 8px;
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.55;
}
.schema-action { height: 30px; margin-top: 2px; }

/* ===== Generate submit area ===== */
.generate-submit {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}
.submit-actions {
  display: flex;
  align-items: center;
  gap: 7px;
  margin-bottom: 8px;
}

.mini-btn,
.secondary-action {
  border: 1px solid var(--pm-border-strong);
  border-radius: 6px;
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  font: inherit; font-size: 12px; font-weight: 600;
  cursor: pointer;
}
.mini-btn { height: 36px; padding: 0 9px; }
.secondary-action { flex: 1; height: 34px; }
.mini-btn:hover,
.secondary-action:hover { border-color: var(--accent); color: var(--pm-primary-hover); }

/* Example button: slightly more prominent */
.secondary-action-example {
  border-color: var(--pm-primary-border);
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
}
.secondary-action-example:hover { background: var(--accent-soft); border-color: var(--pm-primary-border); }

.generate-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 34px;
  padding: 0 13px;
  border: 1px solid var(--pm-primary);
  border-radius: 8px;
  background: var(--pm-primary);
  color: var(--pm-surface);
  font: inherit; font-size: 13px; font-weight: 700;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}
.generate-cta:hover:not(:disabled) {
  border-color: var(--pm-primary-hover);
  background: var(--pm-primary);
  transform: none;
}
.generate-cta:disabled,
.secondary-action:disabled,
.mini-btn:disabled { cursor: not-allowed; opacity: 0.46; }

/* ===== Enhanced hint callout ===== */
.generate-hint-callout {
  display: flex;
  align-items: flex-start;
  gap: 7px;
  margin-top: 9px;
  padding: 8px 11px;
  border: 1px solid var(--pm-warning-border);
  border-radius: 7px;
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.5;
}
.generate-hint-callout svg { flex-shrink: 0; margin-top: 1px; color: var(--pm-warning); }

@media (max-width: 900px) {
  .input-panel { position: static; }
  .field-subrow { align-items: flex-start; flex-direction: column; gap: 2px; }
}

/* Compact grouped fields keep the actual IT select beside each feature. */
.input-panel { min-width: 0; border-radius: var(--pm-radius-card); }
.panel-title { font-size: 14px; font-weight: 600; line-height: 22px; }
.input-panel-head { padding: 0 0 8px; margin-bottom: 8px; flex-wrap: wrap; gap: 6px; }
.field-list { gap: 8px; margin-top: 8px; }
.factor-object-group > .field-block + .field-block { margin-top: 6px; }
.factor-object-title { margin-bottom: 6px; font-weight: 600; line-height: 20px; }
.factor-section-title { font-weight: 600; line-height: 22px; }
.field-label-row, .field-name-line, .field-meta { flex-wrap: wrap; min-width: 0; }
.field-label-row { gap: 4px 8px; }
.field-label { font-size: 13px; font-weight: 500; line-height: 20px; overflow-wrap: anywhere; }
.field-meta { gap: 3px; }
.field-source, .field-type, .field-unit, .field-required, .field-value-status { height: auto; min-height: 18px; font-size: 12px; line-height: 18px; font-weight: 400; }
.text-input { height: var(--pm-control-height); border-radius: var(--pm-radius-control); font-size: 13px; }
.actual-it-field { gap: 4px; }
.select-chip { min-height: 28px; font-size: 12px; line-height: 18px; font-weight: 500; }
.select-chip.active { color: var(--pm-primary); }
.boolean-choice { display: flex; gap: 6px; }
.onboarding-banner { flex-wrap: wrap; border-radius: var(--pm-radius-control); line-height: 18px; }
.onboarding-banner svg { flex-shrink: 0; }
.onboarding-banner > span { flex: 1 1 160px; }
.banner-fill-btn, .custom-add-btn { min-height: 28px; padding: 3px 8px; font-size: 12px; line-height: 20px; }
.generate-submit { margin-top: 12px; padding-top: 10px; }
.secondary-action, .mini-btn { min-height: 28px; height: auto; padding: 3px 8px; line-height: 20px; font-weight: 500; font-size: 12px; }
.generate-cta { min-height: 34px; border-radius: var(--pm-radius-control); font-weight: 600; background: var(--pm-primary); }
.generate-cta:hover:not(:disabled) { background: var(--pm-primary-hover); border-color: var(--pm-primary-hover); transform: none; }
.input-panel button:focus-visible, .input-panel input[type=checkbox]:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.field-complete-icon circle { fill: var(--pm-success); }
.field-complete-icon path { stroke: var(--pm-success); }
@media (max-width: 520px) { .chip-grid.compact { grid-template-columns: repeat(2, minmax(0, 1fr)); } }
@media (prefers-reduced-motion: reduce) { .input-panel button, .head-progress-fill, .field-block { transition: none; } }
</style>
