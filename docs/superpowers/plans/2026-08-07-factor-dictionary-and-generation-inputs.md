# Factor Dictionary and Generation Inputs Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a versioned factor table with every rule package and make fifth-step values auditable, canonical, and explicitly confirmed before production route generation.

**Architecture:** Keep `factor_dictionary` as the complete factor-definition snapshot and `input_schema` as the subset used by executable rules. Preserve primitive, canonical factor values for the deterministic planner while sending input metadata separately for origin, unit, and evidence. The fourth-step compiler owns the dictionary snapshot; the fifth-step form owns user input state and never infers confirmation from defaults.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async SQLite migrations, Vue 3 Composition API, TypeScript, Vitest, pytest.

## Global Constraints

- Do not reintroduce KMAI or V1 compatibility code.
- Preserve existing published V2 packages by treating a missing factor dictionary as the legacy active-field dictionary.
- Never alter or stage unrelated existing worktree changes.
- Production generation accepts only `manual` or `extracted` required values; `example` values remain simulation-only.
- The planner receives canonical primitive factor values only.

---

### Task 1: Add the factor dictionary to the V2 package and persistence layer

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/compiler.py`
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/finalized_rule_package_helpers.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/lifecycle.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/hashing.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Test: `process-plan-agent-api/tests/test_rule_package_api.py`

**Interfaces:**
- Produces `FactorDictionaryV2(schema_version='2.0', fields: list[InputField])`.
- Extends `RulePackageV2.factor_dictionary`, `CompileRulePackageRequest.factor_dictionary`, and persisted `FinalizedRulePackage.factor_dictionary_json`.
- A missing persisted dictionary loads as `InputSchemaV2.fields` for legacy V2 rows only.

- [ ] **Step 1: Write failing API and lifecycle tests**

```python
def test_saved_rule_package_round_trips_its_full_factor_dictionary(client, payload):
    payload['factor_dictionary'] = {
        'schema_version': '2.0',
        'fields': [
            {'key': 'material.grade', 'label': '材料牌号', 'type': 'single_select',
             'options': [{'value': '9Cr18', 'label': '9Cr18'}]},
            {'key': 'geometry.length_mm', 'label': '特征长度', 'type': 'number', 'unit': 'mm'},
        ],
    }
    saved = client.post('/api/extract/finalized-rule-packages', json=payload)
    assert saved.status_code == 200
    assert saved.json()['factor_dictionary'] == payload['factor_dictionary']

def test_legacy_v2_row_uses_input_schema_as_factor_dictionary(row):
    package = v2_package_from_row(row)
    assert package.factor_dictionary.fields == package.input_schema.fields
```

- [ ] **Step 2: Run the focused tests and verify they fail because the field is absent**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py -q`

- [ ] **Step 3: Implement the package and database contract**

```python
class FactorDictionaryV2(StrictModel):
    schema_version: Literal['2.0'] = '2.0'
    fields: list[InputField]

class RulePackageV2(StrictModel):
    manifest: RulePackageManifestV2
    factor_dictionary: FactorDictionaryV2
    input_schema: InputSchemaV2
    # existing route catalog, rules, and tests
```

Add `factor_dictionary_json` with `ensure_column`, serialize it in every API
result, include it in the content hash, and validate that every input-schema
field is a byte-for-byte compatible dictionary definition.

- [ ] **Step 4: Re-run focused tests, then the API package suite**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_rule_package_v2.py -q`

### Task 2: Compile a full fourth-step factor dictionary and preserve compound conditions

**Files:**
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_registry.py`
- Test: `process-plan-agent-ui/src/utils/finalizeRulePackage.spec.ts`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- `buildCompileRequestFromCards()` produces `factor_dictionary` containing all standard definitions and all confirmed dynamic definitions.
- `input_schema.fields` remains the ordered, referenced subset.
- `_parse_locally()` creates an `all` tree when a special requirement and other recognized leaves occur in the same condition.

- [ ] **Step 1: Write failing compiler and parser tests**

