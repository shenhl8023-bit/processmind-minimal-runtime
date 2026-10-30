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
            <span class="card-mode-badge" :class="`card-mode-${cardRuleMode}`">{{ modeLabel }}</span>
          </h2>
          <div v-if="metaLabel" class="preview-card-meta">{{ metaLabel }}</div>
        </div>
      </div>
      <div class="preview-card-actions">
        <label v-if="selectable && !inlineEditing && !ruleEditorExpanded && !manualBooleanEditing && !configurationEditing" class="rule-selection">
          <input type="checkbox" :checked="selected" :disabled="controlsDisabled" :aria-label="`选择${displayName}规则`" @change="$emit('toggle-selected', item)" />
          <span>选择</span>
        </label>
        <span v-if="conditionBusy" class="edited-badge" role="status">处理中…</span>
        <span v-if="hasUnsavedChanges" class="edited-badge" role="status">未保存</span>
        <button
          v-if="!hasUnsavedChanges && !configurationEditing && !inlineEditing && !manualBooleanEditing && editableCandidate && candidateMatchesCardMode && ['conditional','relation'].includes(cardRuleMode) && effectiveStatus !== 'confirmed'"
          type="button" class="confirm-rule-primary-btn"
          :disabled="controlsDisabled || !hasRuleAction" @click="confirmCandidate"
        >确认规则</button>
        <span v-else-if="!hasUnsavedChanges && !inlineEditing && effectiveStatus === 'confirmed' && cardRuleMode !== 'mainline'" class="confirmed-status-pill">✓ 已确认</span>
        <template v-if="!inlineEditing">
          <button
            type="button"
            class="preview-edit-btn"
            :class="{ 'preview-edit-btn-active': configurationEditing && configurationEditorSection === 'appearance' }"
            :disabled="controlsDisabled"
            :aria-expanded="configurationEditing && configurationEditorSection === 'appearance'"
            @click="openConfigurationEditor('appearance')"
          >{{ configurationEditing && configurationEditorSection === 'appearance' ? '取消' : '设置出现方式' }}</button>
          <button
            type="button"
            class="preview-edit-btn preview-edit-btn-relation"
            :class="{ 'preview-edit-btn-active': configurationEditing && configurationEditorSection === 'relations' }"
            :disabled="controlsDisabled || !processOptions.some(process => process.process_id !== exportProcessIdForItem(item))"
            :aria-expanded="configurationEditing && configurationEditorSection === 'relations'"
            @click="openConfigurationEditor('relations')"
          >{{ configurationEditing && configurationEditorSection === 'relations' ? '取消' : '设置工序关联' }}</button>
          <button v-if="ruleEditorExpanded || manualBooleanEditing" type="button" class="preview-edit-btn" :disabled="controlsDisabled" @click="beginEdit">取消修改</button>
        </template>
        <!-- Mainline collapse toggle -->
        <button
          v-if="cardRuleMode === 'mainline'"
          class="collapse-toggle-btn"
          @click="mainlineExpanded = !mainlineExpanded"
          :title="mainlineExpanded ? '折叠' : '展开详情'"
        >
          <svg
            class="collapse-chevron"
            :class="{ 'collapse-chevron--open': mainlineExpanded }"
            width="13" height="13"
            viewBox="0 0 16 16"
            fill="none"
          >
            <path d="M4 6l4 4 4-4" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
        </button>
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
          :section="configurationEditorSection"
          @update:model-value="configurationDraft = $event" @save="saveConfiguration"
        />
        <div class="configuration-secondary-actions">
          <button type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="$emit('start-edit', item)">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M11.5 1.5l3 3L5 14H2v-3L11.5 1.5z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            修改原始描述
          </button>
          <button v-if="item.edited" type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="resetRule">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 8a6 6 0 0 1 10.2-4.2M14 2v4h-4M14 8a6 6 0 0 1-10.2 4.2M2 14v-4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            恢复默认
          </button>
          <button type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="reparseRule">
            <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3-2M8 2a6 6 0 1 0 5.3 3.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
            重新识别
          </button>
        </div>
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
            <button type="button" class="ghost-btn" :disabled="controlsDisabled || hasUnsavedChanges" @click="$emit('start-edit', item)">修改原始描述</button>
            <RuleConditionNodeEditor
              v-if="candidateKind === 'condition' && editableCandidate.when"
              :model-value="editableCandidate.when"
              :fields="editorFields"
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
              <button class="confirm-rule-btn" :disabled="controlsDisabled || !hasRuleAction || editedSourceChanged" @click="confirmCandidate">
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
        <button v-if="item.edited" type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="resetRule">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M2 8a6 6 0 0 1 10.2-4.2M14 2v4h-4M14 8a6 6 0 0 1-10.2 4.2M2 14v-4h4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          恢复默认
        </button>
        <button type="button" class="ghost-btn ghost-btn-icon" :disabled="controlsDisabled || hasUnsavedChanges" @click="reparseRule">
          <svg width="12" height="12" viewBox="0 0 16 16" fill="none"><path d="M8 2v4l3-2M8 2a6 6 0 1 0 5.3 3.2" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>
          重新识别
        </button>
      </div>
      <details v-if="!inlineEditing" class="rule-evidence">
        <summary>
          <svg class="evidence-icon" width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 1a7 7 0 1 0 0 14A7 7 0 0 0 8 1zm0 10.5v-4m0-2.5h.01" stroke="currentColor" stroke-width="1.4" stroke-linecap="round" stroke-linejoin="round"/></svg>
          查看判定依据
        </summary>
        <div class="evidence-content">
          <div class="evidence-item" v-if="item.analysisDraftContext">
            <div class="evidence-item-label">第三步依据</div>
            <div class="evidence-item-value">{{ item.analysisDraftContext }}</div>
          </div>
          <div class="evidence-item">
            <div class="evidence-item-label">原始描述</div>
            <div class="evidence-item-value">{{ item.conditionText }}</div>
          </div>
          <div v-if="editableCandidate" class="candidate-recognition">
            <span class="candidate-type-chip" :class="`candidate-type-${candidateRecognition.kind}`">{{ candidateRecognition.label }}</span>
            <span class="candidate-recognition-reason">{{ editableCandidate.evidence || candidateRecognition.reason }}</span>
          </div>
        </div>
      </details>

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
import { configurationSummary } from '@/utils/processConfigurationEditor'
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
const configurationEditorSection = ref<'appearance' | 'relations'>('appearance')
const configurationDraft = ref<RuleConditionCandidate | null>(null)
const savedConfigurationSignature = ref('')
const submittedConfiguration = ref('')
const configurationSource = ref('')
const configurationFields = computed(() => Array.from(new Map([
  ...props.conditionFields, ...(configurationDraft.value?.field_definitions || []),
].map(field => [field.key, field])).values()))
const hasUnsavedConfiguration = computed(() => configurationEditing.value && candidateSignature(configurationDraft.value) !== savedConfigurationSignature.value)
const configurationSourceChanged = computed(() => configurationEditing.value && configurationSource.value !== props.item.conditionText.trim())

