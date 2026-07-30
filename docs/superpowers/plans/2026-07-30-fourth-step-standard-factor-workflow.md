# Fourth-Step Standard Factor Workflow Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the fourth step the only user-facing place where rule semantics and standard factors are confirmed, then export through an immutable code-owned KmAI adapter with no configurable mapping subsystem.

**Architecture:** Extend the existing condition-field registry into a versioned field-and-factor catalog. Persist a stable `factor_id` on every standard condition leaf, validate it at confirmation/compile/save boundaries, and let KmAI export resolve only that ID through fixed code. Historical packages replay their own embedded snapshot, while one transactional startup migration backfills missing snapshots before removing the retired mapping tables.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async/SQLite, pytest; Vue 3, TypeScript 5.9, Vitest, Vite.

## Global Constraints

- The fourth step is the only user-facing rule-semantic and factor-confirmation entry point.
- `factor_id` is a stable ProcessMind identifier; a KmAI factor key remains an internal export detail.
- Do not use project, global, or export-time mappings to infer a factor, including during legacy migration.
- Unknown, custom, ambiguous, or partially bound compound conditions must return to the fourth step; do not guess.
- A manual Boolean factor keeps the `project_factor.manual_process_*` field form and has no standard `factor_id`.
- The export review status union is exactly `ready | blocked`.
- A manual Boolean `eq true` include / `eq false` exclude pair is exempt only when both confirmed rules use the same field, source segment, priority, and sole target process; every other same-priority conflict remains blocked.
- Before dropping mapping tables, backfill missing `validation_report_json.kmai_compatibility.mapping_snapshot` values from immutable usage rows and verify every affected package. Any failure rolls back the entire migration and preserves all three tables.
- The backfill may change only `validation_report_json`; it must not change manifest, input schema, process catalog, route rules, test cases, report Markdown, or `content_hash`.
- Historical published package content remains immutable. A package with an embedded snapshot replays that snapshot; an older package without one may use only the fixed legacy built-in adapter.
- New packages do not persist mapping identity, revision, scope, usage records, or mapping signatures.
- Preserve the current KmAI factor-calculation and route-execution semantics, including `manual.factor_overrides` warnings.
- Follow TDD for every task: first prove the new test fails for the intended reason, then implement only enough to pass it.

## File Structure

### New files

- `process-plan-agent-api/app/services/rule_packages/standard_factors.py`: immutable ProcessMind standard-factor catalog, exact matching, tree normalization, binding, validation, and fixed legacy adapter data.
- `process-plan-agent-api/tests/test_standard_factor_catalog.py`: catalog contract, registry API, exact binding, ambiguity, unknown value, and compound-leaf coverage.
- `process-plan-agent-ui/src/utils/standardFactorBindings.ts`: pure traversal, completeness, search, and factor-application helpers.
- `process-plan-agent-ui/src/utils/standardFactorBindings.spec.ts`: frontend binding and invalidation tests.
- `process-plan-agent-ui/src/components/finalize/StandardFactorPicker.vue`: searchable factor control used by each condition leaf.
- `process-plan-agent-ui/src/components/finalize/StandardFactorPicker.spec.ts`: rendered label, category, ambiguity, and manual-factor guidance tests.
- `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.vue`: mapping-free `ready/blocked` export review UI.

### Modified backend files

- `process-plan-agent-api/app/services/rule_packages/contracts.py`: add optional `ConditionNode.factor_id`; replace mapping metadata in KmAI export with `factor_catalog_version`.
- `process-plan-agent-api/app/services/rule_packages/condition_contracts.py`: add `StandardFactorDefinition`, `FactorBindingIssue`, and `factors` to the existing registry response.
- `process-plan-agent-api/app/services/rule_packages/condition_registry.py`: publish one combined registry version and standard factors.
- `process-plan-agent-api/app/services/rule_packages/condition_parser.py`: normalize multi-value semantic leaves before binding uniquely matched factors.
- `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`: enforce binding at confirmation and safely migrate unpublished legacy reviews.
- `process-plan-agent-api/app/services/route_analysis.py`: run the unpublished-review factor migration before returning fourth-step data.
- `process-plan-agent-api/app/services/rule_packages/compiler.py`: reject an unbound or mismatched standard condition before creating a package.
- `process-plan-agent-api/app/services/rule_packages/validator.py`: validate factor bindings and precisely exempt mutually exclusive manual Boolean pairs.
- `process-plan-agent-api/app/services/rule_packages/kmai_export.py`: resolve standard leaves by fixed `factor_id`; keep manual overrides code-owned.
- `process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py`: run current packages through fixed factors and historical packages through an explicit read-only legacy snapshot.
- `process-plan-agent-api/app/services/rule_packages/lifecycle.py`: read historical snapshot metadata from `validation_report_json`, with the usage-table fallback removed after migration.
- `process-plan-agent-api/app/routers/rule_packages.py`: return factors from the existing endpoint and stop loading a database mapping registry for compile/compatibility.
- `process-plan-agent-api/app/routers/extract.py`: stop loading/writing mappings and persist only catalog-version compatibility metadata for new packages.
- `process-plan-agent-api/app/services/db_schema_maintenance.py`: transactionally backfill snapshots, verify them, and drop the retired tables without recreating them.
- `process-plan-agent-api/app/models/models.py`: remove retired mapping ORM models and relationships.
- `process-plan-agent-api/app/routers/projects.py`: remove project deletion logic for retired mappings.
- `process-plan-agent-api/app/main.py`: unregister the retired mapping router.
- Existing backend tests listed in each task: adapt fixtures to include `factor_id` and replace dynamic-mapping expectations with fixed-catalog expectations.

### Modified frontend files

- `process-plan-agent-ui/src/api/rulePackages.ts`: own standard-factor and KmAI-export types; add `factor_id` to leaf conditions and factors to registry responses.
- `process-plan-agent-ui/src/api/extract.ts`: import the KmAI export type from `rulePackages.ts`.
- `process-plan-agent-ui/src/api/index.ts`: stop exporting the deleted mapping client.
- `process-plan-agent-ui/src/components/finalize/RuleConditionNodeEditor.vue`: render the factor picker for each leaf and clear stale bindings on condition edits.
- `process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue`: show selected factor name/category and manual-runtime guidance.
- `process-plan-agent-ui/src/composables/finalizeViewHelpers.ts`: carry factor-catalog data into cards.
- `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`: require complete factor bindings for batch confirmation and preserve `factor_id` in compile DTOs.
- `process-plan-agent-ui/src/views/FinalizeView.vue`: load factors with fields, pass them to cards, block on registry failure, and locate blocked export items.
- `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`: remove mapping branches and build structured blocked details.
- `process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.vue`: remove the KmAI mapping tab and responsive mapping width.
- `process-plan-agent-ui/src/components.d.ts`: remove the deleted mapping-manager component registration.
- Existing frontend tests listed in Tasks 3 and 6: update the registry, review-status, and export DTO expectations.

### Deleted files

- Backend: `app/routers/kmai_factor_mappings.py`, `app/services/rule_packages/kmai_mapping_contracts.py`, `app/services/rule_packages/kmai_mapping_registry.py`, `app/services/rule_packages/kmai_mapping_store.py`.
- Backend tests retired with the subsystem: `tests/test_kmai_factor_mapping_api.py`, `tests/test_kmai_mapping_registry.py`, `tests/test_kmai_mapping_schema.py`.
- Frontend: `src/api/kmaiFactorMappings.ts`, `src/api/kmaiFactorMappings.contract.spec.ts`, `src/components/kmai/KmaiMappingManagerDialog.vue`, `src/components/kmai/RulePackageExportReviewDialog.vue`, `src/composables/kmaiFactorMappingState.ts`, `src/composables/kmaiFactorMappingState.spec.ts`, `src/utils/kmaiFactorMappings.ts`, `src/utils/kmaiFactorMappings.spec.ts`, `src/utils/kmaiFactorMappingsManager.ts`, `src/utils/kmaiFactorMappingsManager.spec.ts`.

---

### Task 1: Immutable Standard-Factor Contract and Registry API

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/standard_factors.py`
- Create: `process-plan-agent-api/tests/test_standard_factor_catalog.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py:106-137`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_contracts.py:10-76`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_registry.py:1-170`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py:31-68`
- Test: `process-plan-agent-api/tests/test_rule_package_api.py`

