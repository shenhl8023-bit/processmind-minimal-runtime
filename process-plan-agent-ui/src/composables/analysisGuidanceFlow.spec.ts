import defaultGuidanceJson from '../../../process-plan-agent-api/tests/fixtures/confirmed_project_guidance.json?raw'
import { describe, expect, it } from 'vitest'
import { applyGuidedAnswer, buildGuidedDraft, buildGuidedQuestion, recommendedGuidedOptions } from './analysisGuidanceFlow'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import { projectConditionFields } from '@/utils/projectConditionFields'

const config: AnalysisGuidanceConfiguration = {
  schema_version: '1.0', revision: 0, guidance: '', materials: ['9Cr18', '4Cr14Ni14W2Mo'],
  directions: ['A侧', 'B侧', '中间', '周边', '所有方位'],
  feature_mappings: { 孔: ['孔', '孔(盲孔)', '孔(通孔)', '内圆柱面'], 外圆: ['外圆柱面'] },
  operation_guidance: {
    钻孔: { feature_group: '孔', recommendation: { mode: 'condition', basis: 'feature', features: ['孔(盲孔)', '孔(通孔)'], direction: '周边' } },
    磨外圆: { feature_group: '外圆', recommendation: { mode: 'condition', basis: 'precision', features: ['外圆柱面'], direction: '所有方位', it_threshold: 7, ra_threshold: 0.8 } },
    淬火: { recommendation: { mode: 'condition', basis: 'material', materials: ['9Cr18'] } },
    镀铜: { recommendation: { mode: 'manual' } },
    除铜: { recommendation: { mode: 'relation', source_operation_name: '镀铜' } },
  },
}
const segment = (name: string, id = name, sequence = 2): any => ({ id, export_process_id: `export_${id}`, normalized_step_name: name, sequence, doc_coverage: { hit_docs: 1, total_docs: 2 } })
const answer = (nodeId: string, value: string, label = value) => ({ nodeId, value, label })
function recommend(s: any, cfg = config, initial: any = {}, segments: any[] = [s]) {
  let answers = initial
  for (let i = 0; i < 20; i++) {
    const q = buildGuidedQuestion(s, cfg, answers, segments)
    if (!q) break
    const options = recommendedGuidedOptions(q)
    if (!options.length) break
    answers = applyGuidedAnswer(answers, answer(q.id, options.map(o => o.value).join('|'), options.map(o => o.label).join('、')))
  }
  return answers
}

