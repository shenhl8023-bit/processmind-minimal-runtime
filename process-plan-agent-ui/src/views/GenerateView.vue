<template>
  <div class="generate-view">
    <div class="generate-header-card">
      <div class="gh-left-content">
        <span class="gh-page-title">路线生成</span>
        <template v-if="projectId">
          <span class="generate-project-chip">{{ projectName || `任务 #${projectId}` }}</span>
          
          <div class="gh-meta-section">
            <span class="generate-meta-item">规则包 <strong :class="{ pending: !hasRulePackage }">{{ hasRulePackage ? packageMetaLabel : '待导出' }}</strong></span>
            <span class="generate-meta-item">契约 <strong>{{ packageSchemaVersion || '-' }}</strong></span>
            <span class="generate-meta-item">输入字段 <strong>{{ inputFields.length }}</strong></span>
            <span class="generate-meta-item">已填写 <strong>{{ filledFieldCount }}/{{ inputFields.length }}</strong></span>
          </div>
        </template>
      </div>
    </div>

    <section v-if="!projectId" class="empty-panel">
      <span class="empty-step">05</span>
      <h2>先选择一个工艺规程任务</h2>
      <p>路线生成依赖已经定稿的规则包。请从任务列表选择项目，完成规则定稿后再进入此处。</p>
      <button class="btn btn-primary empty-action" type="button" @click="goUpload">进入任务列表</button>
    </section>

    <div v-else class="generate-grid">
      <GenerateInputPanel
        :project-id="projectId"
        :project-name="projectName"
        :input-fields="inputFields"
        :filled-field-count="filledFieldCount"
        :can-generate="canGenerate"
        :has-rule-package="hasRulePackage"
        :generating="generating"
        :schema-status-text="schemaStatusText"
        :generate-hint-text="generateHintText"
        :field-values="fieldValues"
        :custom-input-values="customInputValues"
        :field-type-label="fieldTypeLabel"
        :is-text-field="isTextField"
        :is-single-select-field="isSingleSelectField"
        :is-array-field="isArrayField"
        :is-boolean-field="isBooleanField"
        :is-number-field="isNumberField"
        :field-text-value="fieldTextValue"
        :field-placeholder="fieldPlaceholder"
        :field-preview-value="fieldPreviewValue"
        :input-value="inputValue"
        :checked-value="checkedValue"
        :array-field-values="arrayFieldValues"
        :set-field-text="setFieldText"
        :set-field-boolean="setFieldBoolean"
        :toggle-field-array-value="toggleFieldArrayValue"
        :set-custom-input="setCustomInput"
        :add-custom-array-value="addCustomArrayValue"
        :clear-all-fields="clearAllFields"
        :fill-example-values="fillExampleValues"
        @generate="runGenerate"
        @go-finalize="goFinalize"
      />

      <GenerateRouteOutputPanel
        :error="error"
        :result="result"
        :project-name="projectName"
        :input-field-count="inputFields.length"
        :filled-field-count="filledFieldCount"
        :has-rule-package="hasRulePackage"
        :can-generate="canGenerate"
        :generating="generating"
        @download="downloadOutputJson"
      />
    </div>

    <WorkflowNavFooter
      :summary="generateNavSummary"
      previous-label="← 返回规则定稿"
      next-label="已是最后一步"
      :previous-disabled="!projectId"
      next-disabled
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
import {
  generateRoute,
  getLatestFinalizedRulePackage,
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
  downloadGeneratedRouteJson,
} from '@/utils/generateRouteOutput'
import { getWorkflowDataRevision } from '@/composables/workflowDataCache'

const route = useRoute()
const router = useRouter()
let generateViewActive = false
let contextLoading = false
let initialLoadFinished = false
let loadedDataRevision = -1

const projectId = ref<number | null>(null)
const projectName = ref('')
const inputSchema = ref<Record<string, any> | null>(null)
const hasRulePackage = ref(false)
const packageSchemaVersion = ref('')
const packageVersion = ref<number | null>(null)
const packageHash = ref('')
const generating = ref(false)
const error = ref('')
const result = ref<GenerateRouteResult | null>(null)
const {
  addCustomArrayValue,
  arrayFieldValues,
  canGenerate,
  checkedValue,
  clearAllFields,
  customInputValues,
  factorValues,
  fieldPlaceholder,
  fieldPreviewValue,
  fieldTextValue,
  fieldValues,
  filledFieldCount,
  fillExampleValues,
  initializeFieldValues,
  inputFields,
  inputValue,
  resetFieldValues,
  setCustomInput,
  setFieldBoolean,
  setFieldText,
  toggleFieldArrayValue,
} = useGenerateInputFields({
  inputSchema,
  hasRulePackage,
  projectId,
})

const packageMetaLabel = computed(() => {
  if (!hasRulePackage.value) return '待导出'
  const versionText = packageVersion.value ? `V${packageVersion.value}` : '已导出'
  const hashText = packageHash.value ? ` · ${packageHash.value.slice(0, 8)}` : ''
  return `${versionText}${hashText}`
})

