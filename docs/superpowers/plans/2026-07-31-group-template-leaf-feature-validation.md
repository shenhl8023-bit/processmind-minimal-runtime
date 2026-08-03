# Template Step Mapping Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将模板映射从“每道工序对应一个分组”升级为“每个工步对应一个或多个叶子分组及候选特征”，同时让父分组承担范围和汇总职责，并阻止空特征叶子模板进入工作台。

**Architecture:** 后端新增独立的 `step_mappings_json` 存储和工步级 API，保留现有工序级 `mappings_json` 供以后单独移除，避免当前功能继续依赖兼容逻辑。工步候选服务按单个工步生成受控叶子候选，前端以可展开工序树审核工步映射；父分组只设置候选范围，正式记录始终落在叶子分组。

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy async, lxml, Pytest, Vue 3, TypeScript, Vitest, Vite.

## Global Constraints

- 当前阶段不修改任何外部系统代码、兼容脚本或外部文件格式。
- 现有 `mappings_json` 和工序级别名 API 暂时保留；新功能只读旧映射用于迁移，不向其中写入新数据。
- 父分组可以没有自身特征，可作为筛选和批量识别范围，但不能成为工步正式映射目标。
- 叶子分组必须至少包含一个 `FeatureTemplate.xml` 中的合法特征，否则模板不可确认。
- 工步正式状态只有 `confirmed` 或 `not_applicable`；未解决工步不写入正式存储并阻止完成映射。
- 同一工步可以保存多条叶子映射；同一叶子可以关联多个工步。
- 大模型只能在程序候选集合内选择，不能创造分组路径、分组 ID 或特征。
- 第二步重新推理时保留已确认 XML 模板，但清除工步映射和浏览器草稿。
- 不新增工步数据库表；只在项目模板表增加一个 JSON 文本列。
- 保留当前工作区已有改动；不得提交 `.vscode/`、`outputs/` 或其他无关文件。

---

### Task 0: Checkpoint The Existing Verified Work

**Files:**
- Existing API changes: `process-plan-agent-api/app/services/rule_packages/condition_parser.py`, `process-plan-agent-api/app/services/template_group_mapping.py`, `process-plan-agent-api/tests/test_rule_condition_parser.py`, `process-plan-agent-api/tests/test_template_group_mapping.py`
- Existing UI changes: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`, `process-plan-agent-ui/src/composables/extractViewHelpers.ts`, `process-plan-agent-ui/src/composables/extractViewHelpers.spec.ts`, `process-plan-agent-ui/src/composables/templateGroupMapping.ts`, `process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts`, `process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts`, `process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts`, `process-plan-agent-ui/src/views/ExtractView.vue`
- Existing docs: `docs/superpowers/specs/2026-07-31-template-replacement-file-picker-design.md`, `docs/superpowers/plans/2026-07-31-template-replacement-auto-parse.md`

**Interfaces:**
- Consumes: already verified timeout fallback, replacement auto-preview, same-file reselection and focus-preservation work.
- Produces: two bounded commits so the new TDD cycle starts from a clean tracked baseline.

- [ ] **Step 1: Re-run the existing baseline**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest -q
cd ../process-plan-agent-ui
npm test
npm run build
cd ..
git diff --check
```

Expected: API `251 passed, 9 skipped`; UI `102 passed`; build exits `0`; `git diff --check` prints nothing.

- [ ] **Step 2: Commit bounded API fallback changes**

```bash
git add \
  process-plan-agent-api/app/services/rule_packages/condition_parser.py \
  process-plan-agent-api/app/services/template_group_mapping.py \
  process-plan-agent-api/tests/test_rule_condition_parser.py \
  process-plan-agent-api/tests/test_template_group_mapping.py
git diff --cached --check
git commit -m "fix: bound AI parsing fallbacks"
```

- [ ] **Step 3: Commit replacement workflow changes**

```bash
git add \
  process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue \
  process-plan-agent-ui/src/composables/extractViewHelpers.ts \
  process-plan-agent-ui/src/composables/extractViewHelpers.spec.ts \
  process-plan-agent-ui/src/composables/templateGroupMapping.ts \
  process-plan-agent-ui/src/composables/templateGroupMapping.spec.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts \
  process-plan-agent-ui/src/views/ExtractView.vue \
  docs/superpowers/specs/2026-07-31-template-replacement-file-picker-design.md \
  docs/superpowers/plans/2026-07-31-template-replacement-auto-parse.md
git diff --cached --check
git commit -m "fix: streamline group template replacement"
```

Expected: `.vscode/` and `outputs/` remain untracked.

---

### Task 1: Validate Leaf Feature Completeness

**Files:**
- Modify: `process-plan-agent-api/app/services/group_template_xml.py`
- Test: `process-plan-agent-api/tests/test_group_template_xml.py`
- Test: `process-plan-agent-api/tests/test_project_group_template_api.py`

**Interfaces:**
- Consumes: parsed node `children`, normalized `feature_selections`, and `FeatureTemplate.xml`.
- Produces: `is_feature_mapping_target(node: dict[str, object]) -> bool` and `missing_leaf_feature_selection` issues.

- [ ] **Step 1: Add failing parser fixtures and assertions**

Add after `xml_bytes()`:

```python
def nested_group_xml(*, parent_name="A侧", child_name="孔", child_feature="孔(盲孔)"):
    return f'''<?xml version="1.0" encoding="UTF-8"?>
    <Kmsoft>
      <Item type="Part_Template" /><Item type="Group_Template" />
      <Item type="Part" filename="part.prt">
        <Item type="Group" id="parent">
          <Params><param name="名称" value="{parent_name}" /></Params>
          <Item type="Group" id="child"><Params>
            <param name="名称" value="{child_name}" />
            <param name="特征选择" value="{child_feature}" />
          </Params></Item>
        </Item>
      </Item>
    </Kmsoft>'''.encode("utf-8")
```

Replace the real-template test and add focused tests:

