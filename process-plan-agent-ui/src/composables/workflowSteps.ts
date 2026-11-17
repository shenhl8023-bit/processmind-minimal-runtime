const internalSteps = [
  { path: '/upload', internalStep: 1, label: '上传资料' },
  { path: '/extract', internalStep: 2, label: '路线归并' },
  { path: '/analysis', internalStep: 3, label: '规则分析' },
  { path: '/finalize', internalStep: 4, label: '规则定稿' },
  { path: '/generate', internalStep: 5, label: '工艺路线验证' },
  { path: '/template-mapping', internalStep: 6, label: '模板映射（可选）' },
] as const

export function getWorkflowSteps(mappingEnabled = true) {
  return internalSteps.filter(step => mappingEnabled || step.internalStep !== 6)
    .map((step, index) => ({ ...step, number: index + 1 }))
}

export function availableWorkflowStep(maxAvailableStep: number, mappingEnabled = true) {
  return getWorkflowSteps(mappingEnabled).filter(step => step.internalStep <= maxAvailableStep).slice(-1)[0]
    || getWorkflowSteps(mappingEnabled)[0]!
}
