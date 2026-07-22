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
          {{ filledFieldCount }}/{{ inputFields.length }}
        </span>
        <div class="head-progress-track">
          <div
            class="head-progress-fill"
            :class="{ 'head-progress-fill--done': canGenerate }"
            :style="{ width: inputFields.length ? `${Math.round(filledFieldCount / inputFields.length * 100)}%` : '0%' }"
          ></div>
        </div>
      </div>
    </div>

    <!-- Onboarding banner: shown when all fields are empty -->
    <Transition name="banner-fade">
      <div v-if="filledFieldCount === 0 && inputFields.length > 0 && !generating" class="onboarding-banner">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10"/><path d="M12 16v-4M12 8h.01"/>
        </svg>
        <span>首次使用？快速填入示例数据，查看生成效果</span>
        <button class="banner-fill-btn" type="button" @click="fillExampleValues">填入示例 →</button>
      </div>
    </Transition>

    <div v-if="inputFields.length" class="field-list">
      <div
        v-for="field in inputFields"
        :key="field.key"
        class="field-block"
        :class="{ complete: Boolean(fieldPreviewValue(field.key)), optional: !field.required }"
      >
        <div class="field-label-row">
          <div class="field-title-stack">
            <div class="field-name-line">
              <span class="field-label">{{ field.name || field.key }}</span>
              <!-- Checkmark for completed fields -->
              <svg v-if="Boolean(fieldPreviewValue(field.key))" class="field-complete-icon" width="13" height="13" viewBox="0 0 16 16" fill="none">
                <circle cx="8" cy="8" r="7" fill="#22c55e" opacity="0.15"/>
                <path d="M5 8l2.5 2.5L11 5.5" stroke="#16a34a" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </div>
            <span class="field-source" :class="`field-source-${fieldSourceKind(field.source)}`" :title="field.source || '规则包输入'">
              {{ fieldSourceLabel(field.source) }}
            </span>
          </div>
          <span class="field-meta">
            <span class="field-type">{{ fieldTypeLabel(field) }}</span>
            <span v-if="!field.required" class="field-optional">可选</span>
            <span v-else class="field-required">必填</span>
          </span>
        </div>

        <input
          v-if="isTextField(field)"
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
            v-else
            class="text-input"
            type="text"
            :value="fieldTextValue(field.key)"
            :placeholder="fieldPlaceholder(field)"
            @input="setFieldText(field.key, inputValue($event))"
          />
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
          <div v-if="field.allow_custom" class="field-subrow">
            <span>补充输入</span>
            <span>添加规则包之外的值</span>
          </div>
          <div v-if="field.allow_custom" class="custom-row">
            <input
              class="text-input"
              type="text"
              :placeholder="field.examples?.[0] ? `例如 ${field.examples[0]}` : '补充参数'"
              :value="customInputValues[field.key] || ''"
              @input="setCustomInput(field.key, inputValue($event))"
              @keydown.enter.prevent="addCustomArrayValue(field.key)"
            />
            <button class="mini-btn" type="button" @click="addCustomArrayValue(field.key)">添加</button>
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
          :value="fieldTextValue(field.key)"
          :placeholder="fieldPlaceholder(field)"
          @input="setFieldText(field.key, inputValue($event))"
        />
      </div>
    </div>

    <div v-if="!hasRulePackage || !inputFields.length" class="schema-empty">
      <strong>无法配置生成参数</strong>
      <span>{{ schemaStatusText }}</span>
      <button class="mini-btn schema-action" type="button" @click="emit('go-finalize')">返回第4步</button>
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

      <!-- Enhanced hint when cannot generate -->
      <div v-if="!canGenerate && hasRulePackage && inputFields.length" class="generate-hint-callout">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 9v4M12 17h.01"/><path d="M10.29 3.86L1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0z"/>
        </svg>
        <span>{{ generateHintText }}</span>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  projectId: number | null
  projectName: string
  inputFields: any[]
  filledFieldCount: number
  canGenerate: boolean
  hasRulePackage: boolean
  generating: boolean
  schemaStatusText: string
  generateHintText: string
  fieldValues: Record<string, any>
  customInputValues: Record<string, string>
  fieldTypeLabel: (field: any) => string
  isTextField: (field: any) => boolean
  isSingleSelectField: (field: any) => boolean
  isArrayField: (field: any) => boolean
  isBooleanField: (field: any) => boolean
  isNumberField: (field: any) => boolean
  fieldTextValue: (key: string) => string
  fieldPlaceholder: (field: any) => string
  fieldPreviewValue: (key: string) => string
  inputValue: (event: Event) => string
  checkedValue: (event: Event) => boolean
  arrayFieldValues: (key: string) => string[]
  setFieldText: (key: string, value: string) => void
  setFieldBoolean: (key: string, value: boolean) => void
  toggleFieldArrayValue: (key: string, value: string) => void
  setCustomInput: (key: string, value: string) => void
  addCustomArrayValue: (key: string) => void
  clearAllFields: () => void
  fillExampleValues: () => void
}>()

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
  if (kind === 'cad') return 'CAD / PLM 自动带入'
  if (kind === 'drawing') return '图样技术要求'
  return '规则包输入'
}
</script>

<style scoped>
.input-panel {
  --ink: #0f172a;
  --muted: #64748b;
  --line: #e2e8f0;
  --surface: #ffffff;
  --panel: #f8fafc;
  --accent: #4f46e5;
  --accent-soft: #eef2ff;
  height: 100%;
  overflow-y: auto;
  padding: 16px;
  border: 1px solid var(--line);
  border-radius: 14px;
  background: var(--surface);
  box-shadow: var(--shadow-sm);
}

