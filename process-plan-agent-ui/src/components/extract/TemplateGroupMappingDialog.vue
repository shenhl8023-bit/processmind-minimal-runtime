<template>
  <div v-if="embedded || modelValue" ref="workspaceRoot" class="tgmd-page">
    <div v-if="!model.template.value && model.loading.value" class="tgmd-page-loading" role="status">
      <span class="tgmd-spinner" />
      <span>正在加载项目分组模板...</span>
    </div>
    <template v-else-if="showMappingWorkspace">
        <header class="tgmd-header workflow-page-header">
          <div class="tgmd-title-block workflow-page-info">
            <div class="tgmd-title-row">
              <h2 id="template-group-mapping-workspace-title" class="workflow-page-title">模板分组映射</h2>
              <span v-if="model.template.value" class="tgmd-title-tag">Kmsoft XML</span>
              <div class="tgmd-review-guidance tgmd-header-guidance workflow-page-description" role="note">
                在已验证的完整母路线基础上补充模板特征映射。删除工步不参与映射输出，叶子分组可自行豁免。
              </div>
            </div>
            </div>
          <div class="tgmd-header-actions workflow-page-actions">
            <button
              v-if="showMappingWorkspace"
              class="tgmd-command"
              type="button"
              :disabled="mappingEditsLocked"
              @click="startReplacement"
            ><RefreshRight />更换模板</button>
          </div>
        </header>
          <main class="tgmd-workspace">
            <section class="tgmd-pane tgmd-operation-pane">
              <header class="tgmd-pane-header tgmd-operation-header">
                <div class="tgmd-op-header-left">
                  <h3>工序与工步</h3>
                  <span class="tgmd-left-progress">已映射 {{ coveredFeatureGroupCount }} · 已豁免 {{ waivedFeatureGroupCount }} · 待映射 {{ uncoveredFeatureGroupCount }}</span>
                  <span v-if="activeStep" class="tgmd-active-step-badge">{{ activeStep.step_name }}</span>
                  <span v-else class="tgmd-pane-subtitle">点击选中工步，勾选右侧特征后关联</span>
                </div>
                <div class="tgmd-operation-tools">
                  <button class="tgmd-smart-button" type="button"
                    :disabled="mappingEditsLocked || !hiddenStepKeys.length"
                    @click="restoreHiddenSteps"><RefreshRight />恢复全部工步<span v-if="hiddenStepKeys.length">（{{ hiddenStepKeys.length }}）</span></button>
                  <div v-if="recognizing" class="tgmd-operation-status" aria-live="polite">
                    <span class="tgmd-status-pill is-live"><span class="tgmd-spinner tgmd-spinner-mini" />正在智能推荐...</span>
                  </div>
                  <button v-if="!recognizing" class="tgmd-smart-button" type="button" :disabled="precisionLoading || model.loading.value || model.saving.value" @click="suggestAllSteps"><MagicStick />智能推荐</button>
                </div>
              </header>
              <div class="tgmd-operation-scroll">
                <article v-for="operation in visibleMappingOperations" :key="operationId(operation)" class="tgmd-operation-card">
                  <div class="tgmd-operation-heading">
                    <button class="tgmd-operation-toggle" type="button" @click="toggleOperationExpanded(operationId(operation))">
                      <div class="tgmd-op-title">
                        <ArrowRight :class="{ open: operationExpanded(operationId(operation)) }" />
                        <strong>{{ operation.name }}</strong>
                        <span :class="['tgmd-process-type', operationTypeLabel(operation) === '辅助工序' ? 'is-auxiliary' : 'is-standard']">
                          {{ operationTypeLabel(operation) }}
                        </span>
                      </div>
                      <span class="tgmd-op-summary">{{ operationMappingSummary(operation) }}</span>
                    </button>
                    <label v-if="operation.process_type === '加工工序'" class="tgmd-precision-field"
                      :class="{ 'is-invalid': precisionValidationAttempted && !machiningPrecisions.includes(operationPrecision(operation)) }">
                      <span>精度</span>
                      <select
                        :data-precision-process-id="operation.process_id"
                        :aria-label="`${operation.name}工序精度`"
                        :aria-invalid="precisionValidationAttempted && !machiningPrecisions.includes(operationPrecision(operation))"
                        :value="operationPrecision(operation)"
                        :disabled="mappingEditsLocked"
                        @click.stop
                        @change="setOperationPrecision(operation, ($event.target as HTMLSelectElement).value)"
                      >
                        <option value="">待确认</option>
                        <option v-for="precision in machiningPrecisions" :key="precision" :value="precision">{{ precision }}</option>
                      </select>
                      <span v-if="precisionSuggestions[operation.process_id || '']" class="tgmd-precision-suggestion"
                        :title="precisionSuggestions[operation.process_id || '']">模型建议</span>
                    </label>
                    <span v-else class="tgmd-auxiliary-precision">辅助工序</span>
                  </div>
                  <div v-if="operationExpanded(operationId(operation))" class="tgmd-step-list">
                    <div v-if="!visibleStepsForOperation(operation).length" class="tgmd-operation-empty">
                      {{ stepRefsForOperation(operation).length ? '该工序的工步已删除，可恢复后继续映射' : '该工序没有关联工步' }}
                    </div>
                    <div v-for="step in visibleStepsForOperation(operation)" :key="step.step_key" role="button" tabindex="0"
                      class="tgmd-step-row" :class="{ 'is-selected': activeStepKey === step.step_key, 'is-mapped': stepMappings(step).length }"
                      @click="activeStepKey = step.step_key" @keydown.enter.prevent="activeStepKey = step.step_key"
                      @keydown.space.prevent="activeStepKey = step.step_key">
                      <span class="tgmd-step-order">{{ String(step.display_order || step.step_order).padStart(2, '0') }}</span>
                      <div class="tgmd-step-content">
                        <strong class="tgmd-step-name">{{ step.step_name }}</strong>
                        <small v-if="operation.process_type === '辅助工序'" class="tgmd-step-eligibility">辅助工步，按工序规则保留</small>
                        <small v-else-if="!stepFeatureMappings(step).length" class="tgmd-step-eligibility">未映射，不导出</small>
                        <small v-if="displayStepMappings(step).length && activeStepKey !== step.step_key" class="tgmd-step-mapping-summary">{{ compactMappingSummary(step) }}</small>
                        <small v-else-if="displayStepMappings(step).length" class="tgmd-step-count-text">{{ displayStepMappings(step).length }} 个已关联特征</small>
                        <div v-if="displayStepMappings(step).length && activeStepKey === step.step_key" class="tgmd-step-mappings">
                          <span v-for="association in displayStepMappings(step)" :key="association.key" class="tgmd-chip-tag">
                            {{ association.label }}
                            <button type="button" title="解除关联" aria-label="解除关联" :disabled="mappingEditsLocked" @click.stop="removeStepMapping(association.mapping, step)"><Close /></button>
                          </span>
                        </div>
                      </div>
                      <div class="tgmd-step-actions" @keydown.stop>
                        <button class="tgmd-hide-step" type="button" :aria-label="`上移工步：${step.step_name}`"
                          :disabled="mappingEditsLocked || !canMoveStep(step, -1)" @click.stop="moveStep(step, -1)">上移</button>
                        <button class="tgmd-hide-step" type="button" :aria-label="`下移工步：${step.step_name}`"
                          :disabled="mappingEditsLocked || !canMoveStep(step, 1)" @click.stop="moveStep(step, 1)">下移</button>
                        <button class="tgmd-hide-step" type="button"
                          :data-hide-step-key="step.step_key" :aria-label="`删除工步：${step.step_name}`"
                          :disabled="mappingEditsLocked" @click.stop="hideStep(step)"><Close />删除</button>
                      </div>
                    </div>
                  </div>
                </article>
                <div v-if="!visibleMappingOperations.length" class="tgmd-empty">当前路线没有可关联的工步</div>
              </div>
            </section>

            <section class="tgmd-pane tgmd-tree-pane">
              <header class="tgmd-pane-header tgmd-tree-header">
                <div class="tgmd-tree-header-left"><h3>模板分组</h3></div>
                <div class="tgmd-tree-header-right">
                  <div class="tgmd-search-box">
                    <Search /><input v-model="treeSearchQuery" placeholder="查找分组/特征..." type="text">
                    <button v-if="treeSearchQuery" class="tgmd-search-clear" type="button" @click="treeSearchQuery = ''"><Close /></button>
                  </div>
                  <button v-if="activeGroupFeatures.length > 1" class="tgmd-toggle-group-selection" type="button"
                    :disabled="mappingEditsLocked"
                    :title="isAllActiveGroupFeaturesSelected ? '清空当前节点所有特征' : '全选当前节点所有特征'" @click="toggleSelectAllActiveGroupFeatures">
                    <Select v-if="!isAllActiveGroupFeaturesSelected" /><Close v-else />
                    {{ isAllActiveGroupFeaturesSelected ? '清空本组' : '全选本组' }}
                  </button>
                  <button class="tgmd-clear-selection" type="button" :disabled="mappingEditsLocked || !selectedFeatures.length" title="清空已勾选的分组节点" @click="clearSelectedFeatures"><Close />清空勾选</button>
                  <div class="tgmd-link-wrapper" @mouseenter="showLinkTooltip = true" @mouseleave="showLinkTooltip = false">
                    <button class="tgmd-link-btn" type="button" :disabled="!canLinkActiveStep" :class="{ 'is-active': canLinkActiveStep }" @click="linkActiveStep">
                      <ArrowLeft />关联<span v-if="selectedFeatures.length" class="tgmd-link-count">{{ selectedFeatures.length }}</span>
                    </button>
                    <Transition name="tgmd-popover-fade">
                      <div v-if="showLinkTooltip && selectedFeatures.length" class="tgmd-popover-card" role="tooltip">
                        <div class="tgmd-popover-header"><span class="tgmd-popover-title">已勾选特征</span><span class="tgmd-popover-badge">{{ selectedFeatures.length }} 项</span></div>
                        <div class="tgmd-popover-list">
                          <div v-for="selection in selectedFeatures" :key="templateFeatureSelectionKey(selection.leaf.key, selection.feature)" class="tgmd-popover-item">
                            <span class="tgmd-popover-path">{{ selection.leaf.path.join(' › ') }}</span><span class="tgmd-popover-feature">{{ selection.feature }}</span>
                          </div>
                        </div>
                      </div>
                    </Transition>
                  </div>
                  <button class="tgmd-current-suggest" type="button" :disabled="mappingEditsLocked || precisionLoading || recognizing || !selectedFeatures.length" title="按已选特征推荐匹配工步" @click="suggestActiveLeaf"><MagicStick />推荐</button>
                </div>
              </header>
              <div class="tgmd-tree-scroll">
                <TemplateGroupTreeNode v-for="node in displayTemplateTree" :key="node.key" :node="node"
                  :active-key="activeGroupKey" :mapped-counts="mappedCounts" :configured-leaf-keys="configuredLeafKeys"
                  :unconfigured-leaf-keys="unconfiguredLeafKeys" :show-metadata="false" multi-select
                  :show-mapping-status="true" :waived-leaf-keys="waivedLeafKeys" :show-waiver-actions="true"
                  @toggle-waiver="toggleLeafWaiver"
                  :selected-feature-keys="selectedFeatureKeys" show-selected-features show-feature-details
                  :readonly="mappingEditsLocked"
                  @select="activeGroupKey = $event" @toggle-feature="toggleSelectedFeature" />
                <div v-if="!displayTemplateTree.length" class="tgmd-empty">没有匹配的模板特征或分组</div>
              </div>
            </section>
          </main>

          <WorkflowNavFooter :inline="!embedded" :class="{ 'tgmd-footer': !embedded }" :notices="workspaceNotices" summary="选择工步并关联右侧模板特征" :show-previous="false" :show-next="false" next-label="保存映射">
            <template #actions>
              <button class="workflow-nav-btn workflow-nav-btn-prev" type="button" :disabled="!Object.keys(draftStepMappings).length || mappingEditsLocked" @click="clearMappings">清空映射</button>
              <button class="workflow-nav-btn workflow-nav-btn-prev" type="button" :disabled="mappingEditsLocked" @click="handleCancel">{{ embedded ? '返回路线验证' : '取消' }}</button>
              <button class="workflow-nav-btn workflow-nav-btn-next" type="button" :disabled="primaryActionDisabled" @click="handlePrimaryAction">{{ primaryActionLabel }}</button>
            </template>
          </WorkflowNavFooter>
    </template>
    <main v-else-if="showEmptyState" class="tgmd-empty-state">
      <div class="tgmd-empty-icon"><UploadFilled /></div>
      <h2>还没有导入分组模板</h2>
      <p>导入 Kmsoft XML 分组模板，再在映射工作区建立工步与分组的对应关系。</p>
      <button class="btn btn-primary" type="button" :disabled="mappingEditsLocked" @click="openTemplateDialog">
        <UploadFilled />导入模板
      </button>
      <span class="tgmd-empty-hint">支持 .xml 格式</span>
    </main>
    <div v-else-if="visibleError" class="tgmd-page-error" role="alert">
      <WarningFilled />
      <span>{{ visibleError }}</span>
    </div>
    <WorkflowNavFooter v-if="embedded && !showMappingWorkspace" :notices="workspaceNotices" summary="导入模板后可继续映射" previous-label="← 返回路线验证" next-label="保存映射" :show-next="false" @previous="handleCancel" />
  </div>

  <Teleport to="body">
    <div v-if="modelValue && importDialogOpen" class="tgmd-backdrop" @click.self="dismissImportDialog">
      <section ref="dialogRoot" class="tgmd-dialog tgmd-import-modal" :class="{ 'is-compact-upload': showUploadState }" role="dialog" aria-modal="true" aria-labelledby="template-group-mapping-title" tabindex="-1" @keydown.esc.stop.prevent="dismissImportDialog">
        <header class="tgmd-header">
          <div class="tgmd-title-block">
            <div class="tgmd-title-row">
              <h2 id="template-group-mapping-title">{{ isReplacing ? '更换分组模板' : '导入分组模板' }}</h2>
              <span class="tgmd-title-tag">Kmsoft XML</span>
            </div>
            <p class="tgmd-subtitle-hint">{{ isReplacing ? '确认后更新当前模板，映射影响会在此提前列出。' : '解析并检查文件结构，确认后进入映射工作区。' }}</p>
          </div>
          <button class="tgmd-icon-button" type="button" title="关闭" aria-label="关闭" :disabled="mappingEditsLocked" @click="dismissImportDialog"><Close /></button>
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
            <input ref="fileInput" class="tgmd-file-input" type="file" accept=".xml,application/xml,text/xml" :disabled="mappingEditsLocked" @change="onFileInput">

            <!-- Drop Zone -->
            <button
              class="tgmd-dropzone"
              :class="{ 'tgmd-dropzone-ready': pendingFile, 'tgmd-dropzone-loading': model.loading.value }"
              type="button"
              :disabled="mappingEditsLocked"
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
            <div class="tgmd-upload-actions">
              <button class="btn btn-outline" type="button" :disabled="model.loading.value || model.saving.value" @click="dismissImportDialog">{{ isReplacing ? '取消更换' : '取消' }}</button>
              <button v-if="pendingFile && visibleError" class="btn btn-primary" type="button" :disabled="mappingEditsLocked" @click="parsePendingFile">重新解析</button>
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
              <button v-else class="btn btn-outline" type="button" :disabled="model.saving.value" @click="dismissImportDialog">取消</button>
            </div>
            <button
              class="btn btn-primary"
              type="button"
              :disabled="!model.preview.value.can_confirm || model.saving.value"
              @click="confirmPreview"
            >
              <DocumentChecked />
              {{ model.saving.value ? '正在确认...' : isReplacing ? '确认更换模板' : '确认并应用模板' }}
            </button>
          </footer>
        </template>

        <div v-else-if="model.state.value === 'workspace'" class="tgmd-modal-notice">
          <p>模板已刷新，可以返回映射工作区继续操作。</p>
          <button class="btn btn-primary" type="button" :disabled="mappingEditsLocked" @click="dismissImportDialog">返回映射工作区</button>
        </div>
      </section>
    </div>
  </Teleport>
