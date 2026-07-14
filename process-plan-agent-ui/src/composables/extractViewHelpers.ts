import type {
  MergeSuggestion,
  OperationItem,
} from '@/api'
import type {
  MergeGroupStatus,
  RouteMergeGroup,
} from '@/composables/useRouteMergeResultWorkspace'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'

type RouteStageMeta = {
  key: string
  title: string
  kicker: string
  description: string
  order: number
}

const ROUTE_FULL_SET_MAIN_MAX_SEQUENCE = 160
const DISPLAY_COMPOSITE_SPLIT_PATTERN = /[、,，/／]+/

export function reviewStatusClass(status?: string | null) {
  return `status-${status || 'pending_confirm'}`
}

export function reviewTagClass(status?: string | null) {
  const normalized = status || 'pending_confirm'
  if (normalized === 'stable') return 'tag-badge-stable'
  if (normalized === 'exception') return 'tag-badge-exception'
  if (normalized === 'evidence') return 'tag-badge-evidence'
  if (normalized === 'data_issue') return 'tag-badge-data'
  return 'tag-badge-pending'
}

export function formatSampleCoverage(hitCount?: number | null, totalCount?: number | null) {
  const hit = Number(hitCount || 0)
  const total = Number(totalCount || 0)
  if (total > 0) return `${hit}/${total}`
  if (hit > 0) return `${hit}`
  return ''
}

export function normalizeOperationName(name?: string | null) {
  return (name || '')
    .replace(/（.*?）/g, '')
    .trim()
}

export function routeOperationDisplayName(operation: Record<string, any>) {
  return formatRouteDisplayName(String(operation.name || ''))
}

export function buildRouteOperationNameCounts(operations: Array<Record<string, any>>) {
  const counts = new Map<string, number>()
  operations.forEach((item) => {
    const normalized = normalizeOperationName(String(item.name || ''))
    if (!normalized) return
    counts.set(normalized, (counts.get(normalized) || 0) + 1)
  })
  return counts
}

export function routeOperationDuplicateLabel(
  operation: Record<string, any>,
  operationNameCounts: Map<string, number>,
) {
  const normalized = normalizeOperationName(String(operation.name || ''))
  const count = operationNameCounts.get(normalized) || 0
  if (count <= 1) return ''
  return `重复阶段工序 ×${count}`
}

export function filterRouteMergeNotice(notice?: string | null) {
  const text = String(notice || '').trim()
  if (!text) return ''
  if (
    text.startsWith('已确认将「')
    || text.startsWith('已确认「')
    || text === '已按系统建议完成全部合并。'
    || text === '已将全部候选归并组设为不合并。'
  ) {
    return ''
  }
  return text
}