// Only executable content makes an edit dirty. Recognition prose and server
// object-key ordering may change without changing the rule being saved.
function candidateSignature(candidate: RuleConditionCandidate | null | undefined): string {
  if (!candidate) return ''
  const kind = candidate.kind || 'condition'
  const content = kind === 'process_configuration'
    ? { kind, configuration: candidate.configuration, field_definitions: candidate.field_definitions || [] }
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
        field_definitions: candidate.field_definitions || [],
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
const modeLabel = computed(() => isManualBooleanFinalizeCard(props.item) ? '人工选择' : ({
  mainline: '始终保留',
  conditional: '条件判断',
  relation: '工序关联',
  unresolved: '条件待补充',
})[cardRuleMode.value])
const candidateKind = computed(() => editableCandidate.value?.kind || 'condition')
const editorFields = computed(() => Array.from(new Map([
  ...props.conditionFields, ...(editableCandidate.value?.field_definitions || []),
].map(field => [field.key, field])).values()))
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
  hasCrossProcessConditionTarget.value
  || (
    effectiveStatus.value === 'pending_confirmation'
    && !isSafeForBatchRuleConfirmation(props.item)
  )
))
const manualReviewReason = computed(() => {
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
  if (candidate.kind === 'process_configuration' && candidate.configuration) return configurationSummary(candidate.configuration, props.displayName, editorFields.value, props.processOptions)
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
  return `${formatRuleCondition(candidate.when, editorFields.value)} → ${actions}`
})
const candidateRecognition = computed(() => {
  const candidate = editableCandidate.value
  const text = props.item.conditionText
  if ((candidate?.kind || 'condition') === 'process_relation') {
    const type = candidate?.relation?.relation_type || 'trigger_after'
    const label = ({
      trigger_after: '工序关系 · 触发并排序',
      order_after: '工序关系 · 先后约束',
      requires: '工序关系 · 前置依赖',
      conflicts: '工序关系 · 互斥',
    } as const)[type]
    const reason = /互斥|不得同时|不能同时/.test(text)
      ? '原文包含互斥表达。'
      : /前置|依赖|必须.*完成/.test(text)
        ? '原文包含前置或依赖表达。'
        : /之后|完成后|前面|此前|之前|后/.test(text)
          ? '原文包含工序先后表达。'
          : '原文表达了工序之间的关联。'
    return { kind: 'relation', label, reason }
  }

  const field = firstConditionField(candidate?.when || null)
  const reason = field === 'special.requirements'
    ? '原文包含需求或特殊要求表达。'
    : field?.startsWith('material.')
      ? '原文包含材料牌号条件。'
      : field?.startsWith('precision.') || field?.startsWith('tolerance.') || field?.startsWith('surface.')
        ? '原文包含精度、公差或表面要求。'
        : field?.startsWith('cad.')
          ? '原文包含结构特征条件。'
          : '原文包含可执行的参数条件。'
  return { kind: 'condition', label: '条件规则', reason }
})
const filteredPickerOptions = computed(() => {
  const search = processPickerSearch.value.trim().toLowerCase()
  return props.processOptions.filter((p) => {
    return !search || p.display_name.toLowerCase().includes(search)
  })
})