**Interfaces:**
- Produces: `STANDARD_FACTOR_CATALOG_VERSION = "2026.11"`.
- Produces: `standard_factors() -> list[StandardFactorDefinition]` and `standard_factor_map() -> dict[str, StandardFactorDefinition]`, both read-only by copy.
- Produces: `normalize_factor_leaves(node: ConditionNode) -> ConditionNode`.
- Produces: `matching_standard_factors(node: ConditionNode) -> list[StandardFactorDefinition]`.
- Produces: `bind_unambiguous_factor_ids(node: ConditionNode) -> tuple[ConditionNode, list[FactorBindingIssue]]`.
- Produces: `validate_factor_bindings(node: ConditionNode, additional_fields: dict[str, CanonicalConditionField] | None = None) -> list[FactorBindingIssue]`.
- Changes: `ConditionNode.factor_id: str | None = None`; logical `all/any/not` nodes must not carry one.
- Changes: `ConditionFieldRegistryResponse` becomes `{version, fields, factors}` at the existing endpoint.

The immutable catalog must cover every non-custom current option and every scalar current field. Use these exact stable mappings:

| Source | Canonical value | `factor_id` | KmAI key | Mode |
|---|---|---|---|---|
| `material.grade` | `null` | `material.grade` | `material_grade` | condition value |
| `cad.features` | `扁位/平面` | `feature.flat_or_plane` | `has_flat_or_plane` | presence |
| `cad.features` | `槽类特征` | `feature.slot` | `has_slot_feature` | presence |
| `cad.features` | `普通孔/辅助孔` | `feature.standard_or_aux_hole` | `has_standard_or_aux_hole` | presence |
| `cad.features` | `铰孔/精孔` | `feature.reamed_or_precision_hole` | `has_reamed_or_precision_hole` | presence |
| `cad.features` | `型孔/割扁` | `feature.shaped_hole_or_cut_flat` | `has_shaped_hole_or_cut_flat` | presence |
| `cad.features` | `顶尖孔` | `feature.center_hole_location` | `uses_center_hole_location` | presence |
| `precision.grades` | `孔精加工` | `precision.hole_finish` | `has_hole_finish_machining` | presence |
| `precision.grades` | `珩孔要求` | `precision.honing` | `requires_honing` | presence |
| `precision.grades` | `研孔要求` | `precision.hole_lapping` | `requires_hole_lapping` | presence |
| `precision.grades` | `外圆磨削` | `precision.outer_diameter_grinding` | `requires_outer_diameter_grinding` | presence |
| `precision.grades` | `端面磨削` | `precision.end_face_grinding` | `requires_end_face_grinding` | presence |
| `precision.grades` | `槽磨削` | `precision.slot_grinding` | `requires_slot_grinding` | presence |
| `precision.grades` | `研外圆` | `precision.outer_diameter_lapping` | `requires_outer_diameter_lapping` | presence |
| `special.requirements` | `渗氮层要求` | `requirement.nitrided_layer` | `has_nitrided_layer` | presence |
| `special.requirements` | `铬酸阳极化要求` | `requirement.chromic_acid_anodizing` | `needs_chromic_acid_anodizing` | presence |
| `special.requirements` | `硬质阳极化要求` | `requirement.hard_anodizing` | `needs_hard_anodizing` | presence |
| `special.requirements` | `追溯标印` | `requirement.traceability_marking` | `needs_marking` | presence |
| `special.requirements` | `无损检测要求` | `requirement.nondestructive_testing` | `needs_ndt_inspection` | presence |
| `special.requirements` | `磁粉检查要求` | `requirement.magnetic_particle_inspection` | `needs_crack_inspection` | presence |
| `special.requirements` | `烧伤检查要求` | `requirement.burn_inspection` | `needs_burn_inspection` | presence |

`material.grade` is one enum factor: all supported/custom grade values and `eq/neq/in` operators retain their condition value and target the same `material_grade` key. Scalar factors also use `canonical_value=None`, preserve the condition value, use the existing deterministic field key with dots replaced by underscores as `kmai_factor_key`, and set `runtime_source="manual_override"`: `precision.outer_diameter_it`, `precision.inner_diameter_it`, `precision.dimension_it`, `surface.roughness_ra`, all seven `tolerance.*` fields, `geometry.diameter_mm`, `geometry.length_mm`, and `mechanical.hardness_hrc`. Their factor IDs are respectively `measurement.<field suffix>`; for example `measurement.outer_diameter_it` and `measurement.roughness_ra`. Only `measurement.hardness_hrc` has the read-only legacy source alias `target_hardness_hrc`; matching/validation accepts it for old packages, while factor selection always writes canonical `mechanical.hardness_hrc`.

Use these display labels/categories: material reuses “材料牌号 · 材料”; CAD presence factors use their current Chinese option labels and “结构特征”, except `feature.center_hole_location`, which is “顶尖孔定位 · 精度要求”; all `precision.*` factors use their current option label and “精度要求”; special-requirement factors use “热处理”, “表面处理”, or “检验与标识” according to the fixed target; scalar factors reuse the current field label/category.

- [ ] **Step 1: Write failing catalog and condition-shape tests**

```python
def test_standard_catalog_keeps_hole_finish_distinct_from_center_through_hole():
    factors = standard_factor_map()
    assert factors["precision.hole_finish"].kmai_factor_key == "has_hole_finish_machining"
    assert factors["feature.center_hole_location"].kmai_factor_key == "uses_center_hole_location"
    assert all(item.kmai_factor_key != "has_center_through_hole" for item in factors.values())


def test_condition_node_persists_factor_id_only_on_leaf():
    leaf = ConditionNode.model_validate({
        "field": "cad.features", "op": "contains", "value": "顶尖孔",
        "factor_id": "feature.center_hole_location",
    })
    assert leaf.factor_id == "feature.center_hole_location"
    with pytest.raises(ValidationError, match="logical condition cannot carry factor_id"):
        ConditionNode.model_validate({"all": [leaf.model_dump(mode="json")], "factor_id": "invalid"})
```

- [ ] **Step 2: Run the focused tests and verify the intended failure**

Run from `process-plan-agent-api`:

```powershell
python -m pytest tests/test_standard_factor_catalog.py -v
```

Expected: FAIL because `standard_factors.py`, `factor_id`, and `StandardFactorDefinition` do not exist.

- [ ] **Step 3: Add the strict contracts and catalog**

```python
class StandardFactorDefinition(StrictModel):
    factor_id: str = Field(min_length=1)
    label: str = Field(min_length=1)
    category: str = Field(min_length=1)
    source_field: str = Field(min_length=1)
    source_field_aliases: list[str] = Field(default_factory=list)
    canonical_value: Any = None
    allowed_operators: list[ConditionOperator] = Field(min_length=1)
    kmai_factor_key: str = Field(min_length=1)
    kmai_value_mode: Literal["presence", "condition_value"]
    runtime_source: Literal["computed", "manual_override"] = "computed"


class FactorBindingIssue(StrictModel):
    code: Literal["factor_unbound", "factor_ambiguous", "factor_mismatch"]
    path: str
    message: str
    candidate_factor_ids: list[str] = Field(default_factory=list)
```

Update `ConditionNode.validate_shape()` so a leaf may carry `factor_id`, while logical nodes reject it. Return deep copies from public catalog functions so callers cannot mutate the code-owned constants.

- [ ] **Step 4: Add failing normalization, exact-match, unknown, ambiguity, and compound tests**

```python
def test_multi_value_presence_leaf_is_split_before_binding():
    normalized = normalize_factor_leaves(ConditionNode.model_validate({
        "field": "precision.grades",
        "op": "contains_any",
        "value": ["孔精加工", "珩孔要求"],
    }))
    assert normalized.any_conditions is not None
    assert [child.value for child in normalized.any_conditions] == ["孔精加工", "珩孔要求"]


def test_exact_value_binds_but_unknown_value_does_not_guess():
    bound, issues = bind_unambiguous_factor_ids(ConditionNode(
        field="precision.grades", op="contains", value="孔精加工",
    ))
    assert bound.factor_id == "precision.hole_finish"
    assert issues == []

    unknown, issues = bind_unambiguous_factor_ids(ConditionNode(
        field="precision.grades", op="contains", value="自定义超精加工",
    ))
    assert unknown.factor_id is None
    assert [issue.code for issue in issues] == ["factor_unbound"]


def test_every_compound_leaf_is_validated_independently():
    node = ConditionNode.model_validate({"all": [
        {"field": "cad.features", "op": "contains", "value": "顶尖孔", "factor_id": "feature.center_hole_location"},
        {"field": "precision.grades", "op": "contains", "value": "自定义值"},
    ]})
    assert [issue.path for issue in validate_factor_bindings(node)] == ["all[1]"]
```

For ambiguity coverage, pass a test-only catalog containing two definitions with the same field/value/operator to the internal matcher and assert `factor_ambiguous` with both IDs. Keep that injectable catalog parameter private; production callers use only the immutable catalog.

- [ ] **Step 5: Implement deterministic normalization and binding**

