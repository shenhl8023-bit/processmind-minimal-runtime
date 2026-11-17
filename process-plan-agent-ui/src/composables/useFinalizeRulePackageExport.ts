import { ref, watch, type ComputedRef, type Ref } from 'vue'
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
import { productAccess, templateMappingEnabled } from '@/composables/productStatus'
import { nativeRulePackageFiles } from '@/utils/nativeRulePackageArchive'
import { downloadValidatedRulePackage } from '@/utils/validatedRulePackageDownload'
import { validateSampleRulePackageTables } from '@/utils/sampleRulePackageAdapter'
import { hasPendingTemplateMappingEdits } from '@/composables/templateMappingEdits'
import { isPublishedTemplateMappingCurrent } from '@/utils/finalizePublishedMapping'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]
type PublishedDownload = {
  savedPackage: Awaited<ReturnType<typeof saveFinalizedRulePackage>>
  filename: string
  mappingEnabled: boolean
}

type UseFinalizeRulePackageExportOptions = {
  projectId: Ref<number | null>
  projectName: Ref<string>
  savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  segmentCards: ComputedRef<FinalizeCard[]>
  unsavedCards?: ComputedRef<FinalizeCard[]>
  savingRuleIds?: Ref<Set<string>>
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
  return value.replace(/[\\/:*?"<>|\u0000-\u001f]/g, '_')
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
  const downloadRetryAvailable = ref(false)
  let pendingDownload: PublishedDownload | null = null
  let stateVersion = 0

  function publicationState() {
    return JSON.stringify([
      options.projectId.value, options.savedRoute.value, options.projectName.value,
      options.segmentCards.value, options.conditionFields.value,
      options.unsavedCards?.value.length || 0, [...(options.savingRuleIds?.value || [])],
      productAccess.value, templateMappingEnabled.value,
    ])
  }

  // Invalidate even when navigation or edits change away and back between clicks.
  watch(publicationState, () => {
    stateVersion += 1
    pendingDownload = null
    downloadRetryAvailable.value = false
  }, { flush: 'sync' })

  function reportExportIssue(title: string, summary: string, details = '') {
    options.onExportIssue?.({ title, summary, details })
  }

  async function ensureTemplateMappingReady(projectId: number, routeVersionId: number | null, workflowRevision: number, requestIsCurrent: () => boolean) {
    try {
      const template = await getCurrentGroupTemplate(projectId)
      if (!requestIsCurrent()) return null
      if (hasPendingTemplateMappingEdits(projectId, routeVersionId || 0, workflowRevision, template.template_revision)) {
        pendingDownload = null
        downloadRetryAvailable.value = false
        reportExportIssue('模板映射尚未保存', '模板映射或精度有未保存修改，请返回模板页保存或放弃修改后再试。')
        return null
      }
      if (!isGroupTemplateReady(template)) {
        pendingDownload = null
        downloadRetryAvailable.value = false
        reportExportIssue('模板分组映射尚未完成', '请为右侧每个包含特征的分组，至少关联一个特征到左侧工步后再发布。无需映射组内全部特征或每个工步。')
        return null
      }
      return template
    } catch (err: any) {
      if (!requestIsCurrent()) return null
      if (err?.response?.status === 404) {
        pendingDownload = null
        downloadRetryAvailable.value = false
        reportExportIssue('尚未绑定分组模板', '请返回模板分组映射页上传模板，并为每个包含特征的分组至少关联一个特征。')
        return null
      }
      throw err
    }
  }

  function templateSignature(template: Awaited<ReturnType<typeof getCurrentGroupTemplate>>) {
    return JSON.stringify([
      template.template_revision, template.content_hash, template.feature_dictionary_version,
      template.tree, template.mappings, template.step_mappings, template.mapping_output,
    ])
  }

  async function downloadSnapshot(snapshot: PublishedDownload, requestIsCurrent: () => boolean) {
    const { savedPackage, mappingEnabled } = snapshot
    if (!mappingEnabled || savedPackage.export_sources?.native_snapshot) {
      if (!nativeRulePackageFiles(savedPackage)) {
        reportExportIssue('原生快照不可下载', savedPackage.export_error || '已发布版本缺少完整的原生路线与规则快照，请刷新后检查交付快照。')
        return
      }
      if (!await downloadValidatedRulePackage(savedPackage, options.projectName.value, {
        filename: snapshot.filename, isCurrent: requestIsCurrent,
      })) return
    } else {
      const tables = savedPackage.demo_tables
      if (savedPackage.export_error || !tables
        || !Array.isArray(tables.factor_table)
        || !Array.isArray(tables.full_route_table) || !tables.full_route_table.length
        || !Array.isArray(tables.rule_table)) {
        reportExportIssue('三文件快照不可下载', savedPackage.export_error || '已发布版本缺少完整的三文件快照，请刷新后检查交付快照。')
        return
      }
      validateSampleRulePackageTables(tables)
      const files = [
        { name: 'factor_table.json', content: textFile(tables.factor_table) },
        { name: 'full_route_table.json', content: textFile(tables.full_route_table) },
        { name: 'rule_table.json', content: textFile(tables.rule_table) },
      ]
      downloadBlob(createZipBlob(files), snapshot.filename)
    }
    pendingDownload = null
    downloadRetryAvailable.value = false
  }

  /** V2 主路径：后端 compile → 保存并发布 → 下载与库一致的快照 ZIP */
  async function downloadRuleDocument() {
    if (!options.projectId.value || exportingRulePackage.value || productAccess.value !== 'ready') return
    const mappingEnabled = templateMappingEnabled.value

    const unsavedCards = options.unsavedCards?.value || []
    if (unsavedCards.length) {
      reportExportIssue('规则尚未保存', `有 ${unsavedCards.length} 项未保存，请先保存或取消修改后再发布。`)
      await options.onBlockedCards?.(unsavedCards)
      return
    }
    if (options.savingRuleIds?.value.size) {
      reportExportIssue('规则正在保存或识别', '请等待当前规则保存或识别完成后再发布。')
      return
    }

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
      includeTemplateMappings: mappingEnabled,
    })

    if (!compileRequest.processes.length) {
      reportExportIssue('没有可发布的工序', '请先返回规则分析，确认路线中至少包含一道工序。')
      return
    }
    const requestProject = options.projectId.value
    const requestRoute = options.savedRoute.value?.route_id || null
    const requestRevision = options.savedRoute.value?.workflow_revision || 0
    const requestProjectName = options.projectName.value
    const requestContent = publicationState()
    const requestStateVersion = stateVersion
    function requestIsCurrent() {
      if (productAccess.value !== 'ready') return false
      const current = requestStateVersion === stateVersion && options.projectId.value === requestProject
        && (options.savedRoute.value?.route_id || null) === requestRoute
        && (options.savedRoute.value?.workflow_revision || 0) === requestRevision
        && !options.unsavedCards?.value.length && !options.savingRuleIds?.value.size
        && publicationState() === requestContent
      if (!current && options.projectId.value === requestProject) {
        reportExportIssue('页面状态已变化', '发布期间任务、路线或规则有修改，请核对当前内容后重新发布。')
      }
      return current
    }

    exportingRulePackage.value = true
    let stage = '编译规则包'
    let publishedForDownload = Boolean(pendingDownload)
    try {
      const retry = pendingDownload
      if (retry) {
        let sameTemplate = true
        if (mappingEnabled) {
          stage = '读取模板映射'
          const template = await ensureTemplateMappingReady(requestProject, requestRoute, requestRevision, requestIsCurrent)
          if (!template || !requestIsCurrent()) return
          sameTemplate = isPublishedTemplateMappingCurrent(retry.savedPackage, template)
        }
        if (sameTemplate) {
          stage = mappingEnabled ? '下载三文件快照' : '下载原生快照'
          await downloadSnapshot(retry, requestIsCurrent)
          return
        }
        pendingDownload = null
        downloadRetryAvailable.value = false
        publishedForDownload = false
      }
      stage = '编译规则包'
      const compiled = await compileRulePackage(compileRequest)
      if (!requestIsCurrent()) return
      if (!compiled.validation?.valid) {
        const detail = formatValidationErrors(compiled.validation) || '规则包校验未通过'
        reportExportIssue('规则包还不能发布', '请先修正未通过校验的规则，再重新发布。', detail)
        return
      }
      let currentTemplateSignature: string | null = null
      if (mappingEnabled) {
        stage = '读取模板映射'
        const template = await ensureTemplateMappingReady(requestProject, requestRoute, requestRevision, requestIsCurrent)
        if (!template || !requestIsCurrent()) return
        currentTemplateSignature = templateSignature(template)
      }

      const ruleReport = buildRuleReportFromV2Package({
        projectName: requestProjectName || '未命名任务',
        packageName,
        contentHash: compiled.content_hash,
        processes: compiled.package.route_catalog.processes,
        rules: compiled.package.route_rules.rules,
        processRelations: compiled.package.route_rules.process_relations || [],
        processConfigurations: compiled.package.route_rules.process_configurations || [],
        conditionFields: options.conditionFields.value,
        validation: compiled.validation,
      })

      const packagePayload = {
        project_id: requestProject,
        expected_workflow_revision: requestRevision,
        route_version_id: requestRoute,
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
      stage = '发布预检'
      const precheck = await precheckFinalizedRulePackage(packagePayload)
      if (!requestIsCurrent()) return
      options.onPrecheck?.(precheck)
      if (!requestIsCurrent()) return
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
      if (mappingEnabled) {
        stage = '读取模板映射'
        const template = await ensureTemplateMappingReady(requestProject, requestRoute, requestRevision, requestIsCurrent)
        if (!template || !requestIsCurrent()) return
        if (templateSignature(template) !== currentTemplateSignature) {
          reportExportIssue('模板映射已更新', '发布预检期间模板映射有变化，请核对最新映射后重新发布。')
          return
        }
      }
      stage = '发布规则包'
      const savedPackage = await saveFinalizedRulePackage(packagePayload)
      if (!requestIsCurrent()) return

      if (savedPackage.status !== 'published' || savedPackage.schema_version !== '2.0'
        || savedPackage.project_id !== requestProject || savedPackage.route_version_id !== requestRoute
        || savedPackage.content_hash !== compiled.content_hash) {
        reportExportIssue('规则包响应不一致', '服务返回的快照与本次发布的任务、路线或规则内容不一致，请刷新后重试。')
        return
      }

      const snapshot: PublishedDownload = {
        savedPackage: JSON.parse(JSON.stringify(savedPackage)),
        filename: `${safeProjectName}_${mappingEnabled ? FINALIZE_EXPORT_COPY.documentNameSuffix : '原生三表'}_v${savedPackage.version}.zip`,
        mappingEnabled,
      }
      pendingDownload = snapshot
      publishedForDownload = true
      options.onExportedVersion?.(savedPackage.version, {
        schemaVersion: savedPackage.schema_version,
        status: savedPackage.status,
      })
      if (!requestIsCurrent()) return
      stage = mappingEnabled ? '下载三文件快照' : '下载原生快照'
      await downloadSnapshot(snapshot, requestIsCurrent)
    } catch (err: any) {
      if (!requestIsCurrent()) return
      if (publishedForDownload) {
        downloadRetryAvailable.value = true
        reportExportIssue('规则包下载失败', '规则包已发布，下载未完成。点击“重试下载”下载同一版本。', err?.message || '未知下载错误')
        return
      }
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
      const status = Number(err?.response?.status) || 0
      const mappingFailure = blockers.some((item: any) => /^group_template_/.test(item?.code || ''))
      const summary = status >= 500
        ? `服务暂不可用（HTTP ${status}），请稍后重试。`
        : !err?.response
          ? '无法连接本地服务，请检查系统是否仍在运行后重试。'
          : mappingFailure
            ? '规则包尚未发布，请先完成必要的分组模板映射后再试。'
            : message
      const issues = [
        ...(Array.isArray(detail?.issues) ? detail.issues : []),
        ...(Array.isArray(detail?.rule_ids) ? detail.rule_ids : []),
        ...(Array.isArray(detail) ? detail.map(item => item?.msg || item?.message) : []),
        ...(Array.isArray(detail?.validation?.errors) ? detail.validation.errors.map((item: any) => item?.message || item) : []),
      ]
      reportExportIssue(
        '规则包发布失败',
        summary,
        [`失败步骤：${stage}${status ? `（HTTP ${status}）` : ''}`, message, blockerText, ...issues].filter(Boolean).join('\n'),
      )
    } finally {
      exportingRulePackage.value = false
    }
  }

  return {
    exportingRulePackage,
    downloadRetryAvailable,
    downloadRuleDocument,
  }
}
