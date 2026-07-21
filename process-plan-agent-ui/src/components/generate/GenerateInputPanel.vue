<template>
  <aside class="input-panel">
    <div class="input-panel-head">
      <div class="panel-head-left">
        <span class="panel-title">输入条件</span>
        <span class="panel-subtitle">描述新零件</span>
      </div>
    </div>



    <div v-if="inputFields.length" class="field-list">
      <div
        v-for="field in inputFields"
        :key="field.key"
        class="field-block"
        :class="{ complete: Boolean(fieldPreviewValue(field.key)), optional: !field.required }"
      >
        <div class="field-label-row">
          <div class="field-title-stack">
            <span class="field-label">{{ field.name || field.key }}</span>
            <span class="field-source">{{ field.source || '规则包输入' }}</span>
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
          <div class="field-subrow">
            <span>补充输入</span>
            <span>添加规则包之外的值</span>
          </div>
          <div class="custom-row">
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

        <label v-else-if="isBooleanField(field)" class="check-row">
          <input type="checkbox" :checked="Boolean(fieldValues[field.key])" @change="setFieldBoolean(field.key, checkedValue($event))" />
          <span>启用该条件</span>
        </label>

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
        <button class="secondary-action" type="button" @click="fillExampleValues" :disabled="generating || !inputFields.length">填入示例</button>
      </div>
      <button class="generate-cta" type="button" @click="emit('generate')" :disabled="generating || !canGenerate">
        <span>{{ generating ? '正在生成路线' : '生成工艺路线' }}</span>
        <span aria-hidden="true">→</span>
      </button>
      <p v-if="!canGenerate">{{ generateHintText }}</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
const props = defineProps<{
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

.input-panel::-webkit-scrollbar {
  width: 6px;
  height: 6px;
}

.input-panel::-webkit-scrollbar-track {
  background: #f8fafc;
  border-radius: 6px;
}

.input-panel::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 6px;
}

.input-panel::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}

/* 与右侧 .output-head 共用同一标题栏尺寸，保证底部分割线水平对齐 */
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

.panel-head-right {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-left: auto;
}

.mini-progress-label {
  font-size: 12px;
  color: var(--muted);
}

.mini-progress-label strong {
  color: var(--ink);
  font-weight: 700;
}

.mini-progress-track {
  width: 60px;
  height: 6px;
  background: #e2e8f0;
  border-radius: 999px;
  overflow: hidden;
}

.mini-progress-fill {
  height: 100%;
  background: #cbd5e1;
  border-radius: 999px;
  transition: width 0.2s ease;
}

.mini-progress-fill.ready {
  background: linear-gradient(90deg, #6366f1, #4f46e5);
}

.field-label-row,
.field-subrow,
.submit-actions,
.generate-cta {
  display: flex;
  align-items: center;
}



.field-list {
  display: flex;
  flex-direction: column;
  gap: 10px;
  margin-top: 12px;
}

.field-block {
  padding: 11px;
  border: 1px solid var(--line);
  border-radius: 8px;
  background: #fbfcfc;
  transition: border-color 0.16s ease, background 0.16s ease;
}

.field-block:focus-within {
  border-color: var(--accent);
  background: #ffffff;
}

.field-block.complete {
  border-color: #c7d2fe;
  background: #fafaff;
}

.field-label-row {
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 8px;
}

.field-title-stack {
  min-width: 0;
}

.field-label {
  display: block;
  color: var(--ink);
  font-size: 13px;
  font-weight: 750;
}

.field-source {
  display: block;
  margin-top: 2px;
  color: #84918f;
  font-size: 11px;
}

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

.field-type {
  border: 1px solid #e2e8f0;
  color: var(--muted);
}

.field-required {
  background: #fdf0e7;
  color: #b54708;
}

.field-optional {
  color: #84918f;
}

.text-input {
  width: 100%;
  height: 36px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: var(--ink);
  font: inherit;
  font-size: 13px;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
}

.text-input:focus {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px rgba(15, 118, 110, 0.12);
}

.chip-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 6px;
}

.chip-grid.compact {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}



.select-chip {
  min-height: 33px;
  padding: 5px 7px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #334155;
  font: inherit;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.16s ease, background 0.16s ease, color 0.16s ease;
}

.select-chip:hover {
  border-color: var(--accent);
}

.select-chip.active {
  border-color: var(--accent);
  background: var(--accent-soft);
  color: #4338ca;
}

.field-subrow {
  justify-content: space-between;
  gap: 8px;
  margin-top: 10px;
  color: var(--muted);
  font-size: 11px;
}

.field-subrow span:first-child {
  color: #0f172a;
  font-weight: 700;
}

.custom-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 58px;
  gap: 7px;
  margin-top: 7px;
}

.mini-btn,
.secondary-action {
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #334155;
  font: inherit;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
}

.mini-btn {
  height: 36px;
  padding: 0 9px;
}

.mini-btn:hover,
.secondary-action:hover {
  border-color: var(--accent);
  color: #4338ca;
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

.check-row input {
  width: 16px;
  height: 16px;
  accent-color: var(--accent);
}



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

.schema-action {
  height: 30px;
  margin-top: 2px;
}

.generate-submit {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--line);
}

.submit-actions {
  gap: 7px;
  margin-bottom: 8px;
}

.secondary-action {
  flex: 1;
  height: 34px;
}

.generate-cta {
  justify-content: space-between;
  width: 100%;
  min-height: 42px;
  padding: 0 13px;
  border: 1px solid #4f46e5;
  border-radius: 8px;
  background: linear-gradient(135deg, #4f46e5, #6366f1);
  color: #ffffff;
  font: inherit;
  font-size: 13px;
  font-weight: 700;
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
.mini-btn:disabled {
  cursor: not-allowed;
  opacity: 0.46;
}

.generate-submit p {
  margin: 8px 0 0;
  color: #84918f;
  font-size: 11px;
  line-height: 1.45;
}

@media (max-width: 900px) {
  .input-panel {
    position: static;
  }

  .field-subrow {
    align-items: flex-start;
    flex-direction: column;
    gap: 2px;
  }
}
</style>
