<template>
  <article
    :id="`finalize-card-${item.segment.id}`"
    class="preview-card card"
    :class="{ 'preview-card-active': active }"
  >
    <div class="preview-card-header">
      <div class="preview-card-title-group">
        <div class="preview-card-name-stack">
          <h2>
            <span>{{ displayName }}</span>
            <span v-if="!configurationEditing" class="card-mode-badge" :class="`card-mode-${cardRuleMode}`">{{ modeLabel }}</span>
            <button
              v-if="cardRuleMode === 'mainline' && !configurationEditing"
              class="collapse-toggle-btn"
              type="button"
              :aria-expanded="mainlineExpanded"
              :aria-label="`${mainlineExpanded ? '折叠' : '展开'}${displayName}详情`"
              :title="mainlineExpanded ? '折叠' : '展开详情'"
              @click="mainlineExpanded = !mainlineExpanded"
            >
              <svg class="collapse-chevron" :class="{ 'collapse-chevron--open': mainlineExpanded }" width="13" height="13" viewBox="0 0 16 16" fill="none">
                <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
            </button>
          </h2>
          <div v-if="metaLabel" class="preview-card-meta">{{ metaLabel }}</div>
        </div>
      </div>
      <div class="preview-card-actions">
        <div class="card-selection-slot">
        <label v-if="selectable && !inlineEditing && !ruleEditorExpanded && !manualBooleanEditing && !configurationEditing" class="rule-selection">
          <input type="checkbox" :checked="selected" :disabled="controlsDisabled" :aria-label="`选择${displayName}规则`" @change="$emit('toggle-selected', item)" />
          <span>选择</span>
        </label>
        </div>
        <div class="card-confirm-slot">
        <span v-if="conditionBusy" class="edited-badge" role="status">处理中…</span>
        <span v-else-if="hasUnsavedChanges && !configurationEditing" class="edited-badge" role="status">未保存</span>
        <button
          v-if="!hasUnsavedChanges && !configurationEditing && !inlineEditing && !manualBooleanEditing && editableCandidate && candidateMatchesCardMode && (candidateKind === 'process_configuration' || ['conditional','relation'].includes(cardRuleMode)) && effectiveStatus !== 'confirmed'"
          type="button" class="confirm-rule-primary-btn"
          :disabled="controlsDisabled || !hasRuleAction || Boolean(authoringError)" @click="confirmCandidate"
        >确认规则</button>
        </div>
        <div class="card-edit-slot">
        <template v-if="!inlineEditing">
          <button
            v-if="!configurationEditing && !ruleEditorExpanded && !manualBooleanEditing"
            type="button"
            class="preview-edit-btn"
            :class="{ 'preview-edit-btn-active': configurationEditing }"
            :disabled="controlsDisabled"
            :aria-expanded="configurationEditing"
            @click="openConfigurationEditor('appearance')"
          >规则修改</button>
          <button v-if="ruleEditorExpanded || manualBooleanEditing" type="button" class="preview-edit-btn" :disabled="controlsDisabled" @click="beginEdit">取消修改</button>
        </template>
        </div>
      </div>
    </div>

    <div v-if="conditionError" class="card-inline-strip card-strip-warn" role="alert">
      <span class="strip-desc">{{ conditionError }}</span>
      <button v-if="!editableCandidate || !candidateMatchesCardMode" class="strip-action" :disabled="controlsDisabled" @click="$emit('parse-condition', item)">重试识别</button>
    </div>
    <!-- Mainline collapsed: minimal one-line hint -->
    <div v-if="cardRuleMode === 'mainline' && !mainlineExpanded && !inlineEditing && !configurationEditing" class="mainline-collapsed-hint">
      <span class="mainline-hint-text">{{ item.conditionText || '主线工序，默认纳入路线' }}</span>
    </div>

    <!-- Full card body -->
    <div v-else class="preview-card-body">
      <template v-if="configurationEditing && configurationDraft">
        <ProcessConfigurationEditor
          :model-value="configurationDraft" :item="item" :display-name="displayName"
          :fields="configurationFields" :processes="processOptions" :disabled="controlsDisabled"
          :stale-source="configurationSourceChanged"
          :require-mode-selection="configurationRequiresModeSelection"
          :section="configurationEditorSection"
          @update:model-value="configurationDraft = $event; configurationRequiresModeSelection = false" @save="saveConfiguration" @cancel="openConfigurationEditor('appearance')"
        >
          <template #secondary-actions>
            <div class="configuration-secondary-tools">
            <details v-if="item.edited" class="configuration-more">
              <summary>更多操作</summary>
              <div class="configuration-more-menu">
                <button v-if="item.edited" type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="resetRule">
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 8a6 6 0 0 1 10.2-4.2M14 2v4h-4M14 8a6 6 0 0 1-10.2 4.2M2 14v-4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
                  恢复默认
                </button>
              </div>
            </details>
            <span v-if="hasUnsavedConfiguration" class="configuration-save-state" role="status">未保存</span>
            </div>
          </template>
        </ProcessConfigurationEditor>
      </template>
      <div v-if="inlineEditing" class="inline-edit-box">
        <textarea :value="inlineEditingText" class="inline-edit-textarea" :disabled="controlsDisabled" rows="3" :ref="handleTextareaRef"
          placeholder="请输入规则，例如：当外圆尺寸精度达到IT8时，纳入磨外圆工序。"
          @input="$emit('update:inlineEditingText', ($event.target as HTMLTextAreaElement).value)" />
        <div class="inline-edit-actions">
          <button class="inline-btn inline-btn-cancel" @click="$emit('cancel')">取消</button>
          <button class="inline-btn inline-btn-save" :disabled="controlsDisabled || !inlineEditingText.trim()" @click="$emit('save', item)">保存并识别</button>
        </div>
      </div>


      <!-- Boolean conversion inline editor -->
      <div v-if="manualBooleanEditing && !inlineEditing" class="manual-boolean-editor">
        <span class="manual-bool-tag">人工选择项名称</span>
        <input
          :id="`manual-bool-label-${item.segment.id}`"
          v-model="manualBooleanLabel"
          type="text"
          maxlength="40"
          :placeholder="defaultManualBooleanLabel(item)"
          class="manual-bool-input"
        />
        <div class="manual-bool-actions">
          <button type="button" class="manual-bool-btn manual-bool-btn-cancel" :disabled="controlsDisabled" @click="cancelBooleanConversion">取消</button>
          <button
            type="button"
            class="manual-bool-btn manual-bool-btn-save"
            :disabled="controlsDisabled || !manualBooleanLabel.trim()"
            @click="confirmBooleanConversion"
          >
            保存并确认人工选择
          </button>
        </div>
      </div>

      <!-- Unresolved: compact inline strip -->
      <div v-if="!inlineEditing && !configurationEditing && cardRuleMode === 'unresolved'" class="card-inline-strip card-strip-warn">
        <span class="strip-label">条件待补充</span>
        <span class="strip-desc">请补充判断字段或明确取值</span>
        <button class="strip-action" @click="$emit('start-edit', item)">补充条件</button>
      </div>

      <!-- Conditional/relation rule status -->
      <template v-if="!inlineEditing && !configurationEditing && ['conditional', 'relation'].includes(cardRuleMode)">
        <!-- No candidate yet -->
        <div v-if="!editableCandidate || !candidateMatchesCardMode" class="card-inline-strip card-strip-pending">
          <span class="strip-label" :class="{ 'strip-label-attention': sourceTextChanged }">{{ pendingStatusLabel }}</span>
          <span class="strip-desc">{{ pendingStatusDetail }}</span>
          <button v-if="effectiveStatus === 'invalid'" type="button" class="strip-action" :disabled="controlsDisabled" @click="openConfigurationEditor('appearance', true)">设置出现规则</button>
          <button class="strip-action" :disabled="controlsDisabled" @click="$emit('parse-condition', item)">{{ pendingActionLabel }}</button>
        </div>

        <!-- Has candidate: compact rule line -->
        <template v-else>
          <div class="card-rule-compact">
            <span class="compact-status" :class="{ 'compact-confirmed': effectiveStatus === 'confirmed' }">{{ hasUnsavedChanges ? '未保存' : effectiveStatus === 'confirmed' ? '✓ 已确认' : '待确认' }}</span>
            <span class="compact-summary">
              <span class="compact-summary-text">{{ candidateSummary }}</span>
            </span>
          </div>

          <div v-if="requiresManualReview" class="manual-review-note">
            <strong>需要人工审核</strong>
            <span>{{ manualReviewReason }}</span>
          </div>

          <!-- Expanded rule editor -->
          <div v-if="ruleEditorExpanded" class="candidate-editor" :inert="controlsDisabled">
            <button v-if="authoringError" type="button" class="ghost-btn" :disabled="controlsDisabled" @click="openConfigurationEditor('appearance', true)">选择出现模式重新设置</button>
            <button type="button" class="ghost-btn" :disabled="controlsDisabled || hasUnsavedChanges" @click="$emit('start-edit', item)">修改原始描述</button>
            <RuleConditionNodeEditor
              v-if="candidateKind === 'condition' && editableCandidate.when"
              :model-value="editableCandidate.when"
              :fields="summaryFields"
              @update:model-value="updateWhen"
            />

            <!-- A condition card only controls its own process. -->
            <div v-if="candidateKind === 'condition'" class="action-editor-tag">
              <div class="action-tag-column" @click.stop>
                <span class="action-title action-title-include">作用工序</span>
                <div class="tag-list">
                  <span class="process-tag process-tag-include">{{ processDisplayName(currentProcessId) }}</span>
                </div>
              </div>

              <div class="action-tag-column" @click.stop>
                <span class="action-title action-title-exclude">规则动作</span>
                <div class="tag-list">
                  <button
                    type="button"
                    class="tag-add-btn"
                    :class="{ 'tag-add-btn-active': conditionActionKind === 'include' }"
                    @click.stop="setCurrentProcessAction('include')"
                  >纳入</button>
                  <button
                    type="button"
                    class="tag-add-btn"
                    :class="{ 'tag-add-btn-active': conditionActionKind === 'exclude' }"
                    @click.stop="setCurrentProcessAction('exclude')"
                  >排除</button>
                </div>
              </div>
            </div>

            <!-- Relation editor -->
            <div v-else-if="editableCandidate.relation" class="relation-editor">
              <label class="relation-control-row">
                <span>关系类型</span>
                <select class="relation-select" :value="editableCandidate.relation.relation_type" @change="changeRelationType">
                  <option value="trigger_after">触发并排在其后</option>
                  <option value="order_after">仅约束先后顺序</option>
                  <option value="requires">作为前置依赖</option>
                  <option value="conflicts">不能同时出现</option>
                </select>
              </label>
              <label v-if="editableCandidate.relation.relation_type === 'trigger_after' && editableCandidate.relation.source_process_ids.length > 1" class="relation-control-row">
                <span>多个来源</span>
                <select class="relation-select" :value="editableCandidate.relation.source_match || 'any'" @change="changeSourceMatch">
                  <option value="any">任一道出现即触发</option>
                  <option value="all">全部出现才触发</option>
                </select>
              </label>

              <!-- Tag-based relation process selector -->
              <div class="action-editor-tag">
                <div class="action-tag-column" @click.stop>
                  <span class="action-title relation-source-title">来源工序</span>
                  <div class="tag-list">
                    <span
                      v-for="pid in editableCandidate.relation.source_process_ids"
                      :key="`src-tag-${pid}`"
                      class="process-tag process-tag-source"
                    >
                      {{ processDisplayName(pid) }}
                      <button class="tag-remove" @click.stop="removeRelationProcess('source', pid)">×</button>
                    </span>
                    <button class="tag-add-btn" @click.stop="openPicker('source')">
                      <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
                        <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                      </svg>
                      添加
                    </button>
                  </div>
                  <Transition name="picker-pop">
                    <div v-if="processPickerOpen === 'source'" class="process-picker-dropdown" @click.stop>
                      <input :ref="setSearchRef" v-model="processPickerSearch" class="picker-search" placeholder="搜索工序名..." />
                      <div class="picker-options">
                        <button
                          v-for="p in filteredPickerOptions"
                          :key="`pi-src-${p.process_id}`"
                          class="picker-option"
                          :class="{ 'picker-option-selected': isRelationSelected('source', p.process_id) }"
                          @click.stop="selectRelationOption('source', p.process_id)"
                        >
                          <span>{{ p.display_name }}</span>
                          <svg v-if="isRelationSelected('source', p.process_id)" class="picker-check" width="12" height="12" viewBox="0 0 16 16" fill="none">
                            <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                          </svg>
                        </button>
                        <div v-if="!filteredPickerOptions.length" class="picker-empty">无匹配工序</div>
                      </div>
                    </div>
                  </Transition>
                </div>

                <div class="action-tag-column" @click.stop>
                  <span class="action-title relation-target-title">目标工序</span>
                  <div class="tag-list">
                    <span
                      v-for="pid in editableCandidate.relation.target_process_ids"
                      :key="`tgt-tag-${pid}`"
                      class="process-tag process-tag-target"
                    >
                      {{ processDisplayName(pid) }}
                      <button class="tag-remove" @click.stop="removeRelationProcess('target', pid)">×</button>
                    </span>
                    <button class="tag-add-btn" @click.stop="openPicker('target')">
                      <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
                        <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                      </svg>
                      添加
                    </button>
                  </div>
                  <Transition name="picker-pop">
                    <div v-if="processPickerOpen === 'target'" class="process-picker-dropdown" @click.stop>
                      <input :ref="setSearchRef" v-model="processPickerSearch" class="picker-search" placeholder="搜索工序名..." />
                      <div class="picker-options">
                        <button
                          v-for="p in filteredPickerOptions"
                          :key="`pi-tgt-${p.process_id}`"
                          class="picker-option"
                          :class="{ 'picker-option-selected': isRelationSelected('target', p.process_id) }"
                          @click.stop="selectRelationOption('target', p.process_id)"
                        >
                          <span>{{ p.display_name }}</span>
                          <svg v-if="isRelationSelected('target', p.process_id)" class="picker-check" width="12" height="12" viewBox="0 0 16 16" fill="none">
                            <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                          </svg>
                        </button>
                        <div v-if="!filteredPickerOptions.length" class="picker-empty">无匹配工序</div>
                      </div>
                    </div>
                  </Transition>
                </div>
              </div>
            </div>

            <div class="candidate-footer">
              <span class="editor-note">{{ editedSourceChanged ? '原文已更新，请先取消修改后核对最新规则。' : '核对后保存，即确认该规则。' }}</span>
              <button class="confirm-rule-btn" :disabled="controlsDisabled || !hasRuleAction || editedSourceChanged || Boolean(authoringError)" @click="confirmCandidate">
                保存并确认
              </button>
            </div>
          </div>

          <div v-if="active && effectiveStatus === 'confirmed' && item.conditionReview?.confirmed_by" class="confirmation-audit">
            {{ item.conditionReview.confirmed_by }} · {{ formatConfirmedAt(item.conditionReview.confirmed_at) }}
          </div>
        </template>
      </template>

      <div v-if="ruleEditorExpanded" class="configuration-secondary-actions">
        <button v-if="!authoringError" type="button" class="ghost-btn" :disabled="controlsDisabled" @click="openConfigurationEditor('appearance')">调整出现方式</button>
        <button v-if="item.edited" type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="resetRule">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 8a6 6 0 0 1 10.2-4.2M14 2v4h-4M14 8a6 6 0 0 1-10.2 4.2M2 14v-4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          恢复默认
        </button>
        <button type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="reparseRule">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3-2M8 2a6 6 0 1 0 5.3 3.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          重新识别
        </button>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import type {
  CanonicalConditionField,
  ProcessRelationType,
  RuleConditionCandidate,
  RuleConditionProcessOption,
  RulePackageCondition,
} from '@/api/rulePackages'
import RuleConditionNodeEditor from '@/components/finalize/RuleConditionNodeEditor.vue'
import ProcessConfigurationEditor from '@/components/finalize/ProcessConfigurationEditor.vue'
import { configurationSummary, validateAuthoredCandidate } from '@/utils/processConfigurationEditor'
import { mergeProjectConditionFields, projectConditionDisplayLabel } from '@/utils/projectConditionFields'
import { resolveGuidanceOperation } from '@/composables/analysisGuidanceFlow'
import { answersFromTrail, savedGuidanceSnapshot, savedQuestionTrail } from '@/composables/analysisQuestionTreeState'
import {
  defaultManualBooleanLabel,
  finalizeRuleMode,
  isSafeForBatchRuleConfirmation,
  isManualBooleanFinalizeCard,
  exportProcessIdForItem,
  buildManualBooleanRuleCandidate,
} from '@/utils/finalizeRulePackage'
import { formatRuleCondition } from '@/utils/finalizeRulePresentation'
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch, type ComponentPublicInstance } from 'vue'

