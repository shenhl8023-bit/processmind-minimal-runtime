import type { FactorCandidate } from '@/components/analysis/types'
import type {
  DocumentItem,
  DocumentOperationDetailItem,
  OperationItem,
  SavedNormalizedRouteVersionResult,
  SegmentFactorReview,
  SegmentRuleReviewSaveResult,
} from '@/api'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

function splitMergedStepNames(stepName?: string | null) {
  return formatRouteDisplayName(String(stepName || ''))
    .split(/[／/]/)
    .map(part => part.trim())
    .filter(Boolean)
}

export function segmentNeedsMergeNameQuestion(segment: Segment | null | undefined) {
  const parts = splitMergedStepNames(segment?.normalized_step_name)
  return parts.length >= 2 && new Set(parts).size >= 2
}

function segmentHasMergeNameTrail(segment: Segment | null | undefined) {
  const trail = Array.isArray(segment?.rule_review?.question_trail) ? segment?.rule_review?.question_trail : []
  return trail.some(item => String(item?.nodeId || '') === 'merge_name_root')
}

function normalizeSegmentSourceNames(segment: Segment | null | undefined) {
  const unique = new Set<string>()
  const names: string[] = []
  ;(segment?.source_operation_names || []).forEach((name) => {
    const text = formatRouteDisplayName(String(name || ''))
    if (!text || unique.has(text)) return
    unique.add(text)
    names.push(text)
  })
  if (names.length) return names
  ;(segment?.source_nodes || []).forEach((name) => {
    const text = formatRouteDisplayName(String(name || ''))
    if (!text || unique.has(text)) return
    unique.add(text)
    names.push(text)
  })
  return names
}

export function segmentDisplayName(segment: Segment | null | undefined) {
  const normalizedName = formatRouteDisplayName(String(segment?.normalized_step_name || ''))
  const sourceLabel = normalizeSegmentSourceNames(segment).join(' / ')
  return normalizedName || sourceLabel
}

export function segmentDisplayMetaLabel(_segment: Segment | null | undefined) {
  return ''
}

export function segmentStepSummary(segment: Segment | null | undefined) {
  const rows = Array.isArray(segment?.matched_detail_rows) ? segment.matched_detail_rows : []
  const unique = new Set<string>()
  const items: string[] = []

  rows.forEach((row) => {
    const content = String(row?.operation_content || '').trim()
    const operationName = String(row?.operation_name || '').trim()
    const text = content || operationName
    if (!text || unique.has(text)) return
    unique.add(text)
    items.push(text)
  })

  if (!items.length) return ''
  if (items.length <= 2) return items.join('；')
  return `${items.slice(0, 2).join('；')} 等 ${items.length} 项`
}

export function segmentHasConfirmedFactor(segment: Segment | null | undefined) {
  return !!segment?.factor_reviews?.some(review => review.decision === 'confirmed')
}

export function segmentHasRuleDecision(segment: Segment | null | undefined) {
  if (segmentNeedsMergeNameQuestion(segment) && !segmentHasMergeNameTrail(segment)) return false
  return !!segment?.rule_review && ['accepted', 'rejected'].includes(segment.rule_review.decision)
}

export function segmentCanDefaultComplete(segment: Segment | null | undefined) {
  if (!segment || segmentHasRuleDecision(segment)) return false
  if (segmentNeedsMergeNameQuestion(segment)) return false
  const hitDocs = Number(segment.doc_coverage?.hit_docs || 0)
  const totalDocs = Number(segment.doc_coverage?.total_docs || 0)
  if (totalDocs <= 0) return false
  return hitDocs >= totalDocs
}

export function isSegmentCompleted(segment: Segment | null | undefined) {
  return segmentHasRuleDecision(segment) || segmentCanDefaultComplete(segment)
}

