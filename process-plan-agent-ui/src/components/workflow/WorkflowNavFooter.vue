<template>
  <div class="workflow-nav-footer" :class="{ 'workflow-nav-footer-inline': inline }" role="navigation" aria-label="流程导航">
    <div class="workflow-nav-inner">
      <div ref="noticeRoot" class="workflow-nav-summary">
        <template v-if="orderedNotices.length">
          <span class="workflow-notice-summary" :class="`is-${orderedNotices[0]!.level || 'info'}`" role="status" aria-live="polite">
            <span class="workflow-notice-dot" aria-hidden="true" />
            <span class="workflow-notice-text">{{ orderedNotices[0]!.summary }}</span>
            <span v-if="orderedNotices.length > 1" class="workflow-notice-count">另 {{ orderedNotices.length - 1 }} 条</span>
          </span>
          <button ref="detailTrigger" type="button" class="workflow-notice-link" :aria-expanded="detailsOpen" @click="detailsOpen = !detailsOpen">查看详情</button>
          <section v-if="detailsOpen" class="workflow-notice-popover" :style="detailStyle" aria-label="消息详情" @keydown.esc.stop="closeDetails(true)">
            <header><strong>消息详情</strong><button type="button" class="workflow-notice-link" aria-label="关闭消息详情" @click="closeDetails(true)">关闭</button></header>
            <article v-for="notice in orderedNotices" :key="notice.id" :class="`is-${notice.level || 'info'}`">
              <strong>{{ notice.summary }}</strong>
              <p v-if="notice.detail">{{ notice.detail }}</p>
              <div v-if="notice.actions?.length" class="workflow-notice-actions">
                <button v-for="action in notice.actions" :key="action.label" type="button" class="workflow-nav-btn workflow-nav-btn-prev" :disabled="action.disabled" @click="action.run()">{{ action.label }}</button>
              </div>
            </article>
          </section>
        </template>
        <span v-else class="workflow-nav-default-summary"><slot name="summary">{{ summary }}</slot></span>
      </div>
      <div class="workflow-nav-actions">
        <slot name="actions">
        <button
          v-if="showPrevious"
          class="workflow-nav-btn workflow-nav-btn-prev"
          type="button"
          :disabled="previousDisabled"
          :title="previousLabel"
          @click="$emit('previous')"
        >
          {{ previousLabel }}
        </button>
        <button
          v-if="showNext"
          class="workflow-nav-btn workflow-nav-btn-next"
          type="button"
          :disabled="nextDisabled"
          :title="nextLabel"
          @click="$emit('next')"
        >
          {{ nextLabel }}
        </button>
        </slot>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import type { WorkflowNotice } from './workflowNotice'

const props = withDefaults(defineProps<{
  summary?: string
  notices?: WorkflowNotice[]
  inline?: boolean
  previousLabel?: string
  nextLabel: string
  showPrevious?: boolean
  showNext?: boolean
  previousDisabled?: boolean
  nextDisabled?: boolean
}>(), {
  summary: '',
  notices: () => [],
  inline: false,
  previousLabel: '← 上一步',
  showPrevious: true,
  showNext: true,
  previousDisabled: false,
  nextDisabled: false,
})

