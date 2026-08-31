"""Stage 3: published V2 packages drive production generation via plan_route."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteVersion,
    Project,
    ProjectGroupTemplate,
)
from app.routers.generate import _normalize_input_values
from app.schemas.schemas import GenerateRequest
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.validator import validate_rule_package


FIXTURE = Path(__file__).parent / "fixtures" / "rule_package_v2.json"

ADDITIONAL_FACTOR_VALUES = {
    "hardness": "LOW",
    "has_hole": False,
    "has_spline": False,
    "roughness": 3.2,
}

CONFIRMED_BASE_INPUT_METADATA = {
    "material.grade": {"origin": "manual"},
    "cad.features": {"origin": "manual"},
    "target_hardness_hrc": {"origin": "manual", "unit": "HRC"},
}


def _require_additional_factor_fields(payload: dict[str, Any]) -> None:
    payload["input_schema"]["fields"].extend(
        [
            {
                "key": "hardness",
                "label": "Hardness",
                "type": "string",
                "required": True,
                "source": "工艺规程",
                "options": [],
                "allow_custom": True,
            },
            {
                "key": "has_hole",
                "label": "Has hole",
                "type": "boolean",
                "required": True,
                "source": "工艺规程",
                "options": [],
                "allow_custom": False,
            },
            {
                "key": "has_spline",
                "label": "Has spline",
                "type": "boolean",
                "required": True,
                "source": "工艺规程",
                "options": [],
                "allow_custom": False,
            },
            {
                "key": "roughness",
                "label": "Roughness",
                "type": "number",
                "required": True,
                "source": "工艺规程",
                "options": [],
                "allow_custom": False,
            },
        ]
    )
    for case in payload["test_cases"]:
        case["input"].update(ADDITIONAL_FACTOR_VALUES)


@pytest.fixture
def generation_context(tmp_path):
    database_path = tmp_path / "generate-v2.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session_factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


async def _seed_published_v2(
    session_factory,
    project_name: str = "v2-gen-test",
    configure_payload: Callable[[dict[str, Any]], None] | None = None,
) -> tuple[int, dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    if configure_payload:
        configure_payload(payload)
    async with session_factory() as db:
        project = Project(name=project_name, status="ROUTE_SET_READY")
        db.add(project)
        await db.flush()
        payload["manifest"]["project_id"] = project.id
        payload["manifest"]["scope"] = {"type": "project", "key": str(project.id)}
        package = RulePackageV2.model_validate(payload)
        assert validate_rule_package(package).valid
        content_hash = rule_package_content_hash(package)
        row = FinalizedRulePackage(
            project_id=project.id,
            route_version_id=None,
            version=1,
            package_name=package.manifest.package_name,
            schema_version="2.0",
            status="published",
            manifest_json=json.dumps(payload["manifest"], ensure_ascii=False),
            input_schema_json=json.dumps(payload["input_schema"], ensure_ascii=False),
            route_catalog_json=json.dumps(payload["route_catalog"], ensure_ascii=False),
            route_rules_json=json.dumps(payload["route_rules"], ensure_ascii=False),
            test_cases_json=json.dumps(payload["test_cases"], ensure_ascii=False),
            rule_report_md="# test",
            validation_report_json=json.dumps({"valid": True}, ensure_ascii=False),
            content_hash=content_hash,
            created_by="tester",
            published_by="tester",
        )
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return project.id, payload


async def _set_retired_rule_engine_value(session_factory, project_id: int, rule_engine: str) -> None:
    async with session_factory() as db:
        columns = {
            row[1]
            for row in (await db.execute(text("PRAGMA table_info(projects)"))).all()
        }
        if "rule_engine" not in columns:
            await db.execute(text("ALTER TABLE projects ADD COLUMN rule_engine VARCHAR(20)"))
        await db.execute(
            text("UPDATE projects SET rule_engine = :rule_engine WHERE id = :project_id"),
            {"rule_engine": rule_engine, "project_id": project_id},
        )
        await db.commit()


async def _generation_state(session_factory, project_id: int) -> tuple[str, int]:
    async with session_factory() as db:
        status = (await db.execute(select(Project.status).where(Project.id == project_id))).scalar_one()
        route_count = (
            await db.execute(
                select(func.count(GeneratedRoute.id)).where(GeneratedRoute.project_id == project_id)
            )
        ).scalar_one()
        return status, route_count


def _assert_input_error(response, *, code: str, field: str, allowed_values: list[Any]) -> None:
    assert response.status_code == 422, response.text
    errors = response.json()["detail"]
    error = next(item for item in errors if item["code"] == code and item["field"] == field)
    assert error["path"] == f"inputs.{field}"
    assert error["reason"] == error["message"]
    assert error["allowed_values"] == allowed_values


def _assert_generation_not_persisted(session_factory, project_id: int) -> None:
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("ROUTE_SET_READY", 0)


def test_generate_uses_published_v2_plan_route(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory))
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": CONFIRMED_BASE_INPUT_METADATA,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_mode"] == "finalized_rule_package_v2"
    assert body["schema_version"] == "2.0"
    assert body["rule_package_version"] == 1
    assert body["selected_process_ids"] == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
    assert "material.9cr18.quench" in body["matched_rule_ids"]
    assert [step["name"] for step in body["steps"]][-1] in {"淬火", "真空淬火（新名称）", "执行淬火"} or body["steps"]
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


def test_generate_serializes_project_template_output(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-template-output"))
    full_route_structure = [{
        "process_name": "车削加工",
        "process_type": "加工工序",
        "precision": "精加工",
        "technical_requirements": [],
        "steps": [],
    }]

    async def seed_template():
        async with session_factory() as db:
            db.add(ProjectGroupTemplate(
                project_id=project_id,
                original_filename="template.xml",
                source_encoding="UTF-8",
                part_filename="part.prt",
                content_hash="template-hash",
                feature_dictionary_version="v1",
                source_xml="<xml />",
                tree_json="[]",
                validation_json="[]",
                mappings_json="[]",
                step_mappings_json="[]",
                mapping_output_json=json.dumps(full_route_structure, ensure_ascii=False),
                template_revision=1,
                group_count=0,
                feature_selection_count=0,
            ))
            await db.commit()

    asyncio.run(seed_template())
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": CONFIRMED_BASE_INPUT_METADATA,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["full_route_structure"] == full_route_structure


def test_generate_rejects_rule_package_from_an_older_route_version(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-stale-route"))

    async def seed_newer_route_version():
        async with session_factory() as db:
            current_route = NormalizedRouteVersion(
                project_id=project_id,
                version=1,
                route_json="[]",
            )
            db.add(current_route)
            await db.flush()
            package = (
                await db.execute(
                    select(FinalizedRulePackage).where(FinalizedRulePackage.project_id == project_id)
                )
            ).scalar_one()
            package.route_version_id = current_route.id
            manifest = json.loads(package.manifest_json)
            manifest["route_version_id"] = current_route.id
            package.manifest_json = json.dumps(manifest, ensure_ascii=False)
            db.add(NormalizedRouteVersion(project_id=project_id, version=2, route_json="[]"))
            await db.commit()

    asyncio.run(seed_newer_route_version())
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": CONFIRMED_BASE_INPUT_METADATA,
        },
    )

    assert response.status_code == 409, response.text
    assert "路线版本已更新" in str(response.json()["detail"])


def test_generate_rejects_missing_required_v2_input(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-input-validation"))
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {"cad": {"features": ["槽类特征"]}},
        },
    )
    assert response.status_code == 422, response.text
    assert any(item["code"] == "required_input_missing" for item in response.json()["detail"])


def test_generate_rejects_example_value_for_required_input(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-example-input"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": {
                "material.grade": {"origin": "example"},
                "cad.features": {"origin": "manual"},
            },
        },
    )

    _assert_input_error(response, code="example_input_not_confirmed", field="material.grade", allowed_values=[])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_required_value_without_confirmed_origin(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-missing-input-origin"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    _assert_input_error(response, code="input_origin_missing", field="material.grade", allowed_values=[])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_optional_rule_value_without_confirmed_origin(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-optional-input-origin"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": {
                "material.grade": {"origin": "manual"},
                "cad.features": {"origin": "manual"},
            },
        },
    )

    _assert_input_error(response, code="input_origin_missing", field="target_hardness_hrc", allowed_values=[])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_extracted_value_without_evidence(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-extracted-without-evidence"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": {
                "material.grade": {"origin": "extracted", "evidence": []},
                "cad.features": {"origin": "manual"},
                "target_hardness_hrc": {"origin": "manual", "unit": "HRC"},
            },
        },
    )

    _assert_input_error(response, code="extracted_input_missing_evidence", field="material.grade", allowed_values=[])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_unit_that_differs_from_factor_definition(generation_context):
    client, session_factory = generation_context

    def with_roundness(payload: dict[str, Any]) -> None:
        payload["input_schema"]["fields"].append({
            "key": "tolerance.roundness_mm",
            "label": "圆度公差",
            "type": "number",
            "unit": "mm",
        })
        for case in payload["test_cases"]:
            case["input"]["tolerance"] = {"roundness_mm": 0.01}

    project_id, _ = asyncio.run(_seed_published_v2(
        session_factory,
        "v2-unit-input",
        configure_payload=with_roundness,
    ))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
                "tolerance": {"roundness_mm": 0.01},
            },
            "input_metadata": {
                "tolerance.roundness_mm": {"origin": "manual", "unit": "μm"},
            },
        },
    )

    _assert_input_error(response, code="input_unit_mismatch", field="tolerance.roundness_mm", allowed_values=[])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_stale_workflow_revision(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-stale-workflow"))
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "expected_workflow_revision": 99,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 409
    assert "页面已过期" in str(response.json()["detail"])


def test_draft_v2_is_not_used_for_generate(generation_context):
    client, session_factory = generation_context
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    async def seed_draft_only():
        async with session_factory() as db:
            project = Project(name="v2-draft-only", status="ROUTE_SET_READY")
            db.add(project)
            await db.flush()
            payload["manifest"]["project_id"] = project.id
            payload["manifest"]["scope"] = {"type": "project", "key": str(project.id)}
            package = RulePackageV2.model_validate(payload)
            row = FinalizedRulePackage(
                project_id=project.id,
                version=1,
                package_name=package.manifest.package_name,
                schema_version="2.0",
                status="draft",
                manifest_json=json.dumps(payload["manifest"], ensure_ascii=False),
                input_schema_json=json.dumps(payload["input_schema"], ensure_ascii=False),
                route_catalog_json=json.dumps(payload["route_catalog"], ensure_ascii=False),
                route_rules_json=json.dumps(payload["route_rules"], ensure_ascii=False),
                test_cases_json=json.dumps(payload["test_cases"], ensure_ascii=False),
                rule_report_md="# draft",
                validation_report_json="{}",
                content_hash=rule_package_content_hash(package),
                created_by="tester",
            )
            db.add(row)
            await db.commit()
            return project.id

    project_id = asyncio.run(seed_draft_only())
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )
    assert response.status_code == 409, response.text
    assert "尚未导出有效规则包" in response.json()["detail"]


def test_published_v2_package_ignores_retired_rule_engine_value(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-forced-v1"))
    asyncio.run(_set_retired_rule_engine_value(session_factory, project_id, "v1"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            "input_metadata": CONFIRMED_BASE_INPUT_METADATA,
        },
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_mode"] == "finalized_rule_package_v2"
    assert "旧规则路径" not in body["summary"]


def test_generate_rejects_missing_required_v2_input_without_side_effects(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-missing-input"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "target_hardness_hrc": 58,
            },
        },
    )

    _assert_input_error(
        response,
        code="required_input_missing",
        field="cad.features",
        allowed_values=[],
    )
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_v2_requires_all_submitted_factor_values(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-unsubmitted-legacy-defaults",
            _require_additional_factor_fields,
        )
    )

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    for field, allowed_values in (
        ("hardness", []),
        ("has_hole", [True, False]),
        ("has_spline", [True, False]),
        ("roughness", []),
    ):
        _assert_input_error(
            response,
            code="required_input_missing",
            field=field,
            allowed_values=allowed_values,
        )
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_v2_ignores_retired_top_level_factor_fields(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-explicit-legacy-fields",
            _require_additional_factor_fields,
        )
    )

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
            **ADDITIONAL_FACTOR_VALUES,
        },
    )

    for field, allowed_values in (
        ("hardness", []),
        ("has_hole", [True, False]),
        ("has_spline", [True, False]),
        ("roughness", []),
    ):
        _assert_input_error(
            response,
            code="required_input_missing",
            field=field,
            allowed_values=allowed_values,
        )
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_v2_accepts_additional_factor_values(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-explicit-factor-values",
            _require_additional_factor_fields,
        )
    )

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
                **ADDITIONAL_FACTOR_VALUES,
            },
            "input_metadata": {
                **CONFIRMED_BASE_INPUT_METADATA,
                "hardness": {"origin": "manual"},
                "has_hole": {"origin": "manual"},
                "has_spline": {"origin": "manual"},
                "roughness": {"origin": "manual"},
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["output_mode"] == "finalized_rule_package_v2"
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


def test_normalize_input_values_uses_only_factor_values():
    body = GenerateRequest(
        project_id=1,
        factor_values={"material": {"grade": "9Cr18"}, "target_hardness_hrc": 58},
    )

    assert _normalize_input_values(body) == {
        "material": {"grade": "9Cr18"},
        "target_hardness_hrc": 58,
    }


def test_generate_rejects_invalid_v2_option_without_side_effects(generation_context):
    client, session_factory = generation_context

    def configure_payload(payload: dict[str, Any]) -> None:
        material_field = next(
            field for field in payload["input_schema"]["fields"] if field["key"] == "material.grade"
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

    project_id, _ = asyncio.run(
        _seed_published_v2(session_factory, "v2-invalid-option", configure_payload)
    )
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "SUS304"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    _assert_input_error(
        response,
        code="input_option_invalid",
        field="material.grade",
        allowed_values=["9Cr18", "95Cr18"],
    )
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_wrong_v2_boolean_type_without_side_effects(generation_context):
    client, session_factory = generation_context

    def configure_payload(payload: dict[str, Any]) -> None:
        payload["input_schema"]["fields"].append(
            {
                "key": "requires_inspection",
                "label": "是否需要检验",
                "type": "boolean",
                "required": False,
                "source": "图样",
                "options": [],
                "allow_custom": False,
            }
        )

    project_id, _ = asyncio.run(
        _seed_published_v2(session_factory, "v2-wrong-boolean", configure_payload)
    )
    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
                "requires_inspection": "false",
            },
        },
    )

    _assert_input_error(
        response,
        code="input_type_mismatch",
        field="requires_inspection",
        allowed_values=[True, False],
    )
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_wrong_v2_number_type_without_side_effects(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-wrong-number"))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": "58",
            },
        },
    )

    _assert_input_error(
        response,
        code="input_type_mismatch",
        field="target_hardness_hrc",
        allowed_values=[],
    )
    _assert_generation_not_persisted(session_factory, project_id)
