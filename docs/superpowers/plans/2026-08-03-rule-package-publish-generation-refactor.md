# 规则包发布与生成链路重构实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 阻止新前端静默切换到更新的发布规则包，保留最新规则包读取的真实错误，并把发布与 V2 执行领域逻辑移出 HTTP 路由。

**Architecture:** 在现有项目工作流写锁内校验可选规则包指纹，然后再选择 V1 或 V2 执行路径。新增聚焦的发布服务和执行服务，路由只保留锁、HTTP 映射、事务及响应编排；前端共享“仅 404 表示不存在”的读取函数，并提交加载输入模式时保存的规则包指纹。

**Tech Stack:** Python 3.11+、FastAPI、Pydantic 2、SQLAlchemy async、SQLite、pytest；Vue 3、TypeScript 5.9、Axios、Vitest、Vite。

## Global Constraints

- 保持现有 API 路径、成功响应字段、按钮文案、下载规则和生成结果不变。
- `expected_rule_package_id`、`expected_rule_package_version`、`expected_rule_package_hash` 必须保持可选，以兼容旧客户端。
- 新前端提交从输入模式上下文取得的全部非空指纹字段。
- 任一已提交指纹不一致时，在规划和持久化前返回 HTTP 409，且 `detail.code == "published_rule_package_changed"`。
- 只有最新规则包接口的 404 转换为 `null`；网络、认证、冲突、验证和 5xx 错误继续抛出。
- 不修改 V1 生成算法、数据库结构、规则包 ZIP 或 KmAI V1 协议。
- 不增加 Python 或 npm 依赖。
- 不修改或暂存无关的未跟踪文件 `docs/superpowers/plans/2026-08-03-generate-input-boolean-group.md`。
- 未经用户明确授权不创建 Git commit；每个任务结束时仅检查差异和测试证据。
- 后端命令从 `process-plan-agent-api` 执行，前端命令从 `process-plan-agent-ui` 执行，Git 命令从仓库根目录执行。

---

## File Map

### Backend

- Create `process-plan-agent-api/app/services/rule_packages/execution.py`：加载并校验当前发布包指纹，验证并执行持久化 V2 规则包。
- Create `process-plan-agent-api/app/services/rule_packages/publishing.py`：准备、分配版本、持久化并发布规则包，不提交外层事务。
- Modify `process-plan-agent-api/app/services/rule_packages/confirmation_validation.py`：以领域异常代替 FastAPI 异常。
- Modify `process-plan-agent-api/app/schemas/schemas.py`：向 `GenerateRequest` 添加可选规则包指纹。
- Modify `process-plan-agent-api/app/routers/generate.py`：委托发布包加载和 V2 执行，保留 V1、持久化与响应组装。
- Modify `process-plan-agent-api/app/routers/extract.py`：委托发布服务，保留工作流锁、HTTP 映射、事务和序列化。
- Modify `process-plan-agent-api/tests/test_generate_v2_production.py`：覆盖匹配、过期和省略指纹。
- Create `process-plan-agent-api/tests/test_rule_package_execution.py`：聚焦测试 V2 执行服务。
- Modify `process-plan-agent-api/tests/test_rule_package_api.py`：覆盖发布服务事务和现有 API 语义。
- Modify `process-plan-agent-api/tests/test_workflow_invalidation.py`：验证确认来源领域异常仍映射为现有 409。

### Frontend

- Modify `process-plan-agent-ui/src/api/extract.ts`：新增 `getOptionalLatestFinalizedRulePackage()`。
- Create `process-plan-agent-ui/src/api/extract.spec.ts`：证明只有 404 转换为 `null`。
- Modify `process-plan-agent-ui/src/api/generate.ts`：声明三个可选指纹字段。
- Create `process-plan-agent-ui/src/utils/generateRulePackageContext.ts`：纯指纹、请求负载和冲突分类工具。
- Create `process-plan-agent-ui/src/utils/generateRulePackageContext.spec.ts`：测试指纹及专用冲突判断。
- Modify `process-plan-agent-ui/src/views/GenerateView.vue`：保存并提交指纹，冲突时清理旧结果并刷新上下文。
- Modify `process-plan-agent-ui/src/views/FinalizeView.vue`：使用可选最新包读取且不吞掉其他错误。

---

### Task 1: 将生成请求绑定到已加载规则包

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/execution.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py:490`
- Modify: `process-plan-agent-api/app/routers/generate.py:156`、`process-plan-agent-api/app/routers/generate.py:978`
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- Consumes: `load_published_rule_package(project_id, db)` 和现有项目工作流锁。
- Produces: `RulePackageExpectation`、`PublishedRulePackageChanged`、`load_published_rule_package_for_execution()`。
- `PublishedRulePackageChanged.detail` 是前端识别冲突所需的稳定响应对象。

- [ ] **Step 1: 编写匹配和过期指纹的失败测试**

在 `_generation_state()` 之后增加：

```python
async def _published_fingerprint(session_factory, project_id: int) -> dict[str, object]:
    async with session_factory() as db:
        row = (
            await db.execute(
                select(FinalizedRulePackage).where(
                    FinalizedRulePackage.project_id == project_id,
                    FinalizedRulePackage.status == "published",
                )
            )
        ).scalar_one()
        return {
            "expected_rule_package_id": row.id,
            "expected_rule_package_version": row.version,
            "expected_rule_package_hash": row.content_hash,
        }