Normalize only presence-field list operators: `contains_any` becomes `any` of `contains` leaves, `contains_all` becomes `all` of `contains` leaves, and presence-field `in` becomes `any` of `eq` leaves. Do not split a material-grade `in` list or numeric `between`; both belong to one condition-value factor. A factor matches only when the field is its canonical source or a declared read-only legacy alias, the operator matches, and either its canonical value is `None` or the leaf value equals it after NFKC/whitespace normalization.

```python
def normalize_factor_leaves(node: ConditionNode) -> ConditionNode:
    if node.field is not None:
        values = node.value if isinstance(node.value, list) else None
        presence_field = node.field in {"cad.features", "precision.grades", "special.requirements"}
        split = {
            "contains_any": ("any", "contains"),
            "contains_all": ("all", "contains"),
            "in": ("any", "eq"),
        }.get(str(node.op)) if presence_field else None
        if values is None or split is None:
            return node.model_copy(deep=True)
        branch, child_op = split
        children = [ConditionNode(field=node.field, op=child_op, value=value) for value in values]
        return ConditionNode(any_conditions=children) if branch == "any" else ConditionNode(all_conditions=children)
    if node.all_conditions is not None:
        return ConditionNode(all_conditions=[normalize_factor_leaves(child) for child in node.all_conditions])
    if node.any_conditions is not None:
        return ConditionNode(any_conditions=[normalize_factor_leaves(child) for child in node.any_conditions])
    return ConditionNode(not_condition=normalize_factor_leaves(node.not_condition))


def _bind_leaf(node: ConditionNode, path: str) -> tuple[ConditionNode, list[FactorBindingIssue]]:
    matches = matching_standard_factors(node)
    if len(matches) == 1:
        return node.model_copy(update={"factor_id": matches[0].factor_id}), []
    code = "factor_ambiguous" if matches else "factor_unbound"
    return node.model_copy(update={"factor_id": None}), [FactorBindingIssue(
        code=code,
        path=path,
        message="标准因子存在多个候选" if matches else "条件尚未绑定标准因子",
        candidate_factor_ids=[item.factor_id for item in matches],
    )]
```

- [ ] **Step 6: Extend the existing registry endpoint and test its exact response**

```python
def test_condition_field_registry_returns_versioned_standard_factors(client):
    response = client.get("/api/extract/finalized-rule-packages/condition-fields")
    assert response.status_code == 200
    body = response.json()
    assert body["version"] == STANDARD_FACTOR_CATALOG_VERSION
    assert body["factors"]
    center = next(item for item in body["factors"] if item["factor_id"] == "feature.center_hole_location")
    assert center["source_field"] == "cad.features"
    assert center["canonical_value"] == "顶尖孔"
    assert center["kmai_factor_key"] == "uses_center_hole_location"
```

Return `ConditionFieldRegistryResponse(version=STANDARD_FACTOR_CATALOG_VERSION, fields=condition_fields(), factors=standard_factors())`; do not add a second endpoint.

Keep `FIELD_REGISTRY_VERSION = STANDARD_FACTOR_CATALOG_VERSION` as a compatibility alias for parser/review imports, so one version invalidates both field and factor assumptions.

- [ ] **Step 7: Run focused backend tests**

```powershell
python -m pytest tests/test_standard_factor_catalog.py tests/test_rule_package_api.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit the catalog contract**

```powershell
git add process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/condition_contracts.py process-plan-agent-api/app/services/rule_packages/condition_registry.py process-plan-agent-api/app/services/rule_packages/standard_factors.py process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/tests/test_standard_factor_catalog.py process-plan-agent-api/tests/test_rule_package_api.py
git commit -m "feat: add immutable standard factor catalog"
```

### Task 2: Candidate Binding, Confirmation Validation, and Safe Unpublished Migration

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_reviews.py`
- Modify: `process-plan-agent-api/app/services/route_analysis.py:286-295`
- Modify: `process-plan-agent-api/app/services/rule_packages/compiler.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/validator.py`
- Modify: `process-plan-agent-api/tests/fixtures/rule_package_v2.json`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`
- Test: `process-plan-agent-api/tests/test_rule_package_api.py`
- Test: `process-plan-agent-api/tests/test_rule_package_v2.py`

**Interfaces:**
- Produces: `migrate_legacy_standard_factor_reviews(route: NormalizedRouteVersion, db: AsyncSession) -> bool`.
- Produces: `RulePackageCompilationError(issues: list[FactorBindingIssue])`; the compile router converts it to HTTP 422 with a stable `{message, issues}` body.
- Consumes: Task 1 binding/validation functions.
- Changes: parsed candidates carry uniquely inferred `factor_id` values; ambiguous or unknown leaves remain unbound and produce explicit issues.
- Changes: confirm, compile, and save reject any standard leaf that is unbound or mismatched; manual Boolean leaves remain valid without `factor_id`.
- Changes: unpublished migration revalidates the complete candidate against the current route process catalog, so a removed/changed action target invalidates the old confirmation even when source text is unchanged.

- [ ] **Step 1: Write failing parser and confirmation tests**

```python
@pytest.mark.asyncio
async def test_parser_binds_an_exact_standard_factor():
    candidate, confidence, issues = await condition_parser.parse_rule_condition(
        "当存在顶尖孔时，纳入磨外圆工序", "process_grind_outer", "磨外圆", PROCESSES,
    )
    assert candidate.when.factor_id == "feature.center_hole_location"
    assert confidence >= 0.85
    assert issues == []


@pytest.mark.asyncio
async def test_confirm_rejects_unknown_unbound_value(review_db):
    body = confirmed_request_with_candidate(
        {"field": "precision.grades", "op": "contains", "value": "未知精加工"}
    )
    with pytest.raises(HTTPException) as error:
        await confirm_condition_review(body, review_db)
    assert error.value.status_code == 422
    assert "标准因子" in str(error.value.detail)
```

Add a compound test whose first leaf is bound and second leaf is not; confirmation must fail and identify the second leaf path. Add a manual Boolean test proving the existing `project_factor.manual_process_* eq true` candidate still confirms without `factor_id`.

Rewrite the existing parser tests named `test_creates_project_factor_for_unregistered_categorical_field`, `test_creates_one_project_factor_with_multiple_user_authored_categories`, `test_maps_unseen_structural_feature_to_extensible_cad_tag`, `test_maps_unseen_process_requirement_to_extensible_special_tag`, and `test_creates_project_factor_for_unknown_part_category_instead_of_special_requirement`. A custom value under a known field may remain as an unbound editable candidate with a `factor_unbound` issue; an unregistered concept must be invalid/unresolved. None may create a confirmable categorical `project_factor.*` definition. The only confirmable project factor is the explicit manual Boolean path.

- [ ] **Step 2: Run the focused tests and verify binding is absent**

```powershell
python -m pytest tests/test_rule_condition_parser.py -k "standard_factor or unbound or manual" -v
```

Expected: FAIL because parser/confirmation do not bind or enforce factors.

- [ ] **Step 3: Bind after parsing and validate before confirmation**

After the parser has produced a condition candidate:

```python
normalized = normalize_factor_leaves(candidate.when)
bound, binding_issues = bind_unambiguous_factor_ids(normalized)
candidate = candidate.model_copy(update={"when": bound})
issues.extend(issue.message for issue in binding_issues)
```

Keep the candidate available when binding is unresolved so the fourth step can show choices. In `confirm_condition_review`, run `validate_candidate` first, then `validate_factor_bindings`; return HTTP 422 with `{message, issues: [issue.model_dump(mode="json") for issue in binding_issues]}` when any binding issue remains. The manual endpoint continues to enforce its exact current shape and bypasses standard-factor validation only for the manual field definition.

Remove the parser branch that promotes an unregistered categorical concept into a confirmable custom `project_factor.*` field. Preserve the source text/evidence and return either an unbound known-field candidate or `invalid` review so the user can select a standard factor or explicitly create a manual Boolean factor.

- [ ] **Step 4: Add failing unpublished legacy migration tests**

Create three stored review rows:

1. confirmed `precision.grades contains 孔精加工` without `factor_id`;
2. confirmed custom `precision.grades contains 未知精加工`;
3. confirmed compound condition with one known and one unknown leaf.

Create a fourth confirmed review whose `then.include_process_ids` references a process no longer present in the route JSON. It must return to `pending_confirmation` with the editable candidate retained and the confirmation cleared.

```python
changed = await migrate_legacy_standard_factor_reviews(route, db)
assert changed is True
known = serialize_condition_review(known_row)
assert known.status == "confirmed"
assert known.confirmed.when.factor_id == "precision.hole_finish"
assert known.field_registry_version == STANDARD_FACTOR_CATALOG_VERSION

