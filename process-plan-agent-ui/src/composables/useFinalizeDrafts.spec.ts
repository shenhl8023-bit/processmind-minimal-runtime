import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useFinalizeDrafts } from './useFinalizeDrafts'

function finalizeItem() {
  return {
    segment: { id: 'process_mark' },
    conditionText: '当需要追溯标印时，安排标记工序',
    factorNames: [],
    userAnswerLabels: [],
    userAnswerContextLabels: [],
  }
}

describe('finalize condition drafts', () => {
  it('does not create an edited draft when save text is unchanged', () => {
    const state = useFinalizeDrafts(ref(1))
    const item = finalizeItem()

    state.startInlineEdit(item)
    state.inlineEditingText.value = `  ${item.conditionText}  `

    expect(state.saveInlineEdit(item)).toBe(false)
    expect(state.drafts.value).toEqual({})
    expect(state.inlineEditingSegmentId.value).toBeNull()
  })

  it('creates a draft and reports a change when save text differs', () => {
    const state = useFinalizeDrafts(ref(1))
    const item = finalizeItem()

    state.startInlineEdit(item)
    state.inlineEditingText.value = '当用户需要标记时，安排标记工序'

    expect(state.saveInlineEdit(item)).toBe(true)
    expect(state.drafts.value.process_mark?.conditionText).toBe('当用户需要标记时，安排标记工序')
    expect(state.inlineEditingSegmentId.value).toBeNull()
  })

  it('clears mounted drafts after step two or three is reset', () => {
    const state = useFinalizeDrafts(ref(1))
    const item = finalizeItem()
    state.setConditionTextDraft(item, '用户修改后的条件')

    state.clearAllDrafts()

    expect(state.drafts.value).toEqual({})
  })
})
