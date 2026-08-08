import { getOptionalLatestFinalizedRulePackage } from '@/api'
import { getFinalizedRulePackageStatus } from '@/api/rulePackages'

export async function loadGenerateRulePackageContext(
  projectId: number,
  forceRefresh = false,
) {
  const status = await getFinalizedRulePackageStatus(projectId)
  if (!status.can_generate) {
    const blocker = status.blockers.find(item => item.blocks.includes('generate'))
    return {
      status,
      rulePackage: null,
      blockerMessage: blocker?.message || '当前规则包不可用于路线生成。',
    }
  }

  const rulePackage = await getOptionalLatestFinalizedRulePackage(projectId, forceRefresh)
  return {
    status,
    rulePackage,
    blockerMessage: rulePackage ? '' : '当前任务没有可用的已发布规则包。',
  }
}
