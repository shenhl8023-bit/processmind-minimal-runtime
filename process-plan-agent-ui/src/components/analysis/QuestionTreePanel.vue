<template>
  <article class="detail-card detail-card-wide tree-panel-enhanced">
    <div class="detail-card-title">
      <span class="title-text">工序判定</span>
      <div v-if="showResultActions" class="tree-result-actions">
        <button v-if="actionableTrailCount" type="button" class="tree-action-btn-secondary" @click="emit('reanswer-last')">
          重答最后一题
        </button>
        <button type="button" class="tree-action-btn-secondary tree-action-btn-accent" @click="emit('reset')">
          重新判断这道工序
        </button>
      </div>
    </div>
    <p v-if="readOnly && !hideReadOnlyNotice" class="tree-readonly-notice" role="status">{{ readOnlyReason || '已进入规则定稿，请到规则定稿页调整。需要从头分析时，请使用顶部“重新回答全部”。' }}</p>

    <div v-if="!visible && !hasAnsweredContent && !hasSavedTrail" class="tree-empty">
      <div class="empty-icon">📂</div>
      <div class="empty-text">{{ emptyReason }}</div>
    </div>

    <template v-else>


      <div v-if="displayTrail.length" class="tree-trail">
        <div class="tree-trail-title">已选条件</div>
        <div class="tree-trail-list">
          <div v-for="(item, index) in displayTrail" :key="`${item.nodeId}-${item.value}`" class="tree-trail-node">
            <span class="tree-trail-chip">
              <span class="tree-trail-chip-dot" aria-hidden="true"></span>
              <span class="tree-trail-label">{{ item.label }}</span>
            </span>
            <span v-if="index < displayTrail.length - 1" class="tree-trail-arrow">
              <svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 20 20" fill="currentColor">
                <path fill-rule="evenodd" d="M7.21 14.77a.75.75 0 01.02-1.06L11.168 10 7.23 6.29a.75.75 0 111.04-1.08l4.5 4.25a.75.75 0 010 1.08l-4.5 4.25a.75.75 0 01-1.06-.02z" clip-rule="evenodd" />
              </svg>
            </span>
          </div>
        </div>
      </div>

      <div v-if="currentQuestion" class="tree-question-card">
        <div class="tree-question-head">
          <div class="tree-question-prompt">{{ currentQuestion.prompt }}</div>
          <span class="tree-prompt-source">{{ promptSourceLabel }}</span>
        </div>

        <div v-if="currentQuestion.customEditor">
          <button type="button" class="btn btn-primary" :disabled="readOnly" @click="emit('edit-custom')">自行设置出现规则</button>
        </div>
        <div v-else-if="currentQuestion.numeric" class="tree-numeric-editor">
          <label class="tree-numeric-field">
            <span>自定义阈值（{{ currentQuestion.numeric.unit }}）</span>
            <input type="number" :value="numericDraft" :min="currentQuestion.numeric.min" :max="currentQuestion.numeric.max" :step="currentQuestion.numeric.integer ? 1 : 'any'" :disabled="readOnly" :aria-invalid="Boolean(numericDraft && !numericValid)" @input="numericDraft = ($event.target as HTMLInputElement).value" @keydown.enter.prevent="submitNumeric" />
          </label>
          <div v-if="currentQuestion.options.length" class="tree-numeric-presets" role="group" aria-label="阈值快捷选项">
            <button v-for="option in currentQuestion.options" :key="option.value" type="button" :aria-pressed="numericDraft !== '' && Number(numericDraft) === Number(option.value)" :disabled="readOnly" @click="numericDraft = option.value">{{ option.label }}</button>
          </div>
          <button type="button" class="tree-numeric-confirm" data-testid="confirm-numeric-threshold" :disabled="readOnly || !numericValid" @click="submitNumeric">确认阈值</button>
          <p v-if="numericDraft && !numericValid" role="alert">请输入{{ currentQuestion.numeric.integer ? '1～18的整数' : '有效数值' }}{{ currentQuestion.numeric.exclusiveMin ? '（必须大于0）' : '' }}。</p>
        </div>
        <div v-else-if="isMaterialTableQuestion" class="tree-table-wrap">
          <table class="tree-table">
            <thead>
              <tr>
                <th class="tree-table-check-col">选择</th>
                <th v-if="materialScopeMode !== 'category'">材料牌号</th>
                <th v-if="materialScopeMode !== 'grade'">材料大类</th>
                <th class="tree-table-count-col">来源样本</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!materialRows.length" class="tree-table-empty-row">
                <td :colspan="materialTableColumnCount">
                  当前样本暂未识别到明确{{ materialScopeLabel }}，请点击“新增一行材料”手动补充。
                </td>
              </tr>
              <tr v-for="row in materialRows" :key="row.id" :class="{ 'is-selected': row.selected }">
                <td class="tree-table-check-col">
                  <input
                    :checked="row.selected"
                    :disabled="readOnly"
                    type="checkbox"
                    class="tree-table-checkbox"
                    @change="toggleMaterialRow(row.id)"
                  />
                </td>
                <td v-if="materialScopeMode !== 'category'">
                  <input
                    :value="row.grade"
                    :disabled="readOnly"
                    type="text"
                    class="tree-table-input"
                    placeholder="手动填写材料牌号"
                    @input="updateMaterialRow(row.id, 'grade', ($event.target as HTMLInputElement).value)"
                  />
                </td>
                <td v-if="materialScopeMode !== 'grade'">
                  <select
                    :value="row.category"
                    :disabled="readOnly"
                    class="tree-table-select"
                    @change="updateMaterialRow(row.id, 'category', ($event.target as HTMLSelectElement).value)"
                  >
                    <option value="">请选择材料大类</option>
                    <option
                      v-for="category in MATERIAL_CATEGORY_OPTIONS"
                      :key="`${row.id}-${category}`"
                      :value="category"
                    >
                      {{ category }}
                    </option>
                  </select>
                </td>
                <td class="tree-table-count-cell">
                  <span v-if="row.countLabel" class="tree-count-pill">{{ row.countLabel }}</span>
                  <span v-else class="tree-count-empty">-</span>
                </td>
              </tr>
            </tbody>
          </table>
          <button type="button" class="tree-table-add-btn" :disabled="readOnly" @click="appendMaterialRow">
            + 新增一行材料
          </button>
        </div>

        <div v-else class="tree-option-list">
          <div
            v-for="option in currentQuestion.options"
            :key="`${currentQuestion.id}-${option.value}`"
            :role="currentQuestion.multiple ? 'checkbox' : 'radio'"
            :aria-checked="isSelected(option)"
            :tabindex="readOnly ? -1 : 0"
            :aria-disabled="Boolean(readOnly)"
            class="tree-option-btn"
            :class="{
              active: isSelected(option),
              recommended: isRecommendedOption(option),
              'tree-option-btn-editing': isEditableOtherOption(option) && showMergeNameOtherInput,
            }"
            @click="handleOptionClick(option)"
            @keydown.enter.prevent="handleOptionClick(option)"
            @keydown.space.prevent="handleOptionClick(option)"
          >
            <template v-if="isEditableOtherOption(option) && showMergeNameOtherInput">
              <div class="tree-option-editing-inline" @click.stop>
                <span class="tree-option-radio"></span>
                <input
                  :ref="setOtherInputRef"
                  :value="mergeNameOtherDraft"
                  :disabled="readOnly"
                  type="text"
                  class="tree-option-inline-input-flat"
                  :placeholder="getPlaceholderForOption(option)"
                  @input="updateMergeNameOtherDraft(($event.target as HTMLInputElement).value)"
                  @keydown="handleMergeNameOtherKeydown"
                />
              </div>
            </template>
            <template v-else>
              <span class="tree-option-radio"></span>
              <span class="tree-option-label">{{ option.label }}</span>
              <span v-if="isRecommendedOption(option)" class="tree-option-badge">系统推荐</span>
            </template>
          </div>
        </div>

        <!-- 推荐面板 -->
        <div v-if="recommendedHintText" class="tree-recommend-row">
          <div class="tree-recommend-icon">
            <svg xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" stroke-width="2" stroke="currentColor" class="sparkles-svg">
              <path stroke-linecap="round" stroke-linejoin="round" d="M9.813 15.904L9 21l-.813-5.096L3 15l5.096-.813L9 9l.813 5.187L15 15l-5.187.904zM18 10.5l-.5 2.5-.5-2.5-2.5-.5 2.5-.5.5-2.5.5 2.5 2.5.5-2.5.5zM15.5 3.5l-.25 1.25-.25-1.25-1.25-.25 1.25-.25.25-1.25.25 1.25 1.25.25-1.25.25" />
            </svg>
          </div>
          <div class="tree-recommend-copy">
            <div class="tree-recommend-text">{{ recommendedHintText }}</div>
            <div v-if="recommendedReasonText" class="tree-recommend-reason">{{ recommendedReasonText }}</div>
          </div>
        </div>

        <!-- 多选确认操作栏 -->
        <div v-if="currentQuestion.multiple" class="tree-multi-actions">
          <div class="tree-multi-hint">
            <template v-if="isMaterialTableQuestion">
              <template v-if="materialScopeMode === 'grade'">
                系统已先列出当前样本里识别到的材料牌号。勾选对应当前工序的牌号，必要时可手动补充。
              </template>
              <template v-else-if="materialScopeMode === 'category'">
                系统已先列出当前样本里识别到的材料大类。勾选对应当前工序的材料大类，必要时可手动补充。
              </template>
              <template v-else>
                系统已先列出当前样本里识别到的材料。勾选对应当前工序的行，必要时可手动补充材料牌号或材料大类。
              </template>
            </template>
            <template v-else>
              可多选，先勾出当前样本里通常会出现该工序的候选项，再确认。
            </template>
            <span v-if="sourceHintText" class="tree-source-hint">{{ sourceHintText }}</span>
          </div>
          <button
            type="button"
            class="tree-action-btn tree-action-btn-primary"
            :disabled="readOnly || selectedCount < minSelections"
            @click="submitMultiSelection"
          >
            {{ currentQuestion.confirmLabel || '确认选择' }}
          </button>
        </div>


        <!-- 动作按钮区 -->
        <div
          v-if="!readOnly && (actionableTrailCount || noteDraftText || (currentQuestion.multiple && selectedCount))"
          class="tree-action-row"
        >
          <button
            v-if="currentQuestion.multiple && selectedCount"
            class="tree-action-btn-secondary"
            :disabled="readOnly || !selectedCount"
            @click="clearCurrentSelection"
          >
            清空本题选择
          </button>
          <button v-if="actionableTrailCount" class="tree-action-btn-secondary" @click="$emit('reanswer-last')">
            重答最后一题
          </button>
          <button v-if="actionableTrailCount || noteDraftText" class="tree-action-btn-secondary" @click="$emit('reset')">
            重新判断这道工序
          </button>
        </div>
      </div>

      <div v-else-if="hasCurrentResult" class="tree-result-card">
        <div v-if="resultSummaryText" class="tree-result-container" role="group" aria-label="判定结论">
          <span class="tree-result-badge" aria-hidden="true">
            <svg viewBox="0 0 16 16" fill="none" width="12" height="12">
              <path d="m3.5 8 3 3 6-6" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" />
            </svg>
          </span>
          <div class="tree-result-text">{{ resultSummaryText }}</div>
        </div>
        <div v-if="noteDraft" class="tree-result-note">补充说明：{{ noteDraft }}</div>
      </div>
    </template>
  </article>
