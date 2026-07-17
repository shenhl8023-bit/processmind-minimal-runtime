<template>
  <div class="mqp-root">
    <div class="route-pane-head">
      <div class="route-pane-title">候选归并组</div>
      <div class="route-pane-subtitle">只展示需要确认的归并建议</div>
    </div>

    <template v-if="candidateCount">
      <div class="route-pane-toolbar">
        <div class="merge-inline-summary">
          <span class="merge-inline-stat">待处理 <strong>{{ pendingCount }}</strong></span>
          <span class="merge-inline-divider">·</span>
          <span class="merge-inline-stat">已判定 <strong>{{ resolvedCount }}</strong></span>
          <span class="merge-inline-divider">·</span>
          <span class="merge-inline-stat">结果节点 <strong>{{ previewCount }}</strong></span>
        </div>
        <div v-if="groups.length" class="merge-batch-actions">
          <button class="btn btn-outline btn-xs" :disabled="busy" @click="$emit('bulk-confirm')">全部合并</button>
          <button class="btn btn-outline btn-xs" :disabled="busy" @click="$emit('bulk-reject')">全部不合并</button>
        </div>
      </div>
      <div v-if="groups.length" class="merge-queue-list">
        <div v-if="pendingCount > 0" class="merge-queue-guide">逐个确认下方归并建议，处理完成后再进入后续规则分析。</div>
        <div
          v-for="group in groups"
          :key="group.id"
          class="merge-queue-card"
          :class="{ active: selectedGroupId === group.id }"
          :data-merge-group-id="group.id"
        >
          <div class="merge-queue-head" @click="$emit('select', group.id)">
            <div class="merge-queue-main">
              <div class="merge-queue-name">{{ candidateLabel(group) }}</div>
              <div v-if="sourceLabel(group) && sourceLabel(group) !== candidateLabel(group)" class="merge-queue-members">
                来源工序：{{ sourceLabel(group) }}
              </div>
              <div class="merge-queue-hint">{{ suggestionLabel(group) }}</div>
              <div v-if="group.equipment_split_applied" class="merge-queue-hint">
                来自主段 {{ group.parent_segment || '原主段' }} · {{ equipmentLabel(group.equipment_support_result) }}
              </div>
            </div>
            <div class="merge-queue-meta">
              <span class="tag" :class="tagClass(group.status)">{{ statusLabel(group.status) }}</span>
            </div>
          </div>
          <div v-if="selectedGroupId === group.id" class="merge-queue-actions-inline">
            <button class="btn btn-primary btn-xs" :disabled="busy" @click="$emit('confirm', group.id)">确认合并</button>
            <button class="btn btn-outline btn-xs" :disabled="busy" @click="$emit('reject', group.id)">不合并</button>
            <button
              v-if="renameEditingGroupId !== group.id"
              class="btn btn-outline btn-xs"
              :disabled="busy"
              @click="$emit('start-rename', group.id)"
            >
              改名
            </button>
          </div>
          <div v-if="renameEditingGroupId === group.id" class="merge-queue-rename" @click.stop>
            <input
              :value="renameDraft"
              class="merge-queue-rename-input"
              type="text"
              @input="$emit('update:rename-draft', ($event.target as HTMLInputElement).value)"
              @keydown.enter.prevent.stop="$emit('submit-rename', group.id)"
              @keydown.esc.prevent.stop="$emit('cancel-rename')"
            />
            <button class="btn btn-primary btn-xs" :disabled="busy || !renameDraft" @click="$emit('submit-rename', group.id)">保存改名</button>
            <button class="btn btn-outline btn-xs" :disabled="busy" @click="$emit('cancel-rename')">取消</button>
          </div>
        </div>
      </div>
      <div v-else class="empty-hint">当前没有待处理的候选归并组，可以直接查看右侧标准化母路线。</div>
    </template>
    <div v-else class="empty-hint">当前没有待处理的候选归并组，可以直接查看右侧标准化母路线。</div>
  </div>
</template>

<script setup lang="ts">
import type { PropType } from 'vue'
import type { MergeGroupStatus, RouteMergeGroup } from '@/composables/useRouteMergeResultWorkspace'

