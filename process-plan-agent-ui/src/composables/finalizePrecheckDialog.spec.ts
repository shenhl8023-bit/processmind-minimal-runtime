import { ref } from 'vue'
import { describe, expect, it, vi } from 'vitest'
import { openFinalizePrecheckDialog } from './finalizePrecheckDialog'

describe('openFinalizePrecheckDialog', () => {
  it('closes the header menu before showing the precheck dialog', () => {
    const showDialog = ref(false)
    const removeAttribute = vi.fn()
    const headerMenu = ref({ removeAttribute } as unknown as HTMLDetailsElement | null)

    openFinalizePrecheckDialog(showDialog, headerMenu)

    expect(removeAttribute).toHaveBeenCalledWith('open')
    expect(showDialog.value).toBe(true)
  })

  it('opens when the header menu has not mounted', () => {
    const showDialog = ref(false)
    const headerMenu = ref<HTMLDetailsElement | null>(null)

    openFinalizePrecheckDialog(showDialog, headerMenu)

    expect(showDialog.value).toBe(true)
  })
})
