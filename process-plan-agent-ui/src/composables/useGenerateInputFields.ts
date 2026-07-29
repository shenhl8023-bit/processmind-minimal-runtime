import { computed, ref, watch, type Ref } from 'vue'

export type GenerateInputField = {
  key: string
  name?: string
  type?: string
  source?: string
  examples?: string[]
  allowed_values?: string[]
  required?: boolean
  allow_custom?: boolean
  unit?: string
  validation?: {
    min?: number | null
    max?: number | null
    min_length?: number | null
    max_length?: number | null
  }
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

function normalizeV2Fields(fields: any): GenerateInputField[] {
  if (!Array.isArray(fields)) return []
  return fields
    .map((field) => {
      const options = Array.isArray(field?.options)
        ? field.options.map((item: any) => String(item?.value ?? item?.label ?? '').trim()).filter(Boolean)
        : []
      return {
        key: String(field?.key || '').trim(),
        name: String(field?.label || field?.name || field?.key || '').trim(),
        type: String(field?.type || 'string').trim().toLowerCase(),
        source: String(field?.source || '').trim(),
        examples: options.slice(0, 3),
        allowed_values: options,
        required: Boolean(field?.required),
        allow_custom: Boolean(field?.allow_custom),
        unit: field?.unit ? String(field.unit) : undefined,
        validation: field?.validation || undefined,
      }
    })
    .filter(field => field.key)
}

/** Expand dotted keys like material.grade into nested objects for V2 expression engine. */
export function nestFactorValues(flat: Record<string, any>) {
  const nested: Record<string, any> = {}
  Object.entries(flat || {}).forEach(([key, value]) => {
    if (!key.includes('.')) {
      nested[key] = value
      return
    }
    const parts = key.split('.').filter(Boolean)
    let cursor = nested
    parts.forEach((part, index) => {
      if (index === parts.length - 1) {
        cursor[part] = value
        return
      }
      if (!cursor[part] || typeof cursor[part] !== 'object' || Array.isArray(cursor[part])) {
        cursor[part] = {}
      }
      cursor = cursor[part]
    })
  })
  return nested
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

function exampleValueForField(field: GenerateInputField) {
  if (field.examples?.length) return isArrayField(field) ? [field.examples[0]] : field.examples[0]
  if (field.allowed_values?.length) return isArrayField(field) ? [field.allowed_values[0]] : field.allowed_values[0]
  if (isBooleanField(field)) return true
  if (isNumberField(field)) return field.validation?.min ?? 0
  if (/material(?:\\.grade)?|材料|牌号/i.test(field.key) || /材料|牌号/.test(field.name || '')) return '9Cr18'
  if (isArrayField(field)) return ['示例特征']
  return '示例值'
}

function isReusableFieldValue(field: GenerateInputField, value: any) {
  if (value === undefined || value === null) return false

  if (isArrayField(field)) {
    if (!Array.isArray(value)) return false
    const normalized = value.map(item => String(item ?? '').trim()).filter(Boolean)
    if (normalized.length !== value.length) return false
    if (field.allowed_values?.length && field.allow_custom === false) {
      return normalized.every(item => field.allowed_values!.includes(item))
    }
    return true
  }

  if (isBooleanField(field)) return typeof value === 'boolean'

  if (isNumberField(field)) {
    const rawValue = typeof value === 'number' ? value : String(value).trim()
    if (rawValue === '') return false
    const normalized = typeof rawValue === 'number' ? rawValue : Number(rawValue)
    if (!Number.isFinite(normalized)) return false
    if (field.type === 'integer' && !Number.isInteger(normalized)) return false
    if (typeof field.validation?.min === 'number' && normalized < field.validation.min) return false
    if (typeof field.validation?.max === 'number' && normalized > field.validation.max) return false
    return true
  }

  if (typeof value !== 'string') return false
  const normalized = value.trim()
  if (
    isSingleSelectField(field)
    && normalized
    && field.allowed_values?.length
    && field.allow_custom === false
  ) {
    return field.allowed_values.includes(normalized)
  }
  if (typeof field.validation?.min_length === 'number' && normalized.length < field.validation.min_length) return false
  if (typeof field.validation?.max_length === 'number' && normalized.length > field.validation.max_length) return false
  return true
}

export function useGenerateInputFields(args: {
  inputSchema: Ref<Record<string, any> | null>
  hasRulePackage: Ref<boolean>
  projectId: Ref<number | null>
  schemaLoading?: Ref<boolean>
}) {
  const fieldValues = ref<Record<string, any>>({})
  const customInputValues = ref<Record<string, string>>({})

  const schemaVersion = computed(() => String(args.inputSchema.value?.schema_version || '1.0'))

  const inputFields = computed<GenerateInputField[]>(() => {
    const schema = args.inputSchema.value
    if (!schema) return []
    if (String(schema.schema_version || '') === '2.0' && Array.isArray(schema.fields)) {
      return normalizeV2Fields(schema.fields)
    }
    const factorDictionary = normalizeFactorDictionary(schema.factor_dictionary)
    const required = normalizeSchemaFields(schema.required_inputs, true)
    const optional = normalizeSchemaFields(schema.optional_inputs, false)
    return [...required, ...optional].map(field => applyFactorDictionary(field, factorDictionary))
  })

  const requiredFields = computed(() => inputFields.value.filter(field => field.required))
  const filledFieldCount = computed(() => inputFields.value.filter(field => hasValidFieldValue(field)).length)

  const factorValues = computed(() => {
    const values: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      const value = fieldValues.value[field.key]
      if (!isReusableFieldValue(field, value)) return
      if (Array.isArray(value)) {
        values[field.key] = value.filter(Boolean)
      } else if (isNumberField(field)) {
        values[field.key] = typeof value === 'number' ? value : Number(String(value).trim())
      } else if (typeof value === 'string') {
        values[field.key] = value.trim()
      } else if (value !== undefined && value !== null) {
        values[field.key] = value
      }
    })
    if (schemaVersion.value === '2.0') {
      return nestFactorValues(values)
    }
    return values
  })

  const canGenerate = computed(() =>
    Boolean(
      args.projectId.value
      && args.hasRulePackage.value
      && !args.schemaLoading?.value
      && inputFields.value.length
      && requiredFields.value.every(field => hasValidFieldValue(field)),
    ),
  )

  function initializeFieldValues() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      const currentValue = fieldValues.value[field.key]
      if (isReusableFieldValue(field, currentValue)) {
        nextValues[field.key] = currentValue
        return
      }
      if (isArrayField(field)) {
        nextValues[field.key] = []
      } else if (isBooleanField(field)) {
        nextValues[field.key] = field.source === '用户直接设定' ? false : undefined
      } else if (isSingleSelectField(field)) {
        nextValues[field.key] = field.allowed_values?.[0] || field.examples?.[0] || ''
      } else {
        nextValues[field.key] = field.examples?.[0] || ''
      }
    })
    fieldValues.value = nextValues
    const fieldKeys = new Set(inputFields.value.map(field => field.key))
    customInputValues.value = Object.fromEntries(
      Object.entries(customInputValues.value).filter(([key]) => fieldKeys.has(key)),
    )
  }

  function hasFieldValue(key: string) {
    const value = fieldValues.value[key]
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return value.trim().length > 0
    return Boolean(value)
  }

  function hasValidFieldValue(field: GenerateInputField) {
    const value = fieldValues.value[field.key]
    if (isBooleanField(field)) return typeof value === 'boolean'
    if (isNumberField(field)) return isReusableFieldValue(field, value)
    return isReusableFieldValue(field, value) && hasFieldValue(field.key)
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
        nextValues[field.key] = preferred.length ? preferred : exampleValueForField(field)
        return
      }
      nextValues[field.key] = exampleValueForField(field)
    })
    fieldValues.value = nextValues
  }

  function resetFieldValues() {
    fieldValues.value = {}
    customInputValues.value = {}
  }

  watch(args.projectId, (nextProjectId, previousProjectId) => {
    if (nextProjectId !== previousProjectId) resetFieldValues()
  }, { flush: 'sync' })

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
    nestFactorValues,
    resetFieldValues,
    schemaVersion,
    setCustomInput,
    setFieldBoolean,
    setFieldText,
    toggleFieldArrayValue,
  }
}
