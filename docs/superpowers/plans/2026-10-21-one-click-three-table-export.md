# 一键导出三表规则包实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在用户点击一次“导出规则包”后，从同一版本的最终路线、模板映射和规则定稿中确定性生成并下载 `factor_table.json`、`full_route_table.json`、`rule_table.json`，其中 `full_route_table` 包含已确认的工序精度。

**Architecture:** 模板映射阶段保存带稳定 process/step ID 的最终路线快照，并把工序阶段精度作为最终路线字段保留。后端发布边界读取同一事务中的路线、映射和规则定稿，编译三张协议表、执行预检并冻结快照；前端只负责调用预检/发布接口和下载冻结快照 ZIP，不在浏览器临时拼接或让模型生成 JSON。

**Tech Stack:** Python 3.8+、FastAPI、SQLAlchemy async、Pydantic、pytest；Vue 3、TypeScript、Vitest、Vite。

**Spec:** `docs/superpowers/specs/2026-10-21-one-click-three-table-export-design.md`

## Global Constraints

- 外部 ZIP 恰含 `factor_table.json`、`full_route_table.json`、`rule_table.json` 三个文件。
- 三张表顶层为数组，使用既有字段、类型、稳定 ID 和引用协议；不输出 V2 包装、审计字段、`technical_requirements` 或 `is_last`。
- `precision` 表示“粗加工/半精加工/精加工/辅助工序”等工序阶段，不从 CAD `feat_rank` 推导。
- 辅助工序的 `steps` 必须为空；加工工序的 `precision` 缺失或未确认必须阻止发布。
- 三张表必须来自同一个冻结的路线版本、模板修订和规则修订；不得将旧规则与实时映射拼接。
- 无法等价表达的规则、未知引用、循环依赖、重复 target 和无效映射必须明确报错，不静默猜测或丢弃。

## Review Focus

- 最终工艺树把加工精度留空时，系统应在映射/发布预检阻止导出，而不是按“精车”等名称猜测；由任务 1 的精度测试覆盖。
- 同名的重复清洗/检验工序必须由稳定 ID 区分，不能被导出合并；由任务 2 的 ID/顺序测试覆盖。
- 发布期间映射或规则版本发生变化时，不能产生半套或混版三表；由任务 3 的快照并发/版本测试覆盖。
- 预检失败时页面不得下载旧快照或部分 ZIP，且错误应定位到路线、映射或规则定稿；由任务 4 的导出 composable 测试覆盖。
- 已发布版本在源数据修改后必须保持可复现；由任务 5 的历史版本和下游引擎测试覆盖。

### Task 1: 在模板映射阶段固定最终路线精度

**Files:**
- Modify: `process-plan-agent-api/app/services/project_group_templates.py: _build_mapping_output, precision handling`
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue: operation header and precision confirmation control`
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.ts: mapping output operation serialization`
- Modify: `process-plan-agent-ui/src/composables/finalRouteSteps.ts: finalProcessMetadata`
- Modify: `process-plan-agent-ui/src/utils/finalizeRulePackage.ts: buildCompileRequestFromCards`
- Test: `process-plan-agent-api/tests/test_project_group_template_api.py`
- Test: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.spec.ts`
- Test: `process-plan-agent-ui/src/composables/finalTemplateMappingOperations.spec.ts`

**Interfaces:**
- Consumes: final route operations with `process_id`, `steps`, `process_type`, and optional `precision`; template mappings with confirmed candidate targets.
- Produces: mapping output rows shaped as `{process_name, process_type, precision, steps, process_id}` with stable step IDs. Structured known route phases prefill precision; unresolved machining precision can be selected and saved in the mapping page; no keyword guesses are used for final-tree input.

- [ ] **Step 1: Write the failing backend tests.** Add cases asserting that explicit `precision: "半精加工"` is preserved, auxiliary operations receive `"辅助工序"`, and explicit final-tree machining operations with empty precision stay unresolved even if their names/steps contain “精”; publication must later block those unresolved rows.
- [ ] **Step 2: Run the focused backend tests and confirm the missing/incorrect behavior.** Run `pytest process-plan-agent-api/tests/test_project_group_template_api.py -k precision -q`.
- [ ] **Step 3: Implement phase mapping and safe persistence.** Preserve explicit precision, map structured phases (`rough`, `semi_finish`, `finish`) to the public labels, set auxiliary precision to `辅助工序`, and keep unknown machining precision empty. Ensure mapping save/read serialization preserves a user-selected precision value. Keep legacy keyword fallback isolated to legacy input only.
- [ ] **Step 4: Add the mapping-page precision control.** In each machining operation header, show a compact selector with `粗加工`、`半精加工`、`精加工`; preselect known structured precision and require a user choice for unknown precision. Auxiliary operations show `辅助工序` as read-only. Persist the selected value through the existing `operations` payload when saving mappings.
- [ ] **Step 5: Write focused frontend tests.** Verify phase-to-label mapping, unknown precision rendering as unresolved, selection updates the operation payload, save/read retains the selected value, and auxiliary precision is not editable.
- [ ] **Step 6: Run focused tests.** Backend: `pytest process-plan-agent-api/tests/test_project_group_template_api.py -k precision -q`; frontend: `npm test -- --run src/components/extract/TemplateGroupMappingDialog.spec.ts src/composables/finalTemplateMappingOperations.spec.ts` from `process-plan-agent-ui`.
- [ ] **Step 7: Commit.** `git add process-plan-agent-api/app/services/project_group_templates.py process-plan-agent-api/tests/test_project_group_template_api.py process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.spec.ts process-plan-agent-ui/src/composables/templateGroupMapping.ts process-plan-agent-ui/src/composables/finalRouteSteps.ts process-plan-agent-ui/src/composables/finalTemplateMappingOperations.spec.ts process-plan-agent-ui/src/utils/finalizeRulePackage.ts && git commit -m "feat: confirm route precision in template mapping"`

### Task 2: 编译并校验三张协议表

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/demo_tables.py`
- Modify: `process-plan-agent-api/app/services/finalized_rule_package_helpers.py`
- Test: `process-plan-agent-api/tests/test_demo_tables.py`

