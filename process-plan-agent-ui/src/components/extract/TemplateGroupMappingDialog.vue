<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tgmd-backdrop" @click.self="closeDialog">
      <section class="tgmd-dialog" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title">
        <header class="tgmd-header">
          <div class="tgmd-title-block">
            <h2 id="template-group-mapping-title">模板分组映射</h2>
            <p v-if="model.template.value">
              {{ model.template.value.original_filename }} · {{ model.template.value.part_filename || '未标注零件文件' }}
            </p>
            <p v-else>导入 Kmsoft XML 分组模板后，再将当前零件的工序映射到特征分组。</p>
          </div>
          <div class="tgmd-header-actions">
            <button
              v-if="model.state.value === 'workspace'"
              class="tgmd-command"
              type="button"
              @click="startReplacement"
            ><RefreshRight />更换模板</button>
            <button class="tgmd-icon-button" type="button" title="关闭" aria-label="关闭" @click="closeDialog"><Close /></button>
          </div>
        </header>

        <div v-if="visibleError" class="tgmd-inline-error" role="alert">
          <WarningFilled />
          <span>{{ visibleError }}</span>
        </div>

        <div v-if="model.loading.value && model.state.value !== 'preview'" class="tgmd-loading">
          <span class="tgmd-spinner" />正在加载项目分组模板...
        </div>

        <template v-else-if="showUploadState">
          <main class="tgmd-upload-state">
            <input ref="fileInput" class="tgmd-file-input" type="file" accept=".xml,application/xml,text/xml" @change="onFileInput">
            <button
              class="tgmd-dropzone"
              :class="{ 'tgmd-dropzone-ready': pendingFile }"
              type="button"
              :disabled="model.loading.value"
              @click="openFilePicker"
              @dragover.prevent
              @drop.prevent="onDrop"
            >
              <UploadFilled />
              <strong>{{ pendingFile ? pendingFile.name : '选择分组模板 XML' }}</strong>
              <span v-if="model.loading.value">正在解析模板结构...</span>
              <span v-else>{{ pendingFile ? formatBytes(pendingFile.size) : '点击选择，或将 .xml 文件拖到这里' }}</span>
            </button>
            <div class="tgmd-upload-actions">
              <button
                v-if="isReplacing"
                class="btn btn-outline"
                type="button"
                :disabled="model.loading.value"
                @click="cancelReplacement"
              >取消更换</button>
              <button
                v-if="model.loading.value"
                class="btn btn-primary"
                type="button"
                disabled
              >
                <span class="tgmd-spinner tgmd-spinner-light" />
                正在解析
              </button>
              <button
                v-else-if="pendingFile && visibleError"
                class="btn btn-primary"
                type="button"
                @click="parsePendingFile"
              >重新解析</button>
            </div>
          </main>
        </template>

        <template v-else-if="model.state.value === 'preview' && model.preview.value">
          <main class="tgmd-preview-state">
            <section class="tgmd-preview-summary">
              <div class="tgmd-preview-heading">
                <DocumentChecked />
                <div>
                  <h3>{{ model.preview.value.original_filename }}</h3>
                  <p>{{ model.preview.value.can_confirm ? '模板结构校验通过' : '模板存在阻断问题，请更换文件后重试' }}</p>
                </div>
                <span :class="['tgmd-validation-badge', model.preview.value.can_confirm ? 'is-valid' : 'is-invalid']">
                  {{ model.preview.value.can_confirm ? '可确认' : '不可确认' }}
                </span>
              </div>

              <dl class="tgmd-meta-grid">
                <div><dt>编码</dt><dd>{{ model.preview.value.source_encoding || '未知' }}</dd></div>
                <div><dt>零件文件</dt><dd>{{ model.preview.value.part_filename || '未标注' }}</dd></div>
                <div><dt>分组</dt><dd>{{ model.preview.value.group_count }}</dd></div>
                <div><dt>特征选择</dt><dd>{{ model.preview.value.feature_selection_count }}</dd></div>
                <div><dt>校验问题</dt><dd>{{ model.preview.value.validation_issues.length }}</dd></div>
              </dl>

              <div v-if="model.preview.value.validation_issues.length" class="tgmd-issue-list">
                <div v-for="(issue, index) in model.preview.value.validation_issues" :key="`${issue.code}-${index}`" class="tgmd-issue-row">
                  <strong>{{ issue.message }}</strong>
                  <span v-if="issue.path.length || issue.value">{{ formatGroupTemplateIssueDetail(issue) }}</span>
                </div>
              </div>

              <div v-if="isReplacing && model.replacementImpact.value" class="tgmd-impact">
                <h4>更换影响</h4>
                <p>
                  可保留 <strong>{{ model.replacementImpact.value.kept_source_operation_ids.length }}</strong> 项映射，
                  将失效 <strong>{{ model.replacementImpact.value.invalidated.length }}</strong> 项。
                </p>
                <div v-if="model.replacementImpact.value.invalidated.length" class="tgmd-invalidated-list">
                  <div v-for="mapping in model.replacementImpact.value.invalidated" :key="mapping.source_operation_id">
                    <span>{{ operationName(mapping.source_operation_id) }}</span>
                    <small>{{ mapping.template_group_path.join(' / ') }}</small>
                  </div>
                </div>
              </div>
            </section>

            <section class="tgmd-preview-tree" aria-label="模板分组预览">
              <header><h3>分组结构</h3><span>仅展示业务分组和特征选择</span></header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in model.preview.value.tree"
                  :key="node.key"
                  :node="node"
                  readonly
                />
              </div>
            </section>
          </main>
          <footer class="tgmd-footer">
            <div>
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="resetPreviewSelection">重新选择</button>
              <button v-if="isReplacing" class="btn btn-outline" type="button" :disabled="model.saving.value" @click="cancelReplacement">取消更换</button>
            </div>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!model.preview.value.can_confirm || model.saving.value"
              @click="confirmPreview"
            >{{ model.saving.value ? '正在确认' : isReplacing ? '确认更换并进入映射' : '确认并进入映射' }}</button>
          </footer>
        </template>

        <template v-else-if="model.state.value === 'workspace' && model.template.value">
          <div v-if="recognizing || mappingWarnings.length" class="tgmd-smart-status" aria-live="polite">
            <span v-if="recognizing"><span class="tgmd-spinner" /> 正在为当前叶子分组推荐加工工步</span>
            <span v-if="mappingWarnings.length" class="tgmd-smart-warning">{{ mappingWarnings.join('；') }}</span>
          </div>

          <main class="tgmd-workspace">
            <section class="tgmd-pane tgmd-tree-pane">
              <header class="tgmd-pane-header">
                <div><h3>模板分组</h3><span>{{ model.template.value.group_count }} 个分组</span></div>
                <span class="tgmd-group-progress">已配置 {{ leafConfiguration.configured.length }} / {{ leafCount }} 个叶子分组</span>
              </header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in model.template.value.tree"
                  :key="node.key"
                  :node="node"
                  :active-key="activeGroupKey"
                  :mapped-counts="mappedCounts"
                  :configured-leaf-keys="configuredLeafKeys"
                  :unconfigured-leaf-keys="unconfiguredLeafKeys"
                  @select="activeGroupKey = $event"
                />
              </div>
              <div v-if="activeGroup" class="tgmd-active-target">
                <span>{{ isFeatureLeaf(activeGroup) ? '当前叶子分组' : '分组汇总' }}</span>
                <strong>{{ activeGroup.path.join(' / ') }}</strong>
                <small v-if="!isFeatureLeaf(activeGroup)">
                  包含 {{ descendantLeafCount(activeGroup) }} 个特征叶子，已配置 {{ descendantConfiguredCount(activeGroup) }} 个
                </small>
              </div>
            </section>

            <section class="tgmd-pane tgmd-operation-pane">
              <header class="tgmd-pane-header tgmd-operation-header">
                <div><h3>关联加工工序</h3><span>{{ activeLeaf ? activeLeaf.path.join(' / ') : '请选择叶子分组' }}</span></div>
                <div class="tgmd-operation-tools">
                  <button class="tgmd-smart-button" type="button" :disabled="!activeLeaf || recognizing" @click="suggestActiveLeaf">
                    <MagicStick />{{ recognizing ? '正在推荐' : '智能推荐当前分组' }}
                  </button>
                </div>
              </header>

              <div v-if="activeLeaf" class="tgmd-operation-scroll">
                <p class="tgmd-feature-summary">特征选择：{{ activeLeaf.feature_selections.join('、') }}</p>
                <article v-for="operation in mappingOperations" :key="operationId(operation)" class="tgmd-operation-card">
                  <button class="tgmd-operation-toggle" type="button" @click="toggleOperationExpanded(operationId(operation))">
                    <ArrowRight :class="{ open: operationExpanded(operationId(operation)) }" />
                    <strong>{{ operation.name }}</strong>
                    <span>{{ operationActiveLeafSummary(operation) }}</span>
                  </button>
                  <div v-if="operationExpanded(operationId(operation))" class="tgmd-step-list">
                    <div
                      v-for="step in visibleStepsForOperation(operation)"
                      :key="step.step_key"
                      class="tgmd-step-row"
                      :class="{ 'is-selected': activeLeafStepKeys.has(step.step_key) }"
                    >
                      <input type="checkbox" :checked="activeLeafStepKeys.has(step.step_key)" @change="toggleActiveLeafStep(step)">
                      <span class="tgmd-step-order">{{ step.step_order }}</span>
                      <div class="tgmd-step-content">
                        <strong>{{ step.step_name }}</strong>
                        <small>{{ activeLeafStepKeys.has(step.step_key) ? '已关联当前叶子分组' : '可关联当前叶子分组' }}</small>
                      </div>
                    </div>
                  </div>
                </article>
                <button class="tgmd-show-excluded" type="button" @click="showExcludedSteps = !showExcludedSteps">
                  {{ showExcludedSteps ? '收起其它工步' : `显示其它工步（${classifiedSteps.excluded.length}）` }}
                </button>
                <div v-if="!mappingOperations.length" class="tgmd-empty">当前路线没有可关联的工步</div>
              </div>
              <div v-else class="tgmd-empty">请选择一个具有特征选择的叶子分组进行编辑</div>
              <div v-if="activeLeaf && !activeLeafStepKeys.size" class="tgmd-unconfigured-hint">
                当前叶子尚未关联工步，可直接继续保存，或使用智能推荐辅助选择。
              </div>
            </section>
          </main>

          <footer class="tgmd-footer">
            <button class="tgmd-clear-all" type="button" :disabled="!Object.keys(draftStepMappings).length || model.saving.value" @click="clearMappings">
              <Delete />清空映射
            </button>
            <div>
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="closeDialog">取消</button>
              <button class="btn btn-primary" type="button" :disabled="model.saving.value || recognizing" @click="saveStepMappings">
                <Link />{{ model.saving.value ? '正在保存' : '保存工步映射' }}
              </button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import {
  ArrowRight,
  Delete,
  DocumentChecked,
  Link,
  MagicStick,
  RefreshRight,
  UploadFilled,
  WarningFilled,
} from '@element-plus/icons-vue'

