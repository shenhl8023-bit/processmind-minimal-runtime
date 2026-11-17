import type { RuleConditionCandidate } from '@/api/rulePackages'
import type { FinalizeCard } from './finalizeViewHelpers'
import {
  exportBlockingCards,
  exportProcessIdForItem,
  requiresServerRuleConditionRefresh,
} from '@/utils/finalizeRulePackage'
import { validateAuthoredCandidate } from '@/utils/processConfigurationEditor'

export type FinalizeBatchItem = {
  segmentId: string
  sequence: number
  name: string
  status: 'confirmed' | 'unsaved' | 'missing' | 'failed' | 'not_executed'
  reason: string
}

export type FinalizeBatchResult = {
  successCount: number
  remainingCount: number
  items: FinalizeBatchItem[]
}

export type FinalizeBatchConfirmOutcome = boolean | undefined | { status: 'workflow_conflict'; reason: string }

// Read live state before every submission: a previous request can allow a draft,
// candidate refresh or workspace change to arrive while the queue is waiting.
export async function confirmFinalizeBatch(options: {
  cards: () => FinalizeCard[]
  unsavedIds: () => Set<string>
  busyIds: () => Set<string>
  isCurrent: () => boolean
  displayName: (card: FinalizeCard) => string
  confirm: (card: FinalizeCard, candidate: RuleConditionCandidate) => Promise<FinalizeBatchConfirmOutcome>
  errorFor: (id: string) => string | undefined
  errorMessage: (error: unknown) => string
  onProgress: (completed: number, total: number) => void
}): Promise<FinalizeBatchResult | null> {
  const pendingIds = () => new Set([
    ...exportBlockingCards(options.cards()).map(card => card.segment.id),
    ...options.unsavedIds(),
  ])
  const signature = (card: FinalizeCard) => JSON.stringify([
    card.conditionText, card.conditionReview?.source_text,
    card.conditionReview?.source_hash, card.conditionReview?.candidate,
  ])
  const targetIds = pendingIds()
  const queue = options.cards().filter(card => targetIds.has(card.segment.id)).map(card => ({
    segmentId: card.segment.id, sequence: card.segment.sequence,
    name: options.displayName(card), signature: signature(card),
  }))
  const items: FinalizeBatchItem[] = []
  let successCount = 0
  options.onProgress(0, queue.length)
  for (const [index, target] of queue.entries()) {
    if (!options.isCurrent()) return null
    const current = options.cards().find(card => card.segment.id === target.segmentId)
    const record = (status: FinalizeBatchItem['status'], reason: string) => {
      items.push({ segmentId: target.segmentId, sequence: target.sequence, name: target.name, status, reason })
    }
    if (options.unsavedIds().has(target.segmentId)) {
      record('unsaved', '有未保存修改，请先保存或取消后再确认。')
    } else if (!current) {
      record('missing', '当前路线已不包含此工序，请刷新后核对。')
    } else if (!exportBlockingCards([current]).length) {
      // Another confirmation can finish while this item waits; keep its result.
    } else if (signature(current) !== target.signature) {
      record('missing', '规则内容或候选已变化，请核对最新内容后重试。')
    } else if (options.busyIds().has(target.segmentId)) {
      record('failed', '规则正在保存或识别，请稍后重试。')
    } else if (!current.conditionText.trim()) {
      record('missing', '缺少规则内容，请先补充并保存。')
    } else {
      const review = current.conditionReview
      if (review?.status !== 'pending_confirmation' || !review.source_hash || !review.candidate) {
        record('missing', '缺少待确认候选，请先识别或补充规则内容。')
      } else if (requiresServerRuleConditionRefresh(current)) {
        record('missing', '候选与当前规则内容或类型不一致，请重新识别后确认。')
      } else {
        const issues = validateAuthoredCandidate(review.candidate, exportProcessIdForItem(current))
        if (issues.length) {
          record('missing', issues.join('；'))
        } else {
          try {
            const confirmed = await options.confirm(current, review.candidate)
            if (!options.isCurrent()) return null
            if (confirmed && typeof confirmed === 'object' && confirmed.status === 'workflow_conflict') {
              record('failed', confirmed.reason)
              for (const remaining of queue.slice(index + 1)) {
                items.push({
                  segmentId: remaining.segmentId, sequence: remaining.sequence, name: remaining.name,
                  status: 'not_executed', reason: `未执行：工作流版本已过期，已停止本次批量确认。${confirmed.reason}`,
                })
              }
              options.onProgress(index + 1, queue.length)
              break
            }
            if (confirmed) {
              successCount += 1
              record('confirmed', '')
            } else {
              record('failed', options.errorFor(target.segmentId) || '规则未确认，请核对最新内容后重试。')
            }
          } catch (error) {
            if (!options.isCurrent()) return null
            record('failed', options.errorMessage(error))
          }
        }
      }
    }
    options.onProgress(index + 1, queue.length)
  }
  return options.isCurrent() ? { successCount, remainingCount: pendingIds().size, items } : null
}
