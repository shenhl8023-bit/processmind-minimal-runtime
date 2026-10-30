import { computed, ref } from 'vue'
import {
  buildDocumentFileUrl,
  buildDocumentPdfPageUrl,
  getDocumentPdfPageCount,
  getDocumentPreview,
  type DocumentItem,
  type DocumentPreview,
} from '@/api'

export function useAnalysisDocumentPreview() {
  const documentPreviewLoading = ref(false)
  const documentPreviewError = ref('')
  const documentPreview = ref<DocumentPreview | null>(null)
  const documentPreviewVisible = ref(false)
  const documentPreviewPdfPageUrls = ref<string[]>([])
  let previewRequestId = 0

  const documentPreviewFileUrl = computed(() => {
    return documentPreview.value
      ? `${buildDocumentFileUrl(documentPreview.value.id)}#toolbar=1&navpanes=0&scrollbar=1&view=FitH`
      : ''
  })

  function clearDocumentPreviewPdfPages() {
    previewRequestId += 1
    documentPreviewLoading.value = false
    documentPreviewPdfPageUrls.value = []
  }

  async function openDocumentPreview(doc: DocumentItem) {
    documentPreviewVisible.value = true
    documentPreviewLoading.value = true
    documentPreviewError.value = ''
    clearDocumentPreviewPdfPages()
    const requestId = ++previewRequestId
    documentPreviewLoading.value = true
    const isCurrent = () => requestId === previewRequestId && documentPreviewVisible.value
    documentPreview.value = {
      id: doc.id,
      original_name: doc.original_name,
      file_type: doc.file_type || null,
      preview_text: '',
    }
    if ((doc.file_type || '').toLowerCase() === 'pdf') {
      try {
        const { page_count } = await getDocumentPdfPageCount(doc.id)
        if (!isCurrent()) return
        documentPreviewPdfPageUrls.value = Array.from(
          { length: Math.max(0, page_count) },
          (_, idx) => buildDocumentPdfPageUrl(doc.id, idx + 1),
        )
      } catch (e: any) {
        if (!isCurrent()) return
        console.error('加载 PDF 预览失败', e)
        documentPreviewError.value = e?.response?.data?.detail || '加载 PDF 预览失败，请稍后重试。'
      } finally {
        if (isCurrent()) documentPreviewLoading.value = false
      }
      return
    }
    try {
      const result = await getDocumentPreview(doc.id)
      if (!isCurrent()) return
      documentPreview.value = result
    } catch (e: any) {
      if (!isCurrent()) return
      console.error('加载文档预览失败', e)
      documentPreviewError.value = e?.response?.data?.detail || '加载文档预览失败，请稍后重试。'
    } finally {
      if (isCurrent()) documentPreviewLoading.value = false
    }
  }

  function closeDocumentPreview() {
    documentPreviewVisible.value = false
    clearDocumentPreviewPdfPages()
  }

  function openDocumentOriginal() {
    if (!documentPreview.value) return
    window.open(buildDocumentFileUrl(documentPreview.value.id), '_blank', 'noopener,noreferrer')
  }

  return {
    documentPreviewLoading,
    documentPreviewError,
    documentPreview,
    documentPreviewVisible,
    documentPreviewFileUrl,
    documentPreviewPdfPageUrls,
    openDocumentPreview,
    closeDocumentPreview,
    openDocumentOriginal,
    clearDocumentPreviewPdfPages,
  }
}
