import { computed, effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { useAnalysisQuestionTree } from './useAnalysisQuestionTree'
import { applyGuidedAnswer, buildGuidedQuestion } from './analysisGuidanceFlow'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'

const answer = (nodeId: string, value: string) => ({ nodeId, value, label: value })
const cfg: AnalysisGuidanceConfiguration = {
  schema_version: '1.0', revision: 4, guidance: '', materials: [],
  directions: ['A侧', 'B侧', '所有方位', '周边'],
  feature_mappings: { 孔: ['通孔', '盲孔'], 外圆: ['外圆柱面'], 平面: ['轴端面'] },
  operation_guidance: {
    磨孔: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'precision', features: ['通孔'], direction: 'A侧', it_threshold: 7 } },
    珩孔: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'precision', it_threshold: 6 } },
    精车: { feature_group: '外圆', recommendation: { mode: 'condition', basis: 'precision', features: ['外圆柱面'], direction: 'B侧', it_threshold: 8 } },
    抛光: { feature_group: '外圆', recommendation: { mode: 'condition', basis: 'roughness', ra_threshold: 0.2 } },
    研面: { feature_group: '平面', recommendation: { mode: 'condition', basis: 'precision', it_threshold: 6 } },
  },
}
const operation = (name: string, index: number): any => ({ id: `s${index}`, export_process_id: `p${index}`,
  normalized_step_name: name, sequence: index, phase: 'finish', source_nodes: [name],
  doc_coverage: { hit_docs: 1, total_docs: 2 }, matched_detail_rows: [], factor_reviews: [], rule_review: null })

afterEach(() => vi.unstubAllGlobals())
function setup(names = ['磨孔', '珩孔', '精车', '抛光'], configuration = structuredClone(cfg)) {
  const entries = new Map<string, string>()
  vi.stubGlobal('window', { localStorage: { getItem: (k: string) => entries.get(k) ?? null,
    setItem: (k: string, v: string) => entries.set(k, v), removeItem: (k: string) => entries.delete(k) } })
  const segments = ref(names.map((name, i) => operation(name, i + 1)))
  const selectedId = ref(segments.value[0]!.id)
  const create = () => useAnalysisQuestionTree({ projectId: computed(() => 9044), routeId: computed(() => 34),
    workflowRevision: computed(() => 3), guidance: computed(() => configuration), segments: computed(() => segments.value),
    selectedSegment: computed(() => segments.value.find(s => s.id === selectedId.value)!), detailRows: computed(() => []),
    selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) })
  const scope = effectScope(), tree = scope.run(create)!
  return { tree, scope, segments, selectedId, entries, create, configuration }
}