```

增加端点测试：

```python
def test_generate_accepts_matching_published_package_fingerprint(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "matching-fingerprint"))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))

    response = client.post("/api/generate/", json={
        "project_id": project_id,
        **fingerprint,
        "factor_values": {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    })

    assert response.status_code == 200, response.text
    assert response.json()["rule_package_id"] == fingerprint["expected_rule_package_id"]


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("expected_rule_package_id", 999999),
        ("expected_rule_package_version", 999999),
        ("expected_rule_package_hash", "stale-content-hash"),
    ],
)
def test_generate_rejects_stale_published_package_fingerprint_without_side_effects(
    generation_context,
    field,
    stale_value,
):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, f"stale-{field}"))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))
    fingerprint[field] = stale_value

    response = client.post("/api/generate/", json={
        "project_id": project_id,
        **fingerprint,
        "factor_values": {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    })

    assert response.status_code == 409
    detail = response.json()["detail"]
    assert detail["code"] == "published_rule_package_changed"
    assert detail["current_rule_package"]["version"] == 1
    _assert_generation_not_persisted(session_factory, project_id)
```

保留现有 `test_generate_uses_published_v2_plan_route` 不变，它证明省略指纹的旧客户端仍然可用。

- [ ] **Step 2: 运行测试并确认过期用例先失败**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -k "fingerprint or uses_published_v2" -v
```

Expected: 匹配用例可能因 Pydantic 忽略未知字段而通过；三个过期用例以 200 而不是 409 失败。

- [ ] **Step 3: 向 GenerateRequest 添加可选字段**

```python
class GenerateRequest(BaseModel):
    project_id: Optional[int] = None
    expected_workflow_revision: int = 0
    expected_rule_package_id: Optional[int] = None
    expected_rule_package_version: Optional[int] = None
    expected_rule_package_hash: Optional[str] = None
    factor_values: dict[str, Any] = Field(default_factory=dict)
    family: str = ""
    material: str = ""
    hardness: str = "LOW"
    has_hole: bool = False
    has_spline: bool = False
    roughness: float = 3.2
```

- [ ] **Step 4: 实现发布包期望边界**

创建 `execution.py`：

```python
"""Published rule-package loading and deterministic V2 execution boundary."""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage
from app.services.rule_packages.loader import load_published_rule_package


@dataclass(frozen=True)
class RulePackageExpectation:
    package_id: int | None = None
    version: int | None = None
    content_hash: str | None = None

    @property
    def supplied(self) -> bool:
        return any(
            value is not None
            for value in (self.package_id, self.version, self.content_hash)
        )


class PublishedRulePackageChanged(ValueError):
    code = "published_rule_package_changed"

    def __init__(self, current: FinalizedRulePackage):
        super().__init__("规则包已更新，请刷新后重新生成。")
        self.detail = {
            "code": self.code,
            "message": str(self),
            "current_rule_package": {
                "id": current.id,
                "version": current.version,
                "content_hash": current.content_hash,
            },
        }


def _matches_expectation(
    row: FinalizedRulePackage,
    expectation: RulePackageExpectation,
) -> bool:
    return all((
        expectation.package_id is None or row.id == expectation.package_id,
        expectation.version is None or row.version == expectation.version,
        expectation.content_hash is None or row.content_hash == expectation.content_hash,
    ))


async def load_published_rule_package_for_execution(
    project_id: int,
    db: AsyncSession,
    *,
    expectation: RulePackageExpectation,
) -> FinalizedRulePackage | None:
    row = await load_published_rule_package(project_id, db)
    if row is not None and expectation.supplied and not _matches_expectation(row, expectation):
        raise PublishedRulePackageChanged(row)
    return row
```

- [ ] **Step 5: 在 V1/V2 分支前集成指纹检查**

在 `generate_route()` 中替换 `_latest_finalized_rule_package()` 调用：

```python
expectation = RulePackageExpectation(
    package_id=body.expected_rule_package_id,
    version=body.expected_rule_package_version,
    content_hash=body.expected_rule_package_hash,
)
try:
    finalized_package = await load_published_rule_package_for_execution(
        body.project_id,
        db,
        expectation=expectation,
    )
except PublishedRulePackageChanged as exc:
    raise HTTPException(status_code=409, detail=exc.detail) from exc
```

确认无其他调用后删除路由内 `_latest_finalized_rule_package()` 和不再使用的直接 loader import：

```powershell
rg -n "_latest_finalized_rule_package|load_published_rule_package" app/routers/generate.py
```

- [ ] **Step 6: 运行完整生成测试并检查差异**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -v
```

Expected: 全部通过，过期指纹无持久化副作用，省略指纹仍成功。

从仓库根目录运行：

```powershell
git diff --check
git status --short
```

---

### Task 2: 提取 V2 校验与确定性规划

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/execution.py`
- Modify: `process-plan-agent-api/app/routers/generate.py:1025`
- Create: `process-plan-agent-api/tests/test_rule_package_execution.py`

**Interfaces:**
- Consumes: 持久化 `FinalizedRulePackage` 和仅包含本次显式提交字段的 V2 inputs。
- Produces: `V2RulePackageExecution(plan: RoutePlan)` 和 `execute_published_v2_rule_package()`。
- Raises: `PublishedRulePackageInvalid`、`PublishedRulePackageInputInvalid`，并保留现有 `RulePackageLifecycleError` 与 `RoutePlanningError`。

- [ ] **Step 1: 编写执行服务失败测试**

创建测试文件，使用共享 `rule_package_v2_payload` fixture：

```python
import json

import pytest

from app.models.models import FinalizedRulePackage
from app.services.rule_packages.execution import (
    PublishedRulePackageInputInvalid,
    execute_published_v2_rule_package,
)


def _published_v2_row(payload: dict) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        id=41,
        project_id=payload["manifest"]["project_id"],
        route_version_id=payload["manifest"].get("route_version_id"),
        version=3,
        package_name=payload["manifest"]["package_name"],
        schema_version="2.0",
        status="published",
        manifest_json=json.dumps(payload["manifest"], ensure_ascii=False),
        input_schema_json=json.dumps(payload["input_schema"], ensure_ascii=False),
        route_catalog_json=json.dumps(payload["route_catalog"], ensure_ascii=False),
        route_rules_json=json.dumps(payload["route_rules"], ensure_ascii=False),
        test_cases_json=json.dumps(payload["test_cases"], ensure_ascii=False),
        rule_report_md="# test",
        validation_report_json="{}",
        content_hash="a" * 64,
        created_by="tester",
    )


def test_execute_published_v2_rule_package_returns_deterministic_plan(
    rule_package_v2_payload,
):
    result = execute_published_v2_rule_package(
        _published_v2_row(rule_package_v2_payload),
        {
            "material": {"grade": "9Cr18"},
            "cad": {"features": ["槽类特征"]},
            "target_hardness_hrc": 58,
        },
    )

    assert result.plan.selected_process_ids == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
    assert "material.9cr18.quench" in [
        trace.rule_id for trace in result.plan.traces if trace.matched
    ]


def test_execute_published_v2_rule_package_reports_input_issues(
    rule_package_v2_payload,
):
    with pytest.raises(PublishedRulePackageInputInvalid) as caught:
        execute_published_v2_rule_package(
            _published_v2_row(rule_package_v2_payload),
            {},
        )

    assert any(issue.field == "material.grade" for issue in caught.value.issues)
```

- [ ] **Step 2: 运行测试并确认导入失败**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_execution.py -v
```

Expected: 因执行结果和异常类型尚不存在而失败。

- [ ] **Step 3: 实现类型化 V2 执行结果**

向 `execution.py` 增加：

```python
from typing import Any

from app.services.rule_packages.contracts import RoutePlan, RulePackageValidationReport
from app.services.rule_packages.input_validation import InputValidationIssue, validate_inputs
from app.services.rule_packages.lifecycle import v2_package_from_row
from app.services.rule_packages.planner import plan_route
from app.services.rule_packages.validator import validate_rule_package


@dataclass(frozen=True)
class V2RulePackageExecution:
    plan: RoutePlan


class PublishedRulePackageInvalid(ValueError):
    def __init__(self, validation: RulePackageValidationReport):
        super().__init__("已发布规则包校验失败")
        self.validation = validation


class PublishedRulePackageInputInvalid(ValueError):
    def __init__(self, issues: list[InputValidationIssue]):
        super().__init__("规则包输入校验失败")
        self.issues = issues


def execute_published_v2_rule_package(
    row: FinalizedRulePackage,
    inputs: dict[str, Any],
) -> V2RulePackageExecution:
    package = v2_package_from_row(row)
    validation = validate_rule_package(package)
    if not validation.valid:
        raise PublishedRulePackageInvalid(validation)
    input_issues = validate_inputs(package.input_schema, inputs)
    if input_issues:
        raise PublishedRulePackageInputInvalid(input_issues)
    return V2RulePackageExecution(plan=plan_route(package, inputs))
```

- [ ] **Step 4: 用执行服务替换路由内联 V2 逻辑**

V2 分支保留显式输入归一化，然后调用服务：

```python
inputs = _normalize_input_values(body, explicit_legacy_fields_only=True)
execution = execute_published_v2_rule_package(finalized_package, inputs)
plan = execution.plan
steps = [
    RouteStep(
        process_id=step.process_id,
        sequence=step.sequence,
        name=step.name,
        op_type=step.op_type,
        reason=step.reason,
        process_steps=list(step.process_steps or []),
        template_group_aliases=[
            alias.model_dump() for alias in step.template_group_aliases
        ],
    )
    for step in plan.steps
]
matched_rule_ids = [trace.rule_id for trace in plan.traces if trace.matched]
selected_process_ids = list(plan.selected_process_ids)
```

在现有 `try` 中按当前响应形状映射服务异常：

```python
except PublishedRulePackageInvalid as exc:
    raise HTTPException(
        status_code=422,
        detail={
            "message": f"已发布规则包 V{finalized_package.version} 校验未通过，无法生成",
            "validation": exc.validation.model_dump(mode="json"),
        },
    ) from exc
except PublishedRulePackageInputInvalid as exc:
    raise HTTPException(
        status_code=422,
        detail=input_validation_error_detail(exc.issues),
    ) from exc
```

保留 `RulePackageLifecycleError`、`RoutePlanningError` 和 `ValueError` 的现有映射。仅在 `rg` 确认无其他用途后删除路由对 `v2_package_from_row`、`validate_rule_package`、`validate_inputs`、`plan_route` 的直接 import。

- [ ] **Step 5: 运行服务与生产生成套件**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_execution.py tests/test_generate_v2_production.py -v
```

Expected: 全部通过，端点响应字段和工序顺序不变。

---

### Task 3: 提取规则包发布事务边界

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/publishing.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/confirmation_validation.py`
- Modify: `process-plan-agent-api/app/routers/extract.py:425`
- Modify: `process-plan-agent-api/tests/test_rule_package_api.py`
- Modify: `process-plan-agent-api/tests/test_workflow_invalidation.py`

**Interfaces:**
- Consumes: `FinalizedRulePackageSaveRequest`、已锁定的 `Project` 和 `AsyncSession`。
- Produces: `FinalizedRulePackagePublication(row, kmai_compatibility)` 与 `create_published_rule_package()`。
- Raises: `RulePackagePublicationRequestInvalid`、`RulePackagePublicationConflict`、`RulePackagePublicationUnprocessable`、`RulePackageVersionConflict`。
- 发布服务和确认来源服务均不依赖 FastAPI，且不提交或回滚外层事务。

- [ ] **Step 1: 增加发布事务和版本序列特征测试**

在 `test_rule_package_api.py` 增加：

```python
def test_failed_republication_keeps_current_package_and_version_sequence(
    rule_package_v2_payload,
):
    first = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert first.status_code == 200, first.text
    assert first.json()["version"] == 1

    invalid = _v2_save_payload(deepcopy(rule_package_v2_payload))
    invalid["route_rules"]["rules"][0]["when"]["op"] = "unsupported"
    rejected = client.post("/api/extract/finalized-rule-packages", json=invalid)
    assert rejected.status_code == 422

    latest_after_failure = client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    ).json()
    assert latest_after_failure["id"] == first.json()["id"]

    second = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert second.status_code == 200, second.text
    assert second.json()["version"] == 2
