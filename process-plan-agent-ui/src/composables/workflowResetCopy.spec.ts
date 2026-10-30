import { describe, expect, it } from 'vitest'
import {
  ruleFinalizeResetCopy,
  secondStepResetCopy,
  thirdStepResetCopy,
} from './workflowResetCopy'

describe('workflow reset copy', () => {
  it('requires a new group template import after rerunning step two', () => {
    expect(secondStepResetCopy.keepItems).toEqual([
      '上传文件',
      '已提取的文档工序明细',
    ])
    expect(secondStepResetCopy.clearItems).toEqual([
      '第二步归并结果和标准路线',
      '第三步问答与因素审核（需重新回答）',
      '已导入的分组模板文件（需重新导入）',
      '第四步模板分组映射关系（需重新完成）',
      '第五步规则定稿与规则包（需重新回答、确认并发布）',
      '第六步验证结果（需基于新规则包重新生成）',
    ])
    expect(secondStepResetCopy.description).toContain('重新导入模板')
  })

  it('requires a new group template import after rerunning step three', () => {
    expect(thirdStepResetCopy.keepItems).not.toContain('已导入的分组模板文件')
    expect(thirdStepResetCopy.clearItems).toEqual([
      '第三步全部问答与因素审核（需重新回答）',
      '已导入的分组模板文件（需重新导入）',
      '第四步模板分组映射关系（需重新完成）',
      '第五步规则定稿与规则包（需重新回答、确认并发布）',
      '第六步已生成路线（需基于新规则包重新生成）',
    ])
    expect(thirdStepResetCopy.description).toContain('完成第四步模板映射')
    expect(thirdStepResetCopy.description).toContain('确认并发布第五步规则包')
  })

  it('describes rule-finalization re-recognition without using the old step numbers', () => {
    expect(ruleFinalizeResetCopy.title).toBe('重新识别尚未确认的规则？')
    expect(ruleFinalizeResetCopy.keepItems).toContain('已完成的模板分组映射')
    expect(ruleFinalizeResetCopy.keepItems).toContain('仍然有效的已确认规则（含人工修改）')
    expect(ruleFinalizeResetCopy.clearItems).toEqual([
      '尚未确认或已失效的规则候选（需重新识别、回答并确认）',
      '当前规则包（需重新发布）',
      '第六步已生成路线（需基于新规则包重新生成）',
    ])
    expect(ruleFinalizeResetCopy.description).toContain('仅重新识别尚未确认或已失效的规则')
    expect(ruleFinalizeResetCopy.description).toContain('重新发布规则包')
  })
})