</template>

<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onDeactivated, ref, watch } from 'vue'
import { getTemplateMappingStatus } from '@/composables/projectGroupTemplateCheck'
import {
  ArrowLeft,
  ArrowRight,
  Close,
  DocumentChecked,
  MagicStick,
  RefreshRight,
  Search,
  Select,
  UploadFilled,
  WarningFilled,
} from '@element-plus/icons-vue'

import {
  suggestTemplateStepMappings,
  suggestTemplateProcessPrecisions,
  type GroupTemplateNode,
  type GroupTemplateStepMapping,
  type GroupTemplateStepMappingInput,
} from '@/api/extract'
import TemplateGroupTreeNode from '@/components/extract/TemplateGroupTreeNode.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'
import {
  acceptTemplateGroupFile,
  buildTemplateRouteStructureOperations,
  findTemplateGroupByKey,
  openTemplateGroupFilePicker,
  type TemplateAliasBinding,
  type TemplateOperation,
} from '@/composables/templateGroupMapping'
import {
  buildTemplateStepRefs,
  templateStepOrder,
  moveTemplateStep,
  buildSourceSuggestionOperations,
  isSuggestionForStep,
  buildTemplateStepRouteFingerprint,
  chunkTemplateSuggestionOperations,
  clearTemplateStepMappingDraft,
  confirmedMappingsForStep,
  mappingsForStep,
  scopeMappingsToFinalSteps,
  createTemplateStepMappingsForFinalStep,
  isFeatureLeaf,
  loadTemplateStepMappingDraft,
  saveTemplateStepMappingDraft,
  selectedTemplateFeatures,
  settleTemplateSuggestionBatches,
  stepMappingKey,
  templateFeatureSelectionKey,
  type TemplateStepRef,
} from '@/composables/templateStepMapping'
import {
  buildEligibleTemplateSteps,
  groupConfirmedMappingsByLeaf,
  mappingRecord,
} from '@/composables/templateGroupProcessMapping'
import { formatGroupTemplateIssueDetail, useProjectGroupTemplate, type TemplateMappingSaveHandler } from '@/composables/useProjectGroupTemplate'
import { clearTemplateMappingEdits, loadTemplateMappingExceptionDraft, loadTemplateMappingPrecisionDraft, saveTemplateMappingEdits } from '@/composables/templateMappingEdits'

const props = defineProps<{
  modelValue: boolean
  projectId: number
  workflowRevision?: number
  routeVersionId?: number
  operations: TemplateOperation[]
  pageNotices?: WorkflowNotice[]
  embedded?: boolean
  beforeSave?: TemplateMappingSaveHandler
  legacyAliases: Record<string, TemplateAliasBinding>
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'cancel'): void
  (event: 'continue'): void
  (event: 'status', payload: { validCount: number; savedValidCount: number; invalidCount: number; candidateCount: number; dirty: boolean; busy: boolean }): void
  (event: 'save', payload: { stepMappings: GroupTemplateStepMapping[]; templateRevision: number; hiddenStepKeys: string[]; waivedGroupPaths: string[][] }): void
}>()

const model = useProjectGroupTemplate(
  computed(() => props.projectId),
  computed(() => props.legacyAliases),
  computed(() => props.workflowRevision ?? 0),
)
const mappingEditsLocked = computed(() => model.loading.value || model.saving.value)
const dialogRoot = ref<HTMLElement | null>(null)
const workspaceRoot = ref<HTMLElement | null>(null)
const fileInput = ref<HTMLInputElement | null>(null)
const pendingFile = ref<File | null>(null)
const transientError = ref('')
const importDialogOpen = ref(!props.embedded && props.modelValue)
const draftStepMappings = ref<Record<string, GroupTemplateStepMappingInput>>({})
const savedSignature = ref('[]')
const savedPrecisionSignature = ref('{}')
const savedExceptionSignature = ref('{"hiddenStepKeys":[],"waivedGroupPaths":[]}')
const draftStepOrder = ref<Record<string, string[]>>({})
const stepOrderByProcess = computed(() => templateStepOrder(mappingOperations.value, draftStepOrder.value))
const draftHiddenStepKeys = ref<string[]>([])
const draftWaivedGroupPaths = ref<string[][]>([])
const draftInitialized = ref(false)
const draftTemplateRevision = ref(0)
const editContext = computed(() => ({ projectId: props.projectId, routeVersionId: props.routeVersionId || 0,
  workflowRevision: props.workflowRevision || 0, templateRevision: model.templateRevision.value }))
const expandedOperationIds = ref<number[]>([])
const precisionOverrides = ref<Record<string, string>>({})
const activeGroupKey = ref('')
const selectedFeatureKeys = ref<string[]>([])
const activeStepKey = ref('')
const recognizing = ref(false)
const recommendationProgress = ref('正在推荐')
const dialogRunId = ref(0)
const mappingWarnings = ref<string[]>([])
const treeSearchQuery = ref('')
const showLinkTooltip = ref(false)

const precisionLoading = ref(false)
const precisionValidationAttempted = ref(false)
const precisionSuggestions = ref<Record<string, string>>({})
const precisionWarnings = ref<string[]>([])
const precisionEdits = ref<Record<string, number>>({})
let precisionRequestId = 0
const visibleError = computed(() => transientError.value || model.error.value
  || (precisionValidationAttempted.value && missingPrecisionOperations.value.length
    ? `请先填写以下 ${missingPrecisionOperations.value.length} 道加工工序的精度，再保存映射：${missingPrecisionOperations.value.map(operation => operation.name).join('、')}。可点击“智能推荐”补全，或在各工序右侧手动选择。`
    : ''))
const isReplacing = computed(() => Boolean(model.template.value))
const showMappingWorkspace = computed(() => Boolean(model.template.value) && (props.embedded || model.state.value === 'workspace'))
const showEmptyState = computed(() => Boolean(props.embedded) && !model.template.value && !model.loading.value)
const showUploadState = computed(() => (
  model.state.value === 'empty'
  || (model.state.value === 'preview' && !model.preview.value)
))
const mappingOperations = computed(() => {
  const seen = new Set<number>()
  return props.operations
    .filter((operation) => {
      const id = operationId(operation)
      if (!id) return true
      if (seen.has(id)) return false
      seen.add(id)
      return true
    })
    .sort((left, right) => Number(left.sequence || 0) - Number(right.sequence || 0) || operationId(left) - operationId(right))
})
const stepRefs = computed(() => mappingOperations.value.flatMap(buildTemplateStepRefs))
// Persist canonical mother-route identities; list filtering never edits the source operations.
const hiddenStepKeys = computed(() => stepRefs.value.filter(step => draftHiddenStepKeys.value.includes(step.step_key)).map(step => step.step_key))
const featureLeaves = computed(() => {
  const visit = (nodes: GroupTemplateNode[]): GroupTemplateNode[] => nodes.flatMap(node => isFeatureLeaf(node) ? [node] : visit(node.children || []))
  return visit(model.template.value?.tree || [])
})
function groupPathKey(path: string[]) { return JSON.stringify(path.map(part => part.normalize('NFC').trim())) }
const waivedGroupPaths = computed(() => featureLeaves.value.filter(leaf => draftWaivedGroupPaths.value
  .some(path => groupPathKey(path) === groupPathKey(leaf.path))).map(leaf => [...leaf.path]))
const waivedLeafKeys = computed(() => featureLeaves.value.filter(leaf => waivedGroupPaths.value
  .some(path => groupPathKey(path) === groupPathKey(leaf.path))).map(leaf => leaf.key))
const exceptionState = computed(() => ({ hiddenStepKeys: hiddenStepKeys.value, waivedGroupPaths: waivedGroupPaths.value, stepOrderByProcess: stepOrderByProcess.value }))
const routeFingerprint = computed(() => buildTemplateStepRouteFingerprint(mappingOperations.value))
const classifiedSteps = computed(() => buildEligibleTemplateSteps(mappingOperations.value))
const eligibleStepKeys = computed(() => new Set(classifiedSteps.value.eligible.map(step => step.step_key)))
function filterTreeNode(node: GroupTemplateNode, query: string): GroupTemplateNode | null {
  const q = query.trim().toLocaleLowerCase()
  if (!q) return node
  const matchesSelf = node.name.toLocaleLowerCase().includes(q)
    || node.feature_selections.some(feature => feature.toLocaleLowerCase().includes(q))
  const children = node.children.map(child => filterTreeNode(child, query)).filter((child): child is GroupTemplateNode => child !== null)
  return matchesSelf || children.length ? { ...node, children } : null
}
const displayTemplateTree = computed(() => {
  const tree = model.template.value?.tree || []
  if (!treeSearchQuery.value.trim()) return tree
  return tree.map(node => filterTreeNode(node, treeSearchQuery.value)).filter((node): node is GroupTemplateNode => node !== null)
})
const selectedFeatures = computed(() => selectedTemplateFeatures(model.template.value?.tree || [], selectedFeatureKeys.value)
  .filter(selection => !waivedLeafKeys.value.includes(selection.leaf.key)))
