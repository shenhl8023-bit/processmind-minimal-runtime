# R-002 参数问答策略交付一致性 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让本地、Docker 和离线包从同一共享文件加载参数问答策略，并在正式环境配置错误时启动失败。

**Architecture:** 将策略文件放在 `docs/配置模板`，后端路径由 `app.core.paths` 统一定义，前端构建时从仓库共享文件导入。后端加载器负责结构校验和显式测试注入，API lifespan 在初始化数据库前校验配置；交付测试锁定 Docker COPY、旧路径删除和离线 staging 契约。

**Tech Stack:** Python 3.11、FastAPI lifespan、pytest、Vue 3/Vite/TypeScript、PowerShell 离线 staging。

## Global Constraints

- 不引入新依赖。
- 不保留前端源码目录的兼容读取路径或静默硬编码回退。
- 不改变现有问答策略语义、V2/V1 规则包协议和数据库结构。
- 测试配置必须通过显式路径注入，不能依赖前端源码目录。

---

### Task 1: 建立共享策略文件和加载契约

**Files:**
- Create: `docs/配置模板/第五步参数问答策略.json`
- Delete: `process-plan-agent-ui/src/config/paramQuestionStrategy.json`
- Modify: `process-plan-agent-api/app/core/paths.py`
- Modify: `process-plan-agent-api/app/services/param_question_strategy.py`
- Test: `process-plan-agent-api/tests/test_param_question_strategy.py`

**Interfaces:**
- Produces `PARAM_QUESTION_STRATEGY_PATH`, `ParamQuestionStrategyError`, `load_param_question_strategy(path: Path | None = None, *, force: bool = False) -> dict[str, object]`, and `validate_param_question_strategy(payload: object, source: Path) -> dict[str, object]`.

- [x] **Step 1: Write failing tests** for valid shared config, explicit temporary path injection, missing file, malformed JSON, and invalid top-level shape.
- [x] **Step 2: Run `..\.runtime\python\python.exe -m pytest tests/test_param_question_strategy.py -q` and confirm the new imports/path behavior fail.**
- [x] **Step 3: Move the JSON to `docs/配置模板`, add `version: "1.0.0"`, define the shared path in `app.core.paths`, and implement strict validation with clear `ParamQuestionStrategyError` messages.**
- [x] **Step 4: Remove the empty-dict and hardcoded priority/terminal fallbacks so existing strategy helpers use the validated shared payload; retain only question-goal/tree metadata and operation hints that are outside this delivery strategy file.**
- [x] **Step 5: Re-run the focused strategy tests and confirm they pass.**

### Task 2: Wire startup, frontend import, and container delivery

**Files:**
- Modify: `process-plan-agent-api/app/main.py`
- Modify: `process-plan-agent-ui/src/config/paramQuestionStrategy.ts`
- Modify: `Dockerfile.api`
- Modify: `Dockerfile.web`
- Modify: `process-plan-agent-api/tests/test_delivery_config.py`
- Modify: `process-plan-agent-api/tests/test_param_question_strategy.py`

**Interfaces:**
- Consumes `load_param_question_strategy` and `PARAM_QUESTION_STRATEGY_PATH` from Task 1.
- Produces a startup lifespan that validates the strategy before `init_db`, a frontend `PARAM_QUESTION_STRATEGY_VERSION`, and explicit Docker copies of the shared file.

- [x] **Step 1: Add a failing lifecycle test showing invalid strategy configuration aborts startup before database initialization.**
- [x] **Step 2: Run the focused lifecycle test and confirm it fails because startup does not validate the strategy.**
- [x] **Step 3: Call `load_param_question_strategy(force=True)` at the beginning of `lifespan`, change the frontend import to `../../../docs/配置模板/第五步参数问答策略.json`, export the version, and add explicit API/Web Docker COPY lines.**
- [x] **Step 4: Extend delivery assertions for the shared file, Docker COPY lines, and absence of the old UI JSON path; run the focused backend delivery and strategy tests.**

### Task 3: Verify offline and full application behavior

**Files:**
- Modify: `process-plan-agent-api/tests/test_offline_package_safety.py`
- Modify: `docs/重构与优化跟踪.md`

**Interfaces:**
- Consumes the shared file and container wiring from Tasks 1-2.
- Produces updated R-002 status, acceptance checklist, verification results, and residual risk notes.

- [x] **Step 1: Update the staging test to assert `docs/配置模板/第五步参数问答策略.json` is present in an offline stage.**
- [x] **Step 2: Run backend focused tests, the full backend suite, frontend tests, frontend production build, delivery/offline tests, and `git diff --check`.**
- [x] **Step 3: Read all command output, record exact counts and the pre-existing TestClient/httpx warning in the tracking document, and leave unrelated user files untouched.**
