import { describe, expect, it } from 'vitest'
import { getTemplateMappingStatus, isGroupTemplateReady } from './projectGroupTemplateCheck'
const leaf = { key: 'outer', path: ['外圆'], name: '外圆', feature_selections: ['外圆柱面'], children: [] }
const mapping = { source_operation_id: 7, source_step_order: 1, source_step_name: '车外圆', status: 'confirmed', template_group_path: ['外圆'], candidate_features: ['外圆柱面'] }
const template = (changes = {}) => ({ tree: [leaf], mappings: [], step_mappings: [mapping], ...changes } as any)
const operations = [{ id: 7, name: '精车', step_items: ['车外圆'] }, { id: 8, name: '包装', step_items: ['包装'] }]
describe('template mapping readiness', () => {
  it('allows one confirmed mapping even with other operations unmapped', () => {
    expect(getTemplateMappingStatus(template(), operations).validCount).toBe(1)
  })
  it('requires at least one valid mapping in every feature-bearing template group', () => {
    const secondLeaf = { key: 'inner', path: ['内孔'], name: '内孔', feature_selections: ['内孔柱面'], children: [] }
    const multipleGroups = template({ tree: [leaf, secondLeaf] })
    const status = getTemplateMappingStatus(multipleGroups, operations)
    expect(status.missingFeatureGroups.map(node => node.key)).toEqual(['inner'])
    expect(isGroupTemplateReady(multipleGroups)).toBe(false)
    expect(isGroupTemplateReady(template({
      tree: [leaf, secondLeaf],
      step_mappings: [mapping, { ...mapping, template_group_path: ['内孔'], candidate_features: ['内孔柱面'] }],
    }))).toBe(true)
  })
  it('rejects missing paths and removed features', () => {
    expect(isGroupTemplateReady(template({ tree: [] }))).toBe(false)
    expect(isGroupTemplateReady(template({ step_mappings: [{ ...mapping, candidate_features: ['不存在'] }] }))).toBe(false)
  })
  it('rejects stale operations and changed steps', () => {
    expect(getTemplateMappingStatus(template(), []).validCount).toBe(0)
    expect(getTemplateMappingStatus(template(), [{ ...operations[0]!, step_items: ['铣端面'] }]).invalidCount).toBe(1)
  })
  it('accepts legacy partial mappings only when the group and source still exist', () => {
    const legacy = template({ step_mappings: [], mappings: [{ source_operation_id: 7, template_group_path: ['外圆'], feature_selections: ['外圆柱面'] }] })
    expect(getTemplateMappingStatus(legacy, operations).validCount).toBe(1)
    expect(getTemplateMappingStatus(legacy, []).validCount).toBe(0)
  })
  it('requires the exact final target and excludes auxiliary-only mappings', () => {
    const final = { id: 100, process_id: 'turn', process_type: '加工工序', source_operation_ids: [7], name: '车削',
      steps: [{ step_id: 'turn.s1', step_name: '车外圆', source_operation_id: 7, source_step_order: 1, source_step_name: '车外圆',
        source_steps: [{ source_operation_id: 7, source_step_order: 1, source_step_name: '车外圆' }] }] } as any
    const scoped = { ...mapping, final_targets: [{ process_id: 'turn', step_id: 'turn.s1' }] }
    expect(getTemplateMappingStatus(template({ step_mappings: [scoped] }), [final]).validCount).toBe(1)
    expect(getTemplateMappingStatus(template({ step_mappings: [{ ...scoped, final_targets: [{ process_id: 'removed', step_id: 'removed.s1' }] }] }), [final]).validCount).toBe(0)
    expect(getTemplateMappingStatus(template({ step_mappings: [scoped] }), [{ ...final, process_type: '辅助工序' }]).validCount).toBe(0)
  })
})
