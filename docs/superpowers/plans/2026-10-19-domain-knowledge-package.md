# Domain Knowledge Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn uploaded domain reference material into reviewed, versioned knowledge packages that can improve route merging and rule analysis with traceable evidence while keeping fifth-step execution deterministic.

**Architecture:** Add immutable knowledge-package versions with typed resources, source locators, and review states. Parse uploaded Markdown into AI-assisted drafts, require human review before activation, then retrieve only applicable reviewed records for steps two and three. Bind route snapshots and compiled V2 packages to the exact knowledge-package version and hash they used.

**Tech Stack:** FastAPI, Pydantic v2, SQLAlchemy async SQLite schema maintenance, Vue 3, TypeScript, Vitest, pytest.

**Spec:** `docs/superpowers/specs/2026-10-19-domain-knowledge-package-design.md`

## Global Constraints

- “规则执行保持确定性。大模型可用于抽取、归一候选和解释；发布规则由 V2 条件引擎和路线规划器执行。”
- “AI 提取内容不得自动成为全局硬规则。草稿需经过结构校验和人工审核，再以不可变版本启用。”
- “区分样本事实与领域知识。”
- “每条知识都带适用范围和来源。”
- “不要求首期建设完整知识图谱平台。”
- “领域知识可以帮助解释或提出条件，但不能单独证明某工序在项目样本中‘总是出现’。”
- “领域包更新不会静默改变已发布路线生成行为；需经重新分析、审核和发布后才生效。”
- Preserve all pre-existing worktree changes; the repository is dirty and includes in-progress knowledge API/UI work that must be extended rather than replaced.
- Treat uploaded document contents as data, never as executable instructions.

## Review Focus

- Missing or malformed source locators must remain visible and must prevent activation of records that require provenance; pin this in Task 2 import validation tests.
- A part-family or process-scope mismatch must return no applicable knowledge and must not change step-two suggestions; pin this in Task 4 retrieval tests.
- Switching package versions must produce a different route-merge signature and mark dependent analysis stale while preserving reviewed history; pin this in Task 5 invalidation tests.
- Sample evidence and domain-package evidence must be separately typed and displayed; pin this in Tasks 4 and 6 tests.
- Draft or rejected package rules must never enter a compiled or published V2 package; pin this in Task 6 lifecycle tests.

---

### Task 1: Define typed package resources and immutable version persistence

**Files:**
- Create: `process-plan-agent-api/app/services/domain_knowledge/contracts.py`
- Create: `process-plan-agent-api/app/services/domain_knowledge/registry.py`
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Create: `process-plan-agent-api/app/services/domain_knowledge/packages.py`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_contracts.py`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_packages_api.py`

**Interfaces:**
- `DomainKnowledgePackageDraft` contains `package_id`, `name`, `domain`, `part_family_scope`, `sources`, and typed `concepts`, `relations`, `factors`, `rule_candidates`, and `route_templates`.
- Every resource has a stable `id`, `applicability`, `source_refs`, and `review_status`; `source_refs` identify a source file hash and Markdown heading plus optional line range.
- `DomainKnowledgePackageVersion` persists `package_id`, monotonically increasing `version`, `status`, `content_hash`, `manifest_json`, `resources_json`, `created_at`, and `activated_at`.
- `create_package_draft(db, draft) -> DomainKnowledgePackageVersion`, `get_package_version(db, package_id, version)`, and `activate_package_version(db, package_id, version) -> DomainKnowledgePackageVersion` are the persistence boundary.
- Package versions are immutable after activation; updates create a new draft version. Only one version per package may be active at a time.

- [ ] **Step 1: Write contract and lifecycle tests**

```python
def test_package_resource_requires_stable_id_scope_and_source_ref():
    with pytest.raises(ValidationError):
        DomainKnowledgeResource.model_validate({"name": "真空淬火"})

def test_activated_version_is_immutable_and_new_draft_increments_version(client):
    first = create_and_activate(client, package_id="machining")
    response = client.patch(f"/api/domain-knowledge/packages/machining/versions/{first['version']}", json={"name": "改名"})
    assert response.status_code == 409
    second = client.post("/api/domain-knowledge/packages/machining/versions", json=valid_draft())
    assert second.json()["version"] == first["version"] + 1

def test_activation_rejects_a_resource_without_a_valid_source_ref(client):
    draft = create_draft_with_missing_source_ref(client)
    response = client.post(f"/api/domain-knowledge/packages/{draft['package_id']}/versions/{draft['version']}/activate")
    assert response.status_code == 422
```

