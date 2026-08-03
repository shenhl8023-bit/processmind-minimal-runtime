import { afterEach, describe, expect, it, vi } from 'vitest'

import type { GroupTemplateNode } from '@/api/extract'
import {
  buildTemplateStepRefs,
  createNotApplicableStepMapping,
  createTemplateStepMapping,
  descendantFeatureLeaves,
  groupStepMappingsByStep,
  isFeatureLeaf,
  loadTemplateStepMappingDraft,
  mappingTargetsForScope,
  saveTemplateStepMappingDraft,
  stepMappingKey,
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
