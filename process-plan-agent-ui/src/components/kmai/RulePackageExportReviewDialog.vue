<template>
  <Teleport to="body">
    <div v-if="modelValue" class="export-review-backdrop" @click.self="cancel">
      <section class="export-review" role="dialog" aria-modal="true" aria-labelledby="export-review-title">
        <header class="export-review__header">
          <div>
            <h2 id="export-review-title">审核并导出规则包</h2>
            <p>请确认本次规则包的审核结果。确认后将发布并下载规则包。</p>
          </div>
          <button
            type="button"
            class="export-review__close"
            :disabled="submitting"
            aria-label="关闭审核弹窗"
            title="关闭"
            @click="cancel"
          >
            &times;
          </button>
        </header>

        <div v-if="review" class="export-review__body">
          <dl class="export-review__summary" aria-label="规则包摘要">
            <div>
              <dt>项目</dt>
              <dd>{{ review.projectName }}</dd>
            </div>
            <div>
              <dt>工序</dt>
              <dd>{{ review.processCount }} 道</dd>
            </div>
            <div>
              <dt>规则</dt>
              <dd>{{ review.ruleCount }} 条</dd>
            </div>
            <div>
              <dt>规则校验</dt>
              <dd :class="review.validation?.valid ? 'is-success' : review.validation ? 'is-danger' : 'is-warning'">
                {{ review.validation ? (review.validation.valid ? '通过' : '未通过') : '未执行' }}
              </dd>
            </div>
            <div>
              <dt>KmAI 兼容性</dt>
              <dd :class="review.status === 'ready' ? 'is-success' : review.status === 'blocked' ? 'is-danger' : 'is-warning'">
                {{ compatibilityLabel }}
              </dd>
            </div>
          </dl>

          <section v-if="review.status === 'ready'" class="export-review__result is-success" aria-live="polite">
            <strong>审核通过</strong>
            <span>规则结构和 KmAI 兼容性检查均已通过，可以导出。</span>
          </section>

          <section v-else-if="review.status === 'blocked'" class="export-review__result is-danger" aria-live="polite">
            <strong>审核未通过</strong>
            <span>请处理以下问题后重新审核。</span>
            <ul v-if="reviewErrors.length">
              <li v-for="(message, index) in reviewErrors" :key="`${index}-${message}`">{{ message }}</li>
            </ul>
          </section>

          <template v-else>
            <section class="export-review__result is-warning" aria-live="polite">
              <strong>需要处理 {{ review.mappingIssues.length }} 项 KmAI 因子映射</strong>
              <span>完成以下映射并确认后，系统将重新检查规则包。</span>
            </section>

            <p v-if="loadError" class="export-review__error">{{ loadError }}</p>
            <div class="export-review__rows">
              <article
                v-for="(draft, index) in drafts"
                :key="`${draft.issue.field}\u0000${draft.issue.value}`"
                class="export-review__row"
              >
                <header class="export-review__source">
                  <strong>{{ draft.issue.field }}</strong>
                  <code>{{ draft.issue.value }}</code>
                  <span>影响 {{ draft.issue.occurrences }} 条规则</span>
                  <span>规则位置：{{ draft.issue.rule_refs.join('、') || '未提供' }}</span>
                </header>

                <fieldset class="export-review__fieldset">
                  <legend>作用范围</legend>
                  <label>
                    <input
                      type="radio"
                      :checked="draft.scope === 'project'"
                      :disabled="!projectId || submitting"
                      @change="setScope(index, 'project')"
                    >
                    当前项目
                  </label>
                  <label>
                    <input
                      type="radio"
                      :checked="draft.scope === 'global'"
                      :disabled="!allowGlobal || submitting"
                      @change="setScope(index, 'global')"
                    >
                    全局
                  </label>
                </fieldset>

                <fieldset class="export-review__fieldset">
                  <legend>处理方式</legend>
                  <label>
                    <input
                      type="radio"
                      :checked="isExistingFactor(index)"
                      :disabled="submitting"
                      @change="setMode(index, 'existing_factor')"
                    >
                    绑定已有因子
                  </label>
                  <label>
                    <input
                      type="radio"
                      :checked="!isExistingFactor(index)"
                      :disabled="submitting || draft.issue.can_create_manual_factor === false"
                      @change="setMode(index, 'manual_factor')"
                    >
                    创建手工布尔因子
                  </label>
                </fieldset>

                <template v-if="isExistingFactor(index)">
                  <input
                    class="export-review__control"
                    type="search"
                    :value="catalogSearch[index] || ''"
                    :disabled="submitting"
                    placeholder="搜索因子名称或键"
                    aria-label="搜索 KmAI 因子"
                    @input="setCatalogSearch(index, $event)"
                  >
                  <select
                    class="export-review__control"
                    :value="existingFactorKey(index)"
                    :disabled="submitting"
                    aria-label="选择目标因子"
                    @change="setExistingFactor(index, $event)"
                  >
                    <option value="" disabled>请选择目标因子</option>
                    <option v-for="factor in filteredCatalog(index)" :key="factor.factor_key" :value="factor.factor_key">
                      {{ factor.factor_name }}（{{ factor.factor_key }}）
                    </option>
                  </select>
                </template>
                <template v-else>
                  <label class="export-review__manual-label" :for="`manual-factor-${index}`">显示名称</label>
                  <input
                    :id="`manual-factor-${index}`"
                    class="export-review__control"
                    :value="manualDisplayName(index)"
                    :disabled="submitting"
                    placeholder="填写手工因子显示名称"
                    @input="setManualDisplayName(index, $event)"
                  >
                  <p class="export-review__warning">
                    该因子不会从 CAD 自动得出。KmAI 运行时必须通过
                    <code>manual.factor_overrides</code> 提供 <code>true/false</code>。
                  </p>
                </template>
              </article>
            </div>
          </template>
        </div>

        <p v-if="submitError" class="export-review__error">{{ submitError }}</p>
        <footer class="export-review__footer">
          <button type="button" :disabled="submitting" @click="cancel">取消</button>
          <button type="button" class="is-primary" :disabled="!canConfirm || submitting" @click="confirm">
            {{ submitting ? '正在保存映射...' : '确认导出' }}
          </button>
        </footer>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  createKmaiFactorMappingBatch,
  getKmaiFactorCatalog,
  previewKmaiFactorMappings,
  type KmaiFactorCatalogItem,
  type KmaiMappingMode,
  type KmaiMappingScope,
} from '@/api/kmaiFactorMappings'
import type { RulePackageExportReview } from '@/composables/useFinalizeRulePackageExport'
import {
  createKmaiMappingDrafts,
  filterBooleanKmaiFactorCatalog,
  toKmaiMappingBatchRequest,
  validateKmaiMappingDrafts,
  type KmaiMappingDraft,
} from '@/utils/kmaiFactorMappings'

