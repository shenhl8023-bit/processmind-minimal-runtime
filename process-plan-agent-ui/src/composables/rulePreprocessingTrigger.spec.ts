import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  startRulePreprocessing: vi.fn(),
}))

vi.mock('@/api/rulePackages', () => ({
  startRulePreprocessing: mocks.startRulePreprocessing,
}))

import {
  buildRulePreprocessFailureSummary,
  buildRulePreprocessingTriggerKey,
  startRulePreprocessingForSavedRoute,
} from './rulePreprocessingTrigger'

const baseSegment = {
  id: 'seg-main',
  sequence: 10,
  normalized_step_name: '粗车',
  step_family: '',
  phase: '',
  parent_segment: '',
  source_type: '',
  source_operation_ids: [1],
  source_nodes: [],
  source_operation_names: [],
  reason_codes: [],
  doc_coverage: { hit_docs: 2, total_docs: 2, ratio: 1, label: '' },
  detail_coverage: { matched_rows: 2 },
  evidence_excerpt: [],
  matched_detail_rows: [],
  equipment_profile: { split_applied: false, equipment_types: [], equipment_models: [] },
  analysis_status: 'accepted',
  factor_reviews: [],
  rule_review: null,
}

describe('startRulePreprocessingForSavedRoute', () => {
  beforeEach(() => {
    mocks.startRulePreprocessing.mockReset()
    mocks.startRulePreprocessing.mockResolvedValue({ task_status: 'running' })
  })

  it('starts preprocessing only for reviewable finalized rules', async () => {
    await startRulePreprocessingForSavedRoute({
      projectId: 12,
      savedRoute: {
        route_id: 99,
        project_id: 12,
        version: 1,
        source_signature: 'sig',
        saved_by: 'user',
        saved_at: '',
        total_docs: 2,
        segment_count: 2,
        workflow_revision: 7,
        segments: [
          baseSegment,
          {
            ...baseSegment,
            id: 'seg-condition',
            normalized_step_name: '铣槽',
            doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5, label: '' },
            factor_reviews: [{
              id: 2,
              factor_name: 'feature.slot',
              decision: 'confirmed',
              note: '',
              source_type: 'manual',
              evidence_refs: [],
              source_operation_ids: [],
              source_operation_names: [],
              created_at: '',
              updated_at: '',
            }],
            rule_review: {
              id: 1,
              decision: 'accepted',
              note: '',
              summary_lines: ['当存在槽类结构时，安排铣槽。'],
              question_trail: [{ nodeId: 'rule_reason_root', value: 'slot', label: '槽类结构' }],
              condition_review: {
                source_text: '当存在槽类结构时，安排铣槽。',
                source_hash: 'hash',
                status: 'invalid',
                candidate: null,
                confirmed: null,
                confidence: null,
                issues: [],
                field_registry_version: 'test',
                confirmed_by: '',
                confirmed_at: '',
              },
              created_at: '',
              updated_at: '',
            },
          },
        ],
      } as any,
      supersetOperations: [
        { id: 1, name: '粗车', sequence: 10, op_type: 'process', confidence: 'high', factors: [] },
      ] as any,
      segmentDisplayName: segment => segment.normalized_step_name,
    })

    expect(mocks.startRulePreprocessing).toHaveBeenCalledTimes(1)
    expect(mocks.startRulePreprocessing).toHaveBeenCalledWith({
      project_id: 12,
      route_id: 99,
      expected_workflow_revision: 7,
      processes: expect.arrayContaining([
        expect.objectContaining({ process_id: 'seg-main', display_name: '粗车', main: true }),
        expect.objectContaining({ process_id: 'seg-condition', display_name: '铣槽', main: false }),
      ]),
      items: [
        expect.objectContaining({
          segment_id: 'seg-condition',
          process_id: 'seg-condition',
          process_name: '铣槽',
          source_text: expect.stringContaining('槽类结构'),
        }),
      ],
    })
  })

  it('does not call the backend when no route is available', async () => {
    await startRulePreprocessingForSavedRoute({
      projectId: 12,
      savedRoute: null,
      supersetOperations: [],
      segmentDisplayName: segment => segment.normalized_step_name,
    })

    expect(mocks.startRulePreprocessing).not.toHaveBeenCalled()
  })

  it('builds a stable trigger key from route revision and preprocessing payload', () => {
    const args = {
      projectId: 12,
      savedRoute: {
        route_id: 99,
        project_id: 12,
        version: 1,
        source_signature: 'sig',
        saved_by: 'user',
        saved_at: '',
        total_docs: 2,
        segment_count: 1,
        workflow_revision: 7,
        segments: [{
          ...baseSegment,
          id: 'seg-condition',
          normalized_step_name: '铣槽',
          doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5, label: '' },
          factor_reviews: [{
            id: 2,
            factor_name: 'feature.slot',
            decision: 'confirmed',
            note: '',
            source_type: 'manual',
            evidence_refs: [],
            source_operation_ids: [],
            source_operation_names: [],
            created_at: '',
            updated_at: '',
          }],
          rule_review: {
            id: 1,
            decision: 'accepted',
            note: '',
            summary_lines: ['当存在槽类结构时，安排铣槽。'],
            question_trail: [{ nodeId: 'rule_reason_root', value: 'slot', label: '槽类结构' }],
            condition_review: {
              source_text: '当存在槽类特征时，纳入铣槽工序。',
              source_hash: 'hash',
              status: 'invalid',
              candidate: null,
              confirmed: null,
              confidence: null,
              issues: [],
              field_registry_version: 'test',
              confirmed_by: '',
              confirmed_at: '',
            },
            created_at: '',
            updated_at: '',
          },
        }],
      } as any,
      supersetOperations: [] as any,
      segmentDisplayName: (segment: any) => segment.normalized_step_name,
    }

    expect(buildRulePreprocessingTriggerKey(args)).toBe(buildRulePreprocessingTriggerKey(args))
    expect(buildRulePreprocessingTriggerKey({
      ...args,
      savedRoute: {
        ...args.savedRoute,
        workflow_revision: 8,
      },
    } as any)).not.toBe(buildRulePreprocessingTriggerKey(args))
  })
})

