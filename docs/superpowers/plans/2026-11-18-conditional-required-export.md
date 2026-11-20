# Conditional Required Export Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans to implement task-by-task. No additional Git commit or publication is authorized by this plan.

**Goal:** Export shared-feature rules without losing conditional input validation.
**Architecture:** Add optional factor.required_when to the existing three arrays and validate/evaluate it in the receiver. Native V2 remains unchanged; stable short IDs rewrite the new references.
**Tech Stack:** Vue/TypeScript/Vitest and Python3.8-compatible standard-library receiver/pytest.
**Spec:** docs/superpowers/specs/2026-11-18-conditional-required-export-design.md

## Global Constraints

- Win7 Pro / Python3.8 target; no dependency upgrades.
- Preserve business data, model settings and untracked user files.
- Keep three JSON arrays and persistent P/S/F identity contracts.
- Old receivers require the companion update; no remote installation claimed.

## Review Focus

- Short IDs must rewrite required_when.field and generated source paths together.
- Missing data for one selected feature cannot be supplied by another.
- No selected_processes, some or repeated array sources in input requirements.
- Preview may remain incomplete; generation must reject missing active inputs.
- Factor order and static-required legacy packages must remain correct.

## Task 1: Export and protocol validation

Files: sampleRulePackageAdapter.ts, validatedRulePackageDownload.spec.ts, rule_packages/demo_tables.py, tests/test_conditional_required_export.py.

- [x] Replace the old intentional refusal test with a successful three-table/short-ID test and watch it fail.
- [x] Add invalid-reference/type/context cases to both public validators; observe failures.
- [x] Output required_when for declared shared parameters, overriding static required only for those parameters; rewrite references during compaction.
- [x] Validate new conditions using existing typed expression validators and reject route/array context.
- [x] Run targeted tests and verify missing-input behavior remains distinct from route conditions.

## Task 2: Receiver and integration

Files: integrations/kmai/config_route_engine.py, integrations/kmai/README.md; sync the authorized local KmAI engine after verification.

- [x] Preserve the current receiver as the baseline; add runnable integration tests showing missing selected-feature parameters are incorrectly accepted.
- [x] Validate required_when references after indexing all factors and enforce it after mapping all factors, before planning routes. Keep parameter preview and old packages unchanged.
- [x] Cross-check original and short-ID export against native input validation and planner for selected/unselected/missing/wrong-type/IT/Ra cases.
- [x] Run frontend/backend regressions, production build, Python3.8 syntax check and isolated-browser download.
- [x] Record evidence and remaining deployment limits in PM-091 and provide the receiver update with usage instructions.

## Completion evidence

Final independent review findings fixed in one TDD pass; 84 integration tests, frontend 1416 passed / 1 skipped, backend 2262 passed / 111 skipped, build and Python3.8 static checks passed. Browser ZIP retains three arrays (41/41/41); 21 missing-parameter checks rejected; 30/31-process examples match native routes. Local companion reader updated after backup, full local repair archive verified and smoke-started on macOS. Another computer and Win7 native execution remain untested. No commit/push/publication; preserve branch and workspace. See PM-091 for artifacts/checksums and final execution ledger.