const props = defineProps<{
  item: FinalizeCard
  active: boolean
  displayName: string
  metaLabel: string
  inlineEditing: boolean
  inlineEditingText: string
  editedBadge: string
  editLabel: string
  conditionLabel: string
  conditionFields: CanonicalConditionField[]
  routeSegments?: FinalizeCard['segment'][]
  processOptions: RuleConditionProcessOption[]
  selectable?: boolean
  selected?: boolean
  conditionError?: string
  actionsDisabled?: boolean
  conditionBusy: boolean
  setInlineTextareaRef: (el: Element | null) => void
}>()

const emit = defineEmits<{
  'toggle-selected': [item: FinalizeCard]
  reset: [item: FinalizeCard]
  'start-edit': [item: FinalizeCard]
  cancel: []
  save: [item: FinalizeCard]
  'parse-condition': [item: FinalizeCard]
  'confirm-condition': [item: FinalizeCard, candidate: RuleConditionCandidate]
  'set-mainline': [item: FinalizeCard]
  'set-boolean': [item: FinalizeCard, label: string]
  'save-configuration': [item: FinalizeCard, candidate: RuleConditionCandidate]
  'update:inlineEditingText': [value: string]
  'edit-state': [segmentId: string, dirty: boolean]
}>()

const controlsDisabled = computed(() => props.conditionBusy || props.actionsDisabled)
const editableCandidate = ref<RuleConditionCandidate | null>(null)
const ruleEditorExpanded = ref(false)
const mainlineExpanded = ref(false)
const manualBooleanEditing = ref(false)
const manualBooleanLabel = ref('')
const savedCandidate = ref<RuleConditionCandidate | null>(null)
const savedManualBooleanLabel = ref('')
const manualConversionChangesKind = ref(false)
const editorSourceText = ref('')
const submittedCandidate = ref('')
const submittedManualLabel = ref<string | null>(null)
const configurationEditing = ref(false)
const configurationRequiresModeSelection = ref(false)
const configurationEditorSection = ref<'appearance' | 'relations'>('appearance')
const configurationDraft = ref<RuleConditionCandidate | null>(null)
const savedConfigurationSignature = ref('')
const submittedConfiguration = ref('')
const configurationSource = ref('')
const nodeGuidance = computed(() => {
  const segment = props.item.segment
  const snapshot = savedGuidanceSnapshot(segment)
  if (!snapshot) return undefined
  const operation = resolveGuidanceOperation(segment, snapshot, answersFromTrail(savedQuestionTrail(segment)), props.routeSegments || [segment], true)
  if (!operation) return null
  return { ...snapshot, operation_guidance: { ...snapshot.operation_guidance, [segment.normalized_step_name]: operation } }
})
const configurationFields = computed(() => mergeProjectConditionFields(
  currentProcessId.value, props.item.segment.normalized_step_name, props.conditionFields,
  [savedCandidate.value, editableCandidate.value, configurationDraft.value],
  nodeGuidance.value,
))
const hasUnsavedConfiguration = computed(() => configurationEditing.value && candidateSignature(configurationDraft.value) !== savedConfigurationSignature.value)
const configurationSourceChanged = computed(() => configurationEditing.value && configurationSource.value !== props.item.conditionText.trim())

