import type { DocumentOperationDetailItem, SavedNormalizedRouteVersionResult } from '@/api'
import {
  buildProfileBlankScopeOptions,
  buildProfileStructureScopeOptions,
  buildThresholdRequirementScopeOptions,
  questionProfileForStep,
} from '@/config/analysisQuestionProfiles'
import { matchSemanticDominantProcess } from '@/config/semanticDominantProcessRules'
import { formatRouteDisplayName } from '@/composables/routeNameDisplay'
type Segment = SavedNormalizedRouteVersionResult['segments'][number]

const MATERIAL_PRIMARY_FIELD_NAMES = ['零件材质', '材料牌号'] as const
const MATERIAL_GENERIC_FIELD_NAMES = ['材料', '材质'] as const
const MATERIAL_STOP_TOKENS = [
  '材料标准',
  '标准',
  '技术条件',
  '技术要求',
  '工艺设备工艺',
  '设备工艺',
  '工艺',
  '牌号',
] as const
const MATERIAL_EXACT_BLACKLIST = new Set([
  '标准',
  '牌号',
  '材料牌号',
  '技术条件',
  '技术要求',
  '材料',
  '材质',
  '零件材质',
  '状态',
])
const MATERIAL_RELATED_FIELD_NAMES = [
  '零件材质',
  '材料牌号',
  '材料标准',
  '毛坯类型',
  '热处理状态',
  '热处理技术条件',
  '技术条件',
  '技术要求',
  '产品型号',
  '零组件号',
  '零组件名称',
  '工序',
  '设备',
] as const
const HEAT_TREAT_SCOPE_FIELD_NAMES = ['热处理技术条件', '热处理要求', '技术条件', '热处理状态'] as const
const BLANK_FIELD_NAMES = ['毛坯类型', '毛坯', '来料', '下料方式'] as const
const STRUCTURE_KEYWORD_MAP = {
  'structure::hole': ['孔', '孔径', '钻孔', '扩孔', '铰孔', '通孔', '盲孔'],
  'structure::slot': ['槽', '键槽', '槽宽', '铣槽'],
  'structure::step_face': ['台阶', '端面', '止口', '肩部'],
  'structure::thread': ['螺纹', '攻丝', '套丝'],
  'structure::solid_hollow': ['中空', '空心', '实心', '壁厚', '管'],
  'structure::other': ['扁', '球面', '锥面', '异形', '型面'],
} as const
const SIZE_VALUE_PATTERNS = {
  'size::diameter': /(?:[φΦ⌀]\s*\d+(?:\.\d+)?(?:[A-Za-z0-9]+)?|直径\s*\d+(?:\.\d+)?)/g,
  'size::length': /(?:长度\s*\d+(?:\.\d+)?|总长\s*\d+(?:\.\d+)?|L\s*=\s*\d+(?:\.\d+)?)/gi,
  'size::wall': /(?:壁厚\s*\d+(?:\.\d+)?|厚\s*\d+(?:\.\d+)?)/g,
  'size::section': /(?:截面\s*\d+(?:\.\d+)?|最大截面\s*\d+(?:\.\d+)?)/g,
  'size::ratio': /(?:长径比\s*\d+(?:\.\d+)?(?::\d+(?:\.\d+)?)?)/g,
} as const
const REQUIREMENT_KEYWORD_MAP = {
  'requirement::tolerance': ['IT', '公差', '尺寸精度', '配合'],
  'requirement::roughness': ['Ra', '粗糙度', '表面粗糙度'],
  'requirement::gd&t': ['同轴度', '圆柱度', '位置度', '跳动', '垂直度', '平面度', '形位'],
  'requirement::surface': ['表面质量', '烧伤', '发黑', '镀', '喷丸', '抛光'],
  'requirement::performance': ['HRC', '硬度', '强度', '渗氮', '调质', '正火', '淬火'],
  'requirement::other': ['检测', '试验', '探伤', '装配'],
} as const
export function splitVariants(text?: string | null) {
  return formatRouteDisplayName(String(text || ''))
    .split(/[／/]/)
    .map(part => part.trim())
    .filter(Boolean)
}

export function splitSourceOperationNames(text?: string | null) {
  return formatRouteDisplayName(String(text || ''))
    .split(/[／/,，、]/)
    .map(part => part.trim())
    .filter(Boolean)
}

export function uniqueSourceNamesForSegment(segment: Segment) {
  return Array.from(
    new Set(
      [
        ...(Array.isArray(segment.source_operation_names) ? segment.source_operation_names : []),
        ...(Array.isArray(segment.source_nodes) ? segment.source_nodes : []),
      ]
        .flatMap(name => splitSourceOperationNames(String(name || '').trim()))
        .filter(Boolean),
    ),
  )
}

