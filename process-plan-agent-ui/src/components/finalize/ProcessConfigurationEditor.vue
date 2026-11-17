<template>
  <div class="configuration-editor" :inert="disabled">
    <div class="configuration-topline">
      <div class="configuration-label">
        <span>出现方式</span>
        <details class="configuration-help">
          <summary aria-label="出现方式说明">?</summary>
          <span>每道工序只选择一种出现方式，修改保存后生效。</span>
        </details>
      </div>
      <div class="configuration-modes" role="group" :aria-label="`${displayName}的出现方式`">
        <button v-for="mode in modes" :key="mode.value" type="button" class="configuration-mode" :aria-pressed="!needsReset && configuration.occurrence === mode.value" :disabled="disabled" @click="changeMode(mode.value)">{{ mode.label }}</button>
      </div>
    </div>
    <p v-if="needsReset" class="configuration-error" role="alert">此规则包含当前出现模式不支持的内容，请选择一种出现模式重新设置。原规则在保存前保持不变。</p>
    <template v-else>
      <label v-if="configuration.occurrence === 'manual'" class="configuration-manual">
        <span>验证时显示</span>
        <input :id="`manual-bool-label-${item.segment.id}`" class="manual-bool-input" :value="manualLabel" maxlength="40" :disabled="disabled" @input="changeManualLabel(($event.target as HTMLInputElement).value)" />
        <span class="configuration-note">默认不勾选，不选就是否；勾选后生成。</span>
      </label>
      <div v-if="configuration.occurrence === 'conditional'" class="configuration-conditions">
        <div class="configuration-heading">
          <div class="configuration-heading-copy">
            <span class="configuration-heading-title">出现条件</span>
            <span class="configuration-heading-hint">全部满足才安排 · 特征与方位对应同一加工对象</span>
          </div>
          <button type="button" class="configuration-link" :disabled="disabled || !fields.length" @click="addCondition">＋ 添加条件</button>
        </div>
        <div v-if="triples.length" class="configuration-column-labels" aria-hidden="true"><span>判断项目</span><span>关系</span><span>取值</span><span></span></div>
        <div v-for="(condition, index) in triples" :key="index" class="configuration-condition-row">
          <RuleConditionNodeEditor :model-value="condition" :fields="visibleFields" @update:model-value="updateCondition(index, $event)" />
          <button type="button" class="configuration-link" :disabled="disabled" :aria-label="`删除第${index + 1}条条件`" @click="removeCondition(index)">删除条件</button>
        </div>
      </div>
      <div v-if="configuration.occurrence === 'associated'" class="configuration-relations">
        <label class="configuration-heading" :for="`associated-source-${item.segment.id}`">跟随工序</label>
        <select :id="`associated-source-${item.segment.id}`" class="configuration-select" aria-label="跟随工序" :value="configuration.relations[0]?.source_process_ids[0] || ''" :disabled="disabled" @change="changeSource(($event.target as HTMLSelectElement).value)">
          <option disabled value="">选择一个来源工序</option>
          <option v-for="process in otherProcesses" :key="process.process_id" :value="process.process_id">{{ process.display_name }}</option>
        </select>
      </div>
    </template>
    <p v-if="error && !needsReset" class="configuration-error" :class="{ 'configuration-error-empty': configuration.occurrence === 'conditional' && !triples.length }" role="alert">{{ error }}</p>
    <div v-if="!error && !staleSource" class="configuration-result">
      <p>{{ configuration.occurrence === 'associated' ? `${associationSource}纳入路线时，自动生成${displayName}，并排在${associationSource}之后。` : summary }}</p>
      <p v-if="configuration.occurrence === 'associated'" class="configuration-note">允许穿插其他工序，支持逐级带出。</p>
    </div>
    <p v-if="staleSource" class="configuration-error" role="alert">原文已更新，请先取消修改后核对最新规则。</p>
    <div class="candidate-footer">
      <slot name="secondary-actions" />
      <div class="configuration-primary-actions">
        <button type="button" class="cancel-rule-btn" :disabled="disabled" @click="emit('cancel')">取消</button>
        <button type="button" class="confirm-rule-btn" :disabled="disabled || Boolean(error) || staleSource" @click="save">保存并确认</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanonicalConditionField, ProcessConfiguration, RuleConditionCandidate, RuleConditionProcessOption, RulePackageCondition } from '@/api/rulePackages'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { buildManualBooleanRuleCandidate, defaultManualBooleanLabel } from '@/utils/finalizeRulePackage'
