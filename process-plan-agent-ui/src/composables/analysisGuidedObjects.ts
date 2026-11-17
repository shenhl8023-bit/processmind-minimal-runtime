import type { TreeAnswer } from './analysisQuestionTreeState'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'

type Answers = Record<string, TreeAnswer>
export const OBJECT_REUSE_NODE = '__object_reuse'
export interface ConfirmedMachiningObject {
  segmentId: string
  name: string
  features: string[]
  direction?: string
}
export interface GuidedObjectReuse {
  schema_version: 1
  features?: { values: string[]; source_segment_ids: string[] }
  direction?: { value: string; source_segment_ids: string[] }
}
const sameSet = (a: string[], b: string[]) => a.length === b.length && a.every(v => b.includes(v))

type GuidanceOperation = AnalysisGuidanceConfiguration['operation_guidance'][string]
function sameData(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (!a || !b || typeof a !== 'object' || typeof b !== 'object') return false
  if (Array.isArray(a) !== Array.isArray(b)) return false
  const left = Object.entries(a), right = Object.entries(b)
  return left.length === right.length && left.every(([key, value]) =>
    Object.prototype.hasOwnProperty.call(b, key) && sameData(value, (b as Record<string, unknown>)[key]))
}

/** A different generation hash is not evidence of a compatible reference. This
 * adapter accepts only a fill-only projection of the same frozen configuration;
 * stable route/node metadata is additionally required across generations. */
function sameProjection(frozen: AnalysisGuidanceConfiguration, source: AnalysisGuidanceConfiguration) {
  const body = (configuration: AnalysisGuidanceConfiguration) => {
    const { revision, generation_version, operation_guidance, ...rest } = configuration
    return { ...rest, operation_guidance: Object.fromEntries(Object.entries(operation_guidance)
      .filter(([key]) => !key.startsWith('__segment__:')).map(([key, operation]) => {
        const old = frozen.operation_guidance[key]?.recommendation
        if (!operation.recommendation || !old) return [key, operation]
        const recommendation = { ...operation.recommendation }
        if (!old.features?.length) delete recommendation.features
        if (!old.direction) delete recommendation.direction
        return [key, { ...operation, recommendation }]
      })) }
  }
  return sameData(body(frozen), body(source))
}

/** Derive missing object suggestions without changing answers or the snapshot. */
export function supplementFrozenObjectRecommendation(frozen: AnalysisGuidanceConfiguration,
  source: AnalysisGuidanceConfiguration, key: string, identity: string,
  operation: GuidanceOperation, answers: Answers): GuidanceOperation {
  const reference = source.operation_guidance[key]
  const old = operation.recommendation, next = reference?.recommendation
  if (!sameData(operation, frozen.operation_guidance[key]) || !reference ||
      operation.recommendation_reference_blocked || reference.recommendation_reference_blocked ||
      old?.mode !== 'condition' || !['precision', 'roughness'].includes(old.basis || '') ||
      next?.mode !== 'condition' || next.basis !== old.basis || !operation.feature_group ||
      operation.feature_group !== reference.feature_group) return operation
  const oldIds = frozen.generation_operation_ids, sourceIds = source.generation_operation_ids
  if (frozen.generation_route_id !== source.generation_route_id ||
      ((oldIds || sourceIds) && (oldIds?.[key] !== identity || sourceIds?.[key] !== identity ||
        Object.values(oldIds || {}).filter(id => id === identity).length !== 1 ||
        Object.values(sourceIds || {}).filter(id => id === identity).length !== 1))) return operation
  const sameGeneration = !!frozen.generation_version && frozen.generation_version === source.generation_version
  if (sameGeneration ? frozen.revision !== source.revision :
    (!sameProjection(frozen, source) || source.revision < frozen.revision ||
      (frozen.generation_version !== source.generation_version &&
        (frozen.generation_route_id === undefined || !oldIds || !sourceIds)))) return operation
  const features = next.features
  const group = operation.feature_group
  if (!features?.length || !features.every(feature => frozen.feature_mappings[group]?.includes(feature) &&
      source.feature_mappings[group]?.includes(feature)) ||
      (next.direction && (!frozen.directions.includes(next.direction) || !source.directions.includes(next.direction)))) return operation
  const selected = answers.guided_features?.value.split('|').filter(Boolean)
  if ((old.features?.length && !sameSet(old.features, features)) ||
      (selected?.length && !sameSet(selected, features)) ||
      (old.direction && old.direction !== next.direction)) return operation
  const recommendation = { ...old }
  if (!old.features?.length) recommendation.features = [...features]
  if (!old.direction && next.direction && frozen.directions.includes(next.direction) && source.directions.includes(next.direction)) {
    recommendation.direction = next.direction
  }
  return sameData(recommendation, old) ? operation : { ...operation, recommendation }
}

/** Only caller-supplied confirmed answers are sources; recommendations identify
 * a candidate object but never establish a previously confirmed one. */
export function resolveConfirmedObject(answers: Answers, candidates: string[], directions: string[],
  prior: ConfirmedMachiningObject[], recommendation?: { features?: string[]; direction?: string }) {
  const resolved = { ...answers }
  const reuse: GuidedObjectReuse = { schema_version: 1 }
  const selected = (answers.guided_features?.value || '').split('|').filter(Boolean)
  const valid = (features: string[]) => features.length > 0 && features.every(v => candidates.includes(v))
  const eligible = prior.filter(object => valid(object.features))
  let features = selected
  if (!answers.guided_features) {
    const target = recommendation?.features
    const choices = target?.length
      ? eligible.filter(object => target.every(v => object.features.includes(v))).map(object => ({ ...object, features: target }))
      : eligible
    const sets = choices.filter((object, i) => choices.findIndex(other => sameSet(other.features, object.features)) === i)
    if (sets.length === 1 && valid(sets[0]!.features)) {
      features = sets[0]!.features
      reuse.features = { values: features, source_segment_ids: choices.map(object => object.segmentId) }
      resolved.guided_features = { nodeId: 'guided_features', value: features.join('|'), label: features.join('、') }
    }
  }
  if (!answers.guided_direction && valid(features)) {
    const sources = eligible.filter(object => features.every(v => object.features.includes(v)) && object.direction && directions.includes(object.direction))
    const values = [...new Set(sources.map(object => object.direction!))]
    const expected = !recommendation?.features || sameSet(features, recommendation.features) ? recommendation?.direction : undefined
    // A/B range covers either side; it does not cover middle/periphery, nor
    // prove that a narrower side exists. Conflicts require a user choice.
    if (values.length === 1 && (!expected || expected === values[0] || (expected === '所有方位' && ['A侧', 'B侧'].includes(values[0]!)))) {
      const direction = values[0]!
      reuse.direction = { value: direction, source_segment_ids: sources.map(object => object.segmentId) }
      resolved.guided_direction = { nodeId: 'guided_direction', value: direction, label: direction }
    }
  }
  const ids = new Set([...(reuse.features?.source_segment_ids || []), ...(reuse.direction?.source_segment_ids || [])])
  const names = [...new Set(prior.filter(object => ids.has(object.segmentId)).map(object => object.name))]
  const hint = names.length ? `沿用“${names.join('、')}”已确认的${reuse.features && reuse.direction ? '特征和方位' : reuse.features ? '特征' : '方位'}；本工序精度条件单独设置。` : ''
  return { answers: resolved, reuse: ids.size ? reuse : undefined, hint }
}
