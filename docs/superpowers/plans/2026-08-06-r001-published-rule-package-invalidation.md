# R-001 Published Rule Package Invalidation Implementation Plan

> - 状态：已实施，验证通过

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 在第四步条件来源发生实际变化时事务化归档当前规则包，并在第五步执行 V2 包前再次拒绝与服务端确认记录不一致的包。

**Architecture:** 在现有规则包生命周期服务中增加不提交事务的 `archive_published_rule_packages()` 原语，由条件审核应用服务在实际状态转换后调用。执行服务继续负责加载和指纹校验，并增加 V2 用户规则来源防御校验；生成路由只在防御校验发现历史漂移时提交归档状态，然后返回现有结构化 `409`。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy AsyncSession、Pydantic V2、SQLite、pytest、Vue 3/Vitest（仅兼容回归）

## Global Constraints

- 保持 FastAPI 路由拥有 `commit()` / `rollback()`；服务层只能修改 ORM 状态和 `flush()`。
- 失效但尚无替代版本的规则包使用 `archived`；只有新版本替代旧版本时使用 `superseded`。
- 不增加数据库列、迁移、运行时依赖或通用 Unit of Work 抽象。
- 不修改 V2 JSON、KmAI V1 JSON、ZIP、内容哈希或成功响应契约。
- V1 不增加来源推断校验，只共享写入时归档行为。
- 不删除历史 `GeneratedRoute`，但来源漂移请求不得创建新的 `GeneratedRoute`。
- 保留当前工作区所有未跟踪设计文档和截图。
- 未经用户明确授权，不执行 `git add`、`git commit`、`git push`、rebase、reset 或分支操作。

---

## File Map

| 文件 | 责任 |
| --- | --- |
| `process-plan-agent-api/app/services/rule_packages/lifecycle.py` | 新增项目级当前发布包归档原语 |
| `process-plan-agent-api/app/services/rule_packages/condition_review_service.py` | 在草稿、解析、确认、人工设定和旧审核迁移的实际状态变化后归档 |
| `process-plan-agent-api/app/services/rule_packages/execution.py` | 执行前验证 V2 包内用户规则来源；发现漂移时归档并抛出领域异常 |
| `process-plan-agent-api/app/routers/generate.py` | 提交防御性归档并映射现有 `published_rule_package_changed` 409 |
| `process-plan-agent-api/tests/test_rule_package_lifecycle.py` | 生命周期原语和条件接口集成测试 |
| `process-plan-agent-api/tests/test_condition_review_service.py` | 服务层变化判定、缓存和事务归属测试 |
| `process-plan-agent-api/tests/test_generate_v2_production.py` | 执行期漂移、包归档和零生成副作用测试 |
| `docs/重构与优化跟踪.md` | 记录状态、实际文件、验证证据和剩余风险 |

---

### Task 1: Add the caller-owned package archive primitive

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/lifecycle.py:24`
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`

**Interfaces:**
- Consumes: `FinalizedRulePackage`, `AsyncSession`, project ID.
- Produces: `archive_published_rule_packages(project_id: int, db: AsyncSession) -> list[int]`.
- Guarantee: only current `published` rows for the target project become `archived`; the function flushes but never commits.

- [ ] **Step 1: Write the failing lifecycle test**

Add the lifecycle import:

```python
from app.services.rule_packages.lifecycle import (
    archive_published_rule_packages,
    publish_rule_package,
)
```

Add this test using the existing `lifecycle_client.lifecycle_session_factory`:

```python
def test_archive_published_rule_packages_is_project_scoped_and_caller_owned(lifecycle_client):
    async def run():
        factory = lifecycle_client.lifecycle_session_factory
        async with factory() as db:
            db.add(Project(id=13, name="other project", status="ROUTE_SET_READY"))
            db.add_all([
                FinalizedRulePackage(
                    project_id=12,
                    version=1,
                    package_name="target-current",
                    schema_version="2.0",
                    status="published",
                ),
                FinalizedRulePackage(
                    project_id=12,
                    version=0,
                    package_name="target-history",
                    schema_version="2.0",
                    status="superseded",
                ),
                FinalizedRulePackage(
                    project_id=13,
                    version=1,
                    package_name="other-current",
                    schema_version="2.0",
                    status="published",
                ),
            ])
            await db.commit()

        async with factory() as db:
            archived_versions = await archive_published_rule_packages(12, db)
            statuses = dict((await db.execute(
                select(FinalizedRulePackage.package_name, FinalizedRulePackage.status)
            )).all())
            assert archived_versions == [1]
            assert statuses == {
                "target-current": "archived",
                "target-history": "superseded",
                "other-current": "published",
            }
            await db.rollback()

        async with factory() as db:
            statuses = dict((await db.execute(
                select(FinalizedRulePackage.package_name, FinalizedRulePackage.status)
            )).all())
            assert statuses["target-current"] == "published"
            assert statuses["other-current"] == "published"

    asyncio.run(run())
```

The production change this test catches is either a missing project filter, use of `superseded`, or a hidden commit.

- [ ] **Step 2: Run the test and verify RED**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_lifecycle.py::test_archive_published_rule_packages_is_project_scoped_and_caller_owned -q
```

Expected: collection fails because `archive_published_rule_packages` does not exist.

- [ ] **Step 3: Implement the minimal lifecycle function**

Add this function beside `supersede_published_rule_packages()`:

```python
async def archive_published_rule_packages(
    project_id: int,
    db: AsyncSession,
) -> list[int]:
    rows = (
        await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == project_id,
                FinalizedRulePackage.status == "published",
            )
        )
    ).scalars().all()
    for row in rows:
        row.status = "archived"
    await db.flush()
    return sorted(int(row.version or 0) for row in rows)
```

Do not modify `Project.status`, `GeneratedRoute`, `supersedes_id`, or `published_at`.

- [ ] **Step 4: Run the focused lifecycle tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_lifecycle.py::test_archive_published_rule_packages_is_project_scoped_and_caller_owned tests/test_rule_package_api.py::test_download_rejects_archived_package -q
```

Expected: both tests pass; no new warning other than the known TestClient/httpx deprecation warning.

- [ ] **Step 5: Review the task diff; commit only after explicit authorization**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
git diff -- process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
```

Authorized commit command, not to be executed without user approval:

```powershell
git add process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
git commit -m "修复：增加规则包事务化归档能力"
```

---

### Task 2: Archive the current package when a condition draft actually changes

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_review_service.py:182`
- Test: `process-plan-agent-api/tests/test_condition_review_service.py`
- Test: `process-plan-agent-api/tests/test_rule_package_lifecycle.py`

**Interfaces:**
- Consumes: Task 1 `archive_published_rule_packages()`.
- Produces: `save_condition_draft()` archives only after a real normalized source change.
- API contract: `/rule-conditions/draft` response remains `RuleConditionReviewResponse`.

- [ ] **Step 1: Add real database test helpers**

Extend imports in `test_condition_review_service.py`:

```python
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.rule_packages.condition_contracts import (
    ConfirmRuleConditionRequest,
    ParseRuleConditionRequest,
    RuleConditionCandidate,
    RuleConditionProcessOption,
    SaveRuleConditionDraftRequest,
)
```

Add helpers:

```python
def _published_package(project_id: int = 7, version: int = 1) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        project_id=project_id,
        version=version,
        package_name=f"published-{project_id}-{version}",
        schema_version="2.0",
        status="published",
    )


async def _package_status(db, project_id: int = 7) -> str:
    return (await db.execute(
        select(FinalizedRulePackage.status).where(
            FinalizedRulePackage.project_id == project_id,
        )
    )).scalar_one()
```

Also add `from sqlalchemy import select`.

- [ ] **Step 2: Write failing changed/no-op service tests**

```python
@pytest.mark.asyncio
async def test_save_draft_archives_package_without_committing(db):
    package = _published_package()
    db.add(package)
    await db.commit()
    body = SaveRuleConditionDraftRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
    )

    response = await service.save_condition_draft(body, db)

    assert response.review.status == "draft"
    assert await _package_status(db) == "archived"
    await db.rollback()
    assert await _package_status(db) == "published"


@pytest.mark.asyncio
async def test_save_unchanged_draft_keeps_package_published(db):
    body = SaveRuleConditionDraftRequest(
        project_id=7,
        route_id=1,
        segment_id="process_grind_outer",
        source_text="outer diameter reaches IT8",
    )
    await service.save_condition_draft(body, db)
    await db.commit()
    db.add(_published_package())
    await db.commit()

    await service.save_condition_draft(body, db)

    assert await _package_status(db) == "published"
```

