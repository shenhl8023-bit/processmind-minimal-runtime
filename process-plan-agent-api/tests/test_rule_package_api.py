import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.services.db_schema_maintenance import ensure_project_schema


client = TestClient(app)


@pytest.fixture(autouse=True)
def isolated_rule_package_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rule-package-api.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    try:
        yield
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _compile_payload(package_payload):
    return {
        "project_id": package_payload["manifest"]["project_id"],
        "package_name": package_payload["manifest"]["package_name"],
        "route_version_id": package_payload["manifest"]["route_version_id"],
        "applicability": package_payload["manifest"]["applicability"],
        "fields": package_payload["input_schema"]["fields"],
        "processes": package_payload["route_catalog"]["processes"],
        "rules": package_payload["route_rules"]["rules"],
        "test_cases": package_payload["test_cases"],
    }


def test_compile_validate_and_simulate_endpoints(rule_package_v2_payload):
    compiled = client.post(
        "/api/extract/finalized-rule-packages/compile",
        json=_compile_payload(rule_package_v2_payload),
    )
    assert compiled.status_code == 200
    compiled_body = compiled.json()
    assert compiled_body["validation"]["valid"] is True
    assert compiled_body["package"]["manifest"]["schema_version"] == "2.0"
    assert len(compiled_body["content_hash"]) == 64

    validated = client.post(
        "/api/extract/finalized-rule-packages/validate",
        json=compiled_body["package"],
    )
    assert validated.status_code == 200
    assert validated.json()["test_results"][0]["passed"] is True

    simulated = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": compiled_body["package"],
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert simulated.status_code == 200
    assert simulated.json()["plan"]["selected_process_ids"] == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]


def test_contract_rejects_unknown_condition_operator(rule_package_v2_payload):
    rule_package_v2_payload["route_rules"]["rules"][0]["when"] = {
        "field": "material.grade",
        "op": "regex",
        "value": ".*",
    }

    response = client.post(
        "/api/extract/finalized-rule-packages/validate",
        json=rule_package_v2_payload,
    )

    assert response.status_code == 422


def test_simulate_rejects_missing_required_input(rule_package_v2_payload):
    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {"material": {"grade": "9Cr18"}},
        },
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["code"] == "required_input_missing"
    assert error["field"] == "cad.features"
    assert error["reason"] == error["message"]
    assert error["allowed_values"] == []


def test_simulate_rejects_non_string_multi_select_item(rule_package_v2_payload):
    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": [123]},
            },
        },
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["code"] == "input_type_mismatch"
    assert error["field"] == "cad.features"
    assert error["reason"] == error["message"]
    assert error["allowed_values"] == []


def test_simulate_rejects_invalid_option_with_allowed_values(rule_package_v2_payload):
    material_field = next(
        field
        for field in rule_package_v2_payload["input_schema"]["fields"]
        if field["key"] == "material.grade"
    )
    material_field.update(
        {
            "type": "single_select",
            "options": [
                {"value": "9Cr18", "label": "9Cr18", "aliases": []},
                {"value": "95Cr18", "label": "95Cr18", "aliases": []},
            ],
            "allow_custom": False,
        }
    )

    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {
                "material": {"grade": "SUS304"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 422
    error = response.json()["detail"][0]
    assert error["code"] == "input_option_invalid"
    assert error["field"] == "material.grade"
    assert error["allowed_values"] == ["9Cr18", "95Cr18"]


def test_simulate_uses_canonical_option_value_for_rule_evaluation(rule_package_v2_payload):
    material_field = next(
        field
        for field in rule_package_v2_payload["input_schema"]["fields"]
        if field["key"] == "material.grade"
    )
    material_field.update(
        {
            "type": "single_select",
            "options": [{"value": "9Cr18", "label": "9Cr18", "aliases": ["X105CrMo17"]}],
            "allow_custom": False,
        }
    )

    response = client.post(
        "/api/extract/finalized-rule-packages/simulate",
        json={
            "package": rule_package_v2_payload,
            "inputs": {
                "material": {"grade": "X105CrMo17"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 200
    assert "process_quench" in response.json()["plan"]["selected_process_ids"]