unknown = serialize_condition_review(unknown_row)
assert unknown.status == "pending_confirmation"
assert unknown.confirmed is None
assert unknown.candidate.when.factor_id is None
assert any("标准因子" in issue for issue in unknown.issues)
```

Also seed an obsolete project/global mapping for the unknown value and assert it does not affect the result.

- [ ] **Step 5: Implement idempotent migration and version invalidation**

For each condition candidate/confirmation:

- Normalize and bind only exact unique legacy leaves.
- Keep `confirmed` only when every leaf validates against the current catalog.
- If a previously selected `factor_id` still validates after a catalog-version change, update the registry version without invalidating the review.
- If the selected factor was removed or changed incompatibly, keep the editable candidate, clear confirmed JSON/user/time, set `pending_confirmation`, and record the affected path.
- Re-run `validate_candidate(candidate, current_route_processes)` during migration; invalidate the same way if its condition actions or process relation references no longer belong to the route.
- Never consult a mapping table.
- Commit once at the end only when at least one row changed, matching the existing migration helpers.

Use one explicit outcome helper for candidate/confirmation state:

```python
def _migrate_review_candidate(candidate, processes):
    if candidate.kind != "condition" or candidate.when is None:
        return candidate, validate_candidate(candidate, processes)
    normalized = normalize_factor_leaves(candidate.when)
    bound, binding_issues = bind_unambiguous_factor_ids(normalized)
    migrated = candidate.model_copy(update={"when": bound})
    candidate_issues = validate_candidate(migrated, processes)
    all_issues = [issue.message for issue in binding_issues] + candidate_issues
    return migrated, all_issues


if all_issues:
    review.condition_status = "pending_confirmation"
    review.condition_candidate_json = _candidate_json(migrated)
    review.condition_confirmed_json = None
    review.condition_confirmed_by = None
    review.condition_confirmed_at = None
    review.condition_issues_json = json.dumps(all_issues, ensure_ascii=False)
else:
    review.condition_candidate_json = _candidate_json(migrated)
    review.condition_confirmed_json = _candidate_json(migrated)
    review.condition_issues_json = "[]"
review.condition_field_registry_version = STANDARD_FACTOR_CATALOG_VERSION
```

Call it from `build_saved_normalized_route_response()` next to the existing legacy Boolean/NDT migrations, before reviews are serialized to the UI.

- [ ] **Step 6: Add compile/save binding tests**

```python
def test_compile_rejects_a_factor_id_that_does_not_match_the_leaf(client, compile_payload):
    compile_payload["rules"][0]["when"] = {
        "field": "precision.grades",
        "op": "contains",
        "value": "孔精加工",
        "factor_id": "feature.center_hole_location",
    }
    response = client.post("/api/extract/finalized-rule-packages/compile", json=compile_payload)
    assert response.status_code == 422
    assert "factor_mismatch" in response.text
```

Add the same assertion to direct V2 package save. Keep general historical package deserialization tolerant of missing IDs; enforcement belongs to new confirmation/compile/save paths so old published payloads remain readable.

Update the current V2 fixture without changing its business fields or inputs: add `factor_id="material.grade"` to the material `in` leaf, `factor_id="measurement.hardness_hrc"` to the `target_hardness_hrc` legacy-alias leaf, and `factor_id="feature.slot"` to the slot leaf. Historical package payloads created inside lifecycle tests remain unmodified.

`compile_rule_package()` raises `RulePackageCompilationError` before materializing the package when any request rule has binding issues. `compile_v2_rule_package()` catches that error, computes `serialized_issues = [issue.model_dump(mode="json") for issue in error.issues]`, and raises `HTTPException(status_code=422, detail={"message": "标准因子绑定校验未通过", "issues": serialized_issues})`. The save endpoint applies the same validator to the submitted V2 package and returns the same detail shape.

- [ ] **Step 7: Run the task test set**

```powershell
python -m pytest tests/test_standard_factor_catalog.py tests/test_rule_condition_parser.py tests/test_rule_package_api.py tests/test_rule_package_v2.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit candidate binding and migration**

```powershell
git add process-plan-agent-api/app/services/rule_packages/condition_parser.py process-plan-agent-api/app/services/rule_packages/condition_reviews.py process-plan-agent-api/app/services/route_analysis.py process-plan-agent-api/app/services/rule_packages/compiler.py process-plan-agent-api/app/services/rule_packages/validator.py process-plan-agent-api/tests/fixtures/rule_package_v2.json process-plan-agent-api/tests/test_rule_condition_parser.py process-plan-agent-api/tests/test_rule_package_api.py process-plan-agent-api/tests/test_rule_package_v2.py
git commit -m "feat: bind factors during fourth-step review"
```

### Task 3: Fourth-Step Factor Selection, Invalidation, and Batch Safety

**Files:**
- Create: `process-plan-agent-ui/src/utils/standardFactorBindings.ts`
- Create: `process-plan-agent-ui/src/utils/standardFactorBindings.spec.ts`
- Create: `process-plan-agent-ui/src/components/finalize/StandardFactorPicker.vue`
- Create: `process-plan-agent-ui/src/components/finalize/StandardFactorPicker.spec.ts`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/components/finalize/RuleConditionNodeEditor.vue`
- Modify: `process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue`
- Modify: `process-plan-agent-ui/src/composables/finalizeViewHelpers.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Produces: `StandardFactorDefinition` and `ConditionFieldRegistryResponse` frontend types matching Task 1.
- Produces: `factorBindingState(condition, factors) -> {complete, ambiguous, issues, selected}`.
- Produces: `matchingStandardFactors(leaf, factors) -> StandardFactorDefinition[]`, mirroring backend exact-match and legacy-alias rules.
- Produces: `filterStandardFactors(factors, query) -> StandardFactorDefinition[]` searching label, category, source field, and ID.
- Produces: `applyStandardFactor(leaf, factor) -> RulePackageCondition`.
- Produces: `withConditionValue(leaf, value) -> RulePackageCondition`, which always removes a stale factor ID.
- Produces: `ruleConfirmationSignature(candidate, sourceText, registryVersion) -> string`, using stable key ordering over the condition tree, actions/relations, factor IDs, source text, and registry version.
- Changes: `isSafeForBatchRuleConfirmation(item, factors, registryVersion)` requires high confidence, current text/version, and a unique complete binding.
- Changes: condition edits delete the old `factor_id`; choosing a factor writes a compatible field/operator/value plus its ID.
- Changes: `buildCompileRequestFromCards` receives `standardFactors` and every generated `system_static` leaf is bound before the request is sent.

- [ ] **Step 1: Write failing pure binding-helper tests**

```typescript
it('marks every leaf of a compound condition independently', () => {
  const state = factorBindingState({ all: [
    { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
    { field: 'precision.grades', op: 'contains', value: '未知精加工' },
  ] }, factors)
  expect(state.complete).toBe(false)
  expect(state.issues[0].path).toBe('all[1]')
})

it('replacing a factor writes canonical semantics and condition edits clear it', () => {
  expect(applyStandardFactor(
    { field: 'precision.grades', op: 'contains', value: '未知值' },
    factors.find(item => item.factor_id === 'precision.hole_finish')!,
  )).toEqual({
    field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
  })
  expect(withConditionValue(
    { field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish' },
    '珩孔要求',
  )).not.toHaveProperty('factor_id')
})
```

Add search assertions for `顶尖孔`, `精度要求`, and `feature.center_hole_location`; all must find the same factor without exposing KmAI keys as primary UI text.

Add a signature test: changing only `when`, `then.include_process_ids`, a relation target, or `factor_id` must change the signature; reordering object keys must not.

- [ ] **Step 2: Run the helper tests and verify the module is missing**

```powershell
npm test -- --run src/utils/standardFactorBindings.spec.ts
```

Expected: FAIL because the helper module and frontend types do not exist.

- [ ] **Step 3: Add matching frontend types and pure helpers**

Use this leaf union so IDs survive DTO creation:

```typescript
export type RulePackageCondition =
  | { all: RulePackageCondition[] }
  | { any: RulePackageCondition[] }
  | { not: RulePackageCondition }
  | { field: string; op: string; value?: unknown; factor_id?: string | null }

export type StandardFactorDefinition = {
  factor_id: string
  label: string
  category: string
  source_field: string
  source_field_aliases: string[]
  canonical_value: unknown
  allowed_operators: string[]
  kmai_factor_key: string
  kmai_value_mode: 'presence' | 'condition_value'
  runtime_source: 'computed' | 'manual_override'
}
```

`applyStandardFactor` retains the leaf operator only if allowed, otherwise uses the first allowed operator; it replaces the value only when `canonical_value !== null`. Manual project fields are recognized separately and considered complete without an ID.

Update `hasCurrentConfirmedUserRule` to require matching signatures for `review.candidate` and `review.confirmed`, in addition to the existing confirmed status and source-text check. The current registry version is part of the comparison. This makes an in-card condition/action edit immediately pending until the server confirms it again; a failed save leaves the edited candidate in memory.

