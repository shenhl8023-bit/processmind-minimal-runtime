import { compileTemplate, parse } from '@vue/compiler-sfc'
import * as Vue from 'vue'
import { transformSync } from 'esbuild'
import { computed, ref } from 'vue'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { exportBlockingCards, isExplicitMainlineInstruction, finalizeRuleMode } from '@/utils/finalizeRulePackage'
import { openFinalizePrecheckDialog } from '@/composables/finalizePrecheckDialog'
import { confirmFinalizeBatch } from '@/composables/finalizeBatchConfirmation'
import { isWorkflowRevisionConflict } from '@/composables/workflowResetState'
import { clearWorkflowProjectDataCache, createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'
import { isPublishedTemplateMappingCurrent } from '@/utils/finalizePublishedMapping'
import * as processConfigurationEditor from '@/utils/processConfigurationEditor'
import { requiresConfirmedUserRule, requiresServerRuleConditionRefresh, hasCurrentConfirmedUserRule } from '@/utils/finalizeRulePackage'
import { buildFinalizeCards } from '@/composables/finalizeViewHelpers'
import { buildRulePreprocessingTriggerKey } from '@/composables/rulePreprocessingTrigger'
import { createBackgroundTaskGuard, runBackgroundTask } from '@/composables/runBackgroundTask'
import source from './FinalizeView.vue?raw'

const { descriptor } = parse(source)

it('passes the complete route to each real card binding for same-name frozen occurrence recovery', () => {
  function cardNode(node: any): any {
    if (node.tag === 'FinalizeRuleCard') return node
    return (node.children || []).map(cardNode).find(Boolean)
  }
  const node = cardNode(descriptor.template!.ast)
  const compiled = compileTemplate({ source: node.loc.source, filename: 'FinalizeView.vue', id: 'frozen-card-wiring' })
  const code = transformSync(compiled.code, { loader: 'js', format: 'cjs' }).code
  const module = { exports: {} as any }
  new Function('require', 'module', 'exports', code)(() => ({ ...Vue, resolveComponent: (name: string) => name }), module, module.exports)
  const segments = [{ id: 'first', normalized_step_name: '钻孔' }, { id: 'second', normalized_step_name: '钻孔' }]
  const context = new Proxy({
    visibleSegments: [{ segment: segments[1] }], savedRoute: { segments },
    finalizeSegmentDisplayName: () => '钻孔', finalizeSegmentMetaLabel: () => '',
    FINALIZE_VIEW_COPY: {}, conditionBusySegmentIds: new Set(), conditionErrors: {},
    pendingReviewCards: [], selectedRuleIds: new Set(),
  } as Record<string, any>, { get: (target, key) => target[key as string] })
  const rendered = module.exports.render(context, [])
  expect(rendered.children[0].props['route-segments']).toEqual(segments)
})

it('disables card mutations while the server preprocessing job owns recognition', () => {
  function find(node: any): any { return node.tag === 'FinalizeRuleCard' ? node : (node.children || []).map(find).find(Boolean) }
  const compiled = compileTemplate({ source: find(descriptor.template!.ast).loc.source, filename: 'FinalizeView.vue', id: 'recognition-owner' })
  const module = { exports: {} as any }
  new Function('require', 'module', 'exports', transformSync(compiled.code, { loader: 'js', format: 'cjs' }).code)(() => ({ ...Vue, resolveComponent: (name: string) => name }), module, module.exports)
  const context = new Proxy({ visibleSegments: [{ segment: { id: 'grind' } }], savedRoute: { segments: [] },
    finalizeSegmentDisplayName: () => '磨外圆', finalizeSegmentMetaLabel: () => '', FINALIZE_VIEW_COPY: {},
    conditionBusySegmentIds: new Set(), conditionErrors: {}, pendingReviewCards: [], selectedRuleIds: new Set(),
    batchParsing: true, batchReviewing: false, resettingWorkflow: false, exportingRulePackage: false,
  } as Record<string, any>, { get: (target, key) => target[key as string] })
  expect(module.exports.render(context, []).children[0].props['actions-disabled']).toBe(true)
})
const template = descriptor.template?.content || ''
const styles = descriptor.styles.map(style => style.content).join('\n')

it('queues structured always answers for inference-free handoff and explicit human confirmation', () => {
  const candidate = { kind: 'process_configuration', configuration: { process_id: 'prepare', occurrence: 'always', when: null, relations: [] } }
  const structured: any = {
    segment: { id: 'prepare', normalized_step_name: '下料', doc_coverage: { hit_docs: 0, total_docs: 3 },
      rule_review: { analysis_draft: { status: 'confirmed', condition_text: '始终安排下料', candidate } } },
    conditionText: '始终安排下料', conditionReview: { status: 'draft', source_text: '' },
  }
  const builtin: any = { segment: { id: 'all', normalized_step_name: '检验', doc_coverage: { hit_docs: 3, total_docs: 3 } }, conditionText: '全部样本中稳定出现', factorNames: [] }
  const cards = ref([structured, builtin])
  const names = ['conditionalCards', 'relationCards', 'reviewableCards', 'batchEligibleCards', 'pendingReviewCards', 'readyRuleCount', 'confirmedRuleCount']
  const script = ts.createSourceFile('FinalizeView.ts', descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true)
  const declarations = script.statements.filter(ts.isVariableStatement).filter(statement =>
    statement.declarationList.declarations.some(d => names.includes(d.name.getText(script)))).map(s => s.getText(script)).join('\n')
  const scope = { computed, segmentCards: cards, unsavedCards: ref([]), finalizeRuleMode,
    requiresConfirmedUserRule, requiresServerRuleConditionRefresh, hasCurrentConfirmedUserRule }
  const state = new Function(...Object.keys(scope), ts.transpile(`${declarations}; return { reviewableCards, batchEligibleCards, pendingReviewCards, readyRuleCount, confirmedRuleCount }`, { target: ts.ScriptTarget.ES2022 }))(...Object.values(scope))
  expect(state.reviewableCards.value.map((card: any) => card.segment.id)).toEqual(['prepare'])
  expect(state.batchEligibleCards.value.map((card: any) => card.segment.id)).toEqual(['prepare'])
  expect(exportBlockingCards([structured])).toHaveLength(1)
  cards.value[0]!.conditionReview = { status: 'pending_confirmation', source_text: '始终安排下料', source_hash: 'a'.repeat(64), candidate }
  expect(state.pendingReviewCards.value).toHaveLength(1)
  expect(state.readyRuleCount.value).toBe(1)
  expect(exportBlockingCards([cards.value[0]])).toHaveLength(1)
  cards.value[0]!.conditionReview = { ...cards.value[0]!.conditionReview, status: 'confirmed', confirmed: candidate }
  expect(state.confirmedRuleCount.value).toBe(1)
  expect(exportBlockingCards([cards.value[0]])).toHaveLength(0)
})

// Execute the view's actual publication handler and callbacks with its API
// boundary supplied by the test, without mounting unrelated workspace polling.
function publicationHandlers(scope: Record<string, unknown>, names = ['handleReviewAndExport', 'openPrecheckDialog']) {
  scope = { loading: ref(false), loadingProjectId: '', validationIssue: ref(''), templateMappingEnabled: ref(true), isPublishedTemplateMappingCurrent, confirmFinalizeBatch, isWorkflowRevisionConflict, ...processConfigurationEditor, ...scope }
  const script = ts.createSourceFile('FinalizeView.ts', descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const functions = script.statements.filter((statement): statement is ts.FunctionDeclaration =>
    ts.isFunctionDeclaration(statement) && (names.includes(statement.name?.text || '') || ['isRuleWorkspaceCurrent', 'isPreprocessWorkspaceCurrent', 'invalidateRulePreprocessing'].includes(statement.name?.text || '')),
  )
  const callbacks: string[] = []
  for (const statement of script.statements) {
    if (ts.isExpressionStatement(statement) && ts.isCallExpression(statement.expression)) {
      const call = statement.expression
      if (names.includes(call.expression.getText(script)) && ['onActivated', 'onDeactivated'].includes(call.expression.getText(script))) {
        callbacks.push(`const ${call.expression.getText(script)} = ${call.arguments[0]!.getText(script)}`)
      }
    }
    if (!ts.isVariableStatement(statement)) continue
    for (const declaration of statement.declarationList.declarations) {
      const call = declaration.initializer
      if (!call || !ts.isCallExpression(call) || call.expression.getText(script) !== 'useFinalizeRulePackageExport') continue
      const options = call.arguments[0]
      if (!options || !ts.isObjectLiteralExpression(options)) continue
      for (const property of options.properties) {
        if (names.includes('handleReviewAndExport') && ts.isPropertyAssignment(property) && ['onExportIssue', 'onPrecheck'].includes(property.name.getText(script))) {
          callbacks.push(`const ${property.name.getText(script)} = ${property.initializer.getText(script)}`)
        }
      }
    }
  }
  const code = [...functions.map(statement => statement.getText(script)), ...callbacks,
    `return { ${names.filter(name => name !== 'openPrecheckDialog').map(name => `${name}: typeof ${name} === 'undefined' ? undefined : ${name}`).join(', ')}${names.includes('handleReviewAndExport') && callbacks.length ? ', onExportIssue, onPrecheck' : ''} }`,
  ].join('\n')
  return new Function(...Object.keys(scope), ts.transpile(code, { target: ts.ScriptTarget.ES2022 }))(...Object.values(scope))
}

describe('finalize validation preparation guards', () => {
  it('locates unsaved edits before attempting to publish an older confirmed snapshot', async () => {
    const downloadRuleDocument = vi.fn()
    const locateBlockedCard = vi.fn()
    const setBatchNotice = vi.fn()
    const card = { segment: { id: 'remove_copper' } }
    const handlers = publicationHandlers({
      precheckResult: ref(null), showPrecheckDialog: ref(false), exportIssue: ref(null),
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false),
      exportingRulePackage: ref(false), segmentCards: ref([]), exportBlockingCards,
      unsavedCards: ref([card]), conditionBusySegmentIds: ref(new Set()),
      downloadRuleDocument, locateBlockedCard, setBatchNotice, openFinalizePrecheckDialog,
    })
    await handlers.handleReviewAndExport()
    expect(downloadRuleDocument).not.toHaveBeenCalled()
    expect(locateBlockedCard).toHaveBeenCalledWith('remove_copper')
    expect(setBatchNotice.mock.calls[0]?.[0]).toContain('未保存')
  })

  it('waits for a card save to finish before publishing', async () => {
    const downloadRuleDocument = vi.fn()
    const handlers = publicationHandlers({
      precheckResult: ref(null), showPrecheckDialog: ref(false), exportIssue: ref(null),
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false),
      exportingRulePackage: ref(false), segmentCards: ref([]), exportBlockingCards,
      unsavedCards: ref([]), conditionBusySegmentIds: ref(new Set(['remove_copper'])),
      downloadRuleDocument, locateBlockedCard: vi.fn(), setBatchNotice: vi.fn(), openFinalizePrecheckDialog,
    })
    await handlers.handleReviewAndExport()
    expect(downloadRuleDocument).not.toHaveBeenCalled()
  })
})

