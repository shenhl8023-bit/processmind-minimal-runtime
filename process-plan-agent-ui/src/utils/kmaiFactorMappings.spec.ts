import { describe, expect, it } from 'vitest'

import {
  createKmaiMappingDrafts,
  filterBooleanKmaiFactorCatalog,
  groupKmaiUnmappedIssues,
  toKmaiMappingBatchRequest,
  validateKmaiMappingDrafts,
} from './kmaiFactorMappings'

describe('KmAI factor mapping drafts', () => {
  it('offers only boolean catalog factors for presence-style mappings', () => {
    const filtered = filterBooleanKmaiFactorCatalog([
      {
        factor_key: 'material_grade',
        factor_name: 'Material grade',
        factor_category: 'material',
        value_type: 'enum',
        source_mode: 'builtin',
        read_only: true,
      },
      {
        factor_key: 'has_slot_feature',
        factor_name: 'Slot feature',
        factor_category: 'feature',
        value_type: 'boolean',
        source_mode: 'builtin',
        read_only: true,
      },
    ])

    expect(filtered.map(factor => factor.factor_key)).toEqual(['has_slot_feature'])
  })

  it('groups repeated field and value issues with summed occurrences and merged rule refs', () => {
    const grouped = groupKmaiUnmappedIssues([
      { field: 'special.requirements', value: 'Custom requirement', occurrences: 1, rule_refs: ['rule.b'] },
      { field: 'cad.features', value: 'slot', occurrences: 2, rule_refs: ['rule.c'] },
      { field: 'special.requirements', value: 'Custom requirement', occurrences: 3, rule_refs: ['rule.a', 'rule.b'] },
    ])

    expect(grouped).toEqual([
      { field: 'cad.features', value: 'slot', occurrences: 2, rule_refs: ['rule.c'] },
      {
        field: 'special.requirements',
        value: 'Custom requirement',
        occurrences: 4,
        rule_refs: ['rule.a', 'rule.b'],
      },
    ])
  })

  it('preserves merged factor suggestions and forbids manual resolution when any duplicate forbids it', () => {
    const [issue] = groupKmaiUnmappedIssues([
      {
        field: 'cad.features',
        value: 'custom slot',
        occurrences: 1,
        rule_refs: ['rule.a'],
        suggested_existing_factors: ['has_slot', 'has_hole'],
        can_create_manual_factor: true,
      },
      {
        field: 'cad.features',
        value: 'custom slot',
        occurrences: 2,
        rule_refs: ['rule.b'],
        suggested_existing_factors: ['has_hole', 'has_custom_slot'],
        can_create_manual_factor: false,
      },
    ])

    expect(issue).toMatchObject({
      suggested_existing_factors: ['has_custom_slot', 'has_hole', 'has_slot'],
      can_create_manual_factor: false,
    })

    const [draft] = createKmaiMappingDrafts([issue!], { scope: 'global' })
    const validation = validateKmaiMappingDrafts([{
      ...draft!,
      resolution: { mode: 'manual_factor', displayName: 'Custom slot' },
    }])
    expect(validation.canContinue).toBe(false)
    expect(validation.issues).toContainEqual(expect.objectContaining({ code: 'manual_factor_forbidden' }))
  })

  it('requires an explicit existing-factor target key', () => {
    const draft = createKmaiMappingDrafts([
      { field: 'cad.features', value: 'slot', occurrences: 1, rule_refs: ['rule.slot'] },
    ], { scope: 'project', projectId: 9 })[0]!

    const validation = validateKmaiMappingDrafts([{ ...draft, resolution: {
      mode: 'existing_factor',
      factorKey: ' ',
    } }])

    expect(validation.canContinue).toBe(false)
    expect(validation.issues).toContainEqual(expect.objectContaining({ code: 'target_factor_key_required' }))
  })

  it('requires a manual display name and never sends a client factor key for manual factors', () => {
    const draft = createKmaiMappingDrafts([
      { field: 'special.requirements', value: 'Custom requirement', occurrences: 1, rule_refs: ['rule.custom'] },
    ], { scope: 'project', projectId: 9 })[0]!
    const unresolvedManual = { ...draft, resolution: { mode: 'manual_factor' as const, displayName: ' ' } }

    expect(validateKmaiMappingDrafts([unresolvedManual]).canContinue).toBe(false)

    const request = toKmaiMappingBatchRequest([{ ...draft, resolution: {
      mode: 'manual_factor',
      displayName: 'Custom requirement',
    } }])

    expect(request).toEqual({
      mappings: [{
        scope: 'project',
        project_id: 9,
        source_field: 'special.requirements',
        source_value: 'Custom requirement',
        mapping_mode: 'manual_factor',
        target_factor_name: 'Custom requirement',
      }],
    })
    expect(request.mappings[0]).not.toHaveProperty('target_factor_key')
  })

  it('does not allow continuing with an unresolved draft', () => {
    const drafts = createKmaiMappingDrafts([
      { field: 'special.requirements', value: 'Unmapped text', occurrences: 1, rule_refs: ['rule.custom'] },
    ], { scope: 'project', projectId: 9 })

    expect(validateKmaiMappingDrafts(drafts).canContinue).toBe(false)
  })

  it('validates scope and builds one atomic batch request for valid drafts', () => {
    const projectDraft = createKmaiMappingDrafts([
      { field: 'cad.features', value: 'slot', occurrences: 1, rule_refs: ['rule.slot'] },
    ], { scope: 'project', projectId: 9 })[0]!
    const globalDraft = createKmaiMappingDrafts([
      { field: 'special.requirements', value: 'Custom requirement', occurrences: 1, rule_refs: ['rule.custom'] },
    ], { scope: 'global', projectId: null })[0]!
    const validDrafts = [
      { ...projectDraft, resolution: { mode: 'existing_factor' as const, factorKey: 'has_slot' } },
      { ...globalDraft, resolution: { mode: 'manual_factor' as const, displayName: 'Custom requirement' } },
    ]

    expect(validateKmaiMappingDrafts(validDrafts)).toEqual({ canContinue: true, issues: [] })
    expect(toKmaiMappingBatchRequest(validDrafts)).toEqual({
      mappings: [
        expect.objectContaining({ scope: 'project', project_id: 9, target_factor_key: 'has_slot' }),
        expect.objectContaining({
          scope: 'global',
          mapping_mode: 'manual_factor',
          target_factor_name: 'Custom requirement',
        }),
      ],
    })
    expect(toKmaiMappingBatchRequest(validDrafts).mappings[1]).not.toHaveProperty('project_id')

    const invalidGlobalScope = {
      ...globalDraft,
      resolution: { mode: 'manual_factor' as const, displayName: 'Custom requirement' },
      projectId: 9,
    }
    expect(validateKmaiMappingDrafts([invalidGlobalScope]).canContinue).toBe(false)
  })

  it('requires explicit global authorization for a no-project global batch', () => {
    const [draft] = createKmaiMappingDrafts([
      { field: 'cad.features', value: 'slot', occurrences: 1, rule_refs: ['rule.slot'] },
    ], { scope: 'global', projectId: null })
    const globalDraft = { ...draft!, resolution: { mode: 'existing_factor' as const, factorKey: 'has_slot' } }

    const unauthorized = validateKmaiMappingDrafts([globalDraft], { allowGlobal: false } as any)
    expect(unauthorized.canContinue).toBe(false)
    expect(unauthorized.issues).toContainEqual(expect.objectContaining({ code: 'global_scope_forbidden' }))
    expect(() => toKmaiMappingBatchRequest([globalDraft], { allowGlobal: false } as any)).toThrow()

    expect(validateKmaiMappingDrafts([globalDraft], { allowGlobal: true } as any)).toEqual({
      canContinue: true,
      issues: [],
    })
  })
})
