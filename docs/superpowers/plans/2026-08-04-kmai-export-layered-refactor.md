# KmAI Export Layered Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the KmAI V1 compatibility exporter into focused backend modules while preserving every exported JSON field, ordering rule, error code, and public facade import.

**Architecture:** Keep `build_kmai_compatibility_export()` in `kmai_export.py` as the only assembly entry point. Move factor/mapping generation to `kmai_export_factors.py`, condition translation and budget accounting to `kmai_export_conditions.py`, and route catalog/rule generation to `kmai_export_routes.py`. The facade passes the per-export factor registry, warnings/errors, limits, and condition callbacks explicitly so no module depends on router or database state.

**Tech Stack:** Python 3.11+, FastAPI service modules, Pydantic 2 contracts, pytest, SQLAlchemy models only through existing callers.

## Global Constraints

- Keep the current `build_kmai_compatibility_export()` signature and return type.
- Keep `factor_schema.json`, `factor_expansion_rules.json`, `route_catalog.json`, and `route_rules.json` top-level shapes and semantics unchanged.
- Keep KmAI V1 factor IDs, factor keys, condition operators, rule ordering, and dynamic-factor allocation deterministic.
- Preserve all current compatibility issue codes, messages, paths, warning/error ordering, and limit short-circuit behavior.
- Do not change the database schema, HTTP routes, V2 contracts, KmAI protocol, frontend source, or runtime dependencies.
- Do not modify unrelated untracked user plans/specs, runtime data, uploads, or build output.
- Do not create a Git commit unless the user explicitly requests it; report diffs and test evidence at each checkpoint instead.

---

## File Map

**Create:**

- `process-plan-agent-api/app/services/rule_packages/kmai_export_context.py`: per-export factor registry, condition budget, and structured artifact result contracts.
- `process-plan-agent-api/app/services/rule_packages/kmai_export_factors.py`: standard factor metadata, legacy mapping snapshots, dynamic factor registration, factor schema, factor expansion rules.
- `process-plan-agent-api/app/services/rule_packages/kmai_export_conditions.py`: V2 condition-to-KmAI translation, DNF expansion, size estimation, and limit configuration.
- `process-plan-agent-api/app/services/rule_packages/kmai_export_routes.py`: route catalog and route-rule artifact builders.
- `process-plan-agent-api/tests/test_kmai_export_context.py`: focused export-state contract tests.
- `process-plan-agent-api/tests/test_kmai_export_factors.py`: focused factor artifact tests.
- `process-plan-agent-api/tests/test_kmai_export_conditions.py`: focused condition budget and expansion tests.
- `process-plan-agent-api/tests/test_kmai_export_routes.py`: focused route artifact tests.

**Modify:**

- `process-plan-agent-api/app/services/rule_packages/kmai_export.py`: retain public facade, compatibility re-exports, context assembly, and final cross-artifact factor-reference validation.
- `process-plan-agent-api/tests/test_kmai_rule_package_export.py`: update only private patch targets if the moved condition function requires it; retain all protocol assertions.

## Task 1: Freeze the Facade Contract and Characterize Factor Boundaries

**Files:**
- Modify: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`
- Create: `process-plan-agent-api/tests/test_kmai_export_context.py`
- Create: `process-plan-agent-api/tests/test_kmai_export_factors.py`
- Test fixture: `process-plan-agent-api/tests/conftest.py` and `process-plan-agent-api/tests/fixtures/rule_package_v2.json`

**Interfaces:**
- Consumes: `RulePackageV2` fixture and the existing facade output.
- Produces: a stable full-export SHA-256 characterization plus failing tests that define `FactorRegistry`, `build_factor_schema(package, registry)`, and `build_factor_expansion_rules(package)` as the new boundaries.

- [ ] **Step 1: Add and pass the current facade characterization**

Add to `test_kmai_rule_package_export.py`:

```python
import hashlib
import json