</template>

<script setup lang="ts">
import { computed, ref, watch, type ComponentPublicInstance } from 'vue'
import { useEditableOtherOption } from '@/composables/useEditableOtherOption'
import {
  MATERIAL_CATEGORY_OPTIONS,
  useQuestionTreeMaterialRows,
  type QuestionTreeOption,
} from '@/composables/useQuestionTreeMaterialRows'

type TreeOption = QuestionTreeOption

const props = defineProps<{
  hideReadOnlyNotice?: boolean
  readOnly?: boolean
  readOnlyReason?: string
  visible: boolean
  emptyReason: string
  currentQuestion: {
    id: string
    title: string
    prompt: string
    options: TreeOption[]
    multiple?: boolean
    minSelections?: number
    confirmLabel?: string
    sourceHint?: string
    recommendedValues?: string[]
    numeric?: { min: number; max?: number; exclusiveMin?: boolean; integer?: boolean; unit: string }
    customEditor?: boolean
  } | null
  trail: Array<{ nodeId: string; value: string; label: string }>
  resultSummary: string
  noteDraft: string
  savedTrail?: Array<{ nodeId: string; value: string; label: string }>
  sourceHint?: string
}>()

const emit = defineEmits<{
  'choose-option': [option: TreeOption]
  'choose-options': [options: TreeOption[]]
  'update-note': [value: string]
  'reanswer-last': []
  reset: []
  'edit-custom': []
}>()

