import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useGenerateInputFields } from './useGenerateInputFields'

it('requires parameters only for selected features and clears them when deselected', () => {
  const scope = 'project_factor.feature_5b54'
  const input = useGenerateInputFields({ inputSchema: ref({ schema_version: '2.0', fields: [
    { key: `${scope}.present`, label: '孔', type: 'boolean', source: '本项目特征输入' },
    { key: `${scope}.direction`, label: '孔的方位', type: 'single_select', options: [{ value: 'A侧', label: 'A侧' }], allow_custom: false },
    { key: `${scope}.it`, label: '孔的实际精度', type: 'number', unit: 'IT' },
  ] }), hasRulePackage: ref(true), projectId: ref(8) })
  input.initializeFieldValues()
  expect(input.fieldValues.value[`${scope}.present`]).toBe(false)
  expect(input.canGenerate.value).toBe(true)
  input.setFieldBoolean(`${scope}.present`, true)
  expect(input.canGenerate.value).toBe(false)
  input.setFieldText(`${scope}.direction`, 'A侧')
  input.setFieldText(`${scope}.it`, '7')
  expect(input.canGenerate.value).toBe(true)
  expect(input.factorValues.value).toEqual({ project_factor: { feature_5b54: { present: true, direction: 'A侧', it: 7 } } })
  input.setFieldBoolean(`${scope}.present`, false)
  expect(input.fieldValues.value[`${scope}.it`]).toBe('')
  expect(input.factorValues.value).toEqual({ project_factor: { feature_5b54: { present: false } } })
  expect(Object.keys(input.factorMetadata.value)).toEqual([`${scope}.present`])
  input.setFieldBoolean(`${scope}.present`, true)
  expect(input.canGenerate.value).toBe(false)
})

it('blocks generation instead of omitting an invalid optional numeric zero', () => {
  const fields = useGenerateInputFields({
    inputSchema: ref({ schema_version: '2.0', fields: [
      { key: 'project_factor.operation_x.ra', label: '实际粗糙度', type: 'number', required: false, validation: { min: 0 } },
    ] }),
    hasRulePackage: ref(true), projectId: ref(7),
  })
  fields.initializeFieldValues()
  fields.fillExampleValues()
  expect(fields.fieldValues.value['project_factor.operation_x.ra']).toBe(0)
  expect(fields.isInvalidConfirmedFieldValue(fields.inputFields.value[0]!)).toBe(true)
  expect(fields.canGenerate.value).toBe(false)
})

it('accepts a numeric zero hardness lower bound when the upper bound is entered', () => {
  const fields = useGenerateInputFields({
    inputSchema: ref({ schema_version: '2.0', fields: [
      { key: 'project_factor.operation_x.hardness_min', type: 'number', required: true, validation: { min: 0 } },
      { key: 'project_factor.operation_x.hardness_max', type: 'number', required: true, validation: { min: 0 } },
    ] }),
    hasRulePackage: ref(true), projectId: ref(7),
  })
  fields.initializeFieldValues()
  fields.fillExampleValues()
  fields.setFieldText('project_factor.operation_x.hardness_max', '60')
  expect(fields.canGenerate.value).toBe(true)
  expect(fields.factorValues.value).toEqual({ project_factor: { operation_x: { hardness_min: 0, hardness_max: 60 } } })
})

it.each(['4', '11', '7.5', 'IT7'])('blocks actual project IT %s with an older 1-18 threshold definition', (value) => {
  const fields = useGenerateInputFields({ inputSchema: ref({ schema_version: '2.0', fields: [
    { key: 'project_factor.operation_a.it', label: '实际尺寸精度等级', type: 'number', unit: 'IT', required: true, validation: { min: 1, max: 18 } },
  ] }), hasRulePackage: ref(true), projectId: ref(5) })
  fields.initializeFieldValues()
  fields.setFieldText('project_factor.operation_a.it', value)
  expect(fields.canGenerate.value).toBe(false)
  expect(fields.factorValues.value).toEqual({})
})

