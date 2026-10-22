import type { Ref } from 'vue'

export function openFinalizePrecheckDialog(
  showDialog: Ref<boolean>,
  headerMenu?: Ref<HTMLDetailsElement | null>,
) {
  headerMenu?.value?.removeAttribute('open')
  showDialog.value = true
}
