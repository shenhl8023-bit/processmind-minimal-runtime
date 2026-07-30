import type { GroupTemplateNode as ApiGroupTemplateNode } from '@/api/extract'

export const TEMPLATE_GROUP_MAPPING_DRAFT_STORAGE_KEY = 'template_group_mapping_draft'
export const TEMPLATE_GROUP_MAPPING_VERSION = 3

export const ALLOWED_TEMPLATE_STEP_FAMILIES = [
  '车削/成形类',
  '孔加工类',
  '特征加工类',
] as const

export type TemplateStepFamily = typeof ALLOWED_TEMPLATE_STEP_FAMILIES[number]
export type TemplateGroupNode = ApiGroupTemplateNode

export type TemplateOperation = {
  id?: number
  name: string
  sequence?: number
  step_family?: string | null
  step_items?: string[]
  source_operation_id?: number | null
}

export type TemplateAliasBinding = {
  source_operation_id: number
  alias: string
  template_group_key: string
  template_group_id: string
  template_group_name: string
  template_group_path: string[]
  feature_selections: string[]
}

export type TemplateGroupMappingConfidence = 'high' | 'medium' | 'low'

export type TemplateGroupMappingCandidate = {
  group_id: string
  path: string[]
  score: number
  reason: string
}

export type TemplateGroupMappingSuggestion = {
  operation_id: number
  operation_name: string
  feature: string
  position: string
  confidence: TemplateGroupMappingConfidence
  requires_manual_confirmation: boolean
  recommended_group_id: string | null
  candidates: TemplateGroupMappingCandidate[]
  evidence: string[]
  reasons: string[]
}

export type TemplateGroupModelChoice = {
  group_id?: string | null
  confidence?: number | null
}

export type RouteSegmentWithAliases = {
  source_operation_ids?: number[]
  operation_ids?: number[]
  template_group_aliases?: Array<Partial<TemplateAliasBinding> & Pick<TemplateAliasBinding, 'source_operation_id' | 'alias'>>
  [key: string]: unknown
}

export type LegacyAliasInvalidation = {
  source_operation_id: number
  alias: string
  template_group_path: string[]
  reason: string
}

function cleanId(value: unknown) {
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : 0
}

function cleanText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizePath(path: unknown): string[] {
  return (Array.isArray(path) ? path : [])
    .map(part => cleanText(part).normalize('NFC'))
    .filter(Boolean)
}

function pathKey(path: unknown) {
  return JSON.stringify(normalizePath(path))
}

function normalizeSearchText(value: unknown) {
  return cleanText(value).normalize('NFC').replace(/[\s，,。；;：:（）()、/_-]+/g, '').toLowerCase()
}

function cloneBinding(binding: TemplateAliasBinding): TemplateAliasBinding {
  return {
    source_operation_id: binding.source_operation_id,
    alias: binding.alias,
    template_group_key: binding.template_group_key,
    template_group_id: binding.template_group_id,
    template_group_name: binding.template_group_name,
    template_group_path: [...binding.template_group_path],
    feature_selections: [...binding.feature_selections],
  }
}

function cloneAliases(aliases: Record<string, TemplateAliasBinding>) {
  return Object.fromEntries(Object.entries(aliases).map(([id, binding]) => [id, cloneBinding(binding)]))
}

export function flattenTemplateGroups(tree: TemplateGroupNode[]) {
  const result: TemplateGroupNode[] = []
  const visit = (nodes: TemplateGroupNode[]) => {
    nodes.forEach((node) => {
      result.push(node)
      visit(node.children || [])
    })
  }
  visit(tree)
  return result
}

export function findTemplateGroupByKey(tree: TemplateGroupNode[], key: string) {
  const normalizedKey = cleanText(key)
  return flattenTemplateGroups(tree).find(group => group.key === normalizedKey) || null
}

export function findTemplateGroupByPath(tree: TemplateGroupNode[], path: string[]) {
  const expected = pathKey(path)
  return flattenTemplateGroups(tree).find(group => pathKey(group.path) === expected) || null
}

