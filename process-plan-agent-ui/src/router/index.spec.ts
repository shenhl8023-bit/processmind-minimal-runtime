import { describe, expect, it, vi } from 'vitest'

vi.mock('vue-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('vue-router')>()
  return {
    ...actual,
    createWebHistory: () => actual.createMemoryHistory(),
  }
})

import router from './index'

describe('workflow routes', () => {
  it('inserts template mapping between analysis and finalization', () => {
    const paths = router.getRoutes().map(route => route.path)
    expect(paths.indexOf('/template-mapping')).toBeGreaterThan(paths.indexOf('/analysis'))
    expect(paths.indexOf('/template-mapping')).toBeLessThan(paths.indexOf('/finalize'))
  })

  it('keeps the process knowledge page and redirects retired domain package URLs', () => {
    const routes = router.getRoutes()
    const retiredPath = router.resolve('/domain-knowledge')

    expect(routes.some(route => route.path === '/knowledge')).toBe(true)
    expect(routes.some(route => route.path === '/domain-knowledge')).toBe(false)
    expect(retiredPath.matched[0]?.redirect).toBe('/upload')
  })
})
