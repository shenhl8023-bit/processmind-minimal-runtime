# R-007 Versioned Database Migrations Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 ProcessMind 的 SQLite 启动维护改为有序、可审计、失败可定位的版本化迁移，并提供带备份的显式重复工序维护命令。

**Architecture:** 新增 `db_schema_migrations.py` 管理迁移控制表、固定注册表和版本 1 至 5 的一次性迁移；`database.init_db()` 继续持有单一启动事务。`db_schema_maintenance.py` 只保留显式重复工序审计与修复，根目录维护脚本负责只读预览、SQLite 在线备份、事务修复和恢复所需输出。

**Tech Stack:** Python 3.11+、SQLAlchemy 2 AsyncConnection、aiosqlite、SQLite、pytest、标准库 argparse/sqlite3

## Global Constraints

- 不引入 Alembic 或其他依赖。
- R-007 只支持当前 SQLite 路径；不顺带实施 R-008。
- 迁移版本 1 至 5 的编号和名称发布后不可改写、重排或复用。
- 迁移函数不自行提交或回滚，继续由 `database.init_db()` 的 `engine.begin()` 持有事务。
- 启动不得自动删除重复工序或因素。
- 维护写命令必须先用 SQLite `Connection.backup()` 创建一致性备份。
- 不修改业务 API、前端、V2 规则包、KmAI V1 JSON、ZIP、哈希算法或发布生命周期语义。
- 测试只使用 `tmp_path` 数据库，不迁移或修复工作区真实 `data/*.db`。
- 保留工作区已有未跟踪设计稿和截图，不覆盖或删除。
- 未经用户明确授权，不执行 `git add`、`git commit`、`git push`、rebase、reset 或分支操作。

---

## File Map

| 文件 | 责任 |
| --- | --- |
| `process-plan-agent-api/app/services/db_schema_migrations.py` | 迁移类型、控制表引导、历史校验、运行器和版本 1 至 5 的迁移 |
| `process-plan-agent-api/app/services/db_schema_maintenance.py` | 显式数据库审计、重复工序修复计划、执行和验证 |
| `process-plan-agent-api/app/database.py` | 在现有启动事务内调用迁移运行器 |
| `process-plan-agent-api/tests/test_db_startup_safety.py` | 全新库、历史库、重复启动、失败回滚及 KmAI 历史升级测试 |
| `process-plan-agent-api/tests/test_database_maintenance.py` | 审计、预览、备份、修复、失败回滚和恢复测试 |
| `scripts/maintain_database.py` | 面向维护人员的 SQLite 命令行入口 |
| `docs/数据库迁移与维护.md` | 审计、预览、停止服务、备份、应用修复和恢复步骤 |
| `docs/superpowers/specs/2026-08-08-r007-versioned-database-migrations-design.md` | 设计状态与最终实现一致性记录 |
| `docs/重构与优化跟踪.md` | R-007 完成状态、验证证据和保留限制 |

---

### Task 1: Build the ordered migration runner

**Files:**
- Create: `process-plan-agent-api/app/services/db_schema_migrations.py`
- Modify: `process-plan-agent-api/tests/test_db_startup_safety.py`

**Interfaces:**
- Produces: `SchemaMigration(version, name, apply)`, `DatabaseMigrationError`, `SCHEMA_MIGRATIONS`, `run_schema_migrations(conn, migrations=None)` and compatibility wrapper `ensure_project_schema(conn)`.
- Guarantee: every applied migration has one unique version/name record; a failed migration is wrapped with its identity and leaves no successful record.

- [x] **Step 1: Add failing runner tests**

Extend `test_db_startup_safety.py` with tests that import the new module and use a temporary async SQLite engine. The first test supplies two local migrations:

```python
async def first(conn):
    await conn.execute(text("CREATE TABLE runner_first (id INTEGER PRIMARY KEY)"))
    return {"created": "runner_first"}

async def second(conn):
    await conn.execute(text("CREATE TABLE runner_second (id INTEGER PRIMARY KEY)"))
    return {"created": "runner_second"}

migrations = (
    SchemaMigration(1, "runner_first_v1", first),
    SchemaMigration(2, "runner_second_v1", second),
)
```

