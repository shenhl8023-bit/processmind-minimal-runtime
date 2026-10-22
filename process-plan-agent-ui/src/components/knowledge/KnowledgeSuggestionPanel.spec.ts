import { describe, expect, it } from 'vitest'
import { createSSRApp, h } from 'vue'
import { renderToString } from 'vue/server-renderer'
import type { KnowledgeEvidence, KnowledgeSuggestion } from '@/api/knowledge'
import KnowledgeSuggestionPanel from './KnowledgeSuggestionPanel.vue'

const suggestion: KnowledgeSuggestion = {
  id: 7, project_id: 17, route_version_id: 42, segment_id: 'heat-treatment',
  title: '真空淬火要求', suggestion_text: '真空淬火后硬度不低于 56 HRC。',
  candidate: null, evidence_ids: [3], status: 'confirmed', created_by: '工艺员',
  updated_by: '审核人', created_at: '2026-10-15T00:00:00Z', updated_at: '2026-10-15T01:00:00Z',
}
const evidence: KnowledgeEvidence = {
  id: 3, project_id: 17, route_version_id: 42, segment_id: 'heat-treatment',
  query: '真空淬火要求', item_id: 'chunk-3', content: '真空淬火，硬度 ≥56 HRC。',
  document_id: 'document-9', document_name: '热处理工艺.pdf', page_no: 23,
  identity: 'heat:v2:p23', retrieval_method: 'hybrid', snapshot_hash: 'hash-3',
  retrieved_at: '2026-10-15T00:00:00Z',
}

async function renderPanel(overrides: Record<string, unknown> = {}) {
  return renderToString(createSSRApp({
    render: () => h(KnowledgeSuggestionPanel, {
      suggestions: [suggestion], evidence: [evidence], projectId: 17, routeVersionId: 42,
      segmentId: 'heat-treatment', ...overrides,
    }),
  }))
}

function applyButton(html: string) {
  return html.match(/<button\b[^>]*>\s*带入当前条件\s*<\/button>/)?.[0] || ''
}

describe('knowledge suggestion panel', () => {
  it('shows reviewed text and traceable source before enabling a matching confirmed suggestion', async () => {
    const html = await renderPanel()
    expect(html).toContain('真空淬火要求')
    expect(html).toContain('真空淬火后硬度不低于 56 HRC。')
    expect(html).toContain('已确认建议')
    expect(html).toContain('审核人')
    expect(html).toContain('2026-10-15T01:00:00Z')
    expect(html).toContain('真空淬火，硬度 ≥56 HRC。')
    expect(html).toContain('热处理工艺.pdf')
    expect(html).toContain('第 23 页')
    expect(html).toContain('heat:v2:p23')
    expect(applyButton(html)).not.toBe('')
    expect(applyButton(html)).not.toContain('disabled')
  })

  it.each(['draft', 'pending_review', 'rejected', 'stale'] as const)(
    'keeps %s suggestions visible without permitting application', async status => {
      const html = await renderPanel({ suggestions: [{ ...suggestion, status }] })
      expect(html).toContain('真空淬火要求')
      expect(applyButton(html)).toContain('disabled')
      expect(html).toContain('建议')
    },
  )

  it('hides evidence from a different segment and blocks incomplete evidence application', async () => {
    const html = await renderPanel({
      evidence: [{ ...evidence, segment_id: 'other', content: '不可串用的其它工序原文' }],
    })
    expect(html).not.toContain('不可串用的其它工序原文')
    expect(html).toContain('依据缺失或不属于当前项目、路线和工序')
    expect(applyButton(html)).toContain('disabled')
  })

  it('shows unknown source location honestly and still preserves the adopted excerpt', async () => {
    const html = await renderPanel({ evidence: [{ ...evidence, document_name: null, page_no: null, identity: null }] })
    expect(html).toContain('真空淬火，硬度 ≥56 HRC。')
    expect(html).toContain('document-9')
    expect(html).toContain('来源页码定位不可用')
    expect(html).not.toContain('第 23 页')
  })

  it('blocks a suggestion with no adopted evidence, a mismatched context, or an operation in progress', async () => {
    const emptyEvidence = await renderPanel({ suggestions: [{ ...suggestion, evidence_ids: [] }] })
    const wrongContext = await renderPanel({ routeVersionId: 43 })
    const busy = await renderPanel({ busy: true })
    expect(applyButton(emptyEvidence)).toContain('disabled')
    expect(applyButton(wrongContext)).toContain('disabled')
    expect(wrongContext).toContain('建议不属于当前项目、路线和工序')
    expect(applyButton(busy)).toContain('disabled')
  })
})
