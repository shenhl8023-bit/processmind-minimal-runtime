import { api, apiBaseUrl } from './client'

export interface DocumentItem {
  id: number
  project_id?: number | null
  filename: string
  original_name: string
  file_type?: string | null
  file_size?: number | null
  uploader: string
  status: string
  created_at: string
}

export interface DocumentPreview {
  id: number
  original_name: string
  file_type?: string | null
  preview_text: string
}

export async function uploadDocuments(files: File[], projectId: number) {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))
  formData.append('project_id', String(projectId))
  const { data } = await api.post('/api/documents/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listDocuments(projectId: number) {
  const { data } = await api.get('/api/documents/', { params: { project_id: projectId } })
  return data as DocumentItem[]
}

export async function getDocumentPreview(docId: number) {
  const { data } = await api.get(`/api/documents/${docId}/preview`)
  return data as DocumentPreview
}

export async function getDocumentFileBlob(docId: number) {
  const { data } = await api.get(`/api/documents/${docId}/file`, {
    responseType: 'blob',
  })
  return data as Blob
}

export async function getDocumentPdfPageCount(docId: number) {
  const { data } = await api.get(`/api/documents/${docId}/pdf-pages`)
  return data as { page_count: number }
}

export function buildDocumentFileUrl(docId: number) {
  return `${apiBaseUrl}/api/documents/${docId}/file`
}

export function buildDocumentPdfPageUrl(docId: number, pageNo: number) {
  return `${apiBaseUrl}/api/documents/${docId}/pdf-pages/${pageNo}`
}

export async function deleteDocument(id: number) {
  const { data } = await api.delete(`/api/documents/${id}`)
  return data
}

export async function createReference(body: { title: string; content?: string; document_id?: number; project_id?: number; ref_type?: string }) {
  const { data } = await api.post('/api/documents/references', body)
  return data
}

export async function uploadReferences(files: File[], projectId: number) {
  const formData = new FormData()
  files.forEach(file => formData.append('files', file))
  formData.append('project_id', String(projectId))
  const { data } = await api.post('/api/documents/references/upload', formData, {
    headers: { 'Content-Type': 'multipart/form-data' },
  })
  return data
}

export async function listReferences(projectId: number) {
  const { data } = await api.get('/api/documents/references', { params: { project_id: projectId } })
  return data
}

export async function deleteReference(id: number) {
  const { data } = await api.delete(`/api/documents/references/${id}`)
  return data
}
