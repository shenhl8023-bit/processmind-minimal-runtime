<template>
  <div class="card upload-card">
    <div class="card-title">
      <svg class="header-icon-svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
        <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
        <polyline points="14 2 14 8 20 8" />
        <line x1="16" y1="13" x2="8" y2="13" />
        <line x1="16" y1="17" x2="8" y2="17" />
        <polyline points="10 9 9 9 8 9" />
      </svg>
      {{ title }}
      <span class="tag tag-accent" style="margin-left: auto">主输入</span>
    </div>
    <p class="card-desc">{{ desc }}</p>

    <div
      :class="['drop-zone', { 'has-files': files.length > 0 }]"
      @click="triggerUpload"
      @dragover.prevent
      @drop.prevent="handleDrop"
    >
      <div class="drop-zone-inner" v-if="files.length === 0">
        <div class="drop-icon">
          <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
            <polyline points="17 8 12 3 7 8" />
            <line x1="12" y1="3" x2="12" y2="15" />
          </svg>
        </div>
        <div class="drop-text">点击或拖拽文件到此处上传</div>
        <div class="drop-hint">支持 .pdf, .docx, .xlsx, .json 格式</div>
      </div>

      <div class="file-list-embedded" v-else @click.stop>
        <div class="file-item-embedded" v-for="file in files" :key="file.id">
          <div class="file-icon-bg" :class="'icon-type-' + getFileType(file.original_name)">
            <svg class="file-svg" width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"></path>
              <polyline points="14 2 14 8 20 8"></polyline>
              <line x1="16" y1="13" x2="8" y2="13"></line>
              <line x1="16" y1="17" x2="8" y2="17"></line>
              <polyline points="10 9 9 9 8 9"></polyline>
            </svg>
          </div>
          <div class="file-info-embedded">
            <div class="file-name-embedded">{{ file.original_name }}</div>
            <div class="file-meta-embedded">{{ formatTime(file.created_at) }} · {{ file.uploader }}</div>
          </div>
          <span class="tag tag-success status-tag">{{ file.status === 'uploaded' ? '已就绪' : file.status }}</span>
          <button class="btn-icon-del" @click="emit('remove-file', file.id)" title="删除文件">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5">
              <line x1="18" y1="6" x2="6" y2="18"></line>
              <line x1="6" y1="6" x2="18" y2="18"></line>
            </svg>
          </button>
        </div>

        <div class="add-more-zone" @click="triggerUpload">
          <div class="add-more-icon">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
          </div>
          <span>继续添加文件</span>
        </div>
      </div>

      <input ref="fileInput" type="file" multiple accept=".pdf,.doc,.docx,.xls,.xlsx,.json" style="display:none" @change="onFileSelected" />
    </div>

    <div v-if="uploading" class="upload-progress">
      <div class="spinner-sm"></div> 正在上传...
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
  (event: 'remove-file', id: number): void
}>()

const fileInput = ref<HTMLInputElement>()

const triggerUpload = () => fileInput.value?.click()

const onFileSelected = (event: Event) => {
  const input = event.target as HTMLInputElement
  if (input.files && input.files.length > 0) {
    emit('upload-files', Array.from(input.files))
    input.value = ''
  }
}

const handleDrop = (event: DragEvent) => {
  if (event.dataTransfer?.files && event.dataTransfer.files.length > 0) {
    emit('upload-files', Array.from(event.dataTransfer.files))
  }
}
</script>

<style scoped>
.upload-card {
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
.drop-zone {
  flex: 1;
  border: 1.5px dashed var(--border-light);
  border-radius: var(--radius-sm);
  transition: var(--transition);
  margin-bottom: 0;
  display: flex;
  flex-direction: column;
  background: #fafafa;
  overflow: hidden;
  min-height: 0;
}
.drop-zone:not(.has-files) {
  cursor: pointer;
  padding: 16px;
  text-align: center;
  align-items: center;
  justify-content: center;
}
.drop-zone:not(.has-files):hover {
  border-color: var(--accent);
  background: var(--accent-light);
}
.drop-zone.has-files {
  border: 1px solid var(--border-light);
  background: #fbfbfc;
  padding: 8px;
  justify-content: flex-start;
}
.drop-zone-inner {
  pointer-events: none;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.drop-icon {
  margin-bottom: 6px;
  color: var(--text-muted);
}
.drop-text {
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  margin-bottom: 2px;
}
.drop-hint {
  font-size: 11px;
  color: var(--text-muted);
}
.file-list-embedded {
  flex: 1;
  overflow-y: auto;
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
  width: 100%;
  align-content: start;
  padding-right: 4px;
}
.file-list-embedded::-webkit-scrollbar {
  width: 4px;
}
.file-list-embedded::-webkit-scrollbar-track {
  background: transparent;
}
.file-list-embedded::-webkit-scrollbar-thumb {
  background: #cbd5e1;
  border-radius: 2px;
}
.file-list-embedded::-webkit-scrollbar-thumb:hover {
  background: #94a3b8;
}
.file-item-embedded {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 8px;
  background: #f8fafc;
  border: 1px solid #e2e8f0;
  border-radius: 6px;
  transition: all 0.2s ease;
  cursor: default;
}
.file-item-embedded:hover {
  border-color: #cbd5e1;
  background: #ffffff;
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
.file-info-embedded {
  flex: 1;
  min-width: 0;
}
.file-name-embedded {
  font-size: 12px;
  font-weight: 600;
  color: var(--text-primary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.file-meta-embedded { display: none; }
.status-tag { display: none; }
.btn-icon-del {
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: var(--text-muted);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  transition: all 0.2s;
  margin-left: auto;
}
.btn-icon-del:hover {
  background: #fee2e2;
  color: #dc2626;
}
.add-more-zone {
  padding: 6px;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 4px;
  font-size: 12px;
  font-weight: 500;
  color: var(--accent);
  cursor: pointer;
  border-radius: var(--radius-sm);
  transition: var(--transition);
  border: 1px dashed transparent;
  min-height: 38px;
}
.add-more-zone:hover {
  background: var(--accent-light);
  border-color: var(--accent);
}
.add-more-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--accent);
}
.upload-progress {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 8px;
  font-size: 12px;
  color: var(--accent);
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
