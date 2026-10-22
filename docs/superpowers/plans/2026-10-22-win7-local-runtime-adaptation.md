# ProcessMind Win7 Local Runtime Adaptation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce a Win7 SP1 x64 offline package that runs the ProcessMind API and prebuilt Vue frontend locally with CPython 3.8.10, without Node.js, CEF, or Qt on the target machine.

**Architecture:** Keep the current Python 3.13.5 and Node 24.x development toolchain. Build the Vue app with the Chromium 109 target, then let a packaged FastAPI process serve `frontend/dist` and `/api` from `127.0.0.1:8000`. A Python-standard-library launcher manages the API process, stores mutable state under `%LOCALAPPDATA%\ProcessMind`, and opens installed Chrome or Edge 109.

**Tech Stack:** FastAPI, Uvicorn, Starlette `StaticFiles`, CPython 3.8.10 x64, Vue 3, Vite, TypeScript, Windows batch files, PowerShell 5.1 packaging, pytest, Vitest.

**Spec:** `docs/superpowers/specs/2026-10-22-win7-local-runtime-adaptation-design.md`

## Global Constraints

- Development and build environment remains Python 3.13.5 and Node.js 24.x; the current Vite toolchain is not downgraded for development.
- Win7 runtime is CPython 3.8.10 x64 with a separate locked dependency set; the target machine does not run Node.js.
- The package does not contain CEF, Qt, or an embedded browser; Chrome 109 or Edge 109 is the acceptance baseline and IE11 is unsupported.
- The API binds only to `127.0.0.1:8000`; production frontend requests use same-origin relative `/api` paths.
- Mutable data, uploads, caches, logs, and PID state live under `%LOCALAPPDATA%\\ProcessMind` unless `PROCESSMIND_RUNTIME_DIR` is set.
- Packaging refuses databases, uploads, `.env` files, real credentials, logs, reparse points, and Node development artifacts.
- Existing development scripts and Docker workflows remain usable; Win7 packaging uses dedicated scripts and does not require Node on the target.

## Review Focus

- A deep Vue history route such as `/extract` must return `index.html` on a direct request and refresh instead of a 404; covered by the static frontend TestClient case in Task 1.
- A missing or unwritable runtime data directory must produce an actionable launcher error without starting a partial service; covered by launcher error tests in Task 4.
- A port occupied by an unrelated process must fail startup without terminating that process; covered by the launcher conflict test in Task 4.
- Python 3.8 must import modules containing modern annotations and asynchronous worker helpers; covered by the compatibility smoke test in Task 2.
- A Win7 package must not contain Node, persistent development data, or real credentials; covered by staging/manifest checks in Task 5.

---

### Task 1: Add production static frontend serving and health endpoints

**Files:**
- Create: `process-plan-agent-api/app/web.py`
- Modify: `process-plan-agent-api/app/core/paths.py`
- Modify: `process-plan-agent-api/app/main.py`
- Test: `process-plan-agent-api/tests/test_static_frontend.py`

**Interfaces:**
- Consumes: existing FastAPI routers and `PROCESSMIND_FRONTEND_DIR`.
- Produces: `create_app(frontend_dir: Optional[Path] = None) -> FastAPI`, `install_frontend(app: FastAPI, frontend_dir: Path) -> None`, and `GET /api/startup-ping` returning `{status: "ok", app: "ProcessMind", kind: "api"}`.

- [ ] **Step 1: Write failing static-serving tests**

  Add tests that create a temporary `index.html` and asset, build an app with `create_app(frontend_dir)`, assert `/` and `/extract` return the same HTML, assert `/assets/app.js` returns the asset, and assert `/api/startup-ping` remains JSON and is not intercepted by the frontend mount.

- [ ] **Step 2: Run the focused test to verify it fails**

  Run: `cd process-plan-agent-api && pytest tests/test_static_frontend.py -q`

  Expected: FAIL because `create_app`, static hosting, and `/api/startup-ping` do not exist.

- [ ] **Step 3: Implement the static frontend boundary**

  Add an `SPAStaticFiles` subclass that falls back to `index.html` only for missing `GET` paths, expose `create_app` for isolated tests, keep the existing global `app`, and enable static hosting only when `PROCESSMIND_FRONTEND_DIR` is set or an explicit directory is passed. Preserve a JSON root response when no production frontend directory is configured so current API tests and development behavior remain stable.

