import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  commitGroupTemplate,
  getCurrentGroupTemplate,
  previewGroupTemplate,
  saveGroupTemplateMappings,
  saveGroupTemplateStepMappings,
} from '@/api/extract'
import type { GroupTemplateMapping, GroupTemplateNode, GroupTemplateStepMapping } from '@/api/extract'
import { mappingsForStep, scopeMappingsToFinalSteps, type TemplateStepRef } from './templateStepMapping'
import { formatGroupTemplateIssueDetail, useProjectGroupTemplate } from './useProjectGroupTemplate'

vi.mock('@/api/extract', () => ({
  previewGroupTemplate: vi.fn(),
  getCurrentGroupTemplate: vi.fn(),
  commitGroupTemplate: vi.fn(),
  saveGroupTemplateMappings: vi.fn(),
  saveGroupTemplateStepMappings: vi.fn(),
}))

const previewGroupTemplateMock = vi.mocked(previewGroupTemplate)
const getCurrentGroupTemplateMock = vi.mocked(getCurrentGroupTemplate)
const commitGroupTemplateMock = vi.mocked(commitGroupTemplate)
const saveGroupTemplateMappingsMock = vi.mocked(saveGroupTemplateMappings)
const saveGroupTemplateStepMappingsMock = vi.mocked(saveGroupTemplateStepMappings)

const xmlFile = new File(['<Kmsoft />'], 'part-template.xml', { type: 'application/xml' })

function node(path: string[]): GroupTemplateNode {
  return {
    key: `grp_${path.join('_')}`,
    source_id: '',
    name: path[path.length - 1] || '',
    path,
    feature_selections: path[path.length - 1] === '孔' ? ['孔(盲孔)'] : [],
    params: {},
    children: [],
  }
}

function preview(canConfirm = true, tree = [node(['A侧', '孔'])]) {
  return {
    original_filename: 'part-template.xml',
    source_encoding: 'utf-8',
    part_filename: 'part.prt',
    content_hash: 'preview-hash',
    feature_dictionary_version: 'dictionary-v1',
    tree,
    validation_issues: canConfirm ? [] : [{ code: 'invalid_root', message: '无效模板', path: [], value: '' }],
    group_count: tree.length,
    feature_selection_count: 1,
    can_confirm: canConfirm,
  }
}

function template(revision = 1, mappings: GroupTemplateMapping[] = []) {
  return {
    project_id: 28,
    original_filename: 'part-template.xml',
    source_encoding: 'utf-8',
    part_filename: 'part.prt',
    content_hash: 'stored-hash',
    feature_dictionary_version: 'dictionary-v1',
    tree: [node(['A侧', '孔'])],
    validation_issues: [],
    mappings,
    step_mappings: [],
    mapping_output: [],
    template_revision: revision,
    group_count: 1,
    feature_selection_count: 1,
    created_at: null,
    updated_at: null,
  }
}

function stepMapping(): GroupTemplateStepMapping {
  return {
    source_operation_id: 11,
    source_operation_name: '车削A侧',
    source_step_key: 'op_11_s01',
    source_step_order: 1,
    source_step_name: '钻孔',
    source_step_text_hash: 'sha256:test',
    scope_template_group_path: ['A侧'],
    template_group_path: ['A侧', '孔'],
    candidate_features: ['孔(盲孔)'],
    match_mode: 'any',
    status: 'confirmed',
    confidence: 1,
    source: 'user_confirmed',
    template_group_key: 'grp_A侧_孔',
    template_group_name: '孔',
  }
}

function mapping(path = ['A侧', '孔']): GroupTemplateMapping {
  return {
    source_operation_id: 11,
    alias: '钻孔（A侧/孔）',
    template_group_key: 'grp_A侧_孔',
    template_group_id: 'grp_A侧_孔',
    template_group_name: '孔',
    template_group_path: path,
    feature_selections: ['孔(盲孔)'],
  }
}

