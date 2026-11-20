import { beforeEach, describe, expect, it, vi } from 'vitest'
import { effectScope, nextTick } from 'vue'

const mocks = vi.hoisted(() => ({
  saveSegmentRuleReview: vi.fn(),
  getSavedNormalizedRoute: vi.fn(),
  getSupersetRoute: vi.fn(),
  getDocumentOperationDetails: vi.fn(),
  listDocuments: vi.fn(),
  listOperations: vi.fn(),
  listProjects: vi.fn(),
  getAnalysisGuidance: vi.fn(), generateAnalysisGuidance: vi.fn(),
  resetWorkflow: vi.fn(), messageError: vi.fn(),
}))

vi.mock('@/api', () => ({
  saveSegmentRuleReview: mocks.saveSegmentRuleReview,
  getSavedNormalizedRoute: mocks.getSavedNormalizedRoute,
  getSupersetRoute: mocks.getSupersetRoute,
  getDocumentOperationDetails: mocks.getDocumentOperationDetails,
  listDocuments: mocks.listDocuments,
  listOperations: mocks.listOperations,
  listProjects: mocks.listProjects,
  getAnalysisGuidance: mocks.getAnalysisGuidance,
  generateAnalysisGuidance: mocks.generateAnalysisGuidance,
  resetWorkflow: mocks.resetWorkflow,
}))

vi.mock('element-plus', () => ({ ElMessage: { error: mocks.messageError } }))

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

async function settleAutosave() {
  for (let i = 0; i < 8; i++) await nextTick()
}

function createAutosaveWorkspace() {
  const scope = effectScope()
  const workspace = scope.run(() => useAnalysisWorkspace())!
  workspace.projectId.value = 1
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
  workspace.analysisGuidance.value = {
    schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'],
    feature_mappings: {}, operation_guidance: { 镀铜: { recommendation: { mode: 'manual' } } },
  }
  workspace.savedRoute.value = {
    project_id: 1, route_id: 10, workflow_revision: 5,
    segments: ['a', 'b', 'c'].map((id, i) => ({
      id, export_process_id: `export_${id}`, sequence: i + 1, normalized_step_name: '镀铜',
      source_nodes: ['镀铜'], source_operation_ids: [], matched_detail_rows: [],
      doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 }, factor_reviews: [], rule_review: null,
    })),
  } as any
  return { workspace, scope }
}

function reviewResponse(args: any) {
  return {
    project_id: args.project_id, route_id: args.route_id, segment_id: args.segment_id,
    analysis_status: 'reviewed', rule_review: {
      decision: args.decision, note: args.note, question_trail: args.question_trail,
      summary_lines: args.summary_lines, analysis_draft: args.analysis_draft,
    },
  }
}

