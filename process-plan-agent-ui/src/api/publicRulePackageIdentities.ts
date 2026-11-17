import { api } from './client'
import type { FinalizedRulePackageResult } from './extract'
import type { PublicRulePackageIdentityRegistry } from '@/utils/sampleRulePackageAdapter'

export async function allocatePublicRulePackageIdentities(saved: FinalizedRulePackageResult): Promise<PublicRulePackageIdentityRegistry> {
  const { data } = await api.post('/api/extract/public-rule-package-identities', {
    finalized_rule_package_id: saved.id, expected_content_hash: saved.content_hash,
  })
  if (data.finalized_rule_package_id !== saved.id || data.project_id !== saved.project_id || data.content_hash !== saved.content_hash || !data.registry) {
    throw new Error('对外编号与当前规则包不一致，请刷新后重新导出。')
  }
  return data.registry
}
