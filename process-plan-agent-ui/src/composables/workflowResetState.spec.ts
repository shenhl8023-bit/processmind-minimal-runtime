import { describe, expect, it } from 'vitest'

import {
  clearProjectWorkflowLocalState,
  publishWorkflowReset,
  isWorkflowRevisionConflict,
  workflowResetSignal,
} from './workflowResetState'

class MemoryStorage {
  private values = new Map<string, string>()

  get length() { return this.values.size }
  key(index: number) { return Array.from(this.values.keys())[index] ?? null }
  getItem(key: string) { return this.values.get(key) ?? null }
  setItem(key: string, value: string) { this.values.set(key, value) }
  removeItem(key: string) { this.values.delete(key) }
}

describe('workflow reset state', () => {
  it('clears analysis and finalize local state for step two and three resets', () => {
    const storage = new MemoryStorage()
    storage.setItem('processmind_analysis_question_tree_v10_17', '{}')
    storage.setItem('processmind_finalize_drafts_v4_17', '{}')
    storage.setItem('processmind_finalize_drafts_v4_18', '{}')

    clearProjectWorkflowLocalState(17, 3, storage)

    expect(storage.getItem('processmind_analysis_question_tree_v10_17')).toBeNull()
    expect(storage.getItem('processmind_finalize_drafts_v4_17')).toBeNull()
    expect(storage.getItem('processmind_finalize_drafts_v4_18')).toBe('{}')
  })

  it('preserves user text drafts when only step four recognition is reset', () => {
    const storage = new MemoryStorage()
    storage.setItem('processmind_analysis_question_tree_v10_17', '{"answers":1}')
    storage.setItem('processmind_finalize_drafts_v4_17', '{"conditionText":"用户原文"}')

    clearProjectWorkflowLocalState(17, 4, storage)

    expect(storage.getItem('processmind_analysis_question_tree_v10_17')).not.toBeNull()
    expect(storage.getItem('processmind_finalize_drafts_v4_17')).toContain('用户原文')
  })

  it('publishes the latest project reset revision for mounted views', () => {
    publishWorkflowReset({ projectId: 17, fromStep: 3, workflowRevision: 9 })

    expect(workflowResetSignal.value).toMatchObject({
      projectId: 17,
      fromStep: 3,
      workflowRevision: 9,
    })
  })

  it('recognizes stale workflow revision conflicts without confusing condition text conflicts', () => {
    expect(isWorkflowRevisionConflict({
      response: { status: 409, data: { detail: { message: '当前页面已过期，请刷新后再操作。' } } },
    })).toBe(true)
    expect(isWorkflowRevisionConflict({
      response: { status: 409, data: { detail: '条件文字已经发生变化' } },
    })).toBe(false)
  })
})
