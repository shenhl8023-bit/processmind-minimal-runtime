import { beforeEach, describe, expect, it } from 'vitest'

import {
  clearTemplateGroupMappingDraft,
  createTemplateAliasBinding,
  findTemplateGroupByKey,
  findTemplateGroupByPath,
  flattenTemplateGroups,
  hasTemplateGroupMappingDraft,
  inferTemplateStepFamilyFromOperation,
  inferTemplateStepFamilyFromOperationName,
  isTemplateMappableOperation,
  isTrustedTemplateGroupChoice,
  loadTemplateGroupMappingDraft,
  migrateLegacyAliasesByPath,
  saveTemplateGroupMappingDraft,
  serializeAliasesForRouteSegment,
  suggestTemplateGroupsForOperation,
  templateGroupsForOperation,
  type TemplateAliasBinding,
  type TemplateGroupNode,
} from './templateGroupMapping'

function group(
  key: string,
  name: string,
  path: string[],
  featureSelections: string[] = [],
  children: TemplateGroupNode[] = [],
  sourceId = '',
): TemplateGroupNode {
  return {
    key,
    source_id: sourceId,
    name,
    path,
    feature_selections: featureSelections,
    params: {},
    children,
  }
}

const tree: TemplateGroupNode[] = [
  group('grp_shell', '壳体', ['壳体'], [], [
    group('grp_cavity', '内腔', ['壳体', '内腔'], [], [
      group('grp_blind_hole', '盲孔', ['壳体', '内腔', '盲孔'], ['孔(盲孔)'], [], 'xml-17'),
    ]),
  ]),
  group('grp_profile', '外形', ['外形'], [], [
    group('grp_rib', '筋条', ['外形', '筋条'], [], [
      group('grp_plane', '平面', ['外形', '筋条', '平面'], ['平面'], [], 'xml-91'),
    ]),
  ]),
]

