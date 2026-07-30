<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tgmd-backdrop" @click.self="close">
      <section class="tgmd-dialog" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title">
        <!-- Header -->
        <header class="tgmd-header">
          <div class="tgmd-title-wrap">
            <h2 id="template-group-mapping-title">模板分组映射</h2>
            <div class="tgmd-stats-group">
              <span class="tgmd-stat">路线 <strong>{{ operations.length }}</strong></span>
              <span class="tgmd-stat">已映射 <strong>{{ mappedCount }}</strong></span>
              <span class="tgmd-stat">未映射 <strong>{{ unmappedOperations.length }}</strong></span>
            </div>
          </div>
          <div class="tgmd-header-right">
            <button
              class="tgmd-auto-btn"
              type="button"
              :disabled="!unmappedOperations.length || autoMapping"
              @click="autoMapOperations"
            ><MagicStick class="tgmd-auto-icon" />{{ autoMapping ? '正在分析...' : '智能映射' }}</button>
            <button class="tgmd-close" type="button" title="关闭" aria-label="关闭" @click="close"><Close /></button>
          </div>
        </header>

        <div v-if="mappingSummary || mappingWarnings.length" class="tgmd-smart-status" aria-live="polite">
          <span v-if="mappingSummary" class="tgmd-smart-summary">
            本次自动映射 <strong>{{ mappingSummary.autoMapped }}</strong> 项，
            待确认 <strong>{{ mappingSummary.pending }}</strong> 项，
            暂无法判断 <strong>{{ mappingSummary.unresolved }}</strong> 项
          </span>
          <span v-if="mappingWarnings.length" class="tgmd-smart-warning">{{ mappingWarnings.join('；') }}</span>
        </div>

        <!-- Main Workspace -->
        <div class="tgmd-workspace">
          <!-- Left Pane: Target Template Tree -->
          <section class="tgmd-pane tgmd-template-pane">
            <header class="tgmd-pane-head">
              <h3>特征分组</h3>
              <span class="tgmd-count">{{ mappedCount }} 项已映射</span>
            </header>
            <div class="tgmd-template-scroll">
              <div v-for="root in templateRoots" :key="root.id" class="tgmd-root-group">
                <button
                  class="tgmd-root-button"
                  :class="{ 'tgmd-root-button-active': expandedRootIds.has(root.id) }"
                  type="button"
                  @click="toggleRoot(root.id)"
                >
                  <span class="tgmd-chevron" :class="{ 'tgmd-chevron-open': expandedRootIds.has(root.id) }">›</span>
                  <FolderOpened class="tgmd-root-icon" />
                  <span>{{ root.name }}</span>
                </button>

                <div v-if="expandedRootIds.has(root.id)" class="tgmd-leaf-list">
                  <div v-for="leaf in root.children || []" :key="leaf.id" class="tgmd-leaf-block">
                    <button
                      class="tgmd-leaf-button"
                      :class="{ 'tgmd-leaf-button-active': activeGroupId === leaf.id }"
                      type="button"
                      @click="activeGroupId = leaf.id"
                    >
                      <CollectionTag class="tgmd-leaf-icon" />
                      <span class="tgmd-leaf-label">{{ leaf.name }}</span>
                      <span v-if="mappedOperationsForGroup(leaf.id).length" class="tgmd-leaf-count">
                        {{ mappedOperationsForGroup(leaf.id).length }}
                      </span>
                      <!-- One-click clear all items under this leaf group -->
                      <button
                        v-if="mappedOperationsForGroup(leaf.id).length"
                        class="tgmd-leaf-clear"
                        type="button"
                        title="清空该分组下的所有工序"
                        @click.stop="clearGroupMappings(leaf.id)"
                      >
                        <Delete />
                      </button>
                    </button>

                    <!-- Mapped items under this group -->
                    <div v-if="mappedOperationsForGroup(leaf.id).length" class="tgmd-mapped-list">
                      <div
                        v-for="operation in mappedOperationsForGroup(leaf.id)"
                        :key="operationId(operation)"
                        class="tgmd-mapped-operation"
                      >
                        <span class="tgmd-seq">{{ operation.sequence || operationId(operation) }}</span>
                        <span class="tgmd-mapped-name" :title="operation.name">{{ operation.name }}</span>
                        <button
                          class="tgmd-remove"
                          type="button"
                          title="移除映射"
                          aria-label="移除"
                          @click="removeMapping(operation)"
                        ><Close /></button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <!-- Middle Transfer Action Button -->
          <div class="tgmd-center-transfer">
            <button
              class="tgmd-transfer-btn"
              type="button"
              :disabled="!selectedOperationIds.length || !activeGroup"
              :title="transferButtonTooltip"
              @click="mapSelectedOperations"
            >
              <ArrowLeft class="tgmd-transfer-icon" />
              <span v-if="selectedOperationIds.length" class="tgmd-transfer-badge">{{ selectedOperationIds.length }}</span>
            </button>
          </div>

          <!-- Right Pane: Source Operations List -->
          <section class="tgmd-pane tgmd-operation-pane">
            <header class="tgmd-pane-head">
              <div class="tgmd-op-head-left">
                <h3>待映射工序</h3>
                <span v-if="activeGroup" class="tgmd-target-breadcrumb" title="当前选择的映射目标">
                  🎯 目标: {{ activeGroup.path.join(' / ') }}
                </span>
                <span v-else class="tgmd-target-warning">
                  请先选择目标分组
                </span>
              </div>
              <div class="tgmd-op-head-right">
                <!-- Integrated Header Search Bar -->
                <div class="tgmd-header-search">
                  <Search class="tgmd-search-icon" />
                  <input v-model="searchTerm" type="search" placeholder="搜索工序...">
                  <button
                    v-if="searchTerm"
                    class="tgmd-search-clear"
                    type="button"
                    title="清空"
                    @click="searchTerm = ''"
                  ><Close /></button>
                </div>

                <label class="tgmd-select-all">
                  <input
                    type="checkbox"
                    :checked="allVisibleOperationsSelected"
                    :indeterminate="someVisibleOperationsSelected"
                    @change="toggleAllVisibleOperations"
                  >
                  <span>全选</span>
                </label>
              </div>
            </header>

            <div class="tgmd-operation-scroll">
              <TransitionGroup name="tgmd-row">
                <div
                  v-for="operation in filteredUnmappedOperations"
                  :key="operationId(operation)"
                  class="tgmd-operation-row"
                  :class="{
                    'tgmd-operation-row-selected': selectedOperationIds.includes(operationId(operation)),
                    'tgmd-operation-row-review': Boolean(mappingSuggestionFor(operation)),
                  }"
                  @dblclick.prevent="quickMap(operation)"
                >
                  <input
                    type="checkbox"
                    :checked="selectedOperationIds.includes(operationId(operation))"
                    @change="toggleOperationSelection(operationId(operation))"
                  >
                  <span class="tgmd-seq">{{ operation.sequence || operationId(operation) }}</span>
                  <div class="tgmd-operation-content">
                    <span class="tgmd-operation-name">{{ operation.name }}</span>
                    <div v-if="mappingSuggestionFor(operation)" class="tgmd-suggestion" @dblclick.stop>
                      <div class="tgmd-suggestion-meta">
                        <span :class="['tgmd-confidence', confidenceClass(mappingSuggestionFor(operation)!)]">
                          {{ confidenceLabel(mappingSuggestionFor(operation)!) }}
                        </span>
                        <span class="tgmd-suggestion-reason">{{ mappingSuggestionFor(operation)!.reason }}</span>
                      </div>
                      <div v-if="mappingSuggestionFor(operation)!.candidates.length" class="tgmd-candidates">
                        <button
                          v-for="candidate in mappingSuggestionFor(operation)!.candidates"
                          :key="candidate.group_id"
                          class="tgmd-candidate-btn"
                          :class="{ 'tgmd-candidate-recommended': candidate.group_id === mappingSuggestionFor(operation)!.recommendedGroupId }"
                          type="button"
                          :title="candidate.reason"
                          @click.stop="applyCandidate(operation, candidate.group_id)"
                        >
                          {{ candidate.path.join(' / ') }}
                          <span v-if="candidate.group_id === mappingSuggestionFor(operation)!.recommendedGroupId">AI 建议</span>
                        </button>
                      </div>
                      <span v-else class="tgmd-no-candidate">请手动选择左侧分组，或补充工序的加工位置与特征。</span>
                      <span v-if="mappingSuggestionFor(operation)!.warnings.length" class="tgmd-row-warning">
                        {{ mappingSuggestionFor(operation)!.warnings.join('；') }}
                      </span>
                    </div>
                  </div>
                </div>
              </TransitionGroup>
              <div v-if="!filteredUnmappedOperations.length" class="tgmd-empty">
                没有符合条件的待映射工序
              </div>
            </div>

            <!-- Clean Status Footer in Right Pane -->
            <div class="tgmd-pane-foot">
              <span>已选择 <strong>{{ selectedOperationIds.length }}</strong> 项工序</span>
              <span v-if="activeGroup && selectedOperationIds.length" class="tgmd-foot-hint">点击中间按钮映射到「{{ activeGroup.name }}」</span>
            </div>
          </section>
        </div>

        <!-- Footer -->
        <footer class="tgmd-footer">
          <button class="tgmd-clear" type="button" :disabled="!mappedCount" @click="clearMappings"><Delete />清空映射</button>
          <div class="tgmd-footer-actions">
            <button class="btn btn-outline" type="button" @click="close">取消</button>
            <button class="btn btn-primary" type="button" @click="save"><Link />保存映射</button>
          </div>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Close, CollectionTag, Delete, FolderOpened, Link, MagicStick, Search } from '@element-plus/icons-vue'