const detailsOpen = ref(false)
const noticeRoot = ref<HTMLElement | null>(null)
const detailTrigger = ref<HTMLButtonElement | null>(null)
const detailStyle = ref<Record<string, string>>({})
const severity = { error: 0, warning: 1, progress: 2, success: 3, info: 4 }
const orderedNotices = computed(() => props.notices.filter(notice => notice.summary.trim()).slice().sort((a, b) => severity[a.level || 'info'] - severity[b.level || 'info']))
watch(() => orderedNotices.value.length, length => { if (!length) detailsOpen.value = false })
watch([detailsOpen, orderedNotices, () => props.inline], updateDetailBounds, { flush: 'post' })
function updateDetailBounds() {
  const root = noticeRoot.value
  if (!detailsOpen.value || !props.inline || typeof window === 'undefined' || !root?.getBoundingClientRect) {
    if (Object.keys(detailStyle.value).length) detailStyle.value = {}
    return
  }
  const anchor = root.getBoundingClientRect()
  let top = 0, bottom = window.innerHeight, left = 0, right = window.innerWidth
  // Inline footers remain inside their scroll/clipping ancestors. Intersect
  // their client boxes rather than allowing the popup to escape tree overflow.
  for (let parent = root.parentElement; parent; parent = parent.parentElement) {
    const style = getComputedStyle(parent)
    const rect = parent.getBoundingClientRect()
    if (/^(auto|scroll|hidden|clip|overlay)$/.test(style.overflowY)) {
      top = Math.max(top, rect.top + parent.clientTop)
      bottom = Math.min(bottom, rect.top + parent.clientTop + parent.clientHeight)
    }
    if (/^(auto|scroll|hidden|clip|overlay)$/.test(style.overflowX)) {
      left = Math.max(left, rect.left + parent.clientLeft)
      right = Math.min(right, rect.left + parent.clientLeft + parent.clientWidth)
    }
  }
  const popupBottom = Math.min(anchor.top - 16, bottom - 8)
  const width = Math.max(0, Math.min(520, window.innerWidth - 40, right - left - 16))
  const popupLeft = Math.max(left + 8, Math.min(anchor.left, right - width - 8))
  detailStyle.value = {
    maxHeight: `${Math.max(0, Math.min(420, popupBottom - top - 8))}px`,
    width: `${width}px`,
    left: `${popupLeft - anchor.left}px`,
    bottom: `calc(100% + ${anchor.top - popupBottom}px)`,
  }
}
function closeDetails(focus = false) {
  detailsOpen.value = false
  if (focus) detailTrigger.value?.focus?.()
}
function dismissOutside(event: Event) {
  if (detailsOpen.value && !noticeRoot.value?.contains(event.target as Node)) closeDetails()
}
function escapeDetails(event: KeyboardEvent) { if (event.key === 'Escape' && detailsOpen.value) closeDetails(true) }
onMounted(() => {
  if (typeof document === 'undefined') return
  document.addEventListener('pointerdown', dismissOutside)
  document.addEventListener('keydown', escapeDetails)
  document.addEventListener('scroll', updateDetailBounds, true)
  if (typeof window !== 'undefined') window.addEventListener('resize', updateDetailBounds)
})
onBeforeUnmount(() => {
  if (typeof document === 'undefined') return
  document.removeEventListener('pointerdown', dismissOutside)
  document.removeEventListener('keydown', escapeDetails)
  document.removeEventListener('scroll', updateDetailBounds, true)
  if (typeof window !== 'undefined') window.removeEventListener('resize', updateDetailBounds)
})

defineEmits<{
  previous: []
  next: []
}>()
</script>

<style scoped>
.workflow-nav-footer {
  position: fixed;
  left: 0;
  right: 0;
  bottom: 0;
  z-index: 45;
  border-top: 1px solid var(--pm-border);
  background: var(--pm-surface);
  pointer-events: none;
}

.workflow-nav-inner {
  /* 与 App.vue .main-area 同一最大宽度，并允许步骤页按右侧内容模块微调按钮组位置 */
  max-width: var(--page-max-width, 1280px);
  width: 100%;
  min-height: 48px;
  padding-top: 7px;
  padding-bottom: 7px;
  margin: 0 auto;
  padding-right: calc(var(--page-padding-x, 24px) + var(--workflow-nav-right-inset, 0px));
  padding-left: var(--page-padding-x, 24px);
  box-sizing: border-box;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  pointer-events: auto;
}

.workflow-nav-summary {
  position: relative;
  display: flex;
  align-items: center;
  gap: 8px;
  flex: 1;
  min-width: 0;
  color: var(--text-secondary, var(--pm-text-secondary));
  font-size: 12px;
  line-height: 1.5;
}

