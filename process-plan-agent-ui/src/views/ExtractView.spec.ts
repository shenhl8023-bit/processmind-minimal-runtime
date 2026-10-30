import { parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import source from './ExtractView.vue?raw'

const script = ts.createSourceFile('ExtractView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

function initializer(scope: Record<string, any>, name = 'initializeExtractView') {
  const declaration = script.statements.find((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && node.name?.text === name,
  )!
  const code = ts.transpile(declaration.getText(script) + '; return ' + name, { target: ts.ScriptTarget.ES2022 })
  return new Function('scope', `with (scope) { ${code} }`)(scope) as () => Promise<void>
}

describe('entering analysis after route generation', () => {
  function entryScope() {
    return {
      canEnterRouteFactorAnalysis: ref(true), projectId: ref<number | null>(6), workflowRevision: ref(3),
      routeFactorAnalysisEntering: ref(false), errorMsg: ref(''), routeMergeNotice: ref(''),
      buildRouteResultSaveFingerprint: () => 'same-layout', lastSavedRouteResultFingerprint: ref(''),
      routeResultMatchesBackendWorkspace: () => true, lastInitializedDataRevision: ref(0),
      getWorkflowDataRevision: () => 4,
      getSavedNormalizedRoute: vi.fn(async () => ({ project_id: 6, workflow_revision: 3, segments: [{ id: 's1' }] })),
      saveRouteMergeWorkspaceBase: vi.fn(async () => true),
      router: { push: vi.fn(async () => {}) },
    }
  }
  it('materializes a durable route even when the generated workspace layout already matches', async () => {
    const scope = entryScope()
    await initializer(scope, 'openRouteFactorAnalysis')()
    expect(scope.getSavedNormalizedRoute).toHaveBeenCalledWith(6, true)
    expect(scope.router.push).toHaveBeenCalledWith({ path: '/analysis', query: { project_id: '6' } })
  })
  it('stays on the route with a recovery message if materialization fails', async () => {
    const scope = entryScope()
    scope.getSavedNormalizedRoute.mockRejectedValue(new Error('offline'))
    await expect(initializer(scope, 'openRouteFactorAnalysis')()).resolves.toBeUndefined()
    expect(scope.router.push).not.toHaveBeenCalled()
    expect(scope.errorMsg.value).toContain('保存')
  })
  it('does not navigate another project when durable route loading completes late', async () => {
    const scope = entryScope()
    const pending = deferred<any>()
    scope.getSavedNormalizedRoute.mockReturnValue(pending.promise)
    const loading = initializer(scope, 'openRouteFactorAnalysis')()
    scope.projectId.value = 7
    pending.resolve({ project_id: 6, workflow_revision: 3, segments: [{ id: 's1' }] })
    await loading
    expect(scope.router.push).not.toHaveBeenCalled()
  })
})

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

const projects = [
  { id: 1, status: 'ROUTE_SET_READY', workflow_revision: 3 },
  { id: 2, status: 'ROUTE_SET_READY', workflow_revision: 7 },
]

function createScope() {
  const scope = {
    route: { path: '/extract', query: { project_id: '1', resume: '', from: '' } },
    router: { replace: vi.fn(async (..._args: any[]) => {}) }, extractInitializeRequestId: 0,
    projectId: ref<number | null>(null), workflowRevision: ref(0), lastInitializedDataRevision: ref(-1),
    status: ref('idle'), errorMsg: ref(''), routeMergePendingCount: ref(0),
    resolveCurrentProjectId: (id: string) => id || '1', getWorkflowDataRevision: () => 4,
    resolveAvailableProjectId: (id: string, items: typeof projects) => String(items.find(project => project.id === Number(id))?.id || items[0]?.id || ''),
    listProjects: vi.fn(async () => projects), loadRouteRulesResults: vi.fn(async () => { scope.status.value = 'done' }),
    hasInMemoryRouteMergeWorkspace: () => false, restoreRouteMergeWorkspaceFromMemory: vi.fn(),
    syncRouteMergePreviewDraftFromNormalizedRoute: vi.fn(), resetRouteMergePreviewDraft: vi.fn(),
    pollExtractionTask: vi.fn(), console: { error: vi.fn() },
  }
  return scope
}

describe('extraction view initialization request ownership', () => {
  it('keeps task B when task A project lookup arrives after B initialization completes', async () => {
    const oldProjects = deferred<typeof projects>()
    const scope = createScope()
    scope.listProjects.mockReturnValueOnce(oldProjects.promise)
    const initialize = initializer(scope)
    const old = initialize()
    scope.route.query.project_id = '2'
    await initialize()
    oldProjects.resolve(projects)
    await old

    expect(scope.projectId.value).toBe(2)
    expect(scope.workflowRevision.value).toBe(7)
    expect(scope.route.query.project_id).toBe('2')
    expect(scope.loadRouteRulesResults).toHaveBeenCalledTimes(1)
  })

  it('ignores a late project lookup when the user leaves the extraction page', async () => {
    const pending = deferred<typeof projects>()
    const scope = createScope()
    scope.listProjects.mockReturnValueOnce(pending.promise)
    const initialize = initializer(scope)
    const old = initialize()
    scope.route.path = '/analysis'
    pending.resolve(projects)
    await old

    expect(scope.projectId.value).toBeNull()
    expect(scope.loadRouteRulesResults).not.toHaveBeenCalled()
  })

  it('does not restore a stale resume draft after task B has finished loading', async () => {
    const oldLoad = deferred<void>()
    const scope = createScope()
    scope.route.query.resume = 'route_merge'
    scope.loadRouteRulesResults.mockReturnValueOnce(oldLoad.promise)
    const initialize = initializer(scope)
    const old = initialize()
    await Promise.resolve()
    scope.route.query.project_id = '2'
    await initialize()
    expect(scope.syncRouteMergePreviewDraftFromNormalizedRoute).toHaveBeenCalledTimes(1)
    oldLoad.resolve()
    await old

    expect(scope.syncRouteMergePreviewDraftFromNormalizedRoute).toHaveBeenCalledTimes(1)
    expect(scope.projectId.value).toBe(2)
  })

  it('keeps current success when an obsolete initialization later fails', async () => {
    const oldProjects = deferred<typeof projects>()
    const scope = createScope()
    scope.listProjects.mockReturnValueOnce(oldProjects.promise)
    const initialize = initializer(scope)
    const old = initialize()
    scope.route.query.project_id = '2'
    await initialize()
    oldProjects.reject(new Error('old network failure'))
    await old

    expect(scope.status.value).toBe('done')
    expect(scope.errorMsg.value).toBe('')
  })

  it('loads the resolved task after its own canonical query replacement', async () => {
    const scope = createScope()
    scope.route.query.project_id = ''
    scope.router.replace.mockImplementation(async (...args: any[]) => {
      scope.route.query = { ...scope.route.query, ...args[0].query }
    })
    await initializer(scope)()

    expect(scope.route.query.project_id).toBe('1')
    expect(scope.projectId.value).toBe(1)
    expect(scope.workflowRevision.value).toBe(3)
    expect(scope.loadRouteRulesResults).toHaveBeenCalledTimes(1)
    expect(scope.status.value).toBe('done')
  })

  it('keeps mounted and activated overlap on the newest initialization', async () => {
    const oldProjects = deferred<typeof projects>()
    const scope = createScope()
    scope.listProjects.mockReturnValueOnce(oldProjects.promise)
    const initialize = initializer(scope)
    const mounted = initialize()
    await initialize()
    oldProjects.resolve(projects)
    await mounted

    expect(scope.projectId.value).toBe(1)
    expect(scope.status.value).toBe('done')
    expect(scope.errorMsg.value).toBe('')
    expect(scope.loadRouteRulesResults).toHaveBeenCalledTimes(1)
  })

  it('lets canonical replacement trigger a newer initialization without a false workspace error', async () => {
    const scope = createScope()
    scope.route.query.project_id = ''
    const initialize = initializer(scope)
    scope.router.replace.mockImplementation(async (...args: any[]) => {
      scope.route.query = { ...scope.route.query, ...args[0].query }
      await initialize()
    })
    await initialize()

    expect(scope.projectId.value).toBe(1)
    expect(scope.workflowRevision.value).toBe(3)
    expect(scope.route.query.project_id).toBe('1')
    expect(scope.loadRouteRulesResults).toHaveBeenCalledTimes(1)
    expect(scope.status.value).toBe('done')
    expect(scope.errorMsg.value).toBe('')
  })
})
