import type {
  GroupTemplateNode,
  GroupTemplateStepMappingInput,
  TemplateGroupMappingOperationInput,
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

export type TemplateFeatureSelection = {
  leaf: GroupTemplateNode
  feature: string
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

export function chunkTemplateSuggestionOperations(
  operations: TemplateGroupMappingOperationInput[],
  maxStepCount = 6,
) {
  const limit = Math.max(1, Math.floor(maxStepCount) || 1)
  const batches: TemplateGroupMappingOperationInput[][] = []
  let batch: TemplateGroupMappingOperationInput[] = []
  let used = 0

  const flush = () => {
    if (!batch.length) return
    batches.push(batch)
    batch = []
    used = 0
  }

  for (const operation of operations) {
    const activeIndexes = operation.step_items
      .map((step, index) => cleanText(step) ? index : -1)
      .filter(index => index >= 0)
    for (let start = 0; start < activeIndexes.length;) {
      if (used === limit) flush()
      const size = Math.min(limit - used, activeIndexes.length - start)
      const selectedIndexes = new Set(activeIndexes.slice(start, start + size))
      batch.push({
        ...operation,
        step_items: operation.step_items.map((step, index) => (
          selectedIndexes.has(index) ? step : ''
        )),
      })
      used += size
      start += size
    }
  }
  flush()
  return batches
}

export async function settleTemplateSuggestionBatches<TBatch, TValue>(
  batches: TBatch[],
  request: (batch: TBatch) => Promise<TValue>,
  onFulfilled?: (value: TValue) => void,
) {
  const settled = await Promise.allSettled(batches.map(async (batch) => {
    const value = await request(batch)
    onFulfilled?.(value)
    return value
  }))
  return {
    values: settled.flatMap(result => result.status === 'fulfilled' ? [result.value] : []),
    failedCount: settled.filter(result => result.status === 'rejected').length,
  }
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

export function selectedFeatureLeaves(tree: GroupTemplateNode[], selectedKeys: string[]) {
  const selected = new Set(selectedKeys)
  return tree.flatMap(descendantFeatureLeaves).filter(node => selected.has(node.key))
}

export function templateFeatureSelectionKey(leafKey: string, feature: string) {
  return JSON.stringify([cleanText(leafKey), cleanText(feature)])
}

export function selectedTemplateFeatures(tree: GroupTemplateNode[], selectedKeys: string[]): TemplateFeatureSelection[] {
  const selected = new Set(selectedKeys)
  return tree.flatMap(descendantFeatureLeaves).flatMap((leaf) => (
    leaf.feature_selections.map(cleanText).filter(Boolean).flatMap((feature) => (
      selected.has(templateFeatureSelectionKey(leaf.key, feature)) ? [{ leaf, feature }] : []
    ))
  ))
}

export function recommendedFeaturesForSelection(
  leafKey: string,
  recommendedFeatures: string[],
  selectedFeatures: TemplateFeatureSelection[],
) {
  const recommended = [...new Set(recommendedFeatures.map(cleanText).filter(Boolean))]
  if (!selectedFeatures.length) return recommended
  const selected = new Set(
    selectedFeatures
      .filter(selection => selection.leaf.key === cleanText(leafKey))
      .map(selection => cleanText(selection.feature))
      .filter(Boolean),
  )
  if (!selected.size) return []
  return recommended.filter(feature => selected.has(feature))
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
  candidateFeatures = leaf.feature_selections,
): GroupTemplateStepMappingInput {
  if (!isFeatureLeaf(leaf)) throw new Error('工步正式映射必须指向特征叶子分组。')
  const allowedFeatures = leaf.feature_selections.map(cleanText).filter(Boolean)
  const requestedFeatures = [...new Set(candidateFeatures.map(cleanText).filter(Boolean))]
    .filter(feature => allowedFeatures.includes(feature))
  if (!requestedFeatures.length) throw new Error('工步正式映射必须至少选择一个有效特征。')
  return {
    source_operation_id: step.operation_id,
    source_operation_name: step.operation_name,
    source_step_order: step.step_order,
    source_step_name: step.step_name,
    scope_template_group_path: scopePath.map(cleanText).filter(Boolean),
    template_group_path: leaf.path.map(cleanText).filter(Boolean),
    candidate_features: requestedFeatures,
    match_mode: 'any',
    status: 'confirmed',
    confidence: Math.max(0, Math.min(Number(confidence) || 0, 1)),
    source,
  }
}

export function mergeTemplateStepMapping(
  existing: GroupTemplateStepMappingInput,
  incoming: GroupTemplateStepMappingInput,
) {
  if (
    existing.source_operation_id !== incoming.source_operation_id
    || existing.source_step_order !== incoming.source_step_order
    || JSON.stringify(existing.template_group_path) !== JSON.stringify(incoming.template_group_path)
  ) return null
  const candidateFeatures = [...new Set([
    ...existing.candidate_features,
    ...incoming.candidate_features,
  ])]
  if (candidateFeatures.length === existing.candidate_features.length) return null
  return {
    ...existing,
    candidate_features: candidateFeatures,
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

export function confirmedMappingsForStep(
  mappings: StepMappingRecord,
  step: Pick<TemplateStepRef, 'step_key'>,
) {
  return (groupStepMappingsByStep(mappings)[step.step_key] || []).filter(mapping => (
    mapping.status === 'confirmed' && mapping.template_group_path.length > 0
  ))
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
