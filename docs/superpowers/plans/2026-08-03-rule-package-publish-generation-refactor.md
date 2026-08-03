# Rule Package Publish and Generation Refactor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Prevent generation from silently switching to a newer published rule package, preserve real latest-package lookup errors, and move publish/V2 execution domain logic out of HTTP routers without changing the normal UI or API responses.

**Architecture:** Add an optional published-package fingerprint to `GenerateRequest` and verify it under the existing project workflow lock before selecting either the V1 or V2 engine. Extract package publication and V2 validation/planning into focused backend services, then make both frontend pages use a shared “404 means absent” API and let the generation page submit the fingerprint it loaded.

**Tech Stack:** Python 3.11+, FastAPI, Pydantic 2, SQLAlchemy async, SQLite, pytest; Vue 3, TypeScript 5.9, Axios, Vitest, Vite.

## Global Constraints

- Preserve the existing API paths, response fields, button copy, download rules, and successful generation output.
- `expected_rule_package_id`, `expected_rule_package_version`, and `expected_rule_package_hash` are optional for backward compatibility.
- New frontend requests submit every non-null fingerprint field loaded with the input schema.
- A provided fingerprint mismatch returns HTTP 409 with `detail.code == "published_rule_package_changed"` before planning or persistence.
- Only a 404 latest-package response becomes `null`; network, authentication, conflict, validation, and 5xx errors are rethrown.
- Keep the V1 generation algorithm and KmAI/archive formats unchanged.
- Do not add dependencies or modify the database schema.
- Keep the unrelated untracked `docs/superpowers/plans/2026-08-03-generate-input-boolean-group.md` out of every commit.
- Each task commit must contain only that task's files.
- Run backend test commands from `process-plan-agent-api`, frontend commands from `process-plan-agent-ui`, and Git commands from the repository root.

---

## File Map

### Backend

- Create `process-plan-agent-api/app/services/rule_packages/execution.py`: load and fingerprint-check the active package; validate and execute persisted V2 packages.
- Create `process-plan-agent-api/app/services/rule_packages/publishing.py`: prepare, version, persist, and lifecycle-transition a finalized package without committing the request transaction.
- Modify `process-plan-agent-api/app/schemas/schemas.py`: add optional expected-package fields to `GenerateRequest`.
- Modify `process-plan-agent-api/app/routers/generate.py`: delegate package selection and V2 execution; keep HTTP, V1, persistence, and response assembly.
- Modify `process-plan-agent-api/app/routers/extract.py`: delegate publication; keep workflow locking, HTTP mapping, commit, refresh, and serialization.
- Modify `process-plan-agent-api/tests/test_generate_v2_production.py`: integration coverage for current, stale, and omitted fingerprints.
- Create `process-plan-agent-api/tests/test_rule_package_execution.py`: focused V2 execution-service tests.
- Modify `process-plan-agent-api/tests/test_rule_package_api.py`: publication-service characterization and rollback coverage.

### Frontend

- Modify `process-plan-agent-ui/src/api/extract.ts`: add `getOptionalLatestFinalizedRulePackage()`.
- Create `process-plan-agent-ui/src/api/extract.spec.ts`: prove only 404 becomes `null`.
- Modify `process-plan-agent-ui/src/api/generate.ts`: type the optional expectation fields.
- Create `process-plan-agent-ui/src/utils/generateRulePackageContext.ts`: pure fingerprint/payload/conflict helpers.
- Create `process-plan-agent-ui/src/utils/generateRulePackageContext.spec.ts`: helper behavior tests.
- Modify `process-plan-agent-ui/src/views/GenerateView.vue`: store and submit the fingerprint; recover from the dedicated stale-package conflict.
- Modify `process-plan-agent-ui/src/views/FinalizeView.vue`: use the optional latest-package API without swallowing other errors.

---

