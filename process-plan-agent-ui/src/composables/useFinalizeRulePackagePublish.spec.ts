import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompileRulePackageResponse, RulePackageV2, StandardFactorDefinition } from '@/api'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  saveFinalizedRulePackage: vi.fn(),
  buildCompileRequestFromCards: vi.fn(),
}))

vi.mock('@/api', () => ({
  compileRulePackage: mocks.compileRulePackage,
  saveFinalizedRulePackage: mocks.saveFinalizedRulePackage,
}))

vi.mock('@/utils/finalizeRulePackage', () => ({
  buildCompileRequestFromCards: mocks.buildCompileRequestFromCards,
  buildRuleReportFromV2Package: () => '# report',
  hasCurrentConfirmedUserRule: () => true,
  requiresConfirmedUserRule: () => false,
}))

import { useFinalizeRulePackagePublish } from './useFinalizeRulePackagePublish'

const firstPackage: RulePackageV2 = {
  manifest: { project_id: 12, package_name: 'first' },
  input_schema: { schema_version: '2.0', fields: [] },
  route_catalog: { schema_version: '2.0', processes: [] },
  route_rules: { schema_version: '2.0', rules: [] },
  test_cases: [],
}

const standardFactors: StandardFactorDefinition[] = [{
  factor_id: 'material.grade',
  label: '材料牌号',
  category: '材料',
  source_field: 'material.grade',
  source_field_aliases: [],
  canonical_value: null,
  allowed_operators: ['eq', 'neq', 'in'],
  kmai_factor_key: 'material_grade',
  kmai_value_mode: 'condition_value',
  runtime_source: 'computed',
}]

function compiled(packageValue: RulePackageV2, valid: boolean): CompileRulePackageResponse {
  return {
    package: packageValue,
    content_hash: valid ? 'second' : 'first',
    validation: { valid: true, errors: [], warnings: [], test_results: [] },
    kmai_compatibility: {
      format: 'kmai-v1',
      valid,
      target_directory: 'rules',
      errors: valid ? [] : [{
        code: 'standard_factor_unbound',
        path: 'route_rules.rules[0].when',
        message: '未绑定标准因子',
      }],
      warnings: [],
      files: {},
      factor_catalog_version: '2026.11',
    },
  }
}

function savedPackage(
  packageValue: RulePackageV2,
  files: Record<string, Record<string, unknown>> = {},
) {
  return {
    version: 3,
    schema_version: '2.0',
    status: 'published',
    manifest: packageValue.manifest,
    input_schema: packageValue.input_schema,
    route_catalog: packageValue.route_catalog,
    route_rules: packageValue.route_rules,
    test_cases: [],
    rule_report_md: '# report',
    validation_report: {},
    kmai_compatibility: {
      format: 'kmai-v1',
      valid: true,
      target_directory: 'rules',
      errors: [],
      warnings: [],
      files,
      factor_catalog_version: '2026.11',
    },
  }
}

function createPublish(options: {
  onPublishReviewRequired?: (review: unknown) => Promise<boolean>
  onPublished?: (packageValue: unknown) => void
  conditionFields?: Array<{ key: string }>
  standardFactors?: StandardFactorDefinition[]
  factorCatalogVersion?: string
  segmentCards?: any[]
}) {
  return useFinalizeRulePackagePublish({
    projectId: ref(12),
    projectName: ref('project'),
    savedRoute: ref({ route_id: 99 }),
    segmentCards: computed(() => options.segmentCards ?? []),
    displayName: () => 'process',
    metaLabel: () => 'meta',
    phaseLabel: () => 'phase',
    primarySteps: () => [],
    attachedSteps: () => [],
    conditionFields: ref(options.conditionFields ?? [{ key: 'cad.features' }]),
    standardFactors: ref(options.standardFactors ?? standardFactors),
    factorCatalogVersion: ref(options.factorCatalogVersion ?? '2026.11'),
    onPublishReviewRequired: options.onPublishReviewRequired,
    onPublished: options.onPublished,
  } as any)
}

