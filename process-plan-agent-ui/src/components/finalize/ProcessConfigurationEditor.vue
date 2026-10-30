<template>
  <div class="configuration-editor" :inert="disabled">
    <div v-if="section !== 'relations'" class="configuration-topline">
      <div class="configuration-modes" role="group" :aria-label="`${displayName}的出现方式`">
        <button v-for="mode in modes" :key="mode.value" type="button" class="configuration-mode" :aria-pressed="configuration.occurrence === mode.value" :disabled="disabled" @click="changeMode(mode.value)">{{ mode.label }}</button>
      </div>
      <p v-if="configuration.occurrence === 'always'" class="configuration-note">每次生成路线都纳入{{ displayName }}。</p>
    </div>
    <label v-if="section !== 'relations' && configuration.occurrence === 'manual'" class="configuration-manual">
      <span>生成时询问</span>
      <input :id="`manual-bool-label-${item.segment.id}`" class="manual-bool-input" :value="manualLabel" maxlength="40" @input="changeManualLabel(($event.target as HTMLInputElement).value)" />
      <span class="configuration-note">选择“是”生成，选择“否”不生成。</span>
    </label>
    <div v-if="section !== 'relations' && configuration.occurrence === 'conditional'" class="configuration-conditions">
      <div class="configuration-heading">
        <div class="configuration-heading-copy">
          <span class="configuration-heading-title">出现条件</span>
          <span class="configuration-heading-hint">{{ conditionMatchesAny ? '满足其一' : '全部满足' }}</span>
        </div>
        <button type="button" class="configuration-link" :disabled="!fields.length" @click="addCondition">＋ 添加条件</button>
      </div>
      <div v-if="configuration.when" class="configuration-condition-row">
        <RuleConditionNodeEditor :model-value="configuration.when" :fields="fields" @update:model-value="updateWhen" />
        <button type="button" class="configuration-link" aria-label="删除出现条件" @click="updateWhen(null)">删除</button>
      </div>
    </div>
    <div v-if="section !== 'appearance'" class="configuration-relations">
      <div class="configuration-heading">
        <div class="configuration-heading-copy">
          <span class="configuration-heading-title">工序关联</span>
          <span class="configuration-heading-hint">前序出现后可自动带出；仅调整顺序不会带出本工序。</span>
        </div>
        <button type="button" class="configuration-link" :disabled="!otherProcesses.length" @click="addRelation">＋ 添加工序关联</button>
      </div>
      <div v-for="(relation, index) in configuration.relations" :key="index" class="configuration-relation-row">
        <span class="configuration-current">{{ displayName }}</span>
        <select class="relation-select" :aria-label="`第${index + 1}项关联关系`" :value="relation.relation_type" @change="updateRelation(index, { relation_type: ($event.target as HTMLSelectElement).value as ProcessRelationType })">
          <option v-if="configuration.occurrence !== 'always'" value="trigger_after">前序出现后自动带出</option>
          <option value="order_after">仅调整先后顺序</option>
          <option value="requires">关联工序是前置要求</option>
          <option value="conflicts">不能同时安排</option>
        </select>
        <select class="configuration-select" :aria-label="`第${index + 1}项关联工序`" :multiple="relation.source_process_ids.length > 1" :value="relation.source_process_ids.length > 1 ? relation.source_process_ids : relation.source_process_ids[0] || ''" @change="changeSource(index, $event)">
          <option v-if="relation.source_process_ids.length < 2" disabled value="">选择关联工序</option>
          <option v-for="process in otherProcesses" :key="process.process_id" :value="process.process_id">{{ process.display_name }}</option>
        </select>
        <button type="button" class="configuration-link" :aria-label="`删除第${index + 1}项关联`" @click="removeRelation(index)">删除</button>
        <label v-if="relation.relation_type === 'trigger_after' && relation.source_process_ids.length > 1" class="configuration-legacy-match">
          历史关联组
          <select class="configuration-select" :value="relation.source_match || 'any'" @change="updateRelation(index, { source_match: ($event.target as HTMLSelectElement).value as 'all' | 'any' })">
            <option value="all">全部生成</option><option value="any">任一生成</option>
          </select>
        </label>
        <p class="configuration-relation-help">{{ processRelationDescription(relation, displayName, processes) }}</p>
      </div>
    </div>
    <p v-if="error" class="configuration-error" role="alert">{{ error }}</p>
    <div class="candidate-footer">
      <span class="editor-note">{{ staleSource ? '原文已更新，请先取消修改后核对最新规则。' : section === 'relations' ? relationSummary : summary }}</span>
      <button type="button" class="confirm-rule-btn" :disabled="disabled || Boolean(error) || staleSource" @click="save">保存并确认</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { CanonicalConditionField, ProcessConfiguration, ProcessRelationCandidate, ProcessRelationType, RuleConditionCandidate, RuleConditionProcessOption, RulePackageCondition } from '@/api/rulePackages'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { buildManualBooleanRuleCandidate, defaultManualBooleanLabel } from '@/utils/finalizeRulePackage'