describe('finalize precheck repair navigation', () => {
  it('locates the named target process even when it is not in the pending review subset', async () => {
    const target = { segment: { id: 'route-no-damage', export_process_id: 'segment-nondestructive_inspection_merge', normalized_step_name: '无损检查' } }
    const unrelated = { segment: { id: 'route-deburr', export_process_id: 'split-900031', normalized_step_name: '去毛刺' } }
    const showPrecheckDialog = ref(true)
    const onlyPending = ref(true)
    const focusSegment = vi.fn()
    const handlers = publicationHandlers({
      showPrecheckDialog,
      onlyPending,
      reviewFocusCards: ref([]),
      segmentCards: ref([unrelated, target]),
      finalizeSegmentDisplayName: (segment: any) => segment.normalized_step_name,
      nextTick: async () => {},
      focusSegment,
      setBatchNotice: vi.fn(),
    }, ['handlePrecheckRuleReview'])

    await handlers.handlePrecheckRuleReview({
      process_id: 'segment-nondestructive_inspection_merge',
      process_name: '无损检查',
    })

    expect(showPrecheckDialog.value).toBe(false)
    expect(onlyPending.value).toBe(false)
    expect(focusSegment).toHaveBeenCalledWith('route-no-damage')
  })

  it('locates a pending rule by its source segment id', async () => {
    const target = { segment: { id: 'segment-quench', normalized_step_name: '淬火' } }
    const showPrecheckDialog = ref(true)
    const onlyPending = ref(true)
    const focusSegment = vi.fn()
    const setBatchNotice = vi.fn()
    const handlers = publicationHandlers({
      showPrecheckDialog,
      onlyPending,
      reviewFocusCards: ref([]),
      segmentCards: ref([target]),
      finalizeSegmentDisplayName: (segment: any) => segment.normalized_step_name,
      nextTick: async () => {},
      focusSegment,
      setBatchNotice,
    }, ['handlePrecheckRuleReview'])

    await handlers.handlePrecheckRuleReview({
      code: 'user_rule_sources_unconfirmed',
      rule_ids: ['user.quench'],
      segment_ids: ['segment-quench'],
    })

    expect(showPrecheckDialog.value).toBe(false)
    expect(onlyPending.value).toBe(false)
    expect(focusSegment).toHaveBeenCalledWith('segment-quench')
    expect(setBatchNotice).not.toHaveBeenCalled()
  })
})

describe('finalize source draft persistence', () => {
  function saveScope() {
    const item: any = { segment: { id: 'remove_copper' }, conditionText: '原来的规则' }
    const inlineEditingText = ref('修改后的规则')
    const inlineEditingSegmentId = ref<string | null>('remove_copper')
    const stored = ref<any>(null)
    const review = { source_text: '修改后的规则', source_hash: 'a'.repeat(64), status: 'draft' }
    const events: string[] = []
    const saveRuleConditionDraft = vi.fn(async () => { events.push('saved'); stored.value = review; return { review } })
    const scope = {
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }),
      workflowResetSignal: ref(null),
      inlineEditingText, inlineEditingSegmentId, conditionBusySegmentIds: ref(new Set()),
      conditionErrors: ref<Record<string, string>>({}), segmentCards: ref([item]),
      saveRuleConditionDraft,
      saveInlineEdit: vi.fn(() => true),
      setConditionTextDraft: (_item: unknown, text: string) => { item.conditionText = text },
      clearPersistedDraft: vi.fn(),
      cancelInlineEdit: () => { inlineEditingSegmentId.value = null; inlineEditingText.value = '' },
      applyConditionReview: (_id: string, value: unknown) => { item.conditionReview = value },
      markExportedRulePackageOutdated: vi.fn(), setConditionBusy: vi.fn(),
      nextTick: async () => {},
      parseConditionItem: vi.fn(async () => { events.push('parsed'); return false }),
      setBatchNotice: vi.fn(), showFinalizeNotice: vi.fn(),
      conditionErrorMessage: (error: Error) => error.message,
      handleWorkflowRevisionConflict: async () => false,
      hasCurrentConditionText: () => true,
      isExplicitMainlineInstruction,
      normalizeExportProcessName: (name: string) => name, finalizeSegmentDisplayName: () => '除铜',
    }
    return { item, stored, events, scope }
  }

  it('saves the source on the server before parsing and keeps it when recognition fails', async () => {
    const state = saveScope()
    const handlers = publicationHandlers(state.scope, ['handleSaveInlineEdit'])
    await handlers.handleSaveInlineEdit(state.item)
    expect(state.events).toEqual(['saved', 'parsed'])
    expect(state.stored.value.source_text).toBe('修改后的规则')
    expect(state.item.conditionReview.status).toBe('draft')
    expect(state.scope.inlineEditingSegmentId.value).toBeNull()
  })

  it('parses with the token returned by draft save even when the old computed card is retained', async () => {
    const state = saveScope()
    state.item.conditionReview = { review_token: 'b'.repeat(64) }
    const review = { source_text: '修改后的规则', review_token: 'c'.repeat(64), status: 'draft' }
    state.scope.saveRuleConditionDraft.mockResolvedValueOnce({ review } as any)
    // The real view replaces the saved segment's review; the handler's old card
    // remains a snapshot until computed cards are read again.
    state.scope.applyConditionReview = vi.fn()
    const handlers = publicationHandlers(state.scope, ['handleSaveInlineEdit'])
    await handlers.handleSaveInlineEdit(state.item)
    expect(state.scope.parseConditionItem).toHaveBeenCalledWith(state.item, false, '修改后的规则', expect.any(Function), 'c'.repeat(64))
  })

  it('keeps the editor open and skips recognition when the source could not be saved', async () => {
    const state = saveScope()
    state.scope.saveRuleConditionDraft.mockRejectedValueOnce(new Error('offline'))
    const handlers = publicationHandlers(state.scope, ['handleSaveInlineEdit'])
    await handlers.handleSaveInlineEdit(state.item)
    expect(state.scope.inlineEditingSegmentId.value).toBe('remove_copper')
    expect(state.scope.inlineEditingText.value).toBe('修改后的规则')
    expect(state.item.conditionText).toBe('原来的规则')
    expect(state.scope.parseConditionItem).not.toHaveBeenCalled()
    expect(state.scope.markExportedRulePackageOutdated).not.toHaveBeenCalled()
  })

  it('keeps an explicitly saved mainline instruction without sending it for conditional recognition', async () => {
    const state = saveScope()
    state.scope.inlineEditingText.value = '设置为主工序，始终纳入“除铜”工序。'
    const handlers = publicationHandlers(state.scope, ['handleSaveInlineEdit'])
    await handlers.handleSaveInlineEdit(state.item)
    expect(state.events).toEqual(['saved'])
    expect(state.scope.parseConditionItem).not.toHaveBeenCalled()
  })
})