- [ ] **Step 2: Run tests and verify they fail for missing contracts and endpoints**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_contracts.py tests/test_domain_knowledge_packages_api.py -q`

Expected: FAIL because the new contract, tables, and API do not exist.

- [ ] **Step 3: Implement Pydantic contracts and persistence**

Create the `domain_knowledge` module. Add package-version and source-document tables with unique `(package_id, version)` and content-hash indexes; use `ensure_project_schema()` for existing databases. Compute the content hash from canonical JSON using sorted keys and compact separators. Reject edits to active versions and validate that activation includes only reviewed resources with valid source references.

- [ ] **Step 4: Add package draft, list, detail, and activate routes**

Add `POST /api/domain-knowledge/packages`, `GET /api/domain-knowledge/packages`, `GET /api/domain-knowledge/packages/{package_id}/versions/{version}`, `POST /api/domain-knowledge/packages/{package_id}/versions`, `PATCH /api/domain-knowledge/packages/{package_id}/versions/{version}/resources/{resource_id}`, and `POST /api/domain-knowledge/packages/{package_id}/versions/{version}/activate` to a new `app/routers/domain_knowledge.py`; mount the router in `app/main.py`. The resource patch route accepts changes only for draft versions and supports `accepted`, `rejected`, and `needs_review` review states.

- [ ] **Step 5: Re-run focused backend tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_contracts.py tests/test_domain_knowledge_packages_api.py tests/test_db_startup_safety.py -q`

Expected: PASS, including startup migration against an existing schema.

### Task 2: Import reference files and create source-linked AI drafts

**Files:**
- Create: `process-plan-agent-api/app/services/domain_knowledge/importer.py`
- Create: `process-plan-agent-api/app/services/domain_knowledge/draft_generator.py`
- Modify: `process-plan-agent-api/app/routers/domain_knowledge.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/requirements.txt`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_import_api.py`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_importer.py`

**Interfaces:**
- `parse_markdown_source(filename: str, content: bytes) -> ParsedKnowledgeSource` returns UTF-8 text, SHA-256, headings, blocks, and line locators; invalid UTF-8 returns a per-file error, not a partially trusted source.
- `generate_package_draft(sources: list[ParsedKnowledgeSource], *, package_id: str, domain: str, part_family_scope: list[str]) -> DomainKnowledgePackageDraft` uses the configured LLM structured-output path and validates every generated source reference against the parsed source index.
- `POST /api/domain-knowledge/packages/{package_id}/imports` accepts multipart Markdown files or one `.7z` archive containing Markdown plus package scope and returns an import job/result with file status, source hashes, extracted draft, validation issues, and counts by resource type.
- AI output is stored as `draft`; failed or ungrounded records remain visible with a reason and cannot pass activation validation.

- [ ] **Step 1: Write importer tests for locator fidelity and invalid input**

```python
def test_markdown_parser_preserves_heading_and_line_locator():
    parsed = parse_markdown_source("rules.md", b"# Heat\n\n## Vacuum quench\n56 HRC\n")
    assert parsed.blocks[0].heading_path == ["Heat", "Vacuum quench"]
    assert parsed.blocks[0].start_line == 4

def test_import_rejects_bad_encoding_and_unknown_source_reference():
    assert parse_markdown_source("bad.md", b"\xff").status == "failed"
    assert validate_draft_sources(draft_with_unknown_locator(), source_index={}).issues

def test_archive_import_rejects_path_traversal_and_expansion_over_limit():
    traversal = import_7z(make_archive({"../outside.md": b"# unsafe"}))
    oversized = import_7z(make_archive_with_expanded_size(100 * 1024 * 1024 + 1))
    assert traversal.status == "failed"
    assert oversized.status == "failed"
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_importer.py tests/test_domain_knowledge_import_api.py -q`

