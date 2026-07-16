<template>
  <div class="upload-view">
    <div class="page-header">
      <h1>第一步：上传任务资料</h1>
      <p class="page-desc">先创建工艺规程规则任务，再按任务上传文件。每个任务的文档、规则和生成结果独立保存。</p>
    </div>

    <UploadProjectBoard
      :projects="visibleProjects"
      :selected-project-id="selectedProjectId"
      :creating-project="creatingProject"
      :profile-short-label="profileShortLabel"
      :format-time="formatTime"
      :project-status-text="projectStatusText"
      @create="createNewProject"
      @select="selectProject"
      @remove="removeProject"
    />

    <div v-if="selectedProjectId" class="content-grid">
      <UploadMainFileCard
        :title="currentMainTitle"
        :desc="currentMainDesc"
        :files="mainFiles"
        :uploading="uploading"
        :format-time="formatTime"
        :get-file-type="getFileType"
        @upload-files="doUpload"
        @remove-file="removeDoc"
      />

      <UploadReferenceCard
        :title="currentRefTitle"
        :desc="currentRefDesc"
        :files="refFiles"
        :uploading="uploadingRef"
        :format-time="formatTime"
        :get-file-type="getFileType"
        @upload-files="doRefUpload"
        @save-written-ref="saveRef"
        @remove-file="removeRef"
      />
    </div>

    <div v-else class="card empty-task-card">
      <div class="empty-task-icon-wrapper">
        <svg class="compass-svg" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">
          <circle cx="12" cy="12" r="10" />
          <polygon points="16.24 7.76 14.12 14.12 7.76 16.24 9.88 9.88 16.24 7.76" />
        </svg>
      </div>
      <h3>先新建工艺规程任务</h3>
      <p>请先点击上方“新建任务”，创建一个 `工艺规程规则` 任务后再上传文件。</p>
      <button class="btn btn-primary btn-with-svg" :disabled="creatingProject" @click="createNewProject">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></svg>
        <span>新建任务</span>
      </button>
    </div>

    <WorkflowNavFooter
      :summary="uploadNavSummary"
      :show-previous="false"
      next-label="进入路线归并 →"
      :next-disabled="!canEnterExtract"
      @next="goNext"
    />

    <!-- Custom Delete Confirmation Dialog -->
    <el-dialog
      v-model="deleteDialogVisible"
      title=""
      width="420px"
      :show-close="false"
      class="custom-delete-dialog"
      align-center
    >
      <div class="delete-dialog-content">
        <div class="delete-icon-wrapper">
          <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M3 6h18"/><path d="M8 6V4a2 2 0 012-2h4a2 2 0 012 2v2"/><path d="M19 6l-1 14a2 2 0 01-2 2H8a2 2 0 01-2-2L5 6"/></svg>
        </div>
        <h3 class="delete-title">确认删除任务？</h3>
        <p class="delete-desc">
          即将删除 <strong>{{ projectToDelete?.name }}</strong>。<br/>
          此操作将同步清除该任务下的所有文档与提炼结果，且<strong>无法恢复</strong>。
        </p>
      </div>
      <template #footer>
        <div class="delete-dialog-footer">
          <button class="btn btn-outline" @click="deleteDialogVisible = false" :disabled="deletingProject">取消</button>
          <button class="btn btn-danger-fill" @click="executeDeleteProject" :disabled="deletingProject">
            {{ deletingProject ? '删除中...' : '确认删除' }}
          </button>
        </div>
      </template>
    </el-dialog>

    <!-- Custom Create Task Dialog (V5 - Compact High-Density) -->
    <el-dialog
      v-model="createDialogVisible"
      width="350px"
      :show-close="false"
      class="custom-create-dialog-v5"
      align-center
    >
      <div class="v5-dialog-content">
        <button class="v5-close-btn" @click="createDialogVisible = false">✕</button>

        <div class="v5-header">
          <div class="v5-header-icon">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 19a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h5l2 3h9a2 2 0 0 1 2 2z"/>
            </svg>
          </div>
          <div class="v5-header-text">
            <h2 class="v5-title">新建分析任务</h2>
            <p class="v5-subtitle">创建一个独立的工作空间，开始您的工艺研究</p>
          </div>
        </div>

        <div class="v5-body">
          <div class="v5-field">
            <div class="v5-label-row">
              <label class="v5-label">任务名称</label>
              <span class="v5-req">*</span>
            </div>
            <input
              v-model="newProjectName"
              type="text"
              placeholder="例如：42CrMo主轴加工"
              class="v5-input"
              @keyup.enter="executeCreateProject"
              auto-focus
            />
            <p class="v5-hint">用于标识提炼与规则分析结果</p>
          </div>

          <!-- Profiles (Only if multiple) -->
          <div v-if="availableNewProjectProfiles.length > 1" class="v5-profiles">
            <label class="v5-label">逻辑包方案</label>
            <div class="v5-chip-container">
              <button
                v-for="profile in availableNewProjectProfiles"
                :key="profile.key"
                :class="['v5-chip', { active: resolvedNewProjectProfile === profile.key }]"
                @click="newProjectProfile = profile.key"
              >
                {{ profile.label }}
              </button>
            </div>
          </div>
        </div>

        <div class="v5-footer">
          <button class="v5-btn-cancel" :disabled="creatingProject" @click="createDialogVisible = false">取消</button>
          <button class="v5-btn-primary" @click="executeCreateProject" :disabled="!canCreateProject || creatingProject">
            {{ creatingProject ? '创建中...' : '确认创建' }}
          </button>
        </div>
      </div>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { computed, ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import UploadMainFileCard from '@/components/upload/UploadMainFileCard.vue'
import UploadProjectBoard from '@/components/upload/UploadProjectBoard.vue'
import UploadReferenceCard from '@/components/upload/UploadReferenceCard.vue'
import WorkflowNavFooter from '@/components/workflow/WorkflowNavFooter.vue'
import { uploadDocuments, listDocuments, deleteDocument, createReference, listReferences, uploadReferences, deleteReference, listProjects, createProject, deleteProject, listProjectProfiles, type ProjectProfile } from '@/api'
import {
  buildProjectRouteQuery,
  clearStoredCurrentProjectId,
  getStoredCurrentProjectId,
  setStoredCurrentProjectId,
} from '@/composables/useCurrentProject'
import { clearProjectQuestionTreeStorage } from '@/composables/analysisQuestionTreeState'
import {
  formatRequestError,
  formatTime,
  getFileType,
  isSystemSeedProject,
  profileShortLabel as resolveProfileShortLabel,
  projectStatusText,
  sortProjects,
} from '@/utils/uploadViewHelpers'

defineOptions({
  name: 'UploadView',
})

const router = useRouter()
const deleteDialogVisible = ref(false)
const projectToDelete = ref<any>(null)
const createDialogVisible = ref(false)
const newProjectName = ref('')
const newProjectProfile = ref('')
const creatingProject = ref(false)
const createProjectInFlight = ref(false)
const lastCreateProjectKey = ref('')
const lastCreateProjectAt = ref(0)
const uploading = ref(false)
const uploadingRef = ref(false)
const deletingProject = ref(false)

const projects = ref<any[]>([])
const profileCatalog = ref<ProjectProfile[]>([])
const selectedProjectId = ref('')
const mainFiles = ref<any[]>([])
const refFiles = ref<any[]>([])
const visibleProjects = computed(() =>
  sortProjects(projects.value)
    .filter((project) => !isSystemSeedProject(project) && project.mode === 'route_rules')
)

onMounted(async () => {
  await Promise.all([
    loadProfileCatalog(),
    ensureProjectReady(),
  ])
  await loadData()
})

async function loadData() {
  if (!selectedProjectId.value) {
    mainFiles.value = []
    refFiles.value = []
  }

  try {
    projects.value = sortProjects(await listProjects())
  } catch (e) {
    console.error('刷新任务状态失败', e)
  }

  if (!selectedProjectId.value) return

  const current = projects.value.find(project => String(project.id) === selectedProjectId.value)
  if (!current) {
    selectedProjectId.value = ''
    clearStoredCurrentProjectId()
    mainFiles.value = []
    refFiles.value = []
    return
  }

  try {
    mainFiles.value = await listDocuments(Number(selectedProjectId.value))
  } catch (e) {
    console.error('加载工艺规程文件失败', e)
    mainFiles.value = []
  }

  try {
    refFiles.value = await listReferences(Number(selectedProjectId.value))
  } catch (e) {
    console.error('加载参考资料失败', e)
    refFiles.value = []
  }
}

async function ensureProjectReady() {
  projects.value = sortProjects(await listProjects())
  const savedId = getStoredCurrentProjectId()
  const current = projects.value.find((project) =>
    String(project.id) === savedId
    && !isSystemSeedProject(project)
    && project.mode === 'route_rules',
  )
  if (current) {
    selectedProjectId.value = String(current.id)
    setStoredCurrentProjectId(selectedProjectId.value)
    return
  }
  selectedProjectId.value = ''
  clearStoredCurrentProjectId()
}

async function loadProfileCatalog() {
  try {
    profileCatalog.value = await listProjectProfiles('route_rules')
  } catch (e) {
    console.error('加载方案逻辑包失败', e)
    profileCatalog.value = []
  }
}

function createNewProject() {
  newProjectName.value = ''
  newProjectProfile.value = ''
  createDialogVisible.value = true
}

async function executeCreateProject() {
  if (createProjectInFlight.value || creatingProject.value) return
  const name = newProjectName.value.trim()
  if (!name) return
  const profile = resolvedNewProjectProfile.value || undefined
  const createKey = `${name}::${profile || ''}`
  const now = Date.now()
  if (lastCreateProjectKey.value === createKey && now - lastCreateProjectAt.value < 3000) {
    return
  }
  createProjectInFlight.value = true
  lastCreateProjectKey.value = createKey
  lastCreateProjectAt.value = now
  creatingProject.value = true
  try {
    createDialogVisible.value = false
    const project = await createProject(name, 'route_rules', profile)
    projects.value = sortProjects([
      project,
      ...projects.value.filter(item => item.id !== project.id),
    ])
    selectedProjectId.value = String(project.id)
    setStoredCurrentProjectId(selectedProjectId.value)
    mainFiles.value = []
    refFiles.value = []
    try {
      projects.value = sortProjects(await listProjects())
    } catch (refreshError) {
      console.error('创建后刷新任务列表失败，先沿用本地任务卡片', refreshError)
    }
    try {
      await loadData()
    } catch (loadError) {
      console.error('创建后加载任务详情失败，稍后重试', loadError)
    }
  } catch (e: any) {
    console.error('创建任务失败', e)
    createDialogVisible.value = true
    alert(formatRequestError(e, '创建任务失败，请检查后端服务后重试'))
  } finally {
    creatingProject.value = false
    createProjectInFlight.value = false
  }
}

async function selectProject(projectId: number) {
  selectedProjectId.value = String(projectId)
  setStoredCurrentProjectId(selectedProjectId.value)
  await loadData()
}

function removeProject(projectId: number) {
  const target = projects.value.find(p => p.id === projectId)
  if (!target) return
  projectToDelete.value = target
  deleteDialogVisible.value = true
}

async function executeDeleteProject() {
  if (!projectToDelete.value || deletingProject.value) return
  const projectId = projectToDelete.value.id
  deletingProject.value = true
  try {
    clearProjectQuestionTreeStorage(projectId)
    await deleteProject(projectId)
    deleteDialogVisible.value = false
    projects.value = projects.value.filter(p => p.id !== projectId)

    if (selectedProjectId.value === String(projectId)) {
      selectedProjectId.value = ''
      clearStoredCurrentProjectId()
    }

    projects.value = sortProjects(await listProjects())
    await loadData()
    projectToDelete.value = null
  } catch (e: any) {
    console.error('删除任务失败', e)
    alert(formatRequestError(e, '删除任务失败，请稍后重试'))
  } finally {
    deletingProject.value = false
  }
}

const currentMainTitle = computed(() => '典型工艺规程文件')
const currentMainDesc = computed(() => '支持 PDF / Word / Excel / JSON，可一次上传多份')
const currentRefTitle = computed(() => '参考资料')
const currentRefDesc = computed(() => '老工艺师经验、背景说明、工艺编制原则等补充知识')
const availableNewProjectProfiles = computed(() => profileCatalog.value.filter(profile => profile.mode === 'route_rules'))
const resolvedNewProjectProfile = computed(() => {
  if (newProjectProfile.value) return newProjectProfile.value
  return availableNewProjectProfiles.value.length === 1 ? (availableNewProjectProfiles.value[0]?.key ?? '') : ''
})
const canCreateProject = computed(() => Boolean(newProjectName.value.trim()))
const canEnterExtract = computed(() =>
  Boolean(selectedProjectId.value) && mainFiles.value.length > 0 && !uploading.value
)
const uploadNavSummary = computed(() => {
  if (!selectedProjectId.value) return '请先创建或选择任务，再上传工艺规程文件。'
  if (mainFiles.value.length === 0) return '当前任务还没有上传工艺规程文件，上传后才能进入路线归并。'
  const refText = refFiles.value.length > 0 ? `，${refFiles.value.length} 份参考资料` : ''
  return `当前任务已上传 ${mainFiles.value.length} 份工艺规程${refText}。`
})

function profileShortLabel(profileKey?: string) {
  return resolveProfileShortLabel(profileCatalog.value, profileKey)
}

async function doUpload(files: File[]) {
  uploading.value = true
  try {
    clearProjectQuestionTreeStorage(selectedProjectId.value)
    const uploaded = await uploadDocuments(files, Number(selectedProjectId.value))
    if (Array.isArray(uploaded) && uploaded.length > 0) {
      mainFiles.value = [...uploaded, ...mainFiles.value]
    }
    await loadData()
  } catch (e) {
    console.error('上传失败', e)
    alert(formatRequestError(e, '上传失败'))
  } finally {
    uploading.value = false
  }
}

async function doRefUpload(files: File[]) {
  uploadingRef.value = true
  try {
    clearProjectQuestionTreeStorage(selectedProjectId.value)
    const uploaded = await uploadReferences(files, Number(selectedProjectId.value))
    if (Array.isArray(uploaded) && uploaded.length > 0) {
      refFiles.value = [...uploaded, ...refFiles.value]
    }
    await loadData()
  } catch (e) {
    console.error('上传参考资料失败', e)
    alert(formatRequestError(e, '上传参考资料失败'))
  } finally {
    uploadingRef.value = false
  }
}

const saveRef = async (payload: { title: string; content: string }) => {
  const content = payload.content.trim()
  const title = payload.title.trim() || '补充要求'
  if (!content) return
  clearProjectQuestionTreeStorage(selectedProjectId.value)
  await createReference({
    project_id: Number(selectedProjectId.value),
    title: title,
    content: content,
    ref_type: 'written'
  })
  await loadData()
}

const removeDoc = async (id: number) => {
  clearProjectQuestionTreeStorage(selectedProjectId.value)
  await deleteDocument(id)
  await loadData()
}

const removeRef = async (id: number) => {
  clearProjectQuestionTreeStorage(selectedProjectId.value)
  await deleteReference(id)
  await loadData()
}

const goNext = async () => {
  if (!canEnterExtract.value) return
  setStoredCurrentProjectId(selectedProjectId.value)
  const nextPath = '/extract'
  const targetUrl = `${nextPath}?${new URLSearchParams(buildProjectRouteQuery(selectedProjectId.value)).toString()}`
  try {
    await router.push(targetUrl)
  } catch (e) {
    console.error('路由跳转失败，改用浏览器跳转', e)
  }
  const currentUrl = `${window.location.pathname}${window.location.search}`
  if (currentUrl !== targetUrl) {
    window.location.assign(targetUrl)
  }
}
</script>

<style scoped>
/* Root Layout Container: Full-Height Flex Fitting */
.upload-view {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 176px); /* Leave room for the fixed workflow footer. */
  overflow: hidden;
  box-sizing: border-box;
}

