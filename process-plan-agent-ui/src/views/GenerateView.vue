<template>
  <div class="generate-view">
    <div class="analysis-style-header workflow-page-header">
      <div class="ash-left-content workflow-page-info">
        <span class="ash-page-title workflow-page-title">工艺路线验证</span>
        <template v-if="projectId">
          <span class="ash-dark-chip" :title="projectName || `任务 #${projectId}`">{{ projectName || `任务 #${projectId}` }}</span>
          
          <div class="ash-meta-section">
            <span class="ash-meta-item ash-meta-stale" v-if="isResultStale">
              规则已更新 <strong>V{{ packageVersion }}</strong>（当前生成结果为 V{{ result?.executable_revision }}）
            </span>
            <span class="ash-meta-item" v-else-if="displayedPackageVersion">
              可验证规则 <strong>V{{ displayedPackageVersion }}</strong>
            </span>
            <span class="ash-meta-item ash-meta-stale" v-else>
              可验证规则 <strong>未保存</strong>
            </span>
            <span class="ash-meta-item">
              已填写 <strong :class="{ 'text-done': filledFieldCount === activeInputFieldCount }">{{ filledFieldCount }}/{{ activeInputFieldCount }}</strong>
            </span>
          </div>
        </template>
      </div>
      <button v-if="projectId" class="btn btn-primary" :disabled="!canExportRules || exportingRules" @click="exportRulePackage">{{ exportingRules ? '正在导出…' : '导出规则包' }}</button>
    </div>

    <section v-if="!projectId" class="empty-panel">
      <span class="empty-step">05</span>
      <h2>先选择一个工艺规程任务</h2>
      <p>工艺路线验证使用第四步保存的当前规则。请从任务列表选择项目，完成规则定稿后再进入此处。</p>
      <button class="btn btn-primary empty-action" type="button" @click="goUpload">进入任务列表</button>
    </section>

    <div v-else class="generate-grid">
      <GenerateInputPanel
        :finalize-step-number="4"
        :project-id="projectId"
        :project-name="projectName"
        :input-fields="inputFields"
        :process-definitions="executableRevision?.package.route_catalog.processes || []"
        :filled-field-count="filledFieldCount"
        :input-field-count="activeInputFieldCount"
        :can-generate="canGenerate"
        :has-rule-package="hasRulePackage"
        :generating="generating"
        :schema-status-text="schemaStatusText"
        :generate-hint-text="generateHintText"
        :field-values="fieldValues"
        :field-value-origin="fieldValueOrigin"
        :custom-input-values="customInputValues"
        :is-confirmed-field-value="isConfirmedFieldValue"
        :is-invalid-confirmed-field-value="isInvalidConfirmedFieldValue"
        :field-type-label="fieldTypeLabel"
        :is-text-field="isTextField"
        :is-single-select-field="isSingleSelectField"
        :is-array-field="isArrayField"
        :is-boolean-field="isBooleanField"
        :is-number-field="isNumberField"
        :field-text-value="fieldTextValue"
        :field-placeholder="fieldPlaceholder"
        :input-value="inputValue"
        :array-field-values="arrayFieldValues"
        :set-field-text="setFieldText"
        :set-field-boolean="setFieldBoolean"
        :toggle-field-array-value="toggleFieldArrayValue"
        :set-custom-input="setCustomInput"
        :add-custom-array-value="addCustomArrayValue"
        :add-custom-single-value="addCustomSingleValue"
        :clear-all-fields="clearAllFields"
        :fill-example-values="fillExampleValues"
        @generate="runGenerate"
        @go-finalize="goFinalize"
      />

      <GenerateRouteOutputPanel
        :error="''"
        :result="result"
        :project-name="projectName"
        :input-field-count="activeInputFieldCount"
        :filled-field-count="filledFieldCount"
        :has-rule-package="hasRulePackage"
        :can-generate="canGenerate"
        :generating="generating"
        :is-stale="isResultStale"
        :current-package-version="packageVersion"
        @go-finalize="goFinalize"
        @fill-example="fillExampleValues"
      />
    </div>

    <WorkflowNavFooter
      :summary="generateNavSummary"
      :notices="generateNotices"
      previous-label="← 返回规则定稿"
      :next-label="templateMappingVisible ? '继续分组模板映射（可选）' : '已完成路线验证'"
      :previous-disabled="!projectId"
      :next-disabled="!canExportRules"
      :show-next="templateMappingVisible"
      @next="goTemplateMapping"
      @previous="goFinalize"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, onActivated, onDeactivated, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GenerateInputPanel from '@/components/generate/GenerateInputPanel.vue'