describe('finalize edit navigation protection', () => {
  it('keeps raw and structured edits visible when saving meets an upstream revision conflict', async () => {
    const loadWorkspace = vi.fn(async () => {})
    const showFinalizeNotice = vi.fn()
    const handlers = publicationHandlers({
      isWorkflowRevisionConflict: () => true,
      hasUnsavedEdits: ref(true), showFinalizeNotice, loadWorkspace,
      workflowConflictReload: null,
    }, ['handleWorkflowRevisionConflict'])
    expect(await handlers.handleWorkflowRevisionConflict({ response: { status: 409 } })).toBe(true)
    expect(loadWorkspace).not.toHaveBeenCalled()
    expect(showFinalizeNotice.mock.calls[0]?.[1]).toContain('未保存修改仍保留')
  })

  it('does not clear editors when a background reset or activation requests a reload', async () => {
    const listProjects = vi.fn(async () => [])
    const handlers = publicationHandlers({
      hasUnsavedEdits: ref(true), setBatchNotice: vi.fn(), listProjects,
      workspaceRequestGuard: { start: () => ({ isCurrent: () => false, isLatest: () => false }) },
      precheckResult: ref(null), validMappingCount: ref(0), loading: ref(false),
      conditionErrors: ref({}), selectedRuleIds: ref(new Set()), error: ref(''),
      workspaceErrorTitle: ref(''), FINALIZE_VIEW_COPY: { errorTitle: '' },
    }, ['loadWorkspace'])
    await handlers.loadWorkspace(true)
    expect(listProjects).not.toHaveBeenCalled()
  })

  it('keeps local recovery drafts when another window resets the workflow during editing', async () => {
    const clearAllDrafts = vi.fn()
    const loadWorkspace = vi.fn()
    const handlers = publicationHandlers({
      projectId: ref(12), locallyHandledResetAt: 0,
      preprocessEpoch: 0, preprocessRefreshInFlight: null, lastRulePreprocessTriggerKey: '',
      preprocessStatus: ref(null), stopPreprocessPolling: vi.fn(),
      recognitionTaskGuard: { cancel: vi.fn() }, batchParseExecutionId: 0, batchParsing: ref(true),
      markExportedRulePackageOutdated: vi.fn(), hasUnsavedEdits: ref(true),
      conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), clearAllDrafts, loadWorkspace,
    }, ['handleExternalWorkflowReset'])
    handlers.handleExternalWorkflowReset({ projectId: 12, fromStep: 3, emittedAt: 100 })
    expect(clearAllDrafts).not.toHaveBeenCalled()
    expect(loadWorkspace).not.toHaveBeenCalled()
  })

  it('preserves unsaved content when refreshing or switching away from the workspace', async () => {
    const locateBlockedCard = vi.fn()
    const loadWorkspace = vi.fn()
    const scope = {
      unsavedCards: ref([{ segment: { id: 'remove_copper' } }]),
      conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), locateBlockedCard, loadWorkspace,
    }
    const handlers = publicationHandlers(scope, ['ensureRuleEditsSaved', 'reloadWorkspace'])
    expect(await handlers.ensureRuleEditsSaved()).toBe(false)
    await handlers.reloadWorkspace()
    expect(loadWorkspace).not.toHaveBeenCalled()
    expect(locateBlockedCard).toHaveBeenCalledWith('remove_copper')
    scope.unsavedCards.value = []
    await handlers.reloadWorkspace()
    expect(loadWorkspace).toHaveBeenCalledWith(true)
  })

  it('does not replace an unsaved card when background recognition completes', async () => {
    const loadWorkspace = vi.fn()
    const handlers = publicationHandlers({
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }), preprocessRefreshInFlight: null,
      preprocessEpoch: 0, finalizeViewActive: true, workflowResetSignal: ref(null),
      getRulePreprocessingStatus: async () => ({ task_status: 'completed' }),
      preprocessStatus: ref({ task_status: 'running' }), batchParsing: ref(true), stopPreprocessPolling: vi.fn(),
      hasUnsavedEdits: ref(true), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), loadWorkspace,
    }, ['pollRulePreprocessing'])
    await handlers.pollRulePreprocessing()
    expect(loadWorkspace).not.toHaveBeenCalled()
  })
})