export function canAutoAcceptSegmentReview(args: {
  hasQuestionTree: boolean
  questionTreeInProgress: boolean
  questionTreeResultSummary?: string
  confirmedFactorCount: number
  excludedFactorCount: number
  pendingFactorCount: number
  allowDefaultAccept?: boolean
}) {
  const {
    hasQuestionTree,
    questionTreeInProgress,
    questionTreeResultSummary,
    confirmedFactorCount,
    excludedFactorCount,
    pendingFactorCount,
    allowDefaultAccept,
  } = args

  if (questionTreeInProgress) return false
  if (allowDefaultAccept) return true

  if (hasQuestionTree) {
    if (!(questionTreeResultSummary || '').trim()) return false
    return true
  }

  if (pendingFactorCount > 0) return false
  return (confirmedFactorCount + excludedFactorCount) > 0
}

export function isSegmentStarted(segment: Segment | null | undefined) {
  return !!segment && ((segment.factor_reviews?.length || 0) > 0 || !!segment.rule_review)
}

export function segmentProgressLabel(segment: Segment | null | undefined) {
  if (segmentHasRuleDecision(segment)) return '已确认'
  if (segmentCanDefaultComplete(segment)) return '已确认'
  if (isSegmentStarted(segment)) return '确认中'
  return '需要确认'
}

export function segmentProgressClass(segment: Segment | null | undefined) {
  if (isSegmentCompleted(segment)) return 'is-completed'
  if (isSegmentStarted(segment)) return 'is-started'
  return 'is-pending'
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
    'conditional=true': '可能是按条件触发的工序',
    'structure_variation=true': '可能受结构差异或工艺要求差异影响',
    'heat_chain=true': '与热处理链或硬度要求相关',
    'naming_variant=true': '原始文件里存在多种叫法，需先确认统一名称',
    'structure_type=活门类': '属于活门类结构',
    'structure_type=衬套类': '属于衬套类结构',
    '外圆结构要求': '存在外圆主形面或回转外形需求',
    '台阶外形要求': '存在台阶外圆或轴肩轮廓需求',
    '外圆基准要求': '外圆承担定位或检测基准作用',
    '外圆配合要求': '外圆属于关键配合面或定尺寸面',
    '回转轮廓要求': '存在锥面、圆弧或过渡回转轮廓',
    '外形轮廓要求': '存在需要车削成形的局部外形轮廓',
    '端面基准要求': '端面承担基准或定位作用',
    '端面贴合要求': '存在贴合端面或台阶端面要求',
    '孔口端面要求': '存在孔口端面或沉台结构要求',
    '端面配合要求': '端面与外圆或内孔存在配合关系',
    '锐边去除要求': '需要处理锐边、毛刺或边缘过渡',
    '孔口倒角要求': '孔口需要导入或倒角处理',
    '装配导入要求': '需要装配导入或防划伤处理',
    '孔结构类型': '存在通孔、盲孔或一般孔结构需求',
    '中心孔定位要求': '存在中心孔或定位孔需求',
    '孔复合要求': '存在阶梯孔、孔台阶或复合孔需求',
    '深长孔要求': '存在深孔或长孔结构需求',
    '孔可达性限制': '孔位可达性、排屑或加工空间受限',
    '孔尺寸精度要求': '孔径尺寸精度要求较高',
    '孔形位精度要求': '孔圆度、圆柱度或位置精度要求较高',
    '孔表面质量要求': '孔表面粗糙度或光整要求较高',
    '孔配合要求': '孔属于关键配合孔或定尺寸孔',
    '配对加工要求': '需要与配对件联动定尺寸',
    '分组配套要求': '需要分组配套或按实测尺寸配合',
    '尺寸公差高': '尺寸公差要求较高',
    '形位精度要求': '圆度、圆柱度、跳动或位置精度要求较高',
    '最终光整要求': '需要最终光整，而不只是一般磨削',
    '装配配合要求': '属于关键装配面、贴合面或密封面',
    '热处理链分化': '材料或技术条件会改变热处理链',
    '热后精整要求': '热处理后仍需补充精整或定尺寸',
    '性能与耐磨要求': '耐磨、寿命或性能指标驱动该工序',
    '尺寸稳定性要求': '长期尺寸稳定性要求较高',
    '被相邻工序一并完成': '常与相邻主工序一并完成',
    '作为上位工序局部内容': '通常属于上位工序中的局部动作',
    '局部特征单列': '只在局部结构或特殊样本中单独列出',
    '命名未统一': '原始文件里存在不同叫法或别名混用',
    '文档记录差异': '文档省略、合并记录或抽取口径不同',
    '热处理尺寸边界': '截面尺寸或有效热处理深度影响工序安排',
    '热处理结构风险': '结构形状或变形风险影响热处理工序选择',
  }
  return mapping[text] || text
}

