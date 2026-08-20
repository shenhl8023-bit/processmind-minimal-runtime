# KmAI Export Layered Refactor Design

Date: 2026-08-04

## Context

`app/services/rule_packages/kmai_export.py` is the only public entry point for
building the KmAI V1 compatibility files, but it currently contains several
independent responsibilities:

- the immutable standard-factor catalog and legacy mapping snapshot;
- dynamic/manual factor registration and factor schema generation;
- condition translation, DNF expansion, and expansion budgets;
- ProcessMind route-catalog conversion;
- factor-expansion and route-rule artifact generation;
- final error aggregation and export assembly.

The current implementation is covered by compatibility, archive, and runtime
tests. The goal is to improve boundaries without changing any exported JSON,
error code, ordering, or public import used by the rest of the application.

## Goals

1. Split the exporter into cohesive, independently testable modules.
2. Make the data passed between stages explicit instead of relying on several
   loosely coordinated mutable dictionaries.
3. Preserve `build_kmai_compatibility_export()` as the single public builder.
4. Preserve the four required KmAI V1 files, their top-level shape, field
   semantics, deterministic ordering, and all existing validation/error codes.
5. Keep combination and condition-object limits enforced before materializing
   an oversized DNF result.

## Non-goals

- No database schema or migration changes.
- No HTTP route, request, or response changes.
- No changes to ProcessMind V2 contracts or the KmAI V1 protocol.
- No changes to the condition language or rule-selection semantics.
- No new runtime dependency.

## Proposed Structure

### `kmai_export.py` (facade)

Retain the current public function and public compatibility symbols imported by
other modules. The facade will:

1. create a per-call export context;
2. invoke the artifact builders in the existing deterministic order;
3. collect artifact results, factor metadata, and compatibility issues;
4. return the existing `KmaiCompatibilityExport` model.

Private helpers that move to another module will be re-exported only when an
existing application module or focused test relies on that symbol. No new
public API is introduced.

### `kmai_export_factors.py`

Owns the immutable standard-factor specifications, legacy mapping entries,
mapping snapshot loading, dynamic/manual factor registration, and generation of
`factor_schema.json` plus `factor_expansion_rules.json`.

The module exposes small functions that receive the package and an explicit
factor registry. It does not read the database, environment, or request state.

### `kmai_export_conditions.py`

Owns conversion of a V2 `ConditionNode` into KmAI leaf conditions, manual-factor
handling, DNF expansion, expansion-size estimation, and environment/default
limit resolution.

The condition API returns structured results and issues. It must retain the
current short-circuit behavior: an expansion-limit violation is reported before
calling the materializing DNF expansion function, and the cumulative condition
object budget is checked across rules.

### `kmai_export_routes.py`

Owns ProcessMind phase-to-stage conversion, fallback step splitting, route
catalog conversion, and route-rule artifact generation. It receives the
condition compiler and factor registry through explicit parameters rather than
importing facade internals.

### Internal context and result contracts

Use a small internal context/result contract for one export call:

- `FactorRegistry`: deterministic allocation of dynamic factor keys and IDs;
- `ConditionBudget`: configured combination/object limits and cumulative object
  count;
- artifact-builder results containing the JSON payload and issues.

These contracts are internal implementation details. They make stage ordering
and state ownership explicit while leaving the external Pydantic model intact.

## Data Flow

```text
RulePackageV2
    |
    v
facade creates context
    |
    +--> factors: factor schema + factor expansion rules
    |
    +--> routes: route catalog + process-key map
    |
    +--> routes/rules use conditions + factor registry
    |
    v
merge four artifacts, mapping snapshot, metadata, and issues
    |
KmaiCompatibilityExport (unchanged contract)
```

The builder order remains stable so dynamic factor IDs and JSON list ordering
remain stable. Every artifact builder is pure with respect to the database and
receives all required state through parameters.

## Compatibility and Error Handling

- `build_kmai_compatibility_export()` keeps its current signature and default
  limits.
- `LegacyFactorAdapterEntry`, `StandardFactorExportError`,
  `builtin_legacy_mapping_snapshot()`, and other currently imported symbols
  remain available from `kmai_export` as compatibility imports.
- Existing issue codes, messages, paths, severity, and ordering are preserved.
- Unsupported conditions, unmapped standard factors, combination overflow, and
  condition-object overflow continue to produce an invalid export rather than a
  partially valid export.
- No module raises `HTTPException`; HTTP mapping remains in the router/service
  boundary.

## Test Plan

### Characterization and regression tests

- Keep existing `test_kmai_rule_package_export.py` assertions for exact factor,
  route, and rule payloads.
- Add a facade regression that compares the complete four-file export and
  metadata with the pre-refactor behavior for the fixture package.
- Keep tests for standard-factor binding, legacy snapshots, manual overrides,
  optional metadata, unsupported `not`, combination limits, and cumulative
  condition-object limits.

### Focused module tests

- Factor registry allocation is deterministic and does not reuse IDs for
  distinct factors.
- Condition budget rejects oversized expressions before DNF materialization.
- Route conversion preserves process relations, fallback steps, and ordering.

### Verification commands

```text
py -3 -m pytest -q
npm.cmd test -- --run
npm.cmd run build
git diff --check
```

The frontend commands are regression checks only; no frontend source is in
scope for this refactor.

## Implementation Constraints

Implement in small extraction steps, running focused backend tests after each
step. Do not edit existing user-authored untracked plans or specs. Do not
create a Git commit unless the user explicitly requests it.

## Completion Criteria

The refactor is complete when:

1. `kmai_export.py` is a thin facade and the three responsibility modules have
   clear, acyclic dependencies.
2. Existing and new focused tests pass without changing expected JSON or issue
   semantics.
3. Full backend tests, frontend tests/build, and whitespace checks pass.
4. `git status` shows only intentional source/test/spec changes and no runtime
   data or build artifacts.
