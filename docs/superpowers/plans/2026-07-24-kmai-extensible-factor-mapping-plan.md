# KmAI Extensible Factor Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a product-level, auditable ProcessMind-to-KmAI factor mapping system with project overrides, global mappings, manual factors, fourth-step resolution, and authoritative historical export snapshots.

**Architecture:** Keep the synchronous KmAI exporter pure by passing it an already-loaded mapping context. Store project/global mappings, revisions, audit events, and published-package usage snapshots in SQLite. Resolve mappings with `project > global > builtin` precedence; bind known values to existing factors and represent genuinely new values as server-generated manual boolean factors. The fourth-step UI resolves structured compatibility errors, while model settings provides the long-term management surface.

**Tech Stack:** FastAPI, Pydantic, SQLAlchemy async sessions, SQLite schema maintenance, Vue 3, TypeScript, Element Plus, Vitest, pytest, browser ZIP generation.

## Global Constraints

- Mapping precedence is exactly `project > global > builtin`.
- Version 1 supports binding existing KmAI factors and creating manual boolean factors; it does not expose a CAD filter-rule editor.
- Manual factors use `source_mode=manual_override`, default to `false`, and must be documented as `manual.factor_overrides` inputs.
- Existing `special.requirements` automatic manual-factor behavior remains compatible when no persisted mapping overrides it.
- Unknown `cad.features` and `precision.grades` values remain export-blocking until explicitly mapped.
- Mapping source values are normalized with Unicode NFKC, whitespace collapse, and trim before lookup and uniqueness checks.
- Published packages are immutable and retain the mapping snapshot used to produce them.
- The server re-runs KmAI compatibility during package save and returns the authoritative KmAI files used for the ZIP; the browser must not package a stale compile response.
- System builtins are read-only; project mappings may be promoted to global only after conflict validation.
- Unrelated user changes already present in the worktree must not be reverted or included in feature commits. Use `git commit --only -m "..." -- <feature paths>` for every commit.
- Backend commands run from `process-plan-agent-api` with `python -m pytest`; frontend commands run from `process-plan-agent-ui` with `npm test` and `npm run build`.

## File Structure

Create the following focused units:

- `process-plan-agent-api/app/services/rule_packages/kmai_mapping_contracts.py`: API request/response models and mapping snapshot types.
- `process-plan-agent-api/app/services/rule_packages/kmai_mapping_registry.py`: builtin catalog, normalization, effective-scope resolution, stable manual-factor keys, and mapping snapshots.
- `process-plan-agent-api/app/services/rule_packages/kmai_mapping_store.py`: async CRUD, batch writes, audit events, usage snapshots, and deletion protection.
- `process-plan-agent-api/app/routers/kmai_factor_mappings.py`: mapping catalog, list, preview, create/batch, update, promote, and delete routes.
- `process-plan-agent-api/tests/test_kmai_mapping_registry.py`: pure registry behavior.
- `process-plan-agent-api/tests/test_kmai_factor_mapping_api.py`: isolated FastAPI and database behavior.
- `process-plan-agent-ui/src/api/kmaiFactorMappings.ts`: typed mapping API client.
- `process-plan-agent-ui/src/utils/kmaiFactorMappings.ts`: pure frontend grouping, draft validation, and request construction.
- `process-plan-agent-ui/src/utils/kmaiFactorMappings.spec.ts`: frontend unit tests.
- `process-plan-agent-ui/src/components/kmai/KmaiMappingResolutionDialog.vue`: fourth-step batch resolver.
- `process-plan-agent-ui/src/components/kmai/KmaiMappingManagerDialog.vue`: model-settings mapping manager.

Modify the existing exporter, compatibility contracts, lifecycle, routers, models, schema maintenance, project deletion, finalization composable/view, model settings drawer, app shell, API barrel, README, and standalone compatibility test only where listed below.

---

### Task 1: Add persistent mapping tables and contracts

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_contracts.py`
- Modify: `process-plan-agent-api/app/models/models.py` after `FinalizedRulePackage`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py` inside `ensure_project_schema`
- Modify: `process-plan-agent-api/app/routers/projects.py` in `delete_project`
- Test: `process-plan-agent-api/tests/test_kmai_mapping_schema.py`
- Modify: `process-plan-agent-api/tests/test_db_startup_safety.py`

**Interfaces:**
- Produces `KmaiMappingScope`, `KmaiMappingMode`, `KmaiMappingSnapshot`, `KmaiFactorCatalogItem`, `KmaiMappingCreateRequest`, `KmaiMappingBatchRequest`, `KmaiMappingUpdateRequest`, `KmaiMappingOut`, `KmaiMappingPreviewRequest`, and `KmaiMappingPreviewResponse` for later tasks.
- Produces ORM rows `KmaiFactorMapping`, `KmaiFactorMappingEvent`, and `KmaiFactorMappingUsage` used by the registry and store.

