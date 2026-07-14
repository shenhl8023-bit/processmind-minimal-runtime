export function buildSettingBasisPrompt(
  subject: string,
  focus: string,
  partialCoverage = false,
) {
  if (partialCoverage) {
    return `${subject}未覆盖所有样本时，存在的条件主要依赖以下哪类${focus}？`
  }
  return `${subject}存在的条件主要依赖以下哪类${focus}？`
}

export function buildTriggerScopePrompt(subject: string, focus: string) {
  return `请进一步确认${subject}存在条件所对应的${focus}范围。`
}

export function buildCurrentProcessTriggerScopePrompt(focus: string) {
  return buildTriggerScopePrompt('该工序', focus)
}

export function buildNamedStepTriggerScopePrompt(stepName: string, focus: string) {
  return buildTriggerScopePrompt(`“${stepName}”工序`, focus)
}

export function buildVariantScopePrompt(variantName: string, focus: string) {
  return `请确认原始工序“${variantName}”存在条件所对应的${focus}范围。`
}
