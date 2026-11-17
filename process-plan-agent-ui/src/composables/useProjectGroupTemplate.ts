import { computed, ref, type MaybeRef, unref, watch } from 'vue'
import { isWorkflowRevisionConflict } from './workflowResetState'

import {
  commitGroupTemplate,
  getCurrentGroupTemplate,
  previewGroupTemplate,
  saveGroupTemplateMappings,
  saveGroupTemplateStepMappings,
  type GroupTemplateMapping,
  type GroupTemplateMappingInput,
  type GroupTemplateMigrationResult,
  type GroupTemplateNode,
  type GroupTemplatePreview,
  type GroupTemplateStepMapping,
  type GroupTemplateStepMappingInput,
  type GroupTemplateValidationIssue,
  type ProjectGroupTemplate,
  type TemplateGroupMappingOperationInput,
} from '@/api/extract'

export type GroupTemplateDialogState = 'empty' | 'preview' | 'workspace'

export type TemplateMappingSaveRequest = {
  project_id: number
  expected_template_revision: number
  expected_workflow_revision: number
  mappings: GroupTemplateStepMappingInput[]
  operations: TemplateGroupMappingOperationInput[]
  replace_all: true
  step_order_by_process?: Record<string, string[]>
  expected_route_version_id?: number
  hidden_step_keys: string[]
  waived_group_paths: string[][]
}

// The atomic export endpoint can return this frozen mapping snapshot in
// export_sources.template_mapping; metadata absent there stays on the template.
export type TemplateMappingSavedSnapshot = Pick<ProjectGroupTemplate, 'template_revision' | 'step_mappings' | 'mapping_output'>
  & { hidden_step_keys: string[]; waived_group_paths: string[][] }
  & Partial<ProjectGroupTemplate>
export type TemplateMappingSaveHandler = (request: TemplateMappingSaveRequest) => Promise<TemplateMappingSavedSnapshot>

export type LegacyGroupTemplateAlias = {
  source_operation_id: number
  alias: string
  template_group_path: string[]
}

export function formatGroupTemplateIssueDetail(issue: GroupTemplateValidationIssue) {
  return [issue.path.join(' / '), issue.value.trim()].filter(Boolean).join(' · ')
}

function pathKey(path: string[]) {
  return JSON.stringify(path.map(part => String(part).normalize('NFC').trim()))
}

function mappingInput(mapping: Pick<GroupTemplateMapping, 'source_operation_id' | 'alias' | 'template_group_path'>): GroupTemplateMappingInput {
  return {
    source_operation_id: mapping.source_operation_id,
    alias: mapping.alias,
    template_group_path: [...mapping.template_group_path],
  }
}

function mappingInputs(mappings: GroupTemplateMapping[]) {
  return mappings.map(mappingInput)
}

function stepMappingInput(mapping: GroupTemplateStepMapping): GroupTemplateStepMappingInput {
  return {
    ...(mapping.final_targets?.length ? { final_targets: mapping.final_targets.map(target => ({ ...target })) } : {}),
    source_operation_id: mapping.source_operation_id,
    source_operation_name: mapping.source_operation_name,
    source_step_order: mapping.source_step_order,
    source_step_name: mapping.source_step_name,
    scope_template_group_path: [...mapping.scope_template_group_path],
    template_group_path: [...mapping.template_group_path],
    candidate_features: [...mapping.candidate_features],
    match_mode: 'any',
    status: mapping.status,
    confidence: mapping.confidence,
    source: mapping.source,
  }
}

function treePathKeys(nodes: GroupTemplateNode[]) {
  const keys = new Set<string>()
  const visit = (children: GroupTemplateNode[]) => {
    children.forEach((node) => {
      keys.add(pathKey(node.path))
      visit(node.children)
    })
  }
  visit(nodes)
  return keys
}