- [ ] **Step 3: Implement Markdown parsing and structured draft generation**

Parse headings and line ranges without executing embedded content. Reuse the existing configured LLM client and response validation patterns; request JSON matching `DomainKnowledgePackageDraft`, then validate IDs, enums, applicability, and source references locally. Add `py7zr>=0.22,<2` for archive parsing. Extract `.7z` entries in memory or into a bounded temporary directory; reject path traversal, nested archives, files over 20 MB, archives over 100 MB expanded, and non-Markdown entries with per-file status. Send parsed Markdown content, never the archive binary, to the model.

- [ ] **Step 4: Save import results and expose per-file status**

Persist original source metadata and each draft result under a draft version. Return per-file statuses `parsed`, `failed`, or `unsupported`, plus validation issues and source locators. Do not activate any result during import.

- [ ] **Step 5: Run focused import tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_importer.py tests/test_domain_knowledge_import_api.py tests/test_llm_client_config.py -q`

Expected: PASS, with LLM calls mocked in tests and bad locators rejected before persistence.

### Task 3: Add the package review and activation workspace

**Files:**
- Create: `process-plan-agent-ui/src/api/domainKnowledge.ts`
- Create: `process-plan-agent-ui/src/views/DomainKnowledgeView.vue`
- Create: `process-plan-agent-ui/src/components/domainKnowledge/SourceReviewTable.vue`
- Create: `process-plan-agent-ui/src/components/domainKnowledge/ResourceReviewEditor.vue`
- Modify: `process-plan-agent-ui/src/router/index.ts`
- Modify: `process-plan-agent-ui/src/App.vue`
- Test: `process-plan-agent-ui/src/api/domainKnowledge.spec.ts`
- Test: `process-plan-agent-ui/src/views/DomainKnowledgeView.spec.ts`

**Interfaces:**
- `DomainKnowledgeApi` provides `listPackages()`, `getPackageVersion(packageId, version)`, `uploadSources(packageId, scope, files)`, `updateDraftResource(packageId, version, resourceId, patch)`, and `activateVersion(packageId, version)` using the backend routes from Tasks 1-2.
- The view supports selecting/creating a package, uploading Markdown files or a `.7z` archive, inspecting parse status, editing each typed resource, accepting/rejecting/marking uncertain, and activating only after backend validation succeeds.
- Source filename, hash, heading, and line locator remain visible next to each proposed item.

- [ ] **Step 1: Write UI API and review-flow tests**

```ts
it('uploads selected Markdown files and returns per-file status', async () => {
  await uploadSources('machining', scope, [markdownFile, archiveFile])
  expect(api.post).toHaveBeenCalledWith(expect.stringContaining('/imports'), expect.any(FormData))
})