- [ ] **Step 4: Write the failing picker render test**

```typescript
it('shows the Chinese factor name and category while keeping the technical id secondary', async () => {
  const html = await renderPicker({
    modelValue: { field: 'cad.features', op: 'contains', value: '顶尖孔', factor_id: 'feature.center_hole_location' },
    factors,
  })
  expect(html).toContain('顶尖孔定位')
  expect(html).toContain('精度要求')
  expect(html).toContain('feature.center_hole_location')
  expect(html).not.toContain('uses_center_hole_location')
})
```

Also render an unbound leaf and assert “请选择标准因子或创建手工因子”; render a manual Boolean leaf and assert “该因子不能由 CAD 自动得出”.

- [ ] **Step 5: Implement and integrate `StandardFactorPicker`**

The control contains a compact selected-factor row, a search input shown when opened, category-grouped options, and an explicit `创建手工布尔因子` command that emits `create-manual`. Pass `factors` recursively through `RuleConditionNodeEditor`. All field/operator/value edits use helper functions that omit `factor_id`; factor choice emits the canonical bound leaf.

```vue
<StandardFactorPicker
  v-if="nodeKind === 'leaf'"
  :model-value="modelValue"
  :factors="factors"
  @update:model-value="value => emit('update:modelValue', value)"
  @create-manual="emit('create-manual')"
/>
```

```typescript
function chooseFactor(factor: StandardFactorDefinition) {
  emit('update:modelValue', applyStandardFactor(props.modelValue, factor))
  open.value = false
}
```

In `FinalizeRuleCard`, display `label · category` beside the compact recognized rule. Keep `factor_id` only in secondary detail/tooltip text. Reuse the existing Boolean conversion action for `create-manual` so there is one manual-factor implementation.

- [ ] **Step 6: Make registry loading and batch confirmation factor-aware**

In `FinalizeView.vue`, store both values from the one response:

```typescript
const conditionFields = ref<CanonicalConditionField[]>([])
const standardFactors = ref<StandardFactorDefinition[]>([])
const factorCatalogVersion = ref('')

const registry = await getConditionFieldRegistry()
conditionFields.value = registry.fields
standardFactors.value = registry.factors
factorCatalogVersion.value = registry.version
```

Registry load failure must clear all three values, keep user edits, show a retryable fourth-step error, and disable confirm/export. Update `isSafeForBatchRuleConfirmation` so a relation rule remains eligible without factor bindings, a manual Boolean remains eligible, and a standard condition is eligible only when `review.field_registry_version === factorCatalogVersion` and every leaf is uniquely bound.

Pass `standardFactors.value` into `buildCompileRequestFromCards`. Change `buildStaticV2Rules(processes, standardFactors)` so `material.grade in ['9Cr18', '95Cr18']` carries `factor_id: 'material.grade'`, and every CAD/precision/special static leaf obtains its unique ID from `matchingStandardFactors`. Throw a local blocked-review error if a code-owned static leaf has zero or multiple catalog matches; never emit it unbound.

- [ ] **Step 7: Prove `factor_id` survives fourth-step compile DTO construction**

```typescript
it('preserves standard factor ids in the V2 compile request', () => {
  const item = finalizeItem({
    conditionReview: confirmedReview({
      field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
    }),
  })
  const request = buildCompileRequestFromCards(compileArgs([item], factors))
  const userRule = request.rules!.find(rule => rule.source === 'user_confirmed')!
  expect(userRule.when).toEqual({
    field: 'precision.grades', op: 'contains', value: '孔精加工', factor_id: 'precision.hole_finish',
  })
})
```

Define `confirmedReview` and `compileArgs` as local test helpers beside the existing `finalizeItem`/`baseConditionFields` helpers; they fill the current confirmed metadata and existing builder arguments, including `standardFactors`. Update existing fixture candidates with valid IDs. Do not add an ID to manual Boolean fixtures. Add a recursive assertion over `request.rules`: every non-manual leaf, including `system_static` leaves, has a factor ID; every manual `project_factor.manual_process_*` leaf does not.

- [ ] **Step 8: Run all focused frontend tests and the type-aware production build**

```powershell
npm test -- --run src/utils/standardFactorBindings.spec.ts src/components/finalize/StandardFactorPicker.spec.ts src/utils/finalizeRulePackage.spec.ts
npm run build
```

Expected: PASS.

- [ ] **Step 9: Commit the fourth-step factor UI**

```powershell
git add process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/utils/standardFactorBindings.ts process-plan-agent-ui/src/utils/standardFactorBindings.spec.ts process-plan-agent-ui/src/components/finalize/StandardFactorPicker.vue process-plan-agent-ui/src/components/finalize/StandardFactorPicker.spec.ts process-plan-agent-ui/src/components/finalize/RuleConditionNodeEditor.vue process-plan-agent-ui/src/components/finalize/FinalizeRuleCard.vue process-plan-agent-ui/src/composables/finalizeViewHelpers.ts process-plan-agent-ui/src/utils/finalizeRulePackage.ts process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts process-plan-agent-ui/src/views/FinalizeView.vue
git commit -m "feat: confirm standard factors in fourth step"
```

### Task 4: Fixed KmAI Adapter and Snapshot-Only Historical Replay

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py:255-305`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_export.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/lifecycle.py`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py:93-105,132-155`
- Modify: `process-plan-agent-api/app/routers/extract.py:56-70,460-570`
- Test: `process-plan-agent-api/tests/test_kmai_rule_package_export.py`
- Test: `process-plan-agent-api/tests/test_kmai_compatibility_runner.py`
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`

**Interfaces:**
- Changes: `build_kmai_compatibility_export(package, *, legacy_mapping_snapshot: Sequence[LegacyFactorAdapterEntry] | None = None, max_combinations=None, max_condition_objects=None) -> KmaiCompatibilityExport`.
- Produces: `legacy_mapping_snapshot_from_validation_report(raw_json: str | None) -> list[LegacyFactorAdapterEntry]`.
- Changes: `compare_kmai_v1(package: RulePackageV2, inputs: dict[str, Any], *, legacy_mapping_snapshot: Sequence[LegacyFactorAdapterEntry] | None = None) -> dict[str, Any]`; no database registry object.
- Changes: `KmaiCompatibilityExport` replaces `mapping_signature` and `mapping_usages` with `factor_catalog_version`.
- New packages store `validation_report.kmai_compatibility.factor_catalog_version` only.
- Preserves: the existing KmAI factor schema IDs/keys and factor-expansion rules, including `has_center_through_hole`; that KmAI-only computation remains available but is not a selectable ProcessMind standard factor.

- [ ] **Step 1: Replace mapping-oriented exporter tests with failing fixed-ID tests**

```python
def test_fixed_export_uses_factor_id_not_source_value_mapping(rule_package_v2):
    rule = rule_package_v2.route_rules.rules[0]
    rule.when = ConditionNode(
        field="precision.grades", op="contains", value="孔精加工",
        factor_id="precision.hole_finish",
    )
    exported = build_kmai_compatibility_export(rule_package_v2)
    condition = exported.files["route_rules.json"]["rules"][0]["when"]["all"][0]
    assert condition == {"factor_key": "has_hole_finish_machining", "op": "=", "value": True}
    assert exported.factor_catalog_version == STANDARD_FACTOR_CATALOG_VERSION


def test_unbound_or_mismatched_leaf_is_blocked_instead_of_requesting_mapping(rule_package_v2):
    rule_package_v2.route_rules.rules[0].when = ConditionNode(
        field="precision.grades", op="contains", value="孔精加工",
    )
    exported = build_kmai_compatibility_export(rule_package_v2)
    assert exported.valid is False
    assert [issue.code for issue in exported.errors] == ["standard_factor_unbound"]
    assert all(issue.code != "kmai_mapping_required" for issue in exported.errors)
```

Add a mismatched-ID assertion for the old bad mapping (`孔精加工` with `feature.center_hole_location`) and a manual Boolean assertion that export remains valid, emits a `kmai_manual_override_required` warning, and defines a Boolean factor for `manual.factor_overrides`.

- [ ] **Step 2: Run the exporter tests and verify they fail on registry-based behavior**

```powershell
python -m pytest tests/test_kmai_rule_package_export.py -k "fixed or unbound or manual" -v
```

Expected: FAIL because the exporter resolves source values through `KmaiMappingRegistry` and emits `kmai_mapping_required`.

- [ ] **Step 3: Refactor leaf conversion around standard-factor definitions**

Use the bound definition as the only current-package adapter source:

