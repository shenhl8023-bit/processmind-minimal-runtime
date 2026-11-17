import { computed, effectScope, nextTick, ref } from 'vue'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { useAnalysisQuestionTree } from './useAnalysisQuestionTree'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'

describe('fix1 frozen guidance recovery', () => {
  afterEach(() => vi.unstubAllGlobals())

  function fixture(name = '铣扁/割扁', namesake = false) {
    const entries = new Map<string, string>()
    vi.stubGlobal('window', { localStorage: {
      getItem: (key: string) => entries.get(key) ?? null,
      setItem: (key: string, value: string) => entries.set(key, value),
      removeItem: (key: string) => entries.delete(key),
    } })
    const segment = ref<any>({ id: 'merged', export_process_id: 'p_merged', normalized_step_name: name,
      sequence: 1, source_nodes: ['铣扁', '割扁'], matched_detail_rows: [],
      doc_coverage: { hit_docs: 1, total_docs: 2 }, rule_review: null })
    const guidance = ref<AnalysisGuidanceConfiguration>({ schema_version: '1.0', revision: 1,
      generation_version: 'old', guidance: '', materials: [], directions: ['周边'],
      feature_mappings: { 扁位: ['旧扁位'], 孔: ['别的孔'] }, operation_guidance: {
        [name]: { feature_group: '扁位', questions: { guided_mode: { prompt: '原节点怎么安排？' } },
          recommendation: { mode: 'condition', basis: 'feature', features: ['旧扁位'], direction: '周边' } },
        ...(!namesake ? {} : { 铣扁: { feature_group: '孔', recommendation: { mode: 'manual' as const } } }),
      } })
    const create = () => useAnalysisQuestionTree({ projectId: computed(() => 81),
      guidance: computed(() => guidance.value), segments: computed(() => [segment.value]),
      selectedSegment: computed(() => segment.value), detailRows: computed(() => []),
      selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []),
    })
    return { entries, segment, guidance, create }
  }

  describe('fix2 legacy frozen identity', () => {
    function legacyFixture(sourceNames = ['铣扁', '割扁']) {
      const setup = fixture()
      const snapshot: AnalysisGuidanceConfiguration = {
        ...setup.guidance.value, feature_mappings: { 扁位: ['旧扁位1'], 槽: ['旧槽1'], 孔: ['孔1'] },
        operation_guidance: {
          '铣扁/割扁#1': { feature_group: '扁位', recommendation: { mode: 'condition', basis: 'feature', features: ['旧扁位1'], direction: '周边' } },
          '铣扁/割扁#2': { feature_group: '槽', recommendation: { mode: 'condition', basis: 'feature', features: ['旧槽1'], direction: '周边' } },
          铣扁: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'feature', features: ['孔1'], direction: '周边' } },
        },
      }
      const answers = [
        { nodeId: 'merge_name_root', value: '铣扁', label: '铣扁' },
        { nodeId: 'guided_mode', value: 'condition', label: '看具体加工条件来定' },
        { nodeId: 'guided_basis', value: 'feature', label: '看加工特征和方位' },
        { nodeId: 'guided_features', value: '旧槽1', label: '旧槽1' },
        { nodeId: 'guided_direction', value: '周边', label: '周边' },
      ]
      const savedDraft = {
        scope: '当前工序：铣扁', object: '旧槽1', condition_text: '同一加工对象具有旧槽1且位于周边时安排铣扁。',
        candidate: { kind: 'process_configuration', configuration: {
          process_id: 'p_merged', occurrence: 'conditional', relations: [],
          when: { all: [
            { field: 'project_factor.old.features', op: 'contains_any', value: ['旧槽1'] },
            { field: 'project_factor.old.direction', op: 'eq', value: '周边' },
          ] },
        }, preview: '原来已保存的槽规则', field_definitions: [
          { key: 'project_factor.old.features', label: '原特征', type: 'multi_select', category: '原加工对象', operators: ['contains_any'], aliases: [], required: false, source: '原问答', options: [{ value: '旧槽1', label: '旧槽1' }], allow_custom: false },
          { key: 'project_factor.old.direction', label: '原方位', type: 'single_select', category: '原加工对象', operators: ['eq'], aliases: [], required: false, source: '原问答', options: [{ value: '周边', label: '周边' }], allow_custom: false },
        ] }, missing: [], provenance: [{ kind: 'user', label: '第三步确认', evidence: '旧问答版本' }], status: 'confirmed',
      }
      const saveSnapshot = () => {
        setup.segment.value.rule_review.question_trail = [...answers, {
          nodeId: '__guidance_snapshot', value: JSON.stringify(snapshot), label: '保存版本',
        }]
      }
      setup.segment.value = { ...setup.segment.value, sequence: 2, normalized_step_name: '铣扁',
        source_nodes: sourceNames, source_operation_names: sourceNames,
        rule_review: { decision: 'accepted', note: '保存的备注', analysis_draft: savedDraft, question_trail: [] },
      }
      saveSnapshot()
      setup.guidance.value = { ...snapshot, generation_version: 'new', directions: ['A侧'] }
      return { ...setup, snapshot, answers, saveSnapshot }
    }

    it.each(['ambiguous', 'missing'])('refuses a namesake on cold recovery with %s original sources', source => {
      const { segment, create, answers } = legacyFixture(source === 'missing' ? [] : undefined)
      const saved = JSON.stringify(segment.value.rule_review)
      const scope = effectScope()
      try {
        const tree = scope.run(create)!
        expect(tree.getGuidanceForSegment(segment.value)).toBeNull()
        expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
        expect(tree.questionTreeTrail.value).toEqual(answers)
        expect(tree.questionTreeEmptyReason.value).toContain('无法唯一恢复')
        expect(JSON.stringify(segment.value.rule_review)).toBe(saved)
        const metadata = tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')!
        expect(JSON.parse(metadata.value).operation_guidance['__segment__:merged']).toBeUndefined()
      } finally { scope.stop() }
    })

    it.each(['reanswerLastQuestionTree', 'resetQuestionTree'] as const)('preserves frozen local answers and saved drafts when %s cannot recover identity', async action => {
      const { entries, segment, snapshot, answers, create } = legacyFixture()
      const localAnswers = answers.slice(0, -1)
      entries.set('processmind_analysis_question_tree_v10_81', JSON.stringify({ merged: {
        answers: Object.fromEntries(localAnswers.map(answer => [answer.nodeId, answer])),
        note: '尚未保存的本地备注', guidanceSnapshot: snapshot,
      } }))
      const saved = JSON.stringify(segment.value.rule_review)
      const first = effectScope()
      try {
        const tree = first.run(create)!
        tree[action]()
        tree.acceptAllRecommendedQuestionTree()
        tree.chooseQuestionTreeOption({ value: 'manual', label: '不能借用其它工序重新回答' })
        expect(tree.questionTreeTrail.value).toEqual(localAnswers)
        expect(tree.questionTreeNoteDraft.value).toBe('尚未保存的本地备注')
        expect(tree.questionTreeIsRejudging.value).toBe(false)
        expect(tree.questionTreeCurrentQuestion.value).toMatchObject({ options: [], prompt: expect.stringContaining('无法唯一恢复') })
        expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
        expect(JSON.stringify(segment.value.rule_review)).toBe(saved)
        await nextTick()
      } finally { first.stop() }
      const second = effectScope()
      try {
        const reloaded = second.run(create)!
        expect(reloaded.getGuidanceForSegment(segment.value)).toBeNull()
        expect(reloaded.questionTreeTrail.value).toEqual(localAnswers)
        expect(reloaded.questionTreeNoteDraft.value).toBe('尚未保存的本地备注')
        expect(JSON.stringify(segment.value.rule_review)).toBe(saved)
      } finally { second.stop() }
    })

    it('blocks new conversion when original sources and an existing draft are both absent', () => {
      const { segment, create, answers } = legacyFixture([])
      segment.value.rule_review.analysis_draft = null
      const scope = effectScope()
      try {
        const tree = scope.run(create)!
        tree.reanswerLastQuestionTree()
        tree.acceptAllRecommendedQuestionTree()
        expect(tree.questionTreeCurrentQuestion.value).toMatchObject({ options: [], prompt: expect.stringContaining('无法唯一恢复') })
        expect(tree.questionTreeTrail.value).toEqual(answers)
        expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
        expect(segment.value.rule_review.analysis_draft).toBeNull()
      } finally { scope.stop() }
    })

    it.each([false, true])('recovers an explicit original indexed identity, preferring stable binding=%s', stable => {
      const { segment, snapshot, saveSnapshot, create } = legacyFixture()
      segment.value.source_nodes = ['铣扁/割扁#2']
      if (stable) {
        snapshot.operation_guidance['__segment__:merged'] = snapshot.operation_guidance['铣扁/割扁#2']!
        segment.value.source_nodes = ['铣扁/割扁#1']
        segment.value.source_operation_names = []
      }
      saveSnapshot()
      const scope = effectScope()
      try {
        const tree = scope.run(create)!
        expect(tree.getGuidanceForSegment(segment.value)?.operation_guidance['铣扁']?.feature_group).toBe('槽')
        expect(tree.getAnalysisDraftForSegment(segment.value)?.candidate?.configuration.when.all[0].value).toEqual(['旧槽1'])
        tree.reanswerLastQuestionTree()
        expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_direction')
        expect(tree.questionTreeCurrentQuestion.value?.options.map(option => option.value)).toEqual(['周边'])
        const metadata = tree.getTrailForSegment(segment.value).find(item => item.nodeId === '__guidance_snapshot')!
        expect(JSON.parse(metadata.value).operation_guidance['__segment__:merged'].feature_group).toBe('槽')
      } finally { scope.stop() }
    })

    it('allows an unstarted node to resolve its current name without a frozen identity', () => {
      const { segment, create } = legacyFixture([])
      segment.value.rule_review = null
      const scope = effectScope()
      try {
        const tree = scope.run(create)!
        expect(tree.getGuidanceForSegment(segment.value)?.generation_version).toBe('new')
        tree.chooseQuestionTreeOption({ value: 'condition', label: '看具体加工条件来定' })
        tree.chooseQuestionTreeOption({ value: 'feature', label: '看加工特征和方位' })
        expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_features')
        expect(tree.questionTreeCurrentQuestion.value?.options.map(option => option.value)).toEqual(['孔1'])
      } finally { scope.stop() }
    })
  })

  it.each([[false, false], [true, false], [false, true], [true, true]])('keeps merged guidance after naming and cold reload (namesake: %s, legacy snapshot: %s)', (namesake, legacy) => {
    const { entries, segment, guidance, create } = fixture('铣扁/割扁', namesake)
    const first = effectScope()
    const tree = first.run(create)!
    tree.chooseQuestionTreeOption({ value: '铣扁', label: '铣扁' })
    tree.acceptAllRecommendedQuestionTree()
    const draft = tree.getAnalysisDraftForSegment(segment.value)
    expect(draft?.candidate?.configuration.when).toMatchObject({ all: [
      { op: 'contains_any', value: ['旧扁位'] }, { op: 'eq', value: '周边' },
    ] })
    const saved = tree.getTrailForSegment(segment.value)
    if (legacy) {
      const metadata = saved.find(answer => answer.nodeId === '__guidance_snapshot')!
      const old = JSON.parse(metadata.value) as AnalysisGuidanceConfiguration
      for (const key of Object.keys(old.operation_guidance)) if (key.startsWith('__segment__:')) delete old.operation_guidance[key]
      metadata.value = JSON.stringify(old)
    }
    segment.value = { ...segment.value, normalized_step_name: '铣扁',
      rule_review: { decision: 'accepted', question_trail: saved, analysis_draft: draft } }
    first.stop()
    entries.clear()
    guidance.value = { ...guidance.value, generation_version: 'new', directions: ['A侧'], feature_mappings: { 扁位: ['新扁位'] } }
    const second = effectScope()
    const restored = second.run(create)!
    expect(restored.getGuidanceForSegment(segment.value)?.generation_version).toBe('old')
    expect(restored.getAnalysisDraftForSegment(segment.value)).toEqual(draft)
    restored.reanswerLastQuestionTree()
    expect(restored.questionTreeCurrentQuestion.value?.options.map(option => option.value)).toEqual(['周边'])
    second.stop()
  })

  it.each([false, true])('restores server answers over local state without definitions (local answers: %s)', localAnswers => {
    const { entries, segment, guidance, create } = fixture('铣扁')
    const first = effectScope()
    const tree = first.run(create)!
    tree.acceptAllRecommendedQuestionTree()
    const draft = tree.getAnalysisDraftForSegment(segment.value)
    expect(draft).toBeTruthy()
    segment.value = { ...segment.value, rule_review: { decision: 'accepted',
      question_trail: tree.getTrailForSegment(segment.value), analysis_draft: draft } }
    first.stop()
    entries.set('processmind_analysis_question_tree_v10_81', JSON.stringify({ merged: {
      answers: localAnswers ? { guided_mode: { nodeId: 'guided_mode', value: 'manual', label: '无定义的旧回答' } } : {}, note: '',
    } }))
    guidance.value = { ...guidance.value, generation_version: 'new', feature_mappings: { 扁位: ['新扁位'] }, directions: ['A侧'] }
    const second = effectScope()
    const restored = second.run(create)!
    expect(restored.getGuidanceForSegment(segment.value)?.generation_version).toBe('old')
    expect(restored.getAnalysisDraftForSegment(segment.value)).toEqual(draft)
    expect(restored.questionTreeTrail.value.map(answer => answer.nodeId)).toEqual(['guided_mode', 'guided_basis', 'guided_features', 'guided_direction'])
    second.stop()
  })

  it('preserves a frozen unfinished local answer over a saved server answer and does not undo an explicit reset', async () => {
    const { entries, segment, guidance, create } = fixture('铣扁')
    const savedGuidance = JSON.parse(JSON.stringify(guidance.value)) as AnalysisGuidanceConfiguration
    const localGuidance = { ...savedGuidance, generation_version: 'local', feature_mappings: { 扁位: ['本地扁位'] } }
    const localAnswer = { nodeId: 'guided_mode', value: 'condition', label: '本地条件回答' }
    entries.set('processmind_analysis_question_tree_v10_81', JSON.stringify({ merged: {
      answers: { guided_mode: localAnswer }, note: '未保存备注', guidanceSnapshot: localGuidance,
    } }))
    segment.value.rule_review = { decision: 'accepted', question_trail: [
      { nodeId: 'guided_mode', value: 'manual', label: '服务器回答' },
      { nodeId: '__guidance_snapshot', value: JSON.stringify(savedGuidance), label: '保存版本' },
    ] }
    const scope = effectScope()
    const tree = scope.run(create)!
    expect(tree.questionTreeTrail.value).toEqual([localAnswer])
    expect(tree.getGuidanceForSegment(segment.value)?.generation_version).toBe('local')
    expect(tree.questionTreeNoteDraft.value).toBe('未保存备注')
    tree.resetQuestionTree()
    expect(tree.questionTreeTrail.value).toEqual([])
    await nextTick()
    scope.stop()
  })
})