function uniqueSourceOperationNamesForSegment(segment: Segment) {
  return Array.from(
    new Set(
      (Array.isArray(segment.source_operation_names) ? segment.source_operation_names : [])
        .flatMap(name => splitSourceOperationNames(String(name || '').trim()))
        .filter(Boolean),
    ),
  )
}

export function mergeCandidateNamesForSegment(segment: Segment | null) {
  if (!segment) return []
  const normalizedNames = splitVariants(String(segment.normalized_step_name || '').trim())
  if (normalizedNames.length >= 2) {
    return Array.from(new Set(normalizedNames.filter(Boolean)))
  }
  const sourceNames = uniqueSourceOperationNamesForSegment(segment)
  const fallbackSourceNames = sourceNames.length ? sourceNames : uniqueSourceNamesForSegment(segment)
  return Array.from(new Set([...fallbackSourceNames].filter(Boolean)))
}

export function semanticDominantProcessName(segment: Segment | null) {
  if (!segment) return null
  return matchSemanticDominantProcess([
    String(segment.normalized_step_name || '').trim(),
    ...uniqueSourceNamesForSegment(segment),
  ])
}

export function segmentVariantNames(segment: Segment | null) {
  if (!segment) return []
  const semanticDominant = semanticDominantProcessName(segment)
  if (semanticDominant) return [semanticDominant]
  const names = [
    ...splitVariants(segment.normalized_step_name),
    ...uniqueSourceNamesForSegment(segment),
  ]
  return Array.from(new Set(names.filter(Boolean)))
}
function cutBeforeNextField(value: string) {
  let result = String(value || '').trim()
  if (!result) return ''
  let cutIndex = result.length
  MATERIAL_RELATED_FIELD_NAMES.forEach((fieldName) => {
    const index = result.indexOf(fieldName)
    if (index > 0 && index < cutIndex) cutIndex = index
  })
  result = result.slice(0, cutIndex).trim()
  return result
}
function looksLikeMaterialValue(value: string, allowNumericAlloy = false) {
  const text = String(value || '').trim()
  if (!text) return false
  if (/^状态/i.test(text) || /状态\s*[A-Za-z0-9-]+$/i.test(text)) return false
  if (/^(标准|技术条件|技术要求|工艺|设备|牌号|材料|材质)/.test(text)) return false
  if (/(?:GJB|GB\/T|GB|HB|YB|JB\/T|ASTM|AMS)\s*[-A-Za-z0-9/]+/i.test(text)) return false
  if (/^\d+[xX×]\d+$/.test(text)) return false
  if (/^\d+[A-Za-z]?$/.test(text) && !allowNumericAlloy) return false
  return (
    (allowNumericAlloy && /^\d{3,5}$/.test(text)) ||
    /\b\d{1,2}(?:Cr|Ni|Mn|Si|Mo|Ti|Al|Cu|W|V)[0-9A-Za-z-]{0,24}\b/i.test(text) ||
    /\b(?:TC|TA|TB|H|GH)\d+[A-Za-z0-9-]*\b/i.test(text) ||
    /\b(?:Inconel|Monel|Hastelloy)\s*\d*[A-Za-z-]*\b/i.test(text) ||
    /钢$/.test(text)
  )
}
function sanitizeMaterialCandidate(rawValue: string, allowNumericAlloy = false) {
  let value = String(rawValue || '').trim()
  if (!value) return ''
  MATERIAL_STOP_TOKENS.forEach((token) => {
    const index = value.indexOf(token)
    if (index >= 0) {
      value = value.slice(0, index).trim()
    }
  })
  value = value
    .replace(/^(材料牌号|零件材质|材料|材质|牌号)/, '')
    .replace(/^状态/i, '')
    .replace(/[=:：]/g, '')
    .trim()
  if (!value || MATERIAL_EXACT_BLACKLIST.has(value)) return ''
  if (/^T\d+$/i.test(value)) return ''
  if (/^(标准|技术条件|技术要求|工艺|设备)/.test(value)) return ''
  if (/(?:GJB|GB\/T|GB|HB|YB|JB\/T|ASTM|AMS)\s*[-A-Za-z0-9/]+/i.test(value)) return ''
  if (/^\d+[xX×]\d+$/.test(value)) return ''
  if (/^\d+[A-Za-z]?$/.test(value) && !(allowNumericAlloy && /^\d{3,5}$/.test(value))) return ''
  if (
    /^[A-Za-z]?\d+[A-Za-z-]*$/.test(value)
    && !/Cr|Ni|Mo|Mn|Si|Ti|Al|Cu|W|V|钢/i.test(value)
    && !(allowNumericAlloy && /^\d{3,5}$/.test(value))
  ) return ''
  if (!/[A-Za-z]|钢/.test(value) && !(allowNumericAlloy && /^\d{3,5}$/.test(value))) return ''
  return value
}
function extractNamedValuesFromTexts(texts: string[], fieldNames: readonly string[]) {
  const values = new Set<string>()
  const allowNumericAlloy = fieldNames.some(fieldName =>
    MATERIAL_PRIMARY_FIELD_NAMES.includes(fieldName as (typeof MATERIAL_PRIMARY_FIELD_NAMES)[number]),
  )
  texts.forEach((text) => {
    if (!text) return
    text.split(/\r?\n/).forEach((rawLine) => {
      const line = String(rawLine || '').trim()
      const compact = String(rawLine || '').replace(/\s+/g, '').trim()
      if (!line && !compact) return
      fieldNames.forEach((fieldName) => {
        if (!compact.includes(fieldName)) return
        let match = line.match(new RegExp(`${fieldName}\\s*[=:：]\\s*([A-Za-z0-9一-龥/\\-_.#]+)`, 'i'))
        if (!match) {
          if (
            MATERIAL_GENERIC_FIELD_NAMES.includes(fieldName as (typeof MATERIAL_GENERIC_FIELD_NAMES)[number]) &&
            /材料标准|材料技术条件|材料状态|材质状态/.test(compact)
          ) {
            return
          }
          match = compact.match(new RegExp(`${fieldName}\\s*[=:：]?\\s*([A-Za-z0-9一-龥/\\-_.#]+)`, 'i'))
        }
        const rawValue = cutBeforeNextField(String(match?.[1] || '').trim().replace(/[;,，；。]+$/g, ''))
        const value = sanitizeMaterialCandidate(rawValue, allowNumericAlloy)
        if (value && value.length <= 32 && looksLikeMaterialValue(value, allowNumericAlloy)) values.add(value)
      })
    })
  })
  return [...values].sort((a, b) => a.localeCompare(b))
}

