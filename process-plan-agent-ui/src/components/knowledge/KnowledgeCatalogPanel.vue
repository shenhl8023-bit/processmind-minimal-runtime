<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import KnowledgeGuidanceCard from '@/components/knowledge/KnowledgeGuidanceCard.vue'
import { listKnowledgeCatalog, getKnowledgeCatalogRecord, type KnowledgeCatalogSection, type KnowledgeCatalogResponse, type KnowledgeCatalogDetail, type KnowledgeCatalogRow, type KnowledgeSource } from '@/api/knowledge'

const props = defineProps<{ section: KnowledgeCatalogSection }>()
const title = computed(() => props.section === 'knowledge' ? '工艺知识' : '工艺资源')
const query = ref('')
const appliedQuery = ref('')
const category = ref('')
const topic = ref('')
const sort = ref<'title_asc' | 'title_desc'>('title_asc')
const page = ref(1)
const data = ref<KnowledgeCatalogResponse | null>(null)
const loading = ref(false)
const error = ref('')
const detail = ref<KnowledgeCatalogDetail | null>(null)
const selectedId = ref('')
const detailLoading = ref(false)
const detailError = ref('')
const detailHeading = ref<HTMLElement | null>(null)
const detailPanel = ref<HTMLElement | null>(null)
const tableScroll = ref<HTMLElement | null>(null)
let detailTrigger: HTMLElement | null = null
let listRequest = 0
let detailRequest = 0
const pageCount = computed(() => Math.max(1, Math.ceil((data.value?.total || 0) / 20)))
const visibleRows = computed(() => loading.value || error.value ? [] : data.value?.items || [])
const detailFields = computed(() => Object.entries(detail.value?.fields || {}))
const detailWarnings = computed(() => detail.value ? rowWarnings(detail.value) : [])
const detailNotes = computed(() => detail.value?.data_warnings.filter(isVerificationNote) || [])
const fieldLabels: Record<string, string> = { type: '资源类别', model: '型号 / 规格', range: '范围 / 能力', parameter: '主要参数 / 用途' }
const keyFields = computed(() => props.section === 'resources'
  ? ['type', 'model', 'range', 'parameter'].filter(key => detail.value?.values[key] != null && detail.value.values[key] !== '').map(key => [fieldLabels[key], detail.value!.values[key]])
  : [])

