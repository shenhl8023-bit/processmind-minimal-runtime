import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1
from app.services.rule_packages.kmai_export import builtin_legacy_mapping_snapshot
from app.services.rule_packages.lifecycle import publish_rule_package


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
            session.add(Project(id=12, name="Lifecycle", status="ROUTE_SET_READY"))
            session.add(NormalizedRouteVersion(id=31, project_id=12, version=1, route_json="[]"))
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    client.lifecycle_session_factory = session_factory
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
        "rule_report_md": "# report",
    }


def _compile_payload(package):
    return {
        "project_id": package["manifest"]["project_id"],
        "package_name": package["manifest"]["package_name"],
        "route_version_id": package["manifest"]["route_version_id"],
        "applicability": package["manifest"]["applicability"],
        "fields": package["input_schema"]["fields"],
        "processes": package["route_catalog"]["processes"],
        "rules": package["route_rules"]["rules"],
        "test_cases": package["test_cases"],
    }


def test_new_package_persists_catalog_version(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))

    assert saved.status_code == 200
    body = saved.json()
    assert body["validation_report"]["kmai_compatibility"] == {"factor_catalog_version": "2026.11"}


def test_compile_and_save_use_immutable_standard_factor(lifecycle_client, rule_package_v2_payload):
    compiled = lifecycle_client.post("/api/extract/finalized-rule-packages/compile", json=_compile_payload(rule_package_v2_payload))
    assert compiled.status_code == 200
    compiled_slot = next(
        rule for rule in compiled.json()["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if rule["rule_id"] == "feature.slot.mill"
    )
    assert compiled_slot["when"]["all"][0]["factor_key"] == "has_slot_feature"

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    saved_slot = next(
        rule for rule in saved.json()["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if rule["rule_id"] == "feature.slot.mill"
    )
    assert saved_slot["when"]["all"][0]["factor_key"] == "has_slot_feature"


def _set_historical_rule(lifecycle_client, package_id, *, snapshot, source_value="\u69fd\u7c7b\u7279\u5f81"):
    async def update():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = (await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.id == package_id))).scalar_one()
            rules = json.loads(row.route_rules_json)
            slot = next(rule for rule in rules["rules"] if rule["rule_id"] == "feature.slot.mill")
            slot["when"].pop("factor_id", None)
            slot["when"]["value"] = source_value
            row.route_rules_json = json.dumps(rules, ensure_ascii=True)
            compatibility = {"mapping_snapshot": snapshot} if snapshot is not None else {}
            row.validation_report_json = json.dumps({"kmai_compatibility": compatibility})
            await db.commit()

    asyncio.run(update())


def test_historical_compatibility_uses_snapshot_embedded_in_package(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    snapshot = [{
        "mapping_identity": "project:7",
        "revision": 3,
        "scope": "project",
        "project_id": 12,
        "source_field": "cad.features",
        "source_value": "\u69fd\u7c7b\u7279\u5f81",
        "mapping_mode": "existing_factor",
        "target_factor_key": "requires_honing",
        "target_factor_name": "Honing",
        "target_factor_category": "precision",
    }]
    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=snapshot)

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )

    assert response.status_code == 200
    assert response.json()["manual_factors"]["requires_honing"] is True
    assert response.json()["manual_factors"]["has_flat_or_plane"] is False


def test_snapshotless_historical_package_has_no_report_adapters(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=None)

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )
    assert response.status_code == 200
    assert "has_slot_feature" not in response.json()["manual_factors"]

    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=None, source_value="unknown old value")
    async def legacy_package():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = (await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.id == saved.json()["id"]))).scalar_one()
            return RulePackageV2.model_validate({
                "manifest": json.loads(row.manifest_json),
                "input_schema": json.loads(row.input_schema_json),
                "route_catalog": json.loads(row.route_catalog_json),
                "route_rules": json.loads(row.route_rules_json),
                "test_cases": json.loads(row.test_cases_json),
            })

    blocked = compare_kmai_v1(
        asyncio.run(legacy_package()),
        {"material": {"grade": "9Cr18"}, "cad": {"features": ["unknown old value"]}, "target_hardness_hrc": 58},
        legacy_mapping_snapshot=builtin_legacy_mapping_snapshot(),
    )
    assert [issue["code"] for issue in blocked["errors"]] == ["standard_factor_unbound"]


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
                    project_id INTEGER NOT NULL, route_version_id INTEGER,
                    version INTEGER NOT NULL, package_name VARCHAR(255) NOT NULL,
                    input_schema_json TEXT, route_catalog_json TEXT, route_rules_json TEXT,
                    rule_report_md TEXT, validation_report_json TEXT, created_by VARCHAR(100), created_at DATETIME
                )
            """))
            await conn.execute(text("""
                INSERT INTO finalized_rule_packages
                    (project_id, version, package_name, input_schema_json, route_catalog_json, route_rules_json, rule_report_md, created_by, created_at)
                VALUES (1, 1, 'rules-v1', '{}', '{}', '{}', '# v1', 'user', CURRENT_TIMESTAMP),
                       (1, 2, 'rules-v2', '{}', '{}', '{}', '# v2', 'user', CURRENT_TIMESTAMP)
            """))
            await ensure_project_schema(conn)
            rows = (await conn.execute(text("""
                SELECT version, status, schema_version, content_hash
                FROM finalized_rule_packages ORDER BY version
            """))).mappings().all()
        await engine.dispose()
        return rows

    rows = asyncio.run(run_migration())

    assert [row["status"] for row in rows] == ["superseded", "published"]
    assert [row["schema_version"] for row in rows] == ["1.0", "1.0"]
    assert all(len(row["content_hash"]) == 64 for row in rows)


def test_publish_helper_does_not_commit_before_caller(lifecycle_client, rule_package_v2_payload):
    async def exercise():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = FinalizedRulePackage(
                project_id=12,
                route_version_id=31,
                version=1,
                package_name="transactional",
                schema_version="2.0",
                status="draft",
                manifest_json=json.dumps(rule_package_v2_payload["manifest"]),
                input_schema_json=json.dumps(rule_package_v2_payload["input_schema"]),
                route_catalog_json=json.dumps(rule_package_v2_payload["route_catalog"]),
                route_rules_json=json.dumps(rule_package_v2_payload["route_rules"]),
                test_cases_json=json.dumps(rule_package_v2_payload["test_cases"]),
                rule_report_md="# report",
                validation_report_json="{}",
                content_hash="x" * 64,
                created_by="tester",
            )
            db.add(row)
            await db.flush()
            await publish_rule_package(row, db, actor="tester")
            await db.rollback()
        async with lifecycle_client.lifecycle_session_factory() as db:
            return (await db.execute(select(FinalizedRulePackage))).scalars().all()

    assert asyncio.run(exercise()) == []
