# R-003 Route Write Transaction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **执行结果（2026-08-07）：** 已完成并验证。后端聚焦 `27 passed, 1 warning`，后端全量 `313 passed, 1 skipped, 1 warning`，前端全量 `125 passed`，生产构建成功。

**Goal:** 让派生路线、归并审核和规则审核写入统一校验工作流版本，并由 HTTP 路由拥有完整事务。

**Architecture:** 路由先调用 `acquire_workflow_revision()` 获得项目写锁，再调用只做查询和 ORM 写入的应用服务，最后一次提交或回滚。路线服务和归并工作台服务移除内部提交；前端从当前项目的 `workflow_revision` 生成所有第二步写请求的并发令牌。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy AsyncSession、Pydantic V2、SQLite、pytest、Vue 3、TypeScript、Vitest、Vite。

## Global Constraints

- 不引入通用 Unit of Work、数据库迁移或运行时依赖。
- 服务层只能查询、校验、add/update/delete、`flush()` 和必要的 `refresh()`，不能 `commit()` 或 `rollback()` 外层事务。
- 不改变规则包 JSON、KmAI V1 ZIP、内容哈希、成功响应结构或 `workflow_revision` 递增规则。
- 不扩展文档上传/删除和抽取后台任务的版本契约。
- 未经用户明确授权，不执行 `git add`、`git commit`、`git push`、rebase、reset 或分支操作。

---

## File Map

| 文件 | 责任 |
| --- | --- |
| `process-plan-agent-api/app/schemas/schemas.py` | 为两个路线写请求增加工作流版本字段 |
| `process-plan-agent-api/app/routers/extract.py` | 获取版本锁、统一提交/回滚，并为会触发缓存写入的读取路由提交 |
| `process-plan-agent-api/app/services/route_analysis.py` | 标准化路线版本和规则审核服务只 flush/refresh |
| `process-plan-agent-api/app/services/route_merge/workspace.py` | 归并快照和手工标准化路线服务只 flush |
| `process-plan-agent-api/tests/test_normalized_route_version_dedup.py` | 服务层调用者事务所有权和版本去重测试 |
| `process-plan-agent-api/tests/test_workflow_invalidation.py` | 三类 API 的旧版本冲突、原子性和成功契约测试 |
| `process-plan-agent-ui/src/api/extract.ts` | 请求类型携带 `expected_workflow_revision` |
| `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.ts` | 保存、批量审核和单项审核发送当前版本 |
| `process-plan-agent-ui/src/composables/useRouteMergeInteractionActions.ts` | 改名审核发送当前版本 |
| `process-plan-agent-ui/src/views/ExtractView.vue` | 持有项目版本并注入路线归并 composable |
| `process-plan-agent-ui/src/api/extract.spec.ts` | API 请求转发回归 |
| `docs/重构与优化跟踪.md` | 完成 R-003 状态、文件和实际验证结果 |

---

### Task 1: Remove service-owned commits

**Files:**
- Modify: `process-plan-agent-api/app/services/route_analysis.py:107-149,189-281,309-408`
- Modify: `process-plan-agent-api/app/services/route_merge/workspace.py:470-579`
- Test: `process-plan-agent-api/tests/test_normalized_route_version_dedup.py`

**Interfaces:**
- Consumes: existing `AsyncSession` arguments and route merge helpers.
- Produces: `save_normalized_route_version()` and `persist_normalized_superset_route()` leave writes pending in the caller session; `save_segment_rule_review_record()` returns a serialized review after `flush/refresh`.

- [x] **Step 1: Write the failing caller-owned transaction test**

Add a second session check to `test_identical_content_reuses_version_without_bump`:

```python
async with session_factory() as db:
    await save_normalized_route_version(
        project_id=1,
        db=db,
        source_signature="rollback-only",
        total_docs=1,
        normalized_route=_sample_route("回滚路线"),
    )
    await db.rollback()

async with session_factory() as db:
    rows = (
        await db.execute(
            select(NormalizedRouteVersion).where(
                NormalizedRouteVersion.project_id == 1,
                NormalizedRouteVersion.source_signature == "rollback-only",
            )
        )
    ).scalars().all()
    assert rows == []
```

The current internal `commit()` makes this test fail because the row survives the caller rollback.

