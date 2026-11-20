import { parse } from '@vue/compiler-sfc'
import { effectScope, nextTick, ref } from 'vue'
import ts from 'typescript'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from '@/api/client'
import { generateRoute } from '@/api/generate'
import { getLatestExecutableRuleRevision } from '@/api/executableRules'
import { clearAllWorkflowDataCache, clearWorkflowProjectDataCache, createLatestWorkflowRequestGuard, getWorkflowDataRevision } from '@/composables/workflowDataCache'
import { resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { useGenerateInputFields } from '@/composables/useGenerateInputFields'
import { formatGenerateErrorDetail } from '@/utils/generateRouteOutput'
import finalizeSource from './FinalizeView.vue?raw'
import generateSource from './GenerateView.vue?raw'

vi.mock('@/api/client', () => ({ api: { get: vi.fn(), post: vi.fn() } }))

// Execute the actual SFC handlers and lifecycle callbacks. Only HTTP, routing
// and unrelated preprocessing are supplied by the harness; no copied handlers.
function handlers(source: string, scope: Record<string, any>, names: string[]) {
  const script = ts.createSourceFile('view.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const code: string[] = []
  for (const node of script.statements) {
    if (ts.isFunctionDeclaration(node) && names.includes(node.name?.text || '')) code.push(node.getText(script))
    if (!ts.isExpressionStatement(node) || !ts.isCallExpression(node.expression)) continue
    const call = node.expression
    const name = call.expression.getText(script)
    if (names.includes('onProjectChanged') && name === 'watch' && call.arguments[0]?.getText(script).includes('route.query.project_id')) {
      code.push(`const onProjectChanged = ${call.arguments[1]!.getText(script)}`)
    }
    if (names.includes(name) && ['onActivated', 'onDeactivated'].includes(name)) {
      code.push(`const ${name} = ${call.arguments[0]!.getText(script)}`)
    }
  }
  return new Function('scope', `with(scope) { ${ts.transpile(code.join('\n'), { target: ts.ScriptTarget.ES2022 })}; return {${names.join(',')}} }`)(scope)
}

function deferred<T = any>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function finalizeScope() {
  return {
    finalizeViewActive: true, initialLoadFinished: true, loading: ref(false), hasUnsavedEdits: ref(false), conditionBusySegmentIds: ref(new Set<string>()),
    projectId: ref<number | null>(1), projectName: ref('任务一'), savedRoute: ref<any>(null), route: { path: '/finalize', query: { project_id: '1' } }, router: { replace: vi.fn() },
    workspaceRequestGuard: createLatestWorkflowRequestGuard(), invalidateRulePreprocessing: vi.fn(), recognitionTaskGuard: { cancel: vi.fn() },
    clearWorkflowProjectDataCache,
    batchParseExecutionId: 0, batchParsing: ref(false), precheckResult: ref(null), validMappingCount: ref(0),
    executableRevisionCounter: ref(0), lastExportedRulePackageVersion: ref(null), outdatedRulePackageVersion: ref(null), conditionErrors: ref({}), selectedRuleIds: ref(new Set()),
    error: ref(''), workspaceErrorTitle: ref(''), FINALIZE_VIEW_COPY: { errorTitle: '' }, templateMappingEnabled: ref(false),
    listProjects: vi.fn().mockResolvedValue([{ id: 1, name: '任务一' }, { id: 2, name: '任务二' }]), resolveAvailableProjectId,
    getSavedNormalizedRoute: vi.fn(async (id: number) => ({ route_id: id * 10, workflow_revision: 3, segments: [{ id: `task-${id}-segment` }] })),
    enterRuleFinalization: vi.fn(async (body: any) => ({
      project_id: body.project_id, route_id: body.route_id, workflow_revision: body.expected_workflow_revision,
      analysis_locked: true, analysis_locked_at: '2026-11-05T00:00:00',
    })),
    listOperations: vi.fn().mockResolvedValue([]), getSupersetRoute: vi.fn().mockResolvedValue({ superset_route: [] }),
    getLatestExecutableRuleRevision: vi.fn().mockResolvedValue(null), getConditionFieldRegistry: vi.fn().mockResolvedValue({ fields: [] }),
    operations: ref([]), supersetOperations: ref([]), conditionFields: ref([]), clearRuleEditStates: vi.fn(), cancelInlineEdit: vi.fn(),
    readDrafts: vi.fn().mockReturnValue(0), activeSegmentId: ref(''), nextTick, startRulePreprocessingForWorkspace: vi.fn(),
    setBatchNotice: vi.fn(), console: { warn: vi.fn(), error: vi.fn() },
  }
}
const finalizeNames = ['loadWorkspace', 'onActivated', 'onDeactivated', 'onProjectChanged']

beforeEach(() => { vi.resetAllMocks(); clearAllWorkflowDataCache() })
afterEach(() => vi.useRealTimers())

describe('A8 finalization workspace ownership', () => {
  it('locks analysis only after the finalization workspace loads successfully', async () => {
    const scope = { ...finalizeScope(), enterRuleFinalization: vi.fn().mockResolvedValue({
      project_id: 1, route_id: 10, workflow_revision: 3,
      analysis_locked: true, analysis_locked_at: '2026-11-05T00:00:00',
    }) }
    const view = handlers(finalizeSource, scope, finalizeNames)
    await view.loadWorkspace()
    expect(scope.enterRuleFinalization).toHaveBeenCalledWith({
      project_id: 1, route_id: 10, expected_workflow_revision: 3,
    })
    expect(scope.savedRoute.value.analysis_locked).toBe(true)
  })

  it('does not lock analysis when a required finalization resource fails to load', async () => {
    const scope = { ...finalizeScope(), enterRuleFinalization: vi.fn() }
    scope.getConditionFieldRegistry.mockRejectedValueOnce(new Error('unavailable'))
    const view = handlers(finalizeSource, scope, finalizeNames)
    await view.loadWorkspace()
    expect(scope.enterRuleFinalization).not.toHaveBeenCalled()
    expect(scope.savedRoute.value).toBeNull()
  })
  it.each([true, false])('loads task B after leaving a pending task A load (initial load finished: %s)', async (initialLoadFinished) => {
    const scope = { ...finalizeScope(), initialLoadFinished }
    const pendingA = deferred()
    const pendingB = deferred()
    scope.getSavedNormalizedRoute.mockReturnValueOnce(pendingA.promise).mockReturnValueOnce(pendingB.promise)
    const view = handlers(finalizeSource, scope, finalizeNames)
    const oldLoad = view.loadWorkspace()
    await Promise.resolve()
    view.onDeactivated()
    scope.route.path = '/upload'
    scope.route.query.project_id = '2'
    view.onProjectChanged()
    scope.route.path = '/finalize'
    view.onActivated()
    await Promise.resolve()
    pendingA.resolve({ route_id: 10, workflow_revision: 3, segments: [{ id: 'old-A' }] })
    await oldLoad
    expect(scope.getSavedNormalizedRoute).toHaveBeenCalledWith(2, true)
    expect(scope.projectId.value).toBe(2)
    expect(scope.savedRoute.value).toBeNull()
    expect(scope.loading.value).toBe(true)
    pendingB.resolve({ route_id: 20, workflow_revision: 4, segments: [{ id: 'current-B' }] })
    await vi.waitFor(() => expect(scope.savedRoute.value?.route_id).toBe(20))
    expect(scope.loading.value).toBe(false)
  })

  it('ignores A responses when the route owner changes before its watcher starts a successor', async () => {
    const scope = finalizeScope()
    const pending = deferred()
    scope.getSavedNormalizedRoute.mockReturnValueOnce(pending.promise)
    const view = handlers(finalizeSource, scope, finalizeNames)
    const loading = view.loadWorkspace()
    await Promise.resolve()
    scope.route.query.project_id = '2'
    pending.resolve({ route_id: 10, workflow_revision: 3, segments: [{ id: 'old-A' }] })
    await loading
    expect(scope.savedRoute.value).toBeNull()
    expect(scope.startRulePreprocessingForWorkspace).not.toHaveBeenCalled()
  })

  it.each(['unsaved', 'saving'])('preserves %s rules on activation and blocks a refresh', async (kind) => {
    const scope = finalizeScope()
    scope.savedRoute.value = { route_id: 10, segments: [{ id: 'local-rule' }] }
    if (kind === 'unsaved') scope.hasUnsavedEdits.value = true
    else scope.conditionBusySegmentIds.value.add('local-rule')
    const view = handlers(finalizeSource, scope, finalizeNames)
    view.onActivated()
    if (kind === 'unsaved') await view.loadWorkspace(true)
    expect(scope.savedRoute.value.segments).toEqual([{ id: 'local-rule' }])
    expect(scope.listProjects).not.toHaveBeenCalled()
  })
})

function contextScope() {
  const scope = {
    exportError: ref(''),
    projectId: ref<number | null>(1), projectName: ref('任务一'), route: { path: '/generate', query: { project_id: '1' } },
    router: { replace: vi.fn() }, generateViewActive: true, initialLoadFinished: true,
    contextLoading: ref(false), contextLoadRequestId: 0, generationRequestId: 0,
    contextRequestGuard: createLatestWorkflowRequestGuard(), generationRequestGuard: createLatestWorkflowRequestGuard(),
    loadedDataRevision: getWorkflowDataRevision(), getWorkflowDataRevision,
    error: ref(''), result: ref<any>(null), generating: ref(false), hasRulePackage: ref(false),
    executableRevision: ref<any>(null), inputsRequireRegeneration: ref(false),
    packageVersion: ref<number | null>(null), rulePackageRules: ref<Record<string, any> | null>(null), workflowRevision: ref(0), inputSchema: ref<Record<string, any> | null>(null),
    resolveAvailableProjectId, formatGenerateErrorDetail,
    listProjects: vi.fn().mockResolvedValue([{ id: 1, name: '任务一', workflow_revision: 3 }, { id: 2, name: '任务二', workflow_revision: 4 }]),
    getLatestExecutableRuleRevision,
    console: { warn: vi.fn(), error: vi.fn() },
  }
  const effects = effectScope()
  const inputs = effects.run(() => useGenerateInputFields({ ...scope, schemaLoading: scope.contextLoading }))!
  return { scope: { ...scope, ...inputs }, effects }
}
const contextNames = ['loadGenerateContext', 'setLoadingProject', 'clearRulePackageContext', 'resetRulePackageMetadata', 'applyRulePackageMetadata', 'canonicalInputSnapshot', 'generationInputSnapshot', 'onActivated', 'onDeactivated']
const rulePackage = (version = 1) => ({ id: version, revision: version, content_hash: `hash-${version}`, generation_ready: true, has_current_generation: false, package: { input_schema: { schema_version: '2.0', fields: [
  { key: 'material.grade', name: '材料', type: 'single_select', options: [{ value: '9Cr18', label: '9Cr18' }], allow_custom: false, required: true },
] }, route_rules: {} } })

describe('A9 and A10 generation context refresh', () => {
  it.each(['metadata', 'history'])('does not restore history after invalid input during %s loading', async (phase) => {
    const context = contextScope()
    const latest = deferred<any>(), historical = deferred<any>()
    const saved = { ...rulePackage(), has_current_generation: true }
    saved.package.input_schema.fields = [{ key: 'operation_grind.ra', type: 'number', unit: 'Ra', validation: { min: Number.MIN_VALUE } }] as any
    const scope = { ...context.scope, getCurrentGenerationResults: vi.fn().mockReturnValue(historical.promise) }
    try {
      scope.executableRevision.value = saved
      scope.inputSchema.value = saved.package.input_schema
      scope.initializeFieldValues()
      vi.mocked(api.get).mockReturnValueOnce(latest.promise)
      const loading = handlers(generateSource, scope, contextNames).loadGenerateContext()
      await Promise.resolve()
      if (phase === 'history') {
        latest.resolve({ data: saved })
        await vi.waitFor(() => expect(scope.getCurrentGenerationResults).toHaveBeenCalled())
      }
      scope.setFieldText('operation_grind.ra', '0')
      expect(scope.factorValues.value).toEqual({})
      latest.resolve({ data: saved })
      historical.resolve({ executable_revision_id: 1, results: [{ executable_revision_id: 1 }] })
      await loading
      expect(scope.inputsRequireRegeneration.value).toBe(true)
      expect(scope.result.value).toBeNull()
    } finally { context.effects.stop() }
  })

  it('does not restore historical results when inputs change while metadata is loading', async () => {
    const context = contextScope()
    const latest = deferred<any>()
    const scope = { ...context.scope, getCurrentGenerationResults: vi.fn().mockResolvedValue({ executable_revision_id: 1, results: [{ executable_revision_id: 1 }] }) }
    try {
      scope.executableRevision.value = rulePackage()
      scope.inputSchema.value = rulePackage().package.input_schema
      scope.initializeFieldValues()
      vi.mocked(api.get).mockReturnValueOnce(latest.promise)
      const loading = handlers(generateSource, scope, contextNames).loadGenerateContext()
      await Promise.resolve()
      scope.setFieldText('material.grade', '9Cr18')
      latest.resolve({ data: { ...rulePackage(), has_current_generation: true } })
      await loading

      expect(scope.inputsRequireRegeneration.value).toBe(true)
      expect(scope.getCurrentGenerationResults).not.toHaveBeenCalled()
      expect(scope.result.value).toBeNull()
    } finally { context.effects.stop() }
  })

  it('does not restore historical results over locally changed inputs on reactivation', async () => {
    const context = contextScope()
    const scope = { ...context.scope, getCurrentGenerationResults: vi.fn() }
    try {
      scope.executableRevision.value = rulePackage()
      scope.inputsRequireRegeneration.value = true
      vi.mocked(api.get).mockResolvedValue({ data: { ...rulePackage(), has_current_generation: true } })

      await handlers(generateSource, scope, contextNames).loadGenerateContext()

      expect(scope.inputsRequireRegeneration.value).toBe(true)
      expect(scope.getCurrentGenerationResults).not.toHaveBeenCalled()
      expect(scope.result.value).toBeNull()
    } finally { context.effects.stop() }
  })

  it('does not restore a historical route generated from different inputs', async () => {
    const context = contextScope()
    const saved = { ...rulePackage(), has_current_generation: true }
    ;(saved.package as any).input_schema.fields[0].options = [
      { value: '9Cr18', label: '9Cr18' },
      { value: '95Cr18', label: '95Cr18' },
    ]
    const scope = {
      ...context.scope,
      getCurrentGenerationResults: vi.fn().mockResolvedValue({
        executable_revision_id: saved.id,
        results: [{ executable_revision_id: saved.id, input_factors: {
          factor_values: { material: { grade: '95Cr18' } },
          input_metadata: { 'material.grade': { origin: 'manual', evidence: [] } },
        }, steps: [{ name: 'IT10路线' }] }],
      }),
    }
    try {
      scope.executableRevision.value = saved
      scope.inputSchema.value = saved.package.input_schema
      scope.initializeFieldValues()
      scope.setFieldText('material.grade', '9Cr18')
      scope.getLatestExecutableRuleRevision = vi.fn().mockResolvedValue(saved)

      await handlers(generateSource, scope, contextNames).loadGenerateContext()

      expect(scope.getCurrentGenerationResults).toHaveBeenCalled()
      expect(scope.inputsRequireRegeneration.value).toBe(true)
      expect(scope.result.value).toBeNull()
    } finally { context.effects.stop() }
  })

  it('retries B when an old A generation invalidates B package loading', async () => {
    const { scope, effects } = contextScope()
    try {
      scope.route.query.project_id = '2'
      const oldGeneration = deferred()
      vi.mocked(api.post).mockReturnValueOnce(oldGeneration.promise)
      const generatingA = generateRoute({ project_id: 1, expected_workflow_revision: 3, factor_values: {} })
      const pendingB = deferred()
      vi.mocked(api.get).mockReturnValueOnce(pendingB.promise).mockResolvedValue({ data: rulePackage(2) })
      const view = handlers(generateSource, scope, contextNames)
      const loadingB = view.loadGenerateContext()
      await Promise.resolve()
      oldGeneration.resolve({ data: { rule_package_version: 1 } })
      await generatingA
      pendingB.resolve({ data: rulePackage(1) })
      await loadingB
      expect(scope.hasRulePackage.value).toBe(true)
      expect(scope.packageVersion.value).toBe(2)
      expect(scope.contextLoading.value).toBe(false)
      expect(scope.error.value).toBe('')
      expect(api.get).toHaveBeenLastCalledWith('/api/extract/executable-rule-revisions/latest', { params: { project_id: 2 } })
    } finally { effects.stop() }
  })

  it('reports repeated invalidation instead of looping forever or claiming no package exists', async () => {
    const { scope, effects } = contextScope()
    try {
      vi.mocked(api.get).mockImplementation(async () => {
        clearAllWorkflowDataCache()
        return { data: rulePackage() }
      })
      const view = handlers(generateSource, scope, contextNames)
      await view.loadGenerateContext()
      expect(scope.contextLoading.value).toBe(false)
      expect(scope.error.value).toContain('刷新')
      expect(vi.mocked(api.get).mock.calls).toHaveLength(2)
    } finally { effects.stop() }
  })

  it('does not let a superseded B request retry over the current task C', async () => {
    const { scope, effects } = contextScope()
    try {
      const pending = deferred()
      vi.mocked(api.get).mockReturnValueOnce(pending.promise).mockResolvedValue({ data: rulePackage(2) })
      const view = handlers(generateSource, scope, contextNames)
      const old = view.loadGenerateContext()
      await Promise.resolve()
      scope.route.query.project_id = '2'
      clearAllWorkflowDataCache()
      await view.loadGenerateContext()
      pending.resolve({ data: rulePackage(1) })
      await old
      expect(scope.projectId.value).toBe(2)
      expect(scope.packageVersion.value).toBe(2)
      expect(scope.error.value).toBe('')
      expect(vi.mocked(api.get).mock.calls).toHaveLength(2)
    } finally { effects.stop() }
  })

  it('reads a package published in another window after cache TTL and displays its new required field', async () => {
    vi.useFakeTimers()
    const { scope, effects } = contextScope()
    try {
      vi.mocked(api.get).mockResolvedValueOnce({ data: rulePackage(1) }).mockResolvedValue({ data: {
        ...rulePackage(2), package: { ...rulePackage(2).package, input_schema: { schema_version: '2.0', fields: [
          { key: 'material.grade', name: '材料', type: 'single_select', options: [{ value: '9Cr18', label: '9Cr18' }], required: true },
          { key: 'new.required', name: '新必填参数', type: 'text', required: true },
        ] } },
      } })
      const view = handlers(generateSource, scope, contextNames)
      await view.loadGenerateContext()
      scope.setFieldText('material.grade', '9Cr18')
      view.onDeactivated()
      vi.advanceTimersByTime(60_000)
      view.onActivated()
      // Flush Promise continuations without advancing wall-clock cache TTL.
      for (let turn = 0; turn < 12; turn += 1) await Promise.resolve()
      expect(scope.packageVersion.value).toBe(2)
      expect(scope.inputFields.value.map(field => field.key)).toEqual(['material.grade', 'new.required'])
      expect(scope.fieldValues.value['material.grade']).toBe('9Cr18')
      expect(scope.canGenerate.value).toBe(false)
      expect(vi.mocked(api.get).mock.calls).toHaveLength(2)
    } finally { effects.stop() }
  })

  it('rechecks the executable revision and preserves valid user input on reactivation', async () => {
    const { scope, effects } = contextScope()
    try {
      vi.mocked(api.get).mockResolvedValue({ data: rulePackage() })
      const view = handlers(generateSource, scope, contextNames)
      await view.loadGenerateContext()
      scope.setFieldText('material.grade', '9Cr18')
      view.onDeactivated()
      view.onActivated()
      for (let turn = 0; turn < 12; turn += 1) await Promise.resolve()
      expect(scope.fieldValues.value['material.grade']).toBe('9Cr18')
      expect(scope.canGenerate.value).toBe(true)
      expect(vi.mocked(api.get).mock.calls).toHaveLength(2)
    } finally { effects.stop() }
  })
})
