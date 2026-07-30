<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tgmd-backdrop" @click.self="closeDialog">
      <section class="tgmd-dialog" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title">
        <header class="tgmd-header">
          <div class="tgmd-title-block">
            <h2 id="template-group-mapping-title">模板分组映射</h2>
            <p v-if="model.template.value">
              {{ model.template.value.original_filename }} · {{ model.template.value.part_filename || '未标注零件文件' }}
            </p>
            <p v-else>导入 Kmsoft XML 分组模板后，再将当前零件的工序映射到特征分组。</p>
          </div>
          <div class="tgmd-header-actions">
            <button
              v-if="model.state.value === 'workspace'"
              class="tgmd-command"
              type="button"
              @click="startReplacement"
            ><RefreshRight />更换模板</button>
            <button class="tgmd-icon-button" type="button" title="关闭" aria-label="关闭" @click="closeDialog"><Close /></button>
          </div>
        </header>

        <div v-if="visibleError" class="tgmd-inline-error" role="alert">
          <WarningFilled />
          <span>{{ visibleError }}</span>
        </div>

        <div v-if="model.loading.value && model.state.value !== 'preview'" class="tgmd-loading">
          <span class="tgmd-spinner" />正在加载项目分组模板...
        </div>

        <template v-else-if="showUploadState">
          <main class="tgmd-upload-state">
            <input ref="fileInput" class="tgmd-file-input" type="file" accept=".xml,application/xml,text/xml" @change="onFileInput">
            <button
              class="tgmd-dropzone"
              :class="{ 'tgmd-dropzone-ready': pendingFile }"
              type="button"
              @click="openFilePicker"
              @dragover.prevent
              @drop.prevent="onDrop"
            >
              <UploadFilled />
              <strong>{{ pendingFile ? pendingFile.name : '选择分组模板 XML' }}</strong>
              <span>{{ pendingFile ? formatBytes(pendingFile.size) : '点击选择，或将 .xml 文件拖到这里' }}</span>
            </button>
            <div class="tgmd-upload-actions">
              <button
                v-if="isReplacing"
                class="btn btn-outline"
                type="button"
                :disabled="model.loading.value"
                @click="cancelReplacement"
              >取消更换</button>
              <button
                class="btn btn-primary"
                type="button"
                :disabled="!pendingFile || model.loading.value"
                @click="parsePendingFile"
              >
                <span v-if="model.loading.value" class="tgmd-spinner tgmd-spinner-light" />
                {{ model.loading.value ? '正在解析' : '解析模板' }}
              </button>
            </div>
          </main>
        </template>

        <template v-else-if="model.state.value === 'preview' && model.preview.value">
          <main class="tgmd-preview-state">
            <section class="tgmd-preview-summary">
              <div class="tgmd-preview-heading">
                <DocumentChecked />
                <div>
                  <h3>{{ model.preview.value.original_filename }}</h3>
                  <p>{{ model.preview.value.can_confirm ? '模板结构校验通过' : '模板存在阻断问题，请更换文件后重试' }}</p>
                </div>
                <span :class="['tgmd-validation-badge', model.preview.value.can_confirm ? 'is-valid' : 'is-invalid']">
                  {{ model.preview.value.can_confirm ? '可确认' : '不可确认' }}
                </span>
              </div>

              <dl class="tgmd-meta-grid">
                <div><dt>编码</dt><dd>{{ model.preview.value.source_encoding || '未知' }}</dd></div>
                <div><dt>零件文件</dt><dd>{{ model.preview.value.part_filename || '未标注' }}</dd></div>
                <div><dt>分组</dt><dd>{{ model.preview.value.group_count }}</dd></div>
                <div><dt>特征选择</dt><dd>{{ model.preview.value.feature_selection_count }}</dd></div>
                <div><dt>校验问题</dt><dd>{{ model.preview.value.validation_issues.length }}</dd></div>
              </dl>

              <div v-if="model.preview.value.validation_issues.length" class="tgmd-issue-list">
                <div v-for="(issue, index) in model.preview.value.validation_issues" :key="`${issue.code}-${index}`" class="tgmd-issue-row">
                  <strong>{{ issue.message }}</strong>
                  <span v-if="issue.path.length">{{ issue.path.join(' / ') }}</span>
                </div>
              </div>

              <div v-if="isReplacing && model.replacementImpact.value" class="tgmd-impact">
                <h4>更换影响</h4>
                <p>
                  可保留 <strong>{{ model.replacementImpact.value.kept_source_operation_ids.length }}</strong> 项映射，
                  将失效 <strong>{{ model.replacementImpact.value.invalidated.length }}</strong> 项。
                </p>
                <div v-if="model.replacementImpact.value.invalidated.length" class="tgmd-invalidated-list">
                  <div v-for="mapping in model.replacementImpact.value.invalidated" :key="mapping.source_operation_id">
                    <span>{{ operationName(mapping.source_operation_id) }}</span>
                    <small>{{ mapping.template_group_path.join(' / ') }}</small>
                  </div>
                </div>
              </div>
            </section>

            <section class="tgmd-preview-tree" aria-label="模板分组预览">
              <header><h3>分组结构</h3><span>仅展示业务分组和特征选择</span></header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in model.preview.value.tree"
                  :key="node.key"
                  :node="node"
                  readonly
                />
              </div>
            </section>
          </main>
          <footer class="tgmd-footer">
            <div>
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="resetPreviewSelection">重新选择</button>
              <button v-if="isReplacing" class="btn btn-outline" type="button" :disabled="model.saving.value" @click="cancelReplacement">取消更换</button>
            </div>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!model.preview.value.can_confirm || model.saving.value"
              @click="confirmPreview"
            >{{ model.saving.value ? '正在确认' : isReplacing ? '确认更换并进入映射' : '确认并进入映射' }}</button>
          </footer>
        </template>

        <template v-else-if="model.state.value === 'workspace' && model.template.value">
          <div v-if="mappingSummary || mappingWarnings.length" class="tgmd-smart-status" aria-live="polite">
            <span v-if="mappingSummary">
              自动映射 {{ mappingSummary.autoMapped }} 项，待确认 {{ mappingSummary.pending }} 项，无法判断 {{ mappingSummary.unresolved }} 项
            </span>
            <span v-if="mappingWarnings.length" class="tgmd-smart-warning">{{ mappingWarnings.join('；') }}</span>
          </div>

          <main class="tgmd-workspace">
            <section class="tgmd-pane tgmd-tree-pane">
              <header class="tgmd-pane-header">
                <div><h3>模板分组</h3><span>{{ model.template.value.group_count }} 个分组</span></div>
                <span>{{ mappedCount }} 项已映射</span>
              </header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in model.template.value.tree"
                  :key="node.key"
                  :node="node"
                  :active-key="activeGroupKey"
                  :mapped-counts="mappedCounts"
                  @select="activeGroupKey = $event"
                  @clear="clearGroupMappings"
                />
              </div>
              <div v-if="activeGroup" class="tgmd-active-target">
                <span>当前目标</span>
                <strong>{{ activeGroup.path.join(' / ') }}</strong>
              </div>
              <div v-if="activeGroup && mappedOperationsForGroup(activeGroup.key).length" class="tgmd-group-mappings">
                <div v-for="operation in mappedOperationsForGroup(activeGroup.key)" :key="operationId(operation)">
                  <span>{{ operation.name }}</span>
                  <button type="button" title="移除映射" aria-label="移除映射" @click="removeMapping(operation)"><Close /></button>
                </div>
              </div>
            </section>

            <div class="tgmd-transfer-column">
              <button
                class="tgmd-transfer-button"
                type="button"
                :disabled="!activeGroup || !selectedOperationIds.length"
                :title="transferButtonTitle"
                @click="mapSelectedOperations"
              >
                <ArrowLeft />
                <span v-if="selectedOperationIds.length">{{ selectedOperationIds.length }}</span>
              </button>
            </div>

            <section class="tgmd-pane tgmd-operation-pane">
              <header class="tgmd-pane-header tgmd-operation-header">
                <div><h3>待映射工序</h3><span>{{ unmappedOperations.length }} 项</span></div>
                <div class="tgmd-operation-tools">
                  <label class="tgmd-search"><Search /><input v-model="searchTerm" type="search" placeholder="搜索工序"></label>
                  <button class="tgmd-smart-button" type="button" :disabled="!unmappedOperations.length || autoMapping" @click="autoMapOperations">
                    <MagicStick />{{ autoMapping ? '分析中' : '智能映射' }}
                  </button>
                </div>
              </header>

              <label class="tgmd-select-all">
                <input type="checkbox" :checked="allVisibleSelected" @change="toggleAllVisible">
                <span>选择当前列表全部工序</span>
              </label>

              <div class="tgmd-operation-scroll">
                <div
                  v-for="operation in filteredUnmappedOperations"
                  :key="operationId(operation)"
                  class="tgmd-operation-row"
                  :class="{ 'is-selected': selectedOperationIds.includes(operationId(operation)), 'has-suggestion': mappingSuggestionFor(operation) }"
                  @dblclick.prevent="quickMap(operation)"
                >
                  <input type="checkbox" :checked="selectedOperationIds.includes(operationId(operation))" @change="toggleOperation(operationId(operation))">
                  <span class="tgmd-operation-sequence">{{ operation.sequence || operationId(operation) }}</span>
                  <div class="tgmd-operation-content">
                    <strong>{{ operation.name }}</strong>
                    <div v-if="mappingSuggestionFor(operation)" class="tgmd-suggestion" @dblclick.stop>
                      <p>{{ mappingSuggestionFor(operation)!.reason }}</p>
                      <div v-if="mappingSuggestionFor(operation)!.candidates.length" class="tgmd-candidates">
                        <button
                          v-for="candidate in mappingSuggestionFor(operation)!.candidates"
                          :key="candidate.group_id"
                          type="button"
                          :title="candidate.reason"
                          @click.stop="applyCandidate(operation, candidate.group_id)"
                        >{{ candidate.path.join(' / ') }}</button>
                      </div>
                      <small v-else>需要手动选择模板分组</small>
                    </div>
                  </div>
                </div>
                <div v-if="!filteredUnmappedOperations.length" class="tgmd-empty">当前没有待映射工序</div>
              </div>
            </section>
          </main>

          <footer class="tgmd-footer">
            <button class="tgmd-clear-all" type="button" :disabled="!mappedCount || model.saving.value" @click="clearMappings">
              <Delete />清空映射
            </button>
            <div>
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="closeDialog">取消</button>
              <button class="btn btn-primary" type="button" :disabled="model.saving.value" @click="saveMappings">
                <Link />{{ model.saving.value ? '正在保存' : '保存映射' }}
              </button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowLeft,
  Close,
  Delete,
  DocumentChecked,
  Link,
  MagicStick,
  RefreshRight,
  Search,
  UploadFilled,
  WarningFilled,
} from '@element-plus/icons-vue'

