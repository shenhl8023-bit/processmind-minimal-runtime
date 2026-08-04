import { describe, expect, it } from 'vitest'
import { ref } from 'vue'

import { useGenerateInputFields } from './useGenerateInputFields'

describe('manual Boolean process inputs', () => {
  it('defaults user-controlled process switches to false', () => {
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
    expect(fields.factorValues.value).toEqual({
      project_factor: { manual_process_12345678: false },
    })
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

    expect(fields.fieldValues.value['material.grade']).toBe('new-a')
    expect(fields.factorValues.value).toEqual({ material: { grade: 'new-a' } })
    expect(fields.canGenerate.value).toBe(true)
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

    fields.fieldValues.value.target_hardness_hrc = 0
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

  it('accepts only integer IT grades from 5 through 10', () => {
    const inputSchema = ref<Record<string, any> | null>({
      schema_version: '2.0',
      fields: [{
        key: 'precision.outer_diameter_it',
        label: '外圆尺寸精度 IT',
        type: 'number',
        required: true,
        validation: { min: 1, max: 18 },
      }],
    })
    const fields = useGenerateInputFields({
      inputSchema,
      hasRulePackage: ref(true),
      projectId: ref(1),
      schemaLoading: ref(false),
    })
    fields.initializeFieldValues()

    for (const value of ['5', '10']) {
      fields.setFieldText('precision.outer_diameter_it', value)
      expect(fields.canGenerate.value).toBe(true)
    }

    for (const value of ['4', '11', '5.5']) {
      fields.setFieldText('precision.outer_diameter_it', value)
      expect(fields.canGenerate.value).toBe(false)
      expect(fields.factorValues.value).toEqual({})
    }
  })

  it('applies the same range to legacy rule package IT inputs', () => {
    const inputSchema = ref<Record<string, any> | null>({
      schema_version: '1.0',
      required_inputs: [{
        key: 'precision.inner_diameter_it',
        name: '内孔尺寸精度 IT',
        type: 'number',
      }],
      optional_inputs: [],
    })
    const fields = useGenerateInputFields({
      inputSchema,
      hasRulePackage: ref(true),
      projectId: ref(1),
      schemaLoading: ref(false),
    })
    fields.initializeFieldValues()

    expect(fields.inputFields.value[0]?.validation).toEqual({ min: 5, max: 10, integer: true })
    fields.setFieldText('precision.inner_diameter_it', '4')
    expect(fields.canGenerate.value).toBe(false)
    fields.setFieldText('precision.inner_diameter_it', '8')
    expect(fields.canGenerate.value).toBe(true)
  })
})
