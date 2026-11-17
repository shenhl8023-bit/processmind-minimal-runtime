import { describe, expect, it } from 'vitest'
import * as editor from './processConfigurationEditor'
import { projectConditionFields, projectConditionScope, projectConditionExpressions, mergeProjectConditionFields, referencedConditionKeys } from './projectConditionFields'

describe('current project conditions', () => {
  it('uses neutral display labels while keeping repeated nodes independently scoped', () => {
    const first = projectConditionFields('drill', '钻孔')
    const second = projectConditionFields('drill-two', '钻孔')
    expect(first.map(field => field.label)).toEqual(['加工对象的特征', '同一加工对象的方位', '孔、孔(盲孔)、孔(通孔)、内圆柱面的实际尺寸精度等级', '孔、孔(盲孔)、孔(通孔)、内圆柱面的实际Ra要求值', '材料牌号', '目标硬度制', '目标硬度下限（含）', '目标硬度上限（含）', '当前部位是否有明确钻孔要求'])
    expect(second.map(field => field.label)).toEqual(first.map(field => field.label))
    for (const field of first.filter(field => field.key !== 'project_factor.material_grade')) {
      expect(second.some(other => other.key === field.key)).toBe(false)
      expect(field.source).toContain('工序=drill')
    }
  })
  it('collects composite references from backend JSON with nullable inactive branches', () => {
    expect([...referencedConditionKeys({ all: [{ all: null, any: null, not: null, field: 'project_factor.old.features', op: 'contains_any', value: ['旧特征'] }], any: null, not: null, field: null, op: null, value: null } as any)]).toEqual(['project_factor.old.features'])
  })
  it('keeps the complete drilling feature domain distinct from recommendations', () => {
    const fields = projectConditionFields('drill', '钻孔', { feature_mappings: { '孔/内孔': ['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面'] }, operation_guidance: { 钻孔: { feature_group: '孔/内孔', recommendation: { features: ['孔(盲孔)', '孔(通孔)'] } } } })
    expect(fields.find(field => field.key.endsWith('.features'))?.options?.map(o => o.value)).toEqual(['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面'])
    expect(fields.find(field => field.key.endsWith('.direction'))?.options?.map(o => o.value)).toEqual(['A侧', 'B侧', '中间', '周边', '所有方位'])
    expect(Object.keys(projectConditionExpressions)).toEqual(['C01a', 'C01b', 'J01', 'J02', 'R01', 'R02', 'R03', 'B01', 'B02', 'M01', 'Q01', 'Y01'])
    expect(fields.some(field => /tolerance\.|geometry\.|special\.|precision\.grades/.test(field.key))).toBe(false)
  })

  it('rejects an AND assembled from different object scopes', () => {
    const candidate: any = { kind: 'process_configuration', configuration: { process_id: 'drill', occurrence: 'conditional', relations: [], when: { all: [
      { field: 'project_factor.operation_a.features', op: 'contains_any', value: ['孔'] },
      { field: 'project_factor.operation_b.direction', op: 'eq', value: '周边' },
    ] } } }
    expect(editor.validateAuthoredCandidate(candidate, 'drill').join()).toContain('同一加工对象')
  })

  it('preserves the existing stable object hash', () => {
    expect(projectConditionScope('drill')).toBe('project_factor.operation_1a78c49e')
  })

  it('requires all three hardness fields for an automatic interval condition', () => {
    expect(editor.validateAuthoredCandidate({ kind: 'process_configuration', preview: '', configuration: { process_id: 'quench', occurrence: 'conditional', relations: [], when: { field: 'project_factor.operation_a.hardness_min', op: 'gte', value: 55 } } }, 'quench').join()).toContain('完整')
  })

  it('retains the full supplied project candidate domain before any field is selected', () => {
    const definitions = projectConditionFields('drill', '钻孔', { materials: ['已冻结牌号A', '已冻结牌号B'] })
    const fields = mergeProjectConditionFields('drill', '钻孔', definitions, [])
    expect(fields.find(field => field.key === 'project_factor.material_grade')?.options?.map(option => option.value)).toEqual(['已冻结牌号A', '已冻结牌号B'])
    expect(fields.some(field => field.key === 'tolerance.roundness_mm')).toBe(false)
  })

  it('uses the complete frozen configuration before registry defaults, with referenced definitions winning', () => {
    const configuration = { directions: ['背面', '所有方位'] }
    const registry = projectConditionFields('drill', '钻孔')
    const fields = mergeProjectConditionFields('drill', '钻孔', registry, [], configuration)
    expect(fields.find(field => field.key.endsWith('.direction'))?.options?.map(option => option.value)).toEqual(['背面', '所有方位'])
    const frozen = { ...registry.find(field => field.key.endsWith('.direction'))!, options: [{ value: '原侧', label: '原侧' }] }
    const candidate: any = { when: { field: frozen.key, op: 'eq', value: '原侧' }, field_definitions: [frozen] }
    const preserved = mergeProjectConditionFields('drill', '钻孔', registry, [candidate], configuration)
    expect(preserved.find(field => field.key === frozen.key)?.options).toEqual([{ value: '原侧', label: '原侧' }])
  })

  it('keeps referenced legacy standard definitions available while hiding unused retired fields', () => {
    const candidate: any = { kind: 'condition', when: { field: 'tolerance.roundness_mm', op: 'lte', value: .01 }, then: { include_process_ids: ['grind'] }, field_definitions: [] }
    const fields = mergeProjectConditionFields('grind', '磨外圆', [], [candidate])
    expect(fields.find(field => field.key === 'tolerance.roundness_mm')).toMatchObject({ label: '圆度公差', type: 'number', unit: 'mm' })
    expect(fields.some(field => field.key === 'geometry.diameter_mm')).toBe(false)
    const frozen = { ...projectConditionFields('grind', '磨外圆')[0]!, options: [{ value: '旧项目特征', label: '旧项目特征' }] }
    const preserved = mergeProjectConditionFields('grind', '磨外圆', [], [{ ...candidate, when: { field: frozen.key, op: 'contains_any', value: ['旧项目特征'] }, field_definitions: [frozen] }])
    expect(preserved.find(field => field.key === frozen.key)?.options).toEqual([{ value: '旧项目特征', label: '旧项目特征' }])
  })
})
