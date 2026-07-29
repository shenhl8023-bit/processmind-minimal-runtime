<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tgmd-backdrop" @click.self="close">
      <section class="tgmd-dialog" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title">
        <header class="tgmd-header">
          <div class="tgmd-title-wrap">
            <div class="tgmd-title-icon"><Link /></div>
            <div>
              <h2 id="template-group-mapping-title">模板分组映射</h2>
              <p>衬套-11 分组模板</p>
            </div>
          </div>
          <div class="tgmd-header-actions">
            <span class="tgmd-stat">路线 <strong>{{ operations.length }}</strong></span>
            <span class="tgmd-stat">已映射 <strong>{{ mappedCount }}</strong></span>
            <span class="tgmd-stat">未映射 <strong>{{ unmappedOperations.length }}</strong></span>
            <button class="tgmd-close" type="button" title="关闭" aria-label="关闭" @click="close"><Close /></button>
          </div>
        </header>

        <div class="tgmd-workspace">
          <section class="tgmd-pane tgmd-template-pane">
            <header class="tgmd-pane-head">
              <div>
                <h3>基础分组模板</h3>
                <p>将工序归入零件特征位置</p>
              </div>
              <span class="tgmd-count">{{ mappedCount }} 项关系</span>
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
                    </button>
                    <div v-if="mappedOperationsForGroup(leaf.id).length" class="tgmd-mapped-list">
                      <div v-for="operation in mappedOperationsForGroup(leaf.id)" :key="operationId(operation)" class="tgmd-mapped-operation">
                        <span class="tgmd-seq">{{ operation.sequence || operationId(operation) }}</span>
                        <span class="tgmd-mapped-name">{{ aliasForOperation(operation) }}</span>
                        <button
                          class="tgmd-remove"
                          type="button"
                          title="移回未映射列表"
                          aria-label="移回未映射列表"
                          @click="removeMapping(operation)"
                        ><Close /></button>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </section>

          <div class="tgmd-transfer">
            <button
              class="tgmd-transfer-button"
              type="button"
              title="映射到当前分组"
              aria-label="映射到当前分组"
              :disabled="!selectedOperationIds.length || !activeGroup"
              @click="mapSelectedOperations"
            ><ArrowLeft /></button>
            <span>{{ selectedOperationIds.length }}</span>
          </div>

          <section class="tgmd-pane tgmd-operation-pane">
            <header class="tgmd-pane-head">
              <div>
                <h3>待映射工序</h3>
                <p>{{ activeGroup ? activeGroup.path.join(' / ') : '请选择目标分组' }}</p>
              </div>
              <label class="tgmd-select-all">
                <input
                  type="checkbox"
                  :checked="allVisibleOperationsSelected"
                  :indeterminate="someVisibleOperationsSelected"
                  @change="toggleAllVisibleOperations"
                >
                <span>全选当前</span>
              </label>
            </header>
            <div class="tgmd-search-row">
              <Search class="tgmd-search-icon" />
              <input v-model="searchTerm" type="search" placeholder="搜索工序、来源工序或工步">
            </div>
            <div class="tgmd-operation-scroll">
              <label v-for="operation in filteredUnmappedOperations" :key="operationId(operation)" class="tgmd-operation-row">
                <input
                  type="checkbox"
                  :checked="selectedOperationIds.includes(operationId(operation))"
                  @change="toggleOperationSelection(operationId(operation))"
                >
                <span class="tgmd-seq">{{ operation.sequence || operationId(operation) }}</span>
                <span class="tgmd-operation-name">{{ operation.name }}</span>
                <span class="tgmd-family">{{ operation.step_family }}</span>
              </label>
              <div v-if="!filteredUnmappedOperations.length" class="tgmd-empty">没有符合条件的待映射工序</div>
            </div>
          </section>
        </div>

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
import { ArrowLeft, Close, CollectionTag, Delete, FolderOpened, Link, Search } from '@element-plus/icons-vue'
import {
  BUSHING_11_TEMPLATE_TREE,
  createTemplateAliasBinding,
  findTemplateGroupById,
  isTemplateMappableOperation,
  type TemplateAliasBinding,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'

const props = defineProps<{
  modelValue: boolean
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

watch(() => props.modelValue, (visible) => {
  if (!visible) return
  draftAliases.value = cloneAliases(props.aliases)
  selectedOperationIds.value = []
  searchTerm.value = ''
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

function aliasForOperation(operation: TemplateOperation) {
  return draftAliases.value[String(operationId(operation))]?.alias || operation.name
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
    if (binding) draftAliases.value[String(binding.source_operation_id)] = binding
  })
  selectedOperationIds.value = []
}

function removeMapping(operation: TemplateOperation) {
  delete draftAliases.value[String(operationId(operation))]
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
.tgmd-backdrop {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, 0.52);
}

.tgmd-dialog {
  display: flex;
  flex-direction: column;
  width: min(1480px, 100%);
  max-height: min(800px, calc(100vh - 48px));
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 24px 64px rgba(15, 23, 42, 0.24);
}

.tgmd-header,
.tgmd-footer,
.tgmd-pane-head,
.tgmd-root-button,
.tgmd-leaf-button,
.tgmd-operation-row,
.tgmd-mapped-operation,
.tgmd-header-actions,
.tgmd-title-wrap,
.tgmd-footer-actions,
.tgmd-select-all,
.tgmd-search-row {
  display: flex;
  align-items: center;
}

.tgmd-header {
  justify-content: space-between;
  gap: 16px;
  min-height: 80px;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
}

.tgmd-title-wrap { gap: 12px; min-width: 0; }
.tgmd-title-icon {
  display: grid;
  width: 34px;
  height: 34px;
  place-items: center;
  border-radius: 8px;
  background: #eef2ff;
  color: #4f46e5;
}
.tgmd-title-icon :deep(svg) { width: 18px; height: 18px; }
.tgmd-title-wrap h2 { margin: 0; color: #172033; font-size: 18px; line-height: 1.35; }
.tgmd-title-wrap p,
.tgmd-pane-head p { margin: 3px 0 0; color: #8a97a8; font-size: 12px; line-height: 1.4; }
.tgmd-header-actions { justify-content: flex-end; flex-wrap: wrap; gap: 8px; }
.tgmd-stat,
.tgmd-count {
  display: inline-flex;
  align-items: center;
  min-height: 28px;
  padding: 0 9px;
  border: 1px solid #dbe3ee;
  border-radius: 6px;
  color: #64748b;
  font-size: 12px;
  white-space: nowrap;
}
.tgmd-stat strong { margin-left: 4px; color: #172033; }
.tgmd-close,
.tgmd-remove {
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: #7b8797;
  cursor: pointer;
}
.tgmd-close { width: 30px; height: 30px; border-radius: 6px; }
.tgmd-close:hover { background: #f1f5f9; color: #334155; }
.tgmd-close :deep(svg),
.tgmd-remove :deep(svg) { width: 16px; height: 16px; }

.tgmd-workspace {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 54px minmax(0, 1.28fr);
  min-height: 0;
  flex: 1;
  padding: 14px 18px;
  background: #f8fafc;
}
.tgmd-pane {
  display: flex;
  min-width: 0;
  min-height: 0;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-top: 3px solid #0f766e;
  border-radius: 8px;
  background: #ffffff;
}
.tgmd-operation-pane { border-top-color: #ea580c; }
.tgmd-pane-head { justify-content: space-between; gap: 12px; min-height: 66px; padding: 11px 14px; border-bottom: 1px solid #e8eef5; }
.tgmd-pane-head h3 { margin: 0; color: #172033; font-size: 14px; line-height: 1.35; }
.tgmd-count { border-color: #dbe4ff; background: #f5f7ff; color: #4f46e5; }

.tgmd-template-scroll,
.tgmd-operation-scroll { min-height: 0; overflow: auto; padding: 10px; }
.tgmd-root-group + .tgmd-root-group { margin-top: 7px; }
.tgmd-root-button,
.tgmd-leaf-button {
  width: 100%;
  border: 0;
  text-align: left;
  cursor: pointer;
}
.tgmd-root-button { gap: 8px; min-height: 42px; padding: 0 10px; border: 1px solid transparent; border-radius: 6px; background: #f8fafc; color: #334155; font-size: 13px; font-weight: 700; }
.tgmd-root-button:hover,
.tgmd-root-button-active { border-color: #c7d2fe; background: #eef2ff; color: #3730a3; }
.tgmd-chevron { width: 10px; color: #94a3b8; font-size: 20px; line-height: 1; transform: rotate(0deg); transition: transform 0.16s ease; }
.tgmd-chevron-open { transform: rotate(90deg); }
.tgmd-root-icon { width: 18px; height: 18px; color: #0f766e; }
.tgmd-leaf-list { margin: 4px 0 0 18px; padding-left: 11px; border-left: 1px solid #dbe3ee; }
.tgmd-leaf-block + .tgmd-leaf-block { margin-top: 2px; }
.tgmd-leaf-button { gap: 8px; min-height: 34px; padding: 0 8px; border-radius: 5px; background: #ffffff; color: #475569; font-size: 12px; }
.tgmd-leaf-button:hover,
.tgmd-leaf-button-active { background: #f5f7ff; color: #4338ca; }
.tgmd-leaf-icon { flex: 0 0 auto; width: 15px; height: 15px; color: #94a3b8; }
.tgmd-leaf-label { min-width: 0; flex: 1; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-leaf-count { display: inline-flex; min-width: 20px; height: 20px; align-items: center; justify-content: center; border-radius: 5px; background: #4f46e5; color: #ffffff; font-size: 11px; font-weight: 700; }
.tgmd-mapped-list { display: grid; gap: 4px; margin: 0 0 8px 8px; padding: 3px 0 1px; }
.tgmd-mapped-operation { min-width: 0; gap: 7px; min-height: 32px; padding: 0 7px; border: 1px solid #dde5ef; border-radius: 5px; background: #ffffff; }
.tgmd-mapped-name { min-width: 0; flex: 1; overflow: hidden; color: #334155; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-remove { width: 22px; height: 22px; border-radius: 4px; }
.tgmd-remove:hover { background: #fee2e2; color: #dc2626; }

.tgmd-transfer { display: flex; align-items: center; justify-content: center; gap: 6px; flex-direction: column; color: #6366f1; font-size: 11px; font-weight: 700; }
.tgmd-transfer-button { display: grid; width: 38px; height: 38px; place-items: center; border: 0; border-radius: 50%; background: #3b82f6; color: #ffffff; cursor: pointer; box-shadow: 0 5px 12px rgba(59, 130, 246, 0.24); }
.tgmd-transfer-button:hover:not(:disabled) { background: #2563eb; }
.tgmd-transfer-button:disabled { background: #cbd5e1; box-shadow: none; cursor: not-allowed; }
.tgmd-transfer-button :deep(svg) { width: 18px; height: 18px; }

.tgmd-search-row { gap: 8px; margin: 10px 12px 0; min-height: 36px; padding: 0 10px; border: 1px solid #dbe3ee; border-radius: 6px; background: #ffffff; color: #94a3b8; }
.tgmd-search-row:focus-within { border-color: #818cf8; box-shadow: 0 0 0 2px rgba(129, 140, 248, 0.12); }
.tgmd-search-icon { width: 15px; height: 15px; }
.tgmd-search-row input { min-width: 0; flex: 1; border: 0; outline: 0; color: #334155; font-size: 12px; }
.tgmd-search-row input::placeholder { color: #a8b2c0; }
.tgmd-select-all { gap: 6px; color: #64748b; font-size: 12px; white-space: nowrap; cursor: pointer; }
.tgmd-select-all input,
.tgmd-operation-row input { width: 15px; height: 15px; accent-color: #4f46e5; }
.tgmd-operation-scroll { display: grid; align-content: start; gap: 7px; padding-top: 10px; }
.tgmd-operation-row { gap: 9px; min-height: 48px; padding: 0 11px; border: 1px solid #dde5ef; border-radius: 6px; background: #ffffff; cursor: pointer; }
.tgmd-operation-row:hover { border-color: #a5b4fc; background: #f8faff; }
.tgmd-seq { display: inline-flex; min-width: 28px; height: 21px; align-items: center; justify-content: center; border-radius: 4px; background: #f1f5f9; color: #475569; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 10px; font-weight: 700; }
.tgmd-operation-name { min-width: 0; flex: 1; overflow: hidden; color: #1e293b; font-size: 13px; font-weight: 700; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-family { max-width: 96px; overflow: hidden; color: #94a3b8; font-size: 11px; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-empty { padding: 44px 16px; color: #94a3b8; font-size: 13px; text-align: center; }

.tgmd-footer { justify-content: space-between; gap: 14px; min-height: 66px; padding: 12px 18px; border-top: 1px solid #e5e7eb; background: #ffffff; }
.tgmd-footer-actions { justify-content: flex-end; gap: 10px; }
.tgmd-footer .btn { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 0 14px; border-radius: 6px; }
.tgmd-footer .btn :deep(svg),
.tgmd-clear :deep(svg) { width: 15px; height: 15px; }
.tgmd-clear { display: inline-flex; align-items: center; gap: 6px; min-height: 34px; padding: 0 10px; border: 1px solid #cbd5e1; border-radius: 6px; background: #ffffff; color: #475569; cursor: pointer; font-size: 12px; }
.tgmd-clear:hover:not(:disabled) { border-color: #fca5a5; background: #fff7f7; color: #b91c1c; }
.tgmd-clear:disabled { color: #cbd5e1; cursor: not-allowed; }

@media (max-width: 900px) {
  .tgmd-backdrop { padding: 10px; }
  .tgmd-dialog { max-height: calc(100vh - 20px); }
  .tgmd-header { align-items: flex-start; flex-direction: column; }
  .tgmd-header-actions { justify-content: flex-start; }
  .tgmd-workspace { grid-template-columns: 1fr; gap: 10px; overflow: auto; }
  .tgmd-template-pane,
  .tgmd-operation-pane { min-height: 300px; }
  .tgmd-transfer { flex-direction: row; min-height: 42px; }
  .tgmd-transfer-button { transform: rotate(-90deg); }
  .tgmd-footer { align-items: stretch; flex-direction: column; }
  .tgmd-footer-actions { justify-content: stretch; }
  .tgmd-footer-actions .btn { flex: 1; justify-content: center; }
}
</style>
