const DEFAULT_WORKFLOW_CACHE_TTL_MS = 45_000

type WorkflowDataCacheEntry<T> = {
  value: T
  updatedAt: number
}

const workflowDataCache = new Map<string, WorkflowDataCacheEntry<unknown>>()
let workflowDataRevision = 0

function bumpWorkflowDataRevision() {
  workflowDataRevision += 1
}

export function getWorkflowDataRevision() {
  return workflowDataRevision
}

export function getWorkflowDataCache<T>(
  key: string,
  maxAgeMs = DEFAULT_WORKFLOW_CACHE_TTL_MS,
) {
  const entry = workflowDataCache.get(key)
  if (!entry) return null
  if (Date.now() - entry.updatedAt > maxAgeMs) {
    workflowDataCache.delete(key)
    return null
  }
  return entry.value as T
}

export function setWorkflowDataCache<T>(key: string, value: T) {
  workflowDataCache.set(key, {
    value,
    updatedAt: Date.now(),
  })
}

export function clearWorkflowDataCache(key: string) {
  workflowDataCache.delete(key)
  bumpWorkflowDataRevision()
}

export function clearWorkflowDataCacheByPrefix(prefix: string) {
  let cleared = false
  Array.from(workflowDataCache.keys()).forEach((key) => {
    if (key.startsWith(prefix)) {
      workflowDataCache.delete(key)
      cleared = true
    }
  })
  if (cleared) bumpWorkflowDataRevision()
}

export function clearWorkflowProjectDataCache(projectId?: string | number | null) {
  const normalizedProjectId = String(projectId ?? '').trim()
  if (!normalizedProjectId) return
  const projectSuffix = `:${normalizedProjectId}`
  const projectSegment = `${projectSuffix}:`
  let cleared = false
  Array.from(workflowDataCache.keys()).forEach((key) => {
    if (key.endsWith(projectSuffix) || key.includes(projectSegment)) {
      workflowDataCache.delete(key)
      cleared = true
    }
  })
  if (cleared) bumpWorkflowDataRevision()
}

export function clearAllWorkflowDataCache() {
  workflowDataCache.clear()
  bumpWorkflowDataRevision()
}
