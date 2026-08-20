# R-006 Rule Package Status Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [x]`) syntax for tracking.

**Goal:** 新增服务端只读规则包状态接口，让第四步和第五步统一依赖服务端的发布、执行和阻塞原因事实来源。

**Architecture:** 将现有执行保护拆成可复用的纯读取检查与命令路径归档两部分；新增 `rule_packages/status.py` 聚合项目、路线、审核、最新历史包、当前活动包和 KmAI 摘要。前端第四步消费聚合状态替代本地编译哈希判断，第五步只在 `can_generate=true` 时加载完整规则包。

**Tech Stack:** Python 3.11+、FastAPI、SQLAlchemy AsyncSession、Pydantic V2、SQLite、pytest、Vue 3、TypeScript 5.9、Vitest、Vite

## Global Constraints

- 状态接口只表达服务端已持久化事实；浏览器本地草稿不进入服务端算法。
- 状态查询不得修改 ORM 对象，不得调用 `flush()`、`commit()`、`rollback()` 或归档服务。
- 保持路由拥有写事务，服务层不自行提交或回滚。
- 不修改 V2 JSON、KmAI V1 JSON、ZIP、内容哈希、数据库结构或现有写请求契约。
- `latest_package` 表示最新历史包；当前活动 `published` 包必须单独查询。
- 客户端行为依赖稳定 `code` 和 `blocks`，不得匹配中文 `message`。
- 只收敛 R-006 新增前端 DTO，不顺带处理 R-009 的全局类型生成。
- 保留工作区中的用户未跟踪文件和截图，不覆盖或删除。
- 未经用户明确授权，不执行 `git add`、`git commit`、`git push`、rebase、reset 或分支操作。

---

## File Map

| 文件 | 责任 |
| --- | --- |
| `process-plan-agent-api/app/services/rule_packages/execution.py` | 提供无副作用的已发布包执行检查，并保留命令路径归档行为 |
| `process-plan-agent-api/app/services/rule_packages/publishing.py` | 暴露发布允许项目状态的共享定义 |
| `process-plan-agent-api/app/services/rule_packages/contracts.py` | 定义状态响应、阻塞项和摘要 DTO |
| `process-plan-agent-api/app/services/rule_packages/status.py` | 聚合项目、路线、审核、历史包、活动包和 KmAI 状态 |
| `process-plan-agent-api/app/routers/rule_packages.py` | 暴露只读 `GET /status` |
| `process-plan-agent-api/tests/test_rule_package_status.py` | 状态服务、API、稳定原因及无副作用集成测试 |
| `process-plan-agent-api/tests/test_generate_v2_production.py` | 共享检查与生成归档回归 |
| `process-plan-agent-ui/src/api/rulePackages.ts` | 新增状态 DTO、阻塞码联合类型和 API 调用 |
| `process-plan-agent-ui/src/composables/useFinalizeWorkspace.ts` | 用服务端状态替代本地编译哈希判断 |
| `process-plan-agent-ui/src/composables/useFinalizeWorkspace.spec.ts` | 第四步状态映射、旧响应和无本地编译测试 |
| `process-plan-agent-ui/src/composables/useConditionReviewQueue.ts` | 持久化审核操作成功后通知工作区刷新服务端状态 |
| `process-plan-agent-ui/src/composables/useConditionReviewQueue.spec.ts` | 条件确认后的状态刷新回归测试 |
| `process-plan-agent-ui/src/views/FinalizeView.vue` | 接入第四步状态门禁和持久化后的轻量刷新 |
| `process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.ts` | 按 `can_generate` 有条件加载完整包 |
| `process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.spec.ts` | 第五步状态门禁测试 |
| `process-plan-agent-ui/src/views/GenerateView.vue` | 接入生成上下文加载器并展示服务端阻塞消息 |
| `docs/重构与优化跟踪.md` | 记录实际完成范围、证据与未验证项 |

---

### Task 1: Extract a read-only published-package inspection

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/execution.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/publishing.py`
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- Produces: `PUBLISHABLE_PROJECT_STATUSES = frozenset({"ROUTE_SET_READY", "GENERATED"})`.
- Produces: `PublishedRulePackageInspection(package, validation, sources_current, parse_error)`.
- Produces: `inspect_published_rule_package(row, *, project_id, db) -> PublishedRulePackageInspection`.
- Guarantee: inspection never changes `FinalizedRulePackage.status`; `load_published_rule_package_for_execution()` remains the only caller in this module that archives source-drifted packages.

- [x] **Step 1: Write the failing read-only inspection test**

Add the public inspection import and helper to `test_generate_v2_production.py`:

```python
from app.services.rule_packages.execution import inspect_published_rule_package
from app.services.rule_packages.loader import load_published_rule_package


