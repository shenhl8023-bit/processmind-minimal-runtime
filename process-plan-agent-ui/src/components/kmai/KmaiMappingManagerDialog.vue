<template>
  <section class="kmai-manager" aria-label="KmAI 映射管理">
    <div class="kmai-manager__toolbar">
      <div>
        <h3>因子映射</h3>
        <p>{{ projectId === null ? '当前仅显示内置和全局映射。' : `同时显示项目 ${projectId} 的覆盖映射。` }}</p>
      </div>
      <button class="kmai-manager__button" type="button" :disabled="loading || busyId !== null" @click="load">
        刷新
      </button>
    </div>

    <div class="kmai-manager__filters">
      <input v-model="filters.search" type="search" placeholder="搜索来源、目标或更新人" aria-label="搜索映射" />
      <select v-model="filters.sourceField" aria-label="来源字段筛选">
        <option value="all">全部来源字段</option>
        <option v-for="field in sourceFields" :key="field" :value="field">{{ field }}</option>
      </select>
      <select v-model="filters.scope" aria-label="作用域筛选">
        <option value="all">全部作用域</option>
        <option value="builtin">内置</option>
        <option value="global">全局</option>
        <option value="project">项目</option>
      </select>
      <select v-model="filters.status" aria-label="状态筛选">
        <option value="all">全部状态</option>
        <option value="active">启用</option>
        <option value="inactive">停用</option>
      </select>
    </div>

    <p v-if="loadError" class="kmai-manager__error">{{ loadError }}</p>
    <div v-if="loading" class="kmai-manager__empty">正在加载映射…</div>
    <div v-else-if="filteredRows.length === 0" class="kmai-manager__empty">没有符合条件的映射。</div>
    <div v-else class="kmai-manager__table-wrap">
      <table class="kmai-manager__table">
        <thead>
          <tr>
            <th>来源</th>
            <th>目标因子</th>
            <th>范围 / 状态</th>
            <th>版本信息</th>
            <th class="kmai-manager__actions-heading">操作</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in filteredRows" :key="row.mapping.mapping_identity" :class="{ 'is-inactive': row.isInactive }">
            <td>
              <code>{{ row.mapping.source_field }}</code>
              <strong>{{ row.mapping.source_value }}</strong>
            </td>
            <td>
              <strong>{{ row.mapping.target_factor_name }}</strong>
              <code>{{ row.mapping.target_factor_key }}</code>
              <span>{{ row.mapping.target_factor_category }}</span>
              <small v-if="row.overriddenTarget" class="kmai-manager__overridden">
                覆盖目标：{{ row.overriddenTarget.factorName }}（{{ row.overriddenTarget.factorKey }}）
              </small>
            </td>
            <td>
              <span class="kmai-manager__badge">{{ row.scopeLabel }}</span>
              <span class="kmai-manager__badge" :class="{ 'is-muted': row.isInactive }">{{ row.statusLabel }}</span>
              <small v-if="row.mapping.reference_count > 0">{{ row.mapping.reference_count }} 个已发布引用</small>
            </td>
            <td>
              <span>修订 {{ row.mapping.revision }}</span>
              <small>更新人：{{ row.mapping.updated_by || '—' }}</small>
            </td>
            <td class="kmai-manager__actions">
              <button type="button" :disabled="!row.canEdit || isBusy(row)" @click="openEdit(row)">编辑</button>
              <button type="button" :disabled="!row.canDeactivate || isBusy(row)" @click="deactivate(row)">停用</button>
              <button
                type="button"
                :disabled="!row.canPromote || isBusy(row)"
                :title="projectId === null && row.mapping.scope === 'project' ? '需要项目上下文' : ''"
                @click="promote(row)"
              >
                提升为全局
              </button>
              <button
                class="is-danger"
                type="button"
                :disabled="!row.canDelete || isBusy(row)"
                :title="row.mapping.reference_count > 0 ? '已被发布包引用，只能停用' : ''"
                @click="hardDelete(row)"
              >
                删除
              </button>
            </td>
          </tr>
        </tbody>
      </table>
    </div>

    <el-dialog
      v-model="editVisible"
      append-to-body
      width="520px"
      title="编辑 KmAI 映射"
      :close-on-click-modal="false"
      :close-on-press-escape="!savingEdit"
      :show-close="!savingEdit"
    >
      <div v-if="editing" class="kmai-manager__edit">
        <label>来源</label>
        <p><code>{{ editing.mapping.source_field }}</code> · {{ editing.mapping.source_value }}</p>

        <template v-if="editing.mapping.mapping_mode === 'existing_factor'">
          <label for="kmai-edit-existing">目标因子</label>
          <select id="kmai-edit-existing" v-model="editExistingKey" :disabled="savingEdit">
            <option v-for="factor in catalog" :key="factor.factor_key" :value="factor.factor_key">
              {{ factor.factor_name }}（{{ factor.factor_key }}）
            </option>
          </select>
          <small>已有因子映射只能更换目录中的目标因子。</small>
        </template>

        <template v-else>
          <label for="kmai-edit-manual-key">生成键（不可修改）</label>
          <input id="kmai-edit-manual-key" :value="editing.mapping.target_factor_key" disabled />
          <label for="kmai-edit-manual-name">显示名称</label>
          <input id="kmai-edit-manual-name" v-model="editManualName" :disabled="savingEdit" />
        </template>
      </div>
      <template #footer>
        <button class="kmai-manager__button" type="button" :disabled="savingEdit" @click="editVisible = false">取消</button>
        <button class="kmai-manager__button is-primary" type="button" :disabled="!canSaveEdit || savingEdit" @click="saveEdit">
          {{ savingEdit ? '保存中…' : '保存' }}
        </button>
      </template>
    </el-dialog>
  </section>