// Only executable content makes an edit dirty. Recognition prose and server
// object-key ordering may change without changing the rule being saved.
function candidateSignature(candidate: RuleConditionCandidate | null | undefined): string {
  if (!candidate) return ''
  const referenced = new Set<string>()
  function collect(condition: RulePackageCondition | null | undefined) {
    if (!condition) return
    if ('field' in condition) referenced.add(condition.field)
    if ('all' in condition && Array.isArray(condition.all)) condition.all.forEach(collect)
    if ('any' in condition && Array.isArray(condition.any)) condition.any.forEach(collect)
    if ('not' in condition) collect(condition.not)
  }
  collect(candidate.configuration?.when || candidate.when)
  const definitions = (candidate.field_definitions || []).filter(field => referenced.has(field.key))
  const kind = candidate.kind || 'condition'
  const content = kind === 'process_configuration'
    ? { kind, configuration: candidate.configuration, field_definitions: definitions }
    : kind === 'process_relation'
    ? {
        kind,
        relation: candidate.relation ? {
          relation_type: candidate.relation.relation_type,
          source_process_ids: [...candidate.relation.source_process_ids].sort(),
          target_process_ids: [...candidate.relation.target_process_ids].sort(),
          source_match: candidate.relation.relation_type === 'trigger_after'
            ? candidate.relation.source_match || 'any'
            : null,
        } : null,
      }
    : {
        kind,
        when: candidate.when || null,
        then: {
          include_process_ids: [...(candidate.then?.include_process_ids || [])].sort(),
          exclude_process_ids: [...(candidate.then?.exclude_process_ids || [])].sort(),
        },
        field_definitions: definitions,
      }
  return JSON.stringify(content, (_key, value) => (
    value && typeof value === 'object' && !Array.isArray(value)
      ? Object.fromEntries(Object.entries(value).filter(([, item]) => item !== null && item !== undefined).sort(([a], [b]) => a.localeCompare(b)))
      : value
  ))
}

const hasUnsavedCandidate = computed(() => ruleEditorExpanded.value
  && candidateSignature(editableCandidate.value) !== candidateSignature(savedCandidate.value))
const hasUnsavedManualLabel = computed(() => manualBooleanEditing.value
  && (manualConversionChangesKind.value || manualBooleanLabel.value.trim() !== savedManualBooleanLabel.value))
const hasUnsavedChanges = computed(() => hasUnsavedCandidate.value || hasUnsavedManualLabel.value || hasUnsavedConfiguration.value
  || (props.inlineEditing && props.inlineEditingText.trim() !== props.item.conditionText.trim()))
const editedSourceChanged = computed(() => hasUnsavedCandidate.value
  && editorSourceText.value !== props.item.conditionText.trim())

watch([() => props.item.segment.id, hasUnsavedChanges], ([segmentId, dirty], previous) => {
  if (previous?.[0] && previous[0] !== segmentId) emit('edit-state', previous[0], false)
  emit('edit-state', segmentId, dirty)
}, { immediate: true })

// Process picker
type PickerKind = 'source' | 'target'
const processPickerOpen = ref<PickerKind | null>(null)
const processPickerSearch = ref('')
const searchInputEl = ref<HTMLInputElement | null>(null)

const currentProcessId = computed(() => exportProcessIdForItem(props.item))
const conditionActionKind = computed(() => (
  editableCandidate.value?.then?.exclude_process_ids?.includes(currentProcessId.value)
    ? 'exclude'
    : 'include'
))

function setSearchRef(el: any) {
  searchInputEl.value = el instanceof HTMLInputElement ? el : null
}

// Watch picker open → auto-focus search
watch(processPickerOpen, async (val) => {
  if (val) {
    await nextTick()
    searchInputEl.value?.focus()
  }
})

