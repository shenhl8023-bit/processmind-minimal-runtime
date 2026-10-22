import { buildTemplateStepRefs, mappingsForStep } from './templateStepMapping'
import { getCurrentGroupTemplate, type ProjectGroupTemplate } from '@/api/extract'

export interface GroupTemplateCheckResult {
  ready: boolean
  code?: 'missing_template' | 'missing_mappings' | 'network_error'
  message?: string
}

function pathKey(path: string[]) {
  return JSON.stringify(path.map(value => String(value).normalize('NFC').trim()))
}

export function getTemplateMappingStatus(
  template: ProjectGroupTemplate | null | undefined,
  operations?: import('./templateGroupMapping').TemplateOperation[],
) {
  const nodes = new Map<string, import('@/api/extract').GroupTemplateNode>()
  function visit(tree: import('@/api/extract').GroupTemplateNode[]) {
    tree.forEach(node => { nodes.set(pathKey(node.path), node); visit(node.children || []) })
  }
  visit(template?.tree || [])
  const machiningOperations = operations?.filter(op => !op.process_id || op.process_type !== '辅助工序')
  const sources = operations === undefined ? null : new Set(machiningOperations!.flatMap(op => op.process_id ? op.source_operation_ids || [] : [Number(op.source_operation_id || op.id)]))
  const steps = machiningOperations?.flatMap(buildTemplateStepRefs)
  const validLegacy = (template?.mappings || []).filter(mapping =>
    nodes.has(pathKey(mapping.template_group_path))
      && mapping.feature_selections?.some(feature => nodes.get(pathKey(mapping.template_group_path))?.feature_selections.includes(feature))
      && (!sources || sources.has(mapping.source_operation_id)))
  const confirmed = (template?.step_mappings || []).filter(mapping => mapping.status === 'confirmed')
  const hasCurrentLineage = (mapping: import('@/api/extract').GroupTemplateStepMapping) => !sources || steps?.some(step => mappingsForStep({ mapping }, step).length && (step.source_steps || [{ source_operation_id: step.operation_id, source_step_order: step.step_order, source_step_name: step.step_name }]).some(source => source.source_operation_id === mapping.source_operation_id && source.source_step_order === mapping.source_step_order && source.source_step_name.normalize('NFC').trim() === mapping.source_step_name.normalize('NFC').trim()))
  const validSteps = confirmed.filter(mapping => {
    const node = nodes.get(pathKey(mapping.template_group_path))
    if (!node || node.children?.length || !mapping.candidate_features?.length
      || !mapping.candidate_features.every(feature => node.feature_selections.includes(feature))) return false
    return hasCurrentLineage(mapping)
  })
  const general = (template?.step_mappings || []).filter(mapping => mapping.status === 'not_applicable')
  const validGeneral = general.filter(mapping => mapping.source === 'user_confirmed' && hasCurrentLineage(mapping))
  const featureGroups = [...nodes.values()].filter(node => !node.children?.length && node.feature_selections?.length)
  const mappedPaths = new Set([
    ...validSteps.map(mapping => pathKey(mapping.template_group_path)),
    ...validLegacy.map(mapping => pathKey(mapping.template_group_path)),
  ])
  const missingFeatureGroups = featureGroups.filter(node => !mappedPaths.has(pathKey(node.path)))
  return {
    validCount: validLegacy.length + validSteps.length,
    invalidCount: (template?.mappings || []).length - validLegacy.length + confirmed.length - validSteps.length + general.length - validGeneral.length,
    validSteps,
    validGeneral,
    validLegacy,
    missingFeatureGroups,
  }
}

export function isGroupTemplateReady(template: ProjectGroupTemplate | null | undefined): boolean {
  const status = getTemplateMappingStatus(template)
  return status.validCount > 0 && status.missingFeatureGroups.length === 0
}

export async function checkProjectGroupTemplateReady(projectId: number): Promise<GroupTemplateCheckResult> {
  if (!projectId) {
    return { ready: false, code: 'missing_template', message: '未指定项目' }
  }
  try {
    const template = await getCurrentGroupTemplate(projectId)
    if (!template) {
      return { ready: false, code: 'missing_template', message: '尚未上传或绑定分组模板' }
    }
    if (!isGroupTemplateReady(template)) {
      return { ready: false, code: 'missing_mappings', message: '尚未完成任何工序的分组模板映射' }
    }
    return { ready: true }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      return { ready: false, code: 'missing_template', message: '尚未上传或绑定分组模板' }
    }
    console.warn('检查分组模板失败:', err)
    return { ready: false, code: 'network_error', message: '检查分组模板失败，请稍后重试' }
  }
}
