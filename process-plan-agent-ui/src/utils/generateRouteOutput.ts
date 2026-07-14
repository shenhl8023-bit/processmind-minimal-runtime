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