### Task 1: Pin Generation to the Loaded Published Package

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/execution.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py:490`
- Modify: `process-plan-agent-api/app/routers/generate.py:977`
- Test: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- Consumes: `load_published_rule_package(project_id, db)` and the existing project workflow lock.
- Produces: `RulePackageExpectation`, `PublishedRulePackageChanged`, and `load_published_rule_package_for_execution()`.
- `PublishedRulePackageChanged.detail` is the exact HTTP `detail` object required by the frontend.

- [ ] **Step 1: Add fingerprint helpers and failing endpoint tests**

Add this helper beside `_generation_state()`:

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

Add one success test and one parameterized stale test:

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
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "stale-fingerprint"))
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
    assert response.json()["detail"]["code"] == "published_rule_package_changed"
    assert response.json()["detail"]["current_rule_package"]["version"] == 1
    _assert_generation_not_persisted(session_factory, project_id)
```

Keep `test_generate_uses_published_v2_plan_route` unchanged; it is the backward-compatibility test for omitted fingerprints. The 409 response plus the unchanged project status and zero generated rows prove the request exits before planning persistence.

- [ ] **Step 2: Run the stale-package tests and verify failure**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -k "fingerprint or uses_published_v2" -v
```

Expected: matching currently passes because Pydantic ignores the new JSON fields, while stale cases FAIL with status 200 instead of 409.

- [ ] **Step 3: Add the optional request fields**

Add these fields immediately after `expected_workflow_revision`:

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

- [ ] **Step 4: Implement the package expectation boundary**

Create `execution.py` with these public types and loader:

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
        return any(value is not None for value in (
            self.package_id,
            self.version,
            self.content_hash,
        ))


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
    checks = (
        expectation.package_id is None or row.id == expectation.package_id,
        expectation.version is None or row.version == expectation.version,
        expectation.content_hash is None or row.content_hash == expectation.content_hash,
    )
    return all(checks)


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

- [ ] **Step 5: Integrate the loader before the V1/V2 branch**

Replace `_latest_finalized_rule_package()` usage in `generate_route()` with:

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

Remove the now-unused `_latest_finalized_rule_package()` helper and direct loader import only after `rg` confirms no other use.

- [ ] **Step 6: Run focused and full generation tests**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -v
```

Expected: all tests PASS, including the existing request without a fingerprint.

- [ ] **Step 7: Commit the package pin**

```powershell
git add -- process-plan-agent-api/app/schemas/schemas.py process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/routers/generate.py process-plan-agent-api/tests/test_generate_v2_production.py
git commit -m "fix: pin generation to published rule package"
```

---

### Task 2: Extract V2 Validation and Planning

**Files:**
- Modify: `process-plan-agent-api/app/services/rule_packages/execution.py`
- Modify: `process-plan-agent-api/app/routers/generate.py:1025-1076`
- Create: `process-plan-agent-api/tests/test_rule_package_execution.py`

**Interfaces:**
- Consumes: a persisted `FinalizedRulePackage` row and normalized explicit V2 inputs.
- Produces: `V2RulePackageExecution(plan: RoutePlan)` via `execute_published_v2_rule_package()`.
- Raises: `PublishedRulePackageInvalid` with a validation report, `PublishedRulePackageInputInvalid` with input issues, plus existing `RulePackageLifecycleError` and `RoutePlanningError`.

- [ ] **Step 1: Write focused service tests**

Create a persisted-row helper from the shared V2 fixture and add:

```python
def test_execute_published_v2_rule_package_returns_deterministic_plan(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)

    result = execute_published_v2_rule_package(row, {
        "material": {"grade": "9Cr18"},
        "cad": {"features": ["槽类特征"]},
        "target_hardness_hrc": 58,
    })

    assert result.plan.selected_process_ids == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
    assert "material.9cr18.quench" in [
        trace.rule_id for trace in result.plan.traces if trace.matched
    ]


def test_execute_published_v2_rule_package_reports_input_issues(rule_package_v2_payload):
    row = _published_v2_row(rule_package_v2_payload)

    with pytest.raises(PublishedRulePackageInputInvalid) as caught:
        execute_published_v2_rule_package(row, {})

    assert any(issue.field == "material.grade" for issue in caught.value.issues)
```

