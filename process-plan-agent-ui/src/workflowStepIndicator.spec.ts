import { createSSRApp, defineComponent, h } from 'vue'
import { renderToString } from '@vue/server-renderer'
import { createMemoryHistory, createRouter } from 'vue-router'
import { describe, expect, it, vi } from 'vitest'
import App from './App.vue'
import appSource from './App.vue?raw'

vi.mock('@/router', () => ({
  workflowRouteLoaders: [],
}))

vi.mock('@/components/settings/ModelSettingsDrawer.vue', () => ({
  default: defineComponent({
    name: 'ModelSettingsDrawerStub',
    setup: () => () => h('aside'),
  }),
}))

describe('workflow step indicator', () => {
  it('renders all workflow steps as display-only progress', async () => {
    const emptyView = defineComponent({ render: () => null })
    const router = createRouter({
      history: createMemoryHistory(),
      routes: ['/upload', '/extract', '/analysis', '/finalize', '/generate'].map(path => ({
        path,
        component: emptyView,
      })),
    })
    await router.push('/finalize?project_id=42')
    await router.isReady()

    const app = createSSRApp(App)
    app.use(router)
    const html = await renderToString(app)
    const renderedIndicator = html.match(/<nav class="step-indicator"[\s\S]*?<\/nav>/)?.[0]
    const indicatorTemplate = appSource.match(/<nav class="step-indicator"[\s\S]*?<\/nav>/)?.[0]

    expect(renderedIndicator).toBeDefined()
    expect(renderedIndicator?.match(/class="step completed"/g)).toHaveLength(3)
    expect(renderedIndicator).toContain('class="step active" aria-current="step"')
    expect(renderedIndicator).toContain('class="step available"')
    expect(renderedIndicator).not.toContain('role="button"')
    expect(renderedIndicator).not.toContain('tabindex=')
    expect(renderedIndicator).not.toContain('title=')
    expect(indicatorTemplate).not.toContain('@click=')
    expect(indicatorTemplate).not.toContain('@keydown')
  })
})
