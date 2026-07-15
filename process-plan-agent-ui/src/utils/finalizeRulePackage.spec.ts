import { describe, expect, it } from 'vitest'

import {
  buildCompileRequestFromCards,
  buildInputSchemaExport,
  buildRouteCatalogExport,
  buildRouteRulesExport,
  buildV2InputFields,
  validateRulePackage,
} from './finalizeRulePackage'
import { nestFactorValues } from '@/composables/useGenerateInputFields'


function finalizeItem(overrides: Record<string, any> = {}) {
  return {
    segment: {
      id: 'process_prepare',
      sequence: 10,
      normalized_step_name: '准备',
      step_family: 'prepare',
      source_nodes: [],
      doc_coverage: { total_docs: 2, hit_docs: 2 },
      ...overrides,
    },
    conditionText: '全部样本中稳定出现',
    factorNames: ['always=true'],
    userAnswerLabels: [],
    userAnswerContextLabels: [],
    systemFactorLabels: [],
  }
}


describe('V1 finalized rule package baseline', () => {
  it('keeps the four-slot input contract', () => {
    const schema = buildInputSchemaExport()

    expect(schema.required_inputs.map(field => field.key)).toEqual([
      'material_grade',
      'cad_features',
      'precision_grades',
    ])
    expect(schema.optional_inputs.map(field => field.key)).toEqual(['special_requirements'])
  })

  it('merges quench naming variants into one stable process id', () => {
    const cards = [
      finalizeItem({ id: 'quench-a', sequence: 20, normalized_step_name: '淬火' }),
      finalizeItem({ id: 'quench-b', sequence: 21, normalized_step_name: '真空淬火' }),
    ]
    const catalog = buildRouteCatalogExport({
      projectId: 1,
      projectName: '测试项目',
      routeVersion: 1,
      cards,
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => '热处理',
      primarySteps: () => ['装炉'],
      attachedSteps: () => [],
    })

    expect(catalog.segments).toHaveLength(1)
    expect(catalog.segments[0].process_id).toBe('process_quench')
    expect(catalog.segments[0].process_name).toBe('淬火')
  })

  it('validates a generated package without errors', () => {
    const cards = [finalizeItem()]
    const schema = buildInputSchemaExport()
    const catalog = buildRouteCatalogExport({
      projectId: 1,
      projectName: '测试项目',
      routeVersion: 1,
      cards,
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => '准备',
      primarySteps: () => ['清理'],
      attachedSteps: () => [],
    })
    const rules = buildRouteRulesExport({
      projectId: 1,
      projectName: '测试项目',
      routeVersion: 1,
      cards,
      displayName: segment => segment.normalized_step_name,
    })

    expect(validateRulePackage(schema, catalog, rules, '# 规则报告').errors).toEqual([])
  })
})


describe('V2 compile DTO from finalize cards', () => {
  it('builds four-slot V2 fields and stable process catalog', () => {
    const cards = [
      finalizeItem(),
      finalizeItem({ id: 'process_mill_slot', sequence: 20, normalized_step_name: '铣槽' }),
      finalizeItem({ id: 'quench-a', sequence: 30, normalized_step_name: '淬火' }),
    ]
    const request = buildCompileRequestFromCards({
      projectId: 12,
      packageName: 'demo_rules',
      routeVersionId: 3,
      cards,
      displayName: segment => segment.normalized_step_name,
      phaseLabel: () => 'machining',
      primarySteps: () => ['主工步'],
      attachedSteps: () => [],
    })

    expect(request.fields.map(field => field.key)).toEqual([
      'material.grade',
      'cad.features',
      'precision.grades',
      'special.requirements',
    ])
    expect(request.processes.some(item => item.process_id === 'process_quench')).toBe(true)
    expect(request.processes.some(item => item.main)).toBe(true)
    expect(request.rules!.length).toBeGreaterThan(0)
    expect(request.test_cases).toHaveLength(1)
    expect(request.test_cases![0]!.case_id).toBe('default-smoke')
    expect(request.test_cases![0]!.expect.included_process_ids!.length).toBeGreaterThan(0)
    expect(request.test_cases![0]!.input).toEqual({
      material: { grade: '9Cr18' },
      cad: { features: ['扁位/平面'] },
      precision: { grades: ['孔精加工'] },
      special: { requirements: ['渗氮层要求'] },
    })
    expect(buildV2InputFields()[0]!.type).toBe('single_select')
  })

  it('nests dotted factor keys for expression engine', () => {
    expect(nestFactorValues({
      'material.grade': '9Cr18',
      'cad.features': ['槽类特征'],
      target_hardness_hrc: 58,
    })).toEqual({
      material: { grade: '9Cr18' },
      cad: { features: ['槽类特征'] },
      target_hardness_hrc: 58,
    })
  })
})
