# Route Merge Feedback Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every single and batch merge review action report success or a useful failure instead of appearing to do nothing.

**Architecture:** Keep the current API and review state flow. Validate local state before sending a request, surface missing state and request failures through the existing `setError` path, and only announce batch completion after every requested action and refresh succeeds.

**Tech Stack:** Vue 3 composables, TypeScript, Vitest; FastAPI workflow review endpoint and pytest regression coverage where needed.

**Spec:** `docs/superpowers/specs/2026-10-20-route-merge-model-assistance-design.md` (interaction feedback section)

## Global Constraints

- Do not change the PDF extraction or left process-tree flow.
- Preserve the existing `/api/extract/merge-suggestions/review` contract.
- Do not claim success if local validation, request submission, or workspace refresh fails.

## Review Focus

- Missing candidate group or project ID: show a visible error and do not call the review API.
- Missing backend suggestion ID: show a refresh/retry message and do not call the API.
- API rejection or workflow revision conflict: show failure and retain a recoverable workspace state.
- Workspace refresh failure after a successful review: do not report that the displayed workspace is up to date.
- First failure in a batch: stop processing and do not show the all-complete message.

---

### Task 1: Diagnose and cover single-action no-op paths

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.ts`
- Test: `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.spec.ts`
- Inspect: `process-plan-agent-ui/src/views/ExtractView.vue`

**Interfaces:**
- Consumes: existing `applyMergeSuggestionAction(groupId, action, setError)` and `setError` callback.
- Produces: same signature; all invalid preconditions set a specific error, successful requests return true only after a successful workspace refresh.

- [x] **Step 1: Trace the UI action in the running application and record whether the request is sent, its status, and refresh behavior.**
- [x] **Step 2: Write failing tests for missing project/group, missing suggestion ID, and refresh failure. Assert API call count, returned boolean, and error text.**
- [x] **Step 3: Run `cd process-plan-agent-ui && npm test -- src/composables/useRouteMergeWorkspace.spec.ts` and verify the new cases fail for the expected missing feedback/incorrect success behavior.**
- [x] **Step 4: Add explicit `setError` messages for missing state and return success only when `refreshRouteMergeWorkspace` succeeds.**
- [x] **Step 5: Re-run the focused Vitest file and the UI build with `cd process-plan-agent-ui && npm run build`.**

### Task 2: Stop batch review on failure and report its outcome

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.ts`
- Test: `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.spec.ts`

**Interfaces:**
- Consumes: Task 1's boolean success result from `applyMergeSuggestionAction`.
- Produces: batch actions stop at the first failed item and preserve its error; the all-complete notice is set only after every item succeeds.

- [x] **Step 1: Add failing tests for a batch whose first review fails and for a batch whose all reviews succeed. Assert call order and final notice.**
- [x] **Step 2: Run the focused test file and verify failure is caused by the unconditional completion notice.**
- [x] **Step 3: Update `confirmAllMergeGroups` and `rejectAllMergeGroups` to set completion notice only when the full batch succeeds.**
- [x] **Step 4: Run focused Vitest, full UI tests with `cd process-plan-agent-ui && npm test`, and `npm run build`.**

### Task 3: Verify review endpoint errors remain visible to the UI

**Files:**
- Inspect: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_workflow_invalidation.py`

**Interfaces:**
- Consumes: existing review request and HTTP error behavior.
- Produces: stable client-visible conflict/not-found errors; no API shape change unless the test proves the existing response is insufficient.

- [x] **Step 1: Add or extend an API test for stale workflow revision and nonexistent suggestion ID.**
- [x] **Step 2: Run the targeted pytest cases and verify the expected HTTP status and detail.**
- [x] **Step 3: Make the smallest endpoint correction only if the current contract fails the test.**
- [x] **Step 4: Run targeted API tests and confirm the UI's existing error path displays the returned failure.**