const props = withDefaults(defineProps<{
  modelValue: boolean
  review: RulePackageExportReview | null
  projectId: number | null
  allowGlobal?: boolean
}>(), {
  allowGlobal: false,
})

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'confirmed'): void
  (event: 'cancelled'): void
}>()

const catalog = ref<KmaiFactorCatalogItem[]>([])
const selectableCatalog = computed(() => filterBooleanKmaiFactorCatalog(catalog.value))
const catalogSearch = ref<Record<number, string>>({})
const drafts = ref<KmaiMappingDraft[]>([])
const submitting = ref(false)
const loadError = ref('')
const submitError = ref('')

const validation = computed(() => validateKmaiMappingDrafts(drafts.value, { allowGlobal: props.allowGlobal }))
const canConfirm = computed(() => {
  if (!props.review || loadError.value) return false
  if (props.review.status === 'ready') return true
  if (props.review.status === 'blocked') return false
  return validation.value.canContinue
    && Boolean(props.projectId || props.allowGlobal)
    && Boolean(props.review.rulePackage)
})
const compatibilityLabel = computed(() => {
  if (!props.review) return '未检查'
  if (!props.review.kmaiCompatibility) return '未检查'
  if (props.review.status === 'ready') return '兼容'
  if (props.review.status === 'mapping_required') return `待处理 ${props.review.mappingIssues.length} 项`
  return '未通过'
})
const reviewErrors = computed(() => {
  if (!props.review) return []
  return [
    ...(props.review.details || []),
    ...(props.review.validation?.errors || []).map(issue => issue.message),
    ...(props.review.kmaiCompatibility?.errors || []).map(issue => issue.message),
  ].filter(Boolean)
})

