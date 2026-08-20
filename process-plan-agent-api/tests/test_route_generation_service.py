from __future__ import annotations

import json
from types import SimpleNamespace

import asyncio
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.models.models import FinalizedRulePackage, Operation
from app.schemas.schemas import GenerateRequest
from app.routers.generate import generate_route
from app.services.route_generation import (
    RouteGenerationInvalidPackage,
    build_route_generation_result,
    generate_published_route,
    normalize_input_values,
)
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.db_schema_maintenance import ensure_project_schema
from app.models.models import Project


def _published_row(rule_package_v2_payload: dict) -> FinalizedRulePackage:
    return FinalizedRulePackage(
        project_id=rule_package_v2_payload["manifest"]["project_id"],
        version=1,
        package_name=rule_package_v2_payload["manifest"]["package_name"],
        schema_version="2.0",
        status="published",
        manifest_json=json.dumps(rule_package_v2_payload["manifest"]),
        input_schema_json=json.dumps(rule_package_v2_payload["input_schema"]),
        route_catalog_json=json.dumps(rule_package_v2_payload["route_catalog"]),
        route_rules_json=json.dumps(rule_package_v2_payload["route_rules"]),
        test_cases_json=json.dumps(rule_package_v2_payload["test_cases"]),
        rule_report_md="# test",
        validation_report_json=json.dumps({"valid": True}),
        content_hash="test-hash",
        created_by="tester",
    )


