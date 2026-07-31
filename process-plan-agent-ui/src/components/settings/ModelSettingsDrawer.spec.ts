import { createSSRApp } from 'vue'
import { renderToString, type SSRContext } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.mock('element-plus/es/components/base/style/css', () => ({}))
vi.mock('element-plus/es/components/dialog/style/css', () => ({}))
vi.mock('element-plus/es', async () => {
  const { defineComponent, h } = await import('vue')
  return {
    ElDialog: defineComponent({
      setup(_props, { slots }) {
        return () => h('div', [slots.header?.(), slots.default?.(), slots.footer?.()])
      },
    }),
  }
})

vi.mock('@/api', () => ({
  listSettings: vi.fn().mockResolvedValue([]),
  updateSetting: vi.fn(),
  testLLMConnection: vi.fn(),
  getAvailableModels: vi.fn().mockResolvedValue([]),
}))

import ModelSettingsDrawer from './ModelSettingsDrawer.vue'

describe('ModelSettingsDrawer', () => {
  it('renders only model configuration', async () => {
    const context: SSRContext = {}
    const rendered = await renderToString(createSSRApp(ModelSettingsDrawer, {
      modelValue: true,
    }), context)
    const html = `${rendered}${context.teleports?.body || ''}`

    expect(html).toContain('模型配置')
    expect(html).not.toContain('KmAI 映射')
    expect(html).not.toContain(['项目', '映射'].join(''))
    expect(html).not.toContain(['全局', '映射'].join(''))
    expect(html).not.toContain(['提升为', '全局'].join(''))
  })
})
