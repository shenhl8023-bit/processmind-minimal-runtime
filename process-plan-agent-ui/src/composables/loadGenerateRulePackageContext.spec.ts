import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getFinalizedRulePackageStatus: vi.fn(),
  getOptionalLatestFinalizedRulePackage: vi.fn(),
}))

vi.mock('@/api/rulePackages', () => ({
  getFinalizedRulePackageStatus: mocks.getFinalizedRulePackageStatus,
}))

vi.mock('@/api', () => ({
  getOptionalLatestFinalizedRulePackage: mocks.getOptionalLatestFinalizedRulePackage,
}))

import { loadGenerateRulePackageContext } from './loadGenerateRulePackageContext'

function packageStatus(canGenerate: boolean) {
  return {
    project_id: 12,
    project_status: 'ROUTE_SET_READY',
    workflow_revision: 7,
    route: { id: 31, version: 1 },
    latest_package: {
      id: 56,
      version: 3,
      route_version_id: 31,
      schema_version: '2.0',
      content_hash: 'hash-12',
      status: 'published',
    },
    can_publish: true,
    can_generate: canGenerate,
    package_executable: canGenerate,
    blockers: canGenerate ? [] : [{
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
      available: true,
      valid: canGenerate,
      error_count: canGenerate ? 0 : 1,
      warning_count: 0,
      factor_catalog_version: '2026.11',
    },
  }
}

describe('loadGenerateRulePackageContext', () => {
  beforeEach(() => Object.values(mocks).forEach(mock => mock.mockReset()))

  it('does not load package content when the server blocks generation', async () => {
    mocks.getFinalizedRulePackageStatus.mockResolvedValue(packageStatus(false))

    const result = await loadGenerateRulePackageContext(12, true)

    expect(result.rulePackage).toBeNull()
    expect(result.blockerMessage).toBe('当前规则来源已变化。')
    expect(mocks.getOptionalLatestFinalizedRulePackage).not.toHaveBeenCalled()
  })

  it('loads the complete current package only after the server allows generation', async () => {
    mocks.getFinalizedRulePackageStatus.mockResolvedValue(packageStatus(true))
    mocks.getOptionalLatestFinalizedRulePackage.mockResolvedValue({
      id: 56,
      input_schema: { fields: [] },
    })

    const result = await loadGenerateRulePackageContext(12, false)

    expect(result.rulePackage?.id).toBe(56)
    expect(result.blockerMessage).toBe('')
    expect(mocks.getOptionalLatestFinalizedRulePackage).toHaveBeenCalledWith(12, false)
  })
})
