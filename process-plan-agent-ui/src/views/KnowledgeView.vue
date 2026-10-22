<script setup lang="ts">
import { computed, onActivated, onMounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import KnowledgeGuidanceCard from '@/components/knowledge/KnowledgeGuidanceCard.vue'
import {
  saveKnowledgeEvidence,
  searchKnowledge,
  type KnowledgeEvidence,
  type KnowledgeSource,
  type KnowledgeRelationship,
  type KnowledgeRelationshipItem,
  type KnowledgeResourceSummary,
  type KnowledgeResourceSummaryItem,
  type KnowledgeRouteOperation,
  type KnowledgeSearchItem,
} from '@/api/knowledge'

defineOptions({ name: 'KnowledgeView' })

const route = useRoute()
const query = ref(firstQueryValue(route.query.q))
const topK = ref(8)
const loading = ref(false)
const error = ref('')
const status = ref<'idle' | 'ok' | 'no_evidence' | 'llm_unavailable' | 'insufficient_evidence'>('idle')
const message = ref('')
const answerText = ref('')
const intent = ref<'capability' | 'general' | string>('general')
const relationshipGaps = ref<string[]>([])
const resourceSummary = ref<KnowledgeResourceSummary | null>(null)
const hasSearched = ref(false)
const items = ref<KnowledgeSearchItem[]>([])
const isHistoryRoute = computed(() => intent.value === 'history_route')
const isTypicalRoute = computed(() => intent.value === 'typical_route')
const savedEvidenceIds = ref<Record<string, number>>({})
const savingItemId = ref('')
const contextGeneration = ref(0)
const searchRequestId = ref(0)
const showAllSampleQuestions = ref(false)

// Render emphasis as Vue text nodes so model output can never inject HTML.
const answerSegments = computed(() => (answerText.value || '').split(/(\*\*[^*]+\*\*)/g).map(text => ({
  text: text.startsWith('**') && text.endsWith('**') ? text.slice(2, -2) : text,
  emphasis: text.startsWith('**') && text.endsWith('**'),
})))

function firstQueryValue(value: unknown): string {
  if (Array.isArray(value)) return typeof value[0] === 'string' ? value[0] : ''
  return typeof value === 'string' ? value : value == null ? '' : String(value)
}

const projectId = computed(() => {
  const value = Number(firstQueryValue(route.query.project_id) || 0)
  return Number.isFinite(value) && value > 0 ? value : undefined
})

const routeVersionId = computed(() => {
  const value = Number(firstQueryValue(route.query.route_version_id) || 0)
  return Number.isFinite(value) && value > 0 ? value : undefined
})

const operationContext = computed(() => {
  const raw = firstQueryValue(route.query.operation_context).trim()
  if (!raw) return undefined
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return undefined
    return Object.fromEntries(
      Object.entries(parsed).filter(([, value]) => value === null || ['string', 'number'].includes(typeof value)),
    ) as Record<string, string | number | null>
  } catch {
    return undefined
  }
})

const sampleQuestions = [
  { label: '去应力条件', question: '轴套何时需要去应力？' },
  { label: '研孔省略', question: '轴套工艺路线中什么时候省略研孔？' },
  { label: '硬阳化余量', question: '6061-T6硬阳化衬套内孔如何留余量？' },
  { label: '典型路线', question: '钢件衬套的典型工艺路线有哪些阶段？' },
  { label: '历史工艺', question: '9Cr18 衬套的历史工艺路线有哪些？' },
  { label: '加工方法', question: '轴套内孔和外圆有哪些加工方法？' },
  { label: '刀具与量具', question: '内孔精加工可以用什么刀具和量具？' },
  { label: '设备参数', question: 'CL6134A 车床的加工范围和精度参数是什么？' },
  { label: '加工能力', question: '内孔精加工有哪些粗糙度和加工余量参考？' },
  { label: '精度与粗糙度', question: '轴套内孔精加工有哪些加工方法，能达到什么精度和粗糙度？' },
  { label: '目标指标', question: '内孔目标 IT7、Ra1.6，样例库有哪些工艺方法？' },
  { label: '加工阶段', question: '钻孔、扩孔、铰孔分别适合什么加工阶段和精度范围？' },
  { label: '外圆能力', question: '加工外圆时，哪些车床类别有对应的能力记录？' },
  { label: '刀具精度', question: '孔加工可以使用哪些刀具，各自的经济精度是多少？' },
  { label: '量具范围', question: '内径 20～25 mm 的孔，可以查到哪些量具？' },
  { label: '历史关联', question: '某历史轴套类工序使用了哪些设备和量具？' },
]
const initialSampleQuestionCount = 6
const visibleSampleQuestions = computed(() => showAllSampleQuestions.value
  ? sampleQuestions
  : sampleQuestions.slice(0, initialSampleQuestionCount))
const emptyRecoveryQuestions = [
  '轴套内孔精加工有哪些加工方法，能达到什么精度和粗糙度？',
  '9Cr18 衬套的历史工艺路线有哪些？',
  'CL6134A 车床的加工范围和精度参数是什么？',
]

const categoryLabels: Record<string, string> = {
  history: '历史工艺',
  capability: '加工能力',
  equipment: '设备',
  tool: '刀具',
  gauge: '量具',
  process_guidance: '工艺说明',
  typical_route: '典型路线',
}

function categoryLabel(category: string): string {
  return categoryLabels[category] || '本地记录'
}

type RelationshipKind = 'equipment' | 'tool' | 'gauge'

const relationshipKinds: Array<{ key: RelationshipKind; label: string }> = [
  { key: 'equipment', label: '设备' },
  { key: 'tool', label: '刀具' },
  { key: 'gauge', label: '量具' },
]

function formatNumber(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return ''
  return Number.isInteger(value) ? String(value) : String(Number(value.toFixed(3)))
}

function formatRange(
  min: number | null | undefined,
  max: number | null | undefined,
  unit = '',
): string {
  if (min != null && max != null && min > max) return ''
  const lower = formatNumber(min)
  const upper = formatNumber(max)
  if (!lower && !upper) return ''
  const range = lower && upper ? (lower === upper ? lower : `${lower}–${upper}`) : lower || upper
  return `${range}${unit ? ` ${unit}` : ''}`
}

function precisionText(item: KnowledgeSearchItem): string {
  const precision = item.capability?.precision
  if (!precision || precision.bounds_valid === false) return ''
  if (precision.code) return precision.code
  const grades = [precision.min_grade, precision.max_grade].filter(value => value != null && value !== '').join('–')
  return grades ? [precision.type, grades].filter(Boolean).join(' ') : ''
}

function roughnessText(item: KnowledgeSearchItem): string {
  const value = item.capability?.roughness
  return value && value.bounds_valid !== false ? formatRange(value.min_um, value.max_um, 'μm') : ''
}

function allowanceText(item: KnowledgeSearchItem): string {
  const value = item.capability?.allowance
  return value && value.bounds_valid !== false ? formatRange(value.min_mm, value.max_mm, 'mm') : ''
}

function sizeText(item: KnowledgeSearchItem): string {
  const value = item.capability?.size
  return value && value.bounds_valid !== false ? formatRange(value.min_mm, value.max_mm, 'mm') : ''
}

