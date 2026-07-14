<template>
  <div class="nrp-root">
    <div class="route-pane-head">
      <div class="route-pane-title">标准化结果路线</div>
      <div class="route-pane-subtitle">已归并 · 最终顺序</div>
    </div>
    <div class="nrp-scroll" v-if="items.length">
      <div
        v-for="(item, idx) in items"
        :key="item.id"
        class="nrp-item-wrap"
      >
        <!-- Track: dot + line -->
        <div class="nrp-track">
          <div class="nrp-dot" :class="{ 'nrp-dot--active': isActive(item) }"></div>
          <div v-if="idx < items.length - 1" class="nrp-line"></div>
        </div>

        <!-- Card -->
        <button
          class="nrp-card"
          :class="{
            'nrp-card--active': isActive(item),
            'nrp-card--dragging': editable && draggingItemId === item.id,
            'nrp-card--drop-target': editable && dropTargetItemId === item.id && draggingItemId !== item.id,
          }"
          :data-merge-group-id="item.groupId"
          type="button"
          :draggable="editable"
          @click="$emit('select', item.id)"
          @dragstart="onDragStart(item.id)"
          @dragenter.prevent="onDragEnter(item.id)"
          @dragover.prevent="onDragOver(item.id)"
          @drop.prevent="onDrop(item.id)"
          @dragend="onDragEnd"
        >
          <!-- Row 1: seq badge + name -->
          <div class="nrp-row1">
            <span class="nrp-seq">{{ item.sequence }}</span>
            <div class="nrp-name-block">
              <span class="nrp-name">{{ routeItemDisplayName(item) }}</span>
              <div v-if="isActive(item) && routeItemMetaLabel(item)" class="nrp-meta">
                {{ routeItemMetaLabel(item) }}
              </div>
            </div>
          </div>

          <!-- Steps: collapsible -->
          <div v-if="selectedItemId === item.id && previewStepGroups(item).length" class="nrp-steps-area" @click.stop>
            <button class="nrp-steps-toggle" type="button" @click.stop="toggleSteps(item.id)">
              <svg
                class="nrp-steps-chevron"
                :class="{ 'nrp-steps-chevron--open': expandedStepIds.has(item.id) }"
                viewBox="0 0 16 16" width="9" height="9" fill="none"
              >
                <path d="M6 4l4 4-4 4" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"/>
              </svg>
              <span>来源工序与工步</span>
              <span class="nrp-steps-count">{{ stepTotalCount(item) }}</span>
            </button>
            <Transition name="nrp-expand">
              <div v-if="expandedStepIds.has(item.id)" class="nrp-steps-content">
                <div
                  v-for="group in previewStepGroups(item)"
                  :key="group.key"
                  class="nrp-step-group"
                >
                  <div class="nrp-step-group-name">{{ group.name }}</div>
                  <div class="nrp-step-chips">
                    <span v-for="step in group.stepItems" :key="`${group.key}-step-${step}`" class="nrp-chip">{{ step }}</span>
                    <span v-for="step in group.attachedStepItems" :key="`${group.key}-attached-${step}`" class="nrp-chip nrp-chip--attached">{{ step }}</span>
                  </div>
                </div>
              </div>
            </Transition>
          </div>

          <!-- Actions -->
          <div v-if="editable && selectedItemId === item.id" class="nrp-actions" @click.stop>
            <div class="nrp-action-row">
              <div class="nrp-icon-group">
                <button class="nrp-icon-btn" :disabled="!canMoveUp" type="button" @click.stop="$emit('move-up', item.id)" title="上移">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/></svg>
                </button>
                <button class="nrp-icon-btn" :disabled="!canMoveDown" type="button" @click.stop="$emit('move-down', item.id)" title="下移">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M19 12l-7 7-7-7"/></svg>
                </button>
                <button class="nrp-icon-btn" :disabled="!canMergePrev" type="button" @click.stop="$emit('merge-prev', item.id)" title="并到上一工序">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 19V5M5 12l7-7 7 7"/><path d="M5 5h14"/></svg>
                </button>
                <button class="nrp-icon-btn" :disabled="!canMergeNext" type="button" @click.stop="$emit('merge-next', item.id)" title="并到下一工序">
                  <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M12 5v14M19 12l-7 7-7-7"/><path d="M5 19h14"/></svg>
                </button>
              </div>
              <button class="nrp-text-btn" :disabled="!canInsert" type="button" @click.stop="$emit('insert-after', item.id)">增加</button>
              <button class="nrp-text-btn" :disabled="!canSplit" type="button" @click.stop="$emit('split', item.id)">拆开</button>
              <button class="nrp-text-btn nrp-text-btn--danger" :disabled="!canRemove" type="button" @click.stop="$emit('remove', item.id)">移除</button>
              <button v-if="!renameEditing" class="nrp-text-btn" type="button" @click.stop="$emit('start-rename', item.id)">改名</button>
            </div>
            <div v-if="renameEditing" class="nrp-rename-row">
              <input
                :value="renameDraft"
                class="nrp-rename-input"
                type="text"
                @click.stop
                @input="$emit('update:renameDraft', ($event.target as HTMLInputElement).value)"
                @keydown.enter.prevent.stop="$emit('submit-rename', item.id)"
                @keydown.esc.prevent.stop="$emit('cancel-rename')"
              />
              <button class="nrp-text-btn nrp-text-btn--primary" :disabled="!renameDraft" type="button" @click.stop="$emit('submit-rename', item.id)">保存</button>
              <button class="nrp-text-btn" type="button" @click.stop="$emit('cancel-rename')">取消</button>
            </div>
          </div>
        </button>
      </div>
    </div>
    <div v-else class="nrp-empty">当前还没有可展示的标准化母路线。</div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import type { PropType } from 'vue'
