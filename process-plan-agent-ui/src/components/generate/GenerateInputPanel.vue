<template>
  <aside class="input-panel">
    <div class="panel-title-row">
      <div>
        <span class="panel-kicker">输入参数</span>
        <h2>新零件参数</h2>
        <p>输入项来自当前规则包，换零件族后会自动变化。</p>
      </div>
    </div>

    <div class="input-summary">
      <div class="summary-chip">
        <span class="summary-chip-label">任务</span>
        <span class="summary-chip-value">{{ projectName || `任务 #${projectId}` }}</span>
      </div>
      <div class="summary-chip">
        <span class="summary-chip-label">字段</span>
        <span class="summary-chip-value">{{ inputFields.length }}</span>
      </div>
      <div class="summary-chip">
        <span class="summary-chip-label">已选</span>
        <span class="summary-chip-value">{{ filledFieldCount }}</span>
      </div>
      <div class="summary-chip" :class="{ ready: canGenerate }">
        <span class="summary-chip-label">状态</span>
        <span class="summary-chip-value">{{ canGenerate ? '可生成' : '待补全' }}</span>
      </div>
    </div>

    <div v-for="field in inputFields" :key="field.key" class="field-block">
      <div class="field-shell">
        <div class="field-label-row">
          <div class="field-title-stack">
            <span class="field-label">{{ field.name || field.key }}</span>
            <span class="field-source">{{ field.source || '规则包输入' }}</span>
          </div>
          <span class="field-meta">
            <span class="field-type">{{ fieldTypeLabel(field) }}</span>
            <span v-if="!field.required" class="field-optional">可选</span>
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
          <div v-if="field.allowed_values?.length" class="chip-grid" :class="{ compact: field.allowed_values.length > 8 }">
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
          <div v-if="field.allowed_values?.length" class="chip-grid" :class="{ compact: field.allowed_values.length > 8 }">
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
            <span class="field-subtitle">补充输入</span>
            <span class="field-subhint">用于规则包中未列出的自定义值</span>
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
          <span>启用</span>
        </label>

        <input
          v-else
          class="text-input"
          :type="isNumberField(field) ? 'number' : 'text'"
          :value="fieldTextValue(field.key)"
          :placeholder="fieldPlaceholder(field)"
          @input="setFieldText(field.key, inputValue($event))"
        />

        <div v-if="fieldPreviewValue(field.key)" class="field-preview">
          <span class="field-preview-label">当前值</span>
          <span class="field-preview-value">{{ fieldPreviewValue(field.key) }}</span>
        </div>
      </div>
    </div>

    <div v-if="!hasRulePackage || !inputFields.length" class="schema-empty">
      {{ schemaStatusText }}
      <button class="mini-btn schema-action" type="button" @click="emit('go-finalize')">返回第4步</button>
    </div>

    <div v-if="missingRequiredFields.length" class="missing-required">
      <span class="missing-required-label">还需填写</span>
      <span v-for="field in missingRequiredFields" :key="field" class="missing-required-chip">{{ field }}</span>
    </div>

    <div class="generate-submit">
      <div class="submit-actions">
        <button class="btn btn-outline btn-half" type="button" @click="clearAllFields" :disabled="generating || !inputFields.length">清空参数</button>
        <button class="btn btn-outline btn-half" type="button" @click="fillExampleValues" :disabled="generating || !inputFields.length">示例参数</button>
      </div>
      <button class="btn btn-primary btn-wide generate-cta" type="button" @click="emit('generate')" :disabled="generating || !canGenerate">
        {{ generating ? '生成中...' : '生成工艺路线' }}
      </button>
      <p v-if="!canGenerate">{{ generateHintText }}</p>
    </div>
  </aside>
</template>

<script setup lang="ts">
defineProps<{
  projectId: number | null
  projectName: string
  inputFields: any[]
  filledFieldCount: number
  missingRequiredFields: string[]
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
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.86), rgba(255, 255, 255, 1) 120px),
    #ffffff;
  border: 1px solid #e4e7ec;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
  padding: 14px;
  position: sticky;
  top: 62px;
  max-height: calc(100vh - 76px);
  overflow-y: auto;
  scrollbar-gutter: stable;
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

.panel-title-row h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0;
}

.panel-title-row p {
  margin: 4px 0 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.55;
}

.input-summary {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-top: 12px;
}

.summary-chip {
  min-height: 52px;
  padding: 9px 10px;
  border: 1px solid #e2e8f0;
  border-radius: 7px;
  background: #f8fafc;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 2px;
}

.summary-chip.ready {
  border-color: #c7d2fe;
  background: #eef2ff;
}

.summary-chip-label {
  color: #64748b;
  font-size: 11px;
  font-weight: 700;
}