// ---- Helpers ----
function firstConditionField(condition: RulePackageCondition | null | undefined): string | null {
  if (!condition) return null
  if ('field' in condition && condition.field) return condition.field
  if (Array.isArray((condition as any)?.all) && (condition as any).all.length > 0) return firstConditionField((condition as any).all[0])
  if (Array.isArray((condition as any)?.any) && (condition as any).any.length > 0) return firstConditionField((condition as any).any[0])
  if ((condition as any)?.not) return firstConditionField((condition as any).not)
  return null
}

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
  if (!editableCandidate.value || !hasRuleAction.value || editedSourceChanged.value || controlsDisabled.value) return
  submittedCandidate.value = candidateSignature(editableCandidate.value)
  emit('confirm-condition', props.item, JSON.parse(JSON.stringify(editableCandidate.value)))
}

function openConfigurationEditor(section: 'appearance' | 'relations') {
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
  const legacyRelation = candidate?.kind === 'process_relation' && candidate.relation && (
    candidate.relation.relation_type !== 'trigger_after'
    || candidate.relation.target_process_ids.length !== 1
    || candidate.relation.target_process_ids[0] !== currentProcessId.value
  )
  const crossProcessRelation = candidate?.kind === 'process_relation' && candidate.relation && (
    candidate.relation.target_process_ids.length !== 1
    || candidate.relation.target_process_ids[0] !== currentProcessId.value
  )
  if (legacyActions || crossProcessRelation) {
    if (!ruleEditorExpanded.value) beginEdit()
    return
  }
  if (!legacyActions && !legacyRelation && !ruleEditorExpanded.value && !manualBooleanEditing.value) {
    if (props.selected) emit('toggle-selected', props.item)
    mainlineExpanded.value = true
    const draft = makeConfigurationDraft()
    configurationDraft.value = draft
    savedConfigurationSignature.value = candidateSignature(draft)
    configurationSource.value = props.item.conditionText.trim()
    configurationEditing.value = true
    return
  }
  if (section === 'relations') {
    if (props.selected) emit('toggle-selected', props.item)
    mainlineExpanded.value = true
    const draft = makeConfigurationDraft()
    configurationDraft.value = draft
    savedConfigurationSignature.value = candidateSignature(draft)
    configurationSource.value = props.item.conditionText.trim()
    configurationEditing.value = true
    return
  }
  beginEdit()
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
  if (candidate?.kind === 'process_configuration' && candidate.configuration) return JSON.parse(JSON.stringify(candidate))
  const manual = isManualBooleanFinalizeCard(props.item)
  const manualCandidate = manual ? buildManualBooleanRuleCandidate(props.item, defaultManualBooleanLabel(props.item)) : null
  const relation = candidate?.kind === 'process_relation' ? candidate.relation : null
  return {
    kind: 'process_configuration', preview: '',
    field_definitions: manualCandidate?.field_definitions || candidate?.field_definitions || [],
    configuration: {
      process_id: currentProcessId.value, occurrence: manual ? 'manual' : cardRuleMode.value === 'mainline' ? 'always' : 'conditional',
      when: manualCandidate?.when || candidate?.when || null,
      relations: relation ? [JSON.parse(JSON.stringify(relation))] : [],
    },
  }
}
function saveConfiguration(candidate: RuleConditionCandidate) {
  if (controlsDisabled.value || configurationSourceChanged.value) return
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
/* ===== Secondary actions row ===== */
.configuration-secondary-actions {
  display: flex;
  gap: 6px;
  flex-wrap: wrap;
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid #f1f5f9;
}

/* ===== Rule selection checkbox ===== */
.rule-selection {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  color: #64748b;
  font-size: 12px;
  cursor: pointer;
  transition: color 0.15s;
}
.rule-selection:hover {
  color: #475569;
}
.rule-selection input {
  accent-color: #6366f1;
  width: 14px;
  height: 14px;
}

/* ===== Evidence / details section ===== */
.rule-evidence {
  order: 2;
  margin-top: 12px;
  color: #64748b;
  font-size: 12.5px;
  border: 1px solid #e8ecf2;
  border-radius: 10px;
  background: #fafbfd;
  overflow: hidden;
}
.rule-evidence > summary {
  cursor: pointer;
  padding: 10px 14px;
  font-weight: 500;
  color: #64748b;
  transition: all 0.15s;
  user-select: none;
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12.5px;
  list-style: none;
}
.rule-evidence > summary::-webkit-details-marker {
  display: none;
}
.rule-evidence > summary::after {
  content: '';
  display: inline-block;
  width: 0;
  height: 0;
  border-left: 4px solid transparent;
  border-right: 4px solid transparent;
  border-top: 5px solid currentColor;
  margin-left: auto;
  opacity: 0.5;
  transition: transform 0.2s ease;
}
.rule-evidence[open] > summary::after {
  transform: rotate(180deg);
}
.rule-evidence > summary:hover {
  color: #334155;
  background: rgba(0, 0, 0, 0.01);
}
.evidence-icon {
  flex-shrink: 0;
  opacity: 0.6;
}
.rule-evidence[open] > summary {
  border-bottom: 1px solid #f1f5f9;
}
.evidence-content {
  padding: 10px 14px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.evidence-item {
  display: flex;
  gap: 10px;
  align-items: flex-start;
  line-height: 1.55;
}
.evidence-item-label {
  flex-shrink: 0;
  color: #94a3b8;
  font-size: 11.5px;
  font-weight: 600;
  min-width: 60px;
  padding-top: 1px;
  letter-spacing: 0.02em;
}
.evidence-item-value {
  flex: 1;
  color: #334155;
  font-size: 12.5px;
  word-break: break-all;
}

/* ===== Mainline collapse toggle ===== */
.collapse-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 26px;
  height: 26px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #f8fafc;
  color: #94a3b8;
  cursor: pointer;
  transition: all 0.18s ease;
  flex-shrink: 0;
}
.collapse-toggle-btn:hover {
  background: #f1f5f9;
  border-color: #cbd5e1;
  color: #64748b;
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
  font-size: 12.5px;
  color: #94a3b8;
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
  border: 1px solid #dce3ed;
  border-radius: 10px;
  font-size: 13px;
  line-height: 1.65;
  color: #1e293b;
  resize: vertical;
  outline: none;
  background: #ffffff;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.03);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.inline-edit-textarea:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}
.inline-edit-textarea::placeholder {
  color: #cbd5e1;
}
.inline-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.inline-btn {
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 6px 16px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  letter-spacing: 0.01em;
}
.inline-btn-cancel {
  background: #ffffff;
  color: #64748b;
}
.inline-btn-cancel:hover {
  background: #f8fafc;
  color: #334155;
  border-color: #cbd5e1;
}
.inline-btn-save {
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  border-color: transparent;
  color: #ffffff;
  box-shadow: 0 1px 3px rgba(79, 70, 229, 0.2);
}
.inline-btn-save:hover:not(:disabled) {
  background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
  box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
  transform: translateY(-0.5px);
}
.inline-btn-save:disabled {
  opacity: 0.45;
}

/* ===== Card base ===== */
.preview-card {
  padding: 14px 16px;
  border-radius: 10px;
  background: #ffffff;
  border: 1px solid #e8ecf2;
  margin-bottom: 8px;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
}
.preview-card:last-child {
  margin-bottom: 0;
}
.preview-card-active {
  position: relative;
  border-color: #c7d2fe;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.02), #fafbff);
  box-shadow: 0 2px 8px rgba(99, 102, 241, 0.06);
}
.preview-card-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 8px;
  bottom: 8px;
  width: 3px;
  background: linear-gradient(180deg, #6366f1, #818cf8);
  border-radius: 0 3px 3px 0;
}

/* ===== Card header ===== */
.preview-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 6px;
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
  font-size: 14.5px;
  font-weight: 700;
  color: #0f172a;
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
  background: linear-gradient(180deg, #6366f1, #818cf8);
  border-radius: 2px;
  flex-shrink: 0;
}

/* ===== Mode badge ===== */
.card-mode-badge {
  padding: 2px 8px;
  border-radius: 6px;
  font-size: 10.5px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
  letter-spacing: 0.02em;
}
.card-mode-mainline {
  background: #f1f5f9;
  color: #475569;
  border: 1px solid #e2e8f0;
}
.card-mode-conditional {
  background: #eef2ff;
  color: #4338ca;
  border: 1px solid #c7d2fe;
}
.card-mode-relation {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}
.card-mode-unresolved {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #fdba74;
}

/* ===== Card meta ===== */
.preview-card-meta {
  font-size: 12px;
  line-height: 1.45;
  color: #94a3b8;
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
  font-size: 11px;
  font-weight: 600;
  color: #b45309;
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  border: 1px solid #fde68a;
  border-radius: 6px;
  padding: 2px 8px;
  letter-spacing: 0.02em;
}

/* ===== Ghost button ===== */
.ghost-btn {
  border: none;
  background: transparent;
  color: #6366f1;
  font-size: 12.5px;
  font-weight: 500;
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
  transition: all 0.15s;
}
.ghost-btn:hover:not(:disabled) {
  background: #eef2ff;
  color: #4338ca;
}
.ghost-btn:disabled {
  color: #cbd5e1;
  cursor: not-allowed;
}

/* ===== Confirm rule primary button ===== */
.confirm-rule-primary-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 14px;
  font-size: 11.5px;
  font-weight: 600;
  color: #ffffff;
  background: linear-gradient(135deg, #10b981 0%, #059669 100%);
  border: none;
  border-radius: 8px;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(16, 185, 129, 0.25);
  white-space: nowrap;
  letter-spacing: 0.02em;
}
.confirm-rule-primary-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #34d399 0%, #059669 100%);
  box-shadow: 0 3px 8px rgba(16, 185, 129, 0.35);
  transform: translateY(-0.5px);
}
.confirm-rule-primary-btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none;
}

