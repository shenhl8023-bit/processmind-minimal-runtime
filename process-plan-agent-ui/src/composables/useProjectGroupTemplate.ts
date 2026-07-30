import { computed, ref, type MaybeRef, unref } from 'vue'

import {
  commitGroupTemplate,
  getCurrentGroupTemplate,
  previewGroupTemplate,
  saveGroupTemplateMappings,
  type GroupTemplateMapping,
  type GroupTemplateMappingInput,
  type GroupTemplateMigrationResult,
  type GroupTemplateNode,
  type GroupTemplatePreview,
  type ProjectGroupTemplate,
} from '@/api/extract'

export type GroupTemplateDialogState = 'empty' | 'preview' | 'workspace'

export type LegacyGroupTemplateAlias = {
  source_operation_id: number
  alias: string
  template_group_path: string[]
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
  return { kept_source_operation_ids: kept, invalidated }
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
  if (!error || typeof error !== 'object' || !('response' in error)) return '分组模板操作失败，请稍后重试。'
  const response = error.response
  if (!response || typeof response !== 'object' || !('data' in response)) return '分组模板操作失败，请稍后重试。'
  const data = response.data
  if (data && typeof data === 'object' && 'detail' in data && typeof data.detail === 'string') return data.detail
  return '分组模板操作失败，请稍后重试。'
}

export function useProjectGroupTemplate(
  projectId: MaybeRef<number>,
  legacyAliases: MaybeRef<Record<string, LegacyGroupTemplateAlias | undefined>>,
) {
  const state = ref<GroupTemplateDialogState>('empty')
  const template = ref<ProjectGroupTemplate | null>(null)
  const preview = ref<GroupTemplatePreview | null>(null)
  const draftMappings = ref<GroupTemplateMappingInput[]>([])
  const loading = ref(false)
  const saving = ref(false)
  const error = ref('')
  const replacementImpact = ref<GroupTemplateMigrationResult | null>(null)
  const templateRevision = computed(() => template.value?.template_revision ?? 0)
  let selectedFile: File | null = null
  let legacyMigrationProjectId: number | null = null
  let previewRequestId = 0

  function applyTemplate(snapshot: ProjectGroupTemplate) {
    template.value = snapshot
    draftMappings.value = mappingInputs(snapshot.mappings)
    state.value = 'workspace'
  }

  async function load(options: { preserveError?: boolean } = {}) {
    const currentProjectId = unref(projectId)
    loading.value = true
    if (!options.preserveError) error.value = ''
    try {
      const current = await getCurrentGroupTemplate(currentProjectId)
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
      if (errorStatus(cause) === 404) {
        state.value = 'empty'
        template.value = null
        preview.value = null
        selectedFile = null
        draftMappings.value = []
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
      loading.value = false
    }
  }

  async function selectFile(file: File) {
    const requestId = ++previewRequestId
    saving.value = false
    loading.value = true
    error.value = ''
    state.value = 'preview'
    selectedFile = null
    preview.value = null
    replacementImpact.value = null
    try {
      const nextPreview = await previewGroupTemplate(file)
      if (requestId !== previewRequestId) return
      selectedFile = file
      preview.value = nextPreview
      replacementImpact.value = template.value ? previewMigration(template.value, nextPreview) : null
    } catch (cause) {
      if (requestId !== previewRequestId) return
      error.value = errorMessage(cause)
    } finally {
      if (requestId === previewRequestId) loading.value = false
    }
  }

  function beginReplacement() {
    if (!template.value) return
    previewRequestId += 1
    loading.value = false
    state.value = 'preview'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  function cancelPreview() {
    previewRequestId += 1
    loading.value = false
    state.value = template.value ? 'workspace' : 'empty'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  async function recoverFromConflict() {
    error.value = '分组模板已在其他页面更新，正在重新加载最新内容。'
    const reloaded = await load({ preserveError: true })
    if (reloaded) error.value = '分组模板已在其他页面更新，已重新加载最新内容。'
  }

  async function confirmTemplate() {
    if (!preview.value?.can_confirm || !selectedFile) return
    saving.value = true
    error.value = ''
    try {
      const committed = await commitGroupTemplate(
        unref(projectId),
        selectedFile,
        preview.value.content_hash,
        templateRevision.value,
      )
      applyTemplate(committed)
      replacementImpact.value = {
        kept_source_operation_ids: committed.kept_source_operation_ids,
        invalidated: committed.invalidated,
      }
      preview.value = null
      selectedFile = null
    } catch (cause) {
      if (errorStatus(cause) === 409) {
        await recoverFromConflict()
      } else {
        error.value = errorMessage(cause)
      }
    } finally {
      saving.value = false
    }
  }

  async function saveMappings() {
    if (!template.value) return
    saving.value = true
    error.value = ''
    try {
      const saved = await saveGroupTemplateMappings(
        unref(projectId),
        templateRevision.value,
        draftMappings.value,
      )
      applyTemplate(saved)
    } catch (cause) {
      if (errorStatus(cause) === 409) {
        await recoverFromConflict()
      } else {
        error.value = errorMessage(cause)
      }
    } finally {
      saving.value = false
    }
  }

  return {
    state,
    template,
    preview,
    draftMappings,
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
  }
}
