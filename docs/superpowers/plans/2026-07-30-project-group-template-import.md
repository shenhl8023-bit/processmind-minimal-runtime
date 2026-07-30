# Project-Level Group Template Import Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the hardcoded Bushing-11 mapping tree with a project-owned Kmsoft XML template that is safely parsed, versioned, reused, replaceable, and used as the only legal source of group mapping targets.

**Architecture:** A safe XML parser converts one Kmsoft `Part` into a normalized recursive tree whose stable group keys are derived from normalized full-name paths. A project-scoped database record owns that tree and the formal mapping set behind optimistic `template_revision` checks. The Vue dialog loads that record and moves through `empty`, `preview`, and `workspace` states; deterministic suggestions and the LLM can only select groups present in the confirmed project template.

**Tech Stack:** FastAPI 0.139, SQLAlchemy 2 async, SQLite, Pydantic 2, lxml 6, Vue 3.5, TypeScript 5.9, Axios, Element Plus, Vitest 4, pytest.

## Global Constraints

- Each uploaded XML must contain exactly one `Item type="Part"` and at least one descendant `Item type="Group"`.
- Accept only `.xml` files up to `5 * 1024 * 1024` bytes and support UTF-8, GB2312, and GB18030 input.
- Reject DTD declarations, entity declarations, external entity resolution, invalid roots, missing template sections, unnamed groups, duplicate normalized sibling names, and unknown feature selections.
- Normalize every group-name path component with trim plus Unicode NFC before identity or comparison.
- Compute each stable key from canonical JSON for the normalized path array, using `grp_` plus the first 24 hexadecimal characters of SHA-256; never use the XML `id` as business identity.
- Ordinary users upload only the group XML; the repository-owned `FeatureTemplate.xml` is the legal feature dictionary and its SHA-256 is persisted as `feature_dictionary_version`.
- The first template confirmation must use `expected_template_revision = 0`; every replacement or mapping save must use the latest server revision and return `409` on a stale value.
- Backend project records are the formal source for templates and mappings. Browser storage is draft recovery only.
- Replacing a template migrates mappings only by exact normalized path. Missing paths invalidate mappings and must never be guessed from XML IDs.
- Existing manual mappings are never overwritten by smart mapping. Composite, ambiguous, low-confidence, and unsupported operations remain pending manual review.
- LLM output is advisory and may only select stable keys from candidates generated from the current confirmed template.
- Preserve current second-step route saving, fourth-step rule-package export, and KMAI v1 behavior by retaining compatible alias metadata while adding stable key, group name, path, and feature selections.
- Do not stage `.vscode/`, `outputs/`, or unrelated working-tree changes.

---

## File Structure

### Backend

- Create `process-plan-agent-api/app/assets/group_templates/FeatureTemplate.xml`: version-controlled legal feature dictionary copied byte-for-byte from the approved Kmsoft asset.
- Create `process-plan-agent-api/tests/fixtures/group_templates/*.xml`: portable copies of the five approved real templates used by parser and API tests.
- Create `process-plan-agent-api/app/services/group_template_xml.py`: encoding detection, safe XML parsing, normalization, feature validation, stable keys, and parse result types.
- Create `process-plan-agent-api/app/services/project_group_templates.py`: row serialization, optimistic concurrency, template replacement, path migration, and formal mapping replacement.
- Modify `process-plan-agent-api/app/models/models.py`: add the one-to-one `ProjectGroupTemplate` ORM model and project relationship.
- Modify `process-plan-agent-api/app/services/db_schema_maintenance.py`: explicitly create/index the new table for deployed SQLite databases.
- Modify `process-plan-agent-api/app/schemas/schemas.py`: add template tree, validation, preview, current-template, migration, and mapping contracts; extend alias metadata.
- Modify `process-plan-agent-api/app/routers/extract.py`: expose preview/current/confirm/mapping endpoints and inject the database into template-driven suggestions.
- Modify `process-plan-agent-api/app/services/template_group_mapping.py`: generate and validate candidates exclusively from the confirmed project tree.
- Create `process-plan-agent-api/tests/test_group_template_xml.py`: parser and real-sample coverage.
- Create `process-plan-agent-api/tests/test_project_group_template_api.py`: persistence, replacement, revision, and endpoint coverage.
- Modify `process-plan-agent-api/tests/test_template_group_mapping.py`: project-template candidate and LLM allow-list coverage.
- Modify `process-plan-agent-api/tests/test_template_group_alias_metadata.py`: route/rule-package compatibility assertions for the extended alias fields.

### Frontend