```python
@pytest.mark.parametrize(("filename", "can_confirm", "missing_leaf_count"), [
    ("临时壳体4.xml", True, 0),
    ("套筒类(未指定参数).xml", True, 0),
    ("套筒类.xml", True, 0),
    ("新衬套模板.xml", False, 18),
    ("飞机壁板类1.xml", False, 16),
])
def test_validates_real_template_leaf_features(filename, can_confirm, missing_leaf_count):
    result = parse_group_template_xml(filename, (SAMPLES / filename).read_bytes())
    missing = [item for item in result.issues if item.code == "missing_leaf_feature_selection"]

    assert result.can_confirm is can_confirm
    assert len(missing) == missing_leaf_count


def test_empty_parent_with_feature_leaf_is_a_valid_scope():
    result = parse_group_template_xml("scope.xml", nested_group_xml())

    assert result.can_confirm is True
    assert result.tree[0]["feature_selections"] == []
    assert result.tree[0]["children"][0]["feature_selections"] == ["孔(盲孔)"]


def test_empty_leaf_blocks_confirmation_with_full_path():
    result = parse_group_template_xml(
        "empty-leaf.xml",
        nested_group_xml(child_name="待分类", child_feature=""),
    )
    issue = next(item for item in result.issues if item.code == "missing_leaf_feature_selection")

    assert result.can_confirm is False
    assert issue.path == ["A侧", "待分类"]
    assert issue.value == ""
    assert issue.message == "叶子分组必须至少配置一个特征选择。"
```

Extend the unknown-feature test:

```python
assert not any(item.code == "missing_leaf_feature_selection" for item in result.issues)
```

Add `<param name="特征选择" value="平面" />` to the wrapped-group success fixture. In `test_project_group_template_api.py`, replace unrelated `feature=""` calls with `feature="孔(通孔)"` so revision and normalization tests continue using valid templates.

- [ ] **Step 2: Verify the tests fail for the new reason**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_group_template_xml.py -q
```

Expected: empty leaves have no `missing_leaf_feature_selection`, and the two nonstandard real templates still report `can_confirm=True`.

- [ ] **Step 3: Implement dictionary-backed leaf validation**

Add `import functools`, cache `_load_feature_dictionary()`, and expose this predicate:

```python
def is_feature_mapping_target(node: dict[str, object]) -> bool:
    children = node.get("children", [])
    values = node.get("feature_selections", [])
    dictionary = _load_feature_dictionary()
    return (
        isinstance(children, list)
        and not children
        and isinstance(values, list)
        and dictionary is not None
        and any(normalize_name(value) in dictionary for value in values)
    )


@functools.lru_cache(maxsize=1)
def _load_feature_dictionary() -> frozenset[str] | None:
    try:
        source_xml, _ = _decode_xml(FEATURE_DICTIONARY_PATH.read_bytes())
        if source_xml is None:
            return None
        parser = etree.XMLParser(
            resolve_entities=False,
            load_dtd=False,
            no_network=True,
            recover=False,
            huge_tree=False,
        )
        root = etree.fromstring(_normalize_xml_declaration(source_xml).encode("utf-8"), parser=parser)
    except (OSError, etree.XMLSyntaxError, UnicodeError):
        return None
    return frozenset(
        normalize_name(item.get("name"))
        for item in root.findall(".//Item")
        if normalize_name(item.get("name"))
    )
```

After recursively parsing `children`, add:

```python
        if not children and not feature_values:
            add_issue(
                "missing_leaf_feature_selection",
                "叶子分组必须至少配置一个特征选择。",
                node_path,
            )
```

- [ ] **Step 4: Run focused tests**

```bash
.venv/bin/python -m pytest \
  tests/test_group_template_xml.py \
  tests/test_project_group_template_api.py -q
```

Expected: all focused tests pass.

- [ ] **Step 5: Commit leaf validation**

```bash
git add \
  process-plan-agent-api/app/services/group_template_xml.py \
  process-plan-agent-api/tests/test_group_template_xml.py \
  process-plan-agent-api/tests/test_project_group_template_api.py
git diff --cached --check
git commit -m "feat: validate template leaf features"
```

---

### Task 2: Add Independent Step-Mapping Persistence

**Files:**
- Modify: `process-plan-agent-api/app/models/models.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/project_group_templates.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_project_group_template_api.py`

**Interfaces:**
- Consumes: `is_feature_mapping_target()` from Task 1 and current template revision locking.
- Produces: `step_mappings_json`, `ProjectGroupStepMapping`, `replace_project_group_step_mappings()`, and `PUT /api/extract/group-templates/step-mappings`.

- [ ] **Step 1: Write failing storage and API tests**

Add a helper:

```python
def _step_mapping(path=None, *, step_order=1, step_name="钻孔", status="confirmed"):
    return {
        "source_operation_id": 11,
        "source_operation_name": "车削加工（A侧）",
        "source_step_order": step_order,
        "source_step_name": step_name,
        "scope_template_group_path": ["A侧"],
        "template_group_path": path or ["A侧", "孔"],
        "candidate_features": ["孔(盲孔)"] if status == "confirmed" else [],
        "match_mode": "any",
        "status": status,
        "confidence": 1.0,
        "source": "user_confirmed",
    }
```

Add API tests:

```python
def test_step_mapping_save_keeps_legacy_operation_aliases_separate(template_api_client):
    client = template_api_client
    payload = _template_xml()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()

    saved = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [_step_mapping()],
        },
    )

    assert saved.status_code == 200
    row = saved.json()["step_mappings"][0]
    assert row["source_step_key"] == "op_11_s01"
    assert row["source_step_text_hash"].startswith("sha256:")
    assert row["template_group_key"].startswith("grp_")
    assert row["candidate_features"] == ["孔(盲孔)"]
    assert saved.json()["mappings"] == []


def test_step_mapping_save_rejects_parent_targets_and_forged_features(template_api_client):
    client = template_api_client
    payload = _template_xml()
    preview = client.post(
        "/api/extract/group-templates/preview",
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()
    created = client.put(
        "/api/extract/group-templates/current",
        data={
            "project_id": str(client.project_id),
            "expected_content_hash": preview["content_hash"],
            "expected_template_revision": "0",
        },
        files={"file": ("template.xml", payload, "application/xml")},
    ).json()

    parent = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [_step_mapping(["A侧"])],
        },
    )
    forged = client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": client.project_id,
            "expected_template_revision": created["template_revision"],
            "mappings": [{**_step_mapping(), "candidate_features": ["不存在的特征"]}],
        },
    )

    assert parent.status_code == 422
    assert parent.json()["detail"] == "工步正式映射必须指向具有合法特征的叶子分组。"
    assert forged.status_code == 422
    assert forged.json()["detail"] == "候选特征不属于目标叶子分组。"
