import { createSSRApp } from 'vue'
import { renderToString, type SSRContext } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

vi.mock('@/api/kmaiFactorMappings', async () => {
  const actual = await vi.importActual<typeof import('@/api/kmaiFactorMappings')>('@/api/kmaiFactorMappings')
  return {
    ...actual,
    getKmaiFactorCatalog: vi.fn().mockResolvedValue([]),
  }
})

import type { RulePackageExportReview } from '@/composables/useFinalizeRulePackageExport'
import RulePackageExportReviewDialog from './RulePackageExportReviewDialog.vue'

const rulePackage = {
  manifest: {},
  input_schema: { schema_version: '2.0' as const, fields: [] },
  route_catalog: { schema_version: '2.0' as const, processes: [] },
  route_rules: { schema_version: '2.0' as const, rules: [] },
  test_cases: [],
}

function review(status: RulePackageExportReview['status']): RulePackageExportReview {
  return {
    status,
    projectName: '轴类零件示例',
    processCount: 3,
    ruleCount: 2,
    validation: {
      valid: status !== 'blocked',
      errors: status === 'blocked'
        ? [{ code: 'invalid_rule', message: '存在未通过校验的规则' }]
        : [],
      warnings: [],
      test_results: [],
    },
    kmaiCompatibility: {
      format: 'kmai-v1',
      valid: status === 'ready',
      target_directory: 'rules',
      errors: [],
      warnings: [],
      files: {},
      mapping_signature: 'test',
      mapping_usages: [],
    },
    mappingIssues: [],
    rulePackage,
  }
}

async function renderReview(value: RulePackageExportReview) {
  const context: SSRContext = {}
  await renderToString(createSSRApp(RulePackageExportReviewDialog, {
    modelValue: true,
    review: value,
    projectId: 12,
    allowGlobal: false,
  }), context)
  return context.teleports?.body || ''
}

describe('RulePackageExportReviewDialog', () => {
  it('renders the ready review in Chinese with an enabled confirmation', async () => {
    const html = await renderReview(review('ready'))

    expect(html).toContain('审核并导出规则包')
    expect(html).toContain('审核通过')
    expect(html).toContain('轴类零件示例')
    expect(html).toContain('3 道')
    expect(html).toContain('2 条')
    expect(html).toMatch(/<button[^>]*>确认导出<\/button>/)
    expect(html).not.toContain('Resolve KmAI factor mappings')
  })

  it('renders mapping controls in Chinese and waits for a complete selection', async () => {
    const value = review('mapping_required')
    value.mappingIssues = [{
      field: 'cad.features',
      value: '装夹定位中心孔',
      occurrences: 2,
      rule_refs: ['route_rules.rules[1]', 'route_rules.rules[4]'],
      can_create_manual_factor: true,
    }]
    const html = await renderReview(value)

    expect(html).toContain('需要处理 1 项 KmAI 因子映射')
    expect(html).toContain('作用范围')
    expect(html).toContain('处理方式')
    expect(html).toContain('绑定已有因子')
    expect(html).toContain('创建手工布尔因子')
    expect(html).toMatch(/<button[^>]*disabled[^>]*>确认导出<\/button>/)
  })

  it('renders blocked errors in Chinese and disables export', async () => {
    const html = await renderReview(review('blocked'))

    expect(html).toContain('审核未通过')
    expect(html).toContain('存在未通过校验的规则')
    expect(html).toMatch(/<button[^>]*disabled[^>]*>确认导出<\/button>/)
  })
})