describe('finalize background response ownership', () => {
  function preprocessingScope() {
    const cards = ref([{ segment: { id: 'copper' }, conditionText: '需要镀铜' }])
    return {
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }),
      workflowResetSignal: ref<any>(null), finalizeViewActive: true, preprocessEpoch: 0,
      preprocessRefreshInFlight: null, preprocessPollTimer: null, lastRulePreprocessTriggerKey: '',
      preprocessStatus: ref<any>({ task_status: 'running' }),
      hasUnsavedEdits: ref(true), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), stopPreprocessPolling: vi.fn(), loadWorkspace: vi.fn(),
      reviewableCards: cards, batchEligibleCards: cards, batchParsing: ref(false),
      supersetOperations: ref([]), conditionProcessOptions: ref([]),
      buildRulePreprocessingTriggerKey: () => 'trigger-12-99',
      finalizeSegmentDisplayName: () => '镀铜', exportProcessIdForItem: () => 'copper',
      normalizeExportProcessName: (name: string) => name,
      window: { setTimeout: vi.fn(() => 1), clearTimeout: vi.fn() },
    }
  }

  it.each(['project', 'route', 'revision', 'reset'])(
    'ignores a preprocessing poll after its %s changes', async change => {
      let finish!: (value: any) => void
      const pending = new Promise(resolve => { finish = resolve })
      const scope = { ...preprocessingScope(), getRulePreprocessingStatus: vi.fn(() => pending) }
      const handlers = publicationHandlers(scope, ['pollRulePreprocessing'])
      const polling = handlers.pollRulePreprocessing()
      if (change === 'project') scope.projectId.value = 28
      else if (change === 'route') scope.savedRoute.value.route_id = 108
      else if (change === 'revision') scope.savedRoute.value.workflow_revision = 4
      else scope.workflowResetSignal.value = { projectId: 12, workflowRevision: 4 }
      scope.preprocessStatus.value = { task_status: 'queued', message: '当前工作区' }
      finish({ task_status: 'failed', message: '旧工作区失败' })
      await polling
      expect(scope.preprocessStatus.value).toEqual({ task_status: 'queued', message: '当前工作区' })
      expect(scope.stopPreprocessPolling).not.toHaveBeenCalled()
      expect(scope.loadWorkspace).not.toHaveBeenCalled()
    },
  )

  it.each(['success', 'failure'])(
    'ignores a stale preprocessing start %s without clearing the new trigger', async outcome => {
      let finish!: (value: any) => void
      const pending = new Promise((resolve, reject) => { finish = outcome === 'success' ? resolve : reject })
      const scope = { ...preprocessingScope(), startRulePreprocessing: vi.fn().mockReturnValueOnce(pending).mockResolvedValue({ task_status: 'completed', message: '新版本' }), pollRulePreprocessing: vi.fn() }
      scope.buildRulePreprocessingTriggerKey = () => `trigger-${scope.savedRoute.value.workflow_revision}`
      const handlers = publicationHandlers(scope, ['startRulePreprocessingForWorkspace'])
      const starting = handlers.startRulePreprocessingForWorkspace()
      expect(scope.startRulePreprocessing).toHaveBeenCalledOnce()
      scope.savedRoute.value.workflow_revision = 4
      await handlers.startRulePreprocessingForWorkspace()
      finish(outcome === 'success' ? { task_status: 'running', message: '旧版本' } : new Error('旧请求失败'))
      await starting
      expect(scope.preprocessStatus.value).toEqual({ task_status: 'completed', message: '新版本' })
      expect(scope.pollRulePreprocessing).not.toHaveBeenCalled()
      await handlers.startRulePreprocessingForWorkspace()
      expect(scope.startRulePreprocessing).toHaveBeenCalledTimes(2)
    },
  )

  it('resumes polling on reactivation and prevents the old poll from releasing its successor', async () => {
    const finishes: Array<(value: any) => void> = []
    const scope = {
      ...preprocessingScope(),
      getRulePreprocessingStatus: vi.fn(() => new Promise(resolve => { finishes.push(resolve) })),
      startRulePreprocessing: vi.fn(async () => ({ task_status: 'queued' })),
      recognitionTaskGuard: { cancel: vi.fn() }, batchParseExecutionId: 0, batchParsing: ref(false),
      workspaceRequestGuard: createLatestWorkflowRequestGuard(),
      loadedDataRevision: 0, getWorkflowDataRevision: () => 0, initialLoadFinished: true, loading: ref(false),
      route: { query: { project_id: '12' } }, getCurrentGroupTemplate: vi.fn(async () => ({})),
      validMappingCount: ref(1), getTemplateMappingStatus: () => ({ validCount: 1 }),
      buildFinalTemplateMappingOperations: () => [], goToTemplateMapping: vi.fn(),
    }
    const handlers = publicationHandlers(scope, ['pollRulePreprocessing', 'startRulePreprocessingForWorkspace', 'onDeactivated', 'onActivated'])
    const oldPoll = handlers.pollRulePreprocessing()
    expect(scope.getRulePreprocessingStatus).toHaveBeenCalledOnce()
    handlers.onDeactivated()
    handlers.onActivated()
    await vi.waitFor(() => expect(scope.getRulePreprocessingStatus).toHaveBeenCalledTimes(2))
    finishes[0]!({ task_status: 'failed', message: '离开前的旧响应' })
    await oldPoll
    await handlers.pollRulePreprocessing()
    expect(scope.getRulePreprocessingStatus).toHaveBeenCalledTimes(2)
    expect(scope.preprocessStatus.value).toEqual({ task_status: 'queued' })
    finishes[1]!({ task_status: 'completed', message: '当前响应' })
    await vi.waitFor(() => expect(scope.preprocessStatus.value.message).toBe('当前响应'))
    expect(scope.setBatchNotice).toHaveBeenCalledOnce()
  })

  function workspaceScope() {
    return {
      ...preprocessingScope(), hasUnsavedEdits: ref(false), workspaceRequestGuard: createLatestWorkflowRequestGuard(),
      clearWorkflowProjectDataCache,
      precheckResult: ref(null), validMappingCount: ref(1), loading: ref(false), conditionErrors: ref({}),
      selectedRuleIds: ref(new Set()), error: ref(''), workspaceErrorTitle: ref(''), FINALIZE_VIEW_COPY: { errorTitle: '' },
      listProjects: async () => [{ id: 12 }, { id: 28 }], route: { path: '/finalize', query: { project_id: '12' } },
      resolveAvailableProjectId: (id: string) => id, projectName: ref(''), router: { replace: vi.fn() },
      getSavedNormalizedRoute: async (id: number) => ({ route_id: id === 12 ? 99 : 108, workflow_revision: 3, segments: [] }),
      enterRuleFinalization: vi.fn(async () => ({ analysis_locked: true, analysis_locked_at: '2026-11-05T00:00:00' })),
      listOperations: async () => [], getSupersetRoute: async () => ({ superset_route: [] }),
      getLatestExecutableRuleRevision: vi.fn(async () => ({ id: 6, revision: 3, generation_ready: false })), executableRevisionCounter: ref(0),
      getConditionFieldRegistry: async () => ({ fields: [] }),
      getCurrentGroupTemplate: vi.fn(),
      operations: ref([]), conditionFields: ref([]), clearRuleEditStates: vi.fn(), cancelInlineEdit: vi.fn(),
      readDrafts: () => false, activeSegmentId: ref(''), nextTick: async () => {},
      lastExportedRulePackageVersion: ref<number | null>(null), outdatedRulePackageVersion: ref<number | null>(null),
      segmentCards: ref([]), exportBlockingCards: () => [], buildCompileRequestFromCards: () => ({}),
      resolveFinalizePhase: vi.fn(), finalizeSegmentPrimarySteps: vi.fn(), finalizeSegmentAttachedSteps: vi.fn(), finalizeSegmentStepNodes: vi.fn(),
      compileRulePackage: vi.fn(async () => ({ content_hash: 'hash' })), loadedDataRevision: 0, getWorkflowDataRevision: () => 0,
      startRulePreprocessingForWorkspace: vi.fn(),
    }
  }

  it('loads finalization without reading templates or requiring an exported package', async () => {
    const scope = workspaceScope()
    await publicationHandlers(scope, ['loadWorkspace']).loadWorkspace(true)
    expect(scope.savedRoute.value?.route_id).toBe(99)
    expect(scope.executableRevisionCounter.value).toBe(3)
    expect(scope.getCurrentGroupTemplate).not.toHaveBeenCalled()
    expect(scope.error.value).toBe('')
  })

  it('ignores a delayed revision counter after switching projects', async () => {
    const scope = workspaceScope()
    let finish!: (value: any) => void
    scope.getLatestExecutableRuleRevision.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const handlers = publicationHandlers(scope, ['loadWorkspace'])
    const oldLoad = handlers.loadWorkspace(true)
    await vi.waitFor(() => expect(scope.getLatestExecutableRuleRevision).toHaveBeenCalledOnce())
    scope.route.query.project_id = '28'
    await handlers.loadWorkspace(true)
    finish({ id: 999, revision: 999 })
    await oldLoad
    expect(scope.projectId.value).toBe(28)
    expect(scope.executableRevisionCounter.value).toBe(3)
  })

  it.each(['unsaved', 'saving'])('keeps an active %s rule on reactivation', state => {
    const scope = { ...workspaceScope(), initialLoadFinished: true, loadWorkspace: vi.fn() }
    if (state === 'unsaved') scope.hasUnsavedEdits.value = true
    else scope.conditionBusySegmentIds.value.add('copper')
    publicationHandlers(scope, ['onActivated']).onActivated()
    expect(scope.loadWorkspace).not.toHaveBeenCalled()
    expect(scope.getCurrentGroupTemplate).not.toHaveBeenCalled()
  })

  it('loads basic finalization without reading or redirecting to old template mappings', async () => {
    const scope = { ...workspaceScope(), templateMappingEnabled: ref(false),
      getCurrentGroupTemplate: vi.fn(async () => { throw new Error('feature_disabled') }),
      getLatestFinalizedRulePackage: async () => null,
    }
    await publicationHandlers(scope, ['loadWorkspace']).loadWorkspace()
    expect(scope.error.value).toBe('')
    expect(scope.savedRoute.value?.route_id).toBe(99)
    expect(scope.getCurrentGroupTemplate).not.toHaveBeenCalled()
    expect(scope.router.replace).not.toHaveBeenCalled()
  })

  it('refreshes the basic workspace on activation without a separate template check', () => {
    const scope = { ...workspaceScope(), templateMappingEnabled: ref(false), initialLoadFinished: true,
      getCurrentGroupTemplate: vi.fn(async () => ({})), startRulePreprocessingForWorkspace: vi.fn(),
    }
    publicationHandlers(scope, ['onActivated']).onActivated()
    expect(scope.getCurrentGroupTemplate).not.toHaveBeenCalled()
    expect(scope.loadWorkspace).toHaveBeenCalledWith(true)
  })

  it('does not restart a completed job with failed items when polling refreshes the workspace', async () => {
    const completed = { task_status: 'completed', failed_count: 1, message: '一条识别失败' }
    const scope = {
      ...workspaceScope(), lastRulePreprocessTriggerKey: 'trigger-12-99',
      getLatestFinalizedRulePackage: async () => null,
      getRulePreprocessingStatus: vi.fn(async () => completed),
      startRulePreprocessing: vi.fn(async () => ({ task_status: 'failed' })),
    }
    const handlers = publicationHandlers(scope, ['pollRulePreprocessing', 'loadWorkspace', 'startRulePreprocessingForWorkspace'])
    await handlers.pollRulePreprocessing()
    expect(scope.startRulePreprocessing).not.toHaveBeenCalled()
    expect(scope.preprocessStatus.value).toEqual(completed)
  })

  function resetRecognitionScope() {
    const segment = (id: string, occurrence: string, confirmed: boolean) => {
      const text = id === 'grind' ? '外圆柱面的实际尺寸精度≤IT7时安排磨外圆。' : `当材料为6061时安排${id}。`
      const candidate = { kind: 'process_configuration', preview: text, configuration: {
        process_id: id, occurrence, when: occurrence === 'always' ? null : { field: 'material.grade', op: 'eq', value: '6061' }, relations: [],
      } }
      return {
        id, sequence: 1, normalized_step_name: id === 'grind' ? '磨外圆' : id,
        source_operation_ids: [], source_nodes: [], matched_detail_rows: [], factor_reviews: [],
        doc_coverage: { hit_docs: 1, total_docs: 1, ratio: 1 },
        rule_review: { decision: 'accepted', question_trail: [], summary_lines: [],
          analysis_draft: { status: 'confirmed', condition_text: text, candidate },
          condition_review: { source_text: text, source_hash: id, review_token: `saved-${id}`,
            status: confirmed ? 'confirmed' : 'draft', candidate: confirmed ? candidate : null,
            confirmed: confirmed ? candidate : null, issues: [], confirmed_by: confirmed ? '用户' : '', confirmed_at: confirmed ? '2026-11-08' : '' },
        },
      }
    }
    const serverRoute = { route_id: 99, workflow_revision: 4, analysis_locked: true,
      segments: [segment('prepare', 'always', true), segment('manual', 'manual', true),
        segment('grind', 'conditional', false), segment('conditional', 'conditional', false),
        segment('always-draft', 'always', false), segment('manual-draft', 'manual', false)] }
    const scope: Record<string, any> = {
      ...workspaceScope(), savedRoute: ref({ ...structuredClone(serverRoute), workflow_revision: 3 }),
      preprocessStatus: ref(null), conditionBusyCounts: new Map(),
      resettingWorkflow: ref(false), resetDialogVisible: ref(true), validationIssue: ref(''), batchNotice: ref(''),
      onlyPending: ref(false), batchParsing: ref(false), batchParseCompleted: ref(0), batchParseTotal: ref(0), batchParseExecutionId: 0,
      batchReviewing: ref(false), reviewAndExporting: ref(false), exportingRulePackage: ref(false), unsavedCards: ref([]),
      recognitionTaskGuard: createBackgroundTaskGuard(), runBackgroundTask, locallyHandledResetAt: 0,
      resetWorkflow: vi.fn(async () => ({ project_id: 12, workflow_revision: 4 })),
      getSavedNormalizedRoute: vi.fn(async () => structuredClone(serverRoute)),
      startRulePreprocessing: vi.fn(async () => ({ task_status: 'queued', workflow_revision: 4 })),
      getRulePreprocessingStatus: vi.fn(async () => ({ task_status: 'running', workflow_revision: 4 })),
      parseRuleCondition: vi.fn(async () => ({ review: { status: 'pending_confirmation' } })),
      buildRulePreprocessingTriggerKey, finalizeSegmentDisplayName: (s: any) => s.normalized_step_name,
      exportProcessIdForItem: (item: any) => item.segment.id, nextTick: Vue.nextTick,
      showFinalizeNotice: vi.fn(), clearAllDrafts: vi.fn(), markExportedRulePackageOutdated: vi.fn(),
      conditionProcessOptions: ref([]), workflowConflictReload: null,
    }
    scope.segmentCards = computed(() => buildFinalizeCards(scope.savedRoute.value?.segments || [], [], {}))
    scope.reviewableCards = computed(() => scope.segmentCards.value.filter(requiresConfirmedUserRule))
    scope.batchEligibleCards = computed(() => scope.reviewableCards.value.filter(requiresServerRuleConditionRefresh))
    scope.publishWorkflowReset = vi.fn((reset: any) => {
      clearWorkflowProjectDataCache(reset.projectId)
      scope.workflowResetSignal.value = { ...reset, emittedAt: 100 }
    })
    const handlers = publicationHandlers(scope, [
      'handleResetAllRecognition', 'restartAllRecognitionInBackground', 'loadWorkspace',
      'startRulePreprocessingForWorkspace', 'pollRulePreprocessing', 'handleBatchParseConditions',
      'parseConditionItem', 'applyConditionReview', 'hasCurrentConditionText', 'setConditionBusy',
      'handleExternalWorkflowReset', 'ensureRuleEditsSaved', 'conditionErrorMessage',
    ])
    return { scope, handlers, serverRoute }
  }

  it('uses one preprocessing owner after reset without a parallel per-card parse queue', async () => {
    const { scope, handlers } = resetRecognitionScope()
    const confirmed = JSON.stringify(scope.savedRoute.value.segments.slice(0, 2))
    await handlers.handleResetAllRecognition()
    await vi.waitFor(() => expect(scope.startRulePreprocessing).toHaveBeenCalledOnce())
    await Vue.nextTick()
    expect(scope.parseRuleCondition).not.toHaveBeenCalled()
    expect(JSON.stringify(scope.savedRoute.value.segments.slice(0, 2))).toBe(confirmed)
  })

  it('includes retained third-step structured drafts in the reset preprocessing queue', async () => {
    const { scope, handlers } = resetRecognitionScope()
    await handlers.handleResetAllRecognition()
    await vi.waitFor(() => expect(scope.startRulePreprocessing).toHaveBeenCalledOnce())
    expect(scope.startRulePreprocessing.mock.calls[0][0].items.map((item: any) => item.segment_id)).toEqual(['grind', 'conditional', 'always-draft', 'manual-draft'])
  })

  it('blocks another reset until preprocessing is accepted and while its job runs', async () => {
    const { scope, handlers } = resetRecognitionScope()
    let finish!: (value: any) => void
    scope.startRulePreprocessing.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const resetting = handlers.handleResetAllRecognition()
    try {
      await vi.waitFor(() => expect(scope.startRulePreprocessing).toHaveBeenCalledOnce())
      expect(scope.resettingWorkflow.value).toBe(true)
      await handlers.handleResetAllRecognition()
      expect(scope.resetWorkflow).toHaveBeenCalledOnce()
    } finally {
      finish({ task_status: 'queued', workflow_revision: 4 })
      await resetting
    }
    expect(scope.resettingWorkflow.value).toBe(false)
    expect(scope.batchParsing.value).toBe(true)
    await handlers.handleResetAllRecognition()
    expect(scope.resetWorkflow).toHaveBeenCalledOnce()
  })

  it('reloads a polled completion without starting a second recognition job', async () => {
    const { scope, handlers, serverRoute } = resetRecognitionScope()
    await handlers.handleResetAllRecognition()
    for (const segment of serverRoute.segments.slice(2)) {
      segment.rule_review.condition_review = { ...segment.rule_review.condition_review,
        status: 'pending_confirmation', candidate: segment.rule_review.analysis_draft.candidate }
    }
    scope.getRulePreprocessingStatus.mockResolvedValueOnce({ task_status: 'completed', workflow_revision: 4 })
    await handlers.pollRulePreprocessing()
    expect(scope.savedRoute.value.segments[2].rule_review.condition_review.status).toBe('pending_confirmation')
    expect(scope.startRulePreprocessing).toHaveBeenCalledOnce()
    expect(scope.parseRuleCondition).not.toHaveBeenCalled()
    expect(scope.batchParsing.value).toBe(false)
  })

  it('keeps polling after a transient status failure instead of leaving recognition locked', async () => {
    const { scope, handlers } = resetRecognitionScope()
    const quiet = vi.spyOn(console, 'warn').mockImplementation(() => {})
    try {
      await handlers.handleResetAllRecognition()
      scope.window.setTimeout.mockClear()
      scope.getRulePreprocessingStatus.mockRejectedValueOnce(new Error('temporary status failure'))
      await handlers.pollRulePreprocessing()
      expect(scope.window.setTimeout).toHaveBeenCalledOnce()
      expect(scope.batchParsing.value).toBe(true)
    } finally { quiet.mockRestore() }
  })

  it('reloads an immediately completed preprocessing job once without restarting it', async () => {
    const { scope, handlers, serverRoute } = resetRecognitionScope()
    scope.startRulePreprocessing.mockImplementationOnce(async () => {
      for (const segment of serverRoute.segments.slice(2)) {
        segment.rule_review.condition_review = { ...segment.rule_review.condition_review,
          status: 'pending_confirmation', candidate: segment.rule_review.analysis_draft.candidate }
      }
      return { task_status: 'completed', workflow_revision: 4 }
    })
    await handlers.handleResetAllRecognition()
    await vi.waitFor(() => expect(scope.getSavedNormalizedRoute).toHaveBeenCalledTimes(2))
    expect(scope.savedRoute.value.segments[2].rule_review.condition_review.status).toBe('pending_confirmation')
    expect(scope.startRulePreprocessing).toHaveBeenCalledOnce()
    expect(scope.parseRuleCondition).not.toHaveBeenCalled()
    expect(scope.batchParsing.value).toBe(false)
  })

  it.each(['project', 'deactivation'])('ignores a reset response after %s cancels its owner', async change => {
    const { scope, handlers } = resetRecognitionScope()
    let finish!: (value: any) => void
    scope.resetWorkflow.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const resetting = handlers.handleResetAllRecognition()
    await vi.waitFor(() => expect(scope.resetWorkflow).toHaveBeenCalledOnce())
    if (change === 'project') { scope.projectId.value = 28; scope.route.query.project_id = '28' }
    scope.recognitionTaskGuard.cancel()
    finish({ project_id: 12, workflow_revision: 4 })
    await resetting
    expect(scope.getSavedNormalizedRoute).not.toHaveBeenCalled()
    expect(scope.startRulePreprocessing).not.toHaveBeenCalled()
    expect(scope.showFinalizeNotice).not.toHaveBeenCalled()
  })

  it('does not enter finalization from an inactive view after a third-step reset', async () => {
    const { scope } = resetRecognitionScope()
    // Lifecycle flags are closure locals in the real component, just as in the other handler tests.
    const inactive = publicationHandlers({ ...scope, finalizeViewActive: false }, ['handleExternalWorkflowReset', 'loadWorkspace'])
    inactive.handleExternalWorkflowReset({ projectId: 12, fromStep: 3, workflowRevision: 5, emittedAt: 101 })
    await Vue.nextTick()
    expect(scope.getSavedNormalizedRoute).not.toHaveBeenCalled()
    expect(scope.enterRuleFinalization).not.toHaveBeenCalled()
    expect(scope.clearAllDrafts).toHaveBeenCalledOnce()
  })


})

