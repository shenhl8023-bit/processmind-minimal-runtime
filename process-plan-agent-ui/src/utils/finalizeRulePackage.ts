import { FINALIZE_EXPORT_COPY } from '@/config/finalizeRulePresentation'

export function sanitizeMarkdownInline(text: string) {
  return String(text || '').replace(/\|/g, '\\|').trim()
}

export function normalizeExportProcessName(name: string) {
  const text = String(name || '').trim()
  if (/真空淬火|淬火/.test(text)) return '淬火'
  return text
}

export function isMainlineFinalizeCard(item: any) {
  const coverage = item.segment?.doc_coverage
  if (coverage?.total_docs && coverage.hit_docs === coverage.total_docs) return true
  if ((item.factorNames || []).includes('always=true')) return true
  return /全部样本中稳定出现|标准主线工序|主线工序保留/.test(String(item.conditionText || ''))
}

export function classifyExportRuleCategory(item: any, displayName: string) {
  const text = [
    displayName,
    item.conditionText,
    ...(item.factorNames || []),
    ...(item.userAnswerLabels || []),
    ...(item.userAnswerContextLabels || []),
  ].join(' ')
  if (isMainlineFinalizeCard(item)) return '主线规则'
  if (/材料|9Cr18|4Cr14|6061|调质|正常化|淬火|热处理|渗氮|阳极化|镀铜|除铜|硬度/.test(text)) return '材料规则'
  if (/IT\d|Ra|粗糙度|精度|公差|圆度|圆柱度|同轴度|跳动|位置度|平面度|垂直度|磨|研|珩/.test(text)) return '精度规则'
  if (/标印|标记|裂纹|磁粉|荧光|烧伤|检查|去应力/.test(text)) return '人工补充规则'
  return '特征规则'
}

export function exportProcessIdForItem(item: any) {
  if (/真空淬火|淬火/.test(String(item.segment?.normalized_step_name || ''))) return 'process_quench'
  return item.segment?.id || ''
}

export function buildFactorDictionaryExport() {
  return {
    schema_version: '1.0',
    model: '四槽输入因素模型',
    material_grade: {
      label: '材料牌号',
      source: 'CAD/PLM',
      input_type: 'single',
      required: true,
      values: ['9Cr18', '4Cr14Ni14W2Mo', '6061'],
      note: '当前样本族已沉淀的材料牌号；后续项目应由样本材料自动汇总生成。',
    },
    cad_features: {
      label: 'CAD特征集合',
      source: 'CAD',
      input_type: 'multi',
      required: true,
      values: ['扁位/平面', '槽类特征', '普通孔/辅助孔', '铰孔/精孔', '型孔/割扁', '顶尖孔'],
      note: '由CAD特征类型归并得到，不直接要求用户填写内部布尔因素。',
    },
    precision_grades: {
      label: '精度/表面要求',
      source: 'CAD/工艺要求',
      input_type: 'multi',
      required: true,
      values: ['孔精加工', '珩孔要求', '研孔要求', '外圆磨削', '端面磨削', '槽磨削', '研外圆'],
      note: '由尺寸公差、形位公差、粗糙度和工艺要求映射得到。',
    },
    special_requirements: {
      label: '特殊要求',
      source: '人工补充/图样技术要求',
      input_type: 'multi',
      required: false,
      values: ['渗氮层要求', '铬酸阳极化要求', '硬质阳极化要求', '追溯标印', '磁粉检查要求', '烧伤检查要求'],
      note: '仅保留无法稳定从CAD直接获取、但会影响工序路线的少量补充项。',
    },
  }
}

export function buildInputSchemaExport() {
  const factorDictionary = buildFactorDictionaryExport()
  return {
    schema_version: '1.0',
    purpose: '第5步新零件路线生成输入结构',
    model: '四槽输入因素模型',
    factor_dictionary: factorDictionary,
    required_inputs: [
      {
        key: 'material_grade',
        name: '材料牌号',
        source: 'CAD/PLM',
        type: 'select',
        allowed_values: factorDictionary.material_grade.values,
        examples: factorDictionary.material_grade.values,
      },
      {
        key: 'cad_features',
        name: 'CAD特征集合',
        source: 'CAD',
        type: 'array',
        allowed_values: factorDictionary.cad_features.values,
      },
      {
        key: 'precision_grades',
        name: '精度/表面要求',
        source: 'CAD/工艺要求',
        type: 'array',
        allowed_values: factorDictionary.precision_grades.values,
      },
    ],
    optional_inputs: [
      {
        key: 'special_requirements',
        name: '特殊要求',
        source: '人工补充/图样技术要求',
        type: 'array',
        allowed_values: factorDictionary.special_requirements.values,
      },
    ],
    notes: [
      '零件类型不作为必填输入，只能作为可选辅助信息。',
      '内部因素由规则包自动映射，不要求用户填写25个因素。',
      '第5步输入收敛为材料、CAD特征、精度/表面要求、特殊要求四类因素。',
    ],
  }
}