defineProps({
  groups: {
    type: Array as PropType<RouteMergeGroup[]>,
    default: () => [],
  },
  selectedGroupId: {
    type: String,
    default: '',
  },
  pendingCount: {
    type: Number,
    default: 0,
  },
  busy: {
    type: Boolean,
    default: false,
  },
  resolvedCount: {
    type: Number,
    default: 0,
  },
  previewCount: {
    type: Number,
    default: 0,
  },
  candidateCount: {
    type: Number,
    default: 0,
  },
  candidateLabel: {
    type: Function as PropType<(group: RouteMergeGroup) => string>,
    required: true,
  },
  sourceLabel: {
    type: Function as PropType<(group: RouteMergeGroup) => string>,
    required: true,
  },
  suggestionLabel: {
    type: Function as PropType<(group: RouteMergeGroup) => string>,
    required: true,
  },
  equipmentLabel: {
    type: Function as PropType<(value?: string) => string>,
    required: true,
  },
  tagClass: {
    type: Function as PropType<(status: MergeGroupStatus) => string>,
    required: true,
  },
  statusLabel: {
    type: Function as PropType<(status: MergeGroupStatus) => string>,
    required: true,
  },
  renameEditingGroupId: {
    type: String,
    default: '',
  },
  renameDraft: {
    type: String,
    default: '',
  },
})

defineEmits<{
  (e: 'select', groupId: string): void
  (e: 'confirm', groupId: string): void
  (e: 'reject', groupId: string): void
  (e: 'bulk-confirm'): void
  (e: 'bulk-reject'): void
  (e: 'start-rename', groupId: string): void
  (e: 'submit-rename', groupId: string): void
  (e: 'cancel-rename'): void
  (e: 'update:rename-draft', value: string): void
}>()
</script>

<style scoped>
.mqp-root {
  display: flex;
  flex-direction: column;
  height: 100%;
  overflow: hidden;
}

/* ─── Header ─────────────────────────────────────────── */
.route-pane-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 18px 20px 14px;
  border-bottom: 1px solid #f1f5f9;
  background: linear-gradient(135deg, #fafbff 0%, #f8fafc 100%);
}
.route-pane-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.015em;
  line-height: 1.2;
}
.route-pane-subtitle {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
  font-weight: 500;
  line-height: 1.2;
}

/* ─── Toolbar ─────────────────────────────────────────── */
.route-pane-toolbar {
  padding: 10px 20px 8px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 8px;
  flex-wrap: wrap;
}
.merge-inline-summary {
  display: flex;
  align-items: center;
  gap: 0;
  color: #64748b;
  font-size: 12px;
}
.merge-inline-stat {
  display: flex;
  align-items: baseline;
  gap: 3px;
  padding: 3px 8px;
  border-radius: 6px;
  transition: background 0.15s;
}
.merge-inline-stat strong {
  font-size: 13px;
  font-weight: 700;
  color: #1e293b;
}
.merge-inline-divider {
  color: #e2e8f0;
  padding: 0 2px;
  font-size: 14px;
}

/* Batch action buttons */
.merge-batch-actions { display: flex; gap: 6px; }
.merge-batch-actions .btn {
  border: 1px solid #c7d2fe;
  background: transparent;
  color: #4f46e5;
  font-size: 11.5px;
  font-weight: 600;
  padding: 3px 10px;
  border-radius: 6px;
  transition: all 0.15s;
}
.merge-batch-actions .btn:hover:not(:disabled) {
  color: #4338ca;
  background: #eef2ff;
  border-color: #818cf8;
}
.merge-batch-actions .btn:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}

/* ─── List ────────────────────────────────────────────── */
.merge-queue-list {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 7px;
  overflow-y: auto;
  padding: 10px 14px 20px;
}