def test_kmai_export_fixture_contract_signature(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)
    payload = {
        "valid": exported.valid,
        "target_directory": exported.target_directory,
        "errors": [item.model_dump(mode="json") for item in exported.errors],
        "warnings": [item.model_dump(mode="json") for item in exported.warnings],
        "files": exported.files,
        "factor_catalog_version": exported.factor_catalog_version,
    }
    encoded = json.dumps(
        payload,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    assert hashlib.sha256(encoded).hexdigest() == (
        "d15479cd1a7e7ae8463c442b8240dc7252a7ead64f8166ac0e176c63b8244603"
    )
```

Run:

```text
py -3 -m pytest -q tests/test_kmai_rule_package_export.py::test_kmai_export_fixture_contract_signature
```

Expected: PASS against the pre-refactor implementation.

- [ ] **Step 2: Write the failing context and factor tests**

In `test_kmai_export_context.py`:

```python
from app.services.rule_packages.kmai_export_context import FactorRegistry


def test_factor_registry_preserves_registration_order_and_existing_payload():
    registry = FactorRegistry()
    first = registry.register("manual_a", {"factor_key": "manual_a", "factor_id": "F900"})
    repeated = registry.register("manual_a", {"factor_key": "manual_a", "factor_id": "F999"})
    registry.register("manual_b", {"factor_key": "manual_b", "factor_id": "F901"})

    assert repeated is first
    assert [item["factor_key"] for item in registry.values()] == ["manual_a", "manual_b"]
    assert registry.get("manual_a")["factor_id"] == "F900"
```

In `test_kmai_export_factors.py`:

```python
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_export_context import FactorRegistry
from app.services.rule_packages.kmai_export_factors import (
    build_factor_expansion_rules,
    build_factor_schema,
    dynamic_factor,
)


def test_factor_artifacts_match_facade(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)
    registry = FactorRegistry()
    dynamic_factor(rule_package_v2, "mechanical.hardness_hrc", registry)

    assert build_factor_schema(rule_package_v2, registry) == exported.files["factor_schema.json"]
    assert build_factor_expansion_rules(rule_package_v2) == exported.files["factor_expansion_rules.json"]


def test_factor_schema_appends_dynamic_factors_in_registration_order(rule_package_v2):
    registry = FactorRegistry()
    registry.register("manual_a", {"factor_key": "manual_a", "factor_id": "F900"})
    registry.register("manual_b", {"factor_key": "manual_b", "factor_id": "F901"})
    factors = build_factor_schema(rule_package_v2, registry)["factors"]
    assert [item["factor_key"] for item in factors[-2:]] == ["manual_a", "manual_b"]
```

- [ ] **Step 3: Run the new boundary tests and verify they fail**

Run from `process-plan-agent-api`:

```text
py -3 -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_factors.py
```

Expected: collection fails because the context and factor modules do not exist yet.

## Task 2: Add Export Context and Extract Factor Builders

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_export_context.py`
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_export_factors.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Test: `process-plan-agent-api/tests/test_kmai_export_context.py`
- Test: `process-plan-agent-api/tests/test_kmai_export_factors.py`

**Interfaces:**
- Consumes: `RulePackageV2`, `ConditionNode`, `LegacyFactorAdapterEntry`, and the existing standard-factor catalog helpers.
- Produces: `FactorRegistry`, `ArtifactBuildResult`, `build_factor_schema(package, registry) -> dict[str, Any]`, `build_factor_expansion_rules(package) -> dict[str, Any]`, `dynamic_factor(package, field_key, registry) -> str`, `dynamic_special_requirement_factor(value, registry) -> str`, `mapped_manual_factor(snapshot, registry) -> str`, `legacy_adapter_key(source_field, source_value) -> tuple[str, str]`, `builtin_legacy_mapping_snapshot() -> list[LegacyFactorAdapterEntry]`, and `legacy_mapping_snapshot_from_validation_report(raw_json) -> list[LegacyFactorAdapterEntry]`.

- [ ] **Step 1: Implement the internal context contracts**

Create `FactorRegistry` with an insertion-ordered private dictionary and these exact methods:

```python
@dataclass
class FactorRegistry:
    _items: dict[str, dict[str, Any]] = field(default_factory=dict)

    def __len__(self) -> int:
        return len(self._items)

    def __contains__(self, factor_key: str) -> bool:
        return factor_key in self._items

    def get(self, factor_key: str) -> dict[str, Any] | None:
        return self._items.get(factor_key)

    def register(self, factor_key: str, payload: dict[str, Any]) -> dict[str, Any]:
        if factor_key not in self._items:
            self._items[factor_key] = payload
        return self._items[factor_key]

    def update(self, factor_key: str, **changes: Any) -> None:
        self._items[factor_key].update(changes)

    def values(self) -> list[dict[str, Any]]:
        return list(self._items.values())
```

`register()` must return the existing payload without replacing it when the key already exists. Also create:

```python
@dataclass
class ArtifactBuildResult:
    payload: dict[str, Any]
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
```

- [ ] **Step 2: Move the factor constants and mapping dataclass**

Move `_FACTOR_SPECS`, `_BUILTIN_LEGACY_VALUE_FACTORS`, `LegacyFactorAdapterEntry`, normalization, snapshot loading, and built-in adapter construction without changing literal values or sort order. Keep the facade imports:

```python
from app.services.rule_packages.kmai_export_factors import (
    LegacyFactorAdapterEntry,
    builtin_legacy_mapping_snapshot,
    legacy_mapping_snapshot_from_validation_report,
)
```

- [ ] **Step 3: Move dynamic registration and factor artifacts**

Move `_field_options`, `_walk_condition_values`, `_material_options`, `_factor_schema`, `_set_factor_rule`, `_cad_condition`, `_factor_expansion_rules`, `_dynamic_factor`, `_dynamic_special_requirement_factor`, and `_mapped_manual_factor`. Rename only the module-local leading underscore where the interface above requires a direct focused test. Replace direct dictionary access with `FactorRegistry` methods while preserving registration order and the existing `F900 + len(registry)` allocation formula.

- [ ] **Step 4: Re-export existing imports from the facade**

The facade must continue to expose the symbols used by `lifecycle.py`, `archive.py`, `kmai_compatibility_runner.py`, and existing tests. Do not duplicate implementations in the facade.

- [ ] **Step 5: Run focused and existing exporter tests**

```text
py -3 -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_factors.py tests/test_kmai_rule_package_export.py tests/test_rule_package_archive.py tests/test_rule_package_lifecycle.py
```

Expected: all selected tests pass and factor/expansion JSON remains byte-for-byte equivalent after JSON serialization.

## Task 3: Characterize Condition Compiler Boundaries

**Files:**
- Create: `process-plan-agent-api/tests/test_kmai_export_conditions.py`
- Test fixture: `process-plan-agent-api/tests/conftest.py`

**Interfaces:**
- Consumes: `ConditionNode` values from the existing fixture and the current limit environment variables.
- Produces: failing tests defining `condition_dnf(package, node, registry, warnings, path, legacy_adapters)`, `condition_expansion_size(node)`, `configured_max_combinations()`, and `configured_max_condition_objects()`.

- [ ] **Step 1: Write limit and DNF tests**

```python
from app.services.rule_packages.contracts import ConditionNode
from app.services.rule_packages.kmai_export_context import FactorRegistry
from app.services.rule_packages.kmai_export_conditions import (
    condition_dnf,
    condition_expansion_size,
)


def _two_by_two_condition() -> ConditionNode:
    leaf = lambda value: {
        "field": "material.grade",
        "op": "eq",
        "value": value,
        "factor_id": "material.grade",
    }
    return ConditionNode.model_validate({
        "all": [
            {"any": [leaf("A"), leaf("B")]},
            {"any": [leaf("C"), leaf("D")]},
        ]
    })


def test_condition_expansion_size_matches_two_by_two_dnf():
    node = _two_by_two_condition()
    assert condition_expansion_size(node) == (4, 8)


def test_condition_dnf_materializes_the_estimated_clauses(rule_package_v2):
    node = _two_by_two_condition()
    clauses = condition_dnf(
        rule_package_v2,
        node,
        FactorRegistry(),
        [],
        "route_rules.rules[0].when",
        None,
    )
    assert len(clauses) == 4
    assert all(len(clause) == 2 for clause in clauses)
```

- [ ] **Step 2: Run the focused tests and verify they fail**

```text
py -3 -m pytest -q tests/test_kmai_export_conditions.py
```

Expected: collection fails because the new module does not exist yet. The existing exporter tests remain the behavior oracle for exact error text.

## Task 4: Extract Condition Translation and Budgets

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_export_conditions.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export_context.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Modify: `process-plan-agent-api/tests/test_kmai_rule_package_export.py` only if its patch target moves
- Test: `process-plan-agent-api/tests/test_kmai_export_conditions.py`

**Interfaces:**
- Consumes: `FactorRegistry`, factor functions from `kmai_export_factors.py`, `ConditionNode`, `RulePackageV2`, `ValidationIssue`, and `LegacyFactorAdapterEntry`.
- Produces: `ConditionBudget`, the four functions in Task 3, and `StandardFactorExportError` as a facade re-export.

- [ ] **Step 1: Add the condition budget contract**

Extend `kmai_export_context.py` with:

```python
@dataclass
class ConditionBudget:
    max_combinations: int
    max_condition_objects: int
    generated_combinations: int = 0
    generated_condition_objects: int = 0

    def project(self, combinations: int, condition_objects: int) -> tuple[int, int]:
        return (
            self.generated_combinations + combinations,
            self.generated_condition_objects + condition_objects,
        )

    def record(self, clauses: list[list[dict[str, Any]]]) -> None:
        self.generated_combinations += len(clauses)
        self.generated_condition_objects += sum(len(clause) for clause in clauses)
```

Add a focused test proving `project()` does not mutate counters and `record()` uses the actual materialized clause sizes.

```python
from app.services.rule_packages.kmai_export_context import ConditionBudget


def test_condition_budget_projects_without_mutation_and_records_actual_clauses():
    budget = ConditionBudget(max_combinations=10, max_condition_objects=20)

    assert budget.project(4, 8) == (4, 8)
    assert (budget.generated_combinations, budget.generated_condition_objects) == (0, 0)

    budget.record([[{"factor_key": "a"}], [{"factor_key": "b"}, {"factor_key": "c"}]])
    assert budget.project(1, 1) == (3, 4)
```

- [ ] **Step 2: Move operator and condition helpers unchanged**

Move `_OPERATOR_MAP`, `_manual_process_condition`, `_fixed_leaf_condition`, `_leaf_condition`, `_condition_dnf`, `_condition_expansion_size`, `_configured_max_combinations`, and `_configured_max_condition_objects`. Keep the recursive paths (`.all[index]`, `.any[index]`) and the exact unsupported-condition message.

- [ ] **Step 3: Preserve dynamic factor side effects explicitly**

Keep `FactorRegistry`, `warnings`, and `legacy_adapters` as explicit function arguments. The condition module may register a dynamic factor only when the current implementation does so; it must not create factors while a limit check has rejected a rule.

- [ ] **Step 4: Keep the existing private facade patch hook**

In `kmai_export.py`, alias the moved function as `_condition_dnf`. The route builder introduced in Task 5 will accept a `condition_dnf_fn` callback, and the facade will pass this alias so the existing “reject before materializing” test remains valid when it patches `app.services.rule_packages.kmai_export._condition_dnf`.

- [ ] **Step 5: Run context, condition, and exporter tests**

```text
py -3 -m pytest -q tests/test_kmai_export_context.py tests/test_kmai_export_conditions.py tests/test_kmai_rule_package_export.py
```

Expected: all tests pass; the oversized-DNF test proves the materializing function is not called.

## Task 5: Characterize Route Artifact Boundaries

**Files:**
- Create: `process-plan-agent-api/tests/test_kmai_export_routes.py`
- Test fixture: `process-plan-agent-api/tests/conftest.py`

**Interfaces:**
- Consumes: `RulePackageV2`, a process-key map, `FactorRegistry`, `ConditionBudget`, optional legacy adapters, and condition callbacks.
- Produces: failing tests defining `build_route_catalog(package)` and `build_route_rules(package, process_keys, registry, budget, legacy_adapters, *, condition_dnf_fn, condition_expansion_size_fn) -> ArtifactBuildResult`.

- [ ] **Step 1: Write route artifact equivalence tests**

```python
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.kmai_export_context import ConditionBudget, FactorRegistry
from app.services.rule_packages.kmai_export_routes import (
    build_route_catalog,
    build_route_rules,
)


def test_route_catalog_matches_facade(rule_package_v2):
    exported = build_kmai_compatibility_export(rule_package_v2)
    catalog, process_keys = build_route_catalog(rule_package_v2)
    assert catalog == exported.files["route_catalog.json"]
    assert process_keys == {item.process_id: item.process_id for item in rule_package_v2.route_catalog.processes}


def test_route_rules_missing_process_is_reported(rule_package_v2):
    package = rule_package_v2.model_copy(deep=True)
    package.route_rules.rules[0].then.include_process_ids = ["missing-process"]
    _, process_keys = build_route_catalog(package)
    result = build_route_rules(
        package,
        process_keys,
        FactorRegistry(),
        ConditionBudget(max_combinations=10000, max_condition_objects=100000),
        None,
        condition_dnf_fn=lambda *args: [[]],
        condition_expansion_size_fn=lambda node: (1, 1),
    )
    assert result.payload["rules"] == []
    assert result.errors[0].code == "kmai_process_reference_missing"
```

- [ ] **Step 2: Run the focused tests and verify they fail**

```text
py -3 -m pytest -q tests/test_kmai_export_routes.py
```

Expected: collection fails because `kmai_export_routes` does not exist yet.

## Task 6: Extract Route Catalog and Rule Builders

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_export_routes.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Test: `process-plan-agent-api/tests/test_kmai_export_routes.py`

**Interfaces:**
- Consumes: `FactorRegistry`, `ConditionBudget`, `ArtifactBuildResult`, factor registration functions, condition callbacks, and the existing `RulePackageV2`/issue models.
- Produces: `build_route_catalog(package) -> tuple[dict[str, Any], dict[str, str]]` and `build_route_rules(package, process_keys, registry, budget, legacy_adapters, *, condition_dnf_fn, condition_expansion_size_fn) -> ArtifactBuildResult`.

- [ ] **Step 1: Move route catalog helpers**

Move `_process_stage`, `_fallback_steps`, and `_route_catalog` without changing token lists, fallback splitting, relation aggregation, sequential process IDs beginning with `P001`, or list ordering. Rename the public-in-module function to `build_route_catalog`.

- [ ] **Step 2: Move route rule generation**

Move `_route_rules` to `build_route_rules`. Replace direct calls to `_condition_expansion_size` and `_condition_dnf` with the two injected callbacks, use `ConditionBudget.project()`/`record()`, and return local errors/warnings through `ArtifactBuildResult`. Preserve the order of: size check, combination limit check, condition-object limit check, DNF materialization, process-reference validation, and clause emission.

- [ ] **Step 3: Run focused and compatibility tests**

```text
py -3 -m pytest -q tests/test_kmai_export_routes.py tests/test_kmai_export_conditions.py tests/test_kmai_rule_package_export.py
```

Expected: route JSON, generated rule IDs, missing-process errors, and limit behavior all pass unchanged.

## Task 7: Reassemble the Thin Facade

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Test: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`, `process-plan-agent-api/tests/test_rule_package_archive.py`, `process-plan-agent-api/tests/test_kmai_compatibility_runner.py`

**Interfaces:**
- Consumes: `FactorRegistry`, `ConditionBudget`, `ArtifactBuildResult`, `build_factor_schema`, `build_factor_expansion_rules`, `build_route_catalog`, `build_route_rules`, condition limit functions, and all compatibility re-exports.
- Produces: the unchanged `build_kmai_compatibility_export(package, *, legacy_mapping_snapshot=None, max_combinations=None, max_condition_objects=None) -> KmaiCompatibilityExport` facade.

- [ ] **Step 1: Replace deleted helper bodies with imports and aliases**

The facade imports the moved public-in-module functions and aliases the existing private test hook:

```python
from app.services.rule_packages.kmai_export_conditions import (
    StandardFactorExportError,
    condition_dnf as _condition_dnf,
    condition_expansion_size as _condition_expansion_size,
    configured_max_combinations as _configured_max_combinations,
    configured_max_condition_objects as _configured_max_condition_objects,
)
```

It re-exports `LegacyFactorAdapterEntry`, `builtin_legacy_mapping_snapshot`, and `legacy_mapping_snapshot_from_validation_report` from the factors module.

- [ ] **Step 2: Keep the existing build order**

Implement the facade in this order: create `FactorRegistry`; normalize the optional legacy snapshot; resolve positive limits and create `ConditionBudget`; call `build_route_catalog`; call `build_route_rules` with `_condition_dnf` and `_condition_expansion_size`; copy its structured errors/warnings into the final result; call `build_factor_schema`; call `build_factor_expansion_rules`; validate every emitted route-rule factor key against the factor schema; assemble `KmaiCompatibilityExport`.

- [ ] **Step 3: Re-run the complete facade contract signature**

Run the SHA-256 characterization added in Task 1. Its payload covers the complete `files`, `errors`, `warnings`, `valid`, `target_directory`, and `factor_catalog_version`; the expected digest must remain `d15479cd1a7e7ae8463c442b8240dc7252a7ead64f8166ac0e176c63b8244603`.

- [ ] **Step 4: Run all rule-package tests**

```text
py -3 -m pytest -q tests/test_kmai_rule_package_export.py tests/test_kmai_export_context.py tests/test_kmai_export_factors.py tests/test_kmai_export_conditions.py tests/test_kmai_export_routes.py tests/test_rule_package_archive.py tests/test_kmai_compatibility_runner.py tests/test_rule_package_api.py tests/test_rule_package_execution.py tests/test_rule_package_lifecycle.py
```

Expected: all selected tests pass with no changed JSON snapshots or issue semantics.

## Task 8: Remove Dead Code and Verify the Repository

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py` and any focused test files from Tasks 1-7 only.

**Interfaces:**
- Consumes: the completed module split and focused tests.
- Produces: a small facade with no duplicate artifact-builder implementation and a clean, intentional diff.

- [ ] **Step 1: Scan for stale definitions and imports**

Run:

```text
rg -n "def _factor_schema|def _factor_expansion_rules|def _route_catalog|def _route_rules|def _condition_dnf|def _condition_expansion_size" process-plan-agent-api/app/services/rule_packages
```

Expected: each moved implementation appears only in its responsibility module; the facade contains aliases only where compatibility requires them.

- [ ] **Step 2: Run backend verification**

From `process-plan-agent-api`:

```text
py -3 -m pytest -q
```

Expected: the existing baseline remains `247 passed, 1 skipped` or a higher count with all tests passing.

- [ ] **Step 3: Run frontend regression verification**

From `process-plan-agent-ui`:

```text
npm.cmd test -- --run
npm.cmd run build
```

Expected: all Vitest files pass and `vue-tsc`/Vite production build succeeds. No frontend files should be changed.

- [ ] **Step 4: Run diff and status checks**

From the repository root:

```text
git diff --check
git status --short
```

Expected: no whitespace errors; only the intentional backend modules/tests and the approved design/plan docs are present. Existing user-authored untracked files remain untouched.

## Handoff

This plan is saved at `docs/superpowers/plans/2026-08-04-kmai-export-layered-refactor.md`. Execute it inline with `superpowers:executing-plans`; do not create commits unless the user separately authorizes Git history changes.
