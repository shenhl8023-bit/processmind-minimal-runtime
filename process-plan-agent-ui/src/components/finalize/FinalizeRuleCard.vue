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
        <span v-if="item.edited" class="edited-badge">{{ editedBadge }}</span>
        <button
          v-if="item.edited && !inlineEditing"
          class="ghost-btn reset-inline-btn"
          @click="$emit('reset', item)"
        >
          恢复默认
        </button>
        <button
          v-if="!inlineEditing"
          class="preview-edit-btn"
          @click="$emit('start-edit', item)"
        >
          <svg class="edit-btn-svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          <span>{{ cardRuleMode === 'mainline' ? '改为条件工序' : editLabel }}</span>
        </button>
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

    <!-- Mainline collapsed: minimal one-line hint -->
    <div v-if="cardRuleMode === 'mainline' && !mainlineExpanded" class="mainline-collapsed-hint">
      <span class="mainline-hint-text">{{ item.conditionText || '主线工序，默认纳入路线' }}</span>
    </div>

    <!-- Full card body -->
    <div v-else class="preview-card-body">
      <div class="preview-row">
        <div class="preview-row-label">
          <span class="condition-badge-label">{{ conditionLabel }}</span>
        </div>
        <div class="preview-row-content preview-condition">
          <div v-if="inlineEditing" class="inline-edit-box">
            <textarea
              :value="inlineEditingText"
              class="inline-edit-textarea"
              rows="3"
              :ref="handleTextareaRef"
              placeholder="请输入工序规则，例如：当外圆尺寸精度要求达到IT8时，纳入磨外圆工序。"
              @input="$emit('update:inlineEditingText', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
            <div class="inline-edit-actions">
              <button class="inline-btn inline-btn-cancel" @click="$emit('cancel')">取消</button>
              <button class="inline-btn inline-btn-save" @click="$emit('save', item)">保存</button>
            </div>
          </div>
          <div v-else>{{ item.conditionText }}</div>
        </div>
      </div>

      <section v-if="!inlineEditing && cardRuleMode === 'unresolved'" class="rule-summary-strip rule-summary-unresolved">
        <div>
          <span class="summary-status">条件待补充</span>
          <p>当前描述还缺少具体判断依据，请补充判断字段、比较关系或明确取值。</p>
        </div>
        <button class="summary-action" @click="$emit('start-edit', item)">补充条件</button>
      </section>

      <section
        v-else-if="!inlineEditing && ['conditional', 'relation'].includes(cardRuleMode)"
        class="rule-review-panel"
        :class="`rule-review-${effectiveStatus}`"
      >
        <!-- Pending: no candidate yet -->
        <div v-if="!editableCandidate || !candidateMatchesCardMode" class="rule-summary-strip rule-summary-pending">
          <div>
            <span class="summary-status" :class="{ 'summary-status-attention': sourceTextChanged }">{{ pendingStatusLabel }}</span>
            <p>{{ pendingStatusDetail }}</p>
          </div>
          <button class="summary-action" :disabled="conditionBusy" @click="$emit('parse-condition', item)">
            {{ pendingActionLabel }}
          </button>
        </div>

        <!-- Has candidate -->
        <template v-else>
          <div class="candidate-summary-row">
            <div class="candidate-summary-copy">
              <span class="summary-status" :class="{ confirmed: effectiveStatus === 'confirmed' }">
                {{ effectiveStatus === 'confirmed' ? '已审核' : '待审核' }}
              </span>
              <strong>{{ candidateSummary }}</strong>
              <div class="candidate-recognition" aria-label="规则识别依据">
                <span class="candidate-recognition-label">识别结果</span>
                <span class="candidate-type-chip" :class="`candidate-type-${candidateRecognition.kind}`">{{ candidateRecognition.label }}</span>
                <span class="candidate-recognition-divider">依据</span>
                <span>{{ candidateRecognition.reason }}</span>
              </div>
            </div>
            <div class="candidate-summary-actions">
              <!-- One-click confirm (no need to expand) -->
              <button
                v-if="effectiveStatus !== 'confirmed'"
                class="quick-confirm-btn"
                :disabled="conditionBusy || !hasRuleAction"
                @click="confirmCandidate"
                title="直接审核通过，无需展开"
              >
                <svg width="11" height="11" viewBox="0 0 16 16" fill="none">
                  <path d="M3 8.5l3.5 4 6.5-7" stroke="currentColor" stroke-width="2.3" stroke-linecap="round" stroke-linejoin="round"/>
                </svg>
                审核通过
              </button>
              <button class="summary-action secondary" @click="ruleEditorExpanded = !ruleEditorExpanded">
                {{ ruleEditorExpanded ? '收起规则' : '修改规则' }}
              </button>
            </div>
          </div>

          <!-- Expanded rule editor -->
          <div v-if="ruleEditorExpanded" class="candidate-editor">
            <RuleConditionNodeEditor
              v-if="candidateKind === 'condition' && editableCandidate.when"
              :model-value="editableCandidate.when"
              :fields="editorFields"
              @update:model-value="updateWhen"
            />

            <!-- Tag-based process selector for condition rules -->
            <div v-if="candidateKind === 'condition'" class="action-editor-tag">
              <!-- Include processes -->
              <div class="action-tag-column" @click.stop>
                <span class="action-title action-title-include">纳入工序</span>
                <div class="tag-list">
                  <span
                    v-for="pid in (editableCandidate.then?.include_process_ids || [])"
                    :key="`inc-tag-${pid}`"
                    class="process-tag process-tag-include"
                  >
                    {{ processDisplayName(pid) }}
                    <button class="tag-remove" @click.stop="removeAction('include', pid)">×</button>
                  </span>
                  <button class="tag-add-btn" @click.stop="openPicker('include')">
                    <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
                      <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                    </svg>
                    添加
                  </button>
                </div>
                <Transition name="picker-pop">
                  <div v-if="processPickerOpen === 'include'" class="process-picker-dropdown" @click.stop>
                    <input
                      :ref="setSearchRef"
                      v-model="processPickerSearch"
                      class="picker-search"
                      placeholder="搜索工序名..."
                    />
                    <div class="picker-options">
                      <button
                        v-for="p in filteredPickerOptions"
                        :key="`pi-inc-${p.process_id}`"
                        class="picker-option"
                        :class="{ 'picker-option-selected': isActionSelected('include', p.process_id) }"
                        @click.stop="selectPickerOption('include', p.process_id)"
                      >
                        <span>{{ p.display_name }}</span>
                        <svg v-if="isActionSelected('include', p.process_id)" class="picker-check" width="12" height="12" viewBox="0 0 16 16" fill="none">
                          <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </button>
                      <div v-if="!filteredPickerOptions.length" class="picker-empty">无匹配工序</div>
                    </div>
                  </div>
                </Transition>
              </div>

              <!-- Exclude processes -->
              <div class="action-tag-column" @click.stop>
                <span class="action-title action-title-exclude">排除工序</span>
                <div class="tag-list">
                  <span
                    v-for="pid in (editableCandidate.then?.exclude_process_ids || [])"
                    :key="`exc-tag-${pid}`"
                    class="process-tag process-tag-exclude"
                  >
                    {{ processDisplayName(pid) }}
                    <button class="tag-remove" @click.stop="removeAction('exclude', pid)">×</button>
                  </span>
                  <button class="tag-add-btn" @click.stop="openPicker('exclude')">
                    <svg width="9" height="9" viewBox="0 0 12 12" fill="none">
                      <path d="M6 1v10M1 6h10" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"/>
                    </svg>
                    添加
                  </button>
                </div>
                <Transition name="picker-pop">
                  <div v-if="processPickerOpen === 'exclude'" class="process-picker-dropdown" @click.stop>
                    <input
                      :ref="setSearchRef"
                      v-model="processPickerSearch"
                      class="picker-search"
                      placeholder="搜索工序名..."
                    />
                    <div class="picker-options">
                      <button
                        v-for="p in filteredPickerOptions"
                        :key="`pi-exc-${p.process_id}`"
                        class="picker-option"
                        :class="{ 'picker-option-selected': isActionSelected('exclude', p.process_id) }"
                        @click.stop="selectPickerOption('exclude', p.process_id)"
                      >
                        <span>{{ p.display_name }}</span>
                        <svg v-if="isActionSelected('exclude', p.process_id)" class="picker-check" width="12" height="12" viewBox="0 0 16 16" fill="none">
                          <path d="M3 8l4 4 6-7" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
                        </svg>
                      </button>
                      <div v-if="!filteredPickerOptions.length" class="picker-empty">无匹配工序</div>
                    </div>
                  </div>
                </Transition>
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
              <label v-if="editableCandidate.relation.source_process_ids.length > 1" class="relation-control-row">
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
              <span class="editor-note">保存修改后，该规则将视为已审核。</span>
              <button class="confirm-rule-btn" :disabled="conditionBusy || !hasRuleAction" @click="confirmCandidate">
                保存修改
              </button>
            </div>
          </div>

          <div v-if="effectiveStatus === 'confirmed' && item.conditionReview?.confirmed_by" class="confirmation-audit">
            {{ item.conditionReview.confirmed_by }} · {{ formatConfirmedAt(item.conditionReview.confirmed_at) }}
          </div>
        </template>
      </section>
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
import { finalizeRuleMode } from '@/utils/finalizeRulePackage'
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
  conditionBusy: boolean
  setInlineTextareaRef: (el: Element | null) => void
}>()