describe('finalize four-mode confirmation guards', () => {
  function confirmationScope(candidate: any) {
    const text = '当材料为6061时纳入除铜'
    const item = { segment: { id: 'remove_copper' }, conditionText: text, conditionReview: { source_text: text, source_hash: 'a'.repeat(64), status: 'pending_confirmation', candidate } }
    const confirmRuleCondition = vi.fn(async () => ({ review: { ...item.conditionReview, status: 'confirmed' } }))
    const scope = {
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }), workflowResetSignal: ref(null),
      conditionBusySegmentIds: ref(new Set<string>()), conditionErrors: ref<Record<string, string>>({}),
      conditionProcessOptions: ref([]), selectedRuleIds: ref(new Set(['remove_copper'])),
      selectedReviewCards: ref([item]), batchReviewing: ref(false), batchReviewCompleted: ref(0), batchReviewTotal: ref(0),
      confirmRuleCondition, saveProcessConfiguration: vi.fn(), applyConditionReview: vi.fn(),
      exportProcessIdForItem: (card: any) => card.segment.id,
      setConditionBusy: (id: string, busy: boolean) => busy ? scope.conditionBusySegmentIds.value.add(id) : scope.conditionBusySegmentIds.value.delete(id),
      markExportedRulePackageOutdated: vi.fn(), setBatchNotice: vi.fn(), hasCurrentConditionText: () => true,
      handleWorkflowRevisionConflict: async () => false, isConditionSourceConflict: () => false, conditionErrorMessage: (error: Error) => error.message,
    }
    return { item, scope }
  }

  it('leaves selection unchanged while a refreshed rule list is loading', () => {
    const selectedRuleIds = ref(new Set(['retained']))
    const handlers = publicationHandlers({
      loading: ref(true), selectedRuleIds, allPendingSelected: ref(false),
      visiblePendingReviewCards: ref([{ segment: { id: 'stale' } }]),
    }, ['toggleSelectAllPending'])
    handlers.toggleSelectAllPending()
    expect([...selectedRuleIds.value]).toEqual(['retained'])
  })

  it('does not submit selected rules from the previous snapshot during refresh', async () => {
    const candidate = { kind: 'process_configuration', configuration: { process_id: 'remove_copper', occurrence: 'always', when: null, relations: [] } }
    const { item, scope } = confirmationScope(candidate)
    const before = JSON.stringify(item)
    const handlers = publicationHandlers({ ...scope, loading: ref(true) }, ['handleConfirmCondition', 'handleConfirmSelectedCandidates'])
    await handlers.handleConfirmSelectedCandidates()
    expect(scope.confirmRuleCondition).not.toHaveBeenCalled()
    expect(scope.batchReviewing.value).toBe(false)
    expect(scope.batchReviewTotal.value).toBe(0)
    expect(JSON.stringify(item)).toBe(before)
  })

  it('disables both header batch controls while the rule list refreshes', () => {
    function findGroup(node: any): any {
      if (node.tag === 'div' && node.props?.some((prop: any) => prop.name === 'aria-label' && prop.value?.content === '批量选择规则')) return node
      return (node.children || []).map(findGroup).find(Boolean)
    }
    const node = findGroup(descriptor.template!.ast)
    const compiled = compileTemplate({ source: node.loc.source, filename: 'FinalizeView.vue', id: 'loading-batch-controls' })
    const code = transformSync(compiled.code, { loader: 'js', format: 'cjs' }).code
    const module = { exports: {} as any }
    new Function('require', 'module', 'exports', code)(() => Vue, module, module.exports)
    const rendered = module.exports.render({
      pendingReviewCards: [{}], visiblePendingReviewCards: [{}], selectedReviewCards: [{}],
      loading: true, allPendingSelected: false, batchReviewing: false, batchParsing: false,
      resettingWorkflow: false, exportingRulePackage: false,
      toggleSelectAllPending() {}, handleConfirmSelectedCandidates() {},
    }, [])
    expect(rendered.children.filter((node: any) => node.type === 'button').map((node: any) => Boolean(node.props.disabled))).toEqual([true, true])
  })

  it.each([false, true])('rejects unsupported candidates through the actual confirmation handler, batch=%s', async batch => {
    const candidate = { kind: 'condition', when: { any: [{ field: 'material.grade', op: 'eq', value: '6061' }] }, then: { include_process_ids: ['remove_copper'] } }
    const { item, scope } = confirmationScope(candidate)
    const handlers = publicationHandlers(scope, ['handleConfirmCondition', 'handleConfirmSelectedCandidates'])
    if (batch) await handlers.handleConfirmSelectedCandidates()
    else await handlers.handleConfirmCondition(item, candidate, false)
    expect(scope.confirmRuleCondition).not.toHaveBeenCalled()
    expect(scope.applyConditionReview).not.toHaveBeenCalled()
    expect(scope.conditionErrors.value.remove_copper).toContain('选择')
    expect(item.conditionReview.candidate).toEqual(candidate)
  })

  it('rejects an associated configuration with a hidden condition before saving', async () => {
    const candidate = { kind: 'process_configuration', configuration: { process_id: 'remove_copper', occurrence: 'associated', when: { field: 'material.grade', op: 'eq', value: '6061' }, relations: [{ relation_type: 'trigger_after', source_process_ids: ['copper'], target_process_ids: ['remove_copper'] }] } }
    const { item, scope } = confirmationScope(candidate)
    const handlers = publicationHandlers(scope, ['handleSaveConfiguration'])
    await handlers.handleSaveConfiguration(item, candidate)
    expect(scope.saveProcessConfiguration).not.toHaveBeenCalled()
    expect(scope.conditionErrors.value.remove_copper).toContain('选择')
  })
})

