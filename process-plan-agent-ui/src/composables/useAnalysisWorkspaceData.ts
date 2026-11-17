import { onScopeDispose, ref, watch } from 'vue'
import {
  getDocumentOperationDetails,
  getSavedNormalizedRoute,
  getSupersetRoute,
  listDocuments,
  listOperations,
  listProjects,
  getAnalysisGuidance,
  generateAnalysisGuidance,
  type DocumentItem,
  type DocumentOperationDetailItem,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import {
  clearStoredCurrentProjectId,
  resolveCurrentProjectId,
  setStoredCurrentProjectId,
} from '@/composables/useCurrentProject'
import { createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'

type UseAnalysisWorkspaceDataOptions = {
  getRouteProjectId: () => string | undefined
}

export function useAnalysisWorkspaceData(options: UseAnalysisWorkspaceDataOptions) {
  const loadRequestGuard = createLatestWorkflowRequestGuard()
  const loading = ref(false)
  const error = ref('')
  const projectId = ref<number | null>(null)
  const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
  const selectedSegmentId = ref('')
  const operations = ref<OperationItem[]>([])
  const supersetOperations = ref<OperationItem[]>([])
  const documents = ref<DocumentItem[]>([])
  const detailRows = ref<DocumentOperationDetailItem[]>([])
  const analysisGuidance = ref<AnalysisGuidanceConfiguration | null>(null)
  const guidanceError = ref('')
  const guidanceErrorReason = ref('')
  const guidanceGenerating = ref(false)
  const generationElapsedSeconds = ref(0)
  let routeContext = 0
  watch([savedRoute, () => savedRoute.value?.route_id, () => savedRoute.value?.workflow_revision,
    () => savedRoute.value?.analysis_locked], () => { routeContext++ }, { flush: 'sync' })
  let generationTimer: ReturnType<typeof setInterval> | undefined

  function stopGenerationTimer() {
    if (generationTimer !== undefined) clearInterval(generationTimer)
    generationTimer = undefined
  }
  onScopeDispose(() => {
    loadRequestGuard.start()
    stopGenerationTimer()
  })

  function clearLoadedWorkspace(errorMessage = '') {
    savedRoute.value = null
    selectedSegmentId.value = ''
    operations.value = []
    supersetOperations.value = []
    documents.value = []
    detailRows.value = []
    analysisGuidance.value = null
    guidanceError.value = ''
    guidanceErrorReason.value = ''
    guidanceGenerating.value = false
    generationElapsedSeconds.value = 0
    stopGenerationTimer()
    error.value = errorMessage
  }

  watch(projectId, () => {
    loadRequestGuard.start()
    clearLoadedWorkspace()
    loading.value = false
  }, { flush: 'sync' })

  async function loadSavedRoute(forceRefresh = false, retryRecommendations = false) {
    if (!projectId.value || loading.value || guidanceGenerating.value) return
    const requestedProjectId = projectId.value
    const request = loadRequestGuard.start()
    loading.value = true
    error.value = ''
    try {
      const projects = await listProjects(forceRefresh)
      if (!request.isCurrent()) return
      const current = projects.find(item => item.id === requestedProjectId)
      if (!current) {
        clearStoredCurrentProjectId()
        projectId.value = null
        clearLoadedWorkspace('当前任务已不存在，请回到路线归并页重新创建任务。')
        return
      }
      const [data, operationItems, supersetResult, documentItems, detailItems, guidance] = await Promise.all([
        getSavedNormalizedRoute(requestedProjectId, forceRefresh),
        listOperations(requestedProjectId, forceRefresh),
        getSupersetRoute(requestedProjectId, forceRefresh),
        listDocuments(requestedProjectId, forceRefresh),
        getDocumentOperationDetails(requestedProjectId, undefined, undefined, forceRefresh),
        getAnalysisGuidance(requestedProjectId),
      ])
      if (!request.isCurrent()) return
      savedRoute.value = data
      operations.value = operationItems || []
      supersetOperations.value = supersetResult.superset_route || []
      documents.value = documentItems || []
      detailRows.value = detailItems.items || []
      analysisGuidance.value = guidance.configuration
      selectedSegmentId.value = data.segments[0]?.id || ''
      // The route is already usable for inspection. Model work has its own
      // state rather than keeping the whole page behind a generic spinner.
      loading.value = false
      if (!data.analysis_locked) {
        const generationRouteContext = routeContext
        const isCurrentGeneration = () => request.isCurrent() && generationRouteContext === routeContext
        if (!retryRecommendations) analysisGuidance.value = null
        guidanceError.value = ''
        guidanceErrorReason.value = ''
        guidanceGenerating.value = true
        generationElapsedSeconds.value = 0
        const started = Date.now()
        stopGenerationTimer()
        generationTimer = setInterval(() => {
          generationElapsedSeconds.value = Math.floor((Date.now() - started) / 1000)
        }, 1000)
        try {
          const generated = await generateAnalysisGuidance(requestedProjectId, retryRecommendations)
          if (!isCurrentGeneration()) return
          if (generated.configuration?.generation_route_id != null
              && generated.configuration.generation_route_id !== data.route_id) {
            guidanceError.value = '问答与推荐所属路线已变更，请重新生成。'
            return
          }
          analysisGuidance.value = generated.configuration
        } catch (generationError: any) {
          if (!isCurrentGeneration()) return
          const detail = generationError?.response?.data?.detail
          if (detail?.code === 'analysis_locked') {
            const [latestRoute, latestGuidance] = await Promise.all([getSavedNormalizedRoute(requestedProjectId, true), getAnalysisGuidance(requestedProjectId)])
            if (!isCurrentGeneration()) return
            savedRoute.value = latestRoute
            analysisGuidance.value = latestGuidance.configuration
            return
          }
          guidanceError.value = (typeof detail === 'string' ? detail : detail?.message) || '问答生成未完成，请重试。已有回答会保留。'
          guidanceErrorReason.value = typeof detail?.reason === 'string' ? detail.reason.slice(0, 1200)
            : generationError?.code === 'ECONNABORTED' ? '等待模型响应超时，请稍后重试。'
            : !generationError?.response ? '暂时无法连接服务，请检查服务是否运行后重试。' : ''
        } finally {
          // Cache invalidation discards data, but the latest request still owns
          // its busy state and timer until a project switch or newer load.
          if (request.isLatest()) {
            stopGenerationTimer()
            generationElapsedSeconds.value = Math.floor((Date.now() - started) / 1000)
            guidanceGenerating.value = false
          }
        }
      }
    } catch (e: any) {
      if (!request.isCurrent()) return
      console.error('加载已保存标准化路线失败', e)
      clearLoadedWorkspace(e?.response?.data?.detail || '加载已保存标准化路线失败，请先回到路线归并页保存一版结果。')
    } finally {
      if (!request.isLatest()) return
      loading.value = false
    }
  }

  function resolveProjectId() {
    const nextId = Number(resolveCurrentProjectId(options.getRouteProjectId()))
    projectId.value = nextId > 0 ? nextId : null
    if (projectId.value) {
      setStoredCurrentProjectId(projectId.value)
    }
  }

  return {
    loading,
    error,
    projectId,
    savedRoute,
    selectedSegmentId,
    operations,
    supersetOperations,
    documents,
    detailRows,
    analysisGuidance,
    guidanceError,
    guidanceErrorReason,
    guidanceGenerating,
    generationElapsedSeconds,
    loadSavedRoute,
    resolveProjectId,
  }
}