- Modify `process-plan-agent-ui/src/api/extract.ts`: add template contracts and multipart/JSON API clients; remove caller-provided suggestion candidates.
- Create `process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts`: load, preview, confirm, replace, save, and stale-revision state transitions.
- Create `process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts`: composable state and error handling tests with mocked API functions.
- Modify `process-plan-agent-ui/src/composables/templateGroupMapping.ts`: remove the fixed tree, accept dynamic trees, use stable path keys, keep local storage draft-only, and build template-driven candidates.
- Modify `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`: dynamic-tree, migration, feature matching, ambiguity, and draft tests.
- Create `process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue`: recursive tree renderer with feature-selection tags and mapped-operation counts.
- Modify `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`: implement the `empty`, `preview`, and `workspace` states plus replacement impact review.
- Modify `process-plan-agent-ui/src/views/ExtractView.vue`: hydrate formal mappings from the backend, pass legacy paths only for one-time draft migration, and persist saved mappings through the dialog.

---

### Task 1: Safe Kmsoft XML Parser And Feature Dictionary

**Files:**
- Create: `process-plan-agent-api/app/assets/group_templates/FeatureTemplate.xml`
- Create: `process-plan-agent-api/tests/fixtures/group_templates/临时壳体4.xml`
- Create: `process-plan-agent-api/tests/fixtures/group_templates/套筒类(未指定参数).xml`
- Create: `process-plan-agent-api/tests/fixtures/group_templates/套筒类.xml`
- Create: `process-plan-agent-api/tests/fixtures/group_templates/飞机壁板类1.xml`
- Create: `process-plan-agent-api/tests/fixtures/group_templates/新衬套模板.xml`
- Create: `process-plan-agent-api/app/services/group_template_xml.py`
- Create: `process-plan-agent-api/tests/test_group_template_xml.py`

**Interfaces:**
- Produces: `parse_group_template_xml(filename: str, payload: bytes) -> GroupTemplateParseResult`.
- Produces: `GroupTemplateParseResult` with `original_filename`, `source_encoding`, `part_filename`, `content_hash`, `feature_dictionary_version`, `source_xml`, `tree`, `issues`, `group_count`, `feature_selection_count`, and `can_confirm`.
- Produces: normalized node dictionaries with `key`, `source_id`, `name`, `path`, `feature_selections`, `params`, and `children`.

- [ ] **Step 1: Copy the approved feature dictionary into the backend asset directory**

Use `apply_patch` to add the exact contents of:

```text
/Users/zhaoyongwei/Desktop/KmAI/KmAI/KmMpsMcpServer/skills/kmsoft-group-template/assets/FeatureTemplate.xml
```

at:

```text
process-plan-agent-api/app/assets/group_templates/FeatureTemplate.xml
```

Do not rewrite its item names; dictionary spelling is part of the compatibility contract.

- [ ] **Step 2: Add portable copies of the five approved sample templates**

Copy the five XML files from:

```text
/Users/zhaoyongwei/Desktop/KmAI/KmAI/KmMpsMcpServer/skills/kmsoft-group-template/assets/sample-templates
```

into `process-plan-agent-api/tests/fixtures/group_templates/` without decoding or re-encoding them. Verify each copied file has the same SHA-256 as its source. Runtime code must never read the external KMAI path; only these repository fixtures may be used by automated tests.

- [ ] **Step 3: Write parser tests against real and adversarial XML**

Add tests with these concrete assertions:

```python
SAMPLES = Path(__file__).parent / "fixtures" / "group_templates"

@pytest.mark.parametrize("filename", [
    "临时壳体4.xml",
    "套筒类(未指定参数).xml",
    "套筒类.xml",
    "飞机壁板类1.xml",
    "新衬套模板.xml",
])
def test_parses_real_kmsoft_templates(filename):
    result = parse_group_template_xml(filename, (SAMPLES / filename).read_bytes())
    assert result.can_confirm is True
    assert result.group_count > 0
    assert result.content_hash == hashlib.sha256((SAMPLES / filename).read_bytes()).hexdigest()
    assert all(node["key"].startswith("grp_") for node in flatten_nodes(result.tree))

def test_stable_key_uses_normalized_path_not_xml_id():
    first = parse_group_template_xml("a.xml", xml_bytes(group_id="id-a", name=" 孔 "))
    second = parse_group_template_xml("b.xml", xml_bytes(group_id="id-b", name="孔"))
    assert first.tree[0]["key"] == second.tree[0]["key"]

def test_duplicate_normalized_sibling_name_blocks_confirmation():
    result = parse_group_template_xml("duplicate.xml", duplicate_sibling_xml())
    assert result.can_confirm is False
    assert result.issues[0].code == "duplicate_sibling_name"
```

Also assert rejection results for wrong extension, payload over 5 MiB, UTF-8/GB2312/GB18030 decode failures, `DOCTYPE`, `ENTITY`, external entities, wrong root, missing `Part_Template`, missing `Group_Template`, zero/multiple Parts, no Groups, blank names, and dictionary-unknown feature names. The unknown-feature assertion must include both `path == ["A侧", "孔"]` and the illegal value.

- [ ] **Step 4: Run the parser tests and verify they fail**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_group_template_xml.py -q
```

Expected: collection fails because `app.services.group_template_xml` does not exist.

- [ ] **Step 5: Implement safe decoding, parsing, and normalization**

Implement the core contracts with these exact constants and key algorithm:

```python
MAX_GROUP_TEMPLATE_BYTES = 5 * 1024 * 1024
FEATURE_DICTIONARY_PATH = Path(__file__).parents[1] / "assets" / "group_templates" / "FeatureTemplate.xml"

