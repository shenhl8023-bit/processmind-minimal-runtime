import { describe, expect, it } from 'vitest'
import appSource from './App.vue?raw'
import analysisSource from './views/AnalysisView.vue?raw'
import extractSource from './views/ExtractView.vue?raw'
import finalizeSource from './views/FinalizeView.vue?raw'
import finalizePrecheckSource from './components/finalize/FinalizePublishPrecheckDialog.vue?raw'
import generateSource from './views/GenerateView.vue?raw'
import uploadSource from './views/UploadView.vue?raw'

describe('workflow viewport layout', () => {
  it('keeps the application inside the viewport and lets main content own page scrolling', () => {
    expect(appSource).toMatch(/html, body\s*\{[^}]*overflow:\s*hidden;/s)
    expect(appSource).toMatch(/\.app-shell\s*\{[^}]*height:\s*100vh;[^}]*overflow:\s*hidden;/s)
    expect(appSource).toMatch(/\.main-area\s*\{[^}]*min-height:\s*0;[^}]*overflow-y:\s*auto;/s)
    expect(appSource).not.toContain('scrollbar-gutter: stable')
  })

  it('sizes the analysis workspace from its parent instead of recalculating the viewport', () => {
    expect(analysisSource).toMatch(/\.analysis-view\s*\{[^}]*height:\s*100%;/s)
    expect(analysisSource).not.toMatch(/\.analysis-view\s*\{[^}]*height:\s*calc\(100vh/s)
  })

  it('sizes the other workflow workspaces from the same parent container', () => {
    expect(uploadSource).toMatch(/\.upload-view\s*\{[^}]*height:\s*100%;/s)
    expect(extractSource).toMatch(/\.results-area\s*\{[^}]*height:\s*100%;/s)
    expect(finalizeSource).toMatch(/\.finalize-view\s*\{[^}]*height:\s*100%;/s)
    expect(finalizeSource).toMatch(/\.finalize-layout\s*\{[^}]*flex:\s*1;[^}]*min-height:\s*0;/s)
    expect(generateSource).toMatch(/\.generate-view\s*\{[^}]*height:\s*100%;/s)
    expect(generateSource).toMatch(/\.generate-grid\s*\{[^}]*flex:\s*1;[^}]*min-height:\s*0;/s)
    expect(uploadSource).toMatch(/@media\s*\(max-width:\s*900px\)/s)
    expect(uploadSource).toMatch(/\.content-grid\s*\{[^}]*overflow-y:\s*auto;/s)
    expect(uploadSource).toMatch(/\.upload-view\s*\{\s*height:\s*100%;\s*min-height:\s*0;\s*overflow:\s*hidden;/s)
  })

  it('does not recalculate desktop workflow heights from the viewport', () => {
    for (const source of [uploadSource, extractSource, finalizeSource, generateSource]) {
      expect(source).not.toMatch(/^\s*height:\s*calc\(100vh\s*-/m)
      expect(source).not.toMatch(/^\s*min-height:\s*calc\(100vh\s*-/m)
    }
  })

  it('keeps finalize publication status explicit and clears stale precheck results', () => {
    expect(finalizeSource).toContain('ash-publish-state')
    expect(finalizeSource).toContain('FinalizePublishPrecheckDialog')
    expect(finalizePrecheckSource).toContain('规则包暂不可发布')
    expect(finalizePrecheckSource).toContain('修复映射')
    expect(finalizeSource).toContain('function openPrecheckDialog()')
    expect(finalizeSource).toContain('openFinalizePrecheckDialog(showPrecheckDialog)')
    expect(finalizeSource).toContain('发布预检有 ${precheckBlockerCount.value} 项待修复')
    expect(finalizeSource).toContain('empty-mark--success')
    expect(finalizeSource).toMatch(/precheckResult\.value\s*=\s*null/)
  })

  it('keeps delivery details accessible after precheck and the resolved-filter empty state compact', () => {
    expect(finalizeSource).toMatch(/v-if="precheckResult && canOpenPrecheck"\s+type="button"\s+class="ash-publish-state ash-publish-state--clickable"/s)
    expect(finalizeSource).toContain("'ash-publish-state--blocked': !precheckResult.ok")
    expect(finalizeSource).toContain('查看交付明细')
    expect(finalizeSource).toContain('暂无待处理工序')
    expect(finalizeSource).toContain('查看全部规则')
    expect(finalizeSource).not.toContain('当前规则已全部确认')
    expect(finalizeSource).not.toContain('可以发布规则包，或切换查看全部规则。')
    expect(finalizeSource).not.toContain('publishStatusLabel')
  })
})