const numericDraft = ref('')
const numericValid = computed(() => {
  const config = props.currentQuestion?.numeric
  const n = Number(numericDraft.value)
  return Boolean(config && numericDraft.value.trim() && Number.isFinite(n) && (config.exclusiveMin ? n > config.min : n >= config.min) && (config.max === undefined || n <= config.max) && (!config.integer || Number.isInteger(n)))
})
watch(() => props.currentQuestion?.id, () => { numericDraft.value = '' }, { immediate: true })
function submitNumeric() {
  if (props.readOnly || !numericValid.value) return
  const unit = props.currentQuestion!.numeric!.unit
  const n = String(Number(numericDraft.value))
  emit('choose-option', { value: n, label: `${unit === 'IT' ? 'IT' : ''}${n}${unit === 'IT' ? '' : ` ${unit}`}` })
}

const multiSelectionMap = ref<Record<string, TreeOption[]>>({})

const multiSelectedOptions = computed(() => {
  const questionId = props.currentQuestion?.id || ''
  return questionId ? (multiSelectionMap.value[questionId] || []) : []
})

const currentAnswer = computed(() => {
  const questionId = props.currentQuestion?.id || ''
  if (!questionId) return null
  return props.trail.find(item => item.nodeId === questionId) || null
})

const {
  inputRef: otherInputRef,
  draft: mergeNameOtherDraft,
  showInput: showMergeNameOtherInput,
  isEditableOtherOption,
  getPlaceholderForOption,
  startEdit: startMergeNameOtherEdit,
  updateDraft: updateMergeNameOtherDraft,
  submit: submitMergeNameOther,
  cancel: cancelMergeNameOther,
  reset: resetMergeNameOther,
} = useEditableOtherOption({
  currentQuestion: computed(() => props.currentQuestion),
  currentAnswer,
  onSubmit: option => { if (!props.readOnly) emit('choose-option', option) },
})