describe('useFinalizeRulePackagePublish', () => {
  beforeEach(() => {
    mocks.compileRulePackage.mockReset()
    mocks.saveFinalizedRulePackage.mockReset()
    mocks.buildCompileRequestFromCards.mockReset()
    mocks.buildCompileRequestFromCards.mockReturnValue({ processes: [{ process_id: 'process_1' }] })
  })

  it('waits for publish review before saving a compatible package', async () => {
    const review = vi.fn().mockResolvedValue(false)
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))

    const { publishRulePackage } = createPublish({ onPublishReviewRequired: review })
    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'ready',
      projectName: 'project',
      processCount: 0,
      ruleCount: 0,
    }))
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  })

  it('never saves a blocked review even when the callback confirms it', async () => {
    const invalid = compiled(firstPackage, true)
    invalid.validation = {
      valid: false,
      errors: [{ code: 'invalid_rule', message: 'invalid rule' }],
      warnings: [],
      test_results: [],
    }
    const review = vi.fn().mockResolvedValue(true)
    mocks.compileRulePackage.mockResolvedValueOnce(invalid)

    const { publishRulePackage } = createPublish({ onPublishReviewRequired: review })
    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({ status: 'blocked' }))
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  })

  it('shows the same blocked review when the field registry is unavailable', async () => {
    const review = vi.fn().mockResolvedValue(false)
    const { publishRulePackage } = createPublish({
      conditionFields: [],
      onPublishReviewRequired: review,
    })

    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'blocked',
      validation: null,
      details: [expect.objectContaining({
        code: 'standard_field_registry_unavailable',
        message: '标准字段库尚未加载，请稍后刷新页面再重新审核。',
        sourceSegmentId: '',
      })],
    }))
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  })

  it('blocks before compile when the standard factor catalog is unavailable', async () => {
    const review = vi.fn().mockResolvedValue(false)
    const { publishRulePackage } = createPublish({
      standardFactors: [],
      factorCatalogVersion: '',
      onPublishReviewRequired: review,
    })

    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'blocked',
      validation: null,
      details: [expect.objectContaining({
        code: 'standard_factor_registry_unavailable',
        message: '标准因子目录尚未加载，请重试加载后再重新审核。',
        sourceSegmentId: '',
      })],
    }))
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
  })

  it('shows a local blocked review when static rules cannot bind to the catalog', async () => {
    const review = vi.fn().mockResolvedValue(false)
    mocks.buildCompileRequestFromCards.mockImplementationOnce(() => {
      throw new Error('静态条件「顶尖孔」无法唯一绑定标准因子')
    })
    const { publishRulePackage } = createPublish({ onPublishReviewRequired: review })

    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'blocked',
      details: [expect.objectContaining({
        code: 'standard_factor_binding_failed',
        message: '静态条件「顶尖孔」无法唯一绑定标准因子',
        sourceSegmentId: '',
      })],
    }))
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
  })

  it('keeps a structured source segment on a local card binding blocker', async () => {
    const review = vi.fn().mockResolvedValue(false)
    mocks.buildCompileRequestFromCards.mockImplementationOnce(() => {
      throw Object.assign(new Error('工序 process_hone 的条件根节点：未绑定标准因子'), {
        sourceSegmentId: 'process_hone',
      })
    })
    const { publishRulePackage } = createPublish({
      onPublishReviewRequired: review,
      segmentCards: [{
        segment: { id: 'process_hone' },
        conditionText: '当存在孔精加工要求时，纳入珩孔工序',
      }],
    })

    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'blocked',
      details: [expect.objectContaining({
        code: 'standard_factor_binding_failed',
        processName: 'process',
        sourceText: '当存在孔精加工要求时，纳入珩孔工序',
        sourceSegmentId: 'process_hone',
      })],
    }))
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
  })

  it('compiles once, waits for review, and publishes without a download dependency', async () => {
    const review = vi.fn().mockResolvedValue(true)
    const onPublished = vi.fn()
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))
    const saved = savedPackage(firstPackage)
    mocks.saveFinalizedRulePackage.mockResolvedValueOnce(saved)

    const { publishRulePackage } = createPublish({
      onPublishReviewRequired: review,
      onPublished,
    })
    await publishRulePackage()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(onPublished).toHaveBeenCalledWith(saved)
  })

  it('blocks an invalid compatibility review after exactly one compile', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, false))
    const review = vi.fn().mockResolvedValue(true)
    const { publishRulePackage } = createPublish({ onPublishReviewRequired: review })

    await publishRulePackage()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({ status: 'blocked' }))
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  })
})
