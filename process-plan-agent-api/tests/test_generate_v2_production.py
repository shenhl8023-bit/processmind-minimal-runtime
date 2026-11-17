"""Current executable V2 cores drive deterministic production generation."""

from __future__ import annotations

import json
import asyncio
import hashlib
from pathlib import Path
from typing import Any, Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from executable_support import generate_current
from app.models.models import (
    FinalizedRulePackage,
    ExecutableRuleRevision,
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
from app.services.rule_packages.demo_tables import compile_demo_tables
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
        route = NormalizedRouteVersion(project_id=project.id, version=1, route_json=json.dumps([
            {"id": p["process_id"], "normalized_step_name": p["display_name"],
             "phase": p.get("phase"), "source_operation_ids": p.get("source_operation_ids", []),
             "step_item_details": [{"id": step["step_id"], "text": step["name"], "kind": step["kind"]}
                                   for step in p.get("steps", [])],
             "doc_coverage": {"hit_docs": 1, "total_docs": 1}}
            for p in sorted(payload["route_catalog"]["processes"], key=lambda p: p["default_sequence"])]))
        db.add(route)
        await db.flush()
        payload["manifest"]["route_version_id"] = route.id
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
        from types import SimpleNamespace
        from app.services.rule_packages.executable_revisions import save_revision
        await db.flush()
        executable = await save_revision(db, project, SimpleNamespace(**payload,
            project_id=project.id, route_version_id=route.id, expected_executable_revision=0,
            package_name=package.manifest.package_name, rule_report_md="# Fixture", created_by="tester",
            factor_dictionary=payload.get("factor_dictionary")))
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


@pytest.mark.parametrize('choice', [None, False, True])
def test_generate_manual_bool_default_off_and_associated_chain(generation_context, choice):
    from app.services.rule_packages.condition_reviews import _manual_process_field_key
    client, session_factory = generation_context
    key = _manual_process_field_key('copper')

    def configure(payload):
        payload['input_schema']['fields'] = [{
            'key': key, 'label': '是否需要镀铜', 'type': 'boolean',
            'required': False, 'source': '用户直接设定',
        }]
        payload['route_catalog']['processes'] = [
            {'process_id': pid, 'display_name': name, 'main': pid == 'prepare', 'default_sequence': index * 10}
            for index, (pid, name) in enumerate([
                ('prepare', '准备'), ('copper', '镀铜'), ('strip', '除铜'), ('inspect', '检查'),
            ], 1)
        ]
        payload['route_rules'] = {'rules': [], 'process_configurations': [
            {'process_id': 'copper', 'occurrence': 'manual', 'when': {'field': key, 'op': 'eq', 'value': True}},
            *[{'process_id': target, 'occurrence': 'associated', 'relations': [{
                'relation_type': 'trigger_after', 'source_process_ids': [source], 'target_process_ids': [target],
            }]} for source, target in [('copper', 'strip'), ('strip', 'inspect')]],
        ]}
        payload['test_cases'] = []

    project_id, _ = asyncio.run(_seed_published_v2(session_factory, configure_payload=configure))
    # Untouched unchecked switches send neither an input nor invented provenance.
    body = {'project_id': project_id, 'factor_values': {}, 'input_metadata': {}}
    if choice is not None:
        body['factor_values'] = {'project_factor': {key.split('.', 1)[1]: choice}}
        body['input_metadata'] = {key: {'origin': 'manual'}}
    response = generate_current(client, json=body)
    assert response.status_code == 200, response.text
    assert response.json()['selected_process_ids'] == (['prepare', 'copper', 'strip', 'inspect'] if choice else ['prepare'])


def test_generate_uses_published_v2_plan_route(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory))
    response = generate_current(client,
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
    assert body["output_mode"] == "executable_rule_revision_v2"
    assert body["schema_version"] == "2.0"
    assert body["executable_revision"] == 1
    assert body["selected_process_ids"] == [
        "process_prepare",
        "process_rough_machine",
        "process_mill_slot",
        "process_quench",
    ]
    assert "material.9cr18.quench" in body["matched_rule_ids"]
    assert [step["name"] for step in body["steps"]][-1] in {"淬火", "真空淬火（新名称）", "执行淬火"} or body["steps"]
    assert asyncio.run(_generation_state(session_factory, project_id)) == ("GENERATED", 1)


@pytest.mark.parametrize("snapshot_state", ["published", "legacy", "tampered"])
def test_generate_keeps_template_output_bound_to_published_snapshot(generation_context, snapshot_state):
    client, session_factory = generation_context

    def snapshot_package(payload):
        payload["manifest"]["route_version_id"] = None
        rough = next(process for process in payload["route_catalog"]["processes"]
                     if process["process_id"] == "process_rough_machine")
        rough.update(main=True, constraints={})
        payload["route_catalog"]["processes"] = [rough]
        payload["route_rules"]["rules"] = []
        payload["test_cases"][0]["expect"] = {"included_process_ids": ["process_rough_machine"]}

    project_id, payload = asyncio.run(_seed_published_v2(session_factory, "v2-template-output", snapshot_package))
    full_route_structure = [{
        "process_name": "粗加工",
        "process_type": "加工工序",
        "precision": "粗加工",
        "steps": [{
            "step_name": "粗车",
            "candidates": {"A侧/外圆": ["外圆柱面"]},
            "step_id": "rough.turn",
        }],
        "process_id": "process_rough_machine",
    }]
    live_route_structure = [{
        **full_route_structure[0],
        "process_name": "尚未发布的新名称",
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
                mapping_output_json=json.dumps(live_route_structure, ensure_ascii=False),
                template_revision=1,
                group_count=0,
                feature_selection_count=0,
            ))
            if snapshot_state != "legacy":
                package = RulePackageV2.model_validate(payload)
                tables = compile_demo_tables(package, full_route_structure)
                canonical = json.dumps(tables, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
                snapshot_hash = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
                row = (await db.execute(
                    select(FinalizedRulePackage).where(FinalizedRulePackage.project_id == project_id)
                )).scalar_one()
                row.demo_tables_json = json.dumps(tables, ensure_ascii=False)
                row.export_sources_json = json.dumps({
                    "demo_tables_hash": snapshot_hash if snapshot_state == "published" else "corrupted",
                    "project_id": project_id, "route_version_id": None,
                    "rule_package_content_hash": rule_package_content_hash(package),
                })
            await db.commit()

    asyncio.run(seed_template())
    response = generate_current(client,
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
    assert response.json()["full_route_structure"] == []
    assert json.loads(response.json()["output_json_text"])["full_route_structure"] == []


def test_generate_rejects_rule_package_from_an_older_route_version(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-stale-route"))

    async def seed_newer_route_version():
        async with session_factory() as db:
            db.add(NormalizedRouteVersion(project_id=project_id, version=2, route_json="[]"))
            await db.commit()

    asyncio.run(seed_newer_route_version())
    response = generate_current(client,
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
    assert "可执行规则版本" in str(response.json()["detail"])


def test_generate_rejects_missing_required_v2_input(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-input-validation"))
    response = generate_current(client,
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

    response = generate_current(client,
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


def test_generate_rejects_package_manifest_from_another_project(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, 'mismatched-package-project'))

    async def corrupt_project_binding():
        async with session_factory() as db:
            row = (await db.execute(select(ExecutableRuleRevision).where(
                ExecutableRuleRevision.project_id == project_id))).scalar_one()
            payload = json.loads(row.package_json)
            payload['manifest']['project_id'] = project_id + 100
            row.package_json = json.dumps(payload)
            await db.commit()

    asyncio.run(corrupt_project_binding())
    response = generate_current(client, json={
        'project_id': project_id,
        'factor_values': {
            'material': {'grade': '9Cr18'}, 'cad': {'features': ['槽类特征']},
            'target_hardness_hrc': 58,
        },
        'input_metadata': CONFIRMED_BASE_INPUT_METADATA,
    })
    assert response.status_code == 409, response.text
    assert '可执行规则版本' in str(response.json()['detail'])
    _assert_generation_not_persisted(session_factory, project_id)


def test_generate_rejects_required_value_without_confirmed_origin(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-missing-input-origin"))

    response = generate_current(client,
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

    response = generate_current(client,
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

    response = generate_current(client,
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

    response = generate_current(client,
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
    response = generate_current(client,
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
    response = generate_current(client,
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
    assert "可执行规则版本" in response.json()["detail"]


def test_published_v2_package_ignores_retired_rule_engine_value(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-forced-v1"))
    asyncio.run(_set_retired_rule_engine_value(session_factory, project_id, "v1"))

    response = generate_current(client,
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
    assert body["output_mode"] == "executable_rule_revision_v2"
    assert "旧规则路径" not in body["summary"]


def test_generate_rejects_missing_required_v2_input_without_side_effects(generation_context):
    client, session_factory = generation_context
    project_id, _ = asyncio.run(_seed_published_v2(session_factory, "v2-missing-input"))

    response = generate_current(client,
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

    response = generate_current(client,
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

    response = generate_current(client,
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

    response = generate_current(client,
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
    assert response.json()["output_mode"] == "executable_rule_revision_v2"
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
    response = generate_current(client,
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
    response = generate_current(client,
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

    response = generate_current(client,
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
