#!/usr/bin/env python3
"""Audit and repair the ProcessMind SQLite database."""

from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import datetime, timezone
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[1]
API_ROOT = REPOSITORY_ROOT / "process-plan-agent-api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.services.db_schema_maintenance import (  # noqa: E402
    audit_database,
    apply_duplicate_operation_repair,
    plan_duplicate_operation_repair,
)


def backup_database(source: sqlite3.Connection, database_path: Path) -> Path:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    backup_path = database_path.with_name(f"{database_path.name}.bak-{stamp}")
    if backup_path.exists():
        raise FileExistsError(f"Refusing to overwrite existing backup: {backup_path}")
    with sqlite3.connect(backup_path) as destination:
        source.backup(destination)
    return backup_path


def _print_audit(database_path: Path, conn: sqlite3.Connection) -> None:
    report = audit_database(conn)
    print(f"Database: {database_path.resolve()}")
    print("Migrations:")
    for entry in report.migration_history:
        print(
            f"  {entry.version}: {entry.name} "
            f"applied_at={entry.applied_at} result={entry.result_json}"
        )
    if report.pending_migrations:
        print("Pending migrations: " + ", ".join(report.pending_migrations))
    else:
        print("Pending migrations: none")
    print(f"duplicate_group_count={report.duplicate_group_count}")
    for group in report.duplicate_groups:
        print(
            "  duplicate "
            f"project={group.project_id} sequence={group.sequence} "
            f"name={group.name!r} keep={group.keep_id} "
            f"remove={list(group.remove_ids)}"
        )
    print(
        "operation_identity_indexes="
        f"non_unique:{report.has_non_unique_operation_index},"
        f"unique:{report.has_unique_operation_index}"
    )


def _run_audit(database_path: Path) -> int:
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        _print_audit(database_path, conn)
    return 0


def _run_repair(database_path: Path, *, apply: bool) -> int:
    with sqlite3.connect(database_path) as conn:
        conn.row_factory = sqlite3.Row
        plan = plan_duplicate_operation_repair(conn)
        if not apply:
            print(
                f"PREVIEW duplicate_group_count={len(plan.groups)} "
                "No changes written."
            )
            for group in plan.groups:
                print(
                    f"  keep={group.keep_id} remove={list(group.remove_ids)} "
                    f"move_factors={list(group.factor_ids_to_move)}"
                )
            return 0

        backup_path = backup_database(conn, database_path)
        print(f"Backup: {backup_path.resolve()}")
        try:
            conn.execute("BEGIN IMMEDIATE")
            current_plan = plan_duplicate_operation_repair(conn)
            apply_duplicate_operation_repair(conn, current_plan)
            conn.commit()
        except Exception as error:
            conn.rollback()
            print(f"Maintenance failed: {error}", file=sys.stderr)
            print(f"Backup preserved: {backup_path.resolve()}", file=sys.stderr)
            return 1
        print(f"Applied duplicate-operation repair: {len(current_plan.groups)} group(s)")
    return 0


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, type=Path, help="Path to process_mind.db")
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("audit", help="Read-only migration and duplicate audit")
    repair_parser = subparsers.add_parser(
        "repair-operation-duplicates",
        help="Preview or repair duplicate operations",
    )
    repair_parser.add_argument(
        "--apply",
        action="store_true",
        help="Write the repair after creating a SQLite backup",
    )
    args = parser.parse_args(argv)
    database_path = args.db.resolve()
    if not database_path.is_file():
        print(f"Database not found: {database_path}", file=sys.stderr)
        return 2
    try:
        if args.command == "audit":
            return _run_audit(database_path)
        return _run_repair(database_path, apply=args.apply)
    except Exception as error:
        print(f"Maintenance command failed: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