import GenerateRouteOutputPanel from '@/components/generate/GenerateRouteOutputPanel.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'
import {
  generateRoute,
  listProjects,
  type GenerateRouteResult,
} from '@/api'
import {
  buildProjectRouteQuery,
  resolveAvailableProjectId,
} from '@/composables/useCurrentProject'
import {
  fieldTypeLabel,
  isArrayField,
  isBooleanField,
  isNumberField,
  isSingleSelectField,
  isTextField,
  useGenerateInputFields,
} from '@/composables/useGenerateInputFields'
import {
  formatGenerateErrorDetail,
} from '@/utils/generateRouteOutput'
import { createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'
import { workflowResetSignal } from '@/composables/workflowResetState'
import { getLatestExecutableRuleRevision, getCurrentGenerationResults, exportExecutableRuleRevision, type ExecutableRuleRevision } from '@/api/executableRules'
import { downloadValidatedRulePackage } from '@/utils/validatedRulePackageDownload'
import { templateMappingVisible } from '@/composables/productStatus'

const route = useRoute()
const router = useRouter()
let generateViewActive = false
const contextLoading = ref(false)
const contextRequestGuard = createLatestWorkflowRequestGuard()
const generationRequestGuard = createLatestWorkflowRequestGuard()
let contextLoadRequestId = 0
let generationRequestId = 0

const projectId = ref<number | null>(null)
const projectName = ref('')
const inputSchema = ref<Record<string, any> | null>(null)
const rulePackageRules = ref<Record<string, any> | null>(null)
const hasRulePackage = ref(false)
const executableRevision = ref<ExecutableRuleRevision | null>(null)
const exportingRules = ref(false)
const inputsRequireRegeneration = ref(false)
const canExportRules = computed(() => Boolean(!contextLoading.value && !generating.value && !inputsRequireRegeneration.value && executableRevision.value?.generation_ready && (result.value?.executable_revision_id === executableRevision.value?.id && result.value?.executable_content_hash === executableRevision.value?.content_hash || executableRevision.value?.has_current_generation)))
const packageVersion = ref<number | null>(null)
const workflowRevision = ref(0)
const generating = ref(false)
const error = ref('')
const result = ref<GenerateRouteResult | null>(null)
const {
  addCustomArrayValue,
  addCustomSingleValue,
  activeInputFieldCount,
  arrayFieldValues,
  canGenerate,
  clearAllFields,
  customInputValues,
  factorValues,
  factorMetadata,
  fieldPlaceholder,
  fieldTextValue,
  fieldValues,
  fieldValueOrigin,
  filledFieldCount,
  fillExampleValues,
  initializeFieldValues,
  inputFields,
  inputValue,
  isConfirmedFieldValue,
  isInvalidConfirmedFieldValue,
  resetFieldValues,
  setCustomInput,
  setFieldBoolean,
  setFieldText,
  toggleFieldArrayValue,
} = useGenerateInputFields({
  inputSchema,
  rulePackageRules,
  hasRulePackage,
  projectId,
  schemaLoading: contextLoading,
})

watch(() => JSON.stringify([fieldValues.value, factorValues.value, factorMetadata.value]), () => {
  if (contextLoading.value) return
  inputsRequireRegeneration.value = true
  result.value = null
}, { flush: 'sync' })

const generationUsesRulePackage = computed(() => (
  Boolean(result.value?.executable_revision)
  && result.value?.output_mode === 'executable_rule_revision_v2'
))
const displayedPackageVersion = computed(() => (
  generationUsesRulePackage.value
    ? (result.value?.executable_revision ?? null)
    : packageVersion.value
))
const packageMetaLabel = computed(() => {
  if (!displayedPackageVersion.value) return '未保存'
  return `规则版本 ${displayedPackageVersion.value}`
})

const schemaStatusText = computed(() => {
  if (contextLoading.value) return '正在加载当前任务的输入参数…'
  if (!hasRulePackage.value) return `当前任务还没有可用规则包。请先在第四步保存当前规则。`
  if (canGenerate.value && !inputFields.value.length) return '当前规则包为固定路线，无需填写参数，可直接生成。'
  return `当前规则包的输入参数未能正确加载，请返回第四步检查当前规则。`
})

const isResultStale = computed(() => Boolean(result.value && (result.value.executable_revision_id !== executableRevision.value?.id || result.value.executable_content_hash !== executableRevision.value?.content_hash)))

const generateHintText = computed(() => {
  if (contextLoading.value) return '正在加载当前任务的输入参数，请稍候。'
  if (!hasRulePackage.value) return `请先在第四步保存当前规则。`
  if (!inputFields.value.length) return schemaStatusText.value
  return '请先补全必填输入参数。'
})
const generateNotices = computed<WorkflowNotice[]>(() => {
  if (error.value) return [{ id: 'generate-error', level: 'error', summary: '规则验证或路线生成未完成', detail: error.value, actions: [{ label: '返回规则定稿', run: goFinalize }] }]
  if (isResultStale.value) return [{ id: 'stale-result', level: 'warning', summary: '规则已更新，请重新生成路线', detail: `当前结果基于旧版 V${result.value?.executable_revision}，最新规则为 V${packageVersion.value}。`, actions: [{ label: '重新生成路线', run: runGenerate, disabled: !canGenerate.value || generating.value }] }]
  if (generating.value) return [{ id: 'generating', level: 'progress', summary: '正在生成工艺路线' }]
  if (inputsRequireRegeneration.value) return [{ id: 'changed-inputs', level: 'info', summary: '输入参数已修改，请重新生成路线', actions: [{ label: '重新生成路线', run: runGenerate, disabled: !canGenerate.value }] }]
  if (hasRulePackage.value && !canGenerate.value && inputFields.value.length) return [{ id: 'generate-input', level: 'info', summary: '请补齐并确认零件条件', detail: generateHintText.value, actions: filledFieldCount.value === 0 ? [{ label: '填入示例', run: fillExampleValues }] : [] }]
  return []
})

const generateNavSummary = computed(() => {
  if (!projectId.value) return '请先选择一个任务，完成规则定稿后再进入工艺路线验证。'
  if (!hasRulePackage.value) return '请返回第四步保存当前规则。'
  if (generating.value) return '正在生成工艺路线。'
  if (inputsRequireRegeneration.value) return '输入参数已修改，请重新生成并检查路线后再导出规则包。'
  if (isResultStale.value) return `检测到规则已更新至 V${packageVersion.value}，当前展示为旧版 V${result.value?.executable_revision} 结果，建议重新点击生成。`
  if (canExportRules.value) return templateMappingVisible.value
    ? '请检查路线结果；满意后可导出规则包，或继续可选的分组模板映射。'
    : '请检查路线结果；满意后可导出规则包。'
  if (canGenerate.value && !inputFields.value.length) return `规则包 ${packageMetaLabel.value} 已就绪，无需填写参数，可直接生成固定路线。`
  return `规则包 ${packageMetaLabel.value} 已就绪，输入字段已填写 ${filledFieldCount.value}/${activeInputFieldCount.value}。`
})

function goFinalize() {
  router.push({
    path: '/finalize',
    query: buildProjectRouteQuery(projectId.value),
  })
}

function goUpload() {
  router.push('/upload')
}

function resetRulePackageMetadata() {
  executableRevision.value = null
  packageVersion.value = null
  rulePackageRules.value = null
  workflowRevision.value = 0
}

function applyRulePackageMetadata(rulePackage: ExecutableRuleRevision) {
  executableRevision.value = rulePackage
  packageVersion.value = rulePackage.revision ?? null
  rulePackageRules.value = rulePackage.package.route_rules ?? null
}

function clearGeneratedWorkflowState() {
  inputSchema.value = null
  hasRulePackage.value = false
  result.value = null
  error.value = ''
  generating.value = false
  resetRulePackageMetadata()
  resetFieldValues()
}

async function refreshGeneratedPackageMetadata(
  generatedResult: GenerateRouteResult, generatedProjectId: number, requestId: number, isLatest: () => boolean,
) {
  const latest = await getLatestExecutableRuleRevision(generatedProjectId)
  if (!isLatest() || requestId !== generationRequestId || projectId.value !== generatedProjectId) return
  if (!latest?.generation_ready) { clearRulePackageContext(); result.value = null; return }
  if (latest.id !== generatedResult.executable_revision_id || latest.content_hash !== generatedResult.executable_content_hash) {
    result.value = null
    inputSchema.value = latest.package.input_schema
    initializeFieldValues()
  }
  applyRulePackageMetadata(latest)
}

function goTemplateMapping() {
  if (canExportRules.value && templateMappingVisible.value) router.push({ path: '/template-mapping', query: buildProjectRouteQuery(projectId.value) })
}

async function exportRulePackage() {
  if (!canExportRules.value || !executableRevision.value || !projectId.value || exportingRules.value) return
  const revision = executableRevision.value, id = projectId.value, context = contextLoadRequestId
  const isCurrent = () => projectId.value === id && executableRevision.value?.id === revision.id && contextLoadRequestId === context && !inputsRequireRegeneration.value
  exportingRules.value = true
  error.value = ''
  try {
    const saved = await exportExecutableRuleRevision(revision.id, {
      project_id: id, expected_workflow_revision: workflowRevision.value,
      expected_content_hash: revision.content_hash, include_template_mapping: false,
    })
    if (!isCurrent()) return
    await downloadValidatedRulePackage(saved, projectName.value, { isCurrent })
  } catch (e: any) {
    if (projectId.value === id && contextLoadRequestId === context) error.value = formatGenerateErrorDetail(e?.response?.data?.detail || e?.message)
  } finally { exportingRules.value = false }
}

async function runGenerate() {
  if (!projectId.value || !executableRevision.value?.generation_ready || contextLoading.value || generating.value || !canGenerate.value) return
  const request = generationRequestGuard.start()
  const generatedProjectId = projectId.value
  const loadedContextRequestId = contextLoadRequestId
  const requestId = ++generationRequestId
  const requestedInputs = JSON.stringify({ factor_values: factorValues.value, input_metadata: factorMetadata.value })
  const requestedFields = JSON.stringify(fieldValues.value)
  generating.value = true
  error.value = ''
  try {
    const generatedResult = await generateRoute({
      project_id: generatedProjectId,
      executable_revision_id: executableRevision.value.id,
      expected_workflow_revision: workflowRevision.value,
      ...JSON.parse(requestedInputs),
    })
    if (
      !request.isLatest()
      || requestId !== generationRequestId
      || loadedContextRequestId !== contextLoadRequestId
      || projectId.value !== generatedProjectId
    ) return
    if (requestedFields !== JSON.stringify(fieldValues.value) || requestedInputs !== JSON.stringify({ factor_values: factorValues.value, input_metadata: factorMetadata.value })) return
    result.value = generatedResult
    inputsRequireRegeneration.value = false
    await refreshGeneratedPackageMetadata(
      generatedResult, generatedProjectId, requestId,
      () => request.isLatest() && loadedContextRequestId === contextLoadRequestId,
    )
  } catch (err: any) {
    if (
      !request.isLatest()
      || requestId !== generationRequestId
      || loadedContextRequestId !== contextLoadRequestId
      || projectId.value !== generatedProjectId
    ) return
    if (requestedFields !== JSON.stringify(fieldValues.value) || requestedInputs !== JSON.stringify({ factor_values: factorValues.value, input_metadata: factorMetadata.value })) return
    console.error(err)
    const fieldLabels = Object.fromEntries(
      inputFields.value.map(field => [field.key, field.name || field.key]),
    )
    error.value = formatGenerateErrorDetail(
      err?.response?.data?.detail ?? err?.message,
      fieldLabels,
    )
  } finally {
    if (request.isLatest() && requestId === generationRequestId) generating.value = false
  }
}

function clearRulePackageContext() {
  result.value = null
  inputSchema.value = null
  hasRulePackage.value = false
  resetRulePackageMetadata()
  resetFieldValues()
}

function canonicalInputSnapshot(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(canonicalInputSnapshot)
  if (value && typeof value === 'object') {
    return Object.fromEntries(Object.entries(value as Record<string, unknown>)
      .sort(([left], [right]) => left.localeCompare(right))
      .map(([key, item]) => [key, canonicalInputSnapshot(item)]))
  }
  return value
}

function generationInputSnapshot(factorValuesValue: unknown, metadataValue: unknown): string {
  const normalizedMetadata = Object.fromEntries(Object.entries((metadataValue || {}) as Record<string, any>)
    .map(([key, value]) => [key, {
      origin: value?.origin,
      unit: value?.unit ?? null,
      evidence: Array.isArray(value?.evidence) ? value.evidence : [],
    }]))
  return JSON.stringify(canonicalInputSnapshot({
    factor_values: factorValuesValue || {},
    input_metadata: normalizedMetadata,
  }))
}

function setLoadingProject(nextProjectId: number | null) {
  if (projectId.value === nextProjectId) return false
  generationRequestGuard.start()
  generationRequestId += 1
  generating.value = false
  result.value = null
  inputsRequireRegeneration.value = false
  error.value = ''
  projectId.value = nextProjectId
  projectName.value = nextProjectId ? `任务 #${nextProjectId}` : ''
  clearRulePackageContext()
  return true
}

async function loadGenerateContext(retryInvalidated = true) {
  const request = contextRequestGuard.start()
  const requestId = ++contextLoadRequestId
  const requestedProjectId = String(route.query.project_id || '')
  const hintedProjectId = Number(requestedProjectId)
  contextLoading.value = true
  error.value = ''
  if (Number.isInteger(hintedProjectId) && hintedProjectId > 0) {
    setLoadingProject(hintedProjectId)
  }
  let inputsAtLoad = JSON.stringify([fieldValues.value, factorValues.value, factorMetadata.value])
  try {
    const projects = await listProjects()
    if (
      !request.isCurrent()
      || requestId !== contextLoadRequestId
      || String(route.query.project_id || '') !== requestedProjectId
    ) return
    const resolvedProjectId = resolveAvailableProjectId(requestedProjectId, projects)
    if (!resolvedProjectId) {
      setLoadingProject(null)
      clearRulePackageContext()
      return
    }
    const targetProjectId = Number(resolvedProjectId)
    if (setLoadingProject(targetProjectId)) inputsAtLoad = JSON.stringify([fieldValues.value, factorValues.value, factorMetadata.value])
    if (requestedProjectId !== resolvedProjectId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: resolvedProjectId },
      })
    }
    const currentProject = projects.find(project => project.id === targetProjectId)
    projectName.value = currentProject?.name || `任务 #${targetProjectId}`
    workflowRevision.value = currentProject?.workflow_revision || 0
    const latestPackage = await getLatestExecutableRuleRevision(targetProjectId).catch((err) => {
      if (err?.response?.status === 404) return null
      throw err
    })
    const currentRouteProjectId = String(route.query.project_id || '')
    if (
      !request.isCurrent()
      || requestId !== contextLoadRequestId
      || projectId.value !== targetProjectId
      || (currentRouteProjectId !== requestedProjectId && currentRouteProjectId !== resolvedProjectId)
    ) return
    if (inputsAtLoad !== JSON.stringify([fieldValues.value, factorValues.value, factorMetadata.value])) {
      inputsRequireRegeneration.value = true
      result.value = null
    }
    if (latestPackage?.generation_ready && latestPackage.package?.input_schema) {
      if (executableRevision.value?.id !== latestPackage.id || executableRevision.value?.content_hash !== latestPackage.content_hash) result.value = null
      inputSchema.value = latestPackage.package.input_schema
      hasRulePackage.value = true
      applyRulePackageMetadata(latestPackage)
      initializeFieldValues()
      if (latestPackage.has_current_generation && !inputsRequireRegeneration.value) {
        const restoringInputs = generationInputSnapshot(factorValues.value, factorMetadata.value)
        const generated = await getCurrentGenerationResults(targetProjectId)
        if (!request.isCurrent() || requestId !== contextLoadRequestId || projectId.value !== targetProjectId) return
        const historical = generated.results[0]
        const historicalInputs = historical?.input_factors
        const historicalSnapshot = historicalInputs && typeof historicalInputs === 'object'
          ? generationInputSnapshot(historicalInputs.factor_values, historicalInputs.input_metadata)
          : null
        if (!historical || historicalSnapshot === null || restoringInputs !== historicalSnapshot) {
          inputsRequireRegeneration.value = true
          result.value = null
        } else result.value = generated.executable_revision_id === latestPackage.id ? historical : null
      }
    } else {
      clearRulePackageContext()
    }
  } catch (err: any) {
    if (!request.isCurrent() || requestId !== contextLoadRequestId) return
    console.warn('读取生成上下文失败', err)
    clearRulePackageContext()
    error.value = formatGenerateErrorDetail(err?.response?.data?.detail ?? err?.message)
  } finally {
    if (request.isLatest() && requestId === contextLoadRequestId) {
      if (!request.isCurrent() && generateViewActive) {
        if (retryInvalidated) {
          await loadGenerateContext(false)
          return
        }
        clearRulePackageContext()
        error.value = '规则包在加载期间再次更新，请重新进入本页刷新后再生成。'
      }
      contextLoading.value = false
    }
  }
}

