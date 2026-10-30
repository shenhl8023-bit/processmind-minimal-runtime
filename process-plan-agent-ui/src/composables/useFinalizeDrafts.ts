import { computed, ref, type ComponentPublicInstance, type Ref } from 'vue'
import { finalizeDraftMatchesReview, finalizeDraftReviewBaseline, type FinalizeDraft } from '@/composables/finalizeViewHelpers'
import type { SavedNormalizedRouteSegment } from '@/api'

export function useFinalizeDrafts(projectId: Ref<number | null>) {
  const drafts = ref<Record<string, FinalizeDraft>>({})
  let skippedDrafts: Record<string, FinalizeDraft> = {}
  const inlineEditingSegmentId = ref<string | null>(null)
  const inlineEditingText = ref('')
  const inlineTextareaRef = ref<HTMLTextAreaElement | null>(null)

  const draftStorageKey = computed(() => `processmind_finalize_drafts_v4_${projectId.value || 'unknown'}`)

  function readDrafts(segments: SavedNormalizedRouteSegment[] = []) {
    if (typeof window === 'undefined') return 0
    try {
      const raw = window.localStorage.getItem(draftStorageKey.value)
      const parsed = raw ? JSON.parse(raw) : {}
      const currentSegments = new Map(segments.map(segment => [segment.id, segment]))
      const restored: Record<string, FinalizeDraft> = {}
      skippedDrafts = {}
      for (const [id, draft] of Object.entries(parsed as Record<string, FinalizeDraft>)) {
        if (!draft || typeof draft.conditionText !== 'string'
          || !Array.isArray(draft.factorNames) || !Array.isArray(draft.userAnswerLabels)
          || !Array.isArray(draft.userAnswerContextLabels)) continue
        const segment = currentSegments.get(id)
        if (segment && finalizeDraftMatchesReview(draft, segment.rule_review?.condition_review)) {
          restored[id] = draft
        } else {
          // Retain the recovery copy on disk, but never apply it to a source that
          // another window has saved or confirmed since it was created.
          skippedDrafts[id] = draft
        }
      }
      drafts.value = restored
      return Object.keys(skippedDrafts).length
    } catch (err) {
      console.warn('读取第四步草稿失败', err)
      drafts.value = {}
      skippedDrafts = {}
      return 0
    }
  }

  function persistDrafts() {
    if (typeof window === 'undefined') return
    window.localStorage.setItem(draftStorageKey.value, JSON.stringify({ ...skippedDrafts, ...drafts.value }))
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
    const nextConditionText = inlineEditingText.value.trim()
    if (nextConditionText === String(item.conditionText || '').trim()) {
      cancelInlineEdit()
      return false
    }
    const existingDraft = drafts.value[segmentId] || {
      factorNames: [...item.factorNames],
      userAnswerLabels: [...item.userAnswerLabels],
      userAnswerContextLabels: [...item.userAnswerContextLabels],
      baseReview: finalizeDraftReviewBaseline(item.conditionReview),
    }

    drafts.value = {
      ...drafts.value,
      [segmentId]: {
        ...existingDraft,
        conditionText: nextConditionText,
      },
    }

    cancelInlineEdit()
    return true
  }

  function setConditionTextDraft(item: any, conditionText: string) {
    const existingDraft = drafts.value[item.segment.id] || {
      factorNames: [...item.factorNames],
      userAnswerLabels: [...item.userAnswerLabels],
      userAnswerContextLabels: [...item.userAnswerContextLabels],
      baseReview: finalizeDraftReviewBaseline(item.conditionReview),
    }
    drafts.value = {
      ...drafts.value,
      [item.segment.id]: {
        ...existingDraft,
        conditionText: conditionText.trim(),
      },
    }
  }

  function resetInlineEdit(item: any) {
    const segmentId = item.segment.id
    clearPersistedDraft(segmentId)

    if (inlineEditingSegmentId.value === segmentId) {
      cancelInlineEdit()
    }
  }

  function clearPersistedDraft(segmentId: string) {
    delete skippedDrafts[segmentId]
    const next = { ...drafts.value }
    delete next[segmentId]
    drafts.value = next
  }

  function clearAllDrafts() {
    skippedDrafts = {}
    drafts.value = {}
    cancelInlineEdit()
    if (typeof window !== 'undefined') {
      window.localStorage.removeItem(draftStorageKey.value)
    }
  }

  return {
    cancelInlineEdit,
    clearAllDrafts,
    clearPersistedDraft,
    drafts,
    inlineEditingSegmentId,
    inlineEditingText,
    persistDrafts,
    readDrafts,
    resetInlineEdit,
    saveInlineEdit,
    setConditionTextDraft,
    setInlineTextareaRef,
    startInlineEdit,
  }
}
