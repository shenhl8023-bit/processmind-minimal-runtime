import { api } from './client'
import type { ProjectMode } from './types'

export interface Project {
  id: number
  name: string
  mode: ProjectMode
  profile: string
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

export async function listProjects() {
  const { data } = await api.get('/api/projects/')
  return data as Project[]
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
  return data as Project
}

export async function deleteProject(id: number) {
  const { data } = await api.delete(`/api/projects/${id}`)
  return data
}