- [ ] **Step 1: Write the schema failure test**

Add a temporary SQLite test that runs `Base.metadata.create_all()` and `ensure_project_schema()` twice, then asserts the three mapping tables, the global/project partial unique indexes, and the foreign keys exist. Insert two projects and prove the same `(source_field, source_value)` is allowed once globally and once per project, but duplicate project rows fail with `IntegrityError`.

The test must also insert a mapping event and usage snapshot, delete the referenced package, and assert the usage is cascaded while the audit event remains queryable with its `before_json` and `after_json` snapshots.

- [ ] **Step 2: Run the schema test and confirm it fails**

Run from `process-plan-agent-api`:

```powershell
python -m pytest tests/test_kmai_mapping_schema.py -q
```

Expected: FAIL because the ORM classes and tables do not exist.

- [ ] **Step 3: Add the mapping contract models**

Create the contract module with strict literal values and explicit fields. The central snapshot must have this shape:

```python
class KmaiMappingSnapshot(StrictModel):
    mapping_id: int | None = None
    mapping_identity: str
    revision: int = 1
    scope: Literal["builtin", "global", "project"]
    project_id: int | None = None
    source_field: str
    source_value: str
    mapping_mode: Literal["existing_factor", "manual_factor"]
    target_factor_key: str
    target_factor_name: str
    target_factor_category: str
```

`KmaiMappingCreateRequest` must accept `scope`, optional `project_id`, `source_field`, `source_value`, `mapping_mode`, optional `target_factor_key`, optional `target_factor_name`, and `actor`, but must never accept a client-supplied generated key for `manual_factor`.

- [ ] **Step 4: Add ORM models and relationships**

Add columns for scope, nullable project ID, normalized source field/value, mapping mode, target factor metadata, status, revision, actor fields, timestamps, and optional `promoted_from_id`. Add `Project.kmai_factor_mappings`, `FinalizedRulePackage.kmai_mapping_usages`, and audit/usage relationships.

Use `ondelete="CASCADE"` for project-owned mapping rows and package usages. Use `ondelete="SET NULL"` for audit-event mapping IDs so historical events survive deletion. Use `ondelete="RESTRICT"` for usage mapping IDs so the store can enforce “in use means deactivate, do not delete.”

- [ ] **Step 5: Add idempotent SQLite DDL and indexes**

Inside `ensure_project_schema`, create these tables and constraints:

```sql
CREATE TABLE IF NOT EXISTS kmai_factor_mappings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    scope VARCHAR(16) NOT NULL CHECK (scope IN ('global', 'project')),
    project_id INTEGER,
    source_field VARCHAR(120) NOT NULL,
    source_value VARCHAR(255) NOT NULL,
    mapping_mode VARCHAR(24) NOT NULL CHECK (mapping_mode IN ('existing_factor', 'manual_factor')),
    target_factor_key VARCHAR(120) NOT NULL,
    target_factor_name VARCHAR(255) NOT NULL,
    target_factor_category VARCHAR(120) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'inactive')),
    revision INTEGER NOT NULL DEFAULT 1,
    promoted_from_id INTEGER,
    created_by VARCHAR(100) NOT NULL DEFAULT '默认用户',
    updated_by VARCHAR(100) NOT NULL DEFAULT '默认用户',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY(project_id) REFERENCES projects(id) ON DELETE CASCADE,
    FOREIGN KEY(promoted_from_id) REFERENCES kmai_factor_mappings(id) ON DELETE SET NULL,
    CHECK ((scope = 'global' AND project_id IS NULL) OR (scope = 'project' AND project_id IS NOT NULL))
);
```

Create `kmai_factor_mapping_events` and `kmai_factor_mapping_usages` with the fields from the approved design, then create partial unique indexes for global and project source pairs and indexes on project, status, package, and mapping IDs. Keep the migration idempotent on repeated startup.

- [ ] **Step 6: Extend explicit project deletion**

Before deleting a project in `app/routers/projects.py`, load and delete its mapping rows and mapping events/usages in the same session, or rely on the new cascading FKs only after confirming SQLite foreign keys are enabled in this path. The test must prove no project-scoped mapping survives deletion and no global mapping is removed.

- [ ] **Step 7: Run schema and startup tests**

```powershell
python -m pytest tests/test_kmai_mapping_schema.py tests/test_db_startup_safety.py -q
```

Expected: PASS, including the second idempotent `ensure_project_schema()` call.

- [ ] **Step 8: Commit only Task 1 files**