export function applyRuleReviewUpdateToRoute(
  savedRoute: SavedNormalizedRouteVersionResult | null,
  result: SegmentRuleReviewSaveResult,
) {
  if (!savedRoute) return savedRoute
  return {
    ...savedRoute,
    segments: savedRoute.segments.map(segment => (
      segment.id === result.segment_id
        ? {
            ...segment,
            analysis_status: result.analysis_status,
            normalized_step_name: result.normalized_step_name || segment.normalized_step_name,
            rule_review: result.rule_review || null,
          }
        : segment
    )),
  }
}

export function formatDateTimeLabel(value: string) {
  return new Date(value).toLocaleString('zh-CN')
}

export function formatPercentLabel(value: number) {
  return `${Math.round((value || 0) * 100)}%`
}

export function segmentCoverageLabel(segment: Segment | null | undefined) {
  if (!segment) return '0/0'
  const label = (segment.doc_coverage?.label || '').trim()
  if (label) return label
  const hitDocs = Number(segment.doc_coverage?.hit_docs || 0)
  const totalDocs = Number(segment.doc_coverage?.total_docs || 0)
  return `${hitDocs}/${totalDocs}`
}

function inferOperationFamily(name?: string) {
  const text = (name || '').trim()
  if (!text) return 'generic'
  if (/(毛坯准备|备料|下料)/.test(text)) return 'prep'
  if (/(端面|平端面)/.test(text)) return 'end_face'
  if (/(倒角|倒圆|孔口倒角|锐边)/.test(text)) return 'chamfer'
  if (/(磁粉|烧伤|裂纹|荧光|检验|检查|探伤)/.test(text)) return 'inspection'
  if (/(调质|正常化|去应力|淬火|真空淬火|热处理|镀铜|渗氮|氰化|除铜|钝化|阳极化|时效)/.test(text)) return 'heat'
  if (/(磨外圆|研外圆|磨端面|磨槽|精磨|镜面磨)/.test(text)) return 'finish'
  if (/(磨孔|研孔|珩孔)/.test(text)) return 'hole_finish'
  if (/(孔|钻|镗|铰|攻螺纹|攻丝|内圆)/.test(text)) return 'hole'
  if (/(铣槽|铣扁|车槽|割型孔|割扁|花键|键槽|槽)/.test(text)) return 'feature'
  if (/(车零件|车外形|车外圆|精车外圆|粗车外圆|外圆)/.test(text)) return 'outer_surface'
  if (/(去毛刺|清洗|标印|标记|包装)/.test(text)) return 'release'
  return 'generic'
}

export function buildDocOperationHighlights(
  detailRows: DocumentOperationDetailItem[],
  docIds: number[],
  excludedNames: Set<string>,
  limit = 5,
) {
  if (!docIds.length) return []
  const docIdSet = new Set(docIds)
  const counter = new Map<string, { name: string; docCount: number }>()
  const docNameSets = new Map<number, Set<string>>()

  detailRows.forEach((row) => {
    const docId = Number(row.document_id || 0)
    if (!docIdSet.has(docId)) return
    const name = (row.normalized_name || row.operation_name || '').trim()
    if (!name || excludedNames.has(name)) return
    if (!docNameSets.has(docId)) {
      docNameSets.set(docId, new Set())
    }
    const docNames = docNameSets.get(docId)!
    if (docNames.has(name)) return
    docNames.add(name)
    if (!counter.has(name)) {
      counter.set(name, { name, docCount: 0 })
    }
    counter.get(name)!.docCount += 1
  })

  return Array.from(counter.values())
    .sort((a, b) => {
      if (a.docCount !== b.docCount) return b.docCount - a.docCount
      return a.name.localeCompare(b.name)
    })
    .slice(0, limit)
}