async def _inspect_source_drift_without_write(session_factory, project_id: int):
    async with session_factory() as db:
        row = await load_published_rule_package(project_id, db)
        assert row is not None
        inspection = await inspect_published_rule_package(
            row,
            project_id=project_id,
            db=db,
        )
        status_after_inspection = row.status
        await db.rollback()
        return inspection, status_after_inspection


def test_published_package_inspection_reports_source_drift_without_archiving(
    generation_context,
):
    _, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_source_drifted_v2(session_factory))

    inspection, status = asyncio.run(
        _inspect_source_drift_without_write(session_factory, project_id)
    )

    assert inspection.package is not None
    assert inspection.validation is not None
    assert inspection.sources_current is False
    assert inspection.parse_error is None
    assert status == "published"
    assert asyncio.run(_rule_package_status(session_factory, project_id)) == "published"
```

This test catches the production regression where a status-oriented inspection calls `archive_published_rule_packages()` or mutates the row.

- [x] **Step 2: Run the new test and verify RED**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py::test_published_package_inspection_reports_source_drift_without_archiving -q
```

Expected: test collection fails because `inspect_published_rule_package` does not exist.

- [x] **Step 3: Add the inspection value object and pure function**

Implement in `execution.py`:

```python
@dataclass(frozen=True)
class PublishedRulePackageInspection:
    package: RulePackageV2 | None
    validation: RulePackageValidationReport | None
    sources_current: bool
    parse_error: str | None = None


async def inspect_published_rule_package(
    row: FinalizedRulePackage,
    *,
    project_id: int,
    db: AsyncSession,
) -> PublishedRulePackageInspection:
    if str(row.schema_version or "1.0") != "2.0":
        return PublishedRulePackageInspection(
            package=None,
            validation=None,
            sources_current=True,
        )
    try:
        package = v2_package_from_row(row)
    except Exception as exc:
        return PublishedRulePackageInspection(
            package=None,
            validation=None,
            sources_current=False,
            parse_error=str(exc),
        )
    validation = validate_rule_package(package)
    try:
        await require_confirmed_user_rule_sources(
            package,
            project_id=project_id,
            route_version_id=int(row.route_version_id or 0),
            db=db,
        )
    except ConfirmedRuleSourcesChanged:
        return PublishedRulePackageInspection(
            package=package,
            validation=validation,
            sources_current=False,
        )
    return PublishedRulePackageInspection(
        package=package,
        validation=validation,
        sources_current=True,
    )
```

Import `RulePackageV2`. Keep malformed-package handling confined to the result object so the status path can report `published_package_invalid` instead of raising `500`.

- [x] **Step 4: Reuse the pure inspection from the execution guard**

Replace the inline V2 source check inside `load_published_rule_package_for_execution()` with:

```python
    inspection = await inspect_published_rule_package(
        current,
        project_id=project_id,
        db=db,
    )
    if str(current.schema_version or "1.0") == "2.0" and not inspection.sources_current:
        if inspection.parse_error is not None:
            return current
        await archive_published_rule_packages(project_id, db)
        raise PublishedRulePackageSourcesChanged()
```

Malformed V2 behavior remains owned by `execute_published_v2_rule_package()`; only confirmed-source drift preserves the existing archive-and-409 behavior.

In `publishing.py`, define:

```python
PUBLISHABLE_PROJECT_STATUSES = frozenset({"ROUTE_SET_READY", "GENERATED"})
```

and replace the inline set membership check with this constant.

- [x] **Step 5: Run focused execution tests and verify GREEN**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py::test_published_package_inspection_reports_source_drift_without_archiving tests/test_generate_v2_production.py::test_generate_archives_source_drifted_v2_before_planning tests/test_generate_v2_production.py::test_generate_accepts_matching_published_rule_package_fingerprint -q
```

Expected: `3 passed`; the inspection leaves the row published, while the actual generate request archives it.

- [x] **Step 6: Review the task diff without staging or committing**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/services/rule_packages/publishing.py process-plan-agent-api/tests/test_generate_v2_production.py
git diff -- process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/services/rule_packages/publishing.py process-plan-agent-api/tests/test_generate_v2_production.py
```

---

### Task 2: Add the status contracts, aggregation service, and API

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py`
- Create: `process-plan-agent-api/app/services/rule_packages/status.py`
- Modify: `process-plan-agent-api/app/routers/rule_packages.py`
- Create: `process-plan-agent-api/tests/test_rule_package_status.py`

**Interfaces:**
- Produces: `RulePackageStatusBlocker`, `RulePackageStatusRoute`, `RulePackageStatusPackage`, `RulePackageReviewSummary`, `RulePackageKmaiSummary`, `RulePackageStatusResponse`.
- Produces: `build_rule_package_status(project_id: int, db: AsyncSession) -> RulePackageStatusResponse | None`; `None` means project not found.
- API: `GET /api/extract/finalized-rule-packages/status?project_id=12`.

- [x] **Step 1: Create the isolated API fixture and write the first failing state tests**

Create `tests/test_rule_package_status.py` with a real temporary SQLite database and literal assertions:

```python
import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema


@pytest.fixture
def status_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rule-package-status.db'}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with factory() as db:
            db.add(Project(id=12, name="状态测试", status="ROUTE_SET_READY", workflow_revision=7))
            await db.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield TestClient(app), factory
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_rule_package_status_returns_404_for_unknown_project(status_context):
    client, _ = status_context
    response = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 999},
    )
    assert response.status_code == 404


def test_rule_package_status_reports_missing_route_without_hiding_publish_state(
    status_context,
):
    client, _ = status_context
    response = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow_revision"] == 7
    assert body["route"] is None
    assert body["latest_package"] is None
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is False
    assert [item["code"] for item in body["blockers"]] == [
        "route_missing",
        "no_published_package",
    ]
```

- [x] **Step 2: Run both tests and verify RED**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_status.py::test_rule_package_status_returns_404_for_unknown_project tests/test_rule_package_status.py::test_rule_package_status_reports_missing_route_without_hiding_publish_state -q
```

Expected: `404` or collection failure because `/status` and its response models do not exist.

- [x] **Step 3: Add exact status DTOs**

Append to `contracts.py`:

```python
RulePackageCapability = Literal["publish", "generate"]


class RulePackageStatusBlocker(StrictModel):
    code: str
    message: str
    blocks: list[RulePackageCapability]
    count: int | None = None


class RulePackageStatusRoute(StrictModel):
    id: int
    version: int


class RulePackageStatusPackage(StrictModel):
    id: int
    version: int
    route_version_id: int | None = None
    schema_version: str
    content_hash: str
    status: str


class RulePackageReviewSummary(StrictModel):
    total: int = 0
    confirmed: int = 0
    pending: int = 0
    invalid_factor_bindings: int = 0


class RulePackageKmaiSummary(StrictModel):
    available: bool = False
    valid: bool = False
    error_count: int = 0
    warning_count: int = 0
    factor_catalog_version: str = ""


class RulePackageStatusResponse(StrictModel):
    project_id: int
    project_status: str
    workflow_revision: int
    route: RulePackageStatusRoute | None = None
    latest_package: RulePackageStatusPackage | None = None
    can_publish: bool
    can_generate: bool
    package_executable: bool
    blockers: list[RulePackageStatusBlocker] = Field(default_factory=list)
    review_summary: RulePackageReviewSummary = Field(default_factory=RulePackageReviewSummary)
    kmai_compatibility: RulePackageKmaiSummary = Field(default_factory=RulePackageKmaiSummary)
```

Import `Literal` if it is not already present.

- [x] **Step 4: Implement the minimal project/route/package aggregation**

Create `status.py` with these public and private boundaries:

```python
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, NormalizedRouteSegmentRuleReview, Project
from app.services.route_analysis import get_latest_normalized_route_version
from app.services.rule_packages.contracts import (
    RulePackageKmaiSummary,
    RulePackageReviewSummary,
    RulePackageStatusBlocker,
    RulePackageStatusPackage,
    RulePackageStatusResponse,
    RulePackageStatusRoute,
)
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.publishing import PUBLISHABLE_PROJECT_STATUSES


def _blocker(code: str, message: str, *blocks: str, count: int | None = None):
    return RulePackageStatusBlocker(
        code=code,
        message=message,
        blocks=list(blocks),
        count=count,
    )


async def _latest_package(project_id: int, db: AsyncSession):
    return (
        await db.execute(
            select(FinalizedRulePackage)
            .where(FinalizedRulePackage.project_id == project_id)
            .order_by(FinalizedRulePackage.version.desc(), FinalizedRulePackage.id.desc())
        )
    ).scalars().first()


def _package_summary(row: FinalizedRulePackage | None):
    if row is None:
        return None
    return RulePackageStatusPackage(
        id=row.id,
        version=row.version,
        route_version_id=row.route_version_id,
        schema_version=str(row.schema_version or "1.0"),
        content_hash=str(row.content_hash or ""),
        status=str(row.status or "archived"),
    )


async def build_rule_package_status(
    project_id: int,
    db: AsyncSession,
) -> RulePackageStatusResponse | None:
    project = await db.get(Project, project_id)
    if project is None:
        return None
    route = await get_latest_normalized_route_version(project_id, db)
    latest = await _latest_package(project_id, db)
    active = await load_published_rule_package(project_id, db)
    blockers: list[RulePackageStatusBlocker] = []
    if str(project.status or "") not in PUBLISHABLE_PROJECT_STATUSES:
        blockers.append(_blocker(
            "project_not_ready",
            "当前任务尚未完成路线提炼。",
            "publish",
            "generate",
        ))
    if route is None:
        blockers.append(_blocker(
            "route_missing",
            "当前任务没有可用的规范化路线。",
            "publish",
            "generate",
        ))
    if active is None:
        blockers.append(_blocker(
            "no_published_package",
            "当前任务没有已发布规则包。",
            "generate",
        ))
    blocked = {capability for item in blockers for capability in item.blocks}
    return RulePackageStatusResponse(
        project_id=project.id,
        project_status=str(project.status or ""),
        workflow_revision=int(project.workflow_revision or 0),
        route=(
            RulePackageStatusRoute(id=route.id, version=route.version)
            if route is not None else None
        ),
        latest_package=_package_summary(latest),
        can_publish="publish" not in blocked,
        can_generate=False,
        package_executable=False,
        blockers=blockers,
        review_summary=RulePackageReviewSummary(),
        kmai_compatibility=RulePackageKmaiSummary(),
    )
```

