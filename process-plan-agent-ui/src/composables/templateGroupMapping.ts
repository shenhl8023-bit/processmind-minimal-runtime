export const TEMPLATE_GROUP_ALIASES_STORAGE_KEY = 'template_group_aliases'
export const TEMPLATE_GROUP_MAPPING_VERSION = 2

export const ALLOWED_TEMPLATE_STEP_FAMILIES = [
  '车削/成形类',
  '孔加工类',
  '特征加工类',
] as const

export type TemplateStepFamily = typeof ALLOWED_TEMPLATE_STEP_FAMILIES[number]

export type TemplateGroupNode = {
  id: string
  name: string
  path?: string[]
  children?: TemplateGroupNode[]
}

export type TemplateOperation = {
  id: number
  name: string
  sequence?: number
  step_family?: string | null
  step_items?: string[]
  source_operation_id?: number | null
}

export type TemplateAliasBinding = {
  source_operation_id: number
  alias: string
  template_group_id: string
  template_group_path: string[]
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
  template_group_aliases?: TemplateAliasBinding[]
  [key: string]: unknown
}

// The root is intentionally omitted from aliases. A target such as A侧/外环槽
// therefore yields the user-facing alias “钻孔（A侧/外环槽）”.
export const BUSHING_11_TEMPLATE_TREE: TemplateGroupNode = {
  id: 'bushing-11',
  name: '衬套-11',
  children: [
    {
      id: '58ca807053814d7a9c95977b7fc5eece',
      name: 'A侧',
      children: [
        { id: '4cb338b6ddde4a96ba8eec7c5d474cf9', name: '端面' },
        { id: '892df827cbef4703b0d9acfe3027bc0', name: '外圆' },
        { id: '3358f0f62d04abb99d35dec48ef73e1', name: '外环槽' },
        { id: 'a8af618bdcbc4ba78cb5969c687b2988', name: '孔' },
        { id: '7be3a8eb257f483691f1c551e5169415', name: '内环槽' },
        { id: '467047205d02401992c36f4569dc3a1a', name: '倒角倒圆' },
      ],
    },
    {
      id: 'dd1e94d99b344aa68c7085b244dcaabd',
      name: 'B侧',
      children: [
        { id: 'c40fd63faa734d47b41e4b8c8fae19c7', name: '端面' },
        { id: '9cb45045a2548b0ba7444856444c890', name: '外圆' },
        { id: '7745857899d54d6483d23ef668ac3a6', name: '外环槽' },
        { id: '1de0e4c267d741f79ab578adc473f6', name: '孔' },
        { id: 'fa1477d6c75e4013b2e2efb62b87fa', name: '内环槽' },
        { id: '44bce9924ef3465185924b22986bd5d', name: '倒角倒圆' },
      ],
    },
    {
      id: '69eeee18c6b34091a1f9effdc14c9be',
      name: '周边',
      children: [
        { id: '3cc17ff1dc74c57b6b9366011ac115', name: '平面和凹槽' },
        { id: 'e83310d574a04a1185523357d836e666', name: '孔' },
      ],
    },
  ],
}

function cleanId(value: unknown) {
  const id = Number(value)
  return Number.isInteger(id) && id > 0 ? id : 0
}

function cleanText(value: unknown) {
  return String(value ?? '').trim()
}

function normalizeIds(value: unknown) {
  return (Array.isArray(value) ? value : [])
    .map(cleanId)
    .filter(Boolean)
}

function cloneBinding(binding: TemplateAliasBinding): TemplateAliasBinding {
  return {
    source_operation_id: binding.source_operation_id,
    alias: binding.alias,
    template_group_id: binding.template_group_id,
    template_group_path: [...binding.template_group_path],
  }
}

export function flattenTemplateGroups(root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE) {
  const result: Array<TemplateGroupNode & { path: string[] }> = []
  function visit(node: TemplateGroupNode, parentPath: string[], isRoot = false) {
    const path = isRoot ? [] : [...parentPath, node.name]
    if (!isRoot) result.push({ ...node, path })
    ;(node.children || []).forEach(child => visit(child, path, false))
  }
  visit(root, [], true)
  return result
}

