<template>
  <article
    :id="`finalize-card-${item.segment.id}`"
    class="preview-card card"
    :class="{ 'preview-card-active': active }"
  >
    <div class="preview-card-header">
      <div class="preview-card-title-group">
        <div class="preview-card-name-stack">
          <h2>{{ displayName }}</h2>
          <div v-if="metaLabel" class="preview-card-meta">{{ metaLabel }}</div>
        </div>
      </div>
      <div class="preview-card-actions">
        <span v-if="item.edited" class="edited-badge">{{ editedBadge }}</span>
        <button
          v-if="item.edited && !inlineEditing"
          class="ghost-btn reset-inline-btn"
          @click="$emit('reset', item)"
        >
          恢复默认
        </button>
        <button
          v-if="!inlineEditing"
          class="preview-edit-btn"
          @click="$emit('start-edit', item)"
        >
          <svg class="edit-btn-svg" width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <path d="M12 20h9" />
            <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
          </svg>
          <span>{{ editLabel }}</span>
        </button>
      </div>
    </div>

    <div class="preview-card-body">
      <div class="preview-row">
        <div class="preview-row-label">
          <span class="condition-badge-label">{{ conditionLabel }}</span>
        </div>
        <div class="preview-row-content preview-condition">
          <div v-if="inlineEditing" class="inline-edit-box">
            <textarea
              :value="inlineEditingText"
              class="inline-edit-textarea"
              rows="3"
              :ref="handleTextareaRef"
              placeholder="请输入工序规则，例如：当外圆尺寸精度要求达到IT8时，纳入“磨外圆”工序。"
              @input="$emit('update:inlineEditingText', ($event.target as HTMLTextAreaElement).value)"
            ></textarea>
            <div class="inline-edit-actions">
              <button class="inline-btn inline-btn-cancel" @click="$emit('cancel')">取消</button>
              <button class="inline-btn inline-btn-save" @click="$emit('save', item)">保存</button>
            </div>
          </div>
          <div v-else>{{ item.conditionText }}</div>
        </div>
      </div>
    </div>
  </article>
</template>

<script setup lang="ts">
import type { FinalizeCard } from '@/composables/finalizeViewHelpers'
import type { ComponentPublicInstance } from 'vue'

const props = defineProps<{
  item: FinalizeCard
  active: boolean
  displayName: string
  metaLabel: string
  inlineEditing: boolean
  inlineEditingText: string
  editedBadge: string
  editLabel: string
  conditionLabel: string
  setInlineTextareaRef: (el: Element | null) => void
}>()

defineEmits<{
  reset: [item: FinalizeCard]
  'start-edit': [item: FinalizeCard]
  cancel: []
  save: [item: FinalizeCard]
  'update:inlineEditingText': [value: string]
}>()

function handleTextareaRef(el: Element | ComponentPublicInstance | null) {
  props.setInlineTextareaRef(el instanceof Element ? el : null)
}
</script>

<style scoped>
.inline-edit-box {
  display: flex;
  flex-direction: column;
  gap: 8px;
  width: 100%;
  margin-top: 4px;
}

.inline-edit-textarea {
  width: 100%;
  min-height: 84px;
  padding: 10px 12px;
  border: 1px solid #c7d2fe;
  border-radius: 8px;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  resize: vertical;
  outline: none;
  background: #ffffff;
  box-shadow: inset 0 1px 2px rgba(15, 23, 42, 0.04);
}

.inline-edit-textarea:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 3px rgba(99, 102, 241, 0.12);
}

.inline-edit-actions {
  display: flex;
  justify-content: flex-end;
  gap: 8px;
}

.inline-btn {
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.15s ease;
}

.inline-btn-cancel {
  background: #ffffff;
  color: #64748b;
}

.inline-btn-cancel:hover {
  background: #f8fafc;
  color: #334155;
}

.inline-btn-save {
  background: #4f46e5;
  border-color: #4f46e5;
  color: #ffffff;
}

.inline-btn-save:hover {
  background: #4338ca;
  border-color: #4338ca;
}

.reset-inline-btn {
  font-size: 12px;
  color: #64748b;
  margin-right: 8px;
  padding: 4px 8px;
  border-radius: 4px;
  transition: all 0.15s ease;
}

.reset-inline-btn:hover {
  color: #ef4444;
  background: rgba(239, 68, 68, 0.05);
}

.preview-card {
  padding: 12px 16px;
  border-radius: 8px;
  background: #ffffff;
  border: 1px solid #e8ecf2;
  margin-bottom: 8px;
  transition: all 0.2s ease;
}

.preview-card:last-child {
  margin-bottom: 0;
}

.preview-card-active {
  position: relative;
  border-color: #c7d2fe;
  background: linear-gradient(135deg, rgba(99, 102, 241, 0.03), #f8fafc);
}

.preview-card-active::before {
  content: '';
  position: absolute;
  left: 0;
  top: 0;
  bottom: 0;
  width: 3px;
  background: #6366f1;
  border-radius: 4px 0 0 4px;
  opacity: 0.8;
}

.preview-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 7px;
}

.preview-card-title-group {
  display: flex;
  align-items: flex-start;
  gap: 8px;
}

.preview-card-name-stack {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
}

.preview-card h2 {
  margin: 0;
  font-size: 14px;
  font-weight: 700;
  color: #1e293b;
  letter-spacing: -0.01em;
  display: flex;
  align-items: center;
  gap: 8px;
}

.preview-card h2::before {
  content: "";
  display: inline-block;
  width: 3px;
  height: 13px;
  background: #6366f1;
  border-radius: 2px;
  opacity: 0.8;
  flex-shrink: 0;
}

.preview-card-meta {
  font-size: 12px;
  line-height: 1.45;
  color: #7c8aa5;
}

.preview-card-actions {
  display: flex;
  align-items: center;
  gap: 8px;
}

.edited-badge {
  font-size: 12px;
  font-weight: 600;
  color: #92400e;
  background: #fff7ed;
  border: 1px solid #fdba74;
  border-radius: 4px;
  padding: 2px 6px;
}

.ghost-btn {
  border: none;
  background: transparent;
  color: #64748b;
  font-size: 13px;
  font-weight: 500;
  cursor: pointer;
  padding: 0 4px;
}

.ghost-btn:hover {
  color: #4f46e5;
}

.preview-edit-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  background: #ffffff;
  border: 1px solid #c7d2fe;
  color: #4f46e5;
  padding: 2px 10px;
  border-radius: 6px;
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1);
  height: 24px;
  gap: 4px;
}

.preview-edit-btn:hover {
  background: #eef2ff;
  border-color: #a5b4fc;
}

.preview-edit-btn:active {
  transform: scale(0.97);
}

.preview-row {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  margin-bottom: 6px;
}

.preview-row-label {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  line-height: normal;
  padding-top: 2px;
}

.condition-badge-label {
  background: #f1f5f9;
  color: #475569;
  border-radius: 4px;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  white-space: nowrap;
  border: 1px solid #e2e8f0;
}

.preview-row-content {
  flex: 1;
  min-width: 0;
}

.preview-condition {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: #334155;
  font-weight: 400;
}

@media (max-width: 1080px) {
  .preview-card-actions {
    justify-content: flex-start;
    margin-top: 12px;
  }

  .preview-condition {
    font-size: 16px;
  }
}
</style>