function sanitizeLooseFieldValue(rawValue: string) {
  const value = cutBeforeNextField(String(rawValue || '').trim().replace(/[;,，；。]+$/g, ''))
    .replace(/^(热处理技术条件|热处理要求|技术条件|热处理状态|技术要求)/, '')
    .replace(/[=:：]/g, '')
    .trim()
  if (!value || MATERIAL_EXACT_BLACKLIST.has(value)) return ''
  if (/^(标准|技术条件|技术要求|工艺|设备|牌号|材料|材质|状态)$/.test(value)) return ''
  return value.length <= 40 ? value : value.slice(0, 40)
}

function extractLooseNamedValuesFromTexts(texts: string[], fieldNames: readonly string[]) {
  const values = new Set<string>()
  texts.forEach((text) => {
    if (!text) return
    text.split(/\r?\n/).forEach((rawLine) => {
      const line = String(rawLine || '').trim()
      const compact = String(rawLine || '').replace(/\s+/g, '').trim()
      if (!line && !compact) return
      fieldNames.forEach((fieldName) => {
        if (!compact.includes(fieldName)) return
        let match = line.match(new RegExp(`${fieldName}\\s*[=:：]\\s*([A-Za-z0-9一-龥/\\-_.#]+)`, 'i'))
        if (!match) {
          match = compact.match(new RegExp(`${fieldName}\\s*[=:：]?\\s*([A-Za-z0-9一-龥/\\-_.#]+)`, 'i'))
        }
        const value = sanitizeLooseFieldValue(String(match?.[1] || ''))
        if (value) values.add(value)
      })
    })
  })
  return [...values].sort((a, b) => a.localeCompare(b))
}

type TextUnit = {
  text: string
  docKey: string
}

function extractNamedValuesFromText(text: string, fieldNames: readonly string[]) {
  return extractNamedValuesFromTexts([text], fieldNames)
}

function extractLooseNamedValuesFromText(text: string, fieldNames: readonly string[]) {
  return extractLooseNamedValuesFromTexts([text], fieldNames)
}

function extractMaterialCodesFromText(text: string) {
  return extractMaterialCodesFromTexts([text])
}

function mergeValueDocStats(
  units: TextUnit[],
  extractValues: (text: string) => string[],
) {
  const valueDocs = new Map<string, Set<string>>()
  units.forEach((unit) => {
    extractValues(unit.text).forEach((value) => {
      if (!valueDocs.has(value)) valueDocs.set(value, new Set())
      valueDocs.get(value)!.add(unit.docKey)
    })
  })
  return valueDocs
}

