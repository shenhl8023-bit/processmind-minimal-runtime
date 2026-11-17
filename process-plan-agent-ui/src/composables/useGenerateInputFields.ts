import { computed, ref, watch, type Ref } from 'vue'
import { referencedRequirementOptions } from '@/utils/requirementOptionUsage'
import { isMaterialInput } from './generateFactorGroups'
import { actualProjectItGrades, isActualProjectItField } from '@/utils/projectConditionFields'
import { sharedFeatureField } from '@/utils/featureInputProjection'

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
  rule_hint?: string
  validation?: {
    min?: number | null
    max?: number | null
    min_length?: number | null
    max_length?: number | null
  }
}

export type InputValueOrigin = 'unset' | 'extracted' | 'manual' | 'example'

export type GenerateInputMetadata = {
  origin: Exclude<InputValueOrigin, 'unset'>
  unit?: string
  evidence: string[]
}

type FactorDictionaryEntry = {
  values: string[]
  input_type?: string
  source?: string
  label?: string
  required?: boolean
}

function isPrecisionItField(field: Pick<GenerateInputField, 'key' | 'name' | 'unit'>) {
  return isActualProjectItField(field)
    || /尺寸精度\s*IT/i.test(field.name || '')
}

function normalizeFieldValidation(field: GenerateInputField): GenerateInputField['validation'] {
  if (isPrecisionItField(field)) return { ...(field.validation || {}), min: 5, max: 10 }
  return field.validation
}

function actualItRuleHint(key: string, rules: Record<string, any> | null | undefined) {
  const descriptions: string[] = []
  function visit(condition: any, negated = false) {
    if (!condition || typeof condition !== 'object') return
    if (condition.field === key) {
      const format = (value: unknown) => Number(value) === -1 ? 'IT01' : `IT${value}`
      const labels: Record<string, string> = { lte: '及更高精度', lt: '以上精度（不含该级）', gte: '及更低精度', gt: '以下精度（不含该级）', eq: '', neq: '以外的等级' }
      const text = condition.op === 'between' && Array.isArray(condition.value) ? `${format(condition.value[0])}～${format(condition.value[1])}` : `${format(condition.value)}${labels[condition.op] ?? `（${condition.op}）`}`
      descriptions.push(negated ? `不满足${text}` : text)
    }
    for (const child of condition.all || condition.any || []) visit(child, negated)
    if (condition.not) visit(condition.not, !negated)
  }
  for (const rule of [...(rules?.rules || []), ...(rules?.process_configurations || [])]) if (rule.enabled !== false) visit(rule.when)
  return descriptions.length ? `当前规则：${[...new Set(descriptions)].join('；')}。允许输入 IT5～IT10，触发与否按规则判断。` : ''
}

function normalizeGenerateInputField(field: GenerateInputField): GenerateInputField {
  return {
    ...field,
    ...(isMaterialInput(field) ? { allow_custom: false, type: 'single_select' } : {}),
    ...(isPrecisionItField(field) ? { allowed_values: actualProjectItGrades.map(String), allow_custom: false } : {}),
    validation: normalizeFieldValidation(field),
  }
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
    .map(normalizeGenerateInputField)
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
    .map(normalizeGenerateInputField)
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

function isManualProcessSwitch(field: GenerateInputField) {
  return isBooleanField(field)
    && field.key.startsWith('project_factor.manual_process_')
    && field.source === '用户直接设定'
}

function isFeaturePresence(field: GenerateInputField) {
  return sharedFeatureField.test(field.key) && field.key.endsWith('.present') && isBooleanField(field)
}

const isDefaultOffField = (field: GenerateInputField) => isManualProcessSwitch(field) || isFeaturePresence(field)

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
  if (isPrecisionItField(field)) return actualProjectItGrades[0]
  if (field.examples?.length) return isArrayField(field) ? [field.examples[0]] : field.examples[0]
  if (field.allowed_values?.length) return isArrayField(field) ? [field.allowed_values[0]] : field.allowed_values[0]
  if (isBooleanField(field)) return true
  if (isNumberField(field)) return field.validation?.min ?? Math.min(0, field.validation?.max ?? 0)
  if (isArrayField(field)) return ['示例特征']
  const minLength = Math.max(0, field.validation?.min_length ?? 0)
  const maxLength = field.validation?.max_length
  const base = /material(?:\\.grade)?|材料|牌号/i.test(field.key) || /材料|牌号/.test(field.name || '') ? '9Cr18' : '示例值'
  const example = base.padEnd(minLength, '例')
  return typeof maxLength === 'number' ? example.slice(0, maxLength) : example
}

