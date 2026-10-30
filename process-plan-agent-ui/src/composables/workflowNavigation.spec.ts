import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getProgress } = vi.hoisted(() => ({ getProgress: vi.fn() }))
vi.mock('@/api/projects', () => ({ getProjectWorkflowProgress: getProgress }))

import {
  guardWorkflowRoute,
  resolveWorkflowRouteAccess,
  workflowBlockedNotice,
  workflowNavigationProgress,
} from './workflowNavigation'

beforeEach(() => {
  getProgress.mockReset()
  workflowBlockedNotice.value = ''
  workflowNavigationProgress.value = null
})

describe('workflow route access', () => {
  it('redirects a direct step-three URL when step two has not been saved', () => {
    expect(resolveWorkflowRouteAccess('/analysis', { project_id: '17' }, {
      project_id: 17,
      completed_steps: 1,
      max_available_step: 2,
      workflow_revision: 8,
    })).toEqual({ path: '/extract', query: { project_id: '17' } })
  })

  it('keeps template mapping locked until every step-three segment is complete', () => {
    expect(resolveWorkflowRouteAccess('/template-mapping', { project_id: '17' }, {
      project_id: 17,
      completed_steps: 2,
      max_available_step: 3,
      workflow_revision: 8,
    })).toEqual({ path: '/analysis', query: { project_id: '17' } })
  })

  it('allows the next step once the previous milestone is complete', () => {
    expect(resolveWorkflowRouteAccess('/template-mapping', { project_id: '17' }, {
      project_id: 17,
      completed_steps: 3,
      max_available_step: 4,
      workflow_revision: 8,
    })).toBe(true)
  })

  it('redirects project workflow URLs without a project to upload', () => {
    expect(resolveWorkflowRouteAccess('/generate', {}, null)).toEqual({ path: '/upload' })
  })

  it('blocks direct navigation and returns the user to the latest available step', async () => {
    getProgress.mockResolvedValue({
      project_id: 17,
      completed_steps: 1,
      max_available_step: 2,
      workflow_revision: 8,
    })

    await expect(guardWorkflowRoute({ path: '/analysis', query: { project_id: '17' } }))
      .resolves.toEqual({ path: '/extract', query: { project_id: '17' } })
    expect(workflowBlockedNotice.value).toContain('路线归并')
  })

  it('allows direct navigation when the previous step is complete', async () => {
    getProgress.mockResolvedValue({
      project_id: 17,
      completed_steps: 3,
      max_available_step: 4,
      workflow_revision: 8,
    })

    await expect(guardWorkflowRoute({ path: '/template-mapping', query: { project_id: '17' } }))
      .resolves.toBe(true)
    expect(workflowBlockedNotice.value).toBe('')
  })
})
