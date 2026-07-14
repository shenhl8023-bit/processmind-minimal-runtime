<template>
  <div class="card ref-card">
    <div class="card-title">
      <svg class="header-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
        <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
      </svg>
      {{ title }}
      <span class="tag tag-info" style="margin-left: auto">辅助输入</span>
    </div>
    <p class="card-desc">{{ desc }}</p>

    <div class="ref-actions" v-if="!showEditor">
      <button class="btn btn-outline btn-sm btn-with-svg" @click="showEditor = true">
        <svg class="btn-icon-svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M12 20h9" />
          <path d="M16.5 3.5a2.121 2.121 0 0 1 3 3L7 19l-4 1 1-4L16.5 3.5z" />
        </svg>
        <span>在线编写</span>
      </button>
      <label
        for="ref-upload-input"
        :class="['btn', 'btn-primary', 'btn-sm', 'ref-upload-trigger', 'btn-with-svg', { disabled: uploading }]"
        :aria-disabled="uploading ? 'true' : 'false'"
      >
        <span v-if="uploading" class="spinner-sm" style="margin-right: 4px; border-width: 1px; width: 12px; height: 12px;"></span>
        <svg v-else class="btn-icon-svg" width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
          <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
          <polyline points="17 8 12 3 7 8" />
          <line x1="12" y1="3" x2="12" y2="15" />
        </svg>
        <span>上传资料</span>
      </label>
      <input id="ref-upload-input" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.json" class="visually-hidden-file-input" @change="onFileSelected" />
    </div>

    <div class="editor-area" v-if="showEditor">
      <input v-model="newRef.title" placeholder="参考资料标题（可选，默认：补充要求）" class="editor-input" />
      <textarea v-model="newRef.content" placeholder="输入你想补充的具体工艺要求、注意事项或老工艺师的经验规则..." class="editor-textarea" rows="6"></textarea>
      <div class="editor-footer">
        <button class="btn btn-primary btn-sm" @click="saveWrittenRef" :disabled="!newRef.content">保存内容</button>
        <button class="btn btn-outline btn-sm" @click="showEditor = false">取消</button>
      </div>
    </div>

    <div class="file-list" v-if="files.length > 0">
      <div class="file-item" v-for="file in files" :key="file.id">
        <div class="file-icon-bg" :class="'icon-type-' + (file.ref_type === 'written' ? 'written' : getFileType(file.title))">
          <svg v-if="file.ref_type === 'written'" class="file-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
            <path d="M18.5 2.5a2.121 2.121 0 1 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
          </svg>
          <svg v-else class="file-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
            <polyline points="14 2 14 8 20 8"></polyline>
            <line x1="16" y1="13" x2="8" y2="13"></line>
            <line x1="16" y1="17" x2="8" y2="17"></line>
            <polyline points="10 9 9 9 8 9"></polyline>
          </svg>
        </div>
        <div class="file-info">
          <div class="file-name">{{ file.title }}</div>
          <div class="file-meta">{{ formatTime(file.created_at) }}</div>
        </div>
        <span class="tag tag-accent">{{ file.ref_type === 'written' ? '手工编写' : '上传文件' }}</span>
        <button class="btn-icon-old danger" @click="emit('remove-file', file.id)">
          <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

defineProps<{
  title: string
  desc: string
  files: any[]
  uploading: boolean
  formatTime: (value: string) => string
  getFileType: (name: string) => string
}>()

const emit = defineEmits<{
  (event: 'upload-files', files: File[]): void
  (event: 'save-written-ref', payload: { title: string; content: string }): void
  (event: 'remove-file', id: number): void
}>()

const showEditor = ref(false)
const newRef = ref({ title: '', content: '' })

const onFileSelected = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    emit('upload-files', Array.from(input.files))
    input.value = ''
  }
}

const saveWrittenRef = () => {
  const content = newRef.value.content.trim()
  const title = newRef.value.title.trim() || '补充要求'
  if (!content) return
  emit('save-written-ref', { title, content })
  newRef.value = { title: '', content: '' }
  showEditor.value = false
}
</script>

