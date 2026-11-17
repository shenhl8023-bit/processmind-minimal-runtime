import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { FinalizedRulePackageResult } from '@/api/extract'
import { downloadValidatedRulePackage } from './validatedRulePackageDownload'
import { downloadBlob } from './exportArchive'
import { allocatePublicRulePackageIdentities } from '@/api/publicRulePackageIdentities'
import { sampleRulePackageTables, type PublicRulePackageIdentityRegistry } from './sampleRulePackageAdapter'
const evidenceLocation = (globalThis as any).process?.env.PM035_EVIDENCE_DIR as string | undefined
const evidenceFs = evidenceLocation ? await import(/* @vite-ignore */ ['node', 'fs'].join(':')) : undefined

vi.mock('@/api/publicRulePackageIdentities', () => ({ allocatePublicRulePackageIdentities: vi.fn() }))

vi.mock('./exportArchive', async importOriginal => ({
  ...await importOriginal<typeof import('./exportArchive')>(), downloadBlob: vi.fn(),
}))

export function sampleSnapshot(): FinalizedRulePackageResult {
  const fields = [
    { key: 'job.material', label: '材料', type: 'single_select', options: [{ value: 'Steel', label: '钢' }, { value: 'Al', label: '铝' }] },
    { key: 'project_factor.object_one.features', label: '同一加工对象特征', type: 'multi_select', options: [{ value: '盲孔', label: '盲孔' }, { value: '通孔', label: '通孔' }] },
    { key: 'project_factor.object_one.direction', label: '同一加工对象方位', type: 'single_select', options: [{ value: 'A侧', label: 'A侧' }, { value: '周边', label: '周边' }, { value: '所有方位', label: '所有方位' }] },
    { key: 'project_factor.manual_process_mark', label: '是否标记', type: 'boolean', source: '用户直接设定' },
    { key: 'project_factor.manual_process_coat', label: '是否镀层', type: 'boolean', source: '用户直接设定' },
    { key: 'job.length', label: '长度（mm）', type: 'number', unit: 'mm', required: true, validation: { min: 2, max: 800 } },
  ]
  const catalog = [
    { process_id: 'internal.prepare', display_name: '准备', main: true, default_sequence: 10, phase: 'auxiliary', steps: [] },
    { process_id: 'internal.drill', display_name: '钻孔', main: true, default_sequence: 20, phase: 'rough', steps: [
      { step_id: 'internal.drill.first', name: '钻导孔', kind: 'primary' },
      { step_id: 'internal.drill.second', name: '扩孔', kind: 'primary' },
      { step_id: 'internal.drill.third', name: '去毛刺', kind: 'attached' },
    ], constraints: { requires: ['internal.prepare'] } },
    { process_id: 'internal.mark', display_name: '标记', default_sequence: 30, phase: 'auxiliary', steps: [] },
    { process_id: 'internal.coat', display_name: '镀层', default_sequence: 40, phase: 'surface_treatment', steps: [] },
    { process_id: 'internal.strip', display_name: '去镀层', default_sequence: 50, phase: 'surface_treatment', steps: [] },
  ]
  const rules = { rules: [], process_relations: [], process_configurations: [
    { process_id: 'internal.prepare', occurrence: 'always', when: null, relations: [] },
    { process_id: 'internal.drill', occurrence: 'conditional', when: { all: [
      { field: 'project_factor.object_one.features', op: 'contains_any', value: ['盲孔', '通孔'] },
      { field: 'project_factor.object_one.direction', op: 'in', value: ['周边'] },
    ] }, relations: [] },
    { process_id: 'internal.mark', occurrence: 'manual', when: { field: 'project_factor.manual_process_mark', op: 'eq', value: true }, relations: [] },
    { process_id: 'internal.coat', occurrence: 'manual', when: { field: 'project_factor.manual_process_coat', op: 'eq', value: true }, relations: [] },
    { process_id: 'internal.strip', occurrence: 'associated', when: null, relations: [
      { relation_type: 'trigger_after', source_process_ids: ['internal.coat'], target_process_ids: ['internal.strip'], source_match: 'any' },
    ] },
  ] }
  return { id: 1, project_id: 35, version: 2, export_sources: { compiler_version: 'native-v2/1', project_id: 35,
    mother_route: Object.fromEntries(catalog.map(p => [p.process_id, { auxiliary: p.phase !== 'rough', steps: p.steps }])),
    native_snapshot: { schema_version: '2.0', normalized_route: catalog.map(p => ({ export_process_id: p.process_id, phase: p.phase })),
      rule_package: { manifest: { project_id: 35 }, factor_dictionary: { fields }, input_schema: { fields },
        route_catalog: { processes: catalog }, route_rules: rules, test_cases: [] },
    },
  } } as any
}

