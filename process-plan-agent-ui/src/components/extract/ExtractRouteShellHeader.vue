<template>
  <div>
    <div class="route-shell-header">
      <div class="route-shell-info">
        <div class="route-shell-title">{{ editUnlocked ? '结果路线微调' : '路线归并' }}</div>
        <span class="route-shell-sep">·</span>
        <div class="route-shell-desc">{{ editUnlocked ? '可对右侧结果路线进行人工调整' : '按归并原则确认标准路线' }}</div>
      </div>
      <div class="route-shell-actions">
        <div class="route-shell-stats">
          <span class="route-shell-stat">原始 <strong>{{ originalCount }}</strong></span>
          <span class="route-shell-stat">结果 <strong>{{ resultCount }}</strong></span>
          <span class="route-shell-stat">待处理 <strong>{{ pendingCount }}</strong></span>
        </div>
        <span class="tag" :class="canEnter ? 'tag-success' : 'tag-warning'">
          {{ canEnter ? '已收敛' : statusLabel }}
        </span>
        <button class="btn btn-text btn-sm route-shell-revert" @click="$emit('rerun')">
          <svg viewBox="0 0 24 24" fill="none" class="icon-sm">
            <path d="M4 4v5h.582m15.356 2A8.001 8.001 0 005.373 6.222M20 20v-5h-.581m-15.357-2a8.001 8.001 0 0013.984 4.778" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"/>
          </svg>
          重新推理
        </button>
      </div>
    </div>

    <div v-if="notice && isWarningNotice" class="route-shell-banner route-shell-banner-warning">
      {{ notice }}
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  editUnlocked: boolean
  originalCount: number
  resultCount: number
  pendingCount: number
  canEnter: boolean
  statusLabel: string
  notice?: string
}>()

defineEmits<{
  rerun: []
}>()

const isWarningNotice = computed(() =>
  Boolean(props.notice?.includes('已更新') || props.notice?.includes('重新提炼'))
)
</script>

<style scoped>
.route-shell-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  padding: 5px 12px;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  background: #ffffff;
  box-shadow: 0 1.5px 5px rgba(15, 23, 42, 0.02);
  margin-bottom: 6px;
}

.route-shell-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.route-shell-sep {
  color: #cbd5e1;
  font-size: 12px;
  flex-shrink: 0;
}

.route-shell-title {
  font-size: 15px;
  font-weight: 700;
  color: #0f172a;
  white-space: nowrap;
  flex-shrink: 0;
}

.route-shell-desc {
  font-size: 13px;
  color: #94a3b8;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.route-shell-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 8px;
}

.route-shell-actions .tag {
  padding: 1.5px 6px;
  font-size: 10.5px;
  border-radius: 999px;
  display: inline-flex;
  align-items: center;
}

.route-shell-revert {
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 2px 5px;
  border-radius: 5px;
  color: #64748b;
  font-size: 11.5px;
  font-weight: 600;
  background: transparent;
  transition: all .2s;
}

.route-shell-revert:hover {
  color: #4f46e5;
  background: #eef2ff;
}

.route-shell-revert .icon-sm {
  width: 12px;
  height: 12px;
}

.route-shell-stats {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
}

.route-shell-stat {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  min-height: 22px;
  padding: 0 8px;
  border-radius: 999px;
  border: 1px solid #e2e8f0;
  background: rgba(255, 255, 255, 0.86);
  font-size: 10.5px;
  color: #64748b;
  white-space: nowrap;
}

.route-shell-stat strong {
  font-size: 11px;
  font-weight: 700;
  color: #0f172a;
}

.route-shell-banner {
  margin: 0 0 12px;
  padding: 12px 16px;
  border-radius: 12px;
  border: 1px solid #dbe4f0;
  background: linear-gradient(180deg, #f8fafc, #f1f5f9);
  color: #334155;
  font-size: 13px;
  line-height: 1.7;
}

.route-shell-banner-warning {
  border-color: #fed7aa;
  background: linear-gradient(180deg, #fff8f1, #fff4e6);
  color: #9a3412;
}

@media (max-width: 900px) {
  .route-shell-header {
    flex-direction: column;
    align-items: stretch;
  }

  .route-shell-actions {
    justify-content: flex-start;
  }

  .route-shell-title {
    font-size: 24px;
  }
}
</style>