const FEATURE_TERM_ALIASES: Record<string, string[]> = {
  '轴端面': ['端面', '平端面', '车端面'],
  '外圆柱面': ['外圆', '车外圆', '磨外圆', '研外圆'],
  '孔': ['孔', '钻孔', '镗孔', '铰孔', '研孔'],
  '孔(盲孔)': ['盲孔', '钻盲孔', '孔'],
  '孔(通孔)': ['通孔', '钻通孔', '孔'],
  'U形外环槽': ['外环槽', '车槽', '铣槽', '磨槽'],
  'U形内环槽': ['内环槽', '车槽', '铣槽', '磨槽'],
  '倒角': ['倒角'],
  '内倒角': ['内倒角', '倒角'],
  '外倒角': ['外倒角', '倒角'],
  '边倒角': ['边倒角', '倒角'],
  '倒圆': ['倒圆', '磨圆'],
  '回转面倒圆': ['回转面倒圆', '倒圆', '磨圆'],
  '平面': ['平面', '铣面', '磨面'],
}

function featureTerms(feature: string) {
  return [...new Set([feature, ...(FEATURE_TERM_ALIASES[feature] || [])])]
}

type ScoredTemplateGroup = {
  group: TemplateGroupNode
  evidence: string[]
  featureEvidence: string[]
  parentEvidence: string[]
  score: number
}

function scoreTemplateGroups(operation: TemplateOperation, tree: TemplateGroupNode[]) {
  const source = normalizeSearchText([
    operation.name,
    ...(operation.step_items || []),
  ].join('；'))
  if (!source) return []

  const scored: ScoredTemplateGroup[] = []
  flattenTemplateGroups(tree).forEach((group) => {
    const parentEvidence = normalizePath(group.path).slice(0, -1)
      .filter(term => normalizeSearchText(term) && source.includes(normalizeSearchText(term)))
    const nameEvidence = normalizeSearchText(group.name) && source.includes(normalizeSearchText(group.name))
      ? [group.name]
      : []
    const featureEvidence = (group.feature_selections || []).flatMap(feature => (
      featureTerms(feature).filter(term => normalizeSearchText(term) && source.includes(normalizeSearchText(term)))
    ))
    if (!nameEvidence.length && !featureEvidence.length) return
    const evidence = [...new Set([...parentEvidence, ...nameEvidence, ...featureEvidence])]
    scored.push({
      group,
      evidence,
      featureEvidence: [...new Set(featureEvidence)],
      parentEvidence,
      score: Math.min(1, 0.45 + (featureEvidence.length ? 0.3 : 0) + (parentEvidence.length ? 0.2 : 0)),
    })
  })

  if (scored.some(item => item.group.feature_selections.length > 0)) {
    return scored.filter(item => item.group.feature_selections.length > 0)
  }
  return scored
}

export function suggestTemplateGroupsForOperation(
  operation: TemplateOperation,
  tree: TemplateGroupNode[],
): TemplateGroupMappingSuggestion {
  const operationId = cleanId(operation.source_operation_id || operation.id)
  const operationName = cleanText(operation.name)
  const base = { operation_id: operationId, operation_name: operationName }
  if (!isTemplateMappableOperation(operation)) {
    return {
      ...base,
      feature: '',
      position: '',
      confidence: 'low',
      requires_manual_confirmation: true,
      recommended_group_id: null,
      candidates: [],
      evidence: [],
      reasons: ['该工序不是可映射到零件特征的加工工序。'],
    }
  }

  const scored = scoreTemplateGroups(operation, tree)
  const candidates = scored.map(item => ({
    group_id: item.group.key,
    path: [...item.group.path],
    score: item.score,
    reason: `原文命中：${item.evidence.join('、')}`,
  }))
  const evidence = [...new Set(scored.flatMap(item => item.evidence))]
  const isUnique = candidates.length === 1
  const isCompound = candidates.length > 1
  return {
    ...base,
    feature: [...new Set(scored.flatMap(item => item.group.feature_selections))].join(','),
    position: [...new Set(scored.flatMap(item => item.parentEvidence))].join('/'),
    confidence: isUnique ? 'high' : candidates.length ? 'medium' : 'low',
    requires_manual_confirmation: !isUnique || isCompound,
    recommended_group_id: isUnique && !isCompound ? candidates[0]!.group_id : null,
    candidates,
    evidence,
    reasons: candidates.length
      ? [isUnique && !isCompound ? '模板中只有一个被原文明确支持的分组。' : '原文支持多个分组，需要人工确认。']
      : ['当前模板中没有与工序原文匹配的分组。'],
  }
}

