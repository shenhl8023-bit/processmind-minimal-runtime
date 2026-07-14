import { computed, ref, watch, type ComputedRef } from 'vue'

export type QuestionTreeOption = {
  value: string
  label: string
  countLabel?: string
  docCount?: number
  totalCount?: number
}

export type QuestionTreeAnswer = {
  nodeId: string
  value: string
  label: string
}

export type QuestionTreeQuestion = {
  id: string
  title: string
  prompt: string
  options: QuestionTreeOption[]
  multiple?: boolean
  minSelections?: number
  confirmLabel?: string
  sourceHint?: string
}

export type MaterialQuestionRow = {
  id: string
  value: string
  grade: string
  category: string
  countLabel?: string
  selected: boolean
}

const DEFAULT_MATERIAL_ROW_COUNT = 5

export const MATERIAL_CATEGORY_OPTIONS = [
  '碳钢',
  '合金钢',
  '不锈钢',
  '铝合金',
  '铜合金',
  '钛合金',
  '高温合金',
  '其他',
] as const

const MATERIAL_CATEGORY_RULES: Array<{
  category: (typeof MATERIAL_CATEGORY_OPTIONS)[number]
  test: (text: string) => boolean
}> = [
  {
    category: '不锈钢',
    test: (text) => (
      /不锈钢/.test(text)
      || /9Cr|1Cr|2Cr13|3Cr13|4Cr13|4Cr14|5Cr15|6Cr13|7Cr17|9Cr17|9Cr18/i.test(text)
      || (/(?:Cr).*(?:Ni|Mo|W)/i.test(text) && !/^GH/i.test(text))
    ),
  },
  {
    category: '铝合金',
    test: (text) => /铝|^1\d{3}$|^2\d{3}$|^3\d{3}$|^5\d{3}$|^6\d{3}$|^7\d{3}$/i.test(text),
  },
  {
    category: '铜合金',
    test: (text) => /铜|Cu|H62|H65|H68|QAl|QSn|QBe/i.test(text),
  },
  {
    category: '钛合金',
    test: (text) => /钛|Ti|^TA\d+|^TB\d+|^TC\d+/i.test(text),
  },
  {
    category: '高温合金',
    test: (text) => /高温合金|Inconel|Monel|Hastelloy|^GH/i.test(text),
  },
  {
    category: '碳钢',
    test: (text) => /^(10|15|20|25|35|45|50|55|60|65|70|75|80|T8|T10|T12)$/i.test(text),
  },
  {
    category: '合金钢',
    test: (text) => /钢$|Cr|Mo|Mn|Si|W|V|GCr15|40Cr|42CrMo|20CrMnTi/i.test(text),
  },
]

export function inferMaterialCategory(label: string) {
  const text = String(label || '').trim()
  if (!text) return ''
  const hit = MATERIAL_CATEGORY_RULES.find(rule => rule.test(text))
  return hit?.category || '其他'
}