/* ===== Confirmed status pill ===== */
.confirmed-status-pill {
  display: inline-flex;
  align-items: center;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  color: #15803d;
  background: linear-gradient(135deg, #f0fdf4, #dcfce7);
  border: 1px solid #bbf7d0;
  border-radius: 6px;
  line-height: 1.2;
  letter-spacing: 0.02em;
}

/* ===== Ghost button subtle variant ===== */
.ghost-btn-subtle {
  opacity: 0.72;
  font-size: 11.5px;
}
.ghost-btn-subtle:hover {
  opacity: 1;
}

/* ===== Edit button ===== */
.preview-edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border: 1px solid #c7d2fe;
  color: #4f46e5;
  padding: 3px 12px;
  border-radius: 8px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  height: 28px;
  gap: 4px;
  letter-spacing: 0.01em;
}
.preview-edit-btn:hover {
  background: #eef2ff;
  border-color: #a5b4fc;
  box-shadow: 0 1px 3px rgba(99, 102, 241, 0.1);
}
.preview-edit-btn-active {
  border-color: #98a9e8;
  background: #f4f6ff;
  color: #3349a5;
}
.preview-edit-btn-relation {
  border-color: #b7ded2;
  color: #176a55;
}
.preview-edit-btn-relation:hover {
  border-color: #8fcab8;
  background: #f0faf6;
  color: #145943;
}
.preview-edit-btn:active {
  transform: scale(0.97);
}