export async function unzipStored(blob: Blob): Promise<Record<string, any>> {
  const bytes = new Uint8Array(await blob.arrayBuffer()), view = new DataView(bytes.buffer)
  const result: Record<string, any> = {}
  let offset = 0
  while (view.getUint32(offset, true) === 0x04034b50) {
    expect(view.getUint16(offset + 8, true)).toBe(0)
    const size = view.getUint32(offset + 18, true), names = view.getUint16(offset + 26, true)
    const start = offset + 30 + names + view.getUint16(offset + 28, true)
    const name = new TextDecoder().decode(bytes.slice(offset + 30, offset + 30 + names))
    result[name] = JSON.parse(new TextDecoder().decode(bytes.slice(start, start + size)))
    offset = start + size
  }
  expect(view.getUint32(offset, true)).toBe(0x02014b50)
  return result
}

function identityRegistry(saved: FinalizedRulePackageResult): PublicRulePackageIdentityRegistry {
  const pkg = saved.export_sources!.native_snapshot.rule_package
  const mapping = (ids: string[], prefix: string) => Object.fromEntries([...ids].sort().map((id, i) => [id, `${prefix}${String(i + 1).padStart(3, '0')}`]))
  return { processes: mapping(pkg.route_catalog.processes.map((p: any) => p.process_id), 'P'),
    steps: mapping(pkg.route_catalog.processes.flatMap((p: any) => p.steps.map((s: any) => s.step_id)), 'S'),
    factors: mapping(pkg.input_schema.fields.map((f: any) => f.key), 'F') }
}

// Independent evaluator for the small public expression language. Full reader/native
// cross-checks consume the optional evidence artifacts below, including real CAD binding.
function selectedIds(tables: ReturnType<typeof sampleRulePackageTables>, input: Record<string, any>): string[] {
  const rules = new Map(tables.rule_table.map(r => [r.target, r]))
  const chosen = new Set<string>(), visited = new Set<string>()
  const evaluate = (c: any): boolean => {
    if (typeof c === 'boolean') return c
    if (c.all) return c.all.every(evaluate)
    if (c.any) return c.any.some(evaluate)
    if ('not' in c) return !evaluate(c.not)
    if (c.field === 'selected_processes') { choose(c.value); return chosen.has(c.value) }
    const actual = input[c.field] ?? null
    if (c.op === 'exists') return (actual !== null && actual !== '' && (!Array.isArray(actual) || !!actual.length)) === c.value
    if (c.op === 'contains') return (Array.isArray(actual) || typeof actual === 'string') && actual.includes(c.value)
    if (c.op === 'neq') return actual !== c.value
    if (actual === null) return false
    if (c.op === 'eq') return actual === c.value
    if (c.op === 'in') return c.value.includes(actual)
    if (c.op === 'gt') return actual > c.value
    if (c.op === 'gte') return actual >= c.value
    if (c.op === 'lt') return actual < c.value
    if (c.op === 'lte') return actual <= c.value
    throw new Error(`unexpected public operator ${c.op}`)
  }
  const choose = (id: string) => {
    if (visited.has(id)) return
    visited.add(id)
    const rule = rules.get(id)!
    if (rule.required || evaluate(rule.when)) chosen.add(id)
  }
  tables.full_route_table.forEach(p => choose(p.process_id))
  return tables.full_route_table.filter(p => chosen.has(p.process_id)).map(p => p.process_id)
}