```

补充直接服务测试，证明调用方回滚后不会留下记录：

```python
def test_publication_service_does_not_commit(
    isolated_rule_package_db,
    rule_package_v2_payload,
):
    from app.schemas.schemas import FinalizedRulePackageSaveRequest
    from app.services.rule_packages.publishing import create_published_rule_package

    async def exercise():
        async with isolated_rule_package_db() as db:
            project = await db.get(Project, 12)
            body = FinalizedRulePackageSaveRequest(
                **_v2_save_payload(rule_package_v2_payload)
            )
            publication = await create_published_rule_package(body, project, db)
            assert publication.row.status == "published"
            await db.rollback()
        async with isolated_rule_package_db() as db:
            return (
                await db.execute(select(FinalizedRulePackage))
            ).scalars().all()

    assert asyncio.run(exercise()) == []
```

为此测试向文件 import 添加 `select`。

- [ ] **Step 2: 运行发布测试并确认服务导入失败**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_api.py -k "failed_republication or publication_service" -v
```

Expected: 因 `publishing.py` 尚不存在而在收集或执行时失败。

- [ ] **Step 3: 将确认来源错误改为领域异常**

在 `confirmation_validation.py` 删除 FastAPI import，并增加：

```python
class ConfirmedRuleSourcesChanged(ValueError):
    def __init__(self, rule_ids: list[str]):
        super().__init__(
            "规则包中的用户规则与数据库中的已确认规则不一致，请刷新第四步后重新审核。"
        )
        self.rule_ids = rule_ids

    @property
    def detail(self) -> dict[str, object]:
        return {
            "message": str(self),
            "rule_ids": self.rule_ids,
        }
```