function otherMetricsText(item: KnowledgeSearchItem): string {
  const value = item.capability?.other_metrics
  if (value == null || value === '') return ''
  return typeof value === 'string' ? value : formatFieldValue(value)
}

function relationshipFor(item: KnowledgeSearchItem, kind: RelationshipKind): KnowledgeRelationship | undefined {
  return item.relationships?.[kind]
}

function relationshipStatusLabel(relationship: KnowledgeRelationship | undefined): string {
  if (!relationship || relationship.status === 'not_provided') return '样例未提供'
  if (relationship.status === 'category_hint') return '仅有类别线索'
  return '已关联'
}

function relationshipBasisLabel(relationship: KnowledgeRelationship | undefined): string {
  if (!relationship || relationship.status === 'not_provided') return '样例库未提供明确关联依据'
  if (relationship.basis === 'id') return '明确 ID 关联'
  if (relationship.basis === 'record_text') return '历史记录依据'
  return relationship.basis || '记录依据'
}

function relationshipHint(kind: RelationshipKind, relationship: KnowledgeRelationship | undefined): string {
  if (!relationship || relationship.status === 'not_provided') {
    const label = relationshipKinds.find(item => item.key === kind)?.label || kind
    return `样例库未提供该能力与${label}的明确关联`
  }
  if (relationship.status === 'category_hint') return '只有类别线索，不能确认具体型号或主数据'
  return relationshipBasisLabel(relationship)
}

function relationshipItems(relationship: KnowledgeRelationship | undefined): KnowledgeRelationshipItem[] {
  return relationship?.items || []
}

function formatFieldValue(value: unknown): string {
  if (value == null || value === '') return ''
  if (Array.isArray(value)) return value.map(formatFieldValue).filter(Boolean).join('、')
  if (typeof value === 'object') return JSON.stringify(value)
  return String(value)
}

function operationResources(operation: KnowledgeRouteOperation): Array<{ label: string; value: string }> {
  return relationshipKinds
    .filter(kind => operation[kind.key] !== undefined)
    .map(kind => ({ label: kind.label, value: formatFieldValue(operation[kind.key]) || '样例未提供' }))
}

function relationshipFields(item: KnowledgeRelationshipItem): string {
  return Object.entries(item.fields || {})
    .map(([key, value]) => `${key}：${formatFieldValue(value)}`)
    .filter(text => !text.endsWith('：'))
    .join(' · ')
}

function relationshipGapLabel(value: string): string {
  const labels: Record<string, string> = { equipment: '设备', tool: '刀具', gauge: '量具' }
  return labels[value] || value
}

type ResourceKind = 'equipment' | 'tool' | 'gauge' | 'history'

const resourceKinds: Array<{ key: ResourceKind; label: string }> = [
  { key: 'equipment', label: '设备' },
  { key: 'tool', label: '刀具' },
  { key: 'gauge', label: '量具' },
  { key: 'history', label: '历史案例' },
]

const isHistoryCatalog = computed(() => resourceSummary.value?.scope === 'catalog' && (
  intent.value === 'history'
  || resourceSummary.value.history != null
  || resourceSummary.value.history_count != null
))

const resourceSummaryTitle = computed(() => {
  if (isHistoryCatalog.value) return '历史案例目录'
  return resourceSummary.value?.scope === 'catalog' ? '主数据汇总' : '历史资源汇总'
})

const catalogResourceLabel = computed(() => {
  const kinds = resourceKinds.filter(kind => (resourceSummary.value?.[kind.key]?.length || 0) > 0)
  if (kinds.length) return kinds.map(kind => kind.label).join('、')
  return resourceKinds.find(kind => kind.key === intent.value)?.label || '主数据'
})

function resourceEntries(kind: ResourceKind): KnowledgeResourceSummaryItem[] {
  return resourceSummary.value?.[kind] || []
}

function resourceUniqueCount(kind: ResourceKind): number {
  const summary = resourceSummary.value
  const explicit = summary?.[`${kind}_count`]
  if (typeof explicit === 'number') return explicit
  return resourceEntries(kind).length
}

function resourceEntryCount(entry: KnowledgeResourceSummaryItem): number {
  if (typeof entry.unique_count === 'number') return entry.unique_count
  if (typeof entry.count === 'number') return entry.count
  return 1
}

function resourceSourceText(source: string | KnowledgeSource): string {
  if (typeof source === 'string') return source
  const location = [
    source.document_name,
    source.worksheet,
    source.row_no != null ? `第 ${source.row_no} 行` : '',
    source.cell_range,
    source.page_no != null ? `第 ${source.page_no} 页` : '',
    source.identity,
  ].filter((value): value is string => typeof value === 'string' && Boolean(value))
  return [...new Set(location)].join(' · ') || source.url || '本地记录'
}

function resourceFields(entry: KnowledgeResourceSummaryItem): Array<{ label: string; value: string }> {
  return Object.entries(entry.fields || {})
    .map(([label, value]) => ({ label, value: formatFieldValue(value) }))
    .filter(field => Boolean(field.value))
}

function askSampleQuestion(question: string) {
  query.value = question
  return runSearch()
}

async function runSearch() {
  const generation = ++contextGeneration.value
  const requestId = ++searchRequestId.value
  const text = query.value.trim()
  savingItemId.value = ''
  if (!text) {
    loading.value = false
    error.value = '请输入要查询的工艺问题。'
    return
  }
  hasSearched.value = true
  savedEvidenceIds.value = {}
  loading.value = true
  error.value = ''
  message.value = ''
  answerText.value = ''
  intent.value = 'general'
  relationshipGaps.value = []
  resourceSummary.value = null
  try {
    const result = await searchKnowledge({
      project_id: projectId.value,
      query: text,
      top_k: topK.value,
      context: operationContext.value,
    })
    if (generation !== contextGeneration.value || requestId !== searchRequestId.value) return
    status.value = result.status
    message.value = result.message
    answerText.value = result.answer
    items.value = result.items
    intent.value = result.intent || 'general'
    relationshipGaps.value = result.relationship_gaps || []
    resourceSummary.value = result.resource_summary || null
  } catch (err: any) {
    if (generation !== contextGeneration.value || requestId !== searchRequestId.value) return
    error.value = err?.response?.data?.detail || '知识库查询失败，请检查服务状态。'
    status.value = 'idle'
    items.value = []
  } finally {
    if (generation === contextGeneration.value && requestId === searchRequestId.value) loading.value = false
  }
}

async function adoptEvidence(item: KnowledgeSearchItem) {
  const generation = contextGeneration.value
  const currentProjectId = projectId.value
  savingItemId.value = item.id
  error.value = ''
  try {
    const saved: KnowledgeEvidence = await saveKnowledgeEvidence({
      project_id: currentProjectId,
      route_version_id: routeVersionId.value,
      segment_id: typeof operationContext.value?.segment_id === 'string'
        ? operationContext.value.segment_id || undefined
        : undefined,
      query: query.value.trim(),
      item_id: item.id,
      content: item.content,
      document_id: item.source.document_id,
      document_name: item.source.document_name,
      page_no: item.source.page_no,
      identity: item.source.identity,
      retrieval_method: item.retrieval_method,
    })
    if (generation !== contextGeneration.value) return
    savedEvidenceIds.value = { ...savedEvidenceIds.value, [item.id]: saved.id }
  } catch (err: any) {
    if (generation !== contextGeneration.value) return
    error.value = err?.response?.data?.detail || '保存知识依据失败。'
  } finally {
    if (generation === contextGeneration.value) savingItemId.value = ''
  }
}

