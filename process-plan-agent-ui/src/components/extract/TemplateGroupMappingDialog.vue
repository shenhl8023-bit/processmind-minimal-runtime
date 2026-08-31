<template>
  <Teleport to="body">
    <div v-if="modelValue" class="tgmd-backdrop" @click.self="closeDialog">
      <section class="tgmd-dialog" :class="{ 'is-compact-upload': showUploadState }" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title">
        <header class="tgmd-header">
          <div class="tgmd-title-block">
            <div class="tgmd-title-row">
              <h2 id="template-group-mapping-title">模板分组映射</h2>
              <span v-if="model.template.value" class="tgmd-file-inline">
                {{ model.template.value.original_filename }} → {{ model.template.value.part_filename || '未标注零件文件' }}
              </span>
              <span v-if="model.template.value" class="tgmd-title-tag">Kmsoft XML</span>
            </div>
            <p v-if="model.state.value !== 'workspace'" class="tgmd-subtitle-hint">导入 Kmsoft XML 分组模板文件后进行工步映射</p>
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
          <span class="tgmd-spinner" />
          <span>正在加载项目分组模板...</span>
        </div>

        <template v-else-if="showUploadState">
          <main class="tgmd-upload-state">
            <input ref="fileInput" class="tgmd-file-input" type="file" accept=".xml,application/xml,text/xml" @change="onFileInput">

            <!-- Drop Zone -->
            <button
              class="tgmd-dropzone"
              :class="{ 'tgmd-dropzone-ready': pendingFile, 'tgmd-dropzone-loading': model.loading.value }"
              type="button"
              :disabled="model.loading.value"
              @click="openFilePicker"
              @dragover.prevent
              @drop.prevent="onDrop"
            >
              <div class="tgmd-drop-icon-wrap">
                <span v-if="model.loading.value" class="tgmd-spinner" />
                <UploadFilled v-else class="tgmd-drop-icon" />
              </div>
              <div class="tgmd-drop-texts">
                <strong>{{ pendingFile ? pendingFile.name : '点击选择或拖入文件' }}</strong>
                <span class="tgmd-dropzone-sub">
                  {{ model.loading.value ? '正在解析模板结构...' : pendingFile ? formatBytes(pendingFile.size) : 'Kmsoft .xml 分组模板格式' }}
                </span>
              </div>
              <span v-if="!pendingFile && !model.loading.value" class="tgmd-drop-hint">拖拽到此</span>
            </button>

            <!-- Actions -->
            <div v-if="isReplacing || (pendingFile && visibleError)" class="tgmd-upload-actions">
              <button v-if="isReplacing" class="btn btn-outline" type="button" :disabled="model.loading.value" @click="cancelReplacement">取消更换</button>
              <button v-if="pendingFile && visibleError" class="btn btn-primary" type="button" @click="parsePendingFile">重新解析</button>
            </div>
          </main>
        </template>

        <template v-else-if="model.state.value === 'preview' && model.preview.value">
          <main class="tgmd-preview-state">

            <!-- Left: Summary Panel -->
            <section class="tgmd-preview-summary">

              <!-- File status card -->
              <div class="tgmd-preview-file-card" :class="model.preview.value.can_confirm ? 'is-ok' : 'is-err'">
                <div class="tgmd-preview-file-icon">
                  <DocumentChecked />
                </div>
                <div class="tgmd-preview-file-info">
                  <strong class="tgmd-preview-filename">{{ model.preview.value.original_filename }}</strong>
                  <span class="tgmd-preview-filedesc">{{ model.preview.value.can_confirm ? '校验全部通过，可正常投入映射使用' : '模板存在阻断性问题，请更换文件后重试' }}</span>
                </div>
                <span :class="['tgmd-validation-badge', model.preview.value.can_confirm ? 'is-valid' : 'is-invalid']">
                  {{ model.preview.value.can_confirm ? '校验通过' : '不可确认' }}
                </span>
              </div>

              <!-- Key Metrics Row -->
              <div class="tgmd-preview-metrics">
                <div class="tgmd-metric">
                  <span class="tgmd-metric-val tgmd-metric-accent">{{ model.preview.value.group_count }}</span>
                  <span class="tgmd-metric-label">分组数</span>
                </div>
                <div class="tgmd-metric">
                  <span class="tgmd-metric-val tgmd-metric-accent">{{ model.preview.value.feature_selection_count }}</span>
                  <span class="tgmd-metric-label">特征选择数</span>
                </div>
                <div class="tgmd-metric" :class="{ 'is-err': model.preview.value.validation_issues.length }">
                  <span class="tgmd-metric-val" :class="model.preview.value.validation_issues.length ? 'tgmd-metric-error' : 'tgmd-metric-ok'">
                    {{ model.preview.value.validation_issues.length }}
                  </span>
                  <span class="tgmd-metric-label">校验问题</span>
                </div>
              </div>

              <!-- Meta info rows -->
              <div class="tgmd-preview-meta">
                <div class="tgmd-meta-row">
                  <span class="tgmd-meta-key">字符编码</span>
                  <span class="tgmd-meta-val">{{ model.preview.value.source_encoding || 'UTF-8' }}</span>
                </div>
                <div class="tgmd-meta-row">
                  <span class="tgmd-meta-key">零件文件</span>
                  <span class="tgmd-meta-val">{{ model.preview.value.part_filename || '未标注' }}</span>
                </div>
              </div>

              <!-- Validation Issues -->
              <div v-if="model.preview.value.validation_issues.length" class="tgmd-issue-section">
                <div class="tgmd-issue-section-header">
                  <WarningFilled class="tgmd-issue-icon" />
                  <span>校验问题清单</span>
                  <span class="tgmd-issue-count">{{ model.preview.value.validation_issues.length }}</span>
                </div>
                <div class="tgmd-issue-list">
                  <div
                    v-for="(issue, index) in model.preview.value.validation_issues"
                    :key="`${issue.code}-${index}`"
                    class="tgmd-issue-row"
                  >
                    <span class="tgmd-issue-dot" />
                    <div class="tgmd-issue-body">
                      <strong>{{ issue.message }}</strong>
                      <span v-if="issue.path.length || issue.value" class="tgmd-issue-detail">{{ formatGroupTemplateIssueDetail(issue) }}</span>
                    </div>
                  </div>
                </div>
              </div>

              <!-- Replacement Impact -->
              <div v-if="isReplacing && model.replacementImpact.value" class="tgmd-impact">
                <div class="tgmd-impact-header">更换影响评估</div>
                <div class="tgmd-impact-stats">
                  <div class="tgmd-impact-stat is-keep">
                    <span class="tgmd-impact-num">{{ model.replacementImpact.value.kept_source_operation_ids.length }}</span>
                    <span class="tgmd-impact-desc">可保留映射</span>
                  </div>
                  <div class="tgmd-impact-stat is-lost">
                    <span class="tgmd-impact-num">{{ model.replacementImpact.value.invalidated.length }}</span>
                    <span class="tgmd-impact-desc">将失效映射</span>
                  </div>
                </div>
                <div v-if="model.replacementImpact.value.invalidated.length" class="tgmd-invalidated-list">
                  <div v-for="mapping in model.replacementImpact.value.invalidated" :key="mapping.source_operation_id" class="tgmd-invalidated-row">
                    <span class="tgmd-invalidated-op">{{ operationName(mapping.source_operation_id) }}</span>
                    <span class="tgmd-invalidated-path">{{ mapping.template_group_path.join(' › ') }}</span>
                  </div>
                </div>
              </div>

            </section>

            <!-- Right: Tree Preview -->
            <section class="tgmd-preview-tree" aria-label="模板分组预览">
              <header class="tgmd-section-header">
                <h3>分组结构预览</h3>
                <span>展现各级业务分组与关联特征</span>
              </header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in model.preview.value.tree"
                  :key="node.key"
                  :node="node"
                  :show-metadata="false"
                  show-feature-details
                  readonly
                />
              </div>
            </section>

          </main>
          <footer class="tgmd-footer">
            <div class="tgmd-footer-left">
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="resetPreviewSelection">重新选择文件</button>
              <button v-if="isReplacing" class="btn btn-outline" type="button" :disabled="model.saving.value" @click="cancelReplacement">取消更换</button>
            </div>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!model.preview.value.can_confirm || model.saving.value"
              @click="confirmPreview"
            >
              <DocumentChecked />
              {{ model.saving.value ? '正在确认...' : isReplacing ? '确认更换并进入映射' : '确认并进入映射' }}
            </button>
          </footer>
        </template>

        <template v-else-if="model.state.value === 'workspace' && model.template.value">
          <main class="tgmd-workspace">
            <section class="tgmd-pane tgmd-operation-pane">
              <header class="tgmd-pane-header tgmd-operation-header">
                <div class="tgmd-op-header-left">
                  <h3>工序与工步</h3>
                  <span class="tgmd-left-progress">已映射 {{ mappedStepCount }}/{{ eligibleStepKeys.size }}</span>
                  <span v-if="activeStep" class="tgmd-active-step-badge">{{ activeStep.step_name }}</span>
                  <span v-else class="tgmd-pane-subtitle">点击选中工步，勾选右侧特征后关联</span>
                </div>
                <div class="tgmd-operation-tools">
                  <div
                    v-if="recognizing || compactMappingWarnings.length"
                    class="tgmd-operation-status"
                    aria-live="polite"
                  >
                    <span v-if="recognizing" class="tgmd-status-pill is-live"><span class="tgmd-spinner tgmd-spinner-mini" />正在智能推荐...</span>
                    <span
                      v-for="notice in compactMappingWarnings"
                      :key="notice"
                      class="tgmd-status-pill"
                      :class="{ 'is-warning': notice.includes('失败') || notice.includes('未完成') }"
                      :title="mappingWarningDetail"
                    >{{ notice }}</span>
                  </div>
                  <button v-if="!recognizing" class="tgmd-smart-button" type="button" @click="suggestAllSteps">
                    <MagicStick />智能推荐
                  </button>
                </div>
              </header>

              <div class="tgmd-operation-scroll">
                <article v-for="operation in visibleMappingOperations" :key="operationId(operation)" class="tgmd-operation-card">
                  <button
                    class="tgmd-operation-toggle"
                    type="button"
                    @click="toggleOperationExpanded(operationId(operation))"
                  >
                    <div class="tgmd-op-title">
                      <ArrowRight :class="{ open: operationExpanded(operationId(operation)) }" />
                      <strong>{{ operation.name }}</strong>
                    </div>
                    <span class="tgmd-op-summary">{{ operationMappingSummary(operation) }}</span>
                  </button>
                  <div v-if="operationExpanded(operationId(operation))" class="tgmd-step-list">
                    <div
                      v-for="step in visibleStepsForOperation(operation)"
                      :key="step.step_key"
                      role="button"
                      tabindex="0"
                      class="tgmd-step-row"
                      :class="{ 'is-selected': activeStepKey === step.step_key, 'is-mapped': stepMappings(step).length }"
                      @click="activeStepKey = step.step_key"
                      @keydown.enter.prevent="activeStepKey = step.step_key"
                      @keydown.space.prevent="activeStepKey = step.step_key"
                    >
                      <span class="tgmd-step-order">{{ String(step.step_order).padStart(2, '0') }}</span>
                      <div class="tgmd-step-content">
                        <strong class="tgmd-step-name">{{ step.step_name }}</strong>
                        <small v-if="stepMappings(step).length && activeStepKey !== step.step_key" class="tgmd-step-mapping-summary">
                          {{ compactMappingSummary(step) }}
                        </small>
                        <small v-else-if="stepMappings(step).length" class="tgmd-step-count-text">{{ stepMappings(step).length }} 个已关联特征</small>
                        <div v-if="stepMappings(step).length && activeStepKey === step.step_key" class="tgmd-step-mappings">
                          <span v-for="mapping in stepMappings(step)" :key="stepMappingKey(mapping)" class="tgmd-chip-tag">
                            {{ mappingLabel(mapping) }}
                            <button type="button" title="解除关联" aria-label="解除关联" @click.stop="removeStepMapping(mapping)"><Close /></button>
                          </span>
                        </div>
                      </div>
                    </div>
                  </div>
                </article>
                <button class="tgmd-show-excluded" type="button" @click="showExcludedSteps = !showExcludedSteps">
                  {{ showExcludedSteps ? '收起其它辅助工步' : `显示其它辅助工步（${classifiedSteps.excluded.length}）` }}
                </button>
                <div v-if="!visibleMappingOperations.length" class="tgmd-empty">当前路线没有可关联的工步</div>
              </div>
            </section>

            <section class="tgmd-pane tgmd-tree-pane">
              <header class="tgmd-pane-header tgmd-tree-header">
                <div class="tgmd-tree-header-left">
                  <h3>模板分组</h3>
                </div>
                <div class="tgmd-tree-header-right">
                  <div class="tgmd-search-box">
                    <Search />
                    <input v-model="treeSearchQuery" placeholder="查找分组/特征..." type="text">
                    <button v-if="treeSearchQuery" class="tgmd-search-clear" type="button" @click="treeSearchQuery = ''"><Close /></button>
                  </div>
                  <button
                    class="tgmd-clear-selection"
                    type="button"
                    :disabled="!selectedFeatures.length"
                    title="清空已勾选的分组节点"
                    @click="clearSelectedFeatures"
                  >
                    <Close />清空勾选
                  </button>
                  <div
                    class="tgmd-link-wrapper"
                    @mouseenter="showLinkTooltip = true"
                    @mouseleave="showLinkTooltip = false"
                  >
                    <button
                      class="tgmd-link-btn"
                      type="button"
                      :disabled="!canLinkActiveStep"
                      :class="{ 'is-active': canLinkActiveStep }"
                      @click="linkActiveStep"
                    >
                      <ArrowLeft />
                      关联
                      <span v-if="selectedFeatures.length" class="tgmd-link-count">{{ selectedFeatures.length }}</span>
                    </button>

                    <!-- Custom Popover Tooltip -->
                    <Transition name="tgmd-popover-fade">
                      <div
                        v-if="showLinkTooltip && selectedFeatures.length"
                        class="tgmd-popover-card"
                        role="tooltip"
                      >
                        <div class="tgmd-popover-header">
                          <span class="tgmd-popover-title">已勾选特征</span>
                          <span class="tgmd-popover-badge">{{ selectedFeatures.length }} 项</span>
                        </div>
                        <div class="tgmd-popover-list">
                          <div
                            v-for="selection in selectedFeatures"
                            :key="templateFeatureSelectionKey(selection.leaf.key, selection.feature)"
                            class="tgmd-popover-item"
                          >
                            <span class="tgmd-popover-path">{{ selection.leaf.path.join(' › ') }}</span>
                            <span class="tgmd-popover-feature">{{ selection.feature }}</span>
                          </div>
                        </div>
                      </div>
                    </Transition>
                  </div>
                  <button class="tgmd-current-suggest" type="button" :disabled="recognizing || !selectedFeatures.length" title="按已选特征推荐匹配工步" @click="suggestActiveLeaf">
                    <MagicStick />推荐
                  </button>
                </div>
              </header>

              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode
                  v-for="node in displayTemplateTree"
                  :key="node.key"
                  :node="node"
                  :active-key="activeGroupKey"
                  :mapped-counts="mappedCounts"
                  :configured-leaf-keys="configuredLeafKeys"
                  :unconfigured-leaf-keys="unconfiguredLeafKeys"
                  :show-metadata="false"
                  multi-select
                  :selected-feature-keys="selectedFeatureKeys"
                  show-selected-features
                  show-feature-details
                  @select="activeGroupKey = $event"
                  @toggle-feature="toggleSelectedFeature"
                />
                <div v-if="!displayTemplateTree.length" class="tgmd-empty">没有匹配的模板特征或分组</div>
              </div>
            </section>
          </main>

          <footer class="tgmd-footer">
            <button class="tgmd-clear-all" type="button" :disabled="!Object.keys(draftStepMappings).length || model.saving.value" @click="clearMappings">
              <Delete />清空所有映射
            </button>
            <div class="tgmd-footer-actions">
              <button class="btn btn-outline" type="button" :disabled="model.saving.value" @click="closeDialog">取消</button>
              <button class="btn btn-primary" type="button" :disabled="model.saving.value || recognizing" @click="saveStepMappings">
                <Link />{{ model.saving.value ? '正在保存...' : '保存工步映射' }}
              </button>
            </div>
          </footer>
        </template>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import {
  ArrowLeft,
  ArrowRight,
  Close,
  Delete,
  DocumentChecked,
  Link,
  MagicStick,
  RefreshRight,
  Search,
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
  buildTemplateRouteStructureOperations,
  findTemplateGroupByKey,
  openTemplateGroupFilePicker,
  type TemplateAliasBinding,
  type TemplateGroupNode,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'
import {
  buildTemplateStepRefs,
  buildTemplateStepRouteFingerprint,
  chunkTemplateSuggestionOperations,
  clearTemplateStepMappingDraft,
  confirmedMappingsForStep,
  createTemplateStepMapping,
  mergeTemplateStepMapping,
  isFeatureLeaf,
  loadTemplateStepMappingDraft,
  recommendedFeaturesForSelection,
  selectedTemplateFeatures,
  saveTemplateStepMappingDraft,
  settleTemplateSuggestionBatches,
  stepMappingKey,
  templateFeatureSelectionKey,
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
const selectedFeatureKeys = ref<string[]>([])
const activeStepKey = ref('')
const recognizing = ref(false)
const recommendationProgress = ref('正在推荐')
const dialogRunId = ref(0)
const mappingWarnings = ref<string[]>([])
const showExcludedSteps = ref(false)
const treeSearchQuery = ref('')
const showLinkTooltip = ref(false)

function filterTreeNode(node: TemplateGroupNode, query: string): TemplateGroupNode | null {
  const q = query.trim().toLowerCase()
  if (!q) return node
  const matchesSelf = node.name.toLowerCase().includes(q) ||
    node.feature_selections.some(f => f.toLowerCase().includes(q))

  const filteredChildren = node.children
    .map(child => filterTreeNode(child, query))
    .filter((child): child is TemplateGroupNode => child !== null)

  if (matchesSelf || filteredChildren.length > 0) {
    return {
      ...node,
      children: filteredChildren,
    }
  }
  return null
}

const displayTemplateTree = computed(() => {
  const rootTree = model.template.value?.tree || []
  if (!treeSearchQuery.value.trim()) return rootTree
  return rootTree
    .map(node => filterTreeNode(node, treeSearchQuery.value))
    .filter((node): node is TemplateGroupNode => node !== null)
})

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
const visibleMappingOperations = computed(() => mappingOperations.value.filter(operation => (
  visibleStepsForOperation(operation).length > 0
)))
const selectedFeatures = computed(() => selectedTemplateFeatures(
  model.template.value?.tree || [],
  selectedFeatureKeys.value,
))
const mappingsByLeaf = computed(() => groupConfirmedMappingsByLeaf(
  Object.values(draftStepMappings.value),
  model.template.value?.tree || [],
))
const leafConfiguration = computed(() => featureLeafConfiguration(
  model.template.value?.tree || [],
  Object.values(draftStepMappings.value),
))
const configuredLeafKeys = computed(() => leafConfiguration.value.configured.map(leaf => leaf.key))
const unconfiguredLeafKeys = computed(() => leafConfiguration.value.unconfigured.map(leaf => leaf.key))
const mappedCounts = computed(() => Object.entries(mappingsByLeaf.value).reduce<Record<string, number>>((counts, [key, mappings]) => {
  counts[key] = mappings.length
  return counts
}, {}))
const activeStep = computed(() => stepRefs.value.find(step => step.step_key === activeStepKey.value) || null)
const mappedStepCount = computed(() => classifiedSteps.value.eligible.filter(step => stepMappings(step).length > 0).length)
const canLinkActiveStep = computed(() => Boolean(
  activeStep.value
  && selectedFeatures.value.some(({ leaf, feature }) => !stepMappings(activeStep.value!).some(mapping => (
    JSON.stringify(mapping.template_group_path) === JSON.stringify(leaf.path)
    && mapping.candidate_features.includes(feature)
  ))),
))
const mappingWarningDetail = computed(() => mappingWarnings.value.join('；'))
const compactMappingWarnings = computed(() => {
  const compact = mappingWarnings.value.map(compactMappingWarning).filter(Boolean)
  return [...new Set(compact)].slice(0, 4)
})

watch(() => props.modelValue, async (visible) => {
  dialogRunId.value += 1
  recognizing.value = false
  recommendationProgress.value = '正在推荐'
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

function compactMappingWarning(value: string) {
  const text = String(value || '').trim()
  if (!text) return ''
  const added = text.match(/已关联\s*(\d+)\s*条/)
  if (added) return `新增 ${added[1]}`
  const supplemented = text.match(/已补充\s*(\d+)\s*条/)
  if (supplemented) return `补充 ${supplemented[1]}`
  const preserved = text.match(/已保留\s*(\d+)\s*条/)
  if (preserved) return `保留已有 ${preserved[1]}`
  const failedBatch = text.match(/(\d+)\s*批推荐未完成/)
  if (failedBatch) return `未完成 ${failedBatch[1]} 批`
  if (text.includes('模型调用失败')) return '部分需手动确认'
  if (text.includes('模型未返回有效结构化结果')) return '部分需手动确认'
  return text.length > 16 ? `${text.slice(0, 16)}…` : text
}

function syncDraftFromTemplate() {
  const template = model.template.value
  if (!template) {
    draftStepMappings.value = {}
    activeGroupKey.value = ''
    selectedFeatureKeys.value = []
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
  selectedFeatureKeys.value = []
  const firstEligibleStep = classifiedSteps.value.eligible[0]
  activeStepKey.value = stepRefs.value.some(step => step.step_key === activeStepKey.value)
    ? activeStepKey.value
    : firstEligibleStep?.step_key || ''
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

function operationMappingSummary(operation: TemplateOperation) {
  const steps = stepRefsForOperation(operation).filter(step => eligibleStepKeys.value.has(step.step_key))
  const mapped = steps.filter(step => stepMappings(step).length > 0).length
  return `已映射 ${mapped}/${steps.length}`
}

function stepMappings(step: TemplateStepRef) {
  return confirmedMappingsForStep(draftStepMappings.value, step)
}

function mappingLabel(mapping: GroupTemplateStepMappingInput) {
  const featureText = mapping.candidate_features.join('、')
  return featureText
    ? `${mapping.template_group_path.join(' / ')} · ${featureText}`
    : mapping.template_group_path.join(' / ')
}

function compactMappingSummary(step: TemplateStepRef) {
  const mappings = stepMappings(step)
  if (!mappings.length) return ''
  const first = mappings[0]!.template_group_path.join(' / ')
  return mappings.length === 1 ? first : `${first} 等 ${mappings.length} 项`
}

function toggleSelectedFeature(selection: { leafKey: string; feature: string }) {
  const candidate = model.template.value
    ? findTemplateGroupByKey(model.template.value.tree, selection.leafKey)
    : null
  if (!candidate || !isFeatureLeaf(candidate) || !candidate.feature_selections.includes(selection.feature)) return
  const key = templateFeatureSelectionKey(selection.leafKey, selection.feature)
  const selected = new Set(selectedFeatureKeys.value)
  if (selected.has(key)) selected.delete(key)
  else selected.add(key)
  selectedFeatureKeys.value = [...selected]
  activeGroupKey.value = selection.leafKey
}

function clearSelectedFeatures() {
  selectedFeatureKeys.value = []
}

function linkActiveStep() {
  const step = activeStep.value
  if (!step || !canLinkActiveStep.value) return
  let added = false
  const selectionsByLeaf = new Map<string, { leaf: GroupTemplateNode; features: string[] }>()
  selectedFeatures.value.forEach(({ leaf, feature }) => {
    const existing = selectionsByLeaf.get(leaf.key)
    if (existing) existing.features.push(feature)
    else selectionsByLeaf.set(leaf.key, { leaf, features: [feature] })
  })
  selectionsByLeaf.forEach(({ leaf, features }) => {
    const mapping = createTemplateStepMapping(step, leaf, leaf.path.slice(0, -1), 'user_confirmed', 1, features)
    const key = stepMappingKey(mapping)
    const existing = draftStepMappings.value[key]
    if (existing) {
      const mergedFeatures = [...new Set([...existing.candidate_features, ...features])]
      if (mergedFeatures.length === existing.candidate_features.length) return
      draftStepMappings.value[key] = { ...existing, candidate_features: mergedFeatures }
    } else draftStepMappings.value[key] = mapping
    added = true
  })
  if (added) persistStepDraft()
}

function removeStepMapping(mapping: GroupTemplateStepMappingInput) {
  delete draftStepMappings.value[stepMappingKey(mapping)]
  persistStepDraft()
}

function clearMappings() {
  draftStepMappings.value = {}
  persistStepDraft()
}

function suggestionOperations() {
  return mappingOperations.value.map(operation => ({
    operation_id: operationId(operation),
    operation_name: operation.name,
    // Keep original positions so the server's stable step keys still match the route.
    step_items: (operation.step_items || []).map((step, index) => {
      const ref = stepRefsForOperation(operation).find(item => item.step_order === index + 1)
      return ref && eligibleStepKeys.value.has(ref.step_key) ? step : ''
    }),
    rule_evidence: [],
    rule_reasons: [],
  }))
}

function mappingOutputOperations() {
  return buildTemplateRouteStructureOperations(props.operations)
}

function applySuggestedMappings(
  suggestions: Awaited<ReturnType<typeof suggestTemplateStepMappings>>['suggestions'],
  targetLeafKeys?: string[],
) {
  const tree = model.template.value?.tree || []
  let added = 0
  let supplemented = 0
  let preserved = 0
  suggestions.forEach((suggestion) => {
    const step = stepRefs.value.find(item => item.step_key === suggestion.step_key)
    if (!step || !suggestion.recommended_group_ids.length) return
    suggestion.recommended_group_ids.forEach((groupId) => {
      if (targetLeafKeys?.length && !targetLeafKeys.includes(groupId)) return
      const leaf = findTemplateGroupByKey(tree, groupId)
      if (!isFeatureLeaf(leaf)) return
      const featureLeaf = leaf as GroupTemplateNode
      const rawFeatures = suggestion.recommended_features_by_group[groupId] || []
      const features = targetLeafKeys?.length
        ? recommendedFeaturesForSelection(groupId, rawFeatures, selectedFeatures.value)
        : rawFeatures
      if (!features.length) return
      const mapping = createTemplateStepMapping(
        step,
        featureLeaf,
        featureLeaf.path.slice(0, -1),
        'auto_confirmed',
        suggestion.confidence,
        features,
      )
      const key = stepMappingKey(mapping)
      const existing = draftStepMappings.value[key]
      if (!existing) {
        draftStepMappings.value[key] = mapping
        added += 1
        return
      }
      const merged = mergeTemplateStepMapping(existing, mapping)
      if (!merged) {
        preserved += 1
        return
      }
      draftStepMappings.value[key] = merged
      supplemented += 1
    })
  })
  if (added) persistStepDraft()
  if (supplemented) persistStepDraft()
  return { added, supplemented, preserved }
}

async function suggestSteps(targetLeafKeys?: string[]) {
  if (recognizing.value || !model.template.value) return
  if (targetLeafKeys?.length && !selectedFeatures.value.length) return
  const runId = ++dialogRunId.value
  recognizing.value = true
  recommendationProgress.value = '正在准备推荐'
  mappingWarnings.value = []
  try {
    const batches = chunkTemplateSuggestionOperations(suggestionOperations(), 10)
    const responseWarnings: string[] = []
    let failedBatchCount = 0
    let added = 0
    let supplemented = 0
    let preserved = 0
    const updateRecommendationWarnings = () => {
      mappingWarnings.value = [
        ...responseWarnings,
        ...(failedBatchCount ? [`${failedBatchCount} 批推荐未完成，可再次点击补充未映射工步。`] : []),
        ...(added ? [`已关联 ${added} 条智能推荐。`] : []),
        ...(supplemented ? [`已补充 ${supplemented} 条遗漏特征。`] : []),
        ...(preserved ? [`已保留 ${preserved} 条已有特征关联。`] : []),
      ]
    }
    const applyResponse = (response: Awaited<ReturnType<typeof suggestTemplateStepMappings>>) => {
      if (runId !== dialogRunId.value || !props.modelValue) return
      responseWarnings.push(...(response.warnings || []))
      const result = applySuggestedMappings(response.suggestions, targetLeafKeys)
      added += result.added
      supplemented += result.supplemented
      preserved += result.preserved
      updateRecommendationWarnings()
    }
    const batchSize = 3
    for (let start = 0; start < batches.length; start += batchSize) {
      const currentBatches = batches.slice(start, start + batchSize)
      recommendationProgress.value = `正在推荐 ${Math.min(start + 1, batches.length)}-${Math.min(start + currentBatches.length, batches.length)} / ${batches.length}`
      const settled = await settleTemplateSuggestionBatches(currentBatches, operations => suggestTemplateStepMappings({
        project_id: props.projectId,
        expected_template_revision: model.templateRevision.value,
        ...(targetLeafKeys?.length ? { target_group_ids: targetLeafKeys } : {}),
        include_llm: !targetLeafKeys?.length,
        operations,
      }), applyResponse)
      failedBatchCount += settled.failedCount
      updateRecommendationWarnings()
    }
    if (runId !== dialogRunId.value || !props.modelValue) return
    updateRecommendationWarnings()
  } catch {
    if (runId !== dialogRunId.value || !props.modelValue) return
    mappingWarnings.value = ['智能推荐暂时不可用，已保留当前映射和人工操作。']
  } finally {
    if (runId === dialogRunId.value && props.modelValue) {
      recognizing.value = false
      recommendationProgress.value = '正在推荐'
    }
  }
}

async function suggestActiveLeaf() {
  const selectedLeafKeys = [...new Set(selectedFeatures.value.map(({ leaf }) => leaf.key))]
  if (!selectedLeafKeys.length) return
  await suggestSteps(selectedLeafKeys)
}

async function suggestAllSteps() {
  await suggestSteps()
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
  await model.saveStepMappings(mappingOutputOperations())
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
  recommendationProgress.value = '正在推荐'
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  emit('update:modelValue', false)
}
</script>

<style scoped>
.tgmd-backdrop {
  position: fixed;
  inset: 0;
  z-index: 3000;
  display: grid;
  place-items: center;
  padding: 12px;
  background: rgba(15, 23, 42, 0.45);
  backdrop-filter: blur(4px);
}

.tgmd-dialog {
  width: min(960px, calc(100vw - 48px));
  height: min(680px, calc(100vh - 64px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid #cbd5e1;
  border-radius: 8px;
  background: #f8fafc;
  box-shadow: 0 16px 36px rgba(15, 23, 42, 0.2);
  color: #0f172a;
  transition: all 180ms ease;
}

/* Compact modal specifically for file upload state */
.tgmd-dialog.is-compact-upload {
  width: min(480px, calc(100vw - 32px));
  height: auto;
  min-height: auto;
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.2);
}

/* Header */
.tgmd-header {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid #e2e8f0;
  background: #ffffff;
}

.tgmd-title-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.tgmd-title-row {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tgmd-title-row h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
  color: #0f172a;
}

.tgmd-title-tag {
  padding: 1px 7px;
  border-radius: 4px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 10px;
  font-weight: 600;
  border: 1px solid #c7d2fe;
  white-space: nowrap;
}

.tgmd-file-inline {
  min-width: 0;
  overflow: hidden;
  color: #475569;
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-operation-status {
  min-height: 20px;
  margin: 0;
  display: flex;
  align-items: center;
  gap: 4px;
  min-width: 0;
  flex-shrink: 1;
  overflow: hidden;
  color: #64748b;
}

.tgmd-status-pill {
  min-width: 0;
  max-width: 110px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border: 1px solid #e2e8f0;
  border-radius: 999px;
  background: #f8fafc;
  color: #475569;
  font-size: 10px;
  font-weight: 600;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.tgmd-status-pill.is-live {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #4338ca;
}

.tgmd-status-pill.is-warning {
  border-color: #fed7aa;
  background: #fff7ed;
  color: #c2410c;
}

.tgmd-file-info {
  margin: 2px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 11px;
}

.tgmd-file-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: #334155;
  font-weight: 500;
}

.tgmd-file-badge svg {
  width: 13px;
  height: 13px;
  color: #6366f1;
}

.tgmd-part-badge {
  color: #64748b;
  padding-left: 8px;
  border-left: 1px solid #cbd5e1;
}

.tgmd-subtitle-hint {
  margin: 2px 0 0;
  color: #64748b;
  font-size: 11px;
}

.tgmd-header-actions,
.tgmd-operation-tools,
.tgmd-footer-actions,
.tgmd-upload-actions {
  display: flex;
  align-items: center;
  gap: 6px;
}

.tgmd-operation-tools {
  min-width: 0;
}

.tgmd-command,
.tgmd-icon-button,
.tgmd-smart-button,
.tgmd-clear-all {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  color: #334155;
  cursor: pointer;
  transition: all 120ms ease;
}

.tgmd-command {
  min-height: 28px;
  padding: 0 9px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 500;
}

.tgmd-command:hover {
  border-color: #c7d2fe;
  background: #eef2ff;
  color: #4338ca;
}

.tgmd-command svg,
.tgmd-smart-button svg,
.tgmd-clear-all svg,
.btn svg {
  width: 14px;
  height: 14px;
}

.tgmd-icon-button {
  width: 28px;
  height: 28px;
  border-radius: 5px;
  border: 1px solid #e2e8f0;
  color: #64748b;
}

.tgmd-icon-button:hover {
  border-color: #cbd5e1;
  background: #f1f5f9;
  color: #0f172a;
}

.tgmd-icon-button svg {
  width: 16px;
  height: 16px;
}

.tgmd-inline-error {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  border-bottom: 1px solid #fecaca;
  background: #fef2f2;
  color: #991b1b;
  font-size: 11px;
  font-weight: 500;
}

.tgmd-inline-error svg {
  width: 15px;
  height: 15px;
  flex: 0 0 auto;
}

.tgmd-loading {
  padding: 40px 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 10px;
  color: #64748b;
  font-size: 13px;
}

.tgmd-spinner {
  width: 18px;
  height: 18px;
  display: inline-block;
  border: 2px solid #cbd5e1;
  border-top-color: #6366f1;
  border-radius: 50%;
  animation: tgmd-spin 0.8s linear infinite;
}

.tgmd-spinner-mini {
  width: 12px;
  height: 12px;
  border-width: 1.5px;
}

.tgmd-spinner-light {
  border-color: rgba(255, 255, 255, 0.45);
  border-top-color: #fff;
}

@keyframes tgmd-spin {
  to {
    transform: rotate(360deg);
  }
}

/* Upload State - Compact & System Consistent */
.tgmd-upload-state {
  display: flex;
  flex-direction: column;
  align-items: stretch;
  gap: 0;
  padding: 20px;
}

.tgmd-file-input {
  display: none;
}

.tgmd-dropzone {
  width: 100%;
  padding: 18px 20px;
  display: flex;
  flex-direction: row;
  align-items: center;
  justify-content: flex-start;
  gap: 16px;
  border: 1.5px dashed #c7d2fe;
  border-radius: 8px;
  background: #fafafa;
  color: #334155;
  cursor: pointer;
  transition: all 150ms ease;
  text-align: left;
}

.tgmd-dropzone:hover,
.tgmd-dropzone-ready {
  border-color: #6366f1;
  background: #eef2ff;
}

.tgmd-drop-icon-wrap {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #eef2ff;
  color: #6366f1;
  transition: all 150ms ease;
}

.tgmd-dropzone:hover .tgmd-drop-icon-wrap,
.tgmd-dropzone-ready .tgmd-drop-icon-wrap {
  background: #e0e7ff;
}

.tgmd-drop-icon {
  width: 20px;
  height: 20px;
  color: inherit;
}

.tgmd-drop-texts {
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tgmd-dropzone strong {
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  line-height: 1.3;
}

.tgmd-dropzone-sub {
  color: #64748b;
  font-size: 11px;
  line-height: 1.4;
}

.tgmd-upload-actions {
  width: 100%;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  margin-top: 12px;
}

/* Preview State */
.tgmd-preview-state {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: 320px minmax(0, 1fr);
  gap: 0;
  overflow: hidden;
}

.tgmd-preview-summary {
  min-height: 0;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 0;
  border-right: 1px solid #e2e8f0;
  background: #fafafa;
}

/* File Status Card */
.tgmd-preview-file-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 16px 14px;
  border-bottom: 1px solid #e2e8f0;
}

.tgmd-preview-file-card.is-ok {
  background: linear-gradient(135deg, #f0fdf4 0%, #ffffff 60%);
  border-bottom-color: #bbf7d0;
}

.tgmd-preview-file-card.is-err {
  background: linear-gradient(135deg, #fff1f2 0%, #ffffff 60%);
  border-bottom-color: #fecdd3;
}

.tgmd-preview-file-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: #eef2ff;
}

.tgmd-preview-file-card.is-ok .tgmd-preview-file-icon {
  background: #d1fae5;
}

.tgmd-preview-file-card.is-err .tgmd-preview-file-icon {
  background: #ffe4e6;
}

.tgmd-preview-file-icon svg {
  width: 18px;
  height: 18px;
  color: #6366f1;
}

.tgmd-preview-file-card.is-ok .tgmd-preview-file-icon svg {
  color: #059669;
}

.tgmd-preview-file-card.is-err .tgmd-preview-file-icon svg {
  color: #e11d48;
}

.tgmd-preview-file-info {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 3px;
}

.tgmd-preview-filename {
  display: block;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tgmd-preview-filedesc {
  display: block;
  font-size: 11px;
  color: #64748b;
  line-height: 1.4;
}

.tgmd-validation-badge {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 11px;
  font-weight: 700;
  white-space: nowrap;
}

.tgmd-validation-badge.is-valid {
  background: #dcfce7;
  color: #15803d;
  border: 1px solid #86efac;
}

.tgmd-validation-badge.is-invalid {
  background: #fff1f2;
  color: #be123c;
  border: 1px solid #fecdd3;
}

/* Key Metrics - 3 columns, big numbers */
.tgmd-preview-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid #e2e8f0;
}

.tgmd-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 14px 8px;
  gap: 4px;
  border-right: 1px solid #e2e8f0;
}

.tgmd-metric:last-child {
  border-right: 0;
}

.tgmd-metric-val {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  color: #1e293b;
}

.tgmd-metric-accent {
  color: #4f46e5;
}

.tgmd-metric-ok {
  color: #059669;
}

.tgmd-metric-error {
  color: #e11d48;
}

.tgmd-metric-label {
  font-size: 10px;
  font-weight: 600;
  color: #94a3b8;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* Meta info rows */
.tgmd-preview-meta {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid #e2e8f0;
}

.tgmd-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid #f1f5f9;
}

.tgmd-meta-row:last-child {
  border-bottom: 0;
}

.tgmd-meta-key {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
}

.tgmd-meta-val {
  font-size: 12px;
  font-weight: 600;
  color: #334155;
  max-width: 60%;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  text-align: right;
}

/* Issue Section */
.tgmd-issue-section {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid #e2e8f0;
}

.tgmd-issue-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: #fff7ed;
  border-bottom: 1px solid #fed7aa;
  font-size: 12px;
  font-weight: 600;
  color: #c2410c;
}

.tgmd-issue-icon {
  width: 14px;
  height: 14px;
  flex: 0 0 auto;
}

.tgmd-issue-count {
  margin-left: auto;
  padding: 1px 6px;
  border-radius: 10px;
  background: #c2410c;
  color: #ffffff;
  font-size: 10px;
  font-weight: 700;
}

.tgmd-issue-list {
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: #fffdfa;
}

.tgmd-issue-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid #ffedd5;
  font-size: 11px;
}

.tgmd-issue-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  border-radius: 50%;
  background: #ea580c;
  margin-top: 5px;
}

.tgmd-issue-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tgmd-issue-body strong {
  font-weight: 600;
  color: #9f1239;
}

.tgmd-issue-detail {
  color: #c2410c;
  font-size: 10px;
}

/* Impact section */
.tgmd-impact {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid #e2e8f0;
}

.tgmd-impact-header {
  font-size: 11px;
  font-weight: 700;
  color: #64748b;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.tgmd-impact-stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
}

.tgmd-impact-stat {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 10px;
  border-radius: 6px;
  gap: 3px;
}

.tgmd-impact-stat.is-keep {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
}

.tgmd-impact-stat.is-lost {
  background: #fff7ed;
  border: 1px solid #fed7aa;
}

.tgmd-impact-num {
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

.tgmd-impact-stat.is-keep .tgmd-impact-num {
  color: #15803d;
}

.tgmd-impact-stat.is-lost .tgmd-impact-num {
  color: #c2410c;
}

.tgmd-impact-desc {
  font-size: 10px;
  font-weight: 600;
  color: #64748b;
}

.tgmd-invalidated-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-top: 4px;
}

.tgmd-invalidated-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 5px 10px;
  border-radius: 4px;
  background: #fff7ed;
  font-size: 11px;
}

.tgmd-invalidated-op {
  font-weight: 600;
  color: #1e293b;
}

.tgmd-invalidated-path {
  color: #94a3b8;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

/* Preview Tree */
.tgmd-preview-tree,
.tgmd-pane {
  min-height: 0;
  border: 0;
  border-radius: 0;
  background: #ffffff;
}

.tgmd-preview-tree {
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.tgmd-section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-bottom: 1px solid #e2e8f0;
  background: #fafafa;
}

.tgmd-section-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.tgmd-section-header span {
  color: #94a3b8;
  font-size: 11px;
}

.tgmd-tree-scroll {
  min-height: 0;
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  padding: 6px 10px 6px 6px;
}

/* Workspace Layout - 2-column */
.tgmd-workspace {
  min-height: 0;
  flex: 1;
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1fr);
  gap: 0;
  margin: 8px 10px;
  overflow: hidden;
  border: 1px solid #dbe3ec;
  border-radius: 7px;
  background: #ffffff;
}

.tgmd-pane {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: #ffffff;
}

.tgmd-operation-pane {
  border-right: 1px solid #dbe3ec;
}

.tgmd-pane-header {
  min-height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid #e2e8f0;
  background: #fafafa;
  border-radius: 0;
}

.tgmd-pane-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: #0f172a;
}

.tgmd-pane-subtitle {
  color: #94a3b8;
  font-size: 11px;
  white-space: nowrap;
}

/* Active step badge in left header */
.tgmd-op-header-left {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.tgmd-left-progress {
  flex: 0 0 auto;
  padding: 1px 6px;
  border: 1px solid #c7d2fe;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 10px;
  font-weight: 700;
  line-height: 17px;
  white-space: nowrap;
}

.tgmd-active-step-badge {
  max-width: 100px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef2ff;
  border: 1px solid #c7d2fe;
  color: #4338ca;
  font-size: 10px;
  font-weight: 600;
  line-height: 17px;
  flex-shrink: 1;
}

/* Tree header layout */
.tgmd-tree-header {
  flex-wrap: nowrap;
  gap: 8px;
}

.tgmd-tree-header-left {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 6px;
}

.tgmd-tree-header-right {
  flex: 0 0 auto;
  display: flex;
  align-items: center;
  gap: 5px;
}

.tgmd-tree-header-tools {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* Search Box */
.tgmd-search-box {
  position: relative;
  width: 132px;
  height: 26px;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 6px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #f8fafc;
  transition: all 120ms ease;
}

.tgmd-search-box:focus-within {
  border-color: #6366f1;
  background: #ffffff;
}

.tgmd-search-box svg {
  width: 12px;
  height: 12px;
  color: #64748b;
  flex: 0 0 auto;
}

.tgmd-search-box input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: 11px;
  color: #0f172a;
}

.tgmd-search-clear {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
  padding: 0;
}

.tgmd-search-clear:hover {
  color: #475569;
}

.tgmd-selected-inline {
  min-width: 0;
  overflow: hidden;
  color: #475569;
  font-size: 11px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-selected-inline {
  color: #3730a3;
}

.tgmd-smart-button {
  height: 26px;
  padding: 0 9px;
  border-color: #c7d2fe;
  border-radius: 4px;
  color: #4338ca;
  background: #eef2ff;
  font-size: 11px;
  font-weight: 600;
}

.tgmd-smart-button:hover:not(:disabled) {
  background: #e0e7ff;
  border-color: #818cf8;
}

.tgmd-smart-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

/* Link Button (inline in tree header) */
.tgmd-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 5px;
  border: 1px solid #cbd5e1;
  background: #f1f5f9;
  color: #94a3b8;
  font-size: 11px;
  font-weight: 600;
  cursor: not-allowed;
  transition: all 150ms ease;
  white-space: nowrap;
}

.tgmd-link-btn svg {
  width: 13px;
  height: 13px;
}

.tgmd-link-btn.is-active {
  border-color: #6366f1;
  background: #4f46e5;
  color: #ffffff;
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(79, 70, 229, 0.3);
}

.tgmd-link-btn.is-active:hover {
  background: #4338ca;
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.32);
}

.tgmd-link-count {
  display: inline-grid;
  place-items: center;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 999px;
  background: rgba(255, 255, 255, 0.25);
  color: inherit;
  font-size: 10px;
  font-weight: 700;
  line-height: 1;
}

/* Custom Link Popover Card */
.tgmd-link-wrapper {
  position: relative;
  display: inline-flex;
}

.tgmd-popover-card {
  position: absolute;
  top: calc(100% + 6px);
  right: 0;
  z-index: 50;
  width: max-content;
  max-width: 320px;
  padding: 8px 10px;
  border-radius: 7px;
  border: 1px solid #cbd5e1;
  background: #ffffff;
  box-shadow: 0 10px 25px -4px rgba(15, 23, 42, 0.16), 0 4px 10px -2px rgba(15, 23, 42, 0.08);
  font-size: 11px;
  color: #0f172a;
  pointer-events: none;
}

.tgmd-popover-card::before {
  content: '';
  position: absolute;
  top: -5px;
  right: 18px;
  width: 8px;
  height: 8px;
  background: #ffffff;
  border-left: 1px solid #cbd5e1;
  border-top: 1px solid #cbd5e1;
  transform: rotate(45deg);
}

.tgmd-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 5px;
  margin-bottom: 5px;
  border-bottom: 1px solid #f1f5f9;
}

.tgmd-popover-title {
  font-weight: 700;
  color: #1e293b;
  font-size: 11px;
}

.tgmd-popover-badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: #eef2ff;
  color: #4338ca;
  font-size: 10px;
  font-weight: 700;
}

.tgmd-popover-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
  max-height: 180px;
  overflow-y: auto;
}