export function buildTemplateGroupMappingSuggestions(
  operations: TemplateOperation[],
  tree: TemplateGroupNode[],
) {
  return operations.map(operation => suggestTemplateGroupsForOperation(operation, tree))
}

export function isTrustedTemplateGroupChoice(
  choice: TemplateGroupModelChoice,
  candidates: TemplateGroupMappingCandidate[],
  minimumConfidence = 0.9,
) {
  const groupId = cleanText(choice.group_id)
  const confidence = Number(choice.confidence || 0)
  return Number.isFinite(confidence)
    && confidence >= minimumConfidence
    && candidates.some(candidate => candidate.group_id === groupId)
}

function isNonFeatureMachiningOperationName(value: unknown) {
  const name = cleanText(value)
  if (!name) return false
  if (/(备料|下料|锻造|铸造|热处理|调质|正火|正常化|淬火|回火|退火|去应力|时效|渗氮|渗碳|氰化|镀|阳极化|钝化|喷涂|涂装|表面处理|清洗|除油|检验|检查|探伤|测量|校验|终检|首检|巡检|总检|包装|封存|标印|标记|打标|装配|车床|铣床|磨床|钻床|镗床|加工中心|机床|设备)/.test(name)) {
    return true
  }
  return /去毛刺/.test(name) && !/(槽|孔|扁|倒角|倒圆|锐边|车|铣|磨|研|割|刨|插|拉)/.test(name)
}

export function isTemplateMappableOperation(
  operation: Pick<TemplateOperation, 'step_family'> & Partial<Pick<TemplateOperation, 'name' | 'step_items'>>,
) {
  const name = cleanText(operation.name)
  if (name && isNonFeatureMachiningOperationName(name)) return false
  return Boolean(inferTemplateStepFamilyFromOperation(operation))
    || ALLOWED_TEMPLATE_STEP_FAMILIES.includes(cleanText(operation.step_family) as TemplateStepFamily)
}

export function inferTemplateStepFamilyFromOperationName(value: unknown): TemplateStepFamily | '' {
  const name = cleanText(value)
  if (!name || isNonFeatureMachiningOperationName(name)) return ''
  if (/(型孔|异形孔|割型|打型)/.test(name)) return '特征加工类'
  if (/(孔|钻|镗|铰|攻丝|攻螺纹|内圆|锪|珩)/.test(name)) return '孔加工类'
  if (/(车削|车外|车端|粗车|精车|外圆|端面|成形)/.test(name)) return '车削/成形类'
  if (/(铣|槽|扁|花键|键槽|割|磨|研|刨|插|拉|打|倒角|倒圆|锐边|挖|平面)/.test(name)) return '特征加工类'
  return ''
}

export function inferTemplateStepFamilyFromOperation(
  operation: Partial<Pick<TemplateOperation, 'name' | 'step_items'>>,
): TemplateStepFamily | '' {
  const name = cleanText(operation.name)
  if (name && isNonFeatureMachiningOperationName(name)) return ''
  const candidates = [
    name,
    ...(Array.isArray(operation.step_items) ? operation.step_items.map(cleanText) : []),
  ].filter(Boolean)
  for (const candidate of candidates) {
    const family = inferTemplateStepFamilyFromOperationName(candidate)
    if (family) return family
  }
  return ''
}

