import { SHARED_RULE_TERMS } from '@/config/sharedRuleLanguage'

export const FINALIZE_VIEW_COPY = {
  pageTitle: '规则定稿',
  pageSubtitle: `预览并微调整条工艺路线中每道工序的${SHARED_RULE_TERMS.settingBasis}与${SHARED_RULE_TERMS.triggerCondition}。`,
  backToAnalysis: '返回规则分析',
  exportDocument: '导出规则包',
  showAll: '查看全部',
  showEditedOnly: '只看已改',
  refresh: '刷新结果',
  routeOverview: '工艺路线总览',
  editedBadge: '已改',
  rawInfoExpand: '原规则',
  rawInfoCollapse: '收起原规则',
  edit: '编辑',
  conditionLabel: `工序${SHARED_RULE_TERMS.settingBasis}`,
  rawInfoLabel: '原信息',
  drawerKicker: '结果微调',
  close: '关闭',
  confirmedFactorTitle: '用户已确认规则因素',
  confirmedFactorPlaceholder: '每行填写一条用户已确认的规则因素。',
  contextTitle: '上层判断口径',
  contextPlaceholder: '可填写该工序的上层判断口径，每行一条。',
  candidateFactorTitle: '系统候选补充因素',
  triggerConditionTitle: SHARED_RULE_TERMS.triggerCondition,
  triggerConditionPlaceholder: '请描述该工序在何种工艺特征或技术要求下安排。',
  rewriteByFactors: '按已选规则因素重写',
  reset: '恢复默认',
  save: '保存本页修改',
  emptyProjectTitle: '还没有选中任务',
  emptyProjectText: '请先在前三步完成路线整理与规则分析，再进入第四步查看结果。',
  loadingTitle: '正在装载第四步结果',
  loadingText: '系统正在读取已保存路线和每道工序的因素结论。',
  errorTitle: '暂时还没有可预览的定稿结果',
  errorBack: '返回第三步',
  emptySegmentTitle: '当前没有可展示的工序',
  emptySegmentText: '请先在第三步完成至少一版规则分析结果。',
  emptyEditedTitle: '当前还没有已修改工序',
  emptyEditedText: '你可以先查看全部工序，挑几道想调整的工序试一下编辑抽屉的效果。',
} as const

export const FINALIZE_EXPORT_COPY = {
  documentTitle: '第四步工序规则定稿说明',
  documentNameSuffix: '第四步规则定稿包',
  explanationHeading: '导出说明',
  explanationLines: [
    '本文档基于第四步“规则定稿”当前页面结果生成。',
    '导出内容默认包含全部工序段，不受“只看已改”筛选影响。',
    `“工序${SHARED_RULE_TERMS.settingBasis}”为当前定稿后的最终规则表述。`,
    '“原信息”用于辅助复核规则来源，不直接作为最终规则文案。',
  ],
  summaryHeading: '工序定稿总览',
  tableHeaders: ['阶段', '序号', '工序名', `工序${SHARED_RULE_TERMS.settingBasis}`],
  fieldLabels: {
    stepFamily: '工序类型',
    edited: '是否已微调',
    condition: `工序${SHARED_RULE_TERMS.settingBasis}`,
    context: '上层判断口径',
    confirmedFactors: '用户已确认规则因素',
    candidateFactors: '系统候选补充因素',
    rawInfo: '原信息',
  },
} as const

export const FINALIZE_FACTOR_PHRASES: Record<string, string> = {
  'always=true': '该工序在全部样本中稳定出现，作为主线工序纳入路线',
  'has_hole=true': '零件存在内孔、通孔或中心孔',
  'has_spline=true': '零件存在槽、键或花键结构',
  'hardness=HIGH': '零件有较高的硬度或强化热处理要求',
  'material!=空': '材料牌号会影响该工序安排',
  'roughness<=0.8': '零件对精度或表面质量要求较高',
  'has_final=true': '零件需要终热处理',
  'has_vac=true': '采用真空淬火路线',
  'hole_complex=true': '孔系较复杂',
  'has_milling=true': '存在槽、扁位或铣削特征',
  'has_relief=true': '需要安排去应力处理',
  'need_trace=true': '图样要求追溯标印',
  'need_mt=true': '图样要求磁粉检查',
  'need_burn_check=true': '图样要求烧伤检查',
  'conditional=true': '只有部分结构或工艺要求下才会出现',
  'structure_variation=true': '不同结构类型下工艺安排存在差异',
  'heat_chain=true': '热处理链要求会影响该工序是否纳入路线',
  'naming_variant=true': '原始工艺规程中存在不同叫法但指向同类工艺内容',
  'structure_type=活门类': '零件属于活门类结构',
  'structure_type=衬套类': '零件属于衬套类结构',
  '外圆结构要求': '零件存在外圆主形面或回转外形需求',
  '台阶外形要求': '零件存在台阶外圆或轴肩轮廓需求',
  '外圆基准要求': '该外圆承担定位或检测基准作用',
  '外圆配合要求': '该外圆属于关键配合面或定尺寸面',
  '回转轮廓要求': '存在锥面、圆弧或过渡回转轮廓需求',
  '外形轮廓要求': '存在需要车削成形的局部外形轮廓',
  '端面基准要求': '该端面承担基准或定位作用',
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
  '性能与耐磨要求': '耐磨、寿命或性能指标会驱动该工序',
  '尺寸稳定性要求': '长期尺寸稳定性要求较高',
}

export function resolveFinalizeFactorPhrase(value: string, fallback: string) {
  return FINALIZE_FACTOR_PHRASES[value] || fallback
}

export function buildFinalizeMainlineSentence(segmentName: string, stable: boolean) {
  if (stable) {
    return `“${segmentName}”在全部样本中稳定出现，作为标准主线工序保留在路线中。`
  }
  return `“${segmentName}”作为当前规则结果中的主线工序保留在路线中。`
}

export function buildFinalizeActionSentence(segmentName: string, reasonText: string) {
  const condition = String(reasonText || '').trim()
  if (/(检验|终检|检查|探伤|磁粉|荧光|渗透)/.test(segmentName)) {
    return `当${condition}时，设置“${segmentName}”作为质量确认节点。`
  }
  if (/(去毛刺|清洗)/.test(segmentName)) {
    return `当${condition}时，安排“${segmentName}”工序进行清理或转序准备。`
  }
  if (/(包装|封存|防护包装)/.test(segmentName)) {
    return `当${condition}时，设置“${segmentName}”作为交付、防护或转运收尾工序。`
  }
  if (/(标印|打标|标记)/.test(segmentName)) {
    return `当${condition}时，安排“${segmentName}”工序完成标识或追溯要求。`
  }
  if (/(表面处理|镀铜|除铜|阳极化|钝化)/.test(segmentName)) {
    return `当${condition}时，安排“${segmentName}”工序满足表面处理或防护要求。`
  }
  if (/(倒角|倒圆)/.test(segmentName)) {
    return `当${condition}时，安排“${segmentName}”工序处理边缘、孔口或装配导入要求。`
  }
  if (/去应力/.test(segmentName)) {
    return `当${condition}时，安排“${segmentName}”工序稳定尺寸并降低后续变形风险。`
  }
  return `当${condition}时，纳入“${segmentName}”工序。`
}

export function buildFinalizeTriggerSentence(segmentName: string, reasonText: string) {
  return buildFinalizeActionSentence(segmentName, reasonText)
}
