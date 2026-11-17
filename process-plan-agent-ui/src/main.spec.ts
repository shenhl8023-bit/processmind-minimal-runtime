import { describe, expect, it, vi } from 'vitest'
import ts from 'typescript'
import source from './main.ts?raw'

describe('application bootstrap', () => {
  it('waits for product initialization before creating or mounting business components', async () => {
    let finish!: () => void
    const pending = new Promise<void>(resolve => { finish = resolve })
    const app = { use: vi.fn(), mount: vi.fn() }
    const createApp = vi.fn(() => app)
    const sync = vi.fn()
    const require = (id: string) => {
      if (id === 'vue') return { createApp }
      if (id === './App.vue') return { default: {} }
      if (id === './router/index') return { default: {} }
      if (id === './api/productStatus') return { refreshProductStatus: () => pending, startProductStatusSync: sync }
      if (id.startsWith('./styles/') && id.endsWith('.css')) return {}
      throw new Error(`Unexpected dependency ${id}`)
    }
    new Function('require', 'exports', ts.transpile(source, { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2020 }))(require, {})
    expect(createApp).not.toHaveBeenCalled()
    expect(app.mount).not.toHaveBeenCalled()
    finish()
    await pending
    expect(createApp).toHaveBeenCalledOnce()
    expect(app.mount).toHaveBeenCalledWith('#app')
    expect(sync).toHaveBeenCalledOnce()
  })
})
