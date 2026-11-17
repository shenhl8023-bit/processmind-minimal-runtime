import { beforeEach, describe, expect, it, vi } from 'vitest'

const { getProgress } = vi.hoisted(() => ({ getProgress: vi.fn() }))
vi.mock('@/api/projects', () => ({ getProjectWorkflowProgress: getProgress }))

import {
  guardWorkflowRoute,
  resolveWorkflowRouteAccess,
  workflowBlockedNotice,
  workflowNavigationProgress,
} from './workflowNavigation'
import { productAccess, productStatus } from './productStatus'

beforeEach(() => {
  productAccess.value = 'ready'
  productStatus.value = {
    edition: 'full', template_mapping_enabled: true,
    expires_at: null, expired: false, server_time: '2026-10-30T10:00:00+08:00',
  }
  getProgress.mockReset()
  workflowBlockedNotice.value = ''
  workflowNavigationProgress.value = null
})

describe('workflow route access', () => {
  it.each(['/template-mapping', '/template-mapping/', '/TEMPLATE-MAPPING'])('redirects hidden full mapping %s while preserving license capability', async path => {
    productStatus.value = { ...productStatus.value!, template_mapping_enabled: false }
    getProgress.mockResolvedValue({ project_id: 17, completed_steps: 5, max_available_step: 6, workflow_revision: 8 })
    await expect(guardWorkflowRoute({ path, query: { project_id: '17' } }))
      .resolves.toEqual({ path: '/generate', query: { project_id: '17' } })
    expect(workflowBlockedNotice.value).toBe('')
    productStatus.value = { ...productStatus.value!, template_mapping_enabled: true }
    await expect(guardWorkflowRoute({ path, query: { project_id: '17' } })).resolves.toBe(true)
  })

  it.each([
    { path: '/knowledge', query: {}, expectedQuery: {} },
    { path: '/knowledge', query: { project_id: '17', q: 'allowance', route_version_id: '9' }, expectedQuery: { project_id: '17' } },
    { path: '/Knowledge', query: { project_id: '17' }, expectedQuery: { project_id: '17' } },
    { path: '/KNOWLEDGE/', query: {}, expectedQuery: {} },
  ])('redirects basic knowledge access to upload with only project context: $path $query', async ({ path, query, expectedQuery }) => {
    productStatus.value = {
      edition: 'basic-trial', template_mapping_enabled: false,
      expires_at: '2026-12-31T00:00:00+08:00', expired: false, server_time: '2026-10-30T10:00:00+08:00',
    }
    await expect(guardWorkflowRoute({ path, query }))
      .resolves.toEqual({ path: '/upload', query: expectedQuery })
  })

  it('keeps direct knowledge access available in the full edition', async () => {
    await expect(guardWorkflowRoute({ path: '/knowledge', query: { project_id: '17' } }))
      .resolves.toBe(true)
  })

  it('keeps basic finalize and generate at steps four and five', () => {
    const progress = { project_id: 17, completed_steps: 3, max_available_step: 4, workflow_revision: 8 }
    expect(resolveWorkflowRouteAccess('/finalize', { project_id: '17' }, progress, false)).toBe(true)
    expect(resolveWorkflowRouteAccess('/generate', { project_id: '17' }, progress, false))
      .toEqual({ path: '/finalize', query: { project_id: '17' } })
  })

  it('redirects a retired basic mapping URL through the validation access check', () => {
    expect(resolveWorkflowRouteAccess('/template-mapping', { project_id: '17' }, {
      project_id: 17, completed_steps: 4, max_available_step: 5, workflow_revision: 8,
    }, false)).toEqual({ path: '/generate', query: { project_id: '17' } })
    expect(resolveWorkflowRouteAccess('/template-mapping', { project_id: '17' }, {
      project_id: 17, completed_steps: 2, max_available_step: 3, workflow_revision: 8,
    }, false)).toEqual({ path: '/analysis', query: { project_id: '17' } })
  })

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

  it('allows finalization after analysis, while optional mapping still requires validation', () => {
    expect(resolveWorkflowRouteAccess('/finalize', { project_id: '17' }, {
      project_id: 17,
      completed_steps: 3,
      max_available_step: 4,
      workflow_revision: 8,
    })).toBe(true)
    expect(resolveWorkflowRouteAccess('/template-mapping', { project_id: '17' }, {
      project_id: 17, completed_steps: 4, max_available_step: 5, workflow_revision: 8,
    })).toEqual({ path: '/generate', query: { project_id: '17' } })
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

    await expect(guardWorkflowRoute({ path: '/finalize', query: { project_id: '17' } }))
      .resolves.toBe(true)
    expect(workflowBlockedNotice.value).toBe('')
  })

  it('does not let an older project check clear the current project blocked notice', async () => {
    let resolveStale!: (progress: any) => void
    let resolveCurrent!: (progress: any) => void
    getProgress
      .mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveCurrent = resolve }))

    const staleRequest = guardWorkflowRoute({ path: '/generate', query: { project_id: '17' } })
    const currentRequest = guardWorkflowRoute({ path: '/generate', query: { project_id: '18' } })

    resolveCurrent({ project_id: 18, completed_steps: 1, max_available_step: 2, workflow_revision: 3 })
    await currentRequest
    expect(workflowBlockedNotice.value).toContain('请先完成')

    resolveStale({ project_id: 17, completed_steps: 5, max_available_step: 6, workflow_revision: 9 })
    await staleRequest

    expect(workflowBlockedNotice.value).toContain('请先完成')
  })

  it('does not let an older blocked project check replace the current project notice', async () => {
    let resolveStale!: (progress: any) => void
    let resolveCurrent!: (progress: any) => void
    getProgress
      .mockImplementationOnce(() => new Promise((resolve) => { resolveStale = resolve }))
      .mockImplementationOnce(() => new Promise((resolve) => { resolveCurrent = resolve }))

    const staleRequest = guardWorkflowRoute({ path: '/generate', query: { project_id: '17' } })
    const currentRequest = guardWorkflowRoute({ path: '/generate', query: { project_id: '18' } })

    resolveCurrent({ project_id: 18, completed_steps: 5, max_available_step: 6, workflow_revision: 3 })
    await currentRequest
    expect(workflowBlockedNotice.value).toBe('')

    resolveStale({ project_id: 17, completed_steps: 1, max_available_step: 2, workflow_revision: 9 })
    await staleRequest

    expect(workflowBlockedNotice.value).toBe('')
  })
})