describe('useProjectGroupTemplate', () => {
  beforeEach(() => {
    vi.resetAllMocks()
  })

  it('keeps the newest template when reloads finish out of order', async () => {
    let finishOld!: (value: ReturnType<typeof template>) => void
    getCurrentGroupTemplateMock
      .mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
      .mockResolvedValueOnce(template(3))
    const model = useProjectGroupTemplate(ref(28), ref({}))
    const oldLoad = model.load()
    await model.load()
    finishOld(template(2))
    await oldLoad
    expect(model.templateRevision.value).toBe(3)
  })

  it('keeps split-step decisions and stale target IDs scoped after loading and saving', async () => {
    const snapshot = {
      ...template(5),
      step_mappings: [
        { ...stepMapping(), final_targets: [{ process_id: 'a', step_id: 'a.s1' }] },
        {
          ...stepMapping(), status: 'not_applicable' as const,
          scope_template_group_path: [], template_group_path: [], candidate_features: [],
          final_targets: [{ process_id: 'b', step_id: 'b.s1' }],
        },
        { ...stepMapping(), final_targets: [{ process_id: 'stale', step_id: 'stale.s1' }] },
      ],
    }
    const steps: TemplateStepRef[] = ['a', 'b'].map(processId => ({
      process_id: processId, step_key: `${processId}.s1`, operation_id: 11,
      operation_name: '车削A侧', step_order: 1, step_name: '钻孔',
      source_steps: [{ source_operation_id: 11, source_step_order: 1, source_step_name: '钻孔' }],
    }))
    getCurrentGroupTemplateMock.mockResolvedValue(snapshot)
    saveGroupTemplateStepMappingsMock.mockResolvedValue({ ...snapshot, template_revision: 6 })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()

    for (const stage of ['loaded', 'saved']) {
      if (stage === 'saved') await model.saveStepMappings()
      const scoped = scopeMappingsToFinalSteps(model.draftStepMappings.value, steps)
      expect(scoped.map(value => ({ status: value.status, targets: value.final_targets }))).toEqual([
        { status: 'confirmed', targets: [{ process_id: 'a', step_id: 'a.s1' }] },
        { status: 'not_applicable', targets: [{ process_id: 'b', step_id: 'b.s1' }] },
        { status: 'confirmed', targets: [{ process_id: 'stale', step_id: 'stale.s1' }] },
      ])
      const record = Object.fromEntries(scoped.map((value, index) => [index, value]))
      expect(mappingsForStep(record, steps[0]!).map(value => value.status)).toEqual(['confirmed'])
      expect(mappingsForStep(record, steps[1]!).map(value => value.status)).toEqual(['not_applicable'])
    }
  })

  it('keeps editing final targets separate from the saved snapshot', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue({
      ...template(5),
      step_mappings: [{ ...stepMapping(), final_targets: [{ process_id: 'a', step_id: 'a.s1' }] }],
    })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()

    expect(model.draftStepMappings.value[0]?.final_targets).toEqual([{ process_id: 'a', step_id: 'a.s1' }])
    model.draftStepMappings.value[0]!.final_targets![0]!.step_id = 'edited.s1'
    model.draftStepMappings.value[0]!.final_targets!.push({ process_id: 'b', step_id: 'b.s1' })
    expect(model.template.value?.step_mappings[0]?.final_targets).toEqual([{ process_id: 'a', step_id: 'a.s1' }])
  })

  it('omits empty legacy targets from editable mappings', async () => {
    const snapshot = { ...template(5), step_mappings: [{ ...stepMapping(), final_targets: [] }] }
    getCurrentGroupTemplateMock.mockResolvedValue(snapshot)
    saveGroupTemplateStepMappingsMock.mockResolvedValue({ ...snapshot, template_revision: 6 })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    expect(model.draftStepMappings.value[0]).not.toHaveProperty('final_targets')
    await model.saveStepMappings()
    expect(model.draftStepMappings.value[0]).not.toHaveProperty('final_targets')
  })

  it('does not apply an old project response or clear the new project loading state', async () => {
    let finishOld!: (value: ReturnType<typeof template>) => void
    let finishCurrent!: (value: ReturnType<typeof template>) => void
    getCurrentGroupTemplateMock
      .mockReturnValueOnce(new Promise(resolve => { finishOld = resolve }))
      .mockReturnValueOnce(new Promise(resolve => { finishCurrent = resolve }))
    const project = ref(28)
    const model = useProjectGroupTemplate(project, ref({}))
    const oldLoad = model.load()
    project.value = 29
    const currentLoad = model.load()
    finishOld(template(2))
    await oldLoad
    expect(model.template.value).toBeNull()
    expect(model.loading.value).toBe(true)
    finishCurrent({ ...template(4), project_id: 29 })
    await currentLoad
    expect(model.template.value?.project_id).toBe(29)
    expect(model.loading.value).toBe(false)
  })

  it('clears the previous project workspace before another save can be sent', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(2, [mapping()]))
    const project = ref(28)
    const model = useProjectGroupTemplate(project, ref({}))
    await model.load()
    project.value = 29
    await model.saveStepMappings()
    expect(model.template.value).toBeNull()
    expect(model.draftMappings.value).toEqual([])
    expect(saveGroupTemplateStepMappingsMock).not.toHaveBeenCalled()
  })

  it('ignores a save response for a project that is no longer selected', async () => {
    let finishSave!: (value: ReturnType<typeof template>) => void
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(2))
      .mockResolvedValueOnce({ ...template(7), project_id: 29 })
    saveGroupTemplateStepMappingsMock.mockReturnValueOnce(new Promise(resolve => { finishSave = resolve }))
    const project = ref(28)
    const model = useProjectGroupTemplate(project, ref({}))
    await model.load()
    const oldSave = model.saveStepMappings()
    project.value = 29
    await model.load()
    finishSave(template(3))
    await oldSave
    expect(model.template.value?.project_id).toBe(29)
    expect(model.templateRevision.value).toBe(7)
    expect(model.saving.value).toBe(false)
  })

  it('discards a preview after switching projects', async () => {
    let finishPreview!: (value: ReturnType<typeof preview>) => void
    previewGroupTemplateMock.mockReturnValueOnce(new Promise(resolve => { finishPreview = resolve }))
    const project = ref(28)
    const model = useProjectGroupTemplate(project, ref({}))
    const pending = model.selectFile(xmlFile)
    project.value = 29
    finishPreview(preview())
    await pending
    expect(model.state.value).toBe('empty')
    expect(model.preview.value).toBeNull()
    expect(model.loading.value).toBe(false)
  })

  it('does not show an old project error over the current project', async () => {
    let failOld!: (error: unknown) => void
    getCurrentGroupTemplateMock
      .mockReturnValueOnce(new Promise((_resolve, reject) => { failOld = reject }))
      .mockResolvedValueOnce({ ...template(7), project_id: 29 })
    const project = ref(28)
    const model = useProjectGroupTemplate(project, ref({}))
    const oldLoad = model.load()
    project.value = 29
    await model.load()
    failOld({ response: { status: 503, data: { detail: '旧任务不可用' } } })
    await oldLoad
    expect(model.error.value).toBe('')
    expect(model.templateRevision.value).toBe(7)
  })

  it('returns false when a save is superseded by a reload', async () => {
    let finishSave!: (value: ReturnType<typeof template>) => void
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(2))
      .mockResolvedValueOnce(template(4))
    saveGroupTemplateStepMappingsMock.mockReturnValueOnce(new Promise(resolve => { finishSave = resolve }))
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    const pending = model.saveStepMappings()
    await model.load()
    finishSave(template(3))
    expect(await pending).toBe(false)
    expect(model.templateRevision.value).toBe(4)
  })

  it('shows the rejected feature value with its group path', () => {
    expect(formatGroupTemplateIssueDetail({
      code: 'unknown_feature_selection',
      message: 'Feature selection is not present in the approved dictionary.',
      path: ['A侧', '孔'],
      value: '非法特征',
    })).toBe('A侧 / 孔 · 非法特征')
  })

  it('moves an empty project through preview into a confirmed workspace', async () => {
    getCurrentGroupTemplateMock.mockRejectedValue({ response: { status: 404 } })
    previewGroupTemplateMock.mockResolvedValue(preview())
    commitGroupTemplateMock.mockResolvedValue({
      ...template(1),
      kept_source_operation_ids: [],
      invalidated: [],
    })
    const model = useProjectGroupTemplate(ref(28), ref({}))

    await model.load()
    expect(model.state.value).toBe('empty')

    await model.selectFile(xmlFile)
    expect(model.state.value).toBe('preview')
    expect(model.preview.value?.can_confirm).toBe(true)

    await model.confirmTemplate()
    expect(model.state.value).toBe('workspace')
    expect(model.templateRevision.value).toBe(1)
  })

  it('opens an existing template directly in its workspace', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(4, [mapping()]))
    const model = useProjectGroupTemplate(ref(28), ref({}))

    await model.load()

    expect(model.state.value).toBe('workspace')
    expect(model.templateRevision.value).toBe(4)
    expect(model.draftMappings.value).toEqual([{
      source_operation_id: 11,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }])
  })

  it('keeps an invalid file in preview for validation feedback', async () => {
    previewGroupTemplateMock.mockResolvedValue(preview(false))
    const model = useProjectGroupTemplate(ref(28), ref({}))

    await model.selectFile(xmlFile)

    expect(model.state.value).toBe('preview')
    expect(model.preview.value?.can_confirm).toBe(false)
    expect(commitGroupTemplateMock).not.toHaveBeenCalled()
  })

  it('cancels a replacement without discarding the confirmed workspace', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(2, [mapping()]))
    previewGroupTemplateMock.mockResolvedValue(preview(true, [node(['B侧', '槽'])]))
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()

    model.beginReplacement()
    await model.selectFile(xmlFile)
    model.cancelPreview()

    expect(model.state.value).toBe('workspace')
    expect(model.template.value?.content_hash).toBe('stored-hash')
    expect(model.draftMappings.value).toEqual([{
      source_operation_id: 11,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }])
  })

  it('reloads the template and clears busy state after a stale revision conflict', async () => {
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(2))
      .mockResolvedValueOnce(template(3))
    previewGroupTemplateMock.mockResolvedValue(preview())
    commitGroupTemplateMock.mockRejectedValue({ response: { status: 409 } })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.beginReplacement()
    await model.selectFile(xmlFile)

    await model.confirmTemplate()

    expect(model.saving.value).toBe(false)
    expect(model.loading.value).toBe(false)
    expect(model.templateRevision.value).toBe(3)
    expect(model.error.value).toBe('分组模板已在其他页面更新，已重新加载最新内容。')
  })

  it('shows the stale conflict while the latest template is still loading', async () => {
    let finishReload!: (value: ReturnType<typeof template>) => void
    const reload = new Promise<ReturnType<typeof template>>((resolve) => {
      finishReload = resolve
    })
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(2))
      .mockReturnValueOnce(reload)
    previewGroupTemplateMock.mockResolvedValue(preview())
    commitGroupTemplateMock.mockRejectedValue({ response: { status: 409 } })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.beginReplacement()
    await model.selectFile(xmlFile)

    const confirmation = model.confirmTemplate()
    await vi.waitFor(() => expect(getCurrentGroupTemplateMock).toHaveBeenCalledTimes(2))

    expect(model.error.value).toBe('分组模板已在其他页面更新，正在重新加载最新内容。')
    finishReload(template(3))
    await confirmation
    expect(model.error.value).toBe('分组模板已在其他页面更新，已重新加载最新内容。')
  })

  it('reports a failed stale reload instead of claiming the latest template was loaded', async () => {
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(2))
      .mockRejectedValueOnce({ response: { status: 503, data: { detail: '服务暂不可用' } } })
    previewGroupTemplateMock.mockResolvedValue(preview())
    commitGroupTemplateMock.mockRejectedValue({ response: { status: 409 } })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.beginReplacement()
    await model.selectFile(xmlFile)

    await model.confirmTemplate()

    expect(model.error.value).toBe('分组模板已在其他页面更新，但重新加载失败：服务暂不可用')
  })

  it('confirms a replacement against the current revision and uses server migration results', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(7, [mapping()]))
    previewGroupTemplateMock.mockResolvedValue(preview(true, [node([' A侧 ', '孔'])]))
    commitGroupTemplateMock.mockResolvedValue({
      ...template(8, [mapping(['A侧', '孔'])]),
      kept_source_operation_ids: [11],
      invalidated: [],
    })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.beginReplacement()
    await model.selectFile(xmlFile)

    expect(model.replacementImpact.value).toMatchObject({ kept_source_operation_ids: [11], invalidated: [] })
    await model.confirmTemplate()

    expect(commitGroupTemplateMock).toHaveBeenCalledWith(28, xmlFile, 'preview-hash', 7)
    expect(model.replacementImpact.value).toEqual({
      kept_source_operation_ids: [11],
      invalidated: [],
      kept_source_step_keys: [],
      invalidated_step_mappings: [],
    })
    expect(model.templateRevision.value).toBe(8)
  })

  it('saves against the latest revision and keeps server-enriched mappings', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(5))
    saveGroupTemplateMappingsMock.mockResolvedValue(template(6, [mapping()]))
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.draftMappings.value = [{
      source_operation_id: 11,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }]

    await model.saveMappings()

    expect(saveGroupTemplateMappingsMock).toHaveBeenCalledWith(28, 5, [{
      source_operation_id: 11,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }])
    expect(model.templateRevision.value).toBe(6)
    expect(model.template.value?.mappings).toEqual([mapping()])
  })

  it('saves formal step mappings without overwriting legacy operation aliases', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(5, [mapping()]))
    saveGroupTemplateStepMappingsMock.mockResolvedValue({
      ...template(6, [mapping()]),
      step_mappings: [stepMapping()],
    })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.load()
    model.draftStepMappings.value = [{
      source_operation_id: 11,
      source_operation_name: '车削A侧',
      source_step_order: 1,
      source_step_name: '钻孔',
      scope_template_group_path: ['A侧'],
      template_group_path: ['A侧', '孔'],
      candidate_features: ['孔(盲孔)'],
      match_mode: 'any',
      status: 'confirmed',
      confidence: 1,
      source: 'user_confirmed',
    }]

    await model.saveStepMappings([{
      operation_id: 11,
      operation_name: '车削A侧',
      step_items: ['钻孔'],
      rule_evidence: ['孔'],
      rule_reasons: ['形成孔特征'],
    }])

    expect(saveGroupTemplateStepMappingsMock).toHaveBeenCalledWith(28, 5, model.draftStepMappings.value, [{
      operation_id: 11,
      operation_name: '车削A侧',
      step_items: ['钻孔'],
      rule_evidence: ['孔'],
      rule_reasons: ['形成孔特征'],
    }])
    expect(model.template.value?.step_mappings).toEqual([stepMapping()])
    expect(model.template.value?.mappings).toEqual([mapping()])
  })

  it('migrates first-load legacy aliases only when their normalized paths exist and leaves them unsaved', async () => {
    getCurrentGroupTemplateMock.mockResolvedValue(template(1))
    const model = useProjectGroupTemplate(ref(28), ref({
      11: {
        source_operation_id: 11,
        alias: '钻孔（A侧/孔）',
        template_group_id: 'legacy-hole-id',
        template_group_path: [' A侧 ', '孔'],
      },
      12: {
        source_operation_id: 12,
        alias: '铣槽（A侧/槽）',
        template_group_id: 'legacy-slot-id',
        template_group_path: ['A侧', '槽'],
      },
    }))

    await model.load()

    expect(model.draftMappings.value).toEqual([{
      source_operation_id: 11,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }])
    expect(model.template.value?.mappings).toEqual([])
    expect(saveGroupTemplateMappingsMock).not.toHaveBeenCalled()
  })

  it('does not pair a failed new file with the previous successful preview', async () => {
    previewGroupTemplateMock
      .mockResolvedValueOnce(preview())
      .mockRejectedValueOnce({ response: { status: 422, data: { detail: '文件无法解析' } } })
    commitGroupTemplateMock.mockResolvedValue({
      ...template(1),
      kept_source_operation_ids: [],
      invalidated: [],
    })
    const model = useProjectGroupTemplate(ref(28), ref({}))
    await model.selectFile(xmlFile)

    await model.selectFile(new File(['broken'], 'broken.xml', { type: 'application/xml' }))
    await model.confirmTemplate()

    expect(model.preview.value).toBeNull()
    expect(model.error.value).toBe('文件无法解析')
    expect(commitGroupTemplateMock).not.toHaveBeenCalled()
  })

  it('keeps only the newest preview when file requests finish out of order', async () => {
    let finishFirst!: (value: ReturnType<typeof preview>) => void
    let finishSecond!: (value: ReturnType<typeof preview>) => void
    previewGroupTemplateMock
      .mockReturnValueOnce(new Promise(resolve => { finishFirst = resolve }))
      .mockReturnValueOnce(new Promise(resolve => { finishSecond = resolve }))
    const model = useProjectGroupTemplate(ref(28), ref({}))
    const firstFile = new File(['first'], 'first.xml', { type: 'application/xml' })
    const secondFile = new File(['second'], 'second.xml', { type: 'application/xml' })

    const firstRequest = model.selectFile(firstFile)
    const secondRequest = model.selectFile(secondFile)
    expect(model.loading.value).toBe(true)
    finishSecond({ ...preview(), original_filename: 'second.xml', content_hash: 'second-hash' })
    await secondRequest
    finishFirst({ ...preview(), original_filename: 'first.xml', content_hash: 'first-hash' })
    await firstRequest

    expect(model.preview.value?.original_filename).toBe('second.xml')
    expect(model.loading.value).toBe(false)
  })

  it('runs first-load legacy migration again after the reactive project changes', async () => {
    const projectId = ref(28)
    const aliases = ref<Record<string, any>>({
      11: { source_operation_id: 11, alias: '钻孔（A侧/孔）', template_group_path: ['A侧', '孔'] },
    })
    getCurrentGroupTemplateMock
      .mockResolvedValueOnce(template(1))
      .mockResolvedValueOnce({ ...template(1), project_id: 29 })
    const model = useProjectGroupTemplate(projectId, aliases)

    await model.load()
    projectId.value = 29
    aliases.value = {
      12: { source_operation_id: 12, alias: '钻孔（A侧/孔）', template_group_path: ['A侧', '孔'] },
    }
    await model.load()

    expect(model.draftMappings.value).toEqual([{
      source_operation_id: 12,
      alias: '钻孔（A侧/孔）',
      template_group_path: ['A侧', '孔'],
    }])
  })
})
