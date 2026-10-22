import { ref, type ComputedRef, type Ref } from 'vue'
import {
  compileRulePackage,
  getCurrentGroupTemplate,
  precheckFinalizedRulePackage,
  saveFinalizedRulePackage,
  type SavedNormalizedRouteVersionResult,
  type CanonicalConditionField,
} from '@/api'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'
import { createZipBlob, downloadBlob, textFile } from '@/utils/exportArchive'
import {
  buildCompileRequestFromCards,
  buildRuleReportFromV2Package,
  exportBlockingCards,
} from '@/utils/finalizeRulePackage'
import { isGroupTemplateReady } from '@/composables/projectGroupTemplateCheck'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'
import type { FinalRouteStep } from '@/composables/finalRouteSteps'

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
  finalSteps?: (segment: Segment) => FinalRouteStep[]
  conditionFields: Ref<CanonicalConditionField[]>
  onBlockedCards?: (cards: FinalizeCard[]) => void | Promise<void>
  onExportIssue?: (issue: { title: string; summary: string; details?: string }) => void
  onPrecheck?: (result: Awaited<ReturnType<typeof precheckFinalizedRulePackage>>) => void
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

export function useFinalizeRulePackageExport(options: UseFinalizeRulePackageExportOptions) {
  const exportingRulePackage = ref(false)

  function reportExportIssue(title: string, summary: string, details = '') {
    options.onExportIssue?.({ title, summary, details })
  }

  async function ensureTemplateMappingReady(projectId: number) {
    try {
      const template = await getCurrentGroupTemplate(projectId)
      if (!isGroupTemplateReady(template)) {
        reportExportIssue('模板分组映射尚未完成', '请为右侧每个包含特征的分组，至少关联一个特征到左侧工步后再发布。无需映射组内全部特征或每个工步。')
        return false
      }
      return true
    } catch (err: any) {
      if (err?.response?.status === 404) {
        reportExportIssue('尚未绑定分组模板', '请返回模板分组映射页上传模板，并为每个包含特征的分组至少关联一个特征。')
        return false
      }
      throw err
    }
  }

  /** V2 主路径：后端 compile → 保存并发布 → 下载与库一致的快照 ZIP */
  async function downloadRuleDocument() {
    if (!options.projectId.value || exportingRulePackage.value) return

    const safeProjectName = safeFilenamePart(options.projectName.value || `任务_${options.projectId.value || 'unknown'}`)
    const packageName = `${safeProjectName}_${FINALIZE_EXPORT_COPY.documentNameSuffix}`
    const blockingCards = exportBlockingCards(options.segmentCards.value)
    if (blockingCards.length) {
      await options.onBlockedCards?.(blockingCards)
      return
    }
    if (!options.conditionFields.value.length) {
      reportExportIssue('字段库尚未加载', '请稍后刷新页面，待标准字段库加载完成后再发布规则包。')
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
      finalSteps: options.finalSteps,
      conditionFields: options.conditionFields.value,
    })

    if (!compileRequest.processes.length) {
      reportExportIssue('没有可发布的工序', '请先返回规则分析，确认路线中至少包含一道工序。')
      return
    }

    exportingRulePackage.value = true
    try {
      const compiled = await compileRulePackage(compileRequest)
      if (!compiled.validation?.valid) {
        const detail = formatValidationErrors(compiled.validation) || '规则包校验未通过'
        reportExportIssue('规则包还不能发布', '请先修正未通过校验的规则，再重新发布。', detail)
        return
      }
      if (!await ensureTemplateMappingReady(options.projectId.value)) {
        return
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

      const packagePayload = {
        project_id: options.projectId.value,
        expected_workflow_revision: options.savedRoute.value?.workflow_revision || 0,
        route_version_id: options.savedRoute.value?.route_id || null,
        package_name: packageName,
        schema_version: '2.0',
        manifest: compiled.package.manifest,
        factor_dictionary: compiled.package.factor_dictionary,
        input_schema: compiled.package.input_schema,
        route_catalog: compiled.package.route_catalog,
        route_rules: compiled.package.route_rules,
        test_cases: compiled.package.test_cases || [],
        rule_report_md: ruleReport,
        validation_report: compiled.validation,
      }
      const precheck = await precheckFinalizedRulePackage(packagePayload)
      options.onPrecheck?.(precheck)
      if (!precheck.ok) {
        const blockerText = precheck.blockers
          .map((item: any) => item?.process_name
            ? `${item.process_name}：${item.message}${item.required_by_labels?.length ? `（${item.required_by_labels.join('、')}）` : ''}`
            : item?.message)
          .filter(Boolean)
          .join('\n')
        reportExportIssue(
          '规则包还不能发布',
          '请先处理发布前预检清单中的阻塞项。',
          blockerText || precheck.checklist.filter(item => item.status === 'blocking').map(item => item.message).join('\n'),
        )
        return
      }
      const savedPackage = await saveFinalizedRulePackage(packagePayload)

      options.onExportedVersion?.(savedPackage.version, {
        schemaVersion: savedPackage.schema_version,
        status: savedPackage.status,
      })

      const tables = savedPackage.demo_tables
      if (savedPackage.export_error || !tables
        || !Array.isArray(tables.factor_table)
        || !Array.isArray(tables.full_route_table) || !tables.full_route_table.length
        || !Array.isArray(tables.rule_table)) {
        reportExportIssue(
          '三文件快照不可下载',
          savedPackage.export_error || '此版本缺少完整的三文件快照，请重新发布后下载。',
        )
        return
      }

      const files = [
        { name: 'factor_table.json', content: textFile(tables.factor_table) },
        { name: 'full_route_table.json', content: textFile(tables.full_route_table) },
        { name: 'rule_table.json', content: textFile(tables.rule_table) },
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
      const blockers = Array.isArray(detail?.blockers) ? detail.blockers : []
      const blockerText = blockers
        .map((item: any) => item?.process_name ? `${item.process_name}：${item.message}` : item?.message)
        .filter(Boolean)
        .join('\n')
      const message = typeof detail === 'string'
        ? detail
        : detail?.message || err?.message || '未知错误'
      reportExportIssue(
        '规则包发布失败',
        '规则包尚未发布，请先完成必要的分组模板映射后再试。',
        [message, blockerText].filter(Boolean).join('\n'),
      )
    } finally {
      exportingRulePackage.value = false
    }
  }

  return {
    exportingRulePackage,
    downloadRuleDocument,
  }
}