export function buildStaticRouteRules() {
  return {
    input_policy: {
      user_inputs: ['material_grade', 'cad_features', 'precision_grades', 'special_requirements'],
      required_user_inputs: ['material_grade', 'cad_features', 'precision_grades'],
      optional_user_inputs: ['special_requirements'],
      excluded_required_inputs: ['part_type', '25_internal_factors'],
      note: '第5步按四槽输入因素模型接收材料、CAD特征、精度/表面要求和少量特殊要求；其余因素由本规则包内部映射。',
    },
    material_rules: [
      { when: { material_grade: '9Cr18' }, then: ['调质', '淬火'], note: '当前样本族中9Cr18稳定触发调质和合并后的淬火候选。' },
      { when: { material_grade: '4Cr14Ni14W2Mo' }, then: ['正常化'], note: '4Cr14Ni14W2Mo样本触发正常化。' },
      { when: { material_grade: '4Cr14Ni14W2Mo', special_requirement: '渗氮层要求' }, then: ['镀铜', '渗氮', '除铜'], note: '渗氮层要求触发镀铜保护、渗氮和除铜链条。' },
      { when: { material_grade: '6061', special_requirement: '铬酸阳极化要求' }, then: ['铬酸阳极化'], note: '6061按表面处理要求触发铬酸阳极化。' },
      { when: { material_grade: '6061', special_requirement: '硬质阳极化要求' }, then: ['硬质阳极化'], note: '6061按表面处理要求触发硬质阳极化。' },
    ],
    feature_rules: [
      { when: { cad_feature: '扁位/平面' }, then: ['铣扁', '割扁'] },
      { when: { cad_feature: '槽类特征' }, then: ['铣槽', '磨槽'] },
      { when: { cad_feature: '普通孔/辅助孔' }, then: ['钻孔', '打孔'] },
      { when: { cad_feature: '铰孔/精孔' }, then: ['钻铰孔'] },
      { when: { cad_feature: '型孔/割扁' }, then: ['割型孔', '打型孔'] },
      { when: { cad_feature: '顶尖孔' }, then: ['研顶尖孔'] },
    ],
    precision_rules: [
      { when: { precision_requirement: '孔精加工' }, then: ['磨孔'] },
      { when: { precision_requirement: '珩孔要求' }, then: ['珩孔'] },
      { when: { precision_requirement: '研孔要求' }, then: ['研孔'] },
      { when: { precision_requirement: '外圆磨削' }, then: ['磨外圆'] },
      { when: { precision_requirement: '端面磨削' }, then: ['磨端面'] },
      { when: { precision_requirement: '槽磨削' }, then: ['磨槽'] },
      { when: { precision_requirement: '研外圆' }, then: ['研外圆'] },
    ],
    special_requirement_rules: [
      { when: { special_requirement: '追溯标印' }, then: ['标记'] },
      { when: { special_requirement: '磁粉检查要求' }, then: ['磁粉检查', '荧光检查'] },
      { when: { special_requirement: '烧伤检查要求' }, then: ['烧伤检查'] },
    ],
  }
}