```python
definition = standard_factor_map().get(node.factor_id or "")
if definition is None:
    raise StandardFactorExportError("standard_factor_unbound", node.factor_id or "")
binding_issues = validate_factor_bindings(node)
if binding_issues:
    raise StandardFactorExportError("standard_factor_mismatch", binding_issues[0].message)
if definition.kmai_value_mode == "presence":
    return [[{"factor_key": definition.kmai_factor_key, "op": "=", "value": True}]]
return [[{
    "factor_key": definition.kmai_factor_key,
    "op": _OPERATOR_MAP[node.op],
    "value": node.value,
}]]
```

Keep DNF expansion limits and process/action conversion unchanged. Scalar definitions with `runtime_source="manual_override"` are added to factor schema deterministically and emit warnings. Manual project Boolean fields still use their stable field-derived factor key and the same warning/README contract.

Move `BUILTIN_FACTOR_SPECS` out of the soon-to-be-deleted mapping registry into the fixed adapter module without changing its F001-F026 IDs, names, categories, or value types. Keep `has_center_through_hole` and its existing factor-expansion rule in this internal KmAI schema, but do not add it to the fourth-step standard-factor catalog.

- [ ] **Step 4: Stop current compile/save from reading or writing mapping data**

Remove `load_effective_mapping_registry()` from compile and save, remove `record_mapping_usage()`, and call `build_kmai_compatibility_export(package)` directly. Persist:

```python
server_validation["kmai_compatibility"] = {
    "factor_catalog_version": kmai_compatibility.factor_catalog_version,
}
```

Add a lifecycle test that inserts a contradictory active mapping row, compiles/saves `precision.grades=孔精加工`, and still receives `has_hole_finish_machining`. Assert no new usage row is created.

- [ ] **Step 5: Add failing historical snapshot replay tests**

```python
def test_historical_compatibility_uses_snapshot_embedded_in_package(lifecycle_client, legacy_published_package):
    snapshot = [{
        "mapping_identity": "project:7", "revision": 3, "scope": "project", "project_id": 12,
        "source_field": "cad.features", "source_value": "槽类特征",
        "mapping_mode": "existing_factor", "target_factor_key": "requires_honing",
        "target_factor_name": "珩孔要求", "target_factor_category": "precision",
    }]
    legacy_published_package.validation_report_json = json.dumps({
        "kmai_compatibility": {"mapping_snapshot": snapshot}
    })
    response = lifecycle_client.post("/api/extract/finalized-rule-packages/compatibility-test", json={
        "project_id": 12,
        "inputs": {"cad": {"features": ["槽类特征"]}},
    })
    assert response.status_code == 200
    assert response.json()["manual_factors"]["requires_honing"] is True
```

Change the live mapping row after publishing and assert the result is unchanged. Add an older-package test with no snapshot that resolves only the six fixed legacy built-ins; an unknown old value must remain blocked.

- [ ] **Step 6: Implement read-only legacy replay without exposing it to new packages**

Define `LegacyFactorAdapterEntry` as an internal frozen dataclass with source field/value, mapping mode, target key, target name, and target category. Parse only `validation_report_json.kmai_compatibility.mapping_snapshot`; ignore identity/revision/scope during execution. `build_kmai_compatibility_export` may use this adapter only when a leaf has no `factor_id` and the explicit `legacy_mapping_snapshot` argument is present. A historical `manual_factor` entry must recreate its captured Boolean factor definition exactly; an `existing_factor` entry must reference the unchanged fixed KmAI schema. New compile/save never passes this argument.

In `kmai_compatibility_runner._manual_factors`, evaluate current bound factors from their standard definitions: presence factors become true when the ProcessMind input list contains `canonical_value`; condition-value factors receive the resolved scalar input. Resolve scalar/manual-project inputs during the in-process simulation exactly as today and keep reporting missing or invalid `manual.factor_overrides` values. Historical unbound leaves use only the explicit legacy adapter supplied by the package report.

```python
@dataclass(frozen=True)
class LegacyFactorAdapterEntry:
    source_field: str
    source_value: str
    mapping_mode: Literal["existing_factor", "manual_factor"]
    target_factor_key: str
    target_factor_name: str
    target_factor_category: str


def legacy_mapping_snapshot_from_validation_report(raw_json: str | None) -> list[LegacyFactorAdapterEntry]:
    report = json.loads(raw_json or "{}")
    snapshots = report.get("kmai_compatibility", {}).get("mapping_snapshot", [])
    if not isinstance(snapshots, list):
        return []
    entries: list[LegacyFactorAdapterEntry] = []
    for item in snapshots:
        mode = str(item["mapping_mode"])
        if mode not in {"existing_factor", "manual_factor"}:
            raise ValueError(f"unsupported historical mapping mode: {mode}")
        entries.append(LegacyFactorAdapterEntry(
            source_field=str(item["source_field"]),
            source_value=str(item["source_value"]),
            mapping_mode=cast(Literal["existing_factor", "manual_factor"], mode),
            target_factor_key=str(item["target_factor_key"]),
            target_factor_name=str(item["target_factor_name"]),
            target_factor_category=str(item["target_factor_category"]),
        ))
    return entries
```

Until Task 7 removes the tables, `lifecycle.py` may temporarily fall back to usage rows only when the report snapshot is missing. Keep the fallback isolated in `load_legacy_mapping_snapshot_for_package`; Task 7 must delete it after the transactional backfill.

- [ ] **Step 7: Run exporter, compatibility, and lifecycle tests**

```powershell
python -m pytest tests/test_kmai_rule_package_export.py tests/test_kmai_compatibility_runner.py tests/test_rule_package_lifecycle.py -v
```

Expected: PASS.

- [ ] **Step 8: Commit the fixed adapter**

```powershell
git add process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/kmai_export.py process-plan-agent-api/app/services/rule_packages/kmai_compatibility_runner.py process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/app/routers/extract.py process-plan-agent-api/tests/test_kmai_rule_package_export.py process-plan-agent-api/tests/test_kmai_compatibility_runner.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
git commit -m "refactor: export through fixed factor adapter"
```

### Task 5: Manual Boolean Conflict Regression Fix

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/validator.py:90-235`
- Test: `process-plan-agent-api/tests/test_rule_package_v2.py`
- Test: `process-plan-agent-api/tests/test_rule_package_api.py`
- Test: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`

**Interfaces:**
- Produces: `_is_mutually_exclusive_manual_pair(include_rule: RuleV2, exclude_rule: RuleV2, process_id: str, manual_field_keys: set[str]) -> bool`.
- Changes: opposing-action collection retains rule objects, not only IDs, so exact pairs can be inspected.
- Preserves: every non-exempt same-priority include/exclude conflict still emits `same_priority_action_conflict`.

- [ ] **Step 1: Add failing paired-manual regression tests**

Parameterize the four affected switch labels/processes: 淬火、渗氮、无损检查、去毛刺. For each, build the two rules emitted by `finalizeRulePackage.ts`:

```python
@pytest.mark.parametrize("process_id", [
    "process_quench", "process_nitriding", "process_ndt", "process_deburr",
])
def test_confirmed_manual_true_false_pair_is_not_a_conflict(package_factory, process_id):
    package = package_factory.with_manual_pair(process_id)
    report = validate_rule_package(package)
    assert "same_priority_action_conflict" not in [issue.code for issue in report.errors]
    yes_plan = plan_route(package, {"project_factor": {package_factory.manual_suffix(process_id): True}})
    no_plan = plan_route(package, {"project_factor": {package_factory.manual_suffix(process_id): False}})
    assert process_id in yes_plan.selected_process_ids
    assert process_id not in no_plan.selected_process_ids
```

- [ ] **Step 2: Add failing negative tests for every exemption boundary**

Keep conflict errors when any one property differs: field, source segment, priority, target process, source not `user_confirmed`, true branch also has another condition, false branch is not `eq false`, or actions are not exact include/exclude opposites. Assert the error code and process ID in every case.

- [ ] **Step 3: Run the focused tests and verify the current false conflict**

```powershell
python -m pytest tests/test_rule_package_v2.py -k "manual and conflict" -v
```

Expected: the valid pair FAILS with `same_priority_action_conflict`; negative controls continue to pass.

- [ ] **Step 4: Implement the exact pair predicate**

The predicate returns true only when:

```python
same_audit_source = (
    include_rule.source == exclude_rule.source == "user_confirmed"
    and include_rule.source_segment_id
    and include_rule.source_segment_id == exclude_rule.source_segment_id
)
same_priority = include_rule.priority == exclude_rule.priority
true_leaf = _sole_boolean_leaf(include_rule.when) == (manual_field, True)
false_leaf = _sole_boolean_leaf(exclude_rule.when) == (manual_field, False)
opposite_actions = (
    include_rule.then.include_process_ids == [process_id]
    and include_rule.then.exclude_process_ids == []
    and exclude_rule.then.include_process_ids == []
    and exclude_rule.then.exclude_process_ids == [process_id]
)
```

