import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import Project
from app.services.db_schema_maintenance import ensure_project_schema


@pytest.fixture
def lifecycle_client(tmp_path):
    database_path = tmp_path / "lifecycle.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            session.add(Project(id=12, name="规则包生命周期测试"))
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _v2_save_payload(package):
    return {
        "project_id": package["manifest"]["project_id"],
        "route_version_id": package["manifest"]["route_version_id"],
        "package_name": package["manifest"]["package_name"],
        "schema_version": "2.0",
        "manifest": package["manifest"],
        "input_schema": package["input_schema"],
        "route_catalog": package["route_catalog"],
        "route_rules": package["route_rules"],
        "test_cases": package["test_cases"],
        "rule_report_md": "# V2 规则包测试报告",
    }


def _v1_save_payload():
    return {
        "project_id": 12,
        "package_name": "legacy_rules",
        "input_schema": {"required_inputs": [{"key": "material_grade"}]},
        "route_catalog": {"segments": [{"process_id": "prepare", "process_name": "准备", "main": True}]},
        "route_rules": {"process_trigger_rules": [{"rule_id": "main", "process_id": "prepare", "main": True}]},
        "rule_report_md": "# V1 规则包测试报告",
    }


def test_v2_save_publishes_and_v1_replaces_current_package(lifecycle_client, rule_package_v2_payload):
    saved_v2 = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert saved_v2.status_code == 200
    v2 = saved_v2.json()
    assert v2["status"] == "published"
    assert v2["validation_report"]["valid"] is True
    assert len(v2["content_hash"]) == 64

    latest_v2 = lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )
    assert latest_v2.status_code == 200
    assert latest_v2.json()["id"] == v2["id"]

    saved_v1 = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v1_save_payload())
    assert saved_v1.status_code == 200
    assert saved_v1.json()["status"] == "published"
    assert saved_v1.json()["schema_version"] == "1.0"

    versions = lifecycle_client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    )
    assert versions.status_code == 200
    statuses = {item["id"]: item["status"] for item in versions.json()}
    assert statuses[v2["id"]] == "superseded"
    assert statuses[saved_v1.json()["id"]] == "published"

    latest = lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == saved_v1.json()["id"]


def test_invalid_v2_cannot_be_saved(lifecycle_client, rule_package_v2_payload):
    rule_package_v2_payload["route_rules"]["rules"][0]["then"]["include_process_ids"] = ["missing_process"]
    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )

    assert saved.status_code == 422
    assert saved.json()["detail"]["validation"]["valid"] is False


def test_migration_backfills_legacy_version_status_and_hash(tmp_path):
    database_path = tmp_path / "legacy.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def run_migration():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("DROP TABLE finalized_rule_packages"))
            await conn.execute(text("""
                CREATE TABLE finalized_rule_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id INTEGER NOT NULL,
                    route_version_id INTEGER,
                    version INTEGER NOT NULL,
                    package_name VARCHAR(255) NOT NULL,
                    input_schema_json TEXT,
                    route_catalog_json TEXT,
                    route_rules_json TEXT,
                    rule_report_md TEXT,
                    validation_report_json TEXT,
                    created_by VARCHAR(100),
                    created_at DATETIME
                )
            """))
            await conn.execute(text("""
                INSERT INTO finalized_rule_packages
                    (project_id, version, package_name, input_schema_json, route_catalog_json,
                     route_rules_json, rule_report_md, created_by, created_at)
                VALUES
                    (1, 1, 'rules-v1', '{}', '{}', '{}', '# v1', 'user', CURRENT_TIMESTAMP),
                    (1, 2, 'rules-v2', '{}', '{}', '{}', '# v2', 'user', CURRENT_TIMESTAMP)
            """))
            await ensure_project_schema(conn)
            rows = (
                await conn.execute(text("""
                    SELECT version, status, schema_version, content_hash
                    FROM finalized_rule_packages
                    ORDER BY version
                """))
            ).mappings().all()
        await engine.dispose()
        return rows

    rows = asyncio.run(run_migration())

    assert [row["status"] for row in rows] == ["superseded", "published"]
    assert [row["schema_version"] for row in rows] == ["1.0", "1.0"]
    assert all(len(row["content_hash"]) == 64 for row in rows)


def test_migration_normalizes_existing_duplicate_published_rows(tmp_path):
    database_path = tmp_path / "duplicate-published.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def run_migration():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("""
                INSERT INTO finalized_rule_packages
                    (project_id, version, package_name, schema_version, status,
                     input_schema_json, route_catalog_json, route_rules_json, rule_report_md)
                VALUES
                    (7, 1, 'old', '1.0', 'published', '{}', '{}', '{}', '# old'),
                    (7, 2, 'new', '1.0', 'published', '{}', '{}', '{}', '# new')
            """))
            await ensure_project_schema(conn)
            rows = (
                await conn.execute(text("""
                    SELECT version, status
                    FROM finalized_rule_packages
                    WHERE project_id = 7
                    ORDER BY version
                """))
            ).mappings().all()
        await engine.dispose()
        return rows

    rows = asyncio.run(run_migration())

    assert [row["status"] for row in rows] == ["superseded", "published"]
