import { computed, ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

import { getDocumentPreview } from '@/api'
import { useAnalysisDocumentTextCache } from './useAnalysisDocumentTextCache'

vi.mock('@/api', () => ({
  getDocumentPreview: vi.fn(),
}))

const getDocumentPreviewMock = vi.mocked(getDocumentPreview)

describe('useAnalysisDocumentTextCache', () => {
  beforeEach(() => {
    getDocumentPreviewMock.mockReset()
  })

  it('shares in-flight preview requests across concurrent ensures', async () => {
    const resolvers = new Map<number, (value: any) => void>()
    getDocumentPreviewMock.mockImplementation((docId) => new Promise((resolve) => {
      resolvers.set(docId, resolve)
    }))

    const selectedDocIds = ref(new Set([1, 2]))
    const cache = useAnalysisDocumentTextCache({
      selectedDocIds: computed(() => selectedDocIds.value),
    })

    const firstEnsure = cache.ensureMatchedDocumentPreviewTexts()
    const secondEnsure = cache.ensureMatchedDocumentPreviewTexts()

    expect(getDocumentPreviewMock).toHaveBeenCalledTimes(2)
    resolvers.get(1)?.({ id: 1, original_name: 'one.pdf', preview_text: 'one' })
    resolvers.get(2)?.({ id: 2, original_name: 'two.pdf', preview_text: 'two' })
    await Promise.all([firstEnsure, secondEnsure])

    expect(cache.documentPreviewTextMap.value).toEqual({ 1: 'one', 2: 'two' })
  })

  it('ignores requests completed after the cache is cleared', async () => {
    const resolvers: Array<(value: any) => void> = []
    getDocumentPreviewMock.mockImplementation(() => new Promise((resolve) => {
      resolvers.push(resolve)
    }))

    const cache = useAnalysisDocumentTextCache({
      selectedDocIds: computed(() => new Set([1])),
    })

    const staleEnsure = cache.ensureMatchedDocumentPreviewTexts()
    cache.clearDocumentPreviewTexts()
    const currentEnsure = cache.ensureMatchedDocumentPreviewTexts()

    resolvers[0]?.({ id: 1, original_name: 'old.pdf', preview_text: 'old' })
    await staleEnsure
    expect(cache.documentPreviewTextMap.value).toEqual({})

    resolvers[1]?.({ id: 1, original_name: 'new.pdf', preview_text: 'new' })
    await currentEnsure
    expect(cache.documentPreviewTextMap.value).toEqual({ 1: 'new' })
  })
})
