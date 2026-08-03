export type RulePackageActionState = {
  resetting: boolean
  parsing: boolean
  reviewing: boolean
  publishing: boolean
  downloading: boolean
  hasSegments: boolean
  factorCatalogReady: boolean
  hasReviewWork: boolean
  allRulesConfirmed: boolean
  currentVersion: number | null
}

const busy = (state: RulePackageActionState) => (
  state.resetting
  || state.parsing
  || state.reviewing
  || state.publishing
  || state.downloading
)

export function reviewActionLabel(
  state: RulePackageActionState,
  completed: number,
  total: number,
) {
  if (state.parsing) return `正在识别 ${completed}/${total}`
  if (state.reviewing) return `正在审核 ${completed}/${total}`
  if (state.allRulesConfirmed) return '规则已审核'
  return '规则审核'
}

export function publishActionLabel(state: RulePackageActionState) {
  if (state.publishing) return '正在发布...'
  if (state.currentVersion) return `已发布 V${state.currentVersion}`
  return '发布规则包'
}

export function downloadActionLabel(state: RulePackageActionState) {
  return state.downloading ? '正在下载...' : '下载当前版本'
}

export function rulePackageActionDisabled(state: RulePackageActionState) {
  const shared = busy(state) || !state.hasSegments || !state.factorCatalogReady
  return {
    review: shared || !state.hasReviewWork || state.allRulesConfirmed,
    publish: shared || !state.allRulesConfirmed || state.currentVersion !== null,
    download: busy(state) || state.currentVersion === null,
  }
}