把函数结尾替换为：

```python
if failures:
    raise ConfirmedRuleSourcesChanged(failures)
```

发布服务会捕获该异常并转换为 `RulePackagePublicationConflict`；现有 API 测试 `test_publish_rejects_forged_confirmed_rule` 必须继续得到 409 和相同消息。

- [ ] **Step 4: 创建发布服务的类型和准备结果**

创建 `publishing.py`，先定义不含 HTTP 状态码的领域异常：

```python
"""Finalized rule-package validation and publication boundary."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.schemas.schemas import FinalizedRulePackageSaveRequest
from app.services.finalized_rule_package_helpers import (
    json_dumps,
    json_dumps_list,
)
from app.services.rule_packages.confirmation_validation import (
    ConfirmedRuleSourcesChanged,
    require_confirmed_user_rule_sources,
)
from app.services.rule_packages.contracts import (
    KmaiCompatibilityExport,
    RulePackageV2,
)
from app.services.rule_packages.hashing import (
    legacy_rule_package_content_hash,
    rule_package_content_hash,
)
from app.services.rule_packages.kmai_export import build_kmai_compatibility_export
from app.services.rule_packages.lifecycle import publish_rule_package
from app.services.rule_packages.validator import (
    validate_rule_package,
    validate_rule_package_factor_bindings,
)


class RulePackagePublicationRequestInvalid(ValueError):
    def __init__(self, detail: Any):
        super().__init__(str(detail))
        self.detail = detail


class RulePackagePublicationConflict(ValueError):
    def __init__(self, detail: Any):
        super().__init__(str(detail))
        self.detail = detail


class RulePackagePublicationUnprocessable(ValueError):
    def __init__(self, detail: Any):
        super().__init__(str(detail))
        self.detail = detail


class RulePackageVersionConflict(ValueError):
    pass


@dataclass(frozen=True)
class FinalizedRulePackagePublication:
    row: FinalizedRulePackage
    kmai_compatibility: KmaiCompatibilityExport | None


@dataclass(frozen=True)
class _PreparedPublication:
    package_name: str
    schema_version: str
    manifest: dict[str, Any]
    test_cases: list[dict[str, Any]]
    validation_report: dict[str, Any]
    content_hash: str
    kmai_compatibility: KmaiCompatibilityExport | None
```

- [ ] **Step 5: 原序提取发布校验**

实现：

