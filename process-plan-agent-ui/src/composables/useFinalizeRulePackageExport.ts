import { ref, type ComputedRef, type Ref } from 'vue'
import {
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import { createZipBlob, downloadBlob, textFile } from '@/utils/exportArchive'
import {
  buildFactorDictionaryExport,
  buildFinalizeRuleMarkdown,
  buildInputSchemaExport,
  buildRouteCatalogExport,
  buildRouteRulesExport,
  validateRulePackage,
} from '@/utils/finalizeRulePackage'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

type UseFinalizeRulePackageExportOptions = {
  projectId: Ref<number | null>
  projectName: Ref<string>
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  segmentCards: ComputedRef<FinalizeCard[]>
  displayName: (segment: Segment) => string
  metaLabel: (segment: Segment) => string
  phaseLabel: (segment: Pick<Segment, 'phase' | 'normalized_step_name' | 'sequence'>) => string
  primarySteps: (segment: any) => string[]
  attachedSteps: (segment: any) => string[]
  onExportedVersion?: (version: number) => void
}

function safeFilenamePart(value: string) {
  return value.replace(/[\/:*?"<>|]/g, '_')
}

export function useFinalizeRulePackageExport(options: UseFinalizeRulePackageExportOptions) {
  const exportingRulePackage = ref(false)

  function buildRuleReport() {
    return buildFinalizeRuleMarkdown({
      projectName: options.projectName.value || '未命名任务',
      routeVersion: options.savedRoute.value?.version || null,
      cards: options.segmentCards.value,
      displayName: options.displayName,
      metaLabel: options.metaLabel,
      phaseLabel: options.phaseLabel,
    })
  }

  function buildRouteCatalog() {
    return buildRouteCatalogExport({
      projectId: options.projectId.value,
      projectName: options.projectName.value || '未命名任务',
      routeVersion: options.savedRoute.value?.version || null,
      cards: options.segmentCards.value,
      displayName: options.displayName,
      phaseLabel: options.phaseLabel,
      primarySteps: options.primarySteps,
      attachedSteps: options.attachedSteps,
    })
  }

  function buildRouteRules() {
    return buildRouteRulesExport({
      projectId: options.projectId.value,
      projectName: options.projectName.value || '未命名任务',
      routeVersion: options.savedRoute.value?.version || null,
      cards: options.segmentCards.value,
      displayName: options.displayName,
    })
  }

  async function downloadRuleDocument() {
    if (!options.projectId.value || exportingRulePackage.value) return

    const safeProjectName = safeFilenamePart(options.projectName.value || `任务_${options.projectId.value || 'unknown'}`)
    const inputSchema = buildInputSchemaExport()
    const factorDictionary = buildFactorDictionaryExport()
    const routeCatalog = buildRouteCatalog()
    const routeRules = buildRouteRules()
    const ruleReport = buildRuleReport()
    const validation = validateRulePackage(inputSchema, routeCatalog, routeRules, ruleReport)

    if (validation.errors.length) {
      window.alert(`规则包校验失败，暂不导出：\n\n${validation.errors.join('\n')}`)
      return
    }
    if (validation.warnings.length) {
      console.warn('规则包校验提醒', validation.warnings)
    }

    const files = [
      { name: 'input_schema.json', content: textFile(inputSchema) },
      { name: 'factor_dictionary.json', content: textFile(factorDictionary) },
      { name: 'route_catalog.json', content: textFile(routeCatalog) },
      { name: 'route_rules.json', content: textFile(routeRules) },
      { name: 'rule_report.md', content: ruleReport },
    ]

    exportingRulePackage.value = true
    try {
      const savedPackage = await saveFinalizedRulePackage({
        project_id: options.projectId.value,
        route_version_id: options.savedRoute.value?.route_id || null,
        package_name: `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}`,
        input_schema: inputSchema,
        route_catalog: routeCatalog,
        route_rules: routeRules,
        rule_report_md: ruleReport,
        validation_report: {
          errors: validation.errors,
          warnings: validation.warnings,
          file_count: files.length,
        },
      })
      options.onExportedVersion?.(savedPackage.version)
      downloadBlob(createZipBlob(files), `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}_v${savedPackage.version}.zip`)
    } catch (err: any) {
      console.error('保存规则包失败', err)
      const message = err?.response?.data?.detail || err?.message || '未知错误'
      window.alert(`规则包保存失败，暂不下载：\n\n${message}`)
    } finally {
      exportingRulePackage.value = false
    }
  }

  return {
    exportingRulePackage,
    downloadRuleDocument,
  }
}
