import { describe, expect, it } from 'vitest'

import type { GroupTemplateNode, GroupTemplateStepMappingInput } from '@/api/extract'
import {
  buildEligibleTemplateSteps,
  featureLeafConfiguration,
  groupConfirmedMappingsByLeaf,
  mappingRecord,
  removeLeafMapping,
} from './templateGroupProcessMapping'

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
  key: 'grp_a', source_id: '', name: 'A侧', path: ['A侧'], feature_selections: [], params: {}, children: [
    leaf('grp_outer', ['A侧', '外环槽'], ['U形外环槽']),
    leaf('grp_inner', ['A侧', '内环槽'], ['U形内环槽']),
    leaf('grp_hole', ['A侧', '孔'], ['孔(盲孔)']),
  ],
}]

const mapping = (path: string[], stepName = '车槽'): GroupTemplateStepMappingInput => ({
  source_operation_id: 11,
  source_operation_name: '车削加工（A侧）',
  source_step_order: 1,
  source_step_name: stepName,
  scope_template_group_path: ['A侧'],
  template_group_path: path,
  candidate_features: ['U形外环槽'],
  match_mode: 'any',
  status: 'confirmed',
  confidence: 1,
  source: 'user_confirmed',
})

describe('templateGroupProcessMapping', () => {
  it('keeps geometry-processing steps and excludes non-feature steps in one operation', () => {
    const result = buildEligibleTemplateSteps([{
      id: 11,
      name: '复合加工',
      step_items: ['钻孔', '清洗零件', '检查孔径', '倒角'],
    }])

    expect(result.eligible.map(item => item.step_name)).toEqual(['钻孔', '倒角'])
    expect(result.excluded.map(item => item.step_name)).toEqual(['清洗零件', '检查孔径'])
  })

  it('indexes one step under more than one feature leaf', () => {
    const result = groupConfirmedMappingsByLeaf([
      mapping(['A侧', '外环槽']),
      mapping(['A侧', '内环槽']),
    ], tree)

    expect(result.grp_outer).toHaveLength(1)
    expect(result.grp_inner).toHaveLength(1)
    expect(result.grp_outer![0]!.source_step_order).toBe(result.grp_inner![0]!.source_step_order)
  })

  it('allows feature leaves to stay unconfigured', () => {
    const result = featureLeafConfiguration(tree, [mapping(['A侧', '外环槽'])])
    expect(result.configured.map(item => item.key)).toEqual(['grp_outer'])
    expect(result.unconfigured.map(item => item.key)).toEqual(['grp_inner', 'grp_hole'])
  })

  it('removes one leaf edge without removing another leaf edge from the same step', () => {
    const draft = mappingRecord([
      mapping(['A侧', '外环槽']),
      mapping(['A侧', '内环槽']),
    ])

    const result = removeLeafMapping(draft, 'grp_outer', tree)

    expect(Object.values(result).map(item => item.template_group_path))
      .toEqual([['A侧', '内环槽']])
  })
})
