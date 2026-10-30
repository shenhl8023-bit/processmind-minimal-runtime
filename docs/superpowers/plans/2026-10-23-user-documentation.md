# ProcessMind User Documentation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deliver accurate Chinese system introduction and user manual for the current ProcessMind runtime, with discoverable links from the root README.

**Architecture:** Keep product documentation in `docs/` and separate overview copy from executable operating instructions. Treat the existing UI routes, startup scripts, README deployment notes, and current API/UI behavior as the source of truth; add no product code.

**Tech Stack:** Markdown, existing shell/PowerShell startup scripts, Vue route labels, FastAPI contracts.

**Spec:** `docs/superpowers/specs/2026-10-23-user-documentation-design.md`

## Global Constraints

- Write in Chinese and use the current UI labels: `上传资料`、`路线归并`、`规则分析`、`模板映射`、`规则定稿`、`验证生成`.
- Document only currently registered routes and runnable entry points; do not promote stale historical pages to current features.
- State model configuration, published-rule-package, template, and human-review prerequisites where they apply.
- Do not include real API keys, local database contents, or uploaded document contents.
- Keep README startup and developer guidance intact apart from adding clear documentation links.

## Review Focus

- A first-time operator can start the local or Docker deployment and identify the correct browser URL; verify all referenced scripts and ports exist.
- A user can follow the six-step workflow without confusing source documents, reference materials, route snapshots, draft rules, and published rule packages; verify each stage has its prerequisite and completion signal.
- A user can recover from common blocked states (no project, no route, missing model, invalid XML, stale package, failed extraction); verify every stated recovery action maps to a visible UI action or existing script.
- Knowledge-base claims distinguish local evidence, typical guidance, and historical records; verify wording against `KnowledgeView.vue` and its result cards.
- README links resolve to the new documents and the finished Markdown has no whitespace errors; verify with a link/path script and `git diff --check`.

---

### Task 1: Write the System Introduction

**Files:**
- Create: `docs/系统简介.md`
- Reference: `docs/superpowers/specs/2026-10-23-user-documentation-design.md`
- Reference: `process-plan-agent-ui/src/App.vue`, `process-plan-agent-ui/src/router/index.ts`

**Interfaces:**
- Consumes: current route names, workflow labels, system positioning in `README.md` and `app/main.py`.
- Produces: a short overview that can be read independently and links readers to the detailed manual.

- [ ] **Step 1: Write the overview sections**

  Include system positioning, intended users, the six-step workflow, supporting entries, typical outputs, prerequisites, human-review boundary, and a link to `docs/用户使用说明.md`.

- [ ] **Step 2: Check terminology against source**

  Run: `rg -n "上传资料|路线归并|规则分析|模板映射|规则定稿|验证生成|工艺知识库|模型设置" process-plan-agent-ui/src/App.vue process-plan-agent-ui/src/router/index.ts docs/系统简介.md`

  Expected: every workflow label in the overview matches a current UI label and no unregistered route is presented as a main step.

### Task 2: Write the Detailed User Manual

**Files:**
- Create: `docs/用户使用说明.md`
- Reference: `README.md`
- Reference: `process-plan-agent-ui/src/views/*.vue`
- Reference: `process-plan-agent-ui/src/components/{upload,extract,analysis,generate,knowledge,settings,finalize}/*.vue`
- Reference: `process-plan-agent-api/app/routers/*.py`

**Interfaces:**
- Consumes: the current UI actions, file formats, startup commands, data paths, and API-backed state transitions.
- Produces: an operator-facing manual with ordered steps, checklists, recovery actions, and deployment appendix.

- [ ] **Step 1: Document preparation and startup**

  Cover local development, Docker, Windows 7 package entry points, supported versions, default URLs, port behavior, data directories, and model configuration fields. Keep secrets as placeholders.

- [ ] **Step 2: Document project and input management**

  Explain creating/selecting/deleting a task, main process-plan uploads (`pdf/doc/docx/xls/xlsx/json`), optional reference uploads, online-written references, and the condition for entering route merge.

- [ ] **Step 3: Document the six-step workflow**

  Explain extraction/retry, merge candidate confirm/reject/rename and manual route edits; rule-analysis filters, question tree, evidence panels and document preview; Kmsoft XML import/validation and mapping; rule review/edit/confirm/precheck/publish; generated input fields, example values, route tree, JSON copy/download and stale-result handling.

- [ ] **Step 4: Document auxiliary features and boundaries**

  Explain model connection test, local knowledge search with source evidence, typical/history/capability result distinctions, “采纳为依据” where available, and the fact that generated or suggested results require domain review.

- [ ] **Step 5: Document recovery and data safety**

  Add a symptom → likely cause → action table for missing project, no documents, extraction failure, no saved route, no rule package, template validation failure, model/API errors, stale generation result, and port conflict. Include deletion irreversibility and runtime-data backup guidance.

### Task 3: Add Documentation Entry Points

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `docs/系统简介.md` and `docs/用户使用说明.md` from Tasks 1–2.
- Produces: visible links from the project landing README without changing existing startup instructions.

- [ ] **Step 1: Add a “用户文档” block**

  Link the two documents near the top-level project description and state their intended use in one sentence each.

- [ ] **Step 2: Check link targets**

  Run: `test -f docs/系统简介.md && test -f docs/用户使用说明.md`

  Expected: both README targets exist.

### Task 4: Verify the Documentation Set

**Files:**
- Test: shell checks over `README.md`, `docs/系统简介.md`, and `docs/用户使用说明.md`

- [ ] **Step 1: Check Markdown whitespace**

  Run: `git diff --check`

  Expected: no output and exit code 0.

- [ ] **Step 2: Check referenced scripts, URLs, and paths**

  Run: `for f in bootstrap.sh start-api.sh start-ui.sh docker-compose.yml start-win7.bat status-win7.cmd stop-win7.cmd; do test -e "$f" || exit 1; done`

  Expected: exit code 0.

- [ ] **Step 3: Check stale-feature leakage**

  Run: `rg -n "domain-knowledge|/domain-knowledge|知识包管理后台" docs/系统简介.md docs/用户使用说明.md`

  Expected: no output; the current guide must not claim the historical, unregistered domain-knowledge page is available.

- [ ] **Step 4: Check section coverage**

  Run: `rg -n "上传资料|路线归并|规则分析|模板映射|规则定稿|验证生成|工艺知识库|模型设置|常见问题" docs/系统简介.md docs/用户使用说明.md`

  Expected: all current workflow and support entry names, plus troubleshooting, appear in the final docs.