```

Add service tests for multiple targets and `not_applicable`:

```python
@pytest.mark.asyncio
async def test_step_mappings_allow_many_targets_and_explicit_not_applicable(template_store):
    _, sessions = template_store
    project_id = await _create_project(sessions)
    async with sessions() as db:
        await commit_project_group_template(db, project_id, _parsed("a.xml"), expected_revision=0)
        saved = await replace_project_group_step_mappings(
            db,
            project_id,
            [
                _step_mapping(),
                _step_mapping(step_order=2, step_name="检验", status="not_applicable"),
            ],
            expected_revision=1,
        )

    assert [item.status for item in saved.step_mappings] == ["confirmed", "not_applicable"]
    assert saved.step_mappings[1].template_group_path == []
```

- [ ] **Step 2: Verify RED**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_project_group_template_api.py -q
```

Expected: the model column, schemas, route and service function do not exist.

- [ ] **Step 3: Add the JSON column and maintenance migration**

In `ProjectGroupTemplate` add:

```python
step_mappings_json = Column(Text, nullable=False, default="[]")
```

Add `step_mappings_json TEXT NOT NULL DEFAULT '[]'` to the create-table SQL and then call:

```python
await ensure_column(
    "project_group_templates",
    "step_mappings_json",
    "step_mappings_json TEXT NOT NULL DEFAULT '[]'",
)
```

- [ ] **Step 4: Add exact Pydantic contracts**

Add to `schemas.py`:

```python
class GroupTemplateStepMappingIn(BaseModel):
    source_operation_id: int = Field(gt=0)
    source_operation_name: str = Field(min_length=1, max_length=255)
    source_step_order: int = Field(ge=1)
    source_step_name: str = Field(min_length=1, max_length=500)
    scope_template_group_path: List[str] = Field(default_factory=list)
    template_group_path: List[str] = Field(default_factory=list)
    candidate_features: List[str] = Field(default_factory=list)
    match_mode: Literal["any"] = "any"
    status: Literal["confirmed", "not_applicable"] = "confirmed"
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source: Literal["user_confirmed", "auto_confirmed", "legacy_migrated"] = "user_confirmed"


class GroupTemplateStepMappingOut(GroupTemplateStepMappingIn):
    source_step_key: str
    source_step_text_hash: str
    template_group_key: str = ""
    template_group_name: str = ""


class GroupTemplateStepMappingsUpdateRequest(BaseModel):
    project_id: int = Field(gt=0)
    expected_template_revision: int = Field(ge=1)
    mappings: List[GroupTemplateStepMappingIn] = Field(default_factory=list)
```

Import `Literal`. Add `step_mappings: List[GroupTemplateStepMappingOut] = []` to `ProjectGroupTemplateOut`, plus `kept_source_step_keys` and `invalidated_step_mappings` to `GroupTemplateCommitOut`.

- [ ] **Step 5: Implement canonical step records and persistence**

In `project_group_templates.py` add:

```python
@dataclass
class ProjectGroupStepMapping:
    source_operation_id: int
    source_operation_name: str
    source_step_key: str
    source_step_order: int
    source_step_name: str
    source_step_text_hash: str
    scope_template_group_path: list[str] = field(default_factory=list)
    template_group_path: list[str] = field(default_factory=list)
    candidate_features: list[str] = field(default_factory=list)
    match_mode: str = "any"
    status: str = "confirmed"
    confidence: float = 1.0
    source: str = "user_confirmed"
    template_group_key: str = ""
    template_group_name: str = ""


def stable_step_key(operation_id: int, step_order: int) -> str:
    return f"op_{int(operation_id)}_s{int(step_order):02d}"


def step_text_hash(value: object) -> str:
    normalized = normalize_name(value)
    return f"sha256:{hashlib.sha256(normalized.encode('utf-8')).hexdigest()}"
```

Add `import hashlib`. Extend `ProjectTemplateSnapshot` with `step_mappings`, and deserialize `row.step_mappings_json` separately from legacy `row.mappings_json`.

Resolve each record with this validation:

```python
def _resolve_step_mapping(
    mapping: object,
    index: dict[str, dict[str, object]],
) -> ProjectGroupStepMapping:
    operation_id = int(_mapping_value(mapping, "source_operation_id", 0) or 0)
    step_order = int(_mapping_value(mapping, "source_step_order", 0) or 0)
    step_name = normalize_name(_mapping_value(mapping, "source_step_name", ""))
    status = str(_mapping_value(mapping, "status", "confirmed"))
    base = ProjectGroupStepMapping(
        source_operation_id=operation_id,
        source_operation_name=normalize_name(_mapping_value(mapping, "source_operation_name", "")),
        source_step_key=stable_step_key(operation_id, step_order),
        source_step_order=step_order,
        source_step_name=step_name,
        source_step_text_hash=step_text_hash(step_name),
        match_mode="any",
        status=status,
        confidence=float(_mapping_value(mapping, "confidence", 1.0) or 0.0),
        source=str(_mapping_value(mapping, "source", "user_confirmed")),
    )
    if status == "not_applicable":
        return base

    target = _mapping_node(mapping, index)
    if target is None or not is_feature_mapping_target(target):
        raise HTTPException(422, "工步正式映射必须指向具有合法特征的叶子分组。")
    requested_features = {
        normalize_name(item)
        for item in _mapping_value(mapping, "candidate_features", [])
        if normalize_name(item)
    }
    node_features = {
        normalize_name(item)
        for item in target.get("feature_selections", [])
        if normalize_name(item)
    }
    if not requested_features or not requested_features.issubset(node_features):
        raise HTTPException(422, "候选特征不属于目标叶子分组。")
    scope_path = _mapping_value(mapping, "scope_template_group_path", [])
    normalized_scope = [normalize_name(item) for item in scope_path] if isinstance(scope_path, list) else []
    target_path = [normalize_name(item) for item in target.get("path", [])]
    if normalized_scope and target_path[:len(normalized_scope)] != normalized_scope:
        raise HTTPException(422, "目标叶子不在所选父分组范围内。")
    return ProjectGroupStepMapping(
        **base.__dict__,
        scope_template_group_path=normalized_scope,
        template_group_path=target_path,
        candidate_features=sorted(requested_features),
        template_group_key=str(target.get("key", "")),
        template_group_name=str(target.get("name", "")),
    )
```

