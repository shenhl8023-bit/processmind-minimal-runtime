<template>
  <div class="condition-node" :class="`condition-node-${nodeKind}`">
    <template v-if="nodeKind === 'leaf'">
      <select class="rule-control rule-field" :value="leafField" @change="changeField">
        <optgroup v-for="group in fieldGroups" :key="group.category" :label="group.category">
          <option v-for="field in group.fields" :key="field.key" :value="field.key">
            {{ field.label }}{{ field.unit ? ` (${field.unit})` : '' }}
          </option>
        </optgroup>
      </select>
      <select class="rule-control rule-operator" :value="leafOperator" @change="changeOperator">
        <option v-for="operator in selectedField?.operators || []" :key="operator" :value="operator">
          {{ operatorLabel(operator) }}
        </option>
      </select>
      <template v-if="!['exists', 'not_exists'].includes(leafOperator)">
        <div v-if="selectedField?.options?.length && isListOperator" class="list-values">
          <select class="rule-control rule-values" multiple aria-label="条件候选值，可多选" @change="changeListValues">
            <option v-for="option in listOptions" :key="option.value" :value="option.value" :selected="Array.isArray(leafValue) && leafValue.includes(option.value)">{{ option.label }}</option>
          </select>
          <input v-if="selectedField.allow_custom" class="rule-control" type="text" placeholder="填写其它值，回车添加" @keydown.enter.prevent="addCustomListValue" />
        </div>
        <div v-if="leafOperator === 'between'" class="between-values">
          <input class="rule-control rule-value" :type="isNumeric ? 'number' : 'text'" :value="betweenValues[0]" @input="changeBetween(0, $event)" />
          <span>至</span>
          <input class="rule-control rule-value" :type="isNumeric ? 'number' : 'text'" :value="betweenValues[1]" @input="changeBetween(1, $event)" />
        </div>
        <select
          v-else-if="selectedField?.type === 'boolean'"
          class="rule-control rule-value"
          :value="String(Boolean(leafValue))"
          @change="changeBooleanValue"
        >
          <option value="true">是</option>
          <option value="false">否</option>
        </select>
        <input v-else-if="selectedField?.allow_custom && selectedField.key === 'project_factor.material_grade' && !isListOperator" class="rule-control rule-value" :value="displayValue" :list="`condition-options-${leafField}`" type="text" placeholder="选择或填写其它牌号" @input="changeValue" />
        <select
          v-else-if="selectedField?.options?.length && !isListOperator"
          class="rule-control rule-value"
          :value="String(leafValue ?? '')"
          @change="changeScalarValue"
        >
          <option disabled value="">请选择</option>
          <option v-if="hasUnlistedScalarValue" :value="String(leafValue)">{{ leafValue }}</option>
          <option v-for="option in selectedField.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <input
          v-else-if="!selectedField?.options?.length || !isListOperator"
          class="rule-control rule-value"
          :type="isNumeric ? 'number' : 'text'"
          :value="displayValue"
          :placeholder="isListOperator ? '多个值用逗号分隔' : '条件值'"
          @input="changeValue"
        />
        <input v-if="selectedField?.allow_custom && selectedField.options?.length && selectedField.key !== 'project_factor.material_grade' && !isListOperator" class="rule-control custom-scalar-value" :value="displayValue" placeholder="填写其它值" @input="changeValue" />
        <datalist v-if="selectedField?.allow_custom && !isListOperator" :id="`condition-options-${leafField}`"><option v-for="option in selectedField.options" :key="option.value" :value="option.value">{{ option.label }}</option></datalist>
      </template>
    </template>

    <template v-else-if="nodeKind === 'not'">
      <span class="logic-chip logic-chip-not">不满足</span>
      <RuleConditionNodeEditor
        :model-value="notChild"
        :fields="fields"
        @update:model-value="updateNotChild"
      />
    </template>

    <template v-else>
      <div class="logic-heading">
        <select class="rule-control logic-select" aria-label="条件满足方式" :value="nodeKind" @change="changeGroupKind">
          <option value="all">全部满足</option>
          <option value="any">满足其一</option>
        </select>
      </div>
      <div class="logic-children">
        <div v-for="(child, index) in groupChildren" :key="index" class="logic-child-row">
          <RuleConditionNodeEditor :model-value="child" :fields="fields" @update:model-value="updateGroupChild(Number(index), $event)" />
          <button type="button" class="condition-remove" @click="removeGroupChild(Number(index))">删除条件</button>
        </div>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanonicalConditionField, RulePackageCondition } from '@/api/rulePackages'

