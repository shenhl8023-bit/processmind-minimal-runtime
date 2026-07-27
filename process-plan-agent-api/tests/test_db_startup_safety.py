import asyncio

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, configure_sqlite_engine
from app.models.models import KmaiFactorMapping, KmaiFactorMappingEvent, Project
from app.routers import projects as projects_router
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


def test_mapping_schema_cascades_project_rows_without_removing_global_rows(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'mapping-delete.db'}")
        configure_sqlite_engine(engine)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await ensure_project_schema(conn)
                await conn.execute(text("INSERT INTO projects (id, name) VALUES (1, 'project')"))
                await conn.execute(text("""
                    INSERT INTO kmai_factor_mappings
                    (scope, project_id, source_field, source_value, mapping_mode,
                     target_factor_key, target_factor_name, target_factor_category)
                    VALUES
                    ('global', NULL, 'cad.features', 'global', 'existing_factor', 'global_key', 'Global', 'cad'),
                    ('project', 1, 'cad.features', 'project', 'existing_factor', 'project_key', 'Project', 'cad')
                """))
                await conn.execute(text("""
                    INSERT INTO kmai_factor_mapping_events
                    (mapping_id, project_id, action, actor, before_json, after_json)
                    VALUES (2, 1, 'created', 'tester', '{"before": null}', '{"after": 2}')
                """))
                await conn.execute(text("""
                    INSERT INTO finalized_rule_packages
                    (id, project_id, version, package_name, schema_version, status)
                    VALUES (1, 1, 1, 'pkg', '1.0', 'published')
                """))
                await conn.execute(text("""
                    INSERT INTO kmai_factor_mapping_usages
                    (mapping_id, package_id, revision, mapping_snapshot_json)
                    VALUES (2, 1, 1, '{"mapping_id": 2}')
                """))
                await conn.execute(text("DELETE FROM finalized_rule_packages WHERE id = 1"))
                await conn.execute(text("DELETE FROM projects WHERE id = 1"))
                rows = (await conn.execute(text("SELECT scope FROM kmai_factor_mappings ORDER BY id"))).all()
                assert rows == [("global",)]
                assert (await conn.execute(text("SELECT COUNT(*) FROM kmai_factor_mapping_events"))).scalar_one() == 0
                assert (await conn.execute(text("SELECT COUNT(*) FROM kmai_factor_mapping_usages"))).scalar_one() == 0
        finally:
            await engine.dispose()

    asyncio.run(run())


def test_project_delete_removes_mapping_event_without_project_id(tmp_path):
    async def run():
        engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'project-delete.db'}")
        configure_sqlite_engine(engine)
        session_factory = async_sessionmaker(engine, expire_on_commit=False)
        try:
            async with engine.begin() as conn:
                await conn.run_sync(Base.metadata.create_all)
                await ensure_project_schema(conn)

            async with session_factory() as db:
                project = Project(name="project")
                global_mapping = KmaiFactorMapping(
                    scope="global",
                    source_field="cad.features",
                    source_value="global",
                    mapping_mode="existing_factor",
                    target_factor_key="global_key",
                    target_factor_name="Global",
                    target_factor_category="cad",
                )
                project_mapping = KmaiFactorMapping(
                    scope="project",
                    project=project,
                    source_field="cad.features",
                    source_value="project",
                    mapping_mode="existing_factor",
                    target_factor_key="project_key",
                    target_factor_name="Project",
                    target_factor_category="cad",
                )
                db.add_all([project, global_mapping, project_mapping])
                await db.flush()
                db.add(
                    KmaiFactorMappingEvent(
                        mapping_id=project_mapping.id,
                        project_id=None,
                        action="created",
                        actor="tester",
                        before_json='{"before": null}',
                        after_json='{"after": 1}',
                    )
                )
                await db.commit()

                await projects_router.delete_project(project.id, db=db)

                assert (await db.execute(text("SELECT COUNT(*) FROM kmai_factor_mapping_events"))).scalar_one() == 0
                assert (await db.execute(text("SELECT scope FROM kmai_factor_mappings"))).all() == [("global",)]
        finally:
            await engine.dispose()

    asyncio.run(run())
