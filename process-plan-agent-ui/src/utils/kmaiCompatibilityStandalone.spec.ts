/// <reference types="node" />

import { readFileSync } from 'node:fs'

import { describe, expect, it } from 'vitest'

type FactorDefinition = {
  factor_key: string
  value_type: string
  default_value: unknown
  source_mode?: string
}

type LoadedPackage = {
  factorSchema: { factors: FactorDefinition[] }
  inputSchema: { fields: Array<{ key: string }> }
  validationReport: Record<string, unknown>
  allowLegacyMappingFallback: boolean
}

type StandaloneHarness = {
  setLoaded: (value: LoadedPackage) => void
  buildV1Factors: (inputs: Record<string, unknown>) => Record<string, unknown>
}

class TestElement {
  listeners: Record<string, (event: unknown) => unknown> = {}
  children: TestElement[] = []
  style: Record<string, unknown> = {}
  className = ''
  textContent = ''
  innerHTML = ''
  disabled = false
  classList = {
    add: (..._names: string[]) => undefined,
    remove: (..._names: string[]) => undefined,
  }

  addEventListener(name: string, callback: (event: unknown) => unknown) {
    this.listeners[name] = callback
  }

  append(...nodes: TestElement[]) {
    this.children.push(...nodes)
  }

  appendChild(node: TestElement) {
    this.children.push(node)
    return node
  }

  click() {}
}

function loadStandaloneHarness(): StandaloneHarness {
  const html = readFileSync(new URL('../../public/kmai-compatibility-test.html', import.meta.url), 'utf8')
  const script = html.match(/<script>([\s\S]*?)<\/script>/)?.[1]
  if (!script) throw new Error('standalone compatibility script not found')

  const hook = `
      document.__kmaiTest = {
        setLoaded: (value) => { loaded = value },
        buildV1Factors,
      }
    })()`
  const instrumented = script.replace(/    \}\)\(\)\s*$/, hook)
  if (instrumented === script) throw new Error('standalone compatibility script hook was not installed')

  const elements: Record<string, TestElement> = {}
  const documentStub = {
    getElementById: (id: string) => elements[id] || (elements[id] = new TestElement()),
    createElement: () => new TestElement(),
    body: new TestElement(),
    __kmaiTest: undefined as StandaloneHarness | undefined,
  }
  new Function('document', instrumented)(documentStub)
  if (!documentStub.__kmaiTest) throw new Error('standalone compatibility harness not exposed')
  return documentStub.__kmaiTest
}

function factor(factor_key: string, value_type = 'boolean', source_mode?: string): FactorDefinition {
  return {
    factor_key,
    value_type,
    default_value: value_type === 'boolean' ? false : null,
    ...(source_mode ? { source_mode } : {}),
  }
}

const factorDefinitions = [
  factor('material_grade', 'enum'),
  factor('has_flat_or_plane'),
  factor('has_slot_feature'),
  factor('uses_center_hole_location'),
  factor('has_hole_finish_machining'),
  factor('requires_honing'),
  factor('needs_marking'),
  factor('mechanical_hardness_hrc', 'number', 'manual_override'),
]

const inputFields = [
  { key: 'material.grade' },
  { key: 'cad.features' },
  { key: 'precision.grades' },
  { key: 'special.requirements' },
]

function buildFactors(
  validationReport: Record<string, unknown>,
  inputs: Record<string, unknown>,
  allowLegacyMappingFallback = false,
) {
  const harness = loadStandaloneHarness()
  harness.setLoaded({
    factorSchema: { factors: factorDefinitions },
    inputSchema: { fields: inputFields },
    validationReport,
    allowLegacyMappingFallback,
  })
  return harness.buildV1Factors(inputs)
}

describe('standalone KmAI factor construction', () => {
  it('uses the immutable current catalog when factor_catalog_version is present without a snapshot', () => {
    const factors = buildFactors(
      { kmai_compatibility: { factor_catalog_version: '2026.11' } },
      {
        material: { grade: '9Cr18' },
        cad: { features: ['槽类特征', '顶尖孔'] },
        precision: { grades: ['孔精加工', '珩孔要求'] },
        special: { requirements: ['追溯标印'] },
        target_hardness_hrc: 58,
      },
    )

    expect(factors).toMatchObject({
      material_grade: '9Cr18',
      has_flat_or_plane: false,
      has_slot_feature: true,
      uses_center_hole_location: true,
      has_hole_finish_machining: true,
      requires_honing: true,
      needs_marking: true,
      mechanical_hardness_hrc: 58,
    })
  })

  it('preserves a historical package explicit mapping snapshot', () => {
    const factors = buildFactors(
      { kmai_compatibility: { mapping_snapshot: [{
        source_field: 'cad.features',
        source_value: '槽类特征',
        mapping_mode: 'existing_factor',
        target_factor_key: 'requires_honing',
      }] } },
      { cad: { features: ['槽类特征'] } },
    )

    expect(factors.requires_honing).toBe(true)
    expect(factors.has_slot_feature).toBe(false)
  })

  it('limits a snapshotless historical package to the six fixed legacy mappings', () => {
    const factors = buildFactors(
      { valid: true },
      {
        cad: { features: ['槽类特征'] },
        precision: { grades: ['孔精加工'] },
        special: { requirements: ['追溯标印'] },
      },
    )

    expect(factors.has_slot_feature).toBe(true)
    expect(factors.has_hole_finish_machining).toBe(false)
    expect(factors.needs_marking).toBe(false)
  })
})
