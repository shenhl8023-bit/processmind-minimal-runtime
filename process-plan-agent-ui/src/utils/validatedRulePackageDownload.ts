import type { FinalizedRulePackageResult } from '@/api/extract'
import { sampleRulePackageFiles } from './nativeRulePackageArchive'
import { createZipBlob, downloadBlob } from './exportArchive'
import { allocatePublicRulePackageIdentities } from '@/api/publicRulePackageIdentities'

export async function downloadValidatedRulePackage(saved: FinalizedRulePackageResult, projectName: string,
  options: { filename?: string; isCurrent?: () => boolean } = {}) {
  // Validate representability before creating any durable identity allocations.
  sampleRulePackageFiles(saved)
  const registry = await allocatePublicRulePackageIdentities(saved)
  if (options.isCurrent && !options.isCurrent()) return false
  const files = sampleRulePackageFiles(saved, registry)
  const name = (projectName || '工艺规程').replace(/[\\/:*?"<>|]/g, '_')
  downloadBlob(createZipBlob(files), options.filename || `${name}_规则包_V${saved.version}.zip`)
  return true
}
