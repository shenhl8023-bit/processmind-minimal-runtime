import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, KmaiFactorMappingUsage, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.kmai_compatibility_runner import compare_kmai_v1
from app.services.rule_packages.kmai_export import builtin_legacy_mapping_snapshot


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


def test_new_package_persists_catalog_version_without_mapping_usage(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))

    assert saved.status_code == 200
    body = saved.json()
    assert body["validation_report"]["kmai_compatibility"] == {"factor_catalog_version": "2026.11"}

    async def usage_rows():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return (await db.execute(
                select(KmaiFactorMappingUsage).where(KmaiFactorMappingUsage.package_id == body["id"])
            )).scalars().all()

    assert asyncio.run(usage_rows()) == []


def test_compile_and_save_ignore_contradictory_active_mapping(lifecycle_client, rule_package_v2_payload):
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

    changed = lifecycle_client.post(
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
    assert changed.status_code == 200

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )

    assert response.status_code == 200
    assert response.json()["manual_factors"]["requires_honing"] is True
    assert response.json()["manual_factors"]["has_flat_or_plane"] is False


def test_snapshotless_historical_package_uses_only_fixed_legacy_builtins(lifecycle_client, rule_package_v2_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=_v2_save_payload(rule_package_v2_payload))
    assert saved.status_code == 200
    _set_historical_rule(lifecycle_client, saved.json()["id"], snapshot=None)

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/compatibility-test",
        json={"project_id": 12, "inputs": {"material": {"grade": "9Cr18"}, "cad": {"features": ["\u69fd\u7c7b\u7279\u5f81"]}, "target_hardness_hrc": 58}},
    )
    assert response.status_code == 200
    assert response.json()["manual_factors"]["has_slot_feature"] is True

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
