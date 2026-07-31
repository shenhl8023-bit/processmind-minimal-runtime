import asyncio
import json
import shutil

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app import database
from app.database import Base, configure_sqlite_engine
from app.services.db_schema_maintenance import ensure_project_schema


LEGACY_MAPPING_TABLES = {
    "kmai_factor_mapping_usages",
    "kmai_factor_mapping_events",
    "kmai_factor_mappings",
}
BUSINESS_COLUMNS = (
    "manifest_json",
    "input_schema_json",
    "route_catalog_json",
    "route_rules_json",
    "test_cases_json",
    "rule_report_md",
    "content_hash",
)
SNAPSHOT_FIRST = {
    "mapping_id": 5,
    "mapping_identity": "project:5",
    "revision": 2,
    "scope": "project",
    "project_id": 7,
    "source_field": "cad.features",
    "source_value": "legacy slot",
    "mapping_mode": "existing_factor",
    "target_factor_key": "feature.slot_presence",
    "target_factor_name": "Slot presence",
    "target_factor_category": "feature",
}
SNAPSHOT_SECOND = {
    "mapping_id": None,
    "mapping_identity": "builtin:legacy-heat",
    "revision": 1,
    "scope": "builtin",
    "project_id": None,
    "source_field": "process.types",
    "source_value": "legacy heat",
    "mapping_mode": "manual_factor",
    "target_factor_key": "process.heat_treatment",
    "target_factor_name": "Heat treatment",
    "target_factor_category": "process",
}


async def _table_names(conn):
    return {
        row[0]
        for row in (
            await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))
        ).all()
    }


async def _read_business_columns(conn, package_id):
    columns = ", ".join(BUSINESS_COLUMNS)
    return (
        await conn.execute(
            text(f"SELECT {columns} FROM finalized_rule_packages WHERE id = :id"),
            {"id": package_id},
        )
    ).one()


async def _create_legacy_mapping_fixture(conn, *, usage_rows=None):
    await conn.run_sync(Base.metadata.create_all)
    for table_name in (
        "kmai_factor_mapping_usages",
        "kmai_factor_mapping_events",
        "kmai_factor_mappings",
    ):
        await conn.execute(text(f"DROP TABLE IF EXISTS {table_name}"))

    await conn.execute(text("""
        CREATE TABLE kmai_factor_mappings (
            id INTEGER PRIMARY KEY,
            scope TEXT NOT NULL DEFAULT 'project',
            project_id INTEGER,
            source_field TEXT NOT NULL,
            source_value TEXT NOT NULL,
            mapping_mode TEXT NOT NULL DEFAULT 'existing_factor',
            target_factor_key TEXT NOT NULL DEFAULT 'legacy',
            target_factor_name TEXT NOT NULL DEFAULT 'Legacy',
            target_factor_category TEXT NOT NULL DEFAULT 'legacy',
            status TEXT NOT NULL DEFAULT 'active',
            revision INTEGER NOT NULL DEFAULT 1,
            promoted_from_id INTEGER,
            created_by TEXT NOT NULL DEFAULT 'legacy',
            updated_by TEXT NOT NULL DEFAULT 'legacy',
            created_at DATETIME,
            updated_at DATETIME
        )
    """))
    await conn.execute(text("""
        CREATE TABLE kmai_factor_mapping_events (
            id INTEGER PRIMARY KEY,
            mapping_id INTEGER,
            project_id INTEGER,
            action TEXT NOT NULL
        )
    """))
    await conn.execute(text("""
        CREATE TABLE kmai_factor_mapping_usages (
            id INTEGER PRIMARY KEY,
            mapping_id INTEGER,
            package_id INTEGER NOT NULL,
            revision INTEGER NOT NULL,
            mapping_snapshot_json TEXT NOT NULL
        )
    """))
    await conn.execute(
        text("INSERT OR REPLACE INTO projects (id, name, status) VALUES (7, 'legacy', 'ROUTE_SET_READY')")
    )
    await conn.execute(text("""
        INSERT INTO finalized_rule_packages (
            id, project_id, version, package_name, schema_version, status,
            manifest_json, input_schema_json, route_catalog_json, route_rules_json,
            test_cases_json, rule_report_md, validation_report_json, content_hash
        ) VALUES (
            41, 7, 2, 'legacy-published', '2.0', 'published',
            :manifest_json, :input_schema_json,
            :route_catalog_json, :route_rules_json,
            :test_cases_json, '# exact report',
            :validation_report_json,
            'aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa'
        )
    """), {
        "manifest_json": '{"manifest":[1,2]}',
        "input_schema_json": '{"input":{"keep":true}}',
        "route_catalog_json": '{"routes":["one"]}',
        "route_rules_json": '{"rules":["two"]}',
        "test_cases_json": '[{"case":"fixed"}]',
        "validation_report_json": (
            '{"valid":true,"kmai_compatibility":{"factor_catalog_version":"legacy"}}'
        ),
    })
    await conn.execute(
        text("""
            INSERT INTO finalized_rule_packages (
                id, project_id, version, package_name, schema_version, status,
                validation_report_json, content_hash
            ) VALUES (
                42, 7, 1, 'legacy-superseded', '2.0', 'superseded',
                :validation_report_json,
                'bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb'
            )
        """),
        {
            "validation_report_json": (
                '{"kmai_compatibility":{"mapping_snapshot":[{"preserve":"exact"}]}}'
            )
        },
    )
    await conn.execute(
        text("""
            INSERT INTO kmai_factor_mappings (id, project_id, source_field, source_value)
            VALUES (5, 7, 'cad.features', 'legacy slot')
        """)
    )
    await conn.execute(
        text("""
            INSERT INTO kmai_factor_mapping_events (id, mapping_id, project_id, action)
            VALUES (8, 5, 7, 'created')
        """)
    )
    rows = usage_rows if usage_rows is not None else [
        (9, 5, 41, 1, json.dumps(SNAPSHOT_SECOND, separators=(",", ":"))),
        (3, 5, 41, 2, json.dumps(SNAPSHOT_FIRST, separators=(",", ":"))),
        (12, 5, 42, 1, '{"must":"not replace existing snapshot"}'),
    ]
    for usage_id, mapping_id, package_id, revision, snapshot_json in rows:
        await conn.execute(
            text("""
                INSERT INTO kmai_factor_mapping_usages
                    (id, mapping_id, package_id, revision, mapping_snapshot_json)
                VALUES (:id, :mapping_id, :package_id, :revision, :snapshot_json)
            """),
            {
                "id": usage_id,
                "mapping_id": mapping_id,
                "package_id": package_id,
                "revision": revision,
                "snapshot_json": snapshot_json,
            },
        )