const props = defineProps<{
  modelValue: RulePackageCondition
  fields: CanonicalConditionField[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RulePackageCondition]
}>()

const nodeKind = computed<'leaf' | 'all' | 'any' | 'not'>(() => {
  if (Array.isArray((props.modelValue as any)?.all)) return 'all'
  if (Array.isArray((props.modelValue as any)?.any)) return 'any'
  if ((props.modelValue as any)?.not) return 'not'
  return 'leaf'
})

const leafField = computed(() => {
  const v = (props.modelValue as any)?.field
  return typeof v === 'string' ? v : ''
})
const leafOperator = computed(() => {
  const v = (props.modelValue as any)?.op
  return typeof v === 'string' ? v : ''
})
const leafValue = computed(() => (props.modelValue as any)?.value)
const selectedField = computed(() => props.fields.find(field => field.key === leafField.value))
const hasUnlistedScalarValue = computed(() => leafValue.value !== null && leafValue.value !== undefined && !Array.isArray(leafValue.value) && !selectedField.value?.options?.some(option => option.value === String(leafValue.value)))
const isNumeric = computed(() => selectedField.value?.type === 'number')
const isListOperator = computed(() => ['in', 'contains_any', 'contains_all'].includes(leafOperator.value))
const listOptions = computed(() => {
  const options = [...(selectedField.value?.options || [])]
  for (const value of Array.isArray(leafValue.value) ? leafValue.value : []) if (!options.some(option => option.value === value)) options.push({ value, label: value })
  return options
})
const displayValue = computed(() => Array.isArray(leafValue.value) ? leafValue.value.join('，') : String(leafValue.value ?? ''))
const betweenValues = computed(() => Array.isArray(leafValue.value) ? leafValue.value : ['', ''])
const groupChildren = computed(() => {
  if (Array.isArray((props.modelValue as any)?.all)) return (props.modelValue as any).all
  if (Array.isArray((props.modelValue as any)?.any)) return (props.modelValue as any).any
  return []
})
const notChild = computed(() => (props.modelValue as any)?.not || ({ field: props.fields[0]?.key || '', op: 'eq', value: '' } as RulePackageCondition))
const fieldGroups = computed(() => {
  const groups = new Map<string, CanonicalConditionField[]>()
  props.fields.forEach((field) => groups.set(field.category, [...(groups.get(field.category) || []), field]))
  return Array.from(groups, ([category, fields]) => ({ category, fields }))
})

function operatorLabel(operator: string) {
  return ({
    eq: '等于', neq: '不等于', in: '属于列表', contains: '包含', contains_any: '包含任一',
    contains_all: '包含全部', gt: '大于', gte: '大于等于', lt: '小于', lte: '小于等于',
    between: '介于', exists: '已填写', not_exists: '未填写',
  } as Record<string, string>)[operator] || operator
}

function defaultValue(field: CanonicalConditionField, operator: string) {
  if (['exists', 'not_exists'].includes(operator)) return undefined
  if (operator === 'between') return field.type === 'number' ? [0, 1] : ['', '']
  if (['in', 'contains_any', 'contains_all'].includes(operator)) return []
  if (field.type === 'number') return field.validation?.min ?? 0
  if (field.type === 'boolean') return true
  return field.options?.[0]?.value || ''
}

function emitLeaf(field: string, op: string, value: unknown) {
  const next: Record<string, unknown> = { field, op }
  if (!['exists', 'not_exists'].includes(op)) next.value = value
  emit('update:modelValue', next as RulePackageCondition)
}

function changeField(event: Event) {
  const key = (event.target as HTMLSelectElement).value
  const field = props.fields.find(item => item.key === key)
  if (!field) return
  const operator = field.operators[0] || 'eq'
  emitLeaf(key, operator, defaultValue(field, operator))
}

function changeOperator(event: Event) {
  const operator = (event.target as HTMLSelectElement).value
  if (!selectedField.value) return
  emitLeaf(leafField.value, operator, defaultValue(selectedField.value, operator))
}

function normalizeValue(value: string) {
  if (isNumeric.value) return value.trim() === '' ? '' : Number(value)
  return value
}

function changeValue(event: Event) {
  const raw = (event.target as HTMLInputElement).value
  const value = isListOperator.value
    ? raw.split(/[，,]/).map(item => item.trim()).filter(Boolean)
    : normalizeValue(raw)
  emitLeaf(leafField.value, leafOperator.value, value)
}

function changeScalarValue(event: Event) {
  emitLeaf(leafField.value, leafOperator.value, normalizeValue((event.target as HTMLSelectElement).value))
}