```powershell
git add process-plan-agent-api/app/models/models.py process-plan-agent-api/app/services/db_schema_maintenance.py process-plan-agent-api/app/services/rule_packages/kmai_mapping_contracts.py process-plan-agent-api/app/routers/projects.py process-plan-agent-api/tests/test_kmai_mapping_schema.py process-plan-agent-api/tests/test_db_startup_safety.py
git commit --only -m "feat: add KmAI mapping persistence schema" -- process-plan-agent-api/app/models/models.py process-plan-agent-api/app/services/db_schema_maintenance.py process-plan-agent-api/app/services/rule_packages/kmai_mapping_contracts.py process-plan-agent-api/app/routers/projects.py process-plan-agent-api/tests/test_kmai_mapping_schema.py process-plan-agent-api/tests/test_db_startup_safety.py
```

### Task 2: Implement the effective mapping registry

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_registry.py`
- Create: `process-plan-agent-api/tests/test_kmai_mapping_registry.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py` only to import builtin catalog constants after registry extraction

**Interfaces:**
- Consumes `AsyncSession` and the ORM mapping rows from Task 1.
- Produces `KmaiMappingRegistry`, `load_effective_mapping_registry(db, project_id)`, `builtin_mapping_registry()`, `normalize_mapping_value(value)`, and `manual_factor_key(source_field, source_value)`.
- `KmaiMappingRegistry.resolve(field, value)` returns a `KmaiMappingSnapshot | None` and `KmaiMappingRegistry.signature` returns a stable SHA-256 digest of sorted effective snapshots.

- [ ] **Step 1: Write registry behavior tests**

Cover these cases:

```python
def test_project_mapping_overrides_global_and_builtin(...):
    # same source pair resolves to project target first

def test_global_mapping_is_visible_to_other_projects(...):
    # global source pair resolves when project has no override

def test_inactive_mapping_falls_through_to_lower_scope(...):
    # inactive project row does not hide active global/builtin row

def test_manual_factor_key_is_stable_after_repeated_generation(...):
    # same normalized field/value always produces same key
```

Also assert NFKC and whitespace normalization, deterministic snapshots, and signature changes when a mapping revision or target factor changes.

- [ ] **Step 2: Run focused tests and confirm failure**

```powershell
python -m pytest tests/test_kmai_mapping_registry.py -q
```

Expected: FAIL because the registry module and functions do not exist.

- [ ] **Step 3: Extract immutable builtin catalog**

Move the current factor specifications and six builtin value mappings out of direct exporter lookup into the registry module. Preserve these exact builtin mappings:

```python
("cad.features", "扁位/平面") -> "has_flat_or_plane"
("cad.features", "槽类特征") -> "has_slot_feature"
("cad.features", "普通孔/辅助孔") -> "has_standard_or_aux_hole"
("cad.features", "铰孔/精孔") -> "has_reamed_or_precision_hole"
("cad.features", "型孔/割扁") -> "has_shaped_hole_or_cut_flat"
("cad.features", "顶尖孔") -> "uses_center_hole_location"
```

Expose the existing factor catalog for the API. Mark builtin snapshots read-only and use stable `builtin:<field>:<normalized-value>` identities.

- [ ] **Step 4: Implement normalization, scope merge, and manual-key generation**

Use `unicodedata.normalize("NFKC", value)`, collapse internal whitespace with a regular expression, and trim. Merge active mappings in builtin, global, project order so later records override earlier records. Generate manual keys as `processmind_manual_<sha256(field + "\\0" + value)[:12]>`.

For an unresolved `special.requirements` value with no persisted override, preserve the existing automatic dynamic-factor path. Do not silently auto-resolve unknown `cad.features` or `precision.grades` values.

- [ ] **Step 5: Run focused tests and commit**

```powershell
python -m pytest tests/test_kmai_mapping_registry.py -q
```

Expected: PASS.

```powershell
git add process-plan-agent-api/app/services/rule_packages/kmai_mapping_registry.py process-plan-agent-api/app/services/rule_packages/kmai_export.py process-plan-agent-api/tests/test_kmai_mapping_registry.py
git commit --only -m "feat: add scoped KmAI mapping registry" -- process-plan-agent-api/app/services/rule_packages/kmai_mapping_registry.py process-plan-agent-api/app/services/rule_packages/kmai_export.py process-plan-agent-api/tests/test_kmai_mapping_registry.py
```

### Task 3: Add mapping persistence service and management API

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_store.py`
- Create: `process-plan-agent-api/app/routers/kmai_factor_mappings.py`
- Modify: `process-plan-agent-api/app/main.py`
- Create: `process-plan-agent-api/tests/test_kmai_factor_mapping_api.py`

