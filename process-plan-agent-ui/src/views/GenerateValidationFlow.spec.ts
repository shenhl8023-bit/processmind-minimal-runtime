import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { computed, effectScope, nextTick, ref, watch } from 'vue'
import { expect, it, vi } from 'vitest'
import source from './GenerateView.vue?raw'
import { createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'
import { useGenerateInputFields } from '@/composables/useGenerateInputFields'
const script = ts.createSourceFile('Generate.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
function run(scope: Record<string, any>, name: string) {
  scope.inputsRequireRegeneration ??= ref(false)
  const fn = script.statements.find((n): n is ts.FunctionDeclaration => ts.isFunctionDeclaration(n) && n.name?.text === name)
  if (!fn) throw new Error(`missing ${name}`)
  return new Function('scope', `with(scope) { ${ts.transpile(fn.getText(script))}; return ${name} }`)(scope)
}

function parameterWatch(scope: Record<string, any>) {
  const watchers = script.statements.filter(node => ts.isExpressionStatement(node)
    && ts.isCallExpression(node.expression) && node.expression.expression.getText(script) === 'watch'
    && node.expression.arguments[0]?.getText(script).includes('factorValues'))
  return new Function('scope', `with(scope) { ${ts.transpile(watchers.map(node => node.getText(script)).join('\n'))} }`)({ ...scope, watch })
}

function exportAvailability(scope: Record<string, any>) {
  const declaration = script.statements.find(node => ts.isVariableStatement(node)
    && node.declarationList.declarations.some(item => item.name.getText(script) === 'canExportRules'))!
  return new Function('scope', `with(scope) { ${ts.transpile(declaration.getText(script))}; return canExportRules }`)({ ...scope, computed })
}

function generationScope() {
  return {
    projectId: ref(1), contextLoading: ref(false), generating: ref(false), canGenerate: ref(true),
    executableRevision: ref({ id: 7, revision: 3, content_hash: 'hash', generation_ready: true, has_current_generation: true }),
    generationRequestGuard: createLatestWorkflowRequestGuard(), contextLoadRequestId: 1, generationRequestId: 0,
    error: ref(''), result: ref<any>({ executable_revision_id: 7, executable_content_hash: 'hash', steps: [{ name: '磨孔' }] }),
    workflowRevision: ref(2), fieldValues: ref({ it: 6 }), factorValues: ref({ it: 6 }), factorMetadata: ref({}),
    inputsRequireRegeneration: ref(false), refreshGeneratedPackageMetadata: vi.fn(),
    formatGenerateErrorDetail: String, inputFields: ref([]),
    generateRoute: vi.fn(),
  }
}

it.each(['restored', 'pending'])('invalidates a %s result when an empty numeric input becomes invalid', async (phase) => {
  const effects = effectScope()
  const base = generationScope()
  const inputs = effects.run(() => useGenerateInputFields({
    inputSchema: ref({ schema_version: '2.0', fields: [{ key: 'operation_grind.ra', type: 'number', unit: 'Ra', validation: { min: Number.MIN_VALUE } }] }),
    hasRulePackage: ref(true), projectId: base.projectId, schemaLoading: base.contextLoading,
  }))!
  inputs.initializeFieldValues()
  const scope = { ...base, ...inputs }
  let finish!: (value: any) => void
  scope.generateRoute.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  try {
    effects.run(() => parameterWatch(scope))
    expect(exportAvailability(scope).value).toBe(true)
    const pending = phase === 'pending' ? run(scope, 'runGenerate')() : undefined
    scope.setFieldText('operation_grind.ra', '0')
    expect(scope.canGenerate.value).toBe(false)
    expect(scope.factorValues.value).toEqual({})
    if (pending) {
      finish({ executable_revision_id: 7, executable_content_hash: 'hash', steps: [{ name: '旧路线' }] })
      await pending
    }
    expect(scope.result.value).toBeNull()
    expect(exportAvailability(scope).value).toBe(false)
  } finally { effects.stop() }
})

it('clears an old route and blocks export when the displayed part parameters change', async () => {
  const scope = generationScope(), effects = effectScope()
  try {
    effects.run(() => parameterWatch(scope))
    const canExport = exportAvailability(scope)
    expect(canExport.value).toBe(true)
    scope.factorValues.value.it = 10
    await nextTick()
    expect(scope.result.value).toBeNull()
    expect(canExport.value).toBe(false)
  } finally { effects.stop() }
})

it('discards a late response for earlier parameters, then accepts a generation for the current inputs', async () => {
  const scope = generationScope(), effects = effectScope()
  let finish!: (value: any) => void
  scope.generateRoute.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
  try {
    effects.run(() => parameterWatch(scope))
    const pending = run(scope, 'runGenerate')()
    scope.factorValues.value.it = 10
    await nextTick()
    finish({ executable_revision_id: 7, executable_content_hash: 'hash', steps: [{ name: '磨孔' }] })
    await pending
    expect(scope.result.value).toBeNull()
    expect(scope.refreshGeneratedPackageMetadata).not.toHaveBeenCalled()
    expect(exportAvailability(scope).value).toBe(false)
    scope.generateRoute.mockResolvedValueOnce({ executable_revision_id: 7, executable_content_hash: 'hash', steps: [{ name: '车孔' }] })
    await run(scope, 'runGenerate')()
    expect(scope.result.value.steps[0].name).toBe('车孔')
    expect(exportAvailability(scope).value).toBe(true)
  } finally { effects.stop() }
})
it('uses the selected executable revision for route generation without publishing', async () => {
  const generateRoute = vi.fn().mockResolvedValue({ executable_revision_id: 7, executable_content_hash: 'hash', steps: [] })
  const scope = { projectId: ref(1), contextLoading: ref(false), generating: ref(false), canGenerate: ref(true), executableRevision: ref({ id: 7, revision: 3, content_hash: 'hash', generation_ready: true }), generationRequestGuard: createLatestWorkflowRequestGuard(), contextLoadRequestId: 1, generationRequestId: 0, error: ref(''), result: ref(null), workflowRevision: ref(2), fieldValues: ref({}), factorValues: ref({}), factorMetadata: ref({}), generateRoute, refreshGeneratedPackageMetadata: vi.fn(), formatGenerateErrorDetail: String, inputFields: ref([]) }
  await run(scope, 'runGenerate')()
  expect(generateRoute).toHaveBeenCalledWith(expect.objectContaining({ executable_revision_id: 7 }))
})
it('provides package export above and optional mapping in bottom navigation after validation', () => {
  const template = parse(source).descriptor.template!.content
  expect(template).toContain('@click="exportRulePackage"')
  expect(template).toContain('继续分组模板映射（可选）')
  expect(template).toContain(':next-disabled="!canExportRules"')
  expect(template).not.toContain('templateMappingEnabled ? 5 : 4')
})
it('exports only the exact currently validated rule core', async () => {
  const exported = { id: 10 }
  const exportExecutableRuleRevision = vi.fn().mockResolvedValue(exported), downloadValidatedRulePackage = vi.fn()
  const scope = { canExportRules: computed(() => true), executableRevision: ref({ id: 7, content_hash: 'hash' }), exportingRules: ref(false), projectId: ref(1), workflowRevision: ref(2), contextLoadRequestId: 1, exportExecutableRuleRevision, downloadValidatedRulePackage, projectName: ref('任务'), error: ref(''), formatGenerateErrorDetail: String }
  await run(scope, 'exportRulePackage')()
  expect(exportExecutableRuleRevision).toHaveBeenCalledWith(7, { project_id: 1, expected_workflow_revision: 2, expected_content_hash: 'hash', include_template_mapping: false })
  expect(downloadValidatedRulePackage).toHaveBeenCalledWith(exported, '任务', { isCurrent: expect.any(Function) })
})
it('reports asynchronous export conversion or identity allocation failures', async () => {
  const failure = Promise.reject(new Error('编号分配失败，请重试'))
  void failure.catch(() => {})
  const scope = { canExportRules: computed(() => true), executableRevision: ref({ id: 7, content_hash: 'hash' }), exportingRules: ref(false), projectId: ref(1), workflowRevision: ref(2), contextLoadRequestId: 1, exportExecutableRuleRevision: vi.fn().mockResolvedValue({ id: 10 }), downloadValidatedRulePackage: vi.fn().mockReturnValue(failure), projectName: ref('任务'), error: ref(''), formatGenerateErrorDetail: String }
  await run(scope, 'exportRulePackage')()
  expect(scope.error.value).toContain('编号分配失败')
  expect(scope.exportingRules.value).toBe(false)
})
it('cancels a pending identity download after the validation context changes', async () => {
  let release!: () => void
  const allocation = new Promise<void>(resolve => { release = resolve })
  const delivered = vi.fn()
  const downloadValidatedRulePackage = vi.fn(async (_saved, _name, options) => {
    await allocation
    if (!options?.isCurrent || options.isCurrent()) delivered()
  })
  const scope = { canExportRules: computed(() => true), executableRevision: ref({ id: 7, content_hash: 'hash' }), exportingRules: ref(false), projectId: ref(1), workflowRevision: ref(2), contextLoadRequestId: 1, exportExecutableRuleRevision: vi.fn().mockResolvedValue({ id: 10 }), downloadValidatedRulePackage, projectName: ref('任务'), error: ref(''), formatGenerateErrorDetail: String }
  const pending = run(scope, 'exportRulePackage')()
  await Promise.resolve()
  scope.contextLoadRequestId++
  release()
  await pending
  expect(delivered).not.toHaveBeenCalled()
})