onMounted(() => {
  if (query.value.trim()) void runSearch()
})

watch(() => route.fullPath, () => {
  contextGeneration.value += 1
  searchRequestId.value += 1
  savingItemId.value = ''
  loading.value = false
  query.value = firstQueryValue(route.query.q)
  items.value = []
  savedEvidenceIds.value = {}
  status.value = 'idle'
  hasSearched.value = false
  message.value = ''
  answerText.value = ''
  intent.value = 'general'
  relationshipGaps.value = []
  resourceSummary.value = null
  error.value = ''
  if (query.value.trim()) void runSearch()
})

onActivated(() => {
  if (query.value.trim() && !items.value.length && !loading.value) void runSearch()
})
</script>

<template>
  <div class="knowledge-view">
    <section class="knowledge-hero" aria-labelledby="knowledge-title">
      <div class="hero-main">
        <div class="hero-title-row">
          <h1 id="knowledge-title">轴套工艺知识库</h1>
          <span class="local-badge">本地样例库</span>
        </div>
        <p>从工艺说明、历史工艺与能力数据中，找到有据可查的参考答案。</p>
      </div>
      <div class="hero-note">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M12 3 4 6v6c0 5 8 9 8 9s8-4 8-9V6l-8-3Z"/><path d="m8.5 12 2.5 2.5 4.5-5"/></svg>
        回答附带原始来源
      </div>
    </section>

    <section class="knowledge-query card">
      <div class="query-heading">
        <label class="query-label" for="knowledge-query-input">你想了解什么？</label>
        <span>工艺说明 / 典型路线 / 历史工艺 / 加工能力 / 资源参数</span>
      </div>
      <div class="query-row">
        <div class="query-field">
          <svg class="search-icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4"/></svg>
        <input
          id="knowledge-query-input"
          v-model="query"
          class="query-input"
          type="search"
          placeholder="例如：9Cr18 衬套的历史工艺路线有哪些？"
          @keyup.enter="runSearch"
        />
        </div>
        <select v-model.number="topK" class="query-limit" aria-label="检索条数">
          <option :value="5">前 5 条</option>
          <option :value="8">前 8 条</option>
          <option :value="10">前 10 条</option>
        </select>
        <button class="btn btn-primary query-submit" :disabled="loading" @click="runSearch">
          <span v-if="loading" class="loading-spinner" aria-hidden="true"></span>
          {{ loading ? '回答生成中…' : '查询' }}
          <svg v-if="!loading" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6"/></svg>
        </button>
      </div>
      <div class="samples-heading"><span>试试这样问</span><span>点击问题，即可查询</span></div>
      <div class="sample-questions" aria-label="示例问题">
        <button v-for="sample in visibleSampleQuestions" :key="sample.label" type="button" :disabled="loading" @click="askSampleQuestion(sample.question)">
          <span class="sample-label">{{ sample.label }}</span>
          <span class="sample-text">{{ sample.question }}</span>
          <span class="sample-arrow" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M7 17 17 7M8 7h9v9" /></svg></span>
        </button>
      </div>
      <button
        v-if="sampleQuestions.length > initialSampleQuestionCount"
        class="sample-toggle"
        type="button"
        :aria-expanded="showAllSampleQuestions"
        @click="showAllSampleQuestions = !showAllSampleQuestions"
      >
        {{ showAllSampleQuestions ? '收起示例' : `更多示例问题（${sampleQuestions.length - initialSampleQuestionCount}）` }}
        <svg :class="{ rotated: showAllSampleQuestions }" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="m6 9 6 6 6-6" /></svg>
      </button>
      <p v-if="operationContext" class="query-context">
        已携带当前工序上下文：{{ operationContext.segment_id || operationContext.operation_name || '当前工序' }}
      </p>
    </section>

    <div v-if="error" class="knowledge-alert error" role="alert">{{ error }}</div>
    <div v-else-if="message" class="knowledge-alert" :class="{ error: status === 'llm_unavailable' }" role="status">{{ message }}</div>

    <section v-if="loading" class="knowledge-loading card" role="status" aria-live="polite">
      <span class="loading-spinner" aria-hidden="true"></span>
      <div><strong>正在查找依据并组织回答</strong><p>检索本地样例，结合相关记录生成答案，请稍候。</p></div>
    </section>

    <section v-if="answerText && !loading" class="knowledge-answer card" aria-labelledby="answer-heading">
      <div class="answer-heading">
        <div class="answer-title"><span class="answer-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><path d="M5 4h10l4 4v12H5V4Z"/><path d="M14 4v5h5M8 13h8m-8 4h5"/></svg></span><h2 id="answer-heading">知识库回答</h2></div>
        <span class="answer-count">基于 {{ items.length }} {{ isHistoryRoute ? '份历史工艺路线' : isTypicalRoute ? '条典型路线指导' : '条本地记录' }}</span>
      </div>
      <p class="answer-body"><template v-for="(segment, index) in answerSegments" :key="index"><strong v-if="segment.emphasis">{{ segment.text }}</strong><template v-else>{{ segment.text }}</template></template></p>
      <div class="answer-footer"><span class="answer-footnote-dot" aria-hidden="true"></span>下方可查看对应记录及来源</div>
    </section>

    <div v-if="intent === 'capability' && relationshipGaps.length && !loading" class="relationship-gap-note" role="status">
      <strong>关联范围提示</strong>
      <span>当前查询涉及的{{ relationshipGaps.map(relationshipGapLabel).join('、') }}关系在样例库中不足；页面只展示有明确依据的关联。</span>
    </div>

    <section v-if="resourceSummary && !loading" class="resource-summary card" aria-labelledby="resource-summary-heading">
      <div class="resource-summary-heading">
        <div>
          <h2 id="resource-summary-heading">{{ resourceSummaryTitle }}</h2>
          <p v-if="isHistoryCatalog">样例库共找到 {{ resourceSummary.record_count }} 条历史案例，下面列出案例目录及原始来源。</p>
          <p v-else-if="resourceSummary.scope === 'catalog'">样例库共找到 {{ resourceSummary.record_count }} 条主数据，下面列出可核对的{{ catalogResourceLabel }}记录。</p>
          <p v-else>覆盖 {{ resourceSummary.record_count }} 条历史记录（工序），资源按名称和型号去重统计；证据卡保留原始工序来源。</p>
          <p v-if="resourceSummary.scope === 'catalog' && !isHistoryCatalog" class="resource-summary-dedup">统计口径：名称、型号与参数去重项；相同名称和型号的不同规格会分别展示。</p>
        </div>
        <div class="resource-summary-badges">
          <span class="resource-summary-badge">本地汇总</span>
          <span v-if="resourceSummary.scope === 'catalog'" class="resource-summary-badge">原始记录 {{ resourceSummary.record_count }} 条</span>
          <span v-if="resourceSummary.unique_count != null" class="resource-summary-badge">去重 {{ resourceSummary.unique_count }} 项</span>
        </div>
      </div>
      <div class="resource-summary-grid" :class="{ 'resource-summary-grid-history': isHistoryCatalog }">
        <template v-for="kind in resourceKinds" :key="kind.key">
          <div v-if="resourceUniqueCount(kind.key)" class="resource-summary-group">
            <div class="resource-summary-group-heading">
              <h3>{{ kind.label }}</h3>
              <span>去重 {{ resourceUniqueCount(kind.key) }} 项</span>
            </div>
            <div class="resource-summary-items">
              <div v-for="resource in resourceEntries(kind.key)" :key="`${resource.id || resource.name}-${resource.model || ''}`" class="resource-summary-item">
                <div class="resource-summary-item-main">
                  <strong>{{ resource.name }}</strong>
                  <span v-if="resource.model">{{ resource.model }}</span>
                </div>
                <small v-if="resource.id">记录 ID：{{ resource.id }}</small>
                <small v-if="resourceEntryCount(resource) > 1">出现 {{ resourceEntryCount(resource) }} 次</small>
                <div v-if="resource.data_warnings?.length" class="knowledge-alert data-warning" role="status">
                  <strong>源数据校验提示</strong>
                  <p v-for="warning in resource.data_warnings" :key="warning">{{ warning }}</p>
                </div>
                <details v-if="resourceFields(resource).length" class="resource-details">
                  <summary>参数与规格 <span>{{ resourceFields(resource).length }} 项</span></summary>
                  <dl class="resource-parameter-list">
                    <div v-for="field in resourceFields(resource)" :key="field.label">
                      <dt>{{ field.label }}</dt>
                      <dd>{{ field.value }}</dd>
                    </div>
                  </dl>
                </details>
                <details v-if="resource.sources?.length" class="resource-details">
                  <summary>来源依据 <span>{{ resource.sources.length }} 条</span></summary>
                  <ul class="resource-source-list">
                    <li v-for="(source, sourceIndex) in resource.sources" :key="sourceIndex">{{ resourceSourceText(source) }}</li>
                  </ul>
                </details>
              </div>
            </div>
          </div>
        </template>
      </div>
    </section>

    <section v-if="items.length && !loading" class="knowledge-results" aria-labelledby="results-heading">
      <div class="results-heading">
        <div>
          <h2 id="results-heading">{{ isHistoryRoute ? '历史工艺路线依据' : isTypicalRoute ? '典型路线依据' : '匹配依据' }} <span class="result-count">{{ items.length }}</span></h2>
          <p>{{ isHistoryRoute ? '每份路线独立展示，工序按原始规程顺序排列。' : isTypicalRoute ? '典型指导与历史实际执行记录分开展示。' : '查看原始记录，核对答案中的引用。' }}</p>
        </div>
        <span class="results-note">按检索相关性排序</span>
      </div>

      <article v-for="(item, index) in items" :key="item.id" class="knowledge-result card">
        <div class="result-topline">
          <span class="result-index">[{{ index + 1 }}]</span>
          <h3 class="result-title">{{ item.title || '本地知识记录' }}</h3>
          <span class="result-rank">{{ item.route ? '历史工艺路线' : categoryLabel(item.category) }}</span>
        </div>
        <section v-if="item.route" class="history-route-panel" :aria-label="`依据 ${index + 1} 历史工艺路线`">
          <div class="history-route-heading">
            <div>
              <h4>{{ item.route.part_name || '历史工艺路线' }}</h4>
              <p>按原始规程顺序展示，保留重复工序</p>
            </div>
            <span class="history-route-count">共 {{ item.route.operation_count }} 道工序</span>
          </div>
          <div class="history-route-meta">
            <span v-if="item.route.part_id"><b>零件</b>{{ item.route.part_id }}</span>
            <span v-if="item.route.material"><b>材料</b>{{ item.route.material }}</span>
            <span v-if="item.route.process_id"><b>规程</b>{{ item.route.process_id }}</span>
            <span v-if="item.route.version">版本 {{ item.route.version }}</span>
          </div>
          <ol class="history-route-operations" aria-label="原始工序顺序">
            <li v-for="operation in item.route.operations" :key="operation.id" class="history-route-operation">
              <div class="history-route-operation-topline">
                <div class="history-route-operation-label"><span class="history-route-number">{{ operation.number }}</span><strong>{{ operation.name }}</strong></div>
                <details class="history-route-source">
                  <summary>来源依据</summary>
                  <p>{{ resourceSourceText(operation.source) }}</p>
                </details>
              </div>
              <details v-if="operationResources(operation).length" class="history-route-resources">
                <summary>工序资源记录</summary>
                <dl>
                  <div v-for="resource in operationResources(operation)" :key="resource.label">
                    <dt>{{ resource.label }}</dt><dd>{{ resource.value }}</dd>
                  </div>
                </dl>
              </details>
            </li>
          </ol>
        </section>
        <KnowledgeGuidanceCard v-else-if="item.guidance" :guidance="item.guidance" />
        <p v-else class="result-content" tabindex="0" :aria-label="`依据 ${index + 1} 记录内容`">{{ item.content }}</p>
        <div v-if="item.data_warnings?.length" class="knowledge-alert data-warning" role="status">
          <strong>源数据校验提示</strong>
          <p v-for="warning in item.data_warnings" :key="warning">{{ warning }}</p>
        </div>
        <section v-if="item.capability" class="capability-panel" aria-label="加工能力结构化信息">
          <div class="capability-heading">
            <div>
              <h4>加工能力</h4>
              <p>按加工特征和适用条件整理的样例关系</p>
            </div>
            <span class="capability-intent">加工能力记录</span>
          </div>
          <div class="capability-groups">
            <div class="capability-group">
              <span class="capability-group-label">加工特征</span>
              <div class="capability-values">
                <span v-if="item.capability.feature" class="capability-value"><b>特征</b>{{ item.capability.feature }}</span>
                <span v-if="item.capability.method" class="capability-value"><b>方法</b>{{ item.capability.method }}</span>
                <span v-if="item.capability.stage" class="capability-value"><b>阶段</b>{{ item.capability.stage }}</span>
              </div>
            </div>
            <div class="capability-group">
              <span class="capability-group-label">指标范围</span>
              <div class="capability-values">
                <span v-if="precisionText(item)" class="capability-value"><b>精度</b>{{ precisionText(item) }}</span>
                <span v-if="roughnessText(item)" class="capability-value"><b>粗糙度</b>{{ roughnessText(item) }}</span>
                <span v-if="allowanceText(item)" class="capability-value"><b>余量</b>{{ allowanceText(item) }}<em v-if="item.capability.allowance?.basis">（{{ item.capability.allowance.basis }}）</em></span>
                <span v-if="otherMetricsText(item)" class="capability-value"><b>其他指标</b>{{ otherMetricsText(item) }}</span>
              </div>
            </div>
            <div v-if="item.capability.material || item.capability.size || item.capability.conditions || item.capability.tool_material" class="capability-group">
              <span class="capability-group-label">适用条件</span>
              <div class="capability-values">
                <span v-if="item.capability.material" class="capability-value"><b>材料</b>{{ item.capability.material }}<em v-if="item.capability.material_state">（{{ item.capability.material_state }}）</em></span>
                <span v-if="sizeText(item)" class="capability-value"><b>尺寸范围</b>{{ sizeText(item) }}<em v-if="item.capability.size?.type">（{{ item.capability.size.type }}）</em></span>
                <span v-if="item.capability.conditions" class="capability-value"><b>条件</b>{{ item.capability.conditions }}</span>
                <span v-if="item.capability.tool_material" class="capability-value"><b>刀具材料</b>{{ item.capability.tool_material }}</span>
              </div>
            </div>
          </div>
          <div v-if="item.relationships" class="relationships-panel">
            <h5>关联对象</h5>
            <div class="relationship-grid">
              <div v-for="relationshipKind in relationshipKinds" :key="relationshipKind.key" class="relationship-card" :class="`relationship-${relationshipFor(item, relationshipKind.key)?.status || 'not_provided'}`">
                <div class="relationship-title-row">
                  <span>{{ relationshipKind.label }}</span>
                  <span class="relationship-status">{{ relationshipStatusLabel(relationshipFor(item, relationshipKind.key)) }}</span>
                </div>
                <p class="relationship-basis">{{ relationshipHint(relationshipKind.key, relationshipFor(item, relationshipKind.key)) }}</p>
                <div v-if="relationshipItems(relationshipFor(item, relationshipKind.key)).length" class="relationship-items">
                  <div v-for="related in relationshipItems(relationshipFor(item, relationshipKind.key))" :key="`${related.id || related.name}-${related.record_level || ''}`" class="relationship-item">
                    <strong>{{ related.name }}</strong>
                    <small v-if="related.id">ID：{{ related.id }}</small>
                    <small v-if="related.model">型号：{{ related.model }}</small>
                    <span v-if="related.record_level" class="record-level">{{ related.record_level }}</span>
                    <small v-if="related.entity_category">{{ related.entity_category }}</small>
                    <small v-if="relationshipFields(related)">{{ relationshipFields(related) }}</small>
                  </div>
                </div>
                <p v-else class="relationship-empty">没有可展示的明确记录</p>
              </div>
            </div>
          </div>
        </section>
        <div class="result-footer">
          <div class="result-source">
            <span class="source-file"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" aria-hidden="true"><path d="M5 3h9l5 5v13H5V3Z"/><path d="M14 3v6h5"/></svg>{{ item.source.document_name || '本地数据' }}</span>
            <div class="source-location">
              <span v-if="item.source.worksheet">{{ item.source.worksheet }}</span>
              <span v-if="item.source.row_no">第 {{ item.source.row_no }} 行</span>
              <span v-if="item.source.cell_range">{{ item.source.cell_range }}</span>
              <span v-if="item.source.page_no">第 {{ item.source.page_no }} 页</span>
            </div>
            <span v-if="item.source.identity" class="source-identity">{{ item.source.identity }}</span>
            <span v-if="item.guidance" class="source-identity">记录 ID：{{ item.id }}</span>
          </div>
          <div class="result-actions">
          <span v-if="savedEvidenceIds[item.id]" class="adopted" role="status">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" aria-hidden="true"><path d="m5 12 4 4L19 6" /></svg>
            已采纳 <small>#{{ savedEvidenceIds[item.id] }}</small>
          </span>
          <button v-else class="btn btn-outline btn-sm" :disabled="savingItemId === item.id" @click="adoptEvidence(item)">
            {{ savingItemId === item.id ? '保存中…' : '采纳为依据' }}
          </button>
          </div>
        </div>
      </article>
    </section>

    <section v-if="!items.length && ['ok', 'no_evidence', 'insufficient_evidence'].includes(status) && hasSearched && !loading" class="knowledge-empty card">
      <div class="empty-mark" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6"><circle cx="10.5" cy="10.5" r="6.5"/><path d="m16 16 4 4M8 10.5h5"/></svg></div>
      <h2>没有找到相关知识</h2>
      <p>本地样例库没有找到相关依据，可以尝试更具体的零件名称、材料牌号、设备型号或加工特征。</p>
      <div class="empty-suggestions" aria-label="试试这些问题">
        <button v-for="question in emptyRecoveryQuestions" :key="question" type="button" :disabled="loading" @click="askSampleQuestion(question)">
          {{ question }}
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M7 17 17 7M8 7h9v9" /></svg>
        </button>
      </div>
    </section>
  </div>
