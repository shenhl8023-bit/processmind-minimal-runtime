<template>
  <div class="template-mapping-view">
    <div v-if="loading" class="mapping-empty">正在加载最终路线…</div>
    <div v-else-if="error || !projectId" class="mapping-empty" role="alert">
      <p>{{ error || '请先选择任务并完成规则分析。' }}</p>
      <button class="btn btn-outline" @click="load">重新加载</button>
    </div>
    <template v-else>
      <TemplateGroupMappingDialog :key="`${projectId}:${workspaceVersion}`" ref="mappingDialog"
        :page-notices="mappingPageNotices" embedded :model-value="true" :project-id="projectId" :route-version-id="routeVersionId" :workflow-revision="workflowRevision" :operations="operations" :legacy-aliases="{}" :before-save="saveAndExportMapping"
        @status="updateMappingStatus" @cancel="requestReturnToValidation" @continue="continueToFinalize" />
    </template>
    <WorkflowNavFooter v-if="loading || error || !projectId" :summary="loading ? '正在加载最终路线…' : '请先完成路线验证，再继续映射'" previous-label="← 返回路线验证" next-label="保存映射" :show-next="false" @previous="go(projectId ? '/generate' : '/upload')" />
    <el-dialog v-model="returnDialogVisible" title="返回路线验证" width="420px" :close-on-click-modal="false" :show-close="false" class="mapping-return-dialog">
      <p class="mapping-return-copy">返回后未保存的映射调整将丢失，是否返回？</p>
      <template #footer>
        <button type="button" class="btn btn-outline" @click="returnDialogVisible = false">继续映射</button>
        <button type="button" class="btn btn-primary" :disabled="mappingStatus.busy" @click="confirmReturnToValidation">返回路线验证</button>
      </template>
    </el-dialog>
  </div>
</template>
<script setup lang="ts">
import { computed, nextTick, onActivated, onBeforeUnmount, onDeactivated, onMounted, ref, watch } from 'vue'
import { onBeforeRouteLeave, onBeforeRouteUpdate, useRoute, useRouter } from 'vue-router'
import { getSavedNormalizedRoute, getSupersetRoute, type FinalizedRulePackageResult } from '@/api/extract'
import { getLatestExecutableRuleRevision, exportExecutableRuleRevision, type ExecutableRuleRevision } from '@/api/executableRules'
import { downloadValidatedRulePackage } from '@/utils/validatedRulePackageDownload'
import type { TemplateMappingSaveRequest, TemplateMappingSavedSnapshot } from '@/composables/useProjectGroupTemplate'
import TemplateGroupMappingDialog from '@/components/extract/TemplateGroupMappingDialog.vue'
import type { WorkflowNotice } from '@/components/workflow/workflowNotice'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import { buildProjectRouteQuery, resolveCurrentProjectId } from '@/composables/useCurrentProject'
import { buildFinalTemplateMappingOperations } from '@/composables/finalTemplateMappingOperations'
import type { TemplateOperation } from '@/composables/templateGroupMapping'
const route = useRoute()
const router = useRouter()
const projectId = computed(() => Number(resolveCurrentProjectId(String(route.query.project_id || ''))) || 0)
const executableRevision = ref<ExecutableRuleRevision | null>(null)
const pendingDownload = ref<FinalizedRulePackageResult | null>(null)
const downloadNotice = ref('')
const operations = ref<TemplateOperation[]>([])
const loading = ref(false)
const error = ref('')
const workspaceVersion = ref(0)
const workflowRevision = ref(0)
const routeVersionId = ref(0)
const mappingDialog = ref<InstanceType<typeof TemplateGroupMappingDialog> | null>(null)
const mappingStatus = ref({ dirty: false, busy: false })
const mappingNotice = ref('')
const returnDialogVisible = ref(false)
const mappingPageNotices = computed<WorkflowNotice[]>(() => {
  const notices: WorkflowNotice[] = []
  if (downloadNotice.value) notices.push({ id: 'mapping-download', level: 'warning', summary: '规则包下载未完成', detail: downloadNotice.value, actions: [{ label: '重新下载规则包', run: retryPackageDownload }] })
  if (mappingNotice.value) notices.push({ id: 'mapping-unsaved', level: 'warning', summary: mappingStatus.value.busy ? '请等待当前映射操作完成' : '映射还有未保存的修改', detail: mappingNotice.value, actions: mappingStatus.value.dirty && !mappingStatus.value.busy ? [{ label: '放弃未保存的修改', run: discardMappingChanges }] : [] })
  return notices
})
let run = 0
let active = true
async function load() {
  if (!active || route.path !== '/template-mapping') return
  const current = ++run
  returnDialogVisible.value = false
  error.value = ''
  executableRevision.value = null
  pendingDownload.value = null
  downloadNotice.value = ''
  operations.value = []
  loading.value = false
  if (!projectId.value) return
  loading.value = true
  try {
    const [saved, superset, revision] = await Promise.all([getSavedNormalizedRoute(projectId.value, true), getSupersetRoute(projectId.value, true), getLatestExecutableRuleRevision(projectId.value)])
    if (current !== run) return
    if (!revision?.generation_ready || !revision.has_current_generation || (saved.route_id && saved.route_id !== revision.route_version_id)) throw new Error('请先在第五步使用当前规则生成并检查工艺路线。')
    executableRevision.value = revision
    if (!saved.segments.length) throw new Error('尚无已保存路线，请先返回规则分析。')
    operations.value = buildFinalTemplateMappingOperations(saved.segments, superset.superset_route)
    workflowRevision.value = saved.workflow_revision
    routeVersionId.value = saved.route_id
    workspaceVersion.value += 1
  } catch (cause: any) {
    if (current === run) error.value = cause?.response?.data?.detail || cause.message || '路线加载失败，请重试。'
  } finally { if (current === run) loading.value = false }
}
function go(path: string) { void router.push({ path, query: buildProjectRouteQuery(projectId.value) }) }
function continueToFinalize() { go('/generate') }
async function retryPackageDownload() {
  const saved = pendingDownload.value
  if (!saved) return
  const context = run, id = projectId.value
  const isCurrent = () => active && context === run && projectId.value === id && pendingDownload.value === saved
  try {
    await downloadValidatedRulePackage(saved, executableRevision.value?.package.manifest.package_name || '工艺规程', { isCurrent })
    if (!isCurrent()) return
    downloadNotice.value = ''
    pendingDownload.value = null
  } catch (cause: any) {
    if (!isCurrent()) return
    const detail = cause?.response?.data?.detail
    const reason = (typeof detail === 'string' ? detail : detail?.message) || cause?.message || '下载准备失败'
    downloadNotice.value = `映射和规则包已保存，下载未完成：${reason}。请核对后重新下载。`
  }
}
async function saveAndExportMapping(request: TemplateMappingSaveRequest): Promise<TemplateMappingSavedSnapshot> {
  const revision = executableRevision.value, current = run, id = projectId.value
  if (!revision?.generation_ready || !revision.has_current_generation || request.project_id !== id) throw new Error('请先使用当前规则重新生成路线。')
  const saved = await exportExecutableRuleRevision(revision.id, {
    project_id: id, expected_workflow_revision: request.expected_workflow_revision,
    expected_content_hash: revision.content_hash, include_template_mapping: true, template_mapping: request,
  })
  const snapshot = saved.export_sources?.template_mapping as TemplateMappingSavedSnapshot | undefined
  if (!snapshot || !Array.isArray(snapshot.step_mappings) || !Array.isArray(snapshot.mapping_output)) throw new Error('规则包缺少本次保存的映射快照，请刷新后重试。')
  if (current === run && id === projectId.value && active) {
    pendingDownload.value = saved
    await retryPackageDownload()
  }
  return snapshot
}

