import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getConditionFieldRegistry: vi.fn(),
  getFinalizedRulePackageStatus: vi.fn(),
  getSavedNormalizedRoute: vi.fn(),
  getSupersetRoute: vi.fn(),
  listOperations: vi.fn(),
  listProjects: vi.fn(),
}))

vi.mock('@/api', () => ({
  getSavedNormalizedRoute: mocks.getSavedNormalizedRoute,
  getSupersetRoute: mocks.getSupersetRoute,
  listOperations: mocks.listOperations,
  listProjects: mocks.listProjects,
}))

vi.mock('@/api/rulePackages', () => ({
  compileRulePackage: mocks.compileRulePackage,
  getConditionFieldRegistry: mocks.getConditionFieldRegistry,
  getFinalizedRulePackageStatus: mocks.getFinalizedRulePackageStatus,
}))

import { useFinalizeWorkspace } from './useFinalizeWorkspace'

function routeResult(projectId: number, routeId = projectId * 10) {
  return {
    route_id: routeId,
    project_id: projectId,
    version: 1,
    workflow_revision: 7,
    segments: [{ id: `segment_${projectId}` }],
  } as any
}

function packageStatus(projectId: number, executable = true) {
  return {
    project_id: projectId,
    project_status: 'ROUTE_SET_READY',
    workflow_revision: 7,
    route: { id: projectId * 10, version: 1 },
    latest_package: {
      id: projectId * 100,
      version: 3,
      route_version_id: projectId * 10,
      schema_version: '2.0',
      content_hash: `hash-${projectId}`,
      status: executable ? 'published' : 'archived',
    },
    can_publish: true,
    can_generate: executable,
    package_executable: executable,
    blockers: executable ? [] : [{
      code: 'published_rule_sources_changed',
      message: '当前规则来源已变化。',
      blocks: ['generate'],
    }],
    review_summary: {
      total: 2,
      confirmed: 2,
      pending: 0,
      invalid_factor_bindings: 0,
    },
    kmai_compatibility: {
      available: executable,
      valid: executable,
      error_count: 0,
      warning_count: 0,
      factor_catalog_version: '2026.11',
    },
  }
}

function registry() {
  return {
    version: '2026.08',
    fields: [{ key: 'material.grade' }],
    factors: [{ factor_id: 'material.grade' }],
  } as any
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((done) => { resolve = done })
  return { promise, resolve }
}

