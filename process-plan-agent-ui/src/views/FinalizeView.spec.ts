import { parse } from '@vue/compiler-sfc'
import { ref } from 'vue'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import { exportBlockingCards, isExplicitMainlineInstruction } from '@/utils/finalizeRulePackage'
import { openFinalizePrecheckDialog } from '@/composables/finalizePrecheckDialog'
import { createLatestWorkflowRequestGuard } from '@/composables/workflowDataCache'
import source from './FinalizeView.vue?raw'

const { descriptor } = parse(source)
const template = descriptor.template?.content || ''
const styles = descriptor.styles.map(style => style.content).join('\n')

// Execute the view's actual publication handler and callbacks with its API
// boundary supplied by the test, without mounting unrelated workspace polling.
function publicationHandlers(scope: Record<string, unknown>, names = ['handleReviewAndExport', 'openPrecheckDialog']) {
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
    `return { ${names.filter(name => name !== 'openPrecheckDialog').join(', ')}${names.includes('handleReviewAndExport') && callbacks.length ? ', onExportIssue, onPrecheck' : ''} }`,
  ].join('\n')
  return new Function(...Object.keys(scope), ts.transpile(code, { target: ts.ScriptTarget.ES2022 }))(...Object.values(scope))
}

describe('finalize publication retries', () => {
  it('shows the delivery summary after a successful precheck while continuing publication', async () => {
    const precheckResult = ref<any>(null)
    const showPrecheckDialog = ref(false)
    const result = { ok: true, checklist: [], blockers: [], export_summary: {
      exported_process_count: 2, exported_step_count: 1, excluded_processes: [], excluded_steps: [],
    } }
    const downloadRuleDocument = vi.fn()
    const handlers = publicationHandlers({
      precheckResult, showPrecheckDialog, exportIssue: ref(null), downloadRuleDocument,
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false),
      exportingRulePackage: ref(false), segmentCards: ref([]), exportBlockingCards,
      unsavedCards: ref([]), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), locateBlockedCard: vi.fn(), openFinalizePrecheckDialog,
    })
    downloadRuleDocument.mockImplementationOnce(async () => handlers.onPrecheck(result))
    await handlers.handleReviewAndExport()
    expect(downloadRuleDocument).toHaveBeenCalledTimes(1)
    expect(precheckResult.value).toEqual(result)
    expect(showPrecheckDialog.value).toBe(true)
  })

  it('exposes publication errors after a successful precheck summary opens', async () => {
    const showPrecheckDialog = ref(false)
    const exportIssue = ref<any>(null)
    const downloadRuleDocument = vi.fn()
    const handlers = publicationHandlers({
      precheckResult: ref<any>(null), showPrecheckDialog, exportIssue, downloadRuleDocument,
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false),
      exportingRulePackage: ref(false), segmentCards: ref([]), exportBlockingCards,
      unsavedCards: ref([]), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), locateBlockedCard: vi.fn(), openFinalizePrecheckDialog,
    })
    downloadRuleDocument.mockImplementationOnce(async () => {
      handlers.onPrecheck({ ok: true, checklist: [], blockers: [], export_summary: {} })
      handlers.onExportIssue({ title: '规则包发布失败', summary: '服务暂不可用（HTTP 503）' })
    })
    await handlers.handleReviewAndExport()
    expect(showPrecheckDialog.value).toBe(false)
    expect(exportIssue.value.summary).toContain('HTTP 503')
  })

  it('shows the current HTTP 503 details after dismissing a previous blocked precheck', async () => {
    const precheckResult = ref<any>(null)
    const showPrecheckDialog = ref(false)
    const exportIssue = ref<any>(null)
    const downloadRuleDocument = vi.fn()
    const handlers = publicationHandlers({
      precheckResult, showPrecheckDialog, exportIssue, downloadRuleDocument,
      reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false),
      exportingRulePackage: ref(false), segmentCards: ref([]), exportBlockingCards,
      unsavedCards: ref([]), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), locateBlockedCard: vi.fn(), openFinalizePrecheckDialog,
    })
    downloadRuleDocument.mockImplementationOnce(async () => {
      handlers.onPrecheck({ ok: false, blockers: [{ code: 'group_template_mapping_missing' }] })
      handlers.onExportIssue({ title: '规则包还不能发布', summary: '请先处理发布前预检清单中的阻塞项。' })
    })
    await handlers.handleReviewAndExport()
    expect(showPrecheckDialog.value).toBe(true)
    expect(exportIssue.value).toBeNull()

    showPrecheckDialog.value = false
    downloadRuleDocument.mockImplementationOnce(async () => {
      handlers.onExportIssue({
        title: '规则包发布失败', summary: '服务暂不可用（HTTP 503），请稍后重试。',
        details: '失败步骤：编译规则包（HTTP 503）',
      })
    })
    await handlers.handleReviewAndExport()
    expect(exportIssue.value?.summary).toContain('HTTP 503')
    expect(exportIssue.value?.details).toContain('编译规则包')
    expect(showPrecheckDialog.value).toBe(false)
  })

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
      preprocessStatus: ref({ task_status: 'running' }), stopPreprocessPolling: vi.fn(),
      hasUnsavedEdits: ref(true), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), loadWorkspace,
    }, ['pollRulePreprocessing'])
    await handlers.pollRulePreprocessing()
    expect(loadWorkspace).not.toHaveBeenCalled()
  })
})

