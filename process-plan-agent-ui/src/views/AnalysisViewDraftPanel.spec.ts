import { describe, expect, it } from 'vitest'
import source from './AnalysisView.vue?raw'

describe('analysis view uses existing question tree as the only visible analysis input', () => {
  it('does not mount the standalone rule draft panel', () => {
    expect(source).not.toContain('AnalysisRuleDraftPanel')
    expect(source).not.toContain('规则草稿')
  })
})