import type { RouteMergePreviewItem } from '@/composables/useRouteMergeResultWorkspace'

type RouteMergePreviewStepGroup = {
  key: string
  name: string
  stepItems: string[]
  attachedStepItems: string[]
}

const props = defineProps({
  items: {
    type: Array as PropType<RouteMergePreviewItem[]>,
    default: () => [],
  },
  isActive: {
    type: Function as PropType<(item: RouteMergePreviewItem) => boolean>,
    required: true,
  },
  stepGroupsForItem: {
    type: Function as PropType<(item: RouteMergePreviewItem) => RouteMergePreviewStepGroup[]>,
    required: true,
  },
  editable: {
    type: Boolean,
    default: false,
  },
  selectedItemId: {
    type: String,
    default: '',
  },
  canMoveUp: {
    type: Boolean,
    default: false,
  },
  canMoveDown: {
    type: Boolean,
    default: false,
  },
  canMergePrev: {
    type: Boolean,
    default: false,
  },
  canMergeNext: {
    type: Boolean,
    default: false,
  },
  canSplit: {
    type: Boolean,
    default: false,
  },
  canInsert: {
    type: Boolean,
    default: false,
  },
  canRemove: {
    type: Boolean,
    default: false,
  },
  renameEditing: {
    type: Boolean,
    default: false,
  },
  renameDraft: {
    type: String,
    default: '',
  },
})

const emit = defineEmits<{
  (e: 'select', itemId: string): void
  (e: 'reorder', payload: { draggedId: string, targetId: string }): void
  (e: 'move-up', itemId: string): void
  (e: 'move-down', itemId: string): void
  (e: 'merge-prev', itemId: string): void
  (e: 'merge-next', itemId: string): void
  (e: 'insert-after', itemId: string): void
  (e: 'remove', itemId: string): void
  (e: 'split', itemId: string): void
  (e: 'start-rename', itemId: string): void
  (e: 'submit-rename', itemId: string): void
  (e: 'cancel-rename'): void
  (e: 'update:renameDraft', value: string): void
}>()

const draggingItemId = ref('')
const dropTargetItemId = ref('')
const expandedStepIds = ref<Set<string>>(new Set())

function toggleSteps(itemId: string) {
  const next = new Set(expandedStepIds.value)
  if (next.has(itemId)) next.delete(itemId)
  else next.add(itemId)
  expandedStepIds.value = next
}

function stepTotalCount(item: RouteMergePreviewItem) {
  return previewStepGroups(item).reduce(
    (sum, g) => sum + g.stepItems.length + g.attachedStepItems.length,
    0,
  )
}

function onDragStart(itemId: string) {
  if (!props.editable) return
  draggingItemId.value = itemId
  dropTargetItemId.value = ''
}

function onDragEnter(itemId: string) {
  if (!props.editable || !draggingItemId.value || draggingItemId.value === itemId) return
  dropTargetItemId.value = itemId
}

function onDragOver(itemId: string) {
  if (!props.editable || !draggingItemId.value || draggingItemId.value === itemId) return
  dropTargetItemId.value = itemId
}