function buildCountedOptions(prefix: string, valueDocs: Map<string, Set<string>>, totalCount: number) {
  const seen = new Set<string>()
  return [...valueDocs.entries()]
    .map(([value, docSet]) => ({
      value: String(value || '').trim(),
      docCount: docSet.size,
    }))
    .filter(item => item.value)
    .filter((item) => {
      const key = item.value.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .sort((a, b) => (b.docCount - a.docCount) || a.value.localeCompare(b.value))
    .map(item => ({
      value: `${prefix}::${item.value}`,
      label: item.value,
      docCount: item.docCount,
      totalCount,
      countLabel: totalCount > 0 ? `${item.docCount}/${totalCount}` : String(item.docCount),
    }))
}

function mergeOptionStats(...stats: Array<Map<string, Set<string>>>) {
  const merged = new Map<string, Set<string>>()
  stats.forEach((stat) => {
    stat.forEach((docSet, value) => {
      if (!merged.has(value)) merged.set(value, new Set())
      docSet.forEach(docKey => merged.get(value)!.add(docKey))
    })
  })
  return merged
}

function materialValueDocStatsFromUnits(units: TextUnit[]) {
  return mergeOptionStats(
    mergeValueDocStats(units, text => extractNamedValuesFromText(text, MATERIAL_PRIMARY_FIELD_NAMES)),
    mergeValueDocStats(units, text => extractNamedValuesFromText(text, MATERIAL_GENERIC_FIELD_NAMES)),
    mergeValueDocStats(units, extractMaterialCodesFromText),
  )
}

function extractMaterialCodesFromTexts(texts: string[]) {
  const values = new Set<string>()
  const patterns = [
    /\b\d{1,2}Cr[0-9A-Za-z-]{1,24}\b/g,
    /\b\d{1,2}Cr[0-9A-Za-z-]*Ni[0-9A-Za-z-]*\b/g,
    /\b\d{1,2}(?:Cr|Mn|Si|Mo|Ni|Ti|Al|Cu|W|V)[0-9A-Za-z-]{1,24}\b/g,
    /\b[0-9A-Za-z-]{2,24}钢\b/g,
  ]
  texts.forEach((text) => {
    patterns.forEach((pattern) => {
      const matches = text.match(pattern) || []
      matches.forEach((match) => {
        const value = sanitizeMaterialCandidate(String(match || '').trim().replace(/[;,，；。]+$/g, ''))
        if (value && value.length <= 32) values.add(value)
      })
    })
  })
  return [...values].sort((a, b) => a.localeCompare(b))
}
function extractCurrentSegmentTexts(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const matchedPdfNames = new Set(
    (segment.matched_detail_rows || [])
      .map((row) => String(row.pdf_name || '').trim())
      .filter(Boolean),
  )
  const detailTexts = detailRows
    .filter((row) => {
      const docId = Number(row.document_id || 0)
      if (matchedDocIds.size && docId > 0) return matchedDocIds.has(docId)
      const pdfName = String(row.pdf_name || '').trim()
      return !!pdfName && matchedPdfNames.has(pdfName)
    })
    .map((row) => `${row.operation_name || ''}\n${row.operation_content || ''}`)
    .filter(Boolean)
  return [...detailTexts, ...matchedDocumentTexts.filter(Boolean)]
}

function extractCurrentSegmentTextUnits(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const matchedPdfNames = new Set(
    (segment.matched_detail_rows || [])
      .map((row) => String(row.pdf_name || '').trim())
      .filter(Boolean),
  )
  const units: TextUnit[] = []
  const seen = new Set<string>()

  detailRows.forEach((row, index) => {
    const docId = Number(row.document_id || 0)
    if (matchedDocIds.size && docId > 0 && !matchedDocIds.has(docId)) return
    if (!matchedDocIds.size) {
      const pdfName = String(row.pdf_name || '').trim()
      if (matchedPdfNames.size && (!pdfName || !matchedPdfNames.has(pdfName))) return
    }
    const text = `${row.operation_name || ''}\n${row.operation_content || ''}`.trim()
    if (!text) return
    const docKey = docId > 0 ? `doc:${docId}` : `pdf:${row.pdf_name || index}`
    const key = `${docKey}::${text}`
    if (seen.has(key)) return
    seen.add(key)
    units.push({ text, docKey })
  })

  if (!units.length) {
    matchedDocumentTexts.forEach((text, index) => {
      const normalizedText = String(text || '').trim()
      if (!normalizedText) return
      const docKey = `matched:${index + 1}`
      const key = `${docKey}::${normalizedText}`
      if (seen.has(key)) return
      seen.add(key)
      units.push({ text: normalizedText, docKey })
    })
  }

  return units
}

function extractMatchedDocumentTextUnits(matchedDocumentTexts: string[] = []) {
  const units: TextUnit[] = []
  const seen = new Set<string>()
  matchedDocumentTexts.forEach((text, index) => {
    const normalizedText = String(text || '').trim()
    if (!normalizedText) return
    const docKey = `matched:${index + 1}`
    const key = `${docKey}::${normalizedText}`
    if (seen.has(key)) return
    seen.add(key)
    units.push({ text: normalizedText, docKey })
  })
  return units
}
export function buildSegmentSemanticText(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
  variantName?: string | null,
) {
  const names = new Set<string>()
  const semanticDominant = variantName ? null : semanticDominantProcessName(segment)
  const normalizedName = semanticDominant || String(segment.normalized_step_name || '').trim()
  if (normalizedName) names.add(normalizedName)
  if (!semanticDominant) {
    uniqueSourceNamesForSegment(segment).forEach(name => names.add(String(name || '').trim()))
  }
  if (variantName) names.add(String(variantName || '').trim())
  const texts = variantName
    ? [
      ...detailRows
        .filter(row => detailRowMatchesVariant(row, variantName))
        .map(row => `${row.operation_name || ''}\n${row.operation_content || ''}`),
      ...matchedTextsForVariant(matchedDocumentTexts, variantName),
    ]
    : extractCurrentSegmentTexts(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  return [
    ...Array.from(names).filter(Boolean),
    ...texts.map(text => String(text || '').trim()).filter(Boolean),
  ].join('\n')
}
export function detailRowMatchesVariant(row: DocumentOperationDetailItem, variantName: string) {
  const normalizedVariant = String(variantName || '').trim()
  if (!normalizedVariant) return false
  const operationName = String(row.operation_name || '').trim()
  if (!operationName) return false
  const variants = splitVariants(operationName)
  return variants.includes(normalizedVariant) || operationName.includes(normalizedVariant)
}
export function matchedTextsForVariant(matchedDocumentTexts: string[], variantName: string) {
  const normalizedVariant = String(variantName || '').trim()
  if (!normalizedVariant) return []
  return matchedDocumentTexts.filter((text) => String(text || '').includes(normalizedVariant))
}
function dedupeOptionList(prefix: string, values: string[]) {
  const seen = new Set<string>()
  return values
    .map(value => String(value || '').trim())
    .filter(Boolean)
    .filter((value) => {
      const key = value.toLowerCase()
      if (seen.has(key)) return false
      seen.add(key)
      return true
    })
    .map(value => ({ value: `${prefix}::${value}`, label: value }))
}
function extractKeywordOptions(
  texts: string[],
  keywords: readonly string[],
  prefix: string,
  mode: 'line' | 'keyword' = 'line',
) {
  const counter = new Map<string, number>()
  texts.forEach((text) => {
    const lines = String(text || '').split(/\r?\n/)
    lines.forEach((rawLine) => {
      const line = String(rawLine || '').trim()
      if (!line) return
      keywords.forEach((keyword) => {
        if (!line.includes(keyword)) return
        if (mode === 'keyword') {
          counter.set(keyword, (counter.get(keyword) || 0) + 1)
          return
        }
        const clipped = line.length > 36 ? `${line.slice(0, 36)}...` : line
        counter.set(clipped, (counter.get(clipped) || 0) + 1)
      })
    })
  })
  return dedupeOptionList(
    prefix,
    [...counter.entries()]
      .sort((a, b) => (b[1] - a[1]) || a[0].localeCompare(b[0]))
      .map(([value]) => value),
  )
}
function fallbackDynamicOptions(prefix: string, kindLabel: string) {
  return [
    { value: `${prefix}::未自动识别`, label: `当前样本里暂未自动识别出明确${kindLabel}` },
    { value: `${prefix}::需人工补充`, label: `需要人工补充${kindLabel}范围` },
  ]
}
export function materialOptionsForSegment(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const units = extractCurrentSegmentTextUnits(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  const previewUnits = extractMatchedDocumentTextUnits(matchedDocumentTexts)
  const totalCount = Number(segment.doc_coverage?.total_docs || 0)
    || new Set([...units, ...previewUnits].map(unit => unit.docKey)).size
  let valueDocs = materialValueDocStatsFromUnits(units)
  if (!valueDocs.size && previewUnits.length) {
    valueDocs = materialValueDocStatsFromUnits(previewUnits)
  }
  return buildCountedOptions('material', valueDocs, totalCount)
}
export function pickMaterialOptionsByBasis(
  basis: string,
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  if (!['material_basis::grade', 'material_basis::class', 'material_basis::spec'].includes(basis)) {
    return fallbackDynamicOptions('material_scope', '材料')
  }
  if (basis === 'material_basis::spec') {
    const units = extractCurrentSegmentTextUnits(segment, detailRows, matchedDocIds, matchedDocumentTexts)
    const totalCount = Number(segment.doc_coverage?.total_docs || 0) || new Set(units.map(unit => unit.docKey)).size
    const values = buildCountedOptions(
      'material_scope',
      mergeValueDocStats(units, text => extractLooseNamedValuesFromText(text, HEAT_TREAT_SCOPE_FIELD_NAMES)),
      totalCount,
    )
    return values.length ? values : fallbackDynamicOptions('material_scope', '热处理技术条件')
  }
  return materialOptionsForSegment(segment, detailRows, matchedDocIds, matchedDocumentTexts).map(option => ({
    value: option.value.replace(/^material::/, 'material_scope::'),
    label: option.label,
    countLabel: option.countLabel,
    docCount: option.docCount,
    totalCount: option.totalCount,
  }))
}
const TURNING_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::outer_circle', fallbackLabel: '外圆', keywords: ['主外圆', '台阶外圆', '外圆', '回转外形', '外形轮廓', '车外圆', '车外形'] },
  { value: 'machining_feature::inner_hole', fallbackLabel: '内孔', keywords: ['中心孔', '定位孔', '阶梯孔', '复合孔', '通孔', '盲孔', '内孔', '孔径', '钻孔', '镗孔', '铰孔', '孔'] },
  { value: 'machining_feature::end_face', fallbackLabel: '端面', keywords: ['平端面', '端面'] },
  { value: 'machining_feature::step_outer', fallbackLabel: '台阶外圆', keywords: ['台阶外圆', '轴肩', '台阶'] },
  { value: 'machining_feature::slot', fallbackLabel: '槽类特征', keywords: ['退刀槽', '环槽', '切槽', '越程槽', '槽'] },
  { value: 'machining_feature::thread', fallbackLabel: '螺纹相关特征', keywords: ['外螺纹', '内螺纹', '螺纹孔', '攻螺纹', '攻丝', '车螺纹', '螺纹'] },
]
const HOLE_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::inner_hole', fallbackLabel: '内孔', keywords: ['内孔', '一般孔', '孔'] },
  { value: 'machining_feature::compound_hole', fallbackLabel: '复合孔', keywords: ['复合孔', '组合孔'] },
  { value: 'machining_feature::step_hole', fallbackLabel: '阶梯孔', keywords: ['阶梯孔', '台阶孔'] },
  { value: 'machining_feature::through_hole', fallbackLabel: '通孔', keywords: ['通孔'] },
  { value: 'machining_feature::blind_hole', fallbackLabel: '盲孔', keywords: ['盲孔'] },
  { value: 'machining_feature::locating_hole', fallbackLabel: '定位孔/中心孔', keywords: ['定位孔', '中心孔'] },
  { value: 'machining_feature::thread_base_hole', fallbackLabel: '螺纹底孔', keywords: ['螺纹底孔', '底孔'] },
  { value: 'machining_feature::hole_mouth', fallbackLabel: '孔口特征', keywords: ['沉孔', '沉台', '锪平', '孔口'] },
]
const END_FACE_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::end_face', fallbackLabel: '平端面', keywords: ['平端面', '端面'] },
  { value: 'machining_feature::datum_face', fallbackLabel: '基准端面', keywords: ['基准端面', '定位端面'] },
  { value: 'machining_feature::fit_face', fallbackLabel: '贴合端面', keywords: ['贴合端面', '配合端面', '密封端面'] },
  { value: 'machining_feature::hole_mouth_face', fallbackLabel: '孔口端面/沉台端面', keywords: ['孔口端面', '沉台端面', '沉台'] },
]
const OUTER_SURFACE_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::outer_circle', fallbackLabel: '主外圆', keywords: ['主外圆', '外圆'] },
  { value: 'machining_feature::step_outer', fallbackLabel: '台阶外圆', keywords: ['台阶外圆', '轴肩', '台阶'] },
  { value: 'machining_feature::outer_profile', fallbackLabel: '回转外形', keywords: ['回转外形', '外形轮廓', '车外形'] },
  { value: 'machining_feature::outer_datum', fallbackLabel: '基准外圆', keywords: ['基准外圆', '定位外圆'] },
]
const GROOVE_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::slot', fallbackLabel: '退刀槽', keywords: ['退刀槽'] },
  { value: 'machining_feature::ring_slot', fallbackLabel: '环槽', keywords: ['环槽'] },
  { value: 'machining_feature::cut_slot', fallbackLabel: '切槽', keywords: ['切槽'] },
  { value: 'machining_feature::overtravel_slot', fallbackLabel: '越程槽', keywords: ['越程槽'] },
  { value: 'machining_feature::keyslot', fallbackLabel: '键槽', keywords: ['键槽', '花键槽'] },
  { value: 'machining_feature::slot', fallbackLabel: '槽', keywords: ['槽'] },
]
const THREAD_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::thread_hole', fallbackLabel: '螺纹孔', keywords: ['螺纹孔'] },
  { value: 'machining_feature::internal_thread', fallbackLabel: '内螺纹', keywords: ['内螺纹'] },
  { value: 'machining_feature::external_thread', fallbackLabel: '外螺纹', keywords: ['外螺纹'] },
  { value: 'machining_feature::thread_base_hole', fallbackLabel: '螺纹底孔', keywords: ['螺纹底孔', '底孔'] },
  { value: 'machining_feature::thread', fallbackLabel: '螺纹', keywords: ['车螺纹', '攻螺纹', '攻丝', '套螺纹', '螺纹'] },
]
const FLAT_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::flat', fallbackLabel: '扁位', keywords: ['扁位', '削平', '割扁', '铣扁', '扁'] },
  { value: 'machining_feature::opposite_side', fallbackLabel: '对边', keywords: ['对边'] },
  { value: 'machining_feature::clamp_plane', fallbackLabel: '装夹平面', keywords: ['装夹平面', '定位平面'] },
  { value: 'machining_feature::clearance_flat', fallbackLabel: '避让平面', keywords: ['避让', '让位', '清根'] },
]
const PROFILE_HOLE_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::profile_hole', fallbackLabel: '型孔', keywords: ['型孔'] },
  { value: 'machining_feature::window_hole', fallbackLabel: '窗口孔', keywords: ['窗口孔'] },
  { value: 'machining_feature::profile_outline', fallbackLabel: '异形轮廓', keywords: ['异形轮廓', '异形孔', '异形'] },
  { value: 'machining_feature::open_profile', fallbackLabel: '开口型孔', keywords: ['开口孔', '切边孔', '开口型孔'] },
  { value: 'machining_feature::compound_profile', fallbackLabel: '复合型孔', keywords: ['复合型孔', '复合孔口'] },
]
const MILLING_STRUCTURE_FEATURE_KEYWORDS = [
  { value: 'machining_feature::plane', fallbackLabel: '平面', keywords: ['装夹平面', '定位平面', '铣平面', '平面'] },
  { value: 'machining_feature::flat', fallbackLabel: '扁位', keywords: ['扁位', '铣扁', '割扁', '对边', '扁'] },
  { value: 'machining_feature::slot', fallbackLabel: '槽类特征', keywords: ['键槽', '铣槽', '挖槽', '槽'] },
  { value: 'machining_feature::keyslot', fallbackLabel: '键槽', keywords: ['花键槽', '键槽'] },
  { value: 'machining_feature::profile', fallbackLabel: '型面或异形轮廓', keywords: ['异形轮廓', '异形', '型面', '型孔', '割型孔', '打型孔', '轮廓'] },
]