it('does not activate while required source references are invalid', async () => {
  renderDomainKnowledgeView({ draft: draftWithInvalidSourceRef() })
  await user.click(screen.getByRole('button', { name: '启用版本' }))
  expect(await screen.findByText(/来源定位无效/)).toBeVisible()
  expect(api.activateVersion).not.toHaveBeenCalled()
})
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-ui && npm test -- src/api/domainKnowledge.spec.ts src/views/DomainKnowledgeView.spec.ts`

- [ ] **Step 3: Implement typed API client and review workspace**

Reuse the existing Vue layout and shared form/button styles. Keep resource-type tabs and a source panel; render parsing failures, low-confidence records, duplicate/conflict issues, and review states as explicit data. Activation always calls the server-side validator.

- [ ] **Step 4: Run UI tests and typecheck**

Run: `cd process-plan-agent-ui && npm test -- src/api/domainKnowledge.spec.ts src/views/DomainKnowledgeView.spec.ts && npm run build`

Expected: PASS with no TypeScript build errors.

### Task 4: Retrieve applicable package knowledge in step two and show provenance

**Files:**
- Create: `process-plan-agent-api/app/services/domain_knowledge/retrieval.py`
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/routers/projects.py`
- Modify: `process-plan-agent-api/app/services/route_merge/group_builder.py`
- Modify: `process-plan-agent-api/app/services/route_merge/workspace.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_route_merge.py`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_project_binding.py`
- Create: `process-plan-agent-ui/src/views/ExtractView.spec.ts`

**Interfaces:**
- `retrieve_route_knowledge(package_version: DomainKnowledgePackageVersion | None, operation_names: list[str], part_family: str | None) -> list[RouteKnowledgeEvidence]` returns only active, reviewed, scope-matching concepts, relations, and route templates with source references.
- Project gains nullable `domain_knowledge_package_id` and `domain_knowledge_package_version` fields, and `GET/PUT /api/projects/{project_id}/domain-knowledge-package` reads or sets an active package version. `PUT` rejects draft and unknown versions.
- `set_project_domain_knowledge_package(db, project_id, package_id, version) -> Project` persists the active package selection; full downstream stale-state handling is Task 5.
- Route workspace loads the package version bound to its project; a project with no binding keeps current behavior.
- Extend `route_merge_source_signature(operations, detail_rows, document_source_keys=None, package_hash: str | None = None) -> str`; include the selected package content hash in the canonical payload and persist package ID/version on the snapshot.
- `RouteMergeWorkspaceOut` adds `knowledge_package: {package_id, version, content_hash} | None` and per-suggestion `domain_evidence`; sample evidence fields remain unchanged.
- Package suggestions may explain or annotate candidate merges and separately list optional route-template additions; they never alter coverage counts or masquerade as sample operations.

- [ ] **Step 1: Write route retrieval, scope, provenance, and cache tests**

```python
def test_retrieval_returns_only_reviewed_matching_scope_records(active_package):
    results = retrieve_route_knowledge(active_package, ["精车"], part_family="轴套")
    assert {item.resource_id for item in results} == {"concept.finish_turning"}
    assert all(item.source_refs for item in results)

def test_route_merge_signature_changes_when_package_hash_changes(operations, details):
    base = route_merge_source_signature(operations, details, package_hash="a" * 64)
    changed = route_merge_source_signature(operations, details, package_hash="b" * 64)
    assert base != changed

def test_project_package_binding_rejects_draft_version(client, project, draft_package):
    response = client.put(f"/api/projects/{project.id}/domain-knowledge-package", json={"package_id": draft_package.package_id, "version": draft_package.version})
    assert response.status_code == 409

def test_template_suggestion_does_not_change_sample_coverage(route_workspace):
    assert route_workspace["normalized_superset_route"][0]["coverage_label"] == "2/5"
    assert route_workspace["normalized_superset_route"][0]["domain_evidence"]
```

```ts
it('shows domain evidence separately from the operation sample evidence', () => {
  expect(source).toContain('领域知识依据')
  expect(source).toContain('matched_detail_rows')
  expect(source).toContain('source_refs')
})
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_route_merge.py tests/test_route_merge_document_invalidation.py -q`

- [ ] **Step 3: Implement scoped retrieval and enrich existing candidates**

Do not replace the current `group_builder` heuristics in this phase. Retrieve by stable concept IDs, reviewed aliases, applicability and current part family; attach evidence and reasons to the existing suggestion payload. Keep sample `matched_detail_rows`, `evidence_excerpt`, and `coverage_label` as the factual basis.

- [ ] **Step 4: Render domain evidence separately in step two**

Show a distinct “领域知识依据” section for applicable package items and a distinct optional-template section. If no active package applies, preserve the current workspace behavior and display no domain evidence.

- [ ] **Step 5: Run focused backend and UI tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_route_merge.py tests/test_route_merge_document_invalidation.py -q`

Run: `cd process-plan-agent-ui && npm test -- src/views/ExtractView.spec.ts`

Expected: PASS; package changes rebuild the cached workspace, and sample coverage remains unchanged.

### Task 5: Invalidate dependent work and add the project package selector

