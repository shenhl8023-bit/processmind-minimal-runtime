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
        <span class="logic-chip">{{ nodeKind === 'all' ? '同时满足' : '满足任一' }}</span>
      </div>
      <div class="logic-children">
        <RuleConditionNodeEditor
          v-for="(child, index) in groupChildren"
          :key="index"
          :model-value="child"
          :fields="fields"
          @update:model-value="updateGroupChild(index, $event)"
        />
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
  if ('all' in props.modelValue) return 'all'
  if ('any' in props.modelValue) return 'any'
  if ('not' in props.modelValue) return 'not'
  return 'leaf'
})

const leafField = computed(() => 'field' in props.modelValue ? props.modelValue.field : '')
const leafOperator = computed(() => 'op' in props.modelValue ? props.modelValue.op : '')
const leafValue = computed(() => 'value' in props.modelValue ? props.modelValue.value : undefined)
const selectedField = computed(() => props.fields.find(field => field.key === leafField.value))
const isNumeric = computed(() => selectedField.value?.type === 'number')
const isListOperator = computed(() => ['in', 'contains_any', 'contains_all'].includes(leafOperator.value))
const displayValue = computed(() => Array.isArray(leafValue.value) ? leafValue.value.join('，') : String(leafValue.value ?? ''))
const betweenValues = computed(() => Array.isArray(leafValue.value) ? leafValue.value : ['', ''])
const groupChildren = computed(() => {
  if ('all' in props.modelValue) return props.modelValue.all
  if ('any' in props.modelValue) return props.modelValue.any
  return []
})
const notChild = computed(() => 'not' in props.modelValue ? props.modelValue.not : ({ field: props.fields[0]?.key || '', op: 'eq', value: '' } as RulePackageCondition))
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
  if (isNumeric.value) return value === '' ? 0 : Number(value)
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

function updateNotChild(value: RulePackageCondition) {
  emit('update:modelValue', { not: value })
}
</script>

<style scoped>
.condition-node { width: 100%; }
.condition-node-leaf { display: grid; grid-template-columns: minmax(180px, 1.45fr) minmax(112px, .7fr) minmax(140px, 1fr); gap: 8px; align-items: center; }
.rule-control { min-width: 0; height: 34px; padding: 0 10px; border: 1px solid #d9e0e9; border-radius: 7px; background: #fff; color: #253247; font-size: 12px; outline: none; }
.rule-control:focus { border-color: #5269a8; box-shadow: 0 0 0 3px rgba(82, 105, 168, .1); }
.between-values { display: grid; grid-template-columns: 1fr auto 1fr; gap: 6px; align-items: center; color: #718096; }
.logic-heading { margin-bottom: 8px; }
.logic-chip { display: inline-flex; padding: 3px 8px; border-radius: 999px; background: #e8edf7; color: #40557d; font-size: 11px; font-weight: 700; }
.logic-chip-not { background: #fff0e7; color: #9a4b22; margin-bottom: 8px; }
.logic-children { display: grid; gap: 8px; padding-left: 12px; border-left: 2px solid #dce4f0; }
@media (max-width: 920px) { .condition-node-leaf { grid-template-columns: 1fr; } }
</style>
