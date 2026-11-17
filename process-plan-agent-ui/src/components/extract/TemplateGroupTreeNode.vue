<template>
  <div class="tgtn-node">
    <div
      class="tgtn-row"
      :class="{ 'tgtn-row-active': activeKey === node.key, 'tgtn-row-readonly': readonly, 'tgtn-row-waived': waivedLeafKeys.includes(node.key) }"
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
        <span v-if="showMappingStatus && featureLeaf && !waivedLeafKeys.includes(node.key) && unconfiguredLeafKeys.includes(node.key)" class="tgtn-status is-unconfigured">待映射</span>
        <span v-if="showMappingStatus && featureLeaf && waivedLeafKeys.includes(node.key)" class="tgtn-status">已豁免</span>
        <span v-else-if="showMappingStatus && featureLeaf && configuredLeafKeys.includes(node.key)" class="tgtn-status is-configured">已映射</span>
      </button>
      <button v-if="featureLeaf && showWaiverActions" class="tgtn-waiver" type="button"
        :data-waiver-leaf-key="node.key" :aria-pressed="waivedLeafKeys.includes(node.key)"
        :aria-label="`${waivedLeafKeys.includes(node.key) ? '取消豁免' : '豁免映射'}：${node.path.join(' / ')}`"
        :disabled="readonly || (configuredLeafKeys.includes(node.key) && !waivedLeafKeys.includes(node.key))"
        @click.stop="$emit('toggle-waiver', node.key)">{{ waivedLeafKeys.includes(node.key) ? '取消豁免' : '豁免映射' }}</button>

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
            :disabled="readonly || waivedLeafKeys.includes(node.key)"
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
        :show-mapping-status="showMappingStatus"
        :readonly="readonly"
        :waived-leaf-keys="waivedLeafKeys" :show-waiver-actions="showWaiverActions"
        @toggle-waiver="$emit('toggle-waiver', $event)"
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
  showMappingStatus?: boolean
  waivedLeafKeys?: string[]
  showWaiverActions?: boolean
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
  showMappingStatus: false,
  waivedLeafKeys: () => [],
  showWaiverActions: false,
  readonly: false,
  depth: 0,
})

