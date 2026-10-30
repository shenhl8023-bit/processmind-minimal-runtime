# Unified Rule Editor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** Integrate the approved three-mode editor and conjunctive process linkage into the local system.

**Architecture:** Persist atomic process configurations alongside legacy candidates; preserve complete semantics through publication, native planning and Demo export.

**Tech Stack:** Vue 3/TypeScript/Vitest; FastAPI/Pydantic/SQLAlchemy/Pytest.

**Spec:** docs/superpowers/specs/2026-10-27-unified-rule-editor-design.md

## Global Constraints
- Preserve clean card layout, colors, fonts and spacing.
- Preserve legacy candidates and all/any/not trees.
- Use existing review JSON/audit metadata; no database migration.
- Use current codex/zhaoyw feature checkout; preserve unrelated edits and active data.
- No reset, bulk-stage, commit or production publication.
- New condition groups default all and can switch to any; input predicate AND all trigger rows. No bypass through dependencies.

## Review Focus
- Legacy any/not and dynamic fields survive reload unchanged.
- Stale save/parse responses never overwrite newer edits.
- Dependencies/static rules cannot bypass failed gates.
- Publication rejects omitted or altered configurations.
- Demo and native generation agree for combined conditions and trigger chains.

---

### Task 1: Atomic backend configuration
**Files:** rule_packages/{contracts,condition_contracts,condition_parser,condition_reviews,confirmation_validation,validator,compiler,planner}.py; routers/rule_packages.py; focused API tests.
**Interfaces:** candidate kind process_configuration with configuration={process_id,occurrence,when,relations}; field_definitions top-level. CompileRulePackageRequest/RouteRulesV2.process_configurations contains audited full configurations. POST /rule-conditions/configuration accepts existing manual request shape and checks server segment identity.
- [x] Add failing tests: save/reload; tampered/omitted publication; manual copper yes/no; material AND triggers; multiple sources; chains; required-gate errors; four relationships; legacy hashes/trees. Run focused pytest and observe meaningful RED.
- [x] Implement compatible schemas, strict save, exact publication matching and atomic fixed-point planning; reject empty conditional, self links, cycles and wrong manual fields.
- [x] Run focused backend tests; expect PASS with exact selected IDs and persisted candidate equality.

### Task 2: Unified frontend editor
**Files:** api/rulePackages.ts; components/finalize/{FinalizeRuleCard,RuleConditionNodeEditor}.vue and specs; views/FinalizeView.vue/spec.ts; focused helpers as needed.
**Interfaces:** save-configuration event submits complete candidate; dedicated API method posts the configuration endpoint. Mode selection is draft-only.
- [x] Add failing SFC tests: one entry/three modes; no request on mode clicks; save/cancel; add/delete and all/any group switching; empty numeric/conditional; multiple relationships; legacy trees; failed save/stale responses. Run focused vitest and observe RED.
- [x] Implement using current classes and safeguards; full configuration in dirty signature, clear draft only on successful save.
- [x] Run focused UI tests; expect PASS including custom renderer imports.

### Task 3: Frontend package and presentation
**Files:** utils/finalizeRulePackage.ts/spec.ts; utils/finalizeRulePresentation.ts/spec.ts; finalizeViewHelpers.ts/spec.ts if required.
**Interfaces:** process_configurations carries full audited config; fields/factor_dictionary contains referenced fields; saved candidate wins over prose heuristics.
- [x] Write failing tests for mode recognition, three-mode compilation, field gathering, static fallback suppression and exact tree/relation retention. Run focused vitest and observe RED.
- [x] Implement atomic compilation, authoritative configuration targets and accurate summaries.
- [x] Run focused utilities; expect PASS including previous export guards.

### Task 4: Demo export and verification
**Files:** rule_packages/demo_tables.py; Demo regression tests; integration ledger.
**Interfaces:** complete Task 1 configuration; existing public three-table protocol unchanged.
- [x] Write failing Demo/native parity tests for copper truth table, multiple conditions/sources, chains, manual no, ordering and explicit unsupported constraints. Run focused pytest and observe RED.
- [x] Lower conjunctions, gather fields and retain explicit unsupported-case errors.
- [x] Run full API pytest, UI npm test, npm run build and git diff --check; record exact results.
- [x] Independent review; fix consequential findings with regression tests. Verify editor in disposable context; preserve active user DB/page.

## Completion evidence — 2026-10-27

Implementation and defect audit completed locally. See `outputs/rule-editor-integration-20261027/audit-report.md` and `progress.md` for regression evidence, exact suite totals, archive verification and limitations. No commit, reset or production publication performed.
