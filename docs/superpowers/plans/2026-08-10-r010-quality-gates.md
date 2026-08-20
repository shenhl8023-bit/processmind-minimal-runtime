# R-010 Quality Gates Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. This repository's instructions prohibit automatic commits, so every task ends with verification and diff review instead of a commit.

**Goal:** Establish repeatable GitHub Actions and local quality gates for backend compatibility, Ruff, rule-package coverage, frontend validation, Docker delivery, Windows offline delivery, and the two critical release smoke paths.

**Architecture:** Keep one GitHub Actions workflow with independent jobs so every failure has a clear boundary. Reuse pytest, npm, Docker Compose, and the existing Windows bootstrap/pack/start scripts; centralize only Python tool configuration in `process-plan-agent-api/pyproject.toml`. Preserve all ProcessMind V2, KmAI V1, database, and API behavior.

**Tech Stack:** GitHub Actions; Python 3.11/3.13, pytest, pytest-cov, Ruff, FastAPI TestClient/httpx2; Node.js 20, Vitest, vue-tsc, Vite; Docker Compose; Windows PowerShell.

## Global Constraints

- Do not modify database schema, API URLs, ProcessMind V2 JSON, KmAI V1 JSON, ZIP structure, or release lifecycle semantics.
- Do not auto-commit, push, publish images, or publish offline archives.
- Ruff starts with only `E9,F63,F7,F82`; broader lint modernization is outside R-010.
- Rule-package statement coverage must be at least `85%` without omitting production modules.
- CI must use Python `3.11` and `3.13`, Node.js `20`, and isolated temporary runtime data.
- Docker and Windows cleanup must run after failures and stop only resources created by the current job.
- Preserve all unrelated untracked workspace files.

---

### Task 1: Backend quality-tool configuration

**Files:**
- Create: `process-plan-agent-api/pyproject.toml`
- Modify: `process-plan-agent-api/requirements-dev.txt`

**Interfaces:**
- Produces `delivery_smoke` as a registered pytest marker.
- Produces a Ruff gate over `E9,F63,F7,F82` with Python 3.11 syntax as the minimum target.
- Produces a coverage configuration for `app.services.rule_packages` with `fail_under = 85`.
- Keeps production `httpx` in `requirements.txt`; adds `httpx2` only to development/test dependencies for FastAPI TestClient.

- [x] **Step 1: Verify the intended Ruff command is red before configuration**

Run from the API directory:

```powershell
..\.runtime\python\python.exe -m ruff check app tests ..\scripts
```

Expected: FAIL because Ruff's unrestricted current defaults report the historical backlog instead of the approved R-010 safety baseline.

- [x] **Step 2: Pin the development dependencies**

Replace `requirements-dev.txt` with:

```text
-r requirements.txt
httpx2==2.10.0
pytest==9.1.1
pytest-asyncio==1.4.0
pytest-cov==7.1.0
ruff==0.16.2
```

- [x] **Step 3: Add the shared pytest, Ruff, and coverage configuration**

Create `pyproject.toml` with:

```toml
[tool.pytest.ini_options]
addopts = ["--strict-config", "--strict-markers"]
asyncio_default_fixture_loop_scope = "function"
testpaths = ["tests"]
markers = [
  "delivery_smoke: release-path smoke tests used by the R-010 delivery gate",
]

[tool.ruff]
target-version = "py311"

[tool.ruff.lint]
select = ["E9", "F63", "F7", "F82"]

[tool.coverage.run]
relative_files = true
source = ["app.services.rule_packages"]

[tool.coverage.report]
fail_under = 85
show_missing = true

[tool.coverage.xml]
output = "coverage.xml"
```

- [x] **Step 4: Verify the configured static gate is green**

```powershell
..\.runtime\python\python.exe -m ruff check app tests ..\scripts
..\.runtime\python\python.exe -m compileall -q app tests ..\scripts
```

Expected: both commands exit `0`.