**Interfaces:**
- Store functions: `list_mappings`, `create_mapping`, `create_mapping_batch`, `update_mapping`, `promote_mapping`, `deactivate_or_delete_mapping`, `record_mapping_usage`, `list_mapping_usages`, and `load_registry_for_package`.
- Routes under `/api/kmai-factor-mappings`: `GET /catalog`, `GET /`, `POST /`, `POST /batch`, `PUT /{mapping_id}`, `POST /{mapping_id}/promote`, `DELETE /{mapping_id}`, and `POST /resolve-preview`.

- [ ] **Step 1: Write isolated API tests**

Build a temporary SQLite engine and FastAPI `get_db` override using the existing pattern in `test_rule_package_lifecycle.py`. Test:

1. Catalog includes builtin factor keys and marks builtin rows read-only.
2. A project manual mapping creates a server-generated stable factor key.
3. Batch creation is atomic: one invalid duplicate causes no item in the batch to persist.
4. Project list shows its own rows and effective global/builtin rows with `overridden` metadata.
5. `PUT` requires matching `expected_revision`; stale updates return `409`.
6. Promotion copies a project mapping to global and rejects an existing global conflict with `409`.
7. A mapping referenced by a usage row cannot be deleted and returns `409 kmai_mapping_in_use`; it can be deactivated.
8. `resolve-preview` scans a supplied V2 package and returns one aggregated issue per `(field, value)` with `occurrences` and `rule_refs`.

- [ ] **Step 2: Run API tests and confirm failure**

```powershell
python -m pytest tests/test_kmai_factor_mapping_api.py -q
```

Expected: FAIL because no router or store exists.

- [ ] **Step 3: Implement store validation and audit writes**

Normalize input before querying. Validate scope/project combinations, allowed source fields, existing factor keys, manual-factor display names, and duplicate source pairs. Generate manual target keys in the registry, increment `revision` on update, write one event per mutation, and flush all batch rows before committing once.

The batch operation must validate every item before adding any item to the session. It must return the effective snapshots after save so the frontend can immediately re-run preview.

- [ ] **Step 4: Implement the router and register it**

Use `Depends(get_db)` on every database route and `HTTPException(409, ...)` for revision, conflict, and usage errors. `resolve-preview` must receive the actual `RulePackageV2` payload and call the registry scanner; it must not trust client-supplied rule paths or occurrence counts.

Add `kmai_factor_mappings` to the import list in `app/main.py` and call `app.include_router(kmai_factor_mappings.router)`.

- [ ] **Step 5: Run API tests and commit**

```powershell
python -m pytest tests/test_kmai_factor_mapping_api.py -q
```

Expected: PASS.

```powershell
git add process-plan-agent-api/app/services/rule_packages/kmai_mapping_store.py process-plan-agent-api/app/routers/kmai_factor_mappings.py process-plan-agent-api/app/main.py process-plan-agent-api/tests/test_kmai_factor_mapping_api.py
git commit --only -m "feat: expose KmAI mapping management API" -- process-plan-agent-api/app/services/rule_packages/kmai_mapping_store.py process-plan-agent-api/app/routers/kmai_factor_mappings.py process-plan-agent-api/app/main.py process-plan-agent-api/tests/test_kmai_factor_mapping_api.py
```

### Task 4: Make the KmAI exporter consume mappings and return structured issues

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py` around `KmaiCompatibilityExport`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Modify: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`

**Interfaces:**
- `build_kmai_compatibility_export(package, mapping_registry=None)` remains synchronous and uses `builtin_mapping_registry()` when no registry is supplied.
- `KmaiCompatibilityIssue` extends the normal issue with optional `field`, `value`, `occurrences`, `rule_refs`, `suggested_existing_factors`, and `can_create_manual_factor`.
- `KmaiCompatibilityExport` adds `mapping_signature` and `mapping_usages` while preserving the existing four generated files.

- [ ] **Step 1: Add failing exporter tests**

Add tests for:

```python
def test_unmapped_cad_values_are_grouped_with_rule_refs(...):
    # repeated 孔类结构 appears once with occurrences=3

def test_existing_mapping_replaces_builtin_lookup(...):
    # registry maps 型孔 to an existing factor and route rule uses that key

def test_manual_mapping_adds_boolean_factor_and_usage_snapshot(...):
    # factor_schema contains source_mode=manual_override and route rule uses key
```

Keep the existing builtin, dynamic special requirement, relation, and combination-limit tests unchanged and assert their outputs remain the same.

- [ ] **Step 2: Run focused exporter tests and confirm failure**

```powershell
python -m pytest tests/test_kmai_rule_package_export.py -q
```

Expected: FAIL on the new registry-aware cases and structured issue fields.

- [ ] **Step 3: Add compatibility contracts**

Define `KmaiCompatibilityIssue` and `KmaiMappingUsageSnapshot` in `contracts.py`. Change only `KmaiCompatibilityExport.errors` and `.warnings` to the richer issue type so existing callers still receive `code`, `path`, and `message`.