function previewMigration(template: ProjectGroupTemplate, preview: GroupTemplatePreview): GroupTemplateMigrationResult {
  const paths = treePathKeys(preview.tree)
  const kept: number[] = []
  const invalidated: GroupTemplateMapping[] = []
  template.mappings.forEach((mapping) => {
    if (paths.has(pathKey(mapping.template_group_path))) {
      kept.push(mapping.source_operation_id)
    } else {
      invalidated.push(mapping)
    }
  })
  const keptSourceStepKeys: string[] = []
  const invalidatedStepMappings: GroupTemplateStepMapping[] = []
  ;(template.step_mappings || []).forEach((mapping) => {
    if (mapping.status === 'not_applicable' || paths.has(pathKey(mapping.template_group_path))) {
      keptSourceStepKeys.push(mapping.source_step_key)
    } else {
      invalidatedStepMappings.push(mapping)
    }
  })
  return {
    kept_source_operation_ids: kept,
    invalidated,
    kept_source_step_keys: keptSourceStepKeys,
    invalidated_step_mappings: invalidatedStepMappings,
  }
}

function migratedLegacyMappings(
  aliases: Record<string, LegacyGroupTemplateAlias | undefined>,
  template: ProjectGroupTemplate,
) {
  const paths = treePathKeys(template.tree)
  const seenOperations = new Set<number>()
  return Object.values(aliases).flatMap((binding) => {
    if (!binding || seenOperations.has(binding.source_operation_id)) return []
    const sourceOperationId = Number(binding.source_operation_id)
    const alias = String(binding.alias || '').trim()
    const path = Array.isArray(binding.template_group_path)
      ? binding.template_group_path.map(part => String(part).normalize('NFC').trim())
      : []
    if (!Number.isInteger(sourceOperationId) || sourceOperationId <= 0 || !alias || !path.length || !paths.has(pathKey(path))) {
      return []
    }
    seenOperations.add(sourceOperationId)
    return [{ source_operation_id: sourceOperationId, alias, template_group_path: path }]
  })
}

function errorStatus(error: unknown) {
  if (!error || typeof error !== 'object' || !('response' in error)) return undefined
  const response = error.response
  return response && typeof response === 'object' && 'status' in response
    ? Number(response.status)
    : undefined
}

function errorMessage(error: unknown) {
  const fallback = error instanceof Error && error.message.trim()
    ? error.message
    : '分组模板操作失败，请稍后重试。'
  if (!error || typeof error !== 'object' || !('response' in error)) return fallback
  const response = error.response
  if (!response || typeof response !== 'object' || !('data' in response)) return fallback
  const data = response.data
  const detail = data && typeof data === 'object' && 'detail' in data ? data.detail : undefined
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object') {
    const message = 'message' in detail && typeof detail.message === 'string' ? detail.message.trim() : ''
    const blockers = 'blockers' in detail && Array.isArray(detail.blockers)
      ? detail.blockers.map(blocker => blocker && typeof blocker.message === 'string' ? blocker.message.trim() : '')
      : []
    return [message, ...blockers].filter(Boolean).join('\n') || fallback
  }
  return fallback
}