export function buildFinalizeRuleMarkdown(args: {
  projectName: string
  routeVersion?: number | string | null
  cards: any[]
  displayName: (segment: any) => string
  metaLabel: (segment: any) => string
  phaseLabel: (segment: any) => string
}) {
  const lines: string[] = []
  lines.push(`# ${FINALIZE_EXPORT_COPY.documentTitle}`)
  lines.push('')
  lines.push(`- 任务名称：${args.projectName || '未命名任务'}`)
  lines.push(`- 已保存版本：V${args.routeVersion || '-'}`)
  lines.push(`- 导出时间：${new Date().toLocaleString('zh-CN', { hour12: false })}`)
  lines.push(`- 工序段数量：${args.cards.length}`)
  lines.push('')
  lines.push(`## ${FINALIZE_EXPORT_COPY.explanationHeading}`)
  lines.push('')
  FINALIZE_EXPORT_COPY.explanationLines.forEach((line) => {
    lines.push(`- ${line}`)
  })
  lines.push('')
  lines.push('## 路线规则明细')
  lines.push('')

  args.cards.forEach((item) => {
    const displayName = args.displayName(item.segment)
    lines.push(`### ${item.segment.sequence}. ${displayName}`)
    lines.push('')
    const metaLabel = args.metaLabel(item.segment)
    if (metaLabel) {
      lines.push(`- 显示说明：${metaLabel}`)
    }
    lines.push(`- 阶段：${args.phaseLabel(item.segment)}`)
    lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.stepFamily}：${item.segment.step_family || '未标注'}`)
    lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.edited}：${item.edited ? '是' : '否'}`)
    lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.condition}：${item.conditionText}`)
    if (item.userAnswerContextLabels.length) {
      lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.context}：${item.userAnswerContextLabels.join('、')}`)
    }
    if (item.userAnswerLabels.length) {
      lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.confirmedFactors}：${item.userAnswerLabels.join('、')}`)
    }
    if (item.systemFactorLabels.length) {
      lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.candidateFactors}：${item.systemFactorLabels.join('、')}`)
    }
    if (item.rawRuleLines.length) {
      lines.push(`- ${FINALIZE_EXPORT_COPY.fieldLabels.rawInfo}：`)
      item.rawRuleLines.forEach((line: string) => {
        lines.push(`  - ${line}`)
      })
    }
    lines.push('')
  })

  lines.push(`## ${FINALIZE_EXPORT_COPY.summaryHeading}`)
  lines.push('')
  lines.push(`| ${FINALIZE_EXPORT_COPY.tableHeaders.join(' | ')} |`)
  lines.push(`| ${FINALIZE_EXPORT_COPY.tableHeaders.map(() => '---').join(' | ')} |`)
  args.cards.forEach((item) => {
    lines.push(`| ${sanitizeMarkdownInline(args.phaseLabel(item.segment))} | ${item.segment.sequence} | ${sanitizeMarkdownInline(args.displayName(item.segment))} | ${sanitizeMarkdownInline(item.conditionText)} |`)
  })
  lines.push('')
  return lines.join('\n')
}

export function buildRouteCatalogExport(args: {
  projectId: number | null
  projectName: string
  routeVersion?: number | string | null
  cards: any[]
  displayName: (segment: any) => string
  phaseLabel: (segment: any) => string
  primarySteps: (segment: any) => string[]
  attachedSteps: (segment: any) => string[]
}) {
  const segmentMap = new Map<string, any>()
  args.cards.forEach((item) => {
    const processId = exportProcessIdForItem(item)
    const existing = segmentMap.get(processId)
    const current = {
      process_id: processId,
      source_process_ids: [item.segment.id],
      sequence: item.segment.sequence,
      process_name: normalizeExportProcessName(item.segment.normalized_step_name),
      source_process_names: [args.displayName(item.segment)],
      phase: args.phaseLabel(item.segment),
      main: isMainlineFinalizeCard(item),
      step_family: item.segment.step_family || '',
      primary_steps: args.primarySteps(item.segment),
      attached_steps: args.attachedSteps(item.segment),
      source_nodes: item.segment.source_nodes || [],
      coverage: item.segment.doc_coverage || null,
    }
    if (!existing) {
      segmentMap.set(processId, current)
      return
    }
    existing.source_process_ids = Array.from(new Set([...existing.source_process_ids, ...current.source_process_ids]))
    existing.source_process_names = Array.from(new Set([...existing.source_process_names, ...current.source_process_names]))
    existing.sequence = Math.min(existing.sequence, current.sequence)
    existing.main = existing.main && current.main
    existing.primary_steps = Array.from(new Set([...existing.primary_steps, ...current.primary_steps]))
    existing.attached_steps = Array.from(new Set([...existing.attached_steps, ...current.attached_steps]))
    existing.source_nodes = Array.from(new Set([...existing.source_nodes, ...current.source_nodes]))
  })
  const segments = Array.from(segmentMap.values()).sort((a, b) => Number(a.sequence || 0) - Number(b.sequence || 0))
  return {
    schema_version: '1.0',
    project_id: args.projectId,
    project_name: args.projectName || '未命名任务',
    route_version: args.routeVersion || null,
    exported_at: new Date().toISOString(),
    process_count: segments.length,
    segments,
    export_decisions: [
      '淬火/真空淬火在输出层统一为“淬火”。',
      '主线工序标记 main=true，不参与条件筛选。',
    ],
  }
}

