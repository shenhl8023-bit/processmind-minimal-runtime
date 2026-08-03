import { ref, type Ref } from 'vue'
import { downloadFinalizedRulePackageArchive } from '@/api'
import { downloadBlob } from '@/utils/exportArchive'

type DownloadIssue = {
  title: string
  summary: string
  details?: string
}

type UseFinalizedRulePackageDownloadOptions = {
  packageId: Readonly<Ref<number | null>>
  packageVersion: Readonly<Ref<number | null>>
  projectName: Readonly<Ref<string>>
  onDownloadIssue?: (issue: DownloadIssue) => void
}

function safeFilenamePart(value: string) {
  return value.replace(/[\\/:*?"<>|]/g, '_')
}

async function downloadErrorDetail(error: any): Promise<string> {
  const data = error?.response?.data
  if (data instanceof Blob) {
    try {
      const parsed = JSON.parse(await data.text())
      return String(parsed?.detail || '未知错误')
    } catch {
      return error?.message || '未知错误'
    }
  }
  return String(data?.detail || error?.message || '未知错误')
}

export function useFinalizedRulePackageDownload(options: UseFinalizedRulePackageDownloadOptions) {
  const downloadingRulePackage = ref(false)

  async function downloadCurrentRulePackage() {
    const packageId = options.packageId.value
    if (!packageId || downloadingRulePackage.value) return
    downloadingRulePackage.value = true
    try {
      const archive = await downloadFinalizedRulePackageArchive(packageId)
      const fallback = `${safeFilenamePart(options.projectName.value || '规则包')}_规则包_v${options.packageVersion.value || 1}.zip`
      downloadBlob(archive.blob, archive.filename || fallback)
    } catch (error: any) {
      const detail = await downloadErrorDetail(error)
      options.onDownloadIssue?.({
        title: '规则包下载失败',
        summary: '当前已发布版本未能下载，请稍后重试。',
        details: detail,
      })
    } finally {
      downloadingRulePackage.value = false
    }
  }

  return { downloadingRulePackage, downloadCurrentRulePackage }
}