import { configurationError, configurationSummary, configurationNeedsReset, conditionTriples, validateAuthoredCandidate } from '@/utils/processConfigurationEditor'
import RuleConditionNodeEditor from '@/components/finalize/RuleConditionNodeEditor.vue'
import { projectConditionDisplayLabel } from '@/utils/projectConditionFields'

const props = defineProps<{ modelValue: RuleConditionCandidate; item: FinalizeCard; displayName: string; fields: CanonicalConditionField[]; processes: RuleConditionProcessOption[]; disabled?: boolean; staleSource?: boolean; requireModeSelection?: boolean; section?: 'appearance' | 'relations' }>()
const emit = defineEmits<{ 'update:modelValue': [value: RuleConditionCandidate]; save: [value: RuleConditionCandidate]; cancel: [] }>()
const configuration = computed(() => props.modelValue.configuration!)
const needsReset = computed(() => props.requireModeSelection || configurationNeedsReset(configuration.value) || Boolean(props.modelValue.when || props.modelValue.then || props.modelValue.relation))
const triples = computed(() => conditionTriples(configuration.value.when) || [])
// Presentation copies keep frozen definitions intact for validation and saving.
const visibleFields = computed(() => props.fields.map(field => ({ ...field, label: projectConditionDisplayLabel(field, props.item.segment.normalized_step_name) })))
const modeDrafts = new Map<ProcessConfiguration['occurrence'], RuleConditionCandidate>()
const modes: { value: ProcessConfiguration['occurrence']; label: string }[] = [
  { value: 'always', label: '主工序' }, { value: 'manual', label: 'Bool 工序' },
  { value: 'conditional', label: '条件工序' }, { value: 'associated', label: '关联工序' },
]
const otherProcesses = computed(() => props.processes.filter(process => process.process_id !== configuration.value.process_id))
const associationSource = computed(() => {
  const sourceId = configuration.value.relations[0]?.source_process_ids[0]
  return props.processes.find(process => process.process_id === sourceId)?.display_name || sourceId
})
const manualLabel = computed(() => { const when = configuration.value.when; return props.modelValue.field_definitions?.find(field => when && 'field' in when && field.key === when.field)?.label ?? defaultManualBooleanLabel(props.item) })
const executionConfiguration = computed(() => {
  if (configuration.value.occurrence !== 'conditional') return configuration.value
  const rows = triples.value
  const when = rows.length ? rows.length === 1 ? rows[0]! : { all: rows } : null
  return { ...configuration.value, when }
})
const error = computed(() => needsReset.value ? '请选择一种出现模式重新设置。' : configurationError(executionConfiguration.value, manualLabel.value) || validateAuthoredCandidate({ ...props.modelValue, configuration: executionConfiguration.value }, configuration.value.process_id)[0] || '')
const summary = computed(() => configurationSummary(executionConfiguration.value, props.displayName, visibleFields.value, props.processes))
function clone<T>(value: T): T { return JSON.parse(JSON.stringify(value)) }
function referencedFields(condition: RulePackageCondition | null): Set<string> {
  if (!condition) return new Set()
  if ('all' in condition && Array.isArray(condition.all)) return new Set(condition.all.flatMap(child => [...referencedFields(child)]))
  return 'field' in condition && condition.field ? new Set([condition.field]) : new Set()
}
function update(patch: Partial<ProcessConfiguration>, fields = props.modelValue.field_definitions) {
  if (props.disabled) return
  const next = { ...configuration.value, ...patch }
  const definitions = new Map([...props.fields, ...(props.modelValue.field_definitions || []), ...(fields || [])].map(field => [field.key, field]))
  emit('update:modelValue', { kind: 'process_configuration', preview: '', field_definitions: [...definitions.values()], configuration: next })
}
function changeMode(occurrence: ProcessConfiguration['occurrence']) {
  if (props.disabled || (occurrence === configuration.value.occurrence && !needsReset.value)) return
  if (!needsReset.value) modeDrafts.set(configuration.value.occurrence, clone(props.modelValue))
  const restored = modeDrafts.get(occurrence)
  if (restored) {
    const definitions = new Map([...(props.modelValue.field_definitions || []), ...(restored.field_definitions || [])].map(field => [field.key, field]))
    emit('update:modelValue', { ...clone(restored), field_definitions: [...definitions.values()] }); return
  }
  if (occurrence === 'manual') {
    const candidate = buildManualBooleanRuleCandidate(props.item, defaultManualBooleanLabel(props.item))
    update({ occurrence, relations: [], when: candidate.when || null }, candidate.field_definitions)
  } else update({ occurrence, relations: [], when: null }, [])
}
function changeManualLabel(label: string) {
  const candidate = buildManualBooleanRuleCandidate(props.item, label)
  update({ when: candidate.when || null }, candidate.field_definitions?.map(field => ({ ...field, label })))
}
function setTriples(rows: RulePackageCondition[]) { update({ when: rows.length ? rows.length === 1 ? rows[0]! : { all: rows } : null }) }
function addCondition() {
  const field = visibleFields.value[0]
  if (!field) return
  const op = field.operators[0] || 'eq'
  const leaf: RulePackageCondition = { field: field.key, op, ...(['exists', 'not_exists'].includes(op) ? {} : {value: field.type === 'boolean' ? true : ['in', 'contains_any', 'contains_all'].includes(op) ? [] : ''}) }
  setTriples([...triples.value, leaf])
}
function updateCondition(index: number, condition: RulePackageCondition) { setTriples(triples.value.map((row, i) => i === index ? condition : row)) }
function removeCondition(index: number) { setTriples(triples.value.filter((_, i) => i !== index)) }
function changeSource(source: string) {
  update({ relations: source ? [{ relation_type: 'trigger_after', source_process_ids: [source], target_process_ids: [configuration.value.process_id], source_match: 'all' }] : [] })
}
function save() {
  if (error.value || props.disabled || props.staleSource) return
  const when = executionConfiguration.value.when
  const used = referencedFields(when)
  const definitions = new Map(clone([...props.fields, ...(props.modelValue.field_definitions || [])]).map(field => [field.key, field]))
  for (const row of conditionTriples(when) || []) {
    if (!('field' in row) || row.field !== 'project_factor.material_grade') continue
    const definition = definitions.get(row.field)
    if (!definition?.allow_custom) continue
    definition.options = definition.options || []
    const values = Array.isArray(row.value) ? row.value : [row.value]
    for (const value of values) if (typeof value === 'string' && value.trim() && !definition.options.some(option => option.value === value)) definition.options.push({ value, label: value })
  }
  emit('save', { ...clone(props.modelValue), configuration: clone(executionConfiguration.value), field_definitions: [...definitions.values()].filter(field => used.has(field.key) && field.key.startsWith('project_factor.')), preview: summary.value })
}
</script>