const activeStep = computed(() => stepRefs.value.find(step => step.step_key === activeStepKey.value && !hiddenStepKeys.value.includes(step.step_key)) || null)
const coveredFeatureGroupCount = computed(() => leafConfiguration.value.configured.length)
const waivedFeatureGroupCount = computed(() => draftStatus.value.waivedFeatureGroups.length)
const uncoveredFeatureGroupCount = computed(() => leafConfiguration.value.unconfigured.length)
const canLinkActiveStep = computed(() => !mappingEditsLocked.value && Boolean(activeStep.value && canDecideStep(activeStep.value) && selectedFeatures.value.some(selection => (
  !isFeatureLinkedToStep(activeStep.value!, selection.leaf, selection.feature)
))))
const activeGroupNode = computed(() => findTemplateGroupByKey(model.template.value?.tree || [], activeGroupKey.value))
const activeGroupFeatures = computed(() => activeGroupNode.value && isFeatureLeaf(activeGroupNode.value)
  ? activeGroupNode.value.feature_selections : [])
const isAllActiveGroupFeaturesSelected = computed(() => Boolean(activeGroupFeatures.value.length && activeGroupFeatures.value.every(feature => (
  selectedFeatureKeys.value.includes(templateFeatureSelectionKey(activeGroupKey.value, feature))
))))
const mappingStatusMessages = computed(() => [...new Set([...mappingWarnings.value, ...precisionWarnings.value].map(notice => notice.trim()).filter(Boolean))])
const workspaceNotices = computed<WorkflowNotice[]>(() => [
  ...(props.pageNotices || []),
  ...(visibleError.value ? [{ id: 'mapping-error', level: 'error' as const, summary: '映射操作未完成', detail: visibleError.value }] : []),
  ...mappingStatusMessages.value.map((detail, index) => ({ id: `mapping-status-${index}`, level: 'warning' as const, summary: detail, detail })),
])

const visibleMappingOperations = computed(() => mappingOperations.value)
const machiningPrecisions = ['粗加工', '半精加工', '精加工']
const missingPrecisionOperations = computed(() => props.operations.filter(operation =>
  operation.process_type === '加工工序' && !machiningPrecisions.includes(operationPrecision(operation)),
))
const mappingsByLeaf = computed(() => groupConfirmedMappingsByLeaf(
  Object.values(draftStepMappings.value),
  model.template.value?.tree || [],
))
const leafConfiguration = computed(() => ({ configured: draftStatus.value.mappedFeatureGroups, unconfigured: draftStatus.value.missingFeatureGroups }))
const configuredLeafKeys = computed(() => leafConfiguration.value.configured.map(leaf => leaf.key))
const unconfiguredLeafKeys = computed(() => leafConfiguration.value.unconfigured.map(leaf => leaf.key))
const mappedCounts = computed(() => Object.entries(mappingsByLeaf.value).reduce<Record<string, number>>((counts, [key, mappings]) => {
  counts[key] = new Set(mappings.flatMap(mapping => (
    mapping.final_targets?.length
      ? mapping.final_targets.map(target => `${target.process_id}:${target.step_id}`)
      : [`op_${mapping.source_operation_id}_s${String(mapping.source_step_order).padStart(2, '0')}`]
  ))).size
  return counts
}, {}))
const draftStatus = computed(() => getTemplateMappingStatus(model.template.value ? {
  ...model.template.value, step_mappings: Object.values(draftStepMappings.value) as GroupTemplateStepMapping[],
  hidden_step_keys: hiddenStepKeys.value, waived_group_paths: waivedGroupPaths.value,
} : null, props.operations))
const savedStatus = computed(() => getTemplateMappingStatus(model.template.value, props.operations))
const canContinue = computed(() => (savedStatus.value.validCount > 0 || savedStatus.value.waivedFeatureGroups.length > 0) && savedStatus.value.missingFeatureGroups.length === 0
  && !missingPrecisionOperations.value.length)
const dirty = computed(() => savedSignature.value !== JSON.stringify(Object.values(draftStepMappings.value))
  || savedPrecisionSignature.value !== JSON.stringify(precisionOverrides.value)
  || savedExceptionSignature.value !== JSON.stringify(exceptionState.value))
const primaryActionLabel = computed(() => model.saving.value
  ? '正在保存'
  : canContinue.value && !dirty.value ? '更新规则包' : '保存并导出规则包')
const primaryActionDisabled = computed(() => (
  model.saving.value
  || model.loading.value
  || recognizing.value
  || precisionLoading.value
  || (!dirty.value && !canContinue.value && !missingPrecisionOperations.value.length)
))
watch(() => props.modelValue, (visible) => {
  if (!props.embedded) importDialogOpen.value = visible
})
watch(importDialogOpen, async (visible) => {
  if (visible) {
    await nextTick()
    dialogRoot.value?.focus()
  }
}, { immediate: true })
watch([draftStatus, savedStatus, dirty, recognizing, precisionLoading, model.saving, model.loading], () => {
  emit('status', {
    validCount: draftStatus.value.validCount, savedValidCount: savedStatus.value.validCount,
    invalidCount: draftStatus.value.invalidCount, candidateCount: 0,
    dirty: dirty.value, busy: recognizing.value || precisionLoading.value || model.saving.value || model.loading.value,
  })
}, { immediate: true, deep: true })

watch([dirty, precisionOverrides, exceptionState, () => JSON.stringify(draftStepMappings.value)], () => {
  if (draftInitialized.value && !model.loading.value && !model.saving.value) {
    saveTemplateMappingEdits(editContext.value, dirty.value, precisionOverrides.value, exceptionState.value)
  }
}, { deep: true, flush: 'sync' })

defineExpose({ save: saveStepMappings, discardChanges })
onBeforeUnmount(invalidatePrecisionSuggestions)
onDeactivated(invalidatePrecisionSuggestions)

watch(() => [props.modelValue, props.projectId] as const, async ([visible]) => {
  dialogRunId.value += 1
  draftInitialized.value = false
  invalidatePrecisionSuggestions()
  recognizing.value = false
  recommendationProgress.value = '正在推荐'
  transientError.value = ''
  pendingFile.value = null
  if (!visible) return
  mappingWarnings.value = []
  const runId = dialogRunId.value
  await model.load()
  if (runId !== dialogRunId.value || !props.modelValue) return
  syncDraftFromTemplate()
}, { immediate: true })

function operationId(operation: TemplateOperation) {
  return Number(operation.process_id ? operation.id : operation.source_operation_id || operation.id || 0)
}

function operationName(sourceOperationId: number) {
  return props.operations.find(operation => operation.source_operation_ids?.includes(sourceOperationId) || operationId(operation) === sourceOperationId)?.name || `工序 ${sourceOperationId}`
}

function stepRefsForOperation(operation: TemplateOperation) {
  return buildTemplateStepRefs(operation)
}

function syncDraftFromTemplate() {
  draftInitialized.value = false
  draftTemplateRevision.value = model.templateRevision.value
  precisionSuggestions.value = {}
  precisionValidationAttempted.value = false
  const template = model.template.value
  if (!template) {
    draftStepMappings.value = {}
    precisionOverrides.value = {}
    savedSignature.value = '[]'
    savedPrecisionSignature.value = '{}'
    draftStepOrder.value = {}
    draftHiddenStepKeys.value = []
    draftWaivedGroupPaths.value = []
    savedExceptionSignature.value = JSON.stringify(exceptionState.value)
    activeGroupKey.value = ''
    selectedFeatureKeys.value = []
    activeStepKey.value = ''
    return
  }
  precisionOverrides.value = Object.fromEntries(
    (template.mapping_output || [])
      .filter(process => process.process_id)
      .map(process => [process.process_id, process.precision || '']),
  )
  savedPrecisionSignature.value = JSON.stringify(precisionOverrides.value)
  precisionOverrides.value = loadTemplateMappingPrecisionDraft(editContext.value, precisionOverrides.value)
  const formal = model.draftStepMappings.value
  const restored = loadTemplateStepMappingDraft(
    props.projectId,
    template.template_revision,
    routeFingerprint.value,
    formal,
  )
  savedSignature.value = JSON.stringify(Object.values(mappingRecord(scopeMappingsToFinalSteps(formal, stepRefs.value))))
  draftStepMappings.value = mappingRecord(scopeMappingsToFinalSteps(restored, stepRefs.value))
  draftStepOrder.value = template.step_order_by_process || {}
  draftHiddenStepKeys.value = template.hidden_step_keys || []
  draftWaivedGroupPaths.value = template.waived_group_paths || []
  savedExceptionSignature.value = JSON.stringify(exceptionState.value)
  const exceptions = loadTemplateMappingExceptionDraft(editContext.value, exceptionState.value)
  draftHiddenStepKeys.value = exceptions.hiddenStepKeys
  draftWaivedGroupPaths.value = exceptions.waivedGroupPaths
  draftStepOrder.value = exceptions.stepOrderByProcess || draftStepOrder.value
  const activeStillExists = findTemplateGroupByKey(template.tree, activeGroupKey.value)
  const firstLeaf = featureLeaves.value[0]
  activeGroupKey.value = activeStillExists?.key || firstLeaf?.key || ''
  selectedFeatureKeys.value = []
  const firstEligibleStep = classifiedSteps.value.eligible[0]
  activeStepKey.value = stepRefs.value.some(step => step.step_key === activeStepKey.value)
    ? activeStepKey.value
    : firstEligibleStep?.step_key || ''
  treeSearchQuery.value = ''
  expandedOperationIds.value = mappingOperations.value
    .filter(operation => operation.process_type !== '辅助工序')
    .slice(0, 3)
    .map(operationId)
  draftInitialized.value = true
  saveTemplateMappingEdits(editContext.value, dirty.value, precisionOverrides.value, exceptionState.value)
}

function discardChanges() {
  if (model.loading.value || model.saving.value || recognizing.value || precisionLoading.value) return
  model.draftStepMappings.value = model.template.value?.step_mappings || []
  clearTemplateStepMappingDraft(props.projectId)
  clearTemplateMappingEdits(editContext.value)
  syncDraftFromTemplate()
}

function syncChangedDraftBase() {
  if (draftTemplateRevision.value === model.templateRevision.value) return false
  // A recovered version token can only be used with a draft from that snapshot.
  discardChanges()
  transientError.value = model.template.value
    ? '分组模板已更新，未保存的草稿已替换为最新映射和精度。请核对后重新编辑、保存。'
    : ''
  return true
}

function formatBytes(size: number) {
  if (size < 1024) return `${size} B`
  return `${(size / 1024).toFixed(size < 10240 ? 1 : 0)} KB`
}

function openFilePicker() {
  if (mappingEditsLocked.value) return
  openTemplateGroupFilePicker(fileInput.value)
}

function openTemplateDialog() {
  if (model.loading.value || model.saving.value) return
  pendingFile.value = null
  transientError.value = ''
  importDialogOpen.value = true
}

async function acceptFile(file: File | undefined) {
  if (mappingEditsLocked.value) return
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
  if (mappingEditsLocked.value || !pendingFile.value) return
  transientError.value = ''
  await model.selectFile(pendingFile.value)
}

function invalidateRecommendations() {
  dialogRunId.value += 1
  invalidatePrecisionSuggestions()
  recognizing.value = false
  recommendationProgress.value = '正在推荐'
  mappingWarnings.value = []
}

async function startReplacement() {
  if (mappingEditsLocked.value) return
  invalidateRecommendations()
  pendingFile.value = null
  transientError.value = ''
  model.beginReplacement()
  importDialogOpen.value = true
}

function cancelReplacement() {
  if (mappingEditsLocked.value) return
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  syncDraftFromTemplate()
  importDialogOpen.value = false
  if (!props.embedded) emit('update:modelValue', false)
}

function resetPreviewSelection() {
  if (mappingEditsLocked.value) return
  pendingFile.value = null
  transientError.value = ''
  if (model.template.value) model.beginReplacement()
  else model.cancelPreview()
  if (fileInput.value) fileInput.value.value = ''
}

async function confirmPreview() {
  if (mappingEditsLocked.value) return
  invalidateRecommendations()
  const runId = dialogRunId.value
  const confirmed = await model.confirmTemplate()
  if (runId === dialogRunId.value && props.modelValue && model.state.value === 'workspace') {
    syncDraftFromTemplate()
    if (confirmed) {
      importDialogOpen.value = false
      if (!props.embedded) emit('update:modelValue', false)
    }
  }
}