describe('finalize background response ownership', () => {
  function preprocessingScope() {
    return {
      projectId: ref(12), savedRoute: ref({ route_id: 99, workflow_revision: 3 }),
      workflowResetSignal: ref<any>(null), finalizeViewActive: true, preprocessEpoch: 0,
      preprocessRefreshInFlight: null, preprocessPollTimer: null, lastRulePreprocessTriggerKey: '',
      preprocessStatus: ref<any>({ task_status: 'running' }),
      hasUnsavedEdits: ref(true), conditionBusySegmentIds: ref(new Set()),
      setBatchNotice: vi.fn(), stopPreprocessPolling: vi.fn(), loadWorkspace: vi.fn(),
      reviewableCards: ref([{ segment: { id: 'copper' }, conditionText: '需要镀铜' }]),
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
      precheckResult: ref(null), validMappingCount: ref(1), loading: ref(false), conditionErrors: ref({}),
      selectedRuleIds: ref(new Set()), error: ref(''), workspaceErrorTitle: ref(''), FINALIZE_VIEW_COPY: { errorTitle: '' },
      listProjects: async () => [{ id: 12 }, { id: 28 }], route: { path: '/finalize', query: { project_id: '12' } },
      resolveAvailableProjectId: (id: string) => id, projectName: ref(''), router: { replace: vi.fn() },
      getSavedNormalizedRoute: async (id: number) => ({ route_id: id === 12 ? 99 : 108, workflow_revision: 3, segments: [] }),
      listOperations: async () => [], getSupersetRoute: async () => ({ superset_route: [] }),
      getLatestFinalizedRulePackage: async (id: number) => id === 12 ? { schema_version: '2.0', route_version_id: 99, content_hash: 'hash', version: 5 } : null,
      getConditionFieldRegistry: async () => ({ fields: [] }), getCurrentGroupTemplate: async () => ({}),
      getTemplateMappingStatus: () => ({ validCount: 1 }), buildFinalTemplateMappingOperations: () => [],
      operations: ref([]), conditionFields: ref([]), clearRuleEditStates: vi.fn(), cancelInlineEdit: vi.fn(),
      readDrafts: () => false, activeSegmentId: ref(''), nextTick: async () => {},
      lastExportedRulePackageVersion: ref<number | null>(null), outdatedRulePackageVersion: ref<number | null>(null),
      segmentCards: ref([]), exportBlockingCards: () => [], buildCompileRequestFromCards: () => ({}),
      resolveFinalizePhase: vi.fn(), finalizeSegmentPrimarySteps: vi.fn(), finalizeSegmentAttachedSteps: vi.fn(), finalizeSegmentStepNodes: vi.fn(),
      compileRulePackage: vi.fn(async () => ({ content_hash: 'hash' })), loadedDataRevision: 0, getWorkflowDataRevision: () => 0,
      startRulePreprocessingForWorkspace: vi.fn(),
    }
  }

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

  it('does not apply a failed content-hash check from the previously loaded project', async () => {
    let rejectCompile!: (reason: Error) => void
    const pendingCompile = new Promise((_resolve, reject) => { rejectCompile = reject })
    const scope = { ...workspaceScope(), compileRulePackage: vi.fn(() => pendingCompile) }
    const handlers = publicationHandlers(scope, ['loadWorkspace'])
    const oldLoad = handlers.loadWorkspace()
    await vi.waitFor(() => expect(scope.compileRulePackage).toHaveBeenCalledOnce())
    scope.route.query.project_id = '28'
    await handlers.loadWorkspace()
    expect(scope.projectId.value).toBe(28)
    rejectCompile(new Error('旧项目校验失败'))
    await oldLoad
    expect(scope.outdatedRulePackageVersion.value).toBeNull()
    expect(scope.lastExportedRulePackageVersion.value).toBeNull()
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
  ])))('ignores a stale $outcome from $handler after revision advances through $advance', async ({ handler, api, outcome, advance }) => {
    let finish!: (value: any) => void
    const pending = new Promise((resolve, reject) => { finish = outcome === 'success' ? resolve : reject })
    const request = vi.fn((_payload: unknown) => pending)
    const item = {
      segment: { id: 'remove_copper' }, conditionText: '原来的规则', defaultConditionText: '默认规则',
      conditionReview: { source_hash: 'a'.repeat(64) },
    }
    const savedRoute = ref({ route_id: 99, workflow_revision: 3 })
    const workflowResetSignal = ref<any>(null)
    const applyConditionReview = vi.fn()
    const handleWorkflowRevisionConflict = vi.fn(async () => false)
    const scope = {
      projectId: ref(12), savedRoute, workflowResetSignal, conditionBusySegmentIds: ref(new Set()),
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
    const handlers = publicationHandlers(scope, [handler])
    const execution = handler === 'handleConfirmCondition'
      ? handlers[handler](item, {}, false)
      : handler === 'handleSetBoolean' ? handlers[handler](item, '需要除铜')
      : handler === 'handleSaveConfiguration' ? handlers[handler](item, { kind: 'process_configuration', preview: '始终生成除铜', configuration: { process_id: 'process_remove_copper', occurrence: 'always', when: null, relations: [] } }) : handlers[handler](item)
    expect(request).toHaveBeenCalledOnce()
    expect(request.mock.calls[0]?.[0]).toMatchObject({ expected_workflow_revision: 3 })
    if (advance === 'loaded route') savedRoute.value = { route_id: 99, workflow_revision: 4 }
    else workflowResetSignal.value = { projectId: 12, fromStep: 4, workflowRevision: 4, emittedAt: 100 }
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