When implementing, construct the final dataclass without passing duplicate keys from `base.__dict__`; explicitly copy the scalar fields shown above. Reject a step that mixes `not_applicable` and `confirmed`, and deduplicate identical `(source_step_key, canonical_path)` records before writing.

Add `replace_project_group_step_mappings()` using the same optimistic `UPDATE ... WHERE template_revision = :expected_revision RETURNING template_revision` pattern, but update only `step_mappings_json` and increment `template_revision`.

During template replacement, migrate new step mappings only when target path still resolves to a legal leaf and all candidate features remain present. Keep legacy `mappings_json` behavior unchanged.

- [ ] **Step 6: Add the route**

```python
@router.put("/group-templates/step-mappings", response_model=ProjectGroupTemplateOut)
async def save_group_template_step_mappings(
    body: GroupTemplateStepMappingsUpdateRequest,
    db: AsyncSession = Depends(get_db),
):
    await _ensure_project_exists(body.project_id, db)
    try:
        result = await replace_project_group_step_mappings(
            db,
            body.project_id,
            body.mappings,
            body.expected_template_revision,
        )
        await db.commit()
        return asdict(result)
    except Exception:
        await db.rollback()
        raise
```

- [ ] **Step 7: Run focused tests**

```bash
.venv/bin/python -m pytest \
  tests/test_project_group_template_api.py -q
```

Expected: all focused tests pass, including an old database gaining `step_mappings_json` without losing `mappings_json`.

- [ ] **Step 8: Commit persistence**

```bash
git add \
  process-plan-agent-api/app/models/models.py \
  process-plan-agent-api/app/services/db_schema_maintenance.py \
  process-plan-agent-api/app/schemas/schemas.py \
  process-plan-agent-api/app/services/project_group_templates.py \
  process-plan-agent-api/app/routers/extract.py \
  process-plan-agent-api/tests/test_project_group_template_api.py
git diff --cached --check
git commit -m "feat: persist template step mappings"
```

---

### Task 3: Generate Controlled Candidates Per Step

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/template_group_mapping.py`
- Modify: `process-plan-agent-api/app/routers/extract.py`
- Test: `process-plan-agent-api/tests/test_template_group_mapping.py`

**Interfaces:**
- Consumes: confirmed template leaf tree and `stable_step_key()`/`step_text_hash()` from Task 2.
- Produces: `POST /api/extract/template-step-mappings/suggest` with one suggestion per input workstep.

- [ ] **Step 1: Write failing per-step tests**

Add:

```python
def test_builds_candidates_for_each_step_without_returning_parent_groups():
    parsed = parse_group_template_xml("fixture.xml", _template_xml())
    operation = TemplateGroupMappingOperationIn(
        operation_id=1,
        operation_name="车削加工（A侧）",
        step_items=["平端面", "车外圆", "钻孔"],
    )

    prepared = template_group_mapping.prepare_step_candidates(operation, parsed.tree)

    assert [item.step_key for item, _ in prepared] == ["op_1_s01", "op_1_s02", "op_1_s03"]
    assert [[candidate.path for candidate in candidates] for _, candidates in prepared] == [
        [["A侧", "端面"]],
        [["A侧", "外圆"]],
        [["A侧", "孔"]],
    ]


@pytest.mark.asyncio
async def test_step_suggestions_keep_multiple_candidates_pending(mapping_store, monkeypatch):
    sessions, _ = mapping_store

    async def choose_both(*args, **kwargs):
        return json.dumps({"suggestions": [{
            "step_key": "op_360_s01",
            "group_ids": ["not-allowed"],
            "confidence": 0.99,
            "evidence": ["钻孔"],
            "reason": "invalid",
        }]})

    monkeypatch.setattr(template_group_mapping, "call_llm", choose_both)
    async with sessions() as db:
        result = await template_group_mapping.resolve_template_step_mappings(
            db,
            TemplateStepMappingSuggestRequest(
                project_id=7,
                expected_template_revision=1,
                operations=[TemplateGroupMappingOperationIn(
                    operation_id=360,
                    operation_name="加工",
                    step_items=["钻孔"],
                )],
            ),
        )

    suggestion = result.suggestions[0]
    assert suggestion.step_key == "op_360_s01"
    assert suggestion.recommended_group_ids == []
    assert suggestion.source == "unresolved"
    assert "候选范围" in "".join(suggestion.warnings)
```

Add a timeout regression asserting deterministic candidates remain in every step suggestion when `call_llm` raises.

- [ ] **Step 2: Verify RED**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_template_group_mapping.py -q
```

Expected: step request/response schemas and `prepare_step_candidates()` do not exist.

- [ ] **Step 3: Add step suggestion schemas**

```python
class TemplateStepMappingSuggestRequest(BaseModel):
    project_id: int = Field(gt=0)
    expected_template_revision: int = Field(ge=1)
    operations: List[TemplateGroupMappingOperationIn] = Field(default_factory=list)


class TemplateStepMappingSuggestionOut(BaseModel):
    operation_id: int
    operation_name: str
    step_key: str
    step_order: int
    step_name: str
    step_text_hash: str
    recommended_group_ids: List[str] = Field(default_factory=list)
    candidates: List[TemplateGroupMappingCandidateIn] = Field(default_factory=list)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = "unresolved"
    evidence: List[str] = Field(default_factory=list)
    reason: str = ""
    warnings: List[str] = Field(default_factory=list)


class TemplateStepMappingSuggestResponse(BaseModel):
    project_id: int
    template_revision: int
    model_used: bool = False
    suggestions: List[TemplateStepMappingSuggestionOut] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
```

- [ ] **Step 4: Split candidate scoring by step**

Add an internal immutable reference:

```python
@dataclass(frozen=True)
class TemplateStepRef:
    operation_id: int
    operation_name: str
    step_key: str
    step_order: int
    step_name: str
    step_text_hash: str
```

Add `from dataclasses import dataclass` and implement:

```python
def prepare_step_candidates(
    operation: TemplateGroupMappingOperationIn,
    tree: list[dict[str, object]],
) -> list[tuple[TemplateStepRef, list[TemplateGroupMappingCandidateIn]]]:
    prepared = []
    for order, raw_step in enumerate(operation.step_items, start=1):
        step_name = _clean_text(raw_step)
        if not step_name:
            continue
        ref = TemplateStepRef(
            operation_id=operation.operation_id,
            operation_name=operation.operation_name,
            step_key=stable_step_key(operation.operation_id, order),
            step_order=order,
            step_name=step_name,
            step_text_hash=step_text_hash(step_name),
        )
        candidates = build_step_candidates(ref, tree)
        prepared.append((ref, candidates))
    return prepared
```

`build_step_candidates()` must iterate only nodes where `is_feature_mapping_target(node)` is true. Score against `step.step_name`; use `step.operation_name` only to prefer matching ancestor paths such as A侧/B侧. If any candidate ancestor occurs in the operation name, remove candidates outside those matching ancestors.

- [ ] **Step 5: Validate model output per step**

Use `step_key` as the response key and accept `group_ids` only when every ID exists in that step's candidate set. A single deterministic candidate can be `auto_confirmed` without invoking the model; multiple candidates remain `unresolved` unless the model returns a legal subset with confidence at least `0.90` and verbatim evidence from `step_name` or `operation_name`.

The LLM prompt must contain this exact restriction:

```python
system_prompt = """你是机械加工工步与模板特征审核器。只输出 JSON，不要输出 Markdown。
每个 suggestion 只处理一个 step_key。你只能从该工步 candidates 中选择 group_ids，禁止创造或改写 ID。
证据必须逐字摘自 step_name 或 operation_name；无法可靠判断时返回空 group_ids。
输出格式：{"suggestions":[{"step_key":"op_1_s01","group_ids":["grp_x"],"confidence":0.9,"evidence":["钻孔"],"reason":"简短理由"}]}。"""
```

- [ ] **Step 6: Add the new endpoint without changing the old endpoint**

```python
@router.post("/template-step-mappings/suggest", response_model=TemplateStepMappingSuggestResponse)
async def suggest_template_step_mappings(
    body: TemplateStepMappingSuggestRequest,
    db: AsyncSession = Depends(get_db),
):
    return await resolve_template_step_mappings(db, body)
```

- [ ] **Step 7: Run focused tests**

```bash
.venv/bin/python -m pytest tests/test_template_group_mapping.py -q
```

Expected: old operation-level endpoint tests and new step-level tests all pass.

- [ ] **Step 8: Commit step suggestions**

```bash
git add \
  process-plan-agent-api/app/schemas/schemas.py \
  process-plan-agent-api/app/services/template_group_mapping.py \
  process-plan-agent-api/app/routers/extract.py \
  process-plan-agent-api/tests/test_template_group_mapping.py
git diff --cached --check
git commit -m "feat: suggest template mappings per step"
```

---

### Task 4: Add Frontend Step-Mapping Domain And API State

**Files:**
- Create: `process-plan-agent-ui/src/composables/templateStepMapping.ts`
- Create: `process-plan-agent-ui/src/composables/templateStepMapping.spec.ts`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts`
- Modify: `process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts`

**Interfaces:**
- Consumes: Task 2/3 API contracts and `TemplateOperation` from the existing helper.
- Produces: stable step refs, leaf/scope helpers, mapping records keyed by step and path, draft schema version `1`, and save/suggest API methods.

- [ ] **Step 1: Write failing pure-domain tests**

Create `templateStepMapping.spec.ts` with:

```typescript
import { describe, expect, it } from 'vitest'
import {
  buildTemplateStepRefs,
  createTemplateStepMapping,
  descendantFeatureLeaves,
  groupStepMappingsByStep,
  isFeatureLeaf,
  stepMappingKey,
} from './templateStepMapping'
import type { GroupTemplateNode } from '@/api/extract'

const leaf = (key: string, path: string[], features: string[]): GroupTemplateNode => ({
  key,
  source_id: '',
  name: path.at(-1) || '',
  path,
  feature_selections: features,
  params: {},
  children: [],
})

const tree: GroupTemplateNode[] = [{
  key: 'grp_a',
  source_id: '',
  name: 'A侧',
  path: ['A侧'],
  feature_selections: [],
  params: {},
  children: [
    leaf('grp_end', ['A侧', '端面'], ['轴端面']),
    leaf('grp_hole', ['A侧', '孔'], ['孔(盲孔)', '孔(通孔)']),
  ],
}]

describe('templateStepMapping', () => {
  it('builds stable one-based step refs', () => {
    expect(buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['平端面', '钻孔'] }))
      .toEqual([
        expect.objectContaining({ step_key: 'op_11_s01', step_order: 1, step_name: '平端面' }),
        expect.objectContaining({ step_key: 'op_11_s02', step_order: 2, step_name: '钻孔' }),
      ])
  })

  it('treats parents as scopes and leaves as formal targets', () => {
    expect(isFeatureLeaf(tree[0]!)).toBe(false)
    expect(isFeatureLeaf(tree[0]!.children[0]!)).toBe(true)
    expect(descendantFeatureLeaves(tree[0]!).map(item => item.key)).toEqual(['grp_end', 'grp_hole'])
  })

  it('allows one step to keep multiple leaf mappings', () => {
    const step = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['钻孔'] })[0]!
    const mapping = createTemplateStepMapping(step, tree[0]!.children[1]!, ['A侧'])
    const record = { [stepMappingKey(mapping)]: mapping }

    expect(groupStepMappingsByStep(record)[step.step_key]).toEqual([mapping])
    expect(mapping.candidate_features).toEqual(['孔(盲孔)', '孔(通孔)'])
  })
})
```

- [ ] **Step 2: Verify RED**

```bash
cd process-plan-agent-ui
npm test -- src/composables/templateStepMapping.spec.ts
```

Expected: the new module does not exist.

- [ ] **Step 3: Add API types and methods**

Add TypeScript equivalents of `GroupTemplateStepMappingInput`, `GroupTemplateStepMapping`, `TemplateStepMappingSuggestion`, and `TemplateStepMappingSuggestResponse`. Add `step_mappings` to `ProjectGroupTemplate` and `GroupTemplateCommitResult`.

Implement:

```typescript
export async function saveGroupTemplateStepMappings(
  projectId: number,
  revision: number,
  mappings: GroupTemplateStepMappingInput[],
) {
  const { data } = await api.put('/api/extract/group-templates/step-mappings', {
    project_id: projectId,
    expected_template_revision: revision,
    mappings,
  })
  return data as ProjectGroupTemplate
}