Add `GET /status` before the other package operations in `rule_packages.py`:

```python
@router.get("/status", response_model=RulePackageStatusResponse)
async def get_rule_package_status(
    project_id: int,
    db: AsyncSession = Depends(get_db),
):
    result = await build_rule_package_status(project_id, db)
    if result is None:
        raise HTTPException(404, "任务不存在")
    return result
```

- [x] **Step 5: Run the first tests and verify GREEN**

Run the Step 2 command again. Expected: `2 passed`.

- [x] **Step 6: Add the complete persisted-review and package matrix as failing tests**

Add seed helpers that insert a current route, rule review and package using real ORM rows. Add these literal assertions:

```python
@pytest.mark.parametrize(
    ("condition_status", "expected_code"),
    [
        ("draft", "pending_rule_reviews"),
        ("parsing", "pending_rule_reviews"),
        ("pending_confirmation", "pending_rule_reviews"),
        ("invalid", "pending_rule_reviews"),
    ],
)
def test_rule_package_status_reports_each_persisted_pending_review(
    status_context,
    condition_status,
    expected_code,
):
    client, factory = status_context
    asyncio.run(_seed_route_review(factory, condition_status=condition_status))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert body["review_summary"]["pending"] == 1
    assert expected_code in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is False


def test_rule_package_status_returns_archived_latest_package_as_history(status_context):
    client, factory = status_context
    asyncio.run(_seed_route_and_package(factory, package_status="archived"))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert body["latest_package"]["status"] == "archived"
    assert body["package_executable"] is False
    assert body["can_generate"] is False
    assert "no_published_package" in [item["code"] for item in body["blockers"]]


def test_rule_package_status_reports_valid_current_v2_and_kmai_summary(
    status_context,
    rule_package_v2_payload,
):
    client, factory = status_context
    asyncio.run(_seed_valid_published_v2(factory, rule_package_v2_payload))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert body["package_executable"] is True
    assert body["can_generate"] is True
    assert body["kmai_compatibility"]["available"] is True
    assert body["kmai_compatibility"]["valid"] is True
    assert body["blockers"] == []


def test_rule_package_status_reports_source_drift_without_archiving(
    status_context,
    rule_package_v2_payload,
):
    client, factory = status_context
    package_id = asyncio.run(_seed_source_drifted_v2(factory, rule_package_v2_payload))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert "published_rule_sources_changed" in [
        item["code"] for item in body["blockers"]
    ]
    assert body["package_executable"] is False
    assert asyncio.run(_stored_package_status(factory, package_id)) == "published"


def test_rule_package_status_reports_invalid_confirmed_factor_binding(status_context):
    client, factory = status_context
    asyncio.run(_seed_confirmed_review_with_unbound_factor(factory))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert body["review_summary"]["invalid_factor_bindings"] == 1
    assert "invalid_factor_bindings" in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is False


def test_rule_package_status_preserves_current_v1_generation_boundary(status_context):
    client, factory = status_context
    asyncio.run(_seed_current_v1_package(factory))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert body["latest_package"]["schema_version"] == "1.0"
    assert body["package_executable"] is True
    assert body["can_generate"] is True
    assert body["kmai_compatibility"]["available"] is False
```

Add dedicated tests with the same response shape for:

```python
@pytest.mark.parametrize(
    "scenario, expected_code",
    [
        ("route_changed", "published_package_route_changed"),
        ("malformed_v2", "published_package_invalid"),
        ("invalid_v2", "published_package_invalid"),
        ("kmai_invalid", "kmai_incompatible"),
    ],
)
def test_rule_package_status_uses_stable_generate_blockers(
    status_context,
    rule_package_v2_payload,
    scenario,
    expected_code,
):
    client, factory = status_context
    asyncio.run(_seed_status_scenario(factory, rule_package_v2_payload, scenario))
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()
    assert expected_code in [item["code"] for item in body["blockers"]]
    assert body["can_generate"] is False
```

The helpers must construct literal ORM fixtures; do not compute expected status with `build_rule_package_status()`.

- [x] **Step 7: Implement review, execution, and KmAI aggregation**

Extend `status.py` with:

```python
async def _review_summary(route_id: int, db: AsyncSession) -> RulePackageReviewSummary:
    rows = (
        await db.execute(
            select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == route_id,
            )
        )
    ).scalars().all()
    relevant = [
        row for row in rows
        if row.condition_source_text or row.condition_candidate_json or row.condition_confirmed_json
    ]
    confirmed = [
        row for row in relevant
        if row.condition_status == "confirmed" and row.condition_confirmed_json
    ]
    invalid_binding_count = 0
    for row in confirmed:
        candidate = loads_candidate(row.condition_confirmed_json)
        if candidate is None or candidate.kind != "condition" or candidate.when is None:
            continue
        definitions = {item.key: item for item in candidate.field_definitions}
        invalid_binding_count += len(validate_factor_bindings(candidate.when, definitions))
    return RulePackageReviewSummary(
        total=len(relevant),
        confirmed=len(confirmed),
        pending=len(relevant) - len(confirmed),
        invalid_factor_bindings=invalid_binding_count,
    )
```

For an active package:

1. Compare `active.route_version_id` with `route.id`.
2. Call `inspect_published_rule_package()`.
3. Map `parse_error` or invalid validation to `published_package_invalid`.
4. Map `sources_current=False` to `published_rule_sources_changed`.
5. For a valid V2 package call `build_kmai_compatibility_export()` and map invalid export to `kmai_incompatible`.
6. For V1, skip V2-only validation and treat the active row as executable when route and project checks pass.
7. Derive `blocked` from the final blocker list; set `package_executable` only from package checks, and `can_generate` from both package checks and project/route blockers.

Use an ordered `add_blocker()` helper backed by a `set[str]` so each code appears once in the table order from the design.

- [x] **Step 8: Run the complete status and execution regression tests**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_status.py tests/test_generate_v2_production.py tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_kmai_rule_package_export.py -q
```

Expected: all selected tests pass; only the repository's known TestClient/httpx deprecation warning may remain.

- [x] **Step 9: Review the backend status diff without staging or committing**

```powershell
git diff --check -- process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/status.py process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/tests/test_rule_package_status.py
git diff -- process-plan-agent-api/app/services/rule_packages/contracts.py process-plan-agent-api/app/services/rule_packages/status.py process-plan-agent-api/app/routers/rule_packages.py process-plan-agent-api/tests/test_rule_package_status.py
```

---

### Task 3: Replace fourth-step hash inference with server status

**Files:**
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeWorkspace.ts`
- Modify: `process-plan-agent-ui/src/composables/useFinalizeWorkspace.spec.ts`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Produces: `RulePackageStatusBlockerCode`, `RulePackageStatusResponse`, `getFinalizedRulePackageStatus(projectId)`.
- Changes: `useFinalizeWorkspace` exposes `rulePackageStatus` and derives `currentPublishedPackage`/`outdatedRulePackageVersion` from the server response.
- Removes: `compileRulePackage()` call from workspace loading.

- [x] **Step 1: Rewrite the workspace tests first and verify they fail**

In `useFinalizeWorkspace.spec.ts`, add the status mock and fixture:

```typescript
const mocks = vi.hoisted(() => ({
  compileRulePackage: vi.fn(),
  getConditionFieldRegistry: vi.fn(),
  getFinalizedRulePackageStatus: vi.fn(),
  getSavedNormalizedRoute: vi.fn(),
  getSupersetRoute: vi.fn(),
  listOperations: vi.fn(),
  listProjects: vi.fn(),
}))

function packageStatus(projectId: number, executable = true) {
  return {
    project_id: projectId,
    project_status: 'ROUTE_SET_READY',
    workflow_revision: 7,
    route: { id: projectId * 10, version: 1 },
    latest_package: {
      id: projectId * 100,
      version: 3,
      route_version_id: projectId * 10,
      schema_version: '2.0',
      content_hash: `hash-${projectId}`,
      status: executable ? 'published' : 'archived',
    },
    can_publish: true,
    can_generate: executable,
    package_executable: executable,
    blockers: executable ? [] : [{
      code: 'published_rule_sources_changed',
      message: '当前规则来源已变化。',
      blocks: ['generate'],
    }],
    review_summary: { total: 2, confirmed: 2, pending: 0, invalid_factor_bindings: 0 },
    kmai_compatibility: {
      available: executable,
      valid: executable,
      error_count: 0,
      warning_count: 0,
      factor_catalog_version: '2026.11',
    },
  }
}
```