- [ ] **Step 4: Add a mapping preflight and route conversion context**

Walk every `all`, `any`, and `not` condition and aggregate source references by normalized `(field, value)`. For unresolved `cad.features` and `precision.grades`, emit one structured issue per value and skip only rules that reference that unresolved value. Do not emit six duplicate generic `ValueError` messages.

Pass the same registry and usage accumulator through `_route_rules`, `_condition_dnf`, `_leaf_condition`, and manual-factor definition generation. Existing mappings use their target factor directly; manual mappings add a stable boolean definition and a `KmaiMappingUsageSnapshot`.

- [ ] **Step 5: Preserve the special-requirement compatibility path**

If `special.requirements` has no persisted mapping, continue calling the existing dynamic-factor generator and emit `kmai_manual_override_required`. If a persisted mapping exists, use that snapshot and do not generate a second factor for the same source value.

- [ ] **Step 6: Run exporter tests and commit**

```powershell
python -m pytest tests/test_kmai_rule_package_export.py -q
```

Expected: PASS, including all existing regression cases.

```powershell
git add process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/kmai_export.py process-plan-agent-api/tests/test_kmai_rule_package_export.py
git commit --only -m "feat: make KmAI export mapping-aware" -- process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/kmai_export.py process-plan-agent-api/tests/test_kmai_rule_package_export.py
```

### Task 5: Make compile, publish, and compatibility tests authoritative

**Files:**
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/lifecycle.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/finalized_rule_package_helpers.py`
- Modify: `process-plan-agent-api/tests/test_rule_package_api.py`
- Modify: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Modify: `process-plan-agent-api/tests/test_kmai_compatibility_runner.py`

**Interfaces:**
- Compile route receives `AsyncSession`, loads `load_effective_mapping_registry(db, package.manifest.project_id)`, and passes it to the synchronous exporter.
- Save route revalidates the V2 package with the current effective registry, rejects invalid KmAI output with a structured `422`, records usage snapshots in the same transaction, and returns `kmai_compatibility` in the save response.
- `publish_rule_package` no longer commits independently; the caller commits the package and usage rows atomically.

- [ ] **Step 1: Add failing API/lifecycle tests**

Extend the isolated lifecycle client tests so a package containing `cad.features=孔类结构` returns structured `422` until a project manual mapping is created. After creating that mapping, save succeeds and the response contains authoritative `kmai_compatibility.files`.

Query the database after save and assert:

```text
one published package row
one mapping usage row per effective mapping snapshot
validation_report_json.kmai_compatibility.mapping_snapshot == usage snapshot
```

Add a stale/changed mapping test proving the saved response uses the server’s current files, not the browser’s earlier compile response. Add a package-history test proving later mapping edits do not change the old usage snapshot.

- [ ] **Step 2: Run focused API tests and confirm failure**

```powershell
python -m pytest tests/test_rule_package_api.py tests/test_rule_package_lifecycle.py -q
```

Expected: FAIL because compile/save do not load mappings, save does not return KmAI files, and lifecycle commits without usage rows.

- [ ] **Step 3: Wire the compile route**

Change `compile_v2_rule_package` to inject `db`, build the package, load the effective registry, and return `build_kmai_compatibility_export(package, mapping_registry=registry)`. Keep `/validate` and `/simulate` independent of KmAI mapping because they validate ProcessMind V2 semantics.

- [ ] **Step 4: Make save authoritative and atomic**

After V2 structural validation in `save_finalized_rule_package`, load the registry and build the KmAI export again. If invalid, return:

```json
{
  "message": "规则包暂不兼容 KmAI，无法发布。",
  "kmai_compatibility": {"valid": false, "errors": []}
}
```

Create the `FinalizedRulePackage` row, flush it, insert usage rows from the export snapshot, call a non-committing publish helper, then commit once. Return the persisted package fields plus the freshly generated `kmai_compatibility` object. The frontend will package these returned files.

- [ ] **Step 5: Preserve historical compatibility context**

Add `load_registry_for_package(db, package_id)` that reconstructs a registry from usage snapshots. `compatibility-test` uses the published package snapshot when available and falls back to the current builtin registry for legacy packages without usage rows.

The runner must use the same mapping context as export. For manual factors, accept an explicit `manual.factor_overrides` map in the compatibility-test inputs; keep the current special-requirement simulation behavior for legacy tests and add a semantic-gap message when a required override is absent.

- [ ] **Step 6: Run focused tests and commit**

```powershell
python -m pytest tests/test_rule_package_api.py tests/test_rule_package_lifecycle.py tests/test_kmai_compatibility_runner.py -q
```

Expected: PASS, including old V2 compile tests and new historical snapshot assertions.

```powershell
git add process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/app/routers/extract.py process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py process-plan-agent-api/app/schemas/schemas.py process-plan-agent-api/app/services/finalized_rule_package_helpers.py process-plan-agent-api/tests/test_rule_package_api.py process-plan-agent-api/tests/test_rule_package_lifecycle.py process-plan-agent-api/tests/test_kmai_compatibility_runner.py
git commit --only -m "feat: enforce authoritative KmAI mapping on publish" -- process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/app/routers/extract.py process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py process-plan-agent-api/app/schemas/schemas.py process-plan-agent-api/app/services/finalized_rule_package_helpers.py process-plan-agent-api/tests/test_rule_package_api.py process-plan-agent-api/tests/test_rule_package_lifecycle.py process-plan-agent-api/tests/test_kmai_compatibility_runner.py
```

### Task 6: Add typed frontend mapping API and pure resolution state

**Files:**
- Create: `process-plan-agent-ui/src/api/kmaiFactorMappings.ts`
- Create: `process-plan-agent-ui/src/utils/kmaiFactorMappings.ts`
- Create: `process-plan-agent-ui/src/utils/kmaiFactorMappings.spec.ts`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/api/index.ts`

