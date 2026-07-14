import { ref, type ComputedRef } from 'vue'
import { getDocumentPreview } from '@/api'

type UseAnalysisDocumentTextCacheOptions = {
  selectedDocIds: ComputedRef<Set<number>>
}

export function useAnalysisDocumentTextCache(options: UseAnalysisDocumentTextCacheOptions) {
  const documentPreviewTextMap = ref<Record<number, string>>({})

  function clearDocumentPreviewTexts() {
    documentPreviewTextMap.value = {}
  }

  async function ensureMatchedDocumentPreviewTexts() {
    const docIds = Array.from(options.selectedDocIds.value).filter(id => id > 0)
    const missingIds = docIds.filter(docId => !(docId in documentPreviewTextMap.value))
    if (!missingIds.length) return
    await Promise.all(
      missingIds.map(async (docId) => {
        try {
          const preview = await getDocumentPreview(docId)
          documentPreviewTextMap.value = {
            ...documentPreviewTextMap.value,
            [docId]: preview.preview_text || '',
          }
        } catch (e) {
          console.warn('加载文档预览文本失败', docId, e)
          documentPreviewTextMap.value = {
            ...documentPreviewTextMap.value,
            [docId]: '',
          }
        }
      }),
    )
  }

  return {
    documentPreviewTextMap,
    clearDocumentPreviewTexts,
    ensureMatchedDocumentPreviewTexts,
  }
}