export function resolveRouteMergeStageMeta(group: RouteMergeGroup): RouteStageMeta {
  const seq = Number(group.sequence || 0)
  const phase = group.phase || ''
  const name = group.standard_name || ''
  const isChamferName = ['倒角', '倒圆', '孔口倒角', '车倒角'].some(token => name.includes(token))

  if (seq <= 20 || name === '下料' || name === '调质/正常化') {
    return {
      key: 'prep',
      title: '预备阶段',
      kicker: '准备',
      description: '毛坯准备与预备热处理在这里收拢，作为整条路线的起点。',
      order: 10,
    }
  }

  if (isChamferName) {
    return {
      key: 'rough_support',
      title: '粗加工辅助阶段',
      kicker: '辅助检验',
      description: '倒角、倒圆这类前段边缘修整通常紧跟粗加工主链出现，优先归到粗加工辅助语义里查看。',
      order: 30,
    }
  }

  if (phase === 'rough' || phase === 'rough_to_finish' || phase === 'mixed') {
    return {
      key: 'rough_process',
      title: '粗加工阶段',
      kicker: '粗加工',
      description: '主加工外形、基准与孔系通常先在这一段展开，决定后续热处理与精整基础。',
      order: 20,
    }
  }

  if ((phase === 'auxiliary' || phase === 'inspection') && seq < 100) {
    return {
      key: 'rough_support',
      title: '粗加工辅助阶段',
      kicker: '辅助检验',
      description: '粗加工后的去毛刺、清洗和中间检验会集中出现在这里，用来承接下一段加工。',
      order: 30,
    }
  }

  if (phase === 'heat_treatment' || phase === 'surface_or_heat_treatment') {
    return {
      key: 'heat_stage',
      title: '热处理阶段',
      kicker: '热处理',
      description: '中间处理与终热处理在这里单列，避免和前后加工段误并。',
      order: 40,
    }
  }

  if (phase === 'semi_finish_or_finish' || phase === 'finish') {
    return {
      key: 'finish_stage',
      title: '精整阶段',
      kicker: '精整',
      description: '磨削、研磨、珩磨等精整工序在这里展开，对最终尺寸与表面质量负责。',
      order: 50,
    }
  }

  if (phase === 'inspection') {
    return {
      key: 'final_inspection',
      title: '终检阶段',
      kicker: '终检',
      description: '烧伤检查、磁粉检查、裂纹检查、荧光检查等终检工序在这里集中出现。',
      order: 60,
    }
  }

  if (phase === 'release' || name === '标印' || name === '标记' || name === '包装') {
    return {
      key: 'release_tail',
      title: '收尾放行阶段',
      kicker: '收尾',
      description: '末次清洗、标印与包装在这里收尾。包装通常位于收尾放行尾段，若文档明确存在更后的放行节点，则以文档顺序为准。',
      order: 70,
    }
  }

  return {
    key: 'other_stage',
    title: '其他阶段',
    kicker: '其他',
    description: '当前节点暂未命中标准阶段规则，先暂放在兜底分组中。',
    order: 90,
  }
}

