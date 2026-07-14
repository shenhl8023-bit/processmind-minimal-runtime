export interface SemanticDominantProcessRule {
  canonical: string
  dominant: RegExp
  companion: RegExp
}

export const SEMANTIC_DOMINANT_PROCESS_RULES: SemanticDominantProcessRule[] = [
  {
    canonical: '去毛刺',
    dominant: /(去毛刺)/,
    companion: /(车|铣|钻|镗|铰|攻|磨|研|珩|挖|割|打|切|修|槽|孔|外圆|端面|扁|型孔|异形|回转|螺纹|加工)/,
  },
  {
    canonical: '倒角',
    dominant: /(倒角|倒圆|孔口倒角|车倒角|外倒角|内倒角)/,
    companion: /(车|铣|钻|镗|铰|攻|磨|研|珩|挖|割|打|切|修|槽|孔|外圆|端面|扁|型孔|异形|回转|螺纹|加工)/,
  },
  {
    canonical: '清洗',
    dominant: /(清洗)/,
    companion: /(检验|检查|终检|探伤|磁粉|烧伤|裂纹|荧光|渗透|热处理|渗氮|阳极化|镀铜|除铜|交付|入库|转序)/,
  },
]

export function matchSemanticDominantProcess(names: string[]) {
  const normalizedNames = Array.from(new Set(
    names.map(name => String(name || '').trim()).filter(Boolean),
  ))
  if (!normalizedNames.length) return null

  const joined = normalizedNames.join(' ')
  for (const rule of SEMANTIC_DOMINANT_PROCESS_RULES) {
    const containsDominant = normalizedNames.some(name => rule.dominant.test(name)) || rule.dominant.test(joined)
    if (!containsDominant) continue
    const hasCompanion = normalizedNames.some(name => !rule.dominant.test(name) && rule.companion.test(name))
      || rule.companion.test(joined.replace(rule.dominant, ''))
    if (hasCompanion) return rule.canonical
  }

  return null
}