export function useQuestionTreeMaterialRows(args: {
  currentQuestion: ComputedRef<QuestionTreeQuestion | null>
  currentAnswer: ComputedRef<QuestionTreeAnswer | null>
  isFallbackOption: (option: QuestionTreeOption) => boolean
}) {
  const materialRowsMap = ref<Record<string, MaterialQuestionRow[]>>({})

  const isMaterialTableQuestion = computed(() =>
    Boolean(args.currentQuestion.value?.multiple && args.currentQuestion.value.id.includes('material_scope')),
  )

  const materialScopeMode = computed<'grade' | 'category' | 'both'>(() => {
    const question = args.currentQuestion.value
    const text = [
      question?.title || '',
      question?.prompt || '',
      question?.confirmLabel || '',
      question?.sourceHint || '',
    ].join(' ')
    if (/按材料牌号|材料牌号/.test(text) && !/按材料类别|材料大类/.test(text)) return 'grade'
    if (/按材料类别|材料大类/.test(text) && !/按材料牌号|材料牌号/.test(text)) return 'category'
    return 'both'
  })

  const materialScopeLabel = computed(() => {
    if (materialScopeMode.value === 'grade') return '材料牌号'
    if (materialScopeMode.value === 'category') return '材料大类'
    return '材料信息'
  })

  const materialTableColumnCount = computed(() => materialScopeMode.value === 'both' ? 4 : 3)

  const materialRows = computed(() => {
    const questionId = args.currentQuestion.value?.id || ''
    return questionId ? (materialRowsMap.value[questionId] || []) : []
  })

  const selectedMaterialCount = computed(() =>
    materialRows.value.filter((row) => {
      if (!row.selected) return false
      if (materialScopeMode.value === 'grade') return Boolean(row.grade.trim())
      if (materialScopeMode.value === 'category') return Boolean(row.category.trim())
      return Boolean(row.grade.trim() || row.category.trim())
    }).length,
  )

  function selectedMaterialOptions() {
    const seen = new Set<string>()
    return materialRows.value
      .filter((row) => {
        if (!row.selected) return false
        if (materialScopeMode.value === 'grade') return Boolean(row.grade.trim())
        if (materialScopeMode.value === 'category') return Boolean(row.category.trim())
        return Boolean(row.grade.trim() || row.category.trim())
      })
      .map((row) => {
        const grade = row.grade.trim()
        const category = row.category.trim()
        if (materialScopeMode.value === 'grade') {
          return { value: `material_scope::grade::${grade}`, label: grade }
        }
        if (materialScopeMode.value === 'category') {
          return { value: `material_scope::category::${category}`, label: category }
        }
        return {
          value: row.value || `material_scope::${grade || category}`,
          label: grade && category ? `${grade}｜${category}` : grade || category,
        }
      })
      .filter((row) => {
        if (!row.label || seen.has(row.label)) return false
        seen.add(row.label)
        return true
      })
  }

  function clearMaterialSelection() {
    const questionId = args.currentQuestion.value?.id || ''
    if (!questionId) return
    materialRowsMap.value = {
      ...materialRowsMap.value,
      [questionId]: (materialRowsMap.value[questionId] || []).map(row => ({ ...row, selected: false })),
    }
  }

  function toggleMaterialRow(rowId: string) {
    const questionId = args.currentQuestion.value?.id || ''
    if (!questionId) return
    materialRowsMap.value = {
      ...materialRowsMap.value,
      [questionId]: (materialRowsMap.value[questionId] || []).map(row =>
        row.id === rowId ? { ...row, selected: !row.selected } : row,
      ),
    }
  }

  function updateMaterialRow(rowId: string, field: 'grade' | 'category', value: string) {
    const questionId = args.currentQuestion.value?.id || ''
    if (!questionId) return
    materialRowsMap.value = {
      ...materialRowsMap.value,
      [questionId]: (materialRowsMap.value[questionId] || []).map((row) => {
        if (row.id !== rowId) return row
        const next = { ...row, [field]: value }
        if (field === 'grade' && !next.category.trim()) {
          next.category = inferMaterialCategory(value)
        }
        return next
      }),
    }
  }

  function appendMaterialRow() {
    const questionId = args.currentQuestion.value?.id || ''
    if (!questionId) return
    const rows = materialRowsMap.value[questionId] || []
    materialRowsMap.value = {
      ...materialRowsMap.value,
      [questionId]: [
        ...rows,
        {
          id: `${questionId}-manual-${rows.length + 1}`,
          value: '',
          grade: '',
          category: '',
          countLabel: '',
          selected: true,
        },
      ],
    }
  }

  watch(
    () => args.currentQuestion.value,
    (question) => {
      if (!question?.multiple || !question.id.includes('material_scope')) return

      const answer = args.currentAnswer.value
      const selectedLabels = new Set(String(answer?.label || '').split('、').map(item => item.trim()).filter(Boolean))
      const detectedRows = question.options
        .filter(option => !args.isFallbackOption(option))
        .map((option, index) => ({
          id: `${question.id}-${index}`,
          value: option.value,
          grade: option.label,
          category: inferMaterialCategory(option.label),
          countLabel: option.countLabel,
          selected: selectedLabels.has(option.label),
        }))
      const detectedLabels = new Set(detectedRows.map(row => row.grade).filter(Boolean))
      const answeredManualRows = [...selectedLabels]
        .filter(label => !detectedLabels.has(label))
        .map((label, index) => ({
          id: `${question.id}-answered-manual-${index + 1}`,
          value: `material_scope::manual::${label}`,
          grade: label,
          category: inferMaterialCategory(label),
          countLabel: '',
          selected: true,
        }))
      const rows = [...detectedRows, ...answeredManualRows]
      while (rows.length < DEFAULT_MATERIAL_ROW_COUNT) {
        rows.push({
          id: `${question.id}-manual-${rows.length + 1}`,
          value: '',
          grade: '',
          category: '',
          countLabel: '',
          selected: false,
        })
      }
      materialRowsMap.value = {
        ...materialRowsMap.value,
        [question.id]: rows,
      }
    },
    { immediate: true },
  )

  return {
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
  }
}
