import { describe, expect, it } from 'vitest'

import type { CompileRulePackageResponse, RulePackageV2 } from '@/api'
import {
  buildExportReview,
  type RulePackageExportReview,
} from './useFinalizeRulePackageExport'
import { useRulePackageExportReview } from './useRulePackageExportReview'

const rulePackage: RulePackageV2 = {
  manifest: {},
  input_schema: { schema_version: '2.0', fields: [] },
  route_catalog: {
    schema_version: '2.0',
    processes: [{ process_id: 'process_hone', display_name: '珩孔' }],
  },
  route_rules: {
    schema_version: '2.0',
    rules: [{
      rule_id: 'rule_hone',
      source: 'user_confirmed',
      source_segment_id: 'process_hone',
      source_text: '当需要珩孔时，安排珩孔工序',
      when: { field: 'cad.features', op: 'contains', value: '珩孔', factor_id: null },
      then: { include_process_ids: ['process_hone'] },
    }],
  },
  test_cases: [],
}

function compiled(options: {
  validationValid: boolean
  kmaiValid: boolean
  errors?: Array<{ code: string; path?: string; message: string }>
}): CompileRulePackageResponse {
  return {
    package: rulePackage,
    content_hash: 'review',
    validation: { valid: options.validationValid, errors: [], warnings: [], test_results: [] },
    kmai_compatibility: {
      format: 'kmai-v1',
      valid: options.kmaiValid,
      target_directory: 'rules',
      errors: options.errors || [],
      warnings: [],
      files: {},
      factor_catalog_version: '2026.11',
    },
  }
}

const readyReview = { status: 'ready', projectName: '项目 A' } as RulePackageExportReview
const blockedReview = { status: 'blocked', projectName: '项目 A' } as RulePackageExportReview

describe('useRulePackageExportReview', () => {
  it('has only ready and blocked states', () => {
    const ready = buildExportReview(compiled({ validationValid: true, kmaiValid: true }), '项目 A')
    const blocked = buildExportReview(compiled({
      validationValid: true,
      kmaiValid: false,
      errors: [{
        code: 'standard_factor_unbound',
        path: 'route_rules.rules[0].when',
        message: '未绑定标准因子',
      }],
    }), '项目 A')

    expect(ready.status).toBe('ready')
    expect(blocked.status).toBe('blocked')
    expect(['ready', 'blocked']).toContain(ready.status)
    expect(['ready', 'blocked']).toContain(blocked.status)
  })

  it('maps a backend rule error back to its fourth-step card', () => {
    const review = buildExportReview(compiled({
      validationValid: true,
      kmaiValid: false,
      errors: [{
        code: 'standard_factor_unbound',
        path: 'route_rules.rules[0].when',
        message: '未绑定标准因子',
      }],
    }), '项目 A')

    expect(review.details).toEqual([{
      code: 'standard_factor_unbound',
      message: '未绑定标准因子',
      processName: '珩孔',
      sourceText: '当需要珩孔时，安排珩孔工序',
      sourceSegmentId: 'process_hone',
    }])
  })

  it('resolves the active review and clears its state', async () => {
    const state = useRulePackageExportReview()
    const pending = state.request(readyReview)

    expect(state.review.value).toStrictEqual(readyReview)
    expect(state.visible.value).toBe(true)

    state.complete(true)

    await expect(pending).resolves.toBe(true)
    expect(state.visible.value).toBe(false)
    expect(state.review.value).toBeNull()
  })

  it('cancels an older pending review before opening the next one', async () => {
    const state = useRulePackageExportReview()
    const first = state.request(readyReview)
    const second = state.request(blockedReview)

    await expect(first).resolves.toBe(false)
    expect(state.review.value).toStrictEqual(blockedReview)

    state.complete(false)
    await expect(second).resolves.toBe(false)
  })
})
