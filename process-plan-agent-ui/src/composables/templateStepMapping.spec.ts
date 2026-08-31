import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GroupTemplateNode, TemplateGroupMappingOperationInput } from '@/api/extract'
import {
  buildTemplateStepRefs,
  chunkTemplateSuggestionOperations,
  createNotApplicableStepMapping,
  createTemplateStepMapping,
  confirmedMappingsForStep,
  descendantFeatureLeaves,
  groupStepMappingsByStep,
  isFeatureLeaf,
  loadTemplateStepMappingDraft,
  mergeTemplateStepMapping,
  mappingTargetsForScope,
  recommendedFeaturesForSelection,
  saveTemplateStepMappingDraft,
  settleTemplateSuggestionBatches,
  selectedTemplateFeatures,
  selectedFeatureLeaves,
  stepMappingKey,
  templateFeatureSelectionKey,
  unresolvedTemplateSteps,
} from './templateStepMapping'

const leaf = (key: string, path: string[], features: string[]): GroupTemplateNode => ({
  key,
  source_id: '',
  name: path[path.length - 1] || '',
  path,
  feature_selections: features,
  params: {},
  children: [],
})

const tree: GroupTemplateNode[] = [{
  key: 'grp_a',
  source_id: '',
  name: 'A侧',
  path: ['A侧'],
  feature_selections: [],
  params: {},
  children: [
    leaf('grp_end', ['A侧', '端面'], ['轴端面']),
    leaf('grp_hole', ['A侧', '孔'], ['孔(盲孔)', '孔(通孔)']),
  ],
}]