.tgmd-popover-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 3px 6px;
  border-radius: 4px;
  background: #f8fafc;
}

.tgmd-popover-path {
  color: #64748b;
  font-size: 10px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-popover-feature {
  flex-shrink: 0;
  font-weight: 600;
  color: #3730a3;
  background: #e0e7ff;
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 10px;
}

.tgmd-popover-fade-enter-active,
.tgmd-popover-fade-leave-active {
  transition: opacity 120ms ease, transform 120ms ease;
}

.tgmd-popover-fade-enter-from,
.tgmd-popover-fade-leave-to {
  opacity: 0;
  transform: translateY(-3px);
}

/* Operation Pane */
.tgmd-operation-scroll {
  min-height: 0;
  flex: 1;
  overflow: auto;
  padding: 5px;
}

/* Operation card */
.tgmd-operation-card {
  margin-bottom: 3px;
  border: 1px solid #e8edf2;
  border-radius: 5px;
  background: #ffffff;
  overflow: hidden;
}

.tgmd-operation-toggle {
  width: 100%;
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 8px;
  border: 0;
  background: #f8fafc;
  color: #0f172a;
  text-align: left;
  cursor: pointer;
  transition: background-color 120ms ease;
  position: relative;
}

.tgmd-operation-toggle:hover {
  background: #f1f5f9;
}

.tgmd-op-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.tgmd-op-title svg {
  width: 12px;
  height: 12px;
  color: #64748b;
  transition: transform 150ms ease;
  flex: 0 0 auto;
}

.tgmd-op-title svg.open {
  transform: rotate(90deg);
}

.tgmd-op-title strong {
  font-size: 11px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-op-summary {
  color: #64748b;
  font-size: 10px;
  flex: 0 0 auto;
}

.tgmd-step-list {
  border-top: 1px solid #f1f5f9;
}

.tgmd-step-row {
  position: relative;
  min-height: 28px;
  display: grid;
  grid-template-columns: 22px minmax(0, 1fr);
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-bottom: 1px solid #f8fafc;
  background: #ffffff;
  color: #334155;
  cursor: pointer;
  outline: 0;
  transition: all 120ms ease;
}

.tgmd-step-row:last-child {
  border-bottom: 0;
}

.tgmd-step-row:hover {
  background: #f8fbff;
}

/* Active Step - Matches SourceRoutePanel srp-op--active */
.tgmd-step-row.is-selected {
  background: #eef2ff;
  box-shadow: inset 3px 0 #6366f1;
}

.tgmd-step-row.is-mapped:not(.is-selected) {
  box-shadow: inset 3px 0 #10b981;
}

/* Monospace Step Order Badge - Matches srp-op-seq */
.tgmd-step-order {
  width: 22px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  background: #f1f5f9;
  color: #475569;
  font: 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
}

.tgmd-step-row.is-selected .tgmd-step-order {
  background: #6366f1;
  color: #ffffff;
}

.tgmd-step-content {
  min-width: 0;
}

.tgmd-step-name {
  display: block;
  font-size: 11px;
  font-weight: 600;
  color: #1e293b;
  line-height: 1.3;
}

.tgmd-step-count-text {
  display: block;
  margin-top: 2px;
  color: #059669;
  font-size: 10px;
  font-weight: 500;
}

.tgmd-step-unmapped-text {
  display: block;
  margin-top: 2px;
  color: #b0b8c4;
  font-size: 10px;
  font-style: italic;
}

.tgmd-step-mapping-summary {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: #6366f1;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-step-mappings {
  display: flex;
  flex-wrap: wrap;
  gap: 3px;
  margin-top: 4px;
}

.tgmd-chip-tag {
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 3px;
  padding: 1px 5px;
  border: 1px solid #a7f3d0;
  border-radius: 4px;
  background: #ecfdf5;
  color: #047857;
  font-size: 10px;
  font-weight: 500;
}

.tgmd-chip-tag button {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  padding: 0;
  border: 0;
  border-radius: 50%;
  background: transparent;
  color: #059669;
  cursor: pointer;
}

.tgmd-chip-tag button:hover {
  background: #d1fae5;
  color: #047857;
}

.tgmd-chip-tag svg {
  width: 10px;
  height: 10px;
}

.tgmd-current-suggest {
  flex-shrink: 0;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid #c7d2fe;
  border-radius: 4px;
  background: #ffffff;
  color: #4338ca;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
  margin-left: 4px;
}

.tgmd-current-suggest:hover:not(:disabled) {
  background: #eef2ff;
  border-color: #a5b4fc;
}

.tgmd-current-suggest:disabled {
  color: #94a3b8;
  border-color: #e2e8f0;
  background: #f8fafc;
  cursor: not-allowed;
}

.tgmd-current-suggest svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.tgmd-clear-selection {
  flex-shrink: 0;
  white-space: nowrap;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  height: 26px;
  padding: 0 8px;
  border: 1px solid #cbd5e1;
  border-radius: 4px;
  background: #ffffff;
  color: #64748b;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
}

.tgmd-clear-selection:hover:not(:disabled) {
  border-color: #fecdd3;
  background: #fff1f2;
  color: #be123c;
}

.tgmd-clear-selection:disabled {
  color: #94a3b8;
  border-color: #e2e8f0;
  background: #f8fafc;
  cursor: not-allowed;
}

.tgmd-clear-selection svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.tgmd-empty {
  padding: 18px 12px;
  color: #94a3b8;
  text-align: center;
  font-size: 12px;
}

.tgmd-show-excluded {
  width: calc(100% - 12px);
  margin: 4px 6px 6px;
  padding: 4px 6px;
  border: 1px dashed #cbd5e1;
  border-radius: 4px;
  background: #ffffff;
  color: #475569;
  font-size: 11px;
  cursor: pointer;
}

.tgmd-show-excluded:hover {
  border-color: #94a3b8;
  background: #f8fafc;
}

/* Footer */
.tgmd-footer {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 12px;
  border-top: 1px solid #e2e8f0;
  background: #ffffff;
}

.tgmd-footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tgmd-clear-all {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 5px;
  border-color: #fecdd3;
  background: #fff1f2;
  color: #be123c;
  font-size: 11px;
  font-weight: 600;
}

.tgmd-clear-all:hover:not(:disabled) {
  background: #ffe4e6;
}

.tgmd-clear-all:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.btn {
  min-height: 28px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 0 12px;
  border-radius: 5px;
  font-size: 11px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-outline {
  border: 1px solid #cbd5e1;
  background: #ffffff;
  color: #334155;
}

.btn-outline:hover:not(:disabled) {
  border-color: #94a3b8;
  background: #f8fafc;
}

.btn-primary {
  border: 1px solid #4338ca;
  background: #4f46e5;
  color: #ffffff;
}

.btn-primary:hover:not(:disabled) {
  background: #4338ca;
}

/* Custom Scrollbars */
.tgmd-tree-scroll::-webkit-scrollbar,
.tgmd-operation-scroll::-webkit-scrollbar,
.tgmd-preview-summary::-webkit-scrollbar {
  width: 5px;
  height: 5px;
}

.tgmd-tree-scroll::-webkit-scrollbar-thumb,
.tgmd-operation-scroll::-webkit-scrollbar-thumb,
.tgmd-preview-summary::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 3px;
}

@media (max-width: 860px) {
  .tgmd-dialog {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
  }
  .tgmd-preview-state {
    grid-template-columns: 1fr;
    overflow: auto;
  }
  .tgmd-preview-tree {
    min-height: 300px;
  }
  .tgmd-workspace {
    grid-template-columns: 1fr;
    overflow: auto;
  }
  .tgmd-operation-pane {
    border-right: 0;
    border-bottom: 1px solid #dbe3ec;
  }
  .tgmd-pane {
    min-height: 320px;
  }
  .tgmd-search-box {
    width: 100px;
  }
  .tgmd-active-step-badge {
    max-width: 120px;
  }
}
</style>