async function load() {
  const request = ++listRequest
  loading.value = true
  error.value = ''
  closeDetail(false)
  try {
    const result = await listKnowledgeCatalog({ section: props.section, category: category.value, topic: topic.value, q: appliedQuery.value, sort: sort.value, page: page.value, page_size: 20 })
    if (request === listRequest) data.value = result
  } catch {
    if (request === listRequest) error.value = '目录加载失败，请检查本地服务后重试。'
  } finally {
    if (request === listRequest) {
      loading.value = false
      await nextTick()
      if (request === listRequest && tableScroll.value) tableScroll.value.scrollTop = 0
    }
  }
}
function search() {
  appliedQuery.value = query.value.trim()
  page.value = 1
  void load()
}
function filterCategory(value: string) {
  category.value = value
  topic.value = ''
  page.value = 1
  void load()
}
function refreshFilter() { page.value = 1; void load() }
function changePage(offset: number) {
  page.value = Math.min(pageCount.value, Math.max(1, page.value + offset))
  void load()
}
async function openDetail(row: KnowledgeCatalogRow, event?: Event) {
  const request = ++detailRequest
  selectedId.value = row.id
  detail.value = null
  detailError.value = ''
  detailLoading.value = true
  if (event?.currentTarget) detailTrigger = event.currentTarget as HTMLElement
  await nextTick()
  detailHeading.value?.focus?.()
  try {
    const result = await getKnowledgeCatalogRecord(row.id)
    if (request === detailRequest) detail.value = result
  } catch {
    if (request === detailRequest) detailError.value = '详情加载失败，请重试。'
  } finally {
    if (request === detailRequest) detailLoading.value = false
  }
}
function closeDetail(restore = true) {
  detailRequest += 1
  selectedId.value = ''
  detail.value = null
  detailError.value = ''
  detailLoading.value = false
  if (restore) detailTrigger?.focus?.()
}
function detailFocusableElements(): HTMLElement[] {
  const panel = detailPanel.value
  if (!panel) return []
  const descendants = Array.prototype.slice.call(panel.querySelectorAll(
    'button, [href], input, select, textarea, summary, [tabindex]:not([tabindex="-1"])',
  )) as HTMLElement[]
  const candidates: Array<HTMLElement | null> = [detailHeading.value, ...descendants]
  return candidates.filter((element, index, all): element is HTMLElement => {
    if (!element || all.indexOf(element) !== index) return false
    return !element.hasAttribute('disabled') && element.getAttribute('aria-hidden') !== 'true'
  })
}
function handleDetailKeydown(event: KeyboardEvent) {
  if (event.key === 'Escape' || event.key === 'Esc') {
    event.preventDefault()
    event.stopPropagation()
    closeDetail()
    return
  }
  if (event.key !== 'Tab') return
  const focusables = detailFocusableElements()
  if (!focusables.length) {
    event.preventDefault()
    detailHeading.value?.focus?.()
    return
  }
  const first = focusables[0]!
  const last = focusables[focusables.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}
function display(value: unknown): string {
  if (value == null || value === '' || (Array.isArray(value) && !value.length)) return '未提供'
  if (typeof value === 'object') return JSON.stringify(value, null, 2)
  return String(value)
}
function sourceText(source: KnowledgeSource) {
  return [source.document_name, source.worksheet, source.row_no != null ? `第 ${source.row_no} 行` : '', source.cell_range, source.page_no != null ? `第 ${source.page_no} 页` : '', source.identity].filter(Boolean).join(' · ') || '来源定位未提供'
}
function isVerificationNote(value: string) { return value.startsWith('已核对原文仅表示') }
function rowWarnings(row: KnowledgeCatalogRow) {
  return row.data_warnings.filter(w => !isVerificationNote(w))
}
onMounted(load)
onBeforeUnmount(() => { listRequest += 1; detailRequest += 1 })
</script>

<template>
  <section class="catalog-panel" :aria-label="title">
    <header class="catalog-heading">
      <div><h2>{{ title }}</h2><p>{{ section === 'knowledge' ? '查阅工艺要求、安排条件及加工能力参考。' : '查看设备、刀具与量具的已有资料和原始参数。' }}</p></div>
      <span class="catalog-local">只读目录</span>
    </header>
    <div class="catalog-categories" aria-label="目录分类">
      <button type="button" :class="{ active: !category }" :aria-pressed="!category" @click="filterCategory('')">全部</button>
      <button v-for="option in data?.categories || []" :key="option.value" type="button" :class="{ active: category === option.value }" :aria-pressed="category === option.value" @click="filterCategory(option.value)">{{ option.label }} <span>{{ option.count }}</span></button>
    </div>
    <div class="catalog-toolbar">
      <form class="catalog-search" @submit.prevent="search">
        <input v-model="query" type="search" aria-label="搜索当前目录" placeholder="搜索当前目录" maxlength="300" />
        <button type="submit" @click.prevent="search">搜索</button>
      </form>
      <select v-if="section === 'knowledge' && category !== 'capability'" v-model="topic" aria-label="工艺主题" @change="refreshFilter">
        <option value="">全部主题</option><option v-for="option in data?.topics.filter(t => t.count > 0) || []" :key="option.value" :value="option.value">{{ option.label }}</option>
      </select>
      <select v-model="sort" aria-label="排序" @change="refreshFilter"><option value="title_asc">名称升序</option><option value="title_desc">名称降序</option></select>
    </div>
    <p class="catalog-scope">{{ section === 'resources' ? '当前资源主要来自手册参考，不代表企业设备台账或已验证的工序适配。' : '规程要求与手册能力分别标明来源；已核对原文不等于业务批准。' }}</p>
    <p v-if="loading" class="catalog-state" role="status">正在读取目录…</p>
    <div v-if="error" class="catalog-state catalog-error" role="alert">{{ error }} <button type="button" @click="load">重试</button></div>
    <div v-if="!loading && !error" ref="tableScroll" class="catalog-table-scroll" tabindex="0" :aria-label="`${title}表格，可滚动查看`">
      <table class="catalog-table">
        <thead><tr><th v-for="column in data?.columns || []" :key="column.key" scope="col">{{ column.label }}</th></tr></thead>
        <tbody><tr v-for="row in visibleRows" :key="row.id" :class="{ selected: selectedId === row.id }">
          <td v-for="column in data?.columns || []" :key="column.key">
            <template v-if="column.key === 'title'"><button class="catalog-record-link" type="button" @click="openDetail(row, $event)">{{ row.title }}</button><small v-if="rowWarnings(row).length" class="catalog-warning" :title="rowWarnings(row).join('；')">{{ rowWarnings(row)[0] }}</small></template>
            <span v-else :class="{ 'catalog-cell': true, 'catalog-status-warning': column.key === 'status' && ['pending', 'conflict'].includes(row.verification_status) }" :title="row.values[column.key]">{{ display(row.values[column.key]) }}</span>
          </td>
        </tr></tbody>
      </table>
      <div v-if="!visibleRows.length" class="catalog-state">没有匹配记录，请调整关键词或分类。</div>
    </div>
    <footer v-if="data && !error && !loading" class="catalog-pagination">
      <span>共 {{ data.total }} 项<span v-if="data.raw_count !== data.total"> · {{ data.raw_count }} 条原始记录</span> · 每页 20 项</span>
      <div><button type="button" :disabled="page <= 1" @click="changePage(-1)">上一页</button><span>{{ page }} / {{ pageCount }}</span><button type="button" :disabled="page >= pageCount" @click="changePage(1)">下一页</button></div>
    </footer>

    <div v-if="selectedId" class="catalog-detail-layer">
      <button class="catalog-detail-backdrop" type="button" aria-label="关闭详情" @click="closeDetail()"></button>
      <section ref="detailPanel" class="catalog-detail" role="dialog" aria-modal="true" aria-labelledby="catalog-detail-heading" @keydown="handleDetailKeydown">
        <header><div><span class="catalog-eyebrow">完整记录 / 只读</span><h3 id="catalog-detail-heading" ref="detailHeading" tabindex="-1">{{ detail?.title || '记录详情' }}</h3></div><button type="button" aria-label="关闭详情" @click="closeDetail()">关闭</button></header>
        <p v-if="detailLoading" role="status">正在读取详情…</p>
        <p v-if="detailError" class="catalog-error" role="alert">{{ detailError }} <button type="button" @click="openDetail({ id: selectedId } as KnowledgeCatalogRow)">重试详情</button></p>
        <template v-if="detail">
          <p class="catalog-scope">{{ detail.source_label }} · {{ detail.values.status || '参考资料' }}</p>
          <ul v-if="detailWarnings.length" class="catalog-detail-warnings"><li v-for="warning in detailWarnings" :key="warning">{{ warning }}</li></ul>
          <p v-if="!detail.guidance && detailNotes.length" class="catalog-detail-note">{{ detailNotes.join('；') }}</p>
          <section v-if="keyFields.length" class="catalog-key-fields"><h4>关键参数</h4><dl><div v-for="[label, value] in keyFields" :key="label"><dt>{{ label }}</dt><dd>{{ display(value) }}</dd></div></dl></section>
          <KnowledgeGuidanceCard v-if="detail.guidance" :guidance="detail.guidance" />
          <details :open="!detail.guidance && section !== 'resources'" class="catalog-raw-fields"><summary>完整参数与原始字段</summary><dl><div v-for="[key, value] in detailFields" :key="key"><dt>{{ key }}</dt><dd>{{ display(value) }}</dd></div></dl></details>
          <section class="catalog-sources"><h4>原始来源 · {{ detail.sources.length }} 处</h4><ul><li v-for="(source, index) in detail.sources" :key="index">{{ sourceText(source) }}</li></ul></section>
        </template>
      </section>
    </div>
  </section>
</template>

<style scoped>
.catalog-panel { display: flex; flex-direction: column; flex: 1; min-height: 0; min-width: 0; padding: 10px 16px; border: 1px solid var(--knowledge-border, var(--border-light)); border-radius: 8px; background: var(--bg-card); }
.catalog-heading { display: flex; justify-content: space-between; gap: 16px; align-items: center; margin-bottom: 7px; flex-shrink: 0; }
.catalog-heading > div { display: flex; align-items: baseline; gap: 10px; min-width: 0; }
.catalog-eyebrow { font-size: 12px; color: var(--text-secondary); }
.catalog-heading h2 { margin: 0; font-size: 18px; line-height: 1.4; font-weight: 650; white-space: nowrap; }
.catalog-heading p, .catalog-scope { font-size: 12px; color: var(--text-secondary); line-height: 1.5; }
.catalog-heading p { min-width: 0; margin: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog-local { font-size: 12px; color: var(--text-secondary); border: 1px solid var(--border-light); padding: 4px 8px; border-radius: 5px; white-space: nowrap; }
.catalog-categories { display: flex; flex-wrap: wrap; gap: 4px; padding-bottom: 6px; border-bottom: 1px solid var(--border-light); flex-shrink: 0; }
button, input, select { font: inherit; }
button { cursor: pointer; }
button:disabled { opacity: .45; cursor: default; }
button:focus-visible, input:focus-visible, select:focus-visible, h3:focus-visible, .catalog-table-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
.catalog-categories button { display: inline-flex; align-items: center; height: 32px; padding: 0 10px; border: 1px solid transparent; background: transparent; border-radius: 6px; color: var(--text-secondary); font-size: 13px; }
.catalog-categories button span { margin-left: 5px; font-size: 12px; font-variant-numeric: tabular-nums; }
.catalog-categories button:hover { background: #f5f7fc; }
.catalog-categories button.active { background: #eef2ff; border-color: #c7d2fe; color: var(--accent); font-weight: 600; }
.catalog-toolbar { display: flex; flex-wrap: wrap; gap: 6px; margin: 8px 0 0; flex-shrink: 0; }
.catalog-search { display: flex; flex: 1; min-width: 200px; }
.catalog-search input { flex: 1; min-width: 0; height: var(--knowledge-control-height, 38px); box-sizing: border-box; border: 1px solid var(--border-light); border-radius: var(--knowledge-control-radius, 6px) 0 0 var(--knowledge-control-radius, 6px); padding: 0 11px; color: var(--text-primary); background: var(--bg-card); font-size: 13px; }
.catalog-search input::placeholder { color: #64748b; }
.catalog-search button { height: var(--knowledge-control-height, 38px); box-sizing: border-box; border: 0; border-radius: 0 var(--knowledge-control-radius, 6px) var(--knowledge-control-radius, 6px) 0; padding: 0 15px; background: var(--accent); color: white; font-size: 13px; }
select { max-width: 180px; min-height: var(--knowledge-control-height, 38px); height: var(--knowledge-control-height, 38px); box-sizing: border-box; border: 1px solid var(--border-light); border-radius: var(--knowledge-control-radius, 6px); padding: 0 8px; background: var(--bg-card); color: var(--text-primary); font-size: 13px; }
.catalog-scope { margin: 6px 0 8px; flex-shrink: 0; }
.catalog-table-scroll { flex: 1; min-height: 80px; overflow: auto; border: 1px solid var(--border-light); border-radius: 6px; scrollbar-gutter: stable; }
.catalog-table { width: 100%; border-collapse: separate; border-spacing: 0; text-align: left; font-size: 13px; }
.catalog-table th { position: sticky; top: 0; z-index: 1; background: #f5f7fb; color: #475569; font-weight: 600; padding: 8px 10px; white-space: nowrap; border-bottom: 1px solid var(--border-light); }
.catalog-table td { min-width: 80px; max-width: 220px; padding: 8px 10px; vertical-align: top; border-bottom: 1px solid #edf0f5; line-height: 1.6; }
.catalog-table td:first-child { min-width: 180px; }
.catalog-table tbody tr:last-child td { border-bottom: 0; }
.catalog-table tbody tr:hover, .catalog-table tr.selected { background: #f5f7fd; }
.catalog-record-link { border: 0; padding: 0; background: transparent; color: var(--accent); font-size: 13px; font-weight: 600; text-align: left; line-height: 1.7; }
.catalog-record-link:hover { text-decoration: underline; }
.catalog-cell { display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; overflow-wrap: anywhere; }
.catalog-warning { display: block; max-width: 220px; color: #925f00; font-size: 12px; margin-top: 4px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.catalog-status-warning, .catalog-error { color: #a14e08; }
.catalog-state { padding: 30px 12px; font-size: 13px; color: var(--text-secondary); text-align: center; }
.catalog-pagination { display: flex; flex-wrap: wrap; justify-content: space-between; align-items: center; gap: 8px 12px; padding-top: 8px; flex-shrink: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.5; font-variant-numeric: tabular-nums; }
.catalog-pagination div { display: flex; align-items: center; gap: 12px; }
.catalog-pagination button, .catalog-detail header button, .catalog-error button { border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-card); color: var(--text-primary); padding: 7px 11px; min-height: 34px; font-size: 13px; white-space: nowrap; }
.catalog-pagination button:hover:not(:disabled), .catalog-detail header button:hover { border-color: #a5b4fc; color: var(--accent); }
.catalog-detail-layer { position: fixed; z-index: 120; inset: 0; display: flex; align-items: center; justify-content: center; box-sizing: border-box; padding: 28px; }
.catalog-detail-backdrop { position: absolute; inset: 0; width: 100%; height: 100%; border: 0; padding: 0; background: rgba(15, 23, 42, .18); cursor: default; }
.catalog-detail { position: relative; z-index: 1; width: min(700px, calc(100vw - 56px)); max-height: calc(100vh - 56px); box-sizing: border-box; overflow-y: auto; border: 1px solid var(--border-light); border-top: 3px solid var(--accent); border-radius: 8px; padding: 16px 20px; background: var(--bg-card); box-shadow: 0 20px 56px rgba(15, 23, 42, .22); }
.catalog-detail > header { position: sticky; top: -16px; z-index: 2; margin: -16px -20px 14px; padding: 14px 20px 12px; border-bottom: 1px solid var(--border-light); background: var(--bg-card); display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; }
.catalog-detail h3 { font-size: 18px; line-height: 1.45; margin-top: 4px; overflow-wrap: anywhere; }
.catalog-detail h3:focus { outline: none; }
.catalog-detail-warnings { padding: 10px 14px 10px 30px; background: #fffbeb; border: 1px solid #fde68a; border-radius: 6px; color: #92400e; font-size: 13px; line-height: 1.8; margin-bottom: 16px; }
.catalog-detail-note { color: var(--text-secondary); background: #f5f7fb; padding: 10px 12px; border-radius: 6px; font-size: 12px; line-height: 1.8; }
.catalog-key-fields { margin: 16px 0 20px; }
.catalog-key-fields h4, .catalog-sources h4 { font-size: 14px; font-weight: 600; margin-bottom: 8px; }
.catalog-key-fields dl { padding: 0 14px; border: 1px solid var(--border-light); border-radius: 6px; background: #f8fafc; }
.catalog-key-fields dl > div, .catalog-raw-fields dl > div { display: grid; grid-template-columns: minmax(100px, 150px) minmax(0, 1fr); gap: 16px; border-bottom: 1px solid var(--border-light); padding: 10px 0; font-size: 13px; line-height: 1.8; }
.catalog-key-fields dl > div:last-child { border-bottom: 0; }
.catalog-key-fields dt, .catalog-raw-fields dt { color: var(--text-secondary); overflow-wrap: anywhere; }
.catalog-key-fields dd, .catalog-raw-fields dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.catalog-raw-fields { margin-top: 16px; border-top: 1px solid var(--border-light); font-size: 13px; }
.catalog-raw-fields summary { cursor: pointer; color: var(--accent); padding: 12px 0; }
.catalog-sources { margin-top: 20px; font-size: 13px; }
.catalog-sources ul { padding-left: 18px; color: var(--text-secondary); line-height: 1.8; overflow-wrap: anywhere; }
@media (max-width: 760px) {
  .catalog-panel { padding: 14px; }
  .catalog-local { display: none; }
  .catalog-heading { margin-bottom: 12px; }
  .catalog-heading > div { display: block; }
  .catalog-heading h2 { font-size: 17px; }
  .catalog-heading p { display: block; margin-top: 2px; white-space: normal; }
  .catalog-categories { gap: 2px; padding-bottom: 8px; }
  .catalog-categories button { padding: 7px 8px; }
  .catalog-toolbar { margin-top: 10px; gap: 6px; }
  .catalog-search { min-width: 100%; }
  .catalog-toolbar select { flex: 1; max-width: none; height: 40px; min-height: 40px; }
  .catalog-scope { margin: 8px 0; }
  .catalog-pagination { gap: 8px; }
  .catalog-pagination > div { justify-content: space-between; width: 100%; }
  .catalog-pagination button { min-height: 40px; }
  .catalog-detail-layer { padding: 12px; }
  .catalog-detail { width: calc(100vw - 24px); max-height: calc(100vh - 24px); padding: 14px 16px; }
  .catalog-detail > header { top: -14px; margin: -14px -16px 12px; padding: 13px 16px 11px; }
  .catalog-key-fields dl > div, .catalog-raw-fields dl > div { grid-template-columns: minmax(0, 1fr); gap: 4px; }
}
@media (max-height: 650px) {
  .catalog-heading p, .catalog-local { display: none; }
  .catalog-heading { margin-bottom: 8px; }
  .catalog-scope { margin-block: 6px; }
}
</style>
