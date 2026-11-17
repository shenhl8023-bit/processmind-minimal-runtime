import { computed, effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import type { SavedNormalizedRouteSegment } from '@/api/extract'
import type { TreeAnswer } from './analysisQuestionTreeState'
import { useAnalysisQuestionTree } from './useAnalysisQuestionTree'

const answer = (nodeId: string, value: string, label = value): TreeAnswer => ({ nodeId, value, label })
const oldGuide = (): AnalysisGuidanceConfiguration => ({
  schema_version: '1.0', revision: 4, generation_version: 'old-contract-hash',
  generation_route_id: 34, generation_operation_ids: { 磨孔: 'p1' },
  guidance: '项目已确认的指导', materials: ['9Cr18'],
  directions: ['A侧', 'B侧', '所有方位', '周边'],
  feature_mappings: { '孔/内孔': ['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面'], 外圆: ['外圆柱面'] },
  operation_guidance: { 磨孔: {
    feature_group: '孔/内孔', instruction: '冻结时的指导',
    questions: { guided_features: { prompt: '冻结时的特征问题' } },
    recommendation: { mode: 'condition', basis: 'precision', it_threshold: 7, ra_threshold: 0.8 },
  } },
})

function completedGuide(frozen: AnalysisGuidanceConfiguration) {
  const source = structuredClone(frozen)
  Object.assign(source.operation_guidance.磨孔!.recommendation!, { features: ['内圆柱面'], direction: '所有方位' })
  return source
}

function setup(frozen = oldGuide(), source = completedGuide(frozen), answers = [answer('guided_mode', 'condition', '原条件回答')], saved = false,
  prior: SavedNormalizedRouteSegment[] = []) {
  const snapshot = structuredClone(frozen)
  snapshot.operation_guidance['__segment__:s1'] = structuredClone(snapshot.operation_guidance.磨孔!)
  const entries = new Map<string, string>()
  vi.stubGlobal('window', { localStorage: {
    getItem: (key: string) => entries.get(key) ?? null,
    setItem: (key: string, value: string) => entries.set(key, value),
    removeItem: (key: string) => entries.delete(key),
  } })
  const segment = ref<SavedNormalizedRouteSegment>({
    id: 's1', export_process_id: 'p1', normalized_step_name: '磨孔', sequence: 1,
    phase: 'finish', source_nodes: ['磨孔'], matched_detail_rows: [], factor_reviews: [],
    step_family: '孔', parent_segment: '', source_type: 'original', source_operation_ids: [],
    doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5, label: '1/2' }, rule_review: null,
    detail_coverage: { matched_rows: 0 }, evidence_excerpt: [], analysis_status: 'pending',
    equipment_profile: { split_applied: false, equipment_types: [], equipment_models: [] },
  })
  const snapshotText = JSON.stringify(snapshot)
  if (saved) {
    segment.value.rule_review = { decision: 'pending', note: '原备注', analysis_draft: null,
      question_trail: [...answers, answer('__guidance_snapshot', snapshotText, '原冻结版本')],
      id: 1, summary_lines: [], created_at: '', updated_at: '' }
  } else {
    entries.set('processmind_analysis_question_tree_v10_9066', JSON.stringify({ s1: {
      answers: Object.fromEntries(answers.map(item => [item.nodeId, item])), note: '原备注', guidanceSnapshot: snapshot,
    } }))
  }
  const guidance = ref(source)
  const scope = effectScope()
  const tree = scope.run(() => useAnalysisQuestionTree({
    projectId: computed(() => 9066), guidance: computed(() => guidance.value),
    segments: computed(() => [...prior, segment.value]), selectedSegment: computed(() => segment.value),
    detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
    matchedDocumentTexts: computed(() => []),
  }))!
  return { tree, scope, segment, entries, snapshot, snapshotText, guidance }
}

afterEach(() => vi.unstubAllGlobals())

