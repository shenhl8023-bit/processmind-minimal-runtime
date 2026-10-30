import { describe, expect, it } from 'vitest'
import { buildFinalizeCards, type FinalizeDraft } from './finalizeViewHelpers'
import { finalizeRuleMode } from '@/utils/finalizeRulePackage'

describe('saved finalize rule sources', () => {
  it('restores a saved conditional edit after its local recovery copy is cleared', () => {
    const cards = buildFinalizeCards([{
      id: 'remove_copper', normalized_step_name: '除铜', sequence: 10,
      factor_reviews: [], doc_coverage: { total_docs: 3, hit_docs: 3 },
      rule_review: { condition_review: {
        source_text: '当材料牌号为 9Cr18 时，纳入除铜工序', status: 'draft',
      } },
    }] as any, [], {})
    expect(cards[0]!.conditionText).toBe('当材料牌号为 9Cr18 时，纳入除铜工序')
    expect(finalizeRuleMode(cards[0])).toBe('conditional')
    expect(cards[0]!.edited).toBe(true)
  })

  it('uses the newer saved source instead of a legacy local recovery draft', () => {
    const cards = buildFinalizeCards([{
      id: 'remove_copper', normalized_step_name: '除铜', sequence: 10,
      factor_reviews: [], doc_coverage: { total_docs: 3, hit_docs: 3 },
      rule_review: { condition_review: {
        source_text: '当材料牌号为 9Cr18 时，纳入除铜工序', source_hash: 'new-source', status: 'confirmed',
      } },
    }] as any, [], {
      remove_copper: {
        conditionText: '旧的本机条件', factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [],
      },
    })
    expect(cards[0]!.conditionText).toBe('当材料牌号为 9Cr18 时，纳入除铜工序')
  })

  it('recovers local text only while its saved source baseline is unchanged', () => {
    const draft = {
      conditionText: '正在编辑的新条件', factorNames: [], userAnswerLabels: [], userAnswerContextLabels: [],
      baseReview: { sourceText: '已保存的原文', sourceHash: 'source-1', confirmedAt: '2026-10-27T09:00:00' },
    } as FinalizeDraft
    const segment = {
      id: 'remove_copper', normalized_step_name: '除铜', sequence: 10,
      factor_reviews: [], doc_coverage: { total_docs: 3, hit_docs: 3 },
      rule_review: { condition_review: {
        source_text: '已保存的原文', source_hash: 'source-1', confirmed_at: '2026-10-27T09:00:00', status: 'confirmed',
      } },
    }
    expect(buildFinalizeCards([segment] as any, [], { remove_copper: draft })[0]!.conditionText).toBe('正在编辑的新条件')
    segment.rule_review.condition_review.confirmed_at = '2026-10-27T10:00:00'
    expect(buildFinalizeCards([segment] as any, [], { remove_copper: draft })[0]!.conditionText).toBe('已保存的原文')
  })
})