The first test catches a missing invalidation call and a hidden service commit. The second catches unconditional invalidation.

- [ ] **Step 3: Run both tests and verify RED**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_condition_review_service.py::test_save_draft_archives_package_without_committing tests/test_condition_review_service.py::test_save_unchanged_draft_keeps_package_published -q
```

Expected: the changed-draft test fails because the package remains `published`; the no-op test passes.

- [ ] **Step 4: Implement draft invalidation after the existing no-op guard**

Import Task 1's helper:

```python
from app.services.rule_packages.lifecycle import archive_published_rule_packages
```

Update only the changed path:

```python
    apply_state_update(
        review,
        new_draft_update(source_text, source_hash, FIELD_REGISTRY_VERSION),
    )
    await archive_published_rule_packages(body.project_id, db)
    return review_response(body, review)
```

Keep the existing early return for identical source text and hash before this block.

- [ ] **Step 5: Add the endpoint-level persistence test**

Add to `test_rule_package_lifecycle.py`:

```python
def test_changed_condition_draft_archives_published_package_but_noop_does_not(
    lifecycle_client,
    rule_package_v2_payload,
):
    source_text = "当存在孔精加工要求时，纳入铣槽工序"
    initial = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/draft",
        json={
            "project_id": 12,
            "route_id": 31,
            "segment_id": "process_mill_slot",
            "source_text": source_text,
        },
    )
    assert initial.status_code == 200
    published = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert published.status_code == 200

    unchanged = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/draft",
        json={
            "project_id": 12,
            "route_id": 31,
            "segment_id": "process_mill_slot",
            "source_text": source_text,
        },
    )
    assert unchanged.status_code == 200
    assert lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    ).status_code == 200

    changed = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/draft",
        json={
            "project_id": 12,
            "route_id": 31,
            "segment_id": "process_mill_slot",
            "source_text": f"{source_text}，且表面粗糙度满足要求",
        },
    )
    assert changed.status_code == 200
    assert lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    ).status_code == 404
    rows = lifecycle_client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    ).json()
    assert rows[0]["status"] == "archived"
```

- [ ] **Step 6: Run service and endpoint tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_condition_review_service.py tests/test_rule_package_lifecycle.py::test_changed_condition_draft_archives_published_package_but_noop_does_not -q
```

Expected: all selected tests pass.

- [ ] **Step 7: Review the task diff; commit only after explicit authorization**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/condition_review_service.py process-plan-agent-api/tests/test_condition_review_service.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
```

Authorized commit command:

```powershell
git add process-plan-agent-api/app/services/rule_packages/condition_review_service.py process-plan-agent-api/tests/test_condition_review_service.py process-plan-agent-api/tests/test_rule_package_lifecycle.py
git commit -m "修复：条件草稿变化后归档旧规则包"
```

---

### Task 3: Complete the condition transition invalidation matrix

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_review_service.py:198-417`
- Modify: `process-plan-agent-api/app/services/rule_packages/condition_review_service.py:420-544`
- Test: `process-plan-agent-api/tests/test_condition_review_service.py`
- Test: `process-plan-agent-api/tests/test_rule_condition_parser.py`

**Interfaces:**
- Consumes: Task 1 archive helper and Task 2 draft behavior.
- Produces: non-cache parse preparation, successful confirmation, successful manual confirmation, and changed legacy migrations archive the current package.
- Preserves: cache hits, stale parse completion, failed validation, and unchanged migrations do not archive.

- [ ] **Step 1: Extend the cache test to cover package status**

In `test_prepare_parse_returns_cached_response_without_reparsing()`, after completing and committing the first parse, add a current package, then assert the cache hit preserves it and a source change archives it:

```python
    db.add(_published_package())
    await db.commit()

    cached = await service.prepare_condition_parse(parse_request, db)
    assert cached.cache_hit is True
    assert await _package_status(db) == "published"

    changed = await service.prepare_condition_parse(
        parse_request.model_copy(update={"source_text": "outer diameter reaches IT7"}),
        db,
    )
    assert changed.cache_hit is False
    assert await _package_status(db) == "archived"
```

- [ ] **Step 2: Write a successful confirmation invalidation test**

Use a bound scalar factor so the test reaches the state transition:

```python
@pytest.mark.asyncio
async def test_confirm_archives_published_package(db, parse_request):
    _, review = await load_route_and_review(7, 1, "process_grind_outer", db)
    source_text = parse_request.source_text.strip()
    source_hash = condition_source_hash(source_text)
    candidate = RuleConditionCandidate.model_validate({
        "kind": "condition",
        "when": {
            "field": "precision.outer_diameter_it",
            "op": "lte",
            "value": 8,
            "factor_id": "precision.outer_diameter_it",
        },
        "then": {
            "include_process_ids": ["process_grind_outer"],
            "exclude_process_ids": [],
        },
    })
    review.condition_source_text = source_text
    review.condition_source_hash = source_hash
    review.condition_status = "pending_confirmation"
    review.condition_candidate_json = candidate.model_dump_json()
    db.add(_published_package())
    await db.commit()

    await service.confirm_condition_review(
        ConfirmRuleConditionRequest(
            project_id=7,
            route_id=1,
            segment_id="process_grind_outer",
            source_text=source_text,
            source_hash=source_hash,
            candidate=candidate,
            processes=parse_request.processes,
            confirmed_by="reviewer",
        ),
        db,
    )

    assert await _package_status(db) == "archived"
```

- [ ] **Step 3: Extend the existing manual Boolean test**

In `test_manual_boolean_rule_is_confirmed_without_model_parsing()`:

1. Import `FinalizedRulePackage`.
2. Seed a `Project(id=7, name="manual")` before the route if the fixture does not already contain it.
3. Seed this package in the same transaction:

```python
FinalizedRulePackage(
    project_id=7,
    version=1,
    package_name="manual-current",
    schema_version="2.0",
    status="published",
)
```

4. After `set_manual_condition_review()`, assert with a real query:

```python
        package_status = (await session.execute(
            select(FinalizedRulePackage.status).where(
                FinalizedRulePackage.project_id == 7,
            )
        )).scalar_one()
        assert package_status == "archived"
```

Use the current candidate and request body unchanged; do not create a second manual-rule fixture.

- [ ] **Step 4: Add changed/unchanged legacy migration assertions**

Add `FinalizedRulePackage` to the existing model import in `test_rule_condition_parser.py`:

```python
from app.models.models import (
    FinalizedRulePackage,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
```

In `test_invalidates_legacy_nondestructive_process_relation_for_re_review()`, create `package` before committing:

```python
        package = FinalizedRulePackage(
            project_id=7,
            version=1,
            package_name="legacy-ndt-current",
            schema_version="2.0",
            status="published",
        )
        session.add(Project(id=7, name="legacy NDT"))
        session.add(package)
```

After the existing review assertions, add:

```python
        assert package.status == "archived"
```

In `test_migrates_only_valid_unpublished_standard_factor_reviews()`, add this row to the existing `session.add_all([...])` list:

```python
            FinalizedRulePackage(
                project_id=7,
                version=1,
                package_name="legacy-factor-current",
                schema_version="2.0",
                status="published",
            ),
```

Replace the two adjacent migration calls with literal status assertions around the second no-op call:

```python
        assert await migrate_legacy_standard_factor_reviews(route, session) is True
        package = (await session.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == 7,
            )
        )).scalar_one()
        assert package.status == "archived"

        package.status = "published"
        await session.flush()
        assert await migrate_legacy_standard_factor_reviews(route, session) is False
        assert package.status == "published"
```

The expected status values must be literal strings. Do not calculate them through lifecycle helpers.

