<template>
  <WorkflowNavFooter
    previous-label="← 返回上传资料"
    :next-label="entering ? '正在保存并进入规则分析...' : canEnter ? '进入规则分析 →' : '进入规则分析'"
    :previous-disabled="entering"
    :next-disabled="!canEnter || entering"
    @previous="$emit('previous')"
    @next="$emit('next')"
  >
    <template #summary>
      <div class="footer-status-pill-wrap">
        <span v-if="entering" class="footer-status-pill footer-status-pill-info">
          <span class="footer-status-pill-icon footer-status-pill-spinner"></span>
          正在保存标准化结果路线，保存完成后会自动进入规则分析。
        </span>
        <span v-else-if="pendingCount > 0" class="footer-status-pill footer-status-pill-warning">
          <span class="footer-status-pill-icon">!</span>
          请先完成全部候选归并判断，当前还有 <strong class="highlight-count">{{ pendingCount }}</strong> 组待处理。
        </span>
        <span v-else class="footer-status-pill footer-status-pill-success">
          <span class="footer-status-pill-icon">✓</span>
          候选归并已全部完成！已生成标准化母路线，可进入规则分析阶段。
        </span>
      </div>
    </template>
  </WorkflowNavFooter>
</template>

<script setup lang="ts">
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'

defineProps<{
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
