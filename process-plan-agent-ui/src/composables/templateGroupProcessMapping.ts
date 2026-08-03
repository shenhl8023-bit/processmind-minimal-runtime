import type { GroupTemplateNode, GroupTemplateStepMappingInput } from '@/api/extract'
import type { TemplateOperation } from './templateGroupMapping'
import {
  buildTemplateStepRefs,
  isFeatureLeaf,
  stepMappingKey,
  type TemplateStepRef,
} from './templateStepMapping'

export type TemplateStepEligibility = 'eligible' | 'excluded'

export type TemplateProcessStep = TemplateStepRef & {
  eligibility: TemplateStepEligibility
  eligibility_reason: string
}

const EXCLUDED_STEP_PATTERNS = [
  /热处理|调质|正常化|正火|淬火|回火|退火|时效|清洗|除油|检验|检查|探伤|测量|包装|标记|打标|装配/,
]
const GEOMETRY_PROCESS_PATTERNS = [
  /车|铣|钻|镗|铰|攻丝|磨|研|珩|切槽|挖槽|倒角|倒圆|成形|割型|打型|电火花|线切割/,
]

function cleanText(value: unknown) {
  return String(value ?? '').normalize('NFC').trim()
}

function flatten(nodes: GroupTemplateNode[]): GroupTemplateNode[] {
  return nodes.flatMap(node => [node, ...flatten(node.children || [])])
}

export function classifyTemplateProcessStep(
  _operation: TemplateOperation,
  step: TemplateStepRef,
): TemplateProcessStep {
  const text = cleanText(step.step_name)
  const excluded = EXCLUDED_STEP_PATTERNS.some(pattern => pattern.test(text))
  if (excluded) return { ...step, eligibility: 'excluded', eligibility_reason: '不直接加工模板几何特征' }
  const eligible = GEOMETRY_PROCESS_PATTERNS.some(pattern => pattern.test(text))
  if (eligible) return { ...step, eligibility: 'eligible', eligibility_reason: '工步包含几何特征加工动作' }
  return { ...step, eligibility: 'excluded', eligibility_reason: '未识别到几何特征加工动作' }
}

export function buildEligibleTemplateSteps(operations: TemplateOperation[]) {
  const all = operations.flatMap(operation => buildTemplateStepRefs(operation)
    .map(step => classifyTemplateProcessStep(operation, step)))
  return {
    eligible: all.filter(step => step.eligibility === 'eligible'),
    excluded: all.filter(step => step.eligibility === 'excluded'),
  }
}

export function groupConfirmedMappingsByLeaf(
  mappings: GroupTemplateStepMappingInput[],
  tree: GroupTemplateNode[],
) {
  const legalLeaves = new Map(flatten(tree).filter(isFeatureLeaf).map(node => [JSON.stringify(node.path), node.key]))
  return confirmedTemplateStepMappings(mappings).reduce<Record<string, GroupTemplateStepMappingInput[]>>((result, mapping) => {
    const leafKey = legalLeaves.get(JSON.stringify(mapping.template_group_path))
    if (leafKey) (result[leafKey] ||= []).push(mapping)
    return result
  }, {})
}

export function featureLeafConfiguration(
  tree: GroupTemplateNode[],
  mappings: GroupTemplateStepMappingInput[],
) {
  const leaves = flatten(tree).filter(isFeatureLeaf)
  const configuredKeys = new Set(Object.keys(groupConfirmedMappingsByLeaf(mappings, tree)))
  return {
    configured: leaves.filter(node => configuredKeys.has(node.key)),
    unconfigured: leaves.filter(node => !configuredKeys.has(node.key)),
  }
}

export function confirmedTemplateStepMappings(mappings: GroupTemplateStepMappingInput[]) {
  return mappings.filter(mapping => mapping.status === 'confirmed' && mapping.template_group_path.length > 0)
}

export function mappingRecord(mappings: GroupTemplateStepMappingInput[]) {
  return Object.fromEntries(mappings.map(mapping => [stepMappingKey(mapping), {
    ...mapping,
    scope_template_group_path: [...mapping.scope_template_group_path],
    template_group_path: [...mapping.template_group_path],
    candidate_features: [...mapping.candidate_features],
  }]))
}

export function removeLeafMapping(
  mappings: Record<string, GroupTemplateStepMappingInput>,
  leafKey: string,
  tree: GroupTemplateNode[],
) {
  const leaf = flatten(tree).find(node => node.key === leafKey)
  if (!leaf || !isFeatureLeaf(leaf)) return mappingRecord(Object.values(mappings))
  const path = JSON.stringify(leaf.path)
  return mappingRecord(Object.values(mappings).filter(mapping => (
    JSON.stringify(mapping.template_group_path) !== path
  )))
}