describe('useAnalysisWorkspace batch accept all', () => {
  it.each(['generating', 'failed'] as const)('does not auto-confirm or report missing answers while guidance is %s and resumes when ready', async (state) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      const ready = workspace.analysisGuidance.value
      workspace.analysisGuidance.value = null
      workspace.guidanceGenerating.value = state === 'generating'
      workspace.guidanceError.value = state === 'failed' ? '模型未返回有效正文' : ''
      workspace.savedRoute.value!.segments[0]!.doc_coverage = { hit_docs: 2, total_docs: 2, ratio: 1, label: '2/2' }
      workspace.selectedSegmentId.value = 'a'
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview).not.toHaveBeenCalled()
      expect(workspace.error.value).toBe('')
      expect(workspace.savedRoute.value!.segments[0]!.rule_review).toBeNull()

      workspace.guidanceGenerating.value = false
      workspace.guidanceError.value = ''
      workspace.analysisGuidance.value = ready
      await settleAutosave()
      expect(workspace.savedRoute.value!.segments[0]!.rule_review?.decision).toBe('accepted')
      expect(workspace.error.value).toBe('')
    } finally { scope.stop() }
  })

  it.each(['success', 'failure'] as const)('clears adoption feedback as soon as generation starts and keeps saved answers on %s', async (outcome) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    let finish!: (value: any) => void
    let fail!: (reason: any) => void
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.recommendationSummary.value).toBe('已采纳 3 道工序推荐。')
      const saved = JSON.parse(JSON.stringify(workspace.savedRoute.value))
      mocks.getSavedNormalizedRoute.mockResolvedValue(saved)
      mocks.getAnalysisGuidance.mockResolvedValue({ configuration: workspace.analysisGuidance.value })
      mocks.generateAnalysisGuidance.mockReturnValueOnce(new Promise((resolve, reject) => { finish = resolve; fail = reject }))
      const generating = workspace.loadSavedRoute(true)
      expect(workspace.recommendationSummary.value).toBe('')
      await vi.waitFor(() => expect(workspace.guidanceGenerating.value).toBe(true))
      if (outcome === 'success') finish({ configuration: { revision: 9 } })
      else fail({ response: { data: { detail: { message: '本轮生成失败' } } } })
      await generating
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.savedRoute.value).toEqual(saved)
      expect(workspace.guidanceError.value).toBe(outcome === 'failure' ? '本轮生成失败' : '')
    } finally { scope.stop() }
  })

  it.each(['resetQuestionTree', 'reanswerLastQuestionTree'] as const)('clears old adoption feedback on %s without deleting the saved review', async (action) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      const saved = JSON.parse(JSON.stringify(workspace.savedRoute.value))
      workspace[action]()
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.savedRoute.value).toEqual(saved)
    } finally { scope.stop() }
  })

  it('clears old adoption feedback when an authorized full reset starts even if reset fails', async () => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    let fail!: (reason: any) => void
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      const saved = JSON.parse(JSON.stringify(workspace.savedRoute.value))
      mocks.resetWorkflow.mockReturnValueOnce(new Promise((_resolve, reject) => { fail = reject }))
      const reset = workspace.resetAllAnalysisAnswers()
      expect(workspace.recommendationSummary.value).toBe('')
      fail({ response: { data: { detail: '重答未获保存' } } })
      expect(await reset).toBe(false)
      expect(workspace.savedRoute.value).toEqual(saved)
      expect(workspace.error.value).toBe('重答未获保存')
    } finally { scope.stop(); quiet.mockRestore() }
  })

  it.each(['resetQuestionTree', 'reanswerLastQuestionTree'] as const)('clears partial adoption feedback when %s is repeated on an incomplete reanswer', async (action) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      const incomplete = workspace.savedRoute.value!.segments[2]!
      incomplete.normalized_step_name = '钻孔'
      incomplete.source_nodes = ['钻孔']
      workspace.selectedSegmentId.value = 'c'
      workspace.resetQuestionTree()
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.recommendationSummary.value).toContain('已采纳 2 道')
      workspace[action]()
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.completedSegmentCount.value).toBe(2)
    } finally { scope.stop() }
  })

  it.each(['project', 'revision', 'reload'] as const)('removes prior adoption feedback when the current %s changes', async (change) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      if (change === 'project') workspace.projectId.value = 2
      if (change === 'revision') workspace.savedRoute.value!.workflow_revision = 6
      if (change === 'reload') workspace.savedRoute.value = { ...workspace.savedRoute.value! }
      expect(workspace.recommendationSummary.value).toBe('')
    } finally { scope.stop() }
  })

  it.each(['missing review', 'pending review', 'wrong project', 'wrong route', 'wrong segment'] as const)('does not count or apply a save response with %s as successful adoption', async (change) => {
    const { workspace, scope } = createAutosaveWorkspace()
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.saveSegmentRuleReview.mockImplementation(async args => {
      const result = reviewResponse(args)
      if (change === 'missing review') result.rule_review = null as any
      if (change === 'pending review') result.rule_review.decision = 'pending'
      if (change === 'wrong project') result.project_id = 2
      if (change === 'wrong route') result.route_id = 99
      if (change === 'wrong segment') result.segment_id = 'b'
      return result
    })
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.completedSegmentCount.value).toBe(0)
      expect(workspace.error.value).toContain('采纳')
    } finally { scope.stop(); quiet.mockRestore() }
  })

  it.each([0, 1] as const)('reports failure and preserves exactly %i saved items when a batch save rejects', async (savedCount) => {
    const { workspace, scope } = createAutosaveWorkspace()
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.saveSegmentRuleReview.mockImplementation(async args => {
      if (args.segment_id === (savedCount ? 'b' : 'a')) throw new Error('save failed')
      return reviewResponse(args)
    })
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.completedSegmentCount.value).toBe(savedCount)
      expect(workspace.error.value).toContain('失败')
      if (savedCount) expect(workspace.error.value).toContain('1')
    } finally { scope.stop(); quiet.mockRestore() }
  })

  it('leaves stale inherited objects pending while saving other complete recommendations', async () => {
    const { workspace, scope } = createAutosaveWorkspace()
    mocks.saveSegmentRuleReview.mockImplementation(async args => {
      if (args.segment_id === 'b') throw { response: { status: 409, data: { detail: {
        code: 'stale_object_reuse', message: '前序加工对象已变化，请重新确认。',
      } } } }
      return reviewResponse(args)
    })
    try {
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.completedSegmentCount.value).toBe(2)
      expect(workspace.recommendationSummary.value).toContain('已采纳 2 道')
      expect(workspace.recommendationSummary.value).toContain('前序加工对象已变化')
      expect(workspace.savedRoute.value!.segments.find(s => s.id === 'b')!.rule_review).toBeNull()
    } finally { scope.stop() }
  })

  it.each([0, 2] as const)('counts only %i saved recommendations while leaving incomplete targets pending', async (readyCount) => {
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      workspace.savedRoute.value!.segments.forEach((segment, index) => {
        if (index >= readyCount) { segment.normalized_step_name = '钻孔'; segment.source_nodes = ['钻孔'] }
      })
      await workspace.acceptAllRecommendedForAllSegments()
      expect(workspace.completedSegmentCount.value).toBe(readyCount)
      if (readyCount) {
        expect(workspace.recommendationSummary.value).toContain('已采纳 2 道')
        expect(workspace.recommendationSummary.value).toContain('1 道还需')
      } else {
        expect(workspace.recommendationSummary.value).toBe('')
        expect(workspace.error.value).toContain('3 道还需')
      }
    } finally { scope.stop() }
  })

  it.each(['revision', 'unmount', 'generation', 'reset cycle', 'lock cycle'] as const)('does not publish or apply a late batch save after %s invalidates it', async (change) => {
    let finish!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async args => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      const batch = workspace.acceptAllRecommendedForAllSegments()
      await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
      const response = reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0])
      if (change === 'revision') workspace.savedRoute.value!.workflow_revision = 6
      if (change === 'unmount') scope.stop()
      if (change === 'generation') workspace.guidanceGenerating.value = true
      if (change === 'reset cycle') { workspace.resettingWorkflow.value = true; workspace.resettingWorkflow.value = false }
      if (change === 'lock cycle') { workspace.savedRoute.value!.analysis_locked = true; workspace.savedRoute.value!.analysis_locked = false }
      finish(response)
      await batch
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.completedSegmentCount.value).toBe(0)
      expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
    } finally { scope.stop() }
  })

  it('discards a reset response after a different route has replaced the reset target', async () => {
    const { workspace, scope } = createAutosaveWorkspace()
    let finish!: (value: any) => void
    const applied = vi.fn()
    mocks.resetWorkflow.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    try {
      const reset = workspace.resetAllAnalysisAnswers(applied)
      workspace.savedRoute.value = { ...workspace.savedRoute.value!, route_id: 20 }
      finish({ project_id: 1, workflow_revision: 6 })
      expect(await reset).toBe(false)
      expect(applied).not.toHaveBeenCalled()
      expect(workspace.savedRoute.value?.route_id).toBe(20)
      expect(mocks.getSavedNormalizedRoute).not.toHaveBeenCalled()
    } finally { scope.stop() }
  })

  it('does not count a save if its target node was removed while the request was pending', async () => {
    const { workspace, scope } = createAutosaveWorkspace()
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    let finish!: (value: any) => void
    mocks.saveSegmentRuleReview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    try {
      workspace.savedRoute.value!.segments = workspace.savedRoute.value!.segments.slice(0, 1)
      const pending = workspace.acceptAllRecommendedForAllSegments()
      await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
      workspace.savedRoute.value!.segments = []
      finish(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await pending
      expect(workspace.recommendationSummary.value).toBe('')
      expect(workspace.completedSegmentCount.value).toBe(0)
    } finally { scope.stop(); quiet.mockRestore() }
  })

  it('saves completed B and C answers even while the request for A is pending', async () => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      for (const id of ['a', 'b', 'c']) {
        workspace.selectedSegmentId.value = id
        workspace.acceptAllRecommendedQuestionTree()
        await settleAutosave()
      }
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.segment_id)).toEqual(['a'])
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.segment_id)).toEqual(['a', 'b', 'c'])
      for (const [args] of mocks.saveSegmentRuleReview.mock.calls) {
        expect(args.analysis_draft.candidate.configuration.process_id).toBe(`export_${args.segment_id}`)
        expect(args.analysis_draft.candidate.configuration.occurrence).toBe('manual')
      }
      expect(workspace.completedSegmentCount.value).toBe(3)
    } finally {
      scope.stop()
    }
  })

  it.each(['project', 'reset', 'lock', 'unmount'] as const)('discards queued answers after %s invalidates the workspace', async (change) => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      for (const id of ['a', 'b']) {
        workspace.selectedSegmentId.value = id
        workspace.acceptAllRecommendedQuestionTree()
        await settleAutosave()
      }
      if (change === 'project') workspace.projectId.value = 2
      if (change === 'reset') workspace.resettingWorkflow.value = true
      if (change === 'lock') workspace.savedRoute.value!.analysis_locked = true
      if (change === 'unmount') scope.stop()
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
      expect(workspace.savedRoute.value?.segments.some(segment => segment.rule_review)).toBeFalsy()
    } finally {
      scope.stop()
    }
  })

  it('drops a queued answer if its required questions are reset before saving', async () => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      for (const id of ['a', 'b']) {
        workspace.selectedSegmentId.value = id
        workspace.acceptAllRecommendedQuestionTree()
        await settleAutosave()
      }
      workspace.resetQuestionTree()
      await settleAutosave()
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
      expect(workspace.savedRoute.value!.segments[1]!.rule_review).toBeNull()
      expect(workspace.questionTreeCurrentQuestion.value).toBeTruthy()
    } finally {
      scope.stop()
    }
  })

  it('keeps a newer reanswer when an older save for the same segment finishes', async () => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      workspace.selectedSegmentId.value = 'a'
      workspace.acceptAllRecommendedQuestionTree()
      await settleAutosave()
      workspace.resetQuestionTree()
      workspace.chooseQuestionTreeOption({ value: 'mainline', label: '固定安排' })
      await settleAutosave()
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.analysis_draft.candidate.configuration.occurrence)).toEqual(['manual', 'always'])
      expect(workspace.savedRoute.value!.segments[0]!.rule_review?.analysis_draft?.candidate?.configuration.occurrence).toBe('always')
    } finally {
      scope.stop()
    }
  })

  it('finishes the autosave queue before taking over with explicit accept-all', async () => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      workspace.selectedSegmentId.value = 'a'
      workspace.acceptAllRecommendedQuestionTree()
      await settleAutosave()
      const batch = workspace.acceptAllRecommendedForAllSegments()
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.segment_id)).toEqual(['a'])
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await batch
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.segment_id)).toEqual(['a', 'b', 'c'])
      expect(workspace.completedSegmentCount.value).toBe(3)
      expect(workspace.batchAcceptingAll.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it.each(['project', 'reset', 'lock', 'reload', 'unmount'] as const)('cancels batch takeover when %s changes while waiting for autosave', async (change) => {
    let releaseA!: (value: any) => void
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise(resolve => { releaseA = resolve }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      workspace.selectedSegmentId.value = 'a'
      workspace.acceptAllRecommendedQuestionTree()
      await settleAutosave()
      const batch = workspace.acceptAllRecommendedForAllSegments()
      await settleAutosave()
      if (change === 'project') workspace.projectId.value = 2
      if (change === 'reset') workspace.resettingWorkflow.value = true
      if (change === 'lock') workspace.savedRoute.value!.analysis_locked = true
      if (change === 'reload') workspace.savedRoute.value = { ...workspace.savedRoute.value! }
      if (change === 'unmount') scope.stop()
      releaseA(reviewResponse(mocks.saveSegmentRuleReview.mock.calls[0]![0]))
      await batch
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
      expect(workspace.savedRoute.value?.segments.some(segment => segment.rule_review)).toBeFalsy()
      expect(workspace.batchAcceptingAll.value).toBe(false)
    } finally {
      scope.stop()
    }
  })

  it('continues queued answers after a failed request without retrying it in a loop', async () => {
    let failA!: (error: Error) => void
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {})
    mocks.saveSegmentRuleReview.mockImplementation(async (args: any) => reviewResponse(args))
    mocks.saveSegmentRuleReview.mockImplementationOnce(() => new Promise((_resolve, reject) => { failA = reject }))
    const { workspace, scope } = createAutosaveWorkspace()
    try {
      for (const id of ['a', 'b']) {
        workspace.selectedSegmentId.value = id
        workspace.acceptAllRecommendedQuestionTree()
        await settleAutosave()
      }
      failA(new Error('temporary network failure'))
      await settleAutosave()
      expect(mocks.saveSegmentRuleReview.mock.calls.map(([args]) => args.segment_id)).toEqual(['a', 'b'])
      expect(workspace.savedRoute.value!.segments[0]!.rule_review).toBeNull()
      expect(workspace.savedRoute.value!.segments[1]!.rule_review?.decision).toBe('accepted')
      expect(workspace.error.value).toContain('保存规则候选判断失败')
    } finally {
      scope.stop()
      consoleError.mockRestore()
    }
  })

  it('does not adopt recommendations for a finalized route', async () => {
    const workspace = useAnalysisWorkspace()
    workspace.projectId.value = 1
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
    workspace.savedRoute.value = {
      project_id: 1, route_id: 10, workflow_revision: 5, analysis_locked: true,
      segments: [{ id: 'seg-1', normalized_step_name: '钻孔', doc_coverage: { hit_docs: 1, total_docs: 2 } }],
    } as any
    expect(workspace.analysisReadOnly.value).toBe(true)
    await workspace.acceptAllRecommendedForAllSegments()
    expect(mocks.saveSegmentRuleReview).not.toHaveBeenCalled()
    expect(workspace.batchAcceptingAll.value).toBe(false)
  })

  it('reloads a newly locked route when an old batch save is rejected by the server', async () => {
    const segment = {
      id: 'seg-1', normalized_step_name: '标记', source_nodes: ['标记'], source_operation_ids: [],
      matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 }, factor_reviews: [], rule_review: null,
    }
    const route = { project_id: 1, route_id: 10, workflow_revision: 5, segments: [segment] }
    mocks.getSavedNormalizedRoute.mockResolvedValue({ ...route, analysis_locked: true })
    mocks.saveSegmentRuleReview.mockRejectedValueOnce({ response: { status: 409, data: {
      detail: { code: 'analysis_locked', message: '已进入规则定稿' },
    } } })
    const workspace = useAnalysisWorkspace()
    workspace.projectId.value = 1
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
    workspace.savedRoute.value = route as any
    workspace.selectedSegmentId.value = 'seg-1'
    await workspace.acceptAllRecommendedForAllSegments()
    expect(workspace.analysisReadOnly.value).toBe(true)
    expect(workspace.savedRoute.value!.segments[0]!.rule_review).toBeNull()
    expect(workspace.batchAcceptingAll.value).toBe(false)
  })
  beforeEach(() => {
    mocks.saveSegmentRuleReview.mockReset()
    mocks.getSavedNormalizedRoute.mockReset()
    mocks.getSupersetRoute.mockReset()
    mocks.getDocumentOperationDetails.mockReset()
    mocks.listDocuments.mockReset()
    mocks.listOperations.mockReset()
    mocks.listProjects.mockReset()
    mocks.getAnalysisGuidance.mockReset()
    mocks.generateAnalysisGuidance.mockReset()
    mocks.resetWorkflow.mockReset()
    mocks.messageError.mockReset()

    mocks.listProjects.mockResolvedValue([{ id: 1, name: 'Project 1' }])
    mocks.listDocuments.mockResolvedValue([])
    mocks.listOperations.mockResolvedValue([])
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [] })
    mocks.getDocumentOperationDetails.mockResolvedValue({ items: [] })
    mocks.getAnalysisGuidance.mockResolvedValue({ configuration: null })
    mocks.generateAnalysisGuidance.mockResolvedValue({ configuration: null })
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
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
    mocks.generateAnalysisGuidance.mockResolvedValueOnce({ configuration: workspace.analysisGuidance.value })
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
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
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
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
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
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
    workspace.savedRoute.value = { project_id: 1, route_id: 10, workflow_revision: 5, segments: newSegments() } as any
    workspace.selectedSegmentId.value = 'seg-1'
    const pending = workspace.acceptAllRecommendedForAllSegments()
    await vi.waitFor(() => expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1))
    workspace.projectId.value = 2
    workspace.savedRoute.value = { project_id: 2, route_id: 20, workflow_revision: 1, segments: newSegments() } as any
    workspace.projectId.value = 1
    workspace.analysisGuidance.value = { schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: ['周边'], feature_mappings: {}, operation_guidance: { 标记: { recommendation: { mode: 'manual' } } } }
    workspace.savedRoute.value = { project_id: 1, route_id: 10, workflow_revision: 5, segments: newSegments() } as any
    finish({ project_id: 1, route_id: 10, segment_id: 'seg-1', analysis_status: 'reviewed', rule_review: { decision: 'accepted' } })
    await pending

    expect(mocks.saveSegmentRuleReview).toHaveBeenCalledTimes(1)
    expect(workspace.savedRoute.value!.segments.every(segment => !segment.rule_review)).toBe(true)
  })
})
