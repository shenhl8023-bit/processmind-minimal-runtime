import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it } from 'vitest'
import source from './GenerateInputPanel.vue?raw'
import * as factorGroups from '@/composables/generateFactorGroups'

const componentModule = { exports: {} as any }
const compiled = compileScript(parse(source).descriptor, { id: 'generate-input-panel-test', inlineTemplate: true })
new Function('require', 'module', 'exports', transformSync(compiled.content, { loader: 'ts', format: 'cjs' }).code)(
  (id: string) => { if (id === 'vue') return Vue; if (id === '@/composables/generateFactorGroups') return factorGroups; throw new Error(id) }, componentModule, componentModule.exports,
)

function render(hasRulePackage: boolean, canGenerate: boolean, finalizeStepNumber = 5, overrides: Record<string, any> = {}) {
  const noop = () => {}
  const props = {
    projectId: 6, projectName: '固定路线', inputFields: [], filledFieldCount: 0,
    canGenerate, hasRulePackage, finalizeStepNumber, generating: false, schemaStatusText: '无需填写参数，可直接生成。',
    generateHintText: '', fieldValues: {}, customInputValues: {}, fieldValueOrigin: () => 'unset',
    isConfirmedFieldValue: () => false, isInvalidConfirmedFieldValue: () => false,
    fieldTypeLabel: () => '', isTextField: () => false, isSingleSelectField: () => false,
    isArrayField: () => false, isBooleanField: () => false, isNumberField: () => false,
    fieldTextValue: () => '', fieldPlaceholder: () => '', inputValue: () => '', arrayFieldValues: () => [],
    setFieldText: noop, setFieldBoolean: noop, toggleFieldArrayValue: noop, setCustomInput: noop,
    addCustomArrayValue: noop, addCustomSingleValue: noop, clearAllFields: noop, fillExampleValues: noop,
  }
  return renderToString(Vue.createSSRApp(componentModule.exports.default, {...props,...overrides}))
}

describe('fixed route generation panel', () => {
  it('labels neutral factors using the saved process catalog', async () => {
    const { projectConditionScope } = await import('@/utils/projectConditionFields')
    const html = await render(true, true, 4, {
      inputFields: [{ key: `${projectConditionScope('drill')}.features`, name: '加工对象的特征', type: 'multi_select' }],
      processDefinitions: [{ process_id: 'drill', display_name: '钻孔' }],
    })
    expect(html).toMatch(/<h4[^>]*>钻孔<\/h4>/)
    expect(html).toContain('加工对象的特征')
  })
  it('renders actual IT as six labeled choices without repeating the rule threshold', async () => {
    const html = await render(true, true, 4, { inputFields: [
      { key: 'project_factor.operation_a.it', name: '磨外圆 · 外圆柱面的实际尺寸精度等级', type: 'number', unit: 'IT', rule_hint: '当前规则：IT7及更高精度' },
    ], isNumberField: () => true, fieldValues: { 'project_factor.operation_a.it': '6' } })
    expect(html).toContain('<select')
    expect(html).not.toContain('type="number"')
    for (const grade of [5, 6, 7, 8, 9, 10]) expect(html).toContain(`value="${grade}"`)
    expect(html).toContain('IT10')
    expect(html).not.toContain('当前规则：IT7及更高精度')
  })
  it('renders the confirmed three sections and fixed precision feature context', async () => {
    const html = await render(true, true, 4, { inputFields: [
      { key: 'project_factor.material_grade', name: '材料牌号', type: 'single_select' },
      { key: 'project_factor.operation_a.it', name: '磨外圆 · 外圆柱面的实际尺寸精度等级', type: 'number', unit: 'IT' },
      { key: 'project_factor.manual_process_a', name: '是否镀铜', type: 'boolean', source: '用户直接设定' },
    ], isSingleSelectField: (field: any) => field.type === 'single_select', isNumberField: (field: any) => field.type === 'number', isBooleanField: (field: any) => field.type === 'boolean' })
    expect(html).toContain('基本信息（材料）')
    expect(html).toContain('加工因素（特征、方位、精度）')
    expect(html).toContain('人工安排')
    expect(html).toContain('加工特征：外圆柱面（已确定）')
    expect(html).toContain('当前没有已配置的材料牌号')
    expect(html).not.toContain('自定义输入')
  })
  it('returns basic users to display step four for unpublished rules', async () => {
    const html = await render(false, false, 4)
    expect(html).toContain('返回第4步')
    expect(html).not.toContain('返回第5步')
  })
  it('explains that a published zero-input route can be generated directly', async () => {
    const html = await render(true, true)
    expect(html).toContain('无需填写参数')
    expect(html).not.toContain('无法配置生成参数')
    expect(html).not.toContain('返回第')
    expect(html).toMatch(/class="generate-cta"[^>]*><span>生成工艺路线/)
  })

  it('keeps a repair action and disabled generation when no package is published', async () => {
    const html = await render(false, false)
    expect(html).toContain('无法配置生成参数')
    expect(html).toContain('返回第5步')
    expect(html).toMatch(/class="generate-cta"[^>]*disabled/)
  })
})


it('renders manual process switches as simple unchecked named checkboxes', async () => {
  const key='project_factor.manual_process_12345678'
  const html=await render(true,true,5,{
    inputFields:[{key,name:'是否需要除铜',type:'boolean',source:'用户直接设定'}],
    fieldValues:{[key]:false},isBooleanField:()=>true,
  })
  expect(html).toContain('type="checkbox"')
  expect(html).toContain('aria-label="除铜"')
  expect(html).not.toContain('默认否')
  expect(html).not.toContain('field-meta')
  expect(html).not.toContain('勾选后生成')
  expect(html).not.toContain('radiogroup')
  expect(html).not.toContain('checked')
})

it('expands only the checked concrete feature and never pre-fills its actual precision', async () => {
  const through = 'project_factor.feature_through', blind = 'project_factor.feature_blind'
  const inputFields = [
    { key: `${through}.present`, name: '孔(通孔)', type: 'boolean' },
    { key: `${through}.direction`, name: '通孔的方位', type: 'single_select', allowed_values: ['A侧', 'B侧', '所有方位'] },
    { key: `${through}.it`, name: '通孔的实际尺寸精度等级', type: 'number', unit: 'IT', rule_hint: '当前规则：IT7及更高精度。' },
    { key: `${blind}.present`, name: '孔(盲孔)', type: 'boolean' },
    { key: `${blind}.direction`, name: '盲孔的方位', type: 'single_select', allowed_values: ['A侧', 'B侧'] },
  ]
  const html = await render(true, false, 4, { inputFields, fieldValues: { [`${through}.present`]: true, [`${blind}.present`]: false } })
  expect(html).toContain('孔类')
  expect(html).toContain('aria-label="通孔"')
  expect(html).toContain('aria-label="盲孔"')
  expect(html).toContain('aria-label="通孔的方位"')
  expect(html).toContain('aria-label="通孔的实际尺寸精度等级"')
  expect(html).not.toContain('aria-label="盲孔的方位"')
  expect(html).not.toContain('添加一组')
  expect(html).not.toMatch(/value="7" selected/)
})
