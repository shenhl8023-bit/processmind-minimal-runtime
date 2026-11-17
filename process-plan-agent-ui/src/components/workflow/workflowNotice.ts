export interface WorkflowNotice {
  id: string
  level?: 'error' | 'warning' | 'progress' | 'success' | 'info'
  summary: string
  detail?: string
  actions?: { label: string; run: () => unknown; disabled?: boolean }[]
}
