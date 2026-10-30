import { beforeEach, describe, expect, it, vi } from 'vitest'

const apiMocks = vi.hoisted(() => ({ post: vi.fn(), get: vi.fn(), patch: vi.fn() }))

vi.mock('@/api/client', () => ({ api: apiMocks }))

import {
  createKnowledgeSuggestion,
  listKnowledgeSuggestions,
  saveKnowledgeEvidence,
  searchKnowledge,
  listKnowledgeCatalog,
  getKnowledgeCatalogRecord,
  updateKnowledgeSuggestion,
} from './knowledge'

describe('knowledge API contracts', () => {
  it('browses without the model and uses query params for special record IDs', async () => {
    apiMocks.get.mockResolvedValueOnce({ data: { total: 30, items: [] } })
    await listKnowledgeCatalog({ section: 'resources', category: 'equipment', page: 2, page_size: 20 })
    expect(apiMocks.get).toHaveBeenCalledWith('/api/knowledge/catalog', { params: { section: 'resources', category: 'equipment', page: 2, page_size: 20 } })
    apiMocks.get.mockResolvedValueOnce({ data: { id: 'WD/01:第3节' } })
    await getKnowledgeCatalogRecord('WD/01:第3节')
    expect(apiMocks.get).toHaveBeenLastCalledWith('/api/knowledge/catalog/record', { params: { record_id: 'WD/01:第3节' } })
  })
  beforeEach(() => {
    apiMocks.post.mockReset()
    apiMocks.get.mockReset()
    apiMocks.patch.mockReset()
  })

  it('sends the question and context without exposing provider credentials', async () => {
    apiMocks.post.mockResolvedValueOnce({
      data: { status: 'ok', message: '', items: [] },
    })

    await searchKnowledge({
      project_id: 17,
      query: '真空淬火硬度',
      top_k: 5,
      context: { segment_id: 'heat-treatment' },
    })

    expect(apiMocks.post).toHaveBeenCalledWith('/api/knowledge/search', {
      project_id: 17,
      query: '真空淬火硬度',
      top_k: 5,
      context: { segment_id: 'heat-treatment' },
    })
  })

  it('keeps source location fields when saving an evidence snapshot', async () => {
    apiMocks.post.mockResolvedValueOnce({
      data: { id: 3, snapshot_hash: 'hash', page_no: 23 },
    })

    const result = await saveKnowledgeEvidence({
      project_id: 17,
      route_version_id: 42,
      segment_id: 'heat-treatment',
      query: '硬度',
      item_id: 'chunk-1',
      content: '不低于56 HRC',
      document_name: 'JRT148-06-01.pdf',
      page_no: 23,
      identity: 'jrt148:v1:p23',
    })

    expect(result.page_no).toBe(23)
    expect(apiMocks.post).toHaveBeenCalledWith('/api/knowledge/evidence', expect.objectContaining({
      route_version_id: 42,
      segment_id: 'heat-treatment',
      page_no: 23,
      identity: 'jrt148:v1:p23',
    }))
  })

  it('creates a rule suggestion from adopted evidence without provider credentials', async () => {
    apiMocks.post.mockResolvedValueOnce({
      data: { id: 9, status: 'draft', suggestion_text: '待审核规则' },
    })

    const result = await createKnowledgeSuggestion({
      project_id: 17,
      route_version_id: 42,
      segment_id: 'heat-treatment',
      title: '热处理硬度要求',
      suggestion_text: '待审核规则',
      evidence_ids: [3],
    })

    expect(result.id).toBe(9)
    expect(apiMocks.post).toHaveBeenCalledWith('/api/knowledge/suggestions/draft', {
      project_id: 17,
      route_version_id: 42,
      segment_id: 'heat-treatment',
      title: '热处理硬度要求',
      suggestion_text: '待审核规则',
      evidence_ids: [3],
    })
  })

  it('lists and updates scoped rule suggestions', async () => {
    apiMocks.get.mockResolvedValueOnce({ data: [{ id: 9, status: 'pending_review' }] })
    apiMocks.patch.mockResolvedValueOnce({ data: { id: 9, status: 'confirmed' } })

    const list = await listKnowledgeSuggestions(17, { route_version_id: 42 })
    const updated = await updateKnowledgeSuggestion(9, { status: 'confirmed', updated_by: '审核人' })

    expect(list[0]?.id).toBe(9)
    expect(apiMocks.get).toHaveBeenCalledWith('/api/knowledge/suggestions', {
      params: { project_id: 17, route_version_id: 42 },
    })
    expect(updated.status).toBe('confirmed')
    expect(apiMocks.patch).toHaveBeenCalledWith('/api/knowledge/suggestions/9', {
      status: 'confirmed',
      updated_by: '审核人',
    })
  })
})
