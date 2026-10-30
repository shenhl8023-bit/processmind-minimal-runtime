import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ getDocumentPreview: vi.fn(), getDocumentPdfPageCount: vi.fn() }))
vi.mock('@/api', () => ({
  ...mocks, buildDocumentFileUrl: (id: number) => `/document/${id}`,
  buildDocumentPdfPageUrl: (id: number, page: number) => `/document/${id}/page/${page}`,
}))
import { useAnalysisDocumentPreview } from './useAnalysisDocumentPreview'

describe('analysis evidence preview request boundaries', () => {
  beforeEach(() => Object.values(mocks).forEach(mock => mock.mockReset()))

  it('keeps the newly selected evidence when an earlier preview responds late', async () => {
    let finish!: (value: any) => void
    mocks.getDocumentPreview.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    mocks.getDocumentPreview.mockResolvedValueOnce({ id: 2, original_name: 'new.txt', preview_text: 'new' })
    const preview = useAnalysisDocumentPreview()
    const old = preview.openDocumentPreview({ id: 1, original_name: 'old.txt', file_type: 'txt' } as any)
    await preview.openDocumentPreview({ id: 2, original_name: 'new.txt', file_type: 'txt' } as any)
    finish({ id: 1, original_name: 'old.txt', preview_text: 'old' })
    await old

    expect(preview.documentPreview.value?.id).toBe(2)
    expect(preview.documentPreview.value?.preview_text).toBe('new')
  })

  it('does not refill PDF pages after closing the preview', async () => {
    let finish!: (value: any) => void
    mocks.getDocumentPdfPageCount.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const preview = useAnalysisDocumentPreview()
    const pending = preview.openDocumentPreview({ id: 1, original_name: 'old.pdf', file_type: 'pdf' } as any)
    preview.closeDocumentPreview()
    finish({ page_count: 3 })
    await pending

    expect(preview.documentPreviewVisible.value).toBe(false)
    expect(preview.documentPreviewPdfPageUrls.value).toEqual([])
    expect(preview.documentPreviewLoading.value).toBe(false)
  })
})