describe('finalize full-route batch confirmation', () => {
  function card(id: string, sequence: number, kind = 'condition'): any {
    const text = `当材料为6061时纳入${id}`
    const candidate = kind === 'process_configuration'
      ? { kind, configuration: { process_id: id, occurrence: 'always', when: null, relations: [] }, preview: '始终纳入' }
      : { kind, when: { field: 'material.grade', op: 'eq', value: '6061' }, then: { include_process_ids: [id], exclude_process_ids: [] }, preview: text }
    return {
      segment: { id, sequence, normalized_step_name: id }, conditionText: text, edited: false,
      conditionReview: { source_text: text, source_hash: `${id}-hash`, status: 'pending_confirmation', candidate, issues: [] },
    }
  }

  function batchScope(items: any[]) {
    const segmentCards = ref(items)
    const scope = {
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }), workflowResetSignal: ref<any>(null),
      loading: ref(false), error: ref(''), resettingWorkflow: ref(false), batchParsing: ref(false),
      reviewAndExporting: ref(false), exportingRulePackage: ref(false),
      segmentCards, visibleSegments: ref(items.slice(0, 1)), onlyPending: ref(true),
      selectedReviewCards: ref<any[]>([]), selectedRuleIds: ref(new Set<string>()),
      unsavedCards: ref<any[]>([]), conditionBusySegmentIds: ref(new Set<string>()),
      conditionErrors: ref<Record<string, string>>({}), conditionProcessOptions: ref([]),
      batchReviewing: ref(false), batchReviewCompleted: ref(0), batchReviewTotal: ref(0),
      batchConfirmationResult: ref<any>(null),
      confirmRuleCondition: vi.fn(async (payload: any) => {
        const item = segmentCards.value.find(item => item.segment.id === payload.segment_id)!
        return { review: { ...item.conditionReview, status: 'confirmed', confirmed: payload.candidate } }
      }),
      applyConditionReview: (id: string, review: any) => { segmentCards.value.find(item => item.segment.id === id)!.conditionReview = review },
      setConditionBusy: (id: string, busy: boolean) => busy ? scope.conditionBusySegmentIds.value.add(id) : scope.conditionBusySegmentIds.value.delete(id),
      exportProcessIdForItem: (item: any) => item.segment.id,
      hasCurrentConditionText: (id: string, text: string) => segmentCards.value.find(item => item.segment.id === id)?.conditionText === text,
      finalizeSegmentDisplayName: (segment: any) => segment.normalized_step_name,
      handleWorkflowRevisionConflict: async () => false, isConditionSourceConflict: vi.fn(() => false),
      conditionErrorMessage: (error: Error) => error.message,
      markExportedRulePackageOutdated: vi.fn(), setBatchNotice: vi.fn(),
      parseConditionItem: vi.fn(async () => true),
      prepareValidation: vi.fn(), router: { push: vi.fn() },
    }
    const handlers = publicationHandlers(scope, ['handleConfirmAllCandidates', 'handleConfirmCondition', 'handleConfirmSelectedCandidates', 'handleReviewAndExport'])
    expect(handlers.handleConfirmAllCandidates).toBeTypeOf('function')
    return { scope, handlers }
  }

  it('confirms unselected, filtered-out and collapsed rules while preserving confirmed rules and staying in step four', async () => {
    const confirmed = card('已确认', 4)
    confirmed.conditionReview.status = 'confirmed'
    confirmed.conditionReview.confirmed = confirmed.conditionReview.candidate
    const original = JSON.stringify(confirmed)
    const mainline = card('自动主工序', 5)
    mainline.factorNames = ['always=true']
    mainline.conditionReview = null
    const { scope, handlers } = batchScope([card('可见工序', 1), card('筛选外工序', 2), card('折叠主工序', 3, 'process_configuration'), confirmed, mainline])
    await handlers.handleConfirmAllCandidates()
    expect(scope.confirmRuleCondition.mock.calls.map(([payload]) => payload.segment_id)).toEqual(['可见工序', '筛选外工序', '折叠主工序'])
    expect(scope.confirmRuleCondition.mock.calls.every(([payload]) => payload.expected_workflow_revision === 3)).toBe(true)
    expect(JSON.stringify(scope.segmentCards.value[3])).toBe(original)
    expect(scope.batchConfirmationResult.value).toMatchObject({ successCount: 3, remainingCount: 0 })
    expect(scope.prepareValidation).not.toHaveBeenCalled()
    expect(scope.router.push).not.toHaveBeenCalled()
    expect(scope.onlyPending.value).toBe(true)
  })

  it('retains raw and structured drafts and reports missing or invalid content by process', async () => {
    const raw = card('原文草稿', 1), structured = card('结构草稿', 2), missing = card('缺内容', 3), invalid = card('缺条件值', 4)
    missing.conditionText = ''
    missing.conditionReview = null
    invalid.conditionReview.candidate.when.value = ''
    const { scope, handlers } = batchScope([raw, structured, missing, invalid, card('可确认', 5)])
    scope.unsavedCards.value = [raw, structured]
    const before = JSON.stringify([raw, structured, missing, invalid])
    await handlers.handleConfirmAllCandidates()
    expect(scope.confirmRuleCondition.mock.calls.map(([payload]) => payload.segment_id)).toEqual(['可确认'])
    expect(JSON.stringify(scope.segmentCards.value.slice(0, 4))).toBe(before)
    expect(scope.unsavedCards.value).toEqual([raw, structured])
    expect(scope.batchConfirmationResult.value).toMatchObject({
      successCount: 1, remainingCount: 4,
      items: [
        { segmentId: '原文草稿', status: 'unsaved', reason: expect.stringContaining('未保存') },
        { segmentId: '结构草稿', status: 'unsaved', reason: expect.stringContaining('未保存') },
        { segmentId: '缺内容', status: 'missing', reason: expect.stringContaining('内容') },
        { segmentId: '缺条件值', status: 'missing', reason: expect.stringContaining('条件值') },
        { segmentId: '可确认', status: 'confirmed' },
      ],
    })
  })

  it('continues after request failures and only counts server-confirmed results', async () => {
    const { scope, handlers } = batchScope([card('请求失败', 1), card('服务端拒绝', 2), card('后续成功', 3)])
    scope.confirmRuleCondition.mockRejectedValueOnce(new Error('服务暂不可用'))
      .mockResolvedValueOnce({ review: { status: 'pending_confirmation' } } as any)
    await handlers.handleConfirmAllCandidates()
    expect(scope.confirmRuleCondition).toHaveBeenCalledTimes(3)
    expect(scope.batchConfirmationResult.value).toMatchObject({
      successCount: 1, remainingCount: 2,
      items: [
        { segmentId: '请求失败', status: 'failed', reason: expect.stringContaining('服务暂不可用') },
        { segmentId: '服务端拒绝', status: 'failed', reason: expect.stringContaining('尚未确认') },
        { segmentId: '后续成功', status: 'confirmed' },
      ],
    })
    expect(scope.batchReviewing.value).toBe(false)
    expect(scope.batchReviewCompleted.value).toBe(3)
    expect(scope.batchReviewTotal.value).toBe(3)
  })

  it('blocks repeated clicks, selected confirmation and validation until the batch completes', async () => {
    const { scope, handlers } = batchScope([card('待响应', 1)])
    scope.selectedReviewCards.value = scope.segmentCards.value
    let finish!: (value: any) => void
    scope.confirmRuleCondition.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const running = handlers.handleConfirmAllCandidates()
    expect(scope.batchReviewing.value).toBe(true)
    await handlers.handleConfirmAllCandidates()
    await handlers.handleConfirmSelectedCandidates()
    await handlers.handleReviewAndExport()
    expect(scope.confirmRuleCondition).toHaveBeenCalledOnce()
    expect(scope.prepareValidation).not.toHaveBeenCalled()
    const candidate = scope.segmentCards.value[0]!.conditionReview.candidate
    finish({ review: { ...scope.segmentCards.value[0]!.conditionReview, status: 'confirmed', confirmed: candidate } })
    await running
    expect(scope.batchReviewing.value).toBe(false)
    expect(scope.batchConfirmationResult.value).toMatchObject({ successCount: 1, remainingCount: 0 })
  })

  it('reports source conflicts without reparsing or changing the saved rule', async () => {
    const { scope, handlers } = batchScope([card('源内容冲突', 1), card('后续成功', 2)])
    const before = JSON.stringify(scope.segmentCards.value[0])
    scope.isConditionSourceConflict.mockReturnValue(true)
    scope.confirmRuleCondition.mockRejectedValueOnce(new Error('条件文字已经发生变化'))
    await handlers.handleConfirmAllCandidates()
    expect(scope.parseConditionItem).not.toHaveBeenCalled()
    expect(JSON.stringify(scope.segmentCards.value[0])).toBe(before)
    expect(scope.batchConfirmationResult.value).toMatchObject({
      successCount: 1, remainingCount: 1,
      items: [
        { segmentId: '源内容冲突', status: 'failed', reason: expect.stringContaining('变化') },
        { segmentId: '后续成功', status: 'confirmed' },
      ],
    })
  })

  it.each([false, true])('stops on a real workflow 409 with a retained draft, previous success=%s', async previousSuccess => {
    const draft = card('保留草稿', 1)
    const items = [draft, ...(previousSuccess ? [card('之前成功', 2)] : []), card('版本冲突', 3), card('未执行', 4)]
    const { scope } = batchScope(items)
    scope.unsavedCards.value = [draft]
    const preserved = JSON.stringify(scope.segmentCards.value.filter(item => item.segment.id !== '之前成功'))
    const serverReason = '当前页面已过期，请刷新后再操作。'
    const conflict = { response: { status: 409, data: { detail: { message: serverReason, workflow_revision: 4 } } } }
    const originalConfirm = scope.confirmRuleCondition.getMockImplementation()!
    scope.confirmRuleCondition.mockImplementation(async payload => {
      if (payload.segment_id === '之前成功') return originalConfirm(payload)
      throw conflict
    })
    const loadWorkspace = vi.fn(async () => {})
    const showFinalizeNotice = vi.fn()
    const handlers = publicationHandlers({
      ...scope, hasUnsavedEdits: computed(() => scope.unsavedCards.value.length > 0),
      isWorkflowRevisionConflict, loadWorkspace, showFinalizeNotice, workflowConflictReload: null,
    }, ['handleConfirmAllCandidates', 'handleConfirmCondition', 'handleWorkflowRevisionConflict', 'conditionErrorMessage'])

    await handlers.handleConfirmAllCandidates()

    expect(scope.confirmRuleCondition.mock.calls.map(([payload]) => payload.segment_id)).toEqual(previousSuccess ? ['之前成功', '版本冲突'] : ['版本冲突'])
    expect(scope.confirmRuleCondition.mock.calls.every(([payload]) => payload.expected_workflow_revision === 3)).toBe(true)
    expect(scope.batchConfirmationResult.value).toMatchObject({
      successCount: previousSuccess ? 1 : 0, remainingCount: 3,
      items: [
        { segmentId: '保留草稿', status: 'unsaved' },
        ...(previousSuccess ? [{ segmentId: '之前成功', status: 'confirmed' }] : []),
        { segmentId: '版本冲突', status: 'failed', reason: serverReason },
        { segmentId: '未执行', status: 'not_executed', reason: expect.stringContaining(serverReason) },
      ],
    })
    expect(scope.batchConfirmationResult.value.items.at(-1).reason).toContain('未执行')
    expect(scope.conditionErrors.value['版本冲突']).toBe(serverReason)
    expect(JSON.stringify(scope.segmentCards.value.filter(item => item.segment.id !== '之前成功'))).toBe(preserved)
    if (previousSuccess) expect(scope.segmentCards.value.find(item => item.segment.id === '之前成功')!.conditionReview.status).toBe('confirmed')
    expect(scope.unsavedCards.value).toEqual([draft])
    expect(scope.savedRoute.value.workflow_revision).toBe(3)
    expect(loadWorkspace).not.toHaveBeenCalled()
    expect(scope.parseConditionItem).not.toHaveBeenCalled()
    expect(scope.prepareValidation).not.toHaveBeenCalled()
    expect(scope.router.push).not.toHaveBeenCalled()
    expect(showFinalizeNotice.mock.calls.length).toBeLessThanOrEqual(1)
    expect(scope.batchReviewing.value).toBe(false)
    expect(scope.conditionBusySegmentIds.value.size).toBe(0)
  })

  it.each([false, true])('keeps default single-rule workflow conflict handling, retained draft=%s', async retainedDraft => {
    const item = card('单条冲突', 1)
    const { scope } = batchScope([item])
    scope.confirmRuleCondition.mockRejectedValueOnce({ response: { status: 409, data: { detail: { message: '当前页面已过期，请刷新后再操作。' } } } })
    const loadWorkspace = vi.fn(async () => {})
    const showFinalizeNotice = vi.fn()
    const handlers = publicationHandlers({
      ...scope, hasUnsavedEdits: ref(retainedDraft), isWorkflowRevisionConflict,
      loadWorkspace, showFinalizeNotice, workflowConflictReload: null,
    }, ['handleConfirmCondition', 'handleWorkflowRevisionConflict', 'conditionErrorMessage'])
    await handlers.handleConfirmCondition(item, item.conditionReview.candidate, false)
    expect(showFinalizeNotice).toHaveBeenCalledOnce()
    expect(loadWorkspace).toHaveBeenCalledTimes(retainedDraft ? 0 : 1)
    expect(item.conditionReview.status).toBe('pending_confirmation')
  })

  it.each(['draft', 'candidate', 'source', 'busy'])('rechecks a queued item after its %s state changes during the first request', async change => {
    const { scope, handlers } = batchScope([card('先处理', 1), card('排队工序', 2)])
    let finish!: (value: any) => void
    scope.confirmRuleCondition.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const running = handlers.handleConfirmAllCandidates()
    const queued = scope.segmentCards.value[1]!
    if (change === 'draft') scope.unsavedCards.value = [queued]
    else if (change === 'candidate') queued.conditionReview.candidate.when.value = '7075'
    else if (change === 'source') queued.conditionText = '当材料为7075时纳入排队工序'
    else scope.conditionBusySegmentIds.value.add('排队工序')
    const before = JSON.stringify(queued)
    const first = scope.segmentCards.value[0]!
    finish({ review: { ...first.conditionReview, status: 'confirmed', confirmed: first.conditionReview.candidate } })
    await running
    expect(scope.confirmRuleCondition).toHaveBeenCalledOnce()
    expect(JSON.stringify(queued)).toBe(before)
    expect(scope.batchConfirmationResult.value).toMatchObject({
      successCount: 1, remainingCount: 1,
      items: [
        { segmentId: '先处理', status: 'confirmed' },
        { segmentId: '排队工序', status: change === 'draft' ? 'unsaved' : change === 'busy' ? 'failed' : 'missing' },
      ],
    })
  })

  it.each(['project', 'route', 'revision', 'reset'])('stops the queue and ignores results after a %s change', async change => {
    const { scope, handlers } = batchScope([card('迟到响应', 1), card('未执行', 2)])
    let finish!: (value: any) => void
    scope.confirmRuleCondition.mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const running = handlers.handleConfirmAllCandidates()
    if (change === 'project') scope.projectId.value = 13
    else if (change === 'route') scope.savedRoute.value.route_id = 100
    else if (change === 'revision') scope.savedRoute.value.workflow_revision = 4
    else scope.workflowResetSignal.value = { projectId: 12, workflowRevision: 4 }
    finish({ review: { status: 'confirmed' } })
    await running
    expect(scope.confirmRuleCondition).toHaveBeenCalledOnce()
    expect(scope.segmentCards.value[0]!.conditionReview.status).toBe('pending_confirmation')
    expect(scope.batchConfirmationResult.value).toBeNull()
    expect(scope.batchReviewing.value).toBe(false)
  })
})

