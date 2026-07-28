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