// Close picker on outside click
function handleDocumentClick() {
  processPickerOpen.value = null
  processPickerSearch.value = ''
}
onMounted(() => document.addEventListener('click', handleDocumentClick))
onBeforeUnmount(() => document.removeEventListener('click', handleDocumentClick))

// ---- Computed ----
const effectiveStatus = computed(() => {
  if (hasUnsavedChanges.value) return 'draft'
  const review = props.item.conditionReview
  if (!review || review.source_text.trim() !== props.item.conditionText.trim()) return 'draft'
  return review.status
})
const sourceTextChanged = computed(() => {
  const review = props.item.conditionReview
  return Boolean(review?.source_text?.trim() && review.source_text.trim() !== props.item.conditionText.trim())
})
const cardRuleMode = computed(() => hasUnsavedCandidate.value && editableCandidate.value
  ? (editableCandidate.value.kind === 'process_relation' ? 'relation' : 'conditional')
  : finalizeRuleMode(props.item))
const modeLabel = computed(() => {
  const candidate = hasUnsavedCandidate.value ? editableCandidate.value : savedCandidate.value
  if (candidate?.kind === 'process_configuration' && candidate.configuration) {
    return { always: '主工序', manual: 'Bool 工序', conditional: '条件工序', associated: '关联工序' }[candidate.configuration.occurrence]
  }
  return isManualBooleanFinalizeCard(props.item) ? 'Bool 工序' : ({
    mainline: '主工序',
    conditional: '条件工序',
    relation: '关联工序',
    unresolved: '条件待补充',
  })[cardRuleMode.value]
})
const candidateKind = computed(() => editableCandidate.value?.kind || 'condition')
const authoringError = computed(() => validateAuthoredCandidate(editableCandidate.value, currentProcessId.value)[0] || '')
const editorFields = computed(() => mergeProjectConditionFields(currentProcessId.value, props.item.segment.normalized_step_name, props.conditionFields, [editableCandidate.value], nodeGuidance.value))
const summaryFields = computed(() => editorFields.value.map(field => ({ ...field, label: projectConditionDisplayLabel(field, props.item.segment.normalized_step_name) })))
const candidateMatchesCardMode = computed(() => {
  if (!editableCandidate.value) return false
  if (candidateKind.value === 'process_configuration') return true
  return cardRuleMode.value === 'relation'
    ? candidateKind.value === 'process_relation'
    : candidateKind.value === 'condition'
})
const hasCrossProcessConditionTarget = computed(() => {
  const candidate = editableCandidate.value
  if (candidateKind.value !== 'condition' || !candidate?.then) return false
  const targets = new Set([
    ...(candidate.then.include_process_ids || []),
    ...(candidate.then.exclude_process_ids || []),
  ])
  return targets.size !== 1 || !targets.has(currentProcessId.value)
})
const requiresManualReview = computed(() => (
  Boolean(authoringError.value) || hasCrossProcessConditionTarget.value
  || (
    effectiveStatus.value === 'pending_confirmation'
    && !isSafeForBatchRuleConfirmation(props.item)
  )
))
const manualReviewReason = computed(() => {
  if (authoringError.value) return authoringError.value
  if (hasCrossProcessConditionTarget.value) {
    return '此条件规则曾指向其他工序。请在“修改”中将动作保存为当前工序，跨工序关系请单独配置。'
  }
  const issue = props.item.conditionReview?.issues?.[0]
  if (issue) return issue
  const confidence = Number(props.item.conditionReview?.confidence || 0)
  return confidence > 0
    ? `识别置信度 ${Math.round(confidence * 100)}%，请核对字段、取值和目标工序。`
    : '当前候选缺少可靠置信度，请核对字段、取值和目标工序。'
})
const pendingStatusLabel = computed(() => {
  if (props.conditionBusy) return '正在识别规则'
  if (sourceTextChanged.value) return props.conditionBusy ? '原文已修改，正在更新' : '原文已修改，待重新识别'
  if (editableCandidate.value) return '规则类型需要更新'
  if (effectiveStatus.value === 'invalid') return '暂未识别'
  return '待识别'
})
const pendingStatusDetail = computed(() => {
  if (sourceTextChanged.value) return '系统会按当前文字重新判断条件和目标工序。'
  if (editableCandidate.value) return '当前识别结果与原文类型不一致，请重新识别。'
  if (effectiveStatus.value === 'invalid') return props.item.conditionReview?.issues?.[0] || '请补充更明确的判断条件、比较关系或取值。'
  return cardRuleMode.value === 'relation'
    ? '审核时将识别触发、依赖或先后关系。'
    : '审核时将识别判断条件和目标工序。'
})
const pendingActionLabel = computed(() => {
  if (props.conditionBusy) return '识别中…'
  return effectiveStatus.value === 'invalid' ? '重试识别' : '识别规则'
})
const hasRuleAction = computed(() => {
  const candidate = editableCandidate.value
  if (!candidate) return false
  if (candidateKind.value === 'process_configuration') {
    return candidate.configuration?.process_id === currentProcessId.value
  }
  if (candidateKind.value === 'process_relation') {
    return Boolean(candidate.relation?.source_process_ids?.length && candidate.relation?.target_process_ids?.length)
  }
  return Boolean(candidate.then?.include_process_ids?.length || candidate.then?.exclude_process_ids?.length)
})
const candidateSummary = computed(() => {
  if (manualBooleanEditing.value) {
    return `用户选择“${manualBooleanLabel.value.trim() || '待填写'}”为是 → 纳入 ${props.displayName}`
  }
  const candidate = editableCandidate.value
  if (!candidate) return ''
  if (candidate.kind === 'process_configuration' && candidate.configuration) return configurationSummary(candidate.configuration, props.displayName, summaryFields.value, props.processOptions)
  if ((candidate.kind || 'condition') === 'process_relation' && candidate.relation) {
    const pm = new Map(props.processOptions.map(p => [p.process_id, p.display_name]))
    const sources = Array.from(new Set(candidate.relation.source_process_ids.map(id => pm.get(id) || id)))
    const src = sources.join('、')
    const tgt = Array.from(new Set(candidate.relation.target_process_ids.map(id => pm.get(id) || id))).join('、')
    if (candidate.relation.relation_type === 'trigger_after') {
      const trigger = sources.length > 1 ? `${src}中${candidate.relation.source_match === 'all' ? '全部工序' : '任一道工序'}` : src
      return `${trigger}进入路线 → 纳入${tgt}，并排在已进入路线的来源工序之后`
    }
    if (candidate.relation.relation_type === 'order_after') return `${tgt}与${src}都进入路线时 → ${tgt}排在来源工序之后；不自动纳入工序`
    if (candidate.relation.relation_type === 'requires') return `${tgt}进入路线 → 必须纳入${src}${sources.length > 1 ? '全部工序' : ''}，并安排在${tgt}之前`
    return `${tgt}不能与${src}${sources.length > 1 ? '中的任一道工序' : ''}同时进入路线`
  }
  const pm = new Map(props.processOptions.map(p => [p.process_id, p.display_name]))
  const includes = (candidate.then?.include_process_ids || []).map(id => pm.get(id) || id)
  const excludes = (candidate.then?.exclude_process_ids || []).map(id => pm.get(id) || id)
  const actions = [
    includes.length ? `纳入 ${includes.join('、')}` : '',
    excludes.length ? `排除 ${excludes.join('、')}` : '',
  ].filter(Boolean).join('；')
  return `${formatRuleCondition(candidate.when, summaryFields.value)} → ${actions}`
})
const filteredPickerOptions = computed(() => {
  const search = processPickerSearch.value.trim().toLowerCase()
  return props.processOptions.filter((p) => {
    return !search || p.display_name.toLowerCase().includes(search)
  })
})

// ---- Helpers ----
function processDisplayName(processId: string) {
  return props.processOptions.find(p => p.process_id === processId)?.display_name || processId
}