function updateMappingStatus(status: { dirty: boolean; busy: boolean }) {
  mappingStatus.value = { dirty: status.dirty, busy: status.busy }
  if (!status.dirty && !status.busy) mappingNotice.value = ''
}
function ensureMappingsSaved() {
  if (mappingStatus.value.busy) {
    mappingNotice.value = '请等待模板加载、推荐或保存完成后再离开。'
    return false
  }
  if (mappingStatus.value.dirty) {
    mappingNotice.value = '有未保存的模板映射或精度修改，请先保存或放弃修改后再离开。'
    return false
  }
  return true
}
function discardMappingChanges() {
  if (mappingStatus.value.busy) return
  mappingDialog.value?.discardChanges()
}
function requestReturnToValidation() {
  if (mappingStatus.value.busy) { ensureMappingsSaved(); return }
  if (mappingStatus.value.dirty) {
    returnDialogVisible.value = true
    return
  }
  go('/generate')
}
async function confirmReturnToValidation() {
  if (!returnDialogVisible.value) return
  if (mappingStatus.value.busy) { ensureMappingsSaved(); return }
  const current = run, id = projectId.value
  discardMappingChanges()
  await nextTick()
  if (!active || current !== run || projectId.value !== id || !ensureMappingsSaved()) return
  returnDialogVisible.value = false
  go('/generate')
}
function protectUnsavedPage(event: BeforeUnloadEvent) {
  if (!active || (!mappingStatus.value.dirty && !mappingStatus.value.busy)) return
  event.preventDefault()
  event.returnValue = ''
}
onBeforeRouteLeave(ensureMappingsSaved)
onBeforeRouteUpdate((to, from) => to.query.project_id === from.query.project_id || ensureMappingsSaved())
onMounted(() => { if (typeof window !== 'undefined') window.addEventListener('beforeunload', protectUnsavedPage) })
onBeforeUnmount(() => { if (typeof window !== 'undefined') window.removeEventListener('beforeunload', protectUnsavedPage) })
watch(projectId, () => { void load() })
onActivated(() => { active = true; void load() })
onDeactivated(() => { active = false; run += 1; loading.value = false })
</script>
<style scoped>
.template-mapping-view { width: 100%; height: 100%; min-height: 0; min-width: 0; display: flex; flex-direction: column; gap: 6px; }
.mapping-empty { flex: 1; min-height: 240px; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; padding: 24px; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-card); background: var(--pm-surface); color: var(--pm-text-secondary); font-size: 13px; line-height: 20px; text-align: center; overflow-wrap: anywhere; }
.mapping-notice { flex: 0 0 auto; display: flex; align-items: center; justify-content: space-between; flex-wrap: wrap; gap: 8px 12px; padding: 8px 12px; border: 1px solid var(--pm-warning-border); border-left-width: 3px; border-radius: var(--pm-radius-control); color: var(--pm-warning); background: var(--pm-warning-soft); font-size: 13px; line-height: 20px; }
.mapping-notice > span { flex: 1 1 280px; min-width: 0; overflow-wrap: anywhere; }
.mapping-notice > button { flex: 0 0 auto; }
.mapping-return-copy { margin: 0; color: var(--pm-text-secondary); font-size: 13px; line-height: 22px; }
@media (max-width: 720px) { .template-mapping-view { height: auto; min-height: 100%; } }
</style>
