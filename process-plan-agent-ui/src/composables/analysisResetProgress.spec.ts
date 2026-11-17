import { describe, expect, it, vi } from 'vitest'
import { ref, watch } from 'vue'
import ts from 'typescript'
import workspace from './useAnalysisWorkspace.ts?raw'

function resetWith(scope: Record<string, unknown>) {
  const script = ts.createSourceFile('workspace.ts', workspace, ts.ScriptTarget.Latest, true)
  let declaration: ts.FunctionDeclaration | undefined
  function visit(node: ts.Node) {
    if (ts.isFunctionDeclaration(node) && node.name?.text === 'resetAllAnalysisAnswers') declaration = node
    ts.forEachChild(node, visit)
  }
  visit(script)
  const environment = { disposed: false, watch, ...scope }
  return new Function(...Object.keys(environment), ts.transpile(declaration!.getText(script) + '; return resetAllAnalysisAnswers', { target: ts.ScriptTarget.ES2022 }))(...Object.values(environment))
}

describe('reset dialog hands over to generation progress', () => {
  it('notifies the view once reset is committed while generation is still pending', async () => {
    let finish!: () => void
    const generation = new Promise<void>(resolve => { finish = resolve })
    const applied = vi.fn()
    const scope = {
      resettingWorkflow: ref(false), projectId: ref(5), savedRoute: ref({ workflow_revision: 7 }), error: ref(''),
      resetWorkflow: vi.fn().mockResolvedValue({ project_id: 5, workflow_revision: 8 }),
      publishWorkflowReset: vi.fn(), workflowResetSignal: ref({ emittedAt: 3 }), locallyHandledResetAt: 0,
      applyAnalysisWorkflowReset: vi.fn(() => generation),
    }
    const pending = resetWith(scope)(applied)
    await Promise.resolve()
    expect(applied).toHaveBeenCalledOnce()
    expect(scope.applyAnalysisWorkflowReset).toHaveBeenCalledOnce()
    expect(scope.resettingWorkflow.value).toBe(true)
    finish()
    expect(await pending).toBe(true)
    expect(scope.resettingWorkflow.value).toBe(false)
  })

  it('keeps the dialog open when the reset request fails', async () => {
    const applied = vi.fn()
    const error = ref('')
    const quiet = vi.spyOn(console, 'error').mockImplementation(() => {})
    try {
      expect(await resetWith({
        resettingWorkflow: ref(false), projectId: ref(5), savedRoute: ref({ workflow_revision: 7 }), error,
        resetWorkflow: vi.fn().mockRejectedValue({ response: { data: { detail: '版本已更新' } } }),
      })(applied)).toBe(false)
      expect(applied).not.toHaveBeenCalled()
      expect(error.value).toBe('版本已更新')
    } finally { quiet.mockRestore() }
  })
})