**Files:**
- Modify: `process-plan-agent-ui/src/api/projects.ts`
- Modify: `process-plan-agent-ui/src/components/upload/UploadProjectBoard.vue`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_project_binding.py`
- Test: `process-plan-agent-api/tests/test_route_merge_document_invalidation.py`

**Interfaces:**
- Consumes the project binding fields and API from Task 4.
- `set_project_domain_knowledge_package(db, project_id, package_id, version) -> Project` updates the project binding and marks dependent route-merge/analysis artifacts stale without deleting review history.
- Route-merge snapshots persist package ID, version, and content hash alongside `source_signature`.
- Project API returns the selected package reference and supports setting/clearing it; the UI lets a project choose an active package version.

- [ ] **Step 1: Write binding, stale-state, and history-preservation tests**

```python
def test_switching_package_invalidates_current_merge_snapshot_but_preserves_route_history(client, project):
    old_route = save_reviewed_route(project)
    old_snapshot = save_route_merge_snapshot(project, package_hash="a" * 64)
    client.put(f"/api/projects/{project.id}/domain-knowledge-package", json={"package_id": "machining", "version": 2})
    assert current_route_merge_snapshot(project.id).source_signature != old_snapshot.source_signature
    assert get_route_version(old_route.id) is not None
    assert project_analysis_is_stale(project.id)

def test_project_cannot_select_draft_or_unknown_package_version(client, project):
    response = client.put(f"/api/projects/{project.id}/domain-knowledge-package", json={"package_id": "machining", "version": 99})
    assert response.status_code == 404
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_project_binding.py tests/test_route_merge_document_invalidation.py -q`

- [ ] **Step 3: Complete package-switch invalidation**

Use the Task 4 project binding endpoint and existing workflow revision/invalidation conventions. A package switch must change the route-merge signature, mark dependent analysis stale, and preserve old normalized route versions and review records.

- [ ] **Step 4: Add project package selector**

Load active package versions from the Task 1 API, display package name/version, and save or clear the project binding through the project API. Do not allow selecting drafts.

- [ ] **Step 5: Verify project and migration tests**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_project_binding.py tests/test_route_merge_document_invalidation.py tests/test_workflow_invalidation.py tests/test_db_startup_safety.py -q`

### Task 6: Use package evidence in third-step analysis and preserve V2 execution boundary

**Files:**
- Modify: `process-plan-agent-api/app/services/knowledge/suggestions.py`
- Modify: `process-plan-agent-api/app/services/knowledge/service.py`
- Modify: `process-plan-agent-api/app/routers/knowledge.py`
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/compiler.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/hashing.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-ui/src/api/knowledge.ts`
- Modify: `process-plan-agent-ui/src/views/AnalysisView.vue`
- Modify: `process-plan-agent-ui/src/views/KnowledgeView.vue`
- Test: `process-plan-agent-api/tests/test_domain_knowledge_rule_analysis.py`
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`
- Test: `process-plan-agent-ui/src/views/KnowledgeView.spec.ts`

**Interfaces:**
- `KnowledgeRuleSuggestion` gains `domain_evidence_refs_json` and `domain_package_ref_json`; existing `evidence_ids` continue to refer only to project knowledge evidence snapshots.
- `build_domain_rule_candidates(package_version, route_segment, sample_evidence) -> list[DomainRuleCandidate]` returns typed candidate conditions, applicability, domain references, sample references, confidence, and uncertainty; a domain reference alone cannot satisfy required sample evidence.
- The existing draft/confirm/apply flow remains the only path to a V2 condition. Confirmed V2 packages record `domain_package_id`, `domain_package_version`, and `domain_package_hash` in their manifest and content hash.
- No draft, rejected, out-of-scope, or unreferenced package rule is compiled or published.

- [ ] **Step 1: Write rule-analysis evidence separation and V2 lifecycle tests**

```python
def test_domain_candidate_keeps_sample_and_domain_evidence_separate(active_package, route_segment, sample_evidence):
    candidate = build_domain_rule_candidates(active_package, route_segment, sample_evidence)[0]
    assert candidate.domain_evidence_refs
    assert candidate.sample_evidence_refs == sample_evidence.ids

def test_domain_rule_without_matching_sample_evidence_cannot_become_v2_condition(client):
    suggestion = create_suggestion(status="confirmed", sample_evidence_ids=[], domain_evidence_refs=["rule.heat"])
    response = client.post("/api/extract/normalized-route-segments/conditions/draft", json=condition_from(suggestion))
    assert response.status_code == 422

def test_compiled_v2_package_records_domain_package_hash(client, package_version):
    compiled = compile_and_publish(client, package_version=package_version)
    assert compiled["manifest"]["domain_knowledge_package"]["content_hash"] == package_version.content_hash
```

