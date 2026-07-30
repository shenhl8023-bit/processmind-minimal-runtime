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

      <button class="tgtn-main" type="button" :disabled="readonly" @click="$emit('select', node.key)">
        <FolderOpened v-if="hasChildren" class="tgtn-kind-icon" />
        <Aim v-else class="tgtn-kind-icon" />
        <span class="tgtn-name">{{ node.name }}</span>
        <span v-if="mappedCount" class="tgtn-count">{{ mappedCount }}</span>
      </button>

      <div v-if="node.feature_selections.length" class="tgtn-features">
        <span v-for="feature in node.feature_selections" :key="feature" class="tgtn-feature">{{ feature }}</span>
      </div>

      <button
        v-if="!readonly && mappedCount"
        class="tgtn-clear"
        type="button"
        title="清空该分组的映射"
        aria-label="清空该分组的映射"
        @click="$emit('clear', node.key)"
      >
        <Delete />
      </button>
    </div>

    <div v-if="hasChildren && expanded" class="tgtn-children">
      <TemplateGroupTreeNode
        v-for="child in node.children"
        :key="child.key"
        :node="child"
        :active-key="activeKey"
        :mapped-counts="mappedCounts"
        :readonly="readonly"
        :depth="depth + 1"
        @select="$emit('select', $event)"
        @clear="$emit('clear', $event)"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, ref } from 'vue'
import { Aim, ArrowRight, Delete, FolderOpened } from '@element-plus/icons-vue'

import type { TemplateGroupNode } from '@/composables/templateGroupMapping'

const props = withDefaults(defineProps<{
  node: TemplateGroupNode
  activeKey?: string
  mappedCounts?: Record<string, number>
  readonly?: boolean
  depth?: number
}>(), {
  activeKey: '',
  mappedCounts: () => ({}),
  readonly: false,
  depth: 0,
})

defineEmits<{
  (event: 'select', key: string): void
  (event: 'clear', key: string): void
}>()

const expanded = ref(props.depth < 2)
const hasChildren = computed(() => props.node.children.length > 0)
const mappedCount = computed(() => Number(props.mappedCounts[props.node.key] || 0))
</script>

<style scoped>
.tgtn-row {
  --tgtn-depth: 0;
  min-height: 38px;
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 4px 8px 4px calc(8px + var(--tgtn-depth) * 16px);
  border-left: 2px solid transparent;
  color: #334155;
}

.tgtn-row:hover { background: #f1f5f9; }
.tgtn-row-active { border-left-color: #2563eb; background: #eff6ff; color: #1d4ed8; }
.tgtn-row-readonly:hover { background: transparent; }

.tgtn-disclosure,
.tgtn-clear {
  width: 28px;
  height: 28px;
  display: grid;
  place-items: center;
  border: 0;
  background: transparent;
  color: #64748b;
  cursor: pointer;
}

.tgtn-disclosure svg,
.tgtn-clear svg { width: 15px; height: 15px; }
.tgtn-disclosure svg { transition: transform 160ms ease; }
.tgtn-disclosure-open { transform: rotate(90deg); }
.tgtn-disclosure-placeholder { width: 28px; flex: 0 0 28px; }

.tgtn-main {
  min-width: 0;
  flex: 1;
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 0;
  border: 0;
  background: transparent;
  color: inherit;
  text-align: left;
  cursor: pointer;
}

.tgtn-main:disabled { cursor: default; }
.tgtn-kind-icon { width: 15px; height: 15px; flex: 0 0 auto; color: #64748b; }
.tgtn-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 13px; font-weight: 600; }
.tgtn-count { min-width: 22px; padding: 1px 6px; border-radius: 10px; background: #dbeafe; color: #1d4ed8; font-size: 11px; text-align: center; }

.tgtn-features { max-width: 42%; display: flex; gap: 4px; overflow: hidden; }
.tgtn-feature { padding: 2px 6px; border: 1px solid #cbd5e1; border-radius: 3px; color: #475569; background: #fff; font-size: 10px; white-space: nowrap; }
.tgtn-clear:hover { color: #b91c1c; background: #fee2e2; }
</style>