def normalize_name(value: object) -> str:
    return unicodedata.normalize("NFC", str(value or "").strip())

def stable_group_key(path: list[str]) -> str:
    canonical = json.dumps(path, ensure_ascii=False, separators=(",", ":"))
    return f"grp_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:24]}"
```

Decode XML declarations case-insensitively, map `gb2312` and `gbk` to Python's `gb18030` decoder, and retain the reported source encoding. Before parsing, reject case-insensitive `<!DOCTYPE` or `<!ENTITY`. Parse with:

```python
parser = etree.XMLParser(
    resolve_entities=False,
    load_dtd=False,
    no_network=True,
    recover=False,
    huge_tree=False,
)
root = etree.fromstring(source_xml.encode("utf-8"), parser=parser)
```

Collect all dictionary `Item/@name` values recursively. Read each Group's direct `Params/param` entries, remove `名称` and `特征选择` from the traceability `params` dictionary, split features only on English commas, trim, preserve order, and deduplicate. Return blocking issues instead of partial success whenever identity or feature validation is invalid.

- [ ] **Step 6: Run parser tests**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_group_template_xml.py -q
```

Expected: all parser and five real-sample tests pass.

- [ ] **Step 7: Commit the parser slice**

```bash
git add process-plan-agent-api/app/assets/group_templates/FeatureTemplate.xml \
  process-plan-agent-api/app/services/group_template_xml.py \
  process-plan-agent-api/tests/test_group_template_xml.py \
  process-plan-agent-api/tests/fixtures/group_templates
git commit -m "feat: parse Kmsoft group templates safely"
```

### Task 2: Project Template Persistence And Optimistic Revision

**Files:**
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Create: `process-plan-agent-api/app/services/project_group_templates.py`
- Create: `process-plan-agent-api/tests/test_project_group_template_api.py`

**Interfaces:**
- Consumes: `GroupTemplateParseResult` from Task 1.
- Produces: `get_project_group_template(db: AsyncSession, project_id: int) -> ProjectGroupTemplate | None`.
- Produces: `commit_project_group_template(db, project_id, parsed, expected_revision) -> TemplateCommitResult`.
- Produces: `replace_project_group_mappings(db, project_id, mappings, expected_revision) -> ProjectTemplateSnapshot`.
- Produces: `serialize_project_group_template(row) -> ProjectTemplateSnapshot`.

- [ ] **Step 1: Write persistence and concurrency tests**

Create an async SQLite fixture and test these exact transitions:

```python
saved = await commit_project_group_template(db, project.id, parsed_a, expected_revision=0)
assert saved.template_revision == 1

mapped = await replace_project_group_mappings(
    db,
    project.id,
    [{"source_operation_id": 11, "alias": "钻孔（A侧/孔）", "template_group_path": ["A侧", "孔"]}],
    expected_revision=1,
)
assert mapped.template_revision == 2
assert mapped.mappings[0].template_group_key.startswith("grp_")
assert mapped.mappings[0].feature_selections == ["孔(盲孔)"]

replaced = await commit_project_group_template(db, project.id, parsed_b, expected_revision=2)
assert replaced.template_revision == 3
assert replaced.kept_source_operation_ids == []
assert replaced.invalidated[0].source_operation_id == 11
```

Also verify stale revision returns HTTP-compatible `409`, first create rejects any expected revision other than `0`, duplicate concurrent first creates produce one winner, exact-path replacement preserves mappings, failed replacement leaves the old row unchanged, and deleting a project cascades to its template.

- [ ] **Step 2: Run the persistence tests and verify they fail**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_project_group_template_api.py -q
```

Expected: fail because `ProjectGroupTemplate` and the persistence service are missing.

- [ ] **Step 3: Add the ORM model and deployed-database schema**

Add `Project.group_template` as a one-to-one `cascade="all, delete-orphan"` relationship and define:

```python
class ProjectGroupTemplate(Base):
    __tablename__ = "project_group_templates"

    id = Column(Integer, primary_key=True, autoincrement=True)
    project_id = Column(Integer, ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True)
    original_filename = Column(String(255), nullable=False)
    source_encoding = Column(String(32), nullable=False)
    part_filename = Column(String(255), nullable=False)
    content_hash = Column(String(64), nullable=False)
    feature_dictionary_version = Column(String(64), nullable=False)
    source_xml = Column(Text, nullable=False)
    tree_json = Column(Text, nullable=False)
    validation_json = Column(Text, nullable=False, default="[]")
    mappings_json = Column(Text, nullable=False, default="[]")
    template_revision = Column(Integer, nullable=False, default=1, server_default="1")
    group_count = Column(Integer, nullable=False, default=0)
    feature_selection_count = Column(Integer, nullable=False, default=0)
    created_at = Column(DateTime, default=utcnow)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow)