function setOtherInputRef(el: Element | ComponentPublicInstance | null) {
  otherInputRef.value = el instanceof HTMLInputElement ? el : null
}

function handleMergeNameOtherKeydown(event: KeyboardEvent) {
  if (props.readOnly) return
  event.stopPropagation()
  if (event.key === 'Escape') {
    event.preventDefault()
    cancelMergeNameOther()
    return
  }
  // Enter confirms Chinese IME candidates too; only submit after composition ends.
  if (event.key !== 'Enter' || event.isComposing || event.keyCode === 229) return
  event.preventDefault()
  submitMergeNameOther()
}

const {
  materialScopeMode,
  materialScopeLabel,
  materialTableColumnCount,
  materialRows,
  isMaterialTableQuestion,
  selectedMaterialCount,
  selectedMaterialOptions,
  clearMaterialSelection,
  toggleMaterialRow,
  updateMaterialRow,
  appendMaterialRow,
} = useQuestionTreeMaterialRows({
  currentQuestion: computed(() => props.currentQuestion),
  currentAnswer,
  isFallbackOption,
})

const sourceHintText = computed(() => props.currentQuestion?.sourceHint || props.sourceHint || '')
const minSelections = computed(() => props.currentQuestion?.minSelections || 1)
const promptSourceLabel = '专业模板问法'
const resultSummaryText = computed(() => String(props.resultSummary || '').trim())
const noteDraftText = computed(() => String(props.noteDraft || '').trim())
const hasCurrentResult = computed(() => Boolean(resultSummaryText.value || noteDraftText.value))
const hasAnsweredContent = computed(() => props.trail.length > 0 || hasCurrentResult.value)
const savedTrailSafe = computed(() => (props.savedTrail || []).filter(item => String(item?.label || '').trim()))
const hasSavedTrail = computed(() => savedTrailSafe.value.length > 0)
const displayTrail = computed(() => {
  if (props.trail.length) return props.trail
  if (props.currentQuestion) return []
  return savedTrailSafe.value
})
const actionableTrailCount = computed(() => displayTrail.value.length)
const showResultActions = computed(() => !props.readOnly && !props.currentQuestion && hasCurrentResult.value)
const selectedCount = computed(() =>
  isMaterialTableQuestion.value
    ? selectedMaterialCount.value
    : multiSelectedOptions.value.length,
)

function isFallbackOption(option: TreeOption) {
  const value = String(option.value || '').trim().toLowerCase()
  const label = String(option.label || '').trim()
  return (
    value === 'other'
    || value.includes('other')
    || value.includes('uncertain')
    || value.includes('manual')
    || label.includes('其他')
    || label.includes('暂时无法判断')
    || label.includes('需要人工补充')
    || label.includes('未自动识别')
  )
}

