import { api } from './client'
import type { ProjectMode } from './types'
import {
  clearWorkflowDataCache,
  getWorkflowDataCache,
  setWorkflowDataCache,
} from '@/composables/workflowDataCache'

const PROJECT_LIST_CACHE_KEY = 'api:projects:list'

export interface Project {
  id: number
  name: string
  mode: ProjectMode
  profile: string
  rule_engine?: 'auto' | 'v1' | 'v2' | string
  status: string
  created_at: string
  updated_at: string
}

export interface ProjectProfile {
  key: string
  mode: ProjectMode
  label: string
  short_label: string
  description: string
}

export async function listProjects(forceRefresh = false) {
  if (!forceRefresh) {
    const cached = getWorkflowDataCache<Project[]>(PROJECT_LIST_CACHE_KEY)
    if (cached) return cached
  }
  const { data } = await api.get('/api/projects/')
  const projects = data as Project[]
  setWorkflowDataCache(PROJECT_LIST_CACHE_KEY, projects)
  return projects
}

export async function listProjectProfiles(mode?: ProjectMode) {
  const { data } = await api.get('/api/projects/profiles', { params: mode ? { mode } : undefined })
  return data as ProjectProfile[]
}

export async function createProject(
  name: string,
  mode: ProjectMode = 'route_rules',
  profile?: string,
) {
  const { data } = await api.post('/api/projects/', { name, mode, profile })
  clearWorkflowDataCache(PROJECT_LIST_CACHE_KEY)
  return data as Project
}

export async function deleteProject(id: number) {
  const { data } = await api.delete(`/api/projects/${id}`)
  clearWorkflowDataCache(PROJECT_LIST_CACHE_KEY)
  return data
}

export async function updateProjectRuleEngine(id: number, ruleEngine: 'auto' | 'v1' | 'v2') {
  const { data } = await api.patch(`/api/projects/${id}/rule-engine`, { rule_engine: ruleEngine })
  clearWorkflowDataCache(PROJECT_LIST_CACHE_KEY)
  return data as Project
}
