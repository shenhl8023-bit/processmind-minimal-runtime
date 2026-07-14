const TURNING_SIDE_LABEL_REPLACEMENTS: Array<[string, string]> = [
  ['车削加工（第1次）', '车削加工（A侧）'],
  ['车削加工（第2次）', '车削加工（B侧）'],
]

const ROUTE_PHASE_LABELS: Record<string, string> = {
  rough: '热前',
  rough_to_finish: '热前',
  mixed: '复合',
  heat_treatment: '热处理',
  surface_or_heat_treatment: '热处理',
  semi_finish_or_finish: '热后',
  finish: '热后',
  inspection: '检验',
  final_inspection: '最终检验',
  auxiliary: '辅助',
  release: '放行',
  preparation: '准备',
  surface_prep: '表面预处理',
  surface_treatment: '表面处理',
  assembly: '装配',
  test: '试验',
  cleaning: '清洗',
  blanking: '下料',
  forming: '成形',
  cutting: '切割',
  deburring: '去毛刺',
}

export function formatRouteDisplayName(value?: string | null) {
  let text = String(value || '').trim()
  if (!text) return ''
  TURNING_SIDE_LABEL_REPLACEMENTS.forEach(([source, target]) => {
    text = text.split(source).join(target)
  })
  if (text === '标印') text = '标记'
  text = text.split('标印（').join('标记（')
  return text
}

export function formatRoutePhaseLabel(value?: string | null) {
  const key = String(value || '').trim()
  return key ? ROUTE_PHASE_LABELS[key] || '' : ''
}

export function formatRouteDisplayNames(values: unknown) {
  const unique = new Set<string>()
  const items: string[] = []
  ;(Array.isArray(values) ? values : []).forEach((value) => {
    const text = formatRouteDisplayName(String(value || ''))
    if (!text || unique.has(text)) return
    unique.add(text)
    items.push(text)
  })
  return items
}