const recommendedOptions = computed<TreeOption[]>(() => {
  const question = props.currentQuestion
  if (!question) return []
  if (question.id.startsWith('guided_')) return question.options.filter(option => (question.recommendedValues || []).includes(option.value))
  const preferred = question.options.filter(option => !isFallbackOption(option))
  const ordered = preferred.length ? preferred : question.options
  if (isMaterialTableQuestion.value) {
    return preferred.length ? preferred : []
  }
  if (!question.multiple) return ordered.slice(0, 1)
  return ordered.slice(0, minSelections.value)
})

const recommendedHintText = computed(() => {
  if (!props.currentQuestion || !recommendedOptions.value.length) return ''
  const labels = recommendedOptions.value.map(option => option.label)
  if (!props.currentQuestion.multiple) {
    return `系统优先推荐：${labels[0]}`
  }
  return `系统已按推荐预选：${labels.join('、')}，你也可以继续调整。`
})

const recommendedReasonText = computed(() => {
  const question = props.currentQuestion
  if (!question || !recommendedOptions.value.length) return ''
  const questionId = String(question.id || '')
  if (questionId.startsWith('guided_')) return '依据当前项目配置推荐，采用后与手动回答生成同一份规则；你可以自行调整。'
  if (questionId === 'merge_name_root') {
    return '这道题只围绕组合名本身拆分出的统一名称候选作答；系统优先推荐当前候选池里排在前面的标准工序名。'
  }
  if (questionId === 'rule_reason_root') {
    return '系统优先推荐当前工序最常见、也最贴近当前工序内容的一类触发因素，方便你先沿主方向继续确认。'
  }
  if (questionId.includes('material')) {
    return '系统优先按当前样本里已识别出的材料信息排序推荐，前面的候选通常更直接对应当前工序。'
  }
  if (questionId.includes('structure') || questionId.includes('feature')) {
    return '系统优先根据当前工序内容里出现频率更高、语义更贴近的结构或加工对象进行推荐。'
  }
  if (questionId.includes('size')) {
    return '系统优先推荐当前工序里最常见、最容易直接触发该工序保留的尺寸边界类型。'
  }
  if (questionId.includes('blank')) {
    return '系统优先推荐当前样本中更直接决定该工序是否出现的毛坯或来料状态。'
  }
  if (questionId.includes('requirement') || questionId.includes('precision')) {
    return '系统优先推荐当前工序最常见的精度、配合或表面质量方向，方便你先确认主导要求。'
  }
  if (sourceHintText.value) {
    return sourceHintText.value
  }
  return '系统会优先推荐当前候选池里更贴近当前工序内容、并且排序更靠前的选项。'
})

watch(
  () => props.currentQuestion,
  (question) => {
    if (!question) return

    if (question.multiple && !question.id.includes('material_scope')) {
      const answer = currentAnswer.value
      const selectedValues = new Set(String(answer?.value || '').split('|').filter(Boolean))
      const existingSelection = multiSelectionMap.value[question.id]
      if (!answer && existingSelection?.length) return
      const initialOptions = answer
        ? question.options.filter(option => selectedValues.has(option.value))
        : recommendedOptions.value
      multiSelectionMap.value = {
        ...multiSelectionMap.value,
        [question.id]: initialOptions,
      }
    }

  },
  { immediate: true },
)

function isSelected(option: TreeOption) {
  if (!props.currentQuestion?.multiple) {
    if (isEditableOtherOption(option) && showMergeNameOtherInput.value) return true
    return currentAnswer.value?.value === option.value
  }
  if (isMaterialTableQuestion.value) return false
  return multiSelectedOptions.value.some(item => item.value === option.value)
}

function isRecommendedOption(option: TreeOption) {
  return recommendedOptions.value.some(item => item.value === option.value)
}

function handleOptionClick(option: TreeOption) {
  if (props.readOnly) return
  const question = props.currentQuestion
  if (!question) return
  if (!question.multiple) {
    if (isEditableOtherOption(option)) {
      startMergeNameOtherEdit(option)
      return
    }
    resetMergeNameOther()
    emit('choose-option', option)
    return
  }
  const questionId = question.id
  const current = multiSelectionMap.value[questionId] || []
  const exists = current.some(item => item.value === option.value)
  multiSelectionMap.value = {
    ...multiSelectionMap.value,
    [questionId]: exists
      ? current.filter(item => item.value !== option.value)
      : [...current, option],
  }
}

