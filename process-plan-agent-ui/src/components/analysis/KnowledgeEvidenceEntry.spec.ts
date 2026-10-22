import { describe, expect, it } from 'vitest'
import source from './KnowledgeEvidenceEntry.vue?raw'

describe('knowledge evidence entry', () => {
  it('offers a contextual enterprise knowledge route without embedding credentials', () => {
    expect(source).toContain('企业知识依据')
    expect(source).toContain("path: '/knowledge'")
    expect(source).toContain('operation_context')
    expect(source).toContain('query.q')
    expect(source).not.toContain('API_KEY')
  })

  it('carries the saved route version so evidence remains bound to the analyzed route', () => {
    expect(source).toContain('routeVersionId')
    expect(source).toContain('route_version_id')
  })
})