it('derives a six-grade actual IT domain and live rule hint without narrowing the trigger threshold', () => {
  const rules = ref<any>({ process_configurations: [{ process_id: 'grind', occurrence: 'conditional', when: { field: 'project_factor.operation_a.it', op: 'lte', value: 7 } }] })
  const fields = useGenerateInputFields({ inputSchema: ref({ schema_version: '2.0', fields: [
    { key: 'project_factor.operation_a.it', label: '实际尺寸精度等级', type: 'number', unit: 'IT', required: true },
  ] }), rulePackageRules: rules, hasRulePackage: ref(true), projectId: ref(5) })
  fields.initializeFieldValues()
  expect(fields.inputFields.value[0]?.allowed_values).toEqual(['5', '6', '7', '8', '9', '10'])
  expect((fields.inputFields.value[0] as any).rule_hint).toContain('IT7')
  for (const grade of ['6', '8']) {
    fields.setFieldText('project_factor.operation_a.it', grade)
    expect(fields.canGenerate.value).toBe(true)
    expect(fields.factorValues.value).toEqual({ project_factor: { operation_a: { it: Number(grade) } } })
  }
  rules.value.process_configurations[0].when.value = 6
  expect((fields.inputFields.value[0] as any).rule_hint).toContain('IT6')
})

it('uses explicit IT units for custom actual-grade fields rather than relying on the label', () => {
  const fields = useGenerateInputFields({ inputSchema: ref({ schema_version: '2.0', fields: [
    { key: 'project_factor.precision_for_object', label: '对象参数', type: 'number', unit: 'IT', required: true },
  ] }), hasRulePackage: ref(true), projectId: ref(5) })
  fields.initializeFieldValues(); fields.setFieldText('project_factor.precision_for_object', '4')
  expect(fields.canGenerate.value).toBe(false)
  fields.setFieldText('project_factor.precision_for_object', '8')
  expect(fields.canGenerate.value).toBe(true)
})

describe('manual Boolean process inputs', () => {
  it.each([
    [{ field: 'special.requirements', op: 'contains', value: '无损检测要求' }, ['无损检测要求']],
    [{ field: 'special.requirements', op: 'exists' }, ['无损检测要求', '除铜要求']],
    [{ field: 'special.requirements', op: 'neq', value: '无损检测要求' }, ['无损检测要求', '除铜要求']],
    [null, ['无损检测要求', '除铜要求']],
  ])('preserves active requirements and conservatively handles incomplete rule context', (when, expected) => {
    const fields = useGenerateInputFields({
      inputSchema: ref({ schema_version: '2.0', fields: [
        { key: 'special.requirements', type: 'multi_select', options: [{ value: '无损检测要求' }, { value: '除铜要求' }] },
        { key: 'material.grade', type: 'single_select', options: [{ value: 'A' }, { value: 'B' }] },
      ] }),
      rulePackageRules: ref(when ? { rules: [
        { when }, { when: { field: 'material.grade', op: 'eq', value: 'A' } },
      ] } : null),
      hasRulePackage: ref(true),
      projectId: ref(5),
    })
    expect(fields.inputFields.value.find(field => field.key === 'special.requirements')?.allowed_values).toEqual(expected)
    expect(fields.inputFields.value.find(field => field.key === 'material.grade')?.allowed_values).toEqual(['A', 'B'])
  })
  it('omits unused legacy requirement options while keeping the active manual switch', () => {
    const inputSchema = ref({ schema_version: '2.0', fields: [
      { key: 'special.requirements', label: '特殊要求', type: 'multi_select', options: [
        { value: '无损检测要求', label: '无损检测要求' },
        { value: '除铜要求', label: '除铜要求' },
        { value: '其他要求', label: '其他要求' },
      ] },
      { key: 'project_factor.manual_process_ndt', label: '是否需要无损检查', type: 'boolean' },
    ] })
    const rulePackageRules = ref<any>({ rules: [
      { enabled: false, when: { field: 'special.requirements', op: 'contains', value: '无损检测要求' } },
    ], process_configurations: [
      { enabled: true, when: { all: [{ field: 'special.requirements', op: 'contains', value: '除铜要求' }, { not: { field: 'special.requirements', op: 'contains', value: '其他要求' } }] } },
      { enabled: true, when: { field: 'project_factor.manual_process_ndt', op: 'eq', value: true } },
    ] })
    const fields = useGenerateInputFields({ inputSchema, rulePackageRules, hasRulePackage: ref(true), projectId: ref(5) })
    fields.initializeFieldValues()
    expect(fields.inputFields.value.find(field => field.key === 'special.requirements')?.allowed_values).toEqual(['除铜要求', '其他要求'])
    expect(fields.inputFields.value.find(field => field.key === 'project_factor.manual_process_ndt')?.name).toBe('是否需要无损检查')
    expect(inputSchema.value.fields[0]?.options).toHaveLength(3)
    fields.setFieldBoolean('project_factor.manual_process_ndt', false)
    fields.toggleFieldArrayValue('special.requirements', '除铜要求')
    expect(fields.factorValues.value).toEqual({ special: { requirements: ['除铜要求'] }, project_factor: { manual_process_ndt: false } })
  })
  it('defaults user-controlled process switches to false without inventing manual confirmation', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({
        schema_version: '2.0',
        fields: [{
          key: 'project_factor.manual_process_12345678',
          label: '是否需要标记',
          type: 'boolean',
          required: false,
          source: '用户直接设定',
        }],
      }),
      hasRulePackage: ref(true),
      projectId: ref(1),
    })

    fields.initializeFieldValues()

    expect(fields.fieldValues.value['project_factor.manual_process_12345678']).toBe(false)
    expect(fields.filledFieldCount.value).toBe(1)
    expect(fields.factorValues.value).toEqual({})
    expect(fields.factorMetadata.value).toEqual({})

    expect(fields.canGenerate.value).toBe(true)
    fields.setFieldBoolean('project_factor.manual_process_12345678', true)
    fields.initializeFieldValues()
    expect(fields.fieldValues.value['project_factor.manual_process_12345678']).toBe(true)
    expect(fields.factorValues.value).toEqual({project_factor:{manual_process_12345678:true}})

    fields.setFieldBoolean('project_factor.manual_process_12345678', false)

    expect(fields.filledFieldCount.value).toBe(1)
    expect(fields.fieldPreviewValue('project_factor.manual_process_12345678')).toBe('否')
    expect(fields.factorValues.value).toEqual({
      project_factor: { manual_process_12345678: false },
    })

    fields.clearAllFields()

    expect(fields.fieldValues.value['project_factor.manual_process_12345678']).toBe(false)
    expect(fields.factorValues.value).toEqual({})
    expect(fields.factorMetadata.value).toEqual({})
  })

  it('keeps other Boolean inputs unselected initially', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({
        schema_version: '2.0',
        fields: [{ key: 'quality.approved', label: '质量确认', type: 'boolean', source: '检验记录' }],
      }),
      hasRulePackage: ref(true),
      projectId: ref(1),
    })

    fields.initializeFieldValues()

    expect(fields.fieldValues.value['quality.approved']).toBeUndefined()
  })
})