.summary-chip-value {
  color: #0f172a;
  font-size: 12px;
  font-weight: 800;
  line-height: 1.35;
  word-break: break-word;
}

.field-block {
  display: block;
  margin-top: 14px;
}

.field-shell {
  padding: 11px;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  background: #fcfdff;
}

.field-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  margin-bottom: 7px;
}

.field-title-stack {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.field-meta {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.field-label {
  display: block;
  font-size: 12px;
  font-weight: 700;
  color: #344054;
}

.field-source {
  color: #94a3b8;
  font-size: 11px;
  line-height: 1.4;
}

.field-type {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 7px;
  border-radius: 999px;
  background: #f2f4f7;
  color: #475467;
  font-size: 11px;
  font-weight: 700;
}

.field-optional {
  flex-shrink: 0;
  color: #98a2b3;
  font-size: 11px;
  font-weight: 700;
}

.schema-empty {
  margin-top: 14px;
  padding: 12px;
  border-radius: 6px;
  border: 1px solid #fed7aa;
  background: #fff7ed;
  color: #9a3412;
  font-size: 12px;
  line-height: 1.6;
}

.schema-action {
  margin-top: 10px;
}

.text-input {
  width: 100%;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #101828;
  font-size: 13px;
  line-height: 1.5;
  outline: none;
  transition: border-color 0.16s ease, box-shadow 0.16s ease;
  height: 34px;
  padding: 0 10px;
}

.text-input:focus {
  border-color: #4f46e5;
  box-shadow: 0 0 0 3px rgba(79, 70, 229, 0.12);
}

.chip-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 7px;
}

.chip-grid.compact {
  grid-template-columns: repeat(3, minmax(0, 1fr));
}

.select-chip {
  min-height: 32px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.16s ease;
}

.select-chip:hover {
  border-color: #98a2b3;
  background: #f9fafb;
}

.select-chip.active {
  border-color: #4f46e5;
  background: #eef2ff;
  color: #3730a3;
}

.custom-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 58px;
  gap: 8px;
  margin-top: 8px;
}

.field-subrow {
  margin-top: 10px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.field-subtitle {
  color: #475569;
  font-size: 11px;
  font-weight: 700;
}

.field-subhint {
  color: #94a3b8;
  font-size: 11px;
}

.mini-btn {
  height: 34px;
  padding: 0 10px;
  border: 1px solid #d0d5dd;
  border-radius: 6px;
  background: #ffffff;
  color: #344054;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
}

.mini-btn:hover {
  background: #f9fafb;
  border-color: #98a2b3;
}

.check-row {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-height: 34px;
  color: #344054;
  font-size: 13px;
  font-weight: 600;
}

.check-row input {
  width: 16px;
  height: 16px;
  accent-color: #4f46e5;
}

.field-preview {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px dashed #e2e8f0;
  display: flex;
  align-items: baseline;
  gap: 8px;
}

.field-preview-label {
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 700;
}

.field-preview-value {
  color: #334155;
  font-size: 11px;
  line-height: 1.5;
}

.generate-submit {
  margin-top: 16px;
  border-top: 1px solid #eaecf0;
  padding-top: 12px;
}

.missing-required {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
  margin-top: 14px;
  padding: 9px 10px;
  border: 1px solid #fed7aa;
  border-radius: 7px;
  background: #fff7ed;
}

.missing-required-label {
  color: #9a3412;
  font-size: 11px;
  font-weight: 800;
}

.missing-required-chip {
  padding: 2px 7px;
  border-radius: 999px;
  background: #ffffff;
  color: #c2410c;
  font-size: 10.5px;
  font-weight: 700;
}

.generate-submit p {
  margin: 8px 0 0;
  color: #98a2b3;
  font-size: 12px;
  line-height: 1.5;
}

.btn-wide {
  width: 100%;
  justify-content: center;
}

.submit-actions {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 8px;
}

.btn-half {
  width: 100%;
  justify-content: center;
}

.generate-cta {
  min-height: 38px;
}

@media (max-width: 900px) {
  .input-panel {
    position: static;
    max-height: none;
    overflow: visible;
  }

  .input-summary,
  .submit-actions {
    grid-template-columns: 1fr;
  }

  .field-subrow {
    flex-direction: column;
    align-items: flex-start;
  }

  .generate-submit {
    position: sticky;
    bottom: 0;
    z-index: 5;
    margin: 14px -6px -6px;
    padding: 10px 6px 6px;
    background: rgba(255, 255, 255, 0.96);
    backdrop-filter: blur(10px);
    box-shadow: 0 -8px 18px rgba(15, 23, 42, 0.06);
  }
}
</style>