/* ===== Card body ===== */
.preview-card-body {
  display: flex;
  flex-direction: column;
  gap: 8px;
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
  color: #64748b;
  font-size: 12px;
  font-weight: 500;
}
.preview-row-value {
  color: #334155;
  font-size: 12.5px;
  line-height: 1.55;
}
.condition-badge-label {
  background: #f1f5f9;
  color: #475569;
  border-radius: 5px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid #e2e8f0;
}
.preview-row-content {
  flex: 1;
  min-width: 0;
}
.preview-condition {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  font-weight: 400;
}

/* ===== Compact inline strips (pending / unresolved) ===== */
.card-inline-strip {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 8px 12px;
  border-radius: 8px;
  font-size: 12px;
  line-height: 1.5;
}
.card-strip-warn {
  background: linear-gradient(135deg, #fffbeb, #fff7ed);
  border: 1px solid #fde68a;
}
.card-strip-pending {
  background: linear-gradient(135deg, #f8fafc, #f1f5f9);
  border: 1px solid #e2e8f0;
}
.strip-label {
  font-weight: 600;
  color: #475569;
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 11.5px;
}
.strip-label-attention {
  color: #b45309;
}
.card-strip-warn .strip-label {
  color: #c2410c;
}
.strip-desc {
  flex: 1;
  min-width: 0;
  color: #64748b;
  overflow-wrap: anywhere;
  line-height: 1.55;
}
.strip-action {
  flex-shrink: 0;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  background: #fff;
  color: #4f46e5;
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s;
}
.strip-action:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #a5b4fc;
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
  font-size: 12.5px;
  line-height: 1.5;
}
.compact-status {
  flex-shrink: 0;
  font-size: 10.5px;
  font-weight: 700;
  color: #64748b;
  letter-spacing: 0.03em;
  text-transform: none;
}
.compact-confirmed {
  color: #15803d;
}
.compact-summary {
  flex: 1;
  min-width: 0;
  color: #334155;
  font-weight: 550;
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
  border-radius: 8px;
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  color: #fff;
  padding: 7px 16px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  letter-spacing: 0.02em;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  box-shadow: 0 1px 3px rgba(79, 70, 229, 0.25);
}
.confirm-rule-btn:hover:not(:disabled) {
  background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
  box-shadow: 0 3px 8px rgba(79, 70, 229, 0.35);
  transform: translateY(-0.5px);
}
.confirm-rule-btn:disabled {
  cursor: not-allowed;
  opacity: 0.45;
}
.candidate-recognition {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 6px;
  margin-top: 6px;
  color: #64748b;
  font-size: 11px;
  line-height: 1.5;
  padding: 0 12px;
}
.candidate-type-chip {
  display: inline-flex;
  align-items: center;
  min-height: 20px;
  padding: 1px 8px;
  border: 1px solid #c7d2fe;
  border-radius: 5px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 10.5px;
  font-weight: 600;
  letter-spacing: 0.02em;
}
.candidate-type-relation {
  border-color: #a7f3d0;
  background: #ecfdf5;
  color: #047857;
}
.manual-review-note {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  margin-top: 8px;
  border-left: 3px solid #f59e0b;
  padding: 8px 10px;
  background: linear-gradient(135deg, #fffbeb, #fef3c7);
  color: #92400e;
  font-size: 11.5px;
  line-height: 1.5;
  border-radius: 0 6px 6px 0;
}
.manual-review-note strong {
  flex-shrink: 0;
  color: #b45309;
  font-size: 11.5px;
}

/* ===== Ghost button variant for Bool ===== */
.ghost-btn-bool {
  color: #4f46e5;
}
.ghost-btn-bool:hover {
  color: #4338ca;
}

/* ===== Boolean editor (inline in card body) ===== */
.manual-boolean-editor {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 14px;
  border-radius: 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  margin-top: 6px;
}
.manual-bool-tag {
  color: #334155;
  font-size: 12.5px;
  font-weight: 600;
  white-space: nowrap;
  flex-shrink: 0;
}
.manual-bool-input {
  flex: 1;
  min-width: 140px;
  height: 32px;
  border: 1px solid #dce3ed;
  border-radius: 8px;
  padding: 0 12px;
  color: #1e293b;
  font-size: 12.5px;
  background: #ffffff;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.manual-bool-input:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
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
  border-radius: 8px;
  font-size: 12.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.01em;
}
.manual-bool-btn-cancel {
  background: #ffffff;
  border: 1px solid #dce3ed;
  color: #64748b;
}
.manual-bool-btn-cancel:hover {
  background: #f1f5f9;
  color: #334155;
  border-color: #cbd5e1;
}
.manual-bool-btn-save {
  background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%);
  border: 1px solid transparent;
  color: #ffffff;
  box-shadow: 0 1px 3px rgba(79, 70, 229, 0.2);
}
.manual-bool-btn-save:hover:not(:disabled) {
  background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%);
  box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
  transform: translateY(-0.5px);
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
  border-top: 1px solid #f1f5f9;
}
.candidate-footer {
  margin-top: 6px;
}
.editor-note {
  color: #94a3b8;
  font-size: 11.5px;
  line-height: 1.45;
}
.confirmation-audit {
  margin-top: 8px;
  color: #6b7d6f;
  font-size: 10.5px;
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
  border: 1px solid #e8ecf2;
  border-radius: 10px;
  background: #fafbfd;
  transition: border-color 0.15s;
}
.action-tag-column:hover {
  border-color: #dce3ed;
}
.action-title {
  font-size: 10.5px;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: none;
}
.action-title-include {
  color: #059669;
}
.action-title-exclude {
  color: #dc2626;
}
.relation-source-title {
  color: #3b82f6;
}
.relation-target-title {
  color: #7c3aed;
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
  font-size: 11.5px;
  font-weight: 600;
  line-height: 1;
  letter-spacing: 0.01em;
}
.process-tag-include {
  background: #ecfdf5;
  color: #047857;
  border: 1px solid #a7f3d0;
}
.process-tag-exclude {
  background: #fef2f2;
  color: #b91c1c;
  border: 1px solid #fecaca;
}
.process-tag-source {
  background: #eff6ff;
  color: #1d4ed8;
  border: 1px solid #bfdbfe;
}
.process-tag-target {
  background: #f5f3ff;
  color: #6d28d9;
  border: 1px solid #ddd6fe;
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
  border: 1.5px dashed #cbd5e1;
  border-radius: 7px;
  background: transparent;
  color: #64748b;
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.18s ease;
}
.tag-add-btn:hover {
  border-color: #6366f1;
  color: #6366f1;
  background: #eef2ff;
}
.tag-add-btn-active {
  border-style: solid;
  border-color: #4f46e5;
  color: #4338ca;
  background: #eef2ff;
}