def test_startup_preserves_duplicate_operations_factors_and_manual_chain(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'startup.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await conn.execute(
                    text("INSERT INTO projects (id, name, status) VALUES (1, 'startup', 'CREATED')")
                )
                await conn.execute(
                    text("""
                        INSERT INTO operations (id, project_id, name, sequence, chain)
                        VALUES
                            (1, 1, '重复工序', 1, 'manual-chain'),
                            (2, 1, '重复工序', 1, NULL),
                            (3, 1, '淬火', 2, '')
                    """)
                )
                await conn.execute(
                    text("""
                        INSERT INTO factors (id, operation_id, name)
                        VALUES (1, 1, '因素一'), (2, 2, '因素二')
                    """)
                )

                await ensure_project_schema(conn)
                await ensure_project_schema(conn)

                operations = (
                    await conn.execute(
                        text("SELECT id, chain FROM operations ORDER BY id")
                    )
                ).all()
                factor_count = (
                    await conn.execute(text("SELECT COUNT(*) FROM factors"))
                ).scalar_one()
                audit_count = (
                    await conn.execute(
                        text("""
                            SELECT COUNT(*)
                            FROM schema_maintenance_audit
                            WHERE migration_name = 'operations_identity_duplicates_audit_v1'
                        """)
                    )
                ).scalar_one()

            assert operations == [
                (1, "manual-chain"),
                (2, "other"),
                (3, "heat"),
            ]
            assert factor_count == 2
            assert audit_count == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_sqlite_connections_enable_foreign_keys(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'foreign-keys.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                enabled = (await conn.execute(text("PRAGMA foreign_keys"))).scalar_one()
                assert enabled == 1

            with pytest.raises(IntegrityError):
                async with engine.begin() as conn:
                    await conn.execute(
                        text("INSERT INTO factors (operation_id, name) VALUES (999, 'orphan')")
                    )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_startup_backfills_legacy_mapping_snapshots_then_retires_tables(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mapping-retirement.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await _create_legacy_mapping_fixture(conn)
                before_business_columns = await _read_business_columns(conn, 41)
                preserved_report = (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=42")
                    )
                ).scalar_one()

            async with engine.begin() as conn:
                await ensure_project_schema(conn)

            async with engine.connect() as conn:
                assert not (LEGACY_MAPPING_TABLES & await _table_names(conn))
                report = json.loads((await conn.execute(text(
                    "SELECT validation_report_json FROM finalized_rule_packages WHERE id=41"
                ))).scalar_one())
                assert report["kmai_compatibility"]["mapping_snapshot"] == [
                    SNAPSHOT_FIRST,
                    SNAPSHOT_SECOND,
                ]
                assert await _read_business_columns(conn, 41) == before_business_columns
                assert (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=42")
                    )
                ).scalar_one() == preserved_report
                assert (
                    await conn.execute(text("""
                        SELECT COUNT(*) FROM schema_migrations
                        WHERE name = 'retire_kmai_factor_mappings_v1'
                    """))
                ).scalar_one() == 1
        finally:
            await engine.dispose()

    asyncio.run(run())