```

In `ensure_project_schema`, add an idempotent `CREATE TABLE IF NOT EXISTS project_group_templates (...)` and `CREATE UNIQUE INDEX IF NOT EXISTS uq_project_group_templates_project ON project_group_templates(project_id)` so deployed SQLite files work even if startup order changes.

- [ ] **Step 4: Implement atomic commit, path migration, and formal mapping replacement**

Use normalized path-array canonical JSON as the dictionary key; never join path strings with `/`. On mapping replacement, resolve each requested path against the current tree and overwrite client-supplied metadata with server values:

```python
{
    "source_operation_id": source_operation_id,
    "alias": alias,
    "template_group_key": node["key"],
    "template_group_id": node["key"],  # legacy field, never an XML UUID
    "template_group_name": node["name"],
    "template_group_path": node["path"],
    "feature_selections": node["feature_selections"],
}
```

For updates, replace the template columns, migrated mappings, and revision in one conditional statement so the row never exposes a new revision with old content:

```sql
UPDATE project_group_templates
SET original_filename = :original_filename,
    source_encoding = :source_encoding,
    part_filename = :part_filename,
    content_hash = :content_hash,
    feature_dictionary_version = :feature_dictionary_version,
    source_xml = :source_xml,
    tree_json = :tree_json,
    validation_json = :validation_json,
    mappings_json = :mappings_json,
    group_count = :group_count,
    feature_selection_count = :feature_selection_count,
    template_revision = template_revision + 1,
    updated_at = CURRENT_TIMESTAMP
WHERE project_id = :project_id AND template_revision = :expected_revision
RETURNING template_revision
```

Raise `HTTPException(409, "分组模板已在其他页面更新，请重新加载。")` when no row is returned. Do not call `commit()` inside the service; routers own transaction completion.

- [ ] **Step 5: Run persistence and startup compatibility tests**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_project_group_template_api.py tests/test_db_startup_safety.py -q
```

Expected: all tests pass and repeated schema maintenance does not alter existing rows.

- [ ] **Step 6: Commit the persistence slice**

```bash
git add process-plan-agent-api/app/models/models.py \
  process-plan-agent-api/app/services/db_schema_maintenance.py \
  process-plan-agent-api/app/services/project_group_templates.py \
  process-plan-agent-api/tests/test_project_group_template_api.py
git commit -m "feat: persist project group templates"
```

### Task 3: Group Template API Contracts

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/tests/test_project_group_template_api.py`

**Interfaces:**
- Consumes: Task 1 parser and Task 2 persistence service.
- Produces: `POST /api/extract/group-templates/preview`.
- Produces: `GET /api/extract/group-templates/current?project_id={id}`.
- Produces: `PUT /api/extract/group-templates/current`.
- Produces: `PUT /api/extract/group-templates/mappings`.

- [ ] **Step 1: Add failing endpoint contract tests**

Use FastAPI `TestClient` with the temporary async SQLite override and assert:

```python
preview = client.post(
    "/api/extract/group-templates/preview",
    files={"file": ("套筒类.xml", template_bytes, "application/xml")},
)
assert preview.status_code == 200
assert preview.json()["can_confirm"] is True

missing = client.get("/api/extract/group-templates/current", params={"project_id": project_id})
assert missing.status_code == 404

created = client.put(
    "/api/extract/group-templates/current",
    data={
        "project_id": str(project_id),
        "expected_content_hash": preview.json()["content_hash"],
        "expected_template_revision": "0",
    },
    files={"file": ("套筒类.xml", template_bytes, "application/xml")},
)
assert created.status_code == 200
assert created.json()["template_revision"] == 1
```

Also assert: preview performs no database write; confirm rejects a changed file hash; invalid previews cannot be confirmed; missing project is `404`; stale template/mapping revisions are `409`; invalid mapping paths are `422`; current-template responses omit `source_xml`; and commit failures roll back.

- [ ] **Step 2: Run endpoint tests and verify route failures**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_project_group_template_api.py -q
```

Expected: API cases fail with `404` before the routes are added.

- [ ] **Step 3: Define Pydantic contracts**

Add these types with recursive `children` and default factories:

```python
class GroupTemplateNodeOut(BaseModel):
    key: str
    source_id: str = ""
    name: str
    path: list[str]
    feature_selections: list[str] = Field(default_factory=list)
    params: dict[str, str] = Field(default_factory=dict)
    children: list["GroupTemplateNodeOut"] = Field(default_factory=list)

class GroupTemplateMappingIn(BaseModel):
    source_operation_id: int = Field(gt=0)
    alias: str = Field(min_length=1, max_length=500)
    template_group_path: list[str] = Field(min_length=1)

class GroupTemplateMappingsUpdateRequest(BaseModel):
    project_id: int = Field(gt=0)
    expected_template_revision: int = Field(ge=1)
    mappings: list[GroupTemplateMappingIn] = Field(default_factory=list)
```

Define preview/current/commit response types with the field names in the design specification. Extend `TemplateGroupAliasBinding` with `template_group_key`, `template_group_name`, and `feature_selections`, while accepting legacy `template_group_id` for existing saved route payloads.

