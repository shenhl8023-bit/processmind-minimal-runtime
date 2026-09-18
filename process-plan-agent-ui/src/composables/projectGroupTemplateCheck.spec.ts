import { describe, expect, it, vi } from 'vitest'
import { getCurrentGroupTemplate } from '@/api/extract'
import {
  checkProjectGroupTemplateReady,
  isGroupTemplateReady,
} from './projectGroupTemplateCheck'

vi.mock('@/api/extract', () => ({
  getCurrentGroupTemplate: vi.fn(),
}))

const getCurrentGroupTemplateMock = vi.mocked(getCurrentGroupTemplate)

describe('projectGroupTemplateCheck', () => {
  it('returns false for null or undefined templates in isGroupTemplateReady', () => {
    expect(isGroupTemplateReady(null)).toBe(false)
    expect(isGroupTemplateReady(undefined)).toBe(false)
  })

  it('detects ready when legacy mappings are present', () => {
    const template: any = {
      project_id: 1,
      mappings: [{ source_operation_id: 10, template_group_path: ['A', 'B'] }],
      step_mappings: [],
    }
    expect(isGroupTemplateReady(template)).toBe(true)
  })

  it('detects ready when confirmed step mappings are present', () => {
    const template: any = {
      project_id: 1,
      mappings: [],
      step_mappings: [
        {
          source_operation_id: 10,
          status: 'confirmed',
          template_group_path: ['A', 'B'],
        },
      ],
    }
    expect(isGroupTemplateReady(template)).toBe(true)
  })

  it('detects not ready when mappings and step mappings are empty or unconfirmed', () => {
    const template: any = {
      project_id: 1,
      mappings: [],
      step_mappings: [
        {
          source_operation_id: 10,
          status: 'draft',
          template_group_path: [],
        },
      ],
    }
    expect(isGroupTemplateReady(template)).toBe(false)
  })

  it('checkProjectGroupTemplateReady returns missing_template when projectId is 0', async () => {
    const result = await checkProjectGroupTemplateReady(0)
    expect(result.ready).toBe(false)
    expect(result.code).toBe('missing_template')
  })

  it('checkProjectGroupTemplateReady returns missing_template on 404', async () => {
    getCurrentGroupTemplateMock.mockRejectedValueOnce({ response: { status: 404 } })
    const result = await checkProjectGroupTemplateReady(123)
    expect(result.ready).toBe(false)
    expect(result.code).toBe('missing_template')
  })

  it('checkProjectGroupTemplateReady returns ready when template is configured', async () => {
    getCurrentGroupTemplateMock.mockResolvedValueOnce({
      project_id: 123,
      original_filename: 'template.xml',
      source_encoding: 'utf-8',
      part_filename: 'part.xml',
      content_hash: 'hash',
      feature_dictionary_version: '1.0',
      tree: [],
      validation_issues: [],
      mappings: [{ source_operation_id: 1, alias: '', template_group_id: '1', template_group_key: '1', template_group_name: '下料', template_group_path: ['下料'], feature_selections: [] }],
      step_mappings: [],
      mapping_output: [],
      template_revision: 1,
      group_count: 1,
      feature_selection_count: 0,
      created_at: null,
      updated_at: null,
    })
    const result = await checkProjectGroupTemplateReady(123)
    expect(result.ready).toBe(true)
  })
})