describe('missing object recommendations in unfinished frozen drafts', () => {
  it.each([false, true])('completes a response-only supplement and preserves the frozen snapshot (saved=%s)', async saved => {
    const frozen = oldGuide(), source = completedGuide(frozen)
    const { tree, scope, segment, entries, snapshotText } = setup(frozen, source, undefined, saved)
    const sourceText = JSON.stringify(source)
    try {
      expect(tree.questionTreeCurrentQuestion.value).toMatchObject({ id: 'guided_features', prompt: '冻结时的特征问题', recommendedValues: ['内圆柱面'] })
      expect(tree.questionTreeTrail.value).toEqual([answer('guided_mode', 'condition', '原条件回答')])
      tree.acceptAllRecommendedForAllSegments([segment.value])
      expect(tree.getAnalysisDraftForSegment(segment.value)?.candidate?.configuration.when).toMatchObject({ all: [
        { value: ['内圆柱面'] }, { any: [{ value: 'A侧' }, { value: 'B侧' }] }, { value: 7 },
      ] })
      expect(tree.getGuidanceForSegment(segment.value)?.generation_version).toBe('old-contract-hash')
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
      expect(tree.questionTreeNoteDraft.value).toBe('原备注')
      await nextTick()
      expect(JSON.stringify(JSON.parse(entries.get('processmind_analysis_question_tree_v10_9066')!).s1.guidanceSnapshot)).toBe(snapshotText)
      expect(JSON.stringify(source)).toBe(sourceText)
    } finally { scope.stop() }
  })

  it('adapts a new contract only with stable route/operation identity and otherwise unchanged configuration', () => {
    const frozen = oldGuide(), source = completedGuide(frozen)
    source.generation_version = 'new-contract-hash'
    source.revision = 5
    const { tree, scope, segment, snapshotText } = setup(frozen, source)
    try {
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toBeTruthy()
      expect(tree.getGuidanceForSegment(segment.value)).toMatchObject({ revision: 4, generation_version: 'old-contract-hash' })
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
    } finally { scope.stop() }
  })

  it('supports a legacy response projection without generation metadata only when the rest of the configuration is identical', () => {
    const frozen = oldGuide()
    delete frozen.generation_version
    delete frozen.generation_route_id
    delete frozen.generation_operation_ids
    const { tree, scope, segment } = setup(frozen)
    try {
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toBeTruthy()
    } finally { scope.stop() }
  })

  it.each(['precision', 'roughness'] as const)('keeps existing %s answers and frozen thresholds when adding earlier object questions', basis => {
    const frozen = oldGuide()
    frozen.operation_guidance.磨孔!.recommendation!.basis = basis
    const source = completedGuide(frozen)
    source.operation_guidance.磨孔!.recommendation!.it_threshold = 6
    source.operation_guidance.磨孔!.recommendation!.ra_threshold = 0.2
    const threshold = answer(basis === 'precision' ? 'guided_it' : 'guided_ra', basis === 'precision' ? '5' : '0.4', '原手动阈值')
    const existing = [answer('guided_mode', 'condition', '原条件回答'), answer('guided_basis', basis, '原依据'), threshold]
    const { tree, scope, segment, snapshotText } = setup(frozen, source, existing)
    try {
      const projected = tree.getGuidanceForSegment(segment.value)!
      expect(projected.operation_guidance.磨孔!.recommendation).toMatchObject({ it_threshold: 7, ra_threshold: 0.8 })
      expect(tree.questionTreeTrail.value).toEqual(existing)
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)?.candidate?.configuration.when).toMatchObject({ all: [
        { value: ['内圆柱面'] }, { any: [{ value: 'A侧' }, { value: 'B侧' }] }, { value: basis === 'precision' ? 5 : 0.4 },
      ] })
      for (const item of existing) expect(tree.questionTreeTrail.value).toContainEqual(item)
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
    } finally { scope.stop() }
  })

  it('fills only a missing direction and does not overwrite an existing feature recommendation', () => {
    const frozen = oldGuide()
    frozen.operation_guidance.磨孔!.recommendation!.features = ['内圆柱面']
    const { tree, scope, segment } = setup(frozen)
    try {
      expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance.磨孔!.recommendation).toMatchObject({ features: ['内圆柱面'], direction: '所有方位' })
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toBeTruthy()
    } finally { scope.stop() }
  })

  it('preserves an already answered direction and threshold when supplementing the missing feature', () => {
    const existing = [answer('guided_mode', 'condition'), answer('guided_direction', 'B侧', '原方位'),
      answer('guided_basis', 'precision'), answer('guided_it', '5', '原阈值')]
    const { tree, scope, segment } = setup(undefined, undefined, existing)
    try {
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)?.candidate?.configuration.when).toMatchObject({ all: [
        { value: ['内圆柱面'] }, { value: 'B侧' }, { value: 5 },
      ] })
      for (const item of existing) expect(tree.questionTreeTrail.value).toContainEqual(item)
    } finally { scope.stop() }
  })

  const incompatible: Array<[string, (frozen: AnalysisGuidanceConfiguration, source: AnalysisGuidanceConfiguration) => void]> = [
    ['blocked frozen operation', frozen => { frozen.operation_guidance.磨孔!.recommendation_reference_blocked = true }],
    ['blocked reference', (_, source) => { source.operation_guidance.磨孔!.recommendation_reference_blocked = true }],
    ['another group', (_, source) => { source.operation_guidance.磨孔!.feature_group = '外圆'; source.operation_guidance.磨孔!.recommendation!.features = ['外圆柱面'] }],
    ['outside frozen candidates', (_, source) => { source.feature_mappings['孔/内孔']!.push('自定义孔'); source.operation_guidance.磨孔!.recommendation!.features = ['自定义孔'] }],
    ['outside frozen directions', (_, source) => { source.directions.push('自定义方位'); source.operation_guidance.磨孔!.recommendation!.direction = '自定义方位' }],
    ['another route', (_, source) => { source.generation_route_id = 35 }],
    ['another stable operation', (_, source) => { source.generation_operation_ids = { 磨孔: 'another' } }],
    ['another occurrence', (_, source) => { source.operation_guidance = { '磨孔#2': source.operation_guidance.磨孔! }; source.generation_operation_ids = { '磨孔#2': 'p2' } }],
    ['changed revision in same generation', (_, source) => { source.revision++ }],
    ['cross-generation without stable identity', (frozen, source) => { delete frozen.generation_operation_ids; delete source.generation_operation_ids; source.generation_version = 'future' }],
    ['cross-generation changed guidance', (_, source) => { source.generation_version = 'future'; source.guidance = '后来改的加工指导' }],
    ['cross-generation changed thresholds', (_, source) => { source.generation_version = 'future'; source.operation_guidance.磨孔!.recommendation!.it_threshold = 9 }],
    ['cross-generation changed operation text', (_, source) => { source.generation_version = 'future'; source.operation_guidance.磨孔!.instruction = '后来改的工序配置' }],
    ['non-condition reference', (_, source) => { source.operation_guidance.磨孔!.recommendation = { mode: 'manual' } }],
  ]
  it.each(incompatible)('does not supplement from %s', (_, change) => {
    const frozen = oldGuide(), source = completedGuide(frozen)
    change(frozen, source)
    const { tree, scope, segment, snapshotText } = setup(frozen, source)
    try {
      expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance.磨孔!.recommendation?.features).toBeUndefined()
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
      expect(tree.questionTreeTrail.value).toEqual([answer('guided_mode', 'condition', '原条件回答')])
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
    } finally { scope.stop() }
  })

  it('does not combine a different existing feature recommendation with the source direction', () => {
    const frozen = oldGuide(), source = completedGuide(frozen)
    frozen.operation_guidance.磨孔!.recommendation!.features = ['孔(通孔)']
    const { tree, scope, segment } = setup(frozen, source)
    try {
      expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance.磨孔!.recommendation).toMatchObject({ features: ['孔(通孔)'] })
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
      expect(tree.questionTreeTrail.value).toEqual([answer('guided_mode', 'condition', '原条件回答')])
    } finally { scope.stop() }
  })

  it('leaves a completed frozen draft and its manually chosen object unchanged', () => {
    const existing = [answer('guided_mode', 'condition'), answer('guided_features', '孔(通孔)'),
      answer('guided_direction', 'B侧'), answer('guided_basis', 'precision'), answer('guided_it', '5')]
    const { tree, scope, segment, snapshotText } = setup(undefined, undefined, existing)
    try {
      const draft = tree.getAnalysisDraftForSegment(segment.value)
      expect(draft?.candidate?.configuration.when).toMatchObject({ all: [{ value: ['孔(通孔)'] }, { value: 'B侧' }, { value: 5 }] })
      expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance.磨孔!.recommendation?.features).toBeUndefined()
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.getAnalysisDraftForSegment(segment.value)).toEqual(draft)
      expect(tree.questionTreeTrail.value).toEqual(existing)
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
    } finally { scope.stop() }
  })

  it('leaves a frozen draft already completed through confirmed object reuse unchanged', () => {
    const frozen = oldGuide()
    frozen.operation_guidance.钻孔 = { feature_group: '孔/内孔', recommendation: {
      mode: 'condition', basis: 'feature', features: ['孔(通孔)'], direction: 'B侧',
    } }
    const prior = { id: 's0', export_process_id: 'p0', normalized_step_name: '钻孔', sequence: 0,
      phase: 'rough', source_nodes: ['钻孔'], doc_coverage: { hit_docs: 1, total_docs: 2 },
      rule_review: { decision: 'accepted', question_trail: [answer('guided_mode', 'condition'),
        answer('guided_features', '孔(通孔)'), answer('guided_direction', 'B侧'), answer('guided_basis', 'feature'),
        answer('__guidance_snapshot', JSON.stringify(frozen))] },
    } as SavedNormalizedRouteSegment
    const existing = [answer('guided_mode', 'condition'), answer('guided_basis', 'precision'), answer('guided_it', '5')]
    const { tree, scope, segment, snapshotText } = setup(frozen, undefined, existing, false, [prior])
    try {
      expect(tree.getAnalysisDraftForSegment(segment.value)?.candidate?.configuration.when).toMatchObject({ all: [
        { value: ['孔(通孔)'] }, { value: 'B侧' }, { value: 5 },
      ] })
      expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance.磨孔!.recommendation?.features).toBeUndefined()
      tree.acceptAllRecommendedQuestionTree()
      expect(tree.questionTreeTrail.value).toEqual(existing)
      expect(tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')?.value).toBe(snapshotText)
    } finally { scope.stop() }
  })
})