function clearCurrentSelection() {
  if (props.readOnly) return
  const questionId = props.currentQuestion?.id || ''
  if (!questionId) return
  if (isMaterialTableQuestion.value) {
    clearMaterialSelection()
    return
  }
  multiSelectionMap.value = {
    ...multiSelectionMap.value,
    [questionId]: [],
  }
}

function submitMultiSelection() {
  if (props.readOnly) return
  if (!props.currentQuestion?.multiple || selectedCount.value < minSelections.value) return
  if (isMaterialTableQuestion.value) {
    emit('choose-options', selectedMaterialOptions())
    return
  }
  emit('choose-options', multiSelectedOptions.value)
}

</script>

<style scoped>
.tree-readonly-notice {
  margin: 8px 0;
  color: #475569;
  font-size: 13px;
}

.tree-option-btn[aria-disabled="true"] {
  opacity: 0.6;
  cursor: not-allowed;
}

/* Container styling adjustments */
.tree-panel-enhanced {
  background: var(--pm-surface);
  border-radius: var(--pm-radius-card);
  border: 1px solid var(--pm-border);
  box-shadow: none;
  padding: 10px 12px;
}

.detail-card-title {
  font-size: 13px;
  font-weight: 600;
  color: var(--pm-text);
  line-height: 20px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: 6px 12px;
}

.tree-result-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  margin-left: auto;
}

/* Empty reason text */
.tree-empty {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 32px;
  text-align: center;
}

.empty-icon {
  font-size: 24px;
  margin-bottom: 8px;
  opacity: 0.6;
}

.empty-text {
  font-size: 12.5px;
  line-height: 1.6;
  color: #94a3b8;
}

/* Trail sequence pipeline style */
.tree-trail {
  display: flex;
  align-items: flex-start;
  gap: 6px 8px;
}

.tree-trail-title {
  flex: 0 0 auto;
  font-size: 12px;
  font-weight: 500;
  color: var(--pm-text-secondary);
  line-height: 24px;
}

.tree-trail-list {
  display: flex;
  flex: 1;
  min-width: 0;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 6px;
}

.tree-trail-node {
  display: inline-flex;
  min-width: 0;
  max-width: 100%;
  align-items: center;
  gap: 4px;
}

.tree-trail-chip {
  display: inline-flex;
  min-width: 0;
  min-height: 24px;
  align-items: center;
  gap: 5px;
  border-radius: 4px;
  padding: 2px 8px;
  background: var(--pm-surface-subtle);
  border: 1px solid var(--pm-border);
  color: var(--pm-text-secondary);
  font-size: 12px;
  line-height: 18px;
}

.tree-trail-label {
  min-width: 0;
  overflow-wrap: anywhere;
}

.tree-trail-chip-dot {
  width: 5px;
  height: 5px;
  flex-shrink: 0;
  background: var(--pm-primary);
  border-radius: 50%;
}

.tree-trail-arrow {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 12px;
  height: 12px;
  flex-shrink: 0;
  color: var(--pm-text-muted);
}

.tree-trail-arrow svg {
  width: 100%;
  height: 100%;
}

/* Saved and active question cards */
.tree-question-card,
.tree-result-card {
  background: transparent;
  border: none;
  padding: 0;
  box-shadow: none;
  position: relative;
  overflow: visible;
  margin-top: 0;
}

.tree-trail + .tree-question-card,
.tree-trail + .tree-result-card {
  margin-top: 8px;
}

.tree-question-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
}

.tree-question-prompt {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  display: flex;
  align-items: flex-start;
  gap: 7px;
  line-height: 1.5;
  margin: 0;
}

.tree-question-prompt::before {
  content: 'Q';
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 16px;
  height: 16px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  border-radius: 3px;
  font-size: 10px;
  font-weight: 700;
  flex-shrink: 0;
  margin-top: 2px;
}

.tree-prompt-source {
  flex-shrink: 0;
  padding: 2px 6px;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  font-size: 10px;
  font-weight: 500;
  line-height: 1.2;
}

/* Option Grid Styling */
.tree-option-list {
  display: flex;
  flex-direction: column;
  gap: 5px;
}

/* Card Options */
.tree-option-btn {
  display: flex;
  align-items: center;
  justify-content: flex-start;
  padding: 7px 12px;
  border-radius: 5px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  cursor: pointer;
  width: 100%;
  position: relative;
  transition: all 0.15s ease;
}

.tree-option-btn:focus,
.tree-option-btn:focus-visible {
  outline: none;
  border-color: var(--pm-primary);
}

.tree-option-btn:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}

