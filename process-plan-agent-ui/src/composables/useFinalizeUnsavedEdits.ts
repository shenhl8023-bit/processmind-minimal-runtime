import { computed, ref, type ComputedRef, type Ref } from 'vue'
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'

export function useFinalizeUnsavedEdits(
  cards: ComputedRef<FinalizeCard[]>,
  inlineEditingSegmentId: Ref<string | null>,
  inlineEditingText: Ref<string>,
) {
  const dirtyRuleIds = ref(new Set<string>())
  const unsavedCards = computed(() => cards.value.filter(card => (
    dirtyRuleIds.value.has(card.segment.id)
    || (inlineEditingSegmentId.value === card.segment.id
      && inlineEditingText.value.trim() !== card.conditionText.trim())
  )))
  const hasUnsavedEdits = computed(() => unsavedCards.value.length > 0)

  function setRuleEditState(segmentId: string, dirty: boolean) {
    const next = new Set(dirtyRuleIds.value)
    if (dirty) next.add(segmentId)
    else next.delete(segmentId)
    dirtyRuleIds.value = next
  }

  function clearRuleEditStates() {
    dirtyRuleIds.value = new Set()
  }

  return { unsavedCards, hasUnsavedEdits, setRuleEditState, clearRuleEditStates }
}