export function templateGroupsForOperation(
  operation: Pick<TemplateOperation, 'step_family'> & Partial<Pick<TemplateOperation, 'name' | 'step_items'>>,
  tree: TemplateGroupNode[],
) {
  return isTemplateMappableOperation(operation) ? flattenTemplateGroups(tree) : []
}

export function deriveTemplateAlias(
  originalName: string,
  group: Pick<TemplateGroupNode, 'path' | 'name'>,
) {
  const name = cleanText(originalName)
  const path = normalizePath(group.path)
  return path.length ? `${name}（${path.join('/')}）` : name
}

export function createTemplateAliasBinding(
  operation: Pick<TemplateOperation, 'id' | 'source_operation_id' | 'name'>,
  group: TemplateGroupNode,
): TemplateAliasBinding | null {
  const sourceOperationId = cleanId(operation.source_operation_id || operation.id)
  const path = normalizePath(group.path)
  if (!sourceOperationId || !group.key || !path.length) return null
  return {
    source_operation_id: sourceOperationId,
    alias: deriveTemplateAlias(operation.name, group),
    template_group_key: group.key,
    template_group_id: group.key,
    template_group_name: group.name,
    template_group_path: path,
    feature_selections: [...group.feature_selections],
  }
}

export function serializeAliasesForRouteSegment(
  segment: RouteSegmentWithAliases,
  aliases: Record<string, TemplateAliasBinding> | Map<number, TemplateAliasBinding>,
) {
  return (segment.source_operation_ids || segment.operation_ids || [])
    .map(cleanId)
    .filter(Boolean)
    .map((id) => {
      const binding = aliases instanceof Map ? aliases.get(id) : aliases[String(id)]
      return binding ? cloneBinding({ ...binding, source_operation_id: id }) : null
    })
    .filter((item): item is TemplateAliasBinding => Boolean(item))
}

export function aliasesFromRouteSegments(segments: RouteSegmentWithAliases[]) {
  const aliases: Record<string, TemplateAliasBinding> = {}
  segments.forEach((segment) => {
    ;(segment.template_group_aliases || []).forEach((binding) => {
      const sourceOperationId = cleanId(binding.source_operation_id)
      const alias = cleanText(binding.alias)
      const path = normalizePath(binding.template_group_path)
      const key = cleanText(binding.template_group_key || binding.template_group_id)
      if (!sourceOperationId || !alias || !key || !path.length) return
      aliases[String(sourceOperationId)] = {
        source_operation_id: sourceOperationId,
        alias,
        template_group_key: key,
        template_group_id: key,
        template_group_name: cleanText(binding.template_group_name || path[path.length - 1]),
        template_group_path: path,
        feature_selections: (binding.feature_selections || []).map(cleanText).filter(Boolean),
      }
    })
  })
  return aliases
}

function extractEntries(raw: unknown) {
  if (Array.isArray(raw)) return raw.map(item => ({ key: '', value: item }))
  if (!raw || typeof raw !== 'object') return []
  const record = raw as Record<string, unknown>
  const entries = record.entries && typeof record.entries === 'object' ? record.entries : record
  if (Array.isArray(entries)) return entries.map(item => ({ key: '', value: item }))
  return Object.entries(entries as Record<string, unknown>).map(([key, value]) => ({ key, value }))
}

export function migrateLegacyAliasesByPath(raw: unknown, tree: TemplateGroupNode[]) {
  const migrated: Record<string, TemplateAliasBinding> = {}
  const invalidated: LegacyAliasInvalidation[] = []
  extractEntries(raw).forEach(({ key, value }) => {
    if (!value || typeof value !== 'object') return
    const item = value as Record<string, unknown>
    const sourceOperationId = cleanId(item.source_operation_id || item.operation_id || key)
    const alias = cleanText(item.alias)
    const path = normalizePath(item.template_group_path || item.templateGroupPath)
    if (!sourceOperationId || !alias || !path.length) return
    const group = findTemplateGroupByPath(tree, path)
    if (!group) {
      invalidated.push({
        source_operation_id: sourceOperationId,
        alias,
        template_group_path: path,
        reason: '原分组路径在当前模板中不存在。',
      })
      return
    }
    migrated[String(sourceOperationId)] = {
      source_operation_id: sourceOperationId,
      alias,
      template_group_key: group.key,
      template_group_id: group.key,
      template_group_name: group.name,
      template_group_path: [...group.path],
      feature_selections: [...group.feature_selections],
    }
  })
  return { migrated, invalidated }
}