```ts
it('renders sample evidence and domain package references in separate sections', () => {
  expect(source).toContain('样本证据')
  expect(source).toContain('领域知识依据')
  expect(source).toContain('domain_package_ref')
})
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_rule_analysis.py tests/test_knowledge_condition_draft_api.py tests/test_rule_package_lifecycle.py -q`

- [ ] **Step 3: Implement typed candidate assembly and audit metadata**

Reuse existing `KnowledgeEvidenceSnapshot`, `KnowledgeRuleSuggestion`, and condition-draft validation. Add domain references as a separate field and validate package version/status/scope before applying a candidate. Preserve the human-confirmation requirement and compile-time validation. Add package identity to the V2 manifest and content hash without changing the deterministic planner contract.

- [ ] **Step 4: Display evidence classes and package version in third-step review**

Render project-sample evidence and domain-package references in separate sections with source locators. Show the package version used by analysis and a stale indicator when the project binding changes.

- [ ] **Step 5: Run focused and regression suites**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_rule_analysis.py tests/test_knowledge_condition_draft_api.py tests/test_knowledge_suggestions_api.py tests/test_rule_package_lifecycle.py tests/test_rule_package_v2.py -q`

Run: `cd process-plan-agent-ui && npm test -- src/views/KnowledgeView.spec.ts src/components/analysis/KnowledgeEvidenceEntry.spec.ts`

Expected: PASS; V2 generation remains deterministic and reads only the published package and V2 rule package.

### Task 7: Seed the first machining package and validate cross-family extensibility

**Files:**
- Create: `process-plan-agent-api/scripts/import_domain_knowledge_baseline.py`
- Create: `process-plan-agent-api/tests/fixtures/domain_knowledge/machining_baseline_manifest.json`
- Create: `process-plan-agent-api/tests/test_domain_knowledge_cross_family.py`
- Modify: `README.md`

**Interfaces:**
- `import_baseline(directory: Path, package_id: str, dry_run: bool = True) -> BaselineImportReport` imports extracted Markdown files into a draft package and reports omitted, duplicate, conflict, ungrounded, and unsupported records.
- The script never activates a version; activation remains a reviewed API action.
- A fixture package for a different part family can drive route retrieval and rule-candidate generation without adding a family-specific branch to application code.

- [ ] **Step 1: Write baseline completeness and cross-family tests**

```python
def test_baseline_import_reports_all_source_files_and_unreviewed_items(tmp_path):
    for index in range(13):
        (tmp_path / f"baseline-{index}.md").write_text(f"# Section {index}\nExample content {index}\n", encoding="utf-8")
    report = import_baseline(tmp_path, "machining", dry_run=True)
    assert report.source_file_count == 13
    assert report.unreviewed_count > 0
    assert report.activated is False

def test_unrelated_part_family_works_with_configuration_only(second_family_package):
    result = retrieve_route_knowledge(second_family_package, ["rough milling"], part_family="housing")
    assert result
    assert result[0].package_id == second_family_package.package_id
```

- [ ] **Step 2: Verify RED**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_cross_family.py -q`

- [ ] **Step 3: Implement dry-run baseline importer and operator documentation**

Accept extracted Markdown as the input directory; keep source files external to the repository unless the user explicitly places them in a project data directory. Emit a JSON report before writing drafts. Document upload, review, activation, project binding, and package-version reproducibility.

- [ ] **Step 4: Run end-to-end focused suites and repository checks**

Run: `cd process-plan-agent-api && .venv/bin/pytest tests/test_domain_knowledge_*.py tests/test_route_merge_document_invalidation.py tests/test_knowledge_condition_draft_api.py tests/test_rule_package_lifecycle.py -q`

Run: `cd process-plan-agent-ui && npm test && npm run build`

Expected: PASS; the 13-file source baseline imports as a reviewable draft, while a different family can use the same package contract and workflow without new domain-specific branches.