/* ===== Process picker dropdown ===== */
.process-picker-dropdown {
  position: absolute;
  top: calc(100% + 6px);
  left: 0;
  z-index: 100;
  width: max(220px, 100%);
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 12px;
  box-shadow: 0 12px 32px rgba(15, 23, 42, 0.12), 0 4px 12px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}
.picker-search {
  width: 100%;
  padding: 10px 14px;
  border: none;
  border-bottom: 1px solid #f1f5f9;
  font-size: 12.5px;
  color: #1e293b;
  outline: none;
  background: #f8fafc;
  font-family: inherit;
}
.picker-search::placeholder {
  color: #94a3b8;
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
  border-radius: 8px;
  background: transparent;
  color: #334155;
  font-size: 12.5px;
  text-align: left;
  cursor: pointer;
  transition: background 0.12s ease;
}
.picker-option:hover {
  background: #f8fafc;
}
.picker-option-selected {
  background: #eef2ff;
  color: #3730a3;
  font-weight: 600;
}
.picker-option-selected:hover {
  background: #e0e7ff;
}
.picker-check {
  color: #4f46e5;
  flex-shrink: 0;
}
.picker-empty {
  padding: 12px 14px;
  color: #94a3b8;
  font-size: 12.5px;
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
  font-size: 12.5px;
  color: #475569;
}
.relation-select {
  flex: 1;
  min-width: 0;
  height: 36px;
  padding: 0 10px;
  border: 1px solid #dce3ed;
  border-radius: 8px;
  background: #fff;
  color: #1e293b;
  font-size: 12.5px;
  outline: none;
  transition: border-color 0.15s, box-shadow 0.15s;
}
.relation-select:focus {
  border-color: #818cf8;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
}

/* ===== Responsive ===== */
@media (max-width: 1080px) {
  .preview-card-actions {
    justify-content: flex-start;
    margin-top: 12px;
  }
  .preview-condition {
    font-size: 16px;
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
</style>