export function resolveRouteFullSetStageMeta(operation: OperationItem): RouteStageMeta {
  const description = String(operation.description || '')
  const normalizedName = normalizeOperationName(operation.name)
  const sequence = Number(operation.sequence || 0)
  const isPrepMaterialName = ['备料', '下料'].includes(normalizedName)
  const isPrepHeatName = ['正常化', '调质'].includes(normalizedName)
  const isSurfaceTreatmentName = ['镀铜', '除铜', '铬酸阳极化', '硬质阳极化', '钝化'].includes(normalizedName)
  const isSpecialLateProcessName = ['打孔', '打型孔'].includes(normalizedName)
  const isTurningShapeName = ['车零件', '车外形', '车外圆', '车端面', '平端面'].includes(normalizedName)
  const isFeatureProcessName = ['钻孔', '镗孔', '钻镗孔', '钻铰孔', '铰孔', '攻螺纹', '铣扁', '铣槽', '车槽', '割型孔', '割扁'].includes(normalizedName)
  const isFinishName = ['磨外圆', '磨孔', '磨端面', '磨槽', '研孔', '研顶尖孔', '研顶尖', '研外圆', '珩孔'].includes(normalizedName)
  const isFinalInspectionName = ['烧伤检查', '磁粉检查', '裂纹检查', '荧光检查'].includes(normalizedName)
  const familyKey = inferMergeFamilyKey(normalizedName)
  const isSingleTransitSupport = familyKey === 'release'
    && normalizedName !== '包装'
    && !description.includes('前段槽位')
    && !description.includes('中段槽位')
    && !description.includes('终段槽位')

  if (isPrepMaterialName) {
    return {
      key: 'prep_stage',
      title: '预备阶段',
      kicker: '准备',
      description: '备料与下料等毛坯准备工序在这里收拢，作为整条路线的起点。',
      order: 10,
    }
  }

  if (description.includes('前段槽位')) {
    return {
      key: 'support_front',
      title: '前段辅助阶段',
      kicker: '前段辅助',
      description: '这里放前段重复辅助工序，通常承接粗加工或基准建立后的去毛刺、清洗与中间检验。',
      order: 22,
    }
  }

  if (description.includes('中段槽位')) {
    return {
      key: 'support_middle',
      title: '中段辅助阶段',
      kicker: '中段辅助',
      description: '这里放中段重复辅助工序，通常对应中间处理、热处理前后或精整前的周转与检验。',
      order: 45,
    }
  }

  if (description.includes('终段槽位')) {
    if (normalizedName.includes('包装')) {
      return {
        key: 'release_tail',
        title: '收尾放行阶段',
        kicker: '收尾',
        description: '末次清洗、标印与包装在这里收尾。包装通常位于收尾放行尾段，若文档明确存在更后的放行节点，则以文档顺序为准。',
        order: 65,
      }
    }
    return {
      key: 'support_final',
      title: '终段辅助阶段',
      kicker: '终段辅助',
      description: '这里放终段重复辅助工序，通常对应终检前后的去毛刺、清洗与终检。',
      order: 65,
    }
  }

  if (isPrepHeatName) {
    return {
      key: 'prep_heat_stage',
      title: '预备热处理阶段',
      kicker: '预热处理',
      description: '正常化与调质等前置热处理在这里集中展开，通常位于毛坯准备之后、主加工之前。',
      order: 15,
    }
  }

  if (isSurfaceTreatmentName) {
    return {
      key: 'surface_stage',
      title: '表面处理阶段',
      kicker: '表面处理',
      description: '阳极化、镀铜、除铜等表面处理工序在这里单列，避免误并到粗加工主链中。',
      order: 42,
    }
  }

  if (isSpecialLateProcessName) {
    return {
      key: 'special_late_stage',
      title: '后段特种加工阶段',
      kicker: '特种加工',
      description: '电火花穿孔、成型等后段特种加工工序在这里单列，避免误标为粗加工。',
      order: 48,
    }
  }

  if (isTurningShapeName) {
    return {
      key: 'turning_shape_stage',
      title: '车削成形段',
      kicker: '车削成形',
      description: '车零件、车外形、车外圆与端面建立等主体成形工序在这里集中展开，通常为后续特征加工提供基准。',
      order: 20,
    }
  }

  if (isFeatureProcessName) {
    return {
      key: 'feature_process_stage',
      title: '特征加工段',
      kicker: '特征加工',
      description: '孔系、槽类与扁位等局部特征加工在这里集中出现，通常承接车削成形后的主体基准继续展开。',
      order: 35,
    }
  }

  if (isFinishName) {
    return {
      key: 'finish_stage',
      title: '精整阶段',
      kicker: '精整',
      description: '磨削、研磨、珩磨等精整工序在这里展开，对最终尺寸与表面质量负责。',
      order: 50,
    }
  }

  if (isFinalInspectionName) {
    return {
      key: 'final_inspection',
      title: '终检阶段',
      kicker: '终检',
      description: '烧伤检查、磁粉检查、裂纹检查、荧光检查等终检工序在这里集中出现。',
      order: 60,
    }
  }

  if (isSingleTransitSupport) {
    if (sequence >= 450) {
      return {
        key: 'support_final',
        title: '终段辅助阶段',
        kicker: '终段辅助',
        description: '单次出现的辅助工序如果实际顺序已经接近尾段，则仍归到终段辅助查看。',
        order: 65,
      }
    }
    return {
      key: 'support_transit',
      title: '流转辅助阶段',
      kicker: '中段辅助',
      description: '单次出现的辅助工序按真实顺序落在主体加工之后、终检放行之前，避免被一律压到收尾阶段。',
      order: 38,
    }
  }

  const pseudoGroup: RouteMergeGroup = {
    id: `op-${operation.id}`,
    sequence,
    standard_name: normalizedName || '未命名工序段',
    operation_ids: [operation.id],
    status: 'pending',
    coverageLabel: formatSampleCoverage(operation.coverage_count, operation.sample_count),
    phase: (
      familyKey === 'heat' ? 'heat_treatment'
        : familyKey === 'surface' ? 'surface_or_heat_treatment'
          : familyKey === 'inspection' ? 'inspection'
            : familyKey === 'release' ? 'auxiliary'
              : ['shape', 'hole', 'feature'].includes(familyKey) ? 'rough' : 'rough'
    ),
    step_family: familyKey,
  }
  return resolveRouteMergeStageMeta(pseudoGroup)
}