onMounted(() => { void loadGenerateContext() })

watch(() => route.query.project_id, () => {
  if (!generateViewActive) return
  generationRequestGuard.start()
  generating.value = false
  result.value = null
  error.value = ''
  void loadGenerateContext()
})

watch(workflowResetSignal, (signal) => {
  if (!signal || signal.projectId !== projectId.value) return
  generationRequestGuard.start()
  clearGeneratedWorkflowState()
  void loadGenerateContext()
})

onActivated(() => {
  generateViewActive = true
  const routeProjectId = Number(route.query.project_id || 0)
  const projectChanged = routeProjectId > 0 && routeProjectId !== projectId.value
  if (contextLoading.value && !projectChanged) return
  // Always reach the API cache so its TTL can detect publication in another window.
  void loadGenerateContext()
})

onDeactivated(() => {
  generateViewActive = false
  contextRequestGuard.start()
  contextLoadRequestId += 1
  contextLoading.value = false
})
</script>

<style scoped>
.generate-view {
  --generate-ink: #0f172a;
  --generate-muted: #64748b;
  --generate-line: #e2e8f0;
  --generate-surface: #ffffff;
  --generate-panel: #f8fafc;
  --generate-accent: #4f46e5;
  --generate-accent-soft: #eef2ff;
  display: flex;
  flex-direction: column;
  height: 100%;
  min-height: 0;
  overflow: hidden;
  color: var(--generate-ink);
}