**Interfaces:**
- Consumes: `RulePackageV2`, mapping output from Task 1, and optional confirmed general-step states.
- Produces: `compile_demo_tables(package, mapped_route, step_states) -> {factor_table, full_route_table, rule_table}` and `validate_demo_tables(tables)`, raising `DemoTableError` with `code`, `path`, and `message` for publication blockers.

- [ ] **Step 1: Add failing compiler/validator tests.** Cover exact top-level arrays, field sets, stable IDs, duplicate target detection, unknown references, auxiliary `steps: []`, empty machining precision rejection, and preservation of repeated process names and route order.
- [ ] **Step 2: Run `pytest process-plan-agent-api/tests/test_demo_tables.py -q` and confirm new tests fail.**
- [ ] **Step 3: Implement protocol validation and deterministic compilation.** Keep public table fields limited to the Demo contract; normalize field types/options/source paths; compile rules from confirmed internal rules only; validate every target and factor reference before returning tables.
- [ ] **Step 4: Add same-feature and dependency checks.** Ensure `some` conditions remain grouped by one CAD feature row, `selected_processes` dependencies refer to known process IDs, and unrepresentable internal relations produce a blocking error.
- [ ] **Step 5: Run the full compiler test module.** `pytest process-plan-agent-api/tests/test_demo_tables.py -q` must pass.
- [ ] **Step 6: Commit.** `git add process-plan-agent-api/app/services/rule_packages/demo_tables.py process-plan-agent-api/app/services/finalized_rule_package_helpers.py process-plan-agent-api/tests/test_demo_tables.py && git commit -m "feat: compile and validate public route tables"`

### Task 3: 在发布事务中冻结三表快照

