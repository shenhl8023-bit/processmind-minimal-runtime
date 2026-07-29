<template>
  <Teleport to="body">
    <div v-if="modelValue" class="kmai-dialog-backdrop" @click.self="cancel">
      <section class="kmai-dialog" role="dialog" aria-modal="true" aria-labelledby="kmai-mapping-title">
        <header class="kmai-dialog__header">
          <div>
            <h2 id="kmai-mapping-title">Resolve KmAI factor mappings</h2>
            <p>Choose an existing factor or create a manual boolean factor for each source value.</p>
          </div>
          <button type="button" class="kmai-dialog__close" :disabled="submitting" @click="cancel">Close</button>
        </header>

        <p v-if="loadError" class="kmai-dialog__error">{{ loadError }}</p>
        <div class="kmai-dialog__rows">
          <article v-for="(draft, index) in drafts" :key="`${draft.issue.field}\u0000${draft.issue.value}`" class="kmai-dialog__row">
            <header class="kmai-dialog__source">
              <strong>{{ draft.issue.field }}</strong>
              <code>{{ draft.issue.value }}</code>
              <span>{{ draft.issue.occurrences }} occurrence{{ draft.issue.occurrences === 1 ? '' : 's' }}</span>
              <span>Rules: {{ draft.issue.rule_refs.join(', ') }}</span>
            </header>

            <fieldset class="kmai-dialog__fieldset">
              <legend>Scope</legend>
              <label>
                <input
                  type="radio"
                  :checked="draft.scope === 'project'"
                  :disabled="!projectId || submitting"
                  @change="setScope(index, 'project')"
                > Project
              </label>
              <label>
                <input
                  type="radio"
                  :checked="draft.scope === 'global'"
                  :disabled="!allowGlobal || submitting"
                  @change="setScope(index, 'global')"
                > Global
              </label>
            </fieldset>

            <fieldset class="kmai-dialog__fieldset">
              <legend>Resolution</legend>
              <label>
                <input
                  type="radio"
                  :checked="isExistingFactor(index)"
                  :disabled="submitting"
                  @change="setMode(index, 'existing_factor')"
                > Bind an existing factor
              </label>
              <label>
                <input
                  type="radio"
                  :checked="!isExistingFactor(index)"
                  :disabled="submitting || draft.issue.can_create_manual_factor === false"
                  @change="setMode(index, 'manual_factor')"
                > Create a manual boolean factor
              </label>
            </fieldset>

            <template v-if="isExistingFactor(index)">
              <input
                class="kmai-dialog__control"
                type="search"
                :value="catalogSearch[index] || ''"
                :disabled="submitting"
                placeholder="Search factor catalog"
                @input="setCatalogSearch(index, $event)"
              >
              <select
                class="kmai-dialog__control"
                :value="existingFactorKey(index)"
                :disabled="submitting"
                @change="setExistingFactor(index, $event)"
              >
                <option value="" disabled>Select a factor</option>
                <option v-for="factor in filteredCatalog(index)" :key="factor.factor_key" :value="factor.factor_key">
                  {{ factor.factor_name }} ({{ factor.factor_key }})
                </option>
              </select>
            </template>
            <template v-else>
              <label class="kmai-dialog__manual-label" :for="`manual-factor-${index}`">Display name</label>
              <input
                :id="`manual-factor-${index}`"
                class="kmai-dialog__control"
                :value="manualDisplayName(index)"
                :disabled="submitting"
                placeholder="Manual factor display name"
                @input="setManualDisplayName(index, $event)"
              >
              <p class="kmai-dialog__warning">This creates a server-generated boolean factor. KmAI must provide true/false through <code>manual.factor_overrides</code>.</p>
            </template>
          </article>
        </div>

        <footer class="kmai-dialog__footer">
          <p v-if="submitError" class="kmai-dialog__error">{{ submitError }}</p>
          <div class="kmai-dialog__actions">
            <button type="button" :disabled="submitting" @click="cancel">Cancel</button>
            <button type="button" :disabled="!canResolve || submitting" @click="resolve">
              {{ submitting ? 'Saving…' : 'Save mappings and continue' }}
            </button>
          </div>
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
  type KmaiMappingIssue,
  type KmaiMappingMode,
  type KmaiMappingScope,
} from '@/api/kmaiFactorMappings'
import type { RulePackageV2 } from '@/api/rulePackages'
import {
  createKmaiMappingDrafts,
  filterBooleanKmaiFactorCatalog,
  toKmaiMappingBatchRequest,
  validateKmaiMappingDrafts,
  type KmaiMappingDraft,
} from '@/utils/kmaiFactorMappings'

const props = withDefaults(defineProps<{
  modelValue: boolean
  issues: KmaiMappingIssue[]
  projectId: number | null
  rulePackage: RulePackageV2 | null
  allowGlobal?: boolean
}>(), {
  allowGlobal: false,
})

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'resolved'): void
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
const canResolve = computed(() => (
  validation.value.canContinue
  && Boolean(props.projectId || props.allowGlobal)
  && Boolean(props.rulePackage)
  && !loadError.value
))