describe('configured recommendation integration', () => {
  it('freezes the complete guidance on first answer and keeps it in the saved trail', () => {
    const segment = ref<any>({ id: 'd', export_process_id: 'p_d', normalized_step_name: '钻孔', sequence: 1, source_nodes: [], doc_coverage: { hit_docs: 1, total_docs: 2 }, rule_review: null })
    const guidance = ref<any>({ schema_version: '1.0', revision: 1, generation_version: 'old', guidance: '', materials: [], directions: ['周边'], feature_mappings: { 孔: ['旧孔'] }, operation_guidance: { 钻孔: { feature_group: '孔', questions: { guided_mode: { prompt: '这类零件，钻孔这一步你一般怎么安排？', option_labels: { condition: '看孔的情况来安排' } } }, recommendation: { mode: 'condition', basis: 'feature', features: ['旧孔'], direction: '周边' } } } })
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({ guidance: computed(() => guidance.value), segments: computed(() => [segment.value]), selectedSegment: computed(() => segment.value), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) }))!
    expect(tree.questionTreeCurrentQuestion.value?.prompt).toContain('你一般怎么安排')
    tree.chooseQuestionTreeOption({ value: 'condition', label: '看孔的情况来安排' })
    guidance.value = { ...guidance.value, revision: 2, generation_version: 'new', feature_mappings: { 孔: ['新孔'] }, directions: ['A侧'] }
    tree.acceptAllRecommendedQuestionTree()
    const draft = tree.getAnalysisDraftForSegment(segment.value)!
    expect(draft.candidate?.configuration.when.all[0].value).toEqual(['旧孔'])
    expect(draft.candidate?.configuration.when.all[1].value).toBe('周边')
    const saved = tree.getTrailForSegment(segment.value)
    expect(saved.some(item => item.nodeId === '__guidance_snapshot')).toBe(true)
    expect(tree.questionTreeTrail.value.some(item => item.nodeId === '__guidance_snapshot')).toBe(false)
    segment.value = { ...segment.value, rule_review: { decision: 'accepted', question_trail: saved, analysis_draft: draft } }
    scope.stop()
    const reloadedScope = effectScope()
    const reloaded = reloadedScope.run(() => useAnalysisQuestionTree({ guidance: computed(() => guidance.value), segments: computed(() => [segment.value]), selectedSegment: computed(() => segment.value), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) }))!
    expect(reloaded.getAnalysisDraftForSegment(segment.value)).toEqual(draft)
    reloadedScope.stop()
  })

  it('does not partially apply a recommendation whose last answer is missing', () => {
    const segment = ref<any>({ id: 'd', normalized_step_name: '钻孔', sequence: 1, source_nodes: [], doc_coverage: { hit_docs: 1, total_docs: 2 }, rule_review: null })
    const configuration: AnalysisGuidanceConfiguration = { schema_version: '1.0', revision: 1, guidance: '', materials: [], directions: ['周边'], feature_mappings: { 孔: ['孔'] }, operation_guidance: { 钻孔: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'feature', features: ['孔'] } } } }
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({ guidance: computed(() => configuration), segments: computed(() => [segment.value]), selectedSegment: computed(() => segment.value), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) }))!
    tree.acceptAllRecommendedQuestionTree()
    expect(tree.questionTreeTrail.value).toEqual([])
    expect(tree.getAnalysisDraftForSegment(segment.value)).toBeNull()
    scope.stop()
  })

  it('keeps a fully covered route complete without requiring an artificial guided answer', () => {
    const selected = ref<any>({ id: 'all', normalized_step_name: '下料备料', source_nodes: ['下料备料'], doc_coverage: { hit_docs: 2, total_docs: 2 }, rule_review: null })
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({ guidance: computed(() => ({ schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: [], feature_mappings: {}, operation_guidance: {} })), selectedSegment: computed(() => selected.value), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) }))!
    expect(tree.questionTreeCurrentQuestion.value).toBeNull()
    expect(tree.getAnalysisDraftForSegment(selected.value)).toBeUndefined()
    scope.stop()
  })
  it('keeps a fully covered merged node mainline after confirming its unified name', () => {
    const selected = ref<any>({ id: 'merged', export_process_id: 'p_merged', normalized_step_name: '下料/备料', source_nodes: ['下料', '备料'], doc_coverage: { hit_docs: 2, total_docs: 2 }, rule_review: null })
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({ guidance: computed(() => ({ schema_version: '1.0', revision: 0, guidance: '', materials: [], directions: [], feature_mappings: {}, operation_guidance: {} })), selectedSegment: computed(() => selected.value), segments: computed(() => [selected.value]), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []) }))!
    expect(tree.questionTreeCurrentQuestion.value?.id).toBe('merge_name_root')
    tree.chooseQuestionTreeOption(tree.questionTreeCurrentQuestion.value!.options[0]!)
    expect(tree.questionTreeCurrentQuestion.value).toBeNull()
    expect(tree.getAnalysisDraftForSegment(selected.value)?.candidate?.configuration.occurrence).toBe('always')
    scope.stop()
  })
  it('walks configured questions and returns the same executable draft as manual answers', () => {
    const selected = ref<any>({ id: 'drill', export_process_id: 'p_drill', normalized_step_name: '钻孔', sequence: 1, source_nodes: [], doc_coverage: { hit_docs: 1, total_docs: 2 }, matched_detail_rows: [], rule_review: null })
    const configuration: AnalysisGuidanceConfiguration = { schema_version: '1.0', revision: 1, guidance: '', materials: [], directions: ['A侧', '周边'], feature_mappings: { 孔: ['孔(通孔)', '孔(盲孔)'] }, operation_guidance: { 钻孔: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'feature', features: ['孔(盲孔)'], direction: '周边' } } } }
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({
      guidance: computed(() => configuration), segments: computed(() => [selected.value]),
      selectedSegment: computed(() => selected.value), detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()), matchedDocumentTexts: computed(() => []),
    }))!
    expect(tree.questionTreeCurrentQuestion.value?.id).toBe('guided_mode')
    tree.acceptAllRecommendedQuestionTree()
    const recommended = tree.getAnalysisDraftForSegment(selected.value)
    expect(recommended?.candidate?.configuration.when.all[0].value).toEqual(['孔(盲孔)'])
    const trail = tree.questionTreeTrail.value.map(item => ({ ...item }))
    tree.resetQuestionTree()
    for (const item of trail) {
      const q = tree.questionTreeCurrentQuestion.value!
      if (q.multiple) tree.chooseQuestionTreeOptions(item.value.split('|').map(value => ({ value, label: value })))
      else tree.chooseQuestionTreeOption({ value: item.value, label: item.label })
    }
    expect(tree.getAnalysisDraftForSegment(selected.value)).toEqual(recommended)
    expect(tree.questionTreeResultSummary.value).toContain('周边')
    scope.stop()
  })
})

