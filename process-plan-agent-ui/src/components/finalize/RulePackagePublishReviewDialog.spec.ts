import { createSSRApp, ssrContextKey } from 'vue'
import { renderToString, type SSRContext } from '@vue/server-renderer'
import { describe, expect, it, vi } from 'vitest'

import type { RulePackagePublishReview } from '@/composables/useFinalizeRulePackagePublish'
import RulePackagePublishReviewDialog from './RulePackagePublishReviewDialog.vue'

function review(status: RulePackagePublishReview['status']): RulePackagePublishReview {
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

async function renderReview(value: RulePackagePublishReview) {
  const context: SSRContext = {}
  await renderToString(createSSRApp(RulePackagePublishReviewDialog, {
    modelValue: true,
    review: value,
  }), context)
  return context.teleports?.body || ''
}

describe('RulePackagePublishReviewDialog', () => {
  it('shows ready manual factors as an informational override summary', async () => {
    const html = await renderReview(review('ready'))

    expect(html).toContain('审核通过')
    expect(html).toContain('审核并发布规则包')
    expect(html).toContain('确认后将发布规则包')
    expect(html).toContain('manual.factor_overrides')
    expect(html).toContain('manual_requires_hone')
    expect(html).toContain('需要珩孔')
    expect(html).toMatch(/<button[^>]*>\s*确认发布\s*<\/button>/)
    expect(html).not.toContain('确认导出')
  })

  it('shows structured blockers with a fourth-step locate action', async () => {
    const html = await renderReview(review('blocked'))

    expect(html).toContain('审核未通过')
    expect(html).toContain('珩孔')
    expect(html).toContain('当需要珩孔时，安排珩孔工序')
    expect(html).toContain('未绑定标准因子')
    expect(html).toContain('返回第四步处理')
    expect(html).toMatch(/<button[^>]*disabled[^>]*>\s*确认发布\s*<\/button>/)
    expect((RulePackagePublishReviewDialog as any).emits).toContain('locate')
  })

  it('emits the selected source segment through the locate button handler', () => {
    const emit = vi.fn()
    const app = createSSRApp({ render: () => null })
    app.provide(ssrContextKey, { modules: new Set<string>() })
    const setupState = app.runWithContext(() => (RulePackagePublishReviewDialog as any).setup(
      { modelValue: true, review: review('blocked') },
      { emit, expose: () => {} },
    ))

    setupState.locate('process_hone')

    expect(emit).toHaveBeenCalledWith('locate', 'process_hone')
  })

  it('offers a return-to-step-four action for a generic blocker', async () => {
    const blocked = review('blocked')
    blocked.details[0]!.sourceSegmentId = ''

    const html = await renderReview(blocked)

    expect(html).toMatch(/<button[^>]*class="blocker-locate"[^>]*>\s*返回第四步处理\s*<\/button>/)
  })

  it('does not render the retired mapping workflow', async () => {
    const html = await renderReview(review('blocked'))

    expect(html).not.toContain('作用范围')
    expect(html).not.toContain('绑定已有因子')
    expect(html).not.toContain('创建手工布尔因子')
    expect(html).not.toContain('正在保存映射')
  })
})
