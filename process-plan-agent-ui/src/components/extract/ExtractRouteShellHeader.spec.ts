import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import ExtractRouteShellHeader from './ExtractRouteShellHeader.vue'

async function renderHeader(canEnter: boolean, statusLabel: string) {
  return renderToString(createSSRApp({
    render: () => h(ExtractRouteShellHeader, {
      editUnlocked: canEnter,
      originalCount: 48,
      resultCount: 41,
      pendingCount: canEnter ? 0 : 2,
      canEnter,
      statusLabel,
    }),
  }))
}

describe('extract route shell header', () => {
  it('hides the completed status while keeping counts and rerun action visible', async () => {
    const html = await renderHeader(true, '可进入规则分析')

    expect(html).not.toContain('已收敛')
    expect(html).toContain('原始')
    expect(html).toContain('48')
    expect(html).toContain('结果')
    expect(html).toContain('41')
    expect(html).toContain('重新推理')
  })

  it('keeps the actionable status visible while work is still pending', async () => {
    const html = await renderHeader(false, '待处理')

    expect(html).toContain('待处理')
    expect(html).toContain('重新推理')
  })
})