describe('question tree reanswer draft persistence', () => {
  afterEach(() => vi.unstubAllGlobals())

  function setup() {
    const entries = new Map<string, string>()
    const localStorage = {
      getItem: (key: string) => entries.get(key) ?? null,
      setItem: (key: string, value: string) => entries.set(key, value),
      removeItem: (key: string) => entries.delete(key),
    }
    vi.stubGlobal('window', { localStorage })
    const projectId = ref(17)
    const segment = ref<any>({
      id: 'process_mark', normalized_step_name: '标记', source_nodes: ['标记'],
      matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 },
      rule_review: { decision: 'accepted', note: 'saved', question_trail: [] },
    })
    const create = () => useAnalysisQuestionTree({
      projectId: computed(() => projectId.value), selectedSegment: computed(() => segment.value),
      detailRows: computed(() => []), selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
      matchedDocumentTexts: computed(() => []),
    })
    return { create, projectId }
  }

  it('restores an unfinished reanswer after a page reload', async () => {
    const { create } = setup()
    const scope = effectScope()
    const tree = scope.run(create)!
    tree.resetQuestionTree()
    tree.updateQuestionTreeNote('unfinished new answer')
    const question = tree.questionTreeCurrentQuestion.value!
    tree.chooseQuestionTreeOption(question.options[0]!)
    await nextTick()
    const trail = tree.questionTreeTrail.value
    scope.stop()

    const restoredScope = effectScope()
    const restored = restoredScope.run(create)!
    expect(restored.questionTreeIsRejudging.value).toBe(true)
    expect(restored.questionTreeVisible.value).toBe(true)
    expect(restored.questionTreeTrail.value).toEqual(trail)
    expect(restored.questionTreeNoteDraft.value).toBe('unfinished new answer')
    restoredScope.stop()
  })

  it('does not carry reanswer mode into another task with matching segment ids', async () => {
    const { create, projectId } = setup()
    const scope = effectScope()
    const tree = scope.run(create)!
    tree.resetQuestionTree()
    projectId.value = 18
    await nextTick()

    expect(tree.questionTreeIsRejudging.value).toBe(false)
    expect(tree.questionTreeVisible.value).toBe(false)
    scope.stop()
  })
})

