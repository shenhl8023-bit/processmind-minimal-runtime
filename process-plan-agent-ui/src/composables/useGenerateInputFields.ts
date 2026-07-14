import { computed, ref, type Ref } from 'vue'

export type GenerateInputField = {
  key: string
  name?: string
  type?: string
  source?: string
  examples?: string[]
  allowed_values?: string[]
  required?: boolean
}

type FactorDictionaryEntry = {
  values: string[]
  input_type?: string
  source?: string
  label?: string
  required?: boolean
}

function normalizeSchemaFields(fields: any, required: boolean): GenerateInputField[] {
  if (!Array.isArray(fields)) return []
  return fields
    .map((field) => ({
      key: String(field?.key || '').trim(),
      name: String(field?.name || field?.label || field?.key || '').trim(),
      type: String(field?.type || 'string').trim().toLowerCase(),
      source: String(field?.source || '').trim(),
      examples: Array.isArray(field?.examples) ? field.examples.map((item: any) => String(item || '').trim()).filter(Boolean) : [],
      allowed_values: Array.isArray(field?.allowed_values) ? field.allowed_values.map((item: any) => String(item || '').trim()).filter(Boolean) : [],
      required,
    }))
    .filter(field => field.key)
}

function normalizeFactorDictionary(dictionary: any) {
  if (!dictionary || typeof dictionary !== 'object') return {}
  const normalized: Record<string, FactorDictionaryEntry> = {}
  Object.entries(dictionary).forEach(([key, value]) => {
    if (!value || typeof value !== 'object') return
    const item = value as Record<string, any>
    const values = Array.isArray(item.values)
      ? item.values.map((entry: any) => String(entry || '').trim()).filter(Boolean)
      : []
    normalized[key] = {
      values,
      input_type: String(item.input_type || '').trim(),
      source: String(item.source || '').trim(),
      label: String(item.label || '').trim(),
      required: typeof item.required === 'boolean' ? item.required : undefined,
    }
  })
  return normalized
}

function applyFactorDictionary(
  field: GenerateInputField,
  dictionary: Record<string, FactorDictionaryEntry>,
): GenerateInputField {
  const entry = dictionary[field.key]
  if (!entry) return field
  const dictionaryType = entry.input_type === 'single'
    ? 'select'
    : entry.input_type === 'multi'
      ? 'array'
      : field.type
  return {
    ...field,
    name: entry.label || field.name,
    source: entry.source || field.source,
    type: dictionaryType,
    allowed_values: entry.values.length ? entry.values : field.allowed_values,
    examples: entry.values.length ? entry.values : field.examples,
    required: typeof entry.required === 'boolean' ? entry.required : field.required,
  }
}

export function isArrayField(field: GenerateInputField) {
  return field.type === 'array' || field.type === 'list' || field.type === 'multi_select'
}

export function isSingleSelectField(field: GenerateInputField) {
  return field.type === 'select' || field.type === 'single_select' || field.type === 'enum'
}

export function isTextField(field: GenerateInputField) {
  return !field.type || field.type === 'string' || field.type === 'text'
}

export function isBooleanField(field: GenerateInputField) {
  return field.type === 'boolean' || field.type === 'bool'
}

export function isNumberField(field: GenerateInputField) {
  return field.type === 'number' || field.type === 'integer'
}

export function fieldTypeLabel(field: GenerateInputField) {
  if (isArrayField(field)) return '多选'
  if (isSingleSelectField(field)) return '单选'
  if (isBooleanField(field)) return '是/否'
  if (isNumberField(field)) return field.type === 'integer' ? '整数' : '数值'
  return '文本'
}

