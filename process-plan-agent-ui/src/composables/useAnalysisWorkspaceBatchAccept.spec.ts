import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  saveSegmentRuleReview: vi.fn(),
  getSavedNormalizedRoute: vi.fn(),
  getSupersetRoute: vi.fn(),
  getDocumentOperationDetails: vi.fn(),
  listDocuments: vi.fn(),
  listOperations: vi.fn(),
  listProjects: vi.fn(),
}))

vi.mock('@/api', () => ({
  saveSegmentRuleReview: mocks.saveSegmentRuleReview,
  getSavedNormalizedRoute: mocks.getSavedNormalizedRoute,
  getSupersetRoute: mocks.getSupersetRoute,
  getDocumentOperationDetails: mocks.getDocumentOperationDetails,
  listDocuments: mocks.listDocuments,
  listOperations: mocks.listOperations,
  listProjects: mocks.listProjects,
}))

vi.mock('vue-router', () => ({
  useRoute: vi.fn(() => ({ query: { project_id: '1' } })),
  useRouter: vi.fn(() => ({ push: vi.fn() })),
}))

vi.mock('@/composables/rulePreprocessingTrigger', () => ({
  startRulePreprocessingForSavedRoute: vi.fn(),
}))

vi.mock('@/composables/useCurrentProject', () => ({
  resolveCurrentProjectId: vi.fn(() => '1'),
  clearStoredCurrentProjectId: vi.fn(),
  setStoredCurrentProjectId: vi.fn(),
}))

import { useAnalysisWorkspace } from './useAnalysisWorkspace'

