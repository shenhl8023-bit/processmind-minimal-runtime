# Finalize Pending Rules Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every rule that still needs human confirmation visible in the finalize page pending filter and keep all related status indicators consistent.

**Architecture:** Add one shared predicate in the existing finalize rule-package utility and make the finalize view derive filtering, remaining work, confirmation progress, and publish readiness from it. Keep the existing publish-blocker focus override and backend contracts unchanged.

**Tech Stack:** Vue 3, TypeScript, Vitest, Vite

## Global Constraints

- Do not change the ProcessMind V2 or KmAI V1 rule-package protocols.
- Do not add dependencies or unrelated refactors.
- Preserve user changes and do not create a Git commit automatically.

---

### Task 1: Define the shared pending-review predicate

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Test: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

**Interfaces:**
- Consumes: `requiresConfirmedUserRule(item)` and `hasCurrentConfirmedUserRule(item, registryVersion?)`
- Produces: `needsFinalizeRuleReview(item, registryVersion?): boolean`

- [ ] Add a failing unit test showing that a current `pending_confirmation` candidate still needs human review, while a confirmed candidate and a mainline card do not.
- [ ] Run `npm test -- --run src/utils/finalizeRulePackage.spec.ts` from `process-plan-agent-ui` and confirm the new test fails because the helper does not exist.
- [ ] Implement `needsFinalizeRuleReview` as the single composition of the existing mode and confirmation checks.
- [ ] Re-run the targeted test and confirm it passes.

### Task 2: Use the shared predicate throughout the finalize view

**Files:**
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Consumes: `needsFinalizeRuleReview(item, factorCatalogVersion)`
- Produces: one `pendingRuleCards` computed collection used by filtering, progress, publish readiness, navigation summary, and batch-review completion.

- [ ] Import `needsFinalizeRuleReview` and derive `pendingRuleCards` from `segmentCards`.
- [ ] Replace the local divergent `itemNeedsPending` logic and batch-review `remaining` filter with the shared collection.
- [ ] Count only confirmed reviewable rules in the header and update the copy to “已确认” / “全部已确认”.
- [ ] Base `allCurrentRulesConfirmed` on catalog readiness and the absence of pending cards.
- [ ] Update the no-pending empty-state description to state that all rule reviews are complete.

### Task 3: Verify the user-facing behavior

**Files:**
- Verify: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`
- Verify: `process-plan-agent-ui/src/composables/useRulePackagePublishReview.spec.ts`
- Verify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Consumes: the completed implementation from Tasks 1 and 2.
- Produces: test and build evidence for delivery.

- [ ] Run `npm test -- --run src/utils/finalizeRulePackage.spec.ts src/composables/useRulePackagePublishReview.spec.ts`.
- [ ] Run `npm run build` to execute `vue-tsc -b` and the Vite production build.
- [ ] Inspect `git diff --check` and the scoped diff to confirm there is no formatting damage or unrelated change.
