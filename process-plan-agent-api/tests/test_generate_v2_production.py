"""Stage 3: published V2 packages drive production generation via plan_route."""

from __future__ import annotations

import json
import asyncio
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
from app.routers.generate import _normalize_input_values
from app.schemas.schemas import GenerateRequest
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.execution import inspect_published_rule_package
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.loader import load_published_rule_package
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.validator import validate_rule_package


FIXTURE = Path(__file__).parent / "fixtures" / "rule_package_v2.json"

LEGACY_INPUT_VALUES = {
    "hardness": "LOW",
    "has_hole": False,
    "has_spline": False,
    "roughness": 3.2,
}


def _require_legacy_compatibility_fields(payload: dict[str, Any]) -> None:
    payload["input_schema"]["fields"].extend(
        [
            {
                "key": "hardness",
                "label": "Hardness",
                "type": "string",
                "required": True,
                "source": "legacy",
                "options": [],
                "allow_custom": True,
            },
            {
                "key": "has_hole",
                "label": "Has hole",
                "type": "boolean",
                "required": True,
                "source": "legacy",
                "options": [],
                "allow_custom": False,
            },
            {
                "key": "has_spline",
                "label": "Has spline",
                "type": "boolean",
                "required": True,
                "source": "legacy",
                "options": [],
                "allow_custom": False,
            },
            {
                "key": "roughness",
                "label": "Roughness",
                "type": "number",
                "required": True,
                "source": "legacy",
                "options": [],
                "allow_custom": False,
            },
        ]
    )
    for case in payload["test_cases"]:
        case["input"].update(LEGACY_INPUT_VALUES)


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
        project = Project(name=project_name, mode="route_rules", status="ROUTE_SET_READY")
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


async def _set_project_rule_engine(session_factory, project_id: int, rule_engine: str) -> None:
    async with session_factory() as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.rule_engine = rule_engine
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


async def _published_fingerprint(session_factory, project_id: int) -> dict[str, Any]:
    async with session_factory() as db:
        package = (
            await db.execute(
                select(FinalizedRulePackage).where(
                    FinalizedRulePackage.project_id == project_id,
                    FinalizedRulePackage.status == "published",
                )
            )
        ).scalar_one()
        return {
            "expected_rule_package_id": package.id,
            "expected_rule_package_version": package.version,
            "expected_rule_package_hash": package.content_hash,
        }


async def _rule_package_status(session_factory, project_id: int) -> str:
    async with session_factory() as db:
        return (await db.execute(
            select(FinalizedRulePackage.status).where(
                FinalizedRulePackage.project_id == project_id,
            )
        )).scalar_one()


async def _seed_source_drifted_v2(session_factory) -> tuple[int, dict[str, Any]]:
    confirmed_at = datetime(2026, 8, 6, 0, 0, tzinfo=timezone.utc)

    def configure(payload: dict[str, Any]) -> None:
        rule = payload["route_rules"]["rules"][0]
        rule.update({
            "source": "user_confirmed",
            "source_segment_id": "segment-quench",
            "source_text": "材料与硬度满足条件时纳入淬火",
            "confirmed_by": "reviewer",
            "confirmed_at": confirmed_at.isoformat(),
        })

    project_id, payload = await _seed_published_v2(
        session_factory,
        "v2-source-drift",
        configure,
    )
    rule = payload["route_rules"]["rules"][0]
    candidate = {
        "kind": "condition",
        "when": rule["when"],
        "then": {
            "include_process_ids": rule["then"]["include_process_ids"],
            "exclude_process_ids": rule["then"]["exclude_process_ids"],
        },
    }
    async with session_factory() as db:
        route = NormalizedRouteVersion(
            project_id=project_id,
            version=1,
            route_json=json.dumps([{"id": "segment-quench"}], ensure_ascii=False),
        )
        db.add(route)
        await db.flush()
        db.add(NormalizedRouteSegmentRuleReview(
            project_id=project_id,
            route_version_id=route.id,
            segment_id="segment-quench",
            condition_source_text="数据库中已经变化的条件",
            condition_source_hash="changed-source",
            condition_status="confirmed",
            condition_candidate_json=json.dumps(candidate, ensure_ascii=False),
            condition_confirmed_json=json.dumps(candidate, ensure_ascii=False),
            condition_confirmed_by="reviewer",
            condition_confirmed_at=confirmed_at,
        ))
        package = (await db.execute(
            select(FinalizedRulePackage).where(
                FinalizedRulePackage.project_id == project_id,
            )
        )).scalar_one()
        package.route_version_id = route.id
        await db.commit()
    return project_id, payload