import { configurationError, configurationSummary, processRelationDescription } from '@/utils/processConfigurationEditor'
import RuleConditionNodeEditor from '@/components/finalize/RuleConditionNodeEditor.vue'
const props = defineProps<{ modelValue: RuleConditionCandidate; item: FinalizeCard; displayName: string; fields: CanonicalConditionField[]; processes: RuleConditionProcessOption[]; disabled?: boolean; staleSource?: boolean; section?: 'appearance' | 'relations' }>()
const emit = defineEmits<{ 'update:modelValue': [value: RuleConditionCandidate]; save: [value: RuleConditionCandidate] }>()
const configuration = computed(() => props.modelValue.configuration!)
const section = computed(() => props.section || 'appearance')
const conditionMatchesAny = computed(() => configuration.value.when && 'any' in configuration.value.when && Array.isArray(configuration.value.when.any))
const modes: { value: ProcessConfiguration['occurrence']; label: string }[] = [{ value: 'always', label: '始终出现（主工序）' }, { value: 'manual', label: '人工选择' }, { value: 'conditional', label: '条件判断' }]
const otherProcesses = computed(() => props.processes.filter(process => process.process_id !== configuration.value.process_id))
const manualLabel = computed(() => { const when = configuration.value.when; return props.modelValue.field_definitions?.find(field => when && 'field' in when && field.key === when.field)?.label ?? defaultManualBooleanLabel(props.item) })
const error = computed(() => configurationError(configuration.value, manualLabel.value))
const summary = computed(() => configurationSummary(configuration.value, props.displayName, props.fields, props.processes))
const relationSummary = computed(() => configuration.value.relations.length
  ? configuration.value.relations.map(relation => processRelationDescription(relation, props.displayName, props.processes)).join(' ')
  : '尚未设置工序关联。')
function referencedFields(condition: RulePackageCondition | null): Set<string> {
  if (!condition) return new Set()
  if ('all' in condition && Array.isArray(condition.all)) return new Set(condition.all.flatMap(child => [...referencedFields(child)]))
  if ('any' in condition && Array.isArray(condition.any)) return new Set(condition.any.flatMap(child => [...referencedFields(child)]))
  if ('not' in condition && condition.not) return referencedFields(condition.not)
  return 'field' in condition && condition.field ? new Set([condition.field]) : new Set()
}
function update(patch: Partial<ProcessConfiguration>, fields = props.modelValue.field_definitions) {
  const next = { ...configuration.value, ...patch }
  const used = referencedFields(next.when)
  emit('update:modelValue', { ...props.modelValue, preview: '', field_definitions: fields?.filter(field => used.has(field.key)) || [], configuration: next })
}
function changeMode(occurrence: ProcessConfiguration['occurrence']) {
  if (occurrence === configuration.value.occurrence) return
  const relations = configuration.value.relations.map(relation => occurrence !== 'conditional' && relation.relation_type === 'trigger_after'
    ? { ...relation, relation_type: 'order_after' as const }
    : relation)
  if (occurrence === 'manual') { const candidate = buildManualBooleanRuleCandidate(props.item, defaultManualBooleanLabel(props.item)); update({ occurrence, relations, when: candidate.when || null }, candidate.field_definitions) }
  else update({ occurrence, relations, when: null })
}
function changeManualLabel(label: string) { const candidate = buildManualBooleanRuleCandidate(props.item, label); update({ when: candidate.when || null }, candidate.field_definitions?.map(field => ({ ...field, label }))) }
function updateWhen(when: RulePackageCondition | null) { update({ when }) }
function addCondition() { const field = props.fields[0]; if (!field) return; const leaf: RulePackageCondition = { field: field.key, op: field.operators[0] || 'eq', value: field.type === 'boolean' ? true : '' }; const when = configuration.value.when; updateWhen(!when ? leaf : 'all' in when && Array.isArray(when.all) ? { all: [...when.all, leaf] } : 'any' in when && Array.isArray(when.any) ? { any: [...when.any, leaf] } : { all: [when, leaf] }) }
function addRelation() { update({ relations: [...configuration.value.relations, { relation_type: configuration.value.occurrence === 'always' ? 'order_after' : 'trigger_after', source_process_ids: [], target_process_ids: [configuration.value.process_id], source_match: 'all' }] }) }
function updateRelation(index: number, patch: Partial<ProcessRelationCandidate>) { update({ relations: configuration.value.relations.map((relation, position) => position === index ? { ...relation, ...patch } : relation) }) }
function changeSource(index: number, event: Event) { const select = event.target as HTMLSelectElement; updateRelation(index, { source_process_ids: select.multiple ? Array.from(select.selectedOptions).map(option => option.value) : [select.value] }) }
function removeRelation(index: number) { update({ relations: configuration.value.relations.filter((_, position) => position !== index) }) }
function save() { if (!error.value && !props.disabled && !props.staleSource) emit('save', { ...JSON.parse(JSON.stringify(props.modelValue)), preview: summary.value }) }
</script>