describe('useFinalizeWorkspace', () => {
  beforeEach(() => {
    Object.values(mocks).forEach(mock => mock.mockReset())
    mocks.listProjects.mockResolvedValue([{ id: 12, name: '轴类项目' }])
    mocks.getSavedNormalizedRoute.mockResolvedValue(routeResult(12))
    mocks.listOperations.mockResolvedValue([{ id: 1, name: '车削' }])
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [{ id: 2, name: '磨削' }] })
    mocks.getConditionFieldRegistry.mockResolvedValue(registry())
    mocks.getFinalizedRulePackageStatus.mockResolvedValue(packageStatus(12))
    mocks.compileRulePackage.mockResolvedValue({ content_hash: 'hash-12' })
  })

  it('loads the complete workspace and keeps a matching published package current', async () => {
    const readDrafts = vi.fn()
    const onRouteLoaded = vi.fn()
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts,
      onRouteLoaded,
    })

    await workspace.loadWorkspace()

    expect(workspace.projectId.value).toBe(12)
    expect(workspace.projectName.value).toBe('轴类项目')
    expect(workspace.savedRoute.value?.route_id).toBe(120)
    expect(workspace.operations.value).toEqual([{ id: 1, name: '车削' }])
    expect(workspace.supersetOperations.value).toEqual([{ id: 2, name: '磨削' }])
    expect(workspace.factorCatalogVersion.value).toBe('2026.08')
    expect(workspace.currentPublishedPackage.value?.version).toBe(3)
    expect(workspace.outdatedRulePackageVersion.value).toBeNull()
    expect(workspace.rulePackageStatus.value?.can_generate).toBe(true)
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(readDrafts).toHaveBeenCalledOnce()
    expect(onRouteLoaded).toHaveBeenCalledWith(expect.objectContaining({ route_id: 120 }))
  })

  it('keeps the route usable when the condition registry fails independently', async () => {
    mocks.getConditionFieldRegistry.mockRejectedValueOnce(new Error('registry offline'))
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
    })

    await workspace.loadWorkspace()

    expect(workspace.savedRoute.value?.route_id).toBe(120)
    expect(workspace.error.value).toBe('')
    expect(workspace.factorCatalogReady.value).toBe(false)
    expect(workspace.factorCatalogError.value).toContain('标准因子目录加载失败')
  })

  it('marks the latest historical package outdated from a stable server blocker', async () => {
    mocks.getFinalizedRulePackageStatus.mockResolvedValueOnce(packageStatus(12, false))
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
    })

    await workspace.loadWorkspace()

    expect(workspace.currentPublishedPackage.value).toBeNull()
    expect(workspace.outdatedRulePackageVersion.value).toBe(3)
    expect(workspace.rulePackageStatus.value?.blockers[0]?.code)
      .toBe('published_rule_sources_changed')
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
  })

  it('refreshes only the rule-package status after a persisted review change', async () => {
    mocks.getFinalizedRulePackageStatus
      .mockResolvedValueOnce({
        ...packageStatus(12),
        can_publish: false,
        blockers: [{
          code: 'pending_rule_reviews',
          message: '仍有规则需要确认。',
          blocks: ['publish'],
          count: 1,
        }],
      })
      .mockResolvedValueOnce(packageStatus(12))
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
    })

    await workspace.loadWorkspace()
    expect(workspace.rulePackageStatus.value?.can_publish).toBe(false)

    await workspace.refreshRulePackageStatus()

    expect(workspace.rulePackageStatus.value?.can_publish).toBe(true)
    expect(workspace.currentPublishedPackage.value?.version).toBe(3)
    expect(mocks.getSavedNormalizedRoute).toHaveBeenCalledOnce()
    expect(mocks.getFinalizedRulePackageStatus).toHaveBeenCalledTimes(2)
  })

  it('keeps package capabilities unknown when the server status request fails', async () => {
    mocks.getFinalizedRulePackageStatus.mockRejectedValueOnce({
      response: { data: { detail: '规则包状态暂时不可用' } },
    })
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
    })

    await workspace.loadWorkspace()

    expect(workspace.rulePackageStatus.value).toBeNull()
    expect(workspace.currentPublishedPackage.value).toBeNull()
    expect(workspace.error.value).toContain('规则包状态暂时不可用')
  })

  it('ignores older route and package status responses after a newer project load starts', async () => {
    const firstRoute = deferred<any>()
    const firstStatus = deferred<any>()
    let requestedProjectId = '12'
    mocks.listProjects.mockResolvedValue([
      { id: 12, name: '旧项目' },
      { id: 22, name: '新项目' },
    ])
    mocks.getSavedNormalizedRoute.mockImplementation((projectId: number) => (
      projectId === 12 ? firstRoute.promise : Promise.resolve(routeResult(22))
    ))
    mocks.listOperations.mockImplementation((projectId: number) => Promise.resolve([{ id: projectId }]))
    mocks.getSupersetRoute.mockResolvedValue({ superset_route: [] })
    mocks.getFinalizedRulePackageStatus.mockImplementation((projectId: number) => (
      projectId === 12 ? firstStatus.promise : Promise.resolve(packageStatus(22))
    ))
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => requestedProjectId,
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
    })

    const oldLoad = workspace.loadWorkspace()
    await vi.waitFor(() => expect(mocks.getSavedNormalizedRoute).toHaveBeenCalledWith(12, false))
    requestedProjectId = '22'
    await workspace.loadWorkspace()
    firstRoute.resolve(routeResult(12))
    firstStatus.resolve(packageStatus(12))
    await oldLoad

    expect(workspace.projectId.value).toBe(22)
    expect(workspace.projectName.value).toBe('新项目')
    expect(workspace.savedRoute.value?.route_id).toBe(220)
    expect(workspace.rulePackageStatus.value?.project_id).toBe(22)
    expect(workspace.currentPublishedPackage.value?.id).toBe(2200)
  })
})