import { suggestTemplateGroupMappings } from '@/api/extract'
import TemplateGroupTreeNode from '@/components/extract/TemplateGroupTreeNode.vue'
import {
  buildTemplateGroupMappingSuggestions,
  clearTemplateGroupMappingDraft,
  createTemplateAliasBinding,
  findTemplateGroupByKey,
  hasTemplateGroupMappingDraft,
  isTemplateMappableOperation,
  isTrustedTemplateGroupChoice,
  loadTemplateGroupMappingDraft,
  migrateLegacyAliasesByPath,
  saveTemplateGroupMappingDraft,
  type TemplateAliasBinding,
  type TemplateGroupMappingCandidate,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'
import { useProjectGroupTemplate } from '@/composables/useProjectGroupTemplate'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  operations: TemplateOperation[]
  aliases: Record<string, TemplateAliasBinding>
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', aliases: Record<string, TemplateAliasBinding>, templateRevision: number): void
}>()

const model = useProjectGroupTemplate(
  computed(() => props.projectId),
  computed(() => props.aliases),
)
const fileInput = ref<HTMLInputElement | null>(null)
const pendingFile = ref<File | null>(null)
const transientError = ref('')
const draftAliases = ref<Record<string, TemplateAliasBinding>>({})
const selectedOperationIds = ref<number[]>([])
const activeGroupKey = ref('')
const searchTerm = ref('')
const autoMapping = ref(false)
const dialogRunId = ref(0)
const mappingWarnings = ref<string[]>([])
const mappingSummary = ref<{ autoMapped: number; pending: number; unresolved: number } | null>(null)