export function templateLeafGroups(root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE) {
  return flattenTemplateGroups(root).filter(group => !(group.children || []).length)
}

type TemplateFeature = 'end_face' | 'outer_diameter' | 'outer_slot' | 'hole' | 'inner_slot' | 'chamfer' | 'planar_slot'

function inferTemplatePosition(text: string) {
  if (/(?:^|[^a-z])a\s*(?:侧|面|端)/i.test(text)) return { value: 'A侧', evidence: 'A侧' }
  if (/(?:^|[^a-z])b\s*(?:侧|面|端)/i.test(text)) return { value: 'B侧', evidence: 'B侧' }
  if (/(周边|外周)/.test(text)) return { value: '周边', evidence: text.match(/周边|外周/)?.[0] || '周边' }
  return { value: '', evidence: '' }
}

function inferTemplateFeatures(text: string): Array<{ value: TemplateFeature; evidence: string }> {
  const rules: Array<{ value: TemplateFeature; pattern: RegExp }> = [
    { value: 'outer_slot', pattern: /(外环槽|外槽)/ },
    { value: 'inner_slot', pattern: /(内环槽|内槽)/ },
    { value: 'chamfer', pattern: /(倒角|倒圆|锐边)/ },
    { value: 'end_face', pattern: /(端面|车端|磨端|研端)/ },
    { value: 'outer_diameter', pattern: /(外圆|车外|磨外|研外)/ },
    { value: 'hole', pattern: /(型孔|异形孔|孔|钻|镗|铰|攻丝|攻螺纹|锪|珩|内圆)/ },
    { value: 'planar_slot', pattern: /(平面|凹槽|铣扁|扁位|扁|键槽|花键|割型|型面|铣槽|挖槽)/ },
  ]
  const matches: Array<{ value: TemplateFeature; evidence: string }> = []
  for (const rule of rules) {
    const evidence = text.match(rule.pattern)?.[0]
    if (evidence) matches.push({ value: rule.value, evidence })
  }
  return matches
}

function templateGroupFeature(name: string): TemplateFeature | '' {
  if (name === '端面') return 'end_face'
  if (name === '外圆') return 'outer_diameter'
  if (name === '外环槽') return 'outer_slot'
  if (name === '孔') return 'hole'
  if (name === '内环槽') return 'inner_slot'
  if (name === '倒角倒圆') return 'chamfer'
  if (name === '平面和凹槽') return 'planar_slot'
  return ''
}

export function suggestTemplateGroupsForOperation(
  operation: TemplateOperation,
  root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE,
): TemplateGroupMappingSuggestion {
  const operationId = cleanId(operation.source_operation_id || operation.id)
  const operationName = cleanText(operation.name)
  const text = [operationName, ...(operation.step_items || []).map(cleanText)].filter(Boolean).join('；')
  const base = {
    operation_id: operationId,
    operation_name: operationName,
  }
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

  const features = inferTemplateFeatures(text)
  const position = inferTemplatePosition(text)
  const evidence = [position.evidence, ...features.map(feature => feature.evidence)].filter(Boolean)
  if (!features.length) {
    return {
      ...base,
      feature: '',
      position: position.value,
      confidence: 'low',
      requires_manual_confirmation: true,
      recommended_group_id: null,
      candidates: [],
      evidence,
      reasons: ['未能从工序名称或工步中识别具体加工特征。'],
    }
  }

  const matchedGroups = templateLeafGroups(root).filter(group => (
    features.some(feature => templateGroupFeature(group.name) === feature.value)
    && (!position.value || group.path[0] === position.value)
  ))
  const isCompound = features.length > 1
  const candidates = matchedGroups.map((group) => {
    const feature = features.find(item => templateGroupFeature(group.name) === item.value)!
    return {
      group_id: group.id,
      path: [...group.path],
      score: position.value && !isCompound ? 1 : 0.72,
      reason: isCompound
        ? `工序包含“${feature.evidence}”，同时还加工其他特征。`
        : position.value
          ? `工序明确包含“${position.evidence}”和“${feature.evidence}”。`
          : `已识别“${feature.evidence}”特征，但缺少 A侧、B侧或周边位置。`,
    }
  })
  const isUnique = Boolean(position.value && !isCompound && candidates.length === 1)
  return {
    ...base,
    feature: features.map(feature => feature.value).join(','),
    position: position.value,
    confidence: isUnique ? 'high' : candidates.length ? 'medium' : 'low',
    requires_manual_confirmation: isCompound,
    recommended_group_id: isUnique ? candidates[0]!.group_id : null,
    candidates,
    evidence,
    reasons: candidates.length
      ? [
          isCompound
            ? '该工序同时加工多个特征，需要人工确认目标分组。'
            : isUnique
              ? '位置与加工特征均明确。'
              : '加工特征明确，但加工位置仍需确认。',
        ]
      : ['模板中没有与当前位置和加工特征同时匹配的分组。'],
  }
}

