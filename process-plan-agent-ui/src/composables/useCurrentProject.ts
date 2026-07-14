const CURRENT_PROJECT_KEY = 'processmind_current_project_id_v4'

function normalizeProjectId(value?: string | number | null) {
  const text = String(value ?? '').trim()
  if (!text) return ''
  const numeric = Number(text)
  if (!Number.isFinite(numeric) || numeric <= 0) return ''
  return String(numeric)
}

export function getCurrentProjectKey() {
  return CURRENT_PROJECT_KEY
}

export function getStoredCurrentProjectId() {
  if (typeof window === 'undefined') return ''
  return normalizeProjectId(localStorage.getItem(CURRENT_PROJECT_KEY))
}

export function setStoredCurrentProjectId(value?: string | number | null) {
  if (typeof window === 'undefined') return ''
  const projectId = normalizeProjectId(value)
  if (!projectId) {
    localStorage.removeItem(CURRENT_PROJECT_KEY)
    return ''
  }
  localStorage.setItem(CURRENT_PROJECT_KEY, projectId)
  return projectId
}

export function clearStoredCurrentProjectId() {
  if (typeof window === 'undefined') return
  localStorage.removeItem(CURRENT_PROJECT_KEY)
}

export function resolveCurrentProjectId(routeProjectId?: string | number | null) {
  return normalizeProjectId(routeProjectId) || getStoredCurrentProjectId()
}

export function resolveAvailableProjectId(
  routeProjectId: string | number | null | undefined,
  projects: Array<{ id: number | string }>,
) {
  const preferredId = resolveCurrentProjectId(routeProjectId)
  const availableIds = new Set(projects.map(project => normalizeProjectId(project.id)).filter(Boolean))
  if (preferredId && availableIds.has(preferredId)) {
    setStoredCurrentProjectId(preferredId)
    return preferredId
  }

  const fallbackId = normalizeProjectId(projects[0]?.id)
  if (fallbackId) {
    setStoredCurrentProjectId(fallbackId)
    return fallbackId
  }

  clearStoredCurrentProjectId()
  return ''
}

export function buildProjectRouteQuery(projectId?: string | number | null, extraQuery?: Record<string, string>) {
  const normalizedId = normalizeProjectId(projectId)
  if (!normalizedId) return undefined
  return {
    project_id: normalizedId,
    ...(extraQuery || {}),
  }
}
