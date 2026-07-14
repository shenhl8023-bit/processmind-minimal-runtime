<template>
  <div class="generate-view">
    <header class="generate-header">
      <div>
        <h1>路线生成</h1>
        <p>填写新零件参数，生成对应的工艺路线结果。</p>
      </div>
      <div class="generate-actions">
        <button class="btn btn-outline" type="button" @click="goFinalize" :disabled="!projectId">返回定稿</button>
      </div>
    </header>

    <section v-if="!projectId" class="empty-panel">
      <div class="empty-code">05</div>
      <h2>还没有选择任务</h2>
      <p>请先从前面步骤进入当前项目，再打开路线生成。</p>
    </section>

    <div v-if="projectId" class="generate-grid">
      <GenerateInputPanel
        :project-id="projectId"
        :project-name="projectName"
        :input-fields="inputFields"
        :filled-field-count="filledFieldCount"
        :missing-required-fields="missingRequiredFields"
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
  missingRequiredFields,
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
  if (!hasRulePackage.value) return '当前项目还没有可用规则包，请先在第4步导出规则包。'
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
  min-height: calc(100vh - 128px);
  color: #101828;
}

.generate-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 18px;
  padding: 4px 0 14px;
}

.generate-header h1 {
  font-size: 24px;
  line-height: 1.2;
  font-weight: 700;
  letter-spacing: 0;
  margin: 0 0 6px;
}

.generate-header p {
  margin: 0;
  color: #667085;
  font-size: 13px;
  line-height: 1.6;
}

.generate-actions {
  display: flex;
  gap: 8px;
  flex-shrink: 0;
}

.generate-grid {
  display: grid;
  grid-template-columns: minmax(320px, 380px) minmax(0, 1fr);
  gap: 14px;
  align-items: start;
}

.empty-panel {
  background: #ffffff;
  border: 1px solid #e4e7ec;
  border-radius: 8px;
  box-shadow: 0 1px 2px rgba(16, 24, 40, 0.04);
}

.empty-panel h2 {
  margin: 0;
  font-size: 16px;
  font-weight: 700;
  letter-spacing: 0;
}

.empty-panel p {
  margin: 4px 0 0;
  color: #667085;
  font-size: 12px;
  line-height: 1.55;
}

.empty-panel {
  min-height: 360px;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  text-align: center;
  padding: 28px;
}

.empty-code {
  height: 34px;
  padding: 0 12px;
  display: inline-flex;
  align-items: center;
  border: 1px solid #d0d5dd;
  border-radius: 999px;
  color: #667085;
  font-size: 12px;
  font-weight: 800;
  margin-bottom: 12px;
}

@media (max-width: 900px) {
  .generate-header {
    flex-direction: column;
  }

  .generate-grid {
    grid-template-columns: 1fr;
  }
}
</style>