.tree-option-btn.recommended {
  border-color: #e2e8f0;
  background: #ffffff;
}

.tree-option-btn.recommended:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}

/* Selected active option card styles */
.tree-option-btn.active {
  border-color: var(--pm-primary);
  background: var(--pm-primary-soft);
  font-weight: 500;
}

.tree-option-btn-editing {
  padding: 7px 12px;
  background: #ffffff;
}

.tree-option-editing-inline {
  display: flex;
  align-items: center;
  width: 100%;
  gap: 8px;
}

.tree-option-inline-input-flat {
  flex: 1;
  min-width: 0;
  height: 28px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  padding: 0 8px;
  font-size: 13px;
  color: #0f172a;
  background: #ffffff;
  transition: all 0.15s ease-in-out;
}

.tree-option-inline-input-flat::placeholder {
  color: #94a3b8;
  font-size: 12px;
}

.tree-option-inline-input-flat:focus {
  outline: none;
  border-color: var(--pm-primary);
  box-shadow: var(--pm-focus-ring);
}

/* Radio Circles */
.tree-option-radio {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 13px;
  height: 13px;
  border-radius: 50%;
  border: 1.5px solid #cbd5e1;
  margin-right: 8px;
  background: #ffffff;
  transition: all 0.15s ease;
  flex-shrink: 0;
  position: relative;
}

.tree-option-btn:hover .tree-option-radio {
  border-color: #94a3b8;
}

.tree-option-btn.active .tree-option-radio {
  border-color: var(--pm-primary);
  background: var(--pm-primary);
}

.tree-option-btn.active .tree-option-radio::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #ffffff;
  transform: translate(-50%, -50%) scale(1);
}

.tree-option-radio::after {
  content: '';
  position: absolute;
  top: 50%;
  left: 50%;
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: #ffffff;
  transform: translate(-50%, -50%) scale(0);
  transition: transform 0.1s ease;
}

.tree-option-label {
  font-size: 13px;
  color: #475569;
  line-height: 1.4;
}

.tree-option-btn.active .tree-option-label {
  color: #0f172a;
}

/* System Recommended pill tag styling */
.tree-option-badge {
  margin-left: auto;
  flex-shrink: 0;
  font-size: 10px;
  font-weight: 500;
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
  border: 1px solid var(--pm-primary-border);
  border-radius: 4px;
  padding: 1px 6px;
}

/* AI Recommendation Card */
.tree-recommend-row {
  margin-top: 8px;
  padding: 7px 10px;
  border-radius: 5px;
  background: var(--pm-surface-subtle);
  border: 1px solid #e2e8f0;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
}

.tree-recommend-icon {
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 3px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  display: flex;
  align-items: center;
  justify-content: center;
}

.sparkles-svg {
  width: 12px;
  height: 12px;
}

.tree-recommend-copy {
  min-width: 0;
  flex: 1;
}

.tree-recommend-text {
  font-size: 11px;
  line-height: 1.4;
  font-weight: 500;
  color: #475569;
}

.tree-recommend-reason {
  font-size: 10.5px;
  line-height: 1.4;
  color: var(--pm-text-secondary);
  margin-top: 2px;
}

/* Material database table styling */
.tree-table-wrap {
  margin-top: 12px;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  background: #ffffff;
  overflow: hidden;
}

.tree-table {
  width: 100%;
  border-collapse: collapse;
}

.tree-table th,
.tree-table td {
  padding: 8px 10px;
  border-bottom: 1px solid #e2e8f0;
  text-align: left;
  vertical-align: middle;
}

.tree-table th {
  font-size: 11.5px;
  font-weight: 600;
  color: #475569;
  background: #f8fafc;
}

.tree-table tr {
  transition: background-color 0.1s ease;
}

.tree-table tr:hover {
  background: #f8fafc;
}

.tree-table tr.is-selected {
  background: var(--pm-primary-soft);
}

.tree-table tr.tree-table-empty-row:hover {
  background: #ffffff;
}

.tree-table-empty-row td {
  color: #94a3b8;
  font-size: 12px;
  text-align: center;
}

.tree-table tr:last-child td {
  border-bottom: none;
}

.tree-table-check-col {
  width: 40px;
  text-align: center;
}

.tree-table-count-col,
.tree-table-count-cell {
  width: 82px;
  text-align: center;
  white-space: nowrap;
}

.tree-count-pill {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 44px;
  padding: 2px 8px;
  border-radius: 999px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  font-size: 11px;
  font-weight: 700;
}