Call `run_schema_migrations(conn, migrations=migrations)` twice and assert literal history rows `(1, "runner_first_v1")` and `(2, "runner_second_v1")`, valid `status="applied"` JSON, and unchanged `applied_at` values after the second call.

Add a failure test whose migration creates a table, inserts a row, then raises `RuntimeError("forced migration failure")`. Execute it inside `engine.begin()` and assert:

```python
with pytest.raises(
    DatabaseMigrationError,
    match=r"Database migration 2 \(runner_fails_v1\) failed",
):
    async with engine.begin() as conn:
        await run_schema_migrations(conn, migrations=migrations)
```

After rollback, assert `runner_partial` and the version 2 history row are absent.

- [x] **Step 2: Run the tests and verify RED**

Run from `process-plan-agent-api/`:

```powershell
python -m pytest tests/test_db_startup_safety.py -q
```

Expected: collection fails because `app.services.db_schema_migrations` does not exist.

- [x] **Step 3: Implement migration metadata, control-table bootstrap, and runner**

Create the module with these public types:

```python
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any

MigrationResult = dict[str, Any]
MigrationApply = Callable[[Any], Awaitable[MigrationResult | None]]

@dataclass(frozen=True)
class SchemaMigration:
    version: int
    name: str
    apply: MigrationApply

class DatabaseMigrationError(RuntimeError):
    def __init__(self, migration: SchemaMigration, cause: Exception):
        super().__init__(
            f"Database migration {migration.version} ({migration.name}) failed: {cause}"
        )
        self.version = migration.version
        self.migration_name = migration.name
```

Implement `_bootstrap_migration_table(conn, migrations)` so it:

1. Creates `schema_migrations(name, version, applied_at, result_json)` for a new database.
2. Uses `PRAGMA table_info("schema_migrations")` to add `version` and `result_json` to the historical two-column table.
3. Adopts the existing `retire_kmai_factor_mappings_v1` record using the fixed version from the supplied registry.
4. Rejects unknown names, null versions, duplicate versions, or a known name stored under the wrong version.
5. Creates `uq_schema_migrations_version` only after validation.

Implement `run_schema_migrations()` in ascending version order. Validate the in-code registry for positive unique versions and non-empty unique names before touching the database. Insert each record only after `apply()` returns, using literal compact JSON:

```python
payload = {"status": "applied", **(result or {})}
```

Do not catch `DatabaseMigrationError` twice. Wrap other exceptions with `raise DatabaseMigrationError(migration, error) from error`.

- [x] **Step 4: Run runner tests and verify GREEN**

```powershell
python -m pytest tests/test_db_startup_safety.py -q
```

Expected: runner tests和现有启动测试通过；本任务阶段的生产迁移注册表暂为空元组，版本 1 至 5 在 Task 2 固化。

- [x] **Step 5: Add strict history tests**

Add table-driven cases for:

- unknown historical name;
- known name with the wrong version;
- duplicate version values;
- legacy KmAI name-only record adoption.

The adoption assertion must be literal:

```python
assert row == (
    5,
    "retire_kmai_factor_mappings_v1",
    '{"status":"adopted_legacy_record"}',
)
```

- [x] **Step 6: Run strict history tests**

```powershell
python -m pytest tests/test_db_startup_safety.py -q
```

Expected: all tests pass and malformed history is rejected before any business migration runs.

---

### Task 2: Freeze existing startup work into migrations 1 through 5

**Files:**
- Modify: `process-plan-agent-api/app/services/db_schema_migrations.py`
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Modify: `process-plan-agent-api/app/database.py`
- Modify: `process-plan-agent-api/tests/test_db_startup_safety.py`
- Modify: rule-package tests that import `ensure_project_schema`

**Interfaces:**
- Produces: fixed `SCHEMA_MIGRATIONS` versions 1 through 5 with names from the approved design.
- Changes: normal startup calls `run_schema_migrations(conn)` and no longer calls duplicate-operation audit on every run.
- Preserves: `ensure_project_schema(conn)` as a thin compatibility wrapper for remaining internal callers.