import {
  suggestTemplateStepMappings,
  type GroupTemplateNode,
  type GroupTemplateStepMapping,
  type GroupTemplateStepMappingInput,
} from '@/api/extract'
import TemplateGroupTreeNode from '@/components/extract/TemplateGroupTreeNode.vue'
import {
  acceptTemplateGroupFile,
  findTemplateGroupByKey,
  openTemplateGroupFilePicker,
  type TemplateAliasBinding,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'
import {
  buildTemplateStepRefs,
  buildTemplateStepRouteFingerprint,
  clearTemplateStepMappingDraft,
  createTemplateStepMapping,
  isFeatureLeaf,
  loadTemplateStepMappingDraft,
  saveTemplateStepMappingDraft,
  stepMappingKey,
  type TemplateStepRef,
} from '@/composables/templateStepMapping'
import {
  buildEligibleTemplateSteps,
  confirmedTemplateStepMappings,
  featureLeafConfiguration,
  groupConfirmedMappingsByLeaf,
  mappingRecord,
} from '@/composables/templateGroupProcessMapping'
import { formatGroupTemplateIssueDetail, useProjectGroupTemplate } from '@/composables/useProjectGroupTemplate'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  operations: TemplateOperation[]
  legacyAliases: Record<string, TemplateAliasBinding>
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', payload: { stepMappings: GroupTemplateStepMapping[]; templateRevision: number }): void
}>()