describe('confirmed machining objects across different later operations', () => {
  it('asks missing feature, direction, precision type, threshold in that order', () => {
    const s = operation('磨孔', 1)
    let a = { guided_mode: answer('guided_mode', 'condition') }
    for (const [id, value] of [['guided_features', '通孔'], ['guided_direction', 'A侧'], ['guided_basis', 'precision'], ['guided_it', '7']]) {
      expect(buildGuidedQuestion(s, cfg, a, [s])?.id).toBe(id)
      a = applyGuidedAnswer(a, answer(id!, value!)) as typeof a
    }
    expect(buildGuidedQuestion(s, cfg, a, [s])).toBeNull()
  })

  it('keeps a chosen object while switching IT to Ra, clearing only the old threshold', () => {
    const a = Object.fromEntries([['guided_mode', 'condition'], ['guided_features', '通孔'], ['guided_direction', 'A侧'], ['guided_basis', 'precision'], ['guided_it', '7']].map(([id, v]) => [id, answer(id!, v!)]))
    const changed = applyGuidedAnswer(a, answer('guided_basis', 'roughness'))
    expect(changed.guided_features?.value).toBe('通孔')
    expect(changed.guided_direction?.value).toBe('A侧')
    expect(changed.guided_it).toBeUndefined()
    expect(buildGuidedQuestion(operation('磨孔', 1), cfg, changed, [])?.id).toBe('guided_ra')
  })

  it('one click resolves two unrelated operation chains, retaining independent IT and Ra', () => {
    const { tree, segments, scope } = setup()
    try {
      tree.acceptAllRecommendedForAllSegments(segments.value)
      const drafts = segments.value.map(s => tree.getAnalysisDraftForSegment(s))
      expect(drafts.every(Boolean)).toBe(true)
      expect(drafts[1]!.candidate!.configuration!.when!.all).toEqual([
        { field: expect.stringMatching(/\.features$/), op: 'contains_any', value: ['通孔'] },
        { field: expect.stringMatching(/\.direction$/), op: 'eq', value: 'A侧' },
        { field: expect.stringMatching(/\.it$/), op: 'lte', value: 6 },
      ])
      expect(drafts[3]!.candidate!.configuration!.when!.all[2]).toMatchObject({ op: 'lte', value: 0.2 })
      for (const i of [1, 3]) {
        const trail = tree.getTrailForSegment(segments.value[i]!)
        expect(trail.some(a => a.nodeId === 'guided_features' || a.nodeId === 'guided_direction')).toBe(false)
        expect(trail.find(a => a.nodeId === '__object_reuse')).toBeTruthy()
        expect(drafts[i]!.provenance.some(p => p.evidence.includes(segments.value[i - 1]!.id))).toBe(true)
      }
    } finally { scope.stop() }
  })

  it('does not treat unaccepted recommendations or another feature category as confirmed objects', () => {
    const { tree, scope, selectedId, segments } = setup(['磨孔', '珩孔', '研面'])
    try {
      selectedId.value = segments.value[1]!.id
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_features')
      selectedId.value = segments.value[0]!.id
      tree.acceptAllRecommendedQuestionTree()
      selectedId.value = segments.value[2]!.id
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_features')
    } finally { scope.stop() }
  })

  it('reports the actual unanswered recommendation field without committing a partial trial', () => {
    const { tree, scope, segments } = setup(['珩孔'])
    try {
      tree.acceptAllRecommendedForAllSegments(segments.value)
      expect(tree.getAnalysisDraftForSegment(segments.value[0]!)).toBeNull()
      expect(tree.getMissingAnswerForSegment(segments.value[0]!)).toBe('加工特征')
      expect(tree.getTrailForSegment(segments.value[0]!).some(a => a.nodeId === 'guided_mode')).toBe(false)
    } finally { scope.stop() }
  })

  it('does not reuse retained object answers from a rejected source', () => {
    const { tree, scope, segments, selectedId } = setup(['磨孔', '珩孔'])
    try {
      tree.acceptAllRecommendedQuestionTree()
      segments.value[0]!.rule_review = { decision: 'rejected', note: '', question_trail: tree.getTrailForSegment(segments.value[0]!) }
      selectedId.value = segments.value[1]!.id
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_features')
      expect(tree.getTrailForSegment(segments.value[1]!).some(a => a.nodeId === '__object_reuse')).toBe(false)
    } finally { scope.stop() }
  })

  it('reuses a confirmed feature alone and asks only the missing direction', () => {
    const { tree, scope, selectedId, segments } = setup(['磨孔', '珩孔'])
    try {
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      tree.chooseQuestionTreeOptions([{ value: '通孔', label: '通孔' }])
      selectedId.value = segments.value[1]!.id
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_direction')
      expect(tree.questionTreeCurrentQuestion.value?.sourceHint).toContain('磨孔')
    } finally { scope.stop() }
  })

  it('asks precision type directly for an existing object; ambiguous directions still need confirmation', () => {
    const configuration = structuredClone(cfg)
    configuration.operation_guidance['磨孔#1'] = configuration.operation_guidance.磨孔!
    configuration.operation_guidance['磨孔#2'] = { ...configuration.operation_guidance.磨孔!, recommendation: { ...configuration.operation_guidance.磨孔!.recommendation!, direction: 'B侧' } }
    const { tree, scope, selectedId, segments } = setup(['磨孔', '磨孔', '珩孔'], configuration)
    try {
      tree.acceptAllRecommendedQuestionTree()
      selectedId.value = segments.value[2]!.id
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_basis')
      selectedId.value = segments.value[1]!.id
      tree.acceptAllRecommendedQuestionTree()
      selectedId.value = segments.value[2]!.id
      expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_direction')
      expect(tree.getAnalysisDraftForSegment(segments.value[2]!)).toBeNull()
    } finally { scope.stop() }
  })

  it('updates inherited direction after an upstream edit, never retaining a copied answer', () => {
    const { tree, scope, selectedId, segments } = setup(['磨孔', '珩孔'])
    try {
      tree.acceptAllRecommendedForAllSegments(segments.value)
      expect(tree.getAnalysisDraftForSegment(segments.value[1]!)!.condition_text).toContain('A侧')
      selectedId.value = segments.value[0]!.id
      tree.resetQuestionTree()
      tree.chooseQuestionTreeOption({ value: 'condition', label: '条件' })
      tree.chooseQuestionTreeOptions([{ value: '通孔', label: '通孔' }])
      tree.chooseQuestionTreeOption({ value: 'B侧', label: 'B侧' })
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segments.value[1]!)!.condition_text).toContain('B侧')
      expect(tree.getAnalysisDraftForSegment(segments.value[1]!)!.condition_text).toContain('IT6')
    } finally { scope.stop() }
  })

  it('restores inherited objects after a cold reload from the actual saved trail', async () => {
    const fixture = setup(['磨孔', '珩孔'])
    const { tree, segments, scope, entries, create } = fixture
    tree.acceptAllRecommendedForAllSegments(segments.value)
    const drafts = segments.value.map(s => tree.getAnalysisDraftForSegment(s))
    segments.value = segments.value.map((s, i) => ({ ...s, rule_review: { decision: 'accepted',
      question_trail: tree.getTrailForSegment(s), analysis_draft: drafts[i], note: '' } }))
    await nextTick()
    scope.stop()
    entries.clear()
    const second = effectScope()
    try {
      const restored = second.run(create)!
      expect(restored.getAnalysisDraftForSegment(segments.value[1]!)).toEqual(drafts[1])
    } finally { second.stop() }
  })
})
