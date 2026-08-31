import { api } from './client'
import {
  clearWorkflowDataCache,
  clearWorkflowProjectDataCache,
  getWorkflowDataCache,
  getWorkflowDataRevision,
  setWorkflowDataCache,
} from '@/composables/workflowDataCache'

const PROJECT_LIST_CACHE_KEY = 'api:projects:list'

export interface Project {
  id: number
  name: string
  workflow_revision: number
  status: string
  created_at: string
  updated_at: string
}

export async function listProjects(forceRefresh = false) {
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<Project[]>(PROJECT_LIST_CACHE_KEY)
    if (cached) return cached
  }
  const requestRevision = getWorkflowDataRevision()
  const { data } = await api.get('/api/projects/')
  const projects = data as Project[]
  setWorkflowDataCache(PROJECT_LIST_CACHE_KEY, projects, requestRevision)
  return projects
}

export async function createProject(name: string) {
  const { data } = await api.post('/api/projects/', { name })
  clearWorkflowDataCache(PROJECT_LIST_CACHE_KEY)
  return data as Project
}

export async function deleteProject(id: number) {
  const { data } = await api.delete(`/api/projects/${id}`)
  clearWorkflowDataCache(PROJECT_LIST_CACHE_KEY)
  clearWorkflowProjectDataCache(id)
  return data
}
