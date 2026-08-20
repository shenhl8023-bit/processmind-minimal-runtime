import { ref, type Ref } from 'vue'
import { resetWorkflow, type SavedNormalizedRouteVersionResult } from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { createBackgroundTaskGuard, runBackgroundTask } from '@/composables/runBackgroundTask'
import {
  isWorkflowRevisionConflict,
  publishWorkflowReset,
  workflowResetSignal,
  type WorkflowResetSignal,
} from '@/composables/workflowResetState'

type FinalizeIssueHandler = (title: string, summary: string, details?: string) => void

export type FinalizeWorkflowConflictOptions = {
  projectId: Ref<number | null>
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  workspaceError: Ref<string>
  onlyPending: Ref<boolean>
  loadWorkspace: (forceRefresh?: boolean) => Promise<void>
  clearAllDrafts: () => void
  cancelPendingRequests: () => void
  getRecognitionQueue: () => FinalizeCard[]
  runRecognitionQueue: (queue: FinalizeCard[], isCurrent: () => boolean) => Promise<void>
  showIssue: FinalizeIssueHandler
  setBatchNotice: (message: string) => void
  errorMessage: (error: unknown) => string
}

export function useFinalizeWorkflowConflict(options: FinalizeWorkflowConflictOptions) {
  const resetDialogVisible = ref(false)
  const resettingWorkflow = ref(false)
  const recognitionTaskGuard = createBackgroundTaskGuard()
  let locallyHandledResetAt = 0
  let workflowConflictReload: Promise<void> | null = null

  function cancelInFlightWork() {
    recognitionTaskGuard.cancel()
    options.cancelPendingRequests()
  }

  async function reloadAfterKnownConflict(notice: { title: string; summary: string } | null = null) {
    if (!workflowConflictReload) {
      cancelInFlightWork()
      if (notice) options.showIssue(notice.title, notice.summary)
      workflowConflictReload = options.loadWorkspace(true).finally(() => {
        workflowConflictReload = null
      })
    }
    await workflowConflictReload
  }

  async function handleWorkflowRevisionConflict(error: unknown) {
    if (!isWorkflowRevisionConflict(error)) return false
    await reloadAfterKnownConflict({
      title: '页面状态已过期',
      summary: '上游步骤已经重新处理，系统正在加载最新结果。',
    })
    return true
  }

  async function handleWorkflowResetSignal(signal: WorkflowResetSignal | null) {
    if (!signal || signal.emittedAt === locallyHandledResetAt) return false
    if (signal.projectId !== options.projectId.value || signal.fromStep > 4) return false
    locallyHandledResetAt = signal.emittedAt
    cancelInFlightWork()
    if (signal.fromStep <= 3) options.clearAllDrafts()
    await options.loadWorkspace(true)
    return true
  }

  async function restartAllRecognitionInBackground(context: {
    projectId: number
    workflowRevision: number
    isCurrent: () => boolean
  }) {
    await options.loadWorkspace(true)
    if (
      !context.isCurrent()
      || options.projectId.value !== context.projectId
      || options.savedRoute.value?.workflow_revision !== context.workflowRevision
    ) {
      return
    }
    if (options.workspaceError.value) {
      throw new Error(options.workspaceError.value)
    }
    const queue = [...options.getRecognitionQueue()]
    if (!queue.length) {
      options.setBatchNotice('没有需要重新识别的普通规则；人工设定保持不变。')
      return
    }
    await options.runRecognitionQueue(queue, context.isCurrent)
  }

  async function handleResetAllRecognition() {
    if (resettingWorkflow.value || !options.projectId.value || !options.savedRoute.value) return
    resettingWorkflow.value = true
    cancelInFlightWork()
    options.setBatchNotice('')
    try {
      const result = await resetWorkflow({
        project_id: options.projectId.value,
        from_step: 4,
        expected_workflow_revision: options.savedRoute.value.workflow_revision,
      })
      publishWorkflowReset({
        projectId: result.project_id,
        fromStep: 4,
        workflowRevision: result.workflow_revision,
      })
      locallyHandledResetAt = workflowResetSignal.value?.emittedAt || 0
      resetDialogVisible.value = false
      options.onlyPending.value = true
      options.setBatchNotice('重置完成，正在后台准备重新识别。')
      const task = recognitionTaskGuard.start()
      const context = {
        projectId: result.project_id,
        workflowRevision: result.workflow_revision,
        isCurrent: task.isCurrent,
      }
      runBackgroundTask(
        () => restartAllRecognitionInBackground(context),
        (error) => options.showIssue(
          '重新识别失败',
          '现有条件原文仍然保留，请刷新页面后重试。',
          options.errorMessage(error),
        ),
      )
    } catch (error: unknown) {
      options.showIssue(
        '重新识别失败',
        '现有条件原文仍然保留，请刷新页面后重试。',
        options.errorMessage(error),
      )
    } finally {
      resettingWorkflow.value = false
    }
  }

  return {
    resetDialogVisible,
    resettingWorkflow,
    cancelInFlightWork,
    reloadAfterKnownConflict,
    handleWorkflowRevisionConflict,
    handleWorkflowResetSignal,
    handleResetAllRecognition,
  }
}