async def _inspect_source_drift_without_write(session_factory, project_id: int):
    async with session_factory() as db:
        row = await load_published_rule_package(project_id, db)
        assert row is not None
        inspection = await inspect_published_rule_package(
            row,
            project_id=project_id,
            db=db,
        )
        status_after_inspection = row.status
        await db.rollback()
        return inspection, status_after_inspection


async def _unpublish_rule_package(session_factory, project_id: int) -> None:
    async with session_factory() as db:
        package = (
            await db.execute(
                select(FinalizedRulePackage).where(
                    FinalizedRulePackage.project_id == project_id,
                    FinalizedRulePackage.status == "published",
                )
            )
        ).scalar_one()
        package.status = "draft"
        await db.commit()


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


def test_generate_accepts_matching_published_rule_package_fingerprint(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-matching-fingerprint"))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            **fingerprint,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["rule_package_version"] == 1
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


def test_published_package_inspection_reports_source_drift_without_archiving(
    generation_context,
):
    _, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_source_drifted_v2(session_factory))

    inspection, status = asyncio.run(
        _inspect_source_drift_without_write(session_factory, project_id)
    )

    assert inspection.package is not None
    assert inspection.validation is not None
    assert inspection.sources_current is False
    assert inspection.parse_error is None
    assert status == "published"
    assert asyncio.run(_rule_package_status(session_factory, project_id)) == "published"


def test_generate_archives_source_drifted_v2_before_planning(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_source_drifted_v2(session_factory))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            **fingerprint,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 409, response.text
    assert response.json()["detail"] == {
        "code": "published_rule_package_changed",
        "message": "当前规则内容已变化，请返回第四步重新发布后再生成。",
        "current_rule_package": None,
    }
    assert asyncio.run(_rule_package_status(session_factory, project_id)) == "archived"
    _assert_generation_not_persisted(session_factory, project_id)


@pytest.mark.parametrize(
    ("field", "stale_value"),
    [
        ("expected_rule_package_id", 999999),
        ("expected_rule_package_version", 999999),
        ("expected_rule_package_hash", "stale-content-hash"),
    ],
)
def test_generate_rejects_stale_published_rule_package_fingerprint(
    generation_context,
    field: str,
    stale_value: int | str,
):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, f"v2-stale-fingerprint-{field}"))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))
    fingerprint[field] = stale_value

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            **fingerprint,
            "factor_values": {
                "material": {"grade": "9Cr18"},
                "cad": {"features": ["槽类特征"]},
                "target_hardness_hrc": 58,
            },
        },
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "published_rule_package_changed"
    assert detail["current_rule_package"]["version"] == 1
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_expected_fingerprint_when_no_package_is_published(
    generation_context,
):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-unpublished-fingerprint"))
    fingerprint = asyncio.run(_published_fingerprint(session_factory, project_id))
    asyncio.run(_unpublish_rule_package(session_factory, project_id))

    response = client.post(
        "/api/generate/",
        json={
            "project_id": project_id,
            **fingerprint,
            "factor_values": {},
        },
    )

    assert response.status_code == 409, response.text
    detail = response.json()["detail"]
    assert detail["code"] == "published_rule_package_changed"
    assert detail["current_rule_package"] is None
    _assert_generation_not_persisted(session_factory, project_id)


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
            project = Project(name="v2-draft-only", mode="route_rules", status="ROUTE_SET_READY")
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


def test_project_rule_engine_v1_forces_legacy_path_with_published_v2(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-forced-v1"))
    asyncio.run(_set_project_rule_engine(session_factory, project_id, "v1"))

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
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["output_mode"] != "finalized_rule_package_v2"
    assert "规则引擎切到 V1" in body["summary"]


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


def test_generate_v2_does_not_use_unsubmitted_legacy_defaults(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-unsubmitted-legacy-defaults",
            _require_legacy_compatibility_fields,
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


def test_generate_v2_accepts_explicit_legacy_compatibility_fields(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-explicit-legacy-fields",
            _require_legacy_compatibility_fields,
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
            **LEGACY_INPUT_VALUES,
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["output_mode"] == "finalized_rule_package_v2"
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


def test_generate_v2_accepts_explicit_factor_values_for_legacy_named_fields(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(
        _seed_published_v2(
            session_factory,
            "v2-explicit-factor-values",
            _require_legacy_compatibility_fields,
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
                **LEGACY_INPUT_VALUES,
            },
        },
    )

    assert response.status_code == 200, response.text
    assert response.json()["output_mode"] == "finalized_rule_package_v2"
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


def test_normalize_input_values_keeps_legacy_defaults_for_v1_only():
    body = GenerateRequest(project_id=1)

    assert _normalize_input_values(body) == LEGACY_INPUT_VALUES
    assert _normalize_input_values(body, explicit_legacy_fields_only=True) == {}


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