function openPicker(kind: PickerKind) {
  processPickerOpen.value = processPickerOpen.value === kind ? null : kind
  processPickerSearch.value = ''
}

function resetCandidateFromReview() {
  const review = props.item.conditionReview
  const sourceMatches = review?.source_text?.trim() === props.item.conditionText.trim()
  const candidate = sourceMatches
    ? (review?.status === 'confirmed' ? review.confirmed || review.candidate : review?.candidate)
    : null
  editableCandidate.value = candidate ? JSON.parse(JSON.stringify(candidate)) : null
  savedCandidate.value = candidate ? JSON.parse(JSON.stringify(candidate)) : null
  editorSourceText.value = props.item.conditionText.trim()
  submittedCandidate.value = ''
  submittedManualLabel.value = null
}
let currentSegmentId = props.item.segment.id
watch(
  () => [props.item.segment.id, props.item.conditionReview, props.item.conditionText] as const,
  () => {
    const sameSegment = currentSegmentId === props.item.segment.id
    currentSegmentId = props.item.segment.id
    if (sameSegment && hasUnsavedConfiguration.value) {
      const review = props.item.conditionReview
      const confirmed = review?.status === 'confirmed' && review.source_text.trim() === props.item.conditionText.trim() ? review.confirmed : null
      if (!submittedConfiguration.value || candidateSignature(confirmed) !== submittedConfiguration.value || candidateSignature(configurationDraft.value) !== submittedConfiguration.value) return
    }
    if (sameSegment && (hasUnsavedCandidate.value || hasUnsavedManualLabel.value)) {
      const review = props.item.conditionReview
      const currentSource = review?.source_text?.trim() === props.item.conditionText.trim()
      const confirmedCandidate = currentSource && review?.status === 'confirmed' ? review.confirmed : null
      const savedStructuredEdit = hasUnsavedCandidate.value && submittedCandidate.value
        && editorSourceText.value === props.item.conditionText.trim()
        && candidateSignature(confirmedCandidate) === submittedCandidate.value
        && candidateSignature(editableCandidate.value) === submittedCandidate.value
      const savedManualEdit = hasUnsavedManualLabel.value && submittedManualLabel.value !== null
        && confirmedCandidate && isManualBooleanFinalizeCard(props.item)
        && defaultManualBooleanLabel(props.item) === submittedManualLabel.value
        && manualBooleanLabel.value.trim() === submittedManualLabel.value
      if (!savedStructuredEdit && !savedManualEdit) return
    }
    resetCandidateFromReview()
    ruleEditorExpanded.value = false
    configurationEditing.value = false
    configurationDraft.value = null
    submittedConfiguration.value = ''
    manualBooleanEditing.value = false
    manualConversionChangesKind.value = false
  },
  { immediate: true, deep: true },
)

function handleTextareaRef(el: Element | ComponentPublicInstance | null) {
  props.setInlineTextareaRef(el instanceof Element ? el : null)
}

function updateWhen(value: RulePackageCondition) {
  if (!editableCandidate.value) return
  editableCandidate.value = { ...editableCandidate.value, when: value, preview: '' }
}

function setCurrentProcessAction(kind: 'include' | 'exclude') {
  if (!editableCandidate.value?.then || !currentProcessId.value) return
  editableCandidate.value = {
    ...editableCandidate.value,
    then: kind === 'include'
      ? { ...editableCandidate.value.then, include_process_ids: [currentProcessId.value], exclude_process_ids: [] }
      : { ...editableCandidate.value.then, include_process_ids: [], exclude_process_ids: [currentProcessId.value] },
  }
}

function changeRelationType(event: Event) {
  if (!editableCandidate.value?.relation) return
  editableCandidate.value = {
    ...editableCandidate.value, preview: '',
    relation: { ...editableCandidate.value.relation, relation_type: (event.target as HTMLSelectElement).value as ProcessRelationType },
  }
}

function changeSourceMatch(event: Event) {
  if (!editableCandidate.value?.relation) return
  editableCandidate.value = {
    ...editableCandidate.value, preview: '',
    relation: { ...editableCandidate.value.relation, source_match: (event.target as HTMLSelectElement).value as 'any' | 'all' },
  }
}

function isRelationSelected(kind: 'source' | 'target', processId: string) {
  const relation = editableCandidate.value?.relation
  if (!relation) return false
  return kind === 'source' ? relation.source_process_ids.includes(processId) : relation.target_process_ids.includes(processId)
}

function selectRelationOption(kind: 'source' | 'target', processId: string) {
  if (!editableCandidate.value?.relation) return
  const sourceIds = new Set(editableCandidate.value.relation.source_process_ids)
  const targetIds = new Set(editableCandidate.value.relation.target_process_ids)
  const selected = kind === 'source' ? sourceIds : targetIds
  const opposite = kind === 'source' ? targetIds : sourceIds
  if (selected.has(processId)) { selected.delete(processId) }
  else { selected.add(processId); opposite.delete(processId) }
  editableCandidate.value = {
    ...editableCandidate.value, preview: '',
    relation: { ...editableCandidate.value.relation, source_process_ids: Array.from(sourceIds), target_process_ids: Array.from(targetIds) },
  }
}

function removeRelationProcess(kind: 'source' | 'target', processId: string) {
  if (!editableCandidate.value?.relation) return
  const sourceIds = new Set(editableCandidate.value.relation.source_process_ids)
  const targetIds = new Set(editableCandidate.value.relation.target_process_ids)
  if (kind === 'source') sourceIds.delete(processId)
  else targetIds.delete(processId)
  editableCandidate.value = {
    ...editableCandidate.value, preview: '',
    relation: { ...editableCandidate.value.relation, source_process_ids: Array.from(sourceIds), target_process_ids: Array.from(targetIds) },
  }
}

function confirmCandidate() {
  if (!editableCandidate.value || !hasRuleAction.value || authoringError.value || editedSourceChanged.value || controlsDisabled.value) return
  submittedCandidate.value = candidateSignature(editableCandidate.value)
  emit('confirm-condition', props.item, JSON.parse(JSON.stringify(editableCandidate.value)))
}

function openConfigurationEditor(section: 'appearance' | 'relations', chooseMode = false) {
  if (controlsDisabled.value) return
  if (configurationEditing.value) {
    if (configurationEditorSection.value === section) {
      configurationEditing.value = false
      configurationDraft.value = null
      submittedConfiguration.value = ''
      resetCandidateFromReview()
    } else {
      configurationEditorSection.value = section
    }
    return
  }
  configurationEditorSection.value = section
  // Preserve historical exclusion or cross-process action rules in their
  // existing editor; opening them must never rewrite their meaning.
  const candidate = editableCandidate.value
  const legacyActions = candidate && (candidate.kind || 'condition') === 'condition' && (
    Boolean(candidate.then?.exclude_process_ids?.length)
    || candidate.then?.include_process_ids?.some(id => id !== currentProcessId.value)
  )
  const crossProcessRelation = candidate?.kind === 'process_relation' && candidate.relation && (
    candidate.relation.target_process_ids.length !== 1
    || candidate.relation.target_process_ids[0] !== currentProcessId.value
  )
  if (!chooseMode && (legacyActions || crossProcessRelation)) {
    if (!ruleEditorExpanded.value) beginEdit()
    return
  }
  if (props.selected) emit('toggle-selected', props.item)
  mainlineExpanded.value = true
  const transferringUnsavedEdit = hasUnsavedCandidate.value
  configurationRequiresModeSelection.value = chooseMode
  ruleEditorExpanded.value = false
  manualBooleanEditing.value = false
  const draft = makeConfigurationDraft()
  configurationDraft.value = draft
  savedConfigurationSignature.value = candidateSignature(transferringUnsavedEdit ? savedCandidate.value : draft)
  configurationSource.value = props.item.conditionText.trim()
  configurationEditing.value = true
}

