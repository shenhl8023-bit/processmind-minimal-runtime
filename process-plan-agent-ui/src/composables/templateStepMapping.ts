import type {
  GroupTemplateNode,
  GroupTemplateStepMappingInput,
} from '@/api/extract'
import type { TemplateOperation } from './templateGroupMapping'

export const TEMPLATE_STEP_MAPPING_DRAFT_VERSION = 1
export const TEMPLATE_STEP_MAPPING_DRAFT_PREFIX = 'template_step_mapping_draft'

export type TemplateStepRef = {
  operation_id: number
  operation_name: string
  step_key: string
  step_order: number
  step_name: string
}

type StepMappingRecord = Record<string, GroupTemplateStepMappingInput>

function cleanText(value: unknown) {
  return String(value ?? '').normalize('NFC').trim()
}

function operationId(operation: TemplateOperation) {
  const value = Number(operation.source_operation_id || operation.id || 0)
  return Number.isInteger(value) && value > 0 ? value : 0
}

function stableStepKey(sourceOperationId: number, order: number) {
  return `op_${sourceOperationId}_s${String(order).padStart(2, '0')}`
}

function mappingStepKey(mapping: Pick<GroupTemplateStepMappingInput, 'source_operation_id' | 'source_step_order'>) {
  return stableStepKey(mapping.source_operation_id, mapping.source_step_order)
}

function cloneMapping(mapping: GroupTemplateStepMappingInput): GroupTemplateStepMappingInput {
  return {
    ...mapping,
    scope_template_group_path: [...mapping.scope_template_group_path],
    template_group_path: [...mapping.template_group_path],
    candidate_features: [...mapping.candidate_features],
  }
}

export function buildTemplateStepRefs(operation: TemplateOperation): TemplateStepRef[] {
  const sourceOperationId = operationId(operation)
  const operationName = cleanText(operation.name)
  return (operation.step_items || []).flatMap((rawStep, index) => {
    const stepName = cleanText(rawStep)
    if (!stepName || !sourceOperationId) return []
    const stepOrder = index + 1
    return [{
      operation_id: sourceOperationId,
      operation_name: operationName,
      step_key: stableStepKey(sourceOperationId, stepOrder),
      step_order: stepOrder,
      step_name: stepName,
    }]
  })
}

export function isFeatureLeaf(node: GroupTemplateNode | null | undefined): boolean {
  return Boolean(
    node
    && (!node.children || node.children.length === 0)
    && Array.isArray(node.feature_selections)
    && node.feature_selections.some(feature => cleanText(feature)),
  )
}

export function descendantFeatureLeaves(node: GroupTemplateNode): GroupTemplateNode[] {
  if (isFeatureLeaf(node)) return [node]
  return (node.children || []).flatMap(descendantFeatureLeaves)
}

export function mappingTargetsForScope(node: GroupTemplateNode): GroupTemplateNode[] {
  return isFeatureLeaf(node) ? [node] : descendantFeatureLeaves(node)
}

export function createTemplateStepMapping(
  step: TemplateStepRef,
  leaf: GroupTemplateNode,
  scopePath: string[] = [],
  source: GroupTemplateStepMappingInput['source'] = 'user_confirmed',
  confidence = 1,
): GroupTemplateStepMappingInput {
  if (!isFeatureLeaf(leaf)) throw new Error('工步正式映射必须指向特征叶子分组。')
  return {
    source_operation_id: step.operation_id,
    source_operation_name: step.operation_name,
    source_step_order: step.step_order,
    source_step_name: step.step_name,
    scope_template_group_path: scopePath.map(cleanText).filter(Boolean),
    template_group_path: leaf.path.map(cleanText).filter(Boolean),
    candidate_features: leaf.feature_selections.map(cleanText).filter(Boolean),
    match_mode: 'any',
    status: 'confirmed',
    confidence: Math.max(0, Math.min(Number(confidence) || 0, 1)),
    source,
  }
}

export function createNotApplicableStepMapping(step: TemplateStepRef): GroupTemplateStepMappingInput {
  return {
    source_operation_id: step.operation_id,
    source_operation_name: step.operation_name,
    source_step_order: step.step_order,
    source_step_name: step.step_name,
    scope_template_group_path: [],
    template_group_path: [],
    candidate_features: [],
    match_mode: 'any',
    status: 'not_applicable',
    confidence: 1,
    source: 'user_confirmed',
  }
}

export function stepMappingKey(
  mapping: Pick<GroupTemplateStepMappingInput, 'source_step_order' | 'source_operation_id' | 'template_group_path' | 'status'>,
) {
  const path = mapping.template_group_path.map(cleanText).filter(Boolean)
  return `${mappingStepKey(mapping)}::${mapping.status}::${JSON.stringify(path)}`
}

export function groupStepMappingsByStep(mappings: StepMappingRecord) {
  return Object.values(mappings).reduce<Record<string, GroupTemplateStepMappingInput[]>>((grouped, mapping) => {
    const stepKey = mappingStepKey(mapping)
    ;(grouped[stepKey] ||= []).push(mapping)
    return grouped
  }, {})
}

export function unresolvedTemplateSteps(steps: TemplateStepRef[], mappings: StepMappingRecord) {
  const grouped = groupStepMappingsByStep(mappings)
  return steps.filter(step => !(grouped[step.step_key] || []).some(mapping => (
    mapping.status === 'not_applicable'
    || (mapping.status === 'confirmed' && mapping.template_group_path.length > 0)
  )))
}

export function buildTemplateStepRouteFingerprint(operations: TemplateOperation[]) {
  return JSON.stringify(operations.map(operation => ({
    id: operationId(operation),
    name: cleanText(operation.name),
    steps: (operation.step_items || []).map(cleanText),
  })))
}

function draftKey(projectId: number) {
  return `${TEMPLATE_STEP_MAPPING_DRAFT_PREFIX}:${projectId}`
}

export function saveTemplateStepMappingDraft(
  projectId: number,
  templateRevision: number,
  routeFingerprint: string,
  mappings: GroupTemplateStepMappingInput[],
) {
  if (typeof localStorage === 'undefined' || !projectId) return
  localStorage.setItem(draftKey(projectId), JSON.stringify({
    version: TEMPLATE_STEP_MAPPING_DRAFT_VERSION,
    templateRevision,
    routeFingerprint,
    mappings: mappings.map(cloneMapping),
  }))
}

export function loadTemplateStepMappingDraft(
  projectId: number,
  templateRevision: number,
  routeFingerprint: string,
) {
  if (typeof localStorage === 'undefined' || !projectId) return []
  try {
    const parsed = JSON.parse(localStorage.getItem(draftKey(projectId)) || 'null')
    if (
      parsed?.version !== TEMPLATE_STEP_MAPPING_DRAFT_VERSION
      || parsed?.templateRevision !== templateRevision
      || parsed?.routeFingerprint !== routeFingerprint
      || !Array.isArray(parsed?.mappings)
    ) return []
    return parsed.mappings.map(cloneMapping) as GroupTemplateStepMappingInput[]
  } catch {
    return []
  }
}

export function clearTemplateStepMappingDraft(projectId: number) {
  if (typeof localStorage === 'undefined' || !projectId) return
  localStorage.removeItem(draftKey(projectId))
}