describe('configured professional question flow and executable draft', () => {
  it('confirms finishing features and direction before requesting a precision threshold', () => {
    const s = segment('磨外圆')
    let a: any = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'precision') }
    expect(buildGuidedQuestion(s, config, a, [s])?.id).toBe('guided_features')
    a = applyGuidedAnswer(a, answer('guided_features', '外圆柱面'))
    expect(buildGuidedQuestion(s, config, a, [s])?.id).toBe('guided_direction')
    a = applyGuidedAnswer(a, answer('guided_direction', 'A侧'))
    expect(buildGuidedQuestion(s, config, a, [s])?.id).toBe('guided_it')
    a = applyGuidedAnswer(a, answer('guided_it', '7'))
    const draft = buildGuidedDraft(s, config, a, [s])!
    expect(draft.candidate?.configuration.when.all).toEqual([
      { field: expect.stringMatching(/\.features$/), op: 'contains_any', value: ['外圆柱面'] },
      { field: expect.stringMatching(/\.direction$/), op: 'eq', value: 'A侧' },
      { field: expect.stringMatching(/\.it$/), op: 'lte', value: 7 },
    ])
    const changed = applyGuidedAnswer(a, answer('guided_features', '外圆柱面|其它'))
    expect(changed.guided_direction).toBeUndefined()
    expect(changed.guided_it).toBeUndefined()
  })
  it('keeps the A/B direction range instead of dropping its condition', () => {
    const s = segment('钻孔')
    const a = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'feature'), guided_features: answer('guided_features', '孔(通孔)'), guided_direction: answer('guided_direction', '所有方位') }
    const draft = buildGuidedDraft(s, config, a, [s])!
    expect(draft.candidate?.configuration.when.all[1]).toEqual({ any: [
      { field: expect.stringMatching(/\.direction$/), op: 'eq', value: 'A侧' },
      { field: expect.stringMatching(/\.direction$/), op: 'eq', value: 'B侧' },
    ] })
    expect(draft.condition_text).not.toContain('方位不限')
  })
  it.each(['钻孔', '磨外圆', '淬火', '检验', '未知工序'])('keeps the five root choices for %s despite model labels', name => {
    const s = segment(name)
    const cfg = structuredClone(config)
    cfg.operation_guidance[name] = {
      questions: {
        guided_mode: { prompt: '模型的首问', option_labels: { mainline: '模型固定', manual: '模型手动', condition: '看材料来定', relation: '模型关联', custom: '模型其他' } },
        guided_basis: { prompt: '模型的下级问题', option_labels: { feature: '模型特征', precision: '模型精度', material: '模型材料', requirement: '模型要求' } },
      }, recommendation: { mode: 'condition' },
    }
    const q = buildGuidedQuestion(s, cfg, {}, [s])!
    expect(q.prompt).toBe('模型的首问')
    expect(q.options).toEqual([
      { value: 'mainline', label: '设置为主工序，在路线中固定出现' },
      { value: 'manual', label: '由用户决定是否出现' },
      { value: 'condition', label: '根据条件设置' },
      { value: 'relation', label: '与其他工序关联' },
      { value: 'custom', label: '其他' },
    ])
    expect(recommendedGuidedOptions(q)).toEqual([{ value: 'condition', label: '根据条件设置' }])
    const lower = buildGuidedQuestion(s, cfg, { guided_mode: answer('guided_mode', 'condition'), ...(name === '磨外圆' ? { guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') } : {}) }, [s])!
    expect(lower.prompt).toBe('模型的下级问题')
    expect(lower.options[0]?.label).toMatch(/^模型/)
  })

  it('displays duplicate source names while binding exclusively to the selected stable node ID', () => {
    const first = segment('镀铜', 'c1', 1), second = segment('镀铜', 'c2', 2), s = segment('除铜', 'd', 3)
    const segments = [first, second, s]
    const initial = { guided_mode: answer('guided_mode', 'relation') }
    const cfg = structuredClone(config)
    cfg.operation_guidance.除铜!.questions = { guided_source: { prompt: '模型关联问题', option_labels: { export_c1: '镀铜（第1道）' } } }
    const q = buildGuidedQuestion(s, cfg, initial, segments)!
    expect(q.options).toEqual([{ value: 'export_c1', label: '镀铜' }, { value: 'export_c2', label: '镀铜' }])
    expect(recommendedGuidedOptions(q)).toEqual([])
    expect(buildGuidedDraft(s, cfg, { ...initial, guided_source: answer('guided_source', '镀铜') }, segments)).toBeNull()
    const draft = buildGuidedDraft(s, cfg, { ...initial, guided_source: answer('guided_source', 'export_c2') }, segments)!
    expect(draft.candidate?.configuration.relations[0]?.source_process_ids).toEqual(['export_c2'])
    cfg.operation_guidance.除铜!.recommendation!.source_segment_id = 'c2'
    expect(recommendedGuidedOptions(buildGuidedQuestion(s, cfg, initial, segments)!)).toEqual([{ value: 'export_c2', label: '镀铜' }])
  })

  it.each([
    ['钻孔', 'feature', { guided_features: '孔', guided_direction: '周边' }, ['加工对象的特征', '同一加工对象的方位']],
    ['磨外圆', 'precision', { guided_features: '外圆柱面', guided_direction: 'A侧', guided_it: '7' }, ['加工对象的特征', '同一加工对象的方位', '外圆柱面的实际尺寸精度等级']],
    ['磨外圆', 'roughness', { guided_features: '外圆柱面', guided_direction: 'A侧', guided_ra: '0.8' }, ['加工对象的特征', '同一加工对象的方位', '外圆柱面的实际Ra要求值']],
    ['淬火', 'hardness', { guided_hardness_unit: 'HRC', guided_hardness_min: '40', guided_hardness_max: '50' }, ['目标硬度单位', '目标硬度下限（含）', '目标硬度上限（含）']],
  ])('generates neutral %s/%s labels with scoped field identities', (name, basis, values, labels) => {
    const s = segment(name)
    const answers: any = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', basis) }
    for (const [id, v] of Object.entries(values)) answers[id] = answer(id, v)
    const fields = buildGuidedDraft(s, config, answers, [s])!.candidate?.field_definitions || []
    expect(fields.map((field: any) => field.label)).toEqual(labels)
    expect(fields.every((field: any) => field.key.startsWith('project_factor.operation_') && field.source.includes(`工序=export_${name}`))).toBe(true)
  })
  it('uses exact occurrence recommendations including the first auxiliary node', () => {
    const cfg = structuredClone(config)
    cfg.operation_guidance = { '检验#1': { recommendation: { mode: 'manual' } }, '检验#2': { recommendation: { mode: 'mainline' } } }
    const first = segment('检验', 'i1', 1), second = segment('检验', 'i2', 5)
    expect(recommend(first, cfg, {}, [first, second]).guided_mode.value).toBe('manual')
    expect(recommend(second, cfg, {}, [first, second]).guided_mode.value).toBe('mainline')
  })
  it('requires the custom editor to save a valid current-process rule before completing', () => {
    const s = segment('钻孔')
    const initial = { guided_mode: answer('guided_mode', 'custom') }
    expect(buildGuidedQuestion(s, config, initial, [s])?.customEditor).toBe(true)
    expect(buildGuidedDraft(s, config, { ...initial, guided_custom: answer('guided_custom', '{}') }, [s])).toBeNull()
    const candidate = { kind: 'process_configuration', configuration: { process_id: 'export_钻孔', occurrence: 'always', when: null, relations: [] }, preview: '固定安排钻孔' }
    expect(buildGuidedDraft(s, config, { ...initial, guided_custom: answer('guided_custom', JSON.stringify(candidate)) }, [s])?.candidate).toEqual(candidate)
  })
  it('uses exactly the configured recommended feature subset, then one direction, on the same operation object', () => {
    const s = segment('钻孔')
    const a = recommend(s)
    expect(a.guided_features.value).toBe('孔(盲孔)|孔(通孔)')
    expect(a.guided_direction.value).toBe('周边')
    const draft = buildGuidedDraft(s, config, a, [s])!
    expect(draft.status).toBe('confirmed')
    expect(draft.candidate?.configuration.process_id).toBe('export_钻孔')
    expect(draft.candidate?.configuration.when.all).toHaveLength(2)
    expect(draft.candidate?.configuration.when.all[0]).toMatchObject({ op: 'contains_any', value: ['孔(盲孔)', '孔(通孔)'] })
    const fields = draft.candidate?.field_definitions || []
    expect(fields[0].key.split('.').slice(0, -1)).toEqual(fields[1].key.split('.').slice(0, -1))
    expect(fields.every((f: any) => f.source.includes('同一加工对象'))).toBe(true)
  })
  it('does not invent recommendations for unknown operations or choose the first candidate', () => {
    const s = segment('未知工序')
    const q = buildGuidedQuestion(s, config, {}, [s])!
    expect(recommendedGuidedOptions(q)).toEqual([])
    expect(buildGuidedDraft(s, config, recommend(s), [s])).toBeNull()
  })
  it('keeps a manually chosen different mode when adopting the remaining recommendations', () => {
    const s = segment('钻孔')
    const a = recommend(s, config, { guided_mode: answer('guided_mode', 'manual') })
    expect(a.guided_mode.value).toBe('manual')
    expect(a.guided_features).toBeUndefined()
    expect(buildGuidedDraft(s, config, a, [s])?.candidate?.configuration.occurrence).toBe('manual')
  })
  it('offers editable Ra <= 0.8 without replacing the IT7 recommendation or accepting invalid thresholds', () => {
    const s = segment('磨外圆')
    expect(recommend(s).guided_it.value).toBe('7')
    const a = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'roughness'), guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') }
    const q = buildGuidedQuestion(s, config, a, [s])!
    expect(q.numeric).toMatchObject({ min: 0, exclusiveMin: true, unit: 'μm' })
    expect(recommendedGuidedOptions(q)[0]?.value).toBe('0.8')
    for (const bad of ['0', '-1', 'NaN', 'Infinity', 'abc']) {
      expect(buildGuidedDraft(s, config, { ...a, guided_ra: answer('guided_ra', bad) }, [s])).toBeNull()
    }
    const draft = buildGuidedDraft(s, config, { ...a, guided_ra: answer('guided_ra', '0.4') }, [s])!
    expect(draft.candidate?.configuration.when.all[2]).toMatchObject({ op: 'lte', value: 0.4 })
    expect(draft.candidate?.field_definitions[2].label).toContain('外圆柱面')
    expect(draft.condition_text).toContain('0.4')
  })
  it('uses only the current operation explicit requirement; copper has no protection condition', () => {
    const s = segment('淬火')
    const a = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'requirement'), guided_requirement: answer('guided_requirement', 'true') }
    const d = buildGuidedDraft(s, config, a, [s])!
    expect(d.candidate?.field_definitions[0].label).toBe('当前部位是否有明确淬火要求')
    const copper = segment('镀铜')
    expect(buildGuidedDraft(copper, config, recommend(copper), [copper])?.candidate?.configuration.occurrence).toBe('manual')
    expect(JSON.stringify(buildGuidedQuestion(copper, config, { guided_mode: answer('guided_mode', 'condition') }, [copper]))).not.toContain('保护')
  })
  it('keeps each type on its agreed factor directions', () => {
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    const drill = segment('钻孔')
    expect(buildGuidedQuestion(drill, config, mode, [drill])!.options.map(o => o.value)).toEqual(['feature'])
    const grinding = segment('磨外圆')
    expect(buildGuidedQuestion(grinding, config, { ...mode, guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') }, [grinding])!.options.map(o => o.value)).toEqual(['precision', 'roughness'])
    const heat = segment('淬火')
    expect(buildGuidedQuestion(heat, config, mode, [heat])!.options.map(o => o.value)).toEqual(['material', 'hardness', 'requirement'])
  })
  it('retains the recommended feature and direction for rough 挖槽去毛刺', () => {
    const s = { ...segment('挖槽去毛刺'), phase: 'rough' }
    const cfg = structuredClone(config)
    cfg.feature_mappings.槽 = ['槽', '直槽']
    cfg.operation_guidance.挖槽去毛刺 = { feature_group: '槽', recommendation: { mode: 'condition', basis: 'feature', features: ['直槽'], direction: '周边' } }
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, cfg, mode, [s])!.options.map(o => o.value)).toEqual(['feature'])
    const a = recommend(s, cfg)
    expect(a.guided_features.value).toBe('直槽')
    expect(a.guided_direction.value).toBe('周边')
    const draft = buildGuidedDraft(s, cfg, a, [s])!
    expect(draft).toMatchObject({ status: 'confirmed', candidate: { configuration: { occurrence: 'conditional' } } })
    expect(draft.candidate?.configuration.when.all).toEqual([
      { field: expect.stringMatching(/\.features$/), op: 'contains_any', value: ['直槽'] },
      { field: expect.stringMatching(/\.direction$/), op: 'eq', value: '周边' },
    ])
    expect(draft.candidate?.field_definitions.map((field: any) => field.label)).toEqual(['加工对象的特征', '同一加工对象的方位'])
  })
  it.each([
    ['precision', 'guided_it', '7', 7],
    ['roughness', 'guided_ra', '0.4', 0.4],
  ])('uses %s for finish-phase 精车 without a grinding name', (basis, id, choice, expected) => {
    const s = { ...segment('精车'), phase: 'finish' }
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    const cfg = { ...config, operation_guidance: { ...config.operation_guidance, 精车: { feature_group: '外圆' } } }
    expect(buildGuidedQuestion(s, cfg, { ...mode, guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') }, [s])!.options.map(o => o.value)).toEqual(['precision', 'roughness'])
    const a = { ...mode, guided_basis: answer('guided_basis', basis), guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') }
    expect(buildGuidedQuestion(s, cfg, a, [s])?.id).toBe(id)
    expect(buildGuidedDraft(s, config, a, [s])).toBeNull()
    const draft = buildGuidedDraft(s, cfg, { ...a, [id]: answer(id, choice) }, [s])!
    expect(draft.candidate?.configuration.when.all[2]).toMatchObject({ op: 'lte', value: expected })
    expect(draft.candidate?.field_definitions).toHaveLength(3)
  })
  it.each([
    ['下料', 'rough'], ['备料', 'rough'], ['下料备料#2', 'rough'],
    ['研顶尖孔', 'finish'], ['研顶尖孔', 'rough'],
    ['清洗', 'auxiliary'], ['随件处理', 'auxiliary'], ['终检', 'inspection'],
  ])('keeps %s/%s on explicit requirements even with a feature group', (name, phase) => {
    const s = { ...segment(name), phase }
    const cfg = structuredClone(config)
    cfg.operation_guidance[name] = { feature_group: '孔' }
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, cfg, mode, [s])!.options.map(o => o.value)).toEqual(['requirement'])
    const a = { ...mode, guided_basis: answer('guided_basis', 'requirement') }
    expect(buildGuidedQuestion(s, cfg, a, [s])?.id).toBe('guided_requirement')
    expect(buildGuidedDraft(s, cfg, a, [s])).toBeNull()
    for (const [choice, expected] of [['true', true], ['false', false]] as const) {
      const draft = buildGuidedDraft(s, cfg, { ...a, guided_requirement: answer('guided_requirement', choice) }, [s])!
      expect(draft).toMatchObject({ status: 'confirmed', candidate: { configuration: { occurrence: 'conditional', when: { op: 'eq', value: expected } } } })
      expect(draft.candidate?.field_definitions).toHaveLength(1)
      expect(draft.candidate?.field_definitions[0]).toMatchObject({ type: 'boolean', label: `当前部位是否有明确${name}要求` })
    }
  })
  it.each([
    ['淬火', 'rough', ['material', 'hardness', 'requirement']],
    ['镀铜', 'rough', ['material', 'requirement']],
    ['磨外圆', 'rough', ['precision', 'roughness']],
    ['挖槽去毛刺', 'unknown', ['requirement']],
    ['精车', 'unknown', ['feature']],
    ['未知加工', 'unknown', ['feature']],
  ])('preserves name-based condition bases for %s/%s', (name, phase, bases) => {
    const s = { ...segment(name), phase }
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, config, { ...mode, ...(name === '磨外圆' ? { guided_features: answer('guided_features', '外圆柱面'), guided_direction: answer('guided_direction', 'A侧') } : {}) }, [s])!.options.map(o => o.value)).toEqual(bases)
  })
  it.each(['下料', '备料', '下料备料', '下料准备', '开料', '切料', '下料/备料', '下料／备料', '下料（锯床）', '下料/备料（锯床）', '下料准备（锯床）', '下料#1', '备料#2', '下料备料#12'])('offers requirement-only conditional preparation drafts for %s without choosing mainline', name => {
    const s = segment(name, name, 1)
    s.doc_coverage = { hit_docs: 19, total_docs: 20 }
    expect(recommendedGuidedOptions(buildGuidedQuestion(s, config, {}, [s])!)).toEqual([])
    expect(buildGuidedDraft(s, config, recommend(s), [s])).toBeNull()
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, config, mode, [s])!.options.map(o => o.value)).toEqual(['requirement'])
    expect(buildGuidedDraft(s, config, mode, [s])).toBeNull()
    const a = applyGuidedAnswer(mode, answer('guided_basis', 'requirement'))
    const q = buildGuidedQuestion(s, config, a, [s])!
    expect(q.id).toBe('guided_requirement')
    expect(q.options.map(o => o.value)).toEqual(['true', 'false'])
    expect(buildGuidedDraft(s, config, a, [s])).toBeNull()
    expect(buildGuidedDraft(s, config, { ...a, guided_requirement: answer('guided_requirement', 'yes') }, [s])).toBeNull()
    for (const [choice, expected] of [['true', true], ['false', false]] as const) {
      const answered = applyGuidedAnswer(a, answer('guided_requirement', choice))
      expect(buildGuidedQuestion(s, config, answered, [s])).toBeNull()
      const draft = buildGuidedDraft(s, config, answered, [s])!
      expect(draft).toMatchObject({ status: 'confirmed', missing: [], candidate: { kind: 'process_configuration', configuration: { process_id: `export_${name}`, occurrence: 'conditional', relations: [] } } })
      const fields = draft.candidate?.field_definitions || []
      expect(fields).toHaveLength(1)
      expect(fields[0]).toMatchObject({ label: `当前部位是否有明确${name}要求`, type: 'boolean', operators: ['eq', 'neq'] })
      expect(fields[0]!.key).toMatch(/^project_factor\.operation_[0-9a-f]+\.requirement$/)
      expect(draft.candidate?.configuration.when).toEqual({ field: fields[0]!.key, op: 'eq', value: expected })
    }
  })
  it.each(['下料/钻孔#2', '钻孔／备料#2', '下料备料/钻孔', '下料加工', '备料加工', '钻镗孔', '未知加工', '下料#x'])('keeps feature candidate validation for non-preparation %s', name => {
    const s = segment(name)
    const cfg = { ...config, feature_mappings: {}, operation_guidance: {} }
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, cfg, mode, [s])!.options.map(o => o.value)).toEqual(['feature'])
    const a = { ...mode, guided_basis: answer('guided_basis', 'feature'), guided_features: answer('guided_features', '孔'), guided_direction: answer('guided_direction', '周边') }
    expect(buildGuidedQuestion(s, cfg, a, [s])).toMatchObject({ id: 'guided_features', options: [] })
    expect(buildGuidedDraft(s, cfg, a, [s])).toBeNull()
    expect(buildGuidedDraft(s, cfg, { ...mode, guided_basis: answer('guided_basis', 'requirement'), guided_requirement: answer('guided_requirement', 'true') }, [s])).toBeNull()
  })
  it('offers copper removal material and its own requirement, matching the fourth step', () => {
    const s = segment('除铜')
    const mode = { guided_mode: answer('guided_mode', 'condition') }
    expect(buildGuidedQuestion(s, config, mode, [s])!.options.map(o => o.value)).toEqual(['material', 'requirement'])
    const fields = projectConditionFields('export_除铜', '除铜', config)
    expect(fields.map(field => field.key.split('.').pop())).toEqual(['features', 'direction', 'it', 'ra', 'material_grade', 'hardness_unit', 'hardness_min', 'hardness_max', 'requirement'])
    const material = buildGuidedDraft(s, config, { ...mode, guided_basis: answer('guided_basis', 'material'), guided_material_scope: answer('guided_material_scope', 'material_scope::grade::9Cr18') }, [s])!
    expect(material.candidate?.configuration.when).toEqual({ field: 'project_factor.material_grade', op: 'in', value: ['9Cr18'] })
    const requirement = buildGuidedDraft(s, config, { ...mode, guided_basis: answer('guided_basis', 'requirement'), guided_requirement: answer('guided_requirement', 'false') }, [s])!
    expect(requirement.candidate?.configuration.when).toMatchObject({ op: 'eq', value: false })
    expect(requirement.candidate?.field_definitions[0].label).toBe('当前部位是否有明确除铜要求')
  })
  it('binds a relation to one earlier actual node and retains the current original position', () => {
    const copper = segment('镀铜', 'c1', 3), laterCopper = segment('镀铜', 'c2', 9), s = segment('除铜', 'd', 7)
    const d = buildGuidedDraft(s, config, recommend(s, config, {}, [copper, s, laterCopper]), [copper, s, laterCopper])!
    expect(d.candidate?.configuration.relations[0]).toMatchObject({ source_process_ids: ['export_c1'], target_process_ids: ['export_d'], relation_type: 'trigger_after' })
    expect(s.sequence).toBe(7)
    expect(buildGuidedDraft(s, config, { guided_mode: answer('guided_mode', 'relation'), guided_source: answer('guided_source', 'export_c2') }, [copper, s, laterCopper])).toBeNull()
  })
  it('retains independent answers while clearing only invalid dependent branches', () => {
    const old = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'precision'), guided_it: answer('guided_it', '7'), merge_name_root: answer('merge_name_root', 'x'), unrelated: answer('unrelated', 'keep') }
    const changed = applyGuidedAnswer(old, answer('guided_basis', 'roughness'))
    expect(changed.guided_it).toBeUndefined()
    expect(changed.merge_name_root).toEqual(old.merge_name_root)
    expect(changed.unrelated).toEqual(old.unrelated)
    expect(changed.guided_mode).toEqual(old.guided_mode)
  })
  it('requires hardness units and whole interval containment, never mere overlap', () => {
    const s = segment('淬火')
    const a = { guided_mode: answer('guided_mode', 'condition'), guided_basis: answer('guided_basis', 'hardness'), guided_hardness_unit: answer('guided_hardness_unit', 'HRC'), guided_hardness_min: answer('guided_hardness_min', '40'), guided_hardness_max: answer('guided_hardness_max', '50') }
    const d = buildGuidedDraft(s, config, a, [s])!
    expect(d.candidate?.configuration.when.all).toEqual(expect.arrayContaining([expect.objectContaining({ op: 'gte', value: 40 }), expect.objectContaining({ op: 'lte', value: 50 }), expect.objectContaining({ op: 'eq', value: 'HRC' })]))
    expect(buildGuidedDraft(s, config, { ...a, guided_hardness_max: answer('guided_hardness_max', '39') }, [s])).toBeNull()
  })
})

