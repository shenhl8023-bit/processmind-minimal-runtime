<template>
  <div class="tgtn-node">
    <div
      class="tgtn-row"
      :class="{ 'tgtn-row-active': activeKey === node.key, 'tgtn-row-readonly': readonly }"
      :style="{ '--tgtn-depth': String(depth) }"
    >
      <button
        v-if="hasChildren"
        class="tgtn-disclosure"
        type="button"
        :title="expanded ? '收起分组' : '展开分组'"
        :aria-label="expanded ? '收起分组' : '展开分组'"
        @click="expanded = !expanded"
      >
        <ArrowRight :class="{ 'tgtn-disclosure-open': expanded }" />
      </button>
      <span v-else class="tgtn-disclosure-placeholder" />

      <button
        class="tgtn-main"
        type="button"
        :disabled="readonly || !selectableScope"
        :title="featureLeaf ? '查看特征分组' : selectableScope ? '查看分组汇总' : '没有可用特征叶子'"
        @click="$emit('select', node.key)"
      >
        <FolderOpened v-if="!featureLeaf" class="tgtn-kind-icon is-folder" />
        <Aim v-else class="tgtn-kind-icon is-aim" />
        <span class="tgtn-name">{{ node.name }}</span>
        <span v-if="showMetadata" :class="['tgtn-role', featureLeaf ? 'is-feature' : 'is-scope']">
          {{ featureLeaf ? '特征' : '分组' }}
        </span>
        <span v-if="showMetadata && featureLeaf && configuredLeafKeys.includes(node.key)" class="tgtn-status is-configured">
          已配置 {{ mappedCount }}
        </span>
        <span v-else-if="showMetadata && featureLeaf && unconfiguredLeafKeys.includes(node.key)" class="tgtn-status is-unconfigured">未配置</span>
      </button>

      <div
        v-if="featureLeaf && (showMetadata || showFeatureDetails || (showSelectedFeatures && hasSelectedFeature)) && node.feature_selections.length"
        :class="[
          'tgtn-features',
          {
            'is-detail': showFeatureDetails,
            'is-selected': showSelectedFeatures && hasSelectedFeature,
          },
        ]"
      >
        <label
          v-if="featureLeaf && multiSelect"
          v-for="feature in node.feature_selections"
          :key="feature"
          class="tgtn-feature-select"
          :class="{ 'is-checked': isSelectedFeature(feature) }"
        >
          <input
            type="checkbox"
            :checked="isSelectedFeature(feature)"
            :aria-label="`选择特征：${node.path.join(' / ')} / ${feature}`"
            :disabled="readonly"
            @click.stop
            @change="$emit('toggle-feature', { leafKey: node.key, feature })"
          >
          <span class="tgtn-checkbox-custom" />
          <span class="tgtn-feature-text">{{ feature }}</span>
        </label>
        <span v-else v-for="feature in node.feature_selections" :key="`display:${feature}`" class="tgtn-feature">{{ feature }}</span>
      </div>

    </div>

    <div v-if="hasChildren && expanded" class="tgtn-children">
      <TemplateGroupTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :active-key="activeKey"
        :mapped-counts="mappedCounts"
        :configured-leaf-keys="configuredLeafKeys"
        :unconfigured-leaf-keys="unconfiguredLeafKeys"
        :show-metadata="showMetadata"
        :multi-select="multiSelect"
        :selected-feature-keys="selectedFeatureKeys"
        :show-selected-features="showSelectedFeatures"
        :show-feature-details="showFeatureDetails"
        :readonly="readonly"
        :depth="depth + 1"
        @select="$emit('select', $event)"
        @toggle-feature="$emit('toggle-feature', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Aim, ArrowRight, FolderOpened } from '@element-plus/icons-vue'

import type { TemplateGroupNode } from '@/composables/templateGroupMapping'
import { descendantFeatureLeaves, isFeatureLeaf, templateFeatureSelectionKey } from '@/composables/templateStepMapping'

const props = withDefaults(defineProps<{
  node: TemplateGroupNode
  activeKey?: string
  mappedCounts?: Record<string, number>
  configuredLeafKeys?: string[]
  unconfiguredLeafKeys?: string[]
  showMetadata?: boolean
  multiSelect?: boolean
  selectedFeatureKeys?: string[]
  showSelectedFeatures?: boolean
  showFeatureDetails?: boolean
  readonly?: boolean
  depth?: number
}>(), {
  activeKey: '',
  mappedCounts: () => ({}),
  configuredLeafKeys: () => [],
  unconfiguredLeafKeys: () => [],
  showMetadata: true,
  multiSelect: false,
  selectedFeatureKeys: () => [],
  showSelectedFeatures: false,
  showFeatureDetails: false,
  readonly: false,
  depth: 0,
})

defineEmits<{
  (event: 'select', key: string): void
  (event: 'toggle-feature', selection: { leafKey: string; feature: string }): void
}>()

const expanded = ref(props.depth < 2)
const hasChildren = computed(() => props.node.children.length > 0)
const featureLeaf = computed(() => isFeatureLeaf(props.node))
const selectableScope = computed(() => featureLeaf.value || descendantFeatureLeaves(props.node).length > 0)
const mappedCount = computed(() => Number(props.mappedCounts[props.node.key] || 0))
const hasSelectedFeature = computed(() => props.node.feature_selections.some(isSelectedFeature))

