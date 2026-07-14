import { computed, ref, watch, type ComputedRef } from 'vue'
import type {
  QuestionTreeAnswer,
  QuestionTreeOption,
  QuestionTreeQuestion,
} from '@/composables/useQuestionTreeMaterialRows'

export function isEditableOtherOption(option: QuestionTreeOption) {
  const value = String(option.value || '').trim()
  if (value === 'coverage_reason::other') return false
  return (
    value === 'other'
    || value.endsWith('::other_manual')
    || value.endsWith('::other')
    || value.includes('other_manual')
  )
}

function otherOptionPlaceholder(question: QuestionTreeQuestion | null, option: QuestionTreeOption) {
  const label = String(option.label || '').trim()
  const questionId = question?.id || ''
  const questionPrompt = String(question?.prompt || '')
  const questionTitle = String(question?.title || '')

  if (
    questionId === 'merge_name_root' ||
    questionPrompt.includes('工序') ||
    questionPrompt.includes('名称') ||
    questionTitle.includes('工序') ||
    questionTitle.includes('名称') ||
    label.includes('工序') ||
    label.includes('名称')
  ) {
    return '请输入具体名称，回车或点击空白确认'
  }

  if (label.includes('特征') || questionPrompt.includes('特征') || questionTitle.includes('特征')) {
    return '请输入特征描述，回车或点击空白确认'
  }
  if (label.includes('要求') || questionPrompt.includes('要求') || questionTitle.includes('要求')) {
    return '请输入具体要求，回车或点击空白确认'
  }
  if (label.includes('原因') || questionPrompt.includes('原因') || questionTitle.includes('原因')) {
    return '请输入具体原因，回车或点击空白确认'
  }
  if (label.includes('尺寸') || questionPrompt.includes('尺寸') || questionTitle.includes('尺寸')) {
    return '请输入具体尺寸，回车或点击空白确认'
  }
  if (
    label.includes('来料') ||
    label.includes('毛坯') ||
    questionPrompt.includes('来料') ||
    questionPrompt.includes('毛坯') ||
    questionTitle.includes('来料') ||
    questionTitle.includes('毛坯')
  ) {
    return '请输入具体来料/毛坯状态，回车或点击空白确认'
  }

  const cleaned = label.replace(/其他|其它|（需补充说明）|\(需补充说明\)|（请补充）|\(请补充\)/g, '').trim()
  if (cleaned) return `请输入具体${cleaned}，回车或点击空白确认`
  return '请输入具体内容，回车或点击空白确认'
}

export function useEditableOtherOption(args: {
  currentQuestion: ComputedRef<QuestionTreeQuestion | null>
  currentAnswer: ComputedRef<QuestionTreeAnswer | null>
  onSubmit: (option: QuestionTreeOption) => void
}) {
  const editingQuestionId = ref('')
  const draft = ref('')
  const inputRef = ref<HTMLInputElement | null>(null)
  let submitting = false

  const showInput = computed(() =>
    args.currentQuestion.value
    && editingQuestionId.value === args.currentQuestion.value.id,
  )

  function getPlaceholderForOption(option: QuestionTreeOption) {
    return otherOptionPlaceholder(args.currentQuestion.value, option)
  }

  function reset() {
    editingQuestionId.value = ''
    draft.value = ''
  }

  function startEdit(option: QuestionTreeOption) {
    const question = args.currentQuestion.value
    if (!question || !isEditableOtherOption(option)) return
    editingQuestionId.value = question.id
    if (args.currentAnswer.value?.value !== option.value) {
      draft.value = ''
    }
  }

  function updateDraft(value: string) {
    draft.value = value
  }

  function submit() {
    if (!showInput.value || submitting) return
    const label = draft.value.trim()
    if (!label) {
      cancel()
      return
    }
    submitting = true
    const editableOption = args.currentQuestion.value?.options.find(isEditableOtherOption)
    args.onSubmit({
      value: editableOption ? editableOption.value : 'other',
      label,
    })
    editingQuestionId.value = ''
    setTimeout(() => {
      submitting = false
    }, 100)
  }

  function cancel() {
    editingQuestionId.value = ''
    const answeredOtherOption = args.currentQuestion.value?.options.find(isEditableOtherOption)
    draft.value = (answeredOtherOption && args.currentAnswer.value?.value === answeredOtherOption.value)
      ? String(args.currentAnswer.value.label || '').trim()
      : ''
  }

  function handleBlur() {
    if (!showInput.value || submitting) return
    if (draft.value.trim()) {
      submit()
    } else {
      cancel()
    }
  }

  watch(
    () => args.currentQuestion.value,
    (question) => {
      if (!question) {
        reset()
        return
      }
      const answeredOtherOption = question.options.find(isEditableOtherOption)
      if (answeredOtherOption && args.currentAnswer.value?.value === answeredOtherOption.value) {
        editingQuestionId.value = question.id
        draft.value = String(args.currentAnswer.value.label || '').trim()
      } else if (editingQuestionId.value === question.id) {
        reset()
      }
    },
    { immediate: true },
  )

  watch(showInput, (show) => {
    if (show) {
      setTimeout(() => {
        inputRef.value?.focus()
      }, 50)
    }
  })

  return {
    inputRef,
    draft,
    showInput,
    isEditableOtherOption,
    getPlaceholderForOption,
    startEdit,
    updateDraft,
    submit,
    cancel,
    handleBlur,
    reset,
  }
}