describe('buildRulePreprocessFailureSummary', () => {
  it('summarizes failed preprocessing state with readable first failure lines', () => {
    const summary = buildRulePreprocessFailureSummary({
      project_id: 7103,
      route_id: 1,
      workflow_revision: 3,
      task_status: 'completed',
      total_count: 22,
      completed_count: 0,
      failed_count: 22,
      current_segment_id: '',
      message: '规则候选已准备 0/22 条，22 条需要重试',
      error: [
        'split-900007: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
        'split-900009: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
        'split-900008: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
        'split-900010: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
      ].join('\n'),
      input_hash: 'hash',
      started_at: '',
      updated_at: '',
      finished_at: '',
    })

    expect(summary).toEqual({
      title: '规则候选预处理失败 22 条',
      message: '规则候选已准备 0/22 条，22 条需要重试',
      lines: [
        'split-900007: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
        'split-900009: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
        'split-900008: 422: 标准工序列表包含不属于当前路线的工序：process_quench',
      ],
      overflowCount: 1,
    })
  })

  it('returns null when preprocessing has no failures', () => {
    expect(buildRulePreprocessFailureSummary({
      project_id: 7103,
      route_id: 1,
      workflow_revision: 3,
      task_status: 'completed',
      total_count: 1,
      completed_count: 1,
      failed_count: 0,
      current_segment_id: '',
      message: '规则候选已准备 1/1 条',
      error: '',
      input_hash: 'hash',
      started_at: '',
      updated_at: '',
      finished_at: '',
    })).toBeNull()
  })
})