```python
async def _prepare_publication(
    body: FinalizedRulePackageSaveRequest,
    project: Project,
    db: AsyncSession,
) -> _PreparedPublication:
    if project.status not in {"ROUTE_SET_READY", "GENERATED"}:
        raise RulePackagePublicationConflict(
            "当前资料已变更或尚未完成路线提炼，请重新完成第二至四步后再导出规则包。"
        )
    if not body.input_schema:
        raise RulePackagePublicationRequestInvalid("input_schema.json 内容不能为空")
    if not body.route_catalog:
        raise RulePackagePublicationRequestInvalid("route_catalog.json 内容不能为空")
    if not body.route_rules:
        raise RulePackagePublicationRequestInvalid("route_rules.json 内容不能为空")
    if not (body.rule_report_md or "").strip():
        raise RulePackagePublicationRequestInvalid("rule_report.md 内容不能为空")

    schema_version = str(body.schema_version or "1.0").strip()
    if schema_version not in {"1.0", "2.0"}:
        raise RulePackagePublicationRequestInvalid(
            f"不支持的规则包 schema_version：{schema_version}"
        )
    package_name = (body.package_name or "process_route_rules").strip()
    package_name = package_name or "process_route_rules"
    manifest = dict(body.manifest or {})
    test_cases = list(body.test_cases or [])
    server_validation = dict(body.validation_report or {})
    kmai_compatibility = None
```

在上一个代码块后增加以下 V2 分支，保持当前校验顺序和响应 detail：

```python
if schema_version == "2.0":
    try:
        package_v2 = RulePackageV2.model_validate({
            "manifest": manifest,
            "input_schema": body.input_schema,
            "route_catalog": body.route_catalog,
            "route_rules": body.route_rules,
            "test_cases": test_cases,
        })
    except ValidationError as exc:
        raise RulePackagePublicationUnprocessable(
            exc.errors(include_url=False)
        ) from exc

    if package_v2.manifest.project_id != body.project_id:
        raise RulePackagePublicationUnprocessable(
            "manifest.project_id 与请求 project_id 不一致"
        )
    if package_v2.manifest.package_name != package_name:
        raise RulePackagePublicationUnprocessable(
            "manifest.package_name 与请求 package_name 不一致"
        )

    binding_issues = validate_rule_package_factor_bindings(package_v2)
    if binding_issues:
        raise RulePackagePublicationUnprocessable({
            "message": "标准因子绑定校验未通过",
            "issues": [issue.model_dump(mode="json") for issue in binding_issues],
        })

    validation = validate_rule_package(package_v2)
    server_validation = validation.model_dump(mode="json")
    if not validation.valid:
        raise RulePackagePublicationUnprocessable({
            "message": "规则包校验未通过，无法导出。",
            "validation": server_validation,
        })
    if body.route_version_id is None:
        raise RulePackagePublicationUnprocessable(
            "V2 规则包必须关联当前路线版本"
        )
    try:
        await require_confirmed_user_rule_sources(
            package_v2,
            project_id=body.project_id,
            route_version_id=body.route_version_id,
            db=db,
        )
    except ConfirmedRuleSourcesChanged as exc:
        raise RulePackagePublicationConflict(exc.detail) from exc

    content_hash = rule_package_content_hash(package_v2)
    kmai_compatibility = build_kmai_compatibility_export(package_v2)
    if not kmai_compatibility.valid:
        raise RulePackagePublicationUnprocessable({
            "message": "KmAI compatibility validation failed; return to standard-factor review before publishing.",
            "kmai_compatibility": kmai_compatibility.model_dump(mode="json"),
        })
    server_validation["kmai_compatibility"] = {
        "factor_catalog_version": kmai_compatibility.factor_catalog_version,
    }
```

完整的 V1 分支和共同路线归属检查为：

```python
else:
    content_hash = legacy_rule_package_content_hash(
        package_name=package_name,
        input_schema=body.input_schema,
        route_catalog=body.route_catalog,
        route_rules=body.route_rules,
        rule_report_md=body.rule_report_md,
    )

if body.route_version_id is not None:
    route_exists = (
        await db.execute(
            select(NormalizedRouteVersion.id).where(
                NormalizedRouteVersion.id == body.route_version_id,
                NormalizedRouteVersion.project_id == body.project_id,
            )
        )
    ).scalar_one_or_none()
    if not route_exists:
        raise RulePackagePublicationUnprocessable(
            "规则包关联的路线版本不属于当前任务"
        )
```

函数最后返回：

```python
return _PreparedPublication(
    package_name=package_name,
    schema_version=schema_version,
    manifest=manifest,
    test_cases=test_cases,
    validation_report=server_validation,
    content_hash=content_hash,
    kmai_compatibility=kmai_compatibility,
)
```

不得信任调用方提供的 V2 validation report，也不得改变现有校验顺序和错误 detail 结构。

- [ ] **Step 6: 实现版本创建和生命周期转换**