export function isMergeGroupActionable(group?: RouteMergeGroup | null) {
  if (!group) return false
  if (group.operation_ids.length <= 1) return false
  return group.status !== 'merged' && group.status !== 'kept'
}

export function getNextActionableGroupIdFromGroups(groups: RouteMergeGroup[], currentId: string) {
  const currentIndex = groups.findIndex(group => group.id === currentId)
  if (currentIndex === -1) return groups[0]?.id || ''
  if (currentIndex + 1 < groups.length) {
    return groups[currentIndex + 1]?.id || ''
  }
  return groups[0]?.id || ''
}

export function routeSupportOperationPriority(operation: OperationItem) {
  const name = normalizeOperationName(operation.name)
  if (name.includes('去毛刺')) return 10
  if (name.includes('清洗')) return 20
  if (name.includes('检验') || name.includes('检查')) return 30
  if (name.includes('标印') || name.includes('标记')) return 40
  if (name.includes('包装')) return 50
  return 90
}

export function compareRouteFullSetOperation(sectionKey: string, left: OperationItem, right: OperationItem) {
  if (['support_front', 'support_middle', 'support_final'].includes(sectionKey)) {
    const priorityDiff = routeSupportOperationPriority(left) - routeSupportOperationPriority(right)
    if (priorityDiff !== 0) return priorityDiff
  }
  return Number(left.sequence || 0) - Number(right.sequence || 0) || Number(left.id || 0) - Number(right.id || 0)
}

function splitCompositeDisplayTokens(operation: OperationItem) {
  const rawName = String(operation.name || '').trim()
  if (!DISPLAY_COMPOSITE_SPLIT_PATTERN.test(rawName)) return []

  const tokens = rawName
    .split(DISPLAY_COMPOSITE_SPLIT_PATTERN)
    .map(token => normalizeOperationName(token))
    .filter(Boolean)

  if (tokens.length < 2) return []

  const standardSteps = Array.isArray(operation.step_items)
    ? operation.step_items.map(step => normalizeOperationName(String(step || ''))).filter(Boolean)
    : []

  if (!standardSteps.length) return []
  if (!tokens.every(token => standardSteps.includes(token))) return []

  return tokens
}

export function buildRouteFullSetDisplayOperations(operations: OperationItem[]) {
  const displayOperations: Array<OperationItem & Record<string, any>> = []

  operations.forEach((operation) => {
    const tokens = splitCompositeDisplayTokens(operation)
    if (!tokens.length) {
      displayOperations.push({
        ...operation,
        name: formatRouteDisplayName(String(operation.name || '')),
      })
      return
    }

    tokens.forEach((token, index) => {
      displayOperations.push({
        ...operation,
        id: Number(operation.id || 0) * 100 + index + 1,
        name: formatRouteDisplayName(token),
        step_items: [token],
        attached_step_items: [],
        source_operation_id: Number(operation.id || 0),
        source_operation_name: formatRouteDisplayName(String(operation.name || '')),
        display_key: `route-display-${operation.id}-${index + 1}`,
      })
    })
  })

  return displayOperations
}