function persistStepDraft() {
  if (!model.template.value) return
  mappingWarnings.value = []
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
  const refs = stepRefsForOperation(operation)
  const key = operation.process_id || `op_${operationId(operation)}`
  const byId = new Map(refs.map(step => [step.step_key, step]))
  return (stepOrderByProcess.value[key] || []).filter(id => !hiddenStepKeys.value.includes(id))
    .flatMap(id => byId.has(id) ? [byId.get(id)!] : []).map((step, index) => ({ ...step, display_order: index + 1 }))
}

function hideStep(step: TemplateStepRef) {
  if (mappingEditsLocked.value || !stepRefs.value.some(item => item.step_key === step.step_key)) return
  mappingsForStep(draftStepMappings.value, step).forEach(mapping => { delete draftStepMappings.value[stepMappingKey(mapping)] })
  draftHiddenStepKeys.value = [...new Set([...hiddenStepKeys.value, step.step_key])]
  if (activeStepKey.value === step.step_key) activeStepKey.value = ''
  persistStepDraft()
}

function stepOrderKey(step: TemplateStepRef) { return step.process_id || `op_${step.operation_id}` }

function canMoveStep(step: TemplateStepRef, direction: -1 | 1) {
  const visible = (stepOrderByProcess.value[stepOrderKey(step)] || []).filter(id => !hiddenStepKeys.value.includes(id))
  const index = visible.indexOf(step.step_key)
  return index >= 0 && Boolean(visible[index + direction])
}

function moveStep(step: TemplateStepRef, direction: -1 | 1) {
  if (mappingEditsLocked.value || !canMoveStep(step, direction)) return
  const key = stepOrderKey(step)
  draftStepOrder.value = { ...stepOrderByProcess.value, [key]: moveTemplateStep(stepOrderByProcess.value[key]!, hiddenStepKeys.value, step.step_key, direction) }
  persistStepDraft()
}

function restoreHiddenSteps() {
  if (mappingEditsLocked.value) return
  draftHiddenStepKeys.value = []
  persistStepDraft()
}

function toggleLeafWaiver(key: string) {
  if (mappingEditsLocked.value) return
  const leaf = featureLeaves.value.find(node => node.key === key)
  if (!leaf) return
  const pathKey = groupPathKey(leaf.path)
  const waived = waivedGroupPaths.value.some(path => groupPathKey(path) === pathKey)
  if (!waived && configuredLeafKeys.value.includes(key)) return
  draftWaivedGroupPaths.value = waived
    ? waivedGroupPaths.value.filter(path => groupPathKey(path) !== pathKey)
    : [...waivedGroupPaths.value, [...leaf.path]]
  mappingWarnings.value = []
}

function operationTypeLabel(operation: TemplateOperation) {
  return operation.process_type === '辅助工序' ? '辅助工序' : '标准工序'
}

function operationMappingSummary(operation: TemplateOperation) {
  if (operation.process_type === '辅助工序') return '辅助工序，按规则保留'
  const allSteps = visibleStepsForOperation(operation)
  if (!allSteps.length) return '无工步，不导出'
  const mapped = allSteps.filter(step => stepFeatureMappings(step).length > 0).length
  const unmapped = Math.max(0, allSteps.length - mapped)
  return `已关联 ${mapped} · 未映射 ${unmapped}（不导出）`
}

function compactMappingSummary(step: TemplateStepRef) {
  const mappings = displayStepMappings(step)
  if (!mappings.length) return ''
  const first = mappings[0]!.mapping.template_group_path.join(' / ')
  return mappings.length === 1 ? first : `${first} 等 ${mappings.length} 项`
}

function stepMappings(step: TemplateStepRef) {
  return confirmedMappingsForStep(draftStepMappings.value, step)
}

function displayStepMappings(step: TemplateStepRef) {
  const groups = new Map<string, GroupTemplateStepMappingInput[]>()
  stepMappings(step).forEach(mapping => {
    const key = JSON.stringify(mapping.template_group_path)
    if (!groups.has(key)) groups.set(key, [])
    groups.get(key)!.push(mapping)
  })
  return [...groups.entries()].map(([key, mappings]) => {
    const mapping = mappings[0]!
    const features = [...new Set(mappings.flatMap(item => item.candidate_features))]
    return {
      key,
      mapping,
      mappings,
      label: features.length
        ? `${mapping.template_group_path.join(' / ')} · ${features.join('、')}`
        : mapping.template_group_path.join(' / '),
    }
  })
}

function stepFeatureMappings(step: TemplateStepRef) {
  return stepMappings(step).filter(mapping => mapping.status !== 'not_applicable')
}

function isFeatureLinkedToStep(step: TemplateStepRef, leaf: GroupTemplateNode, feature: string) {
  const mappings = stepFeatureMappings(step).filter(mapping => (
    JSON.stringify(mapping.template_group_path) === JSON.stringify(leaf.path)
    && mapping.candidate_features.includes(feature)
  ))
  return sourceRefsForStep(step).every(ref => mappings.some(mapping => (
    mapping.source_operation_id === ref.source_operation_id
    && mapping.source_step_order === ref.source_step_order
    && mapping.source_step_name.normalize('NFC').trim() === ref.source_step_name.normalize('NFC').trim()
  )))
}

function toggleSelectedFeature(selection: { leafKey: string; feature: string }) {
  if (mappingEditsLocked.value) return
  const candidate = findTemplateGroupByKey(model.template.value?.tree || [], selection.leafKey)
  if (!candidate || !isFeatureLeaf(candidate) || !candidate.feature_selections.includes(selection.feature)) return
  const key = templateFeatureSelectionKey(selection.leafKey, selection.feature)
  const selected = new Set(selectedFeatureKeys.value)
  if (selected.has(key)) selected.delete(key)
  else selected.add(key)
  selectedFeatureKeys.value = [...selected]
  activeGroupKey.value = selection.leafKey
}

function toggleSelectAllActiveGroupFeatures() {
  if (mappingEditsLocked.value) return
  const leaf = activeGroupNode.value
  if (!leaf || !isFeatureLeaf(leaf) || !leaf.feature_selections.length) return
  const next = new Set(selectedFeatureKeys.value)
  const selectAll = !isAllActiveGroupFeaturesSelected.value
  leaf.feature_selections.forEach(feature => {
    const key = templateFeatureSelectionKey(leaf.key, feature)
    if (selectAll) next.add(key)
    else next.delete(key)
  })
  selectedFeatureKeys.value = [...next]
}

function clearSelectedFeatures() {
  if (mappingEditsLocked.value) return
  selectedFeatureKeys.value = []
}

function linkActiveStep() {
  if (mappingEditsLocked.value) return
  const step = activeStep.value
  if (!step || !canLinkActiveStep.value || !canDecideStep(step)) return
  clearLegacyGeneralStepDecision(step)
  selectedFeatures.value.forEach(({ leaf, feature }) => {
    const missingRefs = sourceRefsForStep(step).filter(ref => {
      const existing = stepFeatureMappings(step).filter(mapping => (
        JSON.stringify(mapping.template_group_path) === JSON.stringify(leaf.path)
        && mapping.candidate_features.includes(feature)
        && mapping.source_operation_id === ref.source_operation_id
        && mapping.source_step_order === ref.source_step_order
        && mapping.source_step_name.normalize('NFC').trim() === ref.source_step_name.normalize('NFC').trim()
      ))
      return existing.length === 0
    })
    createTemplateStepMappingsForFinalStep(
      step, leaf, leaf.path.slice(0, -1), 'user_confirmed', 1, [feature], missingRefs,
    ).forEach(mapping => {
      const key = stepMappingKey(mapping)
      const existing = draftStepMappings.value[key]
      draftStepMappings.value[key] = existing
        ? { ...existing, candidate_features: [...new Set([...existing.candidate_features, ...mapping.candidate_features])] }
        : mapping
    })
  })
  persistStepDraft()
}

function removeStepMapping(mapping: GroupTemplateStepMappingInput, step?: TemplateStepRef) {
  if (mappingEditsLocked.value) return
  const mappings = step
    ? stepMappings(step).filter(item => JSON.stringify(item.template_group_path) === JSON.stringify(mapping.template_group_path))
    : [mapping]
  mappings.forEach(item => { delete draftStepMappings.value[stepMappingKey(item)] })
  persistStepDraft()
}

function sourceRefsForStep(step: TemplateStepRef) {
  return step.source_steps?.length ? step.source_steps : [{
    source_operation_id: step.operation_id,
    source_step_order: step.step_order,
    source_step_name: step.source_step_name || step.step_name,
  }]
}

function canDecideStep(step: TemplateStepRef) {
  return !hiddenStepKeys.value.includes(step.step_key) && eligibleStepKeys.value.has(step.step_key) && step.operation_id > 0 && step.step_order > 0
}

function clearLegacyGeneralStepDecision(step: TemplateStepRef) {
  mappingsForStep(draftStepMappings.value, step).forEach(mapping => {
    if (mapping.status === 'not_applicable') delete draftStepMappings.value[stepMappingKey(mapping)]
  })
}

function sourceRefsForSuggestion(step: TemplateStepRef, suggestionKey: string) {
  const refs = step.source_steps?.length ? step.source_steps : [{
    source_operation_id: step.operation_id,
    source_step_order: step.step_order,
    source_step_name: step.source_step_name || step.step_name,
  }]
  if (!step.source_steps?.length && step.step_key === suggestionKey) return refs
  return refs.filter(ref => `op_${ref.source_operation_id}_s${String(ref.source_step_order).padStart(2, '0')}` === suggestionKey)
}

function clearMappings() {
  if (mappingEditsLocked.value) return
  draftStepMappings.value = {}
  persistStepDraft()
}

function suggestionOperations() {
  return buildSourceSuggestionOperations(mappingOperations.value, new Set([...eligibleStepKeys.value].filter(key => !hiddenStepKeys.value.includes(key))))
}

function mappingOutputOperations() {
  return buildTemplateRouteStructureOperations(props.operations, precisionOverrides.value)
}

function operationPrecision(operation: TemplateOperation) {
  const processId = String(operation.process_id || '')
  return Object.prototype.hasOwnProperty.call(precisionOverrides.value, processId)
    ? precisionOverrides.value[processId]!
    : operation.precision || ''
}

function setOperationPrecision(operation: TemplateOperation, precision: string) {
  if (mappingEditsLocked.value) return
  if (!operation.process_id || operation.process_type !== '加工工序') return
  precisionEdits.value[operation.process_id] = (precisionEdits.value[operation.process_id] || 0) + 1
  precisionOverrides.value = { ...precisionOverrides.value, [operation.process_id]: precision }
  delete precisionSuggestions.value[operation.process_id]
}

function invalidatePrecisionSuggestions() {
  precisionRequestId += 1
  precisionLoading.value = false
  precisionWarnings.value = []
  precisionSuggestions.value = {}
  precisionValidationAttempted.value = false
}

async function focusMissingPrecision() {
  const first = missingPrecisionOperations.value[0]
  if (!first) return
  expandedOperationIds.value = [...new Set([...expandedOperationIds.value, operationId(first)])]
  await nextTick()
  const selector = Array.from(workspaceRoot.value?.querySelectorAll<HTMLSelectElement>('[data-precision-process-id]') || [])
    .find(element => element.dataset.precisionProcessId === first.process_id)
  selector?.scrollIntoView({ block: 'center', behavior: 'smooth' })
  selector?.focus({ preventScroll: true })
}

async function suggestPrecisions() {
  if (precisionLoading.value || recognizing.value || model.saving.value || model.loading.value
    || !model.template.value || !missingPrecisionOperations.value.length) return
  const requestId = ++precisionRequestId
  const runId = dialogRunId.value
  const projectId = props.projectId
  const revision = model.templateRevision.value
  const fingerprint = routeFingerprint.value
  const initialEdits = { ...precisionEdits.value }
  const initialValues = new Map(props.operations.map(operation => [operation.process_id, operationPrecision(operation)]))
  const isCurrent = () => requestId === precisionRequestId && runId === dialogRunId.value
    && props.modelValue && projectId === props.projectId && revision === model.templateRevision.value
    && fingerprint === routeFingerprint.value
  precisionLoading.value = true
  precisionWarnings.value = []
  try {
    const response = await suggestTemplateProcessPrecisions({
      project_id: projectId, expected_template_revision: revision, operations: mappingOutputOperations(),
    })
    if (!isCurrent() || response.project_id !== projectId || response.template_revision !== revision) return
    let filled = 0
    for (const suggestion of response.suggestions || []) {
      const operation = props.operations.find(item => item.process_id === suggestion.process_id && item.process_type === '加工工序')
      if (!operation || !machiningPrecisions.includes(suggestion.precision)
        || !Number.isFinite(suggestion.confidence) || suggestion.confidence < 0.85
        || suggestion.confidence > 1
        || machiningPrecisions.includes(initialValues.get(operation.process_id) || '')
        || (precisionEdits.value[suggestion.process_id] || 0) !== (initialEdits[suggestion.process_id] || 0)
        || operationPrecision(operation) !== initialValues.get(operation.process_id)) continue
      precisionOverrides.value = { ...precisionOverrides.value, [suggestion.process_id]: suggestion.precision }
      precisionSuggestions.value[suggestion.process_id] = [suggestion.reason, ...(suggestion.evidence || [])].filter(Boolean).join('；') || '根据当前工序与路线顺序推荐，可手动修改'
      filled += 1
    }
    precisionWarnings.value = [
      ...(filled ? [`已补全 ${filled} 道工序的精度，请核对后保存。`] : []),
      ...(response.warnings || []),
      ...(!filled && !(response.warnings || []).length ? ['没有可用的精度建议，请手动选择待确认项。'] : []),
    ]
  } catch (cause: any) {
    if (!isCurrent()) return
    precisionWarnings.value = [typeof cause?.response?.data?.detail === 'string'
      ? cause.response.data.detail : '智能判定暂时不可用，已保留当前填写内容，请重试或手动选择精度。']
  } finally {
    if (requestId === precisionRequestId) precisionLoading.value = false
  }
}

