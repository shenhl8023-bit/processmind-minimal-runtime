import { ref } from 'vue'
import { getProjectWorkflowProgress } from '@/api/projects'
import { resolveCurrentProjectId } from '@/composables/useCurrentProject'

export type WorkflowNavigationProgress = Awaited<ReturnType<typeof getProjectWorkflowProgress>>

const workflowSteps = [
  { path: '/upload', label: '上传资料' },
  { path: '/extract', label: '路线归并' },
  { path: '/analysis', label: '规则分析' },
  { path: '/template-mapping', label: '模板映射' },
  { path: '/finalize', label: '规则定稿' },
  { path: '/generate', label: '验证生成' },
] as const

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
) {
  const targetStep = workflowSteps.findIndex(step => path === step.path || path.startsWith(`${step.path}/`)) + 1
  if (!targetStep || targetStep === 1) return true as const

  const projectId = resolveCurrentProjectId(String(query.project_id || ''))
  if (!projectId) return { path: '/upload' }
  if (!progress) return { path: '/upload', query: { project_id: projectId } }
  if (targetStep <= progress.max_available_step) return true as const

  const availableStep = workflowSteps[Math.max(0, progress.max_available_step - 1)] || workflowSteps[0]
  return {
    path: availableStep.path,
    query: { project_id: projectId },
  }
}

export async function guardWorkflowRoute(to: {
  path: string
  query: Record<string, unknown>
}) {
  const targetStep = workflowSteps.findIndex(step => to.path === step.path || to.path.startsWith(`${step.path}/`)) + 1
  if (!targetStep || targetStep === 1) return true

  const projectIdText = resolveCurrentProjectId(String(to.query.project_id || ''))
  if (!projectIdText) {
    workflowBlockedNotice.value = '请先选择任务并完成上传资料，再进入后续步骤。'
    return { path: '/upload' }
  }

  let progress: WorkflowNavigationProgress
  try {
    progress = await refreshWorkflowNavigation(Number(projectIdText))
  } catch {
    workflowBlockedNotice.value = '无法确认当前工作流进度，请重试后继续。'
    return { path: '/upload', query: { project_id: projectIdText } }
  }

  const access = resolveWorkflowRouteAccess(to.path, { ...to.query, project_id: projectIdText }, progress)
  if (access === true) {
    workflowBlockedNotice.value = ''
    return true
  }

  const requiredStep = workflowSteps[Math.max(0, progress.max_available_step - 1)] || workflowSteps[0]
  workflowBlockedNotice.value = `请先完成【${requiredStep.label}】，再进入后续步骤。`
  return access
}