export function buildHeuristicFactorCandidates(args: {
  segment: Segment | null
  documents: DocumentItem[]
  operations: OperationItem[]
  variantNames: string[]
}) {
  const { segment, documents, operations, variantNames } = args
  if (!segment) return []

  const suggestions: Array<{
    key: string
    name: string
    sourceType: 'heuristic'
    strength: string
    confirmedCount: number
    operationCount: number
    operationNames: string[]
    evidences: string[]
    sourceOperationIds: number[]
  }> = []
  const seen = new Set<string>()
  const segmentName = (segment.normalized_step_name || '').trim()
  const ratio = Number(segment.doc_coverage?.ratio || 0)
  const hitDocs = Number(segment.doc_coverage?.hit_docs || 0)
  const totalDocs = Number(segment.doc_coverage?.total_docs || documents.length || 0)
  const operationNames = operations.map(operation => operation.name).filter(Boolean)
  const sourceOperationIds = operations.map(operation => operation.id)

  const pushSuggestion = (name: string, evidence: string, strength = '系统推测') => {
    const key = name.trim()
    if (!key || seen.has(key)) return
    seen.add(key)
    suggestions.push({
      key,
      name: key,
      sourceType: 'heuristic',
      strength,
      confirmedCount: 0,
      operationCount: sourceOperationIds.length,
      operationNames: [...operationNames],
      evidences: [evidence],
      sourceOperationIds: [...sourceOperationIds],
    })
  }

  if (totalDocs > 0) {
    if (ratio >= 0.8) {
      pushSuggestion('always=true', `该工序覆盖 ${hitDocs}/${totalDocs} 个样本，当前更像常规主线工序。`)
    } else if (ratio <= 0.2) {
      pushSuggestion('conditional=true', `该工序仅覆盖 ${hitDocs}/${totalDocs} 个样本，当前更像按条件触发的选择性工序。`)
    } else {
      pushSuggestion('structure_variation=true', `该工序覆盖 ${hitDocs}/${totalDocs} 个样本，出现比例居中，可能与结构差异或工艺要求差异有关。`)
    }
  }

  if (/(磁粉|探伤|荧光)/.test(segmentName)) {
    pushSuggestion('need_mt=true', `工序名包含“${segmentName}”，通常与专项无损检测要求相关。`, 'STRONG')
  }
  if (/烧伤/.test(segmentName)) {
    pushSuggestion('need_burn_check=true', `工序名包含“${segmentName}”，通常与烧伤检查要求相关。`, 'STRONG')
  }
  if (/(淬火|回火|调质|正常化|热处理)/.test(segmentName)) {
    pushSuggestion('heat_chain=true', `工序名包含“${segmentName}”，通常与热处理链或硬度要求有关。`)
  }
  if (/(孔|镗|钻|铰|攻丝|攻螺纹)/.test(segmentName)) {
    pushSuggestion('has_hole=true', `工序名包含“${segmentName}”，通常与内孔、通孔或螺纹结构相关。`)
  }
  if (/(槽|键|花键|铣|扁)/.test(segmentName)) {
    pushSuggestion('has_spline=true', `工序名包含“${segmentName}”，通常与槽、键或花键结构相关。`)
  }
  if (/(标印|标记|打标|刻字)/.test(segmentName)) {
    pushSuggestion('need_trace=true', `工序名包含“${segmentName}”，通常与追溯标识要求相关。`)
  }
  if (variantNames.length > 1) {
    pushSuggestion('naming_variant=true', `这道工序在原始文件中有 ${variantNames.length} 种叫法，如 ${variantNames.slice(0, 3).join('、')}。`)
  }

  const family = inferOperationFamily(segmentName)
  if (family === 'prep') {
    pushSuggestion('always=true', `“${segmentName}”通常属于工艺路线的起始主线工序。`, 'STRONG')
  }
  if (family === 'outer_surface') {
    pushSuggestion('外圆结构要求', `工序名包含“${segmentName}”，通常用于加工外圆主形面或回转外形。`, 'STRONG')
    pushSuggestion('外圆基准要求', `这类工序常用于建立后续加工和检测所需的外圆基准。`)
  }
  if (family === 'end_face') {
    pushSuggestion('端面基准要求', `工序名包含“${segmentName}”，通常与基准端面或定位端面相关。`, 'STRONG')
  }
  if (family === 'chamfer') {
    pushSuggestion('锐边去除要求', `工序名包含“${segmentName}”，通常用于处理锐边、毛刺或边缘过渡。`, 'STRONG')
  }
  if (family === 'hole') {
    pushSuggestion('孔结构类型', `工序名包含“${segmentName}”，通常由通孔、盲孔或复合孔结构驱动。`, 'STRONG')
  }
  if (family === 'feature') {
    pushSuggestion('has_spline=true', `工序名包含“${segmentName}”，通常与槽、键或花键等特征加工相关。`, 'STRONG')
  }
  if (family === 'finish') {
    pushSuggestion('尺寸公差高', `工序名包含“${segmentName}”，通常意味着尺寸精度要求较高。`, 'STRONG')
    pushSuggestion('roughness<=0.8', `工序名包含“${segmentName}”，通常意味着表面质量要求较高。`)
  }

  return suggestions.slice(0, 3)
}