function applySuggestedMappings(
  suggestions: Awaited<ReturnType<typeof suggestTemplateStepMappings>>['suggestions'],
  targetLeafKeys?: string[],
) {
  if (mappingEditsLocked.value) return { added: 0, supplemented: 0, preserved: 0 }
  const tree = model.template.value?.tree || []
  let added = 0
  let supplemented = 0
  let preserved = 0
  suggestions.forEach((suggestion) => {
    if (!suggestion.recommended_group_ids.length) return
    stepRefs.value.filter(item => canDecideStep(item) && isSuggestionForStep(item, suggestion.step_key)).forEach((step) => {
      const sourceRefs = sourceRefsForSuggestion(step, suggestion.step_key)
      if (!sourceRefs.length) return
      suggestion.recommended_group_ids.forEach((groupId) => {
        if (waivedLeafKeys.value.includes(groupId)) return
        if (targetLeafKeys?.length && !targetLeafKeys.includes(groupId)) return
        const leaf = findTemplateGroupByKey(tree, groupId)
        if (!leaf || !isFeatureLeaf(leaf)) return
        const recommended = suggestion.recommended_features_by_group[groupId] || []
        const features = recommended.length
          ? [...new Set(recommended.filter(feature => leaf.feature_selections.includes(feature)))]
          : [...leaf.feature_selections]
        if (!features.length) return
        clearLegacyGeneralStepDecision(step)
        const mappings = createTemplateStepMappingsForFinalStep(
          step,
          leaf,
          leaf.path.slice(0, -1),
          'auto_confirmed',
          suggestion.confidence,
          features,
          sourceRefs,
        )
        mappings.forEach((mapping) => {
          const key = stepMappingKey(mapping)
          const existing = draftStepMappings.value[key]
          if (!existing) {
            draftStepMappings.value[key] = mapping
            added += 1
            return
          }
          const mergedFeatures = [...new Set([...existing.candidate_features, ...mapping.candidate_features])]
          if (mergedFeatures.length === existing.candidate_features.length) {
            preserved += 1
            return
          }
          draftStepMappings.value[key] = { ...existing, candidate_features: mergedFeatures }
          supplemented += 1
        })
      })
    })
  })
  return { added, supplemented, preserved }
}

async function suggestSteps(targetLeafKeys?: string[]) {
  if (mappingEditsLocked.value || recognizing.value || precisionLoading.value || !model.template.value) return
  if (targetLeafKeys?.length && !selectedFeatures.value.length) return
  const runId = ++dialogRunId.value
  const projectId = props.projectId
  const templateRevision = model.templateRevision.value
  const isCurrent = () => runId === dialogRunId.value && props.modelValue
    && projectId === props.projectId && templateRevision === model.templateRevision.value
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
        ...(added ? [`已关联 ${added} 条推荐工步。`] : []),
        ...(supplemented ? [`已补充 ${supplemented} 条遗漏特征。`] : []),
        ...(preserved ? [`已保留 ${preserved} 条已有特征关联。`] : []),
      ]
    }
    const applyResponse = (response: Awaited<ReturnType<typeof suggestTemplateStepMappings>>) => {
      if (!isCurrent()) return
      responseWarnings.push(...(response.warnings || []))
      const result = applySuggestedMappings(response.suggestions, targetLeafKeys)
      added += result.added
      supplemented += result.supplemented
      preserved += result.preserved
      persistStepDraft()
      updateRecommendationWarnings()
    }
    const batchSize = 3
    for (let start = 0; start < batches.length; start += batchSize) {
      if (!isCurrent()) return
      const currentBatches = batches.slice(start, start + batchSize)
      recommendationProgress.value = `正在推荐 ${Math.min(start + 1, batches.length)}-${Math.min(start + currentBatches.length, batches.length)} / ${batches.length}`
      const settled = await settleTemplateSuggestionBatches(currentBatches, operations => suggestTemplateStepMappings({
        project_id: projectId,
        expected_template_revision: templateRevision,
        ...(targetLeafKeys?.length ? { target_group_ids: targetLeafKeys } : {}),
        include_llm: !targetLeafKeys?.length,
        operations,
      }), applyResponse)
      if (!isCurrent()) return
      failedBatchCount += settled.failedCount
      updateRecommendationWarnings()
    }
    if (!isCurrent()) return
    updateRecommendationWarnings()
  } catch {
    if (!isCurrent()) return
    mappingWarnings.value = ['智能推荐暂时不可用，已保留当前映射和人工操作。']
  } finally {
    if (isCurrent()) {
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
  const projectId = props.projectId
  const revision = model.templateRevision.value
  const pending = suggestSteps()
  const runId = dialogRunId.value
  await pending
  if (runId === dialogRunId.value && projectId === props.projectId && revision === model.templateRevision.value && props.modelValue) {
    await suggestPrecisions()
  }
}

async function saveStepMappings() {
  if (recognizing.value || precisionLoading.value || model.loading.value || model.saving.value) return false
  if (syncChangedDraftBase()) return false
  precisionValidationAttempted.value = true
  if (missingPrecisionOperations.value.length) {
    await focusMissingPrecision()
    return false
  }
  transientError.value = ''
  const confirmed = draftStatus.value.validSteps
  mappingWarnings.value = []
  model.draftStepMappings.value = confirmed
  const runId = dialogRunId.value
  const saved = await model.saveStepMappings(mappingOutputOperations(), {
    step_order_by_process: stepOrderByProcess.value,
    ...(props.routeVersionId ? { expected_route_version_id: props.routeVersionId } : {}),
    hidden_step_keys: [...hiddenStepKeys.value], waived_group_paths: waivedGroupPaths.value.map(path => [...path]),
  }, ...(props.beforeSave ? [props.beforeSave] as const : [] as const))
  if (runId !== dialogRunId.value || !props.modelValue) return false
  if (!saved) {
    syncChangedDraftBase()
    return false
  }
  if (model.error.value || !model.template.value) return false
  draftTemplateRevision.value = model.templateRevision.value
  draftStepMappings.value = mappingRecord(model.template.value.step_mappings || [])
  savedSignature.value = JSON.stringify(Object.values(draftStepMappings.value))
  savedPrecisionSignature.value = JSON.stringify(precisionOverrides.value)
  draftStepOrder.value = model.template.value.step_order_by_process || stepOrderByProcess.value
  draftHiddenStepKeys.value = model.template.value.hidden_step_keys || []
  draftWaivedGroupPaths.value = model.template.value.waived_group_paths || []
  savedExceptionSignature.value = JSON.stringify(exceptionState.value)
  const unconfigured = savedStatus.value.missingFeatureGroups
  mappingWarnings.value = unconfigured.length
    ? [
      `已保存，仍有 ${unconfigured.length} 个分组未关联。`,
      unconfigured.map(leaf => leaf.path.join(' / ')).join('、'),
    ]
    : ['工步映射已保存。']
  clearTemplateStepMappingDraft(props.projectId)
  clearTemplateMappingEdits(editContext.value)
  emit('save', {
    stepMappings: model.template.value.step_mappings || [],
    templateRevision: model.templateRevision.value,
    hiddenStepKeys: [...hiddenStepKeys.value],
    waivedGroupPaths: waivedGroupPaths.value.map(path => [...path]),
  })
  if (!props.embedded) closeDialog()
  return savedStatus.value.validCount > 0 || savedStatus.value.waivedFeatureGroups.length > 0
}

async function handlePrimaryAction() {
  if (primaryActionDisabled.value) return
  await saveStepMappings()
}

function closeDialog() {
  if (mappingEditsLocked.value) return
  dialogRunId.value += 1
  invalidatePrecisionSuggestions()
  recognizing.value = false
  recommendationProgress.value = '正在推荐'
  dismissImportDialog()
}

function dismissImportDialog() {
  if (model.loading.value || model.saving.value) return
  if (isReplacing.value) {
    cancelReplacement()
    return
  }
  pendingFile.value = null
  transientError.value = ''
  model.cancelPreview()
  importDialogOpen.value = false
  if (!props.embedded) emit('update:modelValue', false)
}

function handleCancel() {
  if (mappingEditsLocked.value) return
  if (!props.embedded) {
    closeDialog()
    return
  }
  dialogRunId.value += 1
  invalidatePrecisionSuggestions()
  recognizing.value = false
  recommendationProgress.value = '正在推荐'
  emit('cancel')
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
}

.tgmd-dialog {
  width: min(960px, calc(100vw - 48px));
  height: min(680px, calc(100vh - 64px));
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 1px solid var(--pm-border-strong);
  border-radius: var(--pm-radius-dialog);
  background: var(--pm-surface-subtle);
  box-shadow: var(--pm-shadow-popup);
  color: var(--pm-text);
  transition: all 180ms ease;
}

.tgmd-page {
  width: 100%;
  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  overflow: hidden;
  background: transparent;
  color: var(--pm-text);
}

.tgmd-page .tgmd-workspace {
  min-height: 0;
  flex: 1;
}

.tgmd-page-loading,
.tgmd-empty-state,
.tgmd-page-error {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
}

.tgmd-page-loading,
.tgmd-page-error {
  color: var(--text-secondary, var(--pm-text-secondary));
  font-size: 13px;
}

.tgmd-empty-state {
  padding: 32px 20px;
  background: var(--bg-card, var(--pm-surface));
  text-align: center;
}

.tgmd-empty-icon {
  width: 52px;
  height: 52px;
  display: grid;
  place-items: center;
  border: 1px solid var(--pm-primary-border);
  border-radius: 14px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.tgmd-empty-icon svg {
  width: 24px;
  height: 24px;
}

.tgmd-empty-state h2 {
  margin: 4px 0 0;
  color: var(--pm-text);
  font-size: 18px;
  font-weight: 650;
}

.tgmd-empty-state p {
  max-width: 420px;
  margin: 0;
  color: var(--text-secondary, var(--pm-text-secondary));
  font-size: 13px;
  line-height: 1.65;
}

.tgmd-empty-state .btn {
  min-height: 40px;
  margin-top: 6px;
  padding: 0 18px;
  font-size: 13px;
}

.tgmd-empty-hint {
  color: var(--pm-text-muted);
  font-size: 12px;
}

.tgmd-page :focus-visible,
.tgmd-backdrop :focus-visible {
  outline: 2px solid var(--pm-primary);
  outline-offset: 2px;
}

/* Compact modal specifically for file upload state */
.tgmd-dialog.is-compact-upload {
  width: min(480px, calc(100vw - 32px));
  height: auto;
  min-height: auto;
  border-radius: 8px;
  box-shadow: 0 12px 28px rgba(15, 23, 42, 0.2);
}

.tgmd-dialog.tgmd-import-modal:not(.is-compact-upload) {
  width: min(840px, calc(100vw - 32px));
  height: min(680px, calc(100vh - 48px));
}

.tgmd-dialog.tgmd-import-modal.is-compact-upload {
  width: min(520px, calc(100vw - 32px));
  height: auto;
  min-height: 0;
}

.tgmd-modal-notice {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  gap: 12px;
  padding: 24px;
  color: var(--text-secondary, var(--pm-text-secondary));
  text-align: center;
}

.tgmd-modal-notice p {
  margin: 0;
  font-size: 13px;
}

/* Header */
.tgmd-header {
  min-height: 48px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 6px 12px;
  border-bottom: 1px solid var(--pm-border);
  background: var(--pm-surface);
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
  flex-shrink: 0;
  white-space: nowrap;
  font-size: 14px;
  font-weight: 700;
  line-height: 1.2;
  color: var(--pm-text);
}

.tgmd-title-tag {
  padding: 1px 7px;
  border-radius: 4px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
  font-size: 12px;
  font-weight: 600;
  border: 1px solid var(--pm-primary-border);
  white-space: nowrap;
}

.tgmd-file-inline {
  min-width: 0;
  overflow: hidden;
  color: var(--pm-text-secondary);
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
  color: var(--pm-text-muted);
}

.tgmd-status-pill {
  min-width: 0;
  max-width: 110px;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 1px 6px;
  border: 1px solid var(--pm-border);
  border-radius: 999px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font-size: 12px;
  font-weight: 600;
  line-height: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 1;
}

.tgmd-status-pill.is-live {
  border-color: var(--pm-primary-border);
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
}

.tgmd-file-info {
  margin: 2px 0 0;
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
}

.tgmd-file-badge {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  color: var(--pm-text-secondary);
  font-weight: 500;
}

.tgmd-file-badge svg {
  width: 13px;
  height: 13px;
  color: var(--pm-primary);
}

.tgmd-part-badge {
  color: var(--pm-text-muted);
  padding-left: 8px;
  border-left: 1px solid var(--pm-border-strong);
}

.tgmd-subtitle-hint {
  margin: 2px 0 0;
  color: var(--pm-text-muted);
  font-size: 12px;
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
  border: 1px solid var(--pm-border-strong);
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  cursor: pointer;
  transition: all 120ms ease;
}

.tgmd-command {
  min-height: 28px;
  padding: 0 9px;
  border-radius: 5px;
  font-size: 12px;
  font-weight: 500;
}

.tgmd-command:hover {
  border-color: var(--pm-primary-border);
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
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
  border: 1px solid var(--pm-border);
  color: var(--pm-text-muted);
}

.tgmd-icon-button:hover {
  border-color: var(--pm-border-strong);
  background: var(--pm-surface-subtle);
  color: var(--pm-text);
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
  border-bottom: 1px solid var(--pm-danger-border);
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
  font-size: 12px;
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
  color: var(--pm-text-muted);
  font-size: 13px;
}

.tgmd-spinner {
  width: 18px;
  height: 18px;
  display: inline-block;
  border: 2px solid var(--pm-border-strong);
  border-top-color: var(--pm-primary);
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
  border-top-color: var(--pm-surface);
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
  border: 1.5px dashed var(--pm-primary-border);
  border-radius: 8px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  cursor: pointer;
  transition: all 150ms ease;
  text-align: left;
}

.tgmd-dropzone:hover,
.tgmd-dropzone-ready {
  border-color: var(--pm-primary);
  background: var(--pm-primary-soft);
}

.tgmd-drop-icon-wrap {
  width: 40px;
  height: 40px;
  flex: 0 0 40px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  transition: all 150ms ease;
}

.tgmd-dropzone:hover .tgmd-drop-icon-wrap,
.tgmd-dropzone-ready .tgmd-drop-icon-wrap {
  background: var(--pm-primary-soft);
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
  color: var(--pm-text);
  line-height: 1.3;
}

.tgmd-dropzone-sub {
  color: var(--pm-text-muted);
  font-size: 12px;
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
  border-right: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
}

/* File Status Card */
.tgmd-preview-file-card {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 16px 16px 14px;
  border-bottom: 1px solid var(--pm-border);
}

.tgmd-preview-file-card.is-ok {
  background: var(--pm-success-soft);
  border-bottom-color: var(--pm-success-border);
}

.tgmd-preview-file-card.is-err {
  background: var(--pm-danger-soft);
  border-bottom-color: var(--pm-danger-border);
}

.tgmd-preview-file-icon {
  width: 36px;
  height: 36px;
  flex: 0 0 36px;
  display: grid;
  place-items: center;
  border-radius: 8px;
  background: var(--pm-primary-soft);
}

.tgmd-preview-file-card.is-ok .tgmd-preview-file-icon {
  background: var(--pm-success-soft);
}

.tgmd-preview-file-card.is-err .tgmd-preview-file-icon {
  background: var(--pm-danger-soft);
}

.tgmd-preview-file-icon svg {
  width: 18px;
  height: 18px;
  color: var(--pm-primary);
}

.tgmd-preview-file-card.is-ok .tgmd-preview-file-icon svg {
  color: var(--pm-success);
}

.tgmd-preview-file-card.is-err .tgmd-preview-file-icon svg {
  color: var(--pm-danger);
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
  color: var(--pm-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.tgmd-preview-filedesc {
  display: block;
  font-size: 12px;
  color: var(--pm-text-muted);
  line-height: 1.4;
}

.tgmd-validation-badge {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 700;
  white-space: nowrap;
}

.tgmd-validation-badge.is-valid {
  background: var(--pm-success-soft);
  color: var(--pm-success);
  border: 1px solid var(--pm-success-border);
}

.tgmd-validation-badge.is-invalid {
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
  border: 1px solid var(--pm-danger-border);
}

/* Key Metrics - 3 columns, big numbers */
.tgmd-preview-metrics {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  border-bottom: 1px solid var(--pm-border);
}

.tgmd-metric {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 14px 8px;
  gap: 4px;
  border-right: 1px solid var(--pm-border);
}

.tgmd-metric:last-child {
  border-right: 0;
}

.tgmd-metric-val {
  font-size: 28px;
  font-weight: 800;
  line-height: 1;
  color: var(--pm-text);
}

.tgmd-metric-accent {
  color: var(--pm-primary);
}

.tgmd-metric-ok {
  color: var(--pm-success);
}

.tgmd-metric-error {
  color: var(--pm-danger);
}

.tgmd-metric-label {
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-text-muted);
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

/* Meta info rows */
.tgmd-preview-meta {
  display: flex;
  flex-direction: column;
  border-bottom: 1px solid var(--pm-border);
}

.tgmd-meta-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--pm-surface-subtle);
}

.tgmd-meta-row:last-child {
  border-bottom: 0;
}

.tgmd-meta-key {
  font-size: 12px;
  color: var(--pm-text-muted);
  font-weight: 500;
}

.tgmd-meta-val {
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-text-secondary);
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
  border-bottom: 1px solid var(--pm-border);
}

.tgmd-issue-section-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  background: var(--pm-warning-soft);
  border-bottom: 1px solid var(--pm-warning-border);
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-warning);
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
  background: var(--pm-warning);
  color: var(--pm-surface);
  font-size: 12px;
  font-weight: 700;
}

