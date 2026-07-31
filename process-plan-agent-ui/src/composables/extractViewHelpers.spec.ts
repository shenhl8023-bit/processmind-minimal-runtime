import { describe, expect, it } from 'vitest'
import { resolveRouteWorkspaceDisplayState } from './extractViewHelpers'

describe('extract view display state', () => {
  it('keeps the route workspace mounted while the template mapping dialog is open', () => {
    expect(resolveRouteWorkspaceDisplayState({
      routeWorkspaceLoading: true,
      templateGroupMappingVisible: true,
    })).toBe('workspace')
  })

  it('shows route loading progress when no template mapping dialog is open', () => {
    expect(resolveRouteWorkspaceDisplayState({
      routeWorkspaceLoading: true,
      templateGroupMappingVisible: false,
    })).toBe('loading')
  })
})
