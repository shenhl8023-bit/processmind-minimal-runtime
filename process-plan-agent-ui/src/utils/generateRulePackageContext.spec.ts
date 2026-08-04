import { describe, expect, it } from 'vitest'

import {
  isPublishedRulePackageChanged,
  publishedRulePackageFingerprint,
  rulePackageExpectationPayload,
} from './generateRulePackageContext'

describe('generate rule package context', () => {
  it('creates all expected request keys from complete metadata', () => {
    const fingerprint = publishedRulePackageFingerprint({
      id: 41,
      version: 7,
      content_hash: 'sha256:published',
    })

    expect(rulePackageExpectationPayload(fingerprint)).toEqual({
      expected_rule_package_id: 41,
      expected_rule_package_version: 7,
      expected_rule_package_hash: 'sha256:published',
    })
  })

  it('omits only the hash when package metadata has a null hash', () => {
    const fingerprint = publishedRulePackageFingerprint({
      id: 41,
      version: 7,
      content_hash: null,
    })

    expect(rulePackageExpectationPayload(fingerprint)).toEqual({
      expected_rule_package_id: 41,
      expected_rule_package_version: 7,
    })
  })

  it('recognizes the dedicated published rule package conflict', () => {
    expect(isPublishedRulePackageChanged({
      response: {
        status: 409,
        data: { detail: { code: 'published_rule_package_changed' } },
      },
    })).toBe(true)
  })

  it('rejects a different 409 conflict detail', () => {
    expect(isPublishedRulePackageChanged({
      response: {
        status: 409,
        data: { detail: { code: 'workflow_revision_changed' } },
      },
    })).toBe(false)
  })
})
