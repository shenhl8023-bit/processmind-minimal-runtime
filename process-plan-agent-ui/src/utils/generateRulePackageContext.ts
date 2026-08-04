type RulePackageMetadata = {
  id?: number | null
  version?: number | null
  content_hash?: string | null
}

export type PublishedRulePackageFingerprint = {
  id: number | null
  version: number | null
  contentHash: string | null
}

export const PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE =
  '规则包已更新，请重新确认输入后生成。'

export function publishedRulePackageFingerprint(
  value: RulePackageMetadata,
): PublishedRulePackageFingerprint {
  return {
    id: value.id ?? null,
    version: value.version ?? null,
    contentHash: value.content_hash || null,
  }
}

export function rulePackageExpectationPayload(
  fingerprint: PublishedRulePackageFingerprint | null,
): {
  expected_rule_package_id?: number
  expected_rule_package_version?: number
  expected_rule_package_hash?: string
} {
  if (!fingerprint) return {}

  return {
    ...(fingerprint.id !== null ? { expected_rule_package_id: fingerprint.id } : {}),
    ...(fingerprint.version !== null ? { expected_rule_package_version: fingerprint.version } : {}),
    ...(fingerprint.contentHash ? { expected_rule_package_hash: fingerprint.contentHash } : {}),
  }
}

export function isPublishedRulePackageChanged(error: any): boolean {
  return typeof error?.response?.status === 'number'
    && error.response.status === 409
    && error.response.data?.detail?.code === 'published_rule_package_changed'
}
