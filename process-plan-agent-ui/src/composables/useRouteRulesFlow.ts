import { computed, ref, type Ref } from 'vue'
import {
  getExtractTaskStatus,
  startExtraction as apiStartExtraction,
  type ExtractionTaskStatus,
  type MergeSuggestion,
  type OperationItem,
} from '@/api'
import type { RouteMergeGroup } from '@/composables/useRouteMergeResultWorkspace'
import { clearProjectQuestionTreeStorage } from '@/composables/analysisQuestionTreeState'

type UseRouteRulesFlowOptions = {
  projectId: Ref<number | null>
  routeWorkspaceLoading: Ref<boolean>
  routes: Ref<OperationItem[]>
  routeMergeGroups: Ref<RouteMergeGroup[]>
  routeMergeSuggestions: Ref<MergeSuggestion[]>
  routeMergeNormalizedSegments: Ref<any[]>
  selectedMergeGroupId: Ref<string>
  routeMergeNotice: Ref<string>
  loadRouteMergeWorkspaceFromBackend: (syncPreviewDraft?: boolean, forceRefresh?: boolean) => Promise<boolean>
  clearRouteResultDraftStorage: () => void
  clearPreviewHighlight: () => void
}

export function useRouteRulesFlow(options: UseRouteRulesFlowOptions) {
  const status = ref<'idle' | 'loading' | 'done' | 'error'>('idle')
  const errorMsg = ref('')
  const extractTask = ref<ExtractionTaskStatus | null>(null)

  let extractTaskPollTimer: number | null = null
  let extractTaskPollRetryCount = 0

  const extractTaskProgress = computed(() => Number(extractTask.value?.progress || 0))
  const extractTaskMessage = computed(() => extractTask.value?.message || '')
  const extractHarness = computed(() => extractTask.value?.harness || null)
  const extractIdleHint = computed(() => '点击开始提炼，系统将整理上传文档中的工序、证据与标准化母路线。')
  const extractLoadingHint = computed(() => '系统正在后台整理工序、母路线与保存结果，请稍候...')
  const extractTaskStageTitle = computed(() => {
    const stage = extractTask.value?.stage || 'queued'
    const message = extractTask.value?.message || ''
    if (stage === 'loading_route_merge') return '正在装载路线归并结果...'
    if (stage === 'extracting_operations') {
      if (message.includes('工序明细')) {
        return message.includes('复用') ? '正在复用工序明细...' : '正在解析工序明细...'
      }
      if (message.includes('汇总')) return '正在汇总工艺路线全集...'
      if (message.includes('保存')) return '正在保存工艺路线全集...'
      return '正在提取工艺路线全集...'
    }
    if (stage === 'route_set_ready') return '工艺路线全集已生成'
    if (stage === 'completed') return '工艺路线全集已生成'
    return 'AI 正在分析文档...'
  })
  const routeProgressSteps = computed(() => {
    const loadingMerge = options.routeWorkspaceLoading.value || extractTask.value?.stage === 'loading_route_merge'
    const extractDone = loadingMerge || extractTaskProgress.value >= 100 || extractTask.value?.stage === 'route_set_ready'
    return [
      {
        key: 'extract',
        title: '提取工艺路线全集',
        description: extractDone ? '已完成' : '正在整理原始工序与证据',
        status: extractDone ? 'done' : 'active',
      },
      {
        key: 'merge',
        title: '装载路线归并结果',
        description: loadingMerge ? '正在生成归并候选与标准母路线' : '等待全集提取完成',
        status: loadingMerge ? 'active' : extractDone ? 'pending' : 'pending',
      },
    ]
  })

  function resetRouteRulesError() {
    errorMsg.value = ''
    status.value = 'idle'
  }

  function stopExtractTaskPolling() {
    if (extractTaskPollTimer !== null) {
      window.clearTimeout(extractTaskPollTimer)
      extractTaskPollTimer = null
    }
    options.clearPreviewHighlight()
  }

  async function loadRouteRulesResults(forceRefresh = false) {
    if (!options.projectId.value) return
    options.routeWorkspaceLoading.value = true
    status.value = 'done'
    extractTask.value = {
      ...(extractTask.value || {
        project_id: options.projectId.value,
        task_status: 'completed',
        stage: 'route_set_ready',
        message: '工艺路线全集已生成，正在加载路线归并结果...',
        progress: 100,
        error: null,
        started_at: null,
        updated_at: null,
        finished_at: null,
        project_status: 'ROUTE_SET_READY',
      }),
      task_status: 'completed',
      stage: 'loading_route_merge',
      message: '工艺路线全集已生成，正在加载路线归并结果...',
      progress: 100,
      error: null,
    }
    try {
      const loaded = await options.loadRouteMergeWorkspaceFromBackend(true, forceRefresh)
      if (!loaded) throw new Error('路线归并工作台加载失败，请刷新后重试。')
      extractTask.value = null
    } catch (e: any) {
      console.error('加载路线归并结果失败', e)
      errorMsg.value = e?.response?.data?.detail || e?.message || '加载路线归并结果失败'
      status.value = 'error'
    } finally {
      options.routeWorkspaceLoading.value = false
    }
  }

  async function pollExtractionTask() {
    if (!options.projectId.value) return
    try {
      const task = await getExtractTaskStatus(options.projectId.value)
      extractTaskPollRetryCount = 0
      extractTask.value = task
      if (task.task_status === 'completed') {
        stopExtractTaskPolling()
        await loadRouteRulesResults()
        return
      }
      if (task.task_status === 'failed') {
        if (String(task.project_status || '') === 'ROUTE_SET_READY') {
          stopExtractTaskPolling()
          await loadRouteRulesResults()
          return
        }
        stopExtractTaskPolling()
        errorMsg.value = task.error || task.message || '提炼失败'
        status.value = 'error'
        return
      }
      status.value = 'loading'
      stopExtractTaskPolling()
      extractTaskPollTimer = window.setTimeout(() => {
        void pollExtractionTask()
      }, 2000)
    } catch (e: any) {
      extractTaskPollRetryCount += 1
      if (extractTaskPollRetryCount <= 3) {
        status.value = 'loading'
        stopExtractTaskPolling()
        extractTaskPollTimer = window.setTimeout(() => {
          void pollExtractionTask()
        }, 1500)
        return
      }
      stopExtractTaskPolling()
      errorMsg.value = e?.response?.data?.detail || e?.message || '获取提炼进度失败'
      status.value = 'error'
    }
  }

  async function startExtraction(forceReextract: boolean = false) {
    if (status.value === 'loading') return
    if (!options.projectId.value) return
    clearProjectQuestionTreeStorage(options.projectId.value)
    status.value = 'loading'
    extractTaskPollRetryCount = 0
    options.routes.value = []
    options.routeMergeGroups.value = []
    options.routeMergeSuggestions.value = []
    options.routeMergeNormalizedSegments.value = []
    options.selectedMergeGroupId.value = ''
    options.routeMergeNotice.value = ''
    options.routeWorkspaceLoading.value = false
    options.clearRouteResultDraftStorage()
    extractTask.value = null
    errorMsg.value = ''
    try {
      const task = await apiStartExtraction(options.projectId.value, forceReextract)
      extractTask.value = {
        project_id: task.project_id,
        task_status: 'running',
        stage: task.stage,
        message: task.message,
        progress: 5,
        error: null,
        started_at: null,
        updated_at: null,
        finished_at: null,
        project_status: null,
      }
      await pollExtractionTask()
    } catch (e: any) {
      errorMsg.value = e?.response?.data?.detail || e?.message || '提取失败'
      status.value = 'error'
    }
  }

  return {
    status,
    errorMsg,
    extractTask,
    extractHarness,
    extractTaskProgress,
    extractTaskMessage,
    extractIdleHint,
    extractLoadingHint,
    extractTaskStageTitle,
    routeProgressSteps,
    resetRouteRulesError,
    stopExtractTaskPolling,
    loadRouteRulesResults,
    pollExtractionTask,
    startExtraction,
  }
}