function isSelectedFeature(feature: string) {
  return props.selectedFeatureKeys.includes(templateFeatureSelectionKey(props.node.key, feature))
}
</script>

<style scoped>
.tgtn-node {
  position: relative;
}

.tgtn-row {
  --tgtn-depth: 0;
  min-height: 22px;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 2px;
  padding: 1px 4px 1px calc(4px + var(--tgtn-depth) * 10px);
  border-radius: 4px;
  margin: 1px 0;
  transition: background 100ms ease;
  color: #334155;
  border-left: 2px solid transparent;
}

.tgtn-row:hover {
  background: #f8fafc;
}

.tgtn-row-active {
  border-left-color: #6366f1;
  background: #f5f8ff;
  color: #3730a3;
}

.tgtn-row-readonly:hover {
  background: transparent;
}

.tgtn-disclosure {
  width: 16px;
  height: 16px;
  flex: 0 0 16px;
  display: grid;
  place-items: center;
  border: 0;
  border-radius: 3px;
  background: transparent;
  color: #94a3b8;
  cursor: pointer;
}

.tgtn-disclosure:hover {
  background: #e2e8f0;
  color: #475569;
}

.tgtn-disclosure svg {
  width: 10px;
  height: 10px;
  transition: transform 150ms ease;
}

.tgtn-disclosure-open {
  transform: rotate(90deg);
}

.tgtn-disclosure-placeholder {
  width: 16px;
  flex: 0 0 16px;
}

.tgtn-main {
  flex: 0 0 auto;
  max-width: 70%;
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.tgtn-main:disabled {
  cursor: default;
}

.tgtn-kind-icon {
  width: 12px;
  height: 12px;
  flex: 0 0 auto;
  opacity: 0.7;
}

.tgtn-kind-icon.is-folder {
  color: #6366f1;
}

.tgtn-kind-icon.is-aim {
  color: #6366f1;
}

.tgtn-name {
  flex: 0 0 auto;
  font-size: 11px;
  font-weight: 500;
  color: #1e293b;
  white-space: nowrap;
}

.tgtn-row-active .tgtn-name {
  font-weight: 600;
  color: #3730a3;
}

/* Role badges - scope vs feature */
.tgtn-role {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
}

.tgtn-role.is-scope {
  background: transparent;
  color: #94a3b8;
  font-weight: 500;
}

.tgtn-role.is-feature {
  background: #e0e7ff;
  color: #4338ca;
}

.tgtn-status {
  flex: 0 0 auto;
  padding: 0 5px;
  border-radius: 3px;
  font-size: 10px;
  font-weight: 600;
  line-height: 16px;
}

.tgtn-status.is-configured {
  background: #d1fae5;
  color: #065f46;
}

.tgtn-status.is-unconfigured {
  background: #fef3c7;
  color: #92400e;
}

.tgtn-features {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  justify-content: flex-start;
  gap: 3px;
  margin-left: 4px;
}

.tgtn-features.is-detail {
  flex: 1 1 auto;
  width: calc(100% - (12px + var(--tgtn-depth) * 10px));
  max-width: calc(100% - (12px + var(--tgtn-depth) * 10px));
  box-sizing: border-box;
  margin: 1px 0 3px calc(10px + var(--tgtn-depth) * 10px);
  padding: 3px 0 3px 6px;
  border-left: 2px solid #e2e8f0;
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-start;
  gap: 4px;
}

.tgtn-features.is-selected {
  border-left-color: #6366f1;
}

.tgtn-feature {
  max-width: 100%;
  padding: 1px 6px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  color: #475569;
  background: #f8fafc;
  font-size: 10px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* Feature checkbox chips */
.tgtn-feature-select {
  position: relative;
  max-width: 100%;
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 7px 2px 5px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  background: #ffffff;
  color: #475569;
  font-size: 10px;
  font-weight: 500;
  cursor: pointer;
  transition: all 100ms ease;
  user-select: none;
}

.tgtn-feature-text {
  max-width: 150px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.tgtn-feature-select:hover {
  border-color: #a5b4fc;
  background: #f5f3ff;
  color: #4338ca;
}

.tgtn-feature-select.is-checked {
  border-color: #6366f1;
  background: #eef2ff;
  color: #3730a3;
  font-weight: 600;
}

.tgtn-feature-select input[type="checkbox"] {
  position: absolute;
  opacity: 0;
  width: 0;
  height: 0;
  pointer-events: none;
}

.tgtn-checkbox-custom {
  width: 11px;
  height: 11px;
  flex: 0 0 11px;
  border: 1.5px solid #cbd5e1;
  border-radius: 3px;
  background: #fff;
  transition: all 100ms ease;
  display: grid;
  place-items: center;
}

.tgtn-feature-select:hover .tgtn-checkbox-custom {
  border-color: #6366f1;
}

.tgtn-feature-select.is-checked .tgtn-checkbox-custom {
  border-color: #6366f1;
  background: #6366f1;
}

.tgtn-feature-select.is-checked .tgtn-checkbox-custom::after {
  content: '';
  width: 3px;
  height: 6px;
  border: solid #ffffff;
  border-width: 0 1.5px 1.5px 0;
  transform: rotate(45deg) translate(-0.5px, -0.5px);
}

.tgtn-feature-text {
  line-height: 1.3;
}

.tgtn-children {
  position: relative;
}
</style>
