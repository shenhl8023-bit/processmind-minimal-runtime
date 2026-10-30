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
        <select
          v-else-if="selectedField?.options?.length && !isListOperator"
          class="rule-control rule-value"
          :value="String(leafValue ?? '')"
          @change="changeScalarValue"
        >
          <option v-if="hasUnlistedScalarValue" :value="String(leafValue)">{{ leafValue }}</option>
          <option v-for="option in selectedField.options" :key="option.value" :value="option.value">{{ option.label }}</option>
        </select>
        <input
          v-else
          class="rule-control rule-value"
          :type="isNumeric ? 'number' : 'text'"
          :value="displayValue"
          :placeholder="isListOperator ? '多个值用逗号分隔' : '条件值'"
          @input="changeValue"
        />
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
  if (['in', 'contains_any', 'contains_all'].includes(operator)) return field.options?.[0]?.value ? [field.options[0].value] : []
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
  emitLeaf(leafField.value, leafOperator.value, (event.target as HTMLSelectElement).value)
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
.condition-node { width: 100%; }

/* ===== Leaf node (field / op / value row) ===== */
.condition-node-leaf {
  display: grid;
  grid-template-columns: minmax(180px, 1.45fr) minmax(112px, .7fr) minmax(140px, 1fr);
  gap: 8px;
  align-items: center;
}

/* ===== Shared control base ===== */
.rule-control {
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  border: 1px solid #dce3ed;
  border-radius: 8px;
  background: #ffffff;
  color: #1e293b;
  font-size: 12.5px;
  outline: none;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}
.rule-control:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.1);
}
.rule-control:hover:not(:focus) {
  border-color: #c7d2fe;
}

/* ===== Between range values ===== */
.between-values {
  display: grid;
  grid-template-columns: 1fr auto 1fr;
  gap: 6px;
  align-items: center;
  color: #94a3b8;
  font-size: 12px;
}

/* ===== Logic group (all / any) ===== */
.logic-heading {
  margin-bottom: 10px;
}
.logic-select {
  font-weight: 600;
  color: #334155;
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
  color: #94a3b8;
  font-size: 12px;
  font-weight: 500;
  padding: 8px 4px;
  white-space: nowrap;
  cursor: pointer;
  transition: color 0.15s;
}
.condition-remove:hover {
  color: #ef4444;
}

/* ===== Logic chip (NOT) ===== */
.logic-chip {
  display: inline-flex;
  align-items: center;
  padding: 3px 10px;
  border-radius: 6px;
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.logic-chip-not {
  background: linear-gradient(135deg, #fff7ed, #fef3c7);
  color: #b45309;
  border: 1px solid #fde68a;
  margin-bottom: 8px;
}

/* ===== Nested logic children ===== */
.logic-children {
  display: grid;
  gap: 8px;
  padding-left: 14px;
  border-left: 2px solid #e0e7ff;
}

@media (max-width: 920px) {
  .condition-node-leaf { grid-template-columns: 1fr; }
}
</style>