</template>

<script setup lang="ts">
import { computed, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'

import {
  deleteKmaiFactorMapping,
  getKmaiFactorCatalog,
  listKmaiFactorMappings,
  promoteKmaiFactorMapping,
  updateKmaiFactorMapping,
} from '@/api/kmaiFactorMappings'
import type { KmaiFactorCatalogItem, KmaiMapping } from '@/api/kmaiFactorMappings'
import { filterBooleanKmaiFactorCatalog } from '@/utils/kmaiFactorMappings'
import {
  filterKmaiMappingManagerRows,
  isKmaiMappingLoadCurrent,
  toKmaiMappingManagerRows,
} from '@/utils/kmaiFactorMappingsManager'
import type { KmaiMappingManagerFilters, KmaiMappingManagerRow } from '@/utils/kmaiFactorMappingsManager'

const props = defineProps<{
  projectId: number | null
  active: boolean
}>()

const mappings = ref<KmaiMapping[]>([])
const catalog = ref<KmaiFactorCatalogItem[]>([])
const loading = ref(false)
const loadError = ref('')
const busyId = ref<number | null>(null)
const editVisible = ref(false)
const editing = ref<KmaiMappingManagerRow | null>(null)
const savingEdit = ref(false)
const editExistingKey = ref('')
const editManualName = ref('')
let loadVersion = 0

const filters = reactive<KmaiMappingManagerFilters>({
  search: '',
  sourceField: 'all',
  scope: 'all',
  status: 'all',
})

const rows = computed(() => toKmaiMappingManagerRows(mappings.value, props.projectId))
const filteredRows = computed(() => filterKmaiMappingManagerRows(rows.value, filters))
const sourceFields = computed(() => [...new Set(mappings.value.map(mapping => mapping.source_field))].sort())
const canSaveEdit = computed(() => {
  if (!editing.value || !currentActionRow(editing.value, 'canEdit')) return false
  if (editing.value.mapping.mapping_mode === 'existing_factor') return Boolean(editExistingKey.value)
  return Boolean(editManualName.value.trim())
})

watch(
  () => [props.active, props.projectId] as const,
  ([active]) => {
    loadVersion += 1
    mappings.value = []
    loadError.value = ''
    loading.value = false
    editVisible.value = false
    editing.value = null
    if (active) void load()
  },
  { immediate: true },
)

function errorMessage(error: any) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : detail?.message || error?.message || '操作失败，请重试。'
}