```python
async def create_published_rule_package(
    body: FinalizedRulePackageSaveRequest,
    project: Project,
    db: AsyncSession,
) -> FinalizedRulePackagePublication:
    prepared = await _prepare_publication(body, project, db)
    for _attempt in range(3):
        latest_version = (
            await db.execute(
                select(func.max(FinalizedRulePackage.version)).where(
                    FinalizedRulePackage.project_id == body.project_id
                )
            )
        ).scalar_one_or_none()
        row = FinalizedRulePackage(
            project_id=body.project_id,
            route_version_id=body.route_version_id,
            version=int(latest_version or 0) + 1,
            package_name=prepared.package_name,
            schema_version=prepared.schema_version,
            status="draft",
            manifest_json=json_dumps(prepared.manifest),
            input_schema_json=json_dumps(body.input_schema),
            route_catalog_json=json_dumps(body.route_catalog),
            route_rules_json=json_dumps(body.route_rules),
            test_cases_json=json_dumps_list(prepared.test_cases),
            rule_report_md=body.rule_report_md,
            validation_report_json=json_dumps(prepared.validation_report),
            content_hash=prepared.content_hash,
            created_by=(body.created_by or "默认用户").strip() or "默认用户",
        )
        try:
            async with db.begin_nested():
                db.add(row)
                await db.flush()
                await publish_rule_package(row, db, actor=row.created_by)
            return FinalizedRulePackagePublication(
                row=row,
                kmai_compatibility=prepared.kmai_compatibility,
            )
        except IntegrityError:
            continue
    raise RulePackageVersionConflict(
        "规则包版本正在由其他请求导出，请稍后重试。"
    )
```

发布服务不得调用 `commit()` 或外层 `rollback()`。嵌套事务只隔离唯一索引冲突，使外层工作流锁在重试期间保持有效。

- [ ] **Step 7: 将路由缩减为锁、映射、事务和响应**

```python
project = await acquire_workflow_revision(
    db,
    body.project_id,
    body.expected_workflow_revision,
)
try:
    publication = await create_published_rule_package(body, project, db)
    await db.commit()
except RulePackagePublicationRequestInvalid as exc:
    await db.rollback()
    raise HTTPException(status_code=400, detail=exc.detail) from exc
except RulePackagePublicationConflict as exc:
    await db.rollback()
    raise HTTPException(status_code=409, detail=exc.detail) from exc
except RulePackagePublicationUnprocessable as exc:
    await db.rollback()
    raise HTTPException(status_code=422, detail=exc.detail) from exc
except RulePackageVersionConflict as exc:
    await db.rollback()
    raise HTTPException(status_code=409, detail=str(exc)) from exc
except Exception:
    await db.rollback()
    raise

await db.refresh(publication.row)
return serialize_finalized_rule_package(
    publication.row,
    kmai_compatibility=(
        publication.kmai_compatibility.model_dump(mode="json")
        if publication.kmai_compatibility is not None
        else None
    ),
)
```

删除 `extract.py` import 前逐项运行：

```powershell
rg -n "ValidationError|IntegrityError|func\\.|json_dumps|RulePackageV2|require_confirmed|rule_package_content_hash|publish_rule_package|build_kmai" app/routers/extract.py
```

- [ ] **Step 8: 运行发布、生命周期、确认来源和归档套件**

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_api.py tests/test_rule_package_lifecycle.py tests/test_workflow_invalidation.py tests/test_rule_package_archive.py -v
```

Expected: 新事务测试及现有发布、伪造确认来源、版本、下载和归档测试全部通过。

---

### Task 4: 只把最新规则包 404 解释为不存在

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts:558`
- Create: `process-plan-agent-ui/src/api/extract.spec.ts`

**Interfaces:**
- Consumes: `getLatestFinalizedRulePackage(projectId, forceRefresh)`。
- Produces: `getOptionalLatestFinalizedRulePackage(projectId, forceRefresh): Promise<FinalizedRulePackageResult | null>`。

- [ ] **Step 1: 编写 API 错误分类失败测试**

```typescript
import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({ get: vi.fn() }))

vi.mock('./client', () => ({ api: { get: mocks.get } }))
vi.mock('@/composables/workflowDataCache', () => ({
  clearAllWorkflowDataCache: vi.fn(),
  clearWorkflowProjectDataCache: vi.fn(),
  getWorkflowDataCache: vi.fn(() => null),
  getWorkflowDataRevision: vi.fn(() => 0),
  setWorkflowDataCache: vi.fn(),
}))

import { getOptionalLatestFinalizedRulePackage } from './extract'

describe('getOptionalLatestFinalizedRulePackage', () => {
  beforeEach(() => mocks.get.mockReset())

  it('returns null for a 404 response', async () => {
    mocks.get.mockRejectedValue({ response: { status: 404 } })
    await expect(
      getOptionalLatestFinalizedRulePackage(12, true),
    ).resolves.toBeNull()
  })

  it.each([
    { response: { status: 500 } },
    new Error('network unavailable'),
  ])('rethrows non-404 failures', async (failure) => {
    mocks.get.mockRejectedValue(failure)
    await expect(
      getOptionalLatestFinalizedRulePackage(12, true),
    ).rejects.toBe(failure)
  })
})
```

- [ ] **Step 2: 运行测试并确认导入失败**

```powershell
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: `getOptionalLatestFinalizedRulePackage` 尚未导出。

- [ ] **Step 3: 实现可选读取**

在 `getLatestFinalizedRulePackage` 后增加：

```typescript
export async function getOptionalLatestFinalizedRulePackage(
  projectId: number,
  forceRefresh = false,
): Promise<FinalizedRulePackageResult | null> {
  try {
    return await getLatestFinalizedRulePackage(projectId, forceRefresh)
  } catch (error: any) {
    if (Number(error?.response?.status) === 404) return null
    throw error
  }
}
```

- [ ] **Step 4: 运行聚焦测试**

```powershell
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: PASS。

---

### Task 5: 建立前端规则包指纹与冲突工具