type MappingReviewSuggestion = {
  reason: string
  confidence: number | null
  source: 'rules' | 'llm' | 'unresolved'
  recommendedGroupId: string | null
  candidates: TemplateGroupMappingCandidate[]
  evidence: string[]
  warnings: string[]
}

const mappingSuggestions = ref<Record<string, MappingReviewSuggestion>>({})
const visibleError = computed(() => transientError.value || model.error.value)
const isReplacing = computed(() => Boolean(model.template.value))
const showUploadState = computed(() => (
  model.state.value === 'empty'
  || (model.state.value === 'preview' && !model.preview.value)
))
const activeGroup = computed(() => (
  model.template.value
    ? findTemplateGroupByKey(model.template.value.tree, activeGroupKey.value)
    : null
))
const mappableOperations = computed(() => {
  const seen = new Set<number>()
  return props.operations
    .filter(isTemplateMappableOperation)
    .filter((operation) => {
      const id = operationId(operation)
      if (!id || seen.has(id)) return false
      seen.add(id)
      return true
    })
    .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0) || operationId(left) - operationId(right))
})
const unmappedOperations = computed(() => mappableOperations.value.filter(operation => !draftAliases.value[String(operationId(operation))]))
const filteredUnmappedOperations = computed(() => {
  const query = searchTerm.value.trim().toLowerCase()
  if (!query) return unmappedOperations.value
  return unmappedOperations.value.filter(operation => `${operation.name} ${operation.step_family || ''}`.toLowerCase().includes(query))
})
const mappedCount = computed(() => Object.keys(draftAliases.value).length)
const mappedCounts = computed(() => Object.values(draftAliases.value).reduce<Record<string, number>>((counts, binding) => {
  counts[binding.template_group_key] = Number(counts[binding.template_group_key] || 0) + 1
  return counts
}, {}))
const allVisibleSelected = computed(() => (
  filteredUnmappedOperations.value.length > 0
  && filteredUnmappedOperations.value.every(operation => selectedOperationIds.value.includes(operationId(operation)))
))
const transferButtonTitle = computed(() => {
  if (!activeGroup.value) return '请先选择模板分组'
  if (!selectedOperationIds.value.length) return '请先选择工序'
  return `映射到 ${activeGroup.value.path.join(' / ')}`
})

