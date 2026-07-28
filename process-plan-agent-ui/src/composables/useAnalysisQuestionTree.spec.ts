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
})