function beginEdit() {
  if (controlsDisabled.value) return
  if (manualBooleanEditing.value) {
    cancelBooleanConversion()
    return
  }
  if (isManualBooleanFinalizeCard(props.item)) {
    beginBooleanConversion()
    return
  }
  if (props.selected) emit('toggle-selected', props.item)
  mainlineExpanded.value = true
  manualBooleanEditing.value = false
  if (editableCandidate.value && candidateMatchesCardMode.value && ['conditional', 'relation'].includes(cardRuleMode.value)) {
    if (ruleEditorExpanded.value) resetCandidateFromReview()
    ruleEditorExpanded.value = !ruleEditorExpanded.value
  } else emit('start-edit', props.item)
}

function makeConfigurationDraft(): RuleConditionCandidate {
  const candidate = editableCandidate.value
  if (candidate?.kind === 'process_configuration' && candidate.configuration) {
    const draft: RuleConditionCandidate = JSON.parse(JSON.stringify(candidate))
    const config = draft.configuration!
    if (config.occurrence === 'conditional' && !config.when && config.relations.length === 1
      && config.relations[0]?.relation_type === 'trigger_after' && config.relations[0].source_process_ids.length === 1) config.occurrence = 'associated'
    return draft
  }
  const manual = isManualBooleanFinalizeCard(props.item)
  const manualCandidate = manual ? buildManualBooleanRuleCandidate(props.item, defaultManualBooleanLabel(props.item)) : null
  const relation = candidate?.kind === 'process_relation' ? candidate.relation : null
  return {
    kind: 'process_configuration', preview: '',
    field_definitions: manualCandidate?.field_definitions || candidate?.field_definitions || [],
    configuration: {
      process_id: currentProcessId.value, occurrence: manual ? 'manual' : relation?.relation_type === 'trigger_after' && relation.source_process_ids.length === 1 ? 'associated' : cardRuleMode.value === 'mainline' ? 'always' : 'conditional',
      when: manualCandidate?.when || candidate?.when || null,
      relations: relation ? [JSON.parse(JSON.stringify(relation))] : [],
    },
  }
}
function saveConfiguration(candidate: RuleConditionCandidate) {
  if (controlsDisabled.value || configurationSourceChanged.value || validateAuthoredCandidate(candidate, currentProcessId.value).length) return
  submittedConfiguration.value = candidateSignature(candidate)
  emit('save-configuration', props.item, candidate)
}
function resetRule() { emit('reset', props.item) }
function reparseRule() { emit('parse-condition', props.item) }

function beginBooleanConversion() {
  if (props.selected) emit('toggle-selected', props.item)
  mainlineExpanded.value = true
  ruleEditorExpanded.value = false
  manualBooleanLabel.value = defaultManualBooleanLabel(props.item)
  savedManualBooleanLabel.value = manualBooleanLabel.value.trim()
  manualConversionChangesKind.value = !isManualBooleanFinalizeCard(props.item)
  submittedManualLabel.value = null
  manualBooleanEditing.value = true
}

function cancelBooleanConversion() {
  manualBooleanEditing.value = false
  manualBooleanLabel.value = savedManualBooleanLabel.value
  manualConversionChangesKind.value = false
  submittedManualLabel.value = null
}

function confirmBooleanConversion() {
  const label = manualBooleanLabel.value.trim()
  if (!label || controlsDisabled.value) return
  submittedManualLabel.value = label
  emit('set-boolean', props.item, label)
}

function formatConfirmedAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
.configuration-secondary-tools { display: flex; align-items: center; gap: 10px; }
.configuration-save-state { color: var(--pm-warning); font-size: 12px; }
.configuration-more { position: relative; flex: 0 0 auto; }
.configuration-more summary { cursor: pointer; list-style: none; padding: 7px 3px; color: var(--pm-text-muted); font-size: 12px; }
.configuration-more summary::after { content: '⌄'; margin-left: 6px; }
.configuration-more summary::-webkit-details-marker { display: none; }
.configuration-more summary:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.configuration-more-menu { position: absolute; left: 0; bottom: calc(100% + 6px); z-index: 4; display: grid; min-width: 156px; padding: 5px; border: 1px solid var(--pm-border); border-radius: 6px; background: var(--pm-surface); box-shadow: 0 4px 16px #0f172a14; }
.configuration-more-menu .ghost-btn { justify-content: flex-start; white-space: nowrap; }
/* ===== Secondary actions row ===== */
.configuration-secondary-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--pm-surface-subtle);
}

/* ===== Rule selection checkbox ===== */
.rule-selection {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: var(--pm-text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s;
}
.rule-selection:hover {
  color: var(--pm-text-secondary);
}
.rule-selection input {
  accent-color: var(--pm-primary);
  width: 14px;
  height: 14px;
}

/* ===== Mainline collapse toggle ===== */
.collapse-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid var(--pm-border);
  border-radius: 6px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-muted);
  cursor: pointer;
  transition: all 0.18s ease;
  flex-shrink: 0;
}
.collapse-toggle-btn:hover {
  background: var(--pm-surface-subtle);
  border-color: var(--pm-border-strong);
  color: var(--pm-text-muted);
}
.collapse-chevron {
  transition: transform 0.25s cubic-bezier(0.4, 0, 0.2, 1);
}
.collapse-chevron--open {
  transform: rotate(180deg);
}

/* ===== Mainline collapsed hint ===== */
.mainline-collapsed-hint {
  padding: 2px 0;
  display: flex;
  align-items: center;
}
.mainline-hint-text {
  font-size: 13px;
  color: var(--pm-text-muted);
  font-style: italic;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 640px;
}

/* ===== Inline edit ===== */
.inline-edit-box {
  display: flex;
  flex-direction: column;
  gap: 10px;
  width: 100%;
  margin-top: 6px;
}
.inline-edit-textarea {
  width: 100%;
  min-height: 88px;
  padding: 12px 14px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-card);
  font-size: 13px;
  line-height: 1.65;
  color: var(--pm-text);
  resize: vertical;
  outline: none;
  background: var(--pm-surface);
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.03);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.inline-edit-textarea:focus {
  border-color: var(--pm-primary-border);
  box-shadow: var(--pm-focus-ring);
}
.inline-edit-textarea::placeholder {
  color: var(--pm-border-strong);
}
.inline-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.inline-btn {
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-control);
  padding: 6px 16px;
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  letter-spacing: 0.01em;
}
.inline-btn-cancel {
  background: var(--pm-surface);
  color: var(--pm-text-muted);
}
.inline-btn-cancel:hover {
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  border-color: var(--pm-border-strong);
}
.inline-btn-save {
  background: var(--pm-primary);
  border-color: transparent;
  color: var(--pm-surface);
  box-shadow: 0 1px 3px rgba(36, 95, 168, 0.2);
}
.inline-btn-save:hover:not(:disabled) {
  background: var(--pm-primary);
  box-shadow: 0 2px 6px rgba(36, 95, 168, 0.3);
  transform: none;
}
.inline-btn-save:disabled {
  opacity: 0.45;
}

/* ===== Card base ===== */
.preview-card {
  padding: 10px 12px;
  border-radius: var(--pm-radius-card);
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  margin-bottom: 6px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.preview-card:last-child {
  margin-bottom: 0;
}
.preview-card-active {
  position: relative;
  border-color: var(--pm-primary-border);
  background: var(--pm-primary-soft);
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.06);
}
.preview-card-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: var(--pm-primary);
  border-radius: 0 3px 3px 0;
}

/* ===== Card header ===== */
.preview-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
  gap: 12px;
}
.preview-card-title-group {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  min-width: 0;
  flex: 1;
}
.preview-card-name-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.preview-card h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: var(--pm-text);
  letter-spacing: -0.015em;
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.preview-card h2 > span:first-child {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.preview-card h2::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 14px;
  background: var(--pm-primary);
  border-radius: 2px;
  flex-shrink: 0;
}

/* ===== Mode badge ===== */
.card-mode-badge {
  padding: 1px 6px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}
