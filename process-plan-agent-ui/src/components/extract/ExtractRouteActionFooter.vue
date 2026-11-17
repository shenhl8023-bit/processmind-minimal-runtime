<template>
  <WorkflowNavFooter
    :notices="notices"
    :summary="entering ? '正在保存标准化路线…' : pendingCount ? `还有 ${pendingCount} 组归并待处理` : '候选归并已完成，可进入规则分析'"
    previous-label="← 返回上传资料"
    :next-label="entering ? '正在保存并进入规则分析...' : canEnter ? '进入规则分析 →' : '进入规则分析'"
    :previous-disabled="entering"
    :next-disabled="!canEnter || entering"
    @previous="$emit('previous')"
    @next="$emit('next')"
  >
  </WorkflowNavFooter>
</template>

<script setup lang="ts">
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'

defineProps<{
  notices?: WorkflowNotice[]
  pendingCount: number
  canEnter: boolean
  entering?: boolean
}>()

defineEmits<{
  previous: []
  next: []
}>()
</script>

<style scoped>
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

.footer-status-pill-info {
  background: #eef2ff;
  color: #4338ca;
  border: 1px solid #c7d2fe;
  box-shadow: 0 2px 8px rgba(79, 70, 229, 0.06);
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

.footer-status-pill-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(67, 56, 202, 0.22);
  border-top-color: #4f46e5;
  border-radius: 999px;
  animation: footer-status-spin 0.7s linear infinite;
}

@keyframes footer-status-spin {
  to { transform: rotate(360deg); }
}

.highlight-count {
  font-size: 14px;
  font-weight: 700;
  margin: 0 2px;
  color: #ea580c;
}
</style>