const schemaStatusText = computed(() => {
  if (!hasRulePackage.value) return '当前任务还没有可用规则包。请先在第4步导出规则包。'
  return '当前规则包没有定义输入参数，请返回第4步重新导出规则包。'
})

const generateHintText = computed(() => {
  if (!hasRulePackage.value) return '请先在第4步导出规则包。'
  if (!inputFields.value.length) return '当前规则包没有定义输入参数。'
  return '请先补全必填输入参数。'
})
const generateNavSummary = computed(() => {
  if (!projectId.value) return '请先选择一个任务，完成规则定稿后再进入路线生成。'
  if (!hasRulePackage.value) return '当前任务还没有可用规则包，请返回第四步导出规则包。'
  if (generating.value) return '正在生成工艺路线。'
  if (result.value) return '路线已生成，可在右侧查看结果或导出 JSON。'
  return `规则包 ${packageMetaLabel.value} 已就绪，输入字段已填写 ${filledFieldCount.value}/${inputFields.value.length}。`
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

async function runGenerate() {
  if (!projectId.value || !canGenerate.value) return
  generating.value = true
  error.value = ''
  try {
    result.value = await generateRoute({
      project_id: projectId.value,
      factor_values: factorValues.value,
    })
  } catch (err: any) {
    console.error(err)
    error.value = err?.response?.data?.detail || err?.message || '生成路线失败'
  } finally {
    generating.value = false
  }
}

function downloadOutputJson() {
  downloadGeneratedRouteJson({
    result: result.value,
    projectName: projectName.value,
    projectId: projectId.value,
  })
}

async function loadGenerateContext() {
  contextLoading = true
  try {
    const projects = await listProjects()
    const resolvedProjectId = resolveAvailableProjectId(String(route.query.project_id || ''), projects)
    if (!resolvedProjectId) {
      projectId.value = null
      projectName.value = ''
      inputSchema.value = null
      hasRulePackage.value = false
      packageSchemaVersion.value = ''
      packageVersion.value = null
      packageHash.value = ''
      resetFieldValues()
      return
    }
    projectId.value = Number(resolvedProjectId)
    if (String(route.query.project_id || '') !== resolvedProjectId) {
      void router.replace({
        path: route.path,
        query: { ...route.query, project_id: resolvedProjectId },
      })
    }
    projectName.value = projects.find(project => project.id === projectId.value)?.name || `任务 #${projectId.value}`
    const latestPackage = await getLatestFinalizedRulePackage(projectId.value).catch(() => null)
    if (latestPackage?.input_schema) {
      inputSchema.value = latestPackage.input_schema
      hasRulePackage.value = true
      packageSchemaVersion.value = String(latestPackage.schema_version || latestPackage.input_schema?.schema_version || '1.0')
      packageVersion.value = latestPackage.version ?? null
      packageHash.value = latestPackage.content_hash || ''
      initializeFieldValues()
    } else {
      inputSchema.value = null
      hasRulePackage.value = false
      packageSchemaVersion.value = ''
      packageVersion.value = null
      packageHash.value = ''
      resetFieldValues()
    }
  } catch (err) {
    console.warn('读取生成上下文失败', err)
    inputSchema.value = null
    hasRulePackage.value = false
    resetFieldValues()
  } finally {
    contextLoading = false
    loadedDataRevision = getWorkflowDataRevision()
  }
}

onMounted(async () => {
  try {
    await loadGenerateContext()
  } finally {
    initialLoadFinished = true
  }
})

watch(() => route.query.project_id, () => {
  if (!generateViewActive) return
  result.value = null
  error.value = ''
  void loadGenerateContext()
})

onActivated(() => {
  generateViewActive = true
  if (!initialLoadFinished || contextLoading) return

  const routeProjectId = Number(route.query.project_id || 0)
  const projectChanged = routeProjectId > 0 && routeProjectId !== projectId.value
  if (!projectChanged && loadedDataRevision === getWorkflowDataRevision()) return
  void loadGenerateContext()
})

onDeactivated(() => {
  generateViewActive = false
  loadedDataRevision = getWorkflowDataRevision()
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
  height: calc(100vh - 118px);
  color: var(--generate-ink);
}

.generate-header-card {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background: #ffffff;
  border: 1px solid var(--generate-line);
  border-radius: 12px;
  padding: 8px 12px;
  box-shadow: var(--shadow-sm);
  margin-bottom: 12px;
}

.gh-left-content {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.gh-page-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--generate-ink);
  white-space: nowrap;
  flex-shrink: 0;
}

.generate-project-chip {
  display: inline-flex;
  align-items: center;
  background: #0f172a;
  color: #f1f5f9;
  padding: 3px 8px;
  border-radius: 6px;
  font-size: 12.5px;
  font-weight: 700;
  flex-shrink: 0;
}

.gh-meta-section {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-left: 12px;
  border-left: 1px solid var(--generate-line);
  padding-left: 16px;
}

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

.generate-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 18px;
  align-items: start;
  height: calc(100vh - 178px);
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

  .generate-grid {
    grid-template-columns: 1fr;
    height: auto;
  }
}
</style>