```python
@pytest.mark.asyncio
async def test_mixed_material_and_ndt_requirement_preserves_both_leaves():
    candidate, _, _ = await parse_rule_condition(
        '当材料为9Cr18且有无损检测要求时，纳入无损检查工序',
        'process_ndt', '无损检查', [RuleConditionProcessOption(process_id='process_ndt', display_name='无损检查')],
    )
    assert [child.field for child in candidate.when.all_conditions] == [
        'material.grade', 'special.requirements',
    ]
```

```ts
it('exports all confirmed factor definitions but only referenced input fields', () => {
  const request = buildCompileRequestFromCards(/* fixtures with a confirmed but unreferenced field */)
  expect(request.factor_dictionary.fields.map(field => field.key)).toContain('geometry.length_mm')
  expect(request.fields.map(field => field.key)).not.toContain('geometry.length_mm')
})
```

- [ ] **Step 2: Verify the new tests fail**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_condition_parser.py -q`

Run: `cd process-plan-agent-ui && npm test -- src/utils/finalizeRulePackage.spec.ts`

- [ ] **Step 3: Implement complete factor snapshot and compound AST merging**

Keep registry fields under readable semantic keys. Generate dynamic keys from a
normalized label slug with a short deterministic suffix only if a collision is
possible. Combine special-requirement leaves with the ordinary parsed tree in
an `all` node; do not return the special leaf as an alternative shortcut.

- [ ] **Step 4: Run focused tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_condition_parser.py -q`

Run: `cd process-plan-agent-ui && npm test -- src/utils/finalizeRulePackage.spec.ts`

### Task 3: Canonicalize execution inputs and reject ambiguous data

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/input_validation.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/expression_engine.py`
- Modify: `process-plan-agent-api/app/routers/generate.py`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Test: `process-plan-agent-api/tests/test_rule_package_expression.py`
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- `GenerateRequest.input_metadata: dict[str, InputValueMetadata]` where metadata has `origin`, optional canonical `unit`, and `evidence`.
- `canonicalize_inputs(schema, inputs, metadata)` returns canonical nested values plus field errors.
- `validate_inputs()` rejects unrecognized leaf input keys, `example` origins for generation, and non-canonical numeric units.

- [ ] **Step 1: Write failing behavior tests**

```python
def test_alias_is_canonicalized_before_expression_evaluation(schema):
    values, errors = canonicalize_inputs(schema, {'material': {'grade': 'M2'}}, {})
    assert errors == []
    assert values['material']['grade'] == 'W6Mo5Cr4V2'

def test_unknown_factor_key_is_rejected(schema):
    assert validate_inputs(schema, {'material': {'grade': '9Cr18'}, 'unknown': 1})[0].code == 'unknown_input_field'

def test_generate_rejects_example_required_value(api_client):
    response = api_client.post('/api/generate/', json={
        'project_id': 1, 'factor_values': {'material': {'grade': '9Cr18'}},
        'input_metadata': {'material.grade': {'origin': 'example'}},
    })
    assert response.status_code == 422
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_expression.py tests/test_generate_v2_production.py -q`

- [ ] **Step 3: Implement canonical validation before planner execution**

Flatten nested factor-value paths to detect unexpected leaves. Resolve an option
alias to `InputOption.value`; the expression engine therefore receives only
canonical values. Require `input_metadata[field].unit == field.unit` whenever
a numeric field declares a unit. Preserve `input_metadata` on generated
results for audit without changing planner inputs.

- [ ] **Step 4: Verify focused and package tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_expression.py tests/test_generate_v2_production.py tests/test_rule_package_api.py -q`

### Task 4: Replace fifth-step defaults with explicit value state and complete controls

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useGenerateInputFields.ts`
- Modify: `process-plan-agent-ui/src/components/generate/GenerateInputPanel.vue`
- Modify: `process-plan-agent-ui/src/views/GenerateView.vue`
- Modify: `process-plan-agent-ui/src/api/generate.ts`
- Test: `process-plan-agent-ui/src/composables/useGenerateInputFields.spec.ts`

**Interfaces:**
- `fieldStates[key]` is `{ value, origin, evidence, unit? }`.
- `factorValues` contains only fields with `manual` or `extracted` origins.
- `factorMetadata` is keyed by field key and accompanies `factorValues`.

- [ ] **Step 1: Write failing composable tests**

```ts
it('starts single selects and text fields unset instead of choosing examples', () => {
  const fields = createInputFields(selectSchema(['A', 'B']))
  expect(fields.fieldValues.value['material.grade']).toBe('')
  expect(fields.canGenerate.value).toBe(false)
})

