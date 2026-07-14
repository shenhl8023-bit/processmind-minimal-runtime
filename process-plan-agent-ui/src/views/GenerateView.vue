<template>
  <div class="generate-view">
    <header class="generate-header">
      <div>
        <h1>路线生成</h1>
        <p>填写新零件参数，基于已定稿规则包生成对应的工艺路线与工步树。</p>
      </div>
      <button v-if="projectId" class="generate-back" type="button" @click="goFinalize">返回规则定稿</button>
    </header>

    <div v-if="projectId" class="generate-meta-bar">
      <span class="generate-project-chip">{{ projectName || `任务 #${projectId}` }}</span>
      <span class="generate-meta-item">规则包 <strong :class="{ pending: !hasRulePackage }">{{ hasRulePackage ? '已加载' : '待导出' }}</strong></span>
      <span class="generate-meta-item">输入字段 <strong>{{ inputFields.length }}</strong></span>
      <span class="generate-meta-item">已填写 <strong>{{ filledFieldCount }}/{{ inputFields.length }}</strong></span>
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
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import GenerateInputPanel from '@/components/generate/GenerateInputPanel.vue'
import GenerateRouteOutputPanel from '@/components/generate/GenerateRouteOutputPanel.vue'
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

const route = useRoute()
const router = useRouter()

const projectId = ref<number | null>(null)
const projectName = ref('')
const inputSchema = ref<Record<string, any> | null>(null)
const hasRulePackage = ref(false)
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

const schemaStatusText = computed(() => {
  if (!hasRulePackage.value) return '当前任务还没有可用规则包，请先在第4步导出规则包。'
  return '当前规则包没有定义输入参数，请返回第4步重新导出规则包。'
})

const generateHintText = computed(() => {
  if (!hasRulePackage.value) return '请先在第4步导出规则包。'
  if (!inputFields.value.length) return '当前规则包没有定义输入参数。'
  return '请先补全必填输入参数。'
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
  try {
    const projects = await listProjects()
    const resolvedProjectId = resolveAvailableProjectId(String(route.query.project_id || ''), projects)
    if (!resolvedProjectId) {
      projectId.value = null
      projectName.value = ''
      inputSchema.value = null
      hasRulePackage.value = false
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
      initializeFieldValues()
    } else {
      inputSchema.value = null
      hasRulePackage.value = false
      resetFieldValues()
    }
  } catch (err) {
    console.warn('读取生成上下文失败', err)
    inputSchema.value = null
    hasRulePackage.value = false
    resetFieldValues()
  }
}

onMounted(loadGenerateContext)

watch(() => route.query.project_id, () => {
  result.value = null
  error.value = ''
  void loadGenerateContext()
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
  min-height: calc(100vh - 128px);
  color: var(--generate-ink);
  padding-bottom: 22px;
}

.generate-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 4px 0 14px;
}

.generate-header h1 {
  margin: 0 0 6px;
  color: var(--generate-ink);
  font-size: 24px;
  line-height: 1.2;
  font-weight: 700;
}

.generate-header p {
  margin: 0;
  color: var(--generate-muted);
  font-size: 13px;
  line-height: 1.7;
}

.generate-meta-bar {
  display: flex;
  align-items: center;
  min-height: 56px;
  gap: 20px;
  padding: 10px 14px;
  margin-bottom: 18px;
  border: 1px solid var(--generate-line);
  border-radius: 12px;
  background: var(--generate-surface);
  box-shadow: var(--shadow-sm);
}

.generate-project-chip {
  display: inline-flex;
  align-items: center;
  min-height: 32px;
  padding: 0 12px;
  border-radius: 7px;
  background: #0f172a;
  color: #ffffff;
  font-size: 13px;
  font-weight: 800;
}

.generate-meta-item {
  color: var(--generate-muted);
  font-size: 13px;
}

.generate-meta-item strong {
  margin-left: 4px;
  color: #334155;
}

.generate-meta-item strong:not(.pending) {
  color: #4f46e5;
}

.generate-meta-item strong.pending {
  color: #d97706;
}

.generate-back {
  height: 36px;
  padding: 0 13px;
  border: 1px solid #c7d2fe;
  border-radius: 7px;
  background: #ffffff;
  color: #4f46e5;
  font: inherit;
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: border-color 0.16s ease, color 0.16s ease, background 0.16s ease;
}

.generate-back:hover {
  border-color: #6366f1;
  background: var(--generate-accent-soft);
  color: #4338ca;
}

.generate-grid {
  display: grid;
  grid-template-columns: minmax(330px, 395px) minmax(0, 1fr);
  gap: 18px;
  align-items: start;
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

@media (max-width: 1100px) {
  .generate-meta-bar { gap: 12px; }
}

@media (max-width: 900px) {
  .generate-header {
    flex-direction: column;
  }

  .generate-back {
    align-self: flex-start;
  }

  .generate-meta-bar {
    align-items: flex-start;
    flex-wrap: wrap;
    gap: 10px 14px;
  }

  .generate-grid {
    grid-template-columns: 1fr;
  }
}
</style>
