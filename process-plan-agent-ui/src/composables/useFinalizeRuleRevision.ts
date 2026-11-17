import { ref, watch, getCurrentScope, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { compileRulePackage, type CanonicalConditionField } from '@/api/rulePackages'
import type { SavedNormalizedRouteVersionResult, saveFinalizedRulePackage } from '@/api/extract'
import type { FinalizeCard } from './finalizeViewHelpers'
import { buildCompileRequestFromCards, exportBlockingCards } from '@/utils/finalizeRulePackage'
import type { FinalRouteStep } from './finalRouteSteps'
import { workflowResetSignal } from './workflowResetState'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]
type Payload = Parameters<typeof saveFinalizedRulePackage>[0]
export function useFinalizeRuleRevision<T>(options: {
  projectId: Ref<number | null>; projectName: Ref<string>; savedRoute: Ref<SavedNormalizedRouteVersionResult | null>
  cards: ComputedRef<FinalizeCard[]>; unsavedCards: ComputedRef<FinalizeCard[]>; savingRuleIds: Ref<Set<string>>
  conditionFields: Ref<CanonicalConditionField[]>; displayName: (segment: Segment) => string
  phaseLabel: (segment: any) => string; primarySteps: (segment: any) => string[]; attachedSteps: (segment: any) => string[]
  finalSteps?: (segment: Segment) => FinalRouteStep[]
  saveRevision: (payload: Payload) => Promise<T>; onSaved: (revision: T) => void | Promise<void>
  onIssue: (message: string) => void; onBlocked?: (cards: FinalizeCard[]) => void | Promise<void>
}) {
  const preparingValidation = ref(false)
  let stateVersion = 0
  let active = true
  if (getCurrentScope()) onScopeDispose(() => { active = false })
  const signature = () => JSON.stringify([options.projectId.value, options.savedRoute.value, options.projectName.value, options.cards.value, options.conditionFields.value, options.unsavedCards.value.length, [...options.savingRuleIds.value]])
  watch(signature, () => { stateVersion++ }, { flush: 'sync' })
  async function prepareValidation() {
    if (!active || preparingValidation.value || !options.projectId.value || !options.savedRoute.value) return
    if (options.unsavedCards.value.length || options.savingRuleIds.value.size) { options.onIssue('请先保存或取消当前修改。'); return }
    const blocked = exportBlockingCards(options.cards.value)
    if (blocked.length) { options.onIssue(`还有${blocked.length}道工序规则需要确认。`); await options.onBlocked?.(blocked); return }
    const route = options.savedRoute.value, projectId = options.projectId.value, version = stateVersion, snapshot = signature()
    const current = () => {
      const reset = workflowResetSignal.value
      return active && version === stateVersion && signature() === snapshot
        && (!reset || reset.projectId !== projectId || reset.workflowRevision <= route.workflow_revision)
    }
    if (!current()) return
    preparingValidation.value = true
    try {
      const request = buildCompileRequestFromCards({
        projectId, packageName: `${options.projectName.value || '工艺规程'}_规则`, routeVersionId: route.route_id,
        cards: options.cards.value, displayName: options.displayName, phaseLabel: options.phaseLabel,
        primarySteps: options.primarySteps, attachedSteps: options.attachedSteps, finalSteps: options.finalSteps,
        conditionFields: options.conditionFields.value, includeTemplateMappings: false,
      })
      const compiled = await compileRulePackage(request)
      if (!current()) return
      if (!compiled.validation.valid) { options.onIssue((compiled.validation.errors || []).map(e => e.message).join('；') || '当前规则尚未通过校验。'); return }
      const saved = await options.saveRevision({
        project_id: projectId, expected_workflow_revision: route.workflow_revision, route_version_id: route.route_id,
        package_name: request.package_name, schema_version: '2.0', manifest: compiled.package.manifest,
        factor_dictionary: compiled.package.factor_dictionary, input_schema: compiled.package.input_schema,
        route_catalog: compiled.package.route_catalog, route_rules: compiled.package.route_rules,
        test_cases: compiled.package.test_cases, validation_report: compiled.validation, rule_report_md: '',
      })
      if (current()) await options.onSaved(saved)
    } catch (e: any) {
      if (!current()) return
      const detail = e?.response?.data?.detail
      options.onIssue(typeof detail === 'string' ? detail : detail?.message || '保存可验证规则失败，请刷新后重试。')
    } finally { preparingValidation.value = false }
  }
  return { preparingValidation, prepareValidation }
}