defineEmits<{
  (event: 'toggle-waiver', key: string): void
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
/* Keep the existing 10px hierarchy and each action's own disabled contract. */
.tgtn-node, .tgtn-children { position: relative; min-width: 0; }
.tgtn-row {
  --tgtn-depth: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
  min-height: var(--tgtn-row-height, 32px);
  margin: var(--tgtn-row-spacing, 2px) 0;
  padding: var(--tgtn-row-padding, 3px) 6px var(--tgtn-row-padding, 3px) calc(4px + var(--tgtn-depth) * 10px);
  border-left: 2px solid transparent;
  border-radius: 4px;
  color: var(--pm-text-secondary);
  transition: background-color .15s ease;
}
.tgtn-row:hover { background: var(--pm-surface-subtle); }
.tgtn-row-active { border-left-color: var(--pm-primary); background: var(--pm-primary-soft); color: var(--pm-primary); }
.tgtn-row-active:hover { background: var(--pm-primary-soft); }
.tgtn-row-readonly:hover { background: transparent; }
.tgtn-disclosure { flex: 0 0 20px; width: 20px; height: 24px; display: grid; place-items: center; border: 0; border-radius: 4px; background: transparent; color: var(--pm-text-muted); cursor: pointer; }
.tgtn-disclosure:hover { background: var(--pm-disabled-bg); color: var(--pm-text); }
.tgtn-disclosure svg { width: 12px; height: 12px; transition: transform .15s ease; }
.tgtn-disclosure-open { transform: rotate(90deg); }
.tgtn-disclosure-placeholder { width: 20px; flex: 0 0 20px; }
.tgtn-main { flex: 1 1 150px; min-width: 0; max-width: 100%; display: flex; align-items: center; flex-wrap: wrap; gap: 4px 6px; min-height: 24px; padding: 0; border: 0; background: transparent; color: inherit; text-align: left; cursor: pointer; }
.tgtn-main:disabled { cursor: default; }
.tgtn-kind-icon { flex: 0 0 14px; width: 14px; height: 14px; color: var(--pm-primary); }
.tgtn-name { min-width: 0; color: var(--pm-text); font-size: var(--tgtn-name-size, 13px); font-weight: 500; line-height: var(--tgtn-line-height, 20px); overflow-wrap: anywhere; }
.tgtn-row-active .tgtn-name { color: var(--pm-primary); font-weight: 600; }
.tgtn-role, .tgtn-status { flex: 0 0 auto; padding: 0 5px; border-radius: 4px; background: var(--pm-disabled-bg); color: var(--pm-text-secondary); font-size: 12px; font-weight: 500; line-height: var(--tgtn-line-height, 20px); }
.tgtn-role.is-scope { background: transparent; color: var(--pm-text-muted); }
.tgtn-role.is-feature { background: var(--pm-primary-soft); color: var(--pm-primary); }
.tgtn-status.is-configured { background: var(--pm-success-soft); color: var(--pm-success); }
.tgtn-status.is-unconfigured { background: var(--pm-warning-soft); color: var(--pm-warning); }
.tgtn-waiver { flex: 0 0 auto; min-height: var(--tgtn-control-height, 28px); margin-left: auto; padding: var(--tgtn-control-padding, 3px 8px); border: 1px solid var(--pm-border-strong); border-radius: var(--pm-radius-control); background: var(--pm-surface); color: var(--pm-text-secondary); font-size: 12px; line-height: var(--tgtn-line-height, 20px); cursor: pointer; }
.tgtn-waiver:hover:not(:disabled), .tgtn-waiver[aria-pressed=true] { border-color: var(--pm-primary-border); color: var(--pm-primary); background: var(--pm-primary-soft); }
.tgtn-waiver:disabled { opacity: .5; cursor: not-allowed; }
.tgtn-row-waived { background: var(--pm-surface-subtle); }
.tgtn-row-waived .tgtn-main, .tgtn-row-waived .tgtn-name { color: var(--pm-text-muted); }
.tgtn-row-waived .tgtn-features { opacity: .55; }
.tgtn-row-waived .tgtn-feature-select { cursor: not-allowed; }
.tgtn-features { flex: 1 1 100%; min-width: 0; display: flex; align-items: center; flex-wrap: wrap; gap: 4px; margin-left: 24px; }
.tgtn-features.is-detail { max-width: calc(100% - (12px + var(--tgtn-depth) * 10px)); margin: var(--tgtn-feature-spacing, 2px 0 4px) calc(10px + var(--tgtn-depth) * 10px); padding: var(--tgtn-row-padding, 3px) 0 var(--tgtn-row-padding, 3px) 8px; border-left: 2px solid var(--pm-border); }
.tgtn-features.is-selected { border-left-color: var(--pm-primary); }
.tgtn-feature, .tgtn-feature-select { max-width: 100%; display: inline-flex; align-items: center; gap: 5px; min-height: var(--tgtn-control-height, 26px); padding: var(--tgtn-control-padding, 2px 7px); border: 1px solid var(--pm-border); border-radius: 4px; background: var(--pm-surface); color: var(--pm-text-secondary); font-size: 12px; line-height: var(--tgtn-line-height, 20px); }
.tgtn-feature-select { position: relative; cursor: pointer; user-select: none; }
.tgtn-feature-text, .tgtn-feature { overflow-wrap: anywhere; }
.tgtn-feature-select:hover { border-color: var(--pm-primary-border); background: var(--pm-primary-soft); color: var(--pm-primary); }
.tgtn-feature-select.is-checked { border-color: var(--pm-primary); background: var(--pm-primary-soft); color: var(--pm-primary); }
.tgtn-feature-select input[type=checkbox] { position: absolute; opacity: 0; width: 1px; height: 1px; }
.tgtn-checkbox-custom { flex: 0 0 13px; width: 13px; height: 13px; display: grid; place-items: center; border: 1px solid var(--pm-border-strong); border-radius: 3px; background: var(--pm-surface); }
.tgtn-feature-select:hover .tgtn-checkbox-custom { border-color: var(--pm-primary); }
.tgtn-feature-select.is-checked .tgtn-checkbox-custom { border-color: var(--pm-primary); background: var(--pm-primary); }
.tgtn-feature-select.is-checked .tgtn-checkbox-custom::after { content: ''; width: 3px; height: 6px; border: solid #fff; border-width: 0 1.5px 1.5px 0; transform: rotate(45deg) translate(-.5px, -.5px); }
.tgtn-disclosure:focus-visible, .tgtn-main:focus-visible, .tgtn-waiver:focus-visible, .tgtn-feature-select input:focus-visible + .tgtn-checkbox-custom { outline: 2px solid var(--pm-primary); outline-offset: 2px; }
.tgtn-feature-select input:disabled ~ .tgtn-feature-text { color: var(--pm-text-muted); }
@media (prefers-reduced-motion: reduce) { .tgtn-row, .tgtn-disclosure svg { transition: none; } }
</style>