- [ ] **Step 4: Run the focused test to verify it passes**

  Run: `cd process-plan-agent-api && pytest tests/test_static_frontend.py -q`

  Expected: PASS, with API routes taking precedence over the root static mount.

- [ ] **Step 5: Commit**

  ```bash
  git add process-plan-agent-api/app/web.py process-plan-agent-api/app/core/paths.py process-plan-agent-api/app/main.py process-plan-agent-api/tests/test_static_frontend.py
  git commit -m "feat: serve production frontend from FastAPI"
  ```

### Task 2: Make the backend importable and runnable on Python 3.8

**Files:**
- Create: `process-plan-agent-api/app/core/compat.py`
- Modify: `process-plan-agent-api/app/services/extraction_parallel.py`
- Modify: `process-plan-agent-api/app/services/param_project_context.py`
- Modify: `process-plan-agent-api/app/services/knowledge/local_search.py`
- Modify: modern-annotation modules under `process-plan-agent-api/app/` identified by the validator
- Create: `scripts/validate-python38.py`
- Test: `process-plan-agent-api/tests/test_python38_compat.py`

**Interfaces:**
- Consumes: existing synchronous extraction helpers and string normalization behavior.
- Produces: `async run_in_thread(func, *args, **kwargs)`, `remove_suffix(value: str, suffix: str) -> str`, and a validator that parses every backend module with Python 3.8 grammar and reports unsupported runtime APIs.

- [ ] **Step 1: Write failing compatibility tests**

  Pin the suffix behavior for both matching and non-matching strings, run a blocking callable through `run_in_thread`, assert the Python 3.8 AST scan covers all `app/**/*.py`, and assert the validator reports no unapproved `removesuffix` or `asyncio.to_thread` usages after the implementation.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `cd process-plan-agent-api && pytest tests/test_python38_compat.py -q`

  Expected: FAIL because the compatibility module and validator do not exist and current code uses Python 3.9-only helpers.

- [ ] **Step 3: Implement the compatibility layer and audit**

  Implement `run_in_thread` with `loop.run_in_executor` and a `functools.partial`, replace the two `asyncio.to_thread` call sites, replace `str.removesuffix`, and add postponed annotations or `typing` equivalents to every runtime module that currently evaluates PEP 585/604 annotations on import. The validator must use only the standard library, accept an API root argument, parse with `feature_version=(3, 8)`, and fail on the explicitly unsupported API patterns.

- [ ] **Step 4: Run compatibility checks**

  Run: `cd process-plan-agent-api && pytest tests/test_python38_compat.py -q`

  Run: `python3 scripts/validate-python38.py process-plan-agent-api/app`

  Expected: PASS with zero syntax/API findings. Run the existing backend test suite afterward to confirm behavior was preserved.

- [ ] **Step 5: Commit**

  ```bash
  git add process-plan-agent-api/app scripts/validate-python38.py process-plan-agent-api/tests/test_python38_compat.py
  git commit -m "fix: support Python 3.8 backend runtime"
  ```

### Task 3: Build the frontend for Chromium 109 and same-origin production

**Files:**
- Modify: `process-plan-agent-ui/vite.config.ts`
- Modify: `process-plan-agent-ui/index.html`
- Test: `process-plan-agent-ui/tests/win7-build-contract.spec.ts`

**Interfaces:**
- Consumes: the existing Vue router and relative API client.
- Produces: a production `dist/` whose Vite build target is `chrome109`, whose API calls stay relative, and whose index title/icon do not refer to the Vite starter template.

- [ ] **Step 1: Write the failing build-contract test**

  Assert the Vite config contains the `chrome109` build target and the production HTML has the ProcessMind title. Keep the test independent of `dist/` so it runs before a build.

- [ ] **Step 2: Run the focused frontend test to verify it fails**

  Run: `cd process-plan-agent-ui && npm test -- --run tests/win7-build-contract.spec.ts`

  Expected: FAIL because the current config has no Chromium 109 build target and the starter title remains.

- [ ] **Step 3: Implement the build contract**

  Set `build.target: 'chrome109'`, retain the existing Vite proxy for development, keep `VITE_API_BASE_URL` optional so production uses relative `/api`, and replace starter metadata with ProcessMind metadata without introducing a new runtime dependency.