export function buildRouteFullSetSectionsFromTree(operations: OperationItem[]) {
  const ordered = [...operations].sort((a, b) =>
    Number(a.sequence || 0) - Number(b.sequence || 0) || Number(a.id || 0) - Number(b.id || 0)
  )
  const displayOrdered = buildRouteFullSetDisplayOperations(ordered)
  const mainChain = displayOrdered.filter(item => Number(item.sequence || 0) <= ROUTE_FULL_SET_MAIN_MAX_SEQUENCE)
  const tailChain = displayOrdered.filter(item => Number(item.sequence || 0) > ROUTE_FULL_SET_MAIN_MAX_SEQUENCE)
  const sections: Array<{
    key: string
    title: string
    kicker: string
    description: string
    order: number
    operations: OperationItem[]
  }> = []

  if (mainChain.length) {
    sections.push({
      key: 'tree_main_chain',
      title: '主干段',
      kicker: '工艺树',
      description: '严格按全集工艺树原始顺序展示主干段，不再按前端阶段规则重排。',
      order: 10,
      operations: mainChain,
    })
  }

  if (tailChain.length) {
    sections.push({
      key: 'tree_tail_chain',
      title: '后续链',
      kicker: '工艺树',
      description: '严格按全集工艺树原始顺序展示后续链，不再按前端阶段规则重排。',
      order: 20,
      operations: tailChain,
    })
  }

  if (sections.length) return sections
  return [
    {
      key: 'tree_empty_chain',
      title: '全集工艺树',
      kicker: '工艺树',
      description: '严格按全集工艺树原始顺序展示。',
      order: 10,
      operations: displayOrdered,
    },
  ]
}

export function isNoiseOperationName(name?: string | null) {
  const normalized = normalizeOperationName(name)
  if (!normalized) return true
  return [
    '数控车床',
    '激光打标机',
    '数控磨床',
    '数控铣床',
    '加工中心',
    '车床',
    '磨床',
    '铣床',
    '钻床',
    '镗床',
  ].includes(normalized)
}

export function findPreferredMergeGroupId(groups: RouteMergeGroup[]) {
  return groups.find(group => isMergeGroupActionable(group))?.id || groups[0]?.id || ''
}

export function inferMergeFamilyKey(name: string) {
  const normalized = normalizeOperationName(name)
  if (['备料', '下料', '车零件', '车外形', '车外圆', '车端面', '平端面'].includes(normalized)) return 'shape'
  if (['钻孔', '镗孔', '钻镗孔', '钻铰孔', '铰孔', '攻螺纹'].includes(normalized)) return 'hole'
  if (['铣扁', '铣槽', '车槽', '割型孔', '割扁'].includes(normalized)) return 'feature'
  if (['调质', '正常化', '去应力', '淬火', '真空淬火', '镀铜', '渗氮', '氰化', '除铜'].includes(normalized)) return 'heat'
  if (['铬酸阳极化', '硬质阳极化', '钝化'].includes(normalized)) return 'surface'
  if (['磨外圆', '磨孔', '磨端面', '磨槽'].includes(normalized)) return 'grind'
  if (['研孔', '研顶尖孔', '研顶尖', '研外圆'].includes(normalized)) return 'lap'
  if (normalized.includes('检验') || normalized.includes('检查')) return 'inspection'
  if (normalized.includes('清洗') || normalized.includes('去毛刺') || normalized.includes('标印') || normalized.includes('标记') || normalized.includes('包装') || normalized.includes('倒角') || normalized.includes('倒圆') || normalized.includes('锐边')) return 'release'
  return normalized
}

export function inferMergeObjectChain(name: string) {
  const normalized = normalizeOperationName(name)
  if (['备料', '下料'].includes(normalized)) return 'blank_chain'
  if (['车零件', '车外形', '车外圆'].includes(normalized)) return 'outer_turn_chain'
  if (['车端面', '平端面'].includes(normalized)) return 'face_turn_chain'
  if (['钻孔', '镗孔', '钻镗孔', '钻铰孔', '铰孔', '攻螺纹'].includes(normalized)) return 'hole_chain'
  if (['铣扁', '铣槽', '割型孔', '割扁'].includes(normalized)) return 'feature_chain'
  if (['调质', '正常化'].includes(normalized)) return 'heat_prep_chain'
  if (['镀铜', '渗氮', '氰化', '除铜'].includes(normalized)) return 'chemical_heat_chain'
  if (['淬火', '真空淬火'].includes(normalized)) return 'heat_final_chain'
  if (['研孔', '研顶尖孔', '研顶尖'].includes(normalized)) return 'hole_finish_chain'
  if (['磁粉检查', '裂纹检查', '荧光检查'].includes(normalized)) return 'ndt_chain'
  return ''
}