function draftStorageKey(projectId: number | string) {
  return `${TEMPLATE_GROUP_MAPPING_DRAFT_STORAGE_KEY}:${projectId}`
}

function parseStoredPayload(value: string | null) {
  if (!value) return null
  try {
    return JSON.parse(value) as Record<string, unknown>
  } catch {
    return null
  }
}

function mappingRecord(value: Record<string, TemplateAliasBinding> | TemplateAliasBinding[]) {
  const entries = Array.isArray(value)
    ? value.map(binding => [String(binding.source_operation_id), binding] as const)
    : Object.entries(value)
  return Object.fromEntries(entries.map(([id, binding]) => [id, cloneBinding(binding)]))
}

export function loadTemplateGroupMappingDraft(
  projectId: number | string,
  templateRevision: number,
  formalMappings: Record<string, TemplateAliasBinding> | TemplateAliasBinding[],
  tree: TemplateGroupNode[],
  storage: Storage = globalThis.localStorage,
) {
  const formal = mappingRecord(formalMappings)
  if (Object.keys(formal).length) return formal
  const payload = parseStoredPayload(storage.getItem(draftStorageKey(projectId)))
  if (
    !payload
    || Number(payload.schemaVersion) !== TEMPLATE_GROUP_MAPPING_VERSION
    || Number(payload.projectId) !== Number(projectId)
    || Number(payload.templateRevision) !== Number(templateRevision)
  ) return {}
  return migrateLegacyAliasesByPath(payload.entries, tree).migrated
}

export function saveTemplateGroupMappingDraft(
  projectId: number | string,
  templateRevision: number,
  aliases: Record<string, TemplateAliasBinding>,
  routeFingerprint = '',
  storage: Storage = globalThis.localStorage,
) {
  storage.setItem(draftStorageKey(projectId), JSON.stringify({
    schemaVersion: TEMPLATE_GROUP_MAPPING_VERSION,
    projectId: Number(projectId),
    templateRevision: Number(templateRevision),
    routeFingerprint,
    entries: cloneAliases(aliases),
  }))
}

export function clearTemplateGroupMappingDraft(
  projectId: number | string,
  storage: Storage = globalThis.localStorage,
) {
  storage.removeItem(draftStorageKey(projectId))
}

export function hasTemplateGroupMappingDraft(
  projectId: number | string,
  templateRevision?: number,
  storage: Storage = globalThis.localStorage,
) {
  const payload = parseStoredPayload(storage.getItem(draftStorageKey(projectId)))
  return Boolean(
    payload
    && Number(payload.schemaVersion) === TEMPLATE_GROUP_MAPPING_VERSION
    && Number(payload.projectId) === Number(projectId)
    && (templateRevision === undefined || Number(payload.templateRevision) === Number(templateRevision)),
  )
}

export function useTemplateGroupMapping(
  projectId: number | string,
  templateRevision: number,
  tree: TemplateGroupNode[],
  formalMappings: Record<string, TemplateAliasBinding> = {},
  storage: Storage = globalThis.localStorage,
) {
  const aliases = loadTemplateGroupMappingDraft(projectId, templateRevision, formalMappings, tree, storage)
  return {
    aliases,
    setAlias: (binding: TemplateAliasBinding) => {
      aliases[String(binding.source_operation_id)] = cloneBinding(binding)
      saveTemplateGroupMappingDraft(projectId, templateRevision, aliases, '', storage)
    },
    clearAlias: (operationId: number) => {
      delete aliases[String(operationId)]
      saveTemplateGroupMappingDraft(projectId, templateRevision, aliases, '', storage)
    },
  }
}
