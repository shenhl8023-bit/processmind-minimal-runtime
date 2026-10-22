import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getCurrentGroupTemplate: vi.fn(),
  precheckFinalizedRulePackage: vi.fn(),
  saveFinalizedRulePackage: vi.fn(),
  createZipBlob: vi.fn((_files: any[]) => new Blob()),
  downloadBlob: vi.fn(),
}))

vi.mock('@/api', () => ({
  compileRulePackage: mocks.compileRulePackage,
  getCurrentGroupTemplate: mocks.getCurrentGroupTemplate,
  precheckFinalizedRulePackage: mocks.precheckFinalizedRulePackage,
  saveFinalizedRulePackage: mocks.saveFinalizedRulePackage,
}))

vi.mock('@/utils/exportArchive', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/utils/exportArchive')>()
  mocks.createZipBlob.mockImplementation(actual.createZipBlob)
  return {
    ...actual,
    createZipBlob: mocks.createZipBlob,
    downloadBlob: mocks.downloadBlob,
  }
})

vi.mock('@/utils/finalizeRulePackage', async (importOriginal) => ({
  ...await importOriginal<typeof import('@/utils/finalizeRulePackage')>(),
  buildCompileRequestFromCards: () => ({ processes: [{ process_id: 'process_1' }] }),
  buildRuleReportFromV2Package: () => '# report',
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
  process_id: 'turning_a',
  steps: [{
    step_name: '粗车外圆',
    candidates: { 'A侧/外圆': ['外圆柱面'] },
    step_id: 'turning_a_s01',
  }],
}]

const frozenTables = {
  factor_table: [{ key: 'material', label: '材料', type: 'string', source: 'manual_defaults.material_grade', visible: true }],
  full_route_table: fullRouteStructure,
  rule_table: [{ target: 'turning_a', required: true }],
}

function compiled(packageValue: typeof firstPackage) {
  return {
    package: packageValue,
    content_hash: 'second',
    validation: { valid: true, errors: [], warnings: [], test_results: [] },
  }
}

function validTemplate(output: unknown[] = []) {
  return { mapping_output: output, tree: [{ path: ['外圆'], children: [], feature_selections: ['外圆'] }],
    mappings: [{ source_operation_id: 1, template_group_path: ['外圆'], feature_selections: ['外圆'] }], step_mappings: [] }
}

function createExport(extra: Record<string, unknown> = {}) {
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
    ...extra,
  } as any)
}

async function readStoredZip(blob: Blob) {
  const bytes = new Uint8Array(await blob.arrayBuffer())
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength)
  const decoder = new TextDecoder('utf-8', { fatal: true })
  const files: Record<string, string> = {}
  const centralFiles: string[] = []
  let offset = 0
  while (offset + 4 <= bytes.length && view.getUint32(offset, true) === 0x04034b50) {
    const method = view.getUint16(offset + 8, true)
    const compressedSize = view.getUint32(offset + 18, true)
    const nameLength = view.getUint16(offset + 26, true)
    const extraLength = view.getUint16(offset + 28, true)
    const nameStart = offset + 30
    const contentStart = nameStart + nameLength + extraLength
    const name = decoder.decode(bytes.subarray(nameStart, nameStart + nameLength))
    if (method !== 0) throw new Error(`Unexpected ZIP compression method: ${method}`)
    files[name] = decoder.decode(bytes.subarray(contentStart, contentStart + compressedSize))
    offset = contentStart + compressedSize
  }
  const centralOffset = offset
  while (offset + 4 <= bytes.length && view.getUint32(offset, true) === 0x02014b50) {
    const nameLength = view.getUint16(offset + 28, true)
    const extraLength = view.getUint16(offset + 30, true)
    const commentLength = view.getUint16(offset + 32, true)
    const nameStart = offset + 46
    centralFiles.push(decoder.decode(bytes.subarray(nameStart, nameStart + nameLength)))
    offset = nameStart + nameLength + extraLength + commentLength
  }
  const centralSize = offset - centralOffset
  const endSignature = offset + 4 <= bytes.length ? view.getUint32(offset, true) : 0
  const entryCount = endSignature === 0x06054b50 ? view.getUint16(offset + 10, true) : 0
  const reportedCentralSize = endSignature === 0x06054b50 ? view.getUint32(offset + 12, true) : -1
  const reportedCentralOffset = endSignature === 0x06054b50 ? view.getUint32(offset + 16, true) : -1
  const endRecordLength = endSignature === 0x06054b50 ? 22 + view.getUint16(offset + 20, true) : 0
  return {
    files,
    centralFiles,
    endSignature,
    entryCount,
    centralSize,
    reportedCentralSize,
    reportedCentralOffset,
    archiveLength: offset + endRecordLength,
    byteLength: bytes.length,
  }
}