- [ ] **Step 4: Verify build output**

  Run: `cd process-plan-agent-ui && npm test -- --run tests/win7-build-contract.spec.ts && npm run build`

  Expected: PASS and a `dist/index.html` with hashed assets and no unresolved module imports.

- [ ] **Step 5: Commit**

  ```bash
  git add process-plan-agent-ui/vite.config.ts process-plan-agent-ui/index.html process-plan-agent-ui/tests/win7-build-contract.spec.ts docs/superpowers/plans/2026-10-22-win7-local-runtime-adaptation.md
  git commit -m "build: target Chromium 109 for Win7 frontend"
  ```

### Task 4: Add a Python-standard-library Win7 launcher and batch entrypoints

**Files:**
- Create: `scripts/win7_launcher.py`
- Create: `start-win7.cmd`
- Create: `stop-win7.cmd`
- Create: `status-win7.cmd`
- Test: `process-plan-agent-api/tests/test_win7_launcher.py`

**Interfaces:**
- Consumes: the packaged `.runtime/python/python.exe`, API directory, frontend directory, and Task 1 health endpoint.
- Produces: `resolve_runtime_dir(env) -> Path`, `find_browser(env) -> Optional[Path]`, `check_port(host, port) -> int`, `health(url, timeout) -> bool`, and CLI commands `start`, `stop`, `status`.

- [ ] **Step 1: Write failing launcher tests**

  Test runtime-directory precedence (`PROCESSMIND_RUNTIME_DIR`, then `LOCALAPPDATA`, then `TEMP`), state round-tripping, valid port checks, browser candidate selection using temporary fake paths, and refusal to stop a PID whose recorded command line does not contain the package API command.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Run: `cd process-plan-agent-api && pytest tests/test_win7_launcher.py -q`

  Expected: FAIL because the launcher module and batch entrypoints do not exist.

- [ ] **Step 3: Implement launcher behavior**

  Use only Python 3.8 standard-library modules. Start Uvicorn with `--host 127.0.0.1 --port 8000`, set `PROCESSMIND_DATA_DIR`, `PROCESSMIND_FRONTEND_DIR`, and `PROCESSMIND_RUNTIME_DIR` before spawning, capture logs, write an atomic JSON state file, poll `/api/startup-ping`, and use WMIC only for Windows process identity checks. Browser discovery tries installed Chrome and Edge paths, then `start`/`os.startfile` fallback; missing browser prints the URL while leaving the API alive. Stop is idempotent and never kills an unrelated process.

- [ ] **Step 4: Verify launcher behavior**

  Run: `cd process-plan-agent-api && pytest tests/test_win7_launcher.py -q`

  Run: `python3 scripts/win7_launcher.py --help`

  Expected: PASS and a standard-library-only CLI help response.

- [ ] **Step 5: Commit**

  ```bash
  git add scripts/win7_launcher.py start-win7.cmd stop-win7.cmd status-win7.cmd process-plan-agent-api/tests/test_win7_launcher.py
  git commit -m "feat: add Win7 local process launcher"
  ```

### Task 5: Create the Win7 dependency lock, offline staging, and manifest

**Files:**
- Create: `requirements-win7-py38.txt`
- Create: `scripts/build-win7-runtime.ps1`
- Create: `scripts/pack-win7-windows.ps1`
- Create: `scripts/pack-win7-windows.cmd`
- Create: `scripts/stage-win7-package.ps1`
- Create: `process-plan-agent-api/tests/test_win7_package_contract.py`

**Interfaces:**
- Consumes: the frontend `dist/`, CPython 3.8.10 x64 source directory or archive, the Python 3.8 lock, and existing offline safety checks.
- Produces: `dist-win7/processmind-win7-windows-YYYYMMDD.zip`, `manifest.json`, `SHA256SUMS.txt`, and a staging tree without Node artifacts or mutable project data.

- [x] **Step 1: Write failing package-contract tests**

  Assert the lock file declares Python 3.8-compatible versions, the pack script requires `dist/` and a Python 3.8 runtime, the staging allowlist includes the new batch files and frontend output, and the package contract rejects `node_modules`, `.runtime/node`, database files, uploads, and `.env` values.

