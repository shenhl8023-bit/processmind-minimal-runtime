import * as Vue from 'vue'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import source from './UploadView.vue?raw'
import uploadCardSource from '@/components/upload/UploadMainFileCard.vue?raw'
import * as currentProject from '@/composables/useCurrentProject'
import * as helpers from '@/utils/uploadViewHelpers'

const api = {
  listProjects: vi.fn(), listDocuments: vi.fn(), uploadDocuments: vi.fn(),
  deleteDocument: vi.fn(), createProject: vi.fn(), deleteProject: vi.fn(),
}
const clearProjectQuestionTreeStorage = vi.fn()
const refreshWorkflowNavigation = vi.fn()
const router = { push: vi.fn(), replace: vi.fn() }
let route: any
const compiled = compileScript(parse(source).descriptor, { id: 'upload-functional-test' })
const code = transformSync(compiled.content, { loader: 'ts', format: 'cjs', platform: 'node' }).code
const module = { exports: {} as any }
new Function('require', 'module', 'exports', code)((id: string) => {
  if (id === 'vue') return { ...Vue, onMounted: () => {} }
  if (id === 'vue-router') return { useRouter: () => router, useRoute: () => route }
  if (id === '@/api') return api
  if (id === '@/composables/useCurrentProject') return currentProject
  if (id === '@/composables/analysisQuestionTreeState') return { clearProjectQuestionTreeStorage }
  if (id === '@/composables/workflowNavigation') return { refreshWorkflowNavigation }
  if (id === '@/utils/uploadViewHelpers') return helpers
  if (id.endsWith('.vue')) return { default: {} }
  throw new Error(id)
}, module, module.exports)
function mount() { return module.exports.default.setup({}, { expose() {} }) }
function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>(done => { resolve = done })
  return { promise, resolve }
}
beforeEach(() => {
  vi.resetAllMocks()
  route = Vue.reactive({ path: '/upload', query: {} })
  router.replace.mockResolvedValue(undefined)
  const storage = new Map<string, string>()
  vi.stubGlobal('window', { location: { pathname: '/upload', search: '', assign: vi.fn() } })
  vi.stubGlobal('localStorage', {
    getItem: (key: string) => storage.get(key) ?? null,
    setItem: (key: string, value: string) => storage.set(key, value),
    removeItem: (key: string) => storage.delete(key),
  })
  vi.stubGlobal('alert', vi.fn())
  api.listProjects.mockResolvedValue([{ id: 1, name: '任务A' }, { id: 2, name: '任务B' }])
  api.listDocuments.mockResolvedValue([])
})