export function useProjectGroupTemplate(
  projectId: MaybeRef<number>,
  legacyAliases: MaybeRef<Record<string, LegacyGroupTemplateAlias | undefined>>,
  workflowRevision: MaybeRef<number> = 0,
) {
  const state = ref<GroupTemplateDialogState>('empty')
  const template = ref<ProjectGroupTemplate | null>(null)
  const preview = ref<GroupTemplatePreview | null>(null)
  const draftMappings = ref<GroupTemplateMappingInput[]>([])
  const draftStepMappings = ref<GroupTemplateStepMappingInput[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const replacementImpact = ref<GroupTemplateMigrationResult | null>(null)
  const templateRevision = computed(() => template.value?.template_revision ?? 0)
  let selectedFile: File | null = null
  let legacyMigrationProjectId: number | null = null
  let requestId = 0
  let workflowStale = false

  function beginRequest(kind: 'loading' | 'saving') {
    const currentRequestId = ++requestId
    const currentProjectId = unref(projectId)
    const currentWorkflowRevision = unref(workflowRevision)
    loading.value = kind === 'loading'
    saving.value = kind === 'saving'
    return () => currentRequestId === requestId && currentProjectId === unref(projectId)
      && currentWorkflowRevision === unref(workflowRevision)
  }

  watch(() => [unref(projectId), unref(workflowRevision)], () => {
    requestId += 1
    state.value = 'empty'
    template.value = null
    preview.value = null
    selectedFile = null
    draftMappings.value = []
    draftStepMappings.value = []
    replacementImpact.value = null
    legacyMigrationProjectId = null
    error.value = ''
    loading.value = false
    saving.value = false
    workflowStale = false
  }, { flush: 'sync' })

  function applyTemplate(snapshot: ProjectGroupTemplate) {
    template.value = { ...snapshot, hidden_step_keys: snapshot.hidden_step_keys || [], waived_group_paths: snapshot.waived_group_paths || [] }
    draftMappings.value = mappingInputs(snapshot.mappings)
    draftStepMappings.value = (snapshot.step_mappings || []).map(stepMappingInput)
    state.value = 'workspace'
  }

  async function load(options: { preserveError?: boolean } = {}) {
    if (workflowStale) return false
    const currentProjectId = unref(projectId)
    const isCurrent = beginRequest('loading')
    if (!options.preserveError) error.value = ''
    try {
      const current = await getCurrentGroupTemplate(currentProjectId)
      if (!isCurrent()) return false
      applyTemplate(current)
      preview.value = null
      selectedFile = null
      replacementImpact.value = null
      if (legacyMigrationProjectId !== currentProjectId && current.mappings.length === 0) {
        draftMappings.value = migratedLegacyMappings(unref(legacyAliases), current)
      }
      legacyMigrationProjectId = currentProjectId
      return true
    } catch (cause) {
      if (!isCurrent()) return false
      if (errorStatus(cause) === 404) {
        state.value = 'empty'
        template.value = null
        preview.value = null
        selectedFile = null
        draftMappings.value = []
        draftStepMappings.value = []
        replacementImpact.value = null
        legacyMigrationProjectId = currentProjectId
        return true
      }
      const message = errorMessage(cause)
      error.value = options.preserveError
        ? `分组模板已在其他页面更新，但重新加载失败：${message}`
        : message
      return false
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  async function selectFile(file: File) {
    if (workflowStale) return
    const isCurrent = beginRequest('loading')
    error.value = ''
    state.value = 'preview'
    selectedFile = null
    preview.value = null
    replacementImpact.value = null
    try {
      const nextPreview = await previewGroupTemplate(file)
      if (!isCurrent()) return
      selectedFile = file
      preview.value = nextPreview
      replacementImpact.value = template.value ? previewMigration(template.value, nextPreview) : null
    } catch (cause) {
      if (!isCurrent()) return
      error.value = errorMessage(cause)
    } finally {
      if (isCurrent()) loading.value = false
    }
  }

  function beginReplacement() {
    if (workflowStale || !template.value) return
    requestId += 1
    loading.value = false
    saving.value = false
    state.value = 'preview'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  function cancelPreview() {
    if (workflowStale) return
    requestId += 1
    loading.value = false
    saving.value = false
    state.value = template.value ? 'workspace' : 'empty'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  async function recoverFromConflict(cause: unknown) {
    if (isWorkflowRevisionConflict(cause)) {
      workflowStale = true
      template.value = null
      draftMappings.value = []
      draftStepMappings.value = []
      state.value = 'empty'
      error.value = '工艺路线已更新，请重新加载页面后再导入模板、保存映射。'
      return
    }
    error.value = '分组模板已在其他页面更新，正在重新加载最新内容。'
    const reloading = load({ preserveError: true })
    const reloadRequestId = requestId
    const reloaded = await reloading
    if (reloaded && reloadRequestId === requestId) error.value = '分组模板已在其他页面更新，已重新加载最新内容。'
  }

  async function confirmTemplate() {
    if (workflowStale || !preview.value?.can_confirm || !selectedFile) return false
    const isCurrent = beginRequest('saving')
    error.value = ''
    try {
      const committed = await commitGroupTemplate(
        unref(projectId),
        selectedFile,
        preview.value.content_hash,
        templateRevision.value,
        unref(workflowRevision),
      )
      if (!isCurrent()) return false
      applyTemplate({ ...committed, hidden_step_keys: [], waived_group_paths: [] })
      replacementImpact.value = {
        kept_source_operation_ids: committed.kept_source_operation_ids,
        invalidated: committed.invalidated,
        kept_source_step_keys: committed.kept_source_step_keys || [],
        invalidated_step_mappings: committed.invalidated_step_mappings || [],
      }
      preview.value = null
      selectedFile = null
      return true
    } catch (cause) {
      if (!isCurrent()) return false
      if (errorStatus(cause) === 409) {
        await recoverFromConflict(cause)
      } else {
        error.value = errorMessage(cause)
      }
      return false
    } finally {
      if (isCurrent()) saving.value = false
    }
  }

  async function saveMappings() {
    if (workflowStale || !template.value || template.value.project_id !== unref(projectId)) return false
    const isCurrent = beginRequest('saving')
    error.value = ''
    try {
      const saved = await saveGroupTemplateMappings(
        unref(projectId),
        templateRevision.value,
        draftMappings.value,
        unref(workflowRevision),
      )
      if (!isCurrent()) return false
      applyTemplate(saved)
      return true
    } catch (cause) {
      if (!isCurrent()) return false
      if (errorStatus(cause) === 409) {
        await recoverFromConflict(cause)
      } else {
        error.value = errorMessage(cause)
      }
      return false
    } finally {
      if (isCurrent()) saving.value = false
    }
  }

  async function saveStepMappings(
    operations: TemplateGroupMappingOperationInput[] = [],
    exceptions?: { hidden_step_keys: string[]; waived_group_paths: string[][]; step_order_by_process?: Record<string, string[]>; expected_route_version_id?: number },
    beforeSave?: TemplateMappingSaveHandler,
  ) {
    if (workflowStale || !template.value || template.value.project_id !== unref(projectId)) return false
    const currentTemplate = template.value
    const isCurrent = beginRequest('saving')
    error.value = ''
    try {
      // A supplied handler owns persistence (and optionally export) in one server
      // transaction. Never follow it with the standalone mapping PUT.
      const saved = beforeSave ? await beforeSave(JSON.parse(JSON.stringify({
        project_id: unref(projectId),
        expected_template_revision: templateRevision.value,
        expected_workflow_revision: unref(workflowRevision),
        mappings: draftStepMappings.value,
        operations,
        replace_all: true,
        ...(exceptions?.step_order_by_process ? { step_order_by_process: exceptions.step_order_by_process } : {}),
        ...(exceptions?.expected_route_version_id ? { expected_route_version_id: exceptions.expected_route_version_id } : {}),
        hidden_step_keys: exceptions?.hidden_step_keys || currentTemplate.hidden_step_keys || [],
        waived_group_paths: exceptions?.waived_group_paths || currentTemplate.waived_group_paths || [],
      }))) : await saveGroupTemplateStepMappings(
        unref(projectId),
        templateRevision.value,
        draftStepMappings.value,
        operations,
        unref(workflowRevision),
        ...(exceptions ? [exceptions] as const : [] as const),
      )
      if (!isCurrent()) return false
      applyTemplate({ ...currentTemplate, ...saved })
      return true
    } catch (cause) {
      if (!isCurrent()) return false
      if (errorStatus(cause) === 409) {
        await recoverFromConflict(cause)
      } else {
        error.value = errorMessage(cause)
      }
      return false
    } finally {
      if (isCurrent()) saving.value = false
    }
  }

  return {
    state,
    template,
    preview,
    draftMappings,
    draftStepMappings,
    loading,
    saving,
    error,
    replacementImpact,
    templateRevision,
    load,
    selectFile,
    confirmTemplate,
    beginReplacement,
    cancelPreview,
    saveMappings,
    saveStepMappings,
  }
}