watch(
  () => [props.modelValue, props.review] as const,
  async ([visible, review]) => {
    if (!visible) return
    catalogSearch.value = {}
    drafts.value = []
    submitError.value = ''
    loadError.value = ''
    if (!review || review.status !== 'mapping_required') return
    if (!props.projectId && !props.allowGlobal) {
      loadError.value = '缺少项目上下文，无法创建 KmAI 因子映射。'
      return
    }
    const scope: KmaiMappingScope = props.projectId ? 'project' : 'global'
    drafts.value = createKmaiMappingDrafts(review.mappingIssues, { scope, projectId: props.projectId })
    try {
      catalog.value = await getKmaiFactorCatalog()
      drafts.value.forEach((draft, index) => {
        const suggested = draft.issue.suggested_existing_factors?.find(key => (
          selectableCatalog.value.some(factor => factor.factor_key === key)
        ))
        if (suggested) setExistingFactorKey(index, suggested)
      })
    } catch (error: any) {
      loadError.value = apiErrorMessage(error, '读取 KmAI 因子目录失败，请重试。')
    }
  },
  { immediate: true },
)

function apiErrorMessage(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  return typeof detail === 'string' ? detail : detail?.message || error?.message || fallback
}

function updateDraft(index: number, update: (draft: KmaiMappingDraft) => KmaiMappingDraft) {
  const draft = drafts.value[index]
  if (!draft) return
  drafts.value[index] = update(draft)
}

function setScope(index: number, scope: KmaiMappingScope) {
  if (scope === 'project' && !props.projectId) return
  if (scope === 'global' && !props.allowGlobal) return
  updateDraft(index, draft => ({ ...draft, scope, projectId: scope === 'project' ? props.projectId : null }))
}

function setMode(index: number, mode: KmaiMappingMode) {
  if (mode === 'manual_factor' && drafts.value[index]?.issue.can_create_manual_factor === false) return
  updateDraft(index, draft => ({
    ...draft,
    resolution: mode === 'existing_factor'
      ? { mode, factorKey: existingFactorKey(index) }
      : { mode, displayName: manualDisplayName(index) || draft.issue.value },
  }))
}

function isExistingFactor(index: number) {
  return drafts.value[index]?.resolution?.mode !== 'manual_factor'
}

function existingFactorKey(index: number) {
  const resolution = drafts.value[index]?.resolution
  return resolution?.mode === 'existing_factor' ? resolution.factorKey : ''
}

function manualDisplayName(index: number) {
  const resolution = drafts.value[index]?.resolution
  return resolution?.mode === 'manual_factor' ? resolution.displayName : drafts.value[index]?.issue.value || ''
}

function setExistingFactorKey(index: number, factorKey: string) {
  updateDraft(index, draft => ({ ...draft, resolution: { mode: 'existing_factor', factorKey } }))
}

function setExistingFactor(index: number, event: Event) {
  setExistingFactorKey(index, (event.target as HTMLSelectElement).value)
}

function setManualDisplayName(index: number, event: Event) {
  const displayName = (event.target as HTMLInputElement).value
  updateDraft(index, draft => ({ ...draft, resolution: { mode: 'manual_factor', displayName } }))
}

function setCatalogSearch(index: number, event: Event) {
  catalogSearch.value[index] = (event.target as HTMLInputElement).value
}

function filteredCatalog(index: number) {
  const query = (catalogSearch.value[index] || '').trim().toLowerCase()
  if (!query) return selectableCatalog.value
  return selectableCatalog.value.filter(factor => (
    `${factor.factor_key} ${factor.factor_name}`.toLowerCase().includes(query)
  ))
}

async function confirm() {
  const review = props.review
  if (!review || !canConfirm.value || submitting.value) return
  if (review.status === 'ready') {
    emit('confirmed')
    emit('update:modelValue', false)
    return
  }
  if (review.status !== 'mapping_required' || !review.rulePackage) return

  submitting.value = true
  submitError.value = ''
  try {
    await createKmaiFactorMappingBatch(toKmaiMappingBatchRequest(drafts.value, { allowGlobal: props.allowGlobal }))
    const preview = await previewKmaiFactorMappings(props.projectId, review.rulePackage)
    if (!preview.valid) {
      submitError.value = '映射预览仍有未解决项，请调整后重试。'
      return
    }
    emit('confirmed')
    emit('update:modelValue', false)
  } catch (error: any) {
    submitError.value = apiErrorMessage(error, '保存 KmAI 因子映射失败，请重试。')
  } finally {
    submitting.value = false
  }
}

function cancel() {
  if (submitting.value) return
  emit('cancelled')
  emit('update:modelValue', false)
}
</script>

<style scoped>
.export-review-backdrop {
  position: fixed;
  z-index: 3000;
  inset: 0;
  display: grid;
  place-items: center;
  padding: 24px;
  background: rgba(15, 23, 42, .52);
}