Replace the current hash-difference test with:

```typescript
it('uses the server status without recompiling the current draft', async () => {
  mocks.getFinalizedRulePackageStatus.mockResolvedValueOnce(packageStatus(12, true))
  const workspace = createWorkspaceForProject('12')

  await workspace.loadWorkspace()

  expect(workspace.currentPublishedPackage.value?.version).toBe(3)
  expect(workspace.outdatedRulePackageVersion.value).toBeNull()
  expect(workspace.rulePackageStatus.value?.can_generate).toBe(true)
  expect(mocks.compileRulePackage).not.toHaveBeenCalled()
})

it('marks the latest historical package outdated from a stable server blocker', async () => {
  mocks.getFinalizedRulePackageStatus.mockResolvedValueOnce(packageStatus(12, false))
  const workspace = createWorkspaceForProject('12')

  await workspace.loadWorkspace()

  expect(workspace.currentPublishedPackage.value).toBeNull()
  expect(workspace.outdatedRulePackageVersion.value).toBe(3)
  expect(workspace.rulePackageStatus.value?.blockers[0].code)
    .toBe('published_rule_sources_changed')
})
```

Extend the existing delayed-project test so both route and status responses for project 12 resolve after project 22, then assert only project 22 state remains.

Run:

```powershell
npm.cmd test -- src/composables/useFinalizeWorkspace.spec.ts
```

Expected: failure because the status API and `rulePackageStatus` do not exist.

- [x] **Step 2: Add the closed frontend status contract and API call**

In `api/rulePackages.ts` add:

```typescript
export type RulePackageStatusBlockerCode =
  | 'project_not_ready'
  | 'route_missing'
  | 'pending_rule_reviews'
  | 'invalid_factor_bindings'
  | 'no_published_package'
  | 'published_package_route_changed'
  | 'published_rule_sources_changed'
  | 'published_package_invalid'
  | 'kmai_incompatible'

export type RulePackageStatusResponse = {
  project_id: number
  project_status: string
  workflow_revision: number
  route: { id: number; version: number } | null
  latest_package: {
    id: number
    version: number
    route_version_id: number | null
    schema_version: string
    content_hash: string
    status: string
  } | null
  can_publish: boolean
  can_generate: boolean
  package_executable: boolean
  blockers: Array<{
    code: RulePackageStatusBlockerCode
    message: string
    blocks: Array<'publish' | 'generate'>
    count?: number | null
  }>
  review_summary: {
    total: number
    confirmed: number
    pending: number
    invalid_factor_bindings: number
  }
  kmai_compatibility: {
    available: boolean
    valid: boolean
    error_count: number
    warning_count: number
    factor_catalog_version: string
  }
}

export async function getFinalizedRulePackageStatus(projectId: number) {
  const { data } = await api.get('/api/extract/finalized-rule-packages/status', {
    params: { project_id: projectId },
  })
  return data as RulePackageStatusResponse
}
```

Do not cache status independently: route/package writes already use workflow cache invalidation, and each workspace load needs one current atomic assessment.

- [x] **Step 3: Replace the local compile/hash branch in `useFinalizeWorkspace`**

Remove `CompileRulePackageRequest`, `compileRulePackage`, `FinalizeWorkspaceCompileContext`, `allCurrentRulesConfirmed` and `buildCompileRequest` from workspace options. Add:

```typescript
const rulePackageStatus = ref<RulePackageStatusResponse | null>(null)
```

Load `getFinalizedRulePackageStatus(projectId.value)` in the existing `Promise.all`. After the request guard check:

```typescript
rulePackageStatus.value = statusResult
currentPublishedPackage.value = statusResult.package_executable
  && statusResult.latest_package?.status === 'published'
  ? statusResult.latest_package
  : null
outdatedRulePackageVersion.value = statusResult.latest_package
  && !statusResult.package_executable
  ? statusResult.latest_package.version
  : null
```

Clear `rulePackageStatus` in `clearWorkspaceState()` and error handling, return it from the composable, and leave `markPublishedRulePackageOutdated()` as immediate local feedback until the next refresh.

Update `FinalizeView.vue` to remove the obsolete workspace compile callback and to consume `rulePackageStatus` for persisted publish/generate summaries. Keep `allCurrentRulesConfirmed` only for unsaved/local card interaction and final button enablement.

- [x] **Step 4: Run the focused fourth-step tests and verify GREEN**