.tgmd-issue-list {
  max-height: 220px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  background: var(--pm-warning-soft);
}

.tgmd-issue-row {
  display: flex;
  align-items: flex-start;
  gap: 8px;
  padding: 8px 16px;
  border-bottom: 1px solid var(--pm-warning-border);
  font-size: 12px;
}

.tgmd-issue-dot {
  width: 5px;
  height: 5px;
  flex: 0 0 5px;
  border-radius: 50%;
  background: var(--pm-warning);
  margin-top: 5px;
}

.tgmd-issue-body {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.tgmd-issue-body strong {
  font-weight: 600;
  color: var(--pm-danger);
}

.tgmd-issue-detail {
  color: var(--pm-warning);
  font-size: 12px;
}

/* Impact section */
.tgmd-impact {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 12px 16px;
  border-bottom: 1px solid var(--pm-border);
}

.tgmd-impact-header {
  font-size: 12px;
  font-weight: 700;
  color: var(--pm-text-muted);
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
  background: var(--pm-success-soft);
  border: 1px solid var(--pm-success-border);
}

.tgmd-impact-stat.is-lost {
  background: var(--pm-warning-soft);
  border: 1px solid var(--pm-warning-border);
}

.tgmd-impact-num {
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
}

.tgmd-impact-stat.is-keep .tgmd-impact-num {
  color: var(--pm-success);
}

.tgmd-impact-stat.is-lost .tgmd-impact-num {
  color: var(--pm-warning);
}

.tgmd-impact-desc {
  font-size: 12px;
  font-weight: 600;
  color: var(--pm-text-muted);
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
  background: var(--pm-warning-soft);
  font-size: 12px;
}

.tgmd-invalidated-op {
  font-weight: 600;
  color: var(--pm-text);
}

.tgmd-invalidated-path {
  color: var(--pm-text-muted);
  font-size: 12px;
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
  background: var(--pm-surface);
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
  border-bottom: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
}

.tgmd-section-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--pm-text);
}

.tgmd-section-header span {
  color: var(--pm-text-muted);
  font-size: 12px;
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
  border: 1px solid var(--pm-border);
  border-radius: 7px;
  background: var(--pm-surface);
}

.tgmd-pane {
  display: flex;
  flex-direction: column;
  overflow: hidden;
  border: 0;
  border-radius: 0;
  background: var(--pm-surface);
}

.tgmd-operation-pane {
  border-right: 1px solid var(--pm-border);
}

.tgmd-pane-header {
  flex: 0 0 auto;
  min-height: 38px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  padding: 5px 10px;
  border-bottom: 1px solid var(--pm-border);
  background: var(--pm-surface-subtle);
  border-radius: 0;
}

.tgmd-pane-header h3 {
  margin: 0;
  font-size: 13px;
  font-weight: 700;
  color: var(--pm-text);
}

.tgmd-pane-subtitle {
  color: var(--pm-text-muted);
  font-size: 12px;
  white-space: nowrap;
}

/* Active step badge in left header */
.tgmd-op-header-left {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 6px;
  min-width: 0;
  flex: 1;
  overflow: hidden;
}

.tgmd-op-header-left h3 { flex: 0 0 auto; white-space: nowrap; }
.tgmd-op-header-left .tgmd-pane-subtitle { min-width: 0; flex: 0 1 auto; overflow: hidden; text-overflow: ellipsis; }

.tgmd-left-progress {
  flex: 0 0 auto;
  padding: 1px 6px;
  border: 1px solid var(--pm-primary-border);
  border-radius: 999px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
  font-size: 12px;
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
  background: var(--pm-primary-soft);
  border: 1px solid var(--pm-primary-border);
  color: var(--pm-primary-hover);
  font-size: 12px;
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
  border: 1px solid var(--pm-border-strong);
  border-radius: 4px;
  background: var(--pm-surface-subtle);
  transition: all 120ms ease;
}

.tgmd-search-box:focus-within {
  border-color: var(--pm-primary);
  background: var(--pm-surface);
}

.tgmd-search-box svg {
  width: 12px;
  height: 12px;
  color: var(--pm-text-muted);
  flex: 0 0 auto;
}

.tgmd-search-box input {
  min-width: 0;
  width: 100%;
  border: 0;
  outline: 0;
  background: transparent;
  font-size: 12px;
  color: var(--pm-text);
}

.tgmd-search-clear {
  width: 14px;
  height: 14px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: var(--pm-text-muted);
  cursor: pointer;
  padding: 0;
}

.tgmd-search-clear:hover {
  color: var(--pm-text-secondary);
}

.tgmd-selected-inline {
  min-width: 0;
  overflow: hidden;
  color: var(--pm-text-secondary);
  font-size: 12px;
  font-weight: 600;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-selected-inline {
  color: var(--pm-primary);
}

.tgmd-smart-button {
  height: 26px;
  padding: 0 9px;
  border-color: var(--pm-primary-border);
  border-radius: 4px;
  color: var(--pm-primary-hover);
  background: var(--pm-primary-soft);
  font-size: 12px;
  font-weight: 600;
}

.tgmd-smart-button:hover:not(:disabled) {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
}

.tgmd-smart-button:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.tgmd-clear-selection {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--pm-border);
  background: var(--pm-surface);
  color: var(--pm-text-muted);
  font-size: 12px;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.tgmd-toggle-group-selection {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 4px 8px;
  border-radius: 6px;
  border: 1px solid var(--pm-primary-border);
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
  white-space: nowrap;
}

.tgmd-toggle-group-selection:hover {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
}

.tgmd-toggle-group-selection svg {
  width: 12px;
  height: 12px;
}

/* Link Button (inline in tree header) */
.tgmd-link-btn {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  height: 26px;
  padding: 0 9px;
  border-radius: 5px;
  border: 1px solid var(--pm-border-strong);
  background: var(--pm-surface-subtle);
  color: var(--pm-text-muted);
  font-size: 12px;
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
  border-color: var(--pm-primary);
  background: var(--pm-primary);
  color: var(--pm-surface);
  cursor: pointer;
  box-shadow: 0 2px 6px rgba(36, 95, 168, 0.3);
}

.tgmd-link-btn.is-active:hover {
  background: var(--pm-primary-hover);
  box-shadow: 0 2px 8px rgba(36, 95, 168, 0.32);
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
  font-size: 12px;
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
  border: 1px solid var(--pm-border-strong);
  background: var(--pm-surface);
  box-shadow: 0 10px 25px -4px rgba(15, 23, 42, 0.16), 0 4px 10px -2px rgba(15, 23, 42, 0.08);
  font-size: 12px;
  color: var(--pm-text);
  pointer-events: none;
}

.tgmd-popover-card::before {
  content: '';
  position: absolute;
  top: -5px;
  right: 18px;
  width: 8px;
  height: 8px;
  background: var(--pm-surface);
  border-left: 1px solid var(--pm-border-strong);
  border-top: 1px solid var(--pm-border-strong);
  transform: rotate(45deg);
}

.tgmd-popover-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding-bottom: 5px;
  margin-bottom: 5px;
  border-bottom: 1px solid var(--pm-surface-subtle);
}

