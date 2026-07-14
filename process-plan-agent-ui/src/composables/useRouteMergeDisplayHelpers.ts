import type { ComputedRef } from 'vue'
import type { OperationItem } from '@/api'
import type { MergeGroupStatus, RouteMergeGroup, RouteMergePreviewItem } from '@/composables/useRouteMergeResultWorkspace'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'

type UseRouteMergeDisplayHelpersOptions = {
  routeFullSetOperations: ComputedRef<OperationItem[]>
  routeFullSetDisplayOperations: ComputedRef<OperationItem[]>
  routeMergeCandidateGroups: ComputedRef<RouteMergeGroup[]>
}

export type RouteMergePreviewStepGroup = {
  key: string
  name: string
  stepItems: string[]
  attachedStepItems: string[]
}

export function useRouteMergeDisplayHelpers(options: UseRouteMergeDisplayHelpersOptions) {
  function normalizeStepItems(value: unknown) {
    const unique = new Set<string>()
    const normalized: string[] = []
    ;(Array.isArray(value) ? value : []).forEach((item) => {
      const text = String(item || '').trim()
      if (!text || unique.has(text)) return
      unique.add(text)
      normalized.push(text)
    })
    return normalized
  }

  function mergeSuggestionForGroup(group: RouteMergeGroup) {
    const label = String(group.recommendation_label || '').trim()
    const reason = String(group.recommendation_reason || '').trim()
    const targetName = formatRouteDisplayName(String(group.recommended_target_name || group.standard_name || '').trim())
    const suggestionType = String(group.suggestion_type || '').trim()

    if (label && reason) {
      if (suggestionType === 'absorb_into_parent' && targetName) {
        return `推荐类型：${label}。建议并入「${targetName}」；${reason}`
      }
      return `推荐类型：${label}。${reason}`
    }
    if (label) {
      return targetName ? `推荐类型：${label}，目标工序：${targetName}` : `推荐类型：${label}`
    }
    if (suggestionType === 'direct_merge') {
      return '推荐类型：直接归并。加工意图一致，只是命名口径不同。'
    }
    if (suggestionType === 'absorb_into_parent') {
      return targetName
        ? `推荐类型：并入上位工序。该独立工序更像前序主工序中的局部内容，建议并入「${targetName}」。`
        : '推荐类型：并入上位工序。该独立工序更像前序主工序中的局部内容。'
    }
    if (suggestionType === 'keep_separate') {
      return '推荐类型：不建议归并。方法、对象或精度层级存在差异，应保持独立。'
    }
    if (group.standard_name) return `请结合来源工序与工步内容判断是否保留当前组合工序「${formatRouteDisplayName(group.standard_name)}」。`
    return '请结合工序和工步内容判断这组工序是否需要归并。'
  }

  function equipmentSupportLabel(result?: string) {
    if (result === 'support') return '设备支持当前细分'
    if (result === 'caution') return '设备提示需谨慎确认'
    return '设备仅作补充证据'
  }

  function mergeGroupCandidateLabel(group: RouteMergeGroup) {
    const sourceLabel = mergeGroupSourceLabel(group)
    const standardName = formatRouteDisplayName(group.standard_name || '')
    if (standardName) return standardName
    return sourceLabel
  }

  function mergeGroupSourceLabel(group: RouteMergeGroup) {
    const members = options.routeFullSetOperations.value
      .filter(item => group.operation_ids.includes(item.id))
      .sort((a, b) => a.sequence - b.sequence || a.id - b.id)
      .map(item => formatRouteDisplayName(item.name))
    const labels = members.length ? members : (group.standard_name ? [formatRouteDisplayName(group.standard_name)] : [])
    return labels.join(' / ')
  }

  function mergeGroupIdForOperation(operationId: number) {
    return options.routeMergeCandidateGroups.value.find(group => group.operation_ids.includes(operationId))?.id || ''
  }

  function mergeGroupStatusLabel(status: MergeGroupStatus) {
    if (status === 'merged') return '已归并'
    if (status === 'kept') return '保持独立'
    if (status === 'conflict') return '待定'
    return '待归并'
  }

  function mergeGroupTagClass(status: MergeGroupStatus) {
    if (status === 'merged') return 'tag-success'
    if (status === 'kept') return 'tag-neutral'
    if (status === 'conflict') return 'tag-danger'
    return 'tag-warning'
  }

  function previewItemStepGroups(item: Pick<RouteMergePreviewItem, 'operationIds'> | null | undefined): RouteMergePreviewStepGroup[] {
    const targetIds = new Set((item?.operationIds || []).map(id => Number(id)).filter(Boolean))
    if (!targetIds.size) return []

    return options.routeFullSetDisplayOperations.value
      .filter((operation) => {
        const sourceOperationId = Number((operation as any).source_operation_id || operation.id || 0)
        return sourceOperationId > 0 && targetIds.has(sourceOperationId)
      })
      .map((operation) => ({
        key: String((operation as any).display_key || (operation as any).source_operation_id || operation.id || `${operation.name}`),
        name: formatRouteDisplayName(String(operation.name || '未命名工序')),
        stepItems: normalizeStepItems(operation.step_items),
        attachedStepItems: normalizeStepItems(operation.attached_step_items),
      }))
      .filter(group => group.stepItems.length > 0 || group.attachedStepItems.length > 0)
  }

  return {
    mergeSuggestionForGroup,
    equipmentSupportLabel,
    mergeGroupCandidateLabel,
    mergeGroupSourceLabel,
    mergeGroupIdForOperation,
    mergeGroupStatusLabel,
    mergeGroupTagClass,
    previewItemStepGroups,
  }
}
