import { afterEach, expect, it, vi } from 'vitest'
import { computed, effectScope, ref } from 'vue'
import { useAnalysisQuestionTree } from '@/composables/useAnalysisQuestionTree'
import { buildGuidedDraft } from '@/composables/analysisGuidanceFlow'
import { trailWithGuidanceSnapshot } from '@/composables/analysisQuestionTreeState'

afterEach(() => vi.unstubAllGlobals())
const answer = (nodeId: string, value: string, label = value) => ({ nodeId, value, label })

function fixture(extraAnswers: Record<string, ReturnType<typeof answer>> = {}, name = '下料') {
  const entries = new Map<string, string>()
  vi.stubGlobal('window', { localStorage: {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => entries.set(key, value),
    removeItem: (key: string) => entries.delete(key),
  } })
  const config: any = { schema_version: '1.0', revision: 1, guidance: '', materials: ['9Cr18'],
    generation_route_id: 101, directions: ['周边'], feature_mappings: {}, operation_guidance: {
      '__segment__:merged': { recommendation: { mode: 'mainline' } },
    } }
  const segment: any = { id: 'merged', export_process_id: 'p_merged', normalized_step_name: name,
    source_nodes: [name, '备料'], source_operation_names: [name, '备料'], sequence: 1,
    doc_coverage: { hit_docs: 2, total_docs: 2 }, factor_reviews: [], matched_detail_rows: [] }
  const source: any = { id: 'source', export_process_id: 'p_source', normalized_step_name: '镀铜', sequence: 0 }
  const answers = { merge_name_root: answer('merge_name_root', name), guided_mode: answer('guided_mode', 'manual'), ...extraAnswers }
  const savedDraft = buildGuidedDraft(segment, config, answers, [source, segment])!
  segment.rule_review = { decision: 'accepted', note: '', analysis_draft: savedDraft,
    question_trail: trailWithGuidanceSnapshot(Object.values(answers), config) }
  const selected = ref(segment)
  const routeId = ref(101)
  const workflowRevision = ref(1)
  const scope = effectScope()
  const tree = scope.run(() => useAnalysisQuestionTree({ projectId: computed(() => 9001),
    routeId: computed(() => routeId.value),
    workflowRevision: computed(() => workflowRevision.value),
    guidance: computed(() => config), segments: computed(() => [source, selected.value]),
    selectedSegment: computed(() => selected.value), detailRows: computed(() => []),
    selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []),
  }))!
  return { tree, scope, selected, savedDraft, routeId, workflowRevision, config }
}

it('cold reload must preserve the saved manual answer on a fully covered merged node', () => {
  const { tree, scope, selected } = fixture()
  try {
    const reconstructed = tree.getAnalysisDraftForSegment(selected.value)!
    expect(reconstructed.candidate!.configuration!.occurrence).toBe('manual')
  } finally { scope.stop() }
})

it.each([
  ['conditional', '淬火', {
    guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'material'),
    guided_material_scope: answer('guided_material_scope', 'material_scope::grade::9Cr18'),
  }],
  ['associated', '除铜', {
    guided_mode: answer('guided_mode', 'relation'), guided_source: answer('guided_source', 'p_source'),
  }],
] as const)('preserves an explicit saved %s answer over full-coverage defaults', (occurrence, name, answers) => {
  const { tree, scope, selected, savedDraft } = fixture(answers, name)
  try {
    expect(savedDraft.candidate!.configuration!.occurrence).toBe(occurrence)
    expect(tree.getAnalysisDraftForSegment(selected.value)!.candidate).toEqual(savedDraft.candidate)
  } finally { scope.stop() }
})

it('partial coverage keeps the saved answer when live recommendations differ', () => {
  const { tree, scope, selected } = fixture()
  try {
    selected.value.doc_coverage.hit_docs = 1
    expect(tree.getAnalysisDraftForSegment(selected.value)!.candidate!.configuration!.occurrence).toBe('manual')
  } finally { scope.stop() }
})

it('does not reuse local answers when the same project saves a new route with reused segment ids', () => {
  const { tree, scope, selected, routeId, config } = fixture()
  try {
    expect(tree.getAnalysisDraftForSegment(selected.value)!.candidate!.configuration!.occurrence).toBe('manual')
    selected.value = { ...selected.value, rule_review: null, doc_coverage: { hit_docs: 1, total_docs: 2 } }
    config.generation_route_id = 102
    routeId.value = 102
    expect(tree.getTrailForSegment(selected.value).some(item => item.nodeId === 'guided_mode')).toBe(false)
    expect(tree.getAnalysisDraftForSegment(selected.value)).toBeNull()
    expect(tree.questionTreeCurrentQuestion.value!.id).toBe('guided_mode')
  } finally { scope.stop() }
})

it('does not revive answers from before a reset of the same route', () => {
  const { tree, scope, selected, workflowRevision } = fixture()
  try {
    expect(tree.getAnalysisDraftForSegment(selected.value)!.candidate!.configuration!.occurrence).toBe('manual')
    selected.value = { ...selected.value, rule_review: null, doc_coverage: { hit_docs: 1, total_docs: 2 } }
    workflowRevision.value++
    expect(tree.getTrailForSegment(selected.value).some(item => item.nodeId === 'guided_mode')).toBe(false)
    expect(tree.getAnalysisDraftForSegment(selected.value)).toBeNull()
  } finally { scope.stop() }
})

it('reanswer on a fully covered merged node must retain the chosen Bool mode after save acknowledgement', () => {
  const { tree, scope, selected } = fixture()
  try {
    selected.value.rule_review = null
    selected.value.normalized_step_name = '下料/备料'
    tree.resetQuestionTree()
    expect(tree.questionTreeCurrentQuestion.value!.id).toBe('merge_name_root')
    const nameOption = tree.questionTreeCurrentQuestion.value!.options.find(o => o.label === '下料')!
    tree.chooseQuestionTreeOption(nameOption)
    expect(tree.questionTreeCurrentQuestion.value!.id).toBe('guided_mode')
    tree.chooseQuestionTreeOption({ value: 'manual', label: '每次由用户决定是否安排' })
    const before = tree.getAnalysisDraftForSegment(selected.value)!
    const savedTrail = tree.getTrailForSegment(selected.value)
    expect(before.candidate!.configuration!.occurrence).toBe('manual')
    // Same acknowledgement flow as useAnalysisReviewPersistence: apply saved
    // review/name, then clearQuestionTreeRejudging(segment_id).
    selected.value = { ...selected.value, normalized_step_name: '下料', rule_review: {
      decision: 'accepted', note: '', analysis_draft: before, question_trail: savedTrail,
    } }
    tree.clearQuestionTreeRejudging(selected.value.id)
    const after = tree.getAnalysisDraftForSegment(selected.value)!
    expect(after.candidate!.configuration!.occurrence).toBe('manual')
  } finally { scope.stop() }
})

it('two same-name nodes with distinct process identities use independent Bool switches', () => {
  const config: any = { schema_version: '1.0', revision: 1, guidance: '', materials: [],
    directions: [], feature_mappings: {}, operation_guidance: {} }
  const segments: any[] = ['first', 'second'].map((id, i) => ({ id, export_process_id: id,
    normalized_step_name: '检验', sequence: i + 1 }))
  const drafts = segments.map(s => buildGuidedDraft(s, config, { guided_mode: answer('guided_mode', 'manual') }, segments)!)
  expect(drafts[0]!.candidate!.configuration!.when!.field).not.toBe(drafts[1]!.candidate!.configuration!.when!.field)
})
