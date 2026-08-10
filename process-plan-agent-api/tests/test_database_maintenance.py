import gc
import json
import sqlite3
import sys
import warnings
from contextlib import closing
from pathlib import Path

import pytest

from app.services.db_schema_maintenance import (
    audit_database,
    apply_duplicate_operation_repair,
    plan_duplicate_operation_repair,
)


@pytest.fixture
def duplicate_database(tmp_path):
    path = tmp_path / "duplicate-operations.db"
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.executescript("""
        CREATE TABLE schema_migrations (
            name TEXT PRIMARY KEY,
            version INTEGER NOT NULL,
            applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            result_json TEXT NOT NULL
        );
        CREATE TABLE operations (
            id INTEGER PRIMARY KEY,
            project_id INTEGER,
            name TEXT NOT NULL,
            sequence INTEGER NOT NULL,
            chain TEXT
        );
        CREATE TABLE factors (
            id INTEGER PRIMARY KEY,
            operation_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            evidence TEXT,
            strength TEXT,
            confirmed BOOLEAN
        );
        CREATE INDEX idx_operations_project_seq_name
        ON operations (project_id, sequence, name);
    """)
    conn.executemany(
        """
        INSERT INTO schema_migrations (name, version, result_json)
        VALUES (?, ?, ?)
        """,
        [
            ("legacy_project_schema_v1", 1, json.dumps({"status": "applied"})),
            ("workflow_review_schema_v1", 2, json.dumps({"status": "applied"})),
        ],
    )
    conn.executemany(
        """
        INSERT INTO operations (id, project_id, name, sequence, chain)
        VALUES (?, ?, ?, ?, ?)
        """,
        [
            (1, 7, "车削", 1, "manual-chain"),
            (2, 7, "车削", 1, "other"),
            (3, 7, "淬火", 2, "heat"),
        ],
    )
    conn.executemany(
        """
        INSERT INTO factors (id, operation_id, name, evidence, strength, confirmed)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        [
            (1, 1, "材料", "same", "strong", 1),
            (2, 2, "材料", "same", "strong", 1),
            (3, 2, "余量", "different", "weak", 0),
        ],
    )
    conn.commit()
    try:
        yield conn, path
    finally:
        conn.close()


def _business_snapshot(conn):
    return (
        [
            tuple(row)
            for row in conn.execute(
                "SELECT id, project_id, name, sequence, chain FROM operations ORDER BY id"
            ).fetchall()
        ],
        [
            tuple(row)
            for row in conn.execute(
                """
                SELECT id, operation_id, name, evidence, strength, confirmed
                FROM factors
                ORDER BY id
                """
            ).fetchall()
        ],
    )


def test_audit_and_preview_are_read_only(duplicate_database):
    conn, _path = duplicate_database
    before = _business_snapshot(conn)

    report = audit_database(conn)
    plan = plan_duplicate_operation_repair(conn)

    assert report.duplicate_group_count == 1
    assert report.has_non_unique_operation_index is True
    assert report.has_unique_operation_index is False
    assert len(plan.groups) == 1
    assert plan.groups[0].keep_id == 1
    assert plan.groups[0].remove_ids == (2,)
    assert plan.groups[0].factor_ids_to_move == (2, 3)
    assert _business_snapshot(conn) == before


def test_apply_repair_remounts_factors_and_upgrades_identity_index(duplicate_database):
    conn, _path = duplicate_database
    plan = plan_duplicate_operation_repair(conn)

    conn.execute("BEGIN IMMEDIATE")
    apply_duplicate_operation_repair(conn, plan)
    conn.commit()

    assert conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 2
    assert conn.execute(
        "SELECT chain FROM operations WHERE id = 1"
    ).fetchone()[0] == "manual-chain"
    assert [
        tuple(row)
        for row in conn.execute(
            "SELECT operation_id, name FROM factors ORDER BY id"
        ).fetchall()
    ] == [(1, "材料"), (1, "余量")]
    assert conn.execute(
        "SELECT COUNT(*) FROM factors WHERE operation_id NOT IN (SELECT id FROM operations)"
    ).fetchone()[0] == 0
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'idx_operations_project_seq_name'"
    ).fetchone() is None
    assert conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'index' AND name = 'uq_operations_project_seq_name'"
    ).fetchone() is not None


def _load_maintenance_cli():
    repo_root = str(Path(__file__).resolve().parents[2])
    if repo_root not in sys.path:
        sys.path.insert(0, repo_root)
    from scripts.maintain_database import main

    return main


def test_cli_audit_and_preview_are_read_only(duplicate_database, capsys):
    conn, path = duplicate_database
    main = _load_maintenance_cli()
    before = _business_snapshot(conn)

    assert main(["--db", str(path), "audit"]) == 0
    audit_output = capsys.readouterr().out
    assert str(path.resolve()) in audit_output
    assert "duplicate_group_count=1" in audit_output

    assert main(["--db", str(path), "repair-operation-duplicates"]) == 0
    preview_output = capsys.readouterr().out
    assert "PREVIEW" in preview_output
    assert list(path.parent.glob(f"{path.name}.bak-*")) == []
    assert _business_snapshot(conn) == before


def test_cli_apply_writes_backup_and_repair_can_be_restored(duplicate_database, capsys):
    conn, path = duplicate_database
    before = _business_snapshot(conn)
    conn.close()
    main = _load_maintenance_cli()

    assert main(["--db", str(path), "repair-operation-duplicates", "--apply"]) == 0
    output = capsys.readouterr().out
    backups = list(path.parent.glob(f"{path.name}.bak-*"))
    assert len(backups) == 1
    assert str(backups[0].resolve()) in output

    with closing(sqlite3.connect(path)) as repaired:
        assert repaired.execute("SELECT COUNT(*) FROM operations").fetchone()[0] == 2
    with closing(sqlite3.connect(backups[0])) as backup:
        assert _business_snapshot(backup) == before


def test_cli_apply_rolls_back_and_keeps_backup_when_delete_fails(duplicate_database, capsys):
    conn, path = duplicate_database
    conn.execute("""
        CREATE TRIGGER fail_operation_delete
        BEFORE DELETE ON operations
        BEGIN
            SELECT RAISE(ABORT, 'forced maintenance failure');
        END;
    """)
    conn.commit()
    before = _business_snapshot(conn)
    conn.close()
    main = _load_maintenance_cli()

    assert main(["--db", str(path), "repair-operation-duplicates", "--apply"]) == 1
    error_output = capsys.readouterr().err
    backups = list(path.parent.glob(f"{path.name}.bak-*"))
    assert len(backups) == 1
    assert str(backups[0].resolve()) in error_output
    with closing(sqlite3.connect(path)) as unchanged:
        assert _business_snapshot(unchanged) == before


def test_cli_apply_closes_all_database_connections(duplicate_database, capsys):
    conn, path = duplicate_database
    conn.close()
    main = _load_maintenance_cli()

    with warnings.catch_warnings(record=True) as captured:
        warnings.simplefilter("always", ResourceWarning)
        assert main(["--db", str(path), "repair-operation-duplicates", "--apply"]) == 0
        gc.collect()

    capsys.readouterr()
    unclosed = [
        str(item.message)
        for item in captured
        if issubclass(item.category, ResourceWarning) and "unclosed database" in str(item.message)
    ]
    assert unclosed == []
