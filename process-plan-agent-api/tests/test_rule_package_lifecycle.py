import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, KmaiFactorMappingUsage, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
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
            session.add(Project(id=12, name="规则包生命周期测试", status="ROUTE_SET_READY"))
            session.add(NormalizedRouteVersion(
                id=31,
                project_id=12,
                version=1,
                route_json="[]",
            ))
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


def _append_unknown_feature_rule(package, source_value="\u5b54\u7c7b\u7ed3\u6784"):
    payload = deepcopy(package)
    payload["route_rules"]["rules"].append(
        {
            "rule_id": "feature.unknown.custom",
            "priority": 80,
            "enabled": True,
            "when": {"field": "cad.features", "op": "contains", "value": source_value},
            "then": {
                "include_process_ids": ["process_mill_slot"],
                "exclude_process_ids": [],
                "reason": "custom feature mapping",
            },
        }
    )
    return payload


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


def test_save_requires_mapping_and_persists_authoritative_snapshot(lifecycle_client, rule_package_v2_payload):
    package = _append_unknown_feature_rule(rule_package_v2_payload)
    rejected = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(package),
    )
    assert rejected.status_code == 422
    rejected_detail = rejected.json()["detail"]
    assert rejected_detail["kmai_compatibility"]["valid"] is False
    assert any(
        issue["field"] == "cad.features" and issue["value"] == "\u5b54\u7c7b\u7ed3\u6784"
        for issue in rejected_detail["kmai_compatibility"]["errors"]
    )

    mapping = lifecycle_client.post(
        "/api/kmai-factor-mappings",
        json={
            "scope": "project",
            "project_id": 12,
            "source_field": "cad.features",
            "source_value": "\u5b54\u7c7b\u7ed3\u6784",
            "mapping_mode": "manual_factor",
            "target_factor_name": "孔类结构",
        },
    )
    assert mapping.status_code == 200

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(package),
    )
    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
    assert any(
        condition["factor_key"] == mapping.json()["target_factor_key"]
        for rule in saved_body["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        for condition in rule["when"]["all"]
    )

    async def persisted_snapshot():
        async with lifecycle_client.lifecycle_session_factory() as db:
            packages = (await db.execute(select(FinalizedRulePackage))).scalars().all()
            usages = (
                await db.execute(
                    select(KmaiFactorMappingUsage)
                    .where(KmaiFactorMappingUsage.package_id == saved_body["id"])
                    .order_by(KmaiFactorMappingUsage.id)
                )
            ).scalars().all()
            return packages, usages

    packages, usages = asyncio.run(persisted_snapshot())
    assert len(packages) == 1
    assert packages[0].status == "published"
    snapshots = [json.loads(row.mapping_snapshot_json) for row in usages]
    assert snapshots
    assert len(snapshots) == len(saved_body["kmai_compatibility"]["mapping_usages"])
    assert saved_body["validation_report"]["kmai_compatibility"]["mapping_snapshot"] == snapshots


def test_compile_and_save_use_authoritative_mapping_snapshot(lifecycle_client, rule_package_v2_payload):
    mapping = lifecycle_client.post(
        "/api/kmai-factor-mappings",
        json={
            "scope": "project",
            "project_id": 12,
            "source_field": "cad.features",
            "source_value": "\u69fd\u7c7b\u7279\u5f81",
            "mapping_mode": "existing_factor",
            "target_factor_key": "has_flat_or_plane",
        },
    )
    assert mapping.status_code == 200
    mapping_id = mapping.json()["mapping_id"]

    compile_response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compile",
        json={
            "project_id": 12,
            "package_name": rule_package_v2_payload["manifest"]["package_name"],
            "route_version_id": 31,
            "applicability": rule_package_v2_payload["manifest"]["applicability"],
            "fields": rule_package_v2_payload["input_schema"]["fields"],
            "processes": rule_package_v2_payload["route_catalog"]["processes"],
            "rules": rule_package_v2_payload["route_rules"]["rules"],
            "test_cases": rule_package_v2_payload["test_cases"],
        },
    )
    assert compile_response.status_code == 200
    compiled = compile_response.json()
    slot_rule = next(
        item
        for item in compiled["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if item["rule_id"] == "feature.slot.mill"
    )
    assert slot_rule["when"]["all"][0]["factor_key"] == "has_flat_or_plane"

    changed = lifecycle_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={
            "expected_revision": 1,
            "mapping_mode": "existing_factor",
            "target_factor_key": "requires_honing",
        },
    )
    assert changed.status_code == 200

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(compiled["package"]),
    )
    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["kmai_compatibility"]["mapping_signature"] != compiled["kmai_compatibility"]["mapping_signature"]
    assert saved_body["kmai_compatibility"]["files"] != compiled["kmai_compatibility"]["files"]
    changed_slot_rule = next(
        item
        for item in saved_body["kmai_compatibility"]["files"]["route_rules.json"]["rules"]
        if item["rule_id"] == "feature.slot.mill"
    )
    assert changed_slot_rule["when"]["all"][0]["factor_key"] == "requires_honing"

    async def usages():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return [
                row.mapping_id
                for row in (
                    await db.execute(
                        select(KmaiFactorMappingUsage).where(
                            KmaiFactorMappingUsage.package_id == saved_body["id"]
                        )
                    )
                ).scalars().all()
            ]

    assert asyncio.run(usages()) == [mapping_id]

    async def stored_snapshot():
        async with lifecycle_client.lifecycle_session_factory() as db:
            usage = (
                await db.execute(
                    select(KmaiFactorMappingUsage).where(
                        KmaiFactorMappingUsage.package_id == saved_body["id"]
                    )
                )
            ).scalar_one()
            return json.loads(usage.mapping_snapshot_json)

    snapshot = asyncio.run(stored_snapshot())
    assert snapshot["target_factor_key"] == "requires_honing"
    assert snapshot["revision"] == 2
    assert saved_body["validation_report"]["kmai_compatibility"]["mapping_snapshot"] == [snapshot]

    edited_again = lifecycle_client.put(
        f"/api/kmai-factor-mappings/{mapping_id}",
        json={
            "expected_revision": 2,
            "mapping_mode": "existing_factor",
            "target_factor_key": "has_flat_or_plane",
        },
    )
    assert edited_again.status_code == 200

    compatibility = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={
            "project_id": 12,
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert compatibility.status_code == 200
    assert "feature.slot.mill" in compatibility.json()["kmai_matched_rule_ids"]
    assert compatibility.json()["manual_factors"]["requires_honing"] is True
    assert compatibility.json()["manual_factors"]["has_flat_or_plane"] is False
    assert asyncio.run(stored_snapshot()) == snapshot


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


def test_compatibility_test_uses_builtin_fallback_for_legacy_package(
    lifecycle_client,
    rule_package_v2_payload,
):
    mapping = lifecycle_client.post(
        "/api/kmai-factor-mappings",
        json={
            "scope": "project",
            "project_id": 12,
            "source_field": "cad.features",
            "source_value": "\u69fd\u7c7b\u7279\u5f81",
            "mapping_mode": "existing_factor",
            "target_factor_key": "requires_honing",
        },
    )
    assert mapping.status_code == 200
    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert saved.status_code == 200

    async def remove_usage_rows():
        async with lifecycle_client.lifecycle_session_factory() as db:
            await db.execute(
                delete(KmaiFactorMappingUsage).where(
                    KmaiFactorMappingUsage.package_id == saved.json()["id"]
                )
            )
            await db.commit()

    asyncio.run(remove_usage_rows())
    compatibility = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={
            "project_id": 12,
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert compatibility.status_code == 200
    assert compatibility.json()["manual_factors"]["has_slot_feature"] is True
    assert compatibility.json()["manual_factors"]["requires_honing"] is False