async function load() {
  if (!props.active) return
  const request = {
    version: ++loadVersion,
    projectId: props.projectId,
  }
  loading.value = true
  loadError.value = ''
  try {
    const [nextCatalog, nextMappings] = await Promise.all([
      getKmaiFactorCatalog(),
      listKmaiFactorMappings(request.projectId),
    ])
    if (!loadIsCurrent(request)) return
    catalog.value = filterBooleanKmaiFactorCatalog(nextCatalog)
    mappings.value = nextMappings
  } catch (error) {
    if (!loadIsCurrent(request)) return
    loadError.value = errorMessage(error)
  } finally {
    if (loadIsCurrent(request)) loading.value = false
  }
}

function loadIsCurrent(request: { version: number; projectId: number | null }) {
  return isKmaiMappingLoadCurrent(request, {
    active: props.active,
    version: loadVersion,
    projectId: props.projectId,
  })
}

function mappingId(row: KmaiMappingManagerRow) {
  return row.mapping.mapping_id
}

function isBusy(row: KmaiMappingManagerRow) {
  return loading.value || busyId.value !== null || (mappingId(row) !== null && busyId.value === mappingId(row))
}

type MutationCapability = 'canEdit' | 'canDeactivate' | 'canDelete' | 'canPromote'

function currentActionRow(row: KmaiMappingManagerRow, capability: MutationCapability) {
  if (!props.active || loading.value || busyId.value !== null) return null
  const current = rows.value.find(candidate => (
    candidate.mapping.mapping_identity === row.mapping.mapping_identity
    && candidate.mapping.mapping_id === row.mapping.mapping_id
    && candidate.mapping.revision === row.mapping.revision
    && candidate.mapping.project_id === row.mapping.project_id
  ))
  return current?.[capability] ? current : null
}

async function mutate(
  row: KmaiMappingManagerRow,
  capability: MutationCapability,
  action: (mappingId: number, expectedRevision: number) => Promise<unknown>,
  successMessage: string,
) {
  const current = currentActionRow(row, capability)
  const id = current && mappingId(current)
  if (!current || id === null) return false
  busyId.value = id
  try {
    await action(id, current.mapping.revision)
    ElMessage.success(successMessage)
    await load()
    return true
  } catch (error) {
    ElMessage.error(errorMessage(error))
    await load()
    return false
  } finally {
    busyId.value = null
  }
}

function openEdit(row: KmaiMappingManagerRow) {
  const current = currentActionRow(row, 'canEdit')
  if (!current) return
  editing.value = current
  editExistingKey.value = current.mapping.target_factor_key
  editManualName.value = current.mapping.target_factor_name
  editVisible.value = true
}

async function saveEdit() {
  const row = editing.value
  const current = row && currentActionRow(row, 'canEdit')
  const id = current && mappingId(current)
  if (!row || !current || id === null || !canSaveEdit.value || savingEdit.value) return
  savingEdit.value = true
  try {
    if (current.mapping.mapping_mode === 'existing_factor') {
      await updateKmaiFactorMapping(id, {
        expected_revision: current.mapping.revision,
        mapping_mode: 'existing_factor',
        target_factor_key: editExistingKey.value,
      })
    } else {
      await updateKmaiFactorMapping(id, {
        expected_revision: current.mapping.revision,
        mapping_mode: 'manual_factor',
        target_factor_name: editManualName.value.trim(),
      })
    }
    editVisible.value = false
    ElMessage.success('映射已更新')
    await load()
  } catch (error) {
    ElMessage.error(errorMessage(error))
    await load()
    editVisible.value = false
    editing.value = null
  } finally {
    savingEdit.value = false
  }
}

async function deactivate(row: KmaiMappingManagerRow) {
  await mutate(
    row,
    'canDeactivate',
    (id, expectedRevision) => deleteKmaiFactorMapping(id, { expectedRevision }),
    '映射已停用',
  )
}

async function promote(row: KmaiMappingManagerRow) {
  if (props.projectId === null) return
  await mutate(
    row,
    'canPromote',
    (id, expectedRevision) => promoteKmaiFactorMapping(id, expectedRevision),
    '项目映射已提升为全局映射',
  )
}