**Files:**
- Modify: `process-plan-agent-api/app/routers/extract.py: precheck and save_finalized_rule_package`
- Modify: `process-plan-agent-api/app/services/finalized_rule_package_helpers.py: compile_publication_snapshot and serialization`
- Modify: `process-plan-agent-api/app/models/models.py` and schema maintenance only if snapshot columns are missing
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`

**Interfaces:**
- Consumes: validated `RulePackageV2`, current project workflow revision, normalized route version, current template mapping revision, and compiler from Task 2.
- Produces: one published `FinalizedRulePackage` containing `demo_tables_json`, `export_sources_json`, and integrity hash; precheck response with blocking items; historical read returning the frozen snapshot.

- [ ] **Step 1: Add lifecycle tests for precision and atomicity.** Assert precheck reports a named machining process with missing precision, publication stores all three tables and source hashes, a changed mapping does not alter an older package, and an exception leaves no published partial snapshot.
- [ ] **Step 2: Run focused lifecycle tests and confirm failures.** `pytest process-plan-agent-api/tests/test_rule_package_lifecycle.py -k "demo_tables or snapshot or precision or atomic" -q`.
- [ ] **Step 3: Implement transaction-bound compilation.** Read route, mapping, and rules from the same database session; compile and validate before inserting the package; persist source revisions and content hash with the three tables; publish only after all data is flushed successfully.
- [ ] **Step 4: Implement historical integrity checks.** On download/read, validate the stored tables and compare the stored hash; return an explicit re-publish error for missing or invalid old snapshots instead of using current mappings.
- [ ] **Step 5: Run the full lifecycle suite.** `pytest process-plan-agent-api/tests/test_rule_package_lifecycle.py -q`.
- [ ] **Step 6: Commit.** `git add process-plan-agent-api/app/routers/extract.py process-plan-agent-api/app/services/finalized_rule_package_helpers.py process-plan-agent-api/app/models/models.py process-plan-agent-api/app/services/db_schema_maintenance.py process-plan-agent-api/tests/test_rule_package_lifecycle.py && git commit -m "feat: freeze three-table publication snapshots"`

### Task 4: 收敛页面为一次点击导出

**Files:**
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts` only if response types are incomplete
- Test: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts`
- Test: relevant `FinalizeView` component test if present, otherwise add a focused view test

**Interfaces:**
- Consumes: existing compile, precheck, save, and `demo_tables` response APIs from Task 3.
- Produces: one `downloadRuleDocument()` action that runs compile → precheck → save/publish → snapshot ZIP, with no client-side recomputation of route or rules.

- [ ] **Step 1: Add failing UI tests.** Cover successful ZIP creation with exactly three filenames; blocked precheck with no download; missing precision blocker shown as an export issue; stale workflow conflict triggering reload; and invalid/missing snapshot refusing download.
- [ ] **Step 2: Run `npm test -- --run src/composables/useFinalizeRulePackageExport.spec.ts` and confirm failures.**
- [ ] **Step 3: Implement the one-click action.** Keep the button disabled while busy; call backend precheck and save; use returned `demo_tables` only; construct a ZIP with `factor_table.json`, `full_route_table.json`, and `rule_table.json`; do not fall back to live mapping data.
- [ ] **Step 4: Surface actionable blockers.** Include process ID/name, precision field, mapping target, or rule path in the error detail and retain the existing navigation to the relevant mapping/rule card.
- [ ] **Step 5: Run frontend focused tests and production build.** `npm test -- --run src/composables/useFinalizeRulePackageExport.spec.ts`; `npm run build`.
- [ ] **Step 6: Commit.** `git add process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.ts process-plan-agent-ui/src/views/FinalizeView.vue process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/composables process-plan-agent-ui/src/utils && git commit -m "feat: expose one-click three-table export"`

### Task 5: 端到端协议与下游引擎验收

**Files:**
- Modify: `process-plan-agent-api/tests/test_demo_tables.py` or add `process-plan-agent-api/tests/test_three_table_export_e2e.py`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeRulePackageExport.spec.ts` only for final response assertions
- Add/maintain: a fixture directory containing the Demo protocol input and expected route, without copying project-specific production data

**Interfaces:**
- Consumes: published ZIP from Task 4 and the external `config_route_engine.py` contract.
- Produces: repeatable evidence that the three files load, preserve precision and order, filter candidates, compute dependencies, and remain stable across repeated downloads.

- [ ] **Step 1: Add the baseline fixture test.** Load the three tables plus input fixture in the real downstream engine and assert route order, process precision, candidate filtering, and final process count against the expected baseline.
- [ ] **Step 2: Add negative-path tests.** Exercise missing precision, unmatched candidate, unknown target, duplicate ID, and same-feature `some` behavior; assert the intended blocker or route result.
- [ ] **Step 3: Add repeatability/history test.** Export twice without changes and compare canonical JSON; edit the source mapping, then assert the old package remains unchanged and a new export has a new source hash/version.
- [ ] **Step 4: Run all required checks.** Backend: `.venv/bin/python -m pytest -q`; frontend: `npm test`; frontend build: `npm run build`; run the downstream engine专项 test with the fixture.
- [ ] **Step 5: Review generated ZIP contents manually.** Verify exactly three files, UTF-8 Chinese text, two-space JSON indentation, no `technical_requirements`, `is_last`, or internal audit fields.
- [ ] **Step 6: Commit verification fixtures and tests.** `git add process-plan-agent-api/tests process-plan-agent-ui/src && git commit -m "test: verify end-to-end three-table export"`

## Execution Order

按 Task 1 → Task 2 → Task 3 → Task 4 → Task 5 顺序执行。每项任务完成自己的测试和提交后再进入下一项；这样精度契约、编译器、事务快照和页面行为可以分别定位问题。

## Definition of Done

用户在规则定稿页点击一次“导出规则包”后，系统能从已保存且同版本的数据生成一个包含三个固定 JSON 文件的 ZIP。加工工序的精度来自已确认的最终路线；缺失精度、未确认规则或不可表达条件会在下载前阻止并定位。ZIP 可被目标路线引擎加载，重复导出内容稳定，历史版本不受后续编辑影响。
