import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'

export function createGuidanceEditorDraft(configuration: AnalysisGuidanceConfiguration, operationKeys: string[]): AnalysisGuidanceConfiguration {
  const draft = JSON.parse(JSON.stringify(configuration)) as AnalysisGuidanceConfiguration
  for (const key of operationKeys) {
    if (draft.operation_guidance[key]) continue
    const inherited = draft.operation_guidance[key.replace(/#\d+$/, '')]
    draft.operation_guidance[key] = inherited ? JSON.parse(JSON.stringify(inherited)) : {}
  }
  return draft
}
