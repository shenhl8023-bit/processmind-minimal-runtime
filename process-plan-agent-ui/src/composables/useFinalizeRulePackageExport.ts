import { ref, type ComputedRef, type Ref } from 'vue'
import {
  compileRulePackage,
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
  type CanonicalConditionField,
  type CompileRulePackageResponse,
  type RulePackageV2,
  type StandardFactorDefinition,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import { createZipBlob, downloadBlob, textFile } from '@/utils/exportArchive'
import {
  buildCompileRequestFromCards,
  buildRuleReportFromV2Package,
  hasCurrentConfirmedUserRule,
  requiresConfirmedUserRule,
} from '@/utils/finalizeRulePackage'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export type RulePackageExportReviewStatus = 'ready' | 'blocked'

export type ExportBlockDetail = {
  code: string
  message: string
  processName: string
  sourceText: string
  sourceSegmentId: string
}

export type ManualFactorSummary = {
  key: string
  name: string
}

export type RulePackageExportReview = {
  status: RulePackageExportReviewStatus
  projectName: string
  processCount: number
  ruleCount: number
  validation: CompileRulePackageResponse['validation'] | null
  kmaiCompatibility: CompileRulePackageResponse['kmai_compatibility'] | null
  manualFactors: ManualFactorSummary[]
  rulePackage: RulePackageV2 | null
  details: ExportBlockDetail[]
}

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
  standardFactors: Ref<StandardFactorDefinition[]>
  factorCatalogVersion: Ref<string>
  onBlockedCards?: (cards: FinalizeCard[]) => void | Promise<void>
  onExportIssue?: (issue: { title: string; summary: string; details?: string }) => void
  onExportReviewRequired?: (review: RulePackageExportReview) => Promise<boolean>
  onExportedVersion?: (version: number, meta?: { schemaVersion: string; status: string }) => void
  onWorkflowConflict?: () => void | Promise<void>
}