import { suggestTemplateGroupMappings } from '@/api/extract'
import {
  BUSHING_11_TEMPLATE_TREE,
  buildTemplateGroupMappingSuggestions,
  createTemplateAliasBinding,
  findTemplateGroupById,
  isTrustedTemplateGroupChoice,
  isTemplateMappableOperation,
  type TemplateAliasBinding,
  type TemplateGroupMappingCandidate,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  operations: TemplateOperation[]
  aliases: Record<string, TemplateAliasBinding>
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', aliases: Record<string, TemplateAliasBinding>): void
}>()

const draftAliases = ref<Record<string, TemplateAliasBinding>>({})
const selectedOperationIds = ref<number[]>([])
const activeGroupId = ref('')
const expandedRootIds = ref<Set<string>>(new Set())
const searchTerm = ref('')
const autoMapping = ref(false)
const autoMappingRunId = ref(0)
const mappingWarnings = ref<string[]>([])
const mappingSummary = ref<{ autoMapped: number; pending: number; unresolved: number } | null>(null)

type MappingReviewSuggestion = {
  operationId: number
  reason: string
  confidence: number | null
  source: 'rules' | 'llm' | 'unresolved'
  recommendedGroupId: string | null
  candidates: TemplateGroupMappingCandidate[]
  evidence: string[]
  warnings: string[]
}