/* Page Header: Tighter & Compact */
.page-header {
  margin-bottom: 10px;
  flex-shrink: 0;
}
.page-header h1 {
  font-size: 18px;
  font-weight: 700;
  margin-bottom: 2px;
}
.page-desc {
  font-size: 12px;
  color: var(--text-secondary);
}

/* Content Grid Area (Split Columns) */
.content-grid {
  flex: 1;
  min-height: 0;
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 12px;
  margin-bottom: 0;
  overflow: hidden;
}

.btn-with-svg {
  display: inline-flex;
  align-items: center;
  gap: 4px;
}

/* Empty Task Layout */
.empty-task-card {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: 10px;
  text-align: center;
  padding: 32px 16px;
  border: 1px dashed #cbd5e1;
  background: linear-gradient(180deg, #fcfcfd, #f8fafc);
  border-radius: var(--radius-md);
  margin-bottom: 0;
}
.empty-task-icon-wrapper {
  width: 48px;
  height: 48px;
  border-radius: 50%;
  background: #f1f5f9;
  color: #6366f1;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 4px;
  border: 1px solid rgba(99, 102, 241, 0.08);
}
.compass-svg {
  display: block;
}
.empty-task-card h3 {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
}
.empty-task-card p {
  max-width: 480px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
  margin-bottom: 6px;
}

@media (max-width: 900px) {
  .content-grid { grid-template-columns: 1fr; overflow-y: auto; }
  .upload-view { height: auto; overflow: visible; }
}

/* Custom Delete Dialog styling */
:deep(.custom-delete-dialog) {
  border-radius: var(--radius-md);
  overflow: hidden;
  box-shadow: var(--shadow-lg);
}
:deep(.custom-delete-dialog .el-dialog__header) {
  display: none;
}
:deep(.custom-delete-dialog .el-dialog__body) {
  padding: 24px 20px 16px;
}
:deep(.custom-delete-dialog .el-dialog__footer) {
  padding: 0 20px 20px;
}
.delete-dialog-content {
  display: flex;
  flex-direction: column;
  align-items: center;
  text-align: center;
}
.delete-icon-wrapper {
  width: 48px;
  height: 48px;
  background: #fee2e2;
  color: #dc2626;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 12px;
  box-shadow: 0 2px 8px rgba(220, 38, 38, 0.1);
}
.delete-title {
  font-size: 16px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 8px;
}
.delete-desc {
  font-size: 13px;
  color: var(--text-secondary);
  line-height: 1.5;
}
.delete-desc strong {
  color: var(--text-primary);
  font-weight: 600;
}
.delete-dialog-footer {
  display: flex;
  gap: 12px;
  width: 100%;
}
.delete-dialog-footer .btn {
  flex: 1;
  justify-content: center;
  padding: 8px;
  font-size: 13.5px;
}
.btn-danger-fill {
  background: #ef4444;
  color: #fff;
  border: none;
  border-radius: 6px;
  font-weight: 600;
  cursor: pointer;
  transition: all 0.2s ease;
}
.btn-danger-fill:hover {
  background: #dc2626;
}

/* Custom Create Dialog V5 styling */
:deep(.custom-create-dialog-v5) {
  border-radius: 12px;
  overflow: hidden;
  box-shadow: 0 12px 30px rgba(0, 0, 0, 0.1);
  background: #ffffff;
}
:deep(.custom-create-dialog-v5 .el-dialog__header) { display: none; }
:deep(.custom-create-dialog-v5 .el-dialog__body) { padding: 0; }

.v5-dialog-content {
  padding: 16px 20px;
  position: relative;
}
.v5-close-btn {
  position: absolute;
  top: 10px;
  right: 10px;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  border: none;
  background: transparent;
  color: #94a3b8;
  font-size: 11px;
  cursor: pointer;
  transition: all 0.15s ease;
  display: flex;
  align-items: center;
  justify-content: center;
}
.v5-close-btn:hover {
  background: #f1f5f9;
  color: #475569;
}
.v5-header {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 12px;
  padding-bottom: 10px;
  border-bottom: 1px solid #f1f5f9;
}
.v5-header-icon {
  width: 28px;
  height: 28px;
  border-radius: 6px;
  background: #eef2ff;
  color: #6366f1;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  border: 1px solid rgba(99, 102, 241, 0.08);
}
.v5-header-text {
  flex: 1;
  min-width: 0;
}
.v5-title {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
  margin: 0 0 1px 0;
}
.v5-subtitle {
  font-size: 10.5px;
  color: #64748b;
  margin: 0;
}
.v5-body {
  margin-bottom: 12px;
}
.v5-field {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.v5-label-row {
  display: flex;
  align-items: center;
  gap: 2px;
}
.v5-label {
  font-size: 10.5px;
  font-weight: 700;
  color: #475569;
}
.v5-req {
  color: #ef4444;
  font-size: 10.5px;
}
.v5-input {
  width: 100%;
  padding: 6px 10px;
  border: 1px solid #cbd5e1;
  border-radius: 5px;
  font-size: 12px;
  color: #0f172a;
  background: #ffffff;
  transition: all 0.15s ease-in-out;
  outline: none;
}
.v5-input::placeholder {
  color: #cbd5e1;
}
.v5-input:focus {
  border-color: #6366f1;
  box-shadow: 0 0 0 2px rgba(99, 102, 241, 0.1);
}
.v5-hint {
  font-size: 10px;
  color: #94a3b8;
  margin: 1px 0 0 0;
}
.v5-profiles {
  margin-top: 10px;
}
.v5-chip-container {
  display: flex;
  flex-wrap: wrap;
  gap: 4px;
  margin-top: 4px;
}
.v5-chip {
  padding: 3px 8px;
  font-size: 10px;
  font-weight: 600;
  border-radius: 4px;
  border: 1px solid #e2e8f0;
  background: #ffffff;
  color: #64748b;
  cursor: pointer;
  transition: all 0.15s ease;
}
.v5-chip:hover {
  border-color: #cbd5e1;
  background: #f8fafc;
}
.v5-chip.active {
  border-color: #6366f1;
  background: #eef2ff;
  color: #4f46e5;
}
.v5-footer {
  display: flex;
  justify-content: flex-end;
  gap: 6px;
  margin-top: 14px;
  padding-top: 10px;
  border-top: 1px solid #f1f5f9;
}
.v5-btn-cancel {
  padding: 5px 10px;
  font-size: 11.5px;
  font-weight: 600;
  color: #64748b;
  background: transparent;
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.v5-btn-cancel:hover {
  background: #f1f5f9;
  color: #1e293b;
}
.v5-btn-primary {
  padding: 5px 12px;
  font-size: 11.5px;
  font-weight: 700;
  color: #ffffff;
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  border: none;
  border-radius: 5px;
  cursor: pointer;
  transition: all 0.15s ease;
}
.v5-btn-primary:hover:not(:disabled) {
  background: linear-gradient(135deg, #4f46e5, #4338ca);
}
.v5-btn-primary:disabled {
  background: #f1f5f9;
  color: #94a3b8;
  cursor: not-allowed;
}
</style>
