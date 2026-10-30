import * as Vue from 'vue'
import { renderToString } from '@vue/server-renderer'
import { compileScript, parse } from '@vue/compiler-sfc'
import { transformSync } from 'esbuild'
import { describe, expect, it } from 'vitest'
import source from './GenerateInputPanel.vue?raw'

const componentModule = { exports: {} as any }
const compiled = compileScript(parse(source).descriptor, { id: 'generate-input-panel-test', inlineTemplate: true })
new Function('require', 'module', 'exports', transformSync(compiled.content, { loader: 'ts', format: 'cjs' }).code)(
  (id: string) => { if (id === 'vue') return Vue; throw new Error(id) }, componentModule, componentModule.exports,
)

function render(hasRulePackage: boolean, canGenerate: boolean) {
  const noop = () => {}
  const props = {
    projectId: 6, projectName: '固定路线', inputFields: [], filledFieldCount: 0,
    canGenerate, hasRulePackage, generating: false, schemaStatusText: '无需填写参数，可直接生成。',
    generateHintText: '', fieldValues: {}, customInputValues: {}, fieldValueOrigin: () => 'unset',
    isConfirmedFieldValue: () => false, isInvalidConfirmedFieldValue: () => false,
    fieldTypeLabel: () => '', isTextField: () => false, isSingleSelectField: () => false,
    isArrayField: () => false, isBooleanField: () => false, isNumberField: () => false,
    fieldTextValue: () => '', fieldPlaceholder: () => '', inputValue: () => '', arrayFieldValues: () => [],
    setFieldText: noop, setFieldBoolean: noop, toggleFieldArrayValue: noop, setCustomInput: noop,
    addCustomArrayValue: noop, addCustomSingleValue: noop, clearAllFields: noop, fillExampleValues: noop,
  }
  return renderToString(Vue.createSSRApp(componentModule.exports.default, props))
}

describe('fixed route generation panel', () => {
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