function changeListValues(event: Event) {
  emitLeaf(leafField.value, leafOperator.value, Array.from((event.target as HTMLSelectElement).selectedOptions, option => option.value))
}
function addCustomListValue(event: Event) {
  const input = event.target as HTMLInputElement
  const value = input.value.trim()
  if (value) emitLeaf(leafField.value, leafOperator.value, [...new Set([...(Array.isArray(leafValue.value) ? leafValue.value : []), value])])
  input.value = ''
}

function changeBooleanValue(event: Event) {
  emitLeaf(leafField.value, leafOperator.value, (event.target as HTMLSelectElement).value === 'true')
}

function changeBetween(index: number, event: Event) {
  const values = [...betweenValues.value]
  values[index] = normalizeValue((event.target as HTMLInputElement).value)
  emitLeaf(leafField.value, leafOperator.value, values)
}

function updateGroupChild(index: number, value: RulePackageCondition) {
  const children = [...groupChildren.value]
  children[index] = value
  emit('update:modelValue', nodeKind.value === 'all' ? { all: children } : { any: children })
}
function changeGroupKind(event: Event) {
  emit('update:modelValue', (event.target as HTMLSelectElement).value === 'any' ? { any: [...groupChildren.value] } : { all: [...groupChildren.value] })
}
function removeGroupChild(index: number) {
  const children = groupChildren.value.filter((_: RulePackageCondition, position: number) => position !== index)
  emit('update:modelValue', nodeKind.value === 'all' ? { all: children } : { any: children })
}

function updateNotChild(value: RulePackageCondition) {
  emit('update:modelValue', { not: value })
}
</script>

<style scoped>
.condition-node { width: 100%; min-width: 0; }
.list-values { display: grid; gap: 5px; min-width: 0; }
.list-values .rule-values { height: auto; min-height: 88px; padding: 5px; width: 100%; }

/* ===== Leaf node (field / op / value row) ===== */
.condition-node-leaf {
  display: grid;
  grid-template-columns: minmax(0, 1.3fr) minmax(100px, .7fr) minmax(0, 1fr);
  gap: 8px;
  align-items: center;
}

/* ===== Shared control base ===== */
.rule-control {
  min-width: 0;
  height: var(--pm-control-height);
  padding: 0 10px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-control);
  background: var(--pm-surface);
  color: var(--pm-text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.rule-control:focus {
  border-color: var(--pm-primary-border);
  box-shadow: var(--pm-focus-ring);
}
.rule-control:hover:not(:focus) {
  border-color: var(--pm-primary-border);
}

/* ===== Between range values ===== */
.between-values {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 6px;
  align-items: center;
  color: var(--pm-text-muted);
  font-size: 12px;
}

/* ===== Logic group (all / any) ===== */
.logic-heading {
  margin-bottom: 10px;
}
.logic-select {
  font-weight: 600;
  color: var(--pm-text-secondary);
}
.logic-child-row {
  display: flex;
  align-items: start;
  gap: 8px;
}

/* ===== Delete condition button ===== */
.condition-remove {
  border: 0;
  background: transparent;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 500;
  padding: 8px 4px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s;
}
.condition-remove:hover {
  color: var(--pm-danger);
}

/* ===== Logic chip (NOT) ===== */
.logic-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.logic-chip-not {
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  border: 1px solid var(--pm-warning-border);
  margin-bottom: 8px;
}

/* ===== Nested logic children ===== */
.logic-children {
  display: grid;
  gap: 8px;
  padding-left: 14px;
  border-left: 2px solid var(--pm-primary-soft);
}

@media (max-width: 920px) {
  .condition-node-leaf { grid-template-columns: 1fr; }
}
.rule-control { width: 100%; font-size: 13px; }
.rule-control[multiple] { line-height: 22px; }
.rule-control option { padding: 3px 6px; }
.custom-scalar-value { grid-column: 3; }
.between-values { min-width: 0; grid-template-columns: minmax(0, 1fr) auto minmax(0, 1fr); }
.logic-child-row > .condition-node { flex: 1 1 auto; min-width: 0; }
.condition-remove { min-height: 28px; padding: 4px 6px; border-radius: var(--pm-radius-control); color: var(--pm-danger); }
.condition-remove:hover { color: var(--pm-danger); background: var(--pm-danger-soft); }
.condition-remove:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.rule-control:disabled { color: var(--pm-disabled-text); background: var(--pm-disabled-bg); }
@media (max-width: 920px) { .custom-scalar-value { grid-column: 1; } }
</style>