export async function suggestTemplateStepMappings(body: TemplateStepMappingSuggestRequest) {
  const { data } = await api.post('/api/extract/template-step-mappings/suggest', body)
  return data as TemplateStepMappingSuggestResponse
}
```

- [ ] **Step 4: Implement the pure step module**

Use these public signatures:

```typescript
export type TemplateStepRef = {
  operation_id: number
  operation_name: string
  step_key: string
  step_order: number
  step_name: string
}

export function buildTemplateStepRefs(operation: TemplateOperation): TemplateStepRef[]
export function isFeatureLeaf(node: GroupTemplateNode | null | undefined): boolean
export function descendantFeatureLeaves(node: GroupTemplateNode): GroupTemplateNode[]
export function createTemplateStepMapping(
  step: TemplateStepRef,
  leaf: GroupTemplateNode,
  scopePath?: string[],
): GroupTemplateStepMappingInput
export function stepMappingKey(mapping: Pick<GroupTemplateStepMappingInput, 'source_step_order' | 'source_operation_id' | 'template_group_path' | 'status'>): string
export function groupStepMappingsByStep(
  mappings: Record<string, GroupTemplateStepMappingInput>,
): Record<string, GroupTemplateStepMappingInput[]>
```

`buildTemplateStepRefs()` uses `op_${operationId}_s${String(order).padStart(2, '0')}` and drops blank step text. `createTemplateStepMapping()` throws when the target is not a feature leaf and copies all leaf features into `candidate_features`.

Add draft storage under `template_step_mapping_draft:<projectId>` with schema version `1`, `templateRevision`, `routeFingerprint`, and a cloned mapping array. Load only when all three identifiers match.

- [ ] **Step 5: Extend the project-template composable**

Add:

```typescript
const draftStepMappings = ref<GroupTemplateStepMappingInput[]>([])

function applyTemplate(snapshot: ProjectGroupTemplate) {
  template.value = snapshot
  draftMappings.value = mappingInputs(snapshot.mappings)
  draftStepMappings.value = snapshot.step_mappings.map(stepMappingInput)
  state.value = 'workspace'
}

async function saveStepMappings() {
  if (!template.value) return
  saving.value = true
  error.value = ''
  try {
    applyTemplate(await saveGroupTemplateStepMappings(
      unref(projectId),
      templateRevision.value,
      draftStepMappings.value,
    ))
  } catch (cause) {
    if (errorStatus(cause) === 409) await recoverFromConflict()
    else error.value = errorMessage(cause)
  } finally {
    saving.value = false
  }
}
```

Return `draftStepMappings` and `saveStepMappings` without removing the old fields or methods.

- [ ] **Step 6: Add composable tests**

Extend the template fixture with `step_mappings: []`. Mock `saveGroupTemplateStepMappings`, assign one draft step mapping, call `saveStepMappings()`, and assert the API receives the current template revision and the formal response replaces the draft.

- [ ] **Step 7: Run frontend domain tests**

```bash
npm test -- \
  src/composables/templateStepMapping.spec.ts \
  src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: tests and type checking pass.

- [ ] **Step 8: Commit frontend domain**

```bash
git add \
  process-plan-agent-ui/src/api/extract.ts \
  process-plan-agent-ui/src/composables/templateStepMapping.ts \
  process-plan-agent-ui/src/composables/templateStepMapping.spec.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.ts \
  process-plan-agent-ui/src/composables/useProjectGroupTemplate.spec.ts
git diff --cached --check
git commit -m "feat: model template mappings by step"
```

---

### Task 5: Rebuild The Mapping Dialog Around Expandable Steps

**Files:**
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue`
- Modify: `process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue`
- Test: `process-plan-agent-ui/src/composables/templateStepMapping.spec.ts`

**Interfaces:**
- Consumes: Task 4 step refs, leaf/scope helpers, draft mappings, and Task 3 suggestion API.
- Produces: parent-scope selection, expandable operation/step review, multi-leaf mappings, explicit `not_applicable`, and non-blocking automatic recognition.

- [ ] **Step 1: Add domain tests for completion and parent scopes**

Add:

```typescript
it('reports unresolved steps until mapped or explicitly skipped', () => {
  const steps = buildTemplateStepRefs({ id: 11, name: '车削A侧', step_items: ['平端面', '检验'] })
  const mapped = createTemplateStepMapping(steps[0]!, tree[0]!.children[0]!, ['A侧'])
  const skipped = createNotApplicableStepMapping(steps[1]!)

  expect(unresolvedTemplateSteps(steps, { [stepMappingKey(mapped)]: mapped })).toEqual([steps[1]])
  expect(unresolvedTemplateSteps(steps, {
    [stepMappingKey(mapped)]: mapped,
    [stepMappingKey(skipped)]: skipped,
  })).toEqual([])
})

it('uses a parent only to constrain descendant leaves', () => {
  expect(mappingTargetsForScope(tree[0]!).map(item => item.key)).toEqual(['grp_end', 'grp_hole'])
  expect(mappingTargetsForScope(tree[0]!.children[0]!).map(item => item.key)).toEqual(['grp_end'])
})
```

Implement `createNotApplicableStepMapping()`, `unresolvedTemplateSteps()`, and `mappingTargetsForScope()` in the pure module.

- [ ] **Step 2: Make both parents and leaves selectable in the tree**

In `TemplateGroupTreeNode.vue`, do not disable featureless parents. Add:

```typescript
const featureLeaf = computed(() => isFeatureLeaf(props.node))
const selectableScope = computed(() => featureLeaf.value || descendantFeatureLeaves(props.node).length > 0)
```

Use:

```vue
<button
  class="tgtn-main"
  type="button"
  :disabled="readonly || !selectableScope"
  :title="featureLeaf ? '选择特征分组' : selectableScope ? '选择组合范围' : '没有可用特征叶子'"
  @click="$emit('select', node.key)"