export function buildFactorCandidates(args: {
  operations: OperationItem[]
  reviewMap: Map<string, SegmentFactorReview>
  segment: Segment | null
  documents: DocumentItem[]
  variantNames: string[]
}): FactorCandidate[] {
  const bucket = new Map<string, {
    key: string
    name: string
    sourceType: string
    strength: string
    confirmedCount: number
    operationCount: number
    operationNames: string[]
    evidences: string[]
    sourceOperationIds: number[]
  }>()

  args.operations.forEach((operation) => {
    ;(operation.factors || []).forEach((factor) => {
      const key = (factor.name || '').trim()
      if (!key) return
      if (!bucket.has(key)) {
        bucket.set(key, {
          key,
          name: key,
          sourceType: 'aggregated',
          strength: factor.strength || 'WEAK',
          confirmedCount: 0,
          operationCount: 0,
          operationNames: [],
          evidences: [],
          sourceOperationIds: [],
        })
      }
      const current = bucket.get(key)!
      current.confirmedCount += factor.confirmed ? 1 : 0
      current.operationCount += 1
      if (!current.sourceOperationIds.includes(operation.id)) {
        current.sourceOperationIds.push(operation.id)
      }
      if (!current.operationNames.includes(operation.name)) {
        current.operationNames.push(operation.name)
      }
      const evidence = (factor.evidence || '').trim()
      if (evidence && !current.evidences.includes(evidence)) {
        current.evidences.push(evidence)
      }
      if ((factor.strength || '').toUpperCase() === 'STRONG') {
        current.strength = 'STRONG'
      }
    })
  })

  const hasAggregatedCandidates = bucket.size > 0

  args.reviewMap.forEach((review, factorName) => {
    if (bucket.has(factorName)) return
    bucket.set(factorName, {
      key: factorName,
      name: factorName,
      sourceType: review.source_type || 'aggregated',
      strength: review.source_type === 'manual' ? '人工补充' : '已保存',
      confirmedCount: 0,
      operationCount: review.source_operation_names.length || review.source_operation_ids.length,
      operationNames: [...(review.source_operation_names || [])],
      evidences: [...(review.evidence_refs || [])],
      sourceOperationIds: [...(review.source_operation_ids || [])],
    })
  })

  if (!hasAggregatedCandidates) {
    buildHeuristicFactorCandidates({
      segment: args.segment,
      documents: args.documents,
      operations: args.operations,
      variantNames: args.variantNames,
    }).forEach((candidate) => {
      bucket.set(candidate.key, candidate)
    })
  }

  return Array.from(bucket.values())
    .map(item => ({
      ...item,
      review: args.reviewMap.get(item.name) || null,
    }))
    .sort((a, b) => {
      if (a.confirmedCount !== b.confirmedCount) return b.confirmedCount - a.confirmedCount
      if (a.strength !== b.strength) return a.strength === 'STRONG' ? -1 : 1
      if (a.operationCount !== b.operationCount) return b.operationCount - a.operationCount
      return a.name.localeCompare(b.name)
    })
}