describe('analysis question tree reset', () => {
  it('preserves answers and notes through every local edit entry while finalization is locked', () => {
    const readOnly = ref(false)
    const segment = ref<any>({
      id: 'process_mark', normalized_step_name: '标记', source_nodes: ['标记'],
      matched_detail_rows: [], doc_coverage: { hit_docs: 1, total_docs: 2 },
      detail_coverage: { matched_rows: 1 }, rule_review: null,
    })
    const scope = effectScope()
    const tree = scope.run(() => useAnalysisQuestionTree({
      readOnly: computed(() => readOnly.value),
      selectedSegment: computed(() => segment.value), detailRows: computed(() => []),
      selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
      matchedDocumentTexts: computed(() => []),
    }))!
    tree.updateQuestionTreeNote('用户的原说明')
    const before = tree.questionTreeTrail.value.slice()
    const question = tree.questionTreeCurrentQuestion.value!
    readOnly.value = true
    tree.chooseQuestionTreeOption(question.options[0]!)
    tree.chooseQuestionTreeOptions(question.options.slice(0, 1))
    tree.updateQuestionTreeNote('不得保存')
    tree.acceptAllRecommendedQuestionTree()
    tree.acceptAllRecommendedForAllSegments([segment.value])
    tree.reanswerLastQuestionTree()
    tree.resetQuestionTree()
    expect(tree.questionTreeTrail.value).toEqual(before)
    expect(tree.questionTreeNoteDraft.value).toBe('用户的原说明')
    expect(tree.questionTreeIsRejudging.value).toBe(false)
    scope.stop()
  })
  it('clears all mounted question-tree answers after an upstream reset', () => {
    const segment = ref<any>({
      id: 'process_mark',
      normalized_step_name: '标记',
      source_nodes: ['标记'],
      source_operation_names: ['标记'],
      matched_detail_rows: [],
      doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 },
      rule_review: null,
    })
    const tree = useAnalysisQuestionTree({
      projectId: computed(() => 17),
      selectedSegment: computed(() => segment.value),
      detailRows: computed(() => []),
      selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
      matchedDocumentTexts: computed(() => []),
    })
    const question = tree.questionTreeCurrentQuestion.value
    expect(question?.options?.length).toBeGreaterThan(0)
    tree.chooseQuestionTreeOption(question!.options![0]!)
    expect(tree.questionTreeTrail.value.length).toBeGreaterThan(0)

    tree.resetAllQuestionTrees()

    expect(tree.questionTreeTrail.value).toEqual([])
  })

  it('provides getTrailForSegment and getResultSummaryForSegment for arbitrary segments', () => {
    const segment = ref<any>({
      id: 'process_mark',
      normalized_step_name: '标记',
      source_nodes: ['标记'],
      source_operation_names: ['标记'],
      matched_detail_rows: [],
      doc_coverage: { hit_docs: 1, total_docs: 2, ratio: 0.5 },
      detail_coverage: { matched_rows: 1 },
      rule_review: null,
    })
    const tree = useAnalysisQuestionTree({
      projectId: computed(() => 18),
      selectedSegment: computed(() => segment.value),
      detailRows: computed(() => []),
      selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
      matchedDocumentTexts: computed(() => []),
    })

    tree.acceptAllRecommendedForAllSegments([segment.value])
    const trail = tree.getTrailForSegment(segment.value)
    expect(trail.length).toBeGreaterThan(0)
    const summary = tree.getResultSummaryForSegment(segment.value)
    expect(typeof summary).toBe('string')
  })

  it('selects recognized material candidate instead of fallback when document preview texts are provided', () => {
    const segment = ref<any>({
      id: 'split-900003',
      sequence: 20,
      normalized_step_name: '正常化',
      step_family: '热处理类',
      phase: 'heat_treatment',
      source_nodes: ['正常化'],
      source_operation_names: ['正常化'],
      source_operation_ids: [900003],
      coverage_label: '2/20',
      doc_coverage: { hit_docs: 2, total_docs: 20, ratio: 0.1, label: '2/20' },
      detail_coverage: { matched_rows: 2 },
      evidence_excerpt: ['正常化 正常化；1.带⌀20×100试样件1件，试样'],
      matched_detail_rows: [
        { detail_id: 132, document_id: 7, operation_name: '正常化', operation_content: '正常化 正常化；1.带⌀20×100试样件1件' },
        { detail_id: 161, document_id: 8, operation_name: '正常化', operation_content: '正常化 正常化；1.带试样件⌀20X10' },
      ],
      rule_review: null,
    })

    const docPreviewTexts: Record<number, string> = {
      7: '工艺规程 零件名称：加力接通活门衬套 材料牌号：4Cr14Ni14W2Mo 热处理：正常化',
      8: '工艺规程 零件名称：衬套 材料牌号：4Cr14Ni14W2Mo 热处理：正常化',
    }

    const tree = useAnalysisQuestionTree({
      projectId: computed(() => 19),
      selectedSegment: computed(() => null), // not currently selected!
      detailRows: computed(() => []),
      selectedSegmentMatchedDocIds: computed(() => new Set<number>()),
      matchedDocumentTexts: computed(() => []),
      getDocumentTextsForDocIds: (docIds: Set<number>) => Array.from(docIds).map(id => docPreviewTexts[id] || '').filter(Boolean),
    })

    tree.acceptAllRecommendedForAllSegments([segment.value])
    const trail = tree.getTrailForSegment(segment.value)
    expect(trail.length).toBeGreaterThan(0)

    // Verify trail did NOT pick fallback "当前样本里暂未自动识别出明确按材料牌号"
    const fallbackStep = trail.find(step => step.value.includes('未自动识别') || step.label.includes('未自动识别'))
    expect(fallbackStep).toBeUndefined()

    // Verify trail picked 4Cr14Ni14W2Mo!
    const materialStep = trail.find(step => step.value.includes('4Cr14Ni14W2Mo') || step.label.includes('4Cr14Ni14W2Mo'))
    expect(materialStep).toBeDefined()
    expect(materialStep?.label).toBe('4Cr14Ni14W2Mo')

    // Verify result summary contains 4Cr14Ni14W2Mo
    const summary = tree.getResultSummaryForSegment(segment.value)
    expect(summary).toContain('4Cr14Ni14W2Mo')
  })
})