function isReusableFieldValue(field: GenerateInputField, value: any) {
  if (value === undefined || value === null) return false

  if (isArrayField(field)) {
    if (!Array.isArray(value)) return false
    if (value.some(item => typeof item !== 'string')) return false
    const normalized = value.map(item => String(item ?? '').trim()).filter(Boolean)
    if (normalized.length !== value.length) return false
    if (typeof field.validation?.min_length === 'number' && value.length < field.validation.min_length) return false
    if (typeof field.validation?.max_length === 'number' && value.length > field.validation.max_length) return false
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
    if (isPrecisionItField(field) && (!Number.isInteger(normalized) || !actualProjectItGrades.includes(normalized))) return false
    if (!isPrecisionItField(field) && field.unit === 'IT' && (!Number.isInteger(normalized) || normalized < 1 || normalized > 18)) return false
    if (/\.ra$/.test(field.key) && normalized <= 0) return false
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
  rulePackageRules?: Ref<Record<string, any> | null>
  hasRulePackage: Ref<boolean>
  projectId: Ref<number | null>
  schemaLoading?: Ref<boolean>
}) {
  const fieldValues = ref<Record<string, any>>({})
  const fieldOrigins = ref<Record<string, InputValueOrigin>>({})
  const customInputValues = ref<Record<string, string>>({})

  const schemaVersion = computed(() => String(args.inputSchema.value?.schema_version || '1.0'))

  const inputFields = computed<GenerateInputField[]>(() => {
    const schema = args.inputSchema.value
    if (!schema) return []
    if (String(schema.schema_version || '') === '2.0' && Array.isArray(schema.fields)) {
      const fields = normalizeV2Fields(schema.fields).map(field => ({ ...field, ...(isPrecisionItField(field) ? { rule_hint: actualItRuleHint(field.key, args.rulePackageRules?.value) } : {}) }))
      const rules = args.rulePackageRules?.value
      if (!rules || (!Array.isArray(rules.rules) && !Array.isArray(rules.process_configurations))) return fields
      const requirements = referencedRequirementOptions([
        ...(Array.isArray(rules.rules) ? rules.rules : []),
        ...(Array.isArray(rules.process_configurations) ? rules.process_configurations : []),
      ].filter(rule => rule.enabled !== false).map(rule => rule.when))
      if (requirements === null) return fields
      // Display old packages safely without changing their audited schema/hash.
      return fields.flatMap(field => {
        if (field.key !== 'special.requirements' || !isArrayField(field)) return [field]
        const options = (field.allowed_values || []).filter(value => requirements.has(value))
        return options.length ? [{ ...field, allowed_values: options, examples: options.slice(0, 3) }] : []
      })
    }
    const factorDictionary = normalizeFactorDictionary(schema.factor_dictionary)
    const required = normalizeSchemaFields(schema.required_inputs, true)
    const optional = normalizeSchemaFields(schema.optional_inputs, false)
    return [...required, ...optional]
      .map(field => applyFactorDictionary(field, factorDictionary))
      .map(normalizeGenerateInputField)
  })

  function isActiveField(field: GenerateInputField) {
    const match = sharedFeatureField.exec(field.key)
    return !match || match[2] === 'present' || fieldValues.value[`${match[1]}.present`] === true
  }
  const activeFields = computed(() => inputFields.value.filter(isActiveField))
  const activeInputFieldCount = computed(() => activeFields.value.length)
  const requiredFields = computed(() => activeFields.value.filter(field => field.required || (sharedFeatureField.test(field.key) && !isFeaturePresence(field))))
  const filledFieldCount = computed(() => activeFields.value.filter(field => hasConfirmedFieldValue(field)).length)

  const factorValues = computed(() => {
    const values: Record<string, any> = {}
    activeFields.value.forEach((field) => {
      const value = fieldValues.value[field.key]
      if (!hasConfirmedFieldValue(field)) return
      // Missing optional Bool input already means off; only submit a supplied
      // value when we can also send its actual input-origin metadata.
      if (isDefaultOffField(field) && fieldValueOrigin(field.key) === 'unset' && value === false) return
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

  const factorMetadata = computed<Record<string, GenerateInputMetadata>>(() => {
    const metadata: Record<string, GenerateInputMetadata> = {}
    activeFields.value.forEach((field) => {
      if (!hasConfirmedFieldValue(field)) return
      const origin = fieldValueOrigin(field.key)
      if (origin !== 'manual' && origin !== 'extracted') return
      metadata[field.key] = {
        origin,
        ...(isNumberField(field) && field.unit ? { unit: field.unit } : {}),
        evidence: [],
      }
    })
    return metadata
  })

  const canGenerate = computed(() =>
    Boolean(
      args.projectId.value
      && args.hasRulePackage.value
      && !args.schemaLoading?.value
      && (schemaVersion.value === '2.0'
        ? Array.isArray(args.inputSchema.value?.fields)
        : Array.isArray(args.inputSchema.value?.required_inputs) || Array.isArray(args.inputSchema.value?.optional_inputs))
      && requiredFields.value.every(field => hasConfirmedFieldValue(field))
      && activeFields.value.every(field => !hasFieldValue(field.key) || hasConfirmedFieldValue(field))
      && hardnessIntervalsValid(),
    ),
  )

  function initializeFieldValues() {
    const nextValues: Record<string, any> = {}
    const nextOrigins: Record<string, InputValueOrigin> = {}
    inputFields.value.forEach((field) => {
      const currentValue = fieldValues.value[field.key]
      const currentOrigin = fieldValueOrigin(field.key)
      if (currentOrigin !== 'unset' && isReusableFieldValue(field, currentValue)) {
        nextValues[field.key] = currentValue
        nextOrigins[field.key] = currentOrigin
        return
      }
      if (isArrayField(field)) {
        nextValues[field.key] = []
      } else if (isBooleanField(field)) {
        nextValues[field.key] = isDefaultOffField(field) ? false : undefined
      } else {
        nextValues[field.key] = ''
      }
      nextOrigins[field.key] = 'unset'
    })
    fieldValues.value = nextValues
    fieldOrigins.value = nextOrigins
    const fieldKeys = new Set(inputFields.value.map(field => field.key))
    customInputValues.value = Object.fromEntries(
      Object.entries(customInputValues.value).filter(([key]) => fieldKeys.has(key)),
    )
  }

  function hasFieldValue(key: string) {
    const value = fieldValues.value[key]
    if (Array.isArray(value)) return value.length > 0
    if (typeof value === 'string') return value.trim().length > 0
    return value !== undefined && value !== null
  }

  function hardnessIntervalsValid() {
    return inputFields.value.filter(field => field.key.endsWith('.hardness_min')).every(field => {
      const maxKey = field.key.replace(/\.hardness_min$/, '.hardness_max')
      if (!hasFieldValue(field.key) && !hasFieldValue(maxKey)) return true
      if (!hasFieldValue(field.key) || !hasFieldValue(maxKey)) return false
      return Number(fieldValues.value[field.key]) <= Number(fieldValues.value[maxKey])
    })
  }

  function hasValidFieldValue(field: GenerateInputField) {
    const value = fieldValues.value[field.key]
    if (/\.hardness_(min|max)$/.test(field.key) && !hardnessIntervalsValid()) return false
    if (isBooleanField(field)) return typeof value === 'boolean'
    if (isNumberField(field)) return isReusableFieldValue(field, value)
    return isReusableFieldValue(field, value) && hasFieldValue(field.key)
  }

  function fieldValueOrigin(key: string): InputValueOrigin {
    return fieldOrigins.value[key] || 'unset'
  }

  function hasConfirmedFieldValue(field: GenerateInputField) {
    const origin = fieldValueOrigin(field.key)
    if (origin === 'unset' && isDefaultOffField(field) && fieldValues.value[field.key] === false) return true
    return (origin === 'manual' || origin === 'extracted' || origin === 'example') && hasValidFieldValue(field)
  }

  function isConfirmedFieldValue(field: GenerateInputField) {
    return hasConfirmedFieldValue(field)
  }

  function isInvalidConfirmedFieldValue(field: GenerateInputField) {
    const origin = fieldValueOrigin(field.key)
    return (origin === 'manual' || origin === 'extracted' || origin === 'example') && !hasValidFieldValue(field)
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
    if (typeof value === 'boolean') return value ? '是' : '否'
    if (value === undefined || value === null) return ''
    return String(value)
  }

  function inputValue(event: Event) {
    return String((event.target as HTMLInputElement | HTMLTextAreaElement)?.value || '')
  }

  function setFieldText(key: string, value: string) {
    fieldValues.value[key] = value
    fieldOrigins.value[key] = 'manual'
  }

  function setFieldBoolean(key: string, value: boolean) {
    fieldValues.value[key] = value
    fieldOrigins.value[key] = 'manual'
    const match = sharedFeatureField.exec(key)
    if (match?.[2] === 'present' && !value) {
      for (const field of inputFields.value) {
        if (field.key.startsWith(`${match[1]}.`) && field.key !== key) {
          fieldValues.value[field.key] = ''
          fieldOrigins.value[field.key] = 'unset'
          delete customInputValues.value[field.key]
        }
      }
    }
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
    fieldOrigins.value[key] = 'manual'
  }

  function addCustomArrayValue(key: string) {
    const value = String(customInputValues.value[key] || '').trim()
    if (!value) return
    const list = arrayFieldValues(key)
    if (!list.includes(value)) {
      fieldValues.value[key] = [...list, value]
    }
    fieldOrigins.value[key] = 'manual'
    customInputValues.value[key] = ''
  }

  function addCustomSingleValue(key: string) {
    if (inputFields.value.find(field => field.key === key)?.allow_custom !== true) return
    const value = String(customInputValues.value[key] || '').trim()
    if (!value) return
    fieldValues.value[key] = value
    fieldOrigins.value[key] = 'manual'
    customInputValues.value[key] = ''
  }

  function clearAllFields() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      if (isArrayField(field)) nextValues[field.key] = []
      else if (isBooleanField(field)) nextValues[field.key] = isDefaultOffField(field) ? false : undefined
      else nextValues[field.key] = ''
    })
    fieldValues.value = nextValues
    fieldOrigins.value = Object.fromEntries(inputFields.value.map(field => [field.key, 'unset' as const]))
    customInputValues.value = {}
  }

  function fillExampleValues() {
    const nextValues: Record<string, any> = {}
    inputFields.value.forEach((field) => {
      if (isArrayField(field)) {
        const count = Math.min(
          Math.max(2, field.validation?.min_length ?? 0),
          field.validation?.max_length ?? Infinity,
        )
        const preferred = (field.allowed_values || []).slice(0, count)
        if (!field.allowed_values?.length || field.allow_custom) {
          while (preferred.length < count) preferred.push(`示例特征${preferred.length + 1}`)
        }
        nextValues[field.key] = preferred.length ? preferred : exampleValueForField(field)
        return
      }
      nextValues[field.key] = exampleValueForField(field)
    })
    fieldValues.value = nextValues
    fieldOrigins.value = Object.fromEntries(inputFields.value.map(field => [field.key, 'manual' as const]))
    customInputValues.value = {}
  }

  function resetFieldValues() {
    fieldValues.value = {}
    fieldOrigins.value = {}
    customInputValues.value = {}
  }

  watch(args.projectId, (nextProjectId, previousProjectId) => {
    if (nextProjectId !== previousProjectId) resetFieldValues()
  }, { flush: 'sync' })

  return {
    addCustomArrayValue,
    addCustomSingleValue,
    arrayFieldValues,
    activeInputFieldCount,
    canGenerate,
    clearAllFields,
    customInputValues,
    factorValues,
    factorMetadata,
    fieldPlaceholder,
    fieldPreviewValue,
    fieldTextValue,
    fieldValues,
    fieldValueOrigin,
    filledFieldCount,
    fillExampleValues,
    hasFieldValue,
    initializeFieldValues,
    inputFields,
    inputValue,
    isConfirmedFieldValue,
    isInvalidConfirmedFieldValue,
    nestFactorValues,
    resetFieldValues,
    schemaVersion,
    setCustomInput,
    setFieldBoolean,
    setFieldText,
    toggleFieldArrayValue,
  }
}
