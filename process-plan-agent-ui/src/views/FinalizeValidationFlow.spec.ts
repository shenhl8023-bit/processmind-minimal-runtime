import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import { ref } from 'vue'
import { expect, it, vi } from 'vitest'
import source from './FinalizeView.vue?raw'

it('prepares current rules for validation from step four without exporting or entering template mapping', () => {
  const template = parse(source).descriptor.template!.content
  expect(template).not.toContain('@click="goToTemplateMapping"')
  expect(template).toContain('保存并进入路线验证')
  expect(template).toContain('previous-label="← 返回规则分析"')
})
it('runs the executable-revision action after review instead of invoking a package download', async () => {
  const script = ts.createSourceFile('FinalizeView.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
  const declaration = script.statements.find((n): n is ts.FunctionDeclaration => ts.isFunctionDeclaration(n) && n.name?.text === 'handleReviewAndExport')!
  const prepareValidation = vi.fn(), downloadRuleDocument = vi.fn()
  const validationIssue = ref('上次校验失败')
  const scope = { validationIssue, prepareValidation, downloadRuleDocument, reviewAndExporting: ref(false), batchParsing: ref(false), batchReviewing: ref(false), exportingRulePackage: ref(false), unsavedCards: ref([]), conditionBusySegmentIds: ref(new Set()), exportBlockingCards: () => [], segmentCards: ref([]), setBatchNotice: vi.fn(), locateBlockedCard: vi.fn(), precheckResult: ref(null), showPrecheckDialog: ref(false), exportIssue: ref(null) }
  const run = new Function('scope', `with(scope) { ${ts.transpile(declaration.getText(script))}; return handleReviewAndExport }`)(scope)
  await run()
  expect(prepareValidation).toHaveBeenCalledOnce()
  expect(validationIssue.value).toBe('')
  expect(downloadRuleDocument).not.toHaveBeenCalled()
})
