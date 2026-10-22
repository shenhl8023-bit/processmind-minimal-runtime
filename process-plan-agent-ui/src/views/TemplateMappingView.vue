<template>
  <div class="template-mapping-view">
    <div v-if="loading" class="mapping-empty">正在加载最终路线…</div>
    <div v-else-if="error || !projectId" class="mapping-empty" role="alert">
      <p>{{ error || '请先选择任务并完成规则分析。' }}</p>
      <button class="btn btn-outline" @click="load">重新加载</button>
    </div>
    <TemplateGroupMappingDialog v-else :key="`${projectId}:${workspaceVersion}`"
      embedded :model-value="true" :project-id="projectId" :operations="operations" :legacy-aliases="{}"
      @cancel="go('/analysis')" @continue="continueToFinalize" />
  </div>
</template>
<script setup lang="ts">
import { computed, onActivated, onDeactivated, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSavedNormalizedRoute, getSupersetRoute } from '@/api/extract'
import TemplateGroupMappingDialog from '@/components/extract/TemplateGroupMappingDialog.vue'
import { buildProjectRouteQuery, resolveCurrentProjectId } from '@/composables/useCurrentProject'
import { buildFinalTemplateMappingOperations } from '@/composables/finalTemplateMappingOperations'
import type { TemplateOperation } from '@/composables/templateGroupMapping'
const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(resolveCurrentProjectId(String(route.query.project_id || ''))) || 0)
const operations = ref<TemplateOperation[]>([])
const loading = ref(false)
const error = ref('')
const workspaceVersion = ref(0)
let run = 0
let active = true
async function load() {
  if (!active || route.path !== '/template-mapping') return
  const current = ++run
  error.value = ''
  operations.value = []
  loading.value = false
  if (!projectId.value) return
  loading.value = true
  try {
    const [saved, superset] = await Promise.all([getSavedNormalizedRoute(projectId.value, true), getSupersetRoute(projectId.value, true)])
    if (current !== run) return
    if (!saved.segments.length) throw new Error('尚无已保存路线，请先返回规则分析。')
    operations.value = buildFinalTemplateMappingOperations(saved.segments, superset.superset_route)
    workspaceVersion.value += 1
  } catch (cause: any) {
    if (current === run) error.value = cause?.response?.data?.detail || cause.message || '路线加载失败，请重试。'
  } finally { if (current === run) loading.value = false }
}
function go(path: string) { void router.push({ path, query: buildProjectRouteQuery(projectId.value) }) }
function continueToFinalize() { go('/finalize') }
watch(projectId, () => { void load() })
onActivated(() => { active = true; void load() })
onDeactivated(() => { active = false; run += 1; loading.value = false })
</script>
<style scoped>
.template-mapping-view { width: calc(100% + var(--page-padding-x) * 2); height: calc(100% + 46px); min-height: 420px; display: flex; flex-direction: column; margin: -14px calc(var(--page-padding-x) * -1) -32px; }
.mapping-empty { flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 16px; color: var(--text-secondary); background: var(--bg-card); border: 1px solid var(--border-light); border-radius: var(--radius-sm); }

@media (max-width: 900px) {
  .template-mapping-view {
    height: calc(100% + 100px);
    min-height: 420px;
    margin-top: -12px;
    margin-bottom: -88px;
  }
}

@media (max-width: 860px) {
  .template-mapping-view {
    height: auto;
    min-height: 420px;
    margin-bottom: 0;
  }
}
</style>