>
```

Render `特征` for leaves and `范围` for parents. Keep the disclosure button independent and enabled.

- [ ] **Step 3: Replace operation-level draft state in the dialog**

Use:

```typescript
const stepRefs = computed(() => props.operations.flatMap(buildTemplateStepRefs))
const draftStepMappings = ref<Record<string, GroupTemplateStepMappingInput>>({})
const selectedStepKeys = ref<string[]>([])
const expandedOperationIds = ref<number[]>([])
const recognizing = ref(false)
const recognitionProgress = ref({ completed: 0, total: 0 })

const activeScope = computed(() => (
  model.template.value
    ? findTemplateGroupByKey(model.template.value.tree, activeGroupKey.value)
    : null
))
const activeTargets = computed(() => activeScope.value ? mappingTargetsForScope(activeScope.value) : [])
const unresolvedSteps = computed(() => unresolvedTemplateSteps(
  stepRefs.value,
  draftStepMappings.value,
))
```

`syncDraftFromTemplate()` loads `template.step_mappings` first, then a matching local draft, and selects the first root with descendant leaves. It must not convert old operation aliases into formal step mappings without recognition.

- [ ] **Step 4: Render expandable operations and steps**

Replace the flat unmapped operation list with:

```vue
<article v-for="operation in operations" :key="operationId(operation)" class="tgmd-operation-card">
  <button class="tgmd-operation-toggle" type="button" @click="toggleOperationExpanded(operationId(operation))">
    <ArrowRight :class="{ open: operationExpanded(operationId(operation)) }" />
    <strong>{{ operation.name }}</strong>
    <span>{{ operationMappedSummary(operation) }}</span>
  </button>
  <div v-if="operationExpanded(operationId(operation))" class="tgmd-step-list">
    <label v-for="step in stepRefsForOperation(operation)" :key="step.step_key" class="tgmd-step-row">
      <input
        type="checkbox"
        :checked="selectedStepKeys.includes(step.step_key)"
        @change="toggleStep(step.step_key)"
      >
      <span class="tgmd-step-order">{{ step.step_order }}</span>
      <strong>{{ step.step_name }}</strong>
      <span>{{ stepMappingSummary(step) }}</span>
      <button type="button" @click.prevent="markStepNotApplicable(step)">不依赖模板特征</button>
    </label>
  </div>
</article>
```

Do not nest decorative cards; operation rows use a single border-bottom list treatment inside the existing pane.

- [ ] **Step 5: Implement leaf mapping and parent-range recognition**

For a selected leaf, map all selected steps directly:

```typescript
function mapSelectedStepsToLeaf() {
  if (!activeScope.value || !isFeatureLeaf(activeScope.value)) return
  const selected = new Set(selectedStepKeys.value)
  stepRefs.value.filter(step => selected.has(step.step_key)).forEach((step) => {
    const mapping = createTemplateStepMapping(step, activeScope.value!, activeScope.value!.path.slice(0, -1))
    draftStepMappings.value[stepMappingKey(mapping)] = mapping
  })
  selectedStepKeys.value = []
  persistStepDraft()
}
```

For a parent, call the suggestion API with only selected steps and then ignore every returned candidate outside `activeTargets`. Apply unique high-confidence candidates, leave ambiguous steps unresolved, and show `已完成 n / total` without replacing the workspace with a blocking loading page.

On first opening a template with no formal or local step mappings, wait for `nextTick()`, show the workspace, then call `void recognizeAllSteps()`; never await it from the dialog-open watcher.

- [ ] **Step 6: Guard formal save**

```typescript
async function saveStepMappings() {
  if (unresolvedSteps.value.length) {
    mappingWarnings.value = [`还有 ${unresolvedSteps.value.length} 个工步未处理。`]
    return
  }
  model.draftStepMappings.value = Object.values(draftStepMappings.value)
  await model.saveStepMappings()
  if (!model.error.value) {
    clearTemplateStepMappingDraft(props.projectId)
    emit('save', { stepMappings: model.template.value?.step_mappings || [] })
    closeDialog()
  }
}
```

Disable the save button while `unresolvedSteps.length > 0` or `model.saving.value`. Keep cancel available while recognition runs; closing increments the current run ID so late responses cannot modify state.

- [ ] **Step 7: Add restrained UI styles**

Use 4px radii, 36px stable control heights, a fixed 28px step-order column, and `min-width: 0` on text columns. Parent labels use neutral gray, feature labels use green, selected scope uses blue, and unresolved rows use amber. Do not introduce nested cards, gradients, or decorative elements.

- [ ] **Step 8: Run focused tests and build**

```bash
npm test -- \
  src/composables/templateStepMapping.spec.ts \
  src/composables/templateGroupMapping.spec.ts \
  src/composables/useProjectGroupTemplate.spec.ts
npm run build
```

Expected: tests and production build pass.

- [ ] **Step 9: Commit the dialog**

```bash
git add \
  process-plan-agent-ui/src/components/extract/TemplateGroupTreeNode.vue \
  process-plan-agent-ui/src/components/extract/TemplateGroupMappingDialog.vue \
  process-plan-agent-ui/src/composables/templateStepMapping.ts \
  process-plan-agent-ui/src/composables/templateStepMapping.spec.ts
git diff --cached --check
git commit -m "feat: map template features by process step"
```

---

### Task 6: Integrate Route Revisions And Clear Stale Step Mappings

**Files:**
- Modify: `process-plan-agent-api/app/services/project_workflow_lifecycle.py`
- Modify: `process-plan-agent-api/tests/test_workflow_invalidation.py`
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue`
- Modify: `process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue`
- Modify: `process-plan-agent-ui/src/composables/templateStepMapping.ts`
- Test: `process-plan-agent-ui/src/composables/templateStepMapping.spec.ts`

**Interfaces:**
- Consumes: persisted step mappings and draft storage from Tasks 2/4.
- Produces: route-change invalidation, project-level mapping count, and clean reopening after second-step rerun.

- [ ] **Step 1: Add backend invalidation test**

Seed a project template with two `step_mappings_json` entries, run `invalidate_project_workflow(..., from_step=2)`, and assert:

```python
assert result.deleted_template_step_mappings == 2
stored = await get_project_group_template(db, project.id)
assert stored is not None
assert json.loads(stored.step_mappings_json) == []
assert stored.source_xml
```