</template>

<style scoped>
.knowledge-view { max-width: var(--page-max-width); margin: 0 auto; padding: 12px 0 32px; }
.knowledge-hero { display: flex; justify-content: space-between; gap: 24px; align-items: center; margin-bottom: 22px; }
.hero-title-row { display: flex; align-items: center; flex-wrap: wrap; gap: 12px; margin-bottom: 8px; }
.knowledge-hero h1 { font-size: 24px; line-height: 1.4; font-weight: 650; letter-spacing: -.025em; }
.knowledge-hero p { color: var(--text-secondary); font-size: 14px; line-height: 1.7; }
.local-badge { display: inline-flex; align-items: center; gap: 6px; padding: 4px 9px; border: 1px solid var(--border-light); border-radius: 6px; background: var(--bg-card); color: var(--text-secondary); font-size: 12px; font-weight: 500; }
.local-badge::before { content: ''; width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.hero-note { display: flex; align-items: center; gap: 7px; flex-shrink: 0; color: var(--text-secondary); font-size: 12px; }
.hero-note svg { width: 17px; height: 17px; color: var(--accent); }
.card { background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-md); box-shadow: var(--shadow-sm); }
.card:hover { box-shadow: var(--shadow-sm); }
.knowledge-query { padding: 22px 24px; margin-bottom: 20px; }
.query-heading { display: flex; align-items: center; justify-content: space-between; gap: 16px; margin-bottom: 13px; }
.query-label { color: var(--text-primary); font-size: 16px; font-weight: 600; }
.query-heading > span { color: var(--text-secondary); font-size: 12px; }
.query-row { display: flex; gap: 10px; }
.query-field { display: flex; align-items: center; flex: 1; min-width: 0; border: 1px solid var(--border-light); border-radius: 8px; background: var(--bg-primary); transition: border-color .15s, box-shadow .15s; }
.query-field:focus-within { border-color: var(--accent); box-shadow: 0 0 0 3px var(--accent-light); background: var(--bg-card); }
.search-icon { flex: 0 0 18px; width: 18px; height: 18px; margin-left: 14px; color: var(--text-secondary); }
.query-input { flex: 1; min-width: 0; width: 100%; background: transparent; color: var(--text-primary); border: 0; padding: 14px 12px; font: inherit; font-size: 15px; outline: none; }
.query-input::placeholder { color: #64748b; }
.query-limit { border: 1px solid var(--border-light); border-radius: 8px; color: var(--text-secondary); padding: 0 10px; background: var(--bg-card); font: inherit; font-size: 12px; cursor: pointer; }
.query-submit { justify-content: center; flex-shrink: 0; min-width: 100px; padding: 10px 18px; }
.query-submit svg { width: 16px; height: 16px; }
.samples-heading { display: flex; align-items: center; gap: 12px; margin: 21px 0 10px; color: var(--text-secondary); font-size: 13px; }
.samples-heading span:first-child { font-weight: 600; }
.samples-heading span:last-child { font-size: 12px; color: var(--text-secondary); }
.sample-questions { display: flex; flex-wrap: wrap; gap: 8px; }
.sample-questions button { display: flex; align-items: center; gap: 9px; min-width: 0; max-width: 100%; min-height: 40px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-card); color: var(--text-secondary); padding: 9px 11px; font: inherit; font-size: 13px; line-height: 1.5; text-align: left; cursor: pointer; transition: background .15s, border-color .15s, color .15s; }
.sample-questions button:hover:not(:disabled) { border-color: #c7d2fe; background: #f5f6ff; color: var(--accent); }
.sample-questions button:disabled { opacity: .55; cursor: wait; }
.sample-label { flex-shrink: 0; font-size: 11px; color: var(--accent); background: #eef2ff; padding: 3px 6px; border-radius: 4px; }
.sample-text { overflow-wrap: anywhere; }
.sample-arrow { display: inline-flex; align-items: center; justify-content: center; flex: 0 0 auto; width: 18px; height: 18px; margin-left: auto; color: #64748b; }
.sample-arrow svg { width: 16px; height: 16px; }
.sample-toggle { display: inline-flex; align-items: center; gap: 5px; min-height: 36px; margin-top: 6px; padding: 4px 2px; border: 0; background: transparent; color: var(--accent); font: inherit; font-size: 12px; cursor: pointer; }
.sample-toggle:hover:not(:disabled) { color: var(--accent-hover); }
.sample-toggle svg { width: 15px; height: 15px; transition: transform .16s ease; }
.sample-toggle svg.rotated { transform: rotate(180deg); }
.query-context { color: var(--accent); background: #f5f6ff; padding: 8px 11px; border-radius: 6px; font-size: 12px; margin-top: 14px; overflow-wrap: anywhere; }
.knowledge-alert { background: #fffbeb; border: 1px solid #fde68a; border-radius: 8px; color: #92400e; padding: 12px 16px; margin-bottom: 16px; font-size: 14px; line-height: 1.7; }
.knowledge-alert.error { background: #fff1f2; border-color: #fecdd3; color: #be123c; }
.knowledge-alert.data-warning { margin: 8px 0 12px; padding: 8px 10px; font-size: 12px; overflow-wrap: anywhere; }
.data-warning strong { font-weight: 650; }
.data-warning p { margin-top: 3px; }
.knowledge-loading { display: flex; align-items: center; gap: 14px; padding: 24px; color: var(--accent); }
.knowledge-loading strong { font-size: 14px; font-weight: 600; color: var(--text-primary); }
.knowledge-loading p { color: var(--text-secondary); font-size: 13px; margin-top: 5px; }
.loading-spinner { display: inline-block; flex-shrink: 0; width: 15px; height: 15px; border: 2px solid currentColor; border-right-color: transparent; border-radius: 50%; animation: knowledge-spin .8s linear infinite; }
@keyframes knowledge-spin { to { transform: rotate(360deg); } }
.knowledge-answer { overflow: hidden; padding: 0; margin-bottom: 26px; }
.answer-heading { display: flex; align-items: center; justify-content: space-between; gap: 14px; padding: 15px 22px; border-bottom: 1px solid var(--border-light); background: #fafaff; }
.answer-title { display: flex; align-items: center; gap: 10px; }
.answer-icon { display: flex; align-items: center; justify-content: center; width: 30px; height: 30px; background: #eef2ff; color: var(--accent); border-radius: 7px; }
.answer-icon svg { width: 19px; height: 19px; }
.answer-title h2 { font-size: 15px; font-weight: 600; }
.answer-count { color: var(--text-secondary); font-size: 12px; }
.answer-body { padding: 21px 24px 23px; color: #334155; font-size: 14px; line-height: 1.7; white-space: pre-wrap; overflow-wrap: anywhere; }
.answer-body strong { color: var(--text-primary); font-weight: 600; }
.answer-footer { display: flex; align-items: center; gap: 7px; margin: 0 24px; padding: 12px 0; border-top: 1px solid var(--border-light); color: var(--text-secondary); font-size: 12px; }
.answer-footnote-dot { width: 5px; height: 5px; border-radius: 50%; background: var(--accent); }
.relationship-gap-note { display: flex; align-items: baseline; gap: 10px; padding: 11px 14px; margin: -10px 0 20px; border: 1px solid #fde68a; border-radius: 8px; background: #fffbeb; color: #92400e; font-size: 12px; line-height: 1.65; }
.relationship-gap-note strong { flex: 0 0 auto; font-weight: 650; }
.resource-summary { padding: 18px 22px; margin: 0 0 22px; }
.resource-summary-heading { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 14px; }
.resource-summary-heading h2 { color: var(--text-primary); font-size: 15px; font-weight: 650; }
.resource-summary-heading p { margin-top: 5px; color: var(--text-secondary); font-size: 13px; line-height: 1.65; }
.resource-summary-heading .resource-summary-dedup { color: var(--text-secondary); font-size: 12px; }
.resource-summary-badges { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 6px; flex: 0 0 auto; }
.resource-summary-badge { flex: 0 0 auto; padding: 4px 7px; border-radius: 5px; background: #eef2ff; color: var(--accent); font-size: 11px; font-weight: 600; }
.resource-summary-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(min(100%, 260px), 1fr)); gap: 10px; }
.resource-summary-grid-history { grid-template-columns: 1fr; }
.resource-summary-group { min-width: 0; padding: 12px 14px; border-radius: 7px; background: var(--bg-primary); }
.resource-summary-group-heading { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 9px; }
.resource-summary-group-heading h3 { color: var(--text-primary); font-size: 13px; font-weight: 650; }
.resource-summary-group-heading span { color: var(--accent); font-size: 12px; font-weight: 650; }
.resource-summary-items { display: grid; gap: 7px; max-height: 360px; overflow-y: auto; scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent; }
.resource-summary-item { min-width: 0; padding-bottom: 7px; border-bottom: 1px solid #e8eef5; }
.resource-summary-item:last-child { border-bottom: 0; padding-bottom: 0; }
.resource-summary-item-main { display: flex; flex-wrap: wrap; align-items: baseline; gap: 5px 8px; color: var(--text-primary); font-size: 12px; line-height: 1.5; }
.resource-summary-item-main strong { overflow-wrap: anywhere; }
.resource-summary-item-main span { color: var(--text-secondary); font-family: ui-monospace, SFMono-Regular, monospace; font-size: 11px; overflow-wrap: anywhere; }
.resource-summary-item small { display: block; margin-top: 3px; color: var(--text-secondary); font-size: 11px; line-height: 1.5; overflow-wrap: anywhere; }
.resource-details { margin-top: 6px; color: var(--text-secondary); font-size: 12px; }
.resource-details summary { width: fit-content; cursor: pointer; line-height: 1.7; color: var(--accent); }
.resource-details summary span { margin-left: 4px; color: var(--text-secondary); font-size: 11px; }
.resource-details summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
.resource-parameter-list, .resource-source-list { max-height: 200px; overflow-y: auto; margin: 6px 0 0; padding: 8px; background: var(--bg-card); border: 1px solid var(--border-light); border-radius: 5px; scrollbar-width: thin; }
.resource-parameter-list > div { display: grid; grid-template-columns: minmax(80px, .8fr) minmax(0, 1.2fr); gap: 8px; padding: 4px 0; border-bottom: 1px solid var(--border-light); }
.resource-parameter-list > div:last-child { border-bottom: 0; }
.resource-parameter-list dt { color: var(--text-muted); overflow-wrap: anywhere; }
.resource-parameter-list dd { margin: 0; color: var(--text-primary); white-space: pre-wrap; overflow-wrap: anywhere; }
.resource-source-list { list-style: none; }
.resource-source-list li { padding: 4px 0; line-height: 1.7; font-size: 11px; overflow-wrap: anywhere; }
.resource-source-list li + li { border-top: 1px solid var(--border-light); }
.resource-summary-more { margin-top: 9px; color: var(--text-secondary); font-size: 11px; line-height: 1.5; }
.results-heading { display: flex; justify-content: space-between; align-items: center; gap: 16px; margin: 24px 0 13px; }
.results-heading h2 { display: flex; align-items: center; gap: 9px; font-size: 16px; font-weight: 600; margin-bottom: 5px; }
.results-heading p, .results-note { color: var(--text-secondary); font-size: 12px; line-height: 1.6; }
.result-count { display: inline-flex; align-items: center; justify-content: center; min-width: 23px; height: 21px; padding: 0 6px; border-radius: 5px; background: #eef2ff; color: var(--accent); font-size: 11px; font-weight: 600; }
.knowledge-result { padding: 18px 22px 0; margin-bottom: 12px; }
.result-topline { display: flex; align-items: center; gap: 10px; }
.result-index { color: var(--accent); font-size: 12px; font-weight: 600; font-variant-numeric: tabular-nums; }
.result-title { flex: 1; min-width: 0; color: var(--text-primary); font-size: 15px; line-height: 1.6; font-weight: 600; overflow-wrap: anywhere; }
.result-rank { flex-shrink: 0; border: 1px solid var(--border-light); border-radius: 5px; color: var(--text-secondary); padding: 3px 7px; font-size: 11px; }
.result-content { color: var(--text-secondary); font-size: 13px; line-height: 1.85; margin: 13px 0 16px; max-height: 280px; overflow-y: auto; white-space: pre-wrap; overflow-wrap: anywhere; scrollbar-width: thin; scrollbar-color: #cbd5e1 transparent; }
.history-route-panel { margin: 14px 0 18px; border-block: 1px solid var(--border-light); background: var(--bg-primary); }
.history-route-heading { display: flex; justify-content: space-between; align-items: flex-start; gap: 12px; padding: 13px 15px; background: transparent; }
.history-route-heading h4 { color: var(--text-primary); font-size: 14px; font-weight: 650; }
.history-route-heading p { color: var(--text-secondary); margin-top: 4px; font-size: 12px; line-height: 1.6; }
.history-route-count { flex-shrink: 0; padding: 4px 7px; background: #eef2ff; color: var(--accent); border-radius: 5px; font-size: 12px; font-weight: 600; }
.history-route-meta { display: flex; flex-wrap: wrap; gap: 7px 18px; padding: 9px 15px; border-top: 1px solid var(--border-light); border-bottom: 1px solid var(--border-light); color: var(--text-secondary); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.history-route-meta span { display: inline-flex; gap: 6px; }
.history-route-meta b { color: var(--text-muted); font-weight: 500; }
.history-route-operations { margin: 0; padding: 4px 15px; list-style: none; }
.history-route-operation { padding: 8px 0; border-bottom: 1px solid var(--border-light); }
.history-route-operation:last-child { border-bottom: 0; }
.history-route-operation-topline { display: flex; align-items: baseline; justify-content: space-between; gap: 8px 20px; }
.history-route-operation-label { display: flex; align-items: baseline; gap: 12px; min-width: 0; color: var(--text-primary); font-size: 13px; line-height: 1.7; }
.history-route-operation-label strong { font-weight: 500; overflow-wrap: anywhere; }
.history-route-number { min-width: 30px; color: var(--accent); font-family: ui-monospace, SFMono-Regular, monospace; font-size: 12px; font-variant-numeric: tabular-nums; }
.history-route-source { max-width: 55%; color: var(--text-secondary); font-size: 11px; text-align: right; }
.history-route-source summary { color: var(--accent); line-height: 1.8; cursor: pointer; white-space: nowrap; }
.history-route-source summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
.history-route-source p { padding-top: 5px; line-height: 1.7; overflow-wrap: anywhere; }
.history-route-resources { margin: 5px 0 0 42px; color: var(--text-secondary); font-size: 12px; }
.history-route-resources summary { width: fit-content; color: var(--accent); line-height: 1.8; cursor: pointer; }
.history-route-resources summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 2px; }
.history-route-resources dl { margin: 5px 0 0; padding: 7px 9px; border: 1px solid var(--border-light); border-radius: 5px; background: #fbfdff; }
.history-route-resources dl > div { display: grid; grid-template-columns: 36px minmax(0, 1fr); gap: 8px; padding: 4px 0; line-height: 1.7; }
.history-route-resources dt { color: var(--text-muted); }
.history-route-resources dd { margin: 0; white-space: pre-wrap; overflow-wrap: anywhere; }
.capability-panel { margin: 4px 0 17px; border-block: 1px solid var(--border-light); background: var(--bg-primary); }
.capability-heading { display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 12px 14px; border-bottom: 1px solid var(--border-light); background: transparent; }
.capability-heading h4 { color: var(--text-primary); font-size: 14px; font-weight: 650; }
.capability-heading p { margin-top: 3px; color: var(--text-secondary); font-size: 12px; }
.capability-intent { flex: 0 0 auto; padding: 3px 7px; border: 1px solid #c7d2fe; border-radius: 4px; color: var(--accent); background: #eef2ff; font-size: 11px; }
.capability-groups { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 0; background: var(--bg-card); }
.capability-group { min-width: 0; padding: 13px 14px; border-right: 1px solid var(--border-light); }
.capability-group:last-child { border-right: 0; }
.capability-group-label { display: block; margin-bottom: 8px; color: var(--text-secondary); font-size: 11px; font-weight: 650; letter-spacing: .02em; }
.capability-values { display: flex; flex-wrap: wrap; gap: 6px; }
.capability-value { display: inline-flex; align-items: baseline; gap: 5px; max-width: 100%; color: var(--text-primary); font-size: 13px; line-height: 1.55; overflow-wrap: anywhere; }
.capability-value b { color: var(--text-secondary); font-size: 11px; font-weight: 500; }
.capability-value em { color: var(--text-secondary); font-size: 11px; font-style: normal; }
.relationships-panel { padding: 13px 14px 14px; border-top: 1px solid #e5ebf3; }
.relationships-panel h5 { margin-bottom: 9px; color: var(--text-primary); font-size: 13px; font-weight: 650; }
.relationship-grid { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 8px; }
.relationship-card { min-width: 0; padding: 10px; border-radius: 6px; background: var(--bg-card); }
.relationship-card.relationship-linked { background: #f5fffa; }
.relationship-card.relationship-category_hint { background: #f8fbff; }
.relationship-card.relationship-not_provided { background: #f8fafc; }
.relationship-title-row { display: flex; align-items: center; justify-content: space-between; gap: 6px; color: var(--text-primary); font-size: 13px; font-weight: 600; }
.relationship-status { flex: 0 0 auto; padding: 3px 6px; border-radius: 4px; font-size: 11px; font-weight: 500; }
.relationship-linked .relationship-status { color: #047857; background: #d1fae5; }
.relationship-category_hint .relationship-status { color: #1d4ed8; background: #dbeafe; }
.relationship-not_provided .relationship-status { color: #64748b; background: #e2e8f0; }
.relationship-basis { min-height: 32px; margin-top: 7px; color: var(--text-secondary); font-size: 11px; line-height: 1.55; }
.relationship-items { display: grid; gap: 5px; margin-top: 7px; }
.relationship-item { display: flex; flex-wrap: wrap; align-items: baseline; gap: 4px 7px; color: var(--text-primary); font-size: 12px; line-height: 1.5; }
.relationship-item strong { overflow-wrap: anywhere; }
.relationship-item small { color: var(--text-secondary); font-size: 11px; overflow-wrap: anywhere; }
.record-level { padding: 1px 4px; border-radius: 3px; background: #ecfdf5; color: #047857; font-size: 9px; }
.relationship-empty { margin-top: 7px; color: var(--text-secondary); font-size: 11px; }
.result-footer { display: flex; align-items: center; justify-content: space-between; gap: 20px; border-top: 1px solid var(--border-light); padding: 13px 0; }
.result-source { display: flex; flex-wrap: wrap; align-items: center; gap: 5px 12px; min-width: 0; color: var(--text-secondary); font-size: 12px; line-height: 1.6; overflow-wrap: anywhere; }
.source-file { display: inline-flex; align-items: center; gap: 6px; min-width: 0; max-width: 100%; overflow-wrap: anywhere; }
.source-file svg { flex-shrink: 0; width: 13px; height: 13px; color: #64748b; }
.source-location { display: flex; flex-wrap: wrap; gap: 5px 8px; }
.source-location span { background: var(--bg-primary); padding: 1px 6px; border-radius: 4px; }
.source-identity { flex-basis: 100%; color: #64748b; font-family: ui-monospace, SFMono-Regular, monospace; font-size: 10px; }
.result-actions { display: flex; align-items: center; flex-shrink: 0; }
.result-actions .btn { min-height: 36px; padding: 7px 11px; border-color: var(--border-light); color: var(--text-secondary); font-size: 13px; white-space: nowrap; }
.result-actions .btn:hover { transform: none; border-color: #c7d2fe; color: var(--accent); }
.adopted { display: inline-flex; align-items: center; gap: 6px; color: #047857; font-size: 13px; font-weight: 600; }
.adopted svg { width: 16px; height: 16px; }
.adopted small { color: var(--text-secondary); font-size: 11px; font-weight: 500; }
.knowledge-empty { padding: 36px 24px; text-align: center; color: var(--text-secondary); margin: 18px 0; }
.knowledge-empty h2 { color: var(--text-primary); font-size: 16px; margin: 14px 0 7px; }
.knowledge-empty p { max-width: 560px; margin: auto; font-size: 14px; line-height: 1.75; }
.empty-suggestions { display: flex; flex-wrap: wrap; justify-content: center; gap: 8px; max-width: 880px; margin: 20px auto 0; }
.empty-suggestions button { display: inline-flex; align-items: center; gap: 8px; min-height: 38px; max-width: 100%; padding: 8px 11px; border: 1px solid var(--border-light); border-radius: 7px; background: var(--bg-card); color: var(--text-secondary); font: inherit; font-size: 12px; line-height: 1.5; text-align: left; cursor: pointer; transition: border-color .15s, background .15s, color .15s; }
.empty-suggestions button:hover:not(:disabled) { border-color: #c7d2fe; background: #f5f6ff; color: var(--accent); }
.empty-suggestions button svg { flex: 0 0 auto; width: 15px; height: 15px; }
.empty-mark { display: flex; align-items: center; justify-content: center; width: 44px; height: 44px; margin: auto; border-radius: 12px; background: #eef2ff; color: var(--accent); }
.empty-mark svg { width: 24px; height: 24px; }
.knowledge-view :is(button, select, .result-content):focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; }
@media (prefers-reduced-motion: reduce) {
  .loading-spinner { animation: none; }
  .knowledge-view :is(button, .query-field, .sample-toggle svg) { transition: none; }
}
@media (max-width: 720px) {
  .knowledge-view { padding-top: 5px; }
  .knowledge-hero { align-items: flex-start; flex-direction: column; gap: 10px; margin-bottom: 18px; }
  .knowledge-hero h1 { font-size: 21px; }
  .hero-note { font-size: 11px; }
  .knowledge-query { padding: 17px 16px; }
  .query-heading { align-items: flex-start; flex-direction: column; gap: 7px; }
  .query-heading > span { font-size: 12px; }
  .query-row { flex-wrap: wrap; }
  .query-field { flex-basis: 100%; }
  .query-input { font-size: 16px; padding: 12px 10px; }
  .query-limit { min-height: 42px; flex: 1; }
  .query-submit { min-height: 42px; flex: 2; }
  .sample-questions { flex-direction: column; }
  .sample-questions button { width: 100%; gap: 7px; min-height: 44px; padding: 10px; }
  .sample-label { font-size: 11px; }
  .sample-toggle { min-height: 40px; }
  .empty-suggestions { flex-direction: column; align-items: stretch; }
  .empty-suggestions button { min-height: 44px; justify-content: space-between; font-size: 13px; }
  .sample-text { flex: 1; }
  .answer-heading { padding: 13px 16px; flex-wrap: wrap; gap: 8px; }
  .answer-count { font-size: 12px; }
  .answer-body { padding: 17px 16px; font-size: 14px; }
  .resource-summary { padding: 16px; }
  .resource-summary-heading { flex-direction: column; gap: 8px; }
  .resource-summary-grid { grid-template-columns: 1fr; }
  .answer-footer { margin: 0 16px; }
  .relationship-gap-note { align-items: flex-start; flex-direction: column; gap: 2px; margin-top: -4px; }
  .knowledge-result { padding: 15px 16px 0; }
  .result-topline { flex-wrap: wrap; gap: 7px; }
  .result-title { flex-basis: calc(100% - 35px); font-size: 13px; }
  .result-rank { margin-left: 27px; }
  .history-route-heading { flex-wrap: wrap; }
  .history-route-operation-topline { gap: 8px; }
  .history-route-source { max-width: 48%; }
  .capability-groups, .relationship-grid { grid-template-columns: 1fr; }
  .capability-group { border-right: 0; border-bottom: 1px solid #e5ebf3; }
  .capability-group:last-child { border-bottom: 0; }
  .result-footer { align-items: flex-start; flex-direction: column; gap: 12px; }
  .result-actions { align-self: flex-end; }
  .result-actions .btn { min-height: 40px; }
  .results-note { display: none; }
  .knowledge-loading { padding: 20px 16px; }
}
</style>