.card-mode-mainline {
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  border: 1px solid var(--pm-border);
}
.card-mode-conditional {
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
  border: 1px solid var(--pm-primary-border);
}
.card-mode-relation {
  background: var(--pm-success-soft);
  color: var(--pm-success);
  border: 1px solid var(--pm-success-border);
}
.card-mode-unresolved {
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  border: 1px solid var(--pm-warning-border);
}

/* ===== Card meta ===== */
.preview-card-meta {
  font-size: 12px;
  line-height: 1.45;
  color: var(--pm-text-muted);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* ===== Card actions ===== */
.preview-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-shrink: 0;
}

/* ===== Edited / unsaved badge ===== */
.edited-badge {
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-warning);
  background: var(--pm-warning-soft);
  border: 1px solid var(--pm-warning-border);
  border-radius: 6px;
  padding: 2px 8px;
  letter-spacing: 0.02em;
}

/* ===== Ghost button ===== */
.ghost-btn {
  border: none;
  background: transparent;
  color: var(--pm-primary);
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}
.ghost-btn:hover:not(:disabled) {
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
}
.ghost-btn:disabled {
  color: var(--pm-border-strong);
  cursor: not-allowed;
}

/* ===== Confirm rule primary button ===== */
.confirm-rule-primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 14px;
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-surface);
  background: var(--pm-primary);
  border: none;
  border-radius: var(--pm-radius-control);
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(16, 185, 129, 0.25);
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.confirm-rule-primary-btn:hover:not(:disabled) {
  background: var(--pm-primary);
  box-shadow: 0 3px 8px rgba(16, 185, 129, 0.35);
  transform: none;
}
.confirm-rule-primary-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}

/* ===== Ghost button subtle variant ===== */
.ghost-btn-subtle {
  opacity: 0.72;
  font-size: 12px;
}
.ghost-btn-subtle:hover {
  opacity: 1;
}

/* ===== Edit button ===== */
.preview-edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: var(--pm-surface);
  border: 1px solid var(--pm-primary-border);
  color: var(--pm-primary);
  padding: 3px 12px;
  border-radius: var(--pm-radius-control);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  height: 28px;
  gap: 4px;
  letter-spacing: 0.01em;
}
.preview-edit-btn:hover {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
  box-shadow: 0 1px 3px rgba(36, 95, 168, 0.1);
}
.preview-edit-btn-active {
  border-color: var(--pm-primary-border);
  background: var(--pm-primary-soft);
  color: #3349a5;
}
.preview-edit-btn-relation {
  border-color: var(--pm-success-border);
  color: var(--pm-success);
}
.preview-edit-btn-relation:hover {
  border-color: var(--pm-success-border);
  background: var(--pm-success-soft);
  color: var(--pm-success);
}
.preview-edit-btn:active {
  transform: none;
}

/* ===== Card body ===== */
.preview-card-body {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.preview-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  line-height: 1.5;
}
.preview-row-label {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  line-height: normal;
  padding-top: 2px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 500;
}
.preview-row-value {
  color: var(--pm-text-secondary);
  font-size: 13px;
  line-height: 1.55;
}
.condition-badge-label {
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid var(--pm-border);
}
.preview-row-content {
  flex: 1;
  min-width: 0;
}
.preview-condition {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--pm-text-secondary);
  font-weight: 400;
}

/* ===== Compact inline strips (pending / unresolved) ===== */
.card-inline-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: var(--pm-radius-control);
  font-size: 12px;
  line-height: 1.5;
}
.card-strip-warn {
  background: var(--pm-warning-soft);
  border: 1px solid var(--pm-warning-border);
}
.card-strip-pending {
  background: var(--pm-surface-subtle);
  border: 1px solid var(--pm-border);
}
.strip-label {
  font-weight: 600;
  color: var(--pm-text-secondary);
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 12px;
}
.strip-label-attention {
  color: var(--pm-warning);
}
.card-strip-warn .strip-label {
  color: var(--pm-warning);
}
.strip-desc {
  flex: 1;
  min-width: 0;
  color: var(--pm-text-muted);
  overflow-wrap: anywhere;
  line-height: 1.55;
}
.strip-action {
  flex-shrink: 0;
  border: 1px solid var(--pm-primary-border);
  border-radius: 6px;
  background: var(--pm-surface);
  color: var(--pm-primary);
  padding: 4px 10px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.strip-action:hover:not(:disabled) {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
}
.strip-action:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}

/* ===== Compact rule status line ===== */
.card-rule-compact {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.compact-status {
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 700;
  color: var(--pm-text-muted);
  letter-spacing: 0.03em;
  text-transform: none;
}
.compact-confirmed {
  color: var(--pm-success);
}
.compact-summary {
  flex: 1;
  min-width: 0;
  color: var(--pm-text-secondary);
  font-weight: 500;
  overflow-wrap: anywhere;
  line-height: 1.6;
}

/* ===== Editor footer ===== */
.candidate-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-top: 6px;
}
.confirm-rule-btn {
  flex-shrink: 0;
  border: 0;
  border-radius: var(--pm-radius-control);
  background: var(--pm-primary);
  color: var(--pm-surface);
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.02em;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(36, 95, 168, 0.25);
}
.confirm-rule-btn:hover:not(:disabled) {
  background: var(--pm-primary);
  box-shadow: 0 3px 8px rgba(36, 95, 168, 0.35);
  transform: none;
}
.confirm-rule-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
.manual-review-note {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-top: 0;
  border-left: 3px solid var(--pm-warning);
  padding: 4px 8px;
  background: var(--pm-warning-soft);
  color: var(--pm-warning);
  font-size: 12px;
  line-height: 1.5;
  border-radius: 0 6px 6px 0;
}
.manual-review-note strong {
  flex-shrink: 0;
  color: var(--pm-warning);
  font-size: 12px;
}

/* ===== Ghost button variant for Bool ===== */
.ghost-btn-bool {
  color: var(--pm-primary);
}
.ghost-btn-bool:hover {
  color: var(--pm-primary-hover);
}

/* ===== Boolean editor (inline in card body) ===== */
.manual-boolean-editor {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: var(--pm-radius-card);
  background: var(--pm-surface-subtle);
  border: 1px solid var(--pm-border);
  margin-top: 6px;
}
.manual-bool-tag {
  color: var(--pm-text-secondary);
  font-size: 13px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}
.manual-bool-input {
  flex: 1;
  min-width: 140px;
  height: 32px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-control);
  padding: 0 12px;
  color: var(--pm-text);
  font-size: 13px;
  background: var(--pm-surface);
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.manual-bool-input:focus {
  border-color: var(--pm-primary-border);
  box-shadow: var(--pm-focus-ring);
}
.manual-bool-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.manual-bool-btn {
  height: 32px;
  padding: 0 14px;
  border-radius: var(--pm-radius-control);
  font-size: 13px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.01em;
}
.manual-bool-btn-cancel {
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  color: var(--pm-text-muted);
}
.manual-bool-btn-cancel:hover {
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  border-color: var(--pm-border-strong);
}
.manual-bool-btn-save {
  background: var(--pm-primary);
  border: 1px solid transparent;
  color: var(--pm-surface);
  box-shadow: 0 1px 3px rgba(36, 95, 168, 0.2);
}
.manual-bool-btn-save:hover:not(:disabled) {
  background: var(--pm-primary);
  box-shadow: 0 2px 6px rgba(36, 95, 168, 0.3);
  transform: none;
}
.manual-bool-btn-save:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}

/* ===== Candidate editor ===== */
.candidate-editor {
  display: grid;
  gap: 12px;
  margin-top: 14px;
  padding-top: 14px;
  border-top: 1px solid var(--pm-surface-subtle);
}
.candidate-footer {
  margin-top: 6px;
}
.editor-note {
  color: var(--pm-text-muted);
  font-size: 12px;
  line-height: 1.45;
}
.confirmation-audit {
  margin-top: 8px;
  color: var(--pm-success);
  font-size: 12px;
  text-align: right;
  font-style: italic;
}