it('does not allow an example value to enable generation', () => {
  const fields = createRequiredFields()
  fields.fillExampleValues()
  expect(fields.factorMetadata.value['material.grade'].origin).toBe('example')
  expect(fields.canGenerate.value).toBe(false)
})

it('records a custom single-select value as a manual value', () => {
  const fields = createCustomSelectFields()
  fields.setCustomSelectValue('material.grade', 'Custom Alloy')
  expect(fields.factorValues.value).toEqual({ material: { grade: 'Custom Alloy' } })
})
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-ui && npm test -- src/composables/useGenerateInputFields.spec.ts`

- [ ] **Step 3: Implement state, source labels, and controls**

Initialize every field as unset. Mark user edits as manual, extracted defaults
as extracted, and example-fill actions as example. Show the canonical unit in
numeric controls. Render a custom input below any custom-enabled single
select. Replace the misleading automatic-source copy with the declared source
and actual value status. Send `input_metadata` with the generation request.

- [ ] **Step 4: Verify UI tests and production typecheck**

Run: `cd process-plan-agent-ui && npm test -- src/composables/useGenerateInputFields.spec.ts`

Run: `cd process-plan-agent-ui && npm run build`

### Task 5: Export persisted factor tables and make rule tests meaningful

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts`
- Modify: `process-plan-agent-api/app/services/rule_packages/validator.py`
- Test: `process-plan-agent-api/tests/test_rule_package_v2.py`

**Interfaces:**
- ZIP `factor_table.json` contains `savedPackage.factor_dictionary`.
- `buildRuleTestCases()` returns a baseline case plus one positive case for each enabled conditional rule.
- Validator emits an error when an enabled condition rule lacks a matching test case.

- [ ] **Step 1: Write failing export and coverage tests**

```ts
expect(zipFiles['factor_table.json']).toEqual(savedPackage.factor_dictionary)
```

```python
def test_package_requires_a_test_case_for_each_enabled_condition_rule(package):
    package.test_cases = [package.test_cases[0]]
    report = validate_rule_package(package)
    assert any(issue.code == 'uncovered_conditional_rule' for issue in report.errors)
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-ui && npm test -- src/composables/useFinalizeRulePackageExport.spec.ts`

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_v2.py -q`

- [ ] **Step 3: Implement exports and deterministic positive test cases**

Build each generated case by applying the rule's positive condition values to
the baseline valid input, including numeric thresholds and list-membership
values. Expectations include the rule action's included process IDs. A
validator coverage check evaluates each rule case rather than trusting a case
name alone.

- [ ] **Step 4: Run focused test suites**

Run: `cd process-plan-agent-ui && npm test -- src/composables/useFinalizeRulePackageExport.spec.ts src/utils/finalizeRulePackage.spec.ts`

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_rule_package_v2.py tests/test_rule_package_lifecycle.py -q`

### Task 6: Verify the complete path

**Files:**
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`
- Test: `process-plan-agent-ui/src/composables/useGenerateInputFields.spec.ts`

- [ ] **Step 1: Run all backend tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest -q`

- [ ] **Step 2: Run all frontend tests and build**

Run: `cd process-plan-agent-ui && npm test`

Run: `cd process-plan-agent-ui && npm run build`

- [ ] **Step 3: Perform manual package verification**

Create a rule package with a material-plus-special-requirement rule, export
it, and verify the ZIP includes distinct `factor_table.json`,
`full_route_structure.json`, and `rule_table.json`. In step five confirm that
an unset or example required value disables generation, a manual custom
single-select value enables it, and the generated result carries the submitted
input metadata.

- [ ] **Step 4: Check the final diff**

Run: `git diff --check`