export function inferMergeSubtypeKey(name: string) {
  const normalized = normalizeOperationName(name)
  if (['备料'].includes(normalized)) return 'material_prep'
  if (['下料'].includes(normalized)) return 'blank'
  if (['车零件', '车外形', '车外圆'].includes(normalized)) return 'outer_turn'
  if (['车端面', '平端面'].includes(normalized)) return 'face_turn'
  if (['钻孔'].includes(normalized)) return 'hole_drill'
  if (['镗孔', '钻镗孔'].includes(normalized)) return 'hole_bore'
  if (['钻铰孔', '铰孔'].includes(normalized)) return 'hole_ream'
  if (['攻螺纹'].includes(normalized)) return 'hole_tap'
  if (['铣扁', '割扁'].includes(normalized)) return 'feature_flat'
  if (['铣槽', '割型孔'].includes(normalized)) return 'feature_slot'
  if (['调质', '正常化'].includes(normalized)) return 'heat_prep'
  if (['镀铜'].includes(normalized)) return 'copper_plating'
  if (['渗氮', '氰化'].includes(normalized)) return 'chemical_heat'
  if (['除铜'].includes(normalized)) return 'decopper'
  if (['淬火', '真空淬火'].includes(normalized)) return 'heat_final'
  if (['研孔', '研顶尖孔', '研顶尖'].includes(normalized)) return 'hole_finish_lap'
  if (['磁粉检查', '裂纹检查', '荧光检查'].includes(normalized)) return 'ndt'
  return normalized
}

export function mapSuggestionStatus(status: string): MergeGroupStatus {
  if (status === 'merged') return 'merged'
  if (status === 'kept') return 'kept'
  if (status === 'conflict') return 'conflict'
  return 'pending'
}

export function buildRouteMergeGroupsFromSuggestions(
  suggestions: MergeSuggestion[],
  resolveCoverageLabel?: (group: RouteMergeGroup) => string,
) {
  const nextGroups: RouteMergeGroup[] = suggestions.map(item => ({
    id: String(item.target_group_id),
    sequence: Number(item.sequence || 0),
    standard_name: formatRouteDisplayName(String(item.normalized_step_name || '未命名工序段')),
    operation_ids: Array.isArray(item.source_operation_ids) ? item.source_operation_ids.map(id => Number(id)) : [],
    status: mapSuggestionStatus(String(item.status || 'pending')),
    coverageLabel: '',
    suggestion_type: String(item.suggestion_type || 'single'),
    recommendation_label: String(item.recommendation_label || ''),
    recommendation_reason: String(item.recommendation_reason || ''),
    recommended_target_name: formatRouteDisplayName(String(item.recommended_target_name || item.normalized_step_name || '未命名工序段')),
    step_family: String(item.step_family || ''),
    phase: String(item.phase || ''),
    separator_result: String(item.separator_result || 'pass'),
    manual_review_required: Boolean(item.manual_review_required),
    reason_codes: Array.isArray(item.reason_codes) ? item.reason_codes : [],
    evidence_excerpt: Array.isArray(item.evidence_excerpt) ? item.evidence_excerpt : [],
    matched_detail_rows: Array.isArray(item.matched_detail_rows) ? item.matched_detail_rows : [],
    source_type: 'backend_suggestion',
    parent_segment: formatRouteDisplayName(String(item.parent_segment || '')),
    equipment_child_segment: String(item.equipment_child_segment || ''),
    equipment_split_applied: Boolean(item.equipment_split_applied),
    equipment_types: Array.isArray(item.equipment_types) ? item.equipment_types : [],
    equipment_models: Array.isArray(item.equipment_models) ? item.equipment_models : [],
    equipment_support_result: String(item.equipment_support_result || 'neutral'),
    equipment_support_reason: String(item.equipment_support_reason || ''),
  }))

  nextGroups.forEach((group) => {
    group.coverageLabel = resolveCoverageLabel ? resolveCoverageLabel(group) : ''
  })

  return nextGroups.sort((left, right) => left.sequence - right.sequence || left.id.localeCompare(right.id))
}