.tgmd-popover-title {
  font-weight: 700;
  color: var(--pm-text);
  font-size: 12px;
}

.tgmd-popover-badge {
  padding: 1px 6px;
  border-radius: 999px;
  background: var(--pm-primary-soft);
  color: var(--pm-primary-hover);
  font-size: 12px;
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
  background: var(--pm-surface-subtle);
}

.tgmd-popover-path {
  color: var(--pm-text-muted);
  font-size: 12px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-popover-feature {
  flex-shrink: 0;
  font-weight: 600;
  color: var(--pm-primary);
  background: var(--pm-primary-soft);
  padding: 1px 5px;
  border-radius: 3px;
  font-size: 12px;
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
  border: 1px solid var(--pm-border);
  border-radius: 5px;
  background: var(--pm-surface);
  overflow: hidden;
}

.tgmd-operation-heading {
  display: flex;
  align-items: stretch;
  min-width: 0;
  background: var(--pm-surface-subtle);
}

.tgmd-operation-toggle {
  flex: 1 1 auto;
  min-width: 0;
  width: 100%;
  min-height: 32px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  padding: 0 8px;
  border: 0;
  background: var(--pm-surface-subtle);
  color: var(--pm-text);
  text-align: left;
  cursor: pointer;
  transition: background-color 120ms ease;
  position: relative;
}

.tgmd-operation-toggle:hover {
  background: var(--pm-surface-subtle);
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
  color: var(--pm-text-muted);
  transition: transform 150ms ease;
  flex: 0 0 auto;
}

.tgmd-op-title svg.open {
  transform: rotate(90deg);
}

.tgmd-op-title strong {
  min-width: 0;
  flex: 0 1 auto;
  font-size: 12px;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgmd-process-type {
  flex: 0 0 auto;
  padding: 2px 5px;
  border-radius: 4px;
  font-size: 12px;
  font-weight: 600;
  line-height: 1.2;
  white-space: nowrap;
}

.tgmd-process-type.is-standard {
  background: var(--pm-primary-soft);
  color: var(--pm-primary);
}

.tgmd-process-type.is-auxiliary {
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
}

.tgmd-op-summary {
  color: var(--pm-text-muted);
  font-size: 12px;
  flex: 0 0 auto;
}

.tgmd-precision-field {
  display: flex;
  align-items: center;
  gap: 5px;
  flex: 0 0 auto;
  padding: 3px 7px 3px 2px;
  color: var(--pm-text-secondary);
  font-size: 12px;
}

.tgmd-precision-field select {
  width: 76px;
  height: 24px;
  padding: 0 4px;
  border: 1px solid var(--pm-border-strong);
  border-radius: 4px;
  background: var(--pm-surface);
  color: var(--pm-text);
  font-size: 12px;
}

.tgmd-precision-field.is-invalid {
  color: var(--pm-danger);
}

.tgmd-precision-field.is-invalid select {
  border-color: var(--pm-danger);
  background: var(--pm-danger-soft);
}

.tgmd-precision-suggestion {
  color: var(--pm-primary);
  font-size: 12px;
  white-space: nowrap;
}

.tgmd-auxiliary-precision {
  display: flex;
  align-items: center;
  flex: 0 0 auto;
  padding: 0 9px;
  color: var(--pm-text-muted);
  font-size: 12px;
}

.tgmd-step-list {
  border-top: 1px solid var(--pm-surface-subtle);
}

.tgmd-operation-empty {
  padding: 9px 12px 9px 36px;
  color: var(--pm-text-muted);
  font-size: 12px;
  line-height: 1.4;
}

.tgmd-step-row {
  position: relative;
  min-height: 40px;
  display: grid;
  grid-template-columns: 26px minmax(0, 1fr) auto;
  align-items: center;
  gap: 6px;
  padding: 3px 8px;
  border-bottom: 1px solid var(--pm-surface-subtle);
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
  cursor: pointer;
  transition: all 120ms ease;
}

.tgmd-step-row:last-child {
  border-bottom: 0;
}

.tgmd-step-row:hover {
  background: var(--pm-primary-soft);
}

/* Active Step - Matches SourceRoutePanel srp-op--active */
.tgmd-step-row.is-selected {
  background: var(--pm-primary-soft);
  box-shadow: inset 3px 0 var(--pm-primary);
}

.tgmd-step-row.is-mapped:not(.is-selected) {
  box-shadow: inset 3px 0 var(--pm-success);
}

/* Monospace Step Order Badge - Matches srp-op-seq */
.tgmd-step-order {
  width: 22px;
  height: 18px;
  display: grid;
  place-items: center;
  border-radius: 4px;
  background: var(--pm-surface-subtle);
  color: var(--pm-text-secondary);
  font: 11px/1 ui-monospace, SFMono-Regular, Menlo, monospace;
  font-weight: 700;
}

.tgmd-step-row.is-selected .tgmd-step-order {
  background: var(--pm-primary);
  color: var(--pm-surface);
}

.tgmd-step-content {
  min-width: 0;
}

.tgmd-step-actions { display: flex; flex: 0 0 auto; align-items: center; gap: 2px; }
.tgmd-hide-step { display: inline-flex; align-items: center; gap: 3px; padding: 3px 5px; border: 0; border-radius: 4px; background: transparent; color: var(--pm-text-muted); font-size: 12px; cursor: pointer; }
.tgmd-hide-step svg { width: 12px; height: 12px; }
.tgmd-hide-step:hover:not(:disabled) { background: var(--pm-surface-subtle); color: var(--pm-text-secondary); }
.tgmd-hide-step:disabled { cursor: not-allowed; opacity: .55; }


.tgmd-step-name {
  display: block;
  font-size: 13px;
  font-weight: 600;
  color: var(--pm-text);
  line-height: 1.3;
}

.tgmd-step-count-text {
  display: block;
  margin-top: 2px;
  color: var(--pm-success);
  font-size: 12px;
  font-weight: 500;
}

.tgmd-step-eligibility {
  display: inline-flex;
  margin-left: 6px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 500;
}

.tgmd-step-unmapped-text {
  display: block;
  margin-top: 2px;
  color: var(--pm-text-muted);
  font-size: 12px;
  font-style: italic;
}

.tgmd-step-mapping-summary {
  display: block;
  margin-top: 2px;
  overflow: hidden;
  color: var(--pm-primary);
  font-size: 12px;
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
  border: 1px solid var(--pm-success-border);
  border-radius: 4px;
  background: var(--pm-success-soft);
  color: var(--pm-success);
  font-size: 12px;
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
  color: var(--pm-success);
  cursor: pointer;
}

.tgmd-chip-tag button:hover {
  background: var(--pm-success-soft);
  color: var(--pm-success);
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
  border: 1px solid var(--pm-primary-border);
  border-radius: 4px;
  background: var(--pm-surface);
  color: var(--pm-primary-hover);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
  margin-left: 4px;
}

.tgmd-current-suggest:hover:not(:disabled) {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
}

.tgmd-current-suggest:disabled {
  color: var(--pm-text-muted);
  border-color: var(--pm-border);
  background: var(--pm-surface-subtle);
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
  border: 1px solid var(--pm-border-strong);
  border-radius: 4px;
  background: var(--pm-surface);
  color: var(--pm-text-muted);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
}

.tgmd-clear-selection:hover:not(:disabled) {
  border-color: var(--pm-danger-border);
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
}

.tgmd-clear-selection:disabled {
  color: var(--pm-text-muted);
  border-color: var(--pm-border);
  background: var(--pm-surface-subtle);
  cursor: not-allowed;
}

.tgmd-clear-selection svg {
  width: 12px;
  height: 12px;
  flex-shrink: 0;
}

.tgmd-empty {
  padding: 18px 12px;
  color: var(--pm-text-muted);
  text-align: center;
  font-size: 12px;
}

/* Footer */
.tgmd-footer {
  min-height: 44px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 6px 12px;
  border-top: 1px solid var(--pm-border);
  background: var(--pm-surface);
}

.tgmd-footer-left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.tgmd-footer-status {
  min-width: 0;
  flex: 1 1 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  color: var(--text-secondary, var(--pm-text-muted));
  font-size: 12px;
  line-height: 1.5;
  overflow-wrap: anywhere;
  white-space: normal;
}

.tgmd-footer-status .is-warning {
  color: var(--pm-warning);
}

.tgmd-page > .tgmd-footer > .tgmd-clear-all,
.tgmd-page > .tgmd-footer > .tgmd-footer-actions {
  flex-shrink: 0;
}

.tgmd-page > .tgmd-footer > .tgmd-footer-actions {
  margin-left: auto;
}

.tgmd-clear-all {
  min-height: 28px;
  padding: 0 10px;
  border-radius: 5px;
  border-color: var(--pm-danger-border);
  background: var(--pm-danger-soft);
  color: var(--pm-danger);
  font-size: 12px;
  font-weight: 600;
}

.tgmd-clear-all:hover:not(:disabled) {
  background: var(--pm-danger-soft);
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
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 120ms ease;
}

.btn:disabled {
  opacity: 0.55;
  cursor: not-allowed;
}

.btn-outline {
  border: 1px solid var(--pm-border-strong);
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
}

.btn-outline:hover:not(:disabled) {
  border-color: var(--pm-text-muted);
  background: var(--pm-surface-subtle);
}

.btn-primary {
  border: 1px solid var(--pm-primary-hover);
  background: var(--pm-primary);
  color: var(--pm-surface);
}

.btn-primary:hover:not(:disabled) {
  background: var(--pm-primary-hover);
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
  background: var(--pm-border-strong);
  border-radius: 3px;
}

@media (max-width: 860px) {
  .tgmd-dialog {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
  }
  .tgmd-dialog.tgmd-import-modal:not(.is-compact-upload) {
    width: calc(100vw - 16px);
    height: calc(100vh - 16px);
  }
  .tgmd-dialog.tgmd-import-modal.is-compact-upload {
    width: calc(100vw - 24px);
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
    border-bottom: 1px solid var(--pm-border);
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

<style scoped>
/* Recommendation actions stay beside their source step. */
.tgmd-step-candidate { margin-top: 6px; padding: 6px 8px; border: 1px solid var(--pm-primary-border); border-radius: 4px; background: var(--pm-primary-soft); color: var(--pm-primary); font-size: 12px; line-height: 1.5; overflow-wrap: anywhere; }
.tgmd-step-candidate > div { display: flex; gap: 8px; margin-top: 4px; }
.tgmd-step-candidate .tgmd-command, .tgmd-invalid-mapping .tgmd-command { min-height: 24px; padding: 2px 6px; font-size: 12px; }
.tgmd-invalid-mappings { margin: 8px; color: var(--pm-warning); font-size: 12px; }
.tgmd-invalid-mappings summary { cursor: pointer; }
.tgmd-invalid-mapping { display: flex; align-items: center; justify-content: space-between; gap: 8px; padding: 6px 0; overflow-wrap: anywhere; }
.tgmd-smart-status { display: flex; justify-content: space-between; gap: 16px; padding: 7px 18px; border-bottom: 1px solid var(--pm-primary-border); background: var(--pm-primary-soft); color: var(--pm-primary); font-size: 12px; }
.tgmd-smart-warning { color: var(--pm-warning); text-align: right; }
.tgmd-page > .tgmd-header { min-height: 40px; flex: 0 0 auto; padding: 4px 10px; border: 1px solid var(--pm-border); border-radius: 8px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03); }
.tgmd-page > .tgmd-workspace { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 10px; flex: 1 1 auto; min-height: 0; margin: 0; padding: 0; overflow: hidden; border: 0; border-radius: 0; background: transparent; }
.tgmd-page > .tgmd-workspace > .tgmd-pane { min-width: 0; border: 1px solid var(--pm-border); border-radius: 8px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03); }
.tgmd-page > .tgmd-workspace > .tgmd-operation-pane { border-right: 1px solid var(--pm-border); }
.tgmd-pane-header { min-height: 38px; align-items: center; gap: 6px; padding: 5px 10px; background: var(--pm-surface-subtle); }
.tgmd-pane-header h3, .tgmd-pane-header span { margin: 0; }
.tgmd-pane-header h3 { font-size: 13px; }
.tgmd-pane-header > div:first-child { min-width: 0; }
.tgmd-pane-header > div:first-child > span { overflow-wrap: anywhere; color: var(--pm-text-muted); font-size: 12px; }
.tgmd-group-progress { color: var(--pm-primary); font-weight: 600; white-space: nowrap; }
.tgmd-active-target { padding: 9px 12px; border-top: 1px solid var(--pm-border); background: var(--pm-primary-soft); }
.tgmd-active-target span, .tgmd-active-target small { display: block; color: var(--pm-text-muted); font-size: 12px; }
.tgmd-active-target strong { display: block; margin-top: 2px; color: var(--pm-primary); font-size: 12px; overflow-wrap: anywhere; }
.tgmd-active-target small { margin-top: 3px; }
.tgmd-feature-summary { margin: 0; padding: 9px 12px; border-bottom: 1px solid var(--pm-border); background: var(--pm-surface-subtle); color: var(--pm-text-muted); font-size: 12px; }
.tgmd-operation-header { align-items: center; }
.tgmd-operation-tools { min-width: 0; }
.tgmd-review-guidance { margin: 0; padding: 7px 11px; border-bottom: 1px solid var(--pm-border); background: var(--pm-surface-subtle); color: var(--pm-text-muted); font-size: 12px; line-height: 1.5; }
.tgmd-title-row { flex-wrap: wrap; }
.tgmd-page > .tgmd-header .tgmd-header-guidance { flex: 1 1 280px; min-width: 180px; padding: 0; border: 0; background: transparent; color: var(--pm-text-muted); font-size: 12px; line-height: 1.4; }
.tgmd-smart-button { height: 26px; min-height: 26px; padding: 0 9px; border-color: var(--pm-primary-border); border-radius: 4px; color: var(--pm-primary-hover); background: var(--pm-primary-soft); white-space: nowrap; }
.tgmd-page > .tgmd-footer { min-height: 52px; flex: 0 0 auto; padding: 7px 12px; border: 1px solid var(--pm-border); border-radius: 8px; box-shadow: 0 1px 3px rgba(15, 23, 42, 0.03); }
@media (max-width: 860px) {
  .tgmd-page { height: 100%; min-height: 0; }
  .tgmd-page > .tgmd-workspace { grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); flex: 1 1 auto; min-height: 0; overflow: hidden; }
  .tgmd-page > .tgmd-workspace > .tgmd-pane { height: auto; min-height: 0; }
  .tgmd-page > .tgmd-workspace > .tgmd-operation-pane { border-right: 1px solid var(--pm-border); border-bottom: 1px solid var(--pm-border); }
  .tgmd-operation-header, .tgmd-tree-header { align-items: center; flex: 0 0 auto; flex-direction: row; }
  .tgmd-tree-header-right { flex-wrap: wrap; }
  .tgmd-tree-header-right .tgmd-search-box { flex: 1 1 100px; min-width: 100px; }
  .tgmd-page > .tgmd-footer { position: static; margin-top: 0; }
  .tgmd-page > .tgmd-footer .tgmd-footer-actions { margin-left: auto; }
  .tgmd-smart-status { align-items: flex-start; flex-direction: column; }
  .tgmd-smart-warning { text-align: left; }
}

@media (max-width: 520px) {
  .tgmd-page > .tgmd-footer { align-items: stretch; flex-direction: column; gap: 8px; }
  .tgmd-page > .tgmd-footer .tgmd-footer-status { flex: 0 0 auto; }
  .tgmd-page > .tgmd-footer .tgmd-footer-actions { width: 100%; justify-content: flex-end; }
}

/* Mapping density is local; each tree retains its own scroll container. */
.tgmd-page { gap: 6px; font-size: 13px; }
.tgmd-page > .tgmd-header { padding: 4px 10px; border-color: var(--pm-border); border-radius: var(--pm-radius-card); box-shadow: var(--pm-shadow-card); }
.tgmd-page > .tgmd-footer { padding: 10px 12px; border-color: var(--pm-border); border-radius: var(--pm-radius-card); box-shadow: var(--pm-shadow-card); }
.tgmd-page > .tgmd-header .tgmd-header-guidance { flex: 1 1 240px; min-width: 0; font-size: 12px; line-height: 18px; }
.tgmd-title-row { gap: 4px 8px; }
.tgmd-title-row h2 { font-size: 16px; line-height: 24px; font-weight: 600; }
.tgmd-page > .tgmd-header .tgmd-title-row h2 { font-size: 14px; line-height: 20px; font-weight: 600; }
.tgmd-title-tag, .tgmd-process-type, .tgmd-status-pill, .tgmd-active-step-badge { border-radius: 4px; font-weight: 500; line-height: 18px; }
.tgmd-page > .tgmd-workspace { gap: 8px; font-size: 12px; line-height: 18px; }
.tgmd-page .tgmd-tree-scroll { --tgtn-name-size: 12px; --tgtn-line-height: 18px; --tgtn-row-height: 28px; --tgtn-row-spacing: 1px; --tgtn-row-padding: 2px; --tgtn-control-height: 24px; --tgtn-control-padding: 1px 6px; --tgtn-feature-spacing: 1px 0 2px; padding: 4px 6px 4px 4px; }
.tgmd-pane-header { flex-wrap: wrap; gap: 4px 6px; padding: 4px 8px; background: var(--pm-surface-subtle); }
.tgmd-pane-header h3 { font-size: 13px; font-weight: 600; line-height: 18px; }
.tgmd-operation-header .tgmd-op-header-left { flex: 1 1 0; min-width: 0; gap: 6px; }
.tgmd-operation-tools, .tgmd-tree-header-right { flex-wrap: wrap; gap: 4px; }
.tgmd-tree-header-right { flex: 1 1 280px; min-width: 0; }
.tgmd-tree-header-left { flex: 0 0 auto; }
.tgmd-operation-tools { margin-left: auto; flex: 0 0 auto; }
.tgmd-operation-header .tgmd-op-header-left h3, .tgmd-tree-header-left h3 { white-space: nowrap; }
.tgmd-left-progress { white-space: nowrap; }
.tgmd-active-step-badge { max-width: 140px; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tgmd-search-box { flex: 1 1 150px; width: auto; min-width: 100px; height: 28px; border-radius: var(--pm-radius-control); background: var(--pm-surface); }
.tgmd-search-box input { font-size: 12px; }
.tgmd-search-box:focus-within { border-color: var(--pm-primary); box-shadow: var(--pm-focus-ring); }
.tgmd-operation-scroll { padding: 4px; overscroll-behavior: contain; scroll-padding: 4px; }
.tgmd-page .tgmd-tree-scroll { overscroll-behavior: contain; scroll-padding: 4px; }
.tgmd-operation-card { margin-bottom: 4px; border-color: var(--pm-border); border-radius: var(--pm-radius-control); }
.tgmd-operation-heading { flex-wrap: wrap; }
.tgmd-operation-toggle { min-height: 30px; width: auto; padding: 3px 6px; flex: 1 1 180px; flex-wrap: wrap; gap: 2px 6px; }
.tgmd-op-title { flex-wrap: wrap; }
.tgmd-op-title strong { font-size: 12px; line-height: 18px; white-space: normal; overflow-wrap: anywhere; }
.tgmd-op-summary { font-size: 12px; white-space: nowrap; }
.tgmd-precision-field { flex: 0 1 auto; margin-left: auto; padding: 2px 6px; flex-wrap: wrap; font-size: 12px; }
.tgmd-precision-field select { min-height: 24px; height: auto; border-radius: var(--pm-radius-control); font-size: 12px; }
.tgmd-step-row { min-height: 34px; grid-template-columns: 22px minmax(0, 1fr) auto; gap: 4px; padding: 3px 6px; }
.tgmd-step-order { font-family: var(--pm-font); font-size: 12px; font-weight: 600; }
.tgmd-step-name { font-size: 12px; line-height: 18px; overflow-wrap: anywhere; }
.tgmd-step-eligibility { margin-left: 0; line-height: 18px; }
.tgmd-step-mapping-summary { white-space: normal; line-height: 18px; overflow-wrap: anywhere; }
.tgmd-step-actions { gap: 2px; }
.tgmd-hide-step { min-height: 24px; padding: 2px 4px; font-size: 12px; line-height: 18px; }
.tgmd-hide-step[data-hide-step-key]:hover:not(:disabled) { background: var(--pm-danger-soft); color: var(--pm-danger); }
.tgmd-step-row.is-selected { background: var(--pm-primary-soft); box-shadow: inset 3px 0 var(--pm-primary); }
.tgmd-step-row.is-mapped:not(.is-selected) { box-shadow: inset 3px 0 var(--pm-success); }
.tgmd-command, .tgmd-smart-button, .tgmd-clear-selection, .tgmd-toggle-group-selection, .tgmd-link-btn, .tgmd-current-suggest, .tgmd-clear-all { min-height: 28px; height: auto; padding: 3px 8px; border-radius: var(--pm-radius-control); font-size: 12px; line-height: 20px; font-weight: 500; box-shadow: none; }
.tgmd-link-btn.is-active, .tgmd-link-btn.is-active:hover { background: var(--pm-primary); border-color: var(--pm-primary); box-shadow: none; }
.btn { min-height: var(--pm-control-height); padding: 5px 12px; border-radius: var(--pm-radius-control); font-size: 13px; line-height: 20px; font-weight: 500; }
.btn-primary, .btn-primary:hover:not(:disabled) { background: var(--pm-primary); border-color: var(--pm-primary); box-shadow: none; }
.btn-primary:hover:not(:disabled) { background: var(--pm-primary-hover); border-color: var(--pm-primary-hover); }
.tgmd-page :focus-visible, .tgmd-backdrop :focus-visible { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.tgmd-empty, .tgmd-operation-empty { padding: 18px 12px; color: var(--pm-text-muted); font-size: 13px; line-height: 20px; }
.tgmd-inline-error { flex: 0 0 auto; border: 1px solid var(--pm-danger-border); border-left-width: 3px; border-radius: var(--pm-radius-control); background: var(--pm-danger-soft); color: var(--pm-danger); font-size: 13px; line-height: 20px; overflow-wrap: anywhere; }
.tgmd-preview-file-card.is-ok { background: var(--pm-success-soft); }
.tgmd-preview-file-card.is-err { background: var(--pm-danger-soft); }
.tgmd-dialog .tgmd-footer { flex-shrink: 0; flex-wrap: wrap; }
@media (max-width: 860px) {
  .tgmd-operation-header .tgmd-op-header-left { flex: 0 1 auto; flex-wrap: wrap; }
  .tgmd-tree-header-right { flex: 1 1 100%; }
}
@media (max-width: 1100px) and (min-width: 721px) {
  .tgmd-step-row { grid-template-columns: 22px minmax(0, 1fr); }
  .tgmd-step-actions { grid-column: 2; justify-self: end; }
}
@media (max-width: 720px) {
  .tgmd-page { height: auto; min-height: 100%; overflow: visible; }
  .tgmd-page > .tgmd-workspace { grid-template-columns: minmax(0, 1fr); grid-template-rows: repeat(2, minmax(0, 1fr)); flex: 1 0 380px; min-height: 380px; }
}
@media (max-width: 520px) {
  .tgmd-header { align-items: flex-start; flex-wrap: wrap; }
  .tgmd-header-actions { margin-left: auto; }
  .tgmd-step-row { grid-template-columns: 26px minmax(0, 1fr); }
  .tgmd-step-actions { grid-column: 2; justify-self: end; }
  .tgmd-footer-actions { flex-wrap: wrap; }
}
@media (max-height: 600px) and (min-width: 721px) {
  /* Keep pane tools and usable trees above the footer; .main-area owns
     overflow when the application header leaves too little viewport height. */
  .tgmd-page { height: auto; min-height: 100%; flex: 1 0 auto; }
  .tgmd-page > .tgmd-workspace { flex: 1 0 320px; min-height: 320px; }
}
.tgmd-page > .tgmd-footer.workflow-nav-footer-inline { min-height: 48px; padding: 0; gap: 0; }
@media (prefers-reduced-motion: reduce) { .tgmd-dialog, .tgmd-page button { transition: none; } .tgmd-spinner { animation: none; } }
</style>
