import { ref, type ComputedRef, type Ref } from 'vue'
import {
  compileRulePackage,
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import { createZipBlob, downloadBlob, textFile } from '@/utils/exportArchive'
import {
  buildCompileRequestFromCards,
  buildFactorDictionaryExport,
  buildFinalizeRuleMarkdown,
  buildInputSchemaExport,
  buildRouteCatalogExport,
  buildRouteRulesExport,
  buildRuleReportFromV2Package,
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
  onExportedVersion?: (version: number, meta?: { schemaVersion: string; status: string }) => void
}

function safeFilenamePart(value: string) {
  return value.replace(/[\/:*?"<>|]/g, '_')
}

function formatValidationErrors(validation: {
  errors?: Array<{ message?: string } | string>
}) {
  return (validation.errors || [])
    .map((item) => (typeof item === 'string' ? item : item.message || ''))
    .filter(Boolean)
    .join('\n')
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

  /** V2 主路径：后端 compile → 保存并发布 → 下载与库一致的快照 ZIP */
  async function downloadRuleDocument() {
    if (!options.projectId.value || exportingRulePackage.value) return

    const safeProjectName = safeFilenamePart(options.projectName.value || `任务_${options.projectId.value || 'unknown'}`)
    const packageName = `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}`
    const compileRequest = buildCompileRequestFromCards({
      projectId: options.projectId.value,
      packageName,
      routeVersionId: options.savedRoute.value?.route_id || null,
      cards: options.segmentCards.value,
      displayName: options.displayName,
      phaseLabel: options.phaseLabel,
      primarySteps: options.primarySteps,
      attachedSteps: options.attachedSteps,
    })

    if (!compileRequest.processes.length) {
      window.alert('当前没有可导出的工序卡片。')
      return
    }

    exportingRulePackage.value = true
    try {
      const compiled = await compileRulePackage(compileRequest)
      if (!compiled.validation?.valid) {
        const detail = formatValidationErrors(compiled.validation) || '规则包校验未通过'
        window.alert(`规则包校验失败，暂不导出：\n\n${detail}`)
        return
      }

      const ruleReport = buildRuleReportFromV2Package({
        projectName: options.projectName.value || '未命名任务',
        packageName,
        contentHash: compiled.content_hash,
        processes: compiled.package.route_catalog.processes,
        rules: compiled.package.route_rules.rules,
        validation: compiled.validation,
      })

      const savedPackage = await saveFinalizedRulePackage({
        project_id: options.projectId.value,
        route_version_id: options.savedRoute.value?.route_id || null,
        package_name: packageName,
        schema_version: '2.0',
        manifest: compiled.package.manifest,
        input_schema: compiled.package.input_schema,
        route_catalog: compiled.package.route_catalog,
        route_rules: compiled.package.route_rules,
        test_cases: compiled.package.test_cases || [],
        rule_report_md: ruleReport,
        validation_report: compiled.validation,
      })

      options.onExportedVersion?.(savedPackage.version, {
        schemaVersion: savedPackage.schema_version,
        status: savedPackage.status,
      })

      const files = [
        { name: 'manifest.json', content: textFile(savedPackage.manifest || compiled.package.manifest) },
        { name: 'input_schema.json', content: textFile(savedPackage.input_schema) },
        { name: 'route_catalog.json', content: textFile(savedPackage.route_catalog) },
        { name: 'route_rules.json', content: textFile(savedPackage.route_rules) },
        { name: 'test_cases.json', content: textFile(savedPackage.test_cases || []) },
        { name: 'rule_report.md', content: savedPackage.rule_report_md || ruleReport },
        {
          name: 'validation_report.json',
          content: textFile(savedPackage.validation_report || compiled.validation),
        },
      ]
      downloadBlob(
        createZipBlob(files),
        `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}_v${savedPackage.version}.zip`,
      )
    } catch (err: any) {
      console.error('保存规则包失败', err)
      const detail = err?.response?.data?.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || err?.message || '未知错误'
      window.alert(`规则包保存失败，暂不下载：\n\n${message}`)
    } finally {
      exportingRulePackage.value = false
    }
  }

  /** 兼容路径：继续导出 V1 并自动发布（迁移期） */
  async function downloadRuleDocumentV1Compat() {
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
        schema_version: '1.0',
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
      options.onExportedVersion?.(savedPackage.version, {
        schemaVersion: '1.0',
        status: savedPackage.status,
      })
      downloadBlob(
        createZipBlob(files),
        `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}_v${savedPackage.version}.zip`,
      )
    } catch (err: any) {
      console.error('保存 V1 规则包失败', err)
      const message = err?.response?.data?.detail || err?.message || '未知错误'
      window.alert(`规则包保存失败，暂不下载：\n\n${message}`)
    } finally {
      exportingRulePackage.value = false
    }
  }

  return {
    exportingRulePackage,
    downloadRuleDocument,
    downloadRuleDocumentV1Compat,
  }
}