const mappingSuggestions = ref<Record<string, MappingReviewSuggestion>>({})

const templateRoots = computed(() => BUSHING_11_TEMPLATE_TREE.children || [])
const activeGroup = computed(() => findTemplateGroupById(activeGroupId.value))
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
const allVisibleOperationsSelected = computed(() => (
  filteredUnmappedOperations.value.length > 0
  && filteredUnmappedOperations.value.every(operation => selectedOperationIds.value.includes(operationId(operation)))
))
const someVisibleOperationsSelected = computed(() => (
  !allVisibleOperationsSelected.value
  && filteredUnmappedOperations.value.some(operation => selectedOperationIds.value.includes(operationId(operation)))
))

const transferButtonTooltip = computed(() => {
  if (!activeGroup.value) return '请在左侧选择目标特征分组'
  if (!selectedOperationIds.value.length) return '请勾选右侧工序'
  return `将选中的 ${selectedOperationIds.value.length} 项工序映射到「${activeGroup.value.name}」`
})

watch(() => props.modelValue, (visible) => {
  autoMappingRunId.value += 1
  autoMapping.value = false
  if (!visible) return
  draftAliases.value = cloneAliases(props.aliases)
  selectedOperationIds.value = []
  searchTerm.value = ''
  mappingSuggestions.value = {}
  mappingWarnings.value = []
  mappingSummary.value = null
  const rootIds = templateRoots.value.map(root => root.id)
  expandedRootIds.value = new Set(rootIds)
  const firstLeaf = templateRoots.value.flatMap(root => root.children || [])[0]
  activeGroupId.value = findTemplateGroupById(activeGroupId.value)?.children?.length
    ? firstLeaf?.id || ''
    : activeGroupId.value || firstLeaf?.id || ''
}, { immediate: true })

function operationId(operation: TemplateOperation) {
  return Number(operation.source_operation_id || operation.id || 0)
}

function cloneAliases(aliases: Record<string, TemplateAliasBinding>) {
  return Object.fromEntries(Object.entries(aliases).map(([id, binding]) => [id, {
    source_operation_id: Number(binding.source_operation_id),
    alias: String(binding.alias || ''),
    template_group_id: String(binding.template_group_id || ''),
    template_group_path: [...(binding.template_group_path || [])],
  }]))
}

function mappedOperationsForGroup(groupId: string) {
  return mappableOperations.value.filter(operation => (
    draftAliases.value[String(operationId(operation))]?.template_group_id === groupId
  ))
}

function mappingSuggestionFor(operation: TemplateOperation) {
  return mappingSuggestions.value[String(operationId(operation))] || null
}

function confidenceLabel(suggestion: MappingReviewSuggestion) {
  if (suggestion.confidence === null) return suggestion.candidates.length ? '需确认位置' : '无法判断'
  return `置信度 ${Math.round(suggestion.confidence * 100)}%`
}

function confidenceClass(suggestion: MappingReviewSuggestion) {
  if (suggestion.confidence !== null && suggestion.confidence >= 0.9) return 'tgmd-confidence-high'
  if (suggestion.candidates.length) return 'tgmd-confidence-medium'
  return 'tgmd-confidence-low'
}

function toggleRoot(rootId: string) {
  const next = new Set(expandedRootIds.value)
  if (next.has(rootId)) next.delete(rootId)
  else next.add(rootId)
  expandedRootIds.value = next
}

function toggleOperationSelection(operationIdToToggle: number) {
  const next = new Set(selectedOperationIds.value)
  if (next.has(operationIdToToggle)) next.delete(operationIdToToggle)
  else next.add(operationIdToToggle)
  selectedOperationIds.value = [...next]
}

