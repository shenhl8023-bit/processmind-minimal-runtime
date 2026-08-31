# Rule Preprocessing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Start rule-condition recognition in the background after Step 3 saves a normalized route, so Step 4 opens with persisted candidates and only performs confirmation/publishing work.

**Architecture:** Add a small persistent preprocessing task state table and an in-process async job registry, following the existing extraction task pattern. The job loads the saved route, skips current candidates, calls the existing condition parser for each eligible segment with bounded concurrency, and persists progress/errors. Step 3 triggers the job after saving; Step 4 polls status and displays progress while continuing to use the existing review/publish flow.

**Tech Stack:** FastAPI, SQLAlchemy async sessions, SQLite schema maintenance, Vue 3 + TypeScript, Vitest.

**Spec:** Product decision from 2026-08-21 conversation: preprocessing recognizes candidates only; user confirmation remains in Step 4; no Redis/Celery for this iteration.

## Global Constraints

- Do not auto-confirm low-confidence candidates.
- Do not change the meaning of `draft`, `pending_confirmation`, `confirmed`, or `invalid`.
- Reuse `parse_condition_review` and existing field/parser version checks.
- Never overwrite a newer draft or newer workflow revision.
- Keep existing group-template mapping bypass behavior unchanged.
- Preserve unrelated dirty-worktree changes.

### Task 1: Add persistent preprocessing task state

**Files:**
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Test: `process-plan-agent-api/tests/test_rule_preprocessing.py`

- [ ] Add `rule_preprocess_task_states` with one row per `(project_id, route_version_id)`, status/progress/error/version columns, and a unique index.
- [ ] Add schema-maintenance coverage that can initialize the table on an existing SQLite database.
- [ ] Run the focused schema test.

### Task 2: Implement the backend preprocessing service

**Files:**
- Create: `process-plan-agent-api/app/services/rule_preprocessing.py`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`
- Test: `process-plan-agent-api/tests/test_rule_preprocessing.py`

**Interfaces:**
- `POST /api/extract/finalized-rule-packages/preprocess/start`
- `GET /api/extract/finalized-rule-packages/preprocess/status`
- `queue_rule_preprocessing_job(project_id, route_id, expected_workflow_revision, db)`.

- [ ] Add request/response contracts for project, route, workflow revision, task status, counts, and current segment.
- [ ] Load route segments and existing reviews; construct process options from the saved route.
- [ ] Skip mainline segments, unresolved text, current pending candidates, and confirmed current candidates.
- [ ] Call the existing parser path with the current workflow revision and persist progress after each segment.
- [ ] Use a per-project/route lock and in-process task registry; recover stale running rows as failed with a retryable message.
- [ ] Expose start/status endpoints and return the persisted state.
- [ ] Add tests for queue idempotency, skip behavior, progress, failure persistence, and status reload.

### Task 3: Trigger preprocessing when leaving Step 3

**Files:**
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_rule_preprocessing.py`

- [ ] When the user clicks “进入规则定稿” from Step 3, build the current finalize cards and enqueue preprocessing asynchronously before navigation.
- [ ] Do not block navigation when background enqueue fails; log a warning and let Step 4 retry idempotently on load.
- [ ] Add an endpoint-level test proving repeated starts create at most one active task for the same route/input hash.

### Task 4: Add Step 4 progress polling and user-visible state

**Files:**
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Test: `process-plan-agent-ui/src/api/rulePackages.contract.spec.ts` or a new focused composable test.

- [ ] Add typed start/status API functions.
- [ ] On Step 4 load, start preprocessing idempotently and poll status while `running`.
- [ ] Show `规则预处理：已完成 X/Y 条` near the existing review progress.
- [ ] Keep “完成定稿并发布规则包” available; it should process only remaining items.
- [ ] Stop polling on route/project changes and show retry affordance on failed preprocessing.

### Task 5: Verify end-to-end behavior

**Files:**
- No new production files.

- [ ] Run backend focused tests.
- [ ] Run frontend focused tests.
- [ ] Run frontend build.
- [ ] Start/reload API and UI, save project 56 route, confirm preprocessing status endpoint progresses, then open Step 4 and verify no duplicate recognition requests for existing candidates.