describe('templateStepMapping', () => {
  afterEach(() => vi.unstubAllGlobals())
  it('builds stable one-based step refs', () => {
    expect(buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['平端面', '钻孔'] }))
      .toEqual([
        expect.objectContaining({ step_key: 'op_11_s01', step_order: 1, step_name: '平端面' }),
        expect.objectContaining({ step_key: 'op_11_s02', step_order: 2, step_name: '钻孔' }),
      ])
  })

  it('treats parents as scopes and leaves as formal targets', () => {
    expect(isFeatureLeaf(tree[0]!)).toBe(false)
    expect(isFeatureLeaf(tree[0]!.children[0]!)).toBe(true)
    expect(descendantFeatureLeaves(tree[0]!).map(item => item.key)).toEqual(['grp_end', 'grp_hole'])
  })

  it('allows one step to keep multiple leaf mappings', () => {
    const step = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['钻孔'] })[0]!
    const mapping = createTemplateStepMapping(step, tree[0]!.children[1]!, ['A侧'])
    const record = { [stepMappingKey(mapping)]: mapping }

    expect(groupStepMappingsByStep(record)[step.step_key]).toEqual([mapping])
    expect(mapping.candidate_features).toEqual(['孔(盲孔)', '孔(通孔)'])
  })

  it('reports unresolved steps until mapped or explicitly skipped', () => {
    const steps = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['平端面', '检验'] })
    const mapped = createTemplateStepMapping(steps[0]!, tree[0]!.children[0]!, ['A侧'])
    const skipped = createNotApplicableStepMapping(steps[1]!)

    expect(unresolvedTemplateSteps(steps, { [stepMappingKey(mapped)]: mapped })).toEqual([steps[1]])
    expect(unresolvedTemplateSteps(steps, {
      [stepMappingKey(mapped)]: mapped,
      [stepMappingKey(skipped)]: skipped,
    })).toEqual([])
  })

  it('shows only confirmed feature mappings for the selected work step', () => {
    const steps = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['平端面', '检验'] })
    const mapped = createTemplateStepMapping(steps[0]!, tree[0]!.children[0]!, ['A侧'])
    const skipped = createNotApplicableStepMapping(steps[1]!)

    expect(confirmedMappingsForStep({
      [stepMappingKey(mapped)]: mapped,
      [stepMappingKey(skipped)]: skipped,
    }, steps[0]!)).toEqual([mapped])
    expect(confirmedMappingsForStep({
      [stepMappingKey(mapped)]: mapped,
      [stepMappingKey(skipped)]: skipped,
    }, steps[1]!)).toEqual([])
  })

  it('splits full-route recommendation requests without changing step positions', () => {
    const operations: TemplateGroupMappingOperationInput[] = [{
      operation_id: 11,
      operation_name: '车削A侧',
      step_items: ['平端面', '车外圆', '车槽', '钻孔'],
      rule_evidence: [],
      rule_reasons: [],
    }, {
      operation_id: 12,
      operation_name: '车削B侧',
      step_items: ['平端面', '车外圆', ''],
      rule_evidence: [],
      rule_reasons: [],
    }]

    expect(chunkTemplateSuggestionOperations(operations, 3)).toEqual([
      [{ ...operations[0], step_items: ['平端面', '车外圆', '车槽', ''] }],
      [{ ...operations[0], step_items: ['', '', '', '钻孔'] }, { ...operations[1], step_items: ['平端面', '车外圆', ''] }],
    ])
  })

  it('keeps successful suggestion batches when another batch fails', async () => {
    const result = await settleTemplateSuggestionBatches([['first'], ['second']], async (batch) => {
      if (batch[0] === 'second') throw new Error('temporary model failure')
      return batch[0]
    })

    expect(result.values).toEqual(['first'])
    expect(result.failedCount).toBe(1)
  })

  it('reports a completed recommendation batch before a slower batch finishes', async () => {
    let releaseSlow: (() => void) | undefined
    const slow = new Promise<string>((resolve) => { releaseSlow = () => resolve('slow') })
    const received: string[] = []
    const pending = settleTemplateSuggestionBatches(
      ['fast', 'slow'],
      async batch => batch === 'fast' ? 'fast' : slow,
      value => received.push(value),
    )

    await Promise.resolve()
    expect(received).toEqual(['fast'])

    releaseSlow?.()
    await pending
  })

  it('keeps only selected feature leaves for a multi-feature mapping action', () => {
    expect(selectedFeatureLeaves(tree, ['grp_a', 'grp_end', 'grp_hole', 'missing'])
      .map(item => item.key)).toEqual(['grp_end', 'grp_hole'])
  })

  it('selects individual features instead of the whole feature group', () => {
    const hole = tree[0]!.children[1]!
    const selected = selectedTemplateFeatures(tree, [
      templateFeatureSelectionKey(hole.key, '孔(通孔)'),
      templateFeatureSelectionKey(hole.key, '不存在的特征'),
    ])

    expect(selected).toEqual([{ leaf: hole, feature: '孔(通孔)' }])
  })

  it('writes only the user-selected features into a step mapping', () => {
    const step = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['钻孔'] })[0]!

    expect(createTemplateStepMapping(
      step,
      tree[0]!.children[1]!,
      ['A侧'],
      'user_confirmed',
      1,
      ['孔(通孔)'],
    ).candidate_features).toEqual(['孔(通孔)'])
  })

  it('narrows smart recommendations to explicitly selected features', () => {
    const hole = tree[0]!.children[1]!
    const selected = selectedTemplateFeatures(tree, [
      templateFeatureSelectionKey(hole.key, '孔(通孔)'),
    ])

    expect(recommendedFeaturesForSelection(
      hole.key,
      ['孔(盲孔)', '孔(通孔)'],
      selected,
    )).toEqual(['孔(通孔)'])
  })

  it('adds only the newly recommended feature to an existing mapping', () => {
    const step = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['加工孔'] })[0]!
    const existing = createTemplateStepMapping(
      step,
      tree[0]!.children[1]!,
      ['A侧'],
      'user_confirmed',
      1,
      ['孔(盲孔)'],
    )
    const recommended = createTemplateStepMapping(
      step,
      tree[0]!.children[1]!,
      ['A侧'],
      'auto_confirmed',
      0.96,
      ['孔(通孔)'],
    )

    expect(mergeTemplateStepMapping(existing, recommended)?.candidate_features)
      .toEqual(['孔(盲孔)', '孔(通孔)'])
  })

  it('uses a parent only to constrain descendant leaves', () => {
    expect(mappingTargetsForScope(tree[0]!).map(item => item.key)).toEqual(['grp_end', 'grp_hole'])
    expect(mappingTargetsForScope(tree[0]!.children[0]!).map(item => item.key)).toEqual(['grp_end'])
  })

  it('does not restore a draft after the route fingerprint changes', () => {
    const values = new Map<string, string>()
    vi.stubGlobal('localStorage', {
      getItem: (key: string) => values.get(key) || null,
      setItem: (key: string, value: string) => values.set(key, value),
      removeItem: (key: string) => values.delete(key),
    })
    const step = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['钻孔'] })[0]!
    const mapping = createTemplateStepMapping(step, tree[0]!.children[1]!, ['A侧'])

    saveTemplateStepMappingDraft(28, 3, 'route-a', [mapping])

    expect(loadTemplateStepMappingDraft(28, 3, 'route-a')).toEqual([mapping])
    expect(loadTemplateStepMappingDraft(28, 3, 'route-b')).toEqual([])
  })
})