.workflow-nav-default-summary, .workflow-notice-text { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.workflow-notice-summary { display: flex; align-items: center; gap: 7px; min-width: 0; }
.workflow-notice-dot { width: 6px; height: 6px; border-radius: 50%; background: currentColor; flex: 0 0 auto; }
.workflow-notice-count, .workflow-notice-link { flex-shrink: 0; white-space: nowrap; }
.is-error { color: var(--pm-danger); }
.is-warning { color: var(--pm-warning); }
.is-success { color: var(--pm-success); }
.is-progress { color: var(--pm-primary); }
.workflow-notice-link { border: 0; padding: 3px 0; background: transparent; color: var(--pm-primary); font: inherit; cursor: pointer; }
.workflow-notice-popover { position: absolute; bottom: calc(100% + 16px); left: 0; width: min(520px, calc(100vw - 40px)); max-height: min(420px, calc(100vh - 140px)); overflow: auto; box-sizing: border-box; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-card); padding: 12px 16px; background: var(--pm-surface); box-shadow: 0 8px 30px rgba(15,23,42,.14); color: var(--pm-text); line-height: 1.6; }
.workflow-notice-popover header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.workflow-notice-popover article { padding-top: 10px; margin-top: 8px; border-top: 1px solid var(--pm-border); overflow-wrap: anywhere; }
.workflow-notice-popover article strong { font-weight: 600; }
.workflow-notice-popover p { margin: 5px 0; white-space: pre-wrap; color: var(--pm-text-secondary); }
.workflow-notice-actions { display: flex; flex-wrap: wrap; gap: 8px; margin-top: 8px; }
.workflow-nav-footer-inline { position: relative; flex: 0 0 auto; z-index: 40; border: 1px solid var(--pm-border); border-radius: var(--pm-radius-card); }
.workflow-nav-footer-inline .workflow-nav-inner { padding-left: 12px; padding-right: 12px; }

.workflow-nav-actions {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  flex-shrink: 0;
}

:deep(.workflow-nav-btn) {
  min-width: 128px;
  min-height: var(--pm-control-height);
  padding: 5px 12px;
  border-radius: var(--pm-radius-control);
  border: 1px solid var(--pm-border-strong);
  font: inherit;
  font-size: 13px;
  font-weight: 500;
  line-height: 20px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
  transition: background 0.16s ease, border-color 0.16s ease, color 0.16s ease, box-shadow 0.16s ease, transform 0.16s ease;
}

:deep(.workflow-nav-btn-prev) {
  background: var(--pm-surface);
  color: var(--pm-text-secondary);
}

:deep(.workflow-nav-btn-prev:hover:not(:disabled)) {
  background: var(--pm-primary-soft);
  border-color: var(--pm-primary-border);
  color: var(--pm-primary-hover);
}

:deep(.workflow-nav-btn-next) {
  border-color: var(--pm-primary);
  background: var(--pm-primary);
  color: var(--pm-surface);
}

:deep(.workflow-nav-btn-next:hover:not(:disabled)) {
  background: var(--pm-primary-hover);
  border-color: var(--pm-primary-hover);
  box-shadow: none;
}

:deep(.workflow-nav-btn:disabled) {
  cursor: not-allowed;
  opacity: 0.5;
  box-shadow: none;
  transform: none;
}

:deep(.workflow-nav-btn:focus-visible) { outline: 2px solid var(--pm-primary); outline-offset: 2px; }

@media (max-width: 600px) {
  .workflow-nav-footer {
    padding: 8px var(--page-padding-x, 16px);
  }

  .workflow-nav-inner {
    align-items: stretch;
    flex-direction: column;
    height: auto;
    gap: 8px;
    padding: 0;
    --workflow-nav-right-inset: 0px;
  }

  .workflow-nav-actions {
    display: grid;
    grid-auto-flow: column;
    grid-auto-columns: minmax(0, 1fr);
    width: 100%;
  }

  .workflow-notice-link { padding-top: 0; padding-bottom: 0; }

  :deep(.workflow-nav-btn) {
    min-width: 0;
    width: 100%;
  }

}

@media (prefers-reduced-motion: reduce) {
  :deep(.workflow-nav-btn) { transition: none; }
}
</style>
