import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

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

const firstPackage = {
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

function compiled(packageValue: typeof firstPackage, valid: boolean) {
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

function createExport(options: { onKmaiMappingsRequired: () => Promise<boolean> }) {
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
    conditionFields: ref([{ key: 'cad.features' }]),
    onKmaiMappingsRequired: options.onKmaiMappingsRequired,
  } as any)
}

describe('useFinalizeRulePackageExport KmAI mapping retry', () => {
  beforeEach(() => {
    mocks.compileRulePackage.mockReset()
    mocks.saveFinalizedRulePackage.mockReset()
    mocks.createZipBlob.mockClear()
    mocks.downloadBlob.mockClear()
  })

  it('recompiles after resolved mappings and archives the authoritative saved KmAI files', async () => {
    const resolveMappings = vi.fn().mockResolvedValue(true)
    mocks.compileRulePackage
      .mockResolvedValueOnce(compiled(firstPackage, false))
      .mockResolvedValueOnce(compiled(secondPackage, true))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      schema_version: '2.0',
      status: 'published',
      manifest: secondPackage.manifest,
      input_schema: secondPackage.input_schema,
      route_catalog: secondPackage.route_catalog,
      route_rules: secondPackage.route_rules,
      test_cases: [],
      rule_report_md: '# report',
      validation_report: {},
      kmai_compatibility: {
        format: 'kmai-v1',
        valid: true,
        target_directory: 'rules',
        errors: [],
        warnings: [],
        files: { 'route_rules.json': { source: 'saved' } },
        mapping_signature: 'saved',
        mapping_usages: [],
      },
    })

    const { downloadRuleDocument } = createExport({ onKmaiMappingsRequired: resolveMappings })
    await downloadRuleDocument()

    expect(resolveMappings).toHaveBeenCalledTimes(1)
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
    const { downloadRuleDocument } = createExport({ onKmaiMappingsRequired: async () => false })

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('does not save or download when the recompiled package still needs mappings', async () => {
    mocks.compileRulePackage
      .mockResolvedValueOnce(compiled(firstPackage, false))
      .mockResolvedValueOnce(compiled(firstPackage, false))
    const { downloadRuleDocument } = createExport({ onKmaiMappingsRequired: async () => true })

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(2)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })
})