<style scoped>
.configuration-editor { container: process-configuration / inline-size; display: grid; gap: 12px; min-width: 0; margin-top: 8px; padding: 14px; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-card); background: var(--pm-surface); }
.configuration-topline { display: flex; align-items: center; gap: 16px; min-width: 0; }
.configuration-label { display: flex; align-items: center; gap: 4px; flex: 0 0 84px; font-size: 12px; font-weight: 600; color: var(--pm-text-secondary); white-space: nowrap; }
.configuration-label > span, .configuration-help { flex-shrink: 0; }
.configuration-help { position: relative; font-weight: 400; }
.configuration-help summary { display: grid; place-items: center; width: 20px; height: 20px; border: 1px solid var(--pm-border); border-radius: 50%; color: var(--pm-text-muted); font-size: 11px; cursor: pointer; list-style: none; }
.configuration-help summary::-webkit-details-marker { display: none; }
.configuration-help > span { position: absolute; left: 0; top: 26px; z-index: 3; width: 220px; padding: 10px 12px; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-control); background: var(--pm-surface); box-shadow: var(--pm-shadow-popup); line-height: 1.5; }
.configuration-modes { display: inline-flex; flex-wrap: wrap; gap: 3px; min-width: 0; padding: 3px; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-control); background: var(--pm-surface-subtle); }
.configuration-mode { min-height: 28px; padding: 3px 14px; border: 1px solid transparent; border-radius: 4px; background: transparent; color: var(--pm-text-secondary); font-size: 12px; line-height: 20px; cursor: pointer; }
.configuration-mode:hover { color: var(--pm-primary); background: var(--pm-surface); }
.configuration-mode[aria-pressed=true] { border-color: var(--pm-primary-border); background: var(--pm-surface); color: var(--pm-primary); font-weight: 600; box-shadow: 0 1px 2px rgba(35, 53, 74, .06); }
.configuration-conditions, .configuration-relations { min-width: 0; padding-top: 12px; border-top: 1px solid var(--pm-border); }
.configuration-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px 12px; min-width: 0; margin-bottom: 8px; color: var(--pm-text-secondary); font-size: 12px; font-weight: 600; }
.configuration-heading-copy { display: flex; align-items: baseline; flex-wrap: wrap; gap: 4px 10px; min-width: 0; }
.configuration-heading-title { white-space: nowrap; color: var(--pm-text); }
.configuration-heading-hint { color: var(--pm-text-muted); font-size: 12px; font-weight: 400; line-height: 18px; }
.configuration-column-labels { display: grid; grid-template-columns: minmax(0, 1.1fr) minmax(100px, .72fr) minmax(0, 1fr) 54px; gap: 7px; padding: 0 9px 5px; color: var(--pm-text-muted); font-size: 11px; }
.configuration-condition-row { display: flex; align-items: flex-start; gap: 7px; padding: 8px; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-control); background: var(--pm-surface-subtle); }
.configuration-condition-row + .configuration-condition-row { margin-top: 6px; }
.configuration-condition-row > :first-child { flex: 1 1 auto; min-width: 0; }
.configuration-condition-row > .configuration-link { flex: 0 0 54px; margin-top: 2px; color: var(--pm-text-muted); }
.configuration-condition-row > .configuration-link:hover { color: var(--pm-danger); }
.configuration-condition-row :deep(.condition-node-leaf) { grid-template-columns: minmax(0, 1.1fr) minmax(100px, .72fr) minmax(0, 1fr); gap: 7px; }
.configuration-condition-row :deep(.rule-control) { height: 30px; min-width: 0; padding: 4px 8px; border-radius: var(--pm-radius-control); border-color: var(--pm-border-strong); background: var(--pm-surface); color: var(--pm-text); font-size: 12px; }
.configuration-condition-row :deep(.rule-control[multiple]) { height: auto; min-height: 76px; padding: 4px; line-height: 22px; }
.configuration-condition-row :deep(.custom-scalar-value) { grid-column: 3; }
.configuration-condition-row :deep(.rule-control:focus) { border-color: var(--pm-primary); box-shadow: var(--pm-focus-ring); }
.configuration-condition-row :deep(.logic-heading) { margin-bottom: 6px; }
.configuration-condition-row :deep(.logic-children) { gap: 6px; padding-left: 10px; border-color: var(--pm-border); }
.configuration-condition-row :deep(.logic-child-row) { align-items: center; gap: 5px; }
.configuration-condition-row :deep(.condition-remove) { padding: 4px 2px; font-size: 12px; }
.configuration-link { width: fit-content; min-height: 26px; padding: 3px; border: 0; background: transparent; color: var(--pm-primary); font-size: 12px; font-weight: 500; line-height: 20px; cursor: pointer; white-space: nowrap; }
.configuration-link:hover { color: var(--pm-primary-hover); }
.configuration-manual { display: grid; grid-template-columns: 84px minmax(180px, 1fr); align-items: center; gap: 6px 16px; color: var(--pm-text-secondary); font-size: 12px; }
.configuration-manual .configuration-note { grid-column: 2; }
.configuration-relations { display: grid; grid-template-columns: 84px minmax(0, 360px); align-items: center; gap: 16px; }
.configuration-relations .configuration-heading { margin: 0; }
.configuration-select, .manual-bool-input { width: 100%; min-width: 0; height: 30px; padding: 4px 8px; border: 1px solid var(--pm-border-strong); border-radius: var(--pm-radius-control); background: var(--pm-surface); color: var(--pm-text); font-size: 12px; outline: none; }
.configuration-select:focus, .manual-bool-input:focus { border-color: var(--pm-primary); box-shadow: var(--pm-focus-ring); }
.configuration-result { padding: 8px 10px; border-left: 2px solid var(--pm-primary-border); background: var(--pm-surface-subtle); color: var(--pm-text-secondary); font-size: 12px; line-height: 20px; }
.configuration-result p { margin: 0; }
.configuration-note { margin: 0; color: var(--pm-text-muted); font-size: 12px; line-height: 18px; }
.configuration-error { margin: 0; padding: 7px 10px; border: 1px solid var(--pm-danger-border); border-radius: var(--pm-radius-control); background: var(--pm-danger-soft); color: var(--pm-danger); font-size: 12px; line-height: 20px; overflow-wrap: anywhere; }
.configuration-error-empty { border-style: dashed; border-color: var(--pm-border-strong); background: var(--pm-surface-subtle); color: var(--pm-text-muted); }
.candidate-footer { display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px; padding-top: 10px; border-top: 1px solid var(--pm-border); }
.configuration-primary-actions { display: flex; align-items: center; gap: 6px; margin-left: auto; }
.confirm-rule-btn, .cancel-rule-btn { min-height: 28px; padding: 3px 12px; border: 1px solid var(--pm-border-strong); border-radius: var(--pm-radius-control); background: var(--pm-surface); color: var(--pm-text-secondary); font-size: 12px; line-height: 20px; font-weight: 500; white-space: nowrap; cursor: pointer; }
.cancel-rule-btn:hover:not(:disabled) { background: var(--pm-surface-subtle); }
.confirm-rule-btn { border-color: var(--pm-primary); background: var(--pm-primary); color: #fff; }
.confirm-rule-btn:hover:not(:disabled) { border-color: var(--pm-primary-hover); background: var(--pm-primary-hover); }
button:disabled { opacity: .45; cursor: not-allowed; }
button:focus-visible, summary:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
@container process-configuration (max-width: 560px) {
  .configuration-column-labels { display: none; }
  .configuration-condition-row :deep(.condition-node-leaf) { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); }
  .configuration-condition-row :deep(.condition-node-leaf > :first-child) { grid-column: 1 / -1; }
  .configuration-condition-row :deep(.custom-scalar-value) { grid-column: 1 / -1; }
}
@media (max-width: 700px) {
  .configuration-editor { padding: 10px; }
}
@container process-configuration (max-width: 400px) {
  .configuration-topline { align-items: stretch; flex-direction: column; gap: 8px; }
  .configuration-label { flex-basis: auto; }
  .configuration-modes { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); }
  .configuration-mode { padding-left: 5px; padding-right: 5px; }
  .configuration-heading { align-items: flex-start; }
  .configuration-heading-copy { flex-direction: column; }
  .configuration-column-labels { display: none; }
  .configuration-manual, .configuration-relations { grid-template-columns: minmax(0, 1fr); gap: 6px; }
  .configuration-manual .configuration-note { grid-column: 1; }
  .configuration-condition-row { flex-direction: column; gap: 4px; }
  .configuration-condition-row > :first-child { width: 100%; }
  .configuration-condition-row > .configuration-link { flex-basis: auto; align-self: flex-end; }
  .configuration-condition-row :deep(.condition-node-leaf) { grid-template-columns: minmax(0, 1fr); }
  .configuration-condition-row :deep(.custom-scalar-value) { grid-column: 1; }
  .configuration-condition-row :deep(.logic-child-row) { align-items: stretch; flex-direction: column; }
}
</style>