const model = useProjectGroupTemplate(
  computed(() => props.projectId),
  computed(() => props.legacyAliases),
)
const fileInput = ref<HTMLInputElement | null>(null)
const pendingFile = ref<File | null>(null)
const transientError = ref('')
const draftStepMappings = ref<Record<string, GroupTemplateStepMappingInput>>({})
const expandedOperationIds = ref<number[]>([])
const activeGroupKey = ref('')
const recognizing = ref(false)
const dialogRunId = ref(0)
const mappingWarnings = ref<string[]>([])
const showExcludedSteps = ref(false)

const visibleError = computed(() => transientError.value || model.error.value)
const isReplacing = computed(() => Boolean(model.template.value))
const showUploadState = computed(() => (
  model.state.value === 'empty'
  || (model.state.value === 'preview' && !model.preview.value)
))
const mappingOperations = computed(() => {
  const seen = new Set<number>()
  return props.operations
    .filter(operation => buildTemplateStepRefs(operation).length > 0)
    .filter((operation) => {
      const id = operationId(operation)
      if (!id || seen.has(id)) return false
      seen.add(id)
      return true
    })
    .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0) || operationId(left) - operationId(right))
})
const stepRefs = computed(() => mappingOperations.value.flatMap(buildTemplateStepRefs))
const routeFingerprint = computed(() => buildTemplateStepRouteFingerprint(mappingOperations.value))
const classifiedSteps = computed(() => buildEligibleTemplateSteps(mappingOperations.value))
const eligibleStepKeys = computed(() => new Set(classifiedSteps.value.eligible.map(step => step.step_key)))
const activeGroup = computed(() => (
  model.template.value
    ? findTemplateGroupByKey(model.template.value.tree, activeGroupKey.value)
    : null
))
const activeLeaf = computed(() => isFeatureLeaf(activeGroup.value) ? activeGroup.value : null)
const mappingsByLeaf = computed(() => groupConfirmedMappingsByLeaf(
  Object.values(draftStepMappings.value),
  model.template.value?.tree || [],
))
const leafConfiguration = computed(() => featureLeafConfiguration(
  model.template.value?.tree || [],
  Object.values(draftStepMappings.value),
))
const leafCount = computed(() => leafConfiguration.value.configured.length + leafConfiguration.value.unconfigured.length)
const configuredLeafKeys = computed(() => leafConfiguration.value.configured.map(leaf => leaf.key))
const unconfiguredLeafKeys = computed(() => leafConfiguration.value.unconfigured.map(leaf => leaf.key))
const activeLeafStepKeys = computed(() => new Set(
  activeLeaf.value ? (mappingsByLeaf.value[activeLeaf.value.key] || []).map(mapping => (
    `op_${mapping.source_operation_id}_s${String(mapping.source_step_order).padStart(2, '0')}`
  )) : [],
))
const mappedCounts = computed(() => Object.entries(mappingsByLeaf.value).reduce<Record<string, number>>((counts, [key, mappings]) => {
  counts[key] = mappings.length
  return counts
}, {}))

