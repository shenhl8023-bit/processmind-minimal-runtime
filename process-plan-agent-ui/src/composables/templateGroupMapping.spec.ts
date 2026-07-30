import { beforeEach, describe, expect, it } from 'vitest'
import {
  BUSHING_11_TEMPLATE_TREE,
  createTemplateAliasBinding,
  deriveTemplateAlias,
  findTemplateGroupById,
  inferTemplateStepFamilyFromOperation,
  inferTemplateStepFamilyFromOperationName,
  isTemplateMappableOperation,
  isTrustedTemplateGroupChoice,
  loadTemplateGroupAliases,
  migrateTemplateGroupAliases,
  saveTemplateGroupAliases,
  serializeAliasesForRouteSegment,
  suggestTemplateGroupsForOperation,
  templateGroupsForOperation,
} from './templateGroupMapping'

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

  it('filters Bushing-11 groups by the three allowed step families', () => {
    expect(templateGroupsForOperation({ step_family: '车削/成形类' }).length).toBe(14)
    expect(templateGroupsForOperation({ step_family: 'inspection' })).toEqual([])
    expect(BUSHING_11_TEMPLATE_TREE.id).toBe('bushing-11')
  })

  it('includes feature-machining operations even when their coarse family is non-canonical', () => {
    expect(inferTemplateStepFamilyFromOperationName('车削加工（A侧）')).toBe('车削/成形类')
    expect(inferTemplateStepFamilyFromOperationName('磨外圆')).toBe('车削/成形类')
    expect(inferTemplateStepFamilyFromOperationName('研外圆')).toBe('车削/成形类')
    expect(inferTemplateStepFamilyFromOperationName('磨槽')).toBe('特征加工类')
    expect(inferTemplateStepFamilyFromOperationName('打型孔')).toBe('特征加工类')
    expect(inferTemplateStepFamilyFromOperationName('研孔')).toBe('孔加工类')

    expect(isTemplateMappableOperation({ name: '车削加工（B侧）', step_family: '车削加工（B侧）' })).toBe(true)
    expect(isTemplateMappableOperation({ name: '磨槽', step_family: '磨槽' })).toBe(true)
    expect(isTemplateMappableOperation({ name: '研孔', step_family: '孔精整类' })).toBe(true)
    expect(templateGroupsForOperation({ name: '磨槽', step_family: '磨槽' }).length).toBe(14)
    expect(inferTemplateStepFamilyFromOperation({ name: '复合加工', step_items: ['挖槽'] })).toBe('特征加工类')
  })

  it('excludes non-feature route operations even if a coarse family is incorrect', () => {
    expect(isTemplateMappableOperation({ name: '调质', step_family: '特征加工类' })).toBe(false)
    expect(isTemplateMappableOperation({ name: '清洗', step_family: '孔加工类' })).toBe(false)
    expect(isTemplateMappableOperation({ name: '终检', step_family: '车削/成形类' })).toBe(false)
    expect(isTemplateMappableOperation({ name: '包装', step_family: '特征加工类' })).toBe(false)
    expect(isTemplateMappableOperation({ name: '挖槽去毛刺', step_family: 'release' })).toBe(true)
    expect(inferTemplateStepFamilyFromOperation({ name: '清洗', step_items: ['铣槽'] })).toBe('')
  })

  it('derives path aliases and serializes by source operation id', () => {
    const group = findTemplateGroupById('3358f0f62d04abb99d35dec48ef73e1')!
    const binding = createTemplateAliasBinding({ id: 11, name: '钻孔' }, group)
    expect(deriveTemplateAlias('钻孔', group)).toBe('钻孔（A侧/外环槽）')
    expect(serializeAliasesForRouteSegment({ source_operation_ids: [11, 12] }, { '11': binding! })).toEqual([binding])
  })

  it('migrates v1 entries and recovers ids from routeFingerprint', () => {
    const migrated = migrateTemplateGroupAliases({
      schemaVersion: 1,
      projectId: 3,
      templateKey: 'bushing-11',
      entries: [{
        groupId: '3358f0f62d04abb99d35dec48ef73e1',
        routeElementKey: 'segment:old-segment',
      }],
    }, JSON.stringify([{ id: 'old-segment', operationIds: [21, 22] }]), [
      { id: 21, name: '钻孔' },
      { id: 22, name: '铣扁' },
    ])
    expect(migrated['21']?.alias).toBe('钻孔（A侧/外环槽）')
    expect(migrated['22']?.alias).toBe('铣扁（A侧/外环槽）')
  })

  it('persists and loads versioned aliases', () => {
    saveTemplateGroupAliases(3, { '11': { source_operation_id: 11, alias: '铣扁（A侧/外环槽）', template_group_id: '3358f0f62d04abb99d35dec48ef73e1', template_group_path: ['A侧', '外环槽'] } }, storage)
    expect(loadTemplateGroupAliases(3, storage)['11']?.template_group_id).toBe('3358f0f62d04abb99d35dec48ef73e1')
  })

  it('keeps a plain hole operation unresolved across every legal hole position', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 360, name: '打孔' })

    expect(suggestion.recommended_group_id).toBeNull()
    expect(suggestion.confidence).toBe('medium')
    expect(suggestion.candidates.map(candidate => candidate.path.join('/'))).toEqual([
      'A侧/孔',
      'B侧/孔',
      '周边/孔',
    ])
  })

  it('does not guess a side for an outer-diameter operation', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 190, name: '磨外圆' })

    expect(suggestion.recommended_group_id).toBeNull()
    expect(suggestion.candidates.map(candidate => candidate.path.join('/'))).toEqual([
      'A侧/外圆',
      'B侧/外圆',
    ])
  })

  it('recommends a unique group only when both side and feature are explicit', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 50, name: '车A侧端面' })

    expect(suggestion.confidence).toBe('high')
    expect(suggestion.recommended_group_id).toBe('4cb338b6ddde4a96ba8eec7c5d474cf9')
    expect(suggestion.candidates.map(candidate => candidate.path.join('/'))).toEqual(['A侧/端面'])
    expect(suggestion.evidence).toEqual(['A侧', '端面'])
  })

  it('keeps a compound side-specific turning operation unresolved across every detected feature', () => {
    const suggestion = suggestTemplateGroupsForOperation({
      id: 50,
      name: '车削加工（A侧）',
      step_items: ['平端面', '车外圆', '车槽', '锐边磨圆', '钻镗孔', '倒角'],
    })

    expect(suggestion.recommended_group_id).toBeNull()
    expect(suggestion.confidence).toBe('medium')
    expect(suggestion.requires_manual_confirmation).toBe(true)
    expect(suggestion.candidates.map(candidate => candidate.path.join('/'))).toEqual([
      'A侧/端面',
      'A侧/外圆',
      'A侧/孔',
      'A侧/倒角倒圆',
    ])
    expect(suggestion.reasons).toEqual(['该工序同时加工多个特征，需要人工确认目标分组。'])
  })

  it('returns no template candidates for a non-feature route operation', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 900, name: '清洗' })

    expect(suggestion.confidence).toBe('low')
    expect(suggestion.recommended_group_id).toBeNull()
    expect(suggestion.candidates).toEqual([])
  })

  it('only trusts a high-confidence model choice from the legal candidate set', () => {
    const suggestion = suggestTemplateGroupsForOperation({ id: 360, name: '打孔' })

    expect(isTrustedTemplateGroupChoice({
      group_id: suggestion.candidates[0]!.group_id,
      confidence: 0.92,
    }, suggestion.candidates)).toBe(true)
    expect(isTrustedTemplateGroupChoice({
      group_id: suggestion.candidates[0]!.group_id,
      confidence: 0.89,
    }, suggestion.candidates)).toBe(false)
    expect(isTrustedTemplateGroupChoice({
      group_id: 'hallucinated-group-id',
      confidence: 0.99,
    }, suggestion.candidates)).toBe(false)
  })
})
