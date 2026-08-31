import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import create_async_engine

from app.database import Base, configure_sqlite_engine
from app.services.db_schema_maintenance import ensure_project_schema


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


def test_startup_does_not_create_retired_kmai_tables(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'no-kmai.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await ensure_project_schema(conn)
                table_names = {
                    row[0]
                    for row in (
                        await conn.execute(
                            text("SELECT name FROM sqlite_master WHERE type = 'table'")
                        )
                    ).all()
                }
            assert not {
                "kmai_factor_mappings",
                "kmai_factor_mapping_events",
                "kmai_factor_mapping_usages",
            } & table_names
        finally:
            await engine.dispose()

    asyncio.run(run())
