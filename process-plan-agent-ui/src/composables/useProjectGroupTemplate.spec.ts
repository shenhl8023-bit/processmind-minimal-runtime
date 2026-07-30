import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import {
  commitGroupTemplate,
  getCurrentGroupTemplate,
  previewGroupTemplate,
  saveGroupTemplateMappings,
} from '@/api/extract'
import type { GroupTemplateMapping, GroupTemplateNode } from '@/api/extract'
import { useProjectGroupTemplate } from './useProjectGroupTemplate'

vi.mock('@/api/extract', () => ({
  previewGroupTemplate: vi.fn(),
  getCurrentGroupTemplate: vi.fn(),
  commitGroupTemplate: vi.fn(),
  saveGroupTemplateMappings: vi.fn(),
}))

const previewGroupTemplateMock = vi.mocked(previewGroupTemplate)
const getCurrentGroupTemplateMock = vi.mocked(getCurrentGroupTemplate)
const commitGroupTemplateMock = vi.mocked(commitGroupTemplate)
const saveGroupTemplateMappingsMock = vi.mocked(saveGroupTemplateMappings)

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
    template_revision: revision,
    group_count: 1,
    feature_selection_count: 1,
    created_at: null,
    updated_at: null,
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
    expect(model.replacementImpact.value).toEqual({ kept_source_operation_ids: [11], invalidated: [] })
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
})