export function buildTemplateGroupMappingSuggestions(
  operations: TemplateOperation[],
  root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE,
) {
  return operations.map(operation => suggestTemplateGroupsForOperation(operation, root))
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

export function findTemplateGroupById(groupId: string, root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE) {
  const normalizedId = cleanText(groupId)
  return flattenTemplateGroups(root).find(group => group.id === normalizedId) || null
}

function isNonFeatureMachiningOperationName(value: unknown) {
  const name = cleanText(value)
  if (!name) return false

  // These are route/support operations, even if an upstream coarse family happened
  // to label them as a machining family.  Keep the mapping dialog focused on
  // operations that can be placed on a part feature.
  if (/(备料|下料|锻造|铸造|热处理|调质|正火|正常化|淬火|回火|退火|去应力|时效|渗氮|渗碳|氰化|镀|阳极化|钝化|喷涂|涂装|表面处理|清洗|除油|检验|检查|探伤|测量|校验|终检|首检|巡检|总检|包装|封存|标印|标记|打标|装配|车床|铣床|磨床|钻床|镗床|加工中心|机床|设备)/.test(name)) {
    return true
  }

  // A standalone deburring step is not a feature operation.  A named cutting
  // action such as “挖槽去毛刺” is retained because its primary object is a slot.
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

  // 型孔 is a geometric feature rather than a conventional round-hole process.
  if (/(型孔|异形孔|割型|打型)/.test(name)) return '特征加工类'
  if (/(孔|钻|镗|铰|攻丝|攻螺纹|内圆|锪|珩)/.test(name)) return '孔加工类'
  if (/(车削|车外|车端|粗车|精车|外圆|端面|成形)/.test(name)) return '车削/成形类'
  if (/(铣|槽|扁|花键|键槽|割|磨|研|刨|插|拉|打|倒角|倒圆|锐边|挖)/.test(name)) return '特征加工类'
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
  root: TemplateGroupNode = BUSHING_11_TEMPLATE_TREE,
) {
  return isTemplateMappableOperation(operation) ? templateLeafGroups(root) : []
}

export function deriveTemplateAlias(
  originalName: string,
  group: Pick<TemplateGroupNode, 'path' | 'name'>,
) {
  const name = cleanText(originalName)
  const path = (group.path || [group.name]).map(cleanText).filter(Boolean)
  return path.length ? `${name}（${path.join('/')}）` : name
}

export function createTemplateAliasBinding(
  operation: Pick<TemplateOperation, 'id' | 'source_operation_id' | 'name'>,
  group: TemplateGroupNode & { path?: string[] },
): TemplateAliasBinding | null {
  const sourceOperationId = cleanId(operation.source_operation_id || operation.id)
  if (!sourceOperationId) return null
  const path = (group.path || [group.name]).map(cleanText).filter(Boolean)
  if (!path.length) return null
  return {
    source_operation_id: sourceOperationId,
    alias: deriveTemplateAlias(operation.name, { name: group.name, path }),
    template_group_id: group.id,
    template_group_path: path,
  }
}

export function serializeAliasesForRouteSegment(
  segment: RouteSegmentWithAliases,
  aliases: Record<string, TemplateAliasBinding> | Map<number, TemplateAliasBinding>,
) {
  const ids = (segment.source_operation_ids || segment.operation_ids || [])
    .map(cleanId).filter(Boolean)
  return ids.map(id => {
    const binding = aliases instanceof Map ? aliases.get(id) : aliases[String(id)]
    return binding ? cloneBinding({ ...binding, source_operation_id: id }) : null
  }).filter((item): item is TemplateAliasBinding => Boolean(item))
}

export function aliasesFromRouteSegments(segments: RouteSegmentWithAliases[]) {
  const aliases: Record<string, TemplateAliasBinding> = {}
  segments.forEach((segment) => {
    ;(segment.template_group_aliases || []).forEach((binding) => {
      const id = cleanId(binding.source_operation_id)
      const alias = cleanText(binding.alias)
      const groupId = cleanText(binding.template_group_id)
      const path = (binding.template_group_path || []).map(cleanText).filter(Boolean)
      if (!id || !alias || !groupId || !path.length) return
      aliases[String(id)] = {
        source_operation_id: id,
        alias,
        template_group_id: groupId,
        template_group_path: path,
      }
    })
  })
  return aliases
}

function routeKeyMatches(candidate: unknown, routeElementKey: unknown) {
  const candidateText = cleanText(candidate)
  const key = cleanText(routeElementKey)
  if (!candidateText || !key) return false
  return candidateText === key
    || `segment:${candidateText}` === key
    || candidateText === key.replace(/^segment:/, '')
}

function routeOperationIdsFromFingerprint(value: unknown, routeElementKey: unknown) {
  const text = cleanText(value)
  const key = cleanText(routeElementKey)
  if (!text || !key) return []
  try {
    const parsed = JSON.parse(text)
    const candidates = Array.isArray(parsed)
      ? parsed
      : Array.isArray(parsed?.items)
        ? parsed.items
        : Array.isArray(parsed?.segments)
          ? parsed.segments
          : []
    const matched = candidates.find((candidate: any) => routeKeyMatches(candidate?.id, key)
      || routeKeyMatches(candidate?.routeElementKey, key)
      || routeKeyMatches(candidate?.groupId, key))
    if (matched) {
      return normalizeIds(matched.operationIds || matched.operation_ids || matched.source_operation_ids)
    }
  } catch {
    // Older drafts used a compact pipe-delimited fingerprint instead of JSON.
  }

  const escapedKey = key.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')
  const match = text.match(new RegExp(`(?:^|[|;])${escapedKey}(?:[:=])([0-9,]+)(?:$|[|;])`))
  const recoveredIds = match?.[1]
  return recoveredIds ? recoveredIds.split(',').map(cleanId).filter(Boolean) : []
}

function extractEntries(raw: unknown) {
  if (Array.isArray(raw)) return raw
  if (!raw || typeof raw !== 'object') return []
  const record = raw as Record<string, unknown>
  if (Array.isArray(record.entries)) return record.entries
  if (record.entries && typeof record.entries === 'object') {
    return Object.entries(record.entries as Record<string, unknown>).map(([id, value]) => ({
      ...(value && typeof value === 'object' ? value as Record<string, unknown> : {}),
      source_operation_id: id,
    }))
  }
  return Object.entries(record).map(([id, value]) => ({
    ...(value && typeof value === 'object' ? value as Record<string, unknown> : {}),
    source_operation_id: id,
  }))
}

export function migrateTemplateGroupAliases(
  raw: unknown,
  routeFingerprint = '',
  operations: TemplateOperation[] = [],
) {
  const result: Record<string, TemplateAliasBinding> = {}
  const operationsById = new Map<number, TemplateOperation>()
  operations.forEach((operation) => {
    const id = cleanId(operation.source_operation_id || operation.id)
    if (id) operationsById.set(id, operation)
  })

  extractEntries(raw).forEach((item: any) => {
    if (!item || typeof item !== 'object') return
    const sourceId = cleanId(item.source_operation_id || item.operation_id)
    const ids = sourceId
      ? [sourceId]
      : normalizeIds(item.source_operation_ids || item.operationIds || item.operation_ids)
    const recoveredIds = ids.length
      ? ids
      : routeOperationIdsFromFingerprint(item.routeFingerprint || routeFingerprint, item.routeElementKey)
    const alias = cleanText(item.alias)
    const groupId = cleanText(item.template_group_id || item.templateGroupId || item.groupId)
    const group = findTemplateGroupById(groupId)
    const path = (item.template_group_path || item.templateGroupPath || group?.path || [])
      .map(cleanText)
      .filter(Boolean)

    recoveredIds.forEach((id) => {
      if (alias && groupId && path.length) {
        result[String(id)] = {
          source_operation_id: id,
          alias,
          template_group_id: groupId,
          template_group_path: path,
        }
        return
      }
      const operation = operationsById.get(id)
      if (!operation || !group) return
      const binding = createTemplateAliasBinding(operation, group)
      if (binding) result[String(id)] = binding
    })
  })
  return result
}

function parseStoredPayload(value: string | null) {
  if (!value) return null
  try {
    return JSON.parse(value)
  } catch {
    return null
  }
}

function findStoredAliasPayload(projectId: number | string, storage: Storage) {
  const key = `${TEMPLATE_GROUP_ALIASES_STORAGE_KEY}:${projectId}`
  const current = parseStoredPayload(storage.getItem(key))
  if (current) return current
  for (let index = 0; index < storage.length; index += 1) {
    const legacyKey = storage.key(index)
    if (!legacyKey) continue
    const candidate = parseStoredPayload(storage.getItem(legacyKey)) as Record<string, unknown> | null
    if (
      candidate
      && Number(candidate.projectId || candidate.project_id || 0) === Number(projectId)
      && cleanText(candidate.templateKey || candidate.template_key) === 'bushing-11'
      && Number(candidate.schemaVersion || candidate.schema_version || 0) === 1
      && Array.isArray(candidate.entries)
    ) {
      return candidate
    }
  }
  return null
}

export function hasTemplateGroupAliasDraft(projectId: number | string, storage: Storage = globalThis.localStorage) {
  return Boolean(findStoredAliasPayload(projectId, storage))
}

export function loadTemplateGroupAliases(
  projectId: number | string,
  operationsOrStorage: TemplateOperation[] | Storage = [],
  suppliedStorage?: Storage,
) {
  const operations = Array.isArray(operationsOrStorage) ? operationsOrStorage : []
  const storage = Array.isArray(operationsOrStorage)
    ? suppliedStorage || globalThis.localStorage
    : operationsOrStorage
  const payload = findStoredAliasPayload(projectId, storage)
  return migrateTemplateGroupAliases(payload, cleanText((payload as any)?.routeFingerprint), operations)
}

export function saveTemplateGroupAliases(
  projectId: number | string,
  aliases: Record<string, TemplateAliasBinding>,
  storage: Storage = globalThis.localStorage,
  routeFingerprint = '',
) {
  const key = `${TEMPLATE_GROUP_ALIASES_STORAGE_KEY}:${projectId}`
  storage.setItem(key, JSON.stringify({
    version: TEMPLATE_GROUP_MAPPING_VERSION,
    routeFingerprint,
    entries: aliases,
  }))
}

export function useTemplateGroupMapping(projectId: number | string, storage?: Storage) {
  const aliases = loadTemplateGroupAliases(projectId, storage || globalThis.localStorage)
  return {
    aliases,
    setAlias: (binding: TemplateAliasBinding) => {
      aliases[String(binding.source_operation_id)] = cloneBinding(binding)
      saveTemplateGroupAliases(projectId, aliases, storage || globalThis.localStorage)
    },
    clearAlias: (operationId: number) => {
      delete aliases[String(operationId)]
      saveTemplateGroupAliases(projectId, aliases, storage || globalThis.localStorage)
    },
  }
}