- [ ] **Step 4: Add the four endpoints and transaction boundaries**

Use `UploadFile`, `File`, and `Form` for preview/confirm. Read no more than `MAX_GROUP_TEMPLATE_BYTES + 1`. Preview returns parse issues with `200`; confirm returns `422` when `can_confirm` is false or when content hashes differ. After successful persistence call `await db.commit()`; on any exception call `await db.rollback()` and re-raise.

For mappings, accept JSON `GroupTemplateMappingsUpdateRequest`; return the server-enriched formal mappings and incremented revision. Current template returns `404` when absent.

- [ ] **Step 5: Run API and alias contract tests**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_project_group_template_api.py tests/test_template_group_alias_metadata.py -q
```

Expected: all endpoint and compatibility tests pass.

- [ ] **Step 6: Commit the API slice**

```bash
git add process-plan-agent-api/app/schemas/schemas.py \
  process-plan-agent-api/app/routers/extract.py \
  process-plan-agent-api/tests/test_project_group_template_api.py \
  process-plan-agent-api/tests/test_template_group_alias_metadata.py
git commit -m "feat: expose project group template APIs"
```

### Task 4: Template-Driven Smart Mapping Service

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Modify: `process-plan-agent-api/app/services/template_group_mapping.py`
- Modify: `process-plan-agent-api/tests/test_template_group_mapping.py`

**Interfaces:**
- Consumes: confirmed project tree from `get_project_group_template`.
- Produces: `build_template_candidates(operation, tree) -> list[TemplateGroupMappingCandidateIn]`.
- Changes: `resolve_template_group_mappings(db: AsyncSession, body: TemplateGroupMappingSuggestRequest) -> TemplateGroupMappingSuggestResponse`.
- Changes: suggestion requests contain only project ID and operation evidence; client-supplied candidate lists are removed.

- [ ] **Step 1: Rewrite tests around confirmed project templates**

Add cases that seed a project template, then assert:

```python
candidates = build_template_candidates(
    operation(name="车A侧端面", step_items=["平端面"]),
    parsed_template.tree,
)
assert [candidate.path for candidate in candidates] == [["A侧", "端面"]]

compound = build_template_candidates(
    operation(name="车削加工（A侧）", step_items=["平端面", "车外圆", "钻孔"]),
    parsed_template.tree,
)
assert len(compound) >= 3
```

Also assert no confirmed template returns a manual-mapping warning, generic templates with arbitrary group names still produce name/feature substring candidates, unknown LLM keys are rejected, a valid high-confidence key is accepted, confidence below `0.90` remains pending, composite candidates are never auto-applied, and LLM failure preserves deterministic candidates/manual operation.

- [ ] **Step 2: Run smart-mapping tests and verify failures**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_template_group_mapping.py -q
```

Expected: fail because the current service trusts candidates supplied by the caller and has no database/template lookup.

- [ ] **Step 3: Make candidate generation template-driven**

Remove `candidates` from `TemplateGroupMappingOperationIn`. Flatten only nodes in the confirmed tree. Score normalized operation name plus step/rule evidence against:

```text
group name + full path components + feature selection names
```

Keep a small domain-wide semantic alias table only for feature wording such as `车外圆 -> 外圆柱面`, `平端面 -> 轴端面`, and `钻孔 -> 孔`; it must not contain template paths, A/B-side assumptions, or XML IDs. Prefer nodes with non-empty feature selections. Return all tied or independently evidenced feature candidates; return no recommended key for multi-feature results.

- [ ] **Step 4: Restrict LLM resolution to server-generated candidates**

Load the current template row inside `resolve_template_group_mappings`. The prompt may include only server-generated candidate keys, paths, names, features, and original operation evidence. Validate the response key against that exact candidate dictionary and require confidence `>= 0.90` for automatic acceptance. Route injection becomes:

```python
@router.post("/template-group-mappings/suggest", response_model=TemplateGroupMappingSuggestResponse)
async def suggest_template_group_mappings(
    body: TemplateGroupMappingSuggestRequest,
    db: AsyncSession = Depends(get_db),
):
    return await resolve_template_group_mappings(db, body)
```

- [ ] **Step 5: Run focused and backend regression tests**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_template_group_mapping.py tests/test_project_group_template_api.py -q
pytest -q
```

Expected: focused tests and the complete backend suite pass.

- [ ] **Step 6: Commit the smart-mapping backend slice**

```bash
git add process-plan-agent-api/app/schemas/schemas.py \
  process-plan-agent-api/app/routers/extract.py \
  process-plan-agent-api/app/services/template_group_mapping.py \
  process-plan-agent-api/tests/test_template_group_mapping.py