function normalizeDocFeatureLabel(label: string) {
  return String(label || '')
    .replace(/^(车|铣|磨|研|钻|扩|镗|铰|攻|打|挖|割)/, '')
    .replace(/^(一般|普通)/, '')
    .trim()
}

function buildDocDrivenMachiningFeatureOptions(
  texts: string[],
  defs: Array<{ value: string; fallbackLabel: string; keywords: string[] }>,
) {
  const joined = texts.join('\n')
  const options: Array<{ value: string; label: string }> = []
  const seen = new Set<string>()

  defs.forEach((item) => {
    const matchedKeyword = item.keywords.find(keyword => joined.includes(keyword))
    if (!matchedKeyword) return
    const label = normalizeDocFeatureLabel(matchedKeyword) || item.fallbackLabel
    const key = `${item.value}::${label}`
    if (seen.has(key)) return
    seen.add(key)
    options.push({ value: item.value, label })
  })

  return options
}

function operationNameMatchesSegmentVariants(operationName: string, variantNames: string[]) {
  const normalizedName = String(operationName || '').trim()
  if (!normalizedName) return false
  if (!variantNames.length) return true
  const splitNames = splitVariants(normalizedName)
  return variantNames.some((variant) =>
    splitNames.includes(variant)
    || normalizedName.includes(variant)
    || variant.includes(normalizedName),
  )
}