- [ ] **Step 5: Run the new tests and verify RED**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_condition_review_service.py::test_prepare_parse_returns_cached_response_without_reparsing tests/test_condition_review_service.py::test_confirm_archives_published_package tests/test_rule_condition_parser.py::test_manual_boolean_rule_is_confirmed_without_model_parsing -q
..\.runtime\python\python.exe -m pytest tests/test_rule_condition_parser.py -k "legacy or migrat" -q
```

Expected: package-status assertions fail because only draft writes currently archive.

- [ ] **Step 6: Implement the remaining invalidation calls**

In `prepare_condition_parse()`, add the call only after the non-cache parsing state is applied:

```python
    apply_state_update(
        review,
        parsing_update(source_text, source_hash, parser_version, FIELD_REGISTRY_VERSION),
    )
    await archive_published_rule_packages(body.project_id, db)
```

In `confirm_condition_review()` and `set_manual_condition_review()`, add this after each successful `apply_state_update()` and before response serialization:

```python
    await archive_published_rule_packages(body.project_id, db)
```

Do not add an invalidation call to `complete_condition_parse()`; the prepare transaction has already archived the old package.

At the end of `invalidate_legacy_nondestructive_relation_reviews()`, archive only after an actual change:

```python
    if changed:
        await archive_published_rule_packages(route.project_id, db)
    return changed
```

Apply the same changed-only block at the end of `migrate_legacy_standard_factor_reviews()`. Keep `migrate_legacy_condition_reviews()` as the existing Boolean aggregator; when both lower migrations change data, the second archive call is a harmless no-op because no `published` row remains.

- [ ] **Step 7: Run the focused condition suites and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_condition_review_state.py tests/test_condition_review_repository.py tests/test_condition_review_service.py tests/test_rule_condition_parser.py tests/test_rule_package_lifecycle.py -q
```

Expected: all selected tests pass; cache-hit assertions prove the current package remains published when there is no state change.

- [ ] **Step 8: Review the task diff; commit only after explicit authorization**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/condition_review_service.py process-plan-agent-api/tests/test_condition_review_service.py process-plan-agent-api/tests/test_rule_condition_parser.py
```

Authorized commit command:

```powershell
git add process-plan-agent-api/app/services/rule_packages/condition_review_service.py process-plan-agent-api/tests/test_condition_review_service.py process-plan-agent-api/tests/test_rule_condition_parser.py
git commit -m "修复：补全条件审核规则包失效链路"
```

---

### Task 4: Reject and archive a source-drifted V2 package before planning

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/execution.py:30-86`
- Modify: `process-plan-agent-api/app/routers/generate.py:57-65`
- Modify: `process-plan-agent-api/app/routers/generate.py:1024-1033`
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- Consumes: `v2_package_from_row()`, `require_confirmed_user_rule_sources()`, Task 1 archive primitive.
- Produces: `PublishedRulePackageSourcesChanged` with the existing `published_rule_package_changed` detail code.
- Router behavior: commit only the defensive archive, return `409`, and skip planning/persistence.

- [ ] **Step 1: Add test imports and status helper**

Extend test imports:

```python
from datetime import datetime, timezone

from app.models.models import (
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
```

Add:

```python
async def _rule_package_status(session_factory, project_id: int) -> str:
    async with session_factory() as db:
        return (await db.execute(
            select(FinalizedRulePackage.status).where(
                FinalizedRulePackage.project_id == project_id,
            )
        )).scalar_one()
```

- [ ] **Step 2: Add a stale-source seed helper**

