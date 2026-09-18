import { computed, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import {
  useQuestionTreeMaterialRows,
  type QuestionTreeOption,
  type QuestionTreeQuestion,
} from './useQuestionTreeMaterialRows'

function isFallbackOption(option: QuestionTreeOption) {
  const value = String(option.value || '').trim().toLowerCase()
  const label = String(option.label || '').trim()
  return (
    value.includes('other')
    || value.includes('uncertain')
    || value.includes('manual')
    || label.includes('其他')
    || label.includes('未自动识别')
    || label.includes('需要人工补充')
  )
}

describe('useQuestionTreeMaterialRows', () => {
  it('automatically pre-selects detected candidate rows when question is unanswered', () => {
    const currentQuestion = ref<QuestionTreeQuestion | null>({
      id: 'material_scope_detail',
      title: '材料范围确认',
      prompt: '请进一步确认“正常化”工序存在条件所对应的按材料牌号范围。',
      multiple: true,
      options: [
        {
          value: 'material_scope::4Cr14Ni14W2Mo',
          label: '4Cr14Ni14W2Mo',
          countLabel: '2/20',
          docCount: 2,
          totalCount: 20,
        },
      ],
    })
    const currentAnswer = ref<any>(null)

    const { materialRows, selectedMaterialCount, selectedMaterialOptions } = useQuestionTreeMaterialRows({
      currentQuestion: computed(() => currentQuestion.value),
      currentAnswer: computed(() => currentAnswer.value),
      isFallbackOption,
    })

    expect(materialRows.value.length).toBe(5)
    // First row should be 4Cr14Ni14W2Mo and automatically checked!
    expect(materialRows.value[0]).toMatchObject({
      grade: '4Cr14Ni14W2Mo',
      countLabel: '2/20',
      selected: true,
    })
    // Empty manual rows should be unchecked
    expect(materialRows.value[1]?.selected).toBe(false)
    expect(selectedMaterialCount.value).toBe(1)
    expect(selectedMaterialOptions()).toEqual([
      { value: 'material_scope::grade::4Cr14Ni14W2Mo', label: '4Cr14Ni14W2Mo' },
    ])
  })

  it('automatically pre-selects detected candidates when previous answer was a fallback (未自动识别)', () => {
    const currentQuestion = ref<QuestionTreeQuestion | null>({
      id: 'material_scope_detail',
      title: '材料范围确认',
      prompt: '请进一步确认“正常化”工序存在条件所对应的按材料牌号范围。',
      multiple: true,
      options: [
        {
          value: 'material_scope::4Cr14Ni14W2Mo',
          label: '4Cr14Ni14W2Mo',
          countLabel: '2/20',
          docCount: 2,
          totalCount: 20,
        },
      ],
    })
    const currentAnswer = ref<any>({
      nodeId: 'material_scope_detail',
      value: 'material_scope::未自动识别',
      label: '当前样本里暂未自动识别出明确按材料牌号',
    })

    const { materialRows, selectedMaterialCount } = useQuestionTreeMaterialRows({
      currentQuestion: computed(() => currentQuestion.value),
      currentAnswer: computed(() => currentAnswer.value),
      isFallbackOption,
    })

    // Should treat fallback answer as not a valid material selection, and pre-select the detected candidate
    expect(materialRows.value[0]).toMatchObject({
      grade: '4Cr14Ni14W2Mo',
      selected: true,
    })
    expect(selectedMaterialCount.value).toBe(1)
  })

  it('preserves user explicit selections when a valid non-fallback answer exists', () => {
    const currentQuestion = ref<QuestionTreeQuestion | null>({
      id: 'material_scope_detail',
      title: '材料范围确认',
      prompt: '请进一步确认“正常化”工序存在条件所对应的按材料牌号范围。',
      multiple: true,
      options: [
        {
          value: 'material_scope::4Cr14Ni14W2Mo',
          label: '4Cr14Ni14W2Mo',
          countLabel: '2/20',
        },
        {
          value: 'material_scope::9Cr18',
          label: '9Cr18',
          countLabel: '1/20',
        },
      ],
    })
    const currentAnswer = ref<any>({
      nodeId: 'material_scope_detail',
      value: 'material_scope::grade::9Cr18',
      label: '9Cr18',
    })

    const { materialRows, selectedMaterialCount } = useQuestionTreeMaterialRows({
      currentQuestion: computed(() => currentQuestion.value),
      currentAnswer: computed(() => currentAnswer.value),
      isFallbackOption,
    })

    expect(materialRows.value[0]?.grade).toBe('4Cr14Ni14W2Mo')
    expect(materialRows.value[0]?.selected).toBe(false)
    expect(materialRows.value[1]?.grade).toBe('9Cr18')
    expect(materialRows.value[1]?.selected).toBe(true)
    expect(selectedMaterialCount.value).toBe(1)
  })
})