def test_route_generation_service_returns_v2_domain_result(rule_package_v2_payload):
    project = SimpleNamespace(rule_engine="auto")
    package = _published_row(rule_package_v2_payload)
    result = build_route_generation_result(
        project=project,
        operations=[],
        finalized_package=package,
        body=GenerateRequest(
            project_id=1,
            factor_values={
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        ),
    )

    assert result.output_mode == "finalized_rule_package_v2"
    assert result.selected_process_ids
    assert result.rule_package_version == 1


def test_route_generation_service_forced_v1_does_not_use_v2_result(rule_package_v2_payload):
    project = SimpleNamespace(rule_engine="v1")
    package = _published_row(rule_package_v2_payload)
    operation = Operation(name="传统主线", sequence=1, op_type="MAIN")
    result = build_route_generation_result(
        project=project,
        operations=[operation],
        finalized_package=package,
        body=GenerateRequest(project_id=1, factor_values={}),
    )

    assert result.output_mode == "route_rules"
    assert [step.name for step in result.steps] == ["传统主线"]
    assert "V1/旧规则路径" in result.summary


def test_route_generation_service_returns_legacy_package_result():
    package = FinalizedRulePackage(
        id=7,
        project_id=1,
        version=3,
        package_name="legacy-package",
        schema_version="1.0",
        status="published",
        manifest_json="{}",
        input_schema_json="{}",
        route_catalog_json=json.dumps(
            {
                "segments": [
                    {
                        "process_id": "prepare",
                        "sequence": 10,
                        "process_name": "准备",
                        "main": True,
                        "primary_steps": ["清理"],
                        "attached_steps": [],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        route_rules_json=json.dumps(
            {
                "material_rules": [
                    {
                        "when": {"material_grade": "9Cr18"},
                        "then": ["准备"],
                    }
                ]
            },
            ensure_ascii=False,
        ),
        rule_report_md="# test",
        validation_report_json=json.dumps({"valid": True}),
        content_hash="legacy-hash",
        created_by="tester",
    )

    result = build_route_generation_result(
        project=SimpleNamespace(rule_engine="auto"),
        operations=[],
        finalized_package=package,
        body=GenerateRequest(project_id=1, factor_values={"material_grade": "9Cr18"}),
    )

    assert result.output_mode == "finalized_rule_package"
    assert result.rule_package_id == 7
    assert result.rule_package_version == 3
    assert result.rule_package_hash == "legacy-hash"
    assert result.schema_version == "1.0"
    assert [step.name for step in result.steps] == ["准备"]


def test_route_generation_service_preserves_invalid_package_version_in_error(
    rule_package_v2_payload,
):
    payload = json.loads(json.dumps(rule_package_v2_payload))
    payload["route_catalog"]["processes"] = []

    try:
        build_route_generation_result(
            project=SimpleNamespace(rule_engine="auto"),
            operations=[],
            finalized_package=_published_row(payload),
            body=GenerateRequest(project_id=1, factor_values={}),
        )
    except RouteGenerationInvalidPackage as exc:
        assert exc.version == 1
        assert not exc.validation.valid
    else:
        raise AssertionError("invalid published package must be rejected")


def test_route_generation_service_preserves_legacy_defaults_only_for_legacy_path():
    body = GenerateRequest(project_id=1)

    assert normalize_input_values(body) == {
        "hardness": "LOW",
        "has_hole": False,
        "has_spline": False,
        "roughness": 3.2,
    }
    assert normalize_input_values(body, explicit_legacy_fields_only=True) == {}


@pytest.fixture
def route_generation_db(tmp_path):
    database_path = tmp_path / "route-generation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup() -> None:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)

    asyncio.run(setup())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


async def _seed_published_v2(session_factory, rule_package_v2_payload: dict) -> int:
    payload = json.loads(json.dumps(rule_package_v2_payload))
    async with session_factory() as db:
        project = Project(name="route-generation-service", mode="route_rules", status="ROUTE_SET_READY")
        db.add(project)
        await db.flush()
        payload["manifest"]["project_id"] = project.id
        payload["manifest"]["scope"] = {"type": "project", "key": str(project.id)}
        package = RulePackageV2.model_validate(payload)
        db.add(
            FinalizedRulePackage(
                project_id=project.id,
                version=1,
                package_name=package.manifest.package_name,
                schema_version="2.0",
                status="published",
                manifest_json=json.dumps(payload["manifest"]),
                input_schema_json=json.dumps(payload["input_schema"]),
                route_catalog_json=json.dumps(payload["route_catalog"]),
                route_rules_json=json.dumps(payload["route_rules"]),
                test_cases_json=json.dumps(payload["test_cases"]),
                rule_report_md="# test",
                validation_report_json=json.dumps({"valid": True}),
                content_hash=rule_package_content_hash(package),
                created_by="tester",
            )
        )
        await db.commit()
        return project.id


def test_route_generation_service_loads_current_published_package(
    route_generation_db,
    rule_package_v2_payload,
):
    project_id = asyncio.run(_seed_published_v2(route_generation_db, rule_package_v2_payload))

    async def run():
        async with route_generation_db() as db:
            return await generate_published_route(
                GenerateRequest(
                    project_id=project_id,
                    factor_values={
                        "material": {"grade": "9Cr18"},
                        "cad": {"features": ["槽类特征"]},
                        "target_hardness_hrc": 58,
                    },
                ),
                db,
            )

    result = asyncio.run(run())

    assert result.output_mode == "finalized_rule_package_v2"
    assert result.rule_package_version == 1
    assert result.selected_process_ids


def test_generate_route_preserves_legacy_package_parse_error(
    route_generation_db,
):
    async def seed():
        async with route_generation_db() as db:
            project = Project(
                name="legacy-package-error",
                mode="route_rules",
                status="ROUTE_SET_READY",
            )
            db.add(project)
            await db.flush()
            db.add(
                FinalizedRulePackage(
                    project_id=project.id,
                    version=1,
                    package_name="legacy-package",
                    schema_version="1.0",
                    status="published",
                    manifest_json="{}",
                    input_schema_json="{}",
                    route_catalog_json=json.dumps(
                        {
                            "segments": [
                                {
                                    "process_id": "prepare",
                                    "sequence": "not-a-number",
                                    "process_name": "准备",
                                    "main": True,
                                    "primary_steps": [],
                                    "attached_steps": [],
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    route_rules_json=json.dumps(
                        {
                            "material_rules": [
                                {
                                    "when": {"material_grade": "9Cr18"},
                                    "then": ["准备"],
                                }
                            ]
                        },
                        ensure_ascii=False,
                    ),
                    rule_report_md="# test",
                    validation_report_json=json.dumps({"valid": True}),
                    created_by="tester",
                )
            )
            await db.commit()
            return project.id

    project_id = asyncio.run(seed())

    async def run():
        async with route_generation_db() as db:
            with pytest.raises(ValueError, match="invalid literal"):
                await generate_route(
                    GenerateRequest(
                        project_id=project_id,
                        factor_values={"material_grade": "9Cr18"},
                    ),
                    db=db,
                )

    asyncio.run(run())