<style scoped>
.configuration-editor {
  display: grid;
  gap: 10px;
  padding: 12px 0 8px;
}

.configuration-topline {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
}

.configuration-conditions,
.configuration-relations {
  min-width: 0;
  padding-top: 10px;
  border-top: 1px solid #e9eef3;
}

.configuration-modes {
  display: inline-flex;
  gap: 2px;
  flex: 0 1 auto;
  min-width: 0;
  flex-wrap: wrap;
  background: #f4f6f8;
  border: 1px solid #e0e5eb;
  border-radius: 5px;
  padding: 3px;
}
.configuration-mode {
  min-height: 29px;
  border: 1px solid transparent;
  border-radius: 3px;
  background: transparent;
  color: #5e6b7d;
  padding: 4px 11px;
  font-size: 12px;
  font-weight: 500;
  min-width: 0;
  cursor: pointer;
  transition: border-color 0.15s, color 0.15s, background-color 0.15s;
}
.configuration-mode:hover {
  color: #344256;
  background: rgba(255, 255, 255, 0.7);
}
.configuration-mode[aria-pressed=true] {
  color: #4258b7;
  background: #ffffff;
  border-color: #cbd5f4;
  font-weight: 600;
}
.configuration-mode:focus-visible,
.configuration-link:focus-visible,
.confirm-rule-btn:focus-visible {
  outline: 2px solid #7185d8;
  outline-offset: 2px;
}

.configuration-select,
.relation-select,
.manual-bool-input {
  height: 32px;
  border: 1px solid #d7dfe8;
  border-radius: 4px;
  background: #fff;
  color: #273548;
  padding: 4px 9px;
  font-size: 12px;
  min-width: 0;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.configuration-select:focus,
.relation-select:focus,
.manual-bool-input:focus {
  border-color: #8798dd;
  box-shadow: 0 0 0 2px rgba(82, 103, 201, 0.1);
}

.configuration-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  margin-bottom: 6px;
  color: #334155;
  font-size: 12px;
  font-weight: 600;
}
.configuration-heading-copy {
  display: flex;
  align-items: baseline;
  gap: 8px;
  min-width: 0;
}
.configuration-heading-hint {
  font-weight: 400;
  color: #748195;
  font-size: 11px;
}

.configuration-relation-row {
  display: grid;
  grid-template-columns: minmax(90px, .58fr) minmax(180px, 1.12fr) minmax(190px, 1.25fr) auto;
  gap: 6px;
  align-items: center;
  margin-bottom: 6px;
}
.configuration-relation-row > .configuration-select[multiple] {
  height: auto;
  min-height: 56px;
  padding: 4px 6px;
}
.configuration-condition-row {
  display: flex;
  align-items: center;
  gap: 7px;
}
.configuration-condition-row > :first-child {
  flex: 1 1 auto;
  min-width: 0;
}
.configuration-condition-row > .configuration-link {
  flex: 0 0 auto;
}
.configuration-condition-row :deep(.condition-node-leaf) {
  grid-template-columns: minmax(150px, 1.1fr) minmax(110px, .72fr) minmax(150px, 1fr);
  gap: 6px;
}
.configuration-condition-row :deep(.rule-control) {
  height: 32px;
  padding: 0 9px;
  border-radius: 4px;
  border-color: #d7dfe8;
  color: #273548;
  font-size: 12px;
}
.configuration-condition-row :deep(.rule-control:focus) {
  border-color: #8798dd;
  box-shadow: 0 0 0 2px rgba(82, 103, 201, 0.1);
}
.configuration-condition-row :deep(.logic-heading) { margin-bottom: 6px; }
.configuration-condition-row :deep(.logic-children) {
  gap: 6px;
  padding-left: 10px;
  border-color: #dfe5ef;
}
.configuration-condition-row :deep(.logic-child-row) { align-items: center; gap: 5px; }
.configuration-condition-row :deep(.condition-remove) { padding: 4px 2px; font-size: 11px; }
.configuration-condition-row :deep(.logic-chip-not) { margin-bottom: 5px; }

