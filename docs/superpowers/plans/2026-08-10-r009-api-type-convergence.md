# R-009 API Type Convergence Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 收敛工作流状态的后端枚举和前端 API DTO，并建立可重复执行的 OpenAPI 契约校验，降低服务端字段漂移风险。

**Architecture:** 数据库继续保存现有字符串值；新增共享后端状态契约模块，由 Pydantic 响应模型和规则包状态模型复用。前端新增 API DTO/status 模块，逐步替代当前 API 层的裸状态字符串和 `Record<string, any>`；契约脚本从 FastAPI OpenAPI 文档校验关键状态枚举与字段，作为前后端边界的自动化门禁。

**Tech Stack:** Python 3.13/ FastAPI / Pydantic v2 / pytest；Vue 3 / TypeScript / Vitest；Node/npm 现有构建链。

## Global Constraints

- 不修改数据库 schema、既有路由 URL、V2 规则包 JSON 或 KmAI V1 文件协议。
- 数据库存储保持 VARCHAR；未知状态必须在 API 响应校验或契约检查中暴露，不能静默降级为 `any`。
- 不引入新的运行时依赖；前端继续使用现有 TypeScript/Vitest。
- 修改前端 API DTO 后必须运行前端相关 Vitest、`vue-tsc -b` 和生产构建。
- 修改后端响应模型后必须运行契约测试及后端全量 pytest。

---

### Task 1: Backend workflow status contracts

**Files:**
- Create: `process-plan-agent-api/app/contracts/__init__.py`
- Create: `process-plan-agent-api/app/contracts/status.py`
- Modify: `process-plan-agent-api/app/schemas/schemas.py`
- Modify: `process-plan-agent-api/app/services/rule_packages/contracts.py`
- Test: `process-plan-agent-api/tests/test_api_contracts.py`

**Interfaces:**
- Produces `ProjectStatus`, `DocumentStatus`, `ExtractionTaskStatus`, `OperationReviewStatus`, `ConditionReviewStatus`, `RouteReviewDecision`, `RulePackageStatus`, `WorkflowCapability` as `str, Enum` values.
- Produces `STATUS_ENUMS` mapping used by contract checks.

- [x] **Step 1: Write the failing test**

Add tests that import the status contract and assert exact values, then inspect `app.openapi()` and assert the corresponding response schemas expose those enum values and `workflow_revision` remains required where applicable.

- [x] **Step 2: Run test to verify it fails**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_api_contracts.py
```

Expected: FAIL because `app.contracts.status` and the typed response schemas do not exist yet.

- [x] **Step 3: Write minimal implementation**

Create the enum module without changing persisted values. Replace response-model status annotations in `schemas.py` and rule-package status annotations in `services/rule_packages/contracts.py` with the shared enums. Keep free-form `stage`, messages, validation details, and package JSON as existing types.

- [x] **Step 4: Run test to verify it passes**

Run the focused contract test again and confirm all assertions pass.

- [x] **Step 5: Run backend regression**

```powershell
..\.runtime\python\python.exe -m pytest -q
```

### Task 2: Frontend reusable DTO/status types

**Files:**
- Create: `process-plan-agent-ui/src/api/dto.ts`
- Modify: `process-plan-agent-ui/src/api/projects.ts`
- Modify: `process-plan-agent-ui/src/api/extract.ts`
- Modify: `process-plan-agent-ui/src/api/rulePackages.ts`
- Modify: `process-plan-agent-ui/src/api/generate.ts`
- Test: `process-plan-agent-ui/src/api/dto.spec.ts`

**Interfaces:**
- Produces strict frontend aliases for project/task/document/package/review statuses and shared `ApiRecord` (`Record<string, unknown>` only where payloads are intentionally open JSON).
- Produces `ProjectDto`, `ExtractionTaskStatusDto`, `FinalizedRulePackageDto`, and `RulePackageStatusDto` aliases used by API functions.

- [x] **Step 1: Write the failing test**

Add a Vitest test importing the new status value arrays and checking the backend-compatible values, including rejection of an unknown status through a small runtime `isKnownStatus` helper.

- [x] **Step 2: Run test to verify it fails**

```powershell
npm.cmd test -- src/api/dto.spec.ts
```

Expected: FAIL because the DTO module and status helpers do not exist.

- [x] **Step 3: Write minimal implementation**

Create `dto.ts` with `as const` status arrays, derived union types, `ApiRecord`, and the shared DTO shapes. Update API modules to import and use these aliases; replace `Record<string, any>` with `Record<string, unknown>` or named DTOs where the payload is intentionally JSON-shaped. Preserve API URLs and response field names.

- [x] **Step 4: Run frontend focused tests and type check**

```powershell
npm.cmd test -- src/api/dto.spec.ts src/api/extract.spec.ts
npm.cmd run build
```

### Task 3: OpenAPI contract gate and tracking evidence

**Files:**
- Create: `scripts/check_api_contract.py`
- Modify: `process-plan-agent-ui/package.json`
- Modify: `docs/重构与优化跟踪.md`
- Test: `process-plan-agent-api/tests/test_api_contracts.py` (extend command-level assertions if needed)

**Interfaces:**
- `scripts/check_api_contract.py` imports the FastAPI app, validates the shared status enum sets and required workflow fields in OpenAPI, and exits non-zero with actionable output on drift.
- Frontend script `check:api-contract` invokes the Python checker using the repository runtime when available.

- [x] **Step 1: Write the failing command check**

Add a test fixture/assertion for a missing enum or required field and run the checker against the current app; it must fail before the checker is implemented.

- [x] **Step 2: Run it to verify the expected failure**

```powershell
# Run from the repository root.
.\.runtime\python\python.exe scripts\check_api_contract.py
```

Expected: command is unavailable or exits non-zero before implementation.

- [x] **Step 3: Implement the checker and npm entry**

Use only the standard library plus the existing API environment. Validate project/task/package statuses, blocker capability values, and `workflow_revision` on project and workflow write/request schemas. Add `check:api-contract` to the UI package scripts without changing the default build.

- [x] **Step 4: Run the checker and full frontend verification**

```powershell
# Run from the repository root.
.\.runtime\python\python.exe scripts\check_api_contract.py
cd process-plan-agent-ui
npm.cmd test
npm.cmd run build
```

- [x] **Step 5: Update tracking evidence**

Mark R-009 as `已验证完成` only after the backend suite, frontend suite/build, and contract checker all pass. Record exact commands and preserve Docker/CI as unverified if not available.
