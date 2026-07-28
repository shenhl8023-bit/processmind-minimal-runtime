import { ref } from 'vue'
import { clearAllWorkflowDataCache } from '@/composables/workflowDataCache'

export type WorkflowResetStep = 2 | 3 | 4

export interface WorkflowResetSignal {
  projectId: number
  fromStep: WorkflowResetStep
  workflowRevision: number
  emittedAt: number
}

export const workflowResetSignal = ref<WorkflowResetSignal | null>(null)

export function isWorkflowRevisionConflict(error: any) {
  const detail = error?.response?.data?.detail
  return Number(error?.response?.status) === 409
    && typeof detail === 'object'
    && /当前页面已过期|workflow_revision/.test(String(detail?.message || ''))
}

export function clearProjectWorkflowLocalState(
  projectId: number,
  fromStep: WorkflowResetStep,
  storage?: Pick<Storage, 'removeItem'>,
) {
  if (fromStep > 3) return
  const target = storage ?? (typeof window !== 'undefined' ? window.localStorage : null)
  if (!target) return
  target.removeItem(`processmind_analysis_question_tree_v10_${projectId}`)
  target.removeItem(`processmind_finalize_drafts_v4_${projectId}`)
}

export function publishWorkflowReset(reset: Omit<WorkflowResetSignal, 'emittedAt'>) {
  clearProjectWorkflowLocalState(reset.projectId, reset.fromStep)
  clearAllWorkflowDataCache()
  workflowResetSignal.value = {
    ...reset,
    emittedAt: Date.now(),
  }
}