export function displayFactorLabel(value?: string) {
  const text = (value || '').trim()
  if (!text) return ''
  const mapping: Record<string, string> = {
    'always=true': '属于常规主线工序',
    'has_hole=true': '存在内孔 / 通孔 / 中心孔',
    'has_spline=true': '存在槽 / 键 / 花键结构',
    'hardness=HIGH': '高硬度或强化热处理要求',
    'material!=空': '材料牌号会影响该工序',
    'roughness<=0.8': '高精度 / 高表面质量要求',
    'has_final=true': '需要终热处理',
    'has_vac=true': '需要真空淬火',
    'hole_complex=true': '孔系较复杂',
    'has_milling=true': '存在槽 / 扁 / 铣削特征',
    'has_relief=true': '需要去应力',
    'need_trace=true': '需要追溯标印',
    'need_mt=true': '需要磁粉检查',
    'need_burn_check=true': '需要烧伤检查',
    'structure_type=活门类': '属于活门类结构',
    'structure_type=衬套类': '属于衬套类结构',
    '外圆结构要求': '外圆主形面或回转外形需求',
    '台阶外形要求': '台阶外圆或轴肩轮廓需求',
    '外圆基准要求': '作为定位或检测基准的外圆需求',
    '外圆配合要求': '关键配合外圆或定尺寸外圆需求',
    '回转轮廓要求': '锥面、圆弧或过渡回转面需求',
    '外形轮廓要求': '局部外形轮廓需要车削成形',
    '端面基准要求': '基准端面或定位端面需求',
    '端面贴合要求': '台阶端面或贴合端面需求',
    '孔口端面要求': '孔口端面或沉台结构需求',
    '端面配合要求': '与外圆或内孔配合的端面需求',
    '锐边去除要求': '外圆边缘或端面锐边处理需求',
    '孔口倒角要求': '孔口导入或孔口倒角需求',
    '装配导入要求': '装配导入或防划伤处理需求',
    '孔结构类型': '普通孔、盲孔或台阶孔等孔结构需求',
    '中心孔定位要求': '中心孔或定位孔需求',
    '孔复合要求': '阶梯孔、孔台阶或孔复合加工需求',
    '深长孔要求': '深孔或长孔结构需求',
    '孔可达性限制': '孔位可达性或排屑受限',
    '孔尺寸精度要求': '孔径尺寸精度要求较高',
    '孔形位精度要求': '孔圆度、圆柱度或位置精度要求较高',
    '孔表面质量要求': '孔表面粗糙度或光整要求较高',
    '孔配合要求': '关键配合孔或定尺寸孔需求',
    '配对加工要求': '需要与配对件联动定尺寸',
    '分组配套要求': '需要分组配套或按实测尺寸配合',
    '尺寸公差高': '尺寸公差要求较高',
    '形位精度要求': '圆度、圆柱度、跳动等形位精度要求较高',
    '最终光整要求': '需要最终光整而不只是一般磨削',
    '装配配合要求': '属于关键配合面、贴合面或密封面',
    '热处理链分化': '材料或技术条件会改变热处理链',
    '热后精整要求': '热处理后仍需补充精整或定尺寸',
    '性能与耐磨要求': '耐磨、寿命或性能指标驱动',
    '尺寸稳定性要求': '长期尺寸稳定性要求较高',
    '传动装配要求': '属于传动配合或装配功能面',
    '结构特征要求': '存在与当前工序对应的回转结构或成形轮廓需求',
    '热处理特殊要求': '存在特殊热处理技术条件',
  }
  if (mapping[text]) return mapping[text]
  if (text.startsWith('material=')) {
    return `材料为 ${text.split('=', 2)[1] || ''}`.trim()
  }
  if (text === 'has_hole') return '存在内孔 / 通孔 / 中心孔'
  if (text === 'has_spline') return '存在槽 / 键 / 花键结构'
  if (text === 'hardness') return '硬度要求'
  if (text === 'material') return '材料牌号'
  if (text === 'roughness') return '表面粗糙度 / 表面质量要求'
  return text
}
