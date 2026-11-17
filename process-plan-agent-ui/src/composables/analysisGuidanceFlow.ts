import type { AnalysisGuidanceConfiguration, OperationRecommendation } from '@/api/analysisGuidance'
import type { SavedNormalizedRouteSegment, SegmentRuleReview } from '@/api/extract'
import type { CanonicalConditionField, RuleConditionCandidate, RulePackageCondition } from '@/api/rulePackages'
import type { TreeAnswer } from './analysisQuestionTreeState'
import { segmentGuidanceKey } from './analysisQuestionTreeState'
import type { TreeNode } from './analysisQuestionTreeNodes'
import { buildManualBooleanRuleCandidate } from '@/utils/finalizeRulePackage'
import { validateAuthoredCandidate } from '@/utils/processConfigurationEditor'
import { isMaterialPreparationProcess } from './finalRouteSteps'
import questionContract from '../../../process-plan-agent-api/app/assets/analysis_question_contract.json'
import { resolveConfirmedObject, type ConfirmedMachiningObject } from './analysisGuidedObjects'

type Segment = SavedNormalizedRouteSegment
type Answers = Record<string, TreeAnswer>
type Draft = NonNullable<SegmentRuleReview['analysis_draft']>
export interface GuidedQuestion extends TreeNode {
  recommendedValues?: string[]
  numeric?: { min: number; max?: number; exclusiveMin?: boolean; integer?: boolean; unit: string }
  customEditor?: boolean
}
const value = (answers: Answers, key: string) => answers[key]?.value || ''
const list = (text: string) => text.split('|').filter(Boolean)
export const guidedProcessId = (s: Segment) => s.export_process_id || s.id
export function guidedOperationKey(s: Segment, segments: Segment[]) {
  const same = segments.filter(item => item.normalized_step_name === s.normalized_step_name)
  const index = same.findIndex(item => item.id === s.id)
  return `${s.normalized_step_name}#${Math.max(0, index) + 1}`
}
export function guidanceForSegment(s: Segment, c: AnalysisGuidanceConfiguration, segments: Segment[]) {
  return c.operation_guidance[guidedOperationKey(s, segments)] || c.operation_guidance[s.normalized_step_name]
}
/** Restore frozen identity before looking up a renamed or repeated operation. */
export function resolveGuidanceOperation(s: Segment, c: AnalysisGuidanceConfiguration, answers: Answers, segments: Segment[], frozen = false) {
  const bound = c.operation_guidance[segmentGuidanceKey(s.id)]
  if (bound) return bound
  if (frozen && answers.merge_name_root) {
    const identities = [...new Set((s.source_nodes || []).map(name => name.trim()))]
      .filter(key => /[／/]/.test(key) && c.operation_guidance[key])
    if (identities.length) return identities.length === 1 ? c.operation_guidance[identities[0]!] : null
    const sources = new Set((s.source_operation_names?.length ? s.source_operation_names : s.source_nodes || []).map(name => name.trim()))
    const matches = Object.entries(c.operation_guidance).filter(([key]) => {
      const parts = key.replace(/#\d+$/, '').split(/[／/]/).map(name => name.trim())
      return parts.length > 1 && new Set(parts).size === sources.size && parts.every(name => sources.has(name))
    })
    return matches.length === 1 ? matches[0]![1] : null
  }
  return guidanceForSegment(s, c, segments)
}
function processScope(s: Segment) {
  let hash = 2166136261
  for (const char of guidedProcessId(s)) hash = Math.imul(hash ^ char.charCodeAt(0), 16777619)
  return `project_factor.operation_${(hash >>> 0).toString(16).padStart(8, '0')}`
}
function numericValid(text: string, min: number, max = Infinity, exclusive = false, integer = false) {
  if (!text.trim()) return false
  const n = Number(text)
  return Number.isFinite(n) && (exclusive ? n > min : n >= min) && n <= max && (!integer || Number.isInteger(n))
}
function featureGroup(s: Segment, c: AnalysisGuidanceConfiguration, segments: Segment[]) {
  const explicit = guidanceForSegment(s, c, segments)?.feature_group
  if (explicit) return explicit
  return Object.keys(c.feature_mappings).filter(key => key.split('/').some(alias => s.normalized_step_name.includes(alias))).sort((a, b) => b.length - a.length)[0] || ''
}
function priorSegments(s: Segment, segments: Segment[]) {
  const index = segments.findIndex(item => item.id === s.id)
  return index >= 0 ? segments.slice(0, index) : segments.filter(item => item.sequence < s.sequence)
}
function recommendation(s: Segment, c: AnalysisGuidanceConfiguration, segments: Segment[]): OperationRecommendation | undefined {
  return guidanceForSegment(s, c, segments)?.recommendation
}
function question(id: string, prompt: string, options: string[] | Array<{ value: string; label: string }>, recommendedValues: string[] = [], extra: Partial<GuidedQuestion> = {}): GuidedQuestion {
  return { id, title: '工序安排', prompt, options: options.map(o => typeof o === 'string' ? { value: o, label: o } : o), recommendedValues, ...extra }
}
function numericQuestion(id: string, prompt: string, numbers: number[], recommended: number | undefined, unit: string, max?: number): GuidedQuestion {
  const candidates = [...new Set([...numbers, ...(recommended === undefined ? [] : [recommended])])].sort((a, b) => a - b)
  return question(id, prompt, candidates.map(n => ({ value: String(n), label: `${unit === 'IT' ? 'IT' : ''}${n}${unit === 'μm' ? ' μm' : ''}` })), recommended === undefined ? [] : [String(recommended)], {
    numeric: { min: unit === 'IT' ? 1 : 0, max, exclusiveMin: unit === 'μm', integer: unit === 'IT', unit },
  })
}

export function resolveGuidedObject(s: Segment, c: AnalysisGuidanceConfiguration, a: Answers, segments: Segment[], prior: ConfirmedMachiningObject[] = []) {
  if (value(a, 'guided_mode') !== 'condition') return { answers: a, reuse: undefined, hint: '' }
  return resolveConfirmedObject(a, c.feature_mappings[featureGroup(s, c, segments)] || [], c.directions, prior, recommendation(s, c, segments))
}

export function confirmedGuidedObject(s: Segment, c: AnalysisGuidanceConfiguration, a: Answers, segments: Segment[], prior: ConfirmedMachiningObject[]): ConfirmedMachiningObject | null {
  if (value(a, 'guided_mode') !== 'condition') return null
  const finishing = (s.phase === 'finish' || /磨|珩|研/.test(s.normalized_step_name)) && !/顶尖/.test(s.normalized_step_name)
  if (!['feature', 'precision', 'roughness'].includes(value(a, 'guided_basis')) && !(finishing && !value(a, 'guided_basis'))) return null
  const resolved = resolveGuidedObject(s, c, a, segments, prior).answers
  const features = list(value(resolved, 'guided_features'))
  if (!features.length || !features.every(v => (c.feature_mappings[featureGroup(s, c, segments)] || []).includes(v))) return null
  const direction = value(resolved, 'guided_direction')
  return { segmentId: s.id, name: s.normalized_step_name, features, ...(c.directions.includes(direction) ? { direction } : {}) }
}

export function buildGuidedQuestion(s: Segment, c: AnalysisGuidanceConfiguration, a: Answers, segments: Segment[], prior: ConfirmedMachiningObject[] = []): GuidedQuestion | null {
  const resolved = resolveGuidedObject(s, c, a, segments, prior)
  const question = buildBaseGuidedQuestion(s, c, resolved.answers, segments)
  if (!question) return null
  const operation = guidanceForSegment(s, c, segments)
  const text = operation?.questions?.[question.id]
  return {
    ...question,
    ...(text?.prompt ? { prompt: text.prompt } : {}),
    // System choices and node identity labels remain stable even in frozen model text.
    options: question.options.map(option => ({ ...option, label: ['guided_mode', 'guided_source'].includes(question.id) ? option.label : text?.option_labels?.[option.value] || option.label })),
    sourceHint: [resolved.hint, question.sourceHint, ...(operation?.recommendation_issues || [])].filter(Boolean).join(' '),
  }
}

function buildBaseGuidedQuestion(s: Segment, c: AnalysisGuidanceConfiguration, a: Answers, segments: Segment[]): GuidedQuestion | null {
  const name = s.normalized_step_name
  const rec = recommendation(s, c, segments)
  const mode = value(a, 'guided_mode')
  if (!questionContract.opening_options.some(option => option.value === mode)) return question('guided_mode', /检验|清洗|去毛刺/.test(name) ? `到这一步，${name}你一般怎么安排？` : `这类零件，${name}这一步你一般怎么安排？`, questionContract.opening_options, rec ? [rec.mode] : [], { sourceHint: guidanceForSegment(s, c, segments)?.instruction || '沿用母路线中的当前工序及位置，只确定出现方式。' })
  if (mode === 'mainline' || mode === 'manual') return null
  if (mode === 'custom') {
    if (readCustomCandidate(s, a)) return null
    return question('guided_custom', `自行设置${name}的出现规则，保存并确认后完成。`, [], [], { customEditor: true })
  }
  if (mode === 'relation') {
    const prior = priorSegments(s, segments)
    const sources = prior.map(item => ({ value: guidedProcessId(item), label: item.normalized_step_name }))
    if (sources.some(o => o.value === value(a, 'guided_source'))) return null
    const matches = prior.filter(item => rec?.source_segment_id ? item.id === rec.source_segment_id : item.normalized_step_name === rec?.source_operation_name)
    return question('guided_source', `这道${name}跟随哪一道前序工序？`, sources, matches.length === 1 ? [guidedProcessId(matches[0]!)] : [], { sourceHint: '只选一个来源；来源纳入路线时带出当前工序，保留母路线原位置。' })
  }
  const basis = value(a, 'guided_basis')
  const group = featureGroup(s, c, segments)
  const finishing = (s.phase === 'finish' || /磨|珩|研/.test(name)) && !/顶尖/.test(name)
  const heat = /淬火|调质|回火|渗氮|去应力|正常化|退火|正火|热处理/.test(name)
  const surface = /镀|除铜|阳极|氧化|磷化|发黑|喷|钝化/.test(name)
  const preparation = isMaterialPreparationProcess(s)
  const auxiliary = preparation || /顶尖/.test(name) || s.phase === 'auxiliary' || s.phase === 'inspection'
    || (s.phase !== 'rough' && /检验|检查|清洗|去毛刺|标记|包装/.test(name))
  const bases = finishing
    ? [{ value: 'precision', label: '看尺寸精度等级' }, { value: 'roughness', label: '看表面粗糙度要求' }]
    : heat || surface || auxiliary
      ? [
          ...(!auxiliary ? [{ value: 'material', label: '看材料牌号' }] : []),
          ...(heat ? [{ value: 'hardness', label: '看要求的硬度范围' }] : []),
          { value: 'requirement', label: `看当前部位有没有明确的${name}要求` },
        ]
      : [{ value: 'feature', label: '看加工特征和方位' }]
  if (finishing || ['feature', 'precision', 'roughness'].includes(basis)) {
    const features = c.feature_mappings[group] || []
    const suggested = rec?.features?.length ? rec.features : features.length === 1 ? features : []
    if (!list(value(a, 'guided_features')).length || !list(value(a, 'guided_features')).every(v => features.includes(v))) return question('guided_features', `哪些特征要用到这道${name}？`, features, suggested, { multiple: true, minSelections: 1, confirmLabel: '确认特征', sourceHint: '可选多个，有其中一种就满足；接下来再确定加工方位。' })
    if (!c.directions.includes(value(a, 'guided_direction'))) return question('guided_direction', '这些特征位于同一加工对象的哪个方位？', c.directions, rec?.direction ? [rec.direction] : [], { sourceHint: '特征与方位必须属于同一加工对象；所有方位仅表示A侧或B侧任一侧满足。' })
  }
  if (!bases.some(o => o.value === basis)) return question('guided_basis', `什么因素决定这道${name}需要做？`, bases, rec?.basis ? [rec.basis] : [])
  if (basis === 'precision' && !numericValid(value(a, 'guided_it'), 1, 18, false, true)) return numericQuestion('guided_it', `${list(value(a, 'guided_features')).join('、')}的尺寸精度达到IT多少及更高精度时，需要${name}？`, [6, 7, 8, 9], rec?.it_threshold, 'IT', 18)
  if (basis === 'roughness' && !numericValid(value(a, 'guided_ra'), 0, Infinity, true)) return numericQuestion('guided_ra', `同一加工对象的实际Ra要求值小于等于多少 μm 时，需要${name}？`, [0.2, 0.4, 0.8, 1.6], rec?.ra_threshold ?? (/磨/.test(name) ? 0.8 : undefined), 'μm')
  if (basis === 'material' && !list(value(a, 'guided_material_scope')).length) return question('guided_material_scope', `哪些材料牌号必须安排${name}？`, c.materials.map(m => ({ value: `material_scope::grade::${m}`, label: m })), rec?.materials?.map(m => `material_scope::grade::${m}`) || [], { multiple: true, minSelections: 1, confirmLabel: '确认材料' })
  if (basis === 'requirement' && !['true', 'false'].includes(value(a, 'guided_requirement'))) return question('guided_requirement', `当前部位是否有明确${name}要求时安排？`, [{ value: 'true', label: `有明确${name}要求时安排` }, { value: 'false', label: `明确没有${name}要求时安排` }], rec?.basis === 'requirement' ? ['true'] : [])
  if (basis === 'hardness') {
    if (!['HRC', 'HBW', 'HV', 'HRB'].includes(value(a, 'guided_hardness_unit'))) return question('guided_hardness_unit', '目标硬度使用哪种单位？', ['HRC', 'HBW', 'HV', 'HRB'])
    if (!numericValid(value(a, 'guided_hardness_min'), 0)) return numericQuestion('guided_hardness_min', '目标硬度适用范围的下限是多少？（含下限）', [], undefined, value(a, 'guided_hardness_unit'))
    if (!numericValid(value(a, 'guided_hardness_max'), Number(value(a, 'guided_hardness_min')))) return { ...numericQuestion('guided_hardness_max', '目标硬度适用范围的上限是多少？（含上限）', [], undefined, value(a, 'guided_hardness_unit')), numeric: { min: Number(value(a, 'guided_hardness_min')), unit: value(a, 'guided_hardness_unit') } }
  }
  return null
}

export function recommendedGuidedOptions(q: GuidedQuestion) {
  const values = q.recommendedValues || []
  return q.options.filter(o => values.includes(o.value))
}
const dependents: Record<string, string[]> = {
  guided_mode: ['guided_basis', 'guided_features', 'guided_direction', 'guided_it', 'guided_ra', 'guided_material_scope', 'guided_requirement', 'guided_hardness_unit', 'guided_hardness_min', 'guided_hardness_max', 'guided_source', 'guided_custom'],
  guided_basis: ['guided_it', 'guided_ra', 'guided_material_scope', 'guided_requirement', 'guided_hardness_unit', 'guided_hardness_min', 'guided_hardness_max'],
  guided_features: ['guided_direction', 'guided_it', 'guided_ra'],
  guided_direction: ['guided_it', 'guided_ra'],
  guided_hardness_unit: ['guided_hardness_min', 'guided_hardness_max'],
  guided_hardness_min: ['guided_hardness_max'],
}
export function applyGuidedAnswer(answers: Answers, answer: TreeAnswer): Answers {
  const next = { ...answers }
  if (answers[answer.nodeId]?.value !== answer.value) for (const id of dependents[answer.nodeId] || []) delete next[id]
  next[answer.nodeId] = answer
  return next
}
function readCustomCandidate(s: Segment, a: Answers): RuleConditionCandidate | null {
  try {
    const candidate = JSON.parse(value(a, 'guided_custom')) as RuleConditionCandidate
    return candidate && !validateAuthoredCandidate(candidate, guidedProcessId(s)).length ? candidate : null
  } catch { return null }
}
export function buildGuidedDraft(s: Segment, c: AnalysisGuidanceConfiguration, a: Answers, segments: Segment[], prior: ConfirmedMachiningObject[] = []): Draft | null {
  if (!a.guided_mode || buildGuidedQuestion(s, c, a, segments, prior)) return null
  const resolved = resolveGuidedObject(s, c, a, segments, prior)
  a = resolved.answers
  const id = guidedProcessId(s), name = s.normalized_step_name, scope = processScope(s)
  const fields: CanonicalConditionField[] = []
  const conditions: RulePackageCondition[] = []
  const mode = value(a, 'guided_mode'), basis = value(a, 'guided_basis')
  const guidance = guidanceForSegment(s, c, segments)
  const features = c.feature_mappings[featureGroup(s, c, segments)] || guidance?.recommendation?.features || []
  const object = list(value(a, 'guided_features')).join('、') || features.join('、') || name
  let summary = '', candidate: RuleConditionCandidate
  function field(suffix: string, label: string, type: CanonicalConditionField['type'], operators: string[], options: string[] = [], unit?: string) {
    const key = `${scope}.${suffix}`
    fields.push({ key, label, type, category: `${name} · ${object}`, operators, aliases: [], required: false, source: `项目问答配置；同一加工对象；工序=${id}`, options: options.map(v => ({ value: v, label: v })), allow_custom: false, ...(unit ? { unit } : {}) })
    return key
  }
  const leaf = (key: string, op: string, v: unknown) => conditions.push({ field: key, op, value: v })
  if (mode === 'custom') candidate = readCustomCandidate(s, a)!
  else {
    const configuration = { process_id: id, occurrence: ({ mainline: 'always', manual: 'manual', condition: 'conditional', relation: 'associated' } as const)[mode as 'mainline' | 'manual' | 'condition' | 'relation'], when: null as RulePackageCondition | null, relations: [] as NonNullable<RuleConditionCandidate['configuration']>['relations'] }
    if (mode === 'mainline') summary = `${name}固定安排，作为主工序。`
    if (mode === 'manual') {
      const manual = buildManualBooleanRuleCandidate({ segment: s }, `是否需要${name}`)
      configuration.when = manual.when || null
      fields.push(...(manual.field_definitions || []))
      summary = `${name}由用户每次决定是否安排。`
    }
    if (mode === 'relation') {
      const source = priorSegments(s, segments).find(item => guidedProcessId(item) === value(a, 'guided_source'))!
      configuration.relations.push({ relation_type: 'trigger_after', source_process_ids: [guidedProcessId(source)], target_process_ids: [id], source_match: 'any' })
      summary = `${source.normalized_step_name}纳入路线时带出${name}，保留母路线原位置。`
    }
    if (mode === 'condition') {
      if (['feature', 'precision', 'roughness'].includes(basis)) {
        const selected = list(value(a, 'guided_features')), direction = value(a, 'guided_direction')
        leaf(field('features', '加工对象的特征', 'multi_select', ['contains_any'], c.feature_mappings[featureGroup(s, c, segments)] || selected), 'contains_any', selected)
        const directionKey = field('direction', '同一加工对象的方位', 'single_select', ['eq'], c.directions)
        if (direction === '所有方位') conditions.push({ any: ['A侧', 'B侧'].map(side => ({ field: directionKey, op: 'eq', value: side })) })
        else leaf(directionKey, 'eq', direction)
        summary = `同一加工对象具有${selected.join('、')}中任一特征，且位于${direction === '所有方位' ? 'A侧或B侧' : direction}时安排${name}。`
      }
      if (basis === 'precision' || basis === 'roughness') {
        const isIT = basis === 'precision', threshold = Number(value(a, isIT ? 'guided_it' : 'guided_ra'))
        const key = field(isIT ? 'it' : 'ra', `${object}的实际${isIT ? '尺寸精度等级' : 'Ra要求值'}`, 'number', ['lte'], [], isIT ? 'IT' : 'μm')
        fields[fields.length - 1]!.validation = { min: isIT ? 1 : 0, ...(isIT ? { max: 18 } : {}) }
        leaf(key, 'lte', threshold)
        summary = `${object}位于${value(a, 'guided_direction') === '所有方位' ? 'A侧或B侧' : value(a, 'guided_direction')}，且实际${isIT ? '尺寸精度' : 'Ra要求值'}≤${isIT ? 'IT' : ''}${threshold}${isIT ? '' : ' μm'}时安排${name}。`
      } else if (basis === 'material') {
        const selected = list(value(a, 'guided_material_scope')).map(m => m.replace(/^material_scope::grade::/, ''))
        const key = 'project_factor.material_grade'
        fields.push({ key, label: '材料牌号', type: 'single_select', category: '基本信息', operators: ['in', 'eq'], aliases: [], source: '项目配置材料', options: [...new Set([...c.materials, ...selected])].map(v => ({ value: v, label: v })), allow_custom: false, required: false })
        leaf(key, 'in', selected)
        summary = `材料牌号为${selected.join('、')}时安排${name}。`
      } else if (basis === 'requirement') {
        const expected = value(a, 'guided_requirement') === 'true'
        leaf(field('requirement', `当前部位是否有明确${name}要求`, 'boolean', ['eq', 'neq']), 'eq', expected)
        summary = `当前部位${expected ? '有' : '明确没有'}明确${name}要求时安排${name}。`
      } else if (basis === 'hardness') {
        const min = Number(value(a, 'guided_hardness_min')), max = Number(value(a, 'guided_hardness_max')), unit = value(a, 'guided_hardness_unit')
        leaf(field('hardness_unit', '目标硬度单位', 'single_select', ['eq'], ['HRC', 'HBW', 'HV', 'HRB']), 'eq', unit)
        leaf(field('hardness_min', '目标硬度下限（含）', 'number', ['gte'], [], unit), 'gte', min)
        leaf(field('hardness_max', '目标硬度上限（含）', 'number', ['lte'], [], unit), 'lte', max)
        summary = `目标硬度的单位为${unit}，完整区间包含在${min}～${max}（含端点）内时安排${name}。`
      }
      if (!conditions.length) return null
      configuration.when = conditions.length === 1 ? conditions[0]! : { all: conditions }
    }
    candidate = { kind: 'process_configuration', configuration, field_definitions: fields, preview: summary, evidence: '用户确认的第三步回答' }
  }
  if (!candidate || validateAuthoredCandidate(candidate, id).length) return null
  summary ||= candidate.preview
  const sources = [...new Set([...(resolved.reuse?.features?.source_segment_ids || []), ...(resolved.reuse?.direction?.source_segment_ids || [])])]
  return { scope: `当前工序：${name}`, object, condition_text: summary, candidate, missing: [], provenance: [
    { kind: 'user', label: '第三步确认', evidence: `项目配置版本${c.revision}` },
    ...(sources.length ? [{ kind: 'user', label: '沿用已确认加工对象', evidence: `来源工序=${sources.join('、')}；${resolved.hint}` }] : []),
  ], status: 'confirmed' }
}