`_sole_boolean_leaf` accepts only a direct `eq` leaf; it must reject `all/any/not`, preventing an exemption when extra conditions could overlap.

- [ ] **Step 5: Verify frontend generation still emits the exact accepted shape**

Extend the existing manual Boolean test to assert both rules have the same source segment and priority, `true` includes exactly one process, and `false` excludes exactly that process.

- [ ] **Step 6: Run backend and frontend regression tests**

```powershell
python -m pytest tests/test_rule_package_v2.py tests/test_rule_package_api.py -v
npm test -- --run src/utils/finalizeRulePackage.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Commit the conflict fix**

```powershell
git add process-plan-agent-api/app/services/rule_packages/validator.py process-plan-agent-api/tests/test_rule_package_v2.py process-plan-agent-api/tests/test_rule_package_api.py process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts
git commit -m "fix: allow mutually exclusive manual rules"
```

### Task 6: Ready/Blocked Export Review and Frontend Mapping Removal

**Files:**
- Create: `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.vue`
- Modify/Move test: `process-plan-agent-ui/src/components/kmai/RulePackageExportReviewDialog.spec.ts` -> `process-plan-agent-ui/src/components/finalize/RulePackageExportReviewDialog.spec.ts`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`
- Modify: `process-plan-agent-ui/src/composables/useRulePackageExportReview.spec.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Modify: `process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.vue`
- Create: `process-plan-agent-ui/src/components/settings/ModelSettingsDrawer.spec.ts`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/api/index.ts`
- Modify: `process-plan-agent-ui/src/components.d.ts`
- Delete all frontend mapping files listed in “Deleted files”.

**Interfaces:**
- Changes: `RulePackageExportReviewStatus = 'ready' | 'blocked'`.
- Produces: `ExportBlockDetail = {code, message, processName, sourceText, sourceSegmentId}`.
- Changes: dialog emits `locate(sourceSegmentId)` for a blocker and `confirmed/cancelled`; it never saves or recompiles mappings.
- Changes: compile happens once per export attempt; only a ready review can proceed to save/download.

- [ ] **Step 1: Rewrite review-state tests to fail until `mapping_required` is removed**

```typescript
it('has only ready and blocked states', () => {
  const ready = buildExportReview(compiled({ validationValid: true, kmaiValid: true }))
  const blocked = buildExportReview(compiled({
    validationValid: true,
    kmaiValid: false,
    errors: [{ code: 'standard_factor_unbound', path: 'route_rules.rules[0].when', message: '未绑定标准因子' }],
  }))
  expect(ready.status).toBe('ready')
  expect(blocked.status).toBe('blocked')
  expect(['ready', 'blocked']).toContain(ready.status)
})
```

Remove mapping-draft mocks and assert `compileRulePackage` is called exactly once whether the review is ready or blocked.

- [ ] **Step 2: Add structured blocker and navigation tests**

```typescript
it('maps a backend rule error back to its fourth-step card', () => {
  const review = buildExportReview(compiledWithRuleError({
    path: 'route_rules.rules[0].when',
    source_segment_id: 'process_hone',
    source_text: '当需要珩孔时，安排珩孔工序',
  }), '项目 A')
  expect(review.details).toEqual([{
    code: 'standard_factor_unbound',
    message: '未绑定标准因子',
    processName: '珩孔',
    sourceText: '当需要珩孔时，安排珩孔工序',
    sourceSegmentId: 'process_hone',
  }])
})
```

Render the dialog and assert the detail button emits/labels “返回第四步处理”. In `FinalizeView`, handle it by setting `onlyPending=true`, assigning `activeSegmentId`, closing the dialog, awaiting `nextTick`, and calling `document.getElementById('finalize-card-' + id)?.scrollIntoView({block:'center'})`.

- [ ] **Step 3: Implement the mapping-free export flow**

Delete `getKmaiMappingIssues`, `isKmaiMappingError`, `mappingIssues`, `allowGlobal`, mapping drafts, save calls, and the compile loop. Status is blocked when either standard validation or KmAI compatibility is invalid. Local registry/card errors use the same structured details shape.

```typescript
export function buildExportReview(
  compiled: CompileRulePackageResponse,
  projectName: string,
): RulePackageExportReview {
  const status: RulePackageExportReviewStatus = (
    compiled.validation.valid && compiled.kmai_compatibility.valid
  ) ? 'ready' : 'blocked'
  return {
    status,
    projectName: projectName || '未命名任务',
    processCount: compiled.package.route_catalog.processes.length,
    ruleCount: compiled.package.route_rules.rules.length
      + (compiled.package.route_rules.process_relations?.length || 0),
    validation: compiled.validation,
    kmaiCompatibility: compiled.kmai_compatibility,
    rulePackage: compiled.package,
    details: buildExportBlockDetails(compiled),
  }
}
```

Keep manual-factor summary and README output. Add visible ready-review text listing manual Boolean factors that need `manual.factor_overrides`; this is informational and does not disable export.

- [ ] **Step 4: Move and simplify the dialog**

Ready state displays “审核通过” and enables “确认导出”. Blocked state displays “审核未通过”, process/source/problem details, a locate action per item, and disables export. Do not render mapping scopes, target-factor menus, promote actions, or save controls.

```vue
<button
  v-for="detail in review.details || []"
  :key="`${detail.code}:${detail.sourceSegmentId}`"
  type="button"
  class="blocker-locate"
  @click="$emit('locate', detail.sourceSegmentId)"
>
  返回第四步处理
</button>
<button type="button" :disabled="review.status !== 'ready'" @click="$emit('confirmed')">
  确认导出
</button>
```

- [ ] **Step 5: Remove the settings entry and mapping client/components**

Make `ModelSettingsDrawer` model-only: remove `activeTab`, tab buttons, dynamic width, project ID dependency if no longer used, mapping-manager import, and mapping-only styles. Its SSR test asserts `模型配置` exists and `KmAI 映射`, `项目映射`, `全局映射`, and `提升为全局` do not.

The remaining existing model-configuration body is unconditional and the width is fixed:

```vue
<el-dialog v-model="visible" width="480px" class="p-settings-dialog">
```

Move `KmaiCompatibilityExport` type to `rulePackages.ts`, update `extract.ts`, and then delete the mapping API/helper/component files. Remove their exports and generated component declaration.

- [ ] **Step 6: Run all affected frontend tests**

```powershell
npm test -- --run src/components/finalize/RulePackageExportReviewDialog.spec.ts src/components/settings/ModelSettingsDrawer.spec.ts src/composables/useFinalizeRulePackageExport.spec.ts src/composables/useRulePackageExportReview.spec.ts
```

Expected: PASS.

- [ ] **Step 7: Run source-removal checks, the full frontend suite, and build**

```powershell
rg -n "mapping_required|KmaiMapping|kmaiFactorMappings|项目映射|全局映射|提升为全局" src
npm test
npm run build
```

Expected: `rg` returns no matches; tests and build PASS.

- [ ] **Step 8: Commit the frontend removal**

```powershell
git add -A process-plan-agent-ui/src
git commit -m "refactor: remove configurable mapping UI"
```

### Task 7: Transactional Historical Backfill and Backend Mapping Removal

**Files:**
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/lifecycle.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/app/routers/projects.py`
- Modify: `process-plan-agent-api/app/main.py`
- Delete: `process-plan-agent-api/app/routers/kmai_factor_mappings.py`
- Delete: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_contracts.py`
- Delete: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_registry.py`
- Delete: `process-plan-agent-api/app/services/rule_packages/kmai_mapping_store.py`
- Modify: `process-plan-agent-api/tests/test_db_startup_safety.py`
- Modify: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Delete: `process-plan-agent-api/tests/test_kmai_factor_mapping_api.py`
- Delete: `process-plan-agent-api/tests/test_kmai_mapping_registry.py`
- Delete: `process-plan-agent-api/tests/test_kmai_mapping_schema.py`

**Interfaces:**
- Produces: `_retire_kmai_mapping_tables(conn) -> None`, called inside the existing `engine.begin()` startup transaction after finalized-package columns exist.
- Changes: ORM metadata no longer contains any mapping table, so `Base.metadata.create_all` cannot recreate one.
- Changes: `load_legacy_mapping_snapshot_for_package` reads only the package report; the temporary usage-table fallback from Task 4 is removed.
- Removes: `/api/kmai-factor-mappings` and every CRUD/storage/registry contract.

- [ ] **Step 1: Replace startup schema tests with failing retirement tests**

Create a legacy SQLite database using raw SQL, including all three tables and a published/superseded package with usage snapshots but no report snapshot. Capture these immutable columns before startup: `manifest_json`, `input_schema_json`, `route_catalog_json`, `route_rules_json`, `test_cases_json`, `rule_report_md`, `content_hash`.

```python
await ensure_project_schema(conn)
tables = {row[0] for row in (await conn.execute(text(
    "SELECT name FROM sqlite_master WHERE type='table'"
))).all()}
assert "kmai_factor_mapping_usages" not in tables
assert "kmai_factor_mapping_events" not in tables
assert "kmai_factor_mappings" not in tables

