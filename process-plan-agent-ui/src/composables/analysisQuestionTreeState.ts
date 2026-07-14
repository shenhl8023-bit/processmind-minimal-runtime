import type { SavedNormalizedRouteVersionResult } from '@/api'

type Segment = SavedNormalizedRouteVersionResult['segments'][number]

export interface TreeAnswer {
  nodeId: string
  value: string
  label: string
}

export interface SegmentTreeState {
  answers: Record<string, TreeAnswer>
  note: string
}

const LEGACY_NODE_ID_MAP: Record<string, string> = {
  coverage_reason_root: 'rule_reason_root',
  coverage_reason_other: 'rule_reason_other',
  coverage_material_type: 'material_basis_type',
  coverage_structure_type: 'structure_scene_type',
  coverage_size_type: 'size_driver_type',
  coverage_blank_type: 'blank_basis_type',
  coverage_requirement_type: 'requirement_scene_type',
  coverage_requirement_scope: 'requirement_scope_detail',
  coverage_structure_primary: 'structure_feature_primary',
  coverage_material_scope: 'material_scope_detail',
  coverage_size_scope: 'size_scope_detail',
  coverage_blank_scope: 'blank_scope_detail',
  coverage_structure_other_note: 'structure_other_note_prompt',
  coverage_requirement_other_note: 'requirement_other_note_prompt',
}

export function normalizeQuestionNodeId(nodeId: string) {
  return LEGACY_NODE_ID_MAP[nodeId] || nodeId
}

function normalizeTreeAnswer(answer: Partial<TreeAnswer> | null | undefined): TreeAnswer | null {
  const nodeId = normalizeQuestionNodeId(String(answer?.nodeId || '').trim())
  const value = String(answer?.value || '').trim()
  const label = String(answer?.label || '').trim()
  if (!nodeId || !value) return null
  return { nodeId, value, label }
}

function normalizeAnswersRecord(raw: unknown) {
  if (!raw || typeof raw !== 'object') return {}
  return Object.entries(raw as Record<string, Partial<TreeAnswer>>).reduce<Record<string, TreeAnswer>>((acc, [key, value]) => {
    const normalized = normalizeTreeAnswer({
      ...(value || {}),
      nodeId: value?.nodeId || key,
    })
    if (!normalized) return acc
    acc[normalized.nodeId] = normalized
    return acc
  }, {})
}

export function createEmptySegmentTreeState(): SegmentTreeState {
  return {
    answers: {},
    note: '',
  }
}

export function savedQuestionTrail(segment: Segment | null): TreeAnswer[] {
  const trail = segment?.rule_review?.question_trail
  if (!Array.isArray(trail)) return []
  return trail
    .map(item => normalizeTreeAnswer(item))
    .filter((item): item is TreeAnswer => !!item)
}

export function answersFromTrail(trail: TreeAnswer[]) {
  return trail.reduce<Record<string, TreeAnswer>>((acc, item) => {
    acc[item.nodeId] = item
    return acc
  }, {})
}

export function loadPersistedTreeState(storageKey: string) {
  if (typeof window === 'undefined') return {}
  try {
    const raw = window.localStorage.getItem(storageKey)
    if (!raw) return {}
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object') return {}
    return Object.entries(parsed as Record<string, SegmentTreeState>).reduce<Record<string, SegmentTreeState>>((acc, [segmentId, state]) => {
      acc[segmentId] = {
        answers: normalizeAnswersRecord(state?.answers),
        note: String(state?.note || ''),
      }
      return acc
    }, {})
  } catch (error) {
    console.warn('读取问题树本地状态失败', error)
    return {}
  }
}

export function persistTreeState(storageKey: string, value: Record<string, SegmentTreeState>) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.setItem(storageKey, JSON.stringify(value))
  } catch (error) {
    console.warn('保存问题树本地状态失败', error)
  }
}

export function clearPersistedTreeState(storageKey: string) {
  if (typeof window === 'undefined') return
  try {
    window.localStorage.removeItem(storageKey)
  } catch (error) {
    console.warn('清除问题树本地状态失败', error)
  }
}

export function clearProjectQuestionTreeStorage(projectId: string | number | null | undefined) {
  if (typeof window === 'undefined') return
  const normalizedProjectId = String(projectId || '').trim()
  if (!normalizedProjectId) return
  try {
    for (let idx = window.localStorage.length - 1; idx >= 0; idx -= 1) {
      const key = window.localStorage.key(idx)
      if (!key) continue
      if (!key.startsWith('processmind_analysis_question_tree_')) continue
      if (!key.endsWith(`_${normalizedProjectId}`)) continue
      window.localStorage.removeItem(key)
    }
  } catch (error) {
    console.warn('按项目清除问题树本地状态失败', error)
  }
}