const emit = defineEmits<{
  reset: [item: FinalizeCard]
  'start-edit': [item: FinalizeCard]
  cancel: []
  save: [item: FinalizeCard]
  'parse-condition': [item: FinalizeCard]
  'confirm-condition': [item: FinalizeCard, candidate: RuleConditionCandidate]
  'update:inlineEditingText': [value: string]
}>()

const editableCandidate = ref<RuleConditionCandidate | null>(null)
const ruleEditorExpanded = ref(false)
const mainlineExpanded = ref(false)

// Process picker
type PickerKind = 'include' | 'exclude' | 'source' | 'target'
const processPickerOpen = ref<PickerKind | null>(null)
const processPickerSearch = ref('')
const searchInputEl = ref<HTMLInputElement | null>(null)

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
  const review = props.item.conditionReview
  if (!review || review.source_text.trim() !== props.item.conditionText.trim()) return 'draft'
  return review.status
})
const sourceTextChanged = computed(() => {
  const review = props.item.conditionReview
  return Boolean(review?.source_text?.trim() && review.source_text.trim() !== props.item.conditionText.trim())
})
const cardRuleMode = computed(() => finalizeRuleMode(props.item))
const modeLabel = computed(() => ({
  mainline: '主线工序',
  conditional: '条件工序',
  relation: '关联工序',
  unresolved: '条件待补充',
})[cardRuleMode.value])
const candidateKind = computed(() => editableCandidate.value?.kind || 'condition')
const editorFields = computed(() => props.conditionFields)
const candidateMatchesCardMode = computed(() => {
  if (!editableCandidate.value) return false
  return cardRuleMode.value === 'relation'
    ? candidateKind.value === 'process_relation'
    : candidateKind.value === 'condition'
})
const pendingStatusLabel = computed(() => {
  if (props.conditionBusy) return '正在生成候选规则'
  if (sourceTextChanged.value) return '原文已修改，需要重新生成'
  if (editableCandidate.value) return '候选类型需要更新'
  return '待生成候选规则'
})
const pendingStatusDetail = computed(() => {
  if (sourceTextChanged.value) return '已保存的候选规则对应旧文本，重新生成后会按当前文字重新判断规则类型。'
  if (editableCandidate.value) return '当前候选与原文识别出的规则类型不一致，请重新生成后再审核。'
  return cardRuleMode.value === 'relation'
    ? '原文包含工序关系线索，可生成候选后核对触发和先后关系。'
    : '原文包含可执行条件，可生成候选后核对字段、取值和目标工序。'
})
const pendingActionLabel = computed(() => {
  if (props.conditionBusy) return '生成中…'
  return sourceTextChanged.value || editableCandidate.value ? '重新生成候选' : '生成候选'
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
  const candidate = editableCandidate.value
  if (!candidate) return ''
  if ((candidate.kind || 'condition') === 'process_relation' && candidate.relation) {
    const pm = new Map(props.processOptions.map(p => [p.process_id, p.display_name]))
    const src = Array.from(new Set(candidate.relation.source_process_ids.map(id => pm.get(id) || id))).join('、')
    const tgt = Array.from(new Set(candidate.relation.target_process_ids.map(id => pm.get(id) || id))).join('、')
    if (candidate.relation.relation_type === 'trigger_after') return `${src}进入路线 → 纳入${tgt}，并排在${src}之后`
    if (candidate.relation.relation_type === 'order_after') return `${tgt}如进入路线 → 排在${src}之后`
    if (candidate.relation.relation_type === 'requires') return `${tgt}进入路线 → 必须同时包含${src}`
    return `${tgt}与${src}不能同时进入路线`
  }
  const pm = new Map(props.processOptions.map(p => [p.process_id, p.display_name]))
  const includes = (candidate.then?.include_process_ids || []).map(id => pm.get(id) || id)
  const excludes = (candidate.then?.exclude_process_ids || []).map(id => pm.get(id) || id)
  const actions = [
    includes.length ? `纳入 ${includes.join('、')}` : '',
    excludes.length ? `排除 ${excludes.join('、')}` : '',
  ].filter(Boolean).join('；')
  return `${candidate.preview || '已调整结构化条件'} → ${actions}`
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
    if (processPickerOpen.value === 'exclude' && p.main) return false
    return !search || p.display_name.toLowerCase().includes(search)
  })
})