- [x] **Step 1: Add failing full-registry and idempotency tests**

For a fresh database created with `Base.metadata.create_all()`, run the production registry and assert exactly:

```python
assert history == [
    (1, "legacy_project_schema_v1"),
    (2, "workflow_review_schema_v1"),
    (3, "route_review_indexes_v1"),
    (4, "rule_package_lifecycle_v2"),
    (5, "retire_kmai_factor_mappings_v1"),
]
```

Capture all history fields, insert a deliberately invalid post-migration project profile, run the registry again, and assert both the history and inserted profile remain unchanged. This proves repeated startup skipped migration bodies instead of reapplying repair SQL.

Update the duplicate-operation startup test so it expects preserved operations/factors and no new `schema_maintenance_audit` row.

- [x] **Step 2: Run startup tests and verify RED**

```powershell
python -m pytest tests/test_db_startup_safety.py -q
```

Expected: history is empty or incomplete and the current startup still writes the duplicate-operation audit row.

- [x] **Step 3: Move existing SQL into fixed migrations**

Move the existing code without changing its business predicates, grouped as follows:

- Version 1 `legacy_project_schema_v1`: `projects` compatibility table and the current project/operation/document/generated-route column additions.
- Version 2 `workflow_review_schema_v1`: condition-review columns, project mode/profile/rule engine/workflow revision, `extraction_task_states`, project defaults/status backfill, monotonic project ID sequence, and one-time `chain` backfill.
- Version 3 `route_review_indexes_v1`: document operation, route version, factor/rule review and parameter answer indexes plus the current duplicate-aware operation identity index choice. Return `{"duplicate_operation_group_count": <literal count>, "operation_identity_index": "unique"|"non_unique"}`.
- Version 4 `rule_package_lifecycle_v2`: finalized package table/columns, status introduction behavior, content hash backfill, published package normalization and lifecycle indexes.
- Version 5 `retire_kmai_factor_mappings_v1`: existing snapshot validation, backfill, verification and three-table retirement, but remove its direct insert into `schema_migrations`; the runner owns the record.

Delete the old monolithic startup body from `db_schema_maintenance.py`. Keep only explicit maintenance code needed by Task 3.

- [x] **Step 4: Switch application startup to the runner**

In `app/database.py`, replace the import and call with:

```python
from app.services.db_schema_migrations import run_schema_migrations

# inside init_db()
await run_schema_migrations(conn)
```

Update direct test imports to the new module or retain the compatibility wrapper where a test intentionally exercises the old entry point.

- [x] **Step 5: Run startup and historical KmAI tests**

```powershell
python -m pytest tests/test_db_startup_safety.py tests/test_rule_package_lifecycle.py -q
```

Expected: fresh history, repeated startup, copied historical fixture, snapshot backfill and all rollback branches pass.

- [x] **Step 6: Add copied historical snapshot coverage**

Use the existing legacy fixture builder to create a source database, close it, copy it with `shutil.copy2()` to a separate test path, and upgrade only the copied path. Assert:

- versions 1 through 5 are present exactly once;
- the source file still contains all three legacy mapping tables;
- the copy contains the expected immutable mapping snapshot and no legacy mapping tables;
- package business columns match their pre-upgrade values.

The copy is a test fixture mechanism, not the product backup mechanism.

- [x] **Step 7: Run rule-package migration regressions**

```powershell
python -m pytest tests/test_db_startup_safety.py tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_rule_package_status.py tests/test_generate_v2_production.py tests/test_kmai_rule_package_export.py -q
```

Expected: all selected tests pass; only the repository's known TestClient/httpx deprecation warning may remain.

---

### Task 3: Add explicit audit, backup, preview, repair, and restore coverage

**Files:**
- Modify: `process-plan-agent-api/app/services/db_schema_maintenance.py`
- Create: `process-plan-agent-api/tests/test_database_maintenance.py`
- Create: `scripts/maintain_database.py`

