import type { SegmentFactorReview } from '@/api'

export interface FactorCandidate {
  key: string
  name: string
  sourceType: 'aggregated' | 'manual' | 'heuristic' | string
  strength: string
  confirmedCount: number
  operationCount: number
  operationNames: string[]
  evidences: string[]
  sourceOperationIds: number[]
  review: SegmentFactorReview | null
}
