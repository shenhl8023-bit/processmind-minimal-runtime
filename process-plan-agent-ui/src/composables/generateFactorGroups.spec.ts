import { describe, expect, it } from 'vitest'
import { groupGenerateFields } from './generateFactorGroups'
import { projectConditionScope } from '@/utils/projectConditionFields'

describe('route validation factor layout', () => {
  it('uses frozen process identities to label neutral fields without merging different objects', () => {
    const processes = [
      { process_id: 'drill', display_name: '钻孔' },
      { process_id: 'ream', display_name: '钻铰孔' },
      { process_id: 'grind', display_name: '磨外圆' },
    ]
    const fields = processes.flatMap(p => p.process_id === 'grind'
      ? [{ key: `${projectConditionScope(p.process_id)}.it`, name: '外圆柱面的实际尺寸精度等级', type: 'number' }]
      : [{ key: `${projectConditionScope(p.process_id)}.features`, name: '加工对象的特征', type: 'multi_select' },
        { key: `${projectConditionScope(p.process_id)}.direction`, name: '同一加工对象的方位', type: 'single_select' }])
    const snapshot = JSON.stringify(fields)
    const groups = groupGenerateFields(fields, processes)[0]!.groups
    expect(groups.map(g => g.title)).toEqual(['钻孔', '钻铰孔', '磨外圆'])
    expect(groups.map(g => g.fields.length)).toEqual([2, 2, 1])
    expect(groups[2]!.context).toBe('加工特征：外圆柱面（已确定）')
    expect(JSON.stringify(fields)).toBe(snapshot)
  })
  it('groups material once, keeps each operation object together, and separates only manual Bool switches', () => {
    const groups = groupGenerateFields([
      { key: 'project_factor.material_grade', name: '材料牌号', type: 'single_select' },
      { key: 'project_factor.operation_a.features', name: '钻孔加工对象的特征', type: 'multi_select' },
      { key: 'project_factor.operation_a.direction', name: '钻孔同一加工对象的方位', type: 'single_select' },
      { key: 'project_factor.operation_b.it', name: '磨外圆 · 外圆柱面的实际尺寸精度等级', type: 'number' },
      { key: 'project_factor.operation_c.requirement', name: '当前部位是否有明确淬火要求', type: 'boolean' },
      { key: 'project_factor.manual_process_abc', name: '是否镀铜', type: 'boolean', source: '用户直接设定' },
    ])
    expect(groups.map(g => g.title)).toEqual(['基本信息（材料）', '加工因素（特征、方位、精度）', '人工安排'])
    expect(groups[1]!.groups[0]!.fields.map(f => f.key)).toEqual(['project_factor.operation_a.features', 'project_factor.operation_a.direction'])
    expect(groups[1]!.groups[1]!.title).toBe('磨外圆')
    expect(groups[1]!.groups[1]!.context).toBe('加工特征：外圆柱面（已确定）')
    expect(groups[2]!.groups.flatMap(g => g.fields)).toHaveLength(1)
  })
})
