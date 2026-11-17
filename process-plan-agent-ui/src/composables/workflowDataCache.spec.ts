import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearAllWorkflowDataCache,
  clearWorkflowDataCacheByPrefix,
  clearWorkflowProjectDataCache,
  createLatestWorkflowRequestGuard,
  getWorkflowDataCache,
  getWorkflowDataRevision,
  setWorkflowDataCache,
} from './workflowDataCache'

describe('workflow data cache concurrency', () => {
  beforeEach(() => clearAllWorkflowDataCache())

  it('does not let a response started before reset refill the cache', () => {
    const requestRevision = getWorkflowDataRevision()
    clearAllWorkflowDataCache()

    const stored = setWorkflowDataCache('api:extract:operations:17', ['stale'], requestRevision)

    expect(stored).toBe(false)
    expect(getWorkflowDataCache('api:extract:operations:17')).toBeNull()
  })

  it.each([
    ['project invalidation', () => clearWorkflowProjectDataCache(17)],
    ['prefix invalidation', () => clearWorkflowDataCacheByPrefix('api:extract:operations:17')],
  ])('rejects in-flight responses after empty-cache %s', (_label, invalidate) => {
    const requestRevision = getWorkflowDataRevision()

    invalidate()
    const stored = setWorkflowDataCache('api:extract:operations:17', ['stale'], requestRevision)

    expect(stored).toBe(false)
    expect(getWorkflowDataCache('api:extract:operations:17')).toBeNull()
  })

  it('marks an older page load stale when a newer load starts', () => {
    const guard = createLatestWorkflowRequestGuard()
    const first = guard.start()
    const second = guard.start()

    expect(first.isCurrent()).toBe(false)
    expect(second.isCurrent()).toBe(true)
  })
})