export function buildRouteRulesExport(args: {
  projectId: number | null
  projectName: string
  routeVersion?: number | string | null
  cards: any[]
  displayName: (segment: any) => string
}) {
  const factorDictionary = buildFactorDictionaryExport()
  const triggerRules = args.cards.map((item) => {
    const main = isMainlineFinalizeCard(item)
    return {
      rule_id: `RR-${String(item.segment.sequence).padStart(4, '0')}`,
      process_id: exportProcessIdForItem(item),
      source_process_id: item.segment.id,
      process_name: normalizeExportProcessName(item.segment.normalized_step_name),
      source_process_name: args.displayName(item.segment),
      category: classifyExportRuleCategory(item, args.displayName(item.segment)),
      main,
      condition_text: item.conditionText,
      internal_factors: item.factorNames,
      confirmed_factor_labels: item.userAnswerLabels,
      context_labels: item.userAnswerContextLabels,
      candidate_factor_labels: item.systemFactorLabels,
      output_policy: /真空淬火|淬火/.test(item.segment.normalized_step_name)
        ? '输出路线统一命名为“淬火”'
        : '',
    }
  })
  return {
    schema_version: '1.0',
    project_id: args.projectId,
    project_name: args.projectName || '未命名任务',
    route_version: args.routeVersion || null,
    exported_at: new Date().toISOString(),
    factor_dictionary: factorDictionary,
    ...buildStaticRouteRules(),
    process_trigger_rules: triggerRules,
  }
}

export function validateRulePackage(inputSchema: any, routeCatalog: any, routeRules: any, report: string) {
  const errors: string[] = []
  const warnings: string[] = []
  const requiredFileChecks = [
    ['input_schema.json', inputSchema],
    ['route_catalog.json', routeCatalog],
    ['route_rules.json', routeRules],
    ['rule_report.md', report],
  ]
  requiredFileChecks.forEach(([name, value]) => {
    if (!value) errors.push(`${name} 内容为空`)
  })

  const requiredKeys = new Set((inputSchema?.required_inputs || []).map((item: any) => item?.key))
  ;['material_grade', 'cad_features', 'precision_grades'].forEach((key) => {
    if (!requiredKeys.has(key)) errors.push(`input_schema.json 缺少必填输入：${key}`)
  })
  const optionalKeys = new Set((inputSchema?.optional_inputs || []).map((item: any) => item?.key))
  if (!optionalKeys.has('special_requirements')) {
    warnings.push('input_schema.json 建议加入可选输入：special_requirements')
  }
  if (requiredKeys.has('part_type')) {
    warnings.push('part_type 不应作为必填输入，建议仅作为可选辅助字段')
  }

  const catalogSegments = Array.isArray(routeCatalog?.segments) ? routeCatalog.segments : []
  if (!catalogSegments.length) errors.push('route_catalog.json 没有工序段')
  const processIds = new Set<string>()
  const processNames = new Map<string, number>()
  catalogSegments.forEach((segment: any) => {
    const processId = String(segment?.process_id || '').trim()
    const processName = String(segment?.process_name || '').trim()
    if (!processId) errors.push('route_catalog.json 存在缺少 process_id 的工序')
    if (processIds.has(processId)) errors.push(`route_catalog.json 存在重复 process_id：${processId}`)
    processIds.add(processId)
    if (!processName) errors.push(`route_catalog.json 工序 ${processId || '(未知)'} 缺少 process_name`)
    processNames.set(processName, (processNames.get(processName) || 0) + 1)
  })
  processNames.forEach((count, name) => {
    if (name && count > 1) warnings.push(`route_catalog.json 存在重复工序名：${name}`)
  })

  const triggerRules = Array.isArray(routeRules?.process_trigger_rules) ? routeRules.process_trigger_rules : []
  if (!triggerRules.length) errors.push('route_rules.json 没有 process_trigger_rules')
  triggerRules.forEach((rule: any) => {
    const targetId = String(rule?.process_id || '').trim()
    if (!processIds.has(targetId)) errors.push(`route_rules.json 规则 ${rule?.rule_id || '(未知)'} 指向不存在工序：${targetId}`)
    if (!rule?.main && !String(rule?.condition_text || '').trim()) {
      warnings.push(`route_rules.json 条件规则 ${rule?.rule_id || targetId} 缺少 condition_text`)
    }
  })
  if (catalogSegments.some((segment: any) => /真空淬火/.test(String(segment?.process_name || '')))) {
    errors.push('route_catalog.json 输出层仍包含“真空淬火”，应统一为“淬火”')
  }

  return { errors, warnings }
}
