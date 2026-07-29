import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearAllWorkflowDataCache,
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

  it('marks an older page load stale when a newer load starts', () => {
    const guard = createLatestWorkflowRequestGuard()
    const first = guard.start()
    const second = guard.start()

    expect(first.isCurrent()).toBe(false)
    expect(second.isCurrent()).toBe(true)
  })
})
