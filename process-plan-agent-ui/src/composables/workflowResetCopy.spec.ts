import { describe, expect, it } from 'vitest'
import { computed } from 'vue'
import { parse } from '@vue/compiler-sfc'
import ts from 'typescript'
import extractSource from '@/views/ExtractView.vue?raw'
import analysisSource from '@/views/AnalysisView.vue?raw'
import finalizeSource from '@/views/FinalizeView.vue?raw'
import { productStatus, templateMappingEnabled, templateMappingVisible } from './productStatus'
import {
  resetCopyForEdition,
  ruleFinalizeResetCopy,
  secondStepResetCopy,
  thirdStepResetCopy,
} from './workflowResetCopy'

describe('workflow reset copy', () => {
  it.each([
    ['secondStepResetCopy', extractSource],
    ['thirdStepResetCopy', analysisSource],
    ['ruleFinalizeResetCopy', finalizeSource],
  ])('uses current mapping visibility in the actual %s page binding', (name, source) => {
    const script = ts.createSourceFile('view.ts', parse(source).descriptor.scriptSetup!.content, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
    const declaration = script.statements.filter(ts.isVariableStatement)
      .flatMap(statement => Array.from(statement.declarationList.declarations))
      .find(node => node.name.getText(script) === name)!
    const code = ts.transpile(`return ${declaration.initializer!.getText(script)}`, { target: ts.ScriptTarget.ES2022 })
    const copy = new Function('computed', 'resetCopyForEdition', 'templateMappingEnabled', 'templateMappingVisible', code)(
      computed, resetCopyForEdition, templateMappingEnabled, templateMappingVisible,
    )
    const previous = productStatus.value
    try {
      productStatus.value = {
        edition: 'full', template_mapping_enabled: false, expires_at: null,
        expired: false, server_time: '2026-11-17T03:00:00Z',
      }
      expect(templateMappingEnabled.value).toBe(true)
      expect(JSON.stringify(copy.value)).not.toMatch(/模板|第六步|第6步/)
      expect(copy.value.clearItems.some((item: string) => item.includes('第五步'))).toBe(true)
      productStatus.value = { ...productStatus.value, template_mapping_enabled: true }
      expect(JSON.stringify(copy.value)).toContain('模板')
      productStatus.value = { ...productStatus.value, template_mapping_enabled: false }
      expect(JSON.stringify(copy.value)).not.toMatch(/模板|第六步|第6步/)
    } finally {
      productStatus.value = previous
    }
  })

  it.each(['route', 'analysis', 'finalize'] as const)('describes the basic %s reset without template work or a sixth display step', kind => {
    const copy = resetCopyForEdition(kind, false)
    expect(JSON.stringify(copy)).not.toMatch(/模板|第六步/)
    expect(copy.clearItems.some(item => item.includes('第五步'))).toBe(true)
    if (kind !== 'finalize') expect(copy.clearItems.some(item => item.includes('第四步规则定稿'))).toBe(true)
  })

  it('retains the full edition reset descriptions', () => {
    expect(resetCopyForEdition('route', true)).toBe(secondStepResetCopy)
    expect(resetCopyForEdition('analysis', true)).toBe(thirdStepResetCopy)
    expect(resetCopyForEdition('finalize', true)).toBe(ruleFinalizeResetCopy)
  })
  it('requires a new group template import after rerunning step two', () => {
    expect(secondStepResetCopy.keepItems).toEqual([
      '上传文件',
      '已提取的文档工序明细',
    ])
    expect(secondStepResetCopy.clearItems).toEqual([
      '第二步归并结果和标准路线',
      '第三步问答与因素审核（需重新回答）',
      '已导入的分组模板文件（需重新导入）',
      '第四步规则定稿及可验证规则（需重新回答、确认）',
      '第五步验证结果（需使用新规则重新生成）',
      '第六步可选模板映射关系（需要时重新完成）',
    ])
    expect(secondStepResetCopy.description).toContain('模板映射仍为最后的可选步骤')
  })

  it('requires a new group template import after rerunning step three', () => {
    expect(thirdStepResetCopy.keepItems).not.toContain('已导入的分组模板文件')
    expect(thirdStepResetCopy.clearItems).toEqual([
      '第三步全部问答与因素审核（需重新回答）',
      '已导入的分组模板文件（需重新导入）',
      '第四步规则定稿及可验证规则（需重新确认）',
      '第五步已生成路线（需使用新规则重新生成）',
      '第六步可选模板映射关系（需要时重新完成）',
    ])
    expect(thirdStepResetCopy.description).toContain('完成第四步规则定稿')
    expect(thirdStepResetCopy.description).toContain('第五步重新生成路线验证')
  })

  it('describes rule-finalization re-recognition without using the old step numbers', () => {
    expect(ruleFinalizeResetCopy.title).toBe('重新识别尚未确认的规则？')
    expect(ruleFinalizeResetCopy.keepItems).toContain('已完成的模板分组映射')
    expect(ruleFinalizeResetCopy.keepItems).toContain('仍然有效的已确认规则（含人工修改）')
    expect(ruleFinalizeResetCopy.clearItems).toEqual([
      '尚未确认或已失效的规则候选（需重新识别、回答并确认）',
      '当前可验证规则版本（需重新保存）',
      '第五步已生成路线（需使用当前规则重新生成）',
    ])
    expect(ruleFinalizeResetCopy.description).toContain('仅重新识别尚未确认或已失效的规则')
    expect(ruleFinalizeResetCopy.description).toContain('到第五步使用当前规则重新生成路线验证')
  })
})
