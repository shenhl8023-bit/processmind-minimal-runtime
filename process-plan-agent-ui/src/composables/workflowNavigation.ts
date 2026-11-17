import { ref } from 'vue'
import { getProjectWorkflowProgress } from '@/api/projects'
import { resolveCurrentProjectId } from '@/composables/useCurrentProject'
import { knowledgeLibraryEnabled, productAccess, templateMappingVisible } from '@/composables/productStatus'
import { availableWorkflowStep, getWorkflowSteps } from '@/composables/workflowSteps'

export type WorkflowNavigationProgress = Awaited<ReturnType<typeof getProjectWorkflowProgress>>

export const workflowNavigationProgress = ref<WorkflowNavigationProgress | null>(null)
export const workflowBlockedNotice = ref('')

let progressRequestId = 0

export async function refreshWorkflowNavigation(projectId: number) {
  const requestId = ++progressRequestId
  const progress = await getProjectWorkflowProgress(projectId)
  if (requestId === progressRequestId) workflowNavigationProgress.value = progress
  return progress
}

export function resolveWorkflowRouteAccess(
  path: string,
  query: Record<string, unknown>,
  progress: WorkflowNavigationProgress | null,
  mappingEnabled = templateMappingVisible.value,
) {
  const normalizedPath = path.toLowerCase()
  const retiredMapping = !mappingEnabled && /^\/template-mapping(?:\/|$)/.test(normalizedPath)
  const targetPath = retiredMapping ? '/generate' : normalizedPath
  const workflowSteps = getWorkflowSteps(mappingEnabled)
  const targetStep = workflowSteps.find(step => targetPath === step.path || targetPath.startsWith(`${step.path}/`))?.internalStep
  if (!targetStep || targetStep === 1) return true as const

  const projectId = resolveCurrentProjectId(String(query.project_id || ''))
  if (!projectId) return { path: '/upload' }
  if (!progress) return { path: '/upload', query: { project_id: projectId } }
  if (targetStep <= progress.max_available_step) {
    return retiredMapping ? { path: '/generate', query: { project_id: projectId } } : true as const
  }

  const availableStep = availableWorkflowStep(progress.max_available_step, mappingEnabled)
  return {
    path: availableStep.path,
    query: { project_id: projectId },
  }
}

export async function guardWorkflowRoute(to: {
  path: string
  query: Record<string, unknown>
}) {
  if (productAccess.value !== 'ready') {
    return to.path === '/upload' || productAccess.value === 'expired' ? true : { path: '/upload' }
  }
  if (!knowledgeLibraryEnabled.value && /^\/knowledge(?:\/|$)/i.test(to.path)) {
    return { path: '/upload', query: to.query.project_id ? { project_id: String(to.query.project_id) } : {} }
  }
  const targetPath = !templateMappingVisible.value && /^\/template-mapping(?:\/|$)/i.test(to.path) ? '/generate' : to.path.toLowerCase()
  const targetStep = getWorkflowSteps(templateMappingVisible.value)
    .find(step => targetPath === step.path || targetPath.startsWith(`${step.path}/`))?.internalStep
  if (!targetStep || targetStep === 1) return true

  const projectIdText = resolveCurrentProjectId(String(to.query.project_id || ''))
  if (!projectIdText) {
    workflowBlockedNotice.value = '请先选择任务并完成上传资料，再进入后续步骤。'
    return { path: '/upload' }
  }

  let progress: WorkflowNavigationProgress
  const requestId = progressRequestId + 1
  try {
    progress = await refreshWorkflowNavigation(Number(projectIdText))
  } catch {
    if (requestId === progressRequestId) {
      workflowBlockedNotice.value = '无法确认当前工作流进度，请重试后继续。'
    }
    return { path: '/upload', query: { project_id: projectIdText } }
  }

  const access = resolveWorkflowRouteAccess(to.path, { ...to.query, project_id: projectIdText }, progress)
  if (access === true) {
    if (requestId === progressRequestId) workflowBlockedNotice.value = ''
    return true
  }

  const requiredStep = availableWorkflowStep(progress.max_available_step, templateMappingVisible.value)
  if (requestId === progressRequestId) {
    workflowBlockedNotice.value = access.path === targetPath ? ''
      : `请先完成【${requiredStep.label}】，再进入后续步骤。`
  }
  return access
}
