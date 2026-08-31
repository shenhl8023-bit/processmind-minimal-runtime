import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useGenerateInputFields } from './useGenerateInputFields'

describe('manual Boolean process inputs', () => {
  it('keeps user-controlled process switches unset until the user chooses', () => {
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

    expect(fields.fieldValues.value['project_factor.manual_process_12345678']).toBeUndefined()
    expect(fields.filledFieldCount.value).toBe(0)
    expect(fields.factorValues.value).toEqual({})

    fields.setFieldBoolean('project_factor.manual_process_12345678', false)

    expect(fields.filledFieldCount.value).toBe(1)
    expect(fields.fieldPreviewValue('project_factor.manual_process_12345678')).toBe('否')
    expect(fields.factorValues.value).toEqual({
      project_factor: { manual_process_12345678: false },
    })

    fields.clearAllFields()

    expect(fields.fieldValues.value['project_factor.manual_process_12345678']).toBeUndefined()
    expect(fields.factorValues.value).toEqual({})
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

  it('adds a custom single-select value when the factor allows it', () => {
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

    expect(fields.factorValues.value).toEqual({ material: { grade: 'Custom Alloy' } })
    expect(fields.factorMetadata.value['material.grade']?.origin).toBe('manual')
  })
})
