<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'

interface SegmentContext { id?: string | number | null; normalized_step_name?: string | null; phase?: string | null; source_operation_names?: string[] | null }
const props = defineProps<{
  projectId?: number | string | null
  routeVersionId?: number | string | null
  segment?: SegmentContext | null
}>()
const router = useRouter()
const operationContext = computed(() => ({
  segment_id: props.segment?.id || '',
  operation_name: props.segment?.normalized_step_name || '',
  phase: props.segment?.phase || '',
  source_operation_name: props.segment?.source_operation_names?.[0] || '',
}))
const searchQuery = computed(() => (
  props.segment?.source_operation_names?.[0]?.trim()
  || props.segment?.normalized_step_name?.trim()
  || ''
))
function openKnowledgeEvidence() {
  const query: Record<string, string> = { operation_context: JSON.stringify(operationContext.value) }
  if (searchQuery.value) query.q = searchQuery.value
  if (props.projectId) query.project_id = String(props.projectId)
  if (props.routeVersionId) query.route_version_id = String(props.routeVersionId)
  router.push({ path: '/knowledge', query })
}
</script>
<template>
  <button class="knowledge-evidence-entry" type="button" @click="openKnowledgeEvidence">
    <span class="knowledge-evidence-entry-icon" aria-hidden="true">⌕</span>
    <span><strong>企业知识依据</strong><small>查询当前工序规程与标准</small></span>
  </button>
</template>
<style scoped>
.knowledge-evidence-entry { display: inline-flex; align-items: center; gap: 8px; border: 1px solid #c7d2fe; border-radius: 10px; background: #eef2ff; color: #3730a3; cursor: pointer; padding: 8px 11px; text-align: left; }
.knowledge-evidence-entry:hover { border-color: #818cf8; background: #e0e7ff; }
.knowledge-evidence-entry-icon { font-size: 18px; line-height: 1; }
.knowledge-evidence-entry strong, .knowledge-evidence-entry small { display: block; }
.knowledge-evidence-entry strong { font-size: 12px; }
.knowledge-evidence-entry small { color: #6366f1; font-size: 10px; margin-top: 2px; }
</style>