- [x] **Step 2: Run the focused test and verify RED**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_normalized_route_version_dedup.py::test_identical_content_reuses_version_without_bump -q
```

Expected: FAIL at the rollback assertion because the service commits internally.

- [x] **Step 3: Remove service commits and preserve flush semantics**

In `route_analysis.py`:

1. Replace metadata-refresh `await db.commit()` with `await db.flush()` followed by the existing `refresh()`.
2. Replace new-version `await db.commit()` with `await db.flush()` followed by `refresh()`.
3. Replace rebuilt-route metadata `await db.commit()` with `await db.flush()` followed by `refresh()`.
4. In `save_segment_rule_review_record()`, replace both commit calls with `await db.flush()`; keep the refresh only after the review row exists.

In `route_merge/workspace.py`, remove the commits in `ensure_route_merge_snapshot()` and `persist_normalized_superset_route()`; keep their existing `save_route_merge_snapshot()` calls, which already flush.

- [x] **Step 4: Run focused tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_normalized_route_version_dedup.py tests/test_route_merge_document_invalidation.py -q
```

Expected: all focused tests pass; any test that intentionally needs persistence must explicitly commit its session.

---

### Task 2: Add route-level workflow locks and atomic commits

**Files:**
- Modify: `process-plan-agent-api/app/schemas/schemas.py:343-437`
- Modify: `process-plan-agent-api/app/routers/extract.py:348-422,529-578`
- Test: `process-plan-agent-api/tests/test_workflow_invalidation.py`

**Interfaces:**
- Consumes: `acquire_workflow_revision(db, project_id, expected_workflow_revision)`.
- Produces: `SaveNormalizedSupersetRouteRequest.expected_workflow_revision`, `MergeSuggestionReviewRequest.expected_workflow_revision`, and three route handlers that commit once or rollback on every failure.

- [x] **Step 1: Write failing stale-version API tests**

Append these tests to `test_workflow_invalidation.py`:

```python
def test_normalized_route_save_rejects_stale_revision(workflow_client):
    response = workflow_client.post("/api/extract/normalized-superset-route/save", json={
        "project_id": 9,
        "expected_workflow_revision": 6,
        "normalized_superset_route": [{
            "id": "seg-1",
            "normalized_step_name": "旧页面路线",
            "source_operation_ids": [900],
            "source_nodes": ["旧页面"],
        }],
    })
    assert response.status_code == 409
    assert "页面已过期" in str(response.json()["detail"])


def test_merge_review_rejects_stale_revision(workflow_client):
    response = workflow_client.post("/api/extract/merge-suggestions/review", json={
        "project_id": 9,
        "expected_workflow_revision": 6,
        "suggestion_id": "stale-page",
        "action": "accept",
    })
    assert response.status_code == 409
    assert "页面已过期" in str(response.json()["detail"])
```

The existing route handlers ignore these fields, so both tests currently fail with a non-409 result.

- [x] **Step 2: Run the API tests and verify RED**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_workflow_invalidation.py::test_normalized_route_save_rejects_stale_revision tests/test_workflow_invalidation.py::test_merge_review_rejects_stale_revision -q
```

Expected: FAIL because the request models do not define the field and the handlers do not acquire the version.

- [x] **Step 3: Add request fields and route transaction guards**

Add `expected_workflow_revision: int = 0` to both Pydantic request classes.

Update `save_normalized_superset_route()` to acquire the version before any helper, wrap all route/snapshot work in `try/except`, commit once after `save_normalized_route_version()`, refresh the returned version row, and rollback on every exception.

Update `save_segment_rule_review()` to wrap the service call in the same commit/rollback pattern. Keep `acquire_workflow_revision()` before the service call.

Update `review_merge_suggestion()` to acquire the version before loading or mutating the snapshot, then commit once after `save_route_merge_snapshot()`. Catch `HTTPException`, `ValueError`, `KeyError`, and unknown exceptions so every path rolls back while preserving the existing 400/404 messages.

Update `get_saved_normalized_route()` and route-merge GET handlers to commit after helpers that may build snapshots or migrate legacy review state; remove the service-level commits they previously relied on.

- [x] **Step 4: Run the focused API tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_workflow_invalidation.py tests/test_normalized_route_version_dedup.py -q
```

Expected: stale pages receive structured 409 responses, normal workflow reset and rule review tests remain green, and no route version or snapshot is created on a rejected write.

- [x] **Step 5: Add a rollback-after-service-failure regression**

