export type TemplateMappingEditContext = {
  projectId: number
  routeVersionId: number
  workflowRevision: number
  templateRevision: number
}

type PendingMappingEdits = TemplateMappingEditContext & {
  precisionOverrides: Record<string, string>
  hiddenStepKeys?: string[]
  waivedGroupPaths?: string[][]
  stepOrderByProcess?: Record<string, string[]>
}

export type TemplateMappingExceptions = { hiddenStepKeys: string[]; waivedGroupPaths: string[][]; stepOrderByProcess?: Record<string, string[]> }

function key(projectId: number) { return `processmind:pending-template-mapping:${projectId}` }

function read(context: TemplateMappingEditContext): PendingMappingEdits | null {
  if (typeof localStorage === 'undefined' || !context.projectId || !context.routeVersionId) return null
  try {
    const value = JSON.parse(localStorage.getItem(key(context.projectId)) || 'null')
    if (!value || value.projectId !== context.projectId || value.routeVersionId !== context.routeVersionId
      || value.workflowRevision !== context.workflowRevision || value.templateRevision !== context.templateRevision) return null
    return value
  } catch { return null }
}

export function hasPendingTemplateMappingEdits(projectId: number, routeVersionId: number, workflowRevision: number, templateRevision: number) {
  return Boolean(read({ projectId, routeVersionId, workflowRevision, templateRevision }))
}

export function saveTemplateMappingEdits(context: TemplateMappingEditContext, dirty: boolean, precisionOverrides: Record<string, string>, exceptions?: TemplateMappingExceptions) {
  if (typeof localStorage === 'undefined' || !context.projectId || !context.routeVersionId) return
  try {
    if (dirty) localStorage.setItem(key(context.projectId), JSON.stringify({ ...context, precisionOverrides, ...exceptions }))
    else clearTemplateMappingEdits(context)
  } catch { /* Navigation guards still protect the active editor if storage is unavailable. */ }
}

export function clearTemplateMappingEdits(context: TemplateMappingEditContext) {
  if (!read(context)) return
  try { localStorage.removeItem(key(context.projectId)) } catch { /* Keep the active editor usable. */ }
}

export function loadTemplateMappingPrecisionDraft(context: TemplateMappingEditContext, fallback: Record<string, string>) {
  const draft = read(context)?.precisionOverrides
  return draft && typeof draft === 'object' && !Array.isArray(draft)
    && Object.values(draft).every(value => typeof value === 'string') ? { ...draft } : { ...fallback }
}

export function loadTemplateMappingExceptionDraft(context: TemplateMappingEditContext, fallback: TemplateMappingExceptions): TemplateMappingExceptions {
  const draft = read(context)
  const hidden = draft?.hiddenStepKeys
  const waived = draft?.waivedGroupPaths
  return {
    ...((draft?.stepOrderByProcess || fallback.stepOrderByProcess) ? { stepOrderByProcess: Object.fromEntries(
      Object.entries(draft?.stepOrderByProcess || fallback.stepOrderByProcess || {}).filter(([, ids]) => Array.isArray(ids)
        && ids.every(id => typeof id === 'string')).map(([pid, ids]) => [pid, [...ids]])) } : {}),
    hiddenStepKeys: Array.isArray(hidden) && hidden.every(key => typeof key === 'string') ? [...hidden] : [...fallback.hiddenStepKeys],
    waivedGroupPaths: (Array.isArray(waived) && waived.every(path => Array.isArray(path) && path.every(part => typeof part === 'string'))
      ? waived : fallback.waivedGroupPaths).map(path => [...path]),
  }
}
