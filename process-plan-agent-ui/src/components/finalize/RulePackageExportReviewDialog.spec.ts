import { createSSRApp } from 'vue'
import { renderToString, type SSRContext } from '@vue/server-renderer'
import { describe, expect, it } from 'vitest'

import type { RulePackageExportReview } from '@/composables/useFinalizeRulePackageExport'
import RulePackageExportReviewDialog from './RulePackageExportReviewDialog.vue'

function review(status: RulePackageExportReview['status']): RulePackageExportReview {
  return {
    status,
    projectName: '轴类零件示例',
    processCount: 3,
    ruleCount: 2,
    validation: {
      valid: status === 'ready',
      errors: [],
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
      factor_catalog_version: '2026.11',
    },
    manualFactors: status === 'ready'
      ? [{ key: 'manual_requires_hone', name: '需要珩孔' }]
      : [],
    rulePackage: null,
    details: status === 'blocked'
      ? [{
          code: 'standard_factor_unbound',
          message: '未绑定标准因子',
          processName: '珩孔',
          sourceText: '当需要珩孔时，安排珩孔工序',
          sourceSegmentId: 'process_hone',
        }]
      : [],
  }
}

async function renderReview(value: RulePackageExportReview) {
  const context: SSRContext = {}
  await renderToString(createSSRApp(RulePackageExportReviewDialog, {
    modelValue: true,
    review: value,
  }), context)
  return context.teleports?.body || ''
}

describe('RulePackageExportReviewDialog', () => {
  it('shows ready manual factors as an informational override summary', async () => {
    const html = await renderReview(review('ready'))

    expect(html).toContain('审核通过')
    expect(html).toContain('manual.factor_overrides')
    expect(html).toContain('manual_requires_hone')
    expect(html).toContain('需要珩孔')
    expect(html).toMatch(/<button[^>]*>\s*确认导出\s*<\/button>/)
  })

  it('shows structured blockers with a fourth-step locate action', async () => {
    const html = await renderReview(review('blocked'))

    expect(html).toContain('审核未通过')
    expect(html).toContain('珩孔')
    expect(html).toContain('当需要珩孔时，安排珩孔工序')
    expect(html).toContain('未绑定标准因子')
    expect(html).toContain('返回第四步处理')
    expect(html).toMatch(/<button[^>]*disabled[^>]*>\s*确认导出\s*<\/button>/)
    expect((RulePackageExportReviewDialog as any).emits).toContain('locate')
  })

  it('does not render the retired mapping workflow', async () => {
    const html = await renderReview(review('blocked'))

    expect(html).not.toContain('作用范围')
    expect(html).not.toContain('绑定已有因子')
    expect(html).not.toContain('创建手工布尔因子')
    expect(html).not.toContain('正在保存映射')
  })
})