@pytest.mark.parametrize("invalid_snapshot", ["not-json", "[]", "null"])
def test_kmai_invalid_legacy_usage_snapshot_rolls_back_every_change(tmp_path, invalid_snapshot):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'invalid-usage.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await _create_legacy_mapping_fixture(
                    conn,
                    usage_rows=[(3, 5, 41, 1, invalid_snapshot)],
                )
                original_report = (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=41")
                    )
                ).scalar_one()

            with pytest.raises(RuntimeError):
                async with engine.begin() as conn:
                    await ensure_project_schema(conn)

            async with engine.connect() as conn:
                assert LEGACY_MAPPING_TABLES <= await _table_names(conn)
                assert (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=41")
                    )
                ).scalar_one() == original_report
                assert (
                    await conn.execute(text("""
                        SELECT COUNT(*) FROM schema_migrations
                        WHERE name = 'retire_kmai_factor_mappings_v1'
                    """))
                ).scalar_one() == 0
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_kmai_orphan_legacy_usage_rolls_back_every_change(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'orphan-usage.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await _create_legacy_mapping_fixture(
                    conn,
                    usage_rows=[(
                        3,
                        5,
                        999,
                        1,
                        json.dumps(SNAPSHOT_FIRST, separators=(",", ":")),
                    )],
                )

            with pytest.raises(RuntimeError):
                async with engine.begin() as conn:
                    await ensure_project_schema(conn)

            async with engine.connect() as conn:
                assert LEGACY_MAPPING_TABLES <= await _table_names(conn)
                assert (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=41")
                    )
                ).scalar_one() == (
                    '{"valid":true,"kmai_compatibility":{"factor_catalog_version":"legacy"}}'
                )
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_kmai_partially_present_legacy_tables_are_preserved_and_rejected(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'partial-mapping.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await _create_legacy_mapping_fixture(conn)
                await conn.execute(text("DROP TABLE kmai_factor_mapping_events"))

            with pytest.raises(RuntimeError, match="partially present"):
                async with engine.begin() as conn:
                    await ensure_project_schema(conn)

            async with engine.connect() as conn:
                tables = await _table_names(conn)
                assert "kmai_factor_mapping_usages" in tables
                assert "kmai_factor_mappings" in tables
                assert "kmai_factor_mapping_events" not in tables
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_kmai_verification_mismatch_rolls_back_backfill_and_drops(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'verification-mismatch.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await _create_legacy_mapping_fixture(conn)
                await conn.execute(text("""
                    CREATE TRIGGER discard_mapping_snapshot_backfill
                    AFTER UPDATE OF validation_report_json ON finalized_rule_packages
                    WHEN NEW.id = 41
                    BEGIN
                        UPDATE finalized_rule_packages
                        SET validation_report_json = OLD.validation_report_json
                        WHERE id = NEW.id;
                    END
                """))
                original_report = (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=41")
                    )
                ).scalar_one()

            with pytest.raises(RuntimeError, match="verification"):
                async with engine.begin() as conn:
                    await ensure_project_schema(conn)

            async with engine.connect() as conn:
                assert LEGACY_MAPPING_TABLES <= await _table_names(conn)
                assert (
                    await conn.execute(
                        text("SELECT validation_report_json FROM finalized_rule_packages WHERE id=41")
                    )
                ).scalar_one() == original_report
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_fresh_and_repeated_startup_never_creates_mapping_tables(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'fresh-startup.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await ensure_project_schema(conn)
                await ensure_project_schema(conn)
                assert not (LEGACY_MAPPING_TABLES & await _table_names(conn))
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_kmai_init_db_twice_retires_a_copied_legacy_fixture(tmp_path, monkeypatch):
    source_path = tmp_path / "source-legacy.db"
    copied_path = tmp_path / "copied-legacy.db"

    async def build_source():
        source_engine = create_async_engine(f"sqlite+aiosqlite:///{source_path}")
        configure_sqlite_engine(source_engine)
        try:
            async with source_engine.begin() as conn:
                await _create_legacy_mapping_fixture(conn)
        finally:
            await source_engine.dispose()

    asyncio.run(build_source())
    shutil.copy2(source_path, copied_path)

    copied_engine = create_async_engine(f"sqlite+aiosqlite:///{copied_path}")
    configure_sqlite_engine(copied_engine)
    monkeypatch.setattr(database, "engine", copied_engine)
    monkeypatch.setattr(database, "DATABASE_URL", f"sqlite+aiosqlite:///{copied_path}")
    monkeypatch.setattr(database, "IS_SQLITE", True)

    async def start_twice():
        try:
            for _ in range(2):
                await database.init_db()
                async with copied_engine.connect() as conn:
                    assert (await conn.execute(text("SELECT COUNT(*) FROM projects"))).scalar_one() == 1
                    assert (
                        await conn.execute(text("SELECT COUNT(*) FROM finalized_rule_packages"))
                    ).scalar_one() == 2
                    assert not (LEGACY_MAPPING_TABLES & await _table_names(conn))
        finally:
            await copied_engine.dispose()

    asyncio.run(start_twice())