git commit -m "feat: drive mapping suggestions from project templates"
```

### Task 5: Frontend API And Project Template State

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Create: `process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts`
- Create: `process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts`

**Interfaces:**
- Produces: `previewGroupTemplate(file: File): Promise<GroupTemplatePreview>`.
- Produces: `getCurrentGroupTemplate(projectId: number): Promise<ProjectGroupTemplate>`.
- Produces: `commitGroupTemplate(projectId, file, expectedHash, expectedRevision): Promise<GroupTemplateCommitResult>`.
- Produces: `saveGroupTemplateMappings(projectId, revision, mappings): Promise<ProjectGroupTemplate>`.
- Produces: `useProjectGroupTemplate(projectId, legacyAliases)` with `state`, `template`, `preview`, `draftMappings`, `loading`, `saving`, `error`, `load`, `selectFile`, `confirmTemplate`, `beginReplacement`, `cancelPreview`, and `saveMappings`.

- [ ] **Step 1: Write composable state-transition tests**

Mock the four API functions and assert:

```typescript
const model = useProjectGroupTemplate(ref(28), ref({}))
await model.load()
expect(model.state.value).toBe('empty')

await model.selectFile(xmlFile)
expect(model.state.value).toBe('preview')
expect(model.preview.value?.can_confirm).toBe(true)

await model.confirmTemplate()
expect(model.state.value).toBe('workspace')
expect(model.templateRevision.value).toBe(1)
```

Also test: existing template opens directly in workspace; invalid preview stays in preview; canceling replacement restores workspace unchanged; `409` clears busy state and exposes the reload message; replacement uses the current revision; save uses the latest revision and replaces local mappings with server-enriched results; first-load legacy mappings migrate only by exact path into draft mappings and do not count as saved.

- [ ] **Step 2: Run the composable tests and verify they fail**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/useProjectGroupTemplate.spec.ts
```

Expected: fail because the API functions and composable do not exist.

- [ ] **Step 3: Add exact frontend API types and clients**

Define recursive `GroupTemplateNode`, `GroupTemplatePreview`, `ProjectGroupTemplate`, `GroupTemplateMapping`, `GroupTemplateValidationIssue`, and migration result types matching Task 3. Use `FormData` for preview/confirm:

```typescript
form.append('file', file)
form.append('project_id', String(projectId))
form.append('expected_content_hash', expectedHash)
form.append('expected_template_revision', String(expectedRevision))
```

Do not set multipart content type manually; Axios must add the boundary. Change `suggestTemplateGroupMappings` so operations no longer carry client candidate arrays.

- [ ] **Step 4: Implement the explicit three-state composable**

Use:

```typescript
export type GroupTemplateDialogState = 'empty' | 'preview' | 'workspace'
```

Treat GET `404` as `empty`, but surface all other failures. Keep the previously confirmed template in memory while previewing a replacement. On a stale `409`, call `load()` after surfacing `分组模板已在其他页面更新，已重新加载最新内容。`. Compute pre-confirm replacement impact from normalized path-array JSON, then replace it with the authoritative server impact after confirmation.

- [ ] **Step 5: Run composable tests and TypeScript build**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: tests and type checking pass.

- [ ] **Step 6: Commit the API/state slice**

```bash
git add process-plan-agent-ui/src/api/extract.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts
git commit -m "feat: manage project group templates in the UI"
```

### Task 6: Dynamic Mapping Logic And Draft Migration

**Files:**
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.ts`
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`

**Interfaces:**
- Consumes: dynamic `GroupTemplateNode[]` from Task 5.
- Produces: `flattenTemplateGroups(tree)`, `findTemplateGroupByKey(tree, key)`, `findTemplateGroupByPath(tree, path)`, `buildTemplateGroupMappingSuggestions(operations, tree)`, and `migrateLegacyAliasesByPath(aliases, tree)`.
- Produces: draft-only local storage schema version `3` containing `projectId`, `templateRevision`, `routeFingerprint`, and `entries`.

- [ ] **Step 1: Replace fixed-tree tests with dynamic fixtures**

Use a test tree containing arbitrary paths such as `壳体/内腔/盲孔` and `外形/筋条/平面`, then assert:

```typescript
expect(findTemplateGroupByPath(tree, ['壳体', '内腔', '盲孔'])?.key).toBe('grp_blind_hole')
expect(suggestTemplateGroupsForOperation({ name: '钻盲孔' }, tree)
  .candidates.map(item => item.group_id)).toEqual(['grp_blind_hole'])
```

Also assert: changing source XML IDs does not change use of stable keys; duplicate leaf names under different parents stay distinct by full path; a compound operation yields all evidenced feature candidates and no recommendation; selected/manual aliases are untouched; missing-path legacy aliases are excluded and reported; local storage never replaces a non-empty formal mapping set.