- [x] **Step 2: Run the focused tests to verify they fail**

  Run: `cd process-plan-agent-api && pytest tests/test_win7_package_contract.py -q`

  Expected: FAIL because the Win7 lock, scripts, and staging rules do not exist.

- [x] **Step 3: Implement the Win7 lock and runtime builder**

  Pin a separately verified Python 3.8 dependency set with Windows x64 wheels, exclude development-only Node tooling, and make `build-win7-runtime.ps1` install from a local wheelhouse with `--no-index --find-links`. It must verify `python.exe --version`, import FastAPI/Uvicorn/SQLAlchemy/PyMuPDF/python-docx/openpyxl, run the Python 3.8 validator, and fail before staging on any mismatch.

- [x] **Step 4: Implement Win7 staging, manifest, and hashes**

  Stage `process-plan-agent-api`, `process-plan-agent-ui/dist`, the Python runtime, Win7 scripts, examples, and required knowledge/config files. Keep this allowlist in the dedicated `stage-win7-package.ps1` so the existing Node-capable staging script remains compatible with development packages. Explicitly reject Node and mutable data, write target/version/browser metadata, and generate SHA-256 entries for every staged file.

- [x] **Step 5: Run package-contract and staging checks**

  Run: `cd process-plan-agent-api && pytest tests/test_win7_package_contract.py -q`

  Run on Windows PowerShell 5.1: `scripts\\pack-win7-windows.cmd -PythonRuntime "C:\\path\\cpython-3.8.10-embed-amd64" -Wheelhouse "C:\\path\\wheelhouse"`

  Expected: PASS, with a ZIP that contains no `node_modules`, `.runtime\\node`, database, upload, log, `.env`, or credential files.

- [x] **Step 6: Commit**

  ```bash
  git add requirements-win7-py38.txt scripts/build-win7-runtime.ps1 scripts/pack-win7-windows.ps1 scripts/pack-win7-windows.cmd scripts/stage-win7-package.ps1 process-plan-agent-api/tests/test_win7_package_contract.py
  git commit -m "build: package a Python 3.8 Win7 runtime"
  ```

### Task 6: Update documentation and run the complete verification matrix

**Files:**
- Modify: `README.md`
- Create: `scripts/verify-win7-package.py`
- Test: `process-plan-agent-api/tests/test_win7_delivery_docs.py`

**Interfaces:**
- Consumes: the completed launcher, build, staging, and manifest contracts.
- Produces: documented Win7 install/start/stop/recovery steps and a standard-library verifier that checks manifest hashes and required package paths.

- [ ] **Step 1: Write failing documentation/verifier tests**

  Assert README describes CPython 3.8.10, no target Node, Chrome/Edge 109, `start-win7.cmd`, `stop-win7.cmd`, `%LOCALAPPDATA%\\ProcessMind`, and the IE11 boundary. Assert the verifier rejects a missing required file and a modified hash.

- [ ] **Step 2: Run the focused tests to verify they fail**

  Expected: FAIL because the documentation and verifier do not yet describe or validate the new package.

- [ ] **Step 3: Implement documentation and verifier**

  Replace the current Win7 section's Node 20 requirement with the new static frontend flow, document the prerequisite browser and external-service boundary, and implement `verify-win7-package.py` using only the standard library for manifest paths, SHA-256 values, runtime version, and forbidden artifacts.

- [ ] **Step 4: Run the complete local verification**

  Run: `python3 scripts/validate-python38.py process-plan-agent-api/app`

  Run: `cd process-plan-agent-api && pytest -q`

  Run: `cd process-plan-agent-ui && npm test -- --run && npm run build`

  Run: `python3 scripts/stage3_smoke_stdlib.py`

  Expected: all existing backend/frontend tests pass, Python 3.8 validation is clean, and the production frontend builds successfully.

- [ ] **Step 5: Commit**

  ```bash
  git add README.md scripts/verify-win7-package.py process-plan-agent-api/tests/test_win7_delivery_docs.py
  git commit -m "docs: document Win7 package verification"
  ```

- [ ] **Step 6: Record target-machine limitations**

  Run the package verifier on the produced ZIP, then record that Win7 SP1 x64 and Chrome/Edge 109 acceptance requires an actual target VM or machine; do not claim the matrix passed from macOS/Linux-only checks.
