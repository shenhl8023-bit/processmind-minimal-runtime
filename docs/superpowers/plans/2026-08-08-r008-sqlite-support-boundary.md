# R-008 SQLite Support Boundary Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reject every unsupported `DATABASE_URL` before SQLAlchemy creates an engine, while preserving current SQLite startup and migration behavior.

**Architecture:** `app.database` remains the engine/session composition root. A pure validator parses the URL with SQLAlchemy, accepts only the installed async SQLite driver, and raises a credential-safe configuration error before `create_async_engine()` can import an unsupported driver. Deployment documentation mirrors that executable contract.

**Tech Stack:** Python 3.11+, SQLAlchemy async engine, aiosqlite, pytest, FastAPI startup lifecycle, Docker Compose.

## Global Constraints

- The only supported driver is exactly `sqlite+aiosqlite`.
- Validation must run before `create_async_engine()`.
- Configuration errors must never echo usernames, passwords, hosts, database names, or query parameters.
- Keep the existing default database path, WAL, foreign-key, timeout, session, ORM metadata, and versioned migration behavior unchanged.
- Do not add another database driver or change ProcessMind V2 / KmAI V1 contracts.
- Do not commit, push, rebase, reset, or amend unless the user explicitly requests it.

---

### Task 1: Executable Database URL Boundary

**Files:**
- Modify: `process-plan-agent-api/tests/test_db_startup_safety.py`
- Modify: `process-plan-agent-api/app/database.py`

**Interfaces:**
- Consumes: `sqlalchemy.engine.make_url(database_url: str)` and the `DATABASE_URL` environment variable.
- Produces: `DatabaseConfigurationError(RuntimeError)` and `validate_database_url(database_url: str) -> str`.

- [ ] **Step 1: Write the failing subprocess regression test**

Add imports for `os`, `Path`, `subprocess`, and `sys`, then add:

```python
API_ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize(
    ("database_url", "expected_detail", "secret"),
    [
        (
            "postgresql+asyncpg://user:super-secret@localhost/processmind",
            "received driver 'postgresql+asyncpg'",
            "super-secret",
        ),
        ("sqlite:///runtime/process_mind.db", "received driver 'sqlite'", None),
        ("not-a-database-url", "DATABASE_URL is invalid", None),
    ],
)
def test_database_module_rejects_unsupported_url_before_engine_creation(
    database_url,
    expected_detail,
    secret,
):
    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    result = subprocess.run(
        [sys.executable, "-c", "import app.database"],
        cwd=API_ROOT,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    assert result.returncode != 0
    assert "ProcessMind currently supports SQLite only" in result.stderr
    assert "sqlite+aiosqlite" in result.stderr
    assert expected_detail in result.stderr
    assert "ModuleNotFoundError" not in result.stderr
    if secret:
        assert secret not in result.stderr
```

- [ ] **Step 2: Run the regression test and verify RED**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_db_startup_safety.py -k "rejects_unsupported_url" -q
```

Expected: all three cases fail because current code emits SQLAlchemy or driver errors instead of the support-boundary message.

- [ ] **Step 3: Implement the minimal pre-engine validation**

In `app/database.py`, import `make_url` and `ArgumentError`, then add:

```python
SUPPORTED_DATABASE_DRIVER = "sqlite+aiosqlite"


class DatabaseConfigurationError(RuntimeError):
    """The configured database cannot be used by this ProcessMind build."""


def validate_database_url(database_url: str) -> str:
    try:
        driver_name = make_url(database_url).drivername
    except (ArgumentError, TypeError, ValueError) as exc:
        raise DatabaseConfigurationError(
            "DATABASE_URL is invalid. ProcessMind currently supports SQLite only; "
            "remove DATABASE_URL to use the default database or use "
            "'sqlite+aiosqlite:///path/to/process_mind.db'."
        ) from exc
    if driver_name != SUPPORTED_DATABASE_DRIVER:
        raise DatabaseConfigurationError(
            f"Unsupported DATABASE_URL: received driver '{driver_name}'. "
            "ProcessMind currently supports SQLite only via 'sqlite+aiosqlite'; "
            "remove DATABASE_URL to use the default database or set "
            "'sqlite+aiosqlite:///path/to/process_mind.db'."
        )
    return database_url
```

Call it while assigning `DATABASE_URL`, before engine creation.

- [ ] **Step 4: Run the focused test and verify GREEN**

Run the Step 2 command again. Expected: `3 passed` and no unsupported driver import.

- [ ] **Step 5: Run the complete startup safety module**

Run `..\.runtime\python\python.exe -m pytest tests/test_db_startup_safety.py -q`. Expected: all startup, migration, rollback, SQLite pragma, and copied-history cases pass.

### Task 2: Delivery Contract Documentation

**Files:**
- Modify: `.env.example`
- Modify: `.env.compose.example`
- Modify: `docker-compose.yml`
- Modify: `README.md`
- Modify: `docs/数据库迁移与维护.md`

**Interfaces:**
- Consumes: executable `sqlite+aiosqlite` validation from Task 1.
- Produces: one consistent operator-facing support statement for local, Docker, and maintenance workflows.

- [ ] **Step 1: Update environment examples**

State that `DATABASE_URL` is optional locally, only `sqlite+aiosqlite` is supported, and omitting it selects the default database under `PROCESSMIND_DATA_DIR`. Keep the Compose URL unchanged.

- [ ] **Step 2: Document the Compose constraint**

Add a YAML comment immediately above the API `DATABASE_URL` entry explaining that this build accepts only `sqlite+aiosqlite` and uses mounted `/runtime-data`.

- [ ] **Step 3: Update operator documentation**

In README's data section, state that PostgreSQL and other databases are rejected before engine creation and require a separate compatibility/migration project. In the maintenance guide, replace the stale future-R-008 wording with the completed boundary and supported URL form.

- [ ] **Step 4: Verify delivery configuration**

Run from `process-plan-agent-api/`:

```powershell
..\.runtime\python\python.exe -m pytest tests/test_delivery_config.py -q
```

Expected: all delivery configuration tests pass.

### Task 3: Full Verification And Tracking Closure

**Files:**
- Modify: `docs/重构与优化跟踪.md`

**Interfaces:**
- Consumes: fresh focused tests, full backend tests, compile check, and Docker availability check.
- Produces: final R-008 completion record with actual evidence and explicit unverified items.

- [ ] **Step 1: Run focused R-008 regression**

Run `..\.runtime\python\python.exe -m pytest tests/test_db_startup_safety.py tests/test_delivery_config.py -q` from `process-plan-agent-api/`.

- [ ] **Step 2: Run the backend full suite**

Run `..\.runtime\python\python.exe -m pytest -q` from `process-plan-agent-api/`.

- [ ] **Step 3: Compile backend modules**

Run `..\.runtime\python\python.exe -m compileall -q app tests` from `process-plan-agent-api/`.

- [ ] **Step 4: Check Docker availability**

Run `Get-Command docker -ErrorAction SilentlyContinue` from the repository root. If present, run `docker compose config`; otherwise record that Docker verification was unavailable.

- [ ] **Step 5: Update R-008 tracking with observed evidence**

Mark R-008 `已验证完成`; describe the pre-engine validation, credential-safe errors, and synchronized documentation. Record exact test counts, compile result, Docker result, and leave multi-database support as a separate future project.

- [ ] **Step 6: Inspect the final patch**

Run `git diff --check`, `git status --short`, and a scoped `git diff` covering the files listed in this plan. Confirm unrelated untracked files remain untouched and no secret-bearing URL appears in production code, documentation, or tracked output.