export function useGenerateInputFields(args: {
  inputSchema: Ref<Record<string, any> | null>
  hasRulePackage: Ref<boolean>
  projectId: Ref<number | null>
}) {
  const fieldValues = ref<Record<string, any>>({})
  const customInputValues = ref<Record<string, string>>({})

  const inputFields = computed<GenerateInputField[]>(() => {
    const schema = args.inputSchema.value
    if (!schema) return []
    const factorDictionary = normalizeFactorDictionary(schema.factor_dictionary)
    const required = normalizeSchemaFields(schema.required_inputs, true)
    const optional = normalizeSchemaFields(schema.optional_inputs, false)
    return [...required, ...optional].map(field => applyFactorDictionary(field, factorDictionary))
  })

  const requiredFields = computed(() => inputFields.value.filter(field => field.required))
  const filledFieldCount = computed(() => inputFields.value.filter(field => hasFieldValue(field.key)).length)
  const missingRequiredFields = computed(() => requiredFields.value
    .filter(field => !hasFieldValue(field.key))
    .map(field => field.name || field.key))

  const factorValues = computed(() => {
    const values: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      const value = fieldValues.value[field.key]
      if (Array.isArray(value)) {
        values[field.key] = value.filter(Boolean)
      } else if (typeof value === 'string') {
        values[field.key] = value.trim()
      } else if (value !== undefined && value !== null) {
        values[field.key] = value
      }
    })
    return values
  })

  const canGenerate = computed(() =>
    Boolean(
      args.projectId.value
      && args.hasRulePackage.value
      && inputFields.value.length
      && requiredFields.value.every(field => hasFieldValue(field.key)),
    ),
  )

  function initializeFieldValues() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      const currentValue = fieldValues.value[field.key]
      if (currentValue !== undefined) {
        nextValues[field.key] = currentValue
        return
      }
      if (isArrayField(field)) {
        nextValues[field.key] = []
      } else if (isBooleanField(field)) {
        nextValues[field.key] = false
      } else {
        nextValues[field.key] = field.examples?.[0] || ''
      }
    })
    fieldValues.value = nextValues
  }

  function hasFieldValue(key: string) {
    const value = fieldValues.value[key]
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return value.trim().length > 0
    return Boolean(value)
  }

  function fieldTextValue(key: string) {
    const value = fieldValues.value[key]
    if (Array.isArray(value)) return value.join('、')
    return value ?? ''
  }

  function arrayFieldValues(key: string) {
    const value = fieldValues.value[key]
    return Array.isArray(value) ? value : []
  }

  function fieldPlaceholder(field: GenerateInputField) {
    if (field.examples?.length) return `例如 ${field.examples[0]}`
    return field.source ? `来源：${field.source}` : '请输入'
  }

  function fieldPreviewValue(key: string) {
    const value = fieldValues.value[key]
    if (Array.isArray(value)) {
      const normalized = value.map(item => String(item || '').trim()).filter(Boolean)
      if (!normalized.length) return ''
      return normalized.length <= 3 ? normalized.join('、') : `${normalized.slice(0, 3).join('、')} 等 ${normalized.length} 项`
    }
    if (typeof value === 'string') return value.trim()
    if (typeof value === 'boolean') return value ? '已启用' : ''
    if (value === undefined || value === null) return ''
    return String(value)
  }

  function inputValue(event: Event) {
    return String((event.target as HTMLInputElement | HTMLTextAreaElement)?.value || '')
  }

  function checkedValue(event: Event) {
    return Boolean((event.target as HTMLInputElement)?.checked)
  }

  function setFieldText(key: string, value: string) {
    fieldValues.value[key] = value
  }

  function setFieldBoolean(key: string, value: boolean) {
    fieldValues.value[key] = value
  }

  function setCustomInput(key: string, value: string) {
    customInputValues.value[key] = value
  }

  function toggleFieldArrayValue(key: string, value: string) {
    const list = arrayFieldValues(key)
    const index = list.indexOf(value)
    fieldValues.value[key] = index >= 0
      ? list.filter(item => item !== value)
      : [...list, value]
  }

  function addCustomArrayValue(key: string) {
    const value = String(customInputValues.value[key] || '').trim()
    if (!value) return
    const list = arrayFieldValues(key)
    if (!list.includes(value)) {
      fieldValues.value[key] = [...list, value]
    }
    customInputValues.value[key] = ''
  }

  function clearAllFields() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      if (isArrayField(field)) nextValues[field.key] = []
      else if (isBooleanField(field)) nextValues[field.key] = false
      else nextValues[field.key] = ''
    })
    fieldValues.value = nextValues
    customInputValues.value = {}
  }

  function fillExampleValues() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      if (isArrayField(field)) {
        const preferred = (field.allowed_values || []).slice(0, Math.min(2, (field.allowed_values || []).length))
        nextValues[field.key] = preferred.length ? preferred : (field.examples?.[0] ? [field.examples[0]] : [])
        return
      }
      if (isBooleanField(field)) {
        nextValues[field.key] = true
        return
      }
      if (isSingleSelectField(field)) {
        nextValues[field.key] = field.allowed_values?.[0] || field.examples?.[0] || ''
        return
      }
      nextValues[field.key] = field.examples?.[0] || field.allowed_values?.[0] || ''
    })
    fieldValues.value = nextValues
  }

  function resetFieldValues() {
    fieldValues.value = {}
    customInputValues.value = {}
  }

  return {
    addCustomArrayValue,
    arrayFieldValues,
    canGenerate,
    checkedValue,
    clearAllFields,
    customInputValues,
    factorValues,
    fieldPlaceholder,
    fieldPreviewValue,
    fieldTextValue,
    fieldValues,
    filledFieldCount,
    fillExampleValues,
    hasFieldValue,
    initializeFieldValues,
    inputFields,
    inputValue,
    missingRequiredFields,
    resetFieldValues,
    setCustomInput,
    setFieldBoolean,
    setFieldText,
    toggleFieldArrayValue,
  }
}