async function hardDelete(row: KmaiMappingManagerRow) {
  if (!currentActionRow(row, 'canDelete')) return
  try {
    await ElMessageBox.confirm(
      `永久删除“${row.mapping.source_value}”的映射？此操作无法撤销。`,
      '确认删除',
      { confirmButtonText: '永久删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  await mutate(
    row,
    'canDelete',
    (id, expectedRevision) => deleteKmaiFactorMapping(id, {
      expectedRevision,
      delete: true,
    }),
    '映射已永久删除',
  )
}
</script>

<style scoped>
.kmai-manager { display: grid; gap: 14px; padding: 0 20px 18px; color: #334155; }
.kmai-manager__toolbar { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.kmai-manager__toolbar h3 { margin: 0; color: #0f172a; font-size: 15px; }
.kmai-manager__toolbar p { margin: 4px 0 0; color: #64748b; font-size: 12px; }
.kmai-manager__filters { display: grid; grid-template-columns: minmax(220px, 1fr) repeat(3, minmax(125px, .45fr)); gap: 8px; }
.kmai-manager input, .kmai-manager select, .kmai-manager__edit input, .kmai-manager__edit select { box-sizing: border-box; width: 100%; border: 1px solid #cbd5e1; border-radius: 7px; padding: 8px 10px; color: #0f172a; background: #fff; font: inherit; font-size: 12px; }
.kmai-manager__table-wrap { max-height: min(58vh, 560px); overflow: auto; border: 1px solid #e2e8f0; border-radius: 8px; }
.kmai-manager__table { width: 100%; border-collapse: collapse; table-layout: fixed; font-size: 12px; }
.kmai-manager__table th { position: sticky; z-index: 1; top: 0; padding: 9px 10px; background: #f8fafc; color: #64748b; text-align: left; font-weight: 600; }
.kmai-manager__table th:nth-child(1) { width: 18%; }.kmai-manager__table th:nth-child(2) { width: 23%; }.kmai-manager__table th:nth-child(3) { width: 13%; }.kmai-manager__table th:nth-child(4) { width: 12%; }.kmai-manager__table th:nth-child(5) { width: 34%; }
.kmai-manager__table td { padding: 10px; border-top: 1px solid #e2e8f0; vertical-align: top; }
.kmai-manager__table td > strong, .kmai-manager__table td > code, .kmai-manager__table td > span, .kmai-manager__table td > small { display: block; margin-bottom: 4px; overflow-wrap: anywhere; }
.kmai-manager__table tr.is-inactive td { background: #f8fafc; color: #94a3b8; }
.kmai-manager__table code { color: #4f46e5; font-size: 11px; }
.kmai-manager__badge { display: inline-block !important; width: fit-content; padding: 2px 6px; border-radius: 999px; background: #eef2ff; color: #4338ca; }.kmai-manager__badge.is-muted { background: #e2e8f0; color: #64748b; }
.kmai-manager__overridden { color: #b45309; line-height: 1.4; }
.kmai-manager__actions { display: flex; flex-wrap: wrap; gap: 5px; }.kmai-manager__actions-heading { text-align: right !important; }
.kmai-manager__actions button, .kmai-manager__button { border: 1px solid #cbd5e1; border-radius: 6px; padding: 5px 8px; background: #fff; color: #475569; cursor: pointer; font-size: 11px; }
.kmai-manager__actions button:hover:not(:disabled), .kmai-manager__button:hover:not(:disabled) { border-color: #818cf8; color: #4338ca; }.kmai-manager__actions button:disabled, .kmai-manager__button:disabled { opacity: .45; cursor: not-allowed; }
.kmai-manager__actions button.is-danger { color: #b91c1c; }.kmai-manager__button.is-primary { border-color: #4f46e5; background: #4f46e5; color: #fff; }
.kmai-manager__empty { padding: 48px 16px; border: 1px dashed #cbd5e1; border-radius: 8px; color: #64748b; text-align: center; }.kmai-manager__error { margin: 0; color: #b91c1c; font-size: 12px; }
.kmai-manager__edit { display: grid; gap: 8px; }.kmai-manager__edit label { margin-top: 4px; color: #475569; font-size: 12px; font-weight: 600; }.kmai-manager__edit p { margin: 0; }.kmai-manager__edit small { color: #64748b; }
@media (max-width: 900px) { .kmai-manager__filters { grid-template-columns: 1fr 1fr; }.kmai-manager__table { min-width: 900px; } }
</style>
