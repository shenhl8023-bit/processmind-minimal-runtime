<template>
  <ExtractActionFooter blocked>
    <template #summary>
      <div class="footer-status-pill-wrap">
        <span v-if="pendingCount > 0" class="footer-status-pill footer-status-pill-warning">
          <span class="footer-status-pill-icon">!</span>
          请先完成全部候选归并判断，当前还有 <strong class="highlight-count">{{ pendingCount }}</strong> 组待处理。
        </span>
        <span v-else class="footer-status-pill footer-status-pill-success">
          <span class="footer-status-pill-icon">✓</span>
          候选归并已全部完成！已生成标准化母路线，可进入规则分析阶段。
        </span>
      </div>
    </template>
    <template #actions>
      <button
        class="btn next-btn"
        :class="canEnter ? 'btn-primary' : 'btn-disabled-locked'"
        :disabled="!canEnter"
        @click="$emit('next')"
      >
        <svg v-if="!canEnter" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round" class="btn-lock-icon">
          <rect x="3" y="11" width="18" height="11" rx="2" ry="2"/>
          <path d="M7 11V7a5 5 0 0 1 10 0v4"/>
        </svg>
        {{ canEnter ? '进入规则分析 →' : '进入规则分析' }}
      </button>
    </template>
  </ExtractActionFooter>
</template>

<script setup lang="ts">
import ExtractActionFooter from '@/components/extract/ExtractActionFooter.vue'

defineProps<{
  pendingCount: number
  canEnter: boolean
}>()

defineEmits<{
  next: []
}>()
</script>

<style scoped>
.btn-disabled-locked {
  background: #e2e8f0;
  color: #64748b;
  border: 1px solid #cbd5e1;
  cursor: not-allowed;
  box-shadow: none;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
}

.btn-disabled-locked:hover {
  background: #e2e8f0;
  color: #64748b;
  border-color: #cbd5e1;
  transform: none;
}

.btn-disabled-locked:disabled {
  opacity: 1;
}

.btn-lock-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}

.next-btn {
  min-width: 160px;
  height: 36px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 12.5px;
  padding: 0 16px;
  box-sizing: border-box;
}

.footer-status-pill-wrap {
  display: flex;
  align-items: center;
}

.footer-status-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 6px 14px;
  border-radius: 999px;
  font-size: 13px;
  font-weight: 600;
  line-height: 1;
  transition: all 0.2s ease;
}

.footer-status-pill-warning {
  background: #fff7ed;
  color: #c2410c;
  border: 1px solid #ffedd5;
  box-shadow: 0 2px 8px rgba(234, 88, 12, 0.05);
}

.footer-status-pill-success {
  background: #f0fdf4;
  color: #15803d;
  border: 1px solid #dcfce7;
  box-shadow: 0 2px 8px rgba(22, 163, 74, 0.05);
}

.footer-status-pill-icon {
  font-size: 14px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.highlight-count {
  font-size: 14px;
  font-weight: 700;
  margin: 0 2px;
  color: #ea580c;
}
</style>
