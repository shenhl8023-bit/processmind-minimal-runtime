import { ref, type ComputedRef, type Ref } from 'vue'
import {
  compileRulePackage,
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
  type CanonicalConditionField,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import { createZipBlob, downloadBlob, textFile } from '@/utils/exportArchive'
import type { KmaiMappingIssue } from '@/api/kmaiFactorMappings'
import {
  buildCompileRequestFromCards,
  buildRuleReportFromV2Package,
  hasCurrentConfirmedUserRule,
  requiresConfirmedUserRule,
} from '@/utils/finalizeRulePackage'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'

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
  conditionFields: Ref<CanonicalConditionField[]>
  onBlockedCards?: (cards: FinalizeCard[]) => void | Promise<void>
  onExportIssue?: (issue: { title: string; summary: string; details?: string }) => void
  onKmaiMappingsRequired?: (
    issues: KmaiMappingIssue[],
    rulePackage: Record<string, unknown>,
  ) => Promise<boolean>
  onExportedVersion?: (version: number, meta?: { schemaVersion: string; status: string }) => void
  onWorkflowConflict?: () => void | Promise<void>
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

function getKmaiMappingIssues(errors: Array<any> = []): KmaiMappingIssue[] {
  return errors
    .filter(issue => (
      (issue.code === 'kmai_mapping_required' || issue.code === 'kmai_unmapped_value')
      && issue.field && issue.value
    ))
    .map(issue => ({
      field: issue.field,
      value: issue.value,
      occurrences: issue.occurrences || 1,
      rule_refs: issue.rule_refs || [],
      suggested_existing_factors: issue.suggested_existing_factors || [],
      can_create_manual_factor: issue.can_create_manual_factor ?? true,
    }))
}

function getManualKmaiFactors(files: Record<string, Record<string, unknown>>) {
  const factorSchema = files['factor_schema.json']
  const factors = Array.isArray(factorSchema?.factors) ? factorSchema.factors : []
  return factors
    .filter((factor: any) => factor?.source_mode === 'manual_override' && factor?.factor_key)
    .map((factor: any) => ({ key: String(factor.factor_key), name: String(factor.name || factor.factor_key) }))
}

export function useFinalizeRulePackageExport(options: UseFinalizeRulePackageExportOptions) {
  const exportingRulePackage = ref(false)

  function reportExportIssue(title: string, summary: string, details = '') {
    options.onExportIssue?.({ title, summary, details })
  }

  /** V2 主路径：后端 compile → 保存并发布 → 下载与库一致的快照 ZIP */
  async function downloadRuleDocument() {
    if (!options.projectId.value || exportingRulePackage.value) return

    const safeProjectName = safeFilenamePart(options.projectName.value || `任务_${options.projectId.value || 'unknown'}`)
    const packageName = `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}`
    const unconfirmedCards = options.segmentCards.value.filter(
      item => requiresConfirmedUserRule(item) && !hasCurrentConfirmedUserRule(item),
    )
    if (unconfirmedCards.length) {
      await options.onBlockedCards?.(unconfirmedCards)
      return
    }
    if (!options.conditionFields.value.length) {
      reportExportIssue('字段库尚未加载', '请稍后刷新页面，待标准字段库加载完成后再导出规则包。')
      return
    }
    const compileRequest = buildCompileRequestFromCards({
      projectId: options.projectId.value,
      packageName,
      routeVersionId: options.savedRoute.value?.route_id || null,
      cards: options.segmentCards.value,
      displayName: options.displayName,
      phaseLabel: options.phaseLabel,
      primarySteps: options.primarySteps,
      attachedSteps: options.attachedSteps,
      conditionFields: options.conditionFields.value,
    })

    if (!compileRequest.processes.length) {
      reportExportIssue('没有可导出的工序', '请先返回规则分析，确认路线中至少包含一道工序。')
      return
    }

    exportingRulePackage.value = true
    try {
      let compiled = await compileRulePackage(compileRequest)
      if (!compiled.validation?.valid) {
        const detail = formatValidationErrors(compiled.validation) || '规则包校验未通过'
        reportExportIssue('规则包还不能导出', '请先修正未通过校验的规则，再重新导出。', detail)
        return
      }
      if (!compiled.kmai_compatibility?.valid) {
        const mappingIssues = getKmaiMappingIssues(compiled.kmai_compatibility.errors)
        if (mappingIssues.length) {
          const resolved = await options.onKmaiMappingsRequired?.(
            mappingIssues,
            compiled.package as unknown as Record<string, unknown>,
          )
          if (!resolved) return

          // A persisted mapping changes the compiled rule package and KmAI files.
          compiled = await compileRulePackage(compileRequest)
          if (!compiled.validation?.valid) {
            const detail = formatValidationErrors(compiled.validation) || 'Rule package validation failed after resolving mappings.'
            reportExportIssue('Rule package cannot be exported', 'Fix the validation errors and export again.', detail)
            return
          }
          if (!compiled.kmai_compatibility?.valid) {
            const detail = JSON.stringify(compiled.kmai_compatibility?.errors || [], null, 2)
            reportExportIssue('KmAI package is still incompatible', 'The saved mappings did not resolve every KmAI compatibility issue.', detail)
            return
          }
        }
        if (!compiled.kmai_compatibility?.valid) {
          const detail = formatValidationErrors(compiled.kmai_compatibility) || 'KmAI compatibility validation failed.'
          reportExportIssue('规则包暂不兼容 KmAI', '当前规则中有 KmAI 尚不支持的表达，请根据检查详情调整后再导出。', detail)
          return
        }
      }

      const ruleReport = buildRuleReportFromV2Package({
        projectName: options.projectName.value || '未命名任务',
        packageName,
        contentHash: compiled.content_hash,
        processes: compiled.package.route_catalog.processes,
        rules: compiled.package.route_rules.rules,
        processRelations: compiled.package.route_rules.process_relations || [],
        validation: compiled.validation,
      })

      const savedPackage = await saveFinalizedRulePackage({
        project_id: options.projectId.value,
        expected_workflow_revision: options.savedRoute.value?.workflow_revision || 0,
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

      const authoritativeKmai = savedPackage.kmai_compatibility
      if (!authoritativeKmai?.valid) {
        reportExportIssue('KmAI 导出未完成', '服务器未返回可发布的 KmAI 兼容文件，请重新导出。')
        return
      }

      const manualKmaiFactors = getManualKmaiFactors(authoritativeKmai.files)
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
        ...Object.entries(authoritativeKmai.files).map(([name, content]) => ({
          name: `kmai-v1/${name}`,
          content: textFile(content),
        })),
        {
          name: 'kmai-v1/README-替换说明.txt',
          content: [
            'KmAI 规则文件替换说明',
            '',
            `目标目录：${authoritativeKmai.target_directory}`,
            '',
            '1. 先停止 KmAI Agent。',
            '2. 备份目标目录中同名的四个 JSON 文件。',
            '3. 将本目录中的 factor_schema.json、factor_expansion_rules.json、route_catalog.json、route_rules.json 复制到目标目录并覆盖。',
            '4. 不要删除或覆盖原有 group_match_rules.json。',
            '5. 重新启动 KmAI Agent；后续工艺路线生成将使用本次导出的 ProcessMind 规则。',
            '6. route_catalog.json 的 template_group_aliases 为 ProcessMind 附加元数据；KmAI v1 会忽略它，不影响路线生成。',
            '',
            'Manual boolean factors require manual.factor_overrides values (true/false):',
            ...(manualKmaiFactors.length
              ? manualKmaiFactors.map(factor => `- ${factor.key}: ${factor.name}`)
              : ['- None']),
            '',
          ].join('\n'),
        },
      ]
      downloadBlob(
        createZipBlob(files),
        `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}_v${savedPackage.version}.zip`,
      )
    } catch (err: any) {
      console.error('保存规则包失败', err)
      if (isWorkflowRevisionConflict(err)) {
        reportExportIssue('页面状态已过期', '上游工作流已经重新处理，正在加载最新状态。')
        await options.onWorkflowConflict?.()
        return
      }
      const detail = err?.response?.data?.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || err?.message || '未知错误'
      reportExportIssue('规则包保存失败', '规则包尚未发布，请检查服务状态后重新导出。', message)
    } finally {
      exportingRulePackage.value = false
    }
  }

  return {
    exportingRulePackage,
    downloadRuleDocument,
  }
}
