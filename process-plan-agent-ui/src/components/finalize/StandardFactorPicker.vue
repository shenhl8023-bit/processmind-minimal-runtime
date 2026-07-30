<template>
  <div class="standard-factor-picker">
    <div v-if="manualLeaf" class="factor-manual-note">
      <span class="factor-manual-name">手工布尔因子</span>
      <span>该因子不能由 CAD 自动得出</span>
    </div>
    <template v-else>
      <button
        type="button"
        class="factor-selected-row"
        :class="{ 'factor-selected-row-empty': !selectedFactor }"
        @click="open = !open"
      >
        <span v-if="selectedFactor" class="factor-selected-primary">
          <strong>{{ selectedFactor.label }}</strong>
          <span>· {{ selectedFactor.category }}</span>
        </span>
        <span v-else>请选择标准因子或创建手工因子</span>
        <small v-if="selectedFactor" :title="selectedFactor.factor_id">
          {{ selectedFactor.factor_id }}
        </small>
        <span class="factor-picker-chevron" aria-hidden="true">⌄</span>
      </button>

      <div v-if="open" class="factor-picker-panel">
        <input
          v-model="query"
          class="factor-search-input"
          type="search"
          placeholder="搜索因子名称、类别、字段或 ID"
        />
        <div class="factor-option-groups">
          <section v-for="group in factorGroups" :key="group.category" class="factor-option-group">
            <h4>{{ group.category }}</h4>
            <button
              v-for="factor in group.factors"
              :key="factor.factor_id"
              type="button"
              class="factor-option"
              @click="chooseFactor(factor)"
            >
              <span>{{ factor.label }}</span>
              <small>{{ factor.source_field }} · {{ factor.factor_id }}</small>
            </button>
          </section>
          <div v-if="!filteredFactors.length" class="factor-picker-empty">未找到匹配的标准因子</div>
        </div>
      </div>

      <button type="button" class="factor-create-manual" @click="emit('create-manual')">
        创建手工布尔因子
      </button>
    </template>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import type { RulePackageCondition, StandardFactorDefinition } from '@/api/rulePackages'
import {
  applyStandardFactor,
  factorBindingState,
  filterStandardFactors,
} from '@/utils/standardFactorBindings'

const props = defineProps<{
  modelValue: RulePackageCondition
  factors: StandardFactorDefinition[]
}>()

const emit = defineEmits<{
  'update:modelValue': [value: RulePackageCondition]
  'create-manual': []
}>()

const open = ref(false)
const query = ref('')
const manualLeaf = computed(() => (
  'field' in props.modelValue
  && props.modelValue.field.startsWith('project_factor.manual_process_')
  && props.modelValue.op === 'eq'
  && typeof props.modelValue.value === 'boolean'
))
const selectedFactor = computed(() => (
  factorBindingState(props.modelValue, props.factors).selected[0]?.factor || null
))
const filteredFactors = computed(() => filterStandardFactors(props.factors, query.value))
const factorGroups = computed(() => {
  const groups = new Map<string, StandardFactorDefinition[]>()
  filteredFactors.value.forEach((factor) => {
    groups.set(factor.category, [...(groups.get(factor.category) || []), factor])
  })
  return Array.from(groups, ([category, groupFactors]) => ({ category, factors: groupFactors }))
})

function chooseFactor(factor: StandardFactorDefinition) {
  emit('update:modelValue', applyStandardFactor(props.modelValue, factor))
  open.value = false
}
</script>

<style scoped>
.standard-factor-picker { display: grid; gap: 6px; grid-column: 1 / -1; }
.factor-selected-row { min-width: 0; min-height: 34px; display: flex; align-items: center; gap: 8px; padding: 6px 10px; border: 1px solid #ccd7e7; border-radius: 7px; background: #f7f9fd; color: #314361; text-align: left; cursor: pointer; }
.factor-selected-row-empty { border-color: #e3b76d; background: #fffaf0; color: #8a5b13; }
.factor-selected-primary { display: inline-flex; gap: 4px; align-items: baseline; }
.factor-selected-row small { margin-left: auto; color: #7c899d; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.factor-picker-chevron { color: #718096; }
.factor-picker-panel { padding: 8px; border: 1px solid #d9e0e9; border-radius: 8px; background: #fff; box-shadow: 0 8px 22px rgba(40, 55, 82, .12); }
.factor-search-input { width: 100%; height: 32px; padding: 0 9px; border: 1px solid #d9e0e9; border-radius: 6px; outline: none; }
.factor-option-groups { max-height: 260px; overflow: auto; margin-top: 7px; }
.factor-option-group h4 { margin: 8px 4px 3px; color: #718096; font-size: 11px; }
.factor-option { width: 100%; display: grid; gap: 2px; padding: 7px 8px; border: 0; border-radius: 6px; background: transparent; color: #253247; text-align: left; cursor: pointer; }
.factor-option:hover { background: #eef3fb; }
.factor-option small { color: #7c899d; font-family: ui-monospace, SFMono-Regular, Consolas, monospace; }
.factor-picker-empty { padding: 10px; color: #8792a5; text-align: center; }
.factor-create-manual { justify-self: start; padding: 2px 0; border: 0; background: transparent; color: #5269a8; font-size: 12px; cursor: pointer; }
.factor-manual-note { display: flex; align-items: center; gap: 8px; min-height: 34px; padding: 6px 10px; border-radius: 7px; background: #fff8e8; color: #765315; }
.factor-manual-name { font-weight: 700; }
</style>
