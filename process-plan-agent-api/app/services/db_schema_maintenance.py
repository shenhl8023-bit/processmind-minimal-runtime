from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class DuplicateOperationRepairGroup:
    project_id: int | None
    sequence: int
    name: str
    keep_id: int
    remove_ids: tuple[int, ...]
    factor_ids_to_move: tuple[int, ...]


@dataclass(frozen=True)
class DuplicateOperationRepairPlan:
    groups: tuple[DuplicateOperationRepairGroup, ...]


@dataclass(frozen=True)
class MigrationAuditEntry:
    version: int
    name: str
    applied_at: str
    result_json: str


@dataclass(frozen=True)
class DatabaseAuditReport:
    migration_history: tuple[MigrationAuditEntry, ...]
    pending_migrations: tuple[str, ...]
    duplicate_group_count: int
    duplicate_groups: tuple[DuplicateOperationRepairGroup, ...]
    has_non_unique_operation_index: bool
    has_unique_operation_index: bool


def _sqlite_table_exists(conn: sqlite3.Connection, table_name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def _operation_index_flags(conn: sqlite3.Connection) -> tuple[bool, bool]:
    names = {
        row[0]
        for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'index'"
        ).fetchall()
    }
    return (
        "idx_operations_project_seq_name" in names,
        "uq_operations_project_seq_name" in names,
    )


def _duplicate_operation_groups(
    conn: sqlite3.Connection,
) -> tuple[DuplicateOperationRepairGroup, ...]:
    groups: list[DuplicateOperationRepairGroup] = []
    if not _sqlite_table_exists(conn, "operations"):
        return ()
    duplicate_rows = conn.execute("""
        SELECT project_id, sequence, name
        FROM operations
        GROUP BY project_id, sequence, name
        HAVING COUNT(*) > 1
        ORDER BY project_id, sequence, name
    """).fetchall()
    for project_id, sequence, name in duplicate_rows:
        rows = conn.execute(
            """
            SELECT id
            FROM operations
            WHERE project_id IS ? AND sequence = ? AND name = ?
            ORDER BY id
            """,
            (project_id, sequence, name),
        ).fetchall()
        operation_ids = tuple(int(row[0]) for row in rows)
        keep_id = operation_ids[0]
        remove_ids = operation_ids[1:]
        placeholders = ", ".join("?" for _ in remove_ids)
        factor_rows = ()
        if _sqlite_table_exists(conn, "factors"):
            factor_rows = conn.execute(
                f"""
                SELECT id
                FROM factors
                WHERE operation_id IN ({placeholders})
                ORDER BY id
                """,
                remove_ids,
            ).fetchall()
        groups.append(
            DuplicateOperationRepairGroup(
                project_id=project_id,
                sequence=int(sequence),
                name=str(name),
                keep_id=keep_id,
                remove_ids=remove_ids,
                factor_ids_to_move=tuple(int(row[0]) for row in factor_rows),
            )
        )
    return tuple(groups)


def plan_duplicate_operation_repair(
    conn: sqlite3.Connection,
) -> DuplicateOperationRepairPlan:
    return DuplicateOperationRepairPlan(groups=_duplicate_operation_groups(conn))


def audit_database(conn: sqlite3.Connection) -> DatabaseAuditReport:
    history: tuple[MigrationAuditEntry, ...] = ()
    if _sqlite_table_exists(conn, "schema_migrations"):
        columns = {
            row[1]
            for row in conn.execute('PRAGMA table_info("schema_migrations")').fetchall()
        }
        version_expression = "version" if "version" in columns else "0 AS version"
        result_expression = (
            "result_json" if "result_json" in columns else "'' AS result_json"
        )
        history = tuple(
            MigrationAuditEntry(
                version=int(row["version"]),
                name=str(row["name"]),
                applied_at=str(row["applied_at"]),
                result_json=str(row["result_json"]),
            )
            for row in conn.execute(f"""
                SELECT {version_expression}, name, applied_at, {result_expression}
                FROM schema_migrations
                ORDER BY version
            """).fetchall()
        )
    from app.services.db_schema_migrations import SCHEMA_MIGRATIONS

    applied_names = {entry.name for entry in history}
    pending = tuple(
        migration.name
        for migration in SCHEMA_MIGRATIONS
        if migration.name not in applied_names
    )
    duplicate_groups = plan_duplicate_operation_repair(conn).groups
    non_unique, unique = _operation_index_flags(conn)
    return DatabaseAuditReport(
        migration_history=history,
        pending_migrations=pending,
        duplicate_group_count=len(duplicate_groups),
        duplicate_groups=duplicate_groups,
        has_non_unique_operation_index=non_unique,
        has_unique_operation_index=unique,
    )


def apply_duplicate_operation_repair(
    conn: sqlite3.Connection,
    plan: DuplicateOperationRepairPlan,
) -> None:
    if not _sqlite_table_exists(conn, "operations"):
        return
    if not plan.groups:
        return
    for group in plan.groups:
        if group.remove_ids:
            placeholders = ", ".join("?" for _ in group.remove_ids)
            conn.execute(
                f"""
                UPDATE factors
                SET operation_id = ?
                WHERE operation_id IN ({placeholders})
                """,
                (group.keep_id, *group.remove_ids),
            )
    conn.execute("""
        DELETE FROM factors
        WHERE id NOT IN (
            SELECT MIN(id)
            FROM factors
            GROUP BY operation_id, name,
                     COALESCE(evidence, ''),
                     COALESCE(strength, ''),
                     COALESCE(confirmed, 0)
        )
    """)
    for group in plan.groups:
        placeholders = ", ".join("?" for _ in group.remove_ids)
        conn.execute(
            f"DELETE FROM operations WHERE id IN ({placeholders})",
            group.remove_ids,
        )

    remaining = plan_duplicate_operation_repair(conn)
    if remaining.groups:
        raise RuntimeError(
            "Duplicate operation verification failed after repair: "
            f"{len(remaining.groups)} group(s) remain"
        )
    orphan_count = 0
    if _sqlite_table_exists(conn, "factors"):
        orphan_count = conn.execute("""
            SELECT COUNT(*)
            FROM factors AS factor
            LEFT JOIN operations AS operation ON operation.id = factor.operation_id
            WHERE operation.id IS NULL
        """).fetchone()[0]
    if orphan_count:
        raise RuntimeError(
            f"Duplicate operation repair left {orphan_count} orphan factor(s)"
        )
    conn.execute("DROP INDEX IF EXISTS idx_operations_project_seq_name")
    conn.execute("""
        CREATE UNIQUE INDEX IF NOT EXISTS uq_operations_project_seq_name
        ON operations (project_id, sequence, name)
    """)


async def ensure_project_schema(conn) -> None:
    """Backward-compatible startup entry point for internal callers."""
    from app.services.db_schema_migrations import run_schema_migrations

    await run_schema_migrations(conn)