.tree-count-empty {
  color: #cbd5e1;
  font-size: 11px;
}

.tree-table-checkbox {
  width: 14px;
  height: 14px;
  accent-color: var(--pm-primary);
  cursor: pointer;
}

.tree-table-input,
.tree-table-select {
  width: 100%;
  border: 1px solid transparent;
  background: transparent;
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 12px;
  color: #1e293b;
  transition: all 0.15s ease;
}

.tree-table tr.is-selected .tree-table-input,
.tree-table tr.is-selected .tree-table-select {
  background: #ffffff;
  border-color: #cbd5e1;
}

.tree-table-input:hover,
.tree-table-select:hover {
  border-color: #cbd5e1;
}

.tree-table-input:focus,
.tree-table-select:focus {
  outline: none;
  border-color: var(--pm-primary);
  background: #ffffff;
}

.tree-table-add-btn {
  width: 100%;
  padding: 8px;
  background: #ffffff;
  border: none;
  border-top: 1px dashed #e2e8f0;
  color: var(--pm-primary);
  font-size: 11.5px;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.15s;
  text-align: center;
}

.tree-table-add-btn:hover {
  background: #f8fafc;
  color: var(--pm-primary);
}

/* Multi actions */
.tree-multi-actions {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  align-items: flex-end;
  gap: 8px;
}

.tree-multi-hint {
  font-size: 11px;
  line-height: 1.4;
  color: #64748b;
  background: #f8fafc;
  padding: 6px 10px;
  border-radius: 4px;
  border-left: 2px solid #cbd5e1;
  width: 100%;
}

.tree-source-hint {
  display: inline-block;
  font-weight: 600;
  margin-left: 4px;
  color: #0f172a;
}

/* Optional notes input section */
.tree-note-row {
  margin-top: 12px;
}

.tree-note-input-wrapper {
  position: relative;
  display: flex;
  align-items: center;
  width: 100%;
}

.tree-note-icon {
  position: absolute;
  left: 10px;
  font-size: 12px;
  opacity: 0.6;
  pointer-events: none;
}

.tree-note-input {
  width: 100%;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  padding: 8px 10px 8px 28px;
  border-radius: 4px;
  font-size: 12px;
  color: #0f172a;
  transition: border-color 0.15s ease;
}

.tree-note-input::placeholder {
  color: #94a3b8;
}

.tree-note-input:focus {
  outline: none;
  border-color: var(--pm-primary);
}

/* Current Judgment conclusions page styling */
.tree-result-container {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  background: var(--pm-primary-soft);
  border: 1px solid var(--pm-primary-border);
  border-radius: 6px;
  padding: 8px 10px;
}

.tree-result-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  background: var(--pm-primary);
  color: var(--pm-surface);
  font-size: 10px;
  font-weight: 600;
  flex-shrink: 0;
  margin-top: 2px;
}

.tree-result-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--pm-text);
  line-height: 1.55;
  min-width: 0;
  overflow-wrap: anywhere;
  margin: 0;
}

.tree-result-note {
  margin-top: 6px;
  font-size: 11.5px;
  line-height: 1.5;
  color: #475569;
  padding: 6px 10px;
  background: #f8fafc;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
}

/* Secondary history control action buttons */
.tree-action-row {
  margin-top: 10px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  flex-wrap: wrap;
}

.tree-action-btn-secondary {
  min-height: 28px;
  padding: 3px 8px;
  font-size: 12px;
  line-height: 18px;
  font-weight: 500;
  color: #64748b;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s ease;
}

.tree-action-btn-secondary:hover:not(:disabled) {
  background: #f8fafc;
  color: #1e293b;
  border-color: #cbd5e1;
}

.tree-action-btn-secondary:disabled {
  color: #94a3b8;
  border-color: #e2e8f0;
  background: #ffffff;
  cursor: not-allowed;
  opacity: 0.6;
}

.tree-action-btn-accent {
  border-color: #cbd5e1;
  background: #ffffff;
  color: var(--pm-primary);
}

.tree-action-btn-accent:hover:not(:disabled) {
  border-color: #cbd5e1;
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
}

.tree-action-btn-primary {
  padding: 5px 12px;
  font-size: 11.5px;
  font-weight: 500;
  background: var(--pm-primary);
  border: 1px solid transparent;
  color: #ffffff;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.15s;
}

.tree-action-btn-primary:hover:not(:disabled) {
  background: var(--pm-primary-hover);
}
</style>
