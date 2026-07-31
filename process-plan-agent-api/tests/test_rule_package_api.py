import asyncio
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.standard_factors import STANDARD_FACTOR_CATALOG_VERSION


client = TestClient(app)


def test_retired_mapping_api_is_not_registered():
    assert client.get("/api/kmai-factor-mappings").status_code == 404
    assert client.post("/api/kmai-factor-mappings", json={}).status_code == 404


def test_condition_field_registry_returns_versioned_standard_factors():
    """Fails if the sole confirmation registry omits its standard-factor contract."""
    response = client.get("/api/extract/finalized-rule-packages/condition-fields")

    assert response.status_code == 200
    body = response.json()
    assert body["version"] == STANDARD_FACTOR_CATALOG_VERSION
    assert body["factors"]
    center = next(item for item in body["factors"] if item["factor_id"] == "feature.center_hole_location")
    assert center["source_field"] == "cad.features"
    assert center["canonical_value"] == "顶尖孔"
    assert center["kmai_factor_key"] == "uses_center_hole_location"


@pytest.fixture(autouse=True)
def isolated_rule_package_db(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rule-package-api.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            session.add_all([
                Project(id=12, name="规则包 API 测试", status="ROUTE_SET_READY"),
                NormalizedRouteVersion(
                    id=31,
                    project_id=12,
                    version=1,
                    route_json="[]",
                ),
            ])
            await session.commit()

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


def _v2_save_payload(package_payload):
    return {
        "project_id": package_payload["manifest"]["project_id"],
        "route_version_id": package_payload["manifest"]["route_version_id"],
        "package_name": package_payload["manifest"]["package_name"],
        "schema_version": "2.0",
        "manifest": package_payload["manifest"],
        "input_schema": package_payload["input_schema"],
        "route_catalog": package_payload["route_catalog"],
        "route_rules": package_payload["route_rules"],
        "test_cases": package_payload["test_cases"],
        "rule_report_md": "# 标准因子校验测试",
    }


def _compile_payload_with_manual_pair(package_payload, process_id="process_nitriding"):
    payload = deepcopy(package_payload)
    payload["test_cases"] = []
    hash_value = 0x811C9DC5
    for character in process_id:
        hash_value ^= ord(character)
        hash_value = (hash_value * 0x01000193) & 0xFFFFFFFF
    manual_field = f"project_factor.manual_process_{hash_value:08x}"
    payload["input_schema"]["fields"].append({
        "key": manual_field,
        "label": "是否需要渗氮",
        "type": "boolean",
        "required": False,
        "source": "用户直接设定",
        "options": [],
        "allow_custom": False,
    })
    audit = {
        "priority": 2000,
        "enabled": True,
        "source": "user_confirmed",
        "source_segment_id": process_id,
        "source_text": "用户确认是否需要渗氮",
        "confirmed_by": "用户直接设定",
        "confirmed_at": "2026-07-30T10:00:00+00:00",
    }
    payload["route_rules"]["rules"].extend([
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.true",
            "when": {"field": manual_field, "op": "eq", "value": True},
            "then": {"include_process_ids": [process_id], "exclude_process_ids": []},
        },
        {
            **audit,
            "rule_id": f"user.{process_id}.manual.false",
            "when": {"field": manual_field, "op": "eq", "value": False},
            "then": {"include_process_ids": [], "exclude_process_ids": [process_id]},
        },
    ])
    return _compile_payload(payload)


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
    assert compiled_body["kmai_compatibility"]["valid"] is True
    assert set(compiled_body["kmai_compatibility"]["files"]) == {
        "factor_schema.json",
        "factor_expansion_rules.json",
        "route_catalog.json",
        "route_rules.json",
    }

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


def test_compile_accepts_mutually_exclusive_manual_boolean_rules(rule_package_v2_payload):
    response = client.post(
        "/api/extract/finalized-rule-packages/compile",
        json=_compile_payload_with_manual_pair(rule_package_v2_payload),
    )

    assert response.status_code == 200
    validation = response.json()["validation"]
    assert validation["valid"] is True
    assert "same_priority_action_conflict" not in [issue["code"] for issue in validation["errors"]]


def test_compile_rejects_a_factor_id_that_does_not_match_the_leaf(rule_package_v2_payload):
    """A compiler regression must not materialize a rule bound to a different factor."""
    payload = _compile_payload(rule_package_v2_payload)
    payload["rules"][0]["when"] = {
        "field": "precision.grades",
        "op": "contains",
        "value": "孔精加工",
        "factor_id": "feature.center_hole_location",
    }

    response = client.post("/api/extract/finalized-rule-packages/compile", json=payload)

    assert response.status_code == 422
    assert "factor_mismatch" in response.text


def test_v2_save_rejects_a_factor_id_that_does_not_match_the_leaf(rule_package_v2_payload):
    """A save-path regression must not persist a package the compiler would reject."""
    payload = rule_package_v2_payload
    payload["route_rules"]["rules"][0]["when"] = {
        "field": "precision.grades",
        "op": "contains",
        "value": "孔精加工",
        "factor_id": "feature.center_hole_location",
    }

    response = client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(payload),
    )

    assert response.status_code == 422
    assert "factor_mismatch" in response.text


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
