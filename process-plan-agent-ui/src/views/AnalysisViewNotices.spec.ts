import { computed, ref } from 'vue'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { describe, expect, it, vi } from 'vitest'
import source from './AnalysisView.vue?raw'

function createNotices() {
  const script = ts.createSourceFile('AnalysisView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const declarations = ['recommendationRetryAvailable', 'analysisNotices'].map(name => script.statements.find(statement =>
    ts.isVariableStatement(statement) && statement.declarationList.declarations.some(declaration => declaration.name.getText(script) === name),
  )!.getText(script)).join('\n')
  const scope = {
    computed, loadSavedRoute: vi.fn(), loading: ref(false), resettingWorkflow: ref(false),
    guidanceGenerating: ref(false), generationElapsedSeconds: ref(0),
    guidanceError: ref(''), guidanceErrorReason: ref(''), error: ref(''),
    savedRoute: ref({ route_id: 7 }), analysisReadOnly: ref(false),
    analysisGuidance: ref({ operation_guidance: {
      a: { recommendation: {}, recommendation_issues: [] },
      b: { recommendation: {}, recommendation_issues: [] },
      c: { recommendation: null, recommendation_issues: ['推荐缺失'] },
    } }),
    recommendationSummary: ref('已采纳 2 道工序推荐；1 道还需手动回答或重试：工序C。'),
    analysisNavSummary: ref('规则分析进度：已确认 2/3'),
  }
  const code = ts.transpile(declarations + '\nreturn analysisNotices', { target: ts.ScriptTarget.ES2022 })
  const notices = new Function(...Object.keys(scope), code)(...Object.values(scope)) as ReturnType<typeof computed<any[]>>
  return { scope, notices }
}

describe('analysis footer feedback', () => {
  it.each([true, false])('does not confuse a save error with route availability (saved route=%s)', (hasRoute) => {
    const script = ts.createSourceFile('AnalysisView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    const declaration = script.statements.find(statement => ts.isVariableStatement(statement)
      && statement.declarationList.declarations.some(item => item.name.getText(script) === 'analysisNavSummary'))!
    const scope = {
      computed, projectId: ref(12), loading: ref(false), error: ref('保存候选失败：版本冲突'),
      savedRoute: ref(hasRoute ? { route_id: 7, segments: [{ id: 'a' }, { id: 'b' }] } : null),
      completedSegmentCount: ref(1), inProgressSegmentCount: ref(0), pendingSegmentCount: ref(1),
    }
    const code = ts.transpile(declaration.getText(script) + '\nreturn analysisNavSummary.value', { target: ts.ScriptTarget.ES2022 })
    const summary = new Function(...Object.keys(scope), code)(...Object.values(scope)) as string
    if (hasRoute) {
      expect(summary).toContain('已确认 1/2')
      expect(summary).not.toContain('没有可分析')
    } else expect(summary).toContain('没有可分析的已保存路线')
  })

  it('retains the actual partial save count alongside missing recommendations and retry', () => {
    const { notices, scope } = createNotices()
    expect(notices.value.map(notice => notice.id)).toEqual(['recommendation-missing', 'adoption'])
    expect(notices.value.find(notice => notice.id === 'adoption')?.summary).toContain('已采纳 2 道')
    expect(notices.value.find(notice => notice.id === 'adoption')?.summary).toContain('工序C')
    notices.value.find(notice => notice.id === 'recommendation-missing')!.actions[0].run()
    expect(scope.loadSavedRoute).toHaveBeenCalledWith(true, true)
  })

  it.each(['guidanceGenerating', 'guidanceError'] as const)('keeps obsolete success hidden while %s is active', (state) => {
    const { notices, scope } = createNotices()
    if (state === 'guidanceGenerating') scope.guidanceGenerating.value = true
    else scope.guidanceError.value = '生成失败'
    expect(notices.value.some(notice => notice.id === 'adoption')).toBe(false)
  })
})