watch(() => props.modelValue, async (visible) => {
  dialogRunId.value += 1
  recognizing.value = false
  transientError.value = ''
  pendingFile.value = null
  if (!visible) return
  mappingWarnings.value = []
  showExcludedSteps.value = false
  const runId = dialogRunId.value
  await model.load()
  if (runId !== dialogRunId.value || !props.modelValue) return
  syncDraftFromTemplate()
}, { immediate: true })

function operationId(operation: TemplateOperation) {
  return Number(operation.source_operation_id || operation.id || 0)
}

function operationName(sourceOperationId: number) {
  return props.operations.find(operation => operationId(operation) === sourceOperationId)?.name || `工序 ${sourceOperationId}`
}

function stepRefsForOperation(operation: TemplateOperation) {
  return buildTemplateStepRefs(operation)
}

function syncDraftFromTemplate() {
  const template = model.template.value
  if (!template) {
    draftStepMappings.value = {}
    activeGroupKey.value = ''
    return
  }
  const formal = model.draftStepMappings.value
  const restored = loadTemplateStepMappingDraft(
    props.projectId,
    template.template_revision,
    routeFingerprint.value,
  )
  draftStepMappings.value = mappingRecord(confirmedTemplateStepMappings(restored.length ? restored : formal))
  const activeStillExists = findTemplateGroupByKey(template.tree, activeGroupKey.value)
  const firstLeaf = [...leafConfiguration.value.configured, ...leafConfiguration.value.unconfigured][0]
  activeGroupKey.value = activeStillExists?.key || firstLeaf?.key || ''
  expandedOperationIds.value = mappingOperations.value.slice(0, 3).map(operationId)
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`
}

function openFilePicker() {
  openTemplateGroupFilePicker(fileInput.value)
}

async function acceptFile(file: File | undefined) {
  transientError.value = ''
  if (!file) return
  pendingFile.value = file
  const result = await acceptTemplateGroupFile(file, model.selectFile)
  pendingFile.value = result.file
  transientError.value = result.error
}

function onFileInput(event: Event) {
  void acceptFile((event.target as HTMLInputElement).files?.[0])
}

function onDrop(event: DragEvent) {
  void acceptFile(event.dataTransfer?.files?.[0])
}

async function parsePendingFile() {
  if (!pendingFile.value) return
  transientError.value = ''
  await model.selectFile(pendingFile.value)
}

async function startReplacement() {
  pendingFile.value = null
  transientError.value = ''
  model.beginReplacement()
  await nextTick()
  openFilePicker()
}

function cancelReplacement() {
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  syncDraftFromTemplate()
}

function resetPreviewSelection() {
  pendingFile.value = null
  transientError.value = ''
  if (model.template.value) model.beginReplacement()
  else model.cancelPreview()
  if (fileInput.value) fileInput.value.value = ''
}

async function confirmPreview() {
  await model.confirmTemplate()
  if (model.state.value === 'workspace') syncDraftFromTemplate()
}

function persistStepDraft() {
  if (!model.template.value) return
  saveTemplateStepMappingDraft(
    props.projectId,
    model.templateRevision.value,
    routeFingerprint.value,
    Object.values(draftStepMappings.value),
  )
}

function toggleOperationExpanded(id: number) {
  const expanded = new Set(expandedOperationIds.value)
  if (expanded.has(id)) expanded.delete(id)
  else expanded.add(id)
  expandedOperationIds.value = [...expanded]
}

function operationExpanded(id: number) {
  return expandedOperationIds.value.includes(id)
}

function visibleStepsForOperation(operation: TemplateOperation) {
  return stepRefsForOperation(operation).filter(step => (
    showExcludedSteps.value || eligibleStepKeys.value.has(step.step_key)
  ))
}

function operationActiveLeafSummary(operation: TemplateOperation) {
  const steps = stepRefsForOperation(operation).filter(step => eligibleStepKeys.value.has(step.step_key))
  const mapped = steps.filter(step => activeLeafStepKeys.value.has(step.step_key)).length
  return `已关联 ${mapped}/${steps.length}`
}

function descendantLeaves(node: GroupTemplateNode): GroupTemplateNode[] {
  if (isFeatureLeaf(node)) return [node]
  return node.children.flatMap(descendantLeaves)
}

function descendantLeafCount(node: GroupTemplateNode) {
  return descendantLeaves(node).length
}

function descendantConfiguredCount(node: GroupTemplateNode) {
  const configured = new Set(configuredLeafKeys.value)
  return descendantLeaves(node).filter(leaf => configured.has(leaf.key)).length
}

function toggleActiveLeafStep(step: TemplateStepRef) {
  const leaf = activeLeaf.value
  if (!leaf) return
  const mapping = createTemplateStepMapping(step, leaf, leaf.path.slice(0, -1))
  const key = stepMappingKey(mapping)
  if (draftStepMappings.value[key]) delete draftStepMappings.value[key]
  else draftStepMappings.value[key] = mapping
  persistStepDraft()
}

function clearMappings() {
  draftStepMappings.value = {}
  persistStepDraft()
}

async function suggestActiveLeaf() {
  const leaf = activeLeaf.value
  if (recognizing.value || !leaf || !model.template.value) return
  const runId = ++dialogRunId.value
  recognizing.value = true
  mappingWarnings.value = []
  const operations = mappingOperations.value
  try {
    const response = await suggestTemplateStepMappings({
      project_id: props.projectId,
      expected_template_revision: model.templateRevision.value,
      target_group_id: leaf.key,
      operations: operations.map(operation => ({
        operation_id: operationId(operation),
        operation_name: operation.name,
        // Keep original positions so the server's stable step keys still match the route.
        step_items: (operation.step_items || []).map((step, index) => {
          const ref = stepRefsForOperation(operation).find(item => item.step_order === index + 1)
          return ref && eligibleStepKeys.value.has(ref.step_key) ? step : ''
        }),
        rule_evidence: [],
        rule_reasons: [],
      })),
    })
    if (runId !== dialogRunId.value || !props.modelValue) return
    mappingWarnings.value = response.warnings || []
    response.suggestions.forEach((suggestion) => {
      const recommended = suggestion.recommended_group_ids.filter(groupId => groupId === leaf.key)
      const step = stepRefs.value.find(item => item.step_key === suggestion.step_key)
      if (!step || activeLeafStepKeys.value.has(step.step_key) || !recommended.length) return
      draftStepMappings.value[stepMappingKey(createTemplateStepMapping(
        step,
        leaf,
        leaf.path.slice(0, -1),
        'auto_confirmed',
        suggestion.confidence,
      ))] = createTemplateStepMapping(step, leaf, leaf.path.slice(0, -1), 'auto_confirmed', suggestion.confidence)
    })
    persistStepDraft()
  } catch {
    if (runId !== dialogRunId.value || !props.modelValue) return
    mappingWarnings.value = ['智能推荐暂时不可用，已保留当前映射和人工操作。']
  } finally {
    if (runId === dialogRunId.value && props.modelValue) recognizing.value = false
  }
}

async function saveStepMappings() {
  const confirmed = confirmedTemplateStepMappings(Object.values(draftStepMappings.value))
  const unconfigured = featureLeafConfiguration(
    model.template.value?.tree || [],
    confirmed,
  ).unconfigured
  mappingWarnings.value = unconfigured.length
    ? [`仍有 ${unconfigured.length} 个叶子分组未配置，已按当前映射保存。`]
    : []
  model.draftStepMappings.value = confirmed
  await model.saveStepMappings()
  if (model.error.value || !model.template.value) {
    return
  }
  clearTemplateStepMappingDraft(props.projectId)
  emit('save', {
    stepMappings: model.template.value.step_mappings || [],
    templateRevision: model.templateRevision.value,
  })
  closeDialog()
}

function closeDialog() {
  dialogRunId.value += 1
  recognizing.value = false
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  emit('update:modelValue', false)
}
</script>

<style scoped>
.tgmd-backdrop { position: fixed; inset: 0; z-index: 3000; display: grid; place-items: center; padding: 16px; background: rgba(15, 23, 42, .48); }
.tgmd-dialog { width: min(1180px, calc(100vw - 32px)); height: min(780px, calc(100vh - 32px)); display: flex; flex-direction: column; overflow: hidden; border: 1px solid #cbd5e1; border-radius: 8px; background: #f8fafc; box-shadow: 0 22px 60px rgba(15, 23, 42, .24); color: #1e293b; }
.tgmd-header { min-height: 72px; display: flex; align-items: center; justify-content: space-between; gap: 20px; padding: 14px 18px; border-bottom: 1px solid #dbe3ec; background: #fff; }
.tgmd-title-block { min-width: 0; }
.tgmd-title-block h2 { margin: 0; font-size: 18px; line-height: 1.35; letter-spacing: 0; }
.tgmd-title-block p { margin: 4px 0 0; overflow: hidden; color: #64748b; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-header-actions, .tgmd-operation-tools, .tgmd-footer > div, .tgmd-upload-actions { display: flex; align-items: center; gap: 8px; }
.tgmd-command, .tgmd-icon-button, .tgmd-smart-button, .tgmd-clear-all { display: inline-flex; align-items: center; justify-content: center; gap: 6px; border: 1px solid #cbd5e1; background: #fff; color: #334155; cursor: pointer; }
.tgmd-command { min-height: 34px; padding: 0 10px; border-radius: 4px; }
.tgmd-command svg, .tgmd-smart-button svg, .tgmd-clear-all svg, .btn svg { width: 15px; height: 15px; }
.tgmd-icon-button { width: 34px; height: 34px; border-radius: 4px; }
.tgmd-icon-button svg { width: 17px; height: 17px; }
.tgmd-inline-error { display: flex; align-items: flex-start; gap: 8px; padding: 9px 18px; border-bottom: 1px solid #fecaca; background: #fef2f2; color: #991b1b; font-size: 12px; }
.tgmd-inline-error svg { width: 16px; height: 16px; flex: 0 0 auto; }
.tgmd-loading { flex: 1; display: flex; align-items: center; justify-content: center; gap: 10px; color: #64748b; }
.tgmd-spinner { width: 16px; height: 16px; display: inline-block; border: 2px solid #cbd5e1; border-top-color: #2563eb; border-radius: 50%; animation: tgmd-spin .8s linear infinite; }
.tgmd-spinner-light { border-color: rgba(255,255,255,.45); border-top-color: #fff; }
@keyframes tgmd-spin { to { transform: rotate(360deg); } }

.tgmd-upload-state { flex: 1; display: grid; place-content: center; gap: 18px; padding: 32px; }
.tgmd-file-input { display: none; }
.tgmd-dropzone { width: min(520px, calc(100vw - 80px)); min-height: 190px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 9px; padding: 24px; border: 1px dashed #94a3b8; border-radius: 6px; background: #fff; color: #475569; cursor: pointer; }
.tgmd-dropzone:hover, .tgmd-dropzone-ready { border-color: #2563eb; background: #f8fbff; }
.tgmd-dropzone svg { width: 32px; height: 32px; color: #2563eb; }
.tgmd-dropzone strong { max-width: 100%; overflow-wrap: anywhere; font-size: 15px; }
.tgmd-dropzone span { color: #64748b; font-size: 12px; }
.tgmd-upload-actions { justify-content: flex-end; }

.tgmd-preview-state { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(360px, .85fr) minmax(420px, 1.15fr); gap: 16px; padding: 16px; }
.tgmd-preview-summary, .tgmd-preview-tree, .tgmd-pane { min-height: 0; border: 1px solid #dbe3ec; border-radius: 6px; background: #fff; }
.tgmd-preview-summary { overflow: auto; padding: 18px; }
.tgmd-preview-heading { display: flex; align-items: center; gap: 12px; }
.tgmd-preview-heading > svg { width: 28px; height: 28px; color: #2563eb; }
.tgmd-preview-heading > div { min-width: 0; flex: 1; }
.tgmd-preview-heading h3, .tgmd-preview-heading p { margin: 0; }
.tgmd-preview-heading h3 { overflow-wrap: anywhere; font-size: 15px; }
.tgmd-preview-heading p { margin-top: 3px; color: #64748b; font-size: 12px; }
.tgmd-validation-badge { padding: 4px 8px; border-radius: 3px; font-size: 11px; font-weight: 700; }
.tgmd-validation-badge.is-valid { background: #dcfce7; color: #166534; }
.tgmd-validation-badge.is-invalid { background: #fee2e2; color: #991b1b; }
.tgmd-meta-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1px; margin: 18px 0; background: #e2e8f0; }
.tgmd-meta-grid > div { min-width: 0; padding: 10px; background: #f8fafc; }
.tgmd-meta-grid dt { color: #64748b; font-size: 11px; }
.tgmd-meta-grid dd { margin: 3px 0 0; overflow-wrap: anywhere; font-size: 13px; font-weight: 650; }
.tgmd-issue-list, .tgmd-invalidated-list { display: grid; gap: 6px; }
.tgmd-issue-row, .tgmd-invalidated-list > div { display: flex; justify-content: space-between; gap: 12px; padding: 8px 10px; background: #fef2f2; color: #991b1b; font-size: 11px; }
.tgmd-impact { margin-top: 18px; padding-top: 16px; border-top: 1px solid #e2e8f0; }
.tgmd-impact h4, .tgmd-impact p { margin: 0; }
.tgmd-impact p { margin-top: 5px; color: #475569; font-size: 12px; }
.tgmd-invalidated-list { margin-top: 10px; }
.tgmd-invalidated-list small { color: #64748b; }
.tgmd-preview-tree { display: flex; flex-direction: column; overflow: hidden; }
.tgmd-preview-tree > header { padding: 14px 16px; border-bottom: 1px solid #e2e8f0; }
.tgmd-preview-tree h3, .tgmd-preview-tree header span { margin: 0; }
.tgmd-preview-tree h3 { font-size: 14px; }
.tgmd-preview-tree header span { color: #64748b; font-size: 11px; }
.tgmd-tree-scroll { min-height: 0; flex: 1; overflow: auto; padding: 6px 0; }

.tgmd-smart-status { display: flex; justify-content: space-between; gap: 16px; padding: 7px 18px; border-bottom: 1px solid #bfdbfe; background: #eff6ff; color: #1e40af; font-size: 11px; }
.tgmd-smart-warning { color: #92400e; }
.tgmd-workspace { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(300px, .85fr) minmax(480px, 1.15fr); gap: 10px; padding: 12px; }
.tgmd-pane { display: flex; flex-direction: column; overflow: hidden; }
.tgmd-pane-header { min-height: 54px; display: flex; align-items: center; justify-content: space-between; gap: 12px; padding: 10px 12px; border-bottom: 1px solid #e2e8f0; }
.tgmd-pane-header h3, .tgmd-pane-header span { margin: 0; }
.tgmd-pane-header h3 { font-size: 14px; }
.tgmd-pane-header span { color: #64748b; font-size: 11px; }
.tgmd-active-target { padding: 9px 12px; border-top: 1px solid #e2e8f0; background: #eff6ff; }
.tgmd-active-target span { display: block; color: #64748b; font-size: 10px; }
.tgmd-active-target strong { display: block; margin-top: 2px; color: #1d4ed8; font-size: 12px; overflow-wrap: anywhere; }
.tgmd-active-target small { display: block; margin-top: 3px; color: #64748b; font-size: 10px; }
.tgmd-feature-summary { margin: 0; padding: 9px 12px; border-bottom: 1px solid #e2e8f0; background: #f8fafc; color: #64748b; font-size: 11px; }
.tgmd-group-progress { color: #1d4ed8 !important; font-weight: 650; }
.tgmd-group-mappings { max-height: 130px; overflow: auto; border-top: 1px solid #e2e8f0; }
.tgmd-group-mappings > div { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 7px 12px; font-size: 11px; }
.tgmd-group-mappings button { width: 24px; height: 24px; display: grid; place-items: center; border: 0; background: transparent; color: #64748b; cursor: pointer; }
.tgmd-group-mappings svg { width: 14px; height: 14px; }
.tgmd-transfer-column { display: grid; place-items: center; }
.tgmd-transfer-button { position: relative; width: 40px; height: 40px; display: grid; place-items: center; border: 1px solid #2563eb; border-radius: 4px; background: #2563eb; color: #fff; cursor: pointer; }
.tgmd-transfer-button:disabled { border-color: #cbd5e1; background: #e2e8f0; color: #94a3b8; cursor: not-allowed; }
.tgmd-transfer-button svg { width: 18px; height: 18px; }
.tgmd-transfer-button span { position: absolute; top: -8px; right: -8px; min-width: 19px; padding: 2px 5px; border-radius: 10px; background: #0f172a; font-size: 10px; }
.tgmd-operation-header { align-items: flex-start; }
.tgmd-operation-tools { min-width: 0; }
.tgmd-search { width: 170px; height: 32px; display: flex; align-items: center; gap: 6px; padding: 0 8px; border: 1px solid #cbd5e1; border-radius: 4px; }
.tgmd-search svg { width: 14px; height: 14px; color: #64748b; }
.tgmd-search input { min-width: 0; width: 100%; border: 0; outline: 0; background: transparent; font-size: 12px; }
.tgmd-smart-button { height: 32px; padding: 0 9px; border-color: #93c5fd; border-radius: 4px; color: #1d4ed8; }
.tgmd-smart-button:disabled { opacity: .55; cursor: not-allowed; }
.tgmd-select-all { display: flex; align-items: center; gap: 8px; padding: 8px 12px; border-bottom: 1px solid #e2e8f0; color: #475569; font-size: 11px; }
.tgmd-operation-scroll { min-height: 0; flex: 1; overflow: auto; }
.tgmd-operation-card { border-bottom: 1px solid #e2e8f0; background: #fff; }
.tgmd-operation-toggle { width: 100%; min-height: 42px; display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: center; gap: 8px; padding: 7px 12px; border: 0; background: #f8fafc; color: #334155; text-align: left; cursor: pointer; }
.tgmd-operation-toggle:hover { background: #f1f5f9; }
.tgmd-operation-toggle svg { width: 14px; height: 14px; color: #64748b; transition: transform 160ms ease; }
.tgmd-operation-toggle svg.open { transform: rotate(90deg); }
.tgmd-operation-toggle strong { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; }
.tgmd-operation-toggle span { color: #64748b; font-size: 10px; }
.tgmd-step-list { border-top: 1px solid #eef2f7; }
.tgmd-step-row { min-height: 52px; display: grid; grid-template-columns: 18px 28px minmax(0, 1fr); align-items: start; gap: 8px; padding: 9px 12px; border-bottom: 1px solid #f1f5f9; }
.tgmd-step-row:last-child { border-bottom: 0; }
.tgmd-step-row.is-selected { background: #eff6ff; }
.tgmd-step-row.is-unresolved { box-shadow: inset 3px 0 #f59e0b; background: #fffbeb; }
.tgmd-step-row > input { margin-top: 4px; }
.tgmd-step-order { width: 28px; color: #64748b; font: 11px/1.7 ui-monospace, SFMono-Regular, Menlo, monospace; text-align: center; }
.tgmd-step-content { min-width: 0; }
.tgmd-step-content > strong { display: block; overflow-wrap: anywhere; font-size: 12px; line-height: 1.55; }
.tgmd-step-content > small { display: block; margin-top: 3px; color: #64748b; font-size: 10px; }
.tgmd-step-mappings { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 6px; }
.tgmd-step-mappings > span { max-width: 100%; display: inline-flex; align-items: center; gap: 4px; padding: 3px 6px; border: 1px solid #86efac; border-radius: 3px; background: #f0fdf4; color: #166534; font-size: 10px; overflow-wrap: anywhere; }
.tgmd-step-mappings > span.is-skipped { border-color: #cbd5e1; background: #f8fafc; color: #64748b; }
.tgmd-step-mappings button { width: 16px; height: 16px; display: grid; place-items: center; padding: 0; border: 0; background: transparent; color: currentColor; cursor: pointer; }
.tgmd-step-mappings svg { width: 12px; height: 12px; }
.tgmd-step-warning { display: block; margin-top: 5px; color: #92400e; font-size: 10px; }
.tgmd-skip-step { min-height: 30px; padding: 0 8px; border: 1px solid #cbd5e1; border-radius: 4px; background: #fff; color: #475569; font-size: 10px; cursor: pointer; }
.tgmd-skip-step:hover { border-color: #94a3b8; background: #f8fafc; }
.tgmd-operation-row { display: grid; grid-template-columns: 18px 38px minmax(0, 1fr); gap: 7px; align-items: start; padding: 10px 12px; border-bottom: 1px solid #eef2f7; }
.tgmd-operation-row:hover, .tgmd-operation-row.is-selected { background: #f8fbff; }
.tgmd-operation-row.has-suggestion { border-left: 2px solid #60a5fa; }
.tgmd-operation-sequence { color: #64748b; font: 11px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
.tgmd-operation-content { min-width: 0; }
.tgmd-operation-content > strong { display: block; overflow-wrap: anywhere; font-size: 12px; }
.tgmd-suggestion { margin-top: 6px; }
.tgmd-suggestion p { margin: 0 0 6px; color: #64748b; font-size: 10px; }
.tgmd-suggestion small { color: #92400e; }
.tgmd-candidates { display: flex; flex-wrap: wrap; gap: 5px; }
.tgmd-candidates button { max-width: 100%; padding: 4px 7px; border: 1px solid #bfdbfe; border-radius: 3px; background: #eff6ff; color: #1d4ed8; font-size: 10px; cursor: pointer; overflow-wrap: anywhere; }
.tgmd-empty { padding: 32px 16px; color: #94a3b8; text-align: center; font-size: 12px; }
.tgmd-show-excluded { margin: 10px 12px; padding: 7px 10px; border: 1px dashed #cbd5e1; border-radius: 4px; background: #fff; color: #475569; font-size: 11px; cursor: pointer; }
.tgmd-show-excluded:hover { border-color: #94a3b8; background: #f8fafc; }
.tgmd-unconfigured-hint { padding: 8px 12px; border-top: 1px solid #e2e8f0; background: #fffbeb; color: #92400e; font-size: 11px; }

.tgmd-footer { min-height: 62px; display: flex; align-items: center; justify-content: space-between; gap: 16px; padding: 10px 18px; border-top: 1px solid #dbe3ec; background: #fff; }
.tgmd-clear-all { min-height: 34px; padding: 0 10px; border-radius: 4px; color: #b91c1c; }
.btn { min-height: 36px; display: inline-flex; align-items: center; justify-content: center; gap: 6px; padding: 0 14px; border-radius: 4px; font-weight: 650; cursor: pointer; }
.btn:disabled { opacity: .55; cursor: not-allowed; }
.btn-outline { border: 1px solid #cbd5e1; background: #fff; color: #334155; }
.btn-primary { border: 1px solid #1d4ed8; background: #2563eb; color: #fff; }

@media (max-width: 860px) {
  .tgmd-dialog { width: calc(100vw - 16px); height: calc(100vh - 16px); }
  .tgmd-preview-state { grid-template-columns: 1fr; overflow: auto; }
  .tgmd-preview-tree { min-height: 340px; }
  .tgmd-workspace { grid-template-columns: 1fr; overflow: auto; }
  .tgmd-pane { min-height: 360px; }
  .tgmd-operation-header { align-items: stretch; flex-direction: column; }
  .tgmd-operation-tools { width: 100%; }
  .tgmd-search { flex: 1; width: auto; }
  .tgmd-title-block p { white-space: normal; }
}
</style>