function extractCurrentOperationContentTexts(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
) {
  const variantNames = segmentVariantNames(segment)
  const contentTexts = new Set<string>()

  ;(segment.matched_detail_rows || []).forEach((row) => {
    const operationName = String(row.operation_name || '').trim()
    const operationContent = String(row.operation_content || '').trim()
    if (!operationContent) return
    if (!operationNameMatchesSegmentVariants(operationName, variantNames)) return
    contentTexts.add(operationContent)
  })

  detailRows.forEach((row) => {
    const operationName = String(row.operation_name || '').trim()
    const operationContent = String(row.operation_content || '').trim()
    if (!operationContent) return
    if (!operationNameMatchesSegmentVariants(operationName, variantNames)) return
    contentTexts.add(operationContent)
  })

  return [...contentTexts]
}

export function machiningStructureFeatureOptionsForSegment(
  mode: 'turning' | 'milling' | 'hole' | 'end_face' | 'outer_surface' | 'groove' | 'thread' | 'flat' | 'profile_hole',
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  _matchedDocIds: Set<number>,
  _matchedDocumentTexts: string[] = [],
) {
  const texts = extractCurrentOperationContentTexts(segment, detailRows)
  const defs = mode === 'turning'
    ? TURNING_STRUCTURE_FEATURE_KEYWORDS
    : mode === 'hole'
      ? HOLE_STRUCTURE_FEATURE_KEYWORDS
      : mode === 'end_face'
        ? END_FACE_STRUCTURE_FEATURE_KEYWORDS
        : mode === 'outer_surface'
          ? OUTER_SURFACE_STRUCTURE_FEATURE_KEYWORDS
          : mode === 'groove'
            ? GROOVE_STRUCTURE_FEATURE_KEYWORDS
            : mode === 'thread'
              ? THREAD_STRUCTURE_FEATURE_KEYWORDS
              : mode === 'flat'
                ? FLAT_STRUCTURE_FEATURE_KEYWORDS
                : mode === 'profile_hole'
                  ? PROFILE_HOLE_STRUCTURE_FEATURE_KEYWORDS
                  : MILLING_STRUCTURE_FEATURE_KEYWORDS
  const options = buildDocDrivenMachiningFeatureOptions(texts, defs)
  return {
    options: options.length ? options : defs.map(({ value, fallbackLabel }) => ({ value, label: fallbackLabel })),
    usedFallback: options.length === 0,
  }
}
export function structureOptionsForSegment(
  structureType: string,
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const texts = extractCurrentSegmentTexts(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  const profile = questionProfileForStep(buildSegmentSemanticText(segment, detailRows, matchedDocIds, matchedDocumentTexts))
  if (profile?.structureScopeFallbacks) {
    return buildProfileStructureScopeOptions(profile, texts)
  }
  const keywords = STRUCTURE_KEYWORD_MAP[structureType as keyof typeof STRUCTURE_KEYWORD_MAP] || []
  return extractKeywordOptions(texts, keywords, 'structure_scope', 'keyword')
}
export function sizeOptionsForSegment(
  sizeType: string,
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const texts = extractCurrentSegmentTexts(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  const pattern = SIZE_VALUE_PATTERNS[sizeType as keyof typeof SIZE_VALUE_PATTERNS]
  const values = new Set<string>()
  texts.forEach((text) => {
    if (!pattern) return
    const matches = text.match(pattern) || []
    matches.forEach((match) => values.add(String(match).trim()))
  })
  return dedupeOptionList('size_scope', [...values])
}
export function blankOptionsForSegment(
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const texts = extractCurrentSegmentTexts(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  const profile = questionProfileForStep(buildSegmentSemanticText(segment, detailRows, matchedDocIds, matchedDocumentTexts))
  if (profile?.blankScopeFallbacks) {
    return buildProfileBlankScopeOptions(profile, texts)
  }
  const named = extractNamedValuesFromTexts(texts, BLANK_FIELD_NAMES)
  const keywordHits = extractKeywordOptions(
    texts,
    ['棒料', '管料', '板料', '锻件', '铸件', '焊接件', '采购', '成品料', '半成品'],
    'blank_scope',
    'keyword',
  )
  return [
    ...dedupeOptionList('blank_scope', named),
    ...keywordHits.filter(option => !named.includes(option.label)),
  ]
}
export function requirementOptionsForSegment(
  requirementType: string,
  segment: Segment,
  detailRows: DocumentOperationDetailItem[],
  matchedDocIds: Set<number>,
  matchedDocumentTexts: string[] = [],
) {
  const texts = extractCurrentSegmentTexts(segment, detailRows, matchedDocIds, matchedDocumentTexts)
  const profile = questionProfileForStep(buildSegmentSemanticText(segment, detailRows, matchedDocIds, matchedDocumentTexts))
  if (profile?.requirementScopeFallbacks || profile?.requirementScopeFallbacksByType) {
    return buildThresholdRequirementScopeOptions(profile, texts, requirementType)
  }
  const keywords = REQUIREMENT_KEYWORD_MAP[requirementType as keyof typeof REQUIREMENT_KEYWORD_MAP] || []
  const keywordOptions = extractKeywordOptions(texts, keywords, 'requirement_scope', 'keyword')
  const regexMatches = new Set<string>()
  texts.forEach((text) => {
    const matches = text.match(/(?:Ra\s*\d+(?:\.\d+)?|IT\d+|HRC\s*\d+(?:-\d+)?)/g) || []
    matches.forEach((match) => regexMatches.add(String(match).trim()))
  })
  return [
    ...dedupeOptionList('requirement_scope', [...regexMatches]),
    ...keywordOptions.filter(option => !regexMatches.has(option.label)),
  ]
}
