# Finalize Manual Rule Mode Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add direct “main process” and user-controlled Boolean process modes to fourth-step rule review.

**Architecture:** A backend manual-rule endpoint persists explicit user decisions without invoking the LLM. A frontend utility builds stable Boolean candidates and derives the active manual mode, while every rule card exposes the same compact controls. Draft saving performs a normalized equality check before causing any state change.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy, Vue 3, TypeScript, Vitest, Pytest.

## Global Constraints

- Boolean false is the default and excludes the optional process by omission.
- The generated field key is stable for a given process ID.
- The target process cannot be changed by editing the Boolean label.
- Existing natural-language parsing remains unchanged.

### Task 1: Manual rule persistence

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_contracts.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Produces: `set_manual_condition_review(request, db)` for `mainline` and `boolean` decisions.

- [ ] Write failing API-service tests for Boolean persistence and mainline clearing.
- [ ] Run focused Pytest tests and confirm they fail.
- [ ] Implement strict request validation and persistence.
- [ ] Run focused tests and confirm they pass.

### Task 2: Stable Boolean candidate builder

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Test: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

**Interfaces:**
- Produces: `buildManualBooleanRuleCandidate(item, label)` returning a Boolean field, `eq true`, and the current target process.

- [ ] Write failing Vitest assertions for stable key, Boolean type, and target process.
- [ ] Run the focused test and confirm it fails.
- [ ] Implement the candidate builder.
- [ ] Run the focused test and confirm it passes.

### Task 3: Rule-card fallback controls

**Files:**
- Modify: `process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`

**Interfaces:**
- Consumes: the manual-rule endpoint and Boolean candidate builder.
- Produces: `set-mainline` and `set-boolean` card events with busy/error feedback.

- [ ] Add the two compact fallback actions and inline Boolean label editor.
- [ ] Persist the selected mode, update local route state, and invalidate the old export.
- [ ] Run all frontend tests and production build.
- [ ] Run all backend tests and `git diff --check`.

### Task 4: Consistent card actions and no-op saves

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useFinalizeDrafts.ts`
- Create: `process-plan-agent-ui/src/composables/useFinalizeDrafts.spec.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`
- Modify: `process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- `saveInlineEdit(item): boolean` returns `false` when trimmed text is unchanged and leaves drafts untouched.
- `manualRuleModeActionState(item, inlineEditing)` returns visibility and active-mode flags used by every card.

- [ ] Write failing Vitest cases for unchanged and changed saves.
- [ ] Write failing Vitest cases for mainline, conditional, and manual Boolean card action states.
- [ ] Run focused tests and confirm they fail for the missing behavior.
- [ ] Add the normalized no-op guard and stop export invalidation/parsing when it returns `false`.
- [ ] Move the manual-mode action row outside collapsible card content and render active modes as disabled buttons.
- [ ] Run focused tests, all frontend tests, the production build, and `git diff --check`.