export function extractOperationNotes(operations: OperationItem[]) {
  return operations
    .flatMap((operation) => {
      const matches = (operation.description || '')
        .split('\n')
        .map(line => line.trim())
        .filter(line => line.startsWith('补充说明：'))
        .map(line => line.replace(/^补充说明：/, '').trim())
      return matches
    })
    .filter(Boolean)
}

export function buildRuleCandidateSummary(args: {
  segment: Segment | null
  documents: DocumentItem[]
  hitCount: number
  missCount: number
  confirmedFactorLabels: string[]
  excludedFactorLabels: string[]
  hitHighlights: Array<{ name: string; docCount: number }>
  missingHighlights: Array<{ name: string; docCount: number }>
  variantNames: Array<{ name: string; count: number }>
  operationNotes: string[]
}) {
  const { segment } = args
  if (!segment) return []
  const lines: string[] = []
  const totalDocs = segment.doc_coverage.total_docs || args.documents.length
  const ratio = segment.doc_coverage.ratio || 0

  if (args.confirmedFactorLabels.length) {
    lines.push(`当前已确认的主要影响因素：${args.confirmedFactorLabels.join('、')}。`)
  }

  if (args.excludedFactorLabels.length) {
    lines.push(`当前已明确排除的候选因素：${args.excludedFactorLabels.join('、')}。`)
  }

  if (args.operationNotes.length) {
    lines.push(`最近补充判断提到：${args.operationNotes.slice(0, 2).join('；')}。`)
  }

  if (totalDocs > 0) {
    if (ratio >= 0.8) {
      lines.push(`这道工序在当前样本中覆盖较高（${args.hitCount}/${totalDocs}），更接近高频主线工序，除非后续发现明确的排除条件。`)
    } else if (ratio <= 0.2) {
      lines.push(`这道工序在当前样本中覆盖较低（${args.hitCount}/${totalDocs}），更像按条件触发的选择性工序。`)
    } else {
      lines.push(`这道工序在当前样本中的出现比例为 ${args.hitCount}/${totalDocs}，建议结合正反样本差异继续判断触发条件。`)
    }
  }

  if (args.hitHighlights.length) {
    const names = args.hitHighlights.slice(0, 3).map(item => item.name).join('、')
    lines.push(`在命中样本里，它更常与 ${names} 等工序一起出现。`)
  }

  if (args.missCount > 0 && args.missingHighlights.length) {
    const names = args.missingHighlights.slice(0, 3).map(item => item.name).join('、')
    lines.push(`在未命中样本里，更常看到 ${names}，可以作为后续对比线索。`)
  }

  if (args.variantNames.length > 1) {
    const names = args.variantNames.slice(0, 3).map(item => item.name).join('、')
    lines.push(`这道工序在原文中存在多种叫法，如 ${names}，后续整理规则时建议归一到同一标准工序。`)
  }

  return lines
}
