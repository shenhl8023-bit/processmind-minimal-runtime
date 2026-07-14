import { computed, ref, type ComponentPublicInstance, type Ref } from 'vue'
import type { FinalizeDraft } from '@/composables/finalizeViewHelpers'

export function useFinalizeDrafts(projectId: Ref<number | null>) {
  const drafts = ref<Record<string, FinalizeDraft>>({})
  const inlineEditingSegmentId = ref<string | null>(null)
  const inlineEditingText = ref('')
  const inlineTextareaRef = ref<HTMLTextAreaElement | null>(null)

  const draftStorageKey = computed(() => `processmind_finalize_drafts_v4_${projectId.value || 'unknown'}`)

  function readDrafts() {
    if (typeof window === 'undefined') return
    try {
      const raw = window.localStorage.getItem(draftStorageKey.value)
      drafts.value = raw ? JSON.parse(raw) : {}
    } catch (err) {
      console.warn('读取第四步草稿失败', err)
      drafts.value = {}
    }
  }

  function persistDrafts() {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(draftStorageKey.value, JSON.stringify(drafts.value))
  }

  function startInlineEdit(item: any) {
    inlineEditingSegmentId.value = item.segment.id
    inlineEditingText.value = item.conditionText
    setTimeout(() => {
      inlineTextareaRef.value?.focus()
    }, 50)
  }

  function setInlineTextareaRef(el: Element | ComponentPublicInstance | null) {
    inlineTextareaRef.value = el instanceof HTMLTextAreaElement ? el : null
  }

  function cancelInlineEdit() {
    inlineEditingSegmentId.value = null
    inlineEditingText.value = ''
  }

  function saveInlineEdit(item: any) {
    const segmentId = item.segment.id
    const existingDraft = drafts.value[segmentId] || {
      factorNames: [...item.factorNames],
      userAnswerLabels: [...item.userAnswerLabels],
      userAnswerContextLabels: [...item.userAnswerContextLabels],
    }

    drafts.value = {
      ...drafts.value,
      [segmentId]: {
        ...existingDraft,
        conditionText: inlineEditingText.value.trim(),
      },
    }

    cancelInlineEdit()
  }

  function resetInlineEdit(item: any) {
    const segmentId = item.segment.id
    const next = { ...drafts.value }
    delete next[segmentId]
    drafts.value = next

    if (inlineEditingSegmentId.value === segmentId) {
      cancelInlineEdit()
    }
  }

  return {
    cancelInlineEdit,
    drafts,
    inlineEditingSegmentId,
    inlineEditingText,
    persistDrafts,
    readDrafts,
    resetInlineEdit,
    saveInlineEdit,
    setInlineTextareaRef,
    startInlineEdit,
  }
}
