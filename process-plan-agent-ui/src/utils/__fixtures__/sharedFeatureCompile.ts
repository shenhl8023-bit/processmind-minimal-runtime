import { buildGuidedDraft } from '@/composables/analysisGuidanceFlow'
import type { AnalysisGuidanceConfiguration } from '@/api/analysisGuidance'
import { buildCompileRequestFromCards } from '../finalizeRulePackage'
import { projectConditionFields, projectConditionScope } from '../projectConditionFields'

const config: AnalysisGuidanceConfiguration = {
  schema_version: '1.0', revision: 0, guidance: '', materials: ['9Cr18'],
  directions: ['A侧', 'B侧', '中间', '周边', '所有方位'],
  feature_mappings: { 孔: ['孔(通孔)', '孔(盲孔)'] },
  operation_guidance: { 磨孔: { feature_group: '孔' }, 珩孔: { feature_group: '孔' } },
}

type Source = 'guided' | 'editor'
type Precision = 'it' | 'ra'

function card(processId: string, source: Source, precision: Precision, threshold: number, index: number, kind: 'configuration' | 'condition') {
  const segment: any = {
    id: processId, export_process_id: processId, normalized_step_name: index ? '珩孔' : '磨孔', sequence: index + 1,
    source_nodes: [], doc_coverage: { total_docs: 2, hit_docs: 1 },
  }
  const answers = Object.fromEntries(Object.entries({
    guided_mode: 'condition', guided_basis: precision === 'it' ? 'precision' : 'roughness',
    guided_features: '孔(通孔)', guided_direction: 'A侧', [precision === 'it' ? 'guided_it' : 'guided_ra']: String(threshold),
  }).map(([nodeId, value]) => [nodeId, { nodeId, value, label: value }]))
  const draft = buildGuidedDraft(segment, config, answers, [segment])
  if (!draft?.candidate) throw new Error('Incomplete finishing fixture')
  const candidate: any = JSON.parse(JSON.stringify(draft.candidate))
  if (source === 'editor') {
    // These are the actual definitions used by ProcessConfigurationEditor.
    candidate.field_definitions = projectConditionFields(processId, segment.normalized_step_name, config)
      .filter(field => ['features', 'direction', precision].includes(field.key.split('.').pop()!))
    const scope = projectConditionScope(processId)
    candidate.configuration.when = { all: [
      { field: `${scope}.features`, op: 'contains_any', value: ['孔(通孔)'] },
      { field: `${scope}.direction`, op: 'eq', value: 'A侧' },
      { field: `${scope}.${precision}`, op: 'lte', value: threshold },
    ] }
  }
  if (kind === 'condition') {
    candidate.kind = 'condition'
    candidate.when = candidate.configuration.when
    candidate.then = { include_process_ids: [processId], exclude_process_ids: [] }
    delete candidate.configuration
  }
  return {
    segment, edited: true, conditionText: draft.condition_text,
    conditionReview: {
      source_text: draft.condition_text, status: 'confirmed', confirmed: candidate,
      confirmed_by: '隔离回归', confirmed_at: '2026-11-16T08:00:00+00:00', issues: [],
    },
  }
}

/** Actual question/editor definitions → finalize builder, for TS/API parity. */
export function buildSharedFeatureCompileCases() {
  const definitions: Array<{ id: string; sources: Source[]; precision: Precision[]; kind?: 'configuration' | 'condition' }> = [
    { id: 'guided-it', sources: ['guided'], precision: ['it'] },
    { id: 'guided-ra', sources: ['guided'], precision: ['ra'] },
    { id: 'editor-it', sources: ['editor'], precision: ['it'] },
    { id: 'editor-ra', sources: ['editor'], precision: ['ra'] },
    { id: 'mixed-guided-editor-it', sources: ['guided', 'editor'], precision: ['it', 'it'] },
    { id: 'mixed-editor-guided-it', sources: ['editor', 'guided'], precision: ['it', 'it'] },
    { id: 'shared-it-ra', sources: ['guided', 'editor'], precision: ['it', 'ra'] },
    { id: 'legacy-rule-it', sources: ['guided'], precision: ['it'], kind: 'condition' },
    { id: 'legacy-rule-ra', sources: ['guided'], precision: ['ra'], kind: 'condition' },
    { id: 'legacy-mixed-it', sources: ['guided', 'editor'], precision: ['it', 'it'], kind: 'condition' },
  ]
  return definitions.map(definition => {
    const cards = definition.sources.map((source, index) => card(index ? 'hone' : 'grind', source,
      definition.precision[index]!, definition.precision[index] === 'ra' ? 0.8 : index ? 6 : 7, index, definition.kind || 'configuration'))
    const prepare: any = {
      segment: { id: 'prepare', export_process_id: 'prepare', normalized_step_name: '备料', sequence: 0,
        source_nodes: [], doc_coverage: { total_docs: 2, hit_docs: 2 } },
      conditionText: '始终安排备料', edited: false,
    }
    return { id: definition.id, cards, request: buildCompileRequestFromCards({
      projectId: 7, routeVersionId: 1, packageName: definition.id, cards: [prepare, ...cards],
      displayName: segment => segment.normalized_step_name, phaseLabel: () => 'finishing',
      primarySteps: () => ['加工内孔'], attachedSteps: () => [], conditionFields: [],
    }) }
  })
}
