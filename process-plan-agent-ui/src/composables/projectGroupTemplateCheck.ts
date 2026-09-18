import { getCurrentGroupTemplate, type ProjectGroupTemplate } from '@/api/extract'

export interface GroupTemplateCheckResult {
  ready: boolean
  code?: 'missing_template' | 'missing_mappings' | 'network_error'
  message?: string
}

export function isGroupTemplateReady(template: ProjectGroupTemplate | null | undefined): boolean {
  if (!template) return false
  const hasLegacy = Boolean(template.mappings && template.mappings.length > 0)
  const confirmed = (template.step_mappings || []).filter(
    (m: any) => m.status === 'confirmed' && Array.isArray(m.template_group_path) && m.template_group_path.length > 0,
  )
  return hasLegacy || confirmed.length > 0
}

export async function checkProjectGroupTemplateReady(projectId: number): Promise<GroupTemplateCheckResult> {
  if (!projectId) {
    return { ready: false, code: 'missing_template', message: '未指定项目' }
  }
  try {
    const template = await getCurrentGroupTemplate(projectId)
    if (!template) {
      return { ready: false, code: 'missing_template', message: '尚未上传或绑定分组模板' }
    }
    if (!isGroupTemplateReady(template)) {
      return { ready: false, code: 'missing_mappings', message: '尚未完成任何工序的分组模板映射' }
    }
    return { ready: true }
  } catch (err: any) {
    if (err?.response?.status === 404) {
      return { ready: false, code: 'missing_template', message: '尚未上传或绑定分组模板' }
    }
    console.warn('检查分组模板失败:', err)
    return { ready: false, code: 'network_error', message: '检查分组模板失败，请稍后重试' }
  }
}