Also assert `from_step=3` and `from_step=4` leave step mappings unchanged.

- [ ] **Step 2: Implement lifecycle clearing**

Add `deleted_template_step_mappings: int = 0` to `WorkflowInvalidationResult`. In `from_step == 2`, load `ProjectGroupTemplate`, count its JSON list, set `step_mappings_json="[]"`, and increment `template_revision` once. Do not delete the template row or XML.

Use:

```python
template = (
    await db.execute(
        select(ProjectGroupTemplate).where(ProjectGroupTemplate.project_id == project_id)
    )
).scalar_one_or_none()
deleted_template_step_mappings = 0
if from_step == 2 and template is not None:
    try:
        stored = json.loads(template.step_mappings_json or "[]")
    except (TypeError, ValueError):
        stored = []
    deleted_template_step_mappings = len(stored) if isinstance(stored, list) else 0
    template.step_mappings_json = "[]"
    template.template_revision = int(template.template_revision or 0) + 1
```

Add imports for `json` and `ProjectGroupTemplate`.

- [ ] **Step 3: Add draft invalidation test**

In `templateStepMapping.spec.ts`, save a draft with route fingerprint `route-a`, then assert loading with `route-b` returns an empty array and clearing removes the storage key.

- [ ] **Step 4: Integrate the dialog without changing compatibility exports**

In `ExtractView.vue`:

```typescript
const projectWorkflowRevision = ref(0)
```

Set it from the selected project returned by `listProjects()`. Pass `templateMappingOperations` to the dialog and handle the new event:

```vue
<TemplateGroupMappingDialog
  v-model="templateGroupMappingVisible"
  :project-id="Number(projectId || 0)"
  :operations="templateMappingOperations"
  @save="handleTemplateStepMappingsSaved"
/>
```

```typescript
async function handleTemplateStepMappingsSaved(payload: { stepMappings: GroupTemplateStepMapping[] }) {
  if (!projectId.value) return
  await projectGroupTemplate.load()
  routeMergeNotice.value = payload.stepMappings.length
    ? `模板工步映射已保存，共 ${payload.stepMappings.length} 条。`
    : '模板工步映射已清空。'
}
```

Keep existing `templateGroupAliases`, route-segment metadata and compatibility export functions unchanged. Change only the header status/count to prefer `projectGroupTemplate.template.value?.step_mappings.length` for the new mapping badge.

When second-step reset succeeds, call `clearTemplateStepMappingDraft(projectId.value)` alongside the existing local workflow cleanup.

- [ ] **Step 5: Run lifecycle and frontend regression tests**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest tests/test_workflow_invalidation.py -q
cd ../process-plan-agent-ui
npm test -- src/composables/templateStepMapping.spec.ts
npm run build
```

Expected: reset clears only step mappings and draft, while the template XML still loads.

- [ ] **Step 6: Commit integration**

```bash
git add \
  process-plan-agent-api/app/services/project_workflow_lifecycle.py \
  process-plan-agent-api/tests/test_workflow_invalidation.py \
  process-plan-agent-ui/src/views/ExtractView.vue \
  process-plan-agent-ui/src/components/extract/ExtractRouteShellHeader.vue \
  process-plan-agent-ui/src/composables/templateStepMapping.ts \
  process-plan-agent-ui/src/composables/templateStepMapping.spec.ts
git diff --cached --check
git commit -m "fix: invalidate step mappings with route changes"
```

---

### Task 7: Full Regression And Browser Acceptance

**Files:**
- Verify: `process-plan-agent-api/tests`
- Verify: `process-plan-agent-ui/src`
- Verify fixture: `process-plan-agent-api/tests/fixtures/group_templates/临时壳体4.xml`
- Verify fixture: `process-plan-agent-api/tests/fixtures/group_templates/新衬套模板.xml`

**Interfaces:**
- Consumes: all Tasks 1-6.
- Produces: automated and browser evidence that the internal mapping workflow is complete without touching external compatibility code.

- [ ] **Step 1: Run all automated verification**

```bash
cd process-plan-agent-api
.venv/bin/python -m pytest -q
cd ../process-plan-agent-ui
npm test
npm run build
cd ..
git diff --check
```

Expected: all API/UI tests pass and build exits `0`.

- [ ] **Step 2: Verify valid and invalid template preview**

At `http://127.0.0.1:5173/extract?project_id=51&resume=route_merge&from=analysis`:

1. Open `模板分组映射` and replace with `临时壳体4.xml`.
2. Verify preview reports standard validation passed and confirmation remains enabled after file-picker focus returns.
3. Cancel replacement and verify the confirmed template remains.
4. Preview `新衬套模板.xml`.
5. Verify the empty leaf issue shows its full path and confirmation is disabled.

- [ ] **Step 3: Verify step-level mapping interaction**

1. Open the confirmed template workspace; verify it appears immediately while recognition continues in a compact status strip.
2. Expand `车削加工（A侧）`; verify its worksteps are separate rows.
3. Select the `A侧` parent; verify it acts as a range and does not appear as a formal target chip.
4. Map `平端面` to `A侧 / 端面` and `钻孔` to one or more `A侧 / 孔` candidates.
5. Mark one non-feature workstep as `不依赖模板特征`.
6. Verify the operation header displays a derived matched count and unresolved worksteps block save.
7. Resolve all worksteps, save, close, reopen, and verify mappings restore from the server.

- [ ] **Step 4: Verify route reset invalidation**

1. Trigger second-step rerun and confirm the warning.
2. After reset, reopen template mapping.
3. Verify the XML template remains confirmed but old step mappings and local draft are gone.

- [ ] **Step 5: Inspect repository scope**

```bash
git status --short --branch
git log --oneline -10
git diff --check
git diff HEAD~6..HEAD --name-only | rg 'kmai|Kmai|KmAI' && exit 1 || true
```

Expected: only intended internal API/UI/docs files changed; no external compatibility files appear; `.vscode/` and `outputs/` remain untracked.

- [ ] **Step 6: Commit the implementation plan**

```bash
git add docs/superpowers/plans/2026-07-31-group-template-leaf-feature-validation.md
git diff --cached --check
git commit -m "docs: plan internal template step mapping"
```