- [x] **Step 5: Verify TestClient uses the current adapter without the prior deprecation warning**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_rule_package_api.py::test_retired_mapping_api_is_not_registered
```

Expected: `1 passed` and no `StarletteDeprecationWarning` asking to install `httpx2`.

---

### Task 2: Delivery smoke coverage

**Files:**
- Modify: `process-plan-agent-api/tests/test_rule_package_api.py`
- Modify: `process-plan-agent-api/tests/test_generate_v2_production.py`

**Interfaces:**
- Produces three tests selected by `pytest -m delivery_smoke`.
- The main journey exercises `/api/documents/upload`, `/api/extract/finalized-rule-packages`, and `/api/generate/` against one isolated SQLite project.
- The drift journey preserves stable `409` code `published_rule_package_changed` and verifies the old package becomes `archived` without a generated route.

- [x] **Step 1: Verify the delivery selector is red**

```powershell
..\.runtime\python\python.exe -m pytest -q -m delivery_smoke
```

Expected: non-zero exit because no tests are selected before the R-010 smoke markers exist.

- [x] **Step 2: Add the upload-to-publish-to-generate HTTP journey**

Add this test to `test_rule_package_api.py` after `_v2_save_payload` and mark it `delivery_smoke`:

```python
@pytest.mark.delivery_smoke
def test_uploaded_document_can_publish_v2_and_generate_route(
    rule_package_v2_payload,
    isolated_rule_package_db,
):
    uploaded = client.post(
        "/api/documents/upload",
        data={"project_id": "12"},
        files={"files": ("release-smoke.json", b'{"operations": []}', "application/json")},
    )
    assert uploaded.status_code == 200, uploaded.text
    assert len(uploaded.json()) == 1

    async def restore_reviewed_route():
        async with isolated_rule_package_db() as session:
            route = NormalizedRouteVersion(
                project_id=12,
                version=2,
                source_signature="release-smoke-reviewed",
                route_json="[]",
            )
            session.add(route)
            await session.flush()
            route_id = route.id
            project = await session.get(Project, 12)
            project.status = "ROUTE_SET_READY"
            await session.commit()
            return route_id

    route_id = asyncio.run(restore_reviewed_route())
    rule_package_v2_payload["manifest"]["route_version_id"] = route_id

    published = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"

    generated = client.post(
        "/api/generate/",
        json={
            "project_id": 12,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert generated.status_code == 200, generated.text
    assert generated.json()["output_mode"] == "finalized_rule_package_v2"
    assert generated.json()["selected_process_ids"] == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
```

The upload endpoint correctly invalidates the fixture's old downstream route. `restore_reviewed_route()` is deterministic prerequisite setup for the already-reviewed route stage; publishing and generation themselves must still pass through their real HTTP routes and database transactions.

- [x] **Step 3: Mark the two execution boundary scenarios**

Add `@pytest.mark.delivery_smoke` to:

```python
def test_generate_uses_published_v2_plan_route(generation_context):
```

and:

```python
def test_generate_archives_source_drifted_v2_before_planning(generation_context):
```

The first protects the existing production generation path; the second protects the condition-source drift rejection, archived status, stable `409` payload, and absence of generation side effects.

- [x] **Step 4: Run the focused gate**

```powershell
..\.runtime\python\python.exe -m pytest -q -m delivery_smoke
```

Expected: `3 passed`.

- [x] **Step 5: Run the affected modules**

```powershell
..\.runtime\python\python.exe -m pytest -q tests/test_rule_package_api.py tests/test_generate_v2_production.py
```

Expected: all tests pass with no TestClient migration deprecation warning.

---

### Task 2A: Verification-discovered resource cleanup

**Files:**
- Modify: `scripts/maintain_database.py`
- Modify: `process-plan-agent-api/tests/test_database_maintenance.py`
- Modify: `process-plan-agent-api/tests/conftest.py`
- Create: `process-plan-agent-api/tests/test_test_environment.py`
- Modify: `process-plan-agent-api/pyproject.toml`

**Interfaces:**
- Database maintenance commands explicitly close every `sqlite3` connection instead of relying on transaction context managers.
- Pytest explicitly removes its isolated data root during `pytest_unconfigure` and fixes the asyncio fixture loop scope.

- [x] **Step 1: Reproduce the SQLite connection leak**

Add `test_cli_apply_closes_all_database_connections` and run the focused database-maintenance module with resource warnings enabled. Before the fix it reports two unclosed database connections.

- [x] **Step 2: Close maintenance and test-read connections explicitly**

Wrap `sqlite3.connect()` with `contextlib.closing(...)` in the maintenance script and affected database-maintenance tests. The focused module then reports `6 passed` without unclosed-database warnings.

- [x] **Step 3: Reproduce and fix pytest temporary-root cleanup**

Add `test_pytest_unconfigure_cleans_test_data_root`. It first fails because `pytest_unconfigure` does not exist, then passes after the hook calls `_TEST_DATA_ROOT.cleanup()`. Set `asyncio_default_fixture_loop_scope = "function"` to remove the pytest-asyncio configuration warning.

- [x] **Step 4: Confirm clean full-suite output**

Run the full coverage command with `-W default`. Actual result: `388 passed, 1 skipped`, `86.54%` rule-package coverage, and no warnings.

---

### Task 3: GitHub Actions quality and delivery workflow

**Files:**
- Create: `.github/workflows/quality-gates.yml`

**Interfaces:**
- Produces required-check candidates `backend-tests`, `backend-quality`, `delivery-smoke`, `frontend`, `docker-delivery`, and `windows-offline-delivery`.
- Runs on pull requests, pushes to `main` and `codex/**`, and manual dispatch.
- Uploads only `coverage.xml`; it does not publish images or the large offline ZIP.

- [x] **Step 1: Create the workflow**

Create `.github/workflows/quality-gates.yml` with this structure:

```yaml
name: quality-gates

on:
  pull_request:
  push:
    branches:
      - main
      - "codex/**"
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: quality-${{ github.workflow }}-${{ github.ref }}
  cancel-in-progress: true

jobs:
  backend-tests:
    name: backend-tests (Python ${{ matrix.python-version }})
    runs-on: ubuntu-latest
    strategy:
      fail-fast: false
      matrix:
        python-version: ["3.11", "3.13"]
    defaults:
      run:
        working-directory: process-plan-agent-api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: ${{ matrix.python-version }}
          cache: pip
          cache-dependency-path: |
            process-plan-agent-api/requirements.txt
            process-plan-agent-api/requirements-dev.txt
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q
      - run: python -m compileall -q app tests ../scripts

  backend-quality:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: process-plan-agent-api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: |
            process-plan-agent-api/requirements.txt
            process-plan-agent-api/requirements-dev.txt
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m ruff check app tests ../scripts
      - run: python -m pytest -q --cov=app.services.rule_packages --cov-report=term --cov-report=xml
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: rule-package-coverage
          path: process-plan-agent-api/coverage.xml
          if-no-files-found: ignore

  delivery-smoke:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: process-plan-agent-api
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: |
            process-plan-agent-api/requirements.txt
            process-plan-agent-api/requirements-dev.txt
      - run: python -m pip install --upgrade pip
      - run: python -m pip install -r requirements-dev.txt
      - run: python -m pytest -q -m delivery_smoke

  frontend:
    runs-on: ubuntu-latest
    defaults:
      run:
        working-directory: process-plan-agent-ui
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"
          cache: pip
          cache-dependency-path: process-plan-agent-api/requirements.txt
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: process-plan-agent-ui/package-lock.json
      - run: python -m pip install -r ../process-plan-agent-api/requirements.txt
      - run: npm ci
      - run: npm run check:api-contract
      - run: npm test
      - run: npm run build

  docker-delivery:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Build images
        run: docker compose build api web
      - name: Start delivery stack
        run: docker compose up -d --wait --wait-timeout 180
      - name: Verify images, shared policy, and HTTP
        shell: bash
        run: |
          docker compose exec -T api python -c "from pathlib import Path; required = [Path('/app/process-plan-agent-api/knowledge'), Path('/app/process-plan-agent-api/prompt_parts'), Path('/app/docs/配置模板/第五步参数问答策略.json')]; missing = [str(path) for path in required if not path.exists()]; assert not missing, missing"
          curl --fail --retry 10 --retry-delay 2 http://127.0.0.1:8080/
          curl --fail --retry 10 --retry-delay 2 http://127.0.0.1:8080/api/projects/
      - name: Show container logs
        if: failure()
        run: docker compose logs --no-color
      - name: Stop delivery stack
        if: always()
        run: docker compose down -v --remove-orphans

  windows-offline-delivery:
    runs-on: windows-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with:
          node-version: "20"
          cache: npm
          cache-dependency-path: process-plan-agent-ui/package-lock.json
      - name: Build, scan, unpack, and start the offline package
        shell: pwsh
        env:
          PROCESSMIND_NO_PAUSE: "1"
          PROCESSMIND_NO_BROWSER: "1"
        run: |
          $output = Join-Path $env:RUNNER_TEMP 'processmind-offline-output'
          $ready = Join-Path $env:RUNNER_TEMP 'processmind-offline-ready'
          .\bootstrap-windows.cmd
          if ($LASTEXITCODE -ne 0) { throw 'bootstrap-windows.cmd failed' }
          & .\scripts\pack-offline-windows.ps1 -OutputDir $output
          $archives = @(Get-ChildItem -LiteralPath $output -Filter 'processmind-offline-windows-*.zip')
          if ($archives.Count -ne 1) { throw "Expected one offline archive, found $($archives.Count)." }
          $zip = $archives[0]
          Expand-Archive -LiteralPath $zip.FullName -DestinationPath $ready -Force
          $env:PROCESSMIND_OFFLINE = '1'
          Push-Location $ready
          try {
            & .\scripts\manage-windows.ps1 -Action Start
            Invoke-WebRequest -UseBasicParsing http://127.0.0.1:8000/ | Out-Null
            Invoke-WebRequest -UseBasicParsing http://127.0.0.1:5173/ | Out-Null
          }
          finally {
            & .\scripts\manage-windows.ps1 -Action Stop
            Pop-Location
          }
```

- [x] **Step 2: Parse and inspect the workflow locally**

Run:

```powershell
@'
from pathlib import Path
import yaml

path = Path('.github/workflows/quality-gates.yml')
workflow = yaml.safe_load(path.read_text(encoding='utf-8'))
jobs = workflow['jobs']
expected = {
    'backend-tests',
    'backend-quality',
    'delivery-smoke',
    'frontend',
    'docker-delivery',
    'windows-offline-delivery',
}
assert expected == set(jobs), set(jobs)
print('workflow jobs:', ', '.join(sorted(jobs)))
'@ | .\.runtime\python\python.exe -
```

Expected: YAML parses and prints exactly the six job identifiers.

- [x] **Step 3: Review resource cleanup paths**

Confirm the Docker job uses `if: always()` for `docker compose down`, and the Windows job stops the unpacked package in `finally`. Do not add `continue-on-error` to any gate.

---

### Task 4: Local documentation and R-010 tracking

**Files:**
- Modify: `README.md`
- Modify: `docs/重构与优化跟踪.md`
- Modify: `docs/superpowers/plans/2026-08-10-r010-quality-gates.md`

**Interfaces:**
- Produces copy-pasteable local commands matching CI.
- Records R-010 as “已建立，本地已验证，CI/Docker 待实测” until GitHub jobs actually run.
- Records the TestClient migration conclusion: `httpx2` is a test-only dependency; production `httpx` is retained.

- [x] **Step 1: Add a README quality-gates section**

Document these commands:

```powershell
cd process-plan-agent-api
..\.runtime\python\python.exe -m pip install -r requirements-dev.txt
..\.runtime\python\python.exe -m ruff check app tests ..\scripts
..\.runtime\python\python.exe -m pytest -q
..\.runtime\python\python.exe -m pytest -q -m delivery_smoke
..\.runtime\python\python.exe -m pytest -q --cov=app.services.rule_packages --cov-report=term --cov-report=xml

cd ..\process-plan-agent-ui
npm.cmd ci
npm.cmd run check:api-contract
npm.cmd test
npm.cmd run build
```

Also document `docker compose build api web` plus `docker compose up -d --wait`, and the Windows `bootstrap-windows.cmd` / `pack-offline-windows.ps1` delivery entry. State that the workflow is `.github/workflows/quality-gates.yml`.

- [x] **Step 2: Update the tracking summary and R-010 detail**

Replace “未建立” with “已建立，本地已验证，CI/Docker 待实测”. Add completed scope, exact local evidence from Task 5, preserved boundaries, and checked/unchecked completion boxes. Do not claim Python 3.11, GitHub Actions, Docker, or clean-machine offline startup passed locally.

- [x] **Step 3: Record actual plan execution**

Change each completed checkbox in this plan from `[ ]` to `[x]` only after its command has actually run and its output has been read.

---

### Task 5: Final verification and workspace audit

**Files:**
- Verify all task files; do not create new artifacts outside ignored coverage/build/temp directories.

- [x] **Step 1: Run backend static and smoke gates**

```powershell
cd process-plan-agent-api
..\.runtime\python\python.exe -m ruff check app tests ..\scripts
..\.runtime\python\python.exe -m compileall -q app tests ..\scripts
..\.runtime\python\python.exe -m pytest -q -m delivery_smoke
```

- [x] **Step 2: Run backend coverage/full regression**

```powershell
..\.runtime\python\python.exe -m pytest -q --cov=app.services.rule_packages --cov-report=term --cov-report=xml
```

Expected: all backend tests pass and total rule-package coverage is at least `85%`.

Actual: `388 passed, 1 skipped`; total rule-package coverage `86.54%`; no warnings.

- [x] **Step 3: Run frontend gates**

```powershell
cd ..\process-plan-agent-ui
npm.cmd run check:api-contract
npm.cmd test
npm.cmd run build
```

- [x] **Step 4: Run the available Windows staging safety test**

```powershell
cd ..\process-plan-agent-api
..\.runtime\python\python.exe -m pytest -q tests/test_offline_package_safety.py tests/test_delivery_config.py
```

Run the packer against a uniquely named system temporary directory and inspect the resulting ZIP. Use `-SkipNodePrepare` because this local check validates staging, scanning, and archive assembly; the GitHub Windows job validates bundled Node and clean-package startup.

```powershell
$r010Temp = Join-Path ([IO.Path]::GetTempPath()) ("processmind-r010-" + [guid]::NewGuid().ToString("N"))
New-Item -ItemType Directory -LiteralPath $r010Temp | Out-Null
try {
  & ..\scripts\pack-offline-windows.ps1 -OutputDir $r010Temp -SkipNodePrepare
  $archives = @(Get-ChildItem -LiteralPath $r010Temp -Filter 'processmind-offline-windows-*.zip')
  if ($archives.Count -ne 1) { throw "Expected one offline archive, found $($archives.Count)." }
  $archive = $archives[0]
  if ($archive.Length -le 0) { throw 'Offline archive was not created.' }
  Write-Output "Verified offline archive: $($archive.FullName)"
}
finally {
  $resolvedTemp = [IO.Path]::GetFullPath($r010Temp)
  $systemTemp = [IO.Path]::GetFullPath([IO.Path]::GetTempPath())
  if ($resolvedTemp.StartsWith($systemTemp, [StringComparison]::OrdinalIgnoreCase) -and
      (Split-Path -Leaf $resolvedTemp) -like 'processmind-r010-*') {
    Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
  }
}
```

Do not touch a user `dist-offline` directory.

- [x] **Step 5: Validate workflow structure and repository diff**

```powershell
cd ..
git diff --check
git status --short
git diff --stat
```

Inspect all task-related diffs, confirm the eight pre-existing unrelated untracked files remain untouched, and report Docker/Python 3.11/GitHub Actions as unverified.

Actual: workflow structure contains exactly six jobs without `continue-on-error`; `git diff --check` passes; coverage XML and frontend build output remain ignored; the pre-existing unrelated untracked design/image files remain untouched.

No commit or push is performed unless the user explicitly requests it in a later turn.
