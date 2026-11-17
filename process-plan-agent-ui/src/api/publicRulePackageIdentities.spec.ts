import { expect, it, vi } from 'vitest'
const api = vi.hoisted(() => ({ post: vi.fn() }))
vi.mock('./client', () => ({ api }))
import { allocatePublicRulePackageIdentities } from './publicRulePackageIdentities'

it('allocates only against the immutable export identity and checks response binding', async () => {
  const saved = { id: 7, project_id: 2, content_hash: 'frozen' } as any
  const registry = { processes: { native: 'P001' }, steps: {}, factors: {} }
  api.post.mockResolvedValueOnce({ data: { finalized_rule_package_id: 7, project_id: 2, content_hash: 'frozen', registry } })
  expect(await allocatePublicRulePackageIdentities(saved)).toEqual(registry)
  expect(api.post).toHaveBeenCalledWith('/api/extract/public-rule-package-identities', { finalized_rule_package_id: 7, expected_content_hash: 'frozen' })
  api.post.mockResolvedValueOnce({ data: { finalized_rule_package_id: 8, project_id: 2, content_hash: 'frozen', registry } })
  await expect(allocatePublicRulePackageIdentities(saved)).rejects.toThrow('对外编号与当前规则包不一致')
})
