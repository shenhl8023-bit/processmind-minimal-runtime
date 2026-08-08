import { computed } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getConditionFieldRegistry: vi.fn(),
  getOptionalLatestFinalizedRulePackage: vi.fn(),
  getSavedNormalizedRoute: vi.fn(),
  getSupersetRoute: vi.fn(),
  listOperations: vi.fn(),
  listProjects: vi.fn(),
}))

vi.mock('@/api', () => ({
  getOptionalLatestFinalizedRulePackage: mocks.getOptionalLatestFinalizedRulePackage,
  getSavedNormalizedRoute: mocks.getSavedNormalizedRoute,
  getSupersetRoute: mocks.getSupersetRoute,
  listOperations: mocks.listOperations,
  listProjects: mocks.listProjects,
}))

vi.mock('@/api/rulePackages', () => ({
  compileRulePackage: mocks.compileRulePackage,
  getConditionFieldRegistry: mocks.getConditionFieldRegistry,
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

function publishedPackage(projectId: number, routeId = projectId * 10) {
  return {
    id: projectId * 100,
    project_id: projectId,
    route_version_id: routeId,
    version: 3,
    package_name: `project-${projectId}`,
    schema_version: '2.0',
    status: 'published',
    content_hash: `hash-${projectId}`,
  } as any
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
    mocks.getOptionalLatestFinalizedRulePackage.mockResolvedValue(publishedPackage(12))
    mocks.getConditionFieldRegistry.mockResolvedValue(registry())
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
      segmentCards: computed(() => []),
      allCurrentRulesConfirmed: computed(() => true),
      buildCompileRequest: vi.fn().mockReturnValue({ project_id: 12 }),
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
    expect(readDrafts).toHaveBeenCalledOnce()
    expect(onRouteLoaded).toHaveBeenCalledWith(expect.objectContaining({ route_id: 120 }))
  })

  it('keeps the route usable when the condition registry fails independently', async () => {
    mocks.getConditionFieldRegistry.mockRejectedValueOnce(new Error('registry offline'))
    mocks.getOptionalLatestFinalizedRulePackage.mockResolvedValueOnce(null)
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
      segmentCards: computed(() => []),
      allCurrentRulesConfirmed: computed(() => false),
      buildCompileRequest: vi.fn(),
    })

    await workspace.loadWorkspace()

    expect(workspace.savedRoute.value?.route_id).toBe(120)
    expect(workspace.error.value).toBe('')
    expect(workspace.factorCatalogReady.value).toBe(false)
    expect(workspace.factorCatalogError.value).toContain('标准因子目录加载失败')
  })

  it('marks a published package outdated when the compiled content hash differs', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce({ content_hash: 'changed-hash' })
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => '12',
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
      segmentCards: computed(() => []),
      allCurrentRulesConfirmed: computed(() => true),
      buildCompileRequest: vi.fn().mockReturnValue({ project_id: 12 }),
    })

    await workspace.loadWorkspace()

    expect(workspace.currentPublishedPackage.value).toBeNull()
    expect(workspace.outdatedRulePackageVersion.value).toBe(3)
  })

  it('ignores an older route response after a newer project load starts', async () => {
    const firstRoute = deferred<any>()
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
    mocks.getOptionalLatestFinalizedRulePackage.mockResolvedValue(null)
    const workspace = useFinalizeWorkspace({
      requestedProjectId: () => requestedProjectId,
      onProjectResolved: vi.fn(),
      readDrafts: vi.fn(),
      onRouteLoaded: vi.fn(),
      segmentCards: computed(() => []),
      allCurrentRulesConfirmed: computed(() => false),
      buildCompileRequest: vi.fn(),
    })

    const oldLoad = workspace.loadWorkspace()
    await vi.waitFor(() => expect(mocks.getSavedNormalizedRoute).toHaveBeenCalledWith(12, false))
    requestedProjectId = '22'
    await workspace.loadWorkspace()
    firstRoute.resolve(routeResult(12))
    await oldLoad

    expect(workspace.projectId.value).toBe(22)
    expect(workspace.projectName.value).toBe('新项目')
    expect(workspace.savedRoute.value?.route_id).toBe(220)
  })
})