describe('useFinalizeRulePackageExport', () => {
  it('blocks publication when every saved mapping is invalid', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ ...validTemplate(), tree: [] })
    await createExport().downloadRuleDocument()
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

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

  it('exports exactly the three frozen tables from the published package despite different live mapping', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate([{ process_name: '实时映射已经改变' }]))
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
      demo_tables: frozenTables,
    })

    const { downloadRuleDocument } = createExport()
    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledWith(expect.objectContaining({
      manifest: secondPackage.manifest,
      factor_dictionary: secondPackage.factor_dictionary,
    }))
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
    const downloadedBlob = mocks.downloadBlob.mock.calls[0]?.[0] as Blob | undefined
    expect(downloadedBlob).toBeInstanceOf(Blob)
    const archive = await readStoredZip(downloadedBlob as Blob)
    expect(Object.keys(archive.files).sort()).toEqual([
      'factor_table.json', 'full_route_table.json', 'rule_table.json',
    ])
    expect(archive.centralFiles.sort()).toEqual(Object.keys(archive.files).sort())
    expect(archive.endSignature).toBe(0x06054b50)
    expect(archive.entryCount).toBe(3)
    expect(archive.reportedCentralOffset).toBeGreaterThan(0)
    expect(archive.reportedCentralSize).toBe(archive.centralSize)
    expect(archive.archiveLength).toBe(archive.byteLength)
    expect(JSON.parse(archive.files['factor_table.json']!)).toEqual(frozenTables.factor_table)
    expect(JSON.parse(archive.files['full_route_table.json']!)).toEqual(frozenTables.full_route_table)
    expect(JSON.parse(archive.files['rule_table.json']!)).toEqual(frozenTables.rule_table)
    expect(archive.files['full_route_table.json']).toContain('粗加工')
  })

  it('does not download a package without a frozen three-table snapshot', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate())
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
    const onExportIssue = vi.fn()
    const { downloadRuleDocument } = createExport({ onExportIssue })

    await downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.createZipBlob).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({ summary: expect.stringContaining('重新发布') }))
  })

  it('does not download an empty frozen full-route table', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4, schema_version: '2.0', status: 'published', ...firstPackage,
      demo_tables: { ...frozenTables, full_route_table: [] },
    })
    await createExport().downloadRuleDocument()
    expect(mocks.createZipBlob).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('blocks unconfirmed candidates before compilation, saving or downloading', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate())
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4,
      schema_version: '2.0',
      status: 'published',
      ...firstPackage,
    })
    const onBlockedCards = vi.fn()
    const onExportedVersion = vi.fn()
    const text = '当零件存在槽时，纳入铣槽工序'
    const pendingCandidate = {
      segment: { id: 'process_slot', normalized_step_name: '铣槽', doc_coverage: { total_docs: 3, hit_docs: 1 } },
      conditionText: text,
      factorNames: [],
      conditionReview: {
        source_text: text,
        status: 'pending_confirmation',
        candidate: { kind: 'condition', when: { field: 'cad.features', op: 'contains', value: '槽' } },
      },
    }
    const { downloadRuleDocument } = useFinalizeRulePackageExport({
      projectId: ref(12),
      projectName: ref('project'),
      savedRoute: ref({ route_id: 99 }),
      segmentCards: computed(() => [pendingCandidate]),
      displayName: () => '铣槽',
      metaLabel: () => '',
      phaseLabel: () => 'machining',
      primarySteps: () => [],
      attachedSteps: () => [],
      conditionFields: ref([{ key: 'cad.features' }]),
      onBlockedCards,
      onExportedVersion,
    } as any)

    await downloadRuleDocument()

    expect(onBlockedCards).toHaveBeenCalledWith([pendingCandidate])
    expect(onExportedVersion).not.toHaveBeenCalled()
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('blocks publishing when no template is bound', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockRejectedValue({ response: { status: 404 } })
    await createExport().downloadRuleDocument()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('surfaces template mapping blockers from the publish API', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
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
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
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
