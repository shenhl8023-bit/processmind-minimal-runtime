import { expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn() }))
vi.mock('./client', () => ({ api }))
import { getLatestExecutableRuleRevision, saveExecutableRuleRevision, exportExecutableRuleRevision, getCurrentGenerationResults } from './executableRules'

it('reads the latest rule revision and uses its independent counter when saving', async () => {
  api.get.mockResolvedValueOnce({ data: { id: 9, revision: 3, generation_ready: false } })
  api.post.mockResolvedValueOnce({ data: { id: 10, revision: 4 } })
  const current = await getLatestExecutableRuleRevision(4)
  expect(current?.revision).toBe(3)
  await saveExecutableRuleRevision({ project_id: 4, expected_workflow_revision: 2 } as any, 3)
  expect(api.post).toHaveBeenCalledWith('/api/extract/executable-rule-revisions', { project_id: 4, expected_workflow_revision: 2, expected_executable_revision: 3 })
})
it('exports a validated revision using its hash and reads only current generated results', async () => {
  api.post.mockResolvedValueOnce({ data: { version: 2 } })
  api.get.mockResolvedValueOnce({ data: { executable_revision_id: 9, results: [] } })
  await exportExecutableRuleRevision(9, { project_id: 4, expected_workflow_revision: 2, expected_content_hash: 'hash', include_template_mapping: false })
  expect(api.post).toHaveBeenCalledWith('/api/extract/executable-rule-revisions/9/export', { project_id: 4, expected_workflow_revision: 2, expected_content_hash: 'hash', include_template_mapping: false })
  await getCurrentGenerationResults(4)
  expect(api.get).toHaveBeenLastCalledWith('/api/generate/results', { params: { project_id: 4 } })
})