**Interfaces:**
- API functions: `getKmaiFactorCatalog`, `listKmaiFactorMappings`, `createKmaiFactorMappingBatch`, `updateKmaiFactorMapping`, `promoteKmaiFactorMapping`, `deleteKmaiFactorMapping`, and `previewKmaiFactorMappings`.
- Pure helpers: `groupKmaiUnmappedIssues`, `createKmaiMappingDrafts`, `validateKmaiMappingDrafts`, and `toKmaiMappingBatchRequest`.

- [ ] **Step 1: Write frontend unit tests**

Test that repeated `field + value` issues become one row with summed occurrences and merged rule refs; existing-factor drafts require a target key; manual-factor drafts require a display name and never include a client factor key; unresolved drafts produce `canContinue=false`; valid drafts produce one atomic batch request.

- [ ] **Step 2: Run the focused test and confirm failure**

From `process-plan-agent-ui`:

```powershell
npm test -- --run src/utils/kmaiFactorMappings.spec.ts
```

Expected: FAIL because the helper module does not exist.

- [ ] **Step 3: Add API types and client functions**

Extend `CompileRulePackageResponse.kmai_compatibility.errors` with the structured fields while retaining `code`, `path`, and `message`. Add `kmai_compatibility` to `FinalizedRulePackageResult` as optional because legacy GET responses do not contain the transient export files. Add the save response type to use server-returned `files`.

The batch client must send one request:

```ts
await api.post('/api/kmai-factor-mappings/batch', {
  project_id: projectId,
  items: drafts.map(({ sourceField, sourceValue, scope, mode, targetFactorKey, targetFactorName }) => ({
    scope,
    project_id: scope === 'project' ? projectId : null,
    source_field: sourceField,
    source_value: sourceValue,
    mapping_mode: mode,
    target_factor_key: mode === 'existing_factor' ? targetFactorKey : undefined,
    target_factor_name: targetFactorName,
    actor: '默认用户',
  })),
})
```

- [ ] **Step 4: Implement pure grouping and draft helpers**

Keep them framework-free so Vitest can test them without a DOM. Sort issues by field then value, preserve server rule refs, validate global/project scope, and reject an empty manual name. Do not infer a target factor from Chinese text.

- [ ] **Step 5: Run unit tests and commit**

```powershell
npm test -- --run src/utils/kmaiFactorMappings.spec.ts
```

Expected: PASS.

```powershell
git add process-plan-agent-ui/src/api/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.spec.ts process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/api/extract.ts process-plan-agent-ui/src/api/index.ts
git commit --only -m "feat: add frontend KmAI mapping contracts" -- process-plan-agent-ui/src/api/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.spec.ts process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/api/extract.ts process-plan-agent-ui/src/api/index.ts
```

### Task 7: Add fourth-step in-place mapping resolution and authoritative ZIP export

