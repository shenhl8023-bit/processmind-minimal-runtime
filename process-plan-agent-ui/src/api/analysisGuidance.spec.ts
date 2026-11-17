import { expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn(), post: vi.fn() }))
vi.mock('./client', () => ({ api }))
import { generateAnalysisGuidance, getAnalysisGuidance, saveAnalysisGuidance } from './analysisGuidance'

it('reads and updates the project guidance API with its own configuration revision', async () => {
  api.get.mockResolvedValue({ data: { project_id: 3, configuration: { revision: 2 } } })
  api.put.mockResolvedValue({ data: { project_id: 3, configuration: { revision: 3 } } })
  const current = await getAnalysisGuidance(3)
  await saveAnalysisGuidance(3, current.configuration)
  expect(api.get).toHaveBeenCalledWith('/api/projects/3/analysis-guidance')
  expect(api.put).toHaveBeenCalledWith('/api/projects/3/analysis-guidance', { expected_configuration_revision: 2, configuration: { revision: 2 } })
})

it('requests recommendation retry explicitly while keeping normal generation cacheable', async () => {
  api.post.mockResolvedValue({ data: { project_id: 3, configuration: { revision: 3 } } })
  await generateAnalysisGuidance(3)
  await generateAnalysisGuidance(3, true)
  expect(api.post.mock.calls.map(([, , options]) => options.params?.retry_recommendations || false)).toEqual([false, true])
})