watch(() => props.modelValue, async (visible) => {
  dialogRunId.value += 1
  autoMapping.value = false
  transientError.value = ''
  pendingFile.value = null
  if (!visible) return
  selectedOperationIds.value = []
  mappingSuggestions.value = {}
  mappingWarnings.value = []
  mappingSummary.value = null
  const runId = dialogRunId.value
  await model.load()
  if (runId !== dialogRunId.value || !props.modelValue) return
  syncDraftFromTemplate()
}, { immediate: true })

function operationId(operation: TemplateOperation) {
  return Number(operation.source_operation_id || operation.id || 0)
}

function operationName(sourceOperationId: number) {
  return props.operations.find(operation => operationId(operation) === sourceOperationId)?.name || `工序 ${sourceOperationId}`
}

function bindingRecord(bindings: TemplateAliasBinding[]) {
  return Object.fromEntries(bindings.map(binding => [String(binding.source_operation_id), {
    ...binding,
    template_group_path: [...binding.template_group_path],
    feature_selections: [...binding.feature_selections],
  }]))
}

function syncDraftFromTemplate() {
  const template = model.template.value
  if (!template) {
    draftAliases.value = {}
    activeGroupKey.value = ''
    return
  }
  const formalMappings = bindingRecord(template.mappings.map(mapping => ({
    ...mapping,
    template_group_id: mapping.template_group_key || mapping.template_group_id,
  })))
  const restoredDraft = loadTemplateGroupMappingDraft(
    props.projectId,
    template.template_revision,
    formalMappings,
    template.tree,
  )
  const hasCurrentDraft = hasTemplateGroupMappingDraft(props.projectId, template.template_revision)
  draftAliases.value = Object.keys(restoredDraft).length || hasCurrentDraft
    ? restoredDraft
    : migrateLegacyAliasesByPath(props.aliases, template.tree).migrated
  const activeStillExists = findTemplateGroupByKey(template.tree, activeGroupKey.value)
  activeGroupKey.value = activeStillExists?.key || template.tree[0]?.key || ''
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`
}

function openFilePicker() {
  fileInput.value?.click()
}

function acceptFile(file: File | undefined) {
  transientError.value = ''
  if (!file) return
  if (!file.name.toLowerCase().endsWith('.xml')) {
    pendingFile.value = null
    transientError.value = '请选择 .xml 格式的分组模板。'
    return
  }
  pendingFile.value = file
}

function onFileInput(event: Event) {
  acceptFile((event.target as HTMLInputElement).files?.[0])
}

function onDrop(event: DragEvent) {
  acceptFile(event.dataTransfer?.files?.[0])
}

async function parsePendingFile() {
  if (!pendingFile.value) return
  transientError.value = ''
  await model.selectFile(pendingFile.value)
}

function startReplacement() {
  pendingFile.value = null
  transientError.value = ''
  model.beginReplacement()
}

function cancelReplacement() {
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  syncDraftFromTemplate()
}

function resetPreviewSelection() {
  pendingFile.value = null
  transientError.value = ''
  if (model.template.value) model.beginReplacement()
  else model.cancelPreview()
  if (fileInput.value) fileInput.value.value = ''
}

async function confirmPreview() {
  await model.confirmTemplate()
  if (model.state.value === 'workspace') syncDraftFromTemplate()
}

function persistDraft() {
  if (!model.template.value) return
  saveTemplateGroupMappingDraft(
    props.projectId,
    model.templateRevision.value,
    draftAliases.value,
    '',
  )
}

function mappedOperationsForGroup(groupKey: string) {
  return mappableOperations.value.filter(operation => (
    draftAliases.value[String(operationId(operation))]?.template_group_key === groupKey
  ))
}

function mappingSuggestionFor(operation: TemplateOperation) {
  return mappingSuggestions.value[String(operationId(operation))] || null
}

function toggleOperation(id: number) {
  const next = new Set(selectedOperationIds.value)
  if (next.has(id)) next.delete(id)
  else next.add(id)
  selectedOperationIds.value = [...next]
}

function toggleAllVisible() {
  const visibleIds = filteredUnmappedOperations.value.map(operationId)
  const next = new Set(selectedOperationIds.value)
  if (allVisibleSelected.value) visibleIds.forEach(id => next.delete(id))
  else visibleIds.forEach(id => next.add(id))
  selectedOperationIds.value = [...next]
}

function mapOperation(operation: TemplateOperation, groupKey: string) {
  if (draftAliases.value[String(operationId(operation))] || !model.template.value) return false
  const group = findTemplateGroupByKey(model.template.value.tree, groupKey)
  if (!group) return false
  const binding = createTemplateAliasBinding(operation, group)
  if (!binding) return false
  draftAliases.value[String(binding.source_operation_id)] = binding
  delete mappingSuggestions.value[String(binding.source_operation_id)]
  persistDraft()
  return true
}

function mapSelectedOperations() {
  if (!activeGroup.value) return
  const selected = new Set(selectedOperationIds.value)
  mappableOperations.value.forEach((operation) => {
    if (selected.has(operationId(operation))) mapOperation(operation, activeGroup.value!.key)
  })
  selectedOperationIds.value = []
}

function quickMap(operation: TemplateOperation) {
  if (activeGroup.value) mapOperation(operation, activeGroup.value.key)
}

function applyCandidate(operation: TemplateOperation, groupKey: string) {
  if (mapOperation(operation, groupKey)) refreshMappingSummary(mappingSummary.value?.autoMapped || 0)
}

function removeMapping(operation: TemplateOperation) {
  delete draftAliases.value[String(operationId(operation))]
  persistDraft()
}

function clearGroupMappings(groupKey: string) {
  mappedOperationsForGroup(groupKey).forEach(operation => delete draftAliases.value[String(operationId(operation))])
  persistDraft()
}

function clearMappings() {
  draftAliases.value = {}
  selectedOperationIds.value = []
  persistDraft()
}

function refreshMappingSummary(autoMapped: number) {
  const remaining = Object.values(mappingSuggestions.value)
  mappingSummary.value = {
    autoMapped,
    pending: remaining.filter(item => item.candidates.length > 0).length,
    unresolved: remaining.filter(item => item.candidates.length === 0).length,
  }
}

async function autoMapOperations() {
  if (autoMapping.value || !unmappedOperations.value.length || !model.template.value) return
  const runId = ++dialogRunId.value
  autoMapping.value = true
  selectedOperationIds.value = []
  mappingWarnings.value = []
  const operations = [...unmappedOperations.value]
  const deterministic = buildTemplateGroupMappingSuggestions(operations, model.template.value.tree)
  const deterministicById = new Map(deterministic.map(item => [item.operation_id, item]))
  const operationById = new Map(operations.map(item => [operationId(item), item]))
  mappingSuggestions.value = Object.fromEntries(deterministic.map(suggestion => [String(suggestion.operation_id), {
    reason: suggestion.reasons.join('；'),
    confidence: null,
    source: suggestion.candidates.length ? 'rules' : 'unresolved',
    recommendedGroupId: null,
    candidates: suggestion.candidates,
    evidence: suggestion.evidence,
    warnings: [],
  }]))
  refreshMappingSummary(0)

  const resolvable = deterministic.filter(item => item.candidates.length > 0)
  if (!resolvable.length) {
    if (runId === dialogRunId.value) autoMapping.value = false
    return
  }

  let autoMapped = 0
  try {
    const response = await suggestTemplateGroupMappings({
      project_id: props.projectId,
      operations: resolvable.map((suggestion) => {
        const operation = operationById.get(suggestion.operation_id)!
        return {
          operation_id: suggestion.operation_id,
          operation_name: suggestion.operation_name,
          step_items: operation.step_items || [],
          rule_evidence: suggestion.evidence,
          rule_reasons: suggestion.reasons,
        }
      }),
    })
    if (runId !== dialogRunId.value || !props.modelValue) return
    mappingWarnings.value = response.warnings || []
    response.suggestions.forEach((suggestion) => {
      const operation = operationById.get(suggestion.operation_id)
      const deterministicSuggestion = deterministicById.get(suggestion.operation_id)
      const review = mappingSuggestions.value[String(suggestion.operation_id)]
      if (!operation || !deterministicSuggestion || !review) return
      if (
        deterministicSuggestion.candidates.length === 1
        && !draftAliases.value[String(suggestion.operation_id)]
        && isTrustedTemplateGroupChoice(suggestion, deterministicSuggestion.candidates)
      ) {
        if (mapOperation(operation, suggestion.group_id!)) autoMapped += 1
        return
      }
      const legalRecommended = deterministicSuggestion.candidates.some(candidate => candidate.group_id === suggestion.group_id)
        ? suggestion.group_id || null
        : null
      mappingSuggestions.value[String(suggestion.operation_id)] = {
        ...review,
        reason: suggestion.reason || review.reason,
        confidence: suggestion.confidence,
        source: suggestion.source === 'llm' ? 'llm' : 'unresolved',
        recommendedGroupId: legalRecommended,
        evidence: suggestion.evidence?.length ? suggestion.evidence : review.evidence,
        warnings: suggestion.warnings || [],
      }
    })
  } catch {
    if (runId !== dialogRunId.value || !props.modelValue) return
    mappingWarnings.value = ['智能服务暂时不可用，程序候选仍可手动选择。']
  } finally {
    if (runId === dialogRunId.value && props.modelValue) {
      refreshMappingSummary(autoMapped)
      autoMapping.value = false
    }
  }
}

async function saveMappings() {
  model.draftMappings.value = Object.values(draftAliases.value).map(binding => ({
    source_operation_id: binding.source_operation_id,
    alias: binding.alias,
    template_group_path: [...binding.template_group_path],
  }))
  await model.saveMappings()
  if (model.error.value || !model.template.value) {
    syncDraftFromTemplate()
    return
  }
  const aliases = bindingRecord(model.template.value.mappings.map(mapping => ({
    ...mapping,
    template_group_id: mapping.template_group_key || mapping.template_group_id,
  })))
  draftAliases.value = aliases
  clearTemplateGroupMappingDraft(props.projectId)
  emit('save', aliases, model.templateRevision.value)
  closeDialog()
}

function closeDialog() {
  dialogRunId.value += 1
  autoMapping.value = false
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  emit('update:modelValue', false)
}
</script>

<style scoped>
.tgmd-backdrop { position: fixed; inset: 0; z-index: 3000; display: grid; place-items: center; padding: 16px; background: rgba(15, 23, 42, .48); }
.tgmd-dialog { width: min(1180px, calc(100vw - 32px)); height: min(780px, calc(100vh - 32px)); display: flex; flex-direction: column; overflow: hidden; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; box-shadow: 0 22px 60px rgba(15, 23, 42, .24); color: #1e293b; }
.tgmd-header { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 18px; border-bottom: 1px solid #dbe3ec; background: #fff; }
.tgmd-title-block { min-width: 0; }
.tgmd-title-block h2 { margin: 0; font-size: 18px; line-height: 1.35; letter-spacing: 0; }
.tgmd-title-block p { margin: 4px 0 0; overflow: hidden; color: #64748b; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-header-actions, .tgmd-operation-tools, .tgmd-footer > div, .tgmd-upload-actions { display: flex; align-items: center; gap: 8px; }
.tgmd-command, .tgmd-icon-button, .tgmd-smart-button, .tgmd-clear-all { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid #cbd5e1; background: #fff; color: #334155; cursor: pointer; }
.tgmd-command { min-height: 34px; padding: 0 10px; border-radius: 4px; }
.tgmd-command svg, .tgmd-smart-button svg, .tgmd-clear-all svg, .btn svg { width: 15px; height: 15px; }
.tgmd-icon-button { width: 34px; height: 34px; border-radius: 4px; }
.tgmd-icon-button svg { width: 17px; height: 17px; }
.tgmd-inline-error { display: flex; align-items: flex-start; gap: 8px; padding: 9px 18px; border-bottom: 1px solid #fecaca; background: #fef2f2; color: #991b1b; font-size: 12px; }
.tgmd-inline-error svg { width: 16px; height: 16px; flex: 0 0 auto; }
.tgmd-loading { flex: 1; display: flex; align-items: center; justify-content: center; gap: 10px; color: #64748b; }
.tgmd-spinner { width: 16px; height: 16px; display: inline-block; border: 2px solid #cbd5e1; border-top-color: #2563eb; border-radius: 50%; animation: tgmd-spin .8s linear infinite; }
.tgmd-spinner-light { border-color: rgba(255,255,255,.45); border-top-color: #fff; }
@keyframes tgmd-spin { to { transform: rotate(360deg); } }

.tgmd-upload-state { flex: 1; display: grid; place-content: center; gap: 18px; padding: 32px; }
.tgmd-file-input { display: none; }
.tgmd-dropzone { width: min(520px, calc(100vw - 80px)); min-height: 190px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; padding: 24px; border: 1px dashed #94a3b8; border-radius: 6px; background: #fff; color: #475569; cursor: pointer; }
.tgmd-dropzone:hover, .tgmd-dropzone-ready { border-color: #2563eb; background: #f8fbff; }
.tgmd-dropzone svg { width: 32px; height: 32px; color: #2563eb; }
.tgmd-dropzone strong { max-width: 100%; overflow-wrap: anywhere; font-size: 15px; }
.tgmd-dropzone span { color: #64748b; font-size: 12px; }
.tgmd-upload-actions { justify-content: flex-end; }

.tgmd-preview-state { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(360px, .85fr) minmax(420px, 1.15fr); gap: 16px; padding: 16px; }
.tgmd-preview-summary, .tgmd-preview-tree, .tgmd-pane { min-height: 0; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; }
.tgmd-preview-summary { overflow: auto; padding: 18px; }
.tgmd-preview-heading { display: flex; align-items: center; gap: 12px; }
.tgmd-preview-heading > svg { width: 28px; height: 28px; color: #2563eb; }
.tgmd-preview-heading > div { min-width: 0; flex: 1; }
.tgmd-preview-heading h3, .tgmd-preview-heading p { margin: 0; }
.tgmd-preview-heading h3 { overflow-wrap: anywhere; font-size: 15px; }
.tgmd-preview-heading p { margin-top: 3px; color: #64748b; font-size: 12px; }
.tgmd-validation-badge { padding: 4px 8px; border-radius: 3px; font-size: 11px; font-weight: 700; }
.tgmd-validation-badge.is-valid { background: #dcfce7; color: #166534; }
.tgmd-validation-badge.is-invalid { background: #fee2e2; color: #991b1b; }
.tgmd-meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin: 18px 0; background: #e2e8f0; }
.tgmd-meta-grid > div { min-width: 0; padding: 10px; background: #f8fafc; }
.tgmd-meta-grid dt { color: #64748b; font-size: 11px; }
.tgmd-meta-grid dd { margin: 3px 0 0; overflow-wrap: anywhere; font-size: 13px; font-weight: 650; }
.tgmd-issue-list, .tgmd-invalidated-list { display: grid; gap: 6px; }
.tgmd-issue-row, .tgmd-invalidated-list > div { display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px; background: #fef2f2; color: #991b1b; font-size: 11px; }
.tgmd-impact { margin-top: 18px; padding-top: 16px; border-top: 1px solid #e2e8f0; }
.tgmd-impact h4, .tgmd-impact p { margin: 0; }
.tgmd-impact p { margin-top: 5px; color: #475569; font-size: 12px; }
.tgmd-invalidated-list { margin-top: 10px; }
.tgmd-invalidated-list small { color: #64748b; }
.tgmd-preview-tree { display: flex; flex-direction: column; overflow: hidden; }
.tgmd-preview-tree > header { padding: 14px 16px; border-bottom: 1px solid #e2e8f0; }
.tgmd-preview-tree h3, .tgmd-preview-tree header span { margin: 0; }
.tgmd-preview-tree h3 { font-size: 14px; }
.tgmd-preview-tree header span { color: #64748b; font-size: 11px; }
.tgmd-tree-scroll { min-height: 0; flex: 1; overflow: auto; padding: 6px 0; }

.tgmd-smart-status { display: flex; justify-content: space-between; gap: 16px; padding: 7px 18px; border-bottom: 1px solid #bfdbfe; background: #eff6ff; color: #1e40af; font-size: 11px; }
.tgmd-smart-warning { color: #92400e; }
.tgmd-workspace { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(300px, .9fr) 54px minmax(480px, 1.45fr); gap: 10px; padding: 12px; }
.tgmd-pane { display: flex; flex-direction: column; overflow: hidden; }
.tgmd-pane-header { min-height: 54px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }
.tgmd-pane-header h3, .tgmd-pane-header span { margin: 0; }
.tgmd-pane-header h3 { font-size: 14px; }
.tgmd-pane-header span { color: #64748b; font-size: 11px; }
.tgmd-active-target { padding: 9px 12px; border-top: 1px solid #e2e8f0; background: #eff6ff; }
.tgmd-active-target span { display: block; color: #64748b; font-size: 10px; }
.tgmd-active-target strong { display: block; margin-top: 2px; color: #1d4ed8; font-size: 12px; overflow-wrap: anywhere; }
.tgmd-group-mappings { max-height: 130px; overflow: auto; border-top: 1px solid #e2e8f0; }
.tgmd-group-mappings > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 12px; font-size: 11px; }
.tgmd-group-mappings button { width: 24px; height: 24px; display: grid; place-items: center; border: 0; background: transparent; color: #64748b; cursor: pointer; }
.tgmd-group-mappings svg { width: 14px; height: 14px; }
.tgmd-transfer-column { display: grid; place-items: center; }
.tgmd-transfer-button { position: relative; width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid #2563eb; border-radius: 4px; background: #2563eb; color: #fff; cursor: pointer; }
.tgmd-transfer-button:disabled { border-color: #cbd5e1; background: #e2e8f0; color: #94a3b8; cursor: not-allowed; }
.tgmd-transfer-button svg { width: 18px; height: 18px; }
.tgmd-transfer-button span { position: absolute; top: -8px; right: -8px; min-width: 19px; padding: 2px 5px; border-radius: 10px; background: #0f172a; font-size: 10px; }
.tgmd-operation-header { align-items: flex-start; }
.tgmd-operation-tools { min-width: 0; }
.tgmd-search { width: 170px; height: 32px; display: flex; align-items: center; gap: 6px; padding: 0 8px; border: 1px solid #cbd5e1; border-radius: 4px; }
.tgmd-search svg { width: 14px; height: 14px; color: #64748b; }
.tgmd-search input { min-width: 0; width: 100%; border: 0; outline: 0; background: transparent; font-size: 12px; }
.tgmd-smart-button { height: 32px; padding: 0 9px; border-color: #93c5fd; border-radius: 4px; color: #1d4ed8; }
.tgmd-smart-button:disabled { opacity: .55; cursor: not-allowed; }
.tgmd-select-all { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #e2e8f0; color: #475569; font-size: 11px; }
.tgmd-operation-scroll { min-height: 0; flex: 1; overflow: auto; }
.tgmd-operation-row { display: grid; grid-template-columns: 18px 38px minmax(0, 1fr); gap: 7px; align-items: start; padding: 10px 12px; border-bottom: 1px solid #eef2f7; }
.tgmd-operation-row:hover, .tgmd-operation-row.is-selected { background: #f8fbff; }
.tgmd-operation-row.has-suggestion { border-left: 2px solid #60a5fa; }
.tgmd-operation-sequence { color: #64748b; font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
.tgmd-operation-content { min-width: 0; }
.tgmd-operation-content > strong { display: block; overflow-wrap: anywhere; font-size: 12px; }
.tgmd-suggestion { margin-top: 6px; }
.tgmd-suggestion p { margin: 0 0 6px; color: #64748b; font-size: 10px; }
.tgmd-suggestion small { color: #92400e; }
.tgmd-candidates { display: flex; flex-wrap: wrap; gap: 5px; }
.tgmd-candidates button { max-width: 100%; padding: 4px 7px; border: 1px solid #bfdbfe; border-radius: 3px; background: #eff6ff; color: #1d4ed8; font-size: 10px; cursor: pointer; overflow-wrap: anywhere; }
.tgmd-empty { padding: 32px 16px; color: #94a3b8; text-align: center; font-size: 12px; }

.tgmd-footer { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 18px; border-top: 1px solid #dbe3ec; background: #fff; }
.tgmd-clear-all { min-height: 34px; padding: 0 10px; border-radius: 4px; color: #b91c1c; }
.btn { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 14px; border-radius: 4px; font-weight: 650; cursor: pointer; }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn-outline { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.btn-primary { border: 1px solid #1d4ed8; background: #2563eb; color: #fff; }

@media (max-width: 860px) {
  .tgmd-dialog { width: calc(100vw - 16px); height: calc(100vh - 16px); }
  .tgmd-preview-state { grid-template-columns: 1fr; overflow: auto; }
  .tgmd-preview-tree { min-height: 340px; }
  .tgmd-workspace { grid-template-columns: 1fr; overflow: auto; }
  .tgmd-pane { min-height: 360px; }
  .tgmd-transfer-column { min-height: 42px; }
  .tgmd-transfer-button { transform: rotate(-90deg); }
  .tgmd-operation-header { align-items: stretch; flex-direction: column; }
  .tgmd-operation-tools { width: 100%; }
  .tgmd-search { flex: 1; width: auto; }
  .tgmd-title-block p { white-space: normal; }
}
</style>
