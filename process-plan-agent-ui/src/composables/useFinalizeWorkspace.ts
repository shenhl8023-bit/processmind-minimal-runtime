import { computed, nextTick, ref } from 'vue'
import {
  getSavedNormalizedRoute,
  getSupersetRoute,
  listOperations,
  listProjects,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  getConditionFieldRegistry,
  getFinalizedRulePackageStatus,
  type CanonicalConditionField,
  type RulePackageStatusResponse,
  type StandardFactorDefinition,
} from '@/api/rulePackages'
import { FINALIZE_VIEW_COPY } from '@/config/finalizeRulePresentation'
import { resolveAvailableProjectId } from '@/composables/useCurrentProject'
import {
  createLatestWorkflowRequestGuard,
  getWorkflowDataRevision,
} from '@/composables/workflowDataCache'

export type FinalizeWorkspaceOptions = {
  requestedProjectId: () => string
  onProjectResolved?: (projectId: string) => void | Promise<void>
  readDrafts?: () => void
  onRouteLoaded?: (route: SavedNormalizedRouteVersionResult) => void
}

function errorDetail(error: unknown) {
  const response = (error as { response?: { data?: { detail?: unknown } } } | null)?.response
  const detail = response?.data?.detail
  if (typeof detail === 'string') return detail
  if (detail && typeof detail === 'object' && 'message' in detail) {
    return String((detail as { message?: unknown }).message || '')
  }
  return ''
}