/* Guide banner */
.merge-queue-guide {
  font-size: 12px;
  color: #6366f1;
  background: linear-gradient(135deg, #eef2ff 0%, #f0f4ff 100%);
  border: 1px solid #c7d2fe;
  border-left: 3px solid #6366f1;
  border-radius: 8px;
  padding: 9px 13px;
  line-height: 1.55;
  flex-shrink: 0;
  font-weight: 500;
}

/* ─── Cards ───────────────────────────────────────────── */
.merge-queue-card {
  position: relative;
  border: 1px solid #f1f5f9;
  border-radius: 10px;
  background: #fff;
  padding: 11px 13px 11px 16px;
  box-shadow: 0 1px 4px rgba(15, 23, 42, 0.04);
  transition: border-color 0.18s, box-shadow 0.18s, background 0.18s;
  overflow: visible;
  flex-shrink: 0;
}
/* Left accent bar (always present, invisible by default) */
.merge-queue-card::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: transparent;
  border-radius: 10px 0 0 10px;
  transition: background 0.18s;
}
.merge-queue-card:hover {
  border-color: #e2e8f0;
  box-shadow: 0 3px 10px rgba(15, 23, 42, 0.07);
}
.merge-queue-card:hover::before {
  background: #c7d2fe;
}
.merge-queue-card.active {
  z-index: 2;
  border-color: #a5b4fc;
  background: linear-gradient(135deg, #fafbff 0%, #f5f7ff 100%);
  box-shadow: 0 0 0 1px #a5b4fc, 0 4px 16px rgba(99, 102, 241, 0.08);
}
.merge-queue-card.active::before {
  background: linear-gradient(180deg, #6366f1 0%, #818cf8 100%);
}

/* Card head row */
.merge-queue-head {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 10px;
  cursor: pointer;
  user-select: none;
}
.merge-queue-main { min-width: 0; flex: 1; }

/* Operation name */
.merge-queue-name {
  font-size: 14px;
  line-height: 1.45;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.01em;
}
.merge-queue-card.active .merge-queue-name {
  color: #3730a3;
}

/* Original operations */
.merge-queue-members {
  margin-top: 5px;
  font-size: 11.5px;
  line-height: 1.5;
  color: #64748b;
  font-weight: 500;
}

/* Suggestion hint text – clamped */
.merge-queue-hint {
  margin-top: 4px;
  font-size: 11.5px;
  line-height: 1.55;
  color: #94a3b8;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.merge-queue-card.active .merge-queue-hint {
  -webkit-line-clamp: unset;
  overflow: visible;
  color: #6366f1;
}

/* Meta area (tag) */
.merge-queue-meta {
  flex-shrink: 0;
  display: flex;
  align-items: flex-start;
  padding-top: 1px;
}

/* ─── Action buttons ──────────────────────────────────── */
.merge-queue-actions-inline {
  display: flex;
  gap: 6px;
  margin-top: 11px;
  padding-top: 11px;
  border-top: 1px solid #f1f5f9;
  align-items: center;
}
.merge-queue-actions-inline > .btn {
  font-size: 12px;
  padding: 5px 14px;
  font-weight: 600;
  border-radius: 7px;
  transition: all 0.15s;
  line-height: 1.4;
}
.merge-queue-actions-inline > .btn.btn-primary {
  background: linear-gradient(135deg, #6366f1 0%, #4f46e5 100%);
  color: #fff;
  border: none;
  box-shadow: 0 2px 6px rgba(99, 102, 241, 0.3);
}
.merge-queue-actions-inline > .btn.btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #4f46e5 0%, #4338ca 100%);
  box-shadow: 0 3px 10px rgba(99, 102, 241, 0.4);
  transform: translateY(-1px);
}
.merge-queue-actions-inline > .btn.btn-outline {
  border: none;
  background: #f1f5f9;
  color: #475569;
}
.merge-queue-actions-inline > .btn.btn-outline:hover:not(:disabled) {
  background: #e2e8f0;
  color: #1e293b;
}
.merge-queue-actions-inline > .btn:disabled {
  opacity: 0.45;
  cursor: not-allowed;
  transform: none !important;
}

/* ─── Rename ──────────────────────────────────────────── */
.merge-queue-rename {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 10px;
  padding-top: 10px;
  padding-bottom: 2px;
  border-top: 1px solid #f1f5f9;
  flex-wrap: wrap;
}
.merge-queue-rename-input {
  flex: 1;
  min-width: 180px;
  border: 1.5px solid #a5b4fc;
  border-radius: 7px;
  padding: 5px 10px;
  font-size: 13px;
  font-weight: 600;
  color: #0f172a;
  background: #fafbff;
  outline: none;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.08);
  transition: border-color 0.15s, box-shadow 0.15s;
}
.merge-queue-rename-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.15);
}
.merge-queue-rename .btn {
  font-size: 12px;
  padding: 5px 11px;
  border-radius: 7px;
  font-weight: 600;
}

/* ─── Empty ───────────────────────────────────────────── */
.empty-hint {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  color: #94a3b8;
  font-size: 13.5px;
  text-align: center;
  line-height: 1.6;
}

/* ─── Tags (override) ─────────────────────────────────── */
.tag {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 2px 9px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.01em;
}
/* 待归并 → indigo 风格，与整体一致 */
:deep(.tag-warning) { background: #ede9fe; color: #5b21b6; }
:deep(.tag-neutral) { background: #f1f5f9; color: #475569; }
:deep(.tag-success) { background: #dcfce7; color: #15803d; }
</style>
