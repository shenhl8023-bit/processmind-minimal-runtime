import { ref } from 'vue'
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  downloadArchive: vi.fn(),
  downloadBlob: vi.fn(),
}))

vi.mock('@/api', () => ({
  downloadFinalizedRulePackageArchive: mocks.downloadArchive,
}))
vi.mock('@/utils/exportArchive', () => ({ downloadBlob: mocks.downloadBlob }))

import { rulePackageArchiveFilename } from '@/api/extract'
import { useFinalizedRulePackageDownload } from './useFinalizedRulePackageDownload'

describe('useFinalizedRulePackageDownload', () => {
  beforeEach(() => {
    mocks.downloadArchive.mockReset()
    mocks.downloadBlob.mockReset()
  })

  it('parses encoded and quoted server filenames', () => {
    expect(rulePackageArchiveFilename(
      "attachment; filename*=UTF-8''%E8%A7%84%E5%88%99%E5%8C%85_v3.zip",
    )).toBe('规则包_v3.zip')
    expect(rulePackageArchiveFilename('attachment; filename="rules_v3.zip"')).toBe('rules_v3.zip')
  })

  it('repeatedly downloads the same published package', async () => {
    const blob = new Blob(['zip'], { type: 'application/zip' })
    mocks.downloadArchive.mockResolvedValue({ blob, filename: '规则包_v3.zip' })
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId: ref(17),
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()
    await download.downloadCurrentRulePackage()

    expect(mocks.downloadArchive).toHaveBeenNthCalledWith(1, 17)
    expect(mocks.downloadArchive).toHaveBeenNthCalledWith(2, 17)
    expect(mocks.downloadBlob).toHaveBeenCalledTimes(2)
    expect(mocks.downloadBlob).toHaveBeenCalledWith(blob, '规则包_v3.zip')
    expect(issue).not.toHaveBeenCalled()
  })

  it('reports failure without clearing package metadata', async () => {
    mocks.downloadArchive.mockRejectedValue(new Error('network down'))
    const packageId = ref(17)
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId,
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()

    expect(packageId.value).toBe(17)
    expect(mocks.downloadBlob).not.toHaveBeenCalled()
    expect(issue).toHaveBeenCalledWith(expect.objectContaining({ title: '规则包下载失败' }))
  })

  it('reads backend detail from a failed blob response', async () => {
    mocks.downloadArchive.mockRejectedValue({
      response: {
        data: new Blob([JSON.stringify({ detail: '只能下载当前发布版本的规则包。' })], {
          type: 'application/json',
        }),
      },
    })
    const issue = vi.fn()
    const download = useFinalizedRulePackageDownload({
      packageId: ref(17),
      packageVersion: ref(3),
      projectName: ref('轴类项目'),
      onDownloadIssue: issue,
    })

    await download.downloadCurrentRulePackage()

    expect(issue).toHaveBeenCalledWith(expect.objectContaining({
      details: '只能下载当前发布版本的规则包。',
    }))
  })
})