describe('templateGroupMapping', () => {
  let storage: Storage

  beforeEach(() => {
    const values = new Map<string, string>()
    storage = {
      getItem: key => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, value),
      removeItem: key => values.delete(key),
      clear: () => values.clear(),
      key: index => [...values.keys()][index] ?? null,
      get length() { return values.size },
    }
  })

  it('finds arbitrary nested groups by stable key and normalized full path', () => {
    expect(findTemplateGroupByKey(tree, 'grp_blind_hole')?.path).toEqual(['壳体', '内腔', '盲孔'])
    expect(findTemplateGroupByPath(tree, [' 壳体 ', '内腔', '盲孔'])?.key).toBe('grp_blind_hole')
    expect(flattenTemplateGroups(tree).map(node => node.key)).toEqual([
      'grp_shell',
      'grp_cavity',
      'grp_blind_hole',
      'grp_profile',
      'grp_rib',
      'grp_plane',
    ])
  })

  it('uses stable keys when source XML ids change', () => {
    const changedSourceIds = structuredClone(tree)
    changedSourceIds[0]!.children[0]!.children[0]!.source_id = 'different-xml-id'

    const original = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByPath(tree, ['壳体', '内腔', '盲孔'])!)
    const changed = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByPath(changedSourceIds, ['壳体', '内腔', '盲孔'])!)

    expect(changed).toEqual(original)
    expect(changed?.template_group_key).toBe('grp_blind_hole')
    expect(changed?.template_group_id).toBe('grp_blind_hole')
  })

  it('keeps duplicate leaf names distinct by their full paths', () => {
    const duplicateTree = [
      ...tree,
      group('grp_cover', '盖板', ['盖板'], [], [
        group('grp_cover_cavity', '内腔', ['盖板', '内腔'], [], [
          group('grp_cover_blind_hole', '盲孔', ['盖板', '内腔', '盲孔'], ['孔(盲孔)']),
        ]),
      ]),
    ]

    expect(findTemplateGroupByPath(duplicateTree, ['壳体', '内腔', '盲孔'])?.key).toBe('grp_blind_hole')
    expect(findTemplateGroupByPath(duplicateTree, ['盖板', '内腔', '盲孔'])?.key).toBe('grp_cover_blind_hole')
  })

  it('suggests a generic feature group without fixed template names or ids', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 31, name: '钻盲孔' }, tree)

    expect(suggestion.candidates.map(item => item.group_id)).toEqual(['grp_blind_hole'])
    expect(suggestion.recommended_group_id).toBe('grp_blind_hole')
  })

  it('keeps a compound operation pending with every independently evidenced feature', () => {
    const suggestion = suggestTemplateGroupsForOperation({
      id: 32,
      name: '复合加工',
      step_items: ['钻盲孔', '铣筋条平面'],
    }, tree)

    expect(suggestion.candidates.map(item => item.group_id)).toEqual(['grp_blind_hole', 'grp_plane'])
    expect(suggestion.recommended_group_id).toBeNull()
    expect(suggestion.requires_manual_confirmation).toBe(true)
  })

  it('preserves an existing manual alias while enriching it from the exact path', () => {
    const manual: Record<string, TemplateAliasBinding> = {
      11: {
        source_operation_id: 11,
        alias: '人工名称',
        template_group_key: 'old-key-is-ignored',
        template_group_id: 'old-id-is-ignored',
        template_group_name: '旧名称',
        template_group_path: ['壳体', '内腔', '盲孔'],
        feature_selections: [],
      },
    }

    const result = migrateLegacyAliasesByPath(manual, tree)

    expect(result.invalidated).toEqual([])
    expect(result.migrated['11']).toEqual({
      source_operation_id: 11,
      alias: '人工名称',
      template_group_key: 'grp_blind_hole',
      template_group_id: 'grp_blind_hole',
      template_group_name: '盲孔',
      template_group_path: ['壳体', '内腔', '盲孔'],
      feature_selections: ['孔(盲孔)'],
    })
  })

  it('reports a legacy alias whose full path no longer exists', () => {
    const result = migrateLegacyAliasesByPath({
      12: {
        source_operation_id: 12,
        alias: '旧槽映射',
        template_group_id: 'xml-id-must-not-be-used',
        template_group_path: ['壳体', '外槽'],
      },
    }, tree)

    expect(result.migrated).toEqual({})
    expect(result.invalidated).toEqual([expect.objectContaining({
      source_operation_id: 12,
      template_group_path: ['壳体', '外槽'],
    })])
  })

  it('uses formal mappings instead of a browser draft when formal mappings exist', () => {
    const draft = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByKey(tree, 'grp_blind_hole')!)!
    saveTemplateGroupMappingDraft(28, 4, { 11: draft }, 'route-a', storage)
    const formal = {
      12: createTemplateAliasBinding({ id: 12, name: '铣平面' }, findTemplateGroupByKey(tree, 'grp_plane')!)!,
    }

    expect(loadTemplateGroupMappingDraft(28, 4, formal, tree, storage)).toEqual(formal)
  })

  it('loads a draft only for the current template revision', () => {
    const draft = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByKey(tree, 'grp_blind_hole')!)!
    saveTemplateGroupMappingDraft(28, 4, { 11: draft }, 'route-a', storage)

    expect(loadTemplateGroupMappingDraft(28, 4, {}, tree, storage)).toEqual({ 11: draft })
    expect(loadTemplateGroupMappingDraft(28, 5, {}, tree, storage)).toEqual({})
  })

  it('stores schema version 3 project and route metadata and clears drafts explicitly', () => {
    const draft = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByKey(tree, 'grp_blind_hole')!)!
    saveTemplateGroupMappingDraft(28, 4, { 11: draft }, 'route-a', storage)

    expect(JSON.parse(storage.getItem('template_group_mapping_draft:28') || '{}')).toMatchObject({
      schemaVersion: 3,
      projectId: 28,
      templateRevision: 4,
      routeFingerprint: 'route-a',
    })
    clearTemplateGroupMappingDraft(28, storage)
    expect(storage.getItem('template_group_mapping_draft:28')).toBeNull()
  })

  it('distinguishes an intentionally empty current draft from a stale draft', () => {
    saveTemplateGroupMappingDraft(28, 4, {}, 'route-a', storage)

    expect(hasTemplateGroupMappingDraft(28, 4, storage)).toBe(true)
    expect(hasTemplateGroupMappingDraft(28, 5, storage)).toBe(false)
  })

  it('serializes enriched mappings by source operation id', () => {
    const binding = createTemplateAliasBinding({ id: 11, name: '钻盲孔' }, findTemplateGroupByKey(tree, 'grp_blind_hole')!)!

    expect(serializeAliasesForRouteSegment({ source_operation_ids: [11, 12] }, { 11: binding })).toEqual([binding])
  })

  it('filters dynamic groups by whether the operation is feature machining', () => {
    expect(templateGroupsForOperation({ name: '钻盲孔' }, tree)).toHaveLength(6)
    expect(templateGroupsForOperation({ name: '终检' }, tree)).toEqual([])
  })

  it('keeps generic operation-family inference and model allow-list checks', () => {
    expect(inferTemplateStepFamilyFromOperationName('研孔')).toBe('孔加工类')
    expect(inferTemplateStepFamilyFromOperation({ name: '复合加工', step_items: ['挖槽'] })).toBe('特征加工类')
    expect(isTemplateMappableOperation({ name: '调质', step_family: '特征加工类' })).toBe(false)
    expect(isTrustedTemplateGroupChoice({ group_id: 'grp_plane', confidence: 0.92 }, [{
      group_id: 'grp_plane',
      path: ['外形', '筋条', '平面'],
      score: 0.9,
      reason: '命中平面',
    }])).toBe(true)
  })
})
