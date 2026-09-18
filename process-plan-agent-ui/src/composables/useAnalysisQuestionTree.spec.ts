import { computed, ref } from 'vue'
import { describe, expect, it } from 'vitest'

import { useAnalysisQuestionTree } from './useAnalysisQuestionTree'

describe('analysis question tree reset', () => {
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
