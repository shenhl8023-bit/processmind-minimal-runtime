import { beforeEach, describe, expect, it, vi } from 'vitest'

const api = vi.hoisted(() => ({ get: vi.fn(), put: vi.fn() }))
vi.mock('@/api/client', () => ({ api, apiBaseUrl: '' }))

import { commitGroupTemplate, getLatestFinalizedRulePackage, saveGroupTemplateMappings, saveGroupTemplateStepMappings } from './extract'
import { clearAllWorkflowDataCache, getWorkflowDataRevision } from '@/composables/workflowDataCache'

const writes = [
  ['template replacement', () => commitGroupTemplate(12, new File(['<xml/>'], 'template.xml'), 'hash', 4, 3)],
  ['legacy mappings', () => saveGroupTemplateMappings(12, 4, [], 3)],
  ['step mappings and precision', () => saveGroupTemplateStepMappings(12, 4, [], [], 3)],
] as const

describe('template writes invalidate published-package caches', () => {
  beforeEach(() => {
    clearAllWorkflowDataCache()
    api.get.mockReset()
    api.put.mockReset()
  })

  it.each(writes)('rereads the retired package after saving %s', async (_name, write) => {
    api.get.mockResolvedValueOnce({ data: { project_id: 12, version: 5, status: 'published' } })
    await getLatestFinalizedRulePackage(12)
    expect((await getLatestFinalizedRulePackage(12)).version).toBe(5)
    const revision = getWorkflowDataRevision()
    api.put.mockResolvedValueOnce({ data: { project_id: 12, template_revision: 5 } })
    await write()
    api.get.mockRejectedValueOnce({ response: { status: 404 } })
    await expect(getLatestFinalizedRulePackage(12)).rejects.toMatchObject({ response: { status: 404 } })
    expect(getWorkflowDataRevision()).toBeGreaterThan(revision)
  })

  it.each(writes)('retains the cached package after a rejected %s write', async (_name, write) => {
    api.get.mockResolvedValueOnce({ data: { project_id: 12, version: 5, status: 'published' } })
    await getLatestFinalizedRulePackage(12)
    const revision = getWorkflowDataRevision()
    api.put.mockRejectedValueOnce({ response: { status: 409 } })
    await expect(write()).rejects.toMatchObject({ response: { status: 409 } })
    expect((await getLatestFinalizedRulePackage(12)).version).toBe(5)
    expect(getWorkflowDataRevision()).toBe(revision)
    expect(api.get).toHaveBeenCalledTimes(1)
  })

  it.each([false, true])('does not restore an old read after saving (cache already populated: %s)', async populated => {
    if (populated) {
      api.get.mockResolvedValueOnce({ data: { project_id: 12, version: 5, status: 'published' } })
      await getLatestFinalizedRulePackage(12)
    }
    let finish!: (result: any) => void
    api.get.mockReturnValueOnce(new Promise(resolve => { finish = resolve }))
    const oldRead = getLatestFinalizedRulePackage(12, true)
    api.put.mockResolvedValueOnce({ data: { project_id: 12, template_revision: 5 } })
    await saveGroupTemplateStepMappings(12, 4, [], [], 3)
    finish({ data: { project_id: 12, version: 5, status: 'published' } })
    await oldRead
    api.get.mockRejectedValueOnce({ response: { status: 404 } })
    await expect(getLatestFinalizedRulePackage(12)).rejects.toMatchObject({ response: { status: 404 } })
  })
})

it('saves hidden full-route keys and explicit leaf paths in the same revision-scoped mapping request', async () => {
  api.put.mockResolvedValueOnce({ data: { template_revision: 5, hidden_step_keys: ['a.s1'], waived_group_paths: [['A', '孔']] } })
  const exceptions = { hidden_step_keys: ['a.s1'], waived_group_paths: [['A', '孔']] }
  const save = saveGroupTemplateStepMappings as (...args: any[]) => Promise<any>
  const result = await save(12, 4, [], [], 3, exceptions)
  expect(api.put).toHaveBeenLastCalledWith('/api/extract/group-templates/step-mappings', {
    project_id: 12, expected_template_revision: 4, expected_workflow_revision: 3,
    mappings: [], operations: [], replace_all: true, ...exceptions,
  })
  expect(result.hidden_step_keys).toEqual(['a.s1'])
  expect(result.waived_group_paths).toEqual([['A', '孔']])
})