.export-review {
  display: flex;
  width: min(820px, 100%);
  max-height: calc(100vh - 48px);
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 8px;
  background: #fff;
  box-shadow: 0 24px 64px rgba(15, 23, 42, .24);
  color: #334155;
}

.export-review__header,
.export-review__footer,
.export-review__source {
  display: flex;
  align-items: center;
}

.export-review__header {
  justify-content: space-between;
  gap: 16px;
  padding: 18px 22px;
  border-bottom: 1px solid #e2e8f0;
}

.export-review__header h2 { margin: 0; color: #0f172a; font-size: 18px; }
.export-review__header p { margin: 5px 0 0; color: #64748b; font-size: 13px; }
.export-review__close { width: 32px; height: 32px; border: 0; background: transparent; color: #64748b; cursor: pointer; font-size: 24px; line-height: 1; }
.export-review__close:disabled { cursor: wait; }
.export-review__body { display: grid; gap: 16px; min-height: 0; overflow: auto; padding: 18px 22px; background: #f8fafc; }

.export-review__summary {
  display: grid;
  grid-template-columns: minmax(150px, 1.5fr) repeat(4, minmax(100px, 1fr));
  gap: 1px;
  margin: 0;
  overflow: hidden;
  border: 1px solid #dbe3ee;
  border-radius: 7px;
  background: #dbe3ee;
}

.export-review__summary div { min-width: 0; padding: 10px 12px; background: #fff; }
.export-review__summary dt { color: #64748b; font-size: 11px; }
.export-review__summary dd { margin: 4px 0 0; overflow-wrap: anywhere; color: #0f172a; font-size: 13px; font-weight: 700; }
.export-review__summary .is-success { color: #15803d; }
.export-review__summary .is-warning { color: #b45309; }
.export-review__summary .is-danger { color: #b91c1c; }

.export-review__result { display: grid; gap: 5px; padding: 12px 14px; border-left: 3px solid; background: #fff; font-size: 13px; }
.export-review__result strong { color: #0f172a; font-size: 14px; }
.export-review__result span { color: #64748b; }
.export-review__result ul { margin: 6px 0 0; padding-left: 18px; color: #475569; }
.export-review__result.is-success { border-color: #22c55e; }
.export-review__result.is-warning { border-color: #f59e0b; }
.export-review__result.is-danger { border-color: #ef4444; }

.export-review__rows { display: grid; gap: 12px; }
.export-review__row { display: grid; gap: 11px; padding: 14px; border: 1px solid #dbe3ee; border-radius: 7px; background: #fff; }
.export-review__source { flex-wrap: wrap; gap: 8px; color: #64748b; font-size: 12px; }
.export-review__source strong { color: #1e293b; }
.export-review__source code { padding: 2px 6px; border-radius: 4px; background: #eef2ff; color: #4338ca; }
.export-review__fieldset { display: flex; gap: 14px; margin: 0; padding: 0; border: 0; color: #334155; font-size: 13px; }
.export-review__fieldset legend { width: 100%; margin-bottom: 5px; color: #64748b; font-size: 12px; font-weight: 700; }
.export-review__fieldset label { white-space: nowrap; }
.export-review__control { box-sizing: border-box; width: 100%; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px 10px; color: #0f172a; background: #fff; font: inherit; }
.export-review__control:focus { outline: 2px solid #c7d2fe; border-color: #818cf8; }
.export-review__manual-label { color: #475569; font-size: 12px; font-weight: 700; }
.export-review__warning { margin: 0; color: #b45309; font-size: 12px; line-height: 1.5; }
.export-review__error { margin: 0; padding: 10px 22px; color: #b91c1c; font-size: 13px; }

.export-review__footer { justify-content: flex-end; gap: 8px; padding: 14px 22px; border-top: 1px solid #e2e8f0; }
.export-review__footer button { min-width: 88px; padding: 8px 13px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #334155; cursor: pointer; }
.export-review__footer button.is-primary { border-color: #4f46e5; background: #4f46e5; color: #fff; }
.export-review__footer button:disabled { opacity: .5; cursor: not-allowed; }

@media (max-width: 760px) {
  .export-review-backdrop { padding: 10px; }
  .export-review { max-height: calc(100vh - 20px); }
  .export-review__summary { grid-template-columns: 1fr 1fr; }
  .export-review__summary div:first-child { grid-column: 1 / -1; }
  .export-review__fieldset { flex-wrap: wrap; }
}
</style>
