import { parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { createLatestWorkflowRequestGuard, getWorkflowDataRevision } from '@/composables/workflowDataCache'
import { resolveAvailableProjectId } from '@/composables/useCurrentProject'
import { formatGenerateErrorDetail } from '@/utils/generateRouteOutput'
import source from './GenerateView.vue?raw'

const script = ts.createSourceFile('GenerateView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)

// Exercise the actual handlers with deferred HTTP boundaries to control races.
function handlers(scope: Record<string, any>, names: string[]) {
  const code = script.statements.filter((node): node is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(node) && names.includes(node.name?.text || ''),
  ).map(node => node.getText(script)).join('\n')
  return new Function('scope', `with (scope) { ${ts.transpile(`${code}\nreturn { ${names.join(', ')} }`, { target: ts.ScriptTarget.ES2022 })} }`)(scope)
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (reason: unknown) => void
  const promise = new Promise<T>((yes, no) => { resolve = yes; reject = no })
  return { promise, resolve, reject }
}

function generationScope() {
  return {
    projectId: ref<number | null>(1), contextLoading: ref(false), canGenerate: ref(true),
    generating: ref(false), error: ref(''), result: ref<any>(null),
    workflowRevision: ref(3), factorValues: ref({ material: { grade: 'A' } }), factorMetadata: ref({}),
    inputFields: ref([{ key: 'material.grade', name: '材料' }]),
    generationRequestGuard: createLatestWorkflowRequestGuard(), contextLoadRequestId: 1, generationRequestId: 0,
    generateRoute: vi.fn(), refreshGeneratedPackageMetadata: vi.fn().mockResolvedValue(undefined),
    formatGenerateErrorDetail, console: { error: vi.fn() },
  }
}

describe('generation request lifecycle', () => {
  it('submits only once for repeated clicks before the first response', async () => {
    const pending = deferred<any>()
    const scope = generationScope()
    scope.generateRoute.mockReturnValue(pending.promise)
    const view = handlers(scope, ['runGenerate'])
    const first = view.runGenerate()
    const second = view.runGenerate()
    expect(scope.generateRoute).toHaveBeenCalledTimes(1)
    pending.resolve({ rule_package_version: 1 })
    await Promise.all([first, second])
    expect(scope.generating.value).toBe(false)
  })

  it('ignores a response after switching to another task', async () => {
    const pending = deferred<any>()
    const scope = generationScope()
    scope.generateRoute.mockReturnValue(pending.promise)
    const view = handlers(scope, ['runGenerate'])
    const running = view.runGenerate()
    scope.projectId.value = 2
    pending.resolve({ rule_package_version: 1, steps: [{ name: '旧任务工序' }] })
    await running
    expect(scope.result.value).toBeNull()
    expect(scope.refreshGeneratedPackageMetadata).not.toHaveBeenCalled()
  })

  it('ignores failures after the input context has been reloaded for the same task', async () => {
    const pending = deferred<any>()
    const scope = generationScope()
    scope.generateRoute.mockReturnValue(pending.promise)
    const view = handlers(scope, ['runGenerate'])
    const running = view.runGenerate()
    scope.contextLoadRequestId += 1
    pending.reject({ response: { data: { detail: '旧输入已过期' } } })
    await running
    expect(scope.error.value).toBe('')
  })

  it('does not apply a delayed metadata refresh after the context is reloaded', async () => {
    const pending = deferred<any>()
    const scope = {
      ...generationScope(),
      inputSchema: ref<any>({ fields: [{ key: 'old' }] }),
      packageVersion: ref(1), initializeFieldValues: vi.fn(),
      getLatestFinalizedRulePackage: vi.fn().mockReturnValue(pending.promise),
      applyRulePackageMetadata: (item: any) => { scope.packageVersion.value = item.version },
    }
    scope.generateRoute.mockResolvedValue({ rule_package_version: 1, rule_package_hash: 'old' })
    delete (scope as any).refreshGeneratedPackageMetadata
    const view = handlers(scope, ['runGenerate', 'refreshGeneratedPackageMetadata'])
    const running = view.runGenerate()
    await Promise.resolve()
    scope.contextLoadRequestId += 1
    scope.packageVersion.value = 3
    scope.inputSchema.value = { fields: [{ key: 'current' }] }
    pending.resolve({ version: 2, input_schema: { fields: [{ key: 'stale' }] } })
    await running
    expect(scope.packageVersion.value).toBe(3)
    expect(scope.inputSchema.value.fields).toEqual([{ key: 'current' }])
  })
})

describe('generated package metadata refresh', () => {
  it('exposes a newer published version so the generated result can show stale status', async () => {
    const packageVersion = ref(1)
    const inputSchema = ref<any>({ schema_version: '2.0', fields: [{ key: 'old' }] })
    const latest = { version: 2, content_hash: 'new', input_schema: { schema_version: '2.0', fields: [{ key: 'new' }] } }
    const initializeFieldValues = vi.fn()
    const view = handlers({
      projectId: ref(1), generationRequestId: 4, inputSchema, initializeFieldValues,
      getLatestFinalizedRulePackage: vi.fn().mockResolvedValue(latest),
      applyRulePackageMetadata: (item: any) => { packageVersion.value = item.version },
    }, ['refreshGeneratedPackageMetadata'])
    await view.refreshGeneratedPackageMetadata({ rule_package_version: 1, rule_package_hash: 'old' }, 1, 4, () => true)
    expect(packageVersion.value).toBe(2)
    expect(inputSchema.value.fields).toEqual([{ key: 'new' }])
    expect(initializeFieldValues).toHaveBeenCalledOnce()
  })
})

function contextScope() {
  const scope = {
    ...generationScope(),
    route: { path: '/generate', query: { project_id: '1' } }, router: { replace: vi.fn() },
    contextRequestGuard: createLatestWorkflowRequestGuard(), loadedDataRevision: -1,
    hasRulePackage: ref(false), inputSchema: ref<any>(null), projectName: ref(''),
    packageVersion: ref<number | null>(null), rulePackageRules: ref<any>(null),
    initializeFieldValues: vi.fn(), resetFieldValues: vi.fn(),
    listProjects: vi.fn().mockResolvedValue([{ id: 1, name: '任务一', workflow_revision: 3 }, { id: 2, name: '任务二', workflow_revision: 7 }]),
    getLatestFinalizedRulePackage: vi.fn(), resolveAvailableProjectId, getWorkflowDataRevision,
    console: { error: vi.fn(), warn: vi.fn() },
  }
  return scope
}

const contextHandlers = ['loadGenerateContext', 'setLoadingProject', 'clearRulePackageContext', 'resetRulePackageMetadata', 'applyRulePackageMetadata']

describe('generation context loading', () => {
  it('keeps the second task package when the first task schema arrives late', async () => {
    const oldPackage = deferred<any>()
    const scope = contextScope()
    scope.getLatestFinalizedRulePackage.mockImplementation((id: number) => id === 1
      ? oldPackage.promise
      : Promise.resolve({ version: 2, input_schema: { fields: [{ key: 'task.two' }] }, route_rules: {} }))
    const view = handlers(scope, contextHandlers)
    const oldLoad = view.loadGenerateContext()
    await Promise.resolve()
    scope.route.query.project_id = '2'
    await view.loadGenerateContext()
    oldPackage.resolve({ version: 1, input_schema: { fields: [{ key: 'task.one' }] }, route_rules: {} })
    await oldLoad
    expect(scope.projectId.value).toBe(2)
    expect(scope.projectName.value).toBe('任务二')
    expect(scope.workflowRevision.value).toBe(7)
    expect(scope.inputSchema.value.fields).toEqual([{ key: 'task.two' }])
    expect(scope.contextLoading.value).toBe(false)
  })

  it('shows a package transport failure instead of claiming there is no published package', async () => {
    const scope = contextScope()
    scope.getLatestFinalizedRulePackage.mockRejectedValue({ response: { status: 503, data: { detail: '读取规则包服务暂时不可用' } } })
    const view = handlers(scope, contextHandlers)
    await view.loadGenerateContext()
    expect(scope.error.value).toContain('读取规则包服务暂时不可用')
    expect(scope.hasRulePackage.value).toBe(false)
    expect(scope.contextLoading.value).toBe(false)
  })

  it('keeps an unpublished task quiet when the server explicitly returns 404', async () => {
    const scope = contextScope()
    scope.getLatestFinalizedRulePackage.mockRejectedValue({ response: { status: 404 } })
    const view = handlers(scope, contextHandlers)
    await view.loadGenerateContext()
    expect(scope.error.value).toBe('')
    expect(scope.hasRulePackage.value).toBe(false)
  })
})
