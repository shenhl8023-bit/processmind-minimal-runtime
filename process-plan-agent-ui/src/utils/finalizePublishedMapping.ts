import type { FinalizedRulePackageResult, ProjectGroupTemplate } from '@/api/extract'

function canonicalMapping(value: unknown): string {
  return JSON.stringify(value, (_key, item) => (
    item && typeof item === 'object' && !Array.isArray(item)
      ? Object.fromEntries(Object.entries(item).sort(([left], [right]) => left.localeCompare(right)))
      : item
  ))
}

/** Compare the saved input mapping, before publication filters unmapped steps. */
export function isPublishedTemplateMappingCurrent(
  rulePackage: FinalizedRulePackageResult,
  template: ProjectGroupTemplate | null,
): boolean {
  const sources = rulePackage.export_sources
  if (!template || !sources || rulePackage.project_id !== template.project_id
    || !Number.isInteger(template.template_revision) || template.template_revision <= 0
    || sources.template_revision !== template.template_revision
    || !template.content_hash || sources.template_content_hash !== template.content_hash
    || !Array.isArray(sources.source_full_route_table) || !sources.source_full_route_table.length
    || !Array.isArray(template.mapping_output) || !template.mapping_output.length) return false

  return canonicalMapping(sources.source_full_route_table) === canonicalMapping(template.mapping_output)
}