watch(() => props.modelValue, async (visible) => {
  if (!visible) return
  catalogSearch.value = {}
  submitError.value = ''
  loadError.value = ''
  if (!props.projectId && !props.allowGlobal) {
    drafts.value = []
    loadError.value = 'Global mappings are not available without project context.'
    return
  }
  const scope: KmaiMappingScope = props.projectId ? 'project' : 'global'
  drafts.value = createKmaiMappingDrafts(props.issues, { scope, projectId: props.projectId })
  try {
    catalog.value = await getKmaiFactorCatalog()
    drafts.value.forEach((draft, index) => {
      const suggested = draft.issue.suggested_existing_factors?.find(key => (
        selectableCatalog.value.some(factor => factor.factor_key === key)
      ))
      if (suggested) setExistingFactorKey(index, suggested)
    })
  } catch (error: any) {
    loadError.value = error?.message || 'Unable to load the KmAI factor catalog.'
  }
}, { immediate: true })

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
  return selectableCatalog.value.filter(factor => `${factor.factor_key} ${factor.factor_name}`.toLowerCase().includes(query))
}

async function resolve() {
  if (!canResolve.value || submitting.value || !props.rulePackage || (!props.projectId && !props.allowGlobal)) return
  submitting.value = true
  submitError.value = ''
  try {
    await createKmaiFactorMappingBatch(toKmaiMappingBatchRequest(drafts.value, { allowGlobal: props.allowGlobal }))
    const preview = await previewKmaiFactorMappings(props.projectId, props.rulePackage)
    if (!preview.valid) {
      submitError.value = 'The mapping preview still has unresolved values. Update the selections and try again.'
      return
    }
    emit('resolved')
    emit('update:modelValue', false)
  } catch (error: any) {
    const detail = error?.response?.data?.detail
    submitError.value = typeof detail === 'string' ? detail : detail?.message || error?.message || 'Unable to save mappings.'
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
.kmai-dialog-backdrop { position: fixed; z-index: 3000; inset: 0; display: grid; place-items: center; padding: 24px; background: rgba(15, 23, 42, .52); }
.kmai-dialog { display: flex; width: min(780px, 100%); max-height: calc(100vh - 48px); flex-direction: column; overflow: hidden; border: 1px solid #dbe3ee; border-radius: 10px; background: #fff; box-shadow: 0 24px 64px rgba(15, 23, 42, .24); }
.kmai-dialog__header, .kmai-dialog__footer, .kmai-dialog__actions, .kmai-dialog__source { display: flex; align-items: center; }
.kmai-dialog__header { justify-content: space-between; gap: 16px; padding: 18px 22px; border-bottom: 1px solid #e2e8f0; }
.kmai-dialog__header h2 { margin: 0; color: #0f172a; font-size: 18px; }.kmai-dialog__header p { margin: 5px 0 0; color: #64748b; font-size: 13px; }
.kmai-dialog__close { border: 0; background: transparent; color: #64748b; cursor: pointer; }.kmai-dialog__close:disabled { cursor: wait; }
.kmai-dialog__rows { display: grid; gap: 12px; overflow: auto; padding: 18px 22px; background: #f8fafc; }
.kmai-dialog__row { display: grid; gap: 11px; padding: 14px; border: 1px solid #dbe3ee; border-radius: 8px; background: #fff; }
.kmai-dialog__source { flex-wrap: wrap; gap: 8px; color: #64748b; font-size: 12px; }.kmai-dialog__source strong { color: #1e293b; }.kmai-dialog__source code { padding: 2px 6px; border-radius: 4px; background: #eef2ff; color: #4338ca; }
.kmai-dialog__fieldset { display: flex; gap: 14px; margin: 0; padding: 0; border: 0; color: #334155; font-size: 13px; }.kmai-dialog__fieldset legend { width: 100%; margin-bottom: 5px; color: #64748b; font-size: 12px; font-weight: 700; }.kmai-dialog__fieldset label { white-space: nowrap; }
.kmai-dialog__control { width: 100%; box-sizing: border-box; border: 1px solid #cbd5e1; border-radius: 6px; padding: 8px 10px; color: #0f172a; background: #fff; }.kmai-dialog__control:focus { outline: 2px solid #c7d2fe; border-color: #818cf8; }
.kmai-dialog__manual-label { color: #475569; font-size: 12px; font-weight: 700; }.kmai-dialog__warning { margin: 0; color: #b45309; font-size: 12px; line-height: 1.5; }
.kmai-dialog__footer { justify-content: space-between; gap: 14px; padding: 14px 22px; border-top: 1px solid #e2e8f0; }.kmai-dialog__actions { justify-content: flex-end; gap: 8px; margin-left: auto; }.kmai-dialog__actions button { padding: 8px 13px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #334155; cursor: pointer; }.kmai-dialog__actions button:last-child { border-color: #4f46e5; background: #4f46e5; color: #fff; }.kmai-dialog__actions button:disabled { opacity: .5; cursor: not-allowed; }
.kmai-dialog__error { margin: 0; padding: 10px 22px; color: #b91c1c; font-size: 13px; }
@media (max-width: 640px) { .kmai-dialog-backdrop { padding: 10px; }.kmai-dialog { max-height: calc(100vh - 20px); }.kmai-dialog__header, .kmai-dialog__footer { align-items: flex-start; flex-direction: column; }.kmai-dialog__actions { margin-left: 0; }.kmai-dialog__fieldset { flex-wrap: wrap; } }
</style>
