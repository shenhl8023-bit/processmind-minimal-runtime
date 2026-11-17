import { beforeEach, describe, expect, it, vi } from 'vitest'
import { api } from './client'
import { deleteDocument } from './documents'

vi.mock('./client', () => ({ api: { delete: vi.fn() }, apiBaseUrl: '' }))

describe('document delete identity', () => {
  beforeEach(() => vi.resetAllMocks())

  it('sends the project and stored file identity seen by the user', async () => {
    vi.mocked(api.delete).mockResolvedValue({ data: { ok: true } })
    await deleteDocument(17, { project_id: 2, filename: 'stable-upload-token.json' })
    expect(api.delete).toHaveBeenCalledWith('/api/documents/17', {
      params: { project_id: 2, expected_filename: 'stable-upload-token.json' },
    })
  })
})
