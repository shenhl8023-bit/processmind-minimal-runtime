import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import type { CompileRulePackageResponse, RulePackageV2 } from '@/api'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  saveFinalizedRulePackage: vi.fn(),
  createZipBlob: vi.fn(() => new Blob()),
  downloadBlob: vi.fn(),
}))

vi.mock('@/api', () => ({
  compileRulePackage: mocks.compileRulePackage,
  saveFinalizedRulePackage: mocks.saveFinalizedRulePackage,
}))

vi.mock('@/utils/exportArchive', () => ({
  createZipBlob: mocks.createZipBlob,
  downloadBlob: mocks.downloadBlob,
  textFile: (value: unknown) => JSON.stringify(value),
}))

vi.mock('@/utils/finalizeRulePackage', () => ({
  buildCompileRequestFromCards: () => ({ processes: [{ process_id: 'process_1' }] }),
  buildRuleReportFromV2Package: () => '# report',
  hasCurrentConfirmedUserRule: () => true,
  requiresConfirmedUserRule: () => false,
}))

import { useFinalizeRulePackageExport } from './useFinalizeRulePackageExport'

const firstPackage: RulePackageV2 = {
  manifest: { project_id: 12, package_name: 'first' },
  input_schema: { schema_version: '2.0', fields: [] },
  route_catalog: { schema_version: '2.0', processes: [] },
  route_rules: { schema_version: '2.0', rules: [] },
  test_cases: [],
}

const secondPackage = {
  ...firstPackage,
  manifest: { project_id: 12, package_name: 'second' },
}

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
        code: 'kmai_mapping_required',
        message: 'mapping required',
        field: 'cad.features',
        value: 'unmapped feature',
        occurrences: 1,
        rule_refs: ['feature.unmapped'],
      }],
      warnings: [],
      files: {},
      mapping_signature: valid ? 'second' : 'first',
      mapping_usages: [],
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
      mapping_signature: 'saved',
      mapping_usages: [],
    },
  }
}

function createExport(options: {
  onExportReviewRequired?: (review: unknown) => Promise<boolean>
  conditionFields?: Array<{ key: string }>
}) {
  return useFinalizeRulePackageExport({
    projectId: ref(12),
    projectName: ref('project'),
    savedRoute: ref({ route_id: 99 }),
    segmentCards: computed(() => []),
    displayName: () => 'process',
    metaLabel: () => 'meta',
    phaseLabel: () => 'phase',
    primarySteps: () => [],
    attachedSteps: () => [],
    conditionFields: ref(options.conditionFields ?? [{ key: 'cad.features' }]),
    onExportReviewRequired: options.onExportReviewRequired,
  } as any)
}

describe('useFinalizeRulePackageExport KmAI mapping retry', () => {
  beforeEach(() => {
    mocks.compileRulePackage.mockReset()
    mocks.saveFinalizedRulePackage.mockReset()
    mocks.createZipBlob.mockClear()
    mocks.downloadBlob.mockClear()
  })

  it('waits for export review before saving a compatible package', async () => {
    const review = vi.fn().mockResolvedValue(false)
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, true))

    const { downloadRuleDocument } = createExport({ onExportReviewRequired: review })
    await downloadRuleDocument()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'ready',
      projectName: 'project',
      processCount: 0,
      ruleCount: 0,
    }))
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
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

    const { downloadRuleDocument } = createExport({ onExportReviewRequired: review })
    await downloadRuleDocument()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({ status: 'blocked' }))
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('shows the same blocked review when the field registry is unavailable', async () => {
    const review = vi.fn().mockResolvedValue(false)
    const { downloadRuleDocument } = createExport({
      conditionFields: [],
      onExportReviewRequired: review,
    })

    await downloadRuleDocument()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'blocked',
      validation: null,
      details: ['标准字段库尚未加载，请稍后刷新页面再重新审核。'],
    }))
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('recompiles after resolved mappings and archives the authoritative saved KmAI files', async () => {
    const review = vi.fn().mockResolvedValue(true)
    mocks.compileRulePackage
      .mockResolvedValueOnce(compiled(firstPackage, false))
      .mockResolvedValueOnce(compiled(secondPackage, true))
    mocks.saveFinalizedRulePackage.mockResolvedValue(savedPackage(
      secondPackage,
      { 'route_rules.json': { source: 'saved' } },
    ))

    const { downloadRuleDocument } = createExport({
      onExportReviewRequired: review,
    })
    await downloadRuleDocument()

    expect(review).toHaveBeenCalledWith(expect.objectContaining({
      status: 'mapping_required',
      mappingIssues: [expect.objectContaining({
        field: 'cad.features',
        value: 'unmapped feature',
      })],
    }))
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(2)
    expect(mocks.compileRulePackage).toHaveBeenNthCalledWith(1, mocks.compileRulePackage.mock.calls[1]![0])
    expect(mocks.compileRulePackage.mock.calls[0]![0]).toBe(mocks.compileRulePackage.mock.calls[1]![0])
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledWith(expect.objectContaining({
      manifest: secondPackage.manifest,
    }))
    expect(mocks.createZipBlob).toHaveBeenCalledWith(expect.arrayContaining([
      expect.objectContaining({ name: 'kmai-v1/route_rules.json', content: JSON.stringify({ source: 'saved' }) }),
    ]))
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('does not save or download when mapping resolution is cancelled', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage, false))
    const { downloadRuleDocument } = createExport({ onExportReviewRequired: async () => false })

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('does not save or download when the recompiled package still needs mappings', async () => {
    const review = vi.fn()
      .mockResolvedValueOnce(true)
      .mockResolvedValueOnce(false)
    mocks.compileRulePackage
      .mockResolvedValueOnce(compiled(firstPackage, false))
      .mockResolvedValueOnce(compiled(firstPackage, false))
    const { downloadRuleDocument } = createExport({ onExportReviewRequired: review })

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(2)
    expect(review).toHaveBeenCalledTimes(2)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })
})
