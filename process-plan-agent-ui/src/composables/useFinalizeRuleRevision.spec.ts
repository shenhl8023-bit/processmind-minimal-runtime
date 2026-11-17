import { computed, ref, effectScope } from 'vue'
import { describe, expect, it, vi, onTestFinished, beforeEach } from 'vitest'
import { workflowResetSignal } from './workflowResetState'
const mocks = vi.hoisted(() => ({ compileRulePackage: vi.fn() }))
vi.mock('@/api/rulePackages', async importOriginal => ({ ...await importOriginal<any>(), compileRulePackage: mocks.compileRulePackage }))
import { useFinalizeRuleRevision } from './useFinalizeRuleRevision'

function setup() {
  const card: any = { segment: { id: 'p', export_process_id: 'p', normalized_step_name: '包装', sequence: 1, source_operation_ids: [], doc_coverage: { hit_docs: 1, total_docs: 1 } }, conditionText: '固定安排包装', factorNames: [], userAnswerLabels: [], conditionReview: null }
  const cards = ref([card])
  const projectId = ref<number | null>(4)
  const saveRevision = vi.fn().mockResolvedValue({ id: 5, version: 1 })
  const onSaved = vi.fn()
  const onIssue = vi.fn()
  const savedRoute = ref<any>({ route_id: 9, workflow_revision: 2 })
  const options = { projectId, projectName: ref('test'), savedRoute, cards: computed(() => cards.value), unsavedCards: computed(() => []), savingRuleIds: ref(new Set<string>()), conditionFields: ref([]), displayName: () => '包装', phaseLabel: () => '', primarySteps: () => [], attachedSteps: () => [], saveRevision, onSaved, onIssue }
  const scope = effectScope()
  const revision = scope.run(() => useFinalizeRuleRevision(options))!
  onTestFinished(() => scope.stop())
  return { ...revision, options, saveRevision, onSaved, onIssue, projectId, cards, scope }
}
describe('prepare rules for route validation', () => {
  beforeEach(() => { workflowResetSignal.value = null; mocks.compileRulePackage.mockReset() })
  it('compiles the current core without template mappings and saves an executable revision without exporting', async () => {
    mocks.compileRulePackage.mockResolvedValue({ validation: { valid: true }, content_hash: 'hash', package: { manifest: {}, factor_dictionary: {}, input_schema: {}, route_catalog: { processes: [] }, route_rules: { rules: [] }, test_cases: [] } })
    const s = setup()
    await s.prepareValidation()
    expect(mocks.compileRulePackage.mock.calls.slice(-1)[0]![0].processes.every((p: any) => !p.template_group_aliases?.length)).toBe(true)
    expect(s.saveRevision).toHaveBeenCalledWith(expect.objectContaining({ project_id: 4, route_version_id: 9, expected_workflow_revision: 2, schema_version: '2.0' }))
    expect(s.onSaved).toHaveBeenCalledWith({ id: 5, version: 1 })
  })
  it('does not save compiled results after changing projects', async () => {
    let finish!: (value: any) => void
    mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const s = setup()
    const running = s.prepareValidation()
    s.projectId.value = 6
    finish({ validation: { valid: true }, package: {} })
    await running
    expect(s.saveRevision).not.toHaveBeenCalled()
    expect(s.onSaved).not.toHaveBeenCalled()
    expect(s.preparingValidation.value).toBe(false)
  })
})


describe('validation response ownership', () => {
  beforeEach(() => { workflowResetSignal.value = null; mocks.compileRulePackage.mockReset() })
  const compiled = { validation: { valid: true }, package: { manifest: {}, factor_dictionary: {}, input_schema: {}, route_catalog: {}, route_rules: {}, test_cases: [] } }
  it.each(['compile', 'save'].flatMap(stage => ['reset signal', 'disposed scope', 'same-text token'].flatMap(change =>
    ['success', 'failure'].map(outcome => ({ stage, change, outcome })),
  )))('ignores stale $outcome during $stage after $change', async ({ stage, change, outcome }) => {
    let finish!: (value: any) => void
    const pending = new Promise((resolve, reject) => { finish = outcome === 'success' ? resolve : reject })
    const state = setup()
    state.cards.value[0]!.conditionReview = { review_token: 'a'.repeat(64) }
    if (stage === 'compile') mocks.compileRulePackage.mockReturnValueOnce(pending)
    else {
      mocks.compileRulePackage.mockResolvedValueOnce(compiled)
      state.saveRevision.mockReturnValueOnce(pending)
    }
    const running = state.prepareValidation()
    if (stage === 'save') await vi.waitFor(() => expect(state.saveRevision).toHaveBeenCalledOnce())
    if (change === 'reset signal') workflowResetSignal.value = { projectId: 4, fromStep: 3, workflowRevision: 3, emittedAt: 100 }
    else if (change === 'disposed scope') state.scope.stop()
    else state.cards.value[0]!.conditionReview = { review_token: 'b'.repeat(64) }
    finish(outcome === 'failure' ? new Error('late response') : stage === 'compile' ? compiled : { id: 5, revision: 1 })
    await running
    expect(state.onSaved).not.toHaveBeenCalled()
    expect(state.onIssue).not.toHaveBeenCalled()
    if (stage === 'compile') expect(state.saveRevision).not.toHaveBeenCalled()
  })
})