**Files:**
- Create: `process-plan-agent-ui/src/components/kmai/KmaiMappingResolutionDialog.vue`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/utils/kmaiFactorMappings.ts`

**Interfaces:**
- `useFinalizeRulePackageExport` receives `onKmaiMappingsRequired(issues): Promise<boolean>` and `onExportIssue` continues handling non-mapping errors.
- The resolver dialog emits `resolved` only after the batch request and a successful `resolve-preview` call; cancel resolves `false`.

- [ ] **Step 1: Add the export-state failure test**

Extend pure helper tests with a state sequence: compile returns `kmai_unmapped_value`, the resolver returns `true`, compile is called again, save is called once with the second result, and the ZIP source is the save response’s `kmai_compatibility.files`. A cancel or incomplete batch must call neither save nor download.

- [ ] **Step 2: Implement the dialog contract**

Render one grouped row per source value with field, occurrence count, affected rule refs, and two explicit modes:

```text
绑定已有因素: searchable select from catalog
创建人工因素: display name input; server generates factor key
```

Provide project/global scope controls. Global is allowed from the model-settings context; when opened from a project without project context, disable project scope. Show the manual-factor warning beside every manual row. The primary button stays disabled until every row passes pure validation.

- [ ] **Step 3: Integrate a promise-based resolver into FinalizeView**

Add `mappingDialogIssues` state and a resolver callback. When the composable calls `onKmaiMappingsRequired`, open the dialog and await its `resolved`/`cancelled` event. After success, call `previewKmaiFactorMappings` with the current compiled package before resolving `true`; do not rely on `KeepAlive` remounting.

- [ ] **Step 4: Split compile/retry/save in the export composable**

Keep the current review and condition-confirmation gates. After the first compile:

1. Show ordinary validation errors through the existing issue dialog.
2. Filter `kmai_compatibility.errors` to `code === 'kmai_unmapped_value'`.
3. Await the resolver if such issues exist.
4. Recompile the same request after mappings are saved.
5. If the second response is still incompatible, show its structured details and stop.
6. Save the package and use `savedPackage.kmai_compatibility.files` for all `kmai-v1/*` ZIP entries.

Never use the first compile response to create the ZIP after a mapping mutation. Include all returned manual factors in `kmai-v1/README-替换说明.txt` with their factor keys and the `manual.factor_overrides` requirement.

- [ ] **Step 5: Run frontend tests and build**

```powershell
npm test
npm run build
```

Expected: all Vitest tests pass and `vue-tsc` plus Vite build succeed.

- [ ] **Step 6: Commit only fourth-step files**

```powershell
git add process-plan-agent-ui/src/components/kmai/KmaiMappingResolutionDialog.vue process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts process-plan-agent-ui/src/views/FinalizeView.vue process-plan-agent-ui/src/api/extract.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.ts
git commit --only -m "feat: resolve KmAI mappings during rule export" -- process-plan-agent-ui/src/components/kmai/KmaiMappingResolutionDialog.vue process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts process-plan-agent-ui/src/views/FinalizeView.vue process-plan-agent-ui/src/api/extract.ts process-plan-agent-ui/src/utils/kmaiFactorMappings.ts
```

### Task 8: Add the model-settings mapping manager

**Files:**
- Create: `process-plan-agent-ui/src/components/kmai/KmaiMappingManagerDialog.vue`
- Modify: `process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.vue`
- Modify: `process-plan-agent-ui/src/App.vue`
- Modify: `process-plan-agent-ui/src/api/kmaiFactorMappings.ts`
- Create: `process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.ts`
- Create: `process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.spec.ts`

**Interfaces:**
- `ModelSettingsDrawer` accepts `projectId: number | null` and keeps the existing model form behavior intact.
- Manager actions call the Task 6 API client and refresh effective mappings after every mutation.

- [ ] **Step 1: Write manager helper tests**

Test effective-list presentation: builtin rows are read-only; project rows show “项目”; global rows show “全局”; project overrides expose the overridden target; inactive rows are distinguishable; delete is disabled for referenced rows; promotion is disabled when no project context exists.

- [ ] **Step 2: Implement the manager dialog**

Add search, source-field filter, scope filter, active/inactive filter, and a compact table. Provide edit, deactivate, promote, and delete actions. Editing an existing factor allows changing only the target factor; editing a manual factor allows changing its display name but not its generated key. Show revision and updated-by metadata.

- [ ] **Step 3: Integrate the manager into settings**

Add a two-tab shell to `ModelSettingsDrawer`: existing model configuration and “KmAI 映射”. Preserve current 480px model layout; use a wider mapping layout only while the mapping tab is active. In `App.vue`, compute the current project ID from `resolveCurrentProjectId` and pass it into the drawer. With no project context, the manager remains usable for global mappings but disables project-only actions.

- [ ] **Step 4: Run manager tests and build**

```powershell
npm test -- --run src/utils/kmaiFactorMappingsManager.spec.ts
npm run build
```

Expected: PASS and a successful type-check/build.

- [ ] **Step 5: Commit only settings files**

```powershell
git add process-plan-agent-ui/src/components/kmai/KmaiMappingManagerDialog.vue process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.vue process-plan-agent-ui/src/App.vue process-plan-agent-ui/src/api/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.ts process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.spec.ts
git commit --only -m "feat: add KmAI mapping manager to settings" -- process-plan-agent-ui/src/components/kmai/KmaiMappingManagerDialog.vue process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.vue process-plan-agent-ui/src/App.vue process-plan-agent-ui/src/api/kmaiFactorMappings.ts process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.ts process-plan-agent-ui/src/utils/kmaiFactorMappingsManager.spec.ts
```

### Task 9: Update offline compatibility tooling and documentation

**Files:**
- Modify: `process-plan-agent-ui/public/kmai-compatibility-test.html`
- Modify: `README.md`
- Modify: `process-plan-agent-api/tests/test_offline_package_safety.py` only if the generated README contract is covered there
- Modify: `process-plan-agent-api/tests/test_kmai_compatibility_runner.py` for manual override documentation behavior

- [ ] **Step 1: Add a regression fixture for exported mapping snapshots**

Extend the backend export test fixture so `validation_report.json` contains a mapping snapshot and a manual-factor instruction. Assert the standalone compatibility page can read the root validation report without relying on its old hard-coded value map.

- [ ] **Step 2: Update the standalone compatibility page**

When loading a ZIP, parse `validation_report.json` and prefer its effective mapping snapshots for translating V2 source values to factor keys. Fall back to the six builtin mappings only for old ZIPs without a snapshot. Display manual factors and allow the test input to provide `manual.factor_overrides` values explicitly.

- [ ] **Step 3: Document operator behavior**

Update the KmAI section in `README.md` to explain:

- unresolved mappings are handled in fourth-step Rule Finalization;
- model settings contains global/project mapping management;
- project mappings override global mappings;
- existing-factor mappings are safe only after semantic confirmation;
- manual factors require `manual.factor_overrides` at KmAI runtime;
- published ZIPs retain the mapping snapshot used to produce them.

- [ ] **Step 4: Run focused offline and frontend checks**

```powershell
python -m pytest tests/test_kmai_compatibility_runner.py tests/test_offline_package_safety.py -q
```

From `process-plan-agent-ui`:

```powershell
npm run build
```

Expected: PASS and a successful build.

- [ ] **Step 5: Commit documentation/tooling**

```powershell
git add process-plan-agent-ui/public/kmai-compatibility-test.html README.md process-plan-agent-api/tests/test_offline_package_safety.py process-plan-agent-api/tests/test_kmai_compatibility_runner.py
git commit --only -m "docs: document KmAI factor mapping workflow" -- process-plan-agent-ui/public/kmai-compatibility-test.html README.md process-plan-agent-api/tests/test_offline_package_safety.py process-plan-agent-api/tests/test_kmai_compatibility_runner.py
```

### Task 10: Full verification and handoff

**Files:**
- No new production files.
- Test and inspect all files changed by Tasks 1-9.

- [ ] **Step 1: Run all backend tests**

From `process-plan-agent-api`:

```powershell
python -m pytest -q
```

Expected: all backend tests pass, including existing rule-package, lifecycle, startup, and offline tests.

- [ ] **Step 2: Run all frontend tests and build**

From `process-plan-agent-ui`:

```powershell
npm test
npm run build
```

Expected: all Vitest tests pass and the production build completes.

- [ ] **Step 3: Exercise the product workflow**

Start the API and UI with the repository’s Windows start commands. In a project with the three reported values:

1. Open step 4 and click “审核并导出规则包”.
2. Confirm the grouped resolver shows `孔类结构`, `型孔`, and `装夹定位中心孔` once each with occurrence counts.
3. Bind `型孔` only after confirming its semantic target; create a manual factor for `孔类结构` and observe the explicit runtime warning.
4. Save as a project mapping, complete preview, and continue export.
5. Open model settings, verify the project mappings, promote one to global, switch to another project, and verify reuse.
6. Edit the mapping, export a new package, and verify the old package’s mapping snapshot remains unchanged.
7. Attempt to delete a mapping referenced by a published package and verify the UI offers deactivation instead.

- [ ] **Step 4: Inspect the final diff and worktree**

```powershell
git diff --check HEAD~10..HEAD
git status --short
```

Expected: no whitespace errors; unrelated pre-existing user changes remain present and are not included in feature commits.

## Plan Self-Review

- Spec coverage: persistence, scope precedence, existing/manual modes, fourth-step resolver, settings manager, structured errors, authoritative save response, audit events, usage snapshots, historical compatibility, manual-factor documentation, and test coverage are each assigned to a task.
- Placeholder scan: the plan contains no unresolved placeholder marker or unspecified implementation step.
- Type consistency: `KmaiMappingSnapshot` is produced by the registry, consumed by the exporter/store, returned through `KmaiCompatibilityExport`, and displayed by both frontend surfaces. The save response uses the same `kmai_compatibility.files` shape as the compile response.
- Scope: CAD filter editing is explicitly excluded from all tasks; it is a separate future design.