The helper must populate `manifest_json`, `input_schema_json`, `route_catalog_json`, `route_rules_json`, `test_cases_json`, `schema_version="2.0"`, and `status="published"` from `rule_package_v2_payload`.

- [ ] **Step 2: Run the new service test and verify import failure**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_execution.py -v
```

Expected: FAIL because the execution result and exceptions do not exist.

- [ ] **Step 3: Implement the typed V2 execution result**

Append to `execution.py`:

```python
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
    inputs: dict[str, object],
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

Use the actual exported input issue type from `input_validation.py`. If that module names it differently, import the exact declared type and keep `PublishedRulePackageInputInvalid.issues` typed to that declaration; do not replace it with `Any`.

- [ ] **Step 4: Replace the inline V2 block in the router**

The V2 branch must call the service and map its result:

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
        template_group_aliases=list(step.template_group_aliases or []),
    )
    for step in plan.steps
]
matched_rule_ids = [trace.rule_id for trace in plan.traces if trace.matched]
selected_process_ids = list(plan.selected_process_ids)
```

Map exceptions without changing response shapes:

```python
except PublishedRulePackageInvalid as exc:
    raise HTTPException(status_code=422, detail={
        "message": "已发布规则包校验失败",
        "validation": exc.validation.model_dump(mode="json"),
    }) from exc
except PublishedRulePackageInputInvalid as exc:
    raise HTTPException(
        status_code=422,
        detail=input_validation_error_detail(exc.issues),
    ) from exc
```

Keep existing lifecycle, planning, and `ValueError` mappings. Remove direct `v2_package_from_row`, `validate_rule_package`, `validate_inputs`, and `plan_route` imports only when unused elsewhere.

- [ ] **Step 5: Run service and production-generation suites**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_execution.py tests/test_generate_v2_production.py -v
```

Expected: PASS with the same endpoint response fields and selected-process order.

- [ ] **Step 6: Commit the execution boundary**

```powershell
git add -- process-plan-agent-api/app/services/rule_packages/execution.py process-plan-agent-api/app/routers/generate.py process-plan-agent-api/tests/test_rule_package_execution.py
git commit -m "refactor: extract rule package execution"
```

---

### Task 3: Extract Finalized Rule Package Publication

**Files:**
- Create: `process-plan-agent-api/app/services/rule_packages/publishing.py`
- Modify: `process-plan-agent-api/app/routers/extract.py:425-577`
- Modify: `process-plan-agent-api/tests/test_rule_package_api.py`

**Interfaces:**
- Consumes: `FinalizedRulePackageSaveRequest`, the workflow-locked `Project`, and `AsyncSession`.
- Produces: `FinalizedRulePackagePublication(row, kmai_compatibility)` through `create_published_rule_package()`.
- Raises: `RulePackagePublicationError(status_code, detail)` or `RulePackageVersionConflict`; it never commits the outer request transaction.

- [ ] **Step 1: Add a rollback characterization test**

Add a test that publishes V1, attempts an invalid second V2 publication, then verifies the first remains current:

```python
def test_failed_republication_keeps_current_package_and_version_sequence(rule_package_v2_payload):
    first = client.post(
        "/api/extract/finalized-rule-packages",
        json={
            **_v2_save_payload(rule_package_v2_payload),
            "schema_version": "1.0",
            "manifest": {},
            "test_cases": [],
        },
    )
    assert first.status_code == 200

    invalid = deepcopy(rule_package_v2_payload)
    invalid["manifest"]["project_id"] = 999
    rejected = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(invalid),
    )
    assert rejected.status_code == 422

    latest = client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == first.json()["id"]
    assert latest.json()["version"] == 1
    assert latest.json()["status"] == "published"
```

