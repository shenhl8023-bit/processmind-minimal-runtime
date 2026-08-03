import { ref, type ComputedRef, type Ref } from 'vue'
import {
  compileRulePackage,
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
  type CanonicalConditionField,
  type CompileRulePackageResponse,
  type RulePackageV2,
  type SaveFinalizedRulePackageResponse,
  type StandardFactorDefinition,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import {
  buildCompileRequestFromCards,
  buildRuleReportFromV2Package,
  hasCurrentConfirmedUserRule,
  requiresConfirmedUserRule,
} from '@/utils/finalizeRulePackage'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export type RulePackagePublishReviewStatus = 'ready' | 'blocked'

export type PublishBlockDetail = {
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

export type RulePackagePublishReview = {
  status: RulePackagePublishReviewStatus
  projectName: string
  processCount: number
  ruleCount: number
  validation: CompileRulePackageResponse['validation'] | null
  kmaiCompatibility: CompileRulePackageResponse['kmai_compatibility'] | null
  manualFactors: ManualFactorSummary[]
  rulePackage: RulePackageV2 | null
  details: PublishBlockDetail[]
}

type UseFinalizeRulePackagePublishOptions = {
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
  onPublishIssue?: (issue: { title: string; summary: string; details?: string }) => void
  onPublishReviewRequired?: (review: RulePackagePublishReview) => Promise<boolean>
  onPublished?: (packageValue: SaveFinalizedRulePackageResponse) => void
  onWorkflowConflict?: () => void | Promise<void>
}

function safeFilenamePart(value: string) {
  return value.replace(/[\/:*?"<>|]/g, '_')
}

type PublishReviewIssue = { code: string; path?: string; message: string }

function reviewSourceForIssue(compiled: CompileRulePackageResponse, issue: PublishReviewIssue) {
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

export function buildPublishBlockDetails(compiled: CompileRulePackageResponse): PublishBlockDetail[] {
  const issues: PublishReviewIssue[] = [
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
    .filter((factor: any) => (
      factor?.source_mode === 'manual_override'
      && factor?.value_type === 'boolean'
      && factor?.factor_key
    ))
    .map((factor: any) => ({ key: String(factor.factor_key), name: String(factor.name || factor.factor_key) }))
}

export function buildPublishReview(
  compiled: CompileRulePackageResponse,
  projectName: string,
): RulePackagePublishReview {
  const status: RulePackagePublishReviewStatus = (
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
    details: buildPublishBlockDetails(compiled),
  }
}

function buildLocalBlockedReview(options: {
  projectName: string
  processCount: number
  ruleCount: number
  details: PublishBlockDetail[]
}): RulePackagePublishReview {
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

function localPublishBlockDetail(
  code: string,
  message: string,
  sourceText = '',
  sourceSegmentId = '',
  processName = '规则包导出',
): PublishBlockDetail {
  return {
    code,
    message,
    processName,
    sourceText,
    sourceSegmentId,
  }
}

export function useFinalizeRulePackagePublish(options: UseFinalizeRulePackagePublishOptions) {
  const publishingRulePackage = ref(false)

  function reportPublishIssue(title: string, summary: string, details = '') {
    options.onPublishIssue?.({ title, summary, details })
  }

  /** V2 主路径：后端 compile → 审核 → 保存并发布。 */
  async function publishRulePackage() {
    if (!options.projectId.value || publishingRulePackage.value) return

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
      await options.onPublishReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localPublishBlockDetail(
          'standard_field_registry_unavailable',
          '标准字段库尚未加载，请稍后刷新页面再重新审核。',
          '标准字段库',
        )],
      }))
      return
    }
    if (!options.standardFactors.value.length || !options.factorCatalogVersion.value) {
      await options.onPublishReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localPublishBlockDetail(
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
      const sourceSegmentId = typeof buildError?.sourceSegmentId === 'string'
        ? buildError.sourceSegmentId
        : ''
      const sourceCard = options.segmentCards.value.find(item => item.segment.id === sourceSegmentId)
      await options.onPublishReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: options.segmentCards.value.length,
        ruleCount: 0,
        details: [localPublishBlockDetail(
          'standard_factor_binding_failed',
          String(buildError?.message || buildError || '规则条件无法绑定标准因子'),
          sourceCard?.conditionText || '第四步规则条件',
          sourceSegmentId,
          sourceCard ? options.displayName(sourceCard.segment) : '规则包导出',
        )],
      }))
      return
    }

    if (!compileRequest.processes.length) {
      await options.onPublishReviewRequired?.(buildLocalBlockedReview({
        projectName: options.projectName.value,
        processCount: 0,
        ruleCount: (compileRequest.rules?.length || 0) + (compileRequest.process_relations?.length || 0),
        details: [localPublishBlockDetail(
          'no_exportable_processes',
          '当前没有可导出的工序，请先返回规则分析确认路线内容。',
          '第四步工序列表',
        )],
      }))
      return
    }

    publishingRulePackage.value = true
    try {
      const compiled = await compileRulePackage(compileRequest)
      const review = buildPublishReview(compiled, options.projectName.value)
      const confirmed = await options.onPublishReviewRequired?.(review)
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

      options.onPublished?.(savedPackage)
    } catch (err: any) {
      console.error('保存规则包失败', err)
      if (isWorkflowRevisionConflict(err)) {
        reportPublishIssue('页面状态已过期', '上游工作流已经重新处理，正在加载最新状态。')
        await options.onWorkflowConflict?.()
        return
      }
      const detail = err?.response?.data?.detail
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || err?.message || '未知错误'
      reportPublishIssue('规则包发布失败', '规则包尚未发布，请检查服务状态后重试。', message)
    } finally {
      publishingRulePackage.value = false
    }
  }

  return {
    publishingRulePackage,
    publishRulePackage,
  }
}
