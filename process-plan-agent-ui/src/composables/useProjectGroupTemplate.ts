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
  let legacyMigrationChecked = false

  function applyTemplate(snapshot: ProjectGroupTemplate) {
    template.value = snapshot
    draftMappings.value = mappingInputs(snapshot.mappings)
    state.value = 'workspace'
  }

  async function load() {
    loading.value = true
    error.value = ''
    try {
      const current = await getCurrentGroupTemplate(unref(projectId))
      applyTemplate(current)
      preview.value = null
      selectedFile = null
      replacementImpact.value = null
      if (!legacyMigrationChecked && current.mappings.length === 0) {
        draftMappings.value = migratedLegacyMappings(unref(legacyAliases), current)
      }
      legacyMigrationChecked = true
    } catch (cause) {
      if (errorStatus(cause) === 404) {
        state.value = 'empty'
        template.value = null
        preview.value = null
        selectedFile = null
        draftMappings.value = []
        replacementImpact.value = null
        return
      }
      error.value = errorMessage(cause)
    } finally {
      loading.value = false
    }
  }

  async function selectFile(file: File) {
    saving.value = false
    error.value = ''
    selectedFile = file
    try {
      const nextPreview = await previewGroupTemplate(file)
      preview.value = nextPreview
      state.value = 'preview'
      replacementImpact.value = template.value ? previewMigration(template.value, nextPreview) : null
    } catch (cause) {
      error.value = errorMessage(cause)
    }
  }

  function beginReplacement() {
    if (!template.value) return
    state.value = 'preview'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  function cancelPreview() {
    state.value = template.value ? 'workspace' : 'empty'
    preview.value = null
    selectedFile = null
    replacementImpact.value = null
    error.value = ''
  }

  async function recoverFromConflict() {
    await load()
    error.value = '分组模板已在其他页面更新，已重新加载最新内容。'
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