Use `monkeypatch` in `test_workflow_invalidation.py` to replace `app.routers.extract.save_normalized_route_version` with a coroutine that raises `RuntimeError` after the route snapshot has been staged. Call the endpoint with revision 7, assert a 500, then query the fixture database through its session factory and assert the staged snapshot/route version is unchanged. This catches a route that commits before the final service completes.

---

### Task 3: Propagate workflow revisions through the frontend route-merge writes

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts:452-482,614-622`
- Modify: `process-plan-agent-ui/src/composables/useRouteMergeWorkspace.ts:22-51,225-361`
- Modify: `process-plan-agent-ui/src/composables/useRouteMergeInteractionActions.ts:175-209`
- Modify: `process-plan-agent-ui/src/views/ExtractView.vue:278-588,921-965`
- Test: `process-plan-agent-ui/src/api/extract.spec.ts`

**Interfaces:**
- Consumes: project list `workflow_revision` and existing route-merge composable options.
- Produces: every route-merge save, accept/reject, batch action and rename request includes `expected_workflow_revision: number`.

- [x] **Step 1: Write the failing API forwarding test**

Extend `extract.spec.ts` to import the two write functions and add:

```ts
it('forwards the workflow revision for route merge writes', async () => {
  vi.mocked(api.post).mockResolvedValue({ data: { ok: true } } as any)

  await saveNormalizedSupersetRoute({
    project_id: 7,
    expected_workflow_revision: 12,
    normalized_superset_route: [],
  })
  await reviewMergeSuggestion({
    project_id: 7,
    expected_workflow_revision: 12,
    suggestion_id: 'suggestion-1',
    action: 'rename',
    manual_label: '车外圆',
  })

  expect(api.post).toHaveBeenNthCalledWith(
    1,
    '/api/extract/normalized-superset-route/save',
    expect.objectContaining({ project_id: 7, expected_workflow_revision: 12 }),
  )
  expect(api.post).toHaveBeenNthCalledWith(
    2,
    '/api/extract/merge-suggestions/review',
    expect.objectContaining({ project_id: 7, expected_workflow_revision: 12 }),
  )
})
```

- [x] **Step 2: Run the Vitest test and verify RED**

Run from `process-plan-agent-ui/`:

```powershell
npm.cmd test -- src/api/extract.spec.ts
```

Expected: TypeScript/test failure because the current function input types do not accept or forward `expected_workflow_revision`.

- [x] **Step 3: Add the revision to API types and composable options**

1. Add the required field to `saveNormalizedSupersetRoute()` and `reviewMergeSuggestion()` input types.
2. Add `workflowRevision: Ref<number>` to `UseRouteMergeWorkspaceOptions` and the corresponding interaction-action options.
3. Include `expected_workflow_revision: options.workflowRevision.value` in all route-merge API calls, including batch actions (which reuse the single-action function), manual save and rename.
4. In `ExtractView.vue`, add a `workflowRevision` ref; set it from the selected `Project.workflow_revision` during initialization and update it from extraction task responses/reset signals. Pass it to both composables.

- [x] **Step 4: Run frontend tests and build**

```powershell
npm.cmd test -- src/api/extract.spec.ts
npm.cmd test
npm.cmd run build
```

Expected: forwarding test and existing frontend suite pass; production build completes without type errors.

---

### Task 4: Update tracking evidence and run full verification

**Files:**
- Modify: `docs/重构与优化跟踪.md` (R-003 section and summary table)

- [x] **Step 1: Run focused backend verification**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_workflow_invalidation.py tests/test_normalized_route_version_dedup.py tests/test_route_merge_document_invalidation.py -q
```

- [x] **Step 2: Run backend full suite**

```powershell
..\.runtime\python\python.exe -m pytest tests -q
```

- [x] **Step 3: Verify service ownership and whitespace**

```powershell
rg -n "await db\.(commit|rollback)\(" app/services/route_analysis.py app/services/route_merge/workspace.py
git diff --check
```

Expected: the service search returns no matches; `git diff --check` exits successfully.

- [x] **Step 4: Record actual results in the tracking document**

Mark R-003 as `已完成`, add the actual modified files, focused/full backend results, frontend test/build results, and any pre-existing warnings or unavailable Docker validation. Do not claim a command passed unless its output was observed.

- [x] **Step 5: Final review of scope and worktree**

```powershell
git status --short --branch
git diff --stat
git diff -- docs/重构与优化跟踪.md
```

Confirm that only intentional source, test, tracking, and already-existing untracked files are present; do not stage or commit changes.