describe('finalize response revision protection', () => {
  const actions = [
    ['handleSaveInlineEdit', 'saveRuleConditionDraft'],
    ['handleResetInlineEdit', 'saveRuleConditionDraft'],
    ['parseConditionItem', 'parseRuleCondition'],
    ['handleConfirmCondition', 'confirmRuleCondition'],
    ['handleSetMainline', 'saveRuleConditionDraft'],
    ['handleSetBoolean', 'setManualRuleCondition'],
    ['handleSaveConfiguration', 'saveProcessConfiguration'],
  ] as const

  it.each(actions.flatMap(([handler, api]) => ['success', 'failure'].flatMap(outcome => [
    { handler, api, outcome, advance: 'loaded route' }, { handler, api, outcome, advance: 'reset signal' },
    { handler, api, outcome, advance: 'same-text review' },
  ])))('ignores a stale $outcome from $handler after revision advances through $advance', async ({ handler, api, outcome, advance }) => {
    let finish!: (value: any) => void
    const pending = new Promise((resolve, reject) => { finish = outcome === 'success' ? resolve : reject })
    const request = vi.fn((_payload: unknown) => pending)
    const item = {
      segment: { id: 'remove_copper' }, conditionText: '原来的规则', defaultConditionText: '默认规则',
      conditionReview: { source_hash: 'a'.repeat(64), review_token: 'b'.repeat(64) },
    }
    const savedRoute = ref({ route_id: 99, workflow_revision: 3 })
    const workflowResetSignal = ref<any>(null)
    const applyConditionReview = vi.fn()
    const handleWorkflowRevisionConflict = vi.fn(async () => false)
    const scope = {
      projectId: ref(12), savedRoute, workflowResetSignal, segmentCards: ref([item]), conditionBusySegmentIds: ref(new Set()),
      inlineEditingText: ref('新的规则'), inlineEditingSegmentId: ref('remove_copper'),
      conditionErrors: ref({}), conditionProcessOptions: ref([]), setConditionBusy: vi.fn(),
      applyConditionReview, handleWorkflowRevisionConflict, hasCurrentConditionText: () => true,
      clearPersistedDraft: vi.fn(), cancelInlineEdit: vi.fn(), resetInlineEdit: vi.fn(),
      markExportedRulePackageOutdated: vi.fn(), setBatchNotice: vi.fn(), showFinalizeNotice: vi.fn(),
      conditionErrorMessage: () => 'stale error', isConditionSourceConflict: () => false,
      normalizeExportProcessName: (name: string) => name, finalizeSegmentDisplayName: () => '除铜',
      buildManualBooleanRuleCandidate: () => ({}), exportProcessIdForItem: () => 'process_remove_copper',
      isExplicitMainlineInstruction, nextTick: async () => {}, parseConditionItem: vi.fn(),
      selectedRuleIds: ref(new Set()), [api]: request,
    }
    // parseConditionItem is the function under test in its own row.
    if (handler === 'parseConditionItem') delete (scope as any).parseConditionItem
    if (advance === 'same-text review') delete (scope as any).hasCurrentConditionText
    const handlers = publicationHandlers(scope, advance === 'same-text review' ? [handler, 'hasCurrentConditionText'] : [handler])
    const execution = handler === 'handleConfirmCondition'
      ? handlers[handler](item, { kind: 'condition', when: { field: 'material.grade', op: 'eq', value: '6061' }, then: { include_process_ids: ['process_remove_copper'], exclude_process_ids: [] } }, false)
      : handler === 'handleSetBoolean' ? handlers[handler](item, '需要除铜')
      : handler === 'handleSaveConfiguration' ? handlers[handler](item, { kind: 'process_configuration', preview: '始终生成除铜', configuration: { process_id: 'process_remove_copper', occurrence: 'always', when: null, relations: [] } }) : handlers[handler](item)
    expect(request).toHaveBeenCalledOnce()
    expect(request.mock.calls[0]?.[0]).toMatchObject({ expected_workflow_revision: 3, expected_review_token: 'b'.repeat(64) })
    if (advance === 'loaded route') savedRoute.value = { route_id: 99, workflow_revision: 4 }
    else if (advance === 'reset signal') workflowResetSignal.value = { projectId: 12, fromStep: 4, workflowRevision: 4, emittedAt: 100 }
    else scope.segmentCards.value[0]!.conditionReview = { ...item.conditionReview, review_token: 'c'.repeat(64) }
    finish(outcome === 'success' ? { review: { status: 'confirmed' } } : new Error('stale response'))
    await execution
    expect(applyConditionReview).not.toHaveBeenCalled()
    expect(handleWorkflowRevisionConflict).not.toHaveBeenCalled()
    expect(scope.markExportedRulePackageOutdated).not.toHaveBeenCalled()
    expect(scope.resetInlineEdit).not.toHaveBeenCalled()
    expect(scope.clearPersistedDraft).not.toHaveBeenCalled()
  })
})