// ---- Helpers ----
function firstConditionField(condition: RulePackageCondition | null | undefined): string | null {
  if (!condition) return null
  if ('field' in condition) return condition.field
  if ('all' in condition) return firstConditionField(condition.all[0])
  if ('any' in condition) return firstConditionField(condition.any[0])
  return firstConditionField(condition.not)
}

function processDisplayName(processId: string) {
  return props.processOptions.find(p => p.process_id === processId)?.display_name || processId
}

function openPicker(kind: PickerKind) {
  processPickerOpen.value = processPickerOpen.value === kind ? null : kind
  processPickerSearch.value = ''
}

// ---- Watch candidate ----
watch(
  () => [props.item.conditionReview, props.item.conditionText] as const,
  () => {
    const review = props.item.conditionReview
    const sourceMatches = review?.source_text?.trim() === props.item.conditionText.trim()
    const candidate = sourceMatches ? (review?.confirmed || review?.candidate) : null
    editableCandidate.value = candidate ? JSON.parse(JSON.stringify(candidate)) : null
    ruleEditorExpanded.value = false
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

function isActionSelected(kind: 'include' | 'exclude', processId: string) {
  const action = editableCandidate.value?.then
  return kind === 'include'
    ? Boolean(action?.include_process_ids?.includes(processId))
    : Boolean(action?.exclude_process_ids?.includes(processId))
}

function selectPickerOption(kind: 'include' | 'exclude', processId: string) {
  if (!editableCandidate.value?.then) return
  const action = editableCandidate.value.then
  const includeIds = new Set(action.include_process_ids || [])
  const excludeIds = new Set(action.exclude_process_ids || [])
  if (kind === 'include') {
    if (includeIds.has(processId)) { includeIds.delete(processId) }
    else { includeIds.add(processId); excludeIds.delete(processId) }
  } else {
    if (excludeIds.has(processId)) { excludeIds.delete(processId) }
    else { excludeIds.add(processId); includeIds.delete(processId) }
  }
  editableCandidate.value = {
    ...editableCandidate.value,
    then: { ...action, include_process_ids: Array.from(includeIds), exclude_process_ids: Array.from(excludeIds) },
  }
}

function removeAction(kind: 'include' | 'exclude', processId: string) {
  if (!editableCandidate.value?.then) return
  const action = editableCandidate.value.then
  const includeIds = new Set(action.include_process_ids || [])
  const excludeIds = new Set(action.exclude_process_ids || [])
  if (kind === 'include') includeIds.delete(processId)
  else excludeIds.delete(processId)
  editableCandidate.value = {
    ...editableCandidate.value,
    then: { ...action, include_process_ids: Array.from(includeIds), exclude_process_ids: Array.from(excludeIds) },
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
  if (!editableCandidate.value || !hasRuleAction.value) return
  emit('confirm-condition', props.item, JSON.parse(JSON.stringify(editableCandidate.value)))
}

function formatConfirmedAt(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString('zh-CN', { hour12: false })
}
</script>

<style scoped>
/* ===== Mainline collapse ===== */
.collapse-toggle-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: 1px solid #e2e8f0;
  border-radius: 5px;
  background: #f8fafc;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
  flex-shrink: 0;
}
.collapse-toggle-btn:hover { background: #f1f5f9; border-color: #cbd5e1; color: #374151; }
.collapse-chevron { transition: transform 0.22s ease; }
.collapse-chevron--open { transform: rotate(180deg); }

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
  gap: 8px;
  width: 100%;
  margin-top: 4px;
}
.inline-edit-textarea {
  width: 100%;
  min-height: 84px;
  padding: 10px 12px;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  resize: vertical;
  outline: none;
  background: #ffffff;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
}
.inline-edit-textarea:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}
.inline-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}
.inline-btn {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}
.inline-btn-cancel { background: #ffffff; color: #64748b; }
.inline-btn-cancel:hover { background: #f8fafc; color: #334155; }
.inline-btn-save { background: #4f46e5; border-color: #4f46e5; color: #ffffff; }
.inline-btn-save:hover { background: #4338ca; border-color: #4338ca; }

/* ===== Reset btn ===== */
.reset-inline-btn {
  font-size: 12px;
  color: #64748b;
  margin-right: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.15s ease;
}
.reset-inline-btn:hover { color: #ef4444; background: rgba(239, 68, 68, 0.05); }

/* ===== Card base ===== */
.preview-card {
  padding: 12px 16px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #e8ecf2;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}
.preview-card:last-child { margin-bottom: 0; }
.preview-card-active {
  position: relative;
  border-color: #c7d2fe;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.03), #f8fafc);
}
.preview-card-active::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 3px;
  background: #6366f1;
  border-radius: 4px 0 0 4px;
  opacity: 0.8;
}

/* ===== Card header ===== */
.preview-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 7px;
}
.preview-card-title-group {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.preview-card-name-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}
.preview-card h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.preview-card h2::before {
  content: "";
  display: inline-block;
  width: 3px; height: 13px;
  background: #6366f1;
  border-radius: 2px;
  opacity: 0.8;
  flex-shrink: 0;
}
.card-mode-badge {
  padding: 2px 7px;
  border-radius: 999px;
  font-size: 10px;
  font-weight: 700;
}
.card-mode-mainline    { background: #e9eef5; color: #536176; }
.card-mode-conditional { background: #e7edfb; color: #3e5790; }
.card-mode-relation    { background: #e5f5ef; color: #236b58; }
.card-mode-unresolved  { background: #fff0e8; color: #a04b2e; }

.preview-card-meta {
  font-size: 12px;
  line-height: 1.45;
  color: #7c8aa5;
}
.preview-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}
.edited-badge {
  font-size: 12px; font-weight: 600;
  color: #92400e;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 4px;
  padding: 2px 6px;
}
.ghost-btn {
  border: none; background: transparent;
  color: #64748b; font-size: 13px; font-weight: 500;
  cursor: pointer; padding: 0 4px;
}
.ghost-btn:hover { color: #4f46e5; }
.preview-edit-btn {
  display: inline-flex; align-items: center; justify-content: center;
  background: #ffffff; border: 1px solid #c7d2fe; color: #4f46e5;
  padding: 2px 10px; border-radius: 6px; font-size: 12px; font-weight: 600;
  cursor: pointer; transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  height: 24px; gap: 4px;
}
.preview-edit-btn:hover { background: #eef2ff; border-color: #a5b4fc; }
.preview-edit-btn:active { transform: scale(0.97); }

/* ===== Card body ===== */
.preview-card-body {}
.preview-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 6px;
}
.preview-row-label {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  line-height: normal;
  padding-top: 2px;
}
.condition-badge-label {
  background: #f1f5f9; color: #475569;
  border-radius: 4px; padding: 2px 8px;
  font-size: 11px; font-weight: 600;
  white-space: nowrap; border: 1px solid #e2e8f0;
}
.preview-row-content { flex: 1; min-width: 0; }
.preview-condition {
  margin: 0; font-size: 13px; line-height: 1.6; color: #334155; font-weight: 400;
}

/* ===== Review panel ===== */
.rule-review-panel {
  margin-top: 10px; padding: 10px 12px;
  border: 1px solid #dce3ec; border-radius: 9px; background: #f8fafc;
}
.rule-review-confirmed { border-color: #b9dbc9; background: #f4fbf7; }
.rule-review-pending_confirmation { border-color: #cbd7ed; background: #f7f9fd; }

.rule-summary-strip,
.candidate-summary-row,
.candidate-footer {
  display: flex; align-items: center; justify-content: space-between; gap: 12px;
}
.rule-summary-strip { margin-top: 10px; padding: 9px 11px; border: 1px solid #dfe5ed; border-radius: 8px; background: #f9fafc; }
.rule-review-panel > .rule-summary-strip { margin: 0; padding: 0; border: none; background: transparent; }
.rule-summary-unresolved { border-color: #f0c8b9; background: #fff8f4; }
.summary-status { display: inline-flex; margin-bottom: 3px; color: #52647e; font-size: 10px; font-weight: 750; letter-spacing: .02em; }
.summary-status.confirmed { color: #2f7554; }
.summary-status-attention { color: #9a5b2d; }
.rule-summary-unresolved .summary-status { color: #a04b2e; }
.rule-summary-strip p { margin: 0; color: #748095; font-size: 11px; line-height: 1.5; }

.summary-action,
.confirm-rule-btn {
  flex-shrink: 0;
  border: 1px solid #8093bd; border-radius: 7px;
  background: #fff; color: #3e5688;
  padding: 6px 11px; font-size: 11px; font-weight: 700; cursor: pointer;
}
.summary-action:disabled, .confirm-rule-btn:disabled { cursor: not-allowed; opacity: .5; }
.summary-action.secondary { border-color: #d5dde9; color: #64748b; }
.confirm-rule-btn { background: #405987; border-color: #405987; color: #fff; }

/* ===== One-click confirm ===== */
.quick-confirm-btn {
  display: inline-flex; align-items: center; gap: 5px;
  padding: 5px 12px;
  border: 1px solid #28a666; border-radius: 7px;
  background: #f0fbf6; color: #1a7a4a;
  font-size: 11px; font-weight: 700; cursor: pointer;
  transition: all 0.16s ease;
  flex-shrink: 0;
}
.quick-confirm-btn:hover:not(:disabled) {
  background: #1a7a4a; color: #ffffff; border-color: #1a7a4a;
  box-shadow: 0 2px 8px rgba(26, 122, 74, 0.22);
}
.quick-confirm-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.candidate-summary-copy { display: flex; min-width: 0; flex-direction: column; gap: 2px; }
.candidate-summary-copy strong { overflow: hidden; color: #2d3a4f; font-size: 12px; font-weight: 650; line-height: 1.45; text-overflow: ellipsis; }
.candidate-summary-actions { display: flex; flex-shrink: 0; gap: 7px; align-items: center; }
.candidate-recognition {
  display: flex; align-items: center; flex-wrap: wrap; gap: 5px;
  margin-top: 5px; color: #718097; font-size: 10px; line-height: 1.45;
}
.candidate-recognition-label { color: #52647e; font-weight: 750; }
.candidate-type-chip {
  display: inline-flex; align-items: center; min-height: 18px; padding: 0 6px;
  border: 1px solid #cbd8ed; border-radius: 4px; background: #f1f5fc;
  color: #42618d; font-size: 10px; font-weight: 700;
}
.candidate-type-relation { border-color: #bddbd0; background: #eff9f4; color: #2c7656; }
.candidate-recognition-divider { color: #a0acbc; }

/* ===== Candidate editor ===== */
.candidate-editor { display: grid; gap: 11px; margin-top: 11px; }
.candidate-footer { margin-top: 4px; }
.editor-note { color: #78869a; font-size: 10px; }
.confirmation-audit { margin-top: 7px; color: #5f806f; font-size: 10px; text-align: right; }

/* ===== Tag-based process editor ===== */
.action-editor-tag { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }

.action-tag-column {
  position: relative;
  display: flex; flex-direction: column; gap: 7px;
  padding: 9px; border: 1px solid #e0e5ed; border-radius: 8px; background: #fff;
}
.action-title { font-size: 10px; font-weight: 750; }
.action-title-include      { color: #28704d; }
.action-title-exclude      { color: #a34b35; }
.relation-source-title     { color: #2c4da5; }
.relation-target-title     { color: #5a3ead; }

.tag-list {
  display: flex; flex-wrap: wrap; gap: 5px; align-items: center; min-height: 26px;
}
.process-tag {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 8px 3px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 600; line-height: 1;
}
.process-tag-include { background: #e8f5ef; color: #1a6b42; border: 1px solid #b3dfc9; }
.process-tag-exclude { background: #fef0ee; color: #8f3a2e; border: 1px solid #f5bdb5; }
.process-tag-source  { background: #edf2ff; color: #2c4da5; border: 1px solid #c5d3f5; }
.process-tag-target  { background: #f5f0ff; color: #5a3ead; border: 1px solid #d4c5f5; }

.tag-remove {
  background: none; border: none; cursor: pointer;
  color: inherit; opacity: 0.5; font-size: 13px; line-height: 1;
  padding: 0 0 0 2px; display: inline-flex; align-items: center;
  transition: opacity 0.12s;
}
.tag-remove:hover { opacity: 1; }

.tag-add-btn {
  display: inline-flex; align-items: center; gap: 4px;
  padding: 3px 9px; border: 1px dashed #b0bfd0; border-radius: 999px;
  background: transparent; color: #64748b; font-size: 11px; font-weight: 600;
  cursor: pointer; transition: all 0.15s ease;
}
.tag-add-btn:hover { border-color: #6366f1; color: #6366f1; background: #f0f0ff; }

/* ===== Process picker dropdown ===== */
.process-picker-dropdown {
  position: absolute; top: calc(100% + 4px); left: 0; z-index: 100;
  width: max(220px, 100%);
  background: #ffffff; border: 1px solid #d0d9e8; border-radius: 10px;
  box-shadow: 0 8px 24px rgba(15, 23, 42, 0.13), 0 2px 6px rgba(15, 23, 42, 0.06);
  overflow: hidden;
}
.picker-search {
  width: 100%; padding: 9px 12px;
  border: none; border-bottom: 1px solid #e8ecf2;
  font-size: 12px; color: #1e293b; outline: none; background: #f8fafc;
  font-family: inherit;
}
.picker-search::placeholder { color: #94a3b8; }
.picker-options { max-height: 175px; overflow-y: auto; padding: 4px; }
.picker-option {
  display: flex; align-items: center; justify-content: space-between;
  width: 100%; padding: 7px 10px; border: none; border-radius: 6px;
  background: transparent; color: #334155; font-size: 12px;
  text-align: left; cursor: pointer; transition: background 0.1s ease;
}
.picker-option:hover { background: #f1f5f9; }
.picker-option-selected { background: #eef2ff; color: #3730a3; font-weight: 600; }
.picker-option-selected:hover { background: #e0e7ff; }
.picker-check { color: #4f46e5; flex-shrink: 0; }
.picker-empty { padding: 10px 12px; color: #94a3b8; font-size: 12px; text-align: center; }

/* ===== Picker pop transition ===== */
.picker-pop-enter-active { transition: opacity 0.15s ease, transform 0.15s ease; }
.picker-pop-leave-active { transition: opacity 0.1s ease, transform 0.1s ease; }
.picker-pop-enter-from { opacity: 0; transform: translateY(-5px) scale(0.97); }
.picker-pop-leave-to   { opacity: 0; transform: translateY(-3px) scale(0.98); }

/* ===== Relation editor ===== */
.relation-editor { display: grid; gap: 11px; }
.relation-control-row {
  display: flex; align-items: center; gap: 12px;
  font-size: 12px; color: #4a5568;
}
.relation-select {
  flex: 1; min-width: 0; height: 32px; padding: 0 8px;
  border: 1px solid #d9e0e9; border-radius: 7px;
  background: #fff; color: #253247; font-size: 12px; outline: none;
}
.relation-select:focus { border-color: #5269a8; box-shadow: 0 0 0 3px rgba(82, 105, 168, .1); }

/* ===== Responsive ===== */
@media (max-width: 1080px) {
  .preview-card-actions { justify-content: flex-start; margin-top: 12px; }
  .preview-condition { font-size: 16px; }
  .action-editor-tag { grid-template-columns: 1fr; }
  .candidate-summary-row, .rule-summary-strip { align-items: flex-start; flex-direction: column; }
}
</style>