.input-panel::-webkit-scrollbar { width: 6px; height: 6px; }
.input-panel::-webkit-scrollbar-track { background: #f8fafc; border-radius: 6px; }
.input-panel::-webkit-scrollbar-thumb { background: #cbd5e1; border-radius: 6px; }
.input-panel::-webkit-scrollbar-thumb:hover { background: #94a3b8; }

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
  font-size: 11.5px;
  font-weight: 700;
  color: var(--muted);
  white-space: nowrap;
  transition: color 0.25s ease;
}
.progress-label--done { color: #16a34a; }
.head-progress-track {
  width: 56px; height: 5px;
  background: #e2e8f0; border-radius: 999px; overflow: hidden;
}
.head-progress-fill {
  height: 100%; background: #6366f1; border-radius: 999px;
  transition: width 0.4s ease, background 0.3s ease;
}
.head-progress-fill--done { background: #22c55e; }

/* ===== Onboarding banner ===== */
.onboarding-banner {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  padding: 9px 12px;
  border: 1px solid #bfdbfe;
  border-radius: 8px;
  background: linear-gradient(135deg, #eff6ff, #eef2ff);
  color: #3730a3;
  font-size: 12px;
  font-weight: 500;
}
.banner-fill-btn {
  margin-left: auto;
  flex-shrink: 0;
  padding: 4px 10px;
  border: 1px solid #6366f1;
  border-radius: 6px;
  background: #6366f1;
  color: #ffffff;
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.15s ease;
}
.banner-fill-btn:hover { background: #4f46e5; border-color: #4f46e5; }

.banner-fade-enter-active { transition: all 0.3s ease; }
.banner-fade-leave-active { transition: all 0.2s ease; }
.banner-fade-enter-from { opacity: 0; transform: translateY(-6px); }
.banner-fade-leave-to   { opacity: 0; transform: translateY(-4px); }

/* ===== Field list ===== */
.field-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.field-block {
  padding: 11px 11px 11px 13px;
  border: 1px solid var(--line);
  border-left: 3px solid transparent;
  border-radius: 8px;
  background: #fbfcfc;
  transition: border-color 0.16s ease, background 0.16s ease, border-left-color 0.25s ease;
}
.field-block:focus-within {
  border-color: var(--accent);
  background: #ffffff;
}
.field-block.complete {
  border-color: #d1fae5;
  border-left-color: #22c55e;
  background: #f8fffd;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}
.field-title-stack { min-width: 0; }
.field-name-line {
  display: flex;
  align-items: center;
  gap: 5px;
}
.field-label {
  display: inline;
  color: var(--ink);
  font-size: 13px;
  font-weight: 750;
}
.field-complete-icon { flex-shrink: 0; }

.field-source {
  display: inline-flex;
  align-items: center;
  margin-top: 2px;
  width: fit-content;
  border-radius: 3px;
  padding: 1px 5px;
  font-size: 11px;
  line-height: 1.35;
}
.field-source-manual  { background: #fff2e8; color: #a6542e; }
.field-source-cad     { background: #ebf3fb; color: #3b6689; }
.field-source-drawing { background: #f1edf9; color: #665080; }
.field-source-package { background: #edf1f5; color: #677588; }

.field-meta {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
}
.field-type,
.field-required,
.field-optional {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  font-size: 10px;
  font-weight: 800;
}
.field-type     { border: 1px solid #e2e8f0; color: var(--muted); }
.field-required { background: #fdf0e7; color: #b54708; }
.field-optional { color: #84918f; }

/* ===== Inputs ===== */
.text-input {
  width: 100%; height: 36px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: var(--ink);
  font: inherit; font-size: 13px;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}
.text-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}

.chip-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}
.chip-grid.compact { grid-template-columns: repeat(4, minmax(0, 1fr)); }

.select-chip {
  min-height: 33px;
  padding: 5px 7px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #334155;
  font: inherit; font-size: 12px; font-weight: 600;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}
.select-chip:hover { border-color: var(--accent); }
.select-chip.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: #4338ca;
}

.field-subrow {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  color: var(--muted);
  font-size: 11px;
}
.field-subrow span:first-child { color: #0f172a; font-weight: 700; }

.custom-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 58px;
  gap: 7px;
  margin-top: 7px;
}

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 36px;
  color: #334155;
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
  border: 1px solid #f1c497;
  border-radius: 8px;
  background: #fff7ed;
  color: #9a3412;
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
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #334155;
  font: inherit; font-size: 11px; font-weight: 600;
  cursor: pointer;
}
.mini-btn { height: 36px; padding: 0 9px; }
.secondary-action { flex: 1; height: 34px; }
.mini-btn:hover,
.secondary-action:hover { border-color: var(--accent); color: #4338ca; }

/* Example button: slightly more prominent */
.secondary-action-example {
  border-color: #c7d2fe;
  color: #4f46e5;
  background: #f5f3ff;
}
.secondary-action-example:hover { background: var(--accent-soft); border-color: #818cf8; }

.generate-cta {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  min-height: 42px;
  padding: 0 13px;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  color: #ffffff;
  font: inherit; font-size: 13px; font-weight: 700;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, transform 0.16s ease;
}
.generate-cta:hover:not(:disabled) {
  border-color: #4338ca;
  background: linear-gradient(135deg, #4338ca, #4f46e5);
  transform: translateY(-1px);
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
  border: 1px solid #fed7aa;
  border-radius: 7px;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  line-height: 1.5;
}
.generate-hint-callout svg { flex-shrink: 0; margin-top: 1px; color: #f97316; }

@media (max-width: 900px) {
  .input-panel { position: static; }
  .field-subrow { align-items: flex-start; flex-direction: column; gap: 2px; }
}
</style>
