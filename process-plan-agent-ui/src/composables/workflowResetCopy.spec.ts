import { describe, expect, it } from 'vitest'
import {
  ruleFinalizeResetCopy,
  secondStepResetCopy,
  thirdStepResetCopy,
} from './workflowResetCopy'

describe('workflow reset copy', () => {
  it('explains every downstream artifact rebuilt after rerunning step two', () => {
    expect(secondStepResetCopy.keepItems).toEqual([
      '上传文件',
      '已提取的文档工序明细',
      '已导入的分组模板文件',
    ])
    expect(secondStepResetCopy.clearItems).toEqual([
      '第二步归并结果和标准路线',
      '第三步问答与因素审核（需重新回答）',
      '第四步模板分组映射关系（需重新完成）',
      '第五步规则定稿与规则包（需重新回答、确认并发布）',
      '第六步验证结果（需基于新规则包重新生成）',
    ])
    expect(secondStepResetCopy.description).toContain('第三步和第五步需要重新回答、确认')
    expect(secondStepResetCopy.description).toContain('规则包发布后再重新生成路线')
  })

  it('keeps the route and template mapping when all third-step questions are answered again', () => {
    expect(thirdStepResetCopy.keepItems).toContain('已完成的模板分组映射')
    expect(thirdStepResetCopy.clearItems).toEqual([
      '第三步全部问答与因素审核（需重新回答）',
      '第五步规则定稿与规则包（需重新回答、确认并发布）',
      '第六步已生成路线（需基于新规则包重新生成）',
    ])
    expect(thirdStepResetCopy.description).toContain('保留第二步路线和第四步模板映射')
    expect(thirdStepResetCopy.description).toContain('重新回答并发布第五步规则包')
  })

  it('describes rule-finalization re-recognition without using the old step numbers', () => {
    expect(ruleFinalizeResetCopy.title).toBe('重新识别规则定稿中的全部规则？')
    expect(ruleFinalizeResetCopy.keepItems).toContain('已完成的模板分组映射')
    expect(ruleFinalizeResetCopy.clearItems).toEqual([
      '普通规则候选及确认状态（需重新识别、回答并确认）',
      '当前规则包（需重新发布）',
      '第六步已生成路线（需基于新规则包重新生成）',
    ])
    expect(ruleFinalizeResetCopy.description).toContain('普通规则需要重新识别、回答并确认')
    expect(ruleFinalizeResetCopy.description).toContain('重新发布规则包')
  })
})
