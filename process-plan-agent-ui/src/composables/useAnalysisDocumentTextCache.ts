import { ref, type ComputedRef } from 'vue'
import { getDocumentPreview } from '@/api'

type UseAnalysisDocumentTextCacheOptions = {
  selectedDocIds: ComputedRef<Set<number>>
}

export function useAnalysisDocumentTextCache(options: UseAnalysisDocumentTextCacheOptions) {
  const documentPreviewTextMap = ref<Record<number, string>>({})
  const pendingDocumentPreviewTexts = new Map<number, Promise<void>>()
  let cacheGeneration = 0

  function clearDocumentPreviewTexts() {
    cacheGeneration += 1
    documentPreviewTextMap.value = {}
    pendingDocumentPreviewTexts.clear()
  }

  async function ensureMatchedDocumentPreviewTexts() {
    const docIds = Array.from(options.selectedDocIds.value).filter(id => id > 0)
    const missingIds = docIds.filter(docId => !(docId in documentPreviewTextMap.value))
    if (!missingIds.length) return
    const generation = cacheGeneration
    const requests = missingIds.map((docId) => {
      const pendingRequest = pendingDocumentPreviewTexts.get(docId)
      if (pendingRequest) return pendingRequest

      const request = getDocumentPreview(docId)
        .then((preview) => {
          if (generation !== cacheGeneration) return
          documentPreviewTextMap.value = {
            ...documentPreviewTextMap.value,
            [docId]: preview.preview_text || '',
          }
        })
        .catch((e) => {
          console.warn('加载文档预览文本失败', docId, e)
          if (generation !== cacheGeneration) return
          documentPreviewTextMap.value = {
            ...documentPreviewTextMap.value,
            [docId]: '',
          }
        })
        .finally(() => {
          if (pendingDocumentPreviewTexts.get(docId) === request) {
            pendingDocumentPreviewTexts.delete(docId)
          }
        })

      pendingDocumentPreviewTexts.set(docId, request)
      return request
    })

    await Promise.all(requests)
  }

  return {
    documentPreviewTextMap,
    clearDocumentPreviewTexts,
    ensureMatchedDocumentPreviewTexts,
  }
}