- [ ] **Step 2: Run the characterization test**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_api.py -k "failed_republication" -v
```

Expected: PASS before refactoring. This locks the transaction behavior that the extraction must preserve.

- [ ] **Step 3: Define publication result and domain errors**

Create `publishing.py` with:

```python
"""Validation and persistence boundary for finalized rule-package publication."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models.models import FinalizedRulePackage, Project
from app.schemas.schemas import FinalizedRulePackageSaveRequest
from app.services.rule_packages.contracts import KmaiCompatibilityExport


class RulePackagePublicationError(ValueError):
    def __init__(self, status_code: int, detail: Any):
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail


class RulePackageVersionConflict(ValueError):
    pass


@dataclass(frozen=True)
class FinalizedRulePackagePublication:
    row: FinalizedRulePackage
    kmai_compatibility: KmaiCompatibilityExport | None
```

- [ ] **Step 4: Move preparation and validation into a private helper**

Implement:

```python
@dataclass(frozen=True)
class _PreparedPublication:
    package_name: str
    schema_version: str
    manifest: dict[str, Any]
    test_cases: list[dict[str, Any]]
    validation_report: dict[str, Any]
    content_hash: str
    kmai_compatibility: KmaiCompatibilityExport | None


async def _prepare_publication(
    body: FinalizedRulePackageSaveRequest,
    project: Project,
    db: AsyncSession,
) -> _PreparedPublication:
    if project.status not in {"ROUTE_SET_READY", "GENERATED"}:
        raise RulePackagePublicationError(
            409,
            "当前资料已变更或尚未完成路线提炼，请重新完成第二至四步后再导出规则包。",
        )
    if not body.input_schema:
        raise RulePackagePublicationError(400, "input_schema.json 内容不能为空")
    if not body.route_catalog:
        raise RulePackagePublicationError(400, "route_catalog.json 内容不能为空")
    if not body.route_rules:
        raise RulePackagePublicationError(400, "route_rules.json 内容不能为空")
    if not (body.rule_report_md or "").strip():
        raise RulePackagePublicationError(400, "rule_report.md 内容不能为空")

    schema_version = str(body.schema_version or "1.0").strip()
    if schema_version not in {"1.0", "2.0"}:
        raise RulePackagePublicationError(
            400,
            f"不支持的规则包 schema_version：{schema_version}",
        )
    package_name = (body.package_name or "process_route_rules").strip() or "process_route_rules"
    server_validation = dict(body.validation_report or {})
    manifest = dict(body.manifest or {})
    test_cases = list(body.test_cases or [])
    kmai_compatibility = None

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
            raise RulePackagePublicationError(
                422,
                exc.errors(include_url=False),
            ) from exc
        if package_v2.manifest.project_id != body.project_id:
            raise RulePackagePublicationError(
                422,
                "manifest.project_id 与请求 project_id 不一致",
            )
        if package_v2.manifest.package_name != package_name:
            raise RulePackagePublicationError(
                422,
                "manifest.package_name 与请求 package_name 不一致",
            )
        binding_issues = validate_rule_package_factor_bindings(package_v2)
        if binding_issues:
            raise RulePackagePublicationError(422, {
                "message": "标准因子绑定校验未通过",
                "issues": [issue.model_dump(mode="json") for issue in binding_issues],
            })
        validation = validate_rule_package(package_v2)
        server_validation = validation.model_dump(mode="json")
        if not validation.valid:
            raise RulePackagePublicationError(422, {
                "message": "规则包校验未通过，无法导出。",
                "validation": server_validation,
            })
        if body.route_version_id is None:
            raise RulePackagePublicationError(422, "V2 规则包必须关联当前路线版本")
        try:
            await require_confirmed_user_rule_sources(
                package_v2,
                project_id=body.project_id,
                route_version_id=body.route_version_id,
                db=db,
            )
        except HTTPException as exc:
            raise RulePackagePublicationError(
                exc.status_code,
                exc.detail,
            ) from exc
        content_hash = rule_package_content_hash(package_v2)
        kmai_compatibility = build_kmai_compatibility_export(package_v2)
        if not kmai_compatibility.valid:
            raise RulePackagePublicationError(422, {
                "message": "KmAI compatibility validation failed; return to standard-factor review before publishing.",
                "kmai_compatibility": kmai_compatibility.model_dump(mode="json"),
            })
        server_validation["kmai_compatibility"] = {
            "factor_catalog_version": kmai_compatibility.factor_catalog_version,
        }
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
            raise RulePackagePublicationError(
                422,
                "规则包关联的路线版本不属于当前任务",
            )

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

The code preserves every existing status/detail pair:

- project status: 409;
- empty input schema, route catalog, route rules, or report: 400;
- unsupported schema: 400;
- Pydantic and manifest mismatch: 422;
- factor binding, server validation, KmAI validation, route ownership, and confirmed-source checks: their current 422/409 details.

The helper must build and return `server_validation` from server results, not trust the caller's validation result. For V2, retain only `factor_catalog_version` under `kmai_compatibility` exactly as today. This step is a code move plus typed return; do not change validation order.

- [ ] **Step 5: Move version creation and lifecycle transition**

Implement:

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
    raise RulePackageVersionConflict("规则包版本正在由其他请求导出，请稍后重试。")
```

Import the existing hash, validation, confirmation, JSON, lifecycle, SQLAlchemy, Pydantic, and `HTTPException` dependencies into the service. `HTTPException` is used only to adapt the existing confirmed-source helper into `RulePackagePublicationError`; the publication service exposes no HTTP exception to its caller. The nested transaction keeps the workflow-locking outer transaction alive across a uniqueness retry. Do not call `commit()` or `rollback()` in this service.

- [ ] **Step 6: Reduce the route to locking, mapping, commit, and response**

Replace the extracted body with:

```python
project = await acquire_workflow_revision(
    db,
    body.project_id,
    body.expected_workflow_revision,
)
try:
    publication = await create_published_rule_package(body, project, db)
except RulePackagePublicationError as exc:
    raise HTTPException(status_code=exc.status_code, detail=exc.detail) from exc
except RulePackageVersionConflict as exc:
    raise HTTPException(status_code=409, detail=str(exc)) from exc

await db.commit()
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

Remove imports from `extract.py` only when `rg` proves they are no longer used by another endpoint.

- [ ] **Step 7: Run publication, lifecycle, and archive suites**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_rule_package_api.py tests/test_rule_package_lifecycle.py tests/test_rule_package_archive.py -v
```

Expected: PASS. Verify the new rollback characterization and existing download/version tests.

- [ ] **Step 8: Commit the publication boundary**

```powershell
git add -- process-plan-agent-api/app/services/rule_packages/publishing.py process-plan-agent-api/app/routers/extract.py process-plan-agent-api/tests/test_rule_package_api.py
git commit -m "refactor: extract rule package publication"
```

---

### Task 4: Preserve Latest-Package Lookup Errors

**Files:**
- Modify: `process-plan-agent-ui/src/api/extract.ts:558`
- Create: `process-plan-agent-ui/src/api/extract.spec.ts`

**Interfaces:**
- Consumes: `getLatestFinalizedRulePackage(projectId, forceRefresh)`.
- Produces: `getOptionalLatestFinalizedRulePackage(projectId, forceRefresh): Promise<FinalizedRulePackageResult | null>`.

- [ ] **Step 1: Write API-layer error classification tests**

Mock `./client` and workflow cache imports before importing `./extract`:

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

  it('returns null only for a 404 response', async () => {
    mocks.get.mockRejectedValue({ response: { status: 404 } })
    await expect(getOptionalLatestFinalizedRulePackage(12, true)).resolves.toBeNull()
  })

  it.each([
    { response: { status: 500 } },
    new Error('network unavailable'),
  ])('rethrows non-404 failures', async (failure) => {
    mocks.get.mockRejectedValue(failure)
    await expect(getOptionalLatestFinalizedRulePackage(12, true)).rejects.toBe(failure)
  })
})
```

- [ ] **Step 2: Run the focused test and verify import failure**

Run:

```powershell
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: FAIL because `getOptionalLatestFinalizedRulePackage` is not exported.

- [ ] **Step 3: Implement the optional lookup**

Add immediately after `getLatestFinalizedRulePackage`:

```typescript
export async function getOptionalLatestFinalizedRulePackage(
  projectId: number,
  forceRefresh = false,
) {
  try {
    return await getLatestFinalizedRulePackage(projectId, forceRefresh)
  } catch (error: any) {
    if (Number(error?.response?.status) === 404) return null
    throw error
  }
}
```

- [ ] **Step 4: Run the focused test**

Run:

```powershell
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: PASS.

- [ ] **Step 5: Commit the API error boundary**

```powershell
git add -- process-plan-agent-ui/src/api/extract.ts process-plan-agent-ui/src/api/extract.spec.ts
git commit -m "fix: preserve rule package lookup errors"
```

---

### Task 5: Send and Recover from the Package Fingerprint

**Files:**
- Modify: `process-plan-agent-ui/src/api/generate.ts`
- Create: `process-plan-agent-ui/src/utils/generateRulePackageContext.ts`
- Create: `process-plan-agent-ui/src/utils/generateRulePackageContext.spec.ts`
- Modify: `process-plan-agent-ui/src/views/GenerateView.vue`

**Interfaces:**
- Consumes: `FinalizedRulePackageResult` and Axios-style errors.
- Produces: `PublishedRulePackageFingerprint`, `rulePackageExpectationPayload()`, and `isPublishedRulePackageChanged()`.
- `generateRoute()` accepts the three optional expected-package fields.

- [ ] **Step 1: Write pure fingerprint and conflict tests**

Create:

```typescript
import { describe, expect, it } from 'vitest'
import {
  isPublishedRulePackageChanged,
  publishedRulePackageFingerprint,
  rulePackageExpectationPayload,
} from './generateRulePackageContext'

describe('generate rule package context', () => {
  it('builds request expectations from all non-null metadata', () => {
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
      response: { status: 409, data: { detail: { code: 'published_rule_package_changed' } } },
    })).toBe(true)
    expect(isPublishedRulePackageChanged({
      response: { status: 409, data: { detail: { message: 'workflow stale' } } },
    })).toBe(false)
  })
})
```

- [ ] **Step 2: Run the utility test and verify failure**

Run:

```powershell
npm.cmd test -- --run src/utils/generateRulePackageContext.spec.ts
```

Expected: FAIL because the utility does not exist.

- [ ] **Step 3: Implement the pure utility**

Create:

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

export const PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE = '规则包已更新，请重新确认输入后生成。'

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

- [ ] **Step 4: Extend the frontend request type**

Update `generateRoute`:

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

- [ ] **Step 5: Store the fingerprint in GenerateView**

Import `getOptionalLatestFinalizedRulePackage` and the new utility. Replace mutable `packageVersion` with:

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

Change `loadGenerateContext` to accept `forceRefresh = false` and make these exact edits:

```typescript
async function loadGenerateContext(forceRefresh = false) {
```

After `contextLoading.value = true`:

```typescript
error.value = ''
```

Change the two API calls:

```typescript
const projects = await listProjects(forceRefresh)
const latestPackage = await getOptionalLatestFinalizedRulePackage(
  targetProjectId,
  forceRefresh,
)
```

Replace the existing catch body with:

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

Leave the request-current guards, project resolution, schema initialization, and `finally` block unchanged.

- [ ] **Step 6: Submit the fingerprint and handle only its dedicated conflict**

Add the payload spread:

```typescript
const generatedResult = await generateRoute({
  project_id: generatedProjectId,
  expected_workflow_revision: workflowRevision.value,
  ...rulePackageExpectationPayload(packageFingerprint.value),
  factor_values: factorValues.value,
})
```

At the start of the active-request catch branch, add:

```typescript
if (isPublishedRulePackageChanged(err)) {
  result.value = null
  await loadGenerateContext(true)
  if (!error.value) error.value = PUBLISHED_RULE_PACKAGE_CHANGED_MESSAGE
  return
}
```

Use `getOptionalLatestFinalizedRulePackage(generatedProjectId, true)` in `refreshGeneratedPackageMetadata()`. Do not convert errors to `null` there; the surrounding generation catch must surface the failure.

- [ ] **Step 7: Run utility tests and the full frontend suite**

Run:

```powershell
npm.cmd test -- --run src/utils/generateRulePackageContext.spec.ts
npm.cmd test
npm.cmd run build
```

Expected: all commands exit 0. The build proves the spread result satisfies `generateRoute`'s request type.

- [ ] **Step 8: Commit the frontend package pin**

```powershell
git add -- process-plan-agent-ui/src/api/generate.ts process-plan-agent-ui/src/utils/generateRulePackageContext.ts process-plan-agent-ui/src/utils/generateRulePackageContext.spec.ts process-plan-agent-ui/src/views/GenerateView.vue
git commit -m "fix: guard generation rule package context"
```

---

### Task 6: Apply Optional Lookup Semantics to FinalizeView

**Files:**
- Modify: `process-plan-agent-ui/src/views/FinalizeView.vue:1090`

**Interfaces:**
- Consumes: `getOptionalLatestFinalizedRulePackage(projectId, forceRefresh)` from Task 4.
- Produces: no new public interface; non-404 failures now reach the existing workspace error branch.

- [ ] **Step 1: Replace the broad catch**

Change the API import from `getLatestFinalizedRulePackage` to `getOptionalLatestFinalizedRulePackage`, then replace:

```typescript
getLatestFinalizedRulePackage(projectId.value, forceRefresh).catch(() => null)
```

with:

```typescript
getOptionalLatestFinalizedRulePackage(projectId.value, forceRefresh)
```

Do not alter the later hash comparison, stale-version state, button guards, or workspace catch branch.

- [ ] **Step 2: Prove no broad latest-package catch remains**

Run:

```powershell
rg -n "getLatestFinalizedRulePackage\(.*catch|catch\(\(\) => null\)" process-plan-agent-ui/src/views/FinalizeView.vue process-plan-agent-ui/src/views/GenerateView.vue
```

Expected: no matches.

- [ ] **Step 3: Run focused API tests, all UI tests, and build**

Run:

```powershell
npm.cmd test -- --run src/api/extract.spec.ts src/utils/generateRulePackageContext.spec.ts
npm.cmd test
npm.cmd run build
```

Expected: all commands exit 0.

- [ ] **Step 4: Commit the finalize-page integration**

```powershell
git add -- process-plan-agent-ui/src/views/FinalizeView.vue
git commit -m "refactor: share optional rule package lookup"
```

---

### Task 7: Full Regression and Completion Audit

**Files:**
- Verify only; modify a task file only if a failing check proves a required correction.

**Interfaces:**
- Consumes: all prior task outputs.
- Produces: verification evidence for every design completion criterion.

- [ ] **Step 1: Run the complete backend suite**

Run:

```powershell
..\.runtime\python\python.exe -m pytest -q
```

Expected: all backend tests pass; the existing single environment-dependent skip may remain.

- [ ] **Step 2: Run the complete frontend suite**

Run:

```powershell
npm.cmd test
```

Expected: all frontend tests pass.

- [ ] **Step 3: Run the production build**

Run:

```powershell
npm.cmd run build
```

Expected: `vue-tsc -b` and Vite both exit 0.

- [ ] **Step 4: Audit scope and whitespace**

Run from the repository root:

```powershell
git diff --check
git status --short
git diff --stat 1118016..HEAD
```

Expected:

- no whitespace errors;
- no database, ZIP-format, V1 algorithm, layout, or unrelated-plan changes;
- only the files named by Tasks 1-6 differ from the design commit, apart from the implementation-plan document;
- the unrelated boolean-group plan remains untracked and uncommitted.

- [ ] **Step 5: Re-run the two defect proofs**

Run:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_generate_v2_production.py -k "fingerprint" -v
npm.cmd test -- --run src/api/extract.spec.ts
```

Expected: stale fingerprints are rejected without persistence, and only 404 becomes `null`.

- [ ] **Step 6: Review commits without creating another commit**

Run:

```powershell
git log --oneline --decorate -8
```

Expected: one focused implementation commit per completed task, with no final empty or verification-only commit.