**Files:**
- Modify: `process-plan-agent-ui/src/api/generate.ts`
- Create: `process-plan-agent-ui/src/utils/generateRulePackageContext.ts`
- Create: `process-plan-agent-ui/src/utils/generateRulePackageContext.spec.ts`

**Interfaces:**
- Consumes: 规则包元数据和 Axios 风格错误。
- Produces: `PublishedRulePackageFingerprint`、`publishedRulePackageFingerprint()`、`rulePackageExpectationPayload()`、`isPublishedRulePackageChanged()`。
- `generateRoute()` 接受三个可选 expected-package 字段。

- [ ] **Step 1: 编写指纹和冲突判断失败测试**

```typescript
import { describe, expect, it } from 'vitest'
import {
  isPublishedRulePackageChanged,
  publishedRulePackageFingerprint,
  rulePackageExpectationPayload,
} from './generateRulePackageContext'

describe('generate rule package context', () => {
  it('builds expectations from all available metadata', () => {
    const fingerprint = publishedRulePackageFingerprint({
      id: 41,
      version: 3,
      content_hash: 'abc123',
    })
    expect(rulePackageExpectationPayload(fingerprint)).toEqual({
      expected_rule_package_id: 41,
      expected_rule_package_version: 3,
      expected_rule_package_hash: 'abc123',
    })
  })

  it('omits unavailable metadata for legacy compatibility', () => {
    expect(rulePackageExpectationPayload({
      id: 41,
      version: 3,
      contentHash: null,
    })).toEqual({
      expected_rule_package_id: 41,
      expected_rule_package_version: 3,
    })
  })

  it('recognizes only the dedicated stale-package conflict', () => {
    expect(isPublishedRulePackageChanged({
      response: {
        status: 409,
        data: { detail: { code: 'published_rule_package_changed' } },
      },
    })).toBe(true)
    expect(isPublishedRulePackageChanged({
      response: {
        status: 409,
        data: { detail: { message: 'workflow stale' } },
      },
    })).toBe(false)
  })
})
```

- [ ] **Step 2: 运行测试并确认文件不存在**

```powershell
npm.cmd test -- --run src/utils/generateRulePackageContext.spec.ts
```

Expected: FAIL，因为工具模块尚不存在。

- [ ] **Step 3: 实现纯工具**

```typescript
type RulePackageMetadata = {
  id?: number | null
  version?: number | null
  content_hash?: string | null
}

export type PublishedRulePackageFingerprint = {
  id: number | null
  version: number | null
  contentHash: string | null
}

export const PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE =
  '规则包已更新，请重新确认输入后生成。'

export function publishedRulePackageFingerprint(
  value: RulePackageMetadata,
): PublishedRulePackageFingerprint {
  return {
    id: value.id ?? null,
    version: value.version ?? null,
    contentHash: value.content_hash || null,
  }
}

export function rulePackageExpectationPayload(
  fingerprint: PublishedRulePackageFingerprint | null,
) {
  if (!fingerprint) return {}
  return {
    ...(fingerprint.id !== null
      ? { expected_rule_package_id: fingerprint.id }
      : {}),
    ...(fingerprint.version !== null
      ? { expected_rule_package_version: fingerprint.version }
      : {}),
    ...(fingerprint.contentHash
      ? { expected_rule_package_hash: fingerprint.contentHash }
      : {}),
  }
}

export function isPublishedRulePackageChanged(error: any) {
  return Number(error?.response?.status) === 409
    && error?.response?.data?.detail?.code === 'published_rule_package_changed'
}
```

- [ ] **Step 4: 扩展 generateRoute 请求类型**

```typescript
export async function generateRoute(body: {
  project_id: number
  expected_workflow_revision: number
  expected_rule_package_id?: number
  expected_rule_package_version?: number
  expected_rule_package_hash?: string
  factor_values: Record<string, any>
}) {
  const { data } = await api.post('/api/generate/', body)
  clearAllWorkflowDataCache()
  return data as GenerateRouteResult
}
```

- [ ] **Step 5: 运行工具测试和 TypeScript 构建**

```powershell
npm.cmd test -- --run src/utils/generateRulePackageContext.spec.ts
npm.cmd run build
```

Expected: 工具测试及 `vue-tsc`/Vite 构建通过。

---

### Task 6: 集成生成页和规则定稿页

**Files:**
- Modify: `process-plan-agent-ui/src/views/GenerateView.vue`
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue`

**Interfaces:**
- Consumes: Task 4 的 `getOptionalLatestFinalizedRulePackage()` 和 Task 5 的指纹工具。
- Produces: 新生成请求携带加载时指纹；专用冲突清除旧结果并强制刷新上下文；非 404 读取错误进入现有错误展示。

- [ ] **Step 1: 在 GenerateView 保存完整指纹**

替换 API import，并加入工具 import：

```typescript
import {
  generateRoute,
  getOptionalLatestFinalizedRulePackage,
  listProjects,
  type FinalizedRulePackageResult,
  type GenerateRouteResult,
} from '@/api'
import {
  PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE,
  isPublishedRulePackageChanged,
  publishedRulePackageFingerprint,
  rulePackageExpectationPayload,
  type PublishedRulePackageFingerprint,
} from '@/utils/generateRulePackageContext'
```

用指纹状态替换可变版本状态：

```typescript
const packageFingerprint = ref<PublishedRulePackageFingerprint | null>(null)
const packageVersion = computed(() => packageFingerprint.value?.version ?? null)

function resetRulePackageMetadata() {
  packageFingerprint.value = null
  workflowRevision.value = 0
}

