import { ref } from 'vue'
import {
  getDocumentOperationDetails,
  getSavedNormalizedRoute,
  getSupersetRoute,
  listDocuments,
  listOperations,
  listProjects,
  type DocumentItem,
  type DocumentOperationDetailItem,
  type OperationItem,
  type SavedNormalizedRouteVersionResult,
} from '@/api'
import {
  clearStoredCurrentProjectId,
  resolveCurrentProjectId,
  setStoredCurrentProjectId,
} from '@/composables/useCurrentProject'

type UseAnalysisWorkspaceDataOptions = {
  getRouteProjectId: () => string | undefined
}

export function useAnalysisWorkspaceData(options: UseAnalysisWorkspaceDataOptions) {
  const loading = ref(false)
  const error = ref('')
  const projectId = ref<number | null>(null)
  const savedRoute = ref<SavedNormalizedRouteVersionResult | null>(null)
  const selectedSegmentId = ref('')
  const operations = ref<OperationItem[]>([])
  const supersetOperations = ref<OperationItem[]>([])
  const documents = ref<DocumentItem[]>([])
  const detailRows = ref<DocumentOperationDetailItem[]>([])

  function clearLoadedWorkspace(errorMessage = '') {
    savedRoute.value = null
    selectedSegmentId.value = ''
    operations.value = []
    supersetOperations.value = []
    documents.value = []
    detailRows.value = []
    error.value = errorMessage
  }

  async function loadSavedRoute() {
    if (!projectId.value) return
    loading.value = true
    error.value = ''
    try {
      const projects = await listProjects()
      const current = projects.find(item => item.id === projectId.value)
      if (!current) {
        clearStoredCurrentProjectId()
        projectId.value = null
        clearLoadedWorkspace('当前任务已不存在，请回到路线归并页重新创建任务。')
        return
      }
      const [data, operationItems, supersetResult, documentItems, detailItems] = await Promise.all([
        getSavedNormalizedRoute(projectId.value),
        listOperations(projectId.value),
        getSupersetRoute(projectId.value),
        listDocuments(projectId.value),
        getDocumentOperationDetails(projectId.value),
      ])
      savedRoute.value = data
      operations.value = operationItems || []
      supersetOperations.value = supersetResult.superset_route || []
      documents.value = documentItems || []
      detailRows.value = detailItems.items || []
      selectedSegmentId.value = data.segments[0]?.id || ''
    } catch (e: any) {
      console.error('加载已保存标准化路线失败', e)
      clearLoadedWorkspace(e?.response?.data?.detail || '加载已保存标准化路线失败，请先回到路线归并页保存一版结果。')
    } finally {
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
    loadSavedRoute,
    resolveProjectId,
  }
}
