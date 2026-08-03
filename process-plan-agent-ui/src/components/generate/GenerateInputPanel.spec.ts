import { createSSRApp } from 'vue'
import { renderToString } from 'vue/server-renderer'
import { describe, expect, it } from 'vitest'
import GenerateInputPanel from './GenerateInputPanel.vue'
import source from './GenerateInputPanel.vue?raw'

const baseProps = (inputFields = [
  { key: 'material', name: '材料牌号', type: 'string', required: true },
  { key: 'has_hole', name: '是否有内孔', type: 'boolean', required: true },
  { key: 'precision', name: '尺寸精度', type: 'string', required: true },
  { key: 'need_trace', name: '是否需要追溯标卡', type: 'bool', required: false },
]) => ({
  projectId: 1,
  projectName: '测试项目',
  inputFields,
  filledFieldCount: 2,
  canGenerate: true,
  hasRulePackage: true,
  generating: false,
  schemaStatusText: '',
  generateHintText: '',
  fieldValues: { has_hole: true, need_trace: false },
  customInputValues: {},
  fieldTypeLabel: (field: { type: string }) => field.type,
  isTextField: (field: { type: string }) => field.type === 'string',
  isSingleSelectField: () => false,
  isArrayField: () => false,
  isBooleanField: (field: { type: string }) => field.type === 'boolean' || field.type === 'bool',
  isNumberField: () => false,
  fieldTextValue: () => '',
  fieldPlaceholder: () => '',
  fieldPreviewValue: (key: string) => key === 'has_hole' ? '是' : '',
  inputValue: () => '',
  checkedValue: () => false,
  arrayFieldValues: () => [],
  setFieldText: () => {},
  setFieldBoolean: () => {},
  toggleFieldArrayValue: () => {},
  setCustomInput: () => {},
  addCustomArrayValue: () => {},
  clearAllFields: () => {},
  fillExampleValues: () => {},
})

describe('GenerateInputPanel', () => {
  it('groups interleaved boolean fields after ordinary fields', async () => {
    const html = await renderToString(createSSRApp(GenerateInputPanel, baseProps()))

    expect(html).toContain('class="boolean-field-group"')
    expect(html).toContain('工艺选项')
    expect(html).toContain('2 项')
    expect(html).toContain('是否有内孔')
    expect(html).toContain('是否需要追溯标卡')
    expect(html.indexOf('材料牌号')).toBeLessThan(html.indexOf('boolean-field-group'))
    expect(html.indexOf('尺寸精度')).toBeLessThan(html.indexOf('boolean-field-group'))
    expect(html.indexOf('是否有内孔')).toBeGreaterThan(html.indexOf('boolean-field-group'))
  })

  it('omits the boolean group when there are no boolean fields', async () => {
    const html = await renderToString(createSSRApp(GenerateInputPanel, baseProps([
      { key: 'material', name: '材料牌号', type: 'string', required: true },
      { key: 'precision', name: '尺寸精度', type: 'string', required: true },
    ])))

    expect(html).not.toContain('boolean-field-group')
  })

  it('uses a responsive two-column boolean field grid', () => {
    expect(source).toMatch(/\.boolean-field-grid\s*\{[^}]*grid-template-columns:\s*repeat\(2,/s)
    expect(source).toMatch(/@media\s*\(max-width:\s*640px\)[\s\S]*\.boolean-field-grid\s*\{[^}]*grid-template-columns:\s*1fr;/s)
  })
})