const internals = (saved: FinalizedRulePackageResult) => saved.export_sources!.native_snapshot.rule_package
function withEvidence(name: string, saved: FinalizedRulePackageResult, inputs: Record<string, any>[], tables = sampleRulePackageTables(saved)) {
  if (evidenceLocation && evidenceFs) {
    evidenceFs.mkdirSync(evidenceLocation, { recursive: true })
    evidenceFs.writeFileSync(`${evidenceLocation}/${name}.json`, JSON.stringify({ saved, inputs, tables, compact: sampleRulePackageTables(saved, identityRegistry(saved)), registry: identityRegistry(saved) }, null, 2))
  }
}

describe('sample-compatible shared download boundary', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.mocked(allocatePublicRulePackageIdentities).mockImplementation(async saved => identityRegistry(saved))
  })

  it('downloads an actual ZIP containing exactly the three sample arrays, without changing native V2', async () => {
    const saved = sampleSnapshot(), before = JSON.stringify(saved)
    await downloadValidatedRulePackage(saved, '任务/一')
    const [blob, name] = vi.mocked(downloadBlob).mock.calls[0]!
    const tables = await unzipStored(blob)
    expect(name).toBe('任务_一_规则包_V2.zip')
    expect(Object.keys(tables).sort()).toEqual(['factor_table.json', 'full_route_table.json', 'rule_table.json'])
    Object.values(tables).forEach(table => expect(Array.isArray(table)).toBe(true))
    tables['full_route_table.json'].forEach((process: any) => expect(process.process_id).toMatch(/^P\d{3,}$/))
    expect(JSON.stringify(saved)).toBe(before)
  })

  it('preserves all occurrence modes, scoped feature/direction any matches and optional Bool missing/false', () => {
    const saved = sampleSnapshot(), tables = sampleRulePackageTables(saved)
    const base = { 'job.length': 20, 'project_factor.object_one.features': ['盲孔'], 'project_factor.object_one.direction': '周边' }
    const inputs = [{ 'job.length': 20 }, base,
      { ...base, 'project_factor.object_one.features': ['通孔'], 'project_factor.manual_process_mark': true, 'project_factor.manual_process_coat': true },
      { ...base, 'project_factor.object_one.direction': 'A侧', 'project_factor.manual_process_coat': false },
      { ...base, 'project_factor.object_one.features': [], 'project_factor.manual_process_mark': false }]
    expect(inputs.map(input => selectedIds(tables, input))).toEqual([
      ['internal.prepare'], ['internal.prepare', 'internal.drill'],
      ['internal.prepare', 'internal.drill', 'internal.mark', 'internal.coat', 'internal.strip'],
      ['internal.prepare'], ['internal.prepare'],
    ])
    expect(tables.factor_table.find(f => f.key.endsWith('manual_process_mark'))).toMatchObject({ type: 'bool', default: null })
    withEvidence('occurrences', saved, inputs)
  })

  it('keeps two identically labelled machining objects separate and respects already-normalized any-direction rules', () => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    pkg.input_schema.fields.push({ key: 'project_factor.object_two.direction', label: '同一加工对象方位', type: 'single_select', options: [{ value: '周边', label: '周边' }] })
    const tables = sampleRulePackageTables(saved)
    const input = { 'job.length': 20, 'project_factor.object_one.features': ['通孔'], 'project_factor.object_one.direction': 'A侧', 'project_factor.object_two.direction': '周边' }
    expect(selectedIds(tables, input)).toEqual(['internal.prepare'])
    // Native authoring removes the wildcard direction gate; export must not add one back.
    pkg.route_rules.process_configurations[1].when = { field: 'project_factor.object_one.features', op: 'contains_any', value: ['盲孔', '通孔'] }
    const anyDirection = sampleRulePackageTables(saved)
    expect(selectedIds(anyDirection, input)).toEqual(['internal.prepare', 'internal.drill'])
    withEvidence('any-direction', saved, [input])
  })

  it.each(['operation_one', 'feature_5b54_28_901a_5b54_29'])('retains requiredness, exact options, limits, normalized finite-enum matches and integer IT bounds for %s', scope => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    const key = `project_factor.${scope}.it`
    pkg.input_schema.fields.push({ key, label: '实际尺寸精度等级', type: 'number', unit: 'IT', validation: { min: -1, max: 18 } })
    pkg.route_rules.process_configurations[1].when = { all: [
      { field: 'job.material', op: 'eq', value: ' steel ' },
      { field: 'job.length', op: 'between', value: [10, 40] },
      { field: key, op: 'lte', value: 7 },
    ] }
    const tables = sampleRulePackageTables(saved)
    expect(tables.factor_table.find(f => f.key === 'job.length')).toMatchObject({ label: '长度（mm）', type: 'number', required: true, validation: { min: 2, max: 800 } })
    expect(tables.factor_table.find(f => f.key === 'job.material')).toMatchObject({ options: ['Steel', 'Al'] })
    expect(tables.factor_table.find(f => f.key.endsWith('.it'))).toMatchObject({ type: 'int', validation: { min: 5, max: 10 } })
    const inputs = [7, 8].map(it => ({ 'job.length': 20, 'job.material': 'Steel', [key]: it }))
    expect(inputs.map(input => selectedIds(tables, input))).toEqual([['internal.prepare', 'internal.drill'], ['internal.prepare']])
    withEvidence(scope === 'operation_one' ? 'constraints' : 'constraints-shared-it', saved, inputs)
  })

  it('blocks shared-feature exports when conditional parameter requiredness cannot be represented by the sample protocol', () => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    const scope = 'project_factor.feature_5b54_28_901a_5b54_29'
    pkg.input_schema.fields.push(
      { key: `${scope}.present`, label: '孔(通孔)', type: 'boolean', required: false },
      { key: `${scope}.direction`, label: '孔(通孔)的方位', type: 'single_select', options: [{ value: 'A侧', label: 'A侧' }] },
      { key: `${scope}.it`, label: '孔(通孔)的实际尺寸精度等级', type: 'number', unit: 'IT', validation: { min: 5, max: 10 } },
    )
    expect(() => sampleRulePackageTables(saved)).toThrow(/动态必填/)
  })

  it('honors rule priority, manual false overrides and global trigger any/all gates', () => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    pkg.route_rules.process_configurations = pkg.route_rules.process_configurations.filter((c: any) => !['internal.mark', 'internal.strip'].includes(c.process_id))
    pkg.route_catalog.processes.find((p: any) => p.process_id === 'internal.mark').main = true
    pkg.route_rules.rules = [
      { rule_id: 'exclude-mark', priority: 20, source: 'user_confirmed', when: { field: 'project_factor.manual_process_mark', op: 'eq', value: false }, then: { exclude_process_ids: ['internal.mark'] } },
      { rule_id: 'drill-on', priority: 1, when: { field: 'job.length', op: 'gte', value: 10 }, then: { include_process_ids: ['internal.strip'] } },
      { rule_id: 'drill-off', priority: 2, when: { field: 'job.length', op: 'gt', value: 50 }, then: { exclude_process_ids: ['internal.strip'] } },
    ]
    let tables = sampleRulePackageTables(saved)
    expect(selectedIds(tables, { 'job.length': 20, 'project_factor.manual_process_mark': false })).toEqual(['internal.prepare', 'internal.strip'])
    expect(selectedIds(tables, { 'job.length': 60, 'project_factor.manual_process_mark': false })).toEqual(['internal.prepare'])
    withEvidence('priority', saved, [{ 'job.length': 20, 'project_factor.manual_process_mark': false }, { 'job.length': 60, 'project_factor.manual_process_mark': false }])
    pkg.route_rules.rules = [pkg.route_rules.rules[0]]
    pkg.route_rules.process_relations = [{ relation_id: 'strip-trigger', relation_type: 'trigger_after', source_process_ids: ['internal.coat', 'internal.mark'], target_process_ids: ['internal.strip'], source_match: 'all' }]
    tables = sampleRulePackageTables(saved)
    const inputs = [false, true].map(mark => ({ 'job.length': 20, 'project_factor.manual_process_mark': mark, 'project_factor.manual_process_coat': true }))
    expect(inputs.map(input => selectedIds(tables, input))).toEqual([['internal.prepare', 'internal.coat'], ['internal.prepare', 'internal.mark', 'internal.coat', 'internal.strip']])
    withEvidence('trigger-all', saved, inputs)
    pkg.route_rules.process_relations[0].source_match = 'any'
    expect(selectedIds(sampleRulePackageTables(saved), inputs[0]!)).toEqual(['internal.prepare', 'internal.coat', 'internal.strip'])
    withEvidence('trigger-any', saved, inputs)
  })

  it('pulls an unconditional unconfigured prerequisite and preserves native full-parent ordering', () => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    pkg.route_rules.process_configurations = pkg.route_rules.process_configurations.filter((c: any) => c.process_id !== 'internal.prepare')
    pkg.route_catalog.processes[0].main = false
    // Deliberately place native catalog rows out of sequence; execution order is sequence + constraints.
    pkg.route_catalog.processes.reverse()
    const input = { 'job.length': 20, 'project_factor.object_one.features': ['通孔'], 'project_factor.object_one.direction': '周边' }
    const tables = sampleRulePackageTables(saved)
    expect(selectedIds(tables, input)).toEqual(['internal.prepare', 'internal.drill'])
    expect(selectedIds(tables, { 'job.length': 20 })).toEqual([])
    withEvidence('requires', saved, [input, { 'job.length': 20 }])
  })

  it('keeps mapped step order/deletion and waiver candidates while native core and external paths stay unchanged', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot, pkg = internals(saved)
    pkg.input_schema.fields[0].source = 'plm.existing.material_grade'
    snapshot.template_mapping_catalog = JSON.parse(JSON.stringify(pkg.route_catalog))
    const drill = snapshot.template_mapping_catalog.processes[1]
    drill.steps = [{ ...drill.steps[2], candidates: {} }, { ...drill.steps[0], candidates: { '周边/孔': ['通孔'] } }]
    const registry = identityRegistry(saved), before = JSON.stringify(saved)
    const tables = sampleRulePackageTables(saved, registry)
    expect(tables.full_route_table[1]!.steps).toEqual([
      { step_name: '去毛刺', candidates: {}, step_id: registry.steps['internal.drill.third'] },
      { step_name: '钻导孔', candidates: { '周边/孔': ['通孔'] }, step_id: registry.steps['internal.drill.first'] },
    ])
    expect(tables.factor_table.find(f => f.key === registry.factors['job.material'])!.source).toBe('plm.existing.material_grade')
    expect(tables.rule_table[4]!.when).toEqual({ field: 'selected_processes', op: 'contains', value: registry.processes['internal.coat'] })
    expect(tables.factor_table.find(f => f.key === registry.factors['job.length'])!.source).toBe(`manual_defaults.${registry.factors['job.length']}`)
    expect(JSON.stringify(saved)).toBe(before)
    withEvidence('mapping', saved, [{ 'job.length': 20 }, { 'job.length': 20, 'project_factor.object_one.features': ['通孔'], 'project_factor.object_one.direction': '周边' }])
  })

  it.each(['operation_one', 'feature_5b54_28_901a_5b54_29'])('retains %s Ra units and the native strict positive domain without renaming the process', scope => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    const key = `project_factor.${scope}.ra`
    const field = { key, label: '实际表面粗糙度', type: 'number', unit: 'μm', validation: { min: 0, max: 100 } }
    pkg.input_schema.fields.push(field)
    pkg.route_rules.process_configurations[1].when = { field: key, op: 'lte', value: 0.8 }
    const tables = sampleRulePackageTables(saved)
    const exported = tables.factor_table.find(f => f.key === key)!
    expect(exported).toMatchObject({ label: '实际表面粗糙度（μm）', type: 'number', validation: { min: Number.MIN_VALUE, max: 100 } })
    expect([-0.8, 0, Number.MIN_VALUE, 0.8, 100, 101].map(ra => ra >= exported.validation.min && ra <= exported.validation.max)).toEqual([false, false, true, true, true, false])
    const inputs = [Number.MIN_VALUE, 0.8, 0.9].map(ra => ({ 'job.length': 20, [key]: ra }))
    expect(inputs.map(input => selectedIds(tables, input))).toEqual([
      ['internal.prepare', 'internal.drill'], ['internal.prepare', 'internal.drill'], ['internal.prepare'],
    ])
    expect(tables.full_route_table[1]!.process_name).toBe('钻孔')
    withEvidence(scope === 'operation_one' ? 'roughness' : 'roughness-shared-feature', saved, inputs)
    expect(field.validation).toEqual({ min: 0, max: 100 })
    field.validation.min = 0.1
    expect(sampleRulePackageTables(saved).factor_table.find(f => f.key === key)!.validation).toEqual({ min: 0.1, max: 100 })
  })

  it.each([
    ['numeric tolerance', (pkg: any) => { pkg.route_rules.process_configurations[1].when = { field: 'job.length', op: 'eq', value: 20 } }, /原生容差/],
    ['optional negation', (pkg: any) => { pkg.route_rules.process_configurations[1].when = { not: { field: 'job.material', op: 'eq', value: 'Al' } } }, /非必填因素/],
    ['multi equality', (pkg: any) => { pkg.route_rules.process_configurations[1].when = { field: 'project_factor.object_one.features', op: 'eq', value: ['盲孔'] } }, /整体相等/],
    ['runtime conflict', (pkg: any) => { pkg.route_catalog.processes[1].constraints.conflicts_with = ['internal.coat'] }, /互斥/],
    ['conditional prerequisite', (pkg: any) => { pkg.route_catalog.processes[1].constraints.requires.push('internal.coat') }, /前置/],
    ['array source', (pkg: any) => { pkg.input_schema.fields[1].source = 'input_json[].features[].feature_select' }, /同一加工对象/],
    ['options aliases', (pkg: any) => { pkg.input_schema.fields[0].options[0].aliases = ['铁'] }, /别名/],
    ['unknown mode', (pkg: any) => { pkg.route_rules.process_configurations[0].occurrence = 'unknown' }, /出现方式/],
    ['optional inequality', (pkg: any) => { pkg.route_rules.process_configurations[1].when = { field: 'job.material', op: 'neq', value: 'Al' } }, /非必填/],
    ['open text', (pkg: any) => { pkg.input_schema.fields[0].type = 'string'; pkg.route_rules.process_configurations[1].when = { field: 'job.material', op: 'eq', value: 'Steel' } }, /开放文本/],
    ['hardness interval', (pkg: any) => { pkg.input_schema.fields.push({ key: 'project_factor.operation_one.hardness_min', label: '硬度下限', type: 'number' }) }, /跨因素/],
    ['cyclic trigger', (pkg: any) => { pkg.route_rules.process_configurations[3] = { process_id: 'internal.coat', occurrence: 'associated', when: null, relations: [{ relation_type: 'trigger_after', source_process_ids: ['internal.strip'], target_process_ids: ['internal.coat'] }] } }, /循环/],
  ])('rejects %s with an actionable error before allocating IDs or downloading', async (_, change, message) => {
    const saved = sampleSnapshot(); change(internals(saved))
    await expect(downloadValidatedRulePackage(saved, '任务')).rejects.toThrow(message)
    expect(allocatePublicRulePackageIdentities).not.toHaveBeenCalled()
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('fails closed on registry allocation errors or inconsistent identities', async () => {
    vi.mocked(allocatePublicRulePackageIdentities).mockRejectedValueOnce(new Error('编号服务不可用'))
    await expect(downloadValidatedRulePackage(sampleSnapshot(), '任务')).rejects.toThrow('编号服务不可用')
    expect(downloadBlob).not.toHaveBeenCalled()
    vi.mocked(allocatePublicRulePackageIdentities).mockResolvedValueOnce({ processes: {}, steps: {}, factors: {} })
    await expect(downloadValidatedRulePackage(sampleSnapshot(), '任务')).rejects.toThrow('对外编号不完整')
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('blocks a main trigger target whose ordinary exclusion must raise a native conflict', () => {
    const saved = sampleSnapshot(), pkg = internals(saved)
    pkg.route_rules.process_configurations = pkg.route_rules.process_configurations.filter((c: any) => c.process_id !== 'internal.strip')
    pkg.route_catalog.processes[4].main = true
    pkg.route_rules.rules = [{ rule_id: 'strip-excluded', when: { field: 'job.length', op: 'gt', value: 10 }, then: { exclude_process_ids: ['internal.strip'] } }]
    pkg.route_rules.process_relations = [{ relation_id: 'coat-strip', relation_type: 'trigger_after', source_process_ids: ['internal.coat'], target_process_ids: ['internal.strip'] }]
    expect(() => sampleRulePackageTables(saved)).toThrow(/排除规则.*冲突/)
  })

  it('compares frozen mapping objects by content while preserving their actual step order', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    snapshot.template_mapping_catalog = JSON.parse(JSON.stringify(internals(saved).route_catalog))
    const route = sampleRulePackageTables(saved).full_route_table
    // JSON object member order is immaterial; array order remains contractual.
    snapshot.template_mapping_route = route.map(p => ({ ...p, steps: p.steps.map((s: any) => ({ step_id: s.step_id, candidates: s.candidates, step_name: s.step_name })) }))
    expect(sampleRulePackageTables(saved).full_route_table).toEqual(route)
  })

  it('uses frozen auxiliary delivery rows while keeping restored native instructions internal', async () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    snapshot.template_mapping_catalog = JSON.parse(JSON.stringify(internals(saved).route_catalog))
    snapshot.template_mapping_route = sampleRulePackageTables(saved).full_route_table
    // Actual current-project pattern: normalizing has a mother instruction and
    // native execution restores it, while its frozen feature-binding row is [].
    saved.export_sources!.mother_route['internal.prepare'].steps = [{ step_id: 'internal.prepare.instruction', name: '正常化', kind: 'primary' }]
    snapshot.template_mapping_catalog.processes[0].steps = saved.export_sources!.mother_route['internal.prepare'].steps
    const before = JSON.stringify(saved)
    await downloadValidatedRulePackage(saved, '实际投影')
    const archive = await unzipStored(vi.mocked(downloadBlob).mock.calls[0]![0])
    expect(archive['full_route_table.json'][0]).toMatchObject({ process_type: '辅助工序', steps: [] })
    expect(JSON.stringify(saved)).toBe(before)
    expect(snapshot.template_mapping_catalog.processes[0].steps).toHaveLength(1)
  })

  it('does not download a stale snapshot after awaiting the registry', async () => {
    let current = true, release!: (registry: PublicRulePackageIdentityRegistry) => void
    vi.mocked(allocatePublicRulePackageIdentities).mockImplementationOnce(() => new Promise(resolve => { release = resolve }))
    const saved = sampleSnapshot(), pending = downloadValidatedRulePackage(saved, '任务', { isCurrent: () => current })
    current = false; release(identityRegistry(saved))
    expect(await pending).toBe(false)
    expect(downloadBlob).not.toHaveBeenCalled()
  })

  it('keeps archive bytes independent of supporting evidence volume and preserves IDs across sorting/mapping', () => {
    const saved = sampleSnapshot(), before = JSON.stringify(saved), registry = identityRegistry(saved)
    const original = sampleRulePackageTables(saved, registry)
    expect(JSON.stringify(saved)).toBe(before)
    saved.export_sources!.native_snapshot.normalized_route[0].matched_detail_rows = Array.from({ length: 500 }, (_, id) => ({ id, text: '无需随三表交付的证据'.repeat(50) }))
    expect(sampleRulePackageTables(saved, registry)).toEqual(original)
    const pkg = internals(saved)
    pkg.route_catalog.processes.reverse()
    expect(sampleRulePackageTables(saved, registry)).toEqual(original)
    const corrupt = JSON.parse(JSON.stringify(registry))
    corrupt.factors['job.length'] = corrupt.factors['job.material']
    expect(() => sampleRulePackageTables(saved, corrupt)).toThrow('对外编号重复')
  })

  it.each(['roughing', 'finishing'])('recognizes the existing %s phase alias without requiring new metadata', phase => {
    const saved = sampleSnapshot()
    internals(saved).route_catalog.processes[1].phase = phase
    expect(sampleRulePackageTables(saved).full_route_table[1]!.precision).toBe(phase === 'roughing' ? '粗加工' : '精加工')
  })

  it.each([
    ['rough', '热前', '粗加工'], ['semi_finish', '热前', '半精加工'], ['finish', '热后', '精加工'],
    ['roughing', '热前', '粗加工'], ['finishing', '热后', '精加工'],
  ])('exports %s precision from the frozen route when the catalog contains the %s display label', (phase, label, precision) => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    internals(saved).route_catalog.processes[1].phase = label
    snapshot.normalized_route[1].phase = phase
    snapshot.normalized_route.reverse()
    const before = JSON.stringify(saved)
    expect(sampleRulePackageTables(saved).full_route_table[1]!.precision).toBe(precision)
    expect(JSON.stringify(saved)).toBe(before)
  })

  it.each(['export_process_id', 'id'])('matches frozen precision by %s instead of process name or array position', key => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    const process = internals(saved).route_catalog.processes[1]
    process.phase = '热前'
    snapshot.normalized_route = [
      { [key]: 'another-process', normalized_step_name: '钻孔', phase: 'finish' },
      { [key]: process.process_id, normalized_step_name: '钻孔', phase: 'semi_finish',
        ...(key === 'export_process_id' ? { id: 'pre-export-node' } : {}) },
    ]
    expect(sampleRulePackageTables(saved).full_route_table[1]!.precision).toBe('半精加工')
  })

  it('keeps an explicitly confirmed mapping precision ahead of the structured route phase', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    snapshot.template_mapping_route = sampleRulePackageTables(saved).full_route_table
    snapshot.template_mapping_route[1].precision = '半精加工'
    internals(saved).route_catalog.processes[1].phase = '热后'
    snapshot.normalized_route[1].phase = 'finish'
    expect(sampleRulePackageTables(saved).full_route_table[1]!.precision).toBe('半精加工')
  })

  it('still rejects a display label when the matching frozen process has no known precision', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    internals(saved).route_catalog.processes[1].phase = '热前'
    snapshot.normalized_route = [{ export_process_id: 'another-process', phase: 'rough' },
      { export_process_id: 'internal.drill', phase: 'unclassified' }]
    expect(() => sampleRulePackageTables(saved)).toThrow(/缺少已确认加工精度/)
  })

  it.each(['下料', '备料', '下料备料', '下料备料#2', '下料/备料', '下料／备料'])('exports legacy %s as preparation without requiring or inventing machining precision', name => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    const process = internals(saved).route_catalog.processes[0]
    process.display_name = name
    process.phase = '热前'
    snapshot.normalized_route[0] = { export_process_id: process.process_id, normalized_step_name: name,
      step_family: '车削/成形类', phase: 'rough' }
    saved.export_sources!.mother_route[process.process_id].auxiliary = false
    const before = JSON.stringify(saved)
    expect(sampleRulePackageTables(saved).full_route_table[0]).toMatchObject({
      process_name: name, process_type: '辅助工序', precision: '辅助工序', steps: [],
    })
    expect(JSON.stringify(saved)).toBe(before)
  })

  it('does not discard retained steps while correcting a legacy preparation classification', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    const process = internals(saved).route_catalog.processes[1]
    process.display_name = '下料'
    snapshot.normalized_route[1].normalized_step_name = '下料'
    expect(() => sampleRulePackageTables(saved)).toThrow(/辅助工序.*有需保留的工步/)
  })

  it('does not retain a machining precision from a legacy empty preparation mapping row', () => {
    const saved = sampleSnapshot(), snapshot = saved.export_sources!.native_snapshot
    snapshot.template_mapping_route = sampleRulePackageTables(saved).full_route_table
    const process = internals(saved).route_catalog.processes[0]
    process.display_name = snapshot.template_mapping_route[0].process_name = '下料'
    saved.export_sources!.mother_route[process.process_id].auxiliary = false
    snapshot.template_mapping_route[0].process_type = '加工工序'
    snapshot.template_mapping_route[0].precision = '粗加工'
    expect(sampleRulePackageTables(saved).full_route_table[0]).toMatchObject({
      process_type: '辅助工序', precision: '辅助工序', steps: [],
    })
  })
})