.configuration-current,
.configuration-note,
.editor-note {
  font-size: 12px;
  color: #69788b;
  line-height: 1.45;
}
.configuration-note {
  margin: 0;
  text-align: right;
}

.configuration-link {
  width: fit-content;
  min-height: 28px;
  padding: 4px 3px;
  border: 0;
  background: transparent;
  color: #5267c9;
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  white-space: nowrap;
  transition: color 0.15s, opacity 0.15s;
}
.configuration-link:hover {
  color: #3549a3;
}

.configuration-manual {
  display: grid;
  grid-template-columns: 84px minmax(180px, 1fr) auto;
  gap: 8px;
  align-items: center;
  color: #4f5e70;
  font-size: 12px;
}
.configuration-manual .configuration-note {
  text-align: left;
}

.configuration-legacy-match {
  grid-column: 2 / 4;
  color: #69788b;
  font-size: 11px;
}
.configuration-legacy-match .configuration-select { margin-left: 5px; }
.configuration-relation-help {
  grid-column: 2 / 4;
  margin: -2px 0 1px;
  color: #748195;
  font-size: 11px;
  line-height: 1.4;
}
.configuration-relation-help::before {
  content: '↳';
  margin-right: 5px;
  color: #9aa6b5;
}
.configuration-error {
  color: #b33d3d;
  font-size: 12px;
  font-weight: 500;
  margin: 0;
  padding: 7px 9px;
  background: #fff5f5;
  border-radius: 4px;
  border: 1px solid #f2c7c7;
}

.candidate-footer {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 10px;
  border-top: 1px solid #dce3eb;
  padding-top: 10px;
  margin-top: 1px;
}
.editor-note {
  min-width: 0;
  overflow-wrap: anywhere;
}
.confirm-rule-btn {
  border: 0;
  border-radius: 5px;
  padding: 7px 15px;
  background: #5267c9;
  color: #fff;
  white-space: nowrap;
  cursor: pointer;
  font-size: 12px;
  font-weight: 600;
  transition: background-color 0.15s, opacity 0.15s;
}
.confirm-rule-btn:hover:not(:disabled) {
  background: #4458b8;
}
button:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

@media (max-width: 700px) {
  .configuration-topline,
  .configuration-manual,
  .candidate-footer {
    align-items: stretch;
    flex-direction: column;
  }
  .configuration-modes {
    display: grid;
    grid-template-columns: repeat(3, minmax(0, 1fr));
    width: 100%;
  }
  .configuration-mode {
    padding-right: 5px;
    padding-left: 5px;
    white-space: normal;
  }
  .configuration-note { text-align: left; }
  .configuration-manual { grid-template-columns: minmax(0, 1fr); gap: 5px; }
  .configuration-condition-row { align-items: stretch; flex-direction: column; }
  .configuration-condition-row > .configuration-link { align-self: flex-start; }
  .configuration-condition-row :deep(.condition-node-leaf) { grid-template-columns: minmax(0, 1fr); }
  .configuration-condition-row :deep(.logic-child-row) { align-items: stretch; flex-direction: column; }
  .configuration-condition-row :deep(.condition-remove) { align-self: flex-start; }
  .configuration-relation-row {
    grid-template-columns: minmax(0, 1fr) auto;
    gap: 5px 7px;
  }
  .configuration-current { grid-column: 1 / -1; }
  .configuration-relation-row > .relation-select,
  .configuration-relation-row > .configuration-select { grid-column: 1; width: 100%; }
  .configuration-relation-row > .configuration-link { grid-column: 2; grid-row: 2; }
  .configuration-legacy-match,
  .configuration-relation-help { grid-column: 1 / -1; }
  .candidate-footer { gap: 8px; }
  .confirm-rule-btn { align-self: flex-start; }
}
</style>
