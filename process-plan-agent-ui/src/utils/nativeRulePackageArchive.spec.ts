import { describe, expect, it } from 'vitest'
import { nativeRulePackageFiles } from './nativeRulePackageArchive'

describe('native three-table export', () => {
  it('downloads the frozen mapping delivery order and deletions while preserving the core', () => {
    const core = { processes: [{ process_id: 'drill', steps: [
      { step_id: 'a', name: 'A' }, { step_id: 'b', name: 'B' }, { step_id: 'c', name: 'C' },
    ] }] }
    const delivery = { processes: [{ process_id: 'drill', steps: [
      { step_id: 'c', name: 'C', candidates: {} }, { step_id: 'a', name: 'A', candidates: { '孔': ['孔(盲孔)'] } },
    ] }] }
    const saved = { export_sources: { compiler_version: 'native-v2/1', native_snapshot: {
      schema_version: '2.0', normalized_route: [{ id: 'drill' }], template_mapping_catalog: delivery,
      rule_package: { manifest: {}, factor_dictionary: {}, input_schema: {}, route_catalog: core,
        route_rules: {}, test_cases: [] },
    } } } as any
    const files = nativeRulePackageFiles(saved)!
    expect(JSON.parse(files.find(file => file.name === 'full_route_table.json')!.content)).toEqual(delivery)
    expect(saved.export_sources.native_snapshot.rule_package.route_catalog).toEqual(core)
  })
  it('exports three executable tables without analysis evidence while retaining input constraints, steps and relationships', () => {
    const factors = { schema_version: '2.0', fields: [
      { key: 'length', type: 'number', unit: 'mm', required: true, validation: { min: 0, max: 500 } },
    ] }
    const inputs = { schema_version: '2.0', fields: [{ ...factors.fields[0], label: '零件长度' }] }
    const catalog = { schema_version: '2.0', processes: [
      { process_id: 'prepare', process_code: 'PREPARE', display_name: '准备', default_sequence: 100,
        main: true, phase: '热前', steps: [{ step_id: 'mark', name: '标记', kind: 'attached' }] },
      { process_id: 'turn', process_code: 'TURN', display_name: '车削', default_sequence: 200,
        constraints: { requires: ['prepare'], must_run_after: ['prepare'] },
        steps: [{ step_id: 'turn.outer', name: '车外圆', kind: 'primary' }] },
    ] }
    const rules = { schema_version: '2.0', rules: [
      { rule_id: 'r1', enabled: true, when: { field: 'length', op: 'gt', value: 25 }, then: { include: ['turn'] } },
    ], process_relations: [
      { relation_id: 'order', relation_type: 'requires', source_process_ids: ['prepare'], target_process_ids: ['turn'] },
    ], process_configurations: [
      { process_id: 'prepare', mode: 'manual', label: '是否准备' },
    ] }
    const route = [{ id: 'turn', normalized_step_name: '车削', final_steps: [{ step_name: '车外圆' }],
      matched_detail_rows: [{ source_file: '项目资料.docx', text: '分析证据不应出现在执行表中' }],
      evidence_excerpt: '分析证据不应出现在执行表中', review_status: 'confirmed', doc_coverage: { count: 20 },
    }]
    const saved = { export_sources: { compiler_version: 'native-v2/1', native_snapshot: {
      schema_version: '2.0', normalized_route: route, rule_package: {
        manifest: { project_id: 12 }, factor_dictionary: factors, input_schema: inputs,
        route_catalog: catalog, route_rules: rules, test_cases: [],
      },
    } } } as any
    const frozenBefore = JSON.stringify(saved)
    const files = nativeRulePackageFiles(saved)!
    const archive = Object.fromEntries(files.map(file => [file.name, JSON.parse(file.content)]))
    expect(Object.keys(archive).sort()).toEqual([
      'factor_table.json', 'full_route_table.json', 'rule_table.json',
    ])
    expect(archive['factor_table.json']).toEqual({ ...factors, input_schema: inputs })
    expect(archive['full_route_table.json']).toEqual(catalog)
    expect(archive['rule_table.json']).toEqual(rules)
    expect(files.map(file => file.content).join('\n')).not.toContain('分析证据不应出现在执行表中')
    expect(JSON.stringify(saved)).toBe(frozenBefore)

    // More supporting documents must not enlarge or change the executable tables.
    saved.export_sources.native_snapshot.normalized_route[0].matched_detail_rows =
      Array.from({ length: 1000 }, (_, id) => ({ id, text: '来源明细'.repeat(100) }))
    expect(nativeRulePackageFiles(saved)).toEqual(files)
  })
})
