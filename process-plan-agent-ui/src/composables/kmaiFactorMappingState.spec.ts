import { describe, expect, it } from 'vitest'

import {
  buildMappingRequest,
  mergeMappingIssues,
} from './kmaiFactorMappingState'

describe('KmAI factor mapping state', () => {
  it('merges repeated source pairs while retaining occurrence and rule evidence', () => {
    const merged = mergeMappingIssues([
      { field: 'cad.features', value: 'custom slot', occurrences: 1, rule_refs: ['rule.a'] },
      { field: 'cad.features', value: 'custom slot', occurrences: 2, rule_refs: ['rule.b', 'rule.a'] },
    ])

    expect(merged).toEqual([{
      field: 'cad.features',
      value: 'custom slot',
      occurrences: 3,
      rule_refs: ['rule.a', 'rule.b'],
    }])
  })

  it('sends an existing-factor selection as a project mapping', () => {
    expect(buildMappingRequest(12, {
      field: 'cad.features',
      value: 'custom slot',
      occurrences: 1,
      rule_refs: ['rule.a'],
    }, {
      mode: 'existing_factor',
      factorKey: 'has_slot_feature',
    })).toMatchObject({
      scope: 'project',
      project_id: 12,
      source_field: 'cad.features',
      source_value: 'custom slot',
      mapping_mode: 'existing_factor',
      target_factor_key: 'has_slot_feature',
    })
  })

  it('does not send a client-generated key for a manual factor', () => {
    const request = buildMappingRequest(12, {
      field: 'cad.features',
      value: 'custom slot',
      occurrences: 1,
      rule_refs: ['rule.a'],
    }, {
      mode: 'manual_factor',
      manualName: 'Custom slot feature',
    })

    expect(request).toMatchObject({
      mapping_mode: 'manual_factor',
      target_factor_name: 'Custom slot feature',
    })
    expect(request).not.toHaveProperty('target_factor_key')
    expect(request).not.toHaveProperty('target_factor_category')
  })
})
