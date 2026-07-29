import type { GenerateRouteResult } from '@/api'
import { downloadBlob } from '@/utils/exportArchive'

export function normalizedProcessSteps(step: { process_steps?: string[] }) {
  return Array.isArray(step.process_steps)
    ? step.process_steps.map(item => String(item || '').trim()).filter(Boolean)
    : []
}

export function displayStepSequence(step: { sequence?: number | null }, index: number) {
  return step.sequence || (index + 1) * 10
}

export function formatGenerateErrorDetail(
  detail: unknown,
  fieldLabels: Record<string, string> = {},
) {
  if (Array.isArray(detail)) {
    const messages = detail
      .map((item) => {
        if (!item || typeof item !== 'object') return ''
        const row = item as Record<string, any>
        const field = String(row.field || row.path || '').replace(/^inputs\./, '')
        const label = fieldLabels[field] || field
        const reason = String(row.reason || row.message || row.msg || '').trim()
        if (!reason) return ''
        const allowedValues = Array.isArray(row.allowed_values)
          ? row.allowed_values.map(value => String(value)).filter(Boolean)
          : []
        const allowedHint = allowedValues.length ? `（可选值：${allowedValues.join('、')}）` : ''
        return `${label ? `${label}：` : ''}${reason}${allowedHint}`
      })
      .filter(Boolean)
    if (messages.length) return messages.join('；')
  }
  if (detail && typeof detail === 'object') {
    const message = String((detail as Record<string, any>).message || '').trim()
    if (message) return message
  }
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  return '生成路线失败，请检查输入参数后重试。'
}

export function downloadGeneratedRouteJson(args: {
  result: GenerateRouteResult | null
  projectName: string
  projectId: number | null
}) {
  if (!args.result?.output_json_text) return
  const blob = new Blob([`${args.result.output_json_text}\n`], { type: 'application/json;charset=utf-8' })
  const safeName = (args.projectName || `任务_${args.projectId || 'unknown'}`).replace(/[\/:*?"<>|]/g, '_')
  downloadBlob(blob, `${safeName}_生成工艺路线.json`)
}
