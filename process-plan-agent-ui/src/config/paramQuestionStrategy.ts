import rawStrategy from './paramQuestionStrategy.json'
import { normalizeCoverageReasonPriority } from './questionPriorityPolicy'

export type CoverageRootReasonValue =
  | 'coverage_reason::material'
  | 'coverage_reason::structure'
  | 'coverage_reason::size'
  | 'coverage_reason::blank'
  | 'coverage_reason::requirement'

export type CoverageOperationFamily =
  | 'blank_prep'
  | 'heat_treat'
  | 'hole_process'
  | 'turning_shape'
  | 'surface_check'
  | 'other'

interface FamilyRule {
  family: CoverageOperationFamily
  label: string
  patterns: string[]
}

interface ParamQuestionStrategy {
  familyRules: FamilyRule[]
  rootReasonPriority: Record<CoverageOperationFamily, CoverageRootReasonValue[]>
  terminalQuestionTypes: string[]
}

const strategy = rawStrategy as ParamQuestionStrategy
const familyRules = strategy.familyRules || []
const rootReasonPriority = strategy.rootReasonPriority || {} as Record<CoverageOperationFamily, CoverageRootReasonValue[]>
const terminalQuestionTypes = new Set(strategy.terminalQuestionTypes || [])

export function classifyCoverageOperationFamily(stepName?: string | null): CoverageOperationFamily {
  const text = String(stepName || '').trim()
  if (!text) return 'other'
  for (const rule of familyRules) {
    if ((rule.patterns || []).some(pattern => pattern && text.includes(pattern))) {
      return rule.family
    }
  }
  return 'other'
}

export function coverageFamilyLabel(family: CoverageOperationFamily): string {
  return familyRules.find(rule => rule.family === family)?.label || '当前工序'
}

export function prioritizedCoverageReasons(stepName?: string | null): CoverageRootReasonValue[] {
  const family = classifyCoverageOperationFamily(stepName)
  const baseReasons = rootReasonPriority[family]
    || rootReasonPriority.other
    || ['coverage_reason::material', 'coverage_reason::structure', 'coverage_reason::size']
  return normalizeCoverageReasonPriority(baseReasons, { family }) as CoverageRootReasonValue[]
}

export function isTerminalCoverageQuestionType(questionType?: string | null): boolean {
  return terminalQuestionTypes.has(String(questionType || '').trim())
}