- [ ] **Step 2: Run the dynamic mapping tests and verify fixed-tree failures**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupMapping.spec.ts
```

Expected: tests fail while functions default to `BUSHING_11_TEMPLATE_TREE`.

- [ ] **Step 3: Remove `BUSHING_11_TEMPLATE_TREE` and parameterize all lookups**

Change `TemplateGroupNode` to the backend shape (`key`, `source_id`, `name`, `path`, `feature_selections`, `params`, `children`). Every tree function must require a tree argument; no hidden default tree is allowed. Change bindings to carry:

```typescript
{
  source_operation_id,
  alias,
  template_group_key: group.key,
  template_group_id: group.key,
  template_group_name: group.name,
  template_group_path: [...group.path],
  feature_selections: [...group.feature_selections],
}
```

Keep generic machining-term aliases, but remove every hardcoded template UUID, fixed A/B path, fixed leaf count, and template key such as `bushing-11`.

- [ ] **Step 4: Make browser storage draft-only**

Rename storage helpers to make intent explicit (`loadTemplateGroupMappingDraft`, `saveTemplateGroupMappingDraft`, `clearTemplateGroupMappingDraft`). The caller must pass formal mappings first; local entries are used only when formal mappings are empty and their stored `templateRevision` matches the current template. Path migration returns `{ migrated, invalidated }` and never guesses by old `template_group_id`.

- [ ] **Step 5: Run mapping tests and production build**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupMapping.spec.ts src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: all focused tests and type checking pass.

- [ ] **Step 6: Commit the mapping-logic slice**

```bash
git add process-plan-agent-ui/src/composables/templateGroupMapping.ts \
  process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts
git commit -m "refactor: make group mapping template driven"
```

### Task 7: Three-State Dialog And Recursive Template Tree

**Files:**
- Create: `process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue`
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`

**Interfaces:**
- Consumes: `useProjectGroupTemplate`, dynamic tree helpers, project ID, operations, and optional legacy aliases.
- Emits: `save` with server-enriched formal mappings and `templateRevision` after a successful backend save.
- Renders: upload, validated preview, mapping workspace, and replacement impact without obscuring the underlying route page after close.

- [ ] **Step 1: Implement the recursive tree node**

Render one row with a disclosure icon only when `children.length > 0`, group name, non-empty feature selection tags, mapped count, and clear-mappings icon. Recurse into children when expanded. Emit `select(key)` and `clear(key)`; use stable `node.key` for Vue keys and selection. Do not display XML `source_id`.

- [ ] **Step 2: Add the empty upload state**

When `state === 'empty'`, render a compact `.xml` drop/select area, selected filename, and one primary `解析模板` action. Disable action while reading. Display file/parse errors inline in the dialog rather than via an unrelated modal. Closing the dialog must reset transient file/preview state but keep the current project template.

- [ ] **Step 3: Add the parsed preview state**

Show original filename, detected encoding, part filename, group count, feature-selection count, and issue count. Render the recursive tree read-only with feature tags. Blocking issues disable `确认并进入映射`. For replacement, show exact kept/invalidated counts and list invalidated operation names plus old paths before confirmation. Provide `重新选择` and `取消更换` actions.

- [ ] **Step 4: Convert the workspace to a dynamic tree**

Replace `templateRoots`, `findTemplateGroupById`, and root/leaf-only loops with recursive tree state keyed by stable keys. Allow selecting any Group, including parents with empty feature selections. Keep current search, multi-select transfer, double-click mapping, per-group clear, all-clear, and candidate review interactions. In the header show template filename, part filename, counts, and a `更换模板` command.

- [ ] **Step 5: Connect smart mapping and formal save behavior**

Show deterministic candidates immediately, then merge the controlled backend result only if the dialog run ID still matches. Never auto-apply to an existing mapping. Auto-apply only a unique candidate with model confidence `>= 0.90`; all compound/ambiguous cases remain visible for review. If suggestion API fails, keep candidates and manual mapping enabled. `保存映射` calls the backend, clears the matching local draft after success, emits formal mappings, and leaves the dialog open on validation/stale errors.

- [ ] **Step 6: Run focused tests and build**

Run:

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateGroupMapping.spec.ts src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: tests and Vue type checking pass with no reference to `BUSHING_11_TEMPLATE_TREE`.

- [ ] **Step 7: Commit the dialog slice**

```bash
git add process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue \
  process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue
git commit -m "feat: add group template upload and preview workflow"
```

### Task 8: Extract View Integration And Export Compatibility