export function useFinalizeWorkspace(options: FinalizeWorkspaceOptions) {
  const loading = ref(false)
  const error = ref('')
  const workspaceErrorTitle = ref<string>(FINALIZE_VIEW_COPY.errorTitle)
  const projectId = ref<number | null>(null)
  const projectName = ref('')
  const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
  const operations = ref<OperationItem[]>([])
  const supersetOperations = ref<OperationItem[]>([])
  const rulePackageStatus = ref<RulePackageStatusResponse | null>(null)
  const currentPublishedPackage = ref<RulePackageStatusResponse['latest_package']>(null)
  const outdatedRulePackageVersion = ref<number | null>(null)
  const conditionFields = ref<CanonicalConditionField[]>([])
  const standardFactors = ref<StandardFactorDefinition[]>([])
  const factorCatalogVersion = ref('')
  const factorCatalogError = ref('')
  const conditionRegistryLoading = ref(false)
  const loadedDataRevision = ref(-1)
  const workspaceRequestGuard = createLatestWorkflowRequestGuard()
  let rulePackageStatusRequestId = 0

  const factorCatalogReady = computed(() => Boolean(
    conditionFields.value.length
    && standardFactors.value.length
    && factorCatalogVersion.value,
  ))

  function clearConditionRegistry(message = '') {
    conditionFields.value = []
    standardFactors.value = []
    factorCatalogVersion.value = ''
    factorCatalogError.value = message
  }

  function applyConditionRegistry(registry: Awaited<ReturnType<typeof getConditionFieldRegistry>>) {
    conditionFields.value = registry.fields || []
    standardFactors.value = registry.factors || []
    factorCatalogVersion.value = registry.version || ''
    factorCatalogError.value = factorCatalogReady.value
      ? ''
      : '标准字段与因子目录不完整，请重试加载。'
  }

  async function retryConditionRegistry() {
    if (conditionRegistryLoading.value) return
    conditionRegistryLoading.value = true
    try {
      applyConditionRegistry(await getConditionFieldRegistry())
    } catch (registryError: unknown) {
      console.error('第四步标准因子目录加载失败', registryError)
      clearConditionRegistry(
        errorDetail(registryError) || '标准因子目录加载失败，请重试后再审核或发布。',
      )
    } finally {
      conditionRegistryLoading.value = false
    }
  }

  function clearWorkspaceState() {
    projectId.value = null
    projectName.value = ''
    savedRoute.value = null
    operations.value = []
    supersetOperations.value = []
    rulePackageStatus.value = null
    currentPublishedPackage.value = null
    outdatedRulePackageVersion.value = null
    clearConditionRegistry()
  }

  function markPublishedRulePackageOutdated() {
    if (currentPublishedPackage.value?.version) {
      outdatedRulePackageVersion.value = currentPublishedPackage.value.version
    }
    currentPublishedPackage.value = null
  }

  function applyRulePackageStatus(status: RulePackageStatusResponse) {
    rulePackageStatus.value = status
    currentPublishedPackage.value = status.package_executable
      && status.latest_package?.status === 'published'
      ? status.latest_package
      : null
    outdatedRulePackageVersion.value = status.latest_package
      && !status.package_executable
      ? status.latest_package.version
      : null
  }

  async function refreshRulePackageStatus() {
    const targetProjectId = projectId.value
    if (!targetProjectId) return
    const requestId = ++rulePackageStatusRequestId
    try {
      const status = await getFinalizedRulePackageStatus(targetProjectId)
      if (requestId !== rulePackageStatusRequestId || projectId.value !== targetProjectId) return
      applyRulePackageStatus(status)
    } catch (statusError: unknown) {
      if (requestId !== rulePackageStatusRequestId || projectId.value !== targetProjectId) return
      console.error('第四步规则包状态刷新失败', statusError)
      rulePackageStatus.value = null
      currentPublishedPackage.value = null
    }
  }

  async function loadWorkspace(forceRefresh = false) {
    const request = workspaceRequestGuard.start()
    const statusRequestId = ++rulePackageStatusRequestId
    loading.value = true
    error.value = ''
    workspaceErrorTitle.value = FINALIZE_VIEW_COPY.errorTitle
    try {
      const projectList = await listProjects(forceRefresh)
      if (!request.isCurrent()) return
      const resolvedProjectId = resolveAvailableProjectId(options.requestedProjectId(), projectList)
      if (!resolvedProjectId) {
        clearWorkspaceState()
        error.value = ''
        return
      }

      projectId.value = Number(resolvedProjectId)
      if (String(options.requestedProjectId() || '') !== resolvedProjectId) {
        void options.onProjectResolved?.(resolvedProjectId)
      }
      const currentProject = projectList.find(project => Number(project.id) === projectId.value)
      projectName.value = currentProject?.name || `任务 #${projectId.value}`
      const [routeResult, operationList, supersetResult, statusResult, fieldRegistryResult] = await Promise.all([
        getSavedNormalizedRoute(projectId.value, forceRefresh),
        listOperations(projectId.value, forceRefresh),
        getSupersetRoute(projectId.value, forceRefresh),
        getFinalizedRulePackageStatus(projectId.value),
        getConditionFieldRegistry()
          .then(registry => ({ registry, error: null as unknown }))
          .catch(registryError => ({ registry: null, error: registryError as unknown })),
      ])
      if (!request.isCurrent()) return

      savedRoute.value = routeResult
      operations.value = operationList
      supersetOperations.value = supersetResult.superset_route || []
      if (statusRequestId === rulePackageStatusRequestId) {
        applyRulePackageStatus(statusResult)
      }
      if (fieldRegistryResult.registry) {
        applyConditionRegistry(fieldRegistryResult.registry)
      } else {
        console.error('第四步标准因子目录加载失败', fieldRegistryResult.error)
        clearConditionRegistry(
          errorDetail(fieldRegistryResult.error)
            || '标准因子目录加载失败；现有编辑已保留，请重试加载后再审核或发布。',
        )
      }
      options.readDrafts?.()
      options.onRouteLoaded?.(routeResult)
      await nextTick()
    } catch (loadError: unknown) {
      if (!request.isCurrent()) return
      const status = Number((loadError as { response?: { status?: unknown } } | null)?.response?.status)
      if (status !== 404) console.error(loadError)
      savedRoute.value = null
      operations.value = []
      supersetOperations.value = []
      rulePackageStatus.value = null
      currentPublishedPackage.value = null
      outdatedRulePackageVersion.value = null
      clearConditionRegistry()
      workspaceErrorTitle.value = status === 404
        ? '当前任务尚未完成第三步保存'
        : FINALIZE_VIEW_COPY.errorTitle
      error.value = errorDetail(loadError)
        || (status === 404
          ? '当前任务还没有第三步可预览的已保存结果，请先回到第三步完成分析。'
          : '第四步工作台或规则包状态加载失败，请重试。')
    } finally {
      if (!request.isLatest()) return
      loading.value = false
      loadedDataRevision.value = getWorkflowDataRevision()
    }
  }

  return {
    loading,
    error,
    workspaceErrorTitle,
    projectId,
    projectName,
    savedRoute,
    operations,
    supersetOperations,
    rulePackageStatus,
    currentPublishedPackage,
    outdatedRulePackageVersion,
    conditionFields,
    standardFactors,
    factorCatalogVersion,
    factorCatalogError,
    conditionRegistryLoading,
    factorCatalogReady,
    loadedDataRevision,
    clearConditionRegistry,
    applyConditionRegistry,
    retryConditionRegistry,
    markPublishedRulePackageOutdated,
    refreshRulePackageStatus,
    loadWorkspace,
  }
}
