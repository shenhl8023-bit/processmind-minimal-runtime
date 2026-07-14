export function isSystemSeedProject(project: any) {
  return project?.id === 1 && project?.name === '历史任务'
}

export function formatRequestError(error: any, fallback: string) {
  const detail = error?.response?.data?.detail
  if (typeof detail === 'string' && detail.trim()) return detail.trim()
  if (Array.isArray(detail) && detail.length > 0) {
    return detail.map((item) => item?.msg || item).filter(Boolean).join('；')
  }
  const message = typeof error?.message === 'string' ? error.message.trim() : ''
  if (message === 'Network Error') {
    return `${fallback}。当前请求没有成功到达后端，请检查本地服务连接后重试。`
  }
  return message || fallback
}

export function getFileType(name: string) {
  const ext = name?.split('.').pop()?.toLowerCase() || ''
  if (ext === 'pdf') return 'pdf'
  if (['doc', 'docx'].includes(ext)) return 'word'
  if (['xls', 'xlsx'].includes(ext)) return 'excel'
  if (ext === 'json') return 'json'
  return 'other'
}

export function formatTime(t: string) {
  if (!t) return ''
  return new Date(t).toLocaleString('zh-CN')
}

export function projectStatusText(status: string) {
  if (status === 'GENERATED') return '已生成'
  if (status === 'ROUTE_SET_READY') return '全集已生成'
  if (status === 'EXTRACTING') return '提炼中'
  if (status === 'EXTRACT_ERROR') return '提炼失败'
  if (status === 'UPLOADED') return '已上传'
  return '草稿'
}

export function sortProjects(items: any[]) {
  return [...items].sort((a, b) => {
    const aTime = new Date(a?.updated_at || a?.created_at || 0).getTime()
    const bTime = new Date(b?.updated_at || b?.created_at || 0).getTime()
    if (aTime !== bTime) return bTime - aTime
    return Number(b?.id || 0) - Number(a?.id || 0)
  })
}

export function profileShortLabel(profileCatalog: Array<{ key?: string; short_label?: string }>, profileKey?: string) {
  return profileCatalog.find(profile => profile.key === profileKey)?.short_label || ''
}