.analysis-style-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 14px;
  background: #ffffff;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  margin-bottom: 10px;
}
.ash-left-content { display: flex; align-items: center; gap: 10px; }
.ash-page-title { font-size: 15px; font-weight: 700; color: #0f172a; }
.ash-dark-chip {
  background: #0f172a; color: #f1f5f9;
  padding: 2px 8px; border-radius: 5px; font-size: 12px; font-weight: 700;
}
.ash-meta-section {
  display: flex; align-items: center; gap: 12px;
  margin-left: 8px; padding-left: 12px; border-left: 1px solid #e2e8f0;
}
.ash-meta-item { font-size: 12px; color: #64748b; }
.ash-meta-item strong { color: #0f172a; font-weight: 700; }
.ash-meta-stale { color: #d97706; }
.text-done { color: #16a34a !important; }

.generate-meta-item {
  font-size: 12.5px;
  color: var(--generate-muted);
  display: flex;
  align-items: center;
  gap: 4px;
  white-space: nowrap;
}

.generate-meta-item strong {
  color: #0f172a;
  font-weight: 700;
}

.generate-meta-item strong:not(.pending) {
  color: #4f46e5;
}

.generate-meta-item strong.pending {
  color: #d97706;
}

.rule-package-meta {
  gap: 5px;
}

.package-status-badge {
  display: inline-flex;
  align-items: center;
  min-height: 18px;
  padding: 1px 5px;
  border: 1px solid #a7f3d0;
  border-radius: 4px;
  background: #ecfdf5;
  color: #047857;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

.package-details {
  position: relative;
  display: inline-flex;
}

.package-details-trigger {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 18px;
  height: 18px;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  list-style: none;
  transition: color 0.15s ease, background 0.15s ease;
}

.package-details-trigger::-webkit-details-marker {
  display: none;
}

.package-details-trigger svg {
  width: 14px;
  height: 14px;
}

.package-details-trigger:hover,
.package-details[open] .package-details-trigger {
  background: #eef2ff;
  color: #4f46e5;
}

.package-details-trigger:focus-visible {
  outline: 2px solid rgba(79, 70, 229, 0.35);
  outline-offset: 2px;
}

.package-details-popover {
  position: absolute;
  z-index: 30;
  top: calc(100% + 10px);
  left: 50%;
  width: min(320px, calc(100vw - 32px));
  padding: 12px 14px;
  border: 1px solid #dbe3ee;
  border-radius: 7px;
  background: #ffffff;
  box-shadow: 0 14px 32px rgba(15, 23, 42, 0.16);
  color: #334155;
  transform: translateX(-50%);
}

.package-details-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding-bottom: 8px;
  border-bottom: 1px solid #e2e8f0;
}

.package-details-head strong {
  color: #0f172a;
  font-size: 12px;
  font-weight: 750;
}

.package-details-head span {
  color: #047857;
  font-size: 10px;
  font-weight: 700;
}

.package-detail-list {
  display: grid;
  gap: 7px;
  margin: 9px 0 0;
}

.package-detail-list > div {
  display: grid;
  grid-template-columns: 64px minmax(0, 1fr);
  gap: 10px;
  align-items: start;
}

.package-detail-list dt,
.package-detail-list dd {
  margin: 0;
  font-size: 11px;
  line-height: 1.45;
}

.package-detail-list dt {
  color: #94a3b8;
}

.package-detail-list dd {
  overflow-wrap: anywhere;
  color: #334155;
  font-weight: 600;
}

.package-detail-list code {
  display: block;
  max-width: 100%;
  color: #475569;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 10px;
  font-weight: 500;
  overflow-wrap: anywhere;
  white-space: normal;
  word-break: break-all;
}

.package-hash-row dd {
  min-width: 0;
}

.package-result-note {
  margin: 9px 0 0;
  padding-top: 8px;
  border-top: 1px solid #e2e8f0;
  color: #047857;
  font-size: 10.5px;
  font-weight: 650;
}

.sr-only {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
  border: 0;
}

.generate-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  align-items: stretch;
  flex: 1;
  min-height: 0;
  height: auto;
}

.empty-panel {
  min-height: 380px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 34px;
  text-align: center;
  border: 1px solid var(--generate-line);
  border-radius: 14px;
  background: #ffffff;
  box-shadow: var(--shadow-sm);
}

.empty-step {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 46px;
  height: 46px;
  margin-bottom: 16px;
  border-radius: 12px;
  background: linear-gradient(135deg, #6366f1, #818cf8);
  color: #ffffff;
  font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
  font-size: 14px;
  font-weight: 800;
}

.empty-panel h2 {
  margin: 0;
  font-size: 18px;
  font-weight: 750;
}

.empty-panel p {
  max-width: 430px;
  margin: 8px 0 18px;
  color: var(--generate-muted);
  font-size: 13px;
  line-height: 1.65;
}

.empty-action {
  background: #4f46e5;
}

@media (max-width: 900px) {
  .generate-view {
    height: auto;
    min-height: 100%;
    overflow: visible;
  }

  .generate-header-card {
    flex-direction: column;
    align-items: stretch;
    gap: 12px;
    padding: 12px;
  }

  .gh-left-content {
    flex-wrap: wrap;
    gap: 8px 12px;
  }

  .gh-meta-section {
    margin-left: 0;
    border-left: none;
    padding-left: 0;
    width: 100%;
    flex-wrap: wrap;
    gap: 6px 12px;
  }

  .package-details-popover {
    left: 0;
    transform: none;
  }

  .generate-grid {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>