it('completes the confirmed 41-node project with the actual backend default configuration', async () => {
  const cfg = JSON.parse(defaultGuidanceJson) as AnalysisGuidanceConfiguration
  const names = ['下料备料','正常化','调质','车削加工（A侧）','车削加工（B侧）','铣扁','钻孔','钻铰孔','铣槽','标记','去毛刺','清洗','检验','去应力','磨孔','珩孔','磨外圆','磨端面','磨槽','去毛刺','清洗','检验','淬火','镀铜','铬酸阳极化','渗氮','除铜','硬质阳极化','无损检查','烧伤检查','打孔','割型孔','割扁','打型孔','去毛刺','研顶尖孔','研孔','研外圆','清洗','检验','包装']
  const segments = names.map((name, i) => segment(name, `node_${i + 1}`, i + 1))
  const drafts = segments.map(s => buildGuidedDraft(s, cfg, recommend(s, cfg, {}, segments), segments))
  expect(drafts.map((d,i) => d ? null : `${i+1}:${names[i]}`).filter(Boolean)).toEqual([])
  expect(drafts[26]?.candidate?.configuration.relations[0]?.source_process_ids).toEqual(['export_node_24'])
  expect(drafts[19]?.candidate?.configuration.occurrence).toBe('always')
  expect(drafts[38]?.candidate?.configuration.occurrence).toBe('always')
  expect(drafts[16]?.candidate?.configuration.when.all[2]).toMatchObject({ op: 'lte', value: 7 })
  expect(drafts[36]?.candidate?.configuration.when.all[2]).toMatchObject({ op: 'lte', value: 6 })
})
