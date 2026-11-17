import { expect, it } from 'vitest'
import { getWorkflowSteps, availableWorkflowStep } from './workflowSteps'
it('places optional template mapping after route validation in both visible and guarded order', () => {
  expect(getWorkflowSteps().map(s => [s.internalStep, s.path])).toEqual([[1, '/upload'], [2, '/extract'], [3, '/analysis'], [4, '/finalize'], [5, '/generate'], [6, '/template-mapping']])
  expect(getWorkflowSteps(false).map(s => s.number)).toEqual([1, 2, 3, 4, 5])
  expect(getWorkflowSteps(false).slice(-1)[0]?.path).toBe('/generate')
  expect(availableWorkflowStep(4).path).toBe('/finalize')
  expect(availableWorkflowStep(5).path).toBe('/generate')
  expect(getWorkflowSteps().slice(-1)[0]?.label).toContain('可选')
})