```powershell
npm.cmd test -- src/composables/useFinalizeWorkspace.spec.ts src/utils/finalizeRulePackageActionState.spec.ts src/composables/useFinalizeRulePackagePublish.spec.ts src/composables/useFinalizedRulePackageDownload.spec.ts
```

Expected: all selected files pass; workspace loading makes no compile call.

- [x] **Step 5: Review the fourth-step diff without staging or committing**

```powershell
git diff --check -- process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/composables/useFinalizeWorkspace.ts process-plan-agent-ui/src/composables/useFinalizeWorkspace.spec.ts process-plan-agent-ui/src/views/FinalizeView.vue
git diff -- process-plan-agent-ui/src/api/rulePackages.ts process-plan-agent-ui/src/composables/useFinalizeWorkspace.ts process-plan-agent-ui/src/composables/useFinalizeWorkspace.spec.ts process-plan-agent-ui/src/views/FinalizeView.vue
```

---

### Task 4: Gate fifth-step context loading with `can_generate`

**Files:**
- Create: `process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.ts`
- Create: `process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.spec.ts`
- Modify: `process-plan-agent-ui/src/views/GenerateView.vue`

**Interfaces:**
- Produces: `loadGenerateRulePackageContext(projectId, forceRefresh?) -> { status, rulePackage, blockerMessage }`.
- Guarantee: the complete latest-package endpoint is not called when `status.can_generate` is false.

- [x] **Step 1: Write failing loader tests**

Create `loadGenerateRulePackageContext.spec.ts`:

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  getFinalizedRulePackageStatus: vi.fn(),
  getOptionalLatestFinalizedRulePackage: vi.fn(),
}))

vi.mock('@/api/rulePackages', () => ({
  getFinalizedRulePackageStatus: mocks.getFinalizedRulePackageStatus,
}))
vi.mock('@/api', () => ({
  getOptionalLatestFinalizedRulePackage: mocks.getOptionalLatestFinalizedRulePackage,
}))

import { loadGenerateRulePackageContext } from './loadGenerateRulePackageContext'

describe('loadGenerateRulePackageContext', () => {
  beforeEach(() => Object.values(mocks).forEach(mock => mock.mockReset()))

  it('does not load package content when the server blocks generation', async () => {
    mocks.getFinalizedRulePackageStatus.mockResolvedValue({
      can_generate: false,
      blockers: [{
        code: 'published_rule_sources_changed',
        message: '当前规则来源已变化。',
        blocks: ['generate'],
      }],
    })

    const result = await loadGenerateRulePackageContext(12, true)

    expect(result.rulePackage).toBeNull()
    expect(result.blockerMessage).toBe('当前规则来源已变化。')
    expect(mocks.getOptionalLatestFinalizedRulePackage).not.toHaveBeenCalled()
  })

  it('loads the complete current package only after the server allows generation', async () => {
    mocks.getFinalizedRulePackageStatus.mockResolvedValue({
      can_generate: true,
      blockers: [],
    })
    mocks.getOptionalLatestFinalizedRulePackage.mockResolvedValue({
      id: 56,
      input_schema: { fields: [] },
    })

    const result = await loadGenerateRulePackageContext(12, false)

    expect(result.rulePackage?.id).toBe(56)
    expect(result.blockerMessage).toBe('')
    expect(mocks.getOptionalLatestFinalizedRulePackage).toHaveBeenCalledWith(12, false)
  })
})
```

Run:

```powershell
npm.cmd test -- src/composables/loadGenerateRulePackageContext.spec.ts
```

Expected: collection fails because the loader module does not exist.

- [x] **Step 2: Implement the minimal loader**

Create `loadGenerateRulePackageContext.ts`:

```typescript
import { getOptionalLatestFinalizedRulePackage } from '@/api'
import {
  getFinalizedRulePackageStatus,
  type RulePackageStatusResponse,
} from '@/api/rulePackages'