describe('useAnalysisWorkspace batch accept all', () => {
  beforeEach(() => {
    mocks.saveSegmentRuleReview.mockReset()
    mocks.getSavedNormalizedRoute.mockReset()
    mocks.getSupersetRoute.mockReset()
    mocks.getDocumentOperationDetails.mockReset()
    mocks.listDocuments.mockReset()
    mocks.listOperations.mockReset()
    mocks.listProjects.mockReset()

    mocks.listProjects.mockResolvedValue([{ id: 1, name: 'Project 1' }])
    mocks.listDocuments.mockResolvedValue([])
    mocks.listOperations.mockResolvedValue([])
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [] })
    mocks.getDocumentOperationDetails.mockResolvedValue({ items: [] })
  })

  it('iterates through all targets without ReferenceError and saves each segment', async () => {
    const route = {
      route_id: 10,
      project_id: 1,
      version: 1,
      source_signature: 'sig',
      saved_by: 'tester',
      saved_at: '2026-01-01',
      total_docs: 1,
      segment_count: 2,
      workflow_revision: 5,
      segments: [
        {
          id: 'seg-1',
          sequence: 1,
          normalized_step_name: '下料',
          step_family: '毛坯准备类',
          phase: '热前',
          parent_segment: '',
          source_type: 'single',
          source_operation_ids: [1],
          source_nodes: ['下料'],
          doc_coverage: { hit_docs: 1, total_docs: 1, ratio: 1, label: '1/1' },
          detail_coverage: { matched_rows: 1, total_rows: 1, ratio: 1 },
          evidence_excerpt: [],
          matched_detail_rows: [],
          equipment_profile: { types: [], models: [] },
          analysis_status: 'pending',
          factor_reviews: [],
          rule_review: null,
        },
        {
          id: 'seg-2',
          sequence: 2,
          normalized_step_name: '车端面',
          step_family: '车削类',
          phase: '热前',
          parent_segment: '',
          source_type: 'single',
          source_operation_ids: [2],
          source_nodes: ['车端面'],
          doc_coverage: { hit_docs: 1, total_docs: 1, ratio: 1, label: '1/1' },
          detail_coverage: { matched_rows: 1, total_rows: 1, ratio: 1 },
          evidence_excerpt: [],
          matched_detail_rows: [],
          equipment_profile: { types: [], models: [] },
          analysis_status: 'pending',
          factor_reviews: [],
          rule_review: null,
        },
      ],
    }

    mocks.getSavedNormalizedRoute.mockResolvedValue(route)
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => ({
      project_id: args.project_id,
      route_id: args.route_id,
      segment_id: args.segment_id,
      analysis_status: 'reviewed',
      normalized_step_name: null,
      rule_review: {
        id: 100,
        decision: 'accepted',
        note: args.note,
        summary_lines: args.summary_lines,
        question_trail: args.question_trail,
        created_at: '',
        updated_at: '',
      },
    }))

    const workspace = useAnalysisWorkspace()

    workspace.projectId.value = 1
    await workspace.loadSavedRoute(true)
    expect(workspace.savedRoute.value).toBeTruthy()

    await workspace.acceptAllRecommendedForAllSegments()

    expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(2)
    expect(mocks.saveSegmentRuleReview).toHaveBeenNthCalledWith(
      1,
      expect.objectContaining({
        project_id: 1,
        route_id: 10,
        segment_id: 'seg-1',
        decision: 'accepted',
      }),
    )
    expect(mocks.saveSegmentRuleReview).toHaveBeenNthCalledWith(
      2,
      expect.objectContaining({
        project_id: 1,
        route_id: 10,
        segment_id: 'seg-2',
        decision: 'accepted',
      }),
    )
  })

  it('stops an old batch before it saves the next segment into a switched task', async () => {
    let finish!: (value: any) => void
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => ({
      project_id: args.project_id, route_id: args.route_id, segment_id: args.segment_id,
      analysis_status: 'reviewed', rule_review: { decision: 'accepted' },
    }))
    const workspace = useAnalysisWorkspace()
    const segments = ['seg-1', 'seg-2'].map(id => ({
      id, normalized_step_name: '标记', source_nodes: ['标记'], source_operation_ids: [],
      matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 }, factor_reviews: [], rule_review: null,
    }))
    workspace.projectId.value = 1
    workspace.savedRoute.value = { project_id: 1, route_id: 10, workflow_revision: 5, segments } as any
    workspace.selectedSegmentId.value = 'seg-1'
    const pending = workspace.acceptAllRecommendedForAllSegments()
    await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
    workspace.projectId.value = 2
    workspace.savedRoute.value = { project_id: 2, route_id: 20, workflow_revision: 1, segments } as any
    finish({
      project_id: 1, route_id: 10, segment_id: 'seg-1',
      analysis_status: 'reviewed', rule_review: { decision: 'accepted' },
    })
    await pending

    expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
    expect(workspace.savedRoute.value!.segments.every(segment => !segment.rule_review)).toBe(true)
  })

  it('saves a completed reanswer even when the previous decision was already accepted', async () => {
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => ({
      project_id: 1, route_id: 10, segment_id: args.segment_id, analysis_status: 'reviewed',
      rule_review: { decision: 'accepted', note: args.note, question_trail: args.question_trail, summary_lines: args.summary_lines },
    }))
    const workspace = useAnalysisWorkspace()
    workspace.projectId.value = 1
    workspace.savedRoute.value = {
      project_id: 1, route_id: 10, workflow_revision: 5, segments: [{
        id: 'mark', normalized_step_name: '标记', source_nodes: ['标记'], source_operation_ids: [],
        matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
        detail_coverage: { matched_rows: 1 }, factor_reviews: [],
        rule_review: { decision: 'accepted', note: 'old', question_trail: [], summary_lines: [] },
      }],
    } as any
    workspace.selectedSegmentId.value = 'mark'
    workspace.resetQuestionTree()
    workspace.acceptAllRecommendedQuestionTree()

    await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
    expect(workspace.savedRoute.value!.segments[0]!.rule_review!.question_trail.length).toBeGreaterThan(0)
  })

  it('stops an old batch after returning to the same task and route revision', async () => {
    let finish!: (value: any) => void
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => ({
      project_id: args.project_id, route_id: args.route_id, segment_id: args.segment_id,
      analysis_status: 'reviewed', rule_review: { decision: 'accepted' },
    }))
    const workspace = useAnalysisWorkspace()
    const newSegments = () => ['seg-1', 'seg-2'].map(id => ({
      id, normalized_step_name: '标记', source_nodes: ['标记'], source_operation_ids: [],
      matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 }, factor_reviews: [], rule_review: null,
    }))
    workspace.projectId.value = 1
    workspace.savedRoute.value = { project_id: 1, route_id: 10, workflow_revision: 5, segments: newSegments() } as any
    workspace.selectedSegmentId.value = 'seg-1'
    const pending = workspace.acceptAllRecommendedForAllSegments()
    await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
    workspace.projectId.value = 2
    workspace.savedRoute.value = { project_id: 2, route_id: 20, workflow_revision: 1, segments: newSegments() } as any
    workspace.projectId.value = 1
    workspace.savedRoute.value = { project_id: 1, route_id: 10, workflow_revision: 5, segments: newSegments() } as any
    finish({ project_id: 1, route_id: 10, segment_id: 'seg-1', analysis_status: 'reviewed', rule_review: { decision: 'accepted' } })
    await pending

    expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
    expect(workspace.savedRoute.value!.segments.every(segment => !segment.rule_review)).toBe(true)
  })
})
