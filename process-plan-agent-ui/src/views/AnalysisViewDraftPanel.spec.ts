import { describe, expect, it, vi } from 'vitest'
import { parse } from '@vue/compiler-sfc'
import { computed, ref } from 'vue'
import ts from 'typescript'
import source from './AnalysisView.vue?raw'

describe('analysis view uses existing question tree as the only visible analysis input', () => {
  it.each([[false, '/finalize'], [true, '/finalize']])('enters rule finalization with edition mapping=%s', (enabled, expectedPath) => {
    const script = ts.createSourceFile('AnalysisView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    const declaration = script.statements.find((statement): statement is ts.FunctionDeclaration => ts.isFunctionDeclaration(statement) && statement.name?.text === 'goToFinalize')!
    const router = { push: vi.fn() }
    const scope = { templateMappingEnabled: ref(enabled), router, projectId: ref(12), savedRoute: ref({ route_id: 99 }), supersetOperations: ref([]), segmentDisplayName: () => '车削', buildProjectRouteQuery: () => ({ project_id: '12' }), startRulePreprocessingForSavedRoute: async () => {} }
    const run = new Function(...Object.keys(scope), ts.transpile(declaration.getText(script) + '; return goToFinalize', { target: ts.ScriptTarget.ES2022 }))(...Object.values(scope))
    run()
    expect(router.push).toHaveBeenCalledWith({ path: expectedPath, query: { project_id: '12' } })
  })
  it('does not mount the standalone rule draft panel', () => {
    expect(source).not.toContain('AnalysisRuleDraftPanel')
    expect(source).not.toContain('规则草稿')
  })
})

describe('PM-079 analysis review filters', () => {
  it('offers only all and pending, keeps partial answers pending and updates after confirmation', () => {
    const script = ts.createSourceFile('AnalysisView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    const statements = ['filteredSegments', 'segmentFilterOptions'].map(name => script.statements.find(statement =>
      ts.isVariableStatement(statement) && statement.declarationList.declarations.some(node => node.name.getText(script) === name),
    )!.getText(script)).join('\n')
    const savedRoute = ref({ segments: [
      { id: 'unstarted', progress: 'is-pending' },
      { id: 'partial', progress: 'is-started' },
      { id: 'complete', progress: 'is-completed' },
    ] })
    const scope = {
      computed, savedRoute, segmentFilter: ref('pending'),
      segmentProgressClass: (segment: { progress: string }) => segment.progress,
      pendingSegmentCount: computed(() => savedRoute.value.segments.filter(s => s.progress === 'is-pending').length),
      inProgressSegmentCount: computed(() => savedRoute.value.segments.filter(s => s.progress === 'is-started').length),
      completedSegmentCount: computed(() => savedRoute.value.segments.filter(s => s.progress === 'is-completed').length),
    }
    const code = ts.transpile(statements + '\nreturn { filteredSegments, segmentFilterOptions }', { target: ts.ScriptTarget.ES2022 })
    const filters = new Function(...Object.keys(scope), code)(...Object.values(scope))
    expect(filters.segmentFilterOptions.value).toEqual([
      { value: 'all', label: '全部', count: 3 },
      { value: 'pending', label: '待处理', count: 2 },
    ])
    expect(filters.filteredSegments.value.map((s: { id: string }) => s.id)).toEqual(['unstarted', 'partial'])
    scope.segmentFilter.value = 'all'
    expect(filters.filteredSegments.value).toHaveLength(3)
    savedRoute.value.segments[1]!.progress = 'is-completed'
    scope.segmentFilter.value = 'pending'
    expect(filters.filteredSegments.value.map((s: { id: string }) => s.id)).toEqual(['unstarted'])
    expect(filters.segmentFilterOptions.value[1].count).toBe(1)
    savedRoute.value.segments[0]!.progress = 'is-completed'
    expect(filters.filteredSegments.value).toHaveLength(0)
    expect(filters.segmentFilterOptions.value[1].count).toBe(0)
  })
})
