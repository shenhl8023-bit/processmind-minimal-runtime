import { describe, expect, it } from 'vitest'
import { confirmFinalizeBatch } from './finalizeBatchConfirmation'
import type { FinalizeCard } from './finalizeViewHelpers'

function card(id: string): FinalizeCard {
  return {
    segment: {
      id, sequence: 1, normalized_step_name: id, step_family: '加工', phase: '加工',
      parent_segment: '', source_type: 'merged', source_operation_ids: [], source_nodes: [],
      doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5, label: '1/2' },
      detail_coverage: { matched_rows: 0 }, evidence_excerpt: [], matched_detail_rows: [],
      equipment_profile: { split_applied: false, equipment_types: [], equipment_models: [] },
      analysis_status: 'reviewed', factor_reviews: [],
    },
    conditionText: '当材料为6061时纳入当前工序',
    defaultConditionText: '当材料为6061时纳入当前工序', edited: false,
    factorNames: [], factorLabels: [], userAnswerLabels: [], userAnswerContextLabels: [],
    systemFactorLabels: [], rawRuleLines: [], availableFactors: [], analysisDraftContext: '',
    conditionReview: {
      status: 'pending_confirmation', source_text: '当材料为6061时纳入当前工序', source_hash: `${id}-hash`,
      issues: [], field_registry_version: 'fixture-v1', confirmed_by: '', confirmed_at: '',
      candidate: {
        kind: 'condition', preview: '材料为6061',
        when: { field: 'material.grade', op: 'eq', value: '6061' },
        then: { include_process_ids: [id], exclude_process_ids: [] },
      },
    },
  }
}

function confirm(card: FinalizeCard) {
  card.conditionReview = { ...card.conditionReview!, status: 'confirmed', confirmed: card.conditionReview!.candidate }
}

function options(cards: FinalizeCard[]): Parameters<typeof confirmFinalizeBatch>[0] {
  return {
    cards: () => cards, unsavedIds: () => new Set<string>(), busyIds: () => new Set<string>(),
    isCurrent: () => true, displayName: (card: FinalizeCard) => card.segment.normalized_step_name,
    confirm: async (card: FinalizeCard) => { confirm(card); return true },
    errorFor: () => undefined, errorMessage: (error: unknown) => (error as Error).message,
    onProgress: (_completed: number, _total: number) => {},
  }
}

describe('finalize batch confirmation eligibility and recovery', () => {
  it('stops unexecuted items on an explicit workflow conflict and preserves prior successes and drafts', async () => {
    const first = card('已成功'), conflict = card('版本冲突'), unexecuted = card('未执行'), draft = card('未执行草稿')
    const config = options([first, conflict, unexecuted, draft])
    config.unsavedIds = () => new Set(['未执行草稿'])
    const preserved = JSON.stringify([conflict, unexecuted, draft])
    const calls: string[] = []
    const progress: number[][] = []
    const reason = '当前页面已过期，请刷新后再操作。'
    config.onProgress = (completed, total) => { progress.push([completed, total]) }
    config.confirm = async item => {
      calls.push(item.segment.id)
      if (item.segment.id === '版本冲突') return { status: 'workflow_conflict', reason }
      confirm(item)
      return true
    }
    const result = await confirmFinalizeBatch(config)
    expect(calls).toEqual(['已成功', '版本冲突'])
    expect(result).toMatchObject({
      successCount: 1, remainingCount: 3,
      items: [
        { segmentId: '已成功', status: 'confirmed' },
        { segmentId: '版本冲突', status: 'failed', reason },
        { segmentId: '未执行', status: 'not_executed', reason: expect.stringContaining(reason) },
        { segmentId: '未执行草稿', status: 'not_executed', reason: expect.stringContaining('未执行') },
      ],
    })
    expect(JSON.stringify([conflict, unexecuted, draft])).toBe(preserved)
    expect(first.conditionReview!.status).toBe('confirmed')
    expect(progress).toEqual([[0, 4], [1, 4], [2, 4]])
  })

  it.each(['hash', 'source', 'status', 'kind'])('keeps an unusable %s candidate without submitting it', async invalid => {
    const item = card('待处理')
    if (invalid === 'hash') item.conditionReview!.source_hash = ''
    else if (invalid === 'source') item.conditionReview!.source_text = '另一份原文'
    else if (invalid === 'status') item.conditionReview!.status = 'draft'
    else item.conditionReview!.candidate = { kind: 'process_relation', preview: '来源工序出现后跟随', relation: { relation_type: 'trigger_after', source_process_ids: ['来源'], target_process_ids: ['待处理'] } }
    const before = JSON.stringify(item)
    const config = options([item])
    const result = await confirmFinalizeBatch(config)
    expect(JSON.stringify(item)).toBe(before)
    expect(result).toMatchObject({ successCount: 0, remainingCount: 1, items: [{ segmentId: '待处理', status: 'missing', reason: expect.any(String) }] })
    expect(result!.items[0]!.reason).not.toBe('')
  })

  it('keeps an unsaved edit on an already-confirmed rule in the remaining count', async () => {
    const item = card('已确认但正在修改')
    confirm(item)
    const before = JSON.stringify(item)
    const config = options([item])
    config.unsavedIds = () => new Set(['已确认但正在修改'])
    const result = await confirmFinalizeBatch(config)
    expect(result).toMatchObject({ successCount: 0, remainingCount: 1, items: [{ status: 'unsaved' }] })
    expect(JSON.stringify(item)).toBe(before)
  })

  it('continues after an unexpected per-item exception and retains the failed rule', async () => {
    const failed = card('失败工序'), successful = card('成功工序')
    const config = options([failed, successful])
    config.confirm = async item => {
      if (item.segment.id === '失败工序') throw new Error('连接中断')
      confirm(item)
      return true
    }
    const result = await confirmFinalizeBatch(config)
    expect(result).toMatchObject({ successCount: 1, remainingCount: 1, items: [{ status: 'failed', name: '失败工序', reason: '连接中断' }, { status: 'confirmed' }] })
    expect(failed.conditionReview!.status).toBe('pending_confirmation')
    expect(successful.conditionReview!.status).toBe('confirmed')
  })

  it('preserves a queued rule confirmed while waiting without counting it as another success', async () => {
    const first = card('先处理'), second = card('已由其它请求确认')
    const config = options([first, second])
    config.confirm = async item => {
      expect(item.segment.id).toBe('先处理')
      confirm(first)
      confirm(second)
      return true
    }
    const result = await confirmFinalizeBatch(config)
    expect(result).toMatchObject({ successCount: 1, remainingCount: 0, items: [{ segmentId: '先处理', status: 'confirmed' }] })
    expect(result!.items).toHaveLength(1)
  })
})
