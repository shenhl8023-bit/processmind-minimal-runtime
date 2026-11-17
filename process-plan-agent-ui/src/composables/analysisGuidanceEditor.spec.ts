import { expect, it } from 'vitest'
import { createGuidanceEditorDraft } from './analysisGuidanceEditor'
it('shows inherited recommendations for a first occurrence without changing the saved configuration', () => {
  const current: any = { operation_guidance: { 钻孔: { recommendation: { mode: 'condition', basis: 'feature', features: ['孔'] } }, '检验#2': { recommendation: { mode: 'mainline' } } } }
  const draft = createGuidanceEditorDraft(current, ['钻孔#1', '检验#2', '未知#1'])
  expect(draft.operation_guidance['钻孔#1']).toEqual(current.operation_guidance.钻孔)
  expect(draft.operation_guidance['检验#2']?.recommendation?.mode).toBe('mainline')
  draft.operation_guidance['钻孔#1']!.recommendation!.features!.push('盲孔')
  expect(current.operation_guidance.钻孔.recommendation.features).toEqual(['孔'])
})
