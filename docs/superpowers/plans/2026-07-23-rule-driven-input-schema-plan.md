# Rule-Driven Input Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make fifth-step inputs contain only fields and option values referenced by the current fourth-step executable rule package.

**Architecture:** Build user-confirmed rules first, remove static fallback targets that are already covered by a user rule or mainline process, then derive the input schema from the final rules' AST. Keep the existing fifth-step consumer unchanged so it remains a pure reader of the published package.

**Tech Stack:** Vue 3 + TypeScript, FastAPI/Pydantic, Vitest, pytest.

## Global Constraints

- The fifth step must read `input_schema.fields` from the published V2 package.
- Unreferenced registry fields and options must not be exported.
- Existing custom feature/requirement tags must remain exportable.
- Static fallback rules may remain only for processes without a current user-confirmed or mainline decision.

### Task 1: Reproduce the hidden material option

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

- [ ] **Step 1: Write the failing test**

Add a case with a confirmed `9Cr18` rule and assert the compiled request does not include `95Cr18`, `4Cr14Ni14W2Mo`, or `6061` in `material.grade.options`, and does not keep the static `material.9Cr18.heat` rule when both target processes are user-confirmed.

- [ ] **Step 2: Run the focused test and verify it fails**

Run: `npm test -- --run src/utils/finalizeRulePackage.spec.ts`

Expected: FAIL because the current compiler exports the entire registry option list and the static material rule.

### Task 2: Derive the final executable rules

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Test: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

- [ ] **Step 1: Implement static-rule target filtering**

After building `userRules`, collect target process IDs from user actions and mainline processes. Filter each static rule's `then.include_process_ids` to IDs not covered by those decisions, dropping a static rule when no IDs remain.

- [ ] **Step 2: Run the focused test**

Run: `npm test -- --run src/utils/finalizeRulePackage.spec.ts`

Expected: The static-rule assertion passes while the option assertion still fails.

### Task 3: Build fields and options from final rules

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

- [ ] **Step 1: Implement AST collection**

Traverse every final rule condition through `all`, `any`, and `not`; collect referenced field keys and select values. Build the field map from only those keys, then append custom values and trim existing options to the collected values.

- [ ] **Step 2: Run focused tests**

Run: `npm test -- --run src/utils/finalizeRulePackage.spec.ts`

Expected: The new dynamic material test and existing custom-tag tests pass.

### Task 4: Regression verification

**Files:**
- Modify: `process-plan-agent-api/tests/test_rule_package_v2.py` only if a backend contract regression is exposed.

- [ ] **Step 1: Run frontend tests and build**

Run: `npm test && npm run build` in `process-plan-agent-ui`.

Expected: All Vitest tests pass and Vue type-check/build succeeds.

- [ ] **Step 2: Run backend tests**

Run: `.venv/bin/python -m pytest -q` in `process-plan-agent-api`.

Expected: All backend tests pass.

- [ ] **Step 3: Verify the published package path**

Open project 24 at `/finalize?project_id=24`, confirm the package is ready, then enter step 5 and verify the material field contains only values present in the exported package.