export async function loadGenerateRulePackageContext(
  projectId: number,
  forceRefresh = false,
) {
  const status = await getFinalizedRulePackageStatus(projectId)
  if (!status.can_generate) {
    const blocker = status.blockers.find(item => item.blocks.includes('generate'))
    return {
      status,
      rulePackage: null,
      blockerMessage: blocker?.message || '当前规则包不可用于路线生成。',
    }
  }
  const rulePackage = await getOptionalLatestFinalizedRulePackage(projectId, forceRefresh)
  return {
    status: status as RulePackageStatusResponse,
    rulePackage,
    blockerMessage: rulePackage ? '' : '当前任务没有可用的已发布规则包。',
  }
}
```

- [x] **Step 3: Use the loader from `GenerateView.vue`**

Replace the direct latest-package call with:

```typescript
const context = await loadGenerateRulePackageContext(targetProjectId, forceRefresh)
workflowRevision.value = context.status.workflow_revision
const latestPackage = context.rulePackage
```

After the existing request guard checks, keep the current package/schema setup when `latestPackage?.input_schema` exists. Otherwise call `clearRulePackageContext()` and set:

```typescript
error.value = context.blockerMessage
```

Do not remove request guards, package fingerprints, workflow revisions or execution-time `published_rule_package_changed` handling.

- [x] **Step 4: Run focused generate tests and verify GREEN**

```powershell
npm.cmd test -- src/composables/loadGenerateRulePackageContext.spec.ts src/utils/generateRulePackageContext.spec.ts src/composables/useGenerateInputFields.spec.ts src/components/generate/GenerateInputPanel.spec.ts
```

Expected: all selected tests pass, and the blocked test proves the full package endpoint is not called.

- [x] **Step 5: Review the fifth-step diff without staging or committing**

```powershell
git diff --check -- process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.ts process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.spec.ts process-plan-agent-ui/src/views/GenerateView.vue
git diff -- process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.ts process-plan-agent-ui/src/composables/loadGenerateRulePackageContext.spec.ts process-plan-agent-ui/src/views/GenerateView.vue
```

---

### Task 5: Complete documentation and full verification

**Files:**
- Modify: `docs/superpowers/specs/2026-08-08-r006-rule-package-status-design.md`
- Modify: `docs/superpowers/plans/2026-08-08-r006-rule-package-status.md`
- Modify: `docs/重构与优化跟踪.md`

**Interfaces:**
- Produces: a completed R-006 record whose claims match fresh command output.
- Does not produce: commits, staging, Docker claims or Python 3.11 claims without real evidence.

- [x] **Step 1: Run backend focused tests**

```powershell
Set-Location process-plan-agent-api
..\.runtime\python\python.exe -m pytest tests/test_rule_package_status.py tests/test_generate_v2_production.py tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_kmai_rule_package_export.py -q
```

Record the exact passed/skipped/warning counts.

- [x] **Step 2: Run backend full tests**

```powershell
..\.runtime\python\python.exe -m pytest -q
```

Record exact counts and distinguish new failures from pre-existing warnings.

- [x] **Step 3: Run frontend focused and full tests**

```powershell
Set-Location ..\process-plan-agent-ui
npm.cmd test -- src/composables/useFinalizeWorkspace.spec.ts src/composables/loadGenerateRulePackageContext.spec.ts src/utils/finalizeRulePackageActionState.spec.ts src/utils/generateRulePackageContext.spec.ts
npm.cmd test
```

Record the test-file and test counts from both commands.

- [x] **Step 4: Run the production type check and build**

```powershell
npm.cmd run build
```

Success requires `vue-tsc -b` and Vite to exit `0`; record transformed module count and output summary.

- [x] **Step 5: Perform explicit R-006 completion searches**

From the repository root:

```powershell
rg -n "compileRulePackage|content_hash" process-plan-agent-ui/src/composables/useFinalizeWorkspace.ts
rg -n "getFinalizedRulePackageStatus|can_generate|can_publish|package_executable" process-plan-agent-api process-plan-agent-ui/src
rg -n "published_rule_sources_changed|published_package_invalid|kmai_incompatible" process-plan-agent-api/tests process-plan-agent-ui/src
```

Expected: the first command has no workspace-load compile/hash inference; the latter commands show the shared service, API, consumers and regression tests.

- [x] **Step 6: Update design, plan, and tracking document with actual evidence**

Only after Steps 1-5 succeed:

1. Change the R-006 design status to `已实施，验证通过`.
2. Mark this plan's task checkboxes complete for steps actually performed.
3. Change R-006 in `docs/重构与优化跟踪.md` to `已验证完成` only if all completion assertions pass.
4. Add the actual modified files and exact verification counts.
5. Record that Docker was not exercised if no Docker build/health check was run.
6. Record that the status interface covers persisted server state and local drafts remain a UI dirty-state guard.

- [x] **Step 7: Run final diff and workspace checks**

```powershell
git diff --check
git status --short
git diff --stat
```

Confirm that only R-006 source/tests/docs plus the pre-existing untracked design files and screenshots are present. Do not stage or commit.

## Verification Record

- 后端规则包聚焦：`80 passed, 1 warning`。
- 后端全量：`340 passed, 1 skipped, 1 warning`。
- 前端 R-006 聚焦：`5` 个测试文件、`20 passed`；前端全量：`29` 个测试文件、`141 passed`。
- `npm.cmd run build`：`vue-tsc -b` 和 Vite 均退出 `0`，Vite 转换 `1830` 个模块。
- 后端测试使用本机 Python `3.11.15`；未执行 Docker 构建/健康检查、离线交付包验证或静态检查命令。
