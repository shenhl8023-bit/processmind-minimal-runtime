import { expect, it } from 'vitest'
import { ref } from 'vue'
import { buildFinalTemplateMappingOperations } from './finalTemplateMappingOperations'
import { useRouteSegmentSteps } from './useRouteSegmentSteps'
import { buildTemplateStepRefs } from './templateStepMapping'
import { buildTemplateRouteStructureOperations } from './templateGroupMapping'
import { buildCompileRequestFromCards } from '@/utils/finalizeRulePackage'
import { buildFinalRouteSteps, finalProcessMetadata } from './finalRouteSteps'
const sources = [
  { id: 7, name: '车', step_items: ['平端面', '车外圆'], attached_step_items: ['倒角'] },
  { id: 8, name: '车槽', step_items: ['平端面', '挖槽'] },
  { id: 9, name: '钻', step_items: ['钻锥孔'] },
] as any
const segment = { id: 'turning_a', sequence: 1, normalized_step_name: '车削加工（A侧）', phase: 'rough', source_operation_ids: [7, 8, 9] } as any
it('renders one final parent for a merge and shares third-step primary/attached steps', () => {
  const result = buildFinalTemplateMappingOperations([segment], sources)
  expect(result).toHaveLength(1)
  const tree = useRouteSegmentSteps(ref(sources))
  expect(result[0]!.step_items).toEqual([...tree.segmentPrimarySteps(segment), ...tree.segmentAttachedSteps(segment)])
  expect(result[0]!.step_items).toEqual(['平端面', '车外圆', '挖槽', '钻锥孔', '倒角'])
  const payload = buildTemplateRouteStructureOperations(result)[0]!
  expect(payload).toMatchObject({ process_id: 'turning_a', source_operation_ids: [7, 8, 9] })
  expect(payload.steps![0]!.source_steps).toEqual([
    { source_operation_id: 7, source_operation_name: '车', source_step_order: 1, source_step_name: '平端面' },
    { source_operation_id: 8, source_operation_name: '车槽', source_step_order: 1, source_step_name: '平端面' },
  ])
  expect(buildTemplateStepRefs(result[0]!)[2]).toMatchObject({ operation_id: 8, step_order: 2, step_name: '挖槽' })
})
it('keeps new nodes, repeated names and split nodes sharing a source, in final sequence', () => {
  const result = buildFinalTemplateMappingOperations([
    { ...segment, id: 'end-clean', sequence: 4, normalized_step_name: '清洗', source_operation_ids: [] },
    { ...segment, id: 'front-clean', sequence: 1, normalized_step_name: '清洗', source_operation_ids: [] },
    { ...segment, id: 'turn-b', sequence: 3, source_operation_ids: [7] },
    { ...segment, id: 'turn-a', sequence: 2, source_operation_ids: [7] },
  ], sources)
  expect(result.map(item => item.process_id)).toEqual(['front-clean', 'turn-a', 'turn-b', 'end-clean'])
  expect(new Set(result.map(item => item.id)).size).toBe(4)
})
it('keeps identity when the final parent is renamed and reordered', () => {
  const first = buildFinalTemplateMappingOperations([segment], sources)[0]!
  const second = buildFinalTemplateMappingOperations([{ ...segment, sequence: 10, normalized_step_name: '新工序名' }], sources)[0]!
  expect(first.id).toBe(second.id)
  expect(first.process_id).toBe(second.process_id)
  expect(first.steps!.map(step => step.step_id)).toEqual(second.steps!.map(step => step.step_id))
})
it('keeps source positions for attached steps and recognizes the final machining families', () => {
  const result = buildFinalTemplateMappingOperations([
    { ...segment, id: 'drill', normalized_step_name: '打孔', step_family: '孔加工类', source_operation_ids: [11] },
    { ...segment, id: 'flat', sequence: 2, normalized_step_name: '割扁', step_family: '特征加工类', source_operation_ids: [12] },
  ], [
    { id: 11, name: '打孔', step_items: ['打孔'], attached_step_items: ['刻线'] },
    { id: 12, name: '割扁', step_items: ['割扁'] },
  ] as any)
  expect(result.map(item => item.process_type)).toEqual(['加工工序', '加工工序'])
  expect(result[0]!.steps![1]).toMatchObject({ source_operation_id: 11, source_step_order: 2, source_step_name: '刻线' })
})
it('keeps raw attached source names and positions distinct from equal primary names', () => {
  const steps = buildFinalRouteSteps({ ...segment, source_operation_ids: [11] }, [{
    id: 11, name: '打孔', step_items: ['刻线（主工步）'],
    attached_step_items: ['刻线（附带一）', '刻线（附带二）'],
  }] as any)
  expect(steps.map(step => ({ kind: step.kind, order: step.source_step_order, name: step.source_step_name }))).toEqual([
    { kind: 'primary', order: 1, name: '刻线（主工步）' },
    { kind: 'attached', order: 2, name: '刻线（附带一）' },
    { kind: 'attached', order: 3, name: '刻线（附带二）' },
  ])
  expect(new Set(steps.map(step => step.step_id)).size).toBe(3)
})
it('uses a user-confirmed precision override when serializing mapping operations', () => {
  const operation = { ...buildFinalTemplateMappingOperations([segment], sources)[0]!, precision: '' }
  expect(buildTemplateRouteStructureOperations([operation], { turning_a: '半精加工' })[0]!.precision).toBe('半精加工')
})
it.each(['孔加工类', '特征加工类', '车削类', '车削/成形类'])('recognizes the %s machining family independently of its display name', step_family => {
  expect(finalProcessMetadata({ step_family, normalized_step_name: '自定义工序', phase: 'rough' }, [])).toEqual({
    process_type: '加工工序', precision: '粗加工',
  })
})
it.each([
  ['rough', '粗加工'], ['semi_finish', '半精加工'], ['finish', '精加工'],
  ['roughing', '粗加工'], ['finishing', '精加工'],
])('maps structured route phase %s to process precision %s', (phase, precision) => {
  expect(finalProcessMetadata({ step_family: '孔加工类', normalized_step_name: '加工内孔', phase }, []).precision).toBe(precision)
})
it('leaves an unknown machining phase unresolved for explicit mapping confirmation', () => {
  expect(finalProcessMetadata({ step_family: '孔加工类', normalized_step_name: '精密内孔加工', phase: 'unclassified' }, []).precision).toBe('')
})
it.each(['打孔', '割扁', '刻线'])('recognizes %s without a machining family', normalized_step_name => {
  expect(finalProcessMetadata({ normalized_step_name, phase: 'finish' }, []).process_type).toBe('加工工序')
})
it('keeps surface treatment auxiliary even with machining words in its source steps', () => {
  expect(finalProcessMetadata({ normalized_step_name: '表面处理', step_family: '特征加工类', phase: 'surface_treatment' }, [
    { step_name: '打孔后表面处理' },
  ] as any)).toEqual({ process_type: '辅助工序', precision: '辅助工序' })
})
it('uses exactly the mapped final IDs and step order in the publication catalog', () => {
  const segments = [segment, { ...segment, id: 'clean', sequence: 2, phase: 'auxiliary', normalized_step_name: '清洗', source_operation_ids: [9] },
    { ...segment, id: 'quench-a', sequence: 3, phase: 'heat_treatment', normalized_step_name: '淬火（A侧）', source_operation_ids: [] }]
  const mapping = buildFinalTemplateMappingOperations(segments, sources)
  const tree = useRouteSegmentSteps(ref(sources))
  const compiled = buildCompileRequestFromCards({
    projectId: 28, packageName: 'identity-contract',
    cards: segments.map(segment => ({ segment, conditionText: '始终保留', factorNames: ['always=true'] })),
    displayName: segment => segment.normalized_step_name, phaseLabel: segment => segment.phase,
    primarySteps: tree.segmentPrimarySteps, attachedSteps: tree.segmentAttachedSteps, finalSteps: tree.segmentStepNodes,
  })
  expect(compiled.processes.map(process => ({
    name: process.display_name,
    process_id: process.process_id, steps: process.steps!.map(step => ({ step_id: step.step_id, step_name: step.name })),
  }))).toEqual(mapping.map(process => ({
    name: process.name,
    process_id: process.process_id,
    steps: process.process_type === '辅助工序' ? [] : process.steps!.map(({ step_id, step_name }) => ({ step_id, step_name })),
  })))
})
