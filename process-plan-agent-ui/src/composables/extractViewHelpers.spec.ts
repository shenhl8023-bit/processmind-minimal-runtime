import { describe, expect, it } from 'vitest'

import { canLoadRouteMergeWorkspace } from './extractViewHelpers'

describe('route merge workspace loading guard', () => {
  it('does not load the workspace for an uploaded project', () => {
    expect(canLoadRouteMergeWorkspace('UPLOADED')).toBe(false)
  })

  it('loads the workspace only after the route set is ready', () => {
    expect(canLoadRouteMergeWorkspace('ROUTE_SET_READY')).toBe(true)
    expect(canLoadRouteMergeWorkspace('GENERATED')).toBe(true)
  })
})