<style scoped>
.ref-card {
  padding: 12px 14px;
  height: 100%;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}
.card-title {
  display: flex;
  align-items: center;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 6px;
  gap: 4px;
}
.card-desc {
  font-size: 12px;
  color: var(--text-muted);
  margin-bottom: 8px;
  flex-shrink: 0;
}
.header-icon-svg {
  color: var(--accent);
  margin-right: 6px;
  flex-shrink: 0;
  vertical-align: middle;
}
.ref-actions {
  display: flex;
  gap: 6px;
  margin-bottom: 8px;
  flex-shrink: 0;
}
.ref-upload-trigger.disabled {
  opacity: 0.65;
  cursor: not-allowed;
  pointer-events: none;
}
.visually-hidden-file-input {
  position: absolute;
  width: 1px;
  height: 1px;
  padding: 0;
  margin: -1px;
  border: 0;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}
.editor-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 0;
  padding: 10px;
  background: #fafafa;
  border: 1px solid var(--border-light);
  border-radius: var(--radius-sm);
  overflow: hidden;
}
.editor-input {
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  font-size: 12px;
  outline: none;
  width: 100%;
  transition: border-color 0.2s;
  flex-shrink: 0;
}
.editor-input:focus {
  border-color: var(--accent);
  background: #fff;
}
.editor-textarea {
  flex: 1;
  padding: 6px 10px;
  border: 1px solid #d1d5db;
  border-radius: 5px;
  font-size: 12px;
  resize: none;
  outline: none;
  font-family: inherit;
  width: 100%;
  line-height: 1.4;
  transition: border-color 0.2s;
}
.editor-textarea:focus {
  border-color: var(--accent);
  background: #fff;
}
.editor-footer {
  display: flex;
  gap: 6px;
  justify-content: flex-end;
  margin-top: 0;
  flex-shrink: 0;
}
.file-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding-right: 2px;
}
.file-list::-webkit-scrollbar {
  width: 4px;
}
.file-list::-webkit-scrollbar-track {
  background: transparent;
}
.file-list::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}
.file-list::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
.file-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 10px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  transition: all 0.2s ease;
  flex-shrink: 0;
}
.file-item:hover {
  background: #ffffff;
  border-color: #cbd5e1;
  box-shadow: var(--shadow-sm);
  transform: translateY(-1px);
}
.file-icon-bg {
  width: 26px;
  height: 26px;
  border-radius: 4px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}
.file-svg {
  display: block;
}
.icon-type-pdf { background: #fff5f5; color: #fa5252; border: 1px solid #ffe3e3; }
.icon-type-word { background: #e7f5ff; color: #228be6; border: 1px solid #d0ebff; }
.icon-type-excel { background: #ebfbee; color: #40c057; border: 1px solid #d3f9d8; }
.icon-type-json { background: #f3f0ff; color: #7950f2; border: 1px solid #e5dbff; }
.icon-type-other { background: #f8f9fa; color: #868e96; border: 1px solid #f1f3f5; }
.icon-type-written { background: #fff9db; color: #fab005; border: 1px solid #fff3bf; }
.file-info {
  flex: 1;
  min-width: 0;
}
.file-name {
  font-size: 12px;
  font-weight: 550;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-meta {
  font-size: 11px;
  color: var(--text-muted);
  margin-top: 1px;
}
.btn-icon-old {
  background: none;
  border: none;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  color: var(--text-muted);
  transition: all 0.2s;
}
.btn-icon-old:hover {
  background: #eceff4;
  color: var(--text-primary);
}
.btn-icon-old.danger:hover {
  background: #fee2e2;
  color: #b91c1c;
}
.btn-sm {
  padding: 5px 10px;
  font-size: 11.5px;
  height: auto;
  border-radius: 5px;
}
.btn-with-svg {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}
.btn-icon-svg {
  flex-shrink: 0;
}
.spinner-sm {
  width: 14px;
  height: 14px;
  border: 2px solid var(--border-light);
  border-top-color: var(--accent);
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}
@keyframes spin { to { transform: rotate(360deg); } }
</style>