describe('upload task isolation', () => {
  it('loads project documents without requesting auxiliary reference data', async () => {
    api.listDocuments.mockResolvedValue([{ id: 11, original_name: 'route.pdf' }])
    const model = mount()
    model.selectedProjectId.value = '1'
    await model.loadData(true)
    expect(api.listDocuments).toHaveBeenCalledWith(1, true)
    expect(model.mainFiles.value).toEqual([{ id: 11, original_name: 'route.pdf' }])
  })

  it('limits the primary file picker to PDF', () => {
    expect(uploadCardSource).toContain('accept=".pdf"')
    expect(uploadCardSource).not.toMatch(/accept="[^"]*(docx|xlsx|json)/)
  })

  it('rejects dragged non-PDF files before sending the upload request', async () => {
    const model = mount()
    model.selectedProjectId.value = '1'
    await model.doUpload([{ name: 'route.docx' } as File])
    expect(api.uploadDocuments).not.toHaveBeenCalled()
    expect(model.uploadNotices.value[0]?.detail).toBeTruthy()
    expect(alert).not.toHaveBeenCalled()
  })

  it('deletes only the exact file identity shown in the selected project', async () => {
    const model = mount()
    model.selectedProjectId.value = '1'
    model.mainFiles.value = [{ id: 11, filename: 'stable-token.json', project_id: 1 }]
    api.deleteDocument.mockResolvedValue({ ok: true })
    await model.removeDoc(11)
    expect(api.deleteDocument).toHaveBeenCalledWith(11, { project_id: 1, filename: 'stable-token.json' })
  })

  it('loads saved task documents when initialization adds the canonical task query', async () => {
    currentProject.setStoredCurrentProjectId(1)
    api.listDocuments.mockResolvedValue([{ id: 11, filename: 'A.json' }])
    router.replace.mockImplementation(async (target: any) => { route.query = target.query })
    const model = mount()
    await model.initializeUploadView()
    expect(route.query.project_id).toBe('1')
    expect(model.mainFiles.value).toEqual([{ id: 11, filename: 'A.json' }])
    expect(model.canEnterExtract.value).toBe(true)
  })
  it('refreshes workflow milestones after a document is uploaded or removed', async () => {
    api.uploadDocuments.mockResolvedValue([{ id: 11 }])
    api.deleteDocument.mockResolvedValue(undefined)
    const model = mount()
    model.selectedProjectId.value = '1'
    await model.doUpload([])
    expect(refreshWorkflowNavigation).toHaveBeenCalledWith(1)
    refreshWorkflowNavigation.mockClear()
    model.mainFiles.value = [{ id: 11, filename: 'uploaded.json' }]
    await model.removeDoc(11)
    expect(refreshWorkflowNavigation).toHaveBeenCalledWith(1)
  })
  it('cannot upload to an old cached task after resolving another task fails', async () => {
    api.listProjects.mockRejectedValue(new Error('offline'))
    const model = mount()
    model.selectedProjectId.value = '1'
    route.query.project_id = '2'
    await model.initializeUploadView()
    await model.doUpload([])
    expect(api.uploadDocuments).not.toHaveBeenCalled()
    expect(model.selectedProjectId.value).toBe('')
  })
  it('locks cached task actions immediately when another task URL is being resolved', async () => {
    const projects = deferred<any[]>()
    api.listProjects.mockReturnValue(projects.promise)
    const model = mount()
    model.selectedProjectId.value = '1'
    model.mainFiles.value = [{ id: 11, filename: 'A.json' }]
    route.query.project_id = '2'
    const loading = model.initializeUploadView()
    expect(model.mainFiles.value).toEqual([])
    expect(model.canEnterExtract.value).toBe(false)
    await model.doUpload([])
    expect(api.uploadDocuments).not.toHaveBeenCalled()
    projects.resolve([{ id: 1 }, { id: 2 }])
    await loading
  })

  it('does not restore an old task when its initialization returns after a new selection', async () => {
    const oldProjects = deferred<any[]>()
    api.listProjects.mockReturnValueOnce(oldProjects.promise)
    route.query.project_id = '1'
    const model = mount()
    const oldLoading = model.initializeUploadView()
    await model.selectProject(2)
    oldProjects.resolve([{ id: 1 }, { id: 2 }])
    await oldLoading
    expect(model.selectedProjectId.value).toBe('2')
    expect(currentProject.getStoredCurrentProjectId()).toBe('2')
  })
  it('updates the navigation context when choosing a different upload task', async () => {
    route.query.project_id = '1'
    const model = mount()
    await model.selectProject(2)
    expect(router.replace).toHaveBeenCalledWith({ path: '/upload', query: { project_id: '2' } })
  })

  it('honors the explicit task URL over a previously selected task', async () => {
    currentProject.setStoredCurrentProjectId(1)
    route.query.project_id = '2'
    const model = mount()
    await model.ensureProjectReady()
    expect(model.selectedProjectId.value).toBe('2')
  })
  it('keeps task B files when the earlier task A response arrives last', async () => {
    const oldFiles = deferred<any[]>()
    api.listDocuments.mockImplementation((id: number) => id === 1 ? oldFiles.promise : [{ id: 22, filename: 'B.json' }])
    const model = mount()
    const oldSelection = model.selectProject(1)
    await Vue.nextTick()
    await model.selectProject(2)
    oldFiles.resolve([{ id: 11, filename: 'A.json' }])
    await oldSelection
    expect(model.selectedProjectId.value).toBe('2')
    expect(model.mainFiles.value).toEqual([{ id: 22, filename: 'B.json' }])
  })

  it('clears old files and locks next step while another task is loading', async () => {
    const newFiles = deferred<any[]>()
    const model = mount()
    model.selectedProjectId.value = '1'
    model.mainFiles.value = [{ id: 11, filename: 'A.json' }]
    api.listDocuments.mockReturnValue(newFiles.promise)
    const loading = model.selectProject(2)
    expect(model.mainFiles.value).toEqual([])
    expect(model.canEnterExtract.value).toBe(false)
    newFiles.resolve([])
    await loading
  })

  it('preserves question drafts when deleting a document fails and displays the error', async () => {
    api.deleteDocument.mockRejectedValue(new Error('offline'))
    const model = mount()
    model.selectedProjectId.value = '1'
    model.mainFiles.value = [{ id: 11, filename: 'uploaded.json' }]
    await expect(model.removeDoc(11)).resolves.toBeUndefined()
    expect(clearProjectQuestionTreeStorage).not.toHaveBeenCalled()
    expect(model.uploadNotices.value[0]?.detail).toBeTruthy()
    expect(alert).not.toHaveBeenCalled()
  })

  it('keeps task B files when task A upload finishes after switching', async () => {
    const upload = deferred<any[]>()
    api.uploadDocuments.mockReturnValue(upload.promise)
    const model = mount()
    model.selectedProjectId.value = '1'
    const pending = model.doUpload([])
    await model.selectProject(2)
    model.mainFiles.value = [{ id: 22, filename: 'B.json' }]
    upload.resolve([{ id: 11, filename: 'A.json' }])
    await pending
    expect(model.mainFiles.value).toEqual([{ id: 22, filename: 'B.json' }])
    expect(clearProjectQuestionTreeStorage).toHaveBeenCalledWith('1')
  })

  it('allows immediate retry of failed task creation', async () => {
    api.listProjects.mockResolvedValue([{ id: 3, name: '重试任务' }])
    api.createProject.mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ id: 3, name: '重试任务' })
    const model = mount()
    model.newProjectName.value = '重试任务'
    await model.executeCreateProject()
    await model.executeCreateProject()
    expect(model.selectedProjectId.value).toBe('3')
  })

  it('preserves question drafts when an upload fails', async () => {
    api.uploadDocuments.mockRejectedValue(new Error('offline'))
    const model = mount()
    model.selectedProjectId.value = '1'
    await model.doUpload([])
    expect(clearProjectQuestionTreeStorage).not.toHaveBeenCalled()
    expect(model.uploadNotices.value[0]?.detail).toBeTruthy()
    expect(alert).not.toHaveBeenCalled()
  })

  it('keeps the selected task when an earlier create request completes', async () => {
    const created = deferred<any>()
    api.createProject.mockReturnValue(created.promise)
    const model = mount()
    model.newProjectName.value = '新任务'
    const creating = model.executeCreateProject()
    await model.selectProject(2)
    api.listProjects.mockResolvedValue([{ id: 1 }, { id: 2 }, { id: 3, name: '新任务' }])
    created.resolve({ id: 3, name: '新任务' })
    await creating
    expect(model.selectedProjectId.value).toBe('2')
    expect(currentProject.getStoredCurrentProjectId()).toBe('2')
    expect(model.projects.value.some((project: any) => project.id === 3)).toBe(true)
  })

  it('does not report a successful task deletion as failed when refreshing the list fails', async () => {
    api.deleteProject.mockResolvedValue({ ok: true })
    api.listProjects.mockRejectedValue(new Error('offline after delete'))
    const model = mount()
    model.projects.value = [{ id: 1 }, { id: 2 }]
    model.selectedProjectId.value = '1'
    model.mainFiles.value = [{ id: 11, filename: 'A.json' }]
    model.projectToDelete.value = { id: 1 }
    await model.executeDeleteProject()
    expect(model.mainFiles.value).toEqual([])
    expect(model.projectToDelete.value).toBe(null)
    expect(model.selectedProjectId.value).toBe('')
    expect(vi.mocked(alert).mock.calls.flat().join(' ')).not.toContain('删除任务失败')
  })

  it('preserves question drafts when task deletion fails', async () => {
    api.deleteProject.mockRejectedValue(new Error('offline'))
    const model = mount()
    model.projectToDelete.value = { id: 1 }
    await model.executeDeleteProject()
    expect(clearProjectQuestionTreeStorage).not.toHaveBeenCalled()
  })
})