/* ===== Tag-based process editor ===== */
.action-editor-tag {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 10px;
}
.action-tag-column {
  position: relative;
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 10px 12px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-card);
  background: var(--pm-surface-subtle);
  transition: border-color 0.15s;
}
.action-tag-column:hover {
  border-color: var(--pm-border);
}
.action-title {
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: none;
}
.action-title-include {
  color: var(--pm-success);
}
.action-title-exclude {
  color: var(--pm-danger);
}
.relation-source-title {
  color: var(--pm-primary);
}
.relation-target-title {
  color: var(--pm-primary);
}

/* ===== Tag list ===== */
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  align-items: center;
  min-height: 28px;
}
.process-tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px 4px 12px;
  border-radius: 7px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.01em;
}
.process-tag-include {
  background: var(--pm-success-soft);
  color: var(--pm-success);
  border: 1px solid var(--pm-success-border);
}
.process-tag-exclude {
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
  border: 1px solid var(--pm-danger-border);
}
.process-tag-source {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  border: 1px solid var(--pm-primary-border);
}
.process-tag-target {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  border: 1px solid var(--pm-primary-border);
}

/* ===== Tag remove button ===== */
.tag-remove {
  background: none;
  border: none;
  cursor: pointer;
  color: inherit;
  opacity: 0.4;
  font-size: 14px;
  line-height: 1;
  padding: 0 0 0 2px;
  display: inline-flex;
  align-items: center;
  transition: opacity 0.15s;
}
.tag-remove:hover {
  opacity: 1;
}

/* ===== Add tag button ===== */
.tag-add-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 10px;
  border: 1.5px dashed var(--pm-border-strong);
  border-radius: 7px;
  background: transparent;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}
.tag-add-btn:hover {
  border-color: var(--pm-primary);
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
}
.tag-add-btn-active {
  border-style: solid;
  border-color: var(--pm-primary);
  color: var(--pm-primary-hover);
  background: var(--pm-primary-soft);
}

/* ===== Process picker dropdown ===== */
.process-picker-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 100;
  width: max(220px, 100%);
  background: var(--pm-surface);
  border: 1px solid var(--pm-border);
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12), 0 4px 12px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}
.picker-search {
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-bottom: 1px solid var(--pm-surface-subtle);
  font-size: 13px;
  color: var(--pm-text);
  outline: none;
  background: var(--pm-surface-subtle);
  font-family: inherit;
}
.picker-search::placeholder {
  color: var(--pm-text-muted);
}
.picker-options {
  max-height: 180px;
  overflow-y: auto;
  padding: 4px;
}
.picker-option {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding: 8px 12px;
  border: none;
  border-radius: var(--pm-radius-control);
  background: transparent;
  color: var(--pm-text-secondary);
  font-size: 13px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}
.picker-option:hover {
  background: var(--pm-surface-subtle);
}
.picker-option-selected {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  font-weight: 600;
}
.picker-option-selected:hover {
  background: var(--pm-primary-soft);
}
.picker-check {
  color: var(--pm-primary);
  flex-shrink: 0;
}
.picker-empty {
  padding: 12px 14px;
  color: var(--pm-text-muted);
  font-size: 13px;
  text-align: center;
}

/* ===== Picker pop transition ===== */
.picker-pop-enter-active {
  transition: opacity 0.18s ease, transform 0.18s cubic-bezier(0.4, 0, 0.2, 1);
}
.picker-pop-leave-active {
  transition: opacity 0.12s ease, transform 0.12s ease;
}
.picker-pop-enter-from {
  opacity: 0;
  transform: translateY(-6px) scale(0.96);
}
.picker-pop-leave-to {
  opacity: 0;
  transform: translateY(-3px) scale(0.98);
}

/* ===== Relation editor ===== */
.relation-editor {
  display: grid;
  gap: 12px;
}
.relation-control-row {
  display: flex;
  align-items: center;
  gap: 12px;
  font-size: 13px;
  color: var(--pm-text-secondary);
}
.relation-select {
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  border: 1px solid var(--pm-border);
  border-radius: var(--pm-radius-control);
  background: var(--pm-surface);
  color: var(--pm-text);
  font-size: 13px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.relation-select:focus {
  border-color: var(--pm-primary-border);
  box-shadow: var(--pm-focus-ring);
}

/* ===== Responsive ===== */
.preview-card { border-radius: var(--pm-radius-card); box-shadow: var(--pm-shadow-card); }
.preview-card-active { background: var(--pm-primary-soft); border-color: var(--pm-primary-border); box-shadow: var(--pm-shadow-card); }
.preview-card-active::before, .preview-card h2::before { background: var(--pm-primary); }
.preview-card-header { flex-wrap: wrap; gap: 8px 12px; }
.preview-card h2 { font-size: 13px; font-weight: 600; line-height: 20px; flex-wrap: wrap; }
.preview-card h2 > span:first-child { white-space: normal; overflow-wrap: anywhere; }
.preview-card-actions { display: grid; grid-template-columns: 54px 76px 76px; gap: 6px; align-items: center; }
.card-selection-slot, .card-confirm-slot, .card-edit-slot { display: flex; align-items: center; justify-content: flex-end; min-width: 0; }
.card-confirm-slot { flex-wrap: wrap; gap: 4px; }
.card-confirm-slot .confirm-rule-primary-btn, .card-edit-slot .preview-edit-btn { width: 100%; white-space: nowrap; }
.preview-card h2 .collapse-toggle-btn { flex: 0 0 28px; width: 28px; height: 28px; border-radius: var(--pm-radius-control); }
.preview-card-active .configuration-editor { background: var(--pm-surface); }
.card-mode-badge, .edited-badge { border-radius: 4px; font-size: 12px; font-weight: 500; line-height: 16px; }
.mainline-hint-text { white-space: normal; font-style: normal; }
.inline-btn, .preview-edit-btn, .confirm-rule-primary-btn, .confirm-rule-btn, .manual-bool-btn { min-height: var(--pm-control-height-small); height: auto; padding: 3px 8px; border-radius: var(--pm-radius-control); font-size: 12px; line-height: 20px; font-weight: 500; box-shadow: none; }
.confirm-rule-primary-btn, .confirm-rule-btn, .inline-btn-save, .manual-bool-btn-save { background: var(--pm-primary); border-color: var(--pm-primary); color: #fff; }
.confirm-rule-primary-btn:hover:not(:disabled), .confirm-rule-btn:hover:not(:disabled), .inline-btn-save:hover:not(:disabled), .manual-bool-btn-save:hover:not(:disabled) { background: var(--pm-primary-hover); box-shadow: none; transform: none; }
.preview-edit-btn:hover { box-shadow: none; }
.preview-card button:focus-visible, .preview-card summary:focus-visible, .preview-card input[type=checkbox]:focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.card-inline-strip, .manual-review-note { flex-wrap: wrap; border-radius: var(--pm-radius-control); }
.strip-desc { flex-basis: 180px; }
.candidate-footer, .manual-boolean-editor, .manual-bool-actions { flex-wrap: wrap; }
.candidate-footer { border-top: 1px solid var(--pm-border); padding-top: 10px; }
.inline-edit-textarea:focus, .manual-bool-input:focus, .relation-select:focus { border-color: var(--pm-primary); box-shadow: var(--pm-focus-ring); }
.relation-select { height: var(--pm-control-height); border-radius: var(--pm-radius-control); font-size: 13px; }
.configuration-more-menu { border-color: var(--pm-border); box-shadow: var(--pm-shadow-popup); }

@media (max-width: 1080px) {
  .preview-card-actions {
    justify-content: flex-start;
    margin-top: 0;
  }
  .preview-condition {
    font-size: 13px;
  }
  .action-editor-tag {
    grid-template-columns: 1fr;
  }
  .candidate-summary-row,
  .rule-summary-strip {
    align-items: flex-start;
    flex-direction: column;
  }
}
@media (max-width: 600px) {
  .preview-card-header { align-items: stretch; }
  .preview-card-title-group { flex-basis: 100%; }
  .preview-card-actions { margin-left: auto; }
}
</style>
