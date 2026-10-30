import { afterEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'

import { useFinalizeDrafts } from './useFinalizeDrafts'

afterEach(() => vi.unstubAllGlobals())

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

  it('drops an acknowledged local draft without cancelling newer text being edited', () => {
    const state = useFinalizeDrafts(ref(1))
    const item = finalizeItem()
    state.setConditionTextDraft(item, '已在服务端保存的内容')
    state.startInlineEdit(item)
    state.inlineEditingText.value = '用户继续输入的新内容'
    state.clearPersistedDraft(item.segment.id)
    expect(state.drafts.value).toEqual({})
    expect(state.inlineEditingText.value).toBe('用户继续输入的新内容')
    expect(state.inlineEditingSegmentId.value).toBe('process_mark')
  })

  it('keeps a stale legacy recovery copy off the current saved source without deleting the copy', () => {
    const storage = new Map<string, string>()
    const localDraft = {
      conditionText: '旧的本机条件', factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [],
    }
    storage.set('processmind_finalize_drafts_v4_1', JSON.stringify({ process_mark: localDraft }))
    vi.stubGlobal('window', { localStorage: {
      getItem: (key: string) => storage.get(key) ?? null,
      setItem: (key: string, value: string) => storage.set(key, value),
    } })
    const state = useFinalizeDrafts(ref(1))
    const skipped = state.readDrafts([{
      id: 'process_mark', rule_review: { condition_review: {
        source_text: '另一窗口已保存的新条件', source_hash: 'new-source', status: 'confirmed',
      } },
    }] as any)
    expect(skipped).toBe(1)
    expect(state.drafts.value).toEqual({})
    state.persistDrafts()
    expect(JSON.parse(storage.get('processmind_finalize_drafts_v4_1')!)).toEqual({ process_mark: localDraft })
  })

  it('restores a legacy recovery copy when there is no saved source to supersede', () => {
    const localDraft = {
      conditionText: '尚未落库的本机条件', factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [],
    }
    vi.stubGlobal('window', { localStorage: { getItem: () => JSON.stringify({ process_mark: localDraft }) } })
    const state = useFinalizeDrafts(ref(1))
    expect(state.readDrafts([{ id: 'process_mark', rule_review: null }] as any)).toBe(0)
    expect(state.drafts.value.process_mark?.conditionText).toBe('尚未落库的本机条件')
  })

  it('persists the saved source baseline when creating a new recovery copy', () => {
    const state = useFinalizeDrafts(ref(1))
    const item = {
      ...finalizeItem(), conditionReview: {
        source_text: '保存时的原文', source_hash: 'source-1', confirmed_at: '2026-10-27T09:00:00',
      },
    }
    state.setConditionTextDraft(item, '修改后的条件')
    expect(state.drafts.value.process_mark).toMatchObject({
      baseReview: { sourceText: '保存时的原文', sourceHash: 'source-1', confirmedAt: '2026-10-27T09:00:00' },
    })
  })
})