function toggleAllVisibleOperations() {
  const visibleIds = filteredUnmappedOperations.value.map(operationId)
  const next = new Set(selectedOperationIds.value)
  if (allVisibleOperationsSelected.value) visibleIds.forEach(id => next.delete(id))
  else visibleIds.forEach(id => next.add(id))
  selectedOperationIds.value = [...next]
}

function mapSelectedOperations() {
  if (!activeGroup.value) return
  const selected = new Set(selectedOperationIds.value)
  mappableOperations.value.forEach((operation) => {
    if (!selected.has(operationId(operation))) return
    const binding = createTemplateAliasBinding(operation, activeGroup.value!)
    if (binding) {
      draftAliases.value[String(binding.source_operation_id)] = binding
      delete mappingSuggestions.value[String(binding.source_operation_id)]
    }
  })
  selectedOperationIds.value = []
}

function quickMap(operation: TemplateOperation) {
  if (!activeGroup.value) return
  const binding = createTemplateAliasBinding(operation, activeGroup.value)
  if (binding) {
    draftAliases.value[String(binding.source_operation_id)] = binding
    delete mappingSuggestions.value[String(binding.source_operation_id)]
  }
}

function applyCandidate(operation: TemplateOperation, groupId: string) {
  const group = findTemplateGroupById(groupId)
  if (!group || draftAliases.value[String(operationId(operation))]) return false
  const binding = createTemplateAliasBinding(operation, group)
  if (!binding) return false
  draftAliases.value[String(binding.source_operation_id)] = binding
  delete mappingSuggestions.value[String(binding.source_operation_id)]
  refreshMappingSummary(mappingSummary.value?.autoMapped || 0)
  return true
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
  if (autoMapping.value || !unmappedOperations.value.length) return
  const runId = ++autoMappingRunId.value
  autoMapping.value = true
  selectedOperationIds.value = []
  mappingWarnings.value = []

  const operations = [...unmappedOperations.value]
  const deterministic = buildTemplateGroupMappingSuggestions(operations)
  const deterministicById = new Map(deterministic.map(item => [item.operation_id, item]))
  const operationById = new Map(operations.map(item => [operationId(item), item]))
  let autoMapped = 0
  const reviews: Record<string, MappingReviewSuggestion> = {}

  deterministic.forEach((suggestion) => {
    const operation = operationById.get(suggestion.operation_id)
    if (!operation) return
    if (suggestion.recommended_group_id && suggestion.confidence === 'high') {
      if (applyCandidate(operation, suggestion.recommended_group_id)) autoMapped += 1
      return
    }
    reviews[String(suggestion.operation_id)] = {
      operationId: suggestion.operation_id,
      reason: suggestion.reasons.join('；'),
      confidence: null,
      source: suggestion.candidates.length ? 'rules' : 'unresolved',
      recommendedGroupId: null,
      candidates: suggestion.candidates,
      evidence: suggestion.evidence,
      warnings: [],
    }
  })
  mappingSuggestions.value = reviews
  refreshMappingSummary(autoMapped)

  const ambiguous = deterministic.filter(item => !item.recommended_group_id && item.candidates.length > 0)
  if (!ambiguous.length) {
    if (runId === autoMappingRunId.value) autoMapping.value = false
    return
  }
  if (!props.projectId) {
    mappingWarnings.value = ['当前项目编号无效，已保留程序候选供人工选择。']
    if (runId === autoMappingRunId.value) autoMapping.value = false
    return
  }

  try {
    const response = await suggestTemplateGroupMappings({
      project_id: props.projectId,
      operations: ambiguous.map((suggestion) => {
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
    if (runId !== autoMappingRunId.value || !props.modelValue) return
    mappingWarnings.value = response.warnings || []
    response.suggestions.forEach((modelSuggestion) => {
      const operation = operationById.get(modelSuggestion.operation_id)
      const ruleSuggestion = deterministicById.get(modelSuggestion.operation_id)
      const review = mappingSuggestions.value[String(modelSuggestion.operation_id)]
      if (!operation || !ruleSuggestion || !review) return
      if (
        !ruleSuggestion.requires_manual_confirmation
        && isTrustedTemplateGroupChoice(modelSuggestion, ruleSuggestion.candidates)
      ) {
        if (applyCandidate(operation, modelSuggestion.group_id!)) autoMapped += 1
        return
      }
      const legalRecommendedId = ruleSuggestion.candidates.some(candidate => candidate.group_id === modelSuggestion.group_id)
        ? modelSuggestion.group_id || null
        : null
      mappingSuggestions.value[String(modelSuggestion.operation_id)] = {
        ...review,
        reason: modelSuggestion.reason || review.reason,
        confidence: modelSuggestion.confidence,
        source: modelSuggestion.source === 'llm' ? 'llm' : 'unresolved',
        recommendedGroupId: legalRecommendedId,
        evidence: modelSuggestion.evidence?.length ? modelSuggestion.evidence : review.evidence,
        warnings: modelSuggestion.warnings || [],
      }
    })
  } catch {
    if (runId !== autoMappingRunId.value || !props.modelValue) return
    mappingWarnings.value = ['智能服务暂时不可用，程序候选仍可直接选择。']
  } finally {
    if (runId !== autoMappingRunId.value || !props.modelValue) return
    refreshMappingSummary(autoMapped)
    autoMapping.value = false
  }
}

function removeMapping(operation: TemplateOperation) {
  delete draftAliases.value[String(operationId(operation))]
}

function clearGroupMappings(groupId: string) {
  const operationsInGroup = mappedOperationsForGroup(groupId)
  operationsInGroup.forEach((operation) => {
    delete draftAliases.value[String(operationId(operation))]
  })
}

function clearMappings() {
  draftAliases.value = {}
  selectedOperationIds.value = []
}

function close() {
  emit('update:modelValue', false)
}

function save() {
  emit('save', cloneAliases(draftAliases.value))
  close()
}
</script>

<style scoped>
/* ── Backdrop & Dialog Shell ── */
.tgmd-backdrop {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  padding: 16px;
  background: rgba(15, 23, 42, 0.45);
}
.tgmd-dialog {
  display: flex;
  flex-direction: column;
  width: min(1080px, 100%);
  max-height: min(620px, calc(100vh - 32px));
  overflow: hidden;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: var(--radius-md, 12px);
  background: var(--bg-card, #fff);
  box-shadow: var(--shadow-lg, 0 16px 40px -4px rgba(0,0,0,0.12));
}

/* ── Shared flex row ── */
.tgmd-header,
.tgmd-footer,
.tgmd-pane-head,
.tgmd-pane-foot,
.tgmd-root-button,
.tgmd-leaf-button,
.tgmd-operation-row,
.tgmd-mapped-operation,
.tgmd-title-wrap,
.tgmd-stats-group,
.tgmd-header-right,
.tgmd-footer-actions,
.tgmd-select-all,
.tgmd-op-head-left,
.tgmd-op-head-right,
.tgmd-header-search {
  display: flex;
  align-items: center;
}

/* ── Header ── */
.tgmd-header {
  justify-content: space-between;
  gap: 12px;
  padding: 10px 16px;
  border-bottom: 1px solid var(--border-light, #e2e8f0);
}
.tgmd-title-wrap { gap: 12px; min-width: 0; }
.tgmd-title-wrap h2 { margin: 0; color: var(--text-primary, #0f172a); font-size: 14px; font-weight: 600; line-height: 1.4; }
.tgmd-stats-group { gap: 6px; }
.tgmd-header-right { gap: 8px; flex-shrink: 0; }
.tgmd-stat {
  display: inline-flex;
  align-items: center;
  height: 22px;
  padding: 0 7px;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: 4px;
  color: var(--text-muted, #94a3b8);
  font-size: 11px;
  white-space: nowrap;
}
.tgmd-stat strong { margin-left: 3px; color: var(--text-primary, #0f172a); }

/* Smart mapping button */
.tgmd-auto-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 28px;
  padding: 0 10px;
  border: 1px solid #c7d2fe;
  border-radius: 6px;
  background: #f5f7ff;
  color: var(--accent, #4f46e5);
  font-size: 11.5px;
  font-weight: 600;
  cursor: pointer;
  transition: var(--transition, all 0.2s ease);
  white-space: nowrap;
}
.tgmd-auto-btn:hover:not(:disabled) { background: var(--accent-light, #e0e7ff); border-color: #a5b4fc; }
.tgmd-auto-btn:disabled { opacity: 0.4; cursor: not-allowed; }
.tgmd-auto-icon { width: 14px; height: 14px; }

.tgmd-smart-status {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 7px 16px;
  border-bottom: 1px solid #dbeafe;
  background: #f8fbff;
  color: #475569;
  font-size: 11px;
}
.tgmd-smart-summary strong { color: #3730a3; }
.tgmd-smart-warning {
  min-width: 0;
  overflow: hidden;
  color: #b45309;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-close,
.tgmd-remove,
.tgmd-leaf-clear,
.tgmd-search-clear {
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--text-muted, #94a3b8);
  cursor: pointer;
  transition: var(--transition, all 0.2s ease);
}
.tgmd-close { width: 26px; height: 26px; border-radius: 6px; flex-shrink: 0; }
.tgmd-close:hover { background: var(--bg-primary, #f8fafc); color: var(--text-secondary, #475569); }
.tgmd-close :deep(svg),
.tgmd-remove :deep(svg),
.tgmd-leaf-clear :deep(svg),
.tgmd-search-clear :deep(svg) { width: 13px; height: 13px; }

.tgmd-search-clear {
  width: 18px;
  height: 18px;
  border-radius: 50%;
  color: #94a3b8;
}
.tgmd-search-clear:hover { background: #e2e8f0; color: #475569; }

/* Group clear button */
.tgmd-leaf-clear {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: #94a3b8;
  opacity: 0.85;
  margin-left: 2px;
}
.tgmd-leaf-clear:hover {
  background: #fee2e2;
  color: var(--danger, #ef4444);
  opacity: 1;
}

/* ── Workspace 50% / 50% Equal Split ── */
.tgmd-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 42px minmax(0, 1fr);
  gap: 0;
  min-height: 0;
  flex: 1;
  padding: 10px 12px;
  background: var(--bg-primary, #f8fafc);
}

.tgmd-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: var(--radius-sm, 8px);
  background: var(--bg-card, #fff);
}

/* Center Transfer Button Column */
.tgmd-center-transfer {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 0 2px;
}
.tgmd-transfer-btn {
  position: relative;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-light, #cbd5e1);
  border-radius: 50%;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #475569);
  cursor: pointer;
  box-shadow: var(--shadow-sm, 0 1px 2px rgba(0,0,0,0.05));
  transition: var(--transition, all 0.2s ease);
}
.tgmd-transfer-btn:hover:not(:disabled) {
  border-color: var(--accent, #4f46e5);
  background: var(--accent, #4f46e5);
  color: #fff;
  transform: scale(1.1);
  box-shadow: 0 4px 12px rgba(79, 70, 229, 0.3);
}
.tgmd-transfer-btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
  box-shadow: none;
}
.tgmd-transfer-icon { width: 16px; height: 16px; }
.tgmd-transfer-badge {
  position: absolute;
  top: -5px;
  right: -5px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: #ef4444;
  color: #fff;
  font-size: 9.5px;
  font-weight: bold;
  border: 1.5px solid #fff;
}

.tgmd-pane-head {
  justify-content: space-between;
  gap: 8px;
  padding: 6px 10px;
  border-bottom: 1px solid var(--border-light, #e2e8f0);
  background: #fafbfc;
  min-height: 36px;
}
.tgmd-pane-head h3 { margin: 0; color: var(--text-primary, #0f172a); font-size: 12px; font-weight: 600; line-height: 1.4; flex-shrink: 0; }
.tgmd-op-head-left { gap: 6px; min-width: 0; flex: 1; }
.tgmd-op-head-right { gap: 10px; flex-shrink: 0; }

/* Header Integrated Search Bar */
.tgmd-header-search {
  gap: 4px;
  height: 24px;
  padding: 0 6px;
  border: 1px solid var(--border-light, #cbd5e1);
  border-radius: 5px;
  background: #fff;
  transition: var(--transition, all 0.15s ease);
}
.tgmd-header-search:focus-within {
  border-color: var(--accent, #4f46e5);
  box-shadow: 0 0 0 2px rgba(79, 70, 229, 0.12);
}
.tgmd-search-icon { width: 12px; height: 12px; color: #94a3b8; flex-shrink: 0; }
.tgmd-header-search:focus-within .tgmd-search-icon { color: var(--accent, #4f46e5); }
.tgmd-header-search input {
  width: 110px;
  border: 0;
  outline: 0;
  color: var(--text-primary, #0f172a);
  font-size: 11px;
  background: transparent;
  transition: width 0.2s ease;
}
.tgmd-header-search input:focus {
  width: 140px;
}
.tgmd-header-search input::placeholder { color: #94a3b8; }

.tgmd-target-breadcrumb {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: #eef2ff;
  color: var(--accent-hover, #4338ca);
  font-size: 10.5px;
  font-weight: 600;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.tgmd-target-warning {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border-radius: 4px;
  background: #fff7ed;
  color: #c2410c;
  font-size: 10.5px;
  font-weight: 500;
}

.tgmd-count {
  display: inline-flex;
  align-items: center;
  height: 20px;
  padding: 0 6px;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: 4px;
  background: #fff;
  color: var(--text-secondary, #475569);
  font-size: 10px;
  font-weight: 500;
  white-space: nowrap;
}

/* ── Custom Subtle Scrollbars ── */
.tgmd-template-scroll,
.tgmd-operation-scroll {
  min-height: 0;
  overflow: auto;
  padding: 6px;
  scrollbar-width: thin;
  scrollbar-color: rgba(148, 163, 184, 0.25) transparent;
}
.tgmd-template-scroll::-webkit-scrollbar,
.tgmd-operation-scroll::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}
.tgmd-template-scroll::-webkit-scrollbar-track,
.tgmd-operation-scroll::-webkit-scrollbar-track {
  background: transparent;
}
.tgmd-template-scroll::-webkit-scrollbar-thumb,
.tgmd-operation-scroll::-webkit-scrollbar-thumb {
  background: rgba(148, 163, 184, 0.25);
  border-radius: 999px;
}
.tgmd-template-scroll::-webkit-scrollbar-thumb:hover,
.tgmd-operation-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(148, 163, 184, 0.5);
}

.tgmd-root-group + .tgmd-root-group { margin-top: 2px; }

.tgmd-root-button,
.tgmd-leaf-button {
  width: 100%;
  border: 0;
  text-align: left;
  cursor: pointer;
  transition: var(--transition, all 0.15s ease);
}

.tgmd-root-button {
  gap: 6px;
  min-height: 30px;
  padding: 0 6px;
  border-radius: 4px;
  background: transparent;
  color: var(--text-primary, #0f172a);
  font-size: 12px;
  font-weight: 600;
}
.tgmd-root-button:hover { background: #f1f5f9; }
.tgmd-root-button-active { color: var(--accent, #4f46e5); }
.tgmd-chevron { width: 10px; color: var(--text-muted, #94a3b8); font-size: 16px; line-height: 1; transform: rotate(0deg); transition: transform 0.15s ease; }
.tgmd-chevron-open { transform: rotate(90deg); }
.tgmd-root-icon { width: 14px; height: 14px; color: var(--accent, #4f46e5); }

.tgmd-leaf-list {
  margin: 1px 0 2px 12px;
  padding-left: 6px;
  border-left: 1px dashed var(--border-light, #cbd5e1);
}
.tgmd-leaf-block + .tgmd-leaf-block { margin-top: 1px; }

.tgmd-leaf-button {
  position: relative;
  gap: 6px;
  min-height: 26px;
  padding: 0 6px;
  border-radius: 4px;
  background: transparent;
  color: var(--text-secondary, #475569);
  font-size: 11.5px;
}
.tgmd-leaf-button:hover { background: #f1f5f9; }
.tgmd-leaf-button-active {
  background: #eef2ff !important;
  color: var(--accent-hover, #4338ca) !important;
  font-weight: 600;
}

.tgmd-leaf-icon { flex: 0 0 auto; width: 13px; height: 13px; color: var(--text-muted, #94a3b8); }
.tgmd-leaf-button-active .tgmd-leaf-icon { color: var(--accent, #4f46e5); }

.tgmd-leaf-label { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-leaf-count {
  display: inline-flex;
  min-width: 15px;
  height: 15px;
  align-items: center;
  justify-content: center;
  border-radius: 999px;
  background: var(--accent, #4f46e5);
  color: #fff;
  font-size: 9.5px;
  font-weight: 700;
  padding: 0 4px;
}

.tgmd-mapped-list {
  display: grid;
  gap: 2px;
  margin: 2px 0 4px 10px;
  padding-left: 6px;
  border-left: 1px dotted #cbd5e1;
}
.tgmd-mapped-operation {
  min-width: 0;
  gap: 6px;
  min-height: 24px;
  padding: 0 6px;
  border-radius: 4px;
  background: var(--bg-primary, #f8fafc);
  border: 1px solid #f1f5f9;
  transition: var(--transition, all 0.15s ease);
}
.tgmd-mapped-operation:hover {
  background: #fff;
  border-color: #cbd5e1;
}
.tgmd-mapped-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--text-secondary, #475569);
  font-size: 11px;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tgmd-remove {
  width: 18px;
  height: 18px;
  border-radius: 3px;
  opacity: 0.6;
}
.tgmd-mapped-operation:hover .tgmd-remove { opacity: 1; }
.tgmd-remove:hover { background: #fee2e2; color: var(--danger, #ef4444); }

/* ── Operation Pane ── */
.tgmd-operation-pane { position: relative; }
.tgmd-select-all { gap: 5px; color: var(--text-muted, #94a3b8); font-size: 11px; white-space: nowrap; cursor: pointer; }
.tgmd-select-all input,
.tgmd-operation-row input { width: 14px; height: 14px; accent-color: var(--accent, #4f46e5); }
.tgmd-operation-scroll { display: grid; align-content: start; gap: 4px; padding-top: 6px; }

/* Minimal, spacious row style */
.tgmd-operation-row {
  position: relative;
  gap: 8px;
  min-height: 34px;
  padding: 0 10px;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: 6px;
  background: var(--bg-card, #fff);
  cursor: pointer;
  transition: var(--transition, all 0.2s ease);
  user-select: none;
}
.tgmd-operation-row:hover { border-color: #a5b4fc; background: #f8faff; }
.tgmd-operation-row-selected {
  border-color: #a5b4fc;
  background: #f5f7ff;
}
.tgmd-operation-row-review {
  min-height: 66px;
  align-items: flex-start;
  padding-top: 8px;
  padding-bottom: 8px;
}
.tgmd-operation-row-review > input,
.tgmd-operation-row-review > .tgmd-seq { margin-top: 1px; }

.tgmd-seq {
  display: inline-flex;
  min-width: 24px;
  height: 18px;
  align-items: center;
  justify-content: center;
  border-radius: 3px;
  background: var(--bg-primary, #f8fafc);
  color: var(--text-secondary, #475569);
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 10px;
  font-weight: 700;
}
.tgmd-operation-name {
  min-width: 0;
  flex: 1;
  overflow: hidden;
  color: var(--text-primary, #0f172a);
  font-size: 12px;
  font-weight: 500;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tgmd-operation-content {
  display: flex;
  min-width: 0;
  flex: 1;
  flex-direction: column;
  gap: 5px;
}
.tgmd-operation-content > .tgmd-operation-name { display: block; }
.tgmd-suggestion {
  display: grid;
  gap: 5px;
  min-width: 0;
}
.tgmd-suggestion-meta,
.tgmd-candidates {
  display: flex;
  align-items: center;
  gap: 5px;
  min-width: 0;
  flex-wrap: wrap;
}
.tgmd-confidence {
  display: inline-flex;
  align-items: center;
  height: 18px;
  padding: 0 5px;
  border-radius: 4px;
  font-size: 9.5px;
  font-weight: 600;
  white-space: nowrap;
}
.tgmd-confidence-high { background: #dcfce7; color: #166534; }
.tgmd-confidence-medium { background: #fff7ed; color: #c2410c; }
.tgmd-confidence-low { background: #f1f5f9; color: #64748b; }
.tgmd-suggestion-reason {
  min-width: 0;
  flex: 1;
  color: #64748b;
  font-size: 10px;
  line-height: 1.35;
}
.tgmd-candidate-btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 23px;
  padding: 0 7px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  background: #fff;
  color: #334155;
  cursor: pointer;
  font-size: 10px;
  transition: all 0.15s ease;
}
.tgmd-candidate-btn:hover { border-color: #818cf8; background: #eef2ff; color: #3730a3; }
.tgmd-candidate-recommended { border-color: #a5b4fc; background: #f5f7ff; color: #4338ca; }
.tgmd-candidate-btn span {
  padding: 1px 4px;
  border-radius: 3px;
  background: #e0e7ff;
  font-size: 8.5px;
  font-weight: 600;
}
.tgmd-no-candidate,
.tgmd-row-warning { color: #64748b; font-size: 10px; line-height: 1.4; }
.tgmd-row-warning { color: #b45309; }
.tgmd-empty {
  padding: 32px 12px;
  color: var(--text-muted, #94a3b8);
  font-size: 12px;
  text-align: center;
}

/* Clean Pane Foot */
.tgmd-pane-foot {
  justify-content: space-between;
  padding: 6px 10px;
  border-top: 1px solid var(--border-light, #e2e8f0);
  background: #fafbfc;
  color: var(--text-muted, #94a3b8);
  font-size: 11px;
}
.tgmd-pane-foot strong { color: var(--text-primary, #0f172a); }
.tgmd-foot-hint { color: var(--accent, #4f46e5); font-weight: 500; }

/* ── Row slide-out transition ── */
.tgmd-row-move,
.tgmd-row-enter-active,
.tgmd-row-leave-active { transition: all 0.25s ease; }
.tgmd-row-enter-from { opacity: 0; transform: translateX(20px); }
.tgmd-row-leave-to { opacity: 0; transform: translateX(-20px); }
.tgmd-row-leave-active { position: absolute; width: calc(100% - 12px); }

/* ── Footer ── */
.tgmd-footer {
  justify-content: space-between;
  gap: 10px;
  padding: 8px 12px;
  border-top: 1px solid var(--border-light, #e2e8f0);
  background: var(--bg-card, #fff);
}
.tgmd-footer-actions { justify-content: flex-end; gap: 8px; }
.tgmd-footer .btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 12px;
  border-radius: 6px;
  font-size: 12px;
}
.tgmd-footer .btn :deep(svg),
.tgmd-clear :deep(svg) { width: 13px; height: 13px; }
.tgmd-clear {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 30px;
  padding: 0 8px;
  border: 1px solid var(--border-light, #e2e8f0);
  border-radius: 6px;
  background: var(--bg-card, #fff);
  color: var(--text-secondary, #475569);
  cursor: pointer;
  font-size: 11px;
  transition: var(--transition, all 0.2s ease);
}
.tgmd-clear:hover:not(:disabled) { border-color: #fca5a5; background: #fef2f2; color: var(--danger, #ef4444); }
.tgmd-clear:disabled { color: #cbd5e1; cursor: not-allowed; }

/* ── Responsive ── */
@media (max-width: 900px) {
  .tgmd-backdrop { padding: 8px; }
  .tgmd-dialog { max-height: calc(100vh - 16px); }
  .tgmd-header { flex-wrap: wrap; }
  .tgmd-workspace { grid-template-columns: 1fr; gap: 8px; overflow: auto; }
  .tgmd-center-transfer { display: none; }
  .tgmd-template-pane,
  .tgmd-operation-pane { min-height: 240px; }
  .tgmd-footer { flex-wrap: wrap; }
  .tgmd-footer-actions .btn { flex: 1; justify-content: center; }
}
</style>
