import { computed, ref } from 'vue'
import { describe, expect, it } from 'vitest'
import { useFinalizeUnsavedEdits } from './useFinalizeUnsavedEdits'

function setup() {
  const cards = ref<any[]>([
    { segment: { id: 'copper' }, conditionText: '有镀铜时安排除铜' },
    { segment: { id: 'grind' }, conditionText: '精度达到 IT8 时磨外圆' },
  ])
  const editingId = ref<string | null>(null)
  const text = ref('')
  const edits = useFinalizeUnsavedEdits(computed(() => cards.value), editingId, text)
  return { cards, editingId, text, ...edits }
}

describe('finalize unsaved edit protection', () => {
  it('tracks structured edits until saved or cancelled without changing the confirmed data', () => {
    const state = setup()
    state.setRuleEditState('copper', true)
    expect(state.unsavedCards.value.map(card => card.segment.id)).toEqual(['copper'])
    expect(state.cards.value[0].conditionText).toBe('有镀铜时安排除铜')
    state.setRuleEditState('copper', false)
    expect(state.hasUnsavedEdits.value).toBe(false)
  })

  it('counts an inline editor only when its text differs and includes it alongside structured edits', () => {
    const state = setup()
    state.editingId.value = 'grind'
    state.text.value = ' 精度达到 IT8 时磨外圆 '
    expect(state.hasUnsavedEdits.value).toBe(false)
    state.text.value = '精度达到 IT7 时磨外圆'
    state.setRuleEditState('copper', true)
    expect(state.unsavedCards.value.map(card => card.segment.id)).toEqual(['copper', 'grind'])
    state.editingId.value = null
    expect(state.unsavedCards.value.map(card => card.segment.id)).toEqual(['copper'])
  })

  it('clears previous workspace edits when a new route is deliberately loaded', () => {
    const state = setup()
    state.setRuleEditState('copper', true)
    state.clearRuleEditStates()
    expect(state.hasUnsavedEdits.value).toBe(false)
  })
})
