import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getCurrentGroupTemplate: vi.fn(),
  precheckFinalizedRulePackage: vi.fn(),
  saveFinalizedRulePackage: vi.fn(),
  createZipBlob: vi.fn((_files: any[]) => new Blob()),
  downloadBlob: vi.fn(),
  hasPendingTemplateMappingEdits: vi.fn(() => false),
  allocatePublicRulePackageIdentities: vi.fn(),
}))

vi.mock('@/api/publicRulePackageIdentities', () => ({ allocatePublicRulePackageIdentities: mocks.allocatePublicRulePackageIdentities }))

vi.mock('@/api', () => ({
  compileRulePackage: mocks.compileRulePackage,
  getCurrentGroupTemplate: mocks.getCurrentGroupTemplate,
  precheckFinalizedRulePackage: mocks.precheckFinalizedRulePackage,
  saveFinalizedRulePackage: mocks.saveFinalizedRulePackage,
}))

vi.mock('@/composables/templateMappingEdits', () => ({
  hasPendingTemplateMappingEdits: mocks.hasPendingTemplateMappingEdits,
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
import { productAccess, productStatus } from './productStatus'

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
  it('deduplicates repeated publication clicks while compilation is pending', async () => {
    let finish!: (value: any) => void
    mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4, schema_version: '2.0', status: 'published', project_id: 12, route_version_id: 99,
      content_hash: 'second', demo_tables: frozenTables,
    })
    const exporter = createExport()
    const first = exporter.downloadRuleDocument()
    await exporter.downloadRuleDocument()
    finish(compiled(firstPackage))
    await first
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('stops publication if a precheck callback changes the active project', async () => {
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    const projectId = ref(12)
    await createExport({ projectId, onPrecheck: () => { projectId.value = 88 } }).downloadRuleDocument()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it.each(['project', 'route', 'revision', 'draft'])('stops a pending publication if the %s changes', async change => {
    let finish!: (value: any) => void
    mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    const projectId = ref(12)
    const savedRoute = ref({ route_id: 99, workflow_revision: 3 })
    const drafts = ref<any[]>([])
    const exporter = createExport({ projectId, savedRoute, unsavedCards: computed(() => drafts.value) })
    const pending = exporter.downloadRuleDocument()
    if (change === 'project') projectId.value = 88
    if (change === 'route') savedRoute.value = { route_id: 100, workflow_revision: 3 }
    if (change === 'revision') savedRoute.value = { route_id: 99, workflow_revision: 4 }
    if (change === 'draft') drafts.value = [{ segment: { id: 'custom_process' } }]
    finish(compiled(firstPackage))
    await pending
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(exporter.exportingRulePackage.value).toBe(false)
  })

  it('does not resume an obsolete publication when the user switches away and back', async () => {
    let finish!: (value: any) => void
    mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    const projectId = ref(12)
    const exporter = createExport({ projectId })
    const pending = exporter.downloadRuleDocument()
    projectId.value = 88
    projectId.value = 12
    finish(compiled(firstPackage))
    await pending
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('does not place stale mapping errors on a different project after navigation', async () => {
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    let finish!: (value: any) => void
    mocks.getCurrentGroupTemplate.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const projectId = ref(12)
    const onExportIssue = vi.fn()
    const exporter = createExport({ projectId, onExportIssue })
    const pending = exporter.downloadRuleDocument()
    await Promise.resolve()
    projectId.value = 88
    finish({ tree: [], mappings: [], step_mappings: [] })
    await pending
    expect(onExportIssue).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
  })
  it('blocks export and locates a locally edited card even if its saved rule is confirmed', async () => {
    const card = { segment: { id: 'remove_copper' } }
    const onBlockedCards = vi.fn()
    const onExportIssue = vi.fn()
    await createExport({ unsavedCards: computed(() => [card]), onBlockedCards, onExportIssue }).downloadRuleDocument()
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(onBlockedCards).toHaveBeenCalledWith([card])
    expect(onExportIssue.mock.calls[0]?.[0].summary).toContain('未保存')
  })

  it('does not compile while an individual rule save is still in flight', async () => {
    const onExportIssue = vi.fn()
    await createExport({ savingRuleIds: ref(new Set(['remove_copper'])), onExportIssue }).downloadRuleDocument()
    expect(mocks.compileRulePackage).not.toHaveBeenCalled()
    expect(onExportIssue.mock.calls[0]?.[0].summary).toContain('保存')
  })

  it('blocks publication when every saved mapping is invalid', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ ...validTemplate(), tree: [] })
    await createExport().downloadRuleDocument()
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  beforeEach(() => {
    productAccess.value = 'ready'
    productStatus.value = { edition: 'full', template_mapping_enabled: true, expired: false, expires_at: null, server_time: '2026-10-30T00:00:00Z' }
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
    mocks.allocatePublicRulePackageIdentities.mockReset()
    mocks.createZipBlob.mockClear()
    mocks.downloadBlob.mockClear()
    mocks.hasPendingTemplateMappingEdits.mockReset().mockReturnValue(false)
  })

  function nativePublishedPackage() {
    productStatus.value = { edition: 'basic-trial', template_mapping_enabled: false, expired: false, expires_at: '2026-12-31T00:00:00+08:00', server_time: '2026-10-30T00:00:00Z' }
    const nativePackage = { ...firstPackage, route_catalog: { schema_version: '2.0', processes: [
      { process_id: 'native_turn', display_name: '车削', phase: 'rough', main: true, steps: [{ step_id: 'native_turn.rough', name: '粗车' }] },
    ] } }
    mocks.allocatePublicRulePackageIdentities.mockResolvedValue({ processes: { native_turn: 'P001' }, steps: { 'native_turn.rough': 'S001' }, factors: {} })
    return {
      ...firstPackage, version: 4, schema_version: '2.0', status: 'published', project_id: 12,
      route_version_id: 99, content_hash: 'second', demo_tables: null, export_error: null,
      export_sources: {
        compiler_version: 'native-v2/1', project_id: 12, route_version_id: 99, workflow_revision: 0,
        native_snapshot_hash: 'snapshot-hash', route_content_hash: 'route-hash', rule_package_content_hash: 'second',
        native_snapshot: { schema_version: '2.0', normalized_route: [{ id: 'native_turn', normalized_step_name: '车削', final_steps: [{ step_name: '粗车' }] }], rule_package: nativePackage },
      },
    }
  }

  it('downloads the three sample arrays from frozen native data without reading mappings', async () => {
    const published = nativePublishedPackage()
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    mocks.getCurrentGroupTemplate.mockRejectedValue(new Error('Mapping is disabled'))
    const onExportedVersion = vi.fn()
    await createExport({ onExportedVersion }).downloadRuleDocument()
    expect(mocks.getCurrentGroupTemplate).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).toHaveBeenCalledOnce()
    const archive = await readStoredZip(mocks.downloadBlob.mock.calls[0]![0] as Blob)
    expect(Object.keys(archive.files).sort()).toEqual([
      'factor_table.json', 'full_route_table.json', 'rule_table.json',
    ])
    expect(JSON.parse(archive.files['factor_table.json']!)).toEqual([])
    expect(JSON.parse(archive.files['full_route_table.json']!)).toEqual([{ process_id: 'P001', process_name: '车削', process_type: '加工工序', precision: '粗加工', steps: [{ step_id: 'S001', step_name: '粗车', candidates: {} }] }])
    expect(JSON.parse(archive.files['rule_table.json']!)).toEqual([{ target: 'P001', required: true }])
    expect(onExportedVersion).toHaveBeenCalledWith(4, { schemaVersion: '2.0', status: 'published' })
  })

  it('retries the same native snapshot after an asynchronous registry failure', async () => {
    const published = nativePublishedPackage()
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    mocks.allocatePublicRulePackageIdentities.mockRejectedValueOnce(new Error('编号服务不可用'))
    const onExportIssue = vi.fn(), exporter = createExport({ onExportIssue })
    await exporter.downloadRuleDocument()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(exporter.downloadRetryAvailable.value).toBe(true)
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({ title: '规则包下载失败', details: '编号服务不可用' }))

    await exporter.downloadRuleDocument()
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.allocatePublicRulePackageIdentities).toHaveBeenCalledTimes(2)
    expect(mocks.allocatePublicRulePackageIdentities.mock.calls[1]![0]).toEqual(published)
    expect(exporter.downloadRetryAvailable.value).toBe(false)
    const archive = await readStoredZip(mocks.downloadBlob.mock.calls[0]![0] as Blob)
    expect(JSON.parse(archive.files['rule_table.json']!)).toEqual([{ target: 'P001', required: true }])
  })

  it('abandons native download when the project changes while awaiting its registry', async () => {
    const published = nativePublishedPackage(), projectId = ref(12)
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    let finish!: (registry: any) => void
    mocks.allocatePublicRulePackageIdentities.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const exporter = createExport({ projectId }), pending = exporter.downloadRuleDocument()
    await vi.waitFor(() => expect(mocks.allocatePublicRulePackageIdentities).toHaveBeenCalledTimes(1))
    expect(exporter.exportingRulePackage.value).toBe(true)
    projectId.value = 88
    finish({ processes: { native_turn: 'P001' }, steps: { 'native_turn.rough': 'S001' }, factors: {} })
    await pending
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(exporter.downloadRetryAvailable.value).toBe(false)
    expect(exporter.exportingRulePackage.value).toBe(false)
  })

  it.each(['error', 'missing', 'compiler', 'empty-route', 'incomplete-package'])('blocks a basic native download with %s snapshot', async problem => {
    const published: any = nativePublishedPackage()
    if (problem === 'error') published.export_error = '快照完整性校验失败'
    if (problem === 'missing') delete published.export_sources.native_snapshot
    if (problem === 'compiler') published.export_sources.compiler_version = 'demo-v1'
    if (problem === 'empty-route') published.export_sources.native_snapshot.normalized_route = []
    if (problem === 'incomplete-package') published.export_sources.native_snapshot.rule_package = {}
    // An old demo snapshot must not be used as a fallback in basic edition.
    published.demo_tables = frozenTables
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    const onExportIssue = vi.fn()
    await createExport({ onExportIssue }).downloadRuleDocument()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({ title: '原生快照不可下载' }))
  })

  it('stops an in-flight native publication when the trial expires', async () => {
    const published = nativePublishedPackage()
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate())
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    let finish!: (value: any) => void
    mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const pending = createExport().downloadRuleDocument()
    productAccess.value = 'expired'
    finish(compiled(firstPackage))
    await pending
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it('exports exactly the three frozen tables from the published package despite different live mapping', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate([{ process_name: '实时映射已经改变' }]))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      project_id: 12, route_version_id: 99, content_hash: 'second',
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

  it('keeps the downloaded ZIP filename safe for Windows while preserving Chinese project names', async () => {
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4, schema_version: '2.0', status: 'published', project_id: 12, route_version_id: 99,
      content_hash: 'second', demo_tables: frozenTables,
    })
    await createExport({ projectName: ref('零件/试验\n批次:*?') }).downloadRuleDocument()
    expect(mocks.downloadBlob.mock.calls[0]?.[1]).toBe('零件_试验_批次____第四步规则定稿包_v4.zip')
  })

  it('does not download a package without a frozen three-table snapshot', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate())
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 3,
      project_id: 12, route_version_id: 99, content_hash: 'second',
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
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({ title: '三文件快照不可下载' }))
  })

  it('does not download an empty frozen full-route table', async () => {
    mocks.compileRulePackage.mockResolvedValueOnce(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4, schema_version: '2.0', status: 'published', ...firstPackage,
      project_id: 12, route_version_id: 99, content_hash: 'second',
      demo_tables: { ...frozenTables, full_route_table: [] },
    })
    await createExport().downloadRuleDocument()
    expect(mocks.createZipBlob).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
  })

  it.each(['draft', 'project', 'route', 'content'])('rejects a saved snapshot with mismatched %s identity', async mismatch => {
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 4, schema_version: '2.0', status: mismatch === 'draft' ? 'draft' : 'published',
      project_id: mismatch === 'project' ? 88 : 12,
      route_version_id: mismatch === 'route' ? 100 : 99,
      content_hash: mismatch === 'content' ? 'another-package' : 'second',
      demo_tables: frozenTables,
    })
    const onExportedVersion = vi.fn()
    const onExportIssue = vi.fn()
    await createExport({ onExportedVersion, onExportIssue }).downloadRuleDocument()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(onExportedVersion).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenCalled()
  })

  function preparePublication(mappingEnabled: boolean) {
    const published = mappingEnabled ? {
      ...firstPackage, id: 44, version: 4, schema_version: '2.0', status: 'published',
      project_id: 12, route_version_id: 99, content_hash: 'second', demo_tables: frozenTables,
      export_sources: { template_revision: 7, template_content_hash: 'template-hash', source_full_route_table: fullRouteStructure },
    } : nativePublishedPackage()
    mocks.compileRulePackage.mockResolvedValue(compiled(firstPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue({ ...validTemplate(fullRouteStructure), project_id: 12, template_revision: 7, content_hash: 'template-hash' })
    mocks.saveFinalizedRulePackage.mockResolvedValue(published)
    return published
  }

  it.each([true, false])('synchronizes publication before attempting the download (mapping=%s)', async mappingEnabled => {
    preparePublication(mappingEnabled)
    const onExportedVersion = vi.fn()
    const onExportIssue = vi.fn()
    const versionsAtDownload: unknown[][] = []
    mocks.downloadBlob.mockImplementationOnce(() => {
      versionsAtDownload.push([...onExportedVersion.mock.calls])
      throw new Error('Browser download unavailable')
    })
    await createExport({ onExportedVersion, onExportIssue }).downloadRuleDocument()
    expect(versionsAtDownload).toEqual([[[4, { schemaVersion: '2.0', status: 'published' }]]])
    expect(onExportedVersion).toHaveBeenCalledOnce()
    const issue = onExportIssue.mock.calls[0]?.[0]
    expect(issue.title).toContain('下载失败')
    expect(issue.summary).not.toContain('无法连接本地服务')
    expect(issue.details).toContain('Browser download unavailable')
  })

  it.each([
    [true, 'browser'], [false, 'browser'], [true, 'zip'], [false, 'zip'],
  ] as const)('retries the same published snapshot after %s/%s download failure without republishing', async (mappingEnabled, failure) => {
    preparePublication(mappingEnabled)
    if (failure === 'browser') mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Browser download unavailable') })
    else mocks.createZipBlob.mockImplementationOnce(() => { throw new Error('ZIP creation failed') })
    const onExportedVersion = vi.fn()
    const exporter = createExport({ onExportedVersion })
    await exporter.downloadRuleDocument()
    expect(exporter.exportingRulePackage.value).toBe(false)
    expect(exporter.downloadRetryAvailable.value).toBe(true)

    await exporter.downloadRuleDocument()

    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.precheckFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(onExportedVersion).toHaveBeenCalledTimes(1)
    expect(exporter.downloadRetryAvailable.value).toBe(false)
    const download = mocks.downloadBlob.mock.calls[mocks.downloadBlob.mock.calls.length - 1]!
    expect(download[1]).toContain('_v4.zip')
    const archive = await readStoredZip(download[0] as Blob)
    const route = JSON.parse(archive.files['full_route_table.json']!)
    expect(Array.isArray(route)).toBe(true)
    if (mappingEnabled) expect(route).toEqual(fullRouteStructure)
    else expect(route[0]).toMatchObject({ process_id: 'P001', process_name: '车削' })
  })

  describe.each([true, false])('published download invalidation (mapping=%s)', mappingEnabled => {
    it.each(['project', 'route', 'revision', 'rules', 'fields', 'draft', 'saving', 'away-and-back'])(
      'does not reuse the published snapshot after %s changes', async change => {
        preparePublication(mappingEnabled)
        mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Download failed') })
        const projectId = ref(12)
        const savedRoute = ref({ route_id: 99, workflow_revision: 3 })
        const cards = ref<any[]>([])
        const fields = ref([{ key: 'cad.features' }])
        const drafts = ref<any[]>([])
        const savingRuleIds = ref(new Set<string>())
        const exporter = createExport({ projectId, savedRoute, segmentCards: computed(() => cards.value), conditionFields: fields,
          unsavedCards: computed(() => drafts.value), savingRuleIds })
        await exporter.downloadRuleDocument()
        expect(exporter.downloadRetryAvailable.value).toBe(true)
        if (change === 'project') projectId.value = 88
        if (change === 'route') savedRoute.value.route_id = 100
        if (change === 'revision') savedRoute.value.workflow_revision = 4
        if (change === 'rules') cards.value = [{ segment: { id: 'new_process', normalized_step_name: '准备' }, conditionText: '固定为主工序，默认保留' }]
        if (change === 'fields') fields.value = [{ key: 'material.grade' }]
        if (change === 'draft') drafts.value = [{ segment: { id: 'edited_process' } }]
        if (change === 'saving') savingRuleIds.value.add('edited_process')
        if (change === 'away-and-back') { projectId.value = 88; projectId.value = 12 }
        expect(exporter.downloadRetryAvailable.value).toBe(false)
        // Keep the next publication pending so an obsolete local retry is observable.
        let finish!: (value: any) => void
        mocks.compileRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
        const next = exporter.downloadRuleDocument()
        expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
        const blocked = change === 'draft' || change === 'saving'
        expect(mocks.compileRulePackage).toHaveBeenCalledTimes(blocked ? 1 : 2)
        if (!blocked) {
          projectId.value = 999
          finish(compiled(firstPackage))
        }
        await next
        expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
      },
    )

    it('does not apply a publication response after navigating away while saving', async () => {
      const published = preparePublication(mappingEnabled)
      let finish!: (value: any) => void
      const saving = new Promise(resolve => { finish = resolve })
      mocks.saveFinalizedRulePackage.mockReturnValueOnce(saving)
      const projectId = ref(12)
      const onExportedVersion = vi.fn()
      const exporter = createExport({ projectId, onExportedVersion })
      const pending = exporter.downloadRuleDocument()
      await vi.waitFor(() => expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledOnce())
      projectId.value = 88
      finish(published)
      await pending
      expect(onExportedVersion).not.toHaveBeenCalled()
      expect(mocks.downloadBlob).not.toHaveBeenCalled()
    })

    it('rechecks current state after synchronizing the published version', async () => {
      preparePublication(mappingEnabled)
      const projectId = ref(12)
      const onExportedVersion = vi.fn(() => { projectId.value = 88 })
      await createExport({ projectId, onExportedVersion }).downloadRuleDocument()
      expect(onExportedVersion).toHaveBeenCalledOnce()
      expect(mocks.downloadBlob).not.toHaveBeenCalled()
    })
  })

  it.each(['revision', 'content'])('recompiles instead of retrying after remote template %s changes', async change => {
    preparePublication(true)
    mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Download failed') })
    const exporter = createExport()
    await exporter.downloadRuleDocument()
    const template = { ...validTemplate(fullRouteStructure), template_revision: change === 'revision' ? 8 : 7 }
    if (change === 'content') template.mapping_output = [{ process_id: 'changed_mapping' }]
    mocks.getCurrentGroupTemplate.mockResolvedValue(template)
    await exporter.downloadRuleDocument()
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(2)
    expect(mocks.precheckFinalizedRulePackage).toHaveBeenCalledTimes(2)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(2)
  })

  it('blocks publication when the current template has pending edits in another tab', async () => {
    preparePublication(true)
    mocks.hasPendingTemplateMappingEdits.mockReturnValue(true)
    const onExportIssue = vi.fn()
    await createExport({ savedRoute: ref({ route_id: 99, workflow_revision: 3 }), onExportIssue }).downloadRuleDocument()
    expect(mocks.hasPendingTemplateMappingEdits).toHaveBeenCalledWith(12, 99, 3, 7)
    expect(mocks.precheckFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenCalledWith(expect.objectContaining({ summary: expect.stringMatching(/模板.*保存.*放弃/) }))
  })

  it('blocks publication if another tab adds a template draft while precheck is pending', async () => {
    preparePublication(true)
    let finish!: (value: any) => void
    mocks.precheckFinalizedRulePackage.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const onExportIssue = vi.fn()
    const exporter = createExport({ onExportIssue })
    const pending = exporter.downloadRuleDocument()
    await vi.waitFor(() => expect(mocks.precheckFinalizedRulePackage).toHaveBeenCalledOnce())
    mocks.hasPendingTemplateMappingEdits.mockReturnValue(true)
    finish({ ok: true, checklist: [], blockers: [] })
    await pending
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenLastCalledWith(expect.objectContaining({ title: '模板映射尚未保存' }))
  })

  it('retries the actual published mapping when it differs from the pre-publication read', async () => {
    const published = preparePublication(true) as any
    published.export_sources.template_revision = 8
    mocks.saveFinalizedRulePackage.mockImplementationOnce(async () => {
      mocks.getCurrentGroupTemplate.mockResolvedValue({ ...validTemplate(fullRouteStructure), project_id: 12, template_revision: 8, content_hash: 'template-hash' })
      return published
    })
    mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Download failed') })
    const exporter = createExport()
    await exporter.downloadRuleDocument()
    await exporter.downloadRuleDocument()
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.compileRulePackage).toHaveBeenCalledTimes(1)
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(2)
  })

  it('requires a fresh publication when the saved template changes during precheck', async () => {
    preparePublication(true)
    mocks.precheckFinalizedRulePackage.mockImplementationOnce(async () => {
      mocks.getCurrentGroupTemplate.mockResolvedValue({ ...validTemplate(fullRouteStructure), project_id: 12, template_revision: 8, content_hash: 'template-hash' })
      return { ok: true, checklist: [], blockers: [] }
    })
    const onExportIssue = vi.fn()
    const exporter = createExport({ onExportIssue })
    await exporter.downloadRuleDocument()
    expect(mocks.saveFinalizedRulePackage).not.toHaveBeenCalled()
    expect(onExportIssue).toHaveBeenLastCalledWith(expect.objectContaining({ title: '模板映射已更新' }))
    expect(exporter.downloadRetryAvailable.value).toBe(false)
  })

  it('checks cross-tab pending template edits again before retrying a download', async () => {
    preparePublication(true)
    mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Download failed') })
    const onExportIssue = vi.fn()
    const exporter = createExport({ onExportIssue })
    await exporter.downloadRuleDocument()
    mocks.hasPendingTemplateMappingEdits.mockReturnValue(true)
    await exporter.downloadRuleDocument()
    expect(mocks.hasPendingTemplateMappingEdits).toHaveBeenCalledTimes(3)
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
    expect(onExportIssue).toHaveBeenLastCalledWith(expect.objectContaining({ summary: expect.stringMatching(/模板.*保存.*放弃/) }))
  })

  it('abandons a retry when navigation changes during the template recheck', async () => {
    preparePublication(true)
    mocks.downloadBlob.mockImplementationOnce(() => { throw new Error('Download failed') })
    const projectId = ref(12)
    const exporter = createExport({ projectId })
    await exporter.downloadRuleDocument()
    let finish!: (value: any) => void
    mocks.getCurrentGroupTemplate.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const retry = exporter.downloadRuleDocument()
    projectId.value = 88
    finish({ ...validTemplate(fullRouteStructure), template_revision: 7 })
    await retry
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
    expect(mocks.saveFinalizedRulePackage).toHaveBeenCalledTimes(1)
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

  it.each([
    ['compileRulePackage', '编译规则包'],
    ['getCurrentGroupTemplate', '读取模板映射'],
    ['precheckFinalizedRulePackage', '发布预检'],
    ['saveFinalizedRulePackage', '发布规则包'],
  ] as const)('reports HTTP 503 at %s without blaming template mappings and allows a retry', async (request, stage) => {
    mocks.compileRulePackage.mockResolvedValue(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockResolvedValue({
      version: 1, schema_version: '2.0', status: 'published', demo_tables: frozenTables,
      project_id: 12, route_version_id: 99, content_hash: 'second',
    })
    mocks[request].mockRejectedValueOnce({
      response: { status: 503, data: '<html>Service Unavailable</html>' },
      message: 'Request failed with status code 503',
    })
    const onExportIssue = vi.fn()
    const exporter = createExport({ onExportIssue })

    await exporter.downloadRuleDocument()

    const issue = onExportIssue.mock.calls[0]?.[0]
    expect(issue.summary).toContain('503')
    expect(issue.summary).toContain('服务暂不可用')
    expect(issue.details).toContain(stage)
    expect(issue.summary).not.toContain('完成必要的分组模板映射')
    expect(exporter.exportingRulePackage.value).toBe(false)
    expect(mocks.downloadBlob).not.toHaveBeenCalled()

    await exporter.downloadRuleDocument()
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(1)
  })

  it('surfaces rule confirmation conflicts without sending the user back to mapping', async () => {
    mocks.compileRulePackage.mockResolvedValue(compiled(secondPackage))
    mocks.getCurrentGroupTemplate.mockResolvedValue(validTemplate(fullRouteStructure))
    mocks.saveFinalizedRulePackage.mockRejectedValue({
      response: { status: 409, data: { detail: {
        message: '规则包中的用户规则与数据库中的已确认规则不一致，请重新审核。',
        rule_ids: ['user.remove_copper'],
      } } },
    })
    const onExportIssue = vi.fn()
    await createExport({ onExportIssue }).downloadRuleDocument()
    const issue = onExportIssue.mock.calls[0]?.[0]
    expect(issue.summary).toContain('已确认规则不一致')
    expect(issue.summary).not.toContain('分组模板映射')
    expect(issue.details).toContain('user.remove_copper')
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
