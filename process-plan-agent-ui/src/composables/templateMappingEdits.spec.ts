import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { clearTemplateMappingEdits, hasPendingTemplateMappingEdits, loadTemplateMappingPrecisionDraft, saveTemplateMappingEdits } from './templateMappingEdits'

const context = { projectId: 6, routeVersionId: 31, workflowRevision: 4, templateRevision: 2 }
beforeEach(() => {
  const values = new Map<string, string>()
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => values.get(key) ?? null,
    setItem: (key: string, value: string) => values.set(key, value),
    removeItem: (key: string) => values.delete(key),
  })
})
afterEach(() => vi.unstubAllGlobals())

describe('pending template mapping edits', () => {
  it('blocks publication only for the matching project, route, workflow and template', () => {
    saveTemplateMappingEdits(context, true, { turn: '精加工' })
    expect(hasPendingTemplateMappingEdits(6, 31, 4, 2)).toBe(true)
    expect(hasPendingTemplateMappingEdits(7, 31, 4, 2)).toBe(false)
    expect(hasPendingTemplateMappingEdits(6, 32, 4, 2)).toBe(false)
    expect(hasPendingTemplateMappingEdits(6, 31, 5, 2)).toBe(false)
    expect(hasPendingTemplateMappingEdits(6, 31, 4, 3)).toBe(false)
  })

  it('restores unsaved precision and clears pending edits after save or discard', () => {
    saveTemplateMappingEdits(context, true, { turn: '精加工' })
    expect(loadTemplateMappingPrecisionDraft(context, { turn: '粗加工' })).toEqual({ turn: '精加工' })
    clearTemplateMappingEdits({ ...context, templateRevision: 3 })
    expect(hasPendingTemplateMappingEdits(6, 31, 4, 2)).toBe(true)
    saveTemplateMappingEdits(context, false, {})
    expect(hasPendingTemplateMappingEdits(6, 31, 4, 2)).toBe(false)
    expect(loadTemplateMappingPrecisionDraft(context, { turn: '粗加工' })).toEqual({ turn: '粗加工' })
  })
})

it('hydrates old precision-only drafts with saved exceptions and scopes exception drafts to all revisions', async () => {
  const { loadTemplateMappingExceptionDraft } = await import('./templateMappingEdits')
  const fallback = { hiddenStepKeys: ['a.s1'], waivedGroupPaths: [['A', '孔']] }
  saveTemplateMappingEdits(context, true, { turn: '精加工' })
  expect(loadTemplateMappingExceptionDraft(context, fallback)).toEqual(fallback)
  const exceptions = { hiddenStepKeys: ['b.s1'], waivedGroupPaths: [['B', '槽']] }
  saveTemplateMappingEdits(context, true, {}, exceptions)
  expect(loadTemplateMappingExceptionDraft(context, fallback)).toEqual(exceptions)
  for (const change of [{ projectId: 7 }, { routeVersionId: 32 }, { workflowRevision: 5 }, { templateRevision: 3 }]) {
    expect(loadTemplateMappingExceptionDraft({ ...context, ...change }, fallback)).toEqual(fallback)
  }
  clearTemplateMappingEdits(context)
  expect(loadTemplateMappingExceptionDraft(context, fallback)).toEqual(fallback)
})

it('falls back to the saved exception state for malformed old draft fields', async () => {
  const { loadTemplateMappingExceptionDraft } = await import('./templateMappingEdits')
  localStorage.setItem('processmind:pending-template-mapping:6', JSON.stringify({
    ...context, precisionOverrides: {}, hiddenStepKeys: [42], waivedGroupPaths: ['孔'],
  }))
  const fallback = { hiddenStepKeys: ['a.s1'], waivedGroupPaths: [['A', '孔']] }
  expect(loadTemplateMappingExceptionDraft(context, fallback)).toEqual(fallback)
})
