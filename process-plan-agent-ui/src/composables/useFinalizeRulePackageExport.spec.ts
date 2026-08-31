import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getCurrentGroupTemplate: vi.fn(),
  precheckFinalizedRulePackage: vi.fn(),
  saveFinalizedRulePackage: vi.fn(),
  createZipBlob: vi.fn(() => new Blob()),
  downloadBlob: vi.fn(),
}))

vi.mock('@/api', () => ({
  compileRulePackage: mocks.compileRulePackage,
  getCurrentGroupTemplate: mocks.getCurrentGroupTemplate,
  precheckFinalizedRulePackage: mocks.precheckFinalizedRulePackage,
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
  factor_dictionary: {
    schema_version: '2.0',
    fields: [{ key: 'geometry.length_mm', label: '特征长度', type: 'number', unit: 'mm' }],
  },
  input_schema: { schema_version: '2.0', fields: [] },
  route_catalog: { schema_version: '2.0', processes: [] },
  route_rules: { schema_version: '2.0', rules: [] },
  test_cases: [],
}

const secondPackage = {
  ...firstPackage,
  manifest: { project_id: 12, package_name: 'second' },
}

const fullRouteStructure = [{
  process_name: '车削加工（A侧）',
  process_type: '加工工序',
  precision: '粗加工',
  technical_requirements: ['外圆'],
  steps: [{
    step_name: '粗车外圆',
    candidates: { 'A侧/外圆': ['外圆柱面'] },
    is_last: true,
  }],
}]

function compiled(packageValue: typeof firstPackage) {
  return {
    package: packageValue,
    content_hash: 'second',
    validation: { valid: true, errors: [], warnings: [], test_results: [] },
  }
}

function createExport() {
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
  } as any)
}

describe('useFinalizeRulePackageExport', () => {
  beforeEach(() => {
    mocks.compileRulePackage.mockReset()
    mocks.getCurrentGroupTemplate.mockReset()
    mocks.precheckFinalizedRulePackage.mockReset()
    mocks.precheckFinalizedRulePackage.mockResolvedValue({
      project_id: 12,
      ok: true,
      checklist: [],
      blockers: [],
    })
    mocks.saveFinalizedRulePackage.mockReset()
    mocks.createZipBlob.mockClear()
    mocks.downloadBlob.mockClear()
  })

  it('exports factor, full-route, and rule tables', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ mapping_output: fullRouteStructure })
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      schema_version: '2.0',
      status: 'published',
      manifest: secondPackage.manifest,
      factor_dictionary: secondPackage.factor_dictionary,
      input_schema: secondPackage.input_schema,
      route_catalog: secondPackage.route_catalog,
      route_rules: secondPackage.route_rules,
      test_cases: [],
      rule_report_md: '# report',
      validation_report: {},
    })

    const { downloadRuleDocument } = createExport()
    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledWith(expect.objectContaining({
      manifest: secondPackage.manifest,
      factor_dictionary: secondPackage.factor_dictionary,
    }))
    expect(mocks.createZipBlob).toHaveBeenCalledWith([
      { name: 'factor_table.json', content: JSON.stringify(secondPackage.factor_dictionary) },
      { name: 'full_route_structure.json', content: JSON.stringify(fullRouteStructure) },
      { name: 'rule_table.json', content: JSON.stringify(secondPackage.route_rules) },
    ])
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('can still export when the saved full route structure is empty', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ mapping_output: [] })
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      schema_version: '2.0',
      status: 'published',
      manifest: firstPackage.manifest,
      factor_dictionary: firstPackage.factor_dictionary,
      input_schema: firstPackage.input_schema,
      route_catalog: firstPackage.route_catalog,
      route_rules: firstPackage.route_rules,
      test_cases: [],
      rule_report_md: '# report',
      validation_report: {},
    })
    const { downloadRuleDocument } = createExport()

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.createZipBlob).toHaveBeenCalledWith([
      { name: 'factor_table.json', content: JSON.stringify(firstPackage.factor_dictionary) },
      { name: 'full_route_structure.json', content: JSON.stringify([]) },
      { name: 'rule_table.json', content: JSON.stringify(firstPackage.route_rules) },
    ])
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('treats a missing full route structure as empty by default', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockRejectedValue({
      response: { status: 404 },
    })
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      schema_version: '2.0',
      status: 'published',
      manifest: secondPackage.manifest,
      factor_dictionary: secondPackage.factor_dictionary,
      input_schema: secondPackage.input_schema,
      route_catalog: secondPackage.route_catalog,
      route_rules: secondPackage.route_rules,
      test_cases: [],
      rule_report_md: '# report',
      validation_report: {},
    })

    const { downloadRuleDocument } = createExport()
    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.createZipBlob).toHaveBeenCalledWith([
      { name: 'factor_table.json', content: JSON.stringify(secondPackage.factor_dictionary) },
      { name: 'full_route_structure.json', content: JSON.stringify([]) },
      { name: 'rule_table.json', content: JSON.stringify(secondPackage.route_rules) },
    ])
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('surfaces template mapping blockers from the publish API', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ mapping_output: fullRouteStructure })
    mocks.saveFinalizedRulePackage.mockRejectedValue({
      response: {
        data: {
          detail: {
            message: '规则包发布前需完成分组模板映射。',
            blockers: [
              {
                code: 'group_template_mapping_missing',
                message: '请先完成分组模板映射。',
                process_id: 'process_quench',
                process_name: '淬火',
                severity: 'blocking',
              },
            ],
          },
        },
      },
    })

    const onExportIssue = vi.fn()
    const { downloadRuleDocument } = useFinalizeRulePackageExport({
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
      onExportIssue,
    } as any)

    await downloadRuleDocument()

    expect(onExportIssue).toHaveBeenCalledTimes(1)
    const issue = onExportIssue.mock.calls[0]?.[0]
    expect(issue).toEqual(expect.objectContaining({
      title: '规则包发布失败',
      summary: '规则包尚未发布，请先完成必要的分组模板映射后再试。',
    }))
    expect(issue?.details).toContain('淬火：请先完成分组模板映射。')
  })

  it('runs the publish precheck before saving and surfaces its checklist blockers', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ mapping_output: fullRouteStructure })
    mocks.precheckFinalizedRulePackage.mockResolvedValueOnce({
      project_id: 12,
      ok: false,
      checklist: [
        {
          code: 'template_mapping',
          label: '分组模板映射',
          status: 'blocking',
          message: '还有 1 道必要工序未完成分组模板映射。',
        },
      ],
      blockers: [
        {
          code: 'group_template_mapping_missing',
          message: '请先完成分组模板映射。',
          process_name: '铣槽',
          required_by_labels: ['规则包含引用'],
        },
      ],
    })

    const onExportIssue = vi.fn()
    const { downloadRuleDocument } = useFinalizeRulePackageExport({
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
      onExportIssue,
    } as any)

    await downloadRuleDocument()

    expect(mocks.precheckFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({
      title: '规则包还不能发布',
      details: '铣槽：请先完成分组模板映射。（规则包含引用）',
    }))
  })
})