function onDrop(itemId: string) {
  if (!props.editable || !draggingItemId.value || draggingItemId.value === itemId) {
    onDragEnd()
    return
  }
  emit('reorder', { draggedId: draggingItemId.value, targetId: itemId })
  onDragEnd()
}

function onDragEnd() {
  draggingItemId.value = ''
  dropTargetItemId.value = ''
}

function routeItemDisplayName(item: RouteMergePreviewItem) {
  return item.name || item.sourceLabel
}

function routeItemMetaLabel(_item: RouteMergePreviewItem) {
  return ''
}

function previewStepGroups(item: RouteMergePreviewItem) {
  return props.stepGroupsForItem(item)
}
</script>

<style scoped>
.nrp-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ── Head ── */
.route-pane-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 12px; padding: 18px 20px 14px;
  border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(135deg, #fafbff 0%, #f8fafc 100%);
}
.route-pane-title { font-size: 15px; font-weight: 700; color: #0f172a; letter-spacing: -0.015em; }
.route-pane-subtitle { font-size: 13px; color: #94a3b8; font-weight: 500; white-space: nowrap; }
.nrp-empty { padding: 40px; text-align: center; color: #94a3b8; font-size: 14px; }

/* ── Scroll container ── */
.nrp-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 14px 16px 24px;
  display: flex;
  flex-direction: column;
}

/* ── Item wrap: track + card ── */
.nrp-item-wrap {
  display: flex;
  align-items: stretch;
  gap: 10px;
}

/* ── Track ── */
.nrp-track {
  display: flex;
  flex-direction: column;
  align-items: center;
  flex-shrink: 0;
  width: 16px;
  padding-top: 13px;
}
.nrp-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #d1d5db;
  border: 2px solid #ffffff;
  box-shadow: 0 0 0 1px #d1d5db;
  flex-shrink: 0;
  transition: all 0.15s ease;
  z-index: 1;
}
.nrp-dot--active {
  background: #6366f1;
  box-shadow: 0 0 0 1px #6366f1, 0 0 0 3px rgba(99, 102, 241, 0.2);
}
.nrp-line {
  flex: 1;
  width: 2px;
  min-height: 8px;
  background: linear-gradient(to bottom, #e2e8f0 0%, #f1f5f9 100%);
  margin: 3px 0 0;
}

/* ── Card ── */
.nrp-card {
  flex: 1;
  min-width: 0;
  text-align: left;
  border: 1px solid transparent;
  border-radius: 8px;
  padding: 9px 12px;
  margin-bottom: 4px;
  background: #ffffff;
  cursor: pointer;
  position: relative;
  transition: background 0.15s ease, border-color 0.15s ease, box-shadow 0.15s ease;
}
.nrp-card::before {
  content: '';
  position: absolute;
  left: -1px; top: -1px; bottom: -1px;
  width: 3px;
  background: transparent;
  border-radius: 8px 0 0 8px;
  transition: background 0.2s;
}
.nrp-card:hover {
  background: #f8fafc;
  border-color: #e2e8f0;
  box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
}
.nrp-card--active {
  background: #fafcff;
  border-color: #e2e8f0;
  box-shadow: 0 4px 14px rgba(15, 23, 42, 0.05);
}
.nrp-card--active::before { background: #4f46e5; }
.nrp-card--dragging { opacity: 0.4; transform: scale(0.98); }
.nrp-card[draggable="true"] { cursor: grab; }
.nrp-card[draggable="true"]:active { cursor: grabbing; }
.nrp-card--drop-target {
  border-color: #fb923c;
  background: #fff7ed;
  box-shadow: 0 0 0 2px #fdba74;
}

/* Drag handle dots */
.nrp-card[draggable="true"]::after {
  content: '';
  position: absolute;
  right: 10px; top: 50%;
  transform: translateY(-50%);
  width: 10px; height: 16px;
  background-image: radial-gradient(#cbd5e1 1.5px, transparent 1.5px);
  background-size: 5px 5px;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
}
.nrp-card[draggable="true"]:hover::after { opacity: 0.6; }

/* ── Row 1: seq + name ── */
.nrp-row1 {
  display: flex;
  align-items: center;
  gap: 8px;
  min-height: 26px;
}
.nrp-seq {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  min-width: 26px;
  height: 20px;
  border-radius: 5px;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
  font-weight: 700;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  transition: background 0.15s, color 0.15s;
}
.nrp-card--active .nrp-seq {
  background: #6366f1;
  color: #fff;
}
.nrp-name-block {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
}
.nrp-name {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
  line-height: 1.4;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.nrp-meta {
  font-size: 11px;
  color: #94a3b8;
  font-weight: 500;
  line-height: 1.3;
}

/* ── Steps area ── */
.nrp-steps-area {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
}
.nrp-steps-toggle {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  font-size: 11.5px;
  font-weight: 600;
  color: #64748b;
  background: transparent;
  border: none;
  padding: 0;
  cursor: pointer;
  transition: color 0.15s;
}
.nrp-steps-toggle:hover { color: #6366f1; }
.nrp-steps-chevron {
  color: currentColor;
  transition: transform 0.2s ease;
  flex-shrink: 0;
}
.nrp-steps-chevron--open { transform: rotate(90deg); }
.nrp-steps-count {
  background: #e2e8f0;
  color: #64748b;
  border-radius: 999px;
  padding: 1px 6px;
  font-size: 10px;
  font-weight: 700;
  transition: background 0.15s, color 0.15s;
}
.nrp-steps-toggle:hover .nrp-steps-count {
  background: rgba(99, 102, 241, 0.12);
  color: #6366f1;
}
.nrp-steps-content {
  margin-top: 8px;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.nrp-step-group {
  display: flex;
  flex-direction: column;
  gap: 5px;
  padding: 0 0 0 10px;
  border-left: 2px solid #e2e8f0;
}
.nrp-step-group-name {
  font-size: 11.5px;
  font-weight: 700;
  color: #475569;
}
.nrp-step-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
}
.nrp-chip {
  display: inline-flex;
  align-items: center;
  padding: 2px 6px;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  background: #f1f5f9;
  color: #475569;
  font-size: 11px;
  line-height: 1.4;
}
.nrp-chip--attached {
  border-color: #e0e7ff;
  background: #f5f7ff;
  color: #4f46e5;
}

/* Expand transition */
.nrp-expand-enter-active,
.nrp-expand-leave-active {
  transition: opacity 0.2s ease, max-height 0.25s ease;
  overflow: hidden;
  max-height: 600px;
}
.nrp-expand-enter-from,
.nrp-expand-leave-to { opacity: 0; max-height: 0; }

/* ── Actions ── */
.nrp-actions {
  margin-top: 8px;
  padding-top: 8px;
  border-top: 1px solid #f1f5f9;
  display: flex;
  flex-direction: column;
  gap: 6px;
}
.nrp-action-row {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 4px;
}
.nrp-icon-group {
  display: flex;
  background: #f1f5f9;
  border-radius: 6px;
  padding: 2px;
  gap: 1px;
  margin-right: 4px;
}
.nrp-icon-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  background: transparent;
  border-radius: 4px;
  color: #64748b;
  cursor: pointer;
  transition: background 0.12s, color 0.12s;
}
.nrp-icon-btn:hover:not(:disabled) { background: #ffffff; color: #334155; }
.nrp-icon-btn:disabled { opacity: 0.3; cursor: not-allowed; }
.nrp-text-btn {
  border: 1px solid transparent;
  background: transparent;
  color: #64748b;
  font-size: 11.5px;
  font-weight: 600;
  padding: 4px 9px;
  border-radius: 6px;
  cursor: pointer;
  transition: all 0.12s ease;
  display: inline-flex;
  align-items: center;
}
.nrp-text-btn:hover:not(:disabled) { color: #334155; background: #f1f5f9; border-color: #e2e8f0; }
.nrp-text-btn:disabled { opacity: 0.35; cursor: not-allowed; }
.nrp-text-btn--danger { color: #dc2626; }
.nrp-text-btn--danger:hover:not(:disabled) { color: #dc2626; background: #fef2f2; border-color: #fecaca; }
.nrp-text-btn--primary {
  color: #fff;
  background: #4f46e5;
  border-color: transparent;
  box-shadow: 0 1px 4px rgba(79, 70, 229, 0.3);
}
.nrp-text-btn--primary:hover:not(:disabled) { background: #4338ca; box-shadow: 0 2px 8px rgba(79, 70, 229, 0.4); }
.nrp-text-btn--primary:disabled { opacity: 0.5; }

/* ── Rename row ── */
.nrp-rename-row {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
}
.nrp-rename-input {
  flex: 1;
  min-width: 120px;
  border: 1.5px solid #a5b4fc;
  border-radius: 6px;
  padding: 5px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  background: #fafbff;
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
  transition: all 0.2s;
}
.nrp-rename-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
</style>
