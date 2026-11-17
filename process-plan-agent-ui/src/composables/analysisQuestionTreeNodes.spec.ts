import { describe, expect, it } from 'vitest'
import { buildResultSummary } from './analysisQuestionTreeNodes'
import { buildUserFirstCondition } from './finalizeViewHelpers'

describe('question tree conditions passed to rule review', () => {
  it.each(['钻孔', '钻铰孔', '打孔'])('preserves the selected hole structure for %s', (name) => {
    const summary = buildResultSummary(name, {
      rule_reason_root: { nodeId: 'rule_reason_root', value: 'coverage_reason::structure', label: '与结构相关' },
      structure_feature_primary: { nodeId: 'structure_feature_primary', value: 'machining_feature::inner_hole', label: '孔' },
    })
    expect(summary).toBe(`当零件存在孔类结构时，纳入“${name}”工序。`)
  })

  it('does not add a requirement alternative when rebuilding a condition from hole labels', () => {
    expect(buildUserFirstCondition('钻孔', ['孔'], ['与结构相关'], []))
      .toBe('当零件存在孔类结构时，纳入“钻孔”工序。')
  })

  it.each([
    ['无损检查', '车削后或周边加工后的过程检验点'],
    ['烧伤检查', '车削后或周边加工后的过程检验点'],
    ['去毛刺', '车削或机械加工后，需要清理毛刺和残留'],
    ['检验', '粗加工或中间转序后的过程检验点'],
  ])('does not compare a selected requirement scene with itself for %s', (name, scene) => {
    const summary = buildResultSummary(name, {
      rule_reason_root: { nodeId: 'rule_reason_root', value: 'coverage_reason::requirement', label: '与工艺/质量要求相关' },
      requirement_scene_type: { nodeId: 'requirement_scene_type', value: 'requirement_gate::process_check', label: scene },
    })
    expect(summary).toContain(`当${scene}时，`)
    expect(summary).not.toContain('满足')
  })
})