report = json.loads((await conn.execute(text(
    "SELECT validation_report_json FROM finalized_rule_packages WHERE id=41"
))).scalar_one())
assert report["kmai_compatibility"]["mapping_snapshot"] == expected_snapshots
assert await read_business_columns(conn, 41) == before_business_columns
```

- [ ] **Step 2: Add failure/rollback tests before implementing the migration**

Seed malformed `mapping_snapshot_json` and separately seed a usage row whose package is missing. Run startup inside a transaction and assert it raises. Open a new connection and prove all three legacy tables and the original `validation_report_json` still exist unchanged.

Also test:

- existing non-empty package snapshot is preserved, not overwritten;
- multiple usage rows are sorted by usage `id` and copied exactly;
- repeated startup on an already-clean database is a no-op;
- fresh startup never creates any mapping table.

- [ ] **Step 3: Run the startup tests and verify old code recreates the tables**

```powershell
python -m pytest tests/test_db_startup_safety.py -k "kmai or mapping" -v
```

Expected: FAIL because startup currently creates/rebuilds all three mapping tables and does not retire them.

- [ ] **Step 4: Implement transactional backfill, verification, and ordered drop**

Use raw SQL so migration does not keep retired ORM models alive:

```python
async def _retire_kmai_mapping_tables(conn) -> None:
    table_names = await _sqlite_table_names(conn)
    legacy = {
        "kmai_factor_mapping_usages",
        "kmai_factor_mapping_events",
        "kmai_factor_mappings",
    }
    if not (legacy & table_names):
        return
    if not legacy <= table_names:
        raise RuntimeError("KmAI mapping tables are only partially present; refusing destructive cleanup")

    rows = (await conn.execute(text("""
        SELECT usage.id, usage.package_id, usage.mapping_snapshot_json,
               package.validation_report_json
        FROM kmai_factor_mapping_usages AS usage
        LEFT JOIN finalized_rule_packages AS package ON package.id = usage.package_id
        ORDER BY usage.package_id, usage.id
    """))).mappings().all()
    grouped = _validated_usage_snapshots(rows)
    await _backfill_missing_package_snapshots(conn, grouped)
    await _verify_package_snapshots(conn, grouped)
    await conn.execute(text("DROP TABLE kmai_factor_mapping_usages"))
    await conn.execute(text("DROP TABLE kmai_factor_mapping_events"))
    await conn.execute(text("DROP TABLE kmai_factor_mappings"))
```

`_validated_usage_snapshots` must JSON-decode every usage, reject non-object payloads and orphan package IDs, and retain the complete immutable snapshot object. `_backfill_missing_package_snapshots` only updates when `mapping_snapshot` is missing or empty. `_verify_package_snapshots` re-reads each affected package and requires a non-empty list exactly equal to the usage snapshot list when backfilled. Let any exception escape `ensure_project_schema`; the surrounding startup transaction performs rollback.

Delete the old create/index/rebuild statements. Insert a `schema_migrations` record named `retire_kmai_factor_mappings_v1` only after verification and drops succeed.

- [ ] **Step 5: Remove ORM, router, store, and project-delete dependencies**

Delete `Project.kmai_factor_mappings`, `FinalizedRulePackage.kmai_mapping_usages`, all three mapping ORM classes, router registration, imports, and project-specific mapping deletion. Delete the four retired backend modules and three subsystem test files. Remove `KmaiMappingUsageSnapshot`, mapping detail fields, and any remaining mapping signature/usage types from contracts.

In `lifecycle.py`, remove all usage-table imports/queries. Historical replay now calls only:

```python
def load_legacy_mapping_snapshot_for_package(row: FinalizedRulePackage):
    return legacy_mapping_snapshot_from_validation_report(row.validation_report_json)
```

- [ ] **Step 6: Add the removed-route regression assertion**

```python
def test_retired_mapping_api_is_not_registered(client):
    assert client.get("/api/kmai-factor-mappings").status_code == 404
    assert client.post("/api/kmai-factor-mappings", json={}).status_code == 404
```

Keep this in `test_rule_package_api.py` or `test_db_startup_safety.py`; do not retain a CRUD test module for a deleted subsystem.

- [ ] **Step 7: Run backend removal checks and focused tests**

```powershell
rg -n "kmai_factor_mapping|KmaiFactorMapping|mapping_required|mapping_signature|mapping_usages" app tests
python -m pytest tests/test_db_startup_safety.py tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_kmai_rule_package_export.py tests/test_kmai_compatibility_runner.py -v
```

Expected: `rg` has no application matches; only deliberate legacy table-name strings inside the one migration/test may remain. Focused tests PASS.

- [ ] **Step 8: Verify startup twice against a copied legacy database fixture**

Run `init_db()` twice using the test fixture database URL. After each call assert the application can query projects and finalized packages, and all mapping tables remain absent. Never run this destructive migration against the workspace’s real `data/*.db` during development verification.

- [ ] **Step 9: Commit backend/data removal**

```powershell
git add -A process-plan-agent-api/app process-plan-agent-api/tests
git commit -m "refactor: retire dynamic factor mappings"
```

### Task 8: End-to-End Acceptance

**Files:**
- Test/Modify: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Test/Modify: `process-plan-agent-api/tests/test_rule_package_api.py`
- Test/Modify: `process-plan-agent-api/tests/test_rule_package_v2.py`
- Test/Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`
- Test: full backend and frontend suites

**Interfaces:**
- Verifies the complete user journey and deletion boundary; produces no new product abstraction.

- [ ] **Step 1: Add/finish one backend integration test for the confirmed journey**

The test must:

1. load `/condition-fields` and select `precision.hole_finish`;
2. confirm a fourth-step condition carrying that ID;
3. compile and save without any mapping API call or table;
4. assert KmAI route condition uses `has_hole_finish_machining`;
5. assert the saved validation report contains `factor_catalog_version` and no mapping identity/scope/revision/signature.

- [ ] **Step 2: Add/finish the unknown-value integration test**

Parse/submit `precision.grades contains 自定义精加工`, prove automatic/batch confirmation is refused, then prove direct compile/save returns a factor-binding error. The test must not call a retired mapping endpoint as a workaround.

- [ ] **Step 3: Add/finish the four-switch integration regression**

Compile the exact paired rules for 淬火、渗氮、无损检查、去毛刺, validate the package, and run true/false plans for each. Assert each true branch includes and each false branch excludes only its own process.

- [ ] **Step 4: Run complete backend verification**

```powershell
python -m pytest -q
```

Expected: all backend tests PASS with no skipped failure related to removed mappings.

- [ ] **Step 5: Run complete frontend verification**

```powershell
npm test
npm run build
```

Expected: all Vitest tests PASS; `vue-tsc -b` and Vite production build PASS.

- [ ] **Step 6: Run final deletion and contract scans**

From repository root:

```powershell
rg -n "mapping_required|KmaiMappingManager|kmaiFactorMappings|load_effective_mapping_registry|record_mapping_usage" process-plan-agent-api process-plan-agent-ui
rg -n "孔精加工.*has_center_through_hole|has_center_through_hole.*孔精加工" process-plan-agent-api process-plan-agent-ui
rg -n "factor_id|factor_catalog_version|manual.factor_overrides" process-plan-agent-api process-plan-agent-ui
git status --short
```

Expected: the first two scans return no matches; the third shows the intended contracts/tests/UI; status contains only the deliberate implementation changes.

- [ ] **Step 7: Manually exercise the fourth-step UI at desktop and mobile widths**

Start the existing UI/API development servers. Confirm there is no mapping tab, a rule card shows Chinese factor label/category, search and replacement work without text overlap, an unknown factor blocks review, manual Boolean guidance is visible, a blocker locates its card, and the export dialog has only ready/blocked states. Capture screenshots at 1440×900 and 390×844 and verify controls remain readable and non-overlapping.

- [ ] **Step 8: Commit final acceptance adjustments**

```powershell
git add -A
git commit -m "test: verify fourth-step factor workflow"
```

## Execution Notes

- Execute tasks in order. Task 4 intentionally leaves a temporary historical usage-table fallback; Task 7 removes it only after the transactional backfill exists.
- Do not delete the database tables manually or with a one-off command. The tested startup migration is the product mechanism.
- Do not update fixture package hashes by hand. If a current-package fixture gains `factor_id`, regenerate its expected hash through the repository’s existing hash function; historical-package fixtures must keep their original business payload/hash.
- Keep commits task-scoped. If an existing unrelated user change is present, stage only the paths listed by the current task.
