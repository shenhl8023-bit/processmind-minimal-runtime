import { createSSRApp } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { describe, expect, it } from 'vitest'
import ExtractRouteShellHeader from './ExtractRouteShellHeader.vue'

describe('ExtractRouteShellHeader', () => {
  it('hides the template mapping tools while keeping rerun available', async () => {
    const html = await renderToString(createSSRApp(ExtractRouteShellHeader, {
      editUnlocked: true,
      originalCount: 48,
      resultCount: 41,
      pendingCount: 0,
      canEnter: true,
      statusLabel: '可进入规则分析',
      hasTemplateAliases: true,
      showTemplateAliases: true,
      notice: '',
    }))

    expect(html).not.toContain('分组模板映射')
    expect(html).not.toContain('详细信息')
    expect(html).toContain('重新推理')
  })
})