function selectSchema(options: string[]) {
  return {
    schema_version: '2.0',
    fields: [
      {
        key: 'material.grade',
        label: '材料牌号',
        type: 'single_select',
        required: true,
        options: options.map(value => ({ label: value, value })),
      },
    ],
  }
}

function createInputFields(options = ['A', 'B']) {
  const inputSchema = ref<Record<string, any> | null>(selectSchema(options))
  const hasRulePackage = ref(true)
  const projectId = ref<number | null>(1)
  const schemaLoading = ref(false)
  const fields = useGenerateInputFields({
    inputSchema,
    hasRulePackage,
    projectId,
    schemaLoading,
  })
  fields.initializeFieldValues()
  return { fields, hasRulePackage, inputSchema, projectId, schemaLoading }
}

describe('useGenerateInputFields project isolation', () => {
  it('allows a loaded fixed-route schema with no fields but blocks missing or malformed schemas', () => {
    const { fields, inputSchema, schemaLoading, hasRulePackage } = createInputFields()
    inputSchema.value = { schema_version: '2.0', fields: [] }
    expect(fields.factorValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(true)
    schemaLoading.value = true
    expect(fields.canGenerate.value).toBe(false)
    schemaLoading.value = false
    hasRulePackage.value = false
    expect(fields.canGenerate.value).toBe(false)
    hasRulePackage.value = true
    for (const schema of [null, {}, { schema_version: '2.0' }]) {
      inputSchema.value = schema
      expect(fields.canGenerate.value).toBe(false)
    }
  })

  it('preserves generation for legacy schemas containing only optional inputs', () => {
    const { fields, inputSchema } = createInputFields()
    inputSchema.value = { optional_inputs: [{ key: 'material', type: 'string' }] }
    expect(fields.inputFields.value).toHaveLength(1)
    expect(fields.canGenerate.value).toBe(true)
  })

  it('creates valid constrained material and custom multi-select examples', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({ schema_version: '2.0', fields: [
        { key: 'material.grade', type: 'string', required: true, validation: { min_length: 7, max_length: 10 } },
        { key: 'features', type: 'multi_select', required: true, allow_custom: true, options: [], validation: { min_length: 3, max_length: 3 } },
      ] }),
      hasRulePackage: ref(true), projectId: ref(1),
    })
    fields.initializeFieldValues()
    fields.fillExampleValues()
    expect(fields.fieldValues.value['material.grade'].length).toBeGreaterThanOrEqual(7)
    expect(fields.fieldValues.value.features).toHaveLength(3)
    expect(new Set(fields.fieldValues.value.features).size).toBe(3)
    expect(fields.canGenerate.value).toBe(true)
  })

  it('blocks generation when an optional input was entered but is invalid', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({ schema_version: '2.0', fields: [
        { key: 'material.grade', type: 'string', required: true },
        { key: 'diameter', type: 'number', required: false, validation: { min: 0, max: 50 } },
      ] }),
      hasRulePackage: ref(true), projectId: ref(1),
    })
    fields.initializeFieldValues()
    fields.setFieldText('material.grade', '9Cr18')
    expect(fields.canGenerate.value).toBe(true)
    fields.setFieldText('diameter', '100')
    expect(fields.canGenerate.value).toBe(false)
    fields.setFieldText('diameter', '')
    expect(fields.canGenerate.value).toBe(true)
  })

  it('enforces multi-select length before enabling generation', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({ schema_version: '2.0', fields: [
        { key: 'features', type: 'multi_select', required: true, options: [{ value: 'A' }, { value: 'B' }, { value: 'C' }], validation: { min_length: 2, max_length: 2 } },
      ] }),
      hasRulePackage: ref(true), projectId: ref(1),
    })
    fields.initializeFieldValues()
    fields.toggleFieldArrayValue('features', 'A')
    expect(fields.canGenerate.value).toBe(false)
    fields.toggleFieldArrayValue('features', 'B')
    expect(fields.canGenerate.value).toBe(true)
    fields.toggleFieldArrayValue('features', 'C')
    expect(fields.canGenerate.value).toBe(false)
  })

  it('fills examples within maximum and minimum length constraints and clears draft custom values', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({ schema_version: '2.0', fields: [
        { key: 'temperature', type: 'number', required: true, validation: { max: -5 } },
        { key: 'description', type: 'string', required: true, validation: { min_length: 6, max_length: 8 } },
        { key: 'features', type: 'multi_select', required: true, options: ['A', 'B', 'C', 'D'].map(value => ({ value })), validation: { min_length: 3, max_length: 3 } },
      ] }),
      hasRulePackage: ref(true), projectId: ref(1),
    })
    fields.initializeFieldValues()
    fields.setCustomInput('features', 'old draft')
    fields.fillExampleValues()
    expect(fields.fieldValues.value.temperature).toBe(-5)
    expect(fields.fieldValues.value.description.length).toBeGreaterThanOrEqual(6)
    expect(fields.fieldValues.value.features).toEqual(['A', 'B', 'C'])
    expect(fields.customInputValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(true)
    fields.clearAllFields()
    expect(fields.factorValues.value).toEqual({})
    expect(fields.factorMetadata.value).toEqual({})
    expect(fields.canGenerate.value).toBe(false)
  })
  it('clears factor and custom values synchronously when the project changes', () => {
    const { fields, projectId } = createInputFields()
    fields.setFieldText('material.grade', 'B')
    fields.setCustomInput('material.grade', 'draft custom value')

    expect(fields.factorValues.value).toEqual({ material: { grade: 'B' } })
    expect(fields.canGenerate.value).toBe(true)

    projectId.value = 2

    expect(fields.fieldValues.value).toEqual({})
    expect(fields.customInputValues.value).toEqual({})
    expect(fields.factorValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(false)
  })

  it('blocks generation while the asynchronous schema load is in progress', () => {
    const { fields, schemaLoading } = createInputFields()

    fields.setFieldText('material.grade', 'A')
    expect(fields.canGenerate.value).toBe(true)
    schemaLoading.value = true
    expect(fields.canGenerate.value).toBe(false)
    schemaLoading.value = false
    expect(fields.canGenerate.value).toBe(true)
  })

  it('does not reuse a same-key selection that is invalid in the new schema', () => {
    const { fields, inputSchema } = createInputFields(['legacy-a', 'legacy-b'])
    fields.setFieldText('material.grade', 'legacy-b')

    inputSchema.value = selectSchema(['new-a', 'new-b'])

    expect(fields.factorValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(false)

    fields.initializeFieldValues()

    expect(fields.fieldValues.value['material.grade']).toBe('')
    expect(fields.factorValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(false)
  })

  it('normalizes number controls and treats false as a valid required boolean', () => {
    const inputSchema = ref<Record<string, any> | null>({
      schema_version: '2.0',
      fields: [
        {
          key: 'target_hardness_hrc',
          label: '目标硬度',
          type: 'number',
          required: true,
          validation: { min: 0, max: 70 },
        },
        {
          key: 'requires_inspection',
          label: '需要检验',
          type: 'boolean',
          required: true,
        },
      ],
    })
    const fields = useGenerateInputFields({
      inputSchema,
      hasRulePackage: ref(true),
      projectId: ref(1),
      schemaLoading: ref(false),
    })
    fields.initializeFieldValues()

    fields.setFieldText('target_hardness_hrc', '0')
    fields.setFieldBoolean('requires_inspection', false)

    expect(fields.canGenerate.value).toBe(true)
    expect(fields.factorValues.value).toEqual({
      target_hardness_hrc: 0,
      requires_inspection: false,
    })

    fields.setFieldText('target_hardness_hrc', '58')

    expect(fields.canGenerate.value).toBe(true)
    expect(fields.filledFieldCount.value).toBe(2)
    expect(fields.factorValues.value).toEqual({
      target_hardness_hrc: 58,
      requires_inspection: false,
    })
  })

  it('treats example values as confirmed generation inputs', () => {
    const { fields } = createInputFields()

    fields.fillExampleValues()

    expect(fields.fieldValues.value['material.grade']).toBe('A')
    expect(fields.fieldValueOrigin('material.grade')).toBe('manual')
    expect(fields.filledFieldCount.value).toBe(1)
    expect(fields.factorValues.value).toEqual({ material: { grade: 'A' } })
    expect(fields.canGenerate.value).toBe(true)
    expect(fields.factorMetadata.value).toEqual({
      'material.grade': { origin: 'manual', evidence: [] },
    })
  })

  it('normalizes precision IT input ranges and fills valid example values for legacy rule packages', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({
        schema_version: '2.0',
        fields: [
          {
            key: 'precision.dimension_it',
            label: '其他尺寸精度 IT',
            type: 'number',
            required: true,
            source: 'CAD/PLM',
            validation: { min: 1, max: 18 },
          },
          {
            key: 'precision.outer_diameter_it',
            label: '外圆尺寸精度 IT',
            type: 'number',
            required: true,
            source: 'CAD/PLM',
            validation: { min: 1, max: 18 },
          },
          {
            key: 'precision.inner_diameter_it',
            label: '内孔尺寸精度 IT',
            type: 'number',
            required: true,
            source: 'CAD/PLM',
            validation: { min: 5, max: 10 },
          },
        ],
      }),
      hasRulePackage: ref(true),
      projectId: ref(1),
    })
    fields.initializeFieldValues()

    fields.setFieldText('precision.dimension_it', '1')
    fields.setFieldText('precision.outer_diameter_it', '1')
    fields.setFieldText('precision.inner_diameter_it', '5')
    const dimensionField = fields.inputFields.value.find(field => field.key === 'precision.dimension_it')!

    expect(fields.inputFields.value.map(field => [field.key, field.validation])).toEqual([
      ['precision.dimension_it', { min: 5, max: 10 }],
      ['precision.outer_diameter_it', { min: 5, max: 10 }],
      ['precision.inner_diameter_it', { min: 5, max: 10 }],
    ])
    expect(fields.isInvalidConfirmedFieldValue(dimensionField)).toBe(true)
    expect(fields.isConfirmedFieldValue(dimensionField)).toBe(false)
    expect(fields.canGenerate.value).toBe(false)

    fields.fillExampleValues()

    expect(fields.fieldValues.value['precision.dimension_it']).toBe(5)
    expect(fields.fieldValues.value['precision.outer_diameter_it']).toBe(5)
    expect(fields.fieldValues.value['precision.inner_diameter_it']).toBe(5)
    expect(fields.factorValues.value).toEqual({
      precision: {
        dimension_it: 5,
        outer_diameter_it: 5,
        inner_diameter_it: 5,
      },
    })
    expect(fields.isInvalidConfirmedFieldValue(dimensionField)).toBe(false)
    expect(fields.isConfirmedFieldValue(dimensionField)).toBe(true)
    expect(fields.canGenerate.value).toBe(true)
  })

  it('normalizes precision IT ranges after applying legacy factor dictionary labels', () => {
    const fields = useGenerateInputFields({
      inputSchema: ref({
        schema_version: '1.0',
        required_inputs: [{ key: 'precision.dimension_it', type: 'number' }],
        factor_dictionary: {
          'precision.dimension_it': {
            label: '其他尺寸精度 IT',
            source: 'CAD/PLM',
            required: true,
          },
        },
      }),
      hasRulePackage: ref(true),
      projectId: ref(1),
    })
    fields.initializeFieldValues()
    fields.fillExampleValues()

    expect(fields.inputFields.value[0]?.validation).toEqual({ min: 5, max: 10 })
    expect(fields.fieldValues.value['precision.dimension_it']).toBe(5)
    expect(fields.canGenerate.value).toBe(true)
  })

  it('sends manual values with input metadata', () => {
    const { fields } = createInputFields()

    fields.setFieldText('material.grade', 'B')

    expect(fields.factorValues.value).toEqual({ material: { grade: 'B' } })
    expect(fields.factorMetadata.value).toEqual({
      'material.grade': { origin: 'manual', evidence: [] },
    })
    expect(fields.canGenerate.value).toBe(true)
  })

  it('rejects unconfigured material values even if an old field claims to allow custom input', () => {
    const inputSchema = ref<Record<string, any> | null>({
      schema_version: '2.0',
      fields: [{
        key: 'material.grade',
        label: '材料牌号',
        type: 'single_select',
        required: true,
        allow_custom: true,
        options: [{ value: '9Cr18', label: '9Cr18' }],
      }],
    })
    const fields = useGenerateInputFields({
      inputSchema,
      hasRulePackage: ref(true),
      projectId: ref(1),
    })
    fields.initializeFieldValues()

    fields.setCustomInput('material.grade', 'Custom Alloy')
    fields.addCustomSingleValue('material.grade')

    expect(fields.inputFields.value[0]!.allow_custom).toBe(false)
    expect(fields.factorValues.value).toEqual({})
    expect(fields.canGenerate.value).toBe(false)
  })

  it('starts actual IT and Ra blank, validates precision integers and positive roughness, and rejects reversed hardness intervals', () => {
    const fields = useGenerateInputFields({ inputSchema: ref({ schema_version: '2.0', fields: [
      { key: 'project_factor.operation_a.it', label: '磨外圆 · 外圆柱面的实际尺寸精度等级', type: 'number', unit: 'IT' },
      { key: 'project_factor.operation_b.ra', label: '磨孔 · 孔的实际Ra要求值', type: 'number', unit: 'μm' },
      { key: 'project_factor.operation_c.hardness_min', label: '硬度下限', type: 'number' },
      { key: 'project_factor.operation_c.hardness_max', label: '硬度上限', type: 'number' },
    ] }), projectId: ref(1), hasRulePackage: ref(true) })
    fields.initializeFieldValues()
    expect(Object.values(fields.fieldValues.value)).toEqual(['', '', '', ''])
    fields.setFieldText('project_factor.operation_a.it', '7.5')
    expect(fields.canGenerate.value).toBe(false)
    fields.setFieldText('project_factor.operation_a.it', '7')
    fields.setFieldText('project_factor.operation_b.ra', '0')
    expect(fields.canGenerate.value).toBe(false)
    fields.setFieldText('project_factor.operation_b.ra', '0.4')
    fields.setFieldText('project_factor.operation_c.hardness_min', '50')
    fields.setFieldText('project_factor.operation_c.hardness_max', '40')
    expect(fields.canGenerate.value).toBe(false)
    fields.setFieldText('project_factor.operation_c.hardness_max', '55')
    expect(fields.canGenerate.value).toBe(true)
  })
})