describe('finalize review progress summary', () => {
  it('keeps the confirmed rule count without rendering the decorative mini progress bar', () => {
    expect(template).toContain('已确认 <strong>{{ confirmedRuleCount }}/{{ reviewableRuleCount }}</strong>')
    expect(template).not.toContain('mini-progress-bar')
    expect(template).not.toContain('mini-progress-fill')
    expect(styles).not.toContain('.mini-progress-bar')
    expect(styles).not.toContain('.mini-progress-fill')
  })
})


describe('single footer validation entry', () => {
  it.each(['resettingWorkflow', 'reviewAndExporting', 'batchParsing', 'batchReviewing'])('disables the remaining navigation entry while %s is active', busy => {
    function find(node: any): any { return node.tag === 'WorkflowNavFooter' ? node : (node.children || []).map(find).find(Boolean) }
    const node = find(descriptor.template!.ast)
    const compiled = transformSync(compileTemplate({ source: node.loc.source, filename: 'FinalizeView.vue', id: 'footer-gates' }).code, { loader: 'js', format: 'cjs' }).code
    const mod = { exports: {} as any }
    new Function('require', 'module', 'exports', compiled)(() => ({ ...Vue, resolveComponent: (name: string) => name }), mod, mod.exports)
    const context = { projectId: 1, loading: false, exportingRulePackage: false, hasUnsavedEdits: false, publishBlockingCount: 0, segmentCards: [{}], resettingWorkflow: false, reviewAndExporting: false, batchParsing: false, batchReviewing: false, error: '', [busy]: true }
    const rendered = mod.exports.render(context, [])
    expect(rendered.props['next-disabled']).toBe(true)
  })
})


describe('persistent validation failure notice', () => {
  function validationNotices() {
    const script = ts.createSourceFile('FinalizeView.ts', descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true)
    const names = ['batchNotice', 'batchNoticeTimer', 'validationIssue', 'finalizeNotices']
    const declarations = script.statements.filter(ts.isVariableStatement).filter(statement =>
      statement.declarationList.declarations.some(d => names.includes(d.name.getText(script)))).map(s => s.getText(script))
    const noticeFunction = script.statements.find(statement => ts.isFunctionDeclaration(statement) && statement.name?.text === 'setBatchNotice')!
    const revisionBinding = script.statements.filter(ts.isVariableStatement).flatMap(statement => statement.declarationList.declarations)
      .find(d => ts.isCallExpression(d.initializer!) && d.initializer.expression.getText(script) === 'useFinalizeRuleRevision')!
    const options = (revisionBinding.initializer as ts.CallExpression).arguments[0] as ts.ObjectLiteralExpression
    const onIssue = options.properties.find(property => ts.isPropertyAssignment(property) && property.name.getText(script) === 'onIssue') as ts.PropertyAssignment
    const scope = { computed, ref, setTimeout, clearTimeout,
      batchConfirmationResult: ref({ successCount: 40, remainingCount: 0 }), batchConfirmationIssues: ref([]),
      preprocessFailureSummary: ref(null), reloadWorkspace: vi.fn(), loading: ref(false), resettingWorkflow: ref(false) }
    return new Function(...Object.keys(scope), ts.transpile(`${declarations.join('\n')}\n${noticeFunction.getText(script)}\nconst issue = ${onIssue.initializer.getText(script)}; return { issue, finalizeNotices, setBatchNotice }`, { target: ts.ScriptTarget.ES2022 }))(...Object.values(scope))
  }
  it('keeps compile failure as an error alongside the older batch success after the info timer expires', () => {
    vi.useFakeTimers()
    try {
      const state = validationNotices()
      state.setBatchNotice('旧的临时信息')
      state.issue('工序配置重复：process_quench')
      vi.advanceTimersByTime(5000)
      const failure = state.finalizeNotices.value.find((notice: any) => notice.level === 'error')
      expect(failure?.summary).toBe('工序配置重复：process_quench')
      expect(state.finalizeNotices.value.some((notice: any) => notice.level === 'success')).toBe(true)
      failure.actions.find((action: any) => action.label === '关闭').run()
      expect(state.finalizeNotices.value.some((notice: any) => notice.level === 'error')).toBe(false)
    } finally { vi.useRealTimers() }
  })
  it('clears the prior validation error when the user starts another validation attempt', async () => {
    const validationIssue = ref('上一次校验失败')
    const handlers = publicationHandlers({ validationIssue,
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false), exportingRulePackage: ref(false),
      unsavedCards: ref([{ segment: { id: 'edit' } }]), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), locateBlockedCard: vi.fn(),
    }, ['handleReviewAndExport'])
    await handlers.handleReviewAndExport()
    expect(validationIssue.value).toBe('')
  })
})