**Files:**
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue`
- Modify: `process-plan-agent-api/tests/test_template_group_alias_metadata.py`
- Modify: `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`

**Interfaces:**
- Consumes: formal server mappings emitted by Task 7.
- Preserves: `template_group_aliases` in saved normalized route segments and downstream rule-package/KMAI exports.
- Changes: local/route aliases are legacy draft candidates only until formal mappings are saved.

- [ ] **Step 1: Add compatibility assertions before integration changes**

Backend assertions must verify saved route and rule-package aliases contain:

```json
{
  "template_group_key": "grp_...",
  "template_group_id": "grp_...",
  "template_group_name": "孔",
  "template_group_path": ["A侧", "孔"],
  "feature_selections": ["孔(盲孔)"]
}
```

Frontend assertions must verify serialization preserves these fields and reading a legacy path-only route alias resolves it against the current tree without using the old UUID.

- [ ] **Step 2: Run compatibility tests and verify missing metadata failures**

Run:

```bash
cd process-plan-agent-api
pytest tests/test_template_group_alias_metadata.py -q
cd ../process-plan-agent-ui
npm test -- src/composables/templateGroupMapping.spec.ts
```

Expected: new metadata assertions fail before integration is updated.

- [ ] **Step 3: Replace ExtractView's local-first hydration**

Pass route/local aliases to the dialog as `legacyAliases`, not as formal `aliases`. On dialog open, let `useProjectGroupTemplate.load()` fetch the project record. Set `templateGroupAliases` from the returned formal mappings. If no formal mappings exist, compute a one-time path-only legacy draft and show it for user review; do not silently persist it.

Change the dialog save handler to accept `{ mappings, templateRevision }`, update `templateGroupAliases`, clear the matching local draft, update the route-save fingerprint, and keep the existing `routeMergeNotice` feedback.

- [ ] **Step 4: Preserve route, rule-package, and KMAI payloads**

Update `scopedTemplateGroupAliases`, `templateAliasFingerprint`, and `templateGroupAliasesForItem` to use stable key/name/path/features. Keep `template_group_id` equal to the stable key in serialized payloads for readers that still expect the old property. Verify KMAI v1 ignores the added fields and route saving still detects mapping changes.

- [ ] **Step 5: Run complete automated verification**

Run:

```bash
cd process-plan-agent-api
pytest -q
cd ../process-plan-agent-ui
npm test
npm run build
```

Expected: complete backend suite, complete Vitest suite, Vue type checking, and production build pass.

- [ ] **Step 6: Commit the integration slice**

```bash
git add process-plan-agent-ui/src/views/ExtractView.vue \
  process-plan-agent-api/tests/test_template_group_alias_metadata.py \
  process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts
git commit -m "feat: integrate formal group mappings with route export"
```

### Task 9: Browser Acceptance And Documentation Closeout

**Files:**
- Modify only if observed behavior requires a scoped fix in files already listed above.

**Interfaces:**
- Verifies: upload, reuse, replacement, dynamic mapping, smart suggestions, stale revision, route save, fourth-step export, and KMAI compatibility.

- [ ] **Step 1: Start both development services**

Use the repository's existing backend and frontend startup commands. If `8000` or `5173` is occupied by this project, restart that process; otherwise use the next available port and point the frontend API configuration to it.

- [ ] **Step 2: Verify first upload and reuse in the in-app browser**

Create a clean project, reach step two, open template mapping, upload `套筒类.xml`, inspect encoding/part/counts/tree/features, confirm, manually map one operation, save, close, and reopen. Expected: the dialog opens directly in workspace and the formal mapping remains.

- [ ] **Step 3: Verify generic and failure cases**

Repeat with `飞机壁板类1.xml` and confirm the displayed tree is unrelated to the sleeve hierarchy. Upload XML with an unknown feature and a DTD. Expected: both show precise inline blocking issues and the current confirmed template remains unchanged.

- [ ] **Step 4: Verify replacement impact and concurrency**

Replace a template with one that retains one mapped full path and removes another. Expected: preview lists kept/invalidated mappings; confirmation preserves only the exact path. Open the same project in a second tab and save from the stale tab. Expected: `409` feedback and latest server state reload, with no silent overwrite.

- [ ] **Step 5: Verify suggestion and downstream behavior**

Run smart mapping on a unique feature, a plain ambiguous hole operation, and a compound turning operation. Expected: only the unique high-confidence result may auto-apply; ambiguous/compound results remain reviewable. Save the route, export the fourth-step rule package, and run the standalone KMAI compatibility page. Expected: group metadata is present and existing KMAI v1 generation still succeeds.

- [ ] **Step 6: Re-run final verification and inspect the diff**

Run:

```bash
cd process-plan-agent-api && pytest -q
cd ../process-plan-agent-ui && npm test && npm run build
cd .. && git status --short && git diff --check
```

Expected: all checks pass; `git diff --check` has no output; `.vscode/` and `outputs/` remain untracked and unstaged.

- [ ] **Step 7: Commit any browser-only fixes**

If browser acceptance required scoped fixes, stage only the affected files from this plan and commit:

```bash
git commit -m "fix: finalize project group template workflow"
```

If no fixes were required, do not create an empty commit.

---

## Completion Criteria

- A project with no template cannot enter mapping until one valid XML is confirmed.
- A confirmed template and mappings survive closing, reopening, and application restart.
- All five approved sample templates parse and render as their own recursive structures.
- XML IDs never determine mapping identity or migration.
- Feature selections come only from XML and are validated against the bundled dictionary.
- Template replacement is revision-safe and path migration is visible before confirmation.
- Formal mappings come from the backend; local storage can only restore matching-revision drafts.
- Smart mapping is template-driven, preserves manual decisions, and safely degrades to manual mapping.
- Second-step route saving, fourth-step rule package export, and KMAI compatibility continue to work.
- Complete backend tests, frontend tests, type checking, build, and browser acceptance pass.