function applyRulePackageMetadata(rulePackage: FinalizedRulePackageResult) {
  packageFingerprint.value = publishedRulePackageFingerprint(rulePackage)
}
```

- [ ] **Step 2: 让上下文加载区分不存在和读取失败**

修改签名和 API 调用：

```typescript
async function loadGenerateContext(forceRefresh = false) {
  const request = contextRequestGuard.start()
  const requestId = ++contextLoadRequestId
  const requestedProjectId = String(route.query.project_id || '')
  const hintedProjectId = Number(requestedProjectId)
  contextLoading.value = true
  error.value = ''
```

```typescript
const projects = await listProjects(forceRefresh)
const latestPackage = await getOptionalLatestFinalizedRulePackage(
  targetProjectId,
  forceRefresh,
)
```

用真实错误替换 catch 中的“无规则包”状态：

```typescript
} catch (err: any) {
  if (!request.isCurrent() || requestId !== contextLoadRequestId) return
  console.warn('读取生成上下文失败', err)
  clearRulePackageContext()
  const detail = err?.response?.data?.detail
  error.value = typeof detail === 'string'
    ? detail
    : detail?.message || err?.message || '读取当前已发布规则包失败，请稍后重试。'
}
```

404 已由可选读取转为 `null`，因此仍进入现有无规则包分支。

- [ ] **Step 3: 提交指纹并处理专用冲突**

生成请求增加：

```typescript
const generatedResult = await generateRoute({
  project_id: generatedProjectId,
  expected_workflow_revision: workflowRevision.value,
  ...rulePackageExpectationPayload(packageFingerprint.value),
  factor_values: factorValues.value,
})
```

在活跃请求的 catch 分支最前面增加：

```typescript
if (isPublishedRulePackageChanged(err)) {
  result.value = null
  clearRulePackageContext()
  await loadGenerateContext(true)
  error.value = PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE
  return
}
```

删除 `refreshGeneratedPackageMetadata()` 及成功路径对它的调用。本次结果已经由后端指纹校验并返回权威 `rule_package_id`、`rule_package_version` 和 `rule_package_hash`，不再发起第二次最新包查询。

- [ ] **Step 4: 在 FinalizeView 使用共享可选读取**

把 import 从 `getLatestFinalizedRulePackage` 改为 `getOptionalLatestFinalizedRulePackage`，然后替换：

```typescript
getLatestFinalizedRulePackage(projectId.value, forceRefresh).catch(() => null)
```

为：

```typescript
getOptionalLatestFinalizedRulePackage(projectId.value, forceRefresh)
```

不得修改后续哈希比较、过期版本状态、按钮保护或 workspace catch。

- [ ] **Step 5: 证明宽泛 catch 和冗余成功后查询已消失**

```powershell
rg -n "getLatestFinalizedRulePackage\\(.*catch|catch\\(\\(\\) => null\\)|refreshGeneratedPackageMetadata" src/views/FinalizeView.vue src/views/GenerateView.vue
```

Expected: 无匹配。

- [ ] **Step 6: 运行前端聚焦、全量测试和构建**

```powershell
npm.cmd test -- --run src/api/extract.spec.ts src/utils/generateRulePackageContext.spec.ts
npm.cmd test
npm.cmd run build
```

Expected: 全部命令退出码为 0；构建证明请求 spread 与 `generateRoute` 类型兼容。

---

### Task 7: 全量回归与完成审计

**Files:**
- Verify only；只有验证失败能证明实现缺陷时才修改 Task 1-6 的文件。

**Interfaces:**
- Consumes: 前六个任务的全部输出。
- Produces: 对设计中每项完成标准的可复核证据。

- [ ] **Step 1: 运行后端全量测试**

```powershell
..\.runtime\python\python.exe -m pytest -q
```

Expected: 全部后端测试通过；已有环境相关 skip 可以保留，但必须记录准确数量。

- [ ] **Step 2: 运行前端全量测试**

```powershell
npm.cmd test
```

Expected: 全部 Vitest 测试通过。

- [ ] **Step 3: 运行生产构建**

```powershell
npm.cmd run build
```

Expected: `vue-tsc -b` 和 Vite 都以 0 退出。

- [ ] **Step 4: 重跑两个缺陷证明**

后端：

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -k "fingerprint" -v
```

前端：

```powershell
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: 过期指纹在无持久化副作用的情况下被拒绝，且只有 404 转为 `null`。

- [ ] **Step 5: 审计范围、协议与工作区**

从仓库根目录运行：

```powershell
git diff --check
git status --short
git diff --stat
rg -n "expected_rule_package_(id|version|hash)|published_rule_package_changed" process-plan-agent-api process-plan-agent-ui
```

Expected:

- 无空白错误。
- 没有数据库、ZIP 格式、V1 算法、布局或无关计划变更。
- 仅 File Map 中列出的实现文件、设计文档和本计划发生变化。
- 无关 boolean-group 计划仍保持未跟踪且未被修改。
- 三个可选字段和稳定冲突 code 在后端契约、服务、前端请求和测试中形成完整链路。

- [ ] **Step 6: 最终人工差异复核**

```powershell
git diff -- process-plan-agent-api/app process-plan-agent-api/tests process-plan-agent-ui/src
```

逐项确认：旧客户端省略指纹仍执行、指纹冲突先于规划与持久化、服务不提交外层事务、非 404 错误不被转成“无规则包”、ProcessMind/KmAI 交接协议未变。未经用户授权不暂存、不提交、不推送。