function safeFilenamePart(value: string) {
  return value.replace(/[\/:*?"<>|]/g, '_')
}

type ExportReviewIssue = { code: string; path?: string; message: string }

function reviewSourceForIssue(compiled: CompileRulePackageResponse, issue: ExportReviewIssue) {
  const ruleMatch = issue.path?.match(/^route_rules\.rules\[(\d+)]/)
  const relationMatch = issue.path?.match(/^route_rules\.process_relations\[(\d+)]/)
  const rule = ruleMatch
    ? compiled.package.route_rules.rules[Number(ruleMatch[1])]
    : undefined
  const relation = relationMatch
    ? compiled.package.route_rules.process_relations?.[Number(relationMatch[1])]
    : undefined
  const source = rule || relation
  const sourceSegmentId = source?.source_segment_id || ''
  const relatedProcessIds = rule
    ? [...(rule.then.include_process_ids || []), ...(rule.then.exclude_process_ids || [])]
    : relation
      ? [...relation.target_process_ids, ...relation.source_process_ids]
      : []
  const process = compiled.package.route_catalog.processes.find(item => item.process_id === sourceSegmentId)
    || compiled.package.route_catalog.processes.find(item => relatedProcessIds.includes(item.process_id))

  return {
    processName: process?.display_name || sourceSegmentId || '规则包导出',
    sourceText: source?.source_text || '',
    sourceSegmentId,
  }
}

export function buildExportBlockDetails(compiled: CompileRulePackageResponse): ExportBlockDetail[] {
  const issues: ExportReviewIssue[] = [
    ...(compiled.validation.errors || []),
    ...(compiled.kmai_compatibility.errors || []),
  ]
  return issues.map(issue => ({
    code: issue.code,
    message: issue.message,
    ...reviewSourceForIssue(compiled, issue),
  }))
}

function getManualKmaiFactors(files: Record<string, Record<string, unknown>>): ManualFactorSummary[] {
  const factorSchema = files['factor_schema.json']
  const factors = Array.isArray(factorSchema?.factors) ? factorSchema.factors : []
  return factors
    .filter((factor: any) => factor?.source_mode === 'manual_override' && factor?.factor_key)
    .map((factor: any) => ({ key: String(factor.factor_key), name: String(factor.name || factor.factor_key) }))
}

export function buildExportReview(
  compiled: CompileRulePackageResponse,
  projectName: string,
): RulePackageExportReview {
  const status: RulePackageExportReviewStatus = (
    compiled.validation.valid && compiled.kmai_compatibility.valid
  ) ? 'ready' : 'blocked'
  return {
    status,
    projectName: projectName || '未命名任务',
    processCount: compiled.package.route_catalog.processes.length,
    ruleCount: compiled.package.route_rules.rules.length
      + (compiled.package.route_rules.process_relations?.length || 0),
    validation: compiled.validation,
    kmaiCompatibility: compiled.kmai_compatibility,
    manualFactors: getManualKmaiFactors(compiled.kmai_compatibility.files),
    rulePackage: compiled.package,
    details: buildExportBlockDetails(compiled),
  }
}

function buildLocalBlockedReview(options: {
  projectName: string
  processCount: number
  ruleCount: number
  details: ExportBlockDetail[]
}): RulePackageExportReview {
  return {
    status: 'blocked',
    projectName: options.projectName || '未命名任务',
    processCount: options.processCount,
    ruleCount: options.ruleCount,
    validation: null,
    kmaiCompatibility: null,
    manualFactors: [],
    rulePackage: null,
    details: options.details,
  }
}

function localExportBlockDetail(
  code: string,
  message: string,
  sourceText = '',
): ExportBlockDetail {
  return {
    code,
    message,
    processName: '规则包导出',
    sourceText,
    sourceSegmentId: '',
  }
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
      item => requiresConfirmedUserRule(item)
        && !hasCurrentConfirmedUserRule(item, options.factorCatalogVersion.value),
    )
    if (unconfirmedCards.length) {
      await options.onBlockedCards?.(unconfirmedCards)
      return
    }
    if (!options.conditionFields.value.length) {
      await options.onExportReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localExportBlockDetail(
          'standard_field_registry_unavailable',
          '标准字段库尚未加载，请稍后刷新页面再重新审核。',
          '标准字段库',
        )],
      }))
      return
    }
    if (!options.standardFactors.value.length || !options.factorCatalogVersion.value) {
      await options.onExportReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localExportBlockDetail(
          'standard_factor_registry_unavailable',
          '标准因子目录尚未加载，请重试加载后再重新审核。',
          '标准因子目录',
        )],
      }))
      return
    }
    let compileRequest: ReturnType<typeof buildCompileRequestFromCards>
    try {
      compileRequest = buildCompileRequestFromCards({
        projectId: options.projectId.value,
        packageName,
        routeVersionId: options.savedRoute.value?.route_id || null,
        cards: options.segmentCards.value,
        displayName: options.displayName,
        phaseLabel: options.phaseLabel,
        primarySteps: options.primarySteps,
        attachedSteps: options.attachedSteps,
        conditionFields: options.conditionFields.value,
        standardFactors: options.standardFactors.value,
      })
    } catch (buildError: any) {
      await options.onExportReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localExportBlockDetail(
          'standard_factor_binding_failed',
          String(buildError?.message || buildError || '规则条件无法绑定标准因子'),
          '第四步规则条件',
        )],
      }))
      return
    }

    if (!compileRequest.processes.length) {
      await options.onExportReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: 0,
        ruleCount: (compileRequest.rules?.length || 0) + (compileRequest.process_relations?.length || 0),
        details: [localExportBlockDetail(
          'no_exportable_processes',
          '当前没有可导出的工序，请先返回规则分析确认路线内容。',
          '第四步工序列表',
        )],
      }))
      return
    }

    exportingRulePackage.value = true
    try {
      const compiled = await compileRulePackage(compileRequest)
      const review = buildExportReview(compiled, options.projectName.value)
      const confirmed = await options.onExportReviewRequired?.(review)
      if (!confirmed || review.status !== 'ready') return

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