```python
async def _seed_source_drifted_v2(session_factory) -> tuple[int, dict[str, Any]]:
    confirmed_at = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)

    def configure(payload: dict[str, Any]) -> None:
        rule = payload["route_rules"]["rules"][0]
        rule.update({
            "source": "user_confirmed",
            "source_segment_id": "segment-quench",
            "source_text": "材料与硬度满足条件时纳入淬火",
            "confirmed_by": "reviewer",
            "confirmed_at": confirmed_at.isoformat(),
        })

    project_id, payload = await _seed_published_v2(
        session_factory,
        "v2-source-drift",
        configure,
    )
    rule = payload["route_rules"]["rules"][0]
    candidate = {
        "kind": "condition",
        "when": rule["when"],
        "then": {
            "include_process_ids": rule["then"]["include_process_ids"],
            "exclude_process_ids": rule["then"]["exclude_process_ids"],
        },
    }
    async with session_factory() as db:
        route = NormalizedRouteVersion(
            project_id=project_id,
            version=1,
            route_json=json.dumps([{"id": "segment-quench"}], ensure_ascii=False),
        )
        db.add(route)
        await db.flush()
        db.add(NormalizedRouteSegmentRuleReview(
            project_id=project_id,
            route_version_id=route.id,
            segment_id="segment-quench",
            condition_source_text="数据库中已经变化的条件",
            condition_source_hash="changed-source",
            condition_status="confirmed",
            condition_candidate_json=json.dumps(candidate, ensure_ascii=False),
            condition_confirmed_json=json.dumps(candidate, ensure_ascii=False),
            condition_confirmed_by="reviewer",
            condition_confirmed_at=confirmed_at,
        ))
        package = (await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == project_id,
            )
        )).scalar_one()
        package.route_version_id = route.id
        await db.commit()
    return project_id, payload
```

This fixture deliberately bypasses condition endpoints so the execution guard, rather than eager invalidation, must catch the drift.

- [ ] **Step 3: Write the failing production-generation test**

```python
def test_generate_archives_source_drifted_v2_before_planning(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_source_drifted_v2(session_factory))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            **fingerprint,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "published_rule_package_changed",
        "message": "当前规则内容已变化，请返回第四步重新发布后再生成。",
        "current_rule_package": None,
    }
    assert asyncio.run(_rule_package_status(session_factory, project_id)) == "archived"
    _assert_generation_not_persisted(session_factory, project_id)
```

The production change this test catches is any path that plans before checking server-owned confirmation sources, returns a non-structured error, fails to persist the archive, or writes a generated route.

- [ ] **Step 4: Run the test and verify RED**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py::test_generate_archives_source_drifted_v2_before_planning -q
```

Expected: the request currently returns 200 and persists a route because the package fingerprint still matches.

- [ ] **Step 5: Add the source-drift domain exception and execution check**

In `execution.py`, add imports:

```python
from app.services.rule_packages.confirmation_validation import (
    ConfirmedRuleSourcesChanged,
    require_confirmed_user_rule_sources,
)
from app.services.rule_packages.lifecycle import archive_published_rule_packages
```

Add the typed exception:

```python
class PublishedRulePackageSourcesChanged(Exception):
    def __init__(self):
        self.detail = {
            "code": "published_rule_package_changed",
            "message": "当前规则内容已变化，请返回第四步重新发布后再生成。",
            "current_rule_package": None,
        }
        super().__init__(self.detail["message"])
```

After the existing client fingerprint mismatch block and before returning `current`, add:

```python
    if str(current.schema_version or "1.0") == "2.0":
        package = v2_package_from_row(current)
        try:
            await require_confirmed_user_rule_sources(
                package,
                project_id=project_id,
                route_version_id=int(current.route_version_id or 0),
                db=db,
            )
        except ConfirmedRuleSourcesChanged as exc:
            await archive_published_rule_packages(project_id, db)
            raise PublishedRulePackageSourcesChanged() from exc
```

Do not run this check for V1.

- [ ] **Step 6: Commit the defensive archive at the router boundary**

Import `PublishedRulePackageSourcesChanged` in `generate.py`. Catch it before `PublishedRulePackageChanged`:

```python
    except PublishedRulePackageSourcesChanged as exc:
        try:
            await db.commit()
        except Exception:
            await db.rollback()
            raise
        raise HTTPException(status_code=409, detail=exc.detail) from exc
    except PublishedRulePackageChanged as exc:
        raise HTTPException(status_code=409, detail=exc.detail) from exc
```

No operation, input normalization, planning, fallback, project-status change, or `GeneratedRoute` write may move above this block.

- [ ] **Step 7: Run execution tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py tests/test_workflow_invalidation.py -q
```

Expected: the new drift test and all existing fingerprint, source confirmation, V1 and V2 generation tests pass.

- [ ] **Step 8: Run the mutation check**

Confirm mentally and through targeted reruns that each change is protected:

- Removing `require_confirmed_user_rule_sources()` makes the drift test return 200.
- Removing the archive call leaves package status `published`.
- Moving the check after persistence makes `_assert_generation_not_persisted()` fail.
- Changing the error code breaks the literal response assertion and the existing frontend utility contract.

- [ ] **Step 9: Review the task diff; commit only after explicit authorization**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/routers/generate.py process-plan-agent-api/tests/test_generate_v2_production.py
```

Authorized commit command:

```powershell
git add process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/routers/generate.py process-plan-agent-api/tests/test_generate_v2_production.py
git commit -m "修复：执行前拒绝来源过期的规则包"
```

---

### Task 5: Run regression gates and close the tracking item

**Files:**
- Modify: `docs/重构与优化跟踪.md`
- Modify: `docs/superpowers/specs/2026-08-06-r001-published-rule-package-invalidation-design.md`
- Modify: `docs/superpowers/plans/2026-08-06-r001-published-rule-package-invalidation.md`

**Interfaces:**
- Consumes: Tasks 1-4 completed code and test output.
- Produces: verified `R-001` evidence, checked acceptance boxes, actual file list, and remaining-risk record.

- [ ] **Step 1: Run the complete focused backend regression**

From `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_lifecycle.py tests/test_condition_review_state.py tests/test_condition_review_repository.py tests/test_condition_review_service.py tests/test_rule_condition_parser.py tests/test_rule_package_api.py tests/test_generate_v2_production.py tests/test_workflow_invalidation.py tests/test_rule_package_archive.py tests/test_kmai_rule_package_export.py tests/test_kmai_export_routes.py tests/test_kmai_export_factors.py tests/test_kmai_export_context.py tests/test_kmai_export_conditions.py tests/test_kmai_compatibility_runner.py -q
```

Expected: zero failures. Record the exact passed/skipped/warning counts from pytest output.

- [ ] **Step 2: Run the full backend suite**

```powershell
..\.runtime\python\python.exe -m pytest tests -q
```

Expected: zero failures. Do not reuse the earlier baseline count; record the fresh result.

- [ ] **Step 3: Run the frontend error-contract regression**

From `process-plan-agent-ui/`:

```powershell
npm.cmd test -- src/utils/generateRulePackageContext.spec.ts
npm.cmd run build
```

Expected: the utility test recognizes `published_rule_package_changed`; `vue-tsc` and Vite build succeed.

- [ ] **Step 4: Run repository and document checks**

From the repository root:

```powershell
git diff --check
git status --short --branch
```

Also verify both Markdown files have even code-fence counts, no trailing whitespace, and no unresolved placeholder markers.

- [ ] **Step 5: Update tracking evidence**

In `docs/重构与优化跟踪.md`:

1. Change `R-001` from `进行中` to `已完成` only after every acceptance assertion passes.
2. Check each R-001 acceptance box individually.
3. Add the actual modified files.
4. Record exact focused/full/backend/frontend/build commands and result counts.
5. Add a dated change-record row stating that condition writes now archive old packages and execution rejects source drift.
6. Record remaining scope: `segment-rule-reviews` transaction/invalidation remains in `R-003`; service status aggregation remains in `R-006`.

In the design and plan documents, change status to implemented only after fresh verification.

- [ ] **Step 6: Review all task changes; commit only after explicit authorization**

```powershell
git diff --stat
git diff --check
git status --short
```

Confirm that pre-existing untracked specs and screenshots remain untouched.

Authorized final commit command:

```powershell
git add docs/重构与优化跟踪.md docs/superpowers/specs/2026-08-06-r001-published-rule-package-invalidation-design.md docs/superpowers/plans/2026-08-06-r001-published-rule-package-invalidation.md process-plan-agent-api/app/services/rule_packages/lifecycle.py process-plan-agent-api/app/services/rule_packages/condition_review_service.py process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/routers/generate.py process-plan-agent-api/tests/test_rule_package_lifecycle.py process-plan-agent-api/tests/test_condition_review_service.py process-plan-agent-api/tests/test_rule_condition_parser.py process-plan-agent-api/tests/test_generate_v2_production.py
git commit -m "修复：规则变化后阻止旧发布包继续执行"
```

Do not run this command unless the user separately authorizes a commit.