**Interfaces:**
- Produces: `audit_database(connection)`, `plan_duplicate_operation_repair(connection)`, `apply_duplicate_operation_repair(connection, plan)` and CLI `main(argv=None) -> int`.
- Guarantee: audit and preview are read-only; `--apply` backs up first, uses one transaction, verifies results, and returns nonzero on failure.

- [x] **Step 1: Write failing service tests**

Create a temporary SQLite fixture with `schema_migrations`, `operations`, and `factors`. Include two duplicate operation rows, distinct factors on each row, one exact duplicate factor, and a manual non-empty chain.

Test the literal plan shape:

```python
assert plan.groups[0].keep_id == 1
assert plan.groups[0].remove_ids == (2,)
assert plan.groups[0].factor_ids_to_move == (2, 3)
```

Hash the relevant table rows before and after `audit_database()` and `plan_duplicate_operation_repair()` to prove both are read-only.

- [x] **Step 2: Run service tests and verify RED**

```powershell
python -m pytest tests/test_database_maintenance.py -q
```

Expected: collection fails because the maintenance interfaces do not exist.

- [x] **Step 3: Implement immutable audit and repair-plan types**

Use frozen dataclasses with tuple fields:

```python
@dataclass(frozen=True)
class DuplicateOperationRepairGroup:
    project_id: int
    sequence: int
    name: str
    keep_id: int
    remove_ids: tuple[int, ...]
    factor_ids_to_move: tuple[int, ...]

@dataclass(frozen=True)
class DuplicateOperationRepairPlan:
    groups: tuple[DuplicateOperationRepairGroup, ...]
```

Audit returns migration rows, pending code migrations, duplicate groups and both operation-index flags. Derive preview and apply from the same `DuplicateOperationRepairPlan`.

- [x] **Step 4: Implement transactional repair and verification**

For each group, update factors from every `remove_id` to `keep_id`, delete exact duplicate factors using the existing grouping columns, then delete removed operations. After all groups:

1. rescan and require zero duplicate groups;
2. require zero factors whose `operation_id` has no operation;
3. drop `idx_operations_project_seq_name`;
4. create `uq_operations_project_seq_name`;
5. preserve all non-empty `chain` values.

Do not call `commit()` or `rollback()` inside the service; the CLI owns the sqlite3 transaction.

- [x] **Step 5: Add CLI tests before the CLI implementation**

Use `scripts.maintain_database.main()` with `capsys` and a temporary database:

- `audit` exits 0, prints absolute DB path and duplicate count, and leaves rows unchanged.
- repair without `--apply` exits 0, prints `PREVIEW`, creates no backup, and leaves rows unchanged.
- repair with `--apply` creates exactly one `.bak-<UTC stamp>` database before changes and reports its absolute path.
- a SQLite trigger that aborts operation deletion makes the command exit nonzero; factor moves roll back and the backup remains readable.
- replacing the repaired temporary DB with the backup restores the exact pre-repair table rows.

- [x] **Step 6: Run CLI tests and verify RED**

```powershell
python -m pytest tests/test_database_maintenance.py -q
```

Expected: service tests pass but CLI tests fail because `scripts/maintain_database.py` does not exist.

- [x] **Step 7: Implement the maintenance CLI**

Use `argparse` with global required `--db` and subcommands `audit` and `repair-operation-duplicates`; add `--apply` only to the repair subcommand. Resolve the path, reject a missing or non-file target with exit code 2, and use:

```python
def backup_database(source: sqlite3.Connection, database_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = database_path.with_name(f"{database_path.name}.bak-{stamp}")
    with sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path
```

For `--apply`, create the backup, execute `BEGIN IMMEDIATE`, rebuild the plan inside the transaction, apply and verify, then commit. On any exception, rollback, print the exception and backup path to stderr, and return 1.

- [x] **Step 8: Run maintenance tests and verify GREEN**

```powershell
python -m pytest tests/test_database_maintenance.py -q
```

Expected: audit, preview, apply, failure rollback, backup readability and restore tests pass.

- [x] **Step 9: Run CLI subprocess smoke tests against a disposable DB**

Create the database only through a pytest fixture or a temporary path, then execute:

```powershell
python scripts/maintain_database.py --db <temporary-db> audit
python scripts/maintain_database.py --db <temporary-db> repair-operation-duplicates
```

Expected: both exit 0; the second reports preview mode and creates no backup.

---

### Task 4: Document operations and complete verification

**Files:**
- Create: `docs/数据库迁移与维护.md`
- Modify: `docs/superpowers/specs/2026-08-08-r007-versioned-database-migrations-design.md`
- Modify: `docs/superpowers/plans/2026-08-08-r007-versioned-database-migrations.md`
- Modify: `docs/重构与优化跟踪.md`

**Interfaces:**
- Produces: executable maintenance and recovery instructions plus an R-007 completion record grounded in fresh test output.
- Does not produce: commits, staging, Docker claims, frontend claims or database-support claims without evidence.

- [x] **Step 1: Write the operations document**

Document exact Windows and POSIX commands for:

1. stopping ProcessMind API with the existing scripts;
2. locating the configured SQLite file without printing secrets;
3. running audit and repair preview;
4. applying repair and recording the backup path;
5. restoring while the API remains stopped by first preserving the failed database under a different filename;
6. restarting and checking `/api/health` plus migration audit output.

State that migrations run automatically at API startup, migration records are append-only, manual SQL edits to `schema_migrations` are unsupported, and non-SQLite support remains R-008.

- [x] **Step 2: Run focused backend verification**

```powershell
python -m pytest tests/test_db_startup_safety.py tests/test_database_maintenance.py tests/test_rule_package_lifecycle.py tests/test_rule_package_api.py tests/test_rule_package_status.py tests/test_generate_v2_production.py tests/test_kmai_rule_package_export.py -q
```

Record exact passed/skipped/warning counts.

- [x] **Step 3: Run complete backend verification**

```powershell
python -m pytest -q
```

Record exact counts and distinguish failures caused by R-007 from pre-existing warnings.

- [x] **Step 4: Compile changed Python modules**

```powershell
python -m compileall -q app/services/db_schema_migrations.py app/services/db_schema_maintenance.py app/database.py ../scripts/maintain_database.py
```

Expected: exit 0 with no syntax errors.

- [x] **Step 5: Perform explicit completion searches**

From repository root:

```powershell
rg -n "audit_duplicate_operations|dedupe_operations" process-plan-agent-api/app process-plan-agent-api/tests scripts
rg -n "run_schema_migrations|SchemaMigration|DatabaseMigrationError" process-plan-agent-api/app process-plan-agent-api/tests
rg -n "retire_kmai_factor_mappings_v1|schema_migrations" process-plan-agent-api/app process-plan-agent-api/tests scripts
```

Expected: startup has no call to repeated audit or dedupe; the runner, fixed registry, compatibility marker and tests are visible at their intended boundaries.

- [x] **Step 6: Update design, plan, and tracking document with actual evidence**

Only after Steps 2 through 5 succeed:

1. Change the R-007 design status to `已实施，验证通过`.
2. Mark only actually completed plan checkboxes.
3. Change the R-007 tracking row and detail to `已验证完成`.
4. Record exact migration names, maintenance command behavior, modified files and test counts.
5. Retain explicit statements that Docker, non-SQLite databases and real production database upgrade were not verified unless they were actually exercised.

- [x] **Step 7: Run final diff and workspace checks**

```powershell
git diff --check
git status --short
git diff --stat
```

Confirm that only R-007 source, tests and docs plus pre-existing untracked files are present. Do not stage or commit.

## Verification Record

- 迁移/启动/规则包聚焦：`98 passed, 1 warning`。
- 维护服务、备份、恢复和失败回滚：`5 passed`。
- 后端全量：`352 passed, 1 skipped, 1 warning`，使用仓库自带 Python `3.13.5`。
- Python 编译检查：`compileall` 成功。
- CLI 空 SQLite 冒烟：`audit` 与修复预览均退出 `0`，空库没有业务写入。
- 未执行 Docker、非 SQLite、真实生产数据库升级、离线交付包和前端验证；本条目未修改前端。
