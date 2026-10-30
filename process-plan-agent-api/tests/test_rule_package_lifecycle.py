import asyncio
import importlib.util
import io
import json
from copy import deepcopy
from pathlib import Path
import zipfile

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.models.models import ProjectGroupTemplate, DocumentOperationDetail
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.lifecycle import publish_rule_package


@pytest.fixture
def lifecycle_client(tmp_path, rule_package_v2_payload):
    database_path = tmp_path / "lifecycle.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
    # Lifecycle examples use the common denominator of both executable formats.
    # Unsupported runtime constraints are covered by explicit precheck tests.
    for process in rule_package_v2_payload["route_catalog"]["processes"]:
        process["constraints"] = {"requires": [], "must_run_after": [], "must_run_before": [], "conflicts_with": []}
    for field in rule_package_v2_payload["input_schema"]["fields"]:
        field.pop("validation", None)
    # This fixture's explicit mapping rows follow its catalog insertion order.
    # Keep native ordering consistent; stale-order cases override it below.
    for index, process in enumerate(rule_package_v2_payload["route_catalog"]["processes"], 1):
        process["default_sequence"] = index * 100
    rule_package_v2_payload["route_rules"]["rules"][0]["then"]["include_process_ids"].append("process_rough_machine")
    material = rule_package_v2_payload["input_schema"]["fields"][0]
    material["type"] = "single_select"
    material["options"] = [{"value": value, "label": value} for value in ("9Cr18", "95Cr18", "其他材料")]
    material["allow_custom"] = False
    features = rule_package_v2_payload["input_schema"]["fields"][1]
    features["options"] = [{"value": value, "label": value} for value in ("槽类特征", "孔类结构")]
    features["allow_custom"] = False

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
            session.add(ProjectGroupTemplate(
                project_id=12,
                original_filename="group-template.xml",
                source_encoding="utf-8",
                part_filename="group-template.prt",
                content_hash="a" * 64,
                feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft />",
                tree_json=json.dumps([
                    {"path": [f"group-{operation_id}"], "children": [], "feature_selections": []}
                    for operation_id in range(11, 16)
                ] + [{"path": ["槽"], "children": [], "feature_selections": ["槽类特征"]}]),
                validation_json="[]",
                mappings_json=json.dumps([
                    {
                        "source_operation_id": operation_id,
                        "alias": f"op-{operation_id}",
                        "template_group_key": f"group-{operation_id}",
                        "template_group_id": f"group-{operation_id}",
                        "template_group_name": f"group-{operation_id}",
                        "template_group_path": [f"group-{operation_id}"],
                        "feature_selections": [],
                    }
                    for operation_id in range(11, 16)
                ] + [{
                    "source_operation_id": 11,
                    "alias": "op-11-slot",
                    "template_group_key": "slot",
                    "template_group_id": "slot",
                    "template_group_name": "槽",
                    "template_group_path": ["槽"],
                    "feature_selections": ["槽类特征"],
                }], ensure_ascii=False),
                step_mappings_json=json.dumps([
                    {
                        "source_operation_id": 11 + index,
                        "source_operation_name": process["display_name"],
                        "source_step_order": step_index,
                        "source_step_name": step["name"],
                        "status": "not_applicable",
                        "source": "user_confirmed",
                        "final_targets": [{"process_id": process["process_id"], "step_id": step["step_id"]}],
                    }
                    for index, process in enumerate(rule_package_v2_payload["route_catalog"]["processes"])
                    for step_index, step in enumerate(process["steps"], start=1)
                ], ensure_ascii=False),
                mapping_output_json=json.dumps([
                    {
                        "process_name": process["display_name"],
                        "process_type": "加工工序" if process["steps"] else "辅助工序",
                        "precision": "粗加工" if process["steps"] else "辅助工序",
                        "steps": [
                            {"step_name": step["name"],
                             "candidates": {"group-12": ["外圆柱面"]} if process["process_id"] == "process_rough_machine" else {},
                             "step_id": step["step_id"]}
                            for step in process["steps"]
                        ],
                        "process_id": process["process_id"],
                    }
                    for process in rule_package_v2_payload["route_catalog"]["processes"]
                ], ensure_ascii=False),
                template_revision=1,
                group_count=5,
                feature_selection_count=0,
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
    route_catalog = deepcopy(package["route_catalog"])
    for index, process in enumerate(route_catalog.get("processes", []), start=0):
        process["template_group_aliases"] = [{
            "source_operation_id": 11 + index,
            "alias": process["display_name"],
            "template_group_id": f"group-{11 + index}",
            "template_group_key": f"group-{11 + index}",
            "template_group_name": process["display_name"],
            "template_group_path": [f"group-{11 + index}"],
        }]
    return {
        "project_id": package["manifest"]["project_id"],
        "route_version_id": package["manifest"]["route_version_id"],
        "package_name": package["manifest"]["package_name"],
        "schema_version": "2.0",
        "manifest": package["manifest"],
        "factor_dictionary": package.get("factor_dictionary"),
        "input_schema": package["input_schema"],
        "route_catalog": route_catalog,
        "route_rules": package["route_rules"],
        "test_cases": package["test_cases"],
        "rule_report_md": "# V2 规则包测试报告",
    }


def _v1_save_payload():
    return {
        "project_id": 12,
        "package_name": "legacy_rules",
        "schema_version": "1.0",
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
    payload["test_cases"].append(
        {
            "case_id": "feature-unknown-custom",
            "input": {
                "material": {"grade": "其他材料"},
                "cad": {"features": [source_value]},
                "target_hardness_hrc": 0,
            },
            "expect": {
                "included_process_ids": ["process_mill_slot"],
                "excluded_process_ids": [],
            },
        }
    )
    return payload


def test_v2_save_publishes_and_rejects_retired_schema(lifecycle_client, rule_package_v2_payload):
    saved_v2 = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(rule_package_v2_payload),
    )
    assert saved_v2.status_code == 200, saved_v2.text
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
    assert saved_v1.status_code == 422

    versions = lifecycle_client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    )
    assert versions.status_code == 200
    statuses = {item["id"]: item["status"] for item in versions.json()}
    assert statuses[v2["id"]] == "published"

    latest = lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )
    assert latest.status_code == 200
    assert latest.json()["id"] == v2["id"]


def test_v2_save_round_trips_full_factor_dictionary(lifecycle_client, rule_package_v2_payload):
    payload = _v2_save_payload(rule_package_v2_payload)
    payload["factor_dictionary"] = {
        "schema_version": "2.0",
        "fields": [
            *rule_package_v2_payload["input_schema"]["fields"],
            {
                "key": "geometry.length_mm",
                "label": "特征长度",
                "type": "number",
                "unit": "mm",
            },
        ],
    }

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)

    assert saved.status_code == 200
    saved_dictionary = saved.json()["factor_dictionary"]
    assert saved_dictionary["schema_version"] == "2.0"
    assert [field["key"] for field in saved_dictionary["fields"]] == [
        field["key"] for field in payload["factor_dictionary"]["fields"]
    ]
    assert saved_dictionary["fields"][-1]["unit"] == "mm"

    latest = lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )
    assert latest.status_code == 200
    assert latest.json()["factor_dictionary"] == saved_dictionary


def test_retired_rule_package_is_not_exposed_as_an_executable_package(lifecycle_client):
    async def seed_retired_package():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add(FinalizedRulePackage(
                project_id=12,
                version=1,
                package_name="retired-rules",
                schema_version="retired",
                status="published",
                input_schema_json="{}",
                route_catalog_json="{}",
                route_rules_json="{}",
                rule_report_md="# retired",
            ))
            await db.commit()

    asyncio.run(seed_retired_package())

    packages = lifecycle_client.get(
        "/api/extract/finalized-rule-packages",
        params={"project_id": 12},
    )
    latest = lifecycle_client.get(
        "/api/extract/finalized-rule-packages/latest",
        params={"project_id": 12},
    )

    assert packages.status_code == 200
    assert packages.json() == []
    assert latest.status_code == 404


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
                    (1, 1, 'rules-old', '{}', '{}', '{}', '# old', 'user', CURRENT_TIMESTAMP),
                    (1, 2, 'rules-new', '{}', '{}', '{}', '# new', 'user', CURRENT_TIMESTAMP)
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
    assert [row["schema_version"] for row in rows] == ["retired", "retired"]
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
                    (7, 1, 'old', 'retired', 'published', '{}', '{}', '{}', '# old'),
                    (7, 2, 'new', 'retired', 'published', '{}', '{}', '{}', '# new')
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


def test_save_accepts_rules_with_unknown_features(lifecycle_client, rule_package_v2_payload):
    package = _append_unknown_feature_rule(rule_package_v2_payload)

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(package),
    )
    assert saved.status_code == 200
    saved_body = saved.json()

    async def persisted_packages():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return (await db.execute(select(FinalizedRulePackage))).scalars().all()

    packages = asyncio.run(persisted_packages())
    assert len(packages) == 1
    assert packages[0].status == "published"
    assert saved_body["validation_report"]["valid"] is True


def test_compile_and_save_preserve_rule_package(lifecycle_client, rule_package_v2_payload):
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
    assert compiled["validation"]["valid"] is True

    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages",
        json=_v2_save_payload(compiled["package"]),
    )
    assert saved.status_code == 200
    saved_body = saved.json()
    assert saved_body["route_rules"] == compiled["package"]["route_rules"]


def test_save_requires_template_mapping_before_publish(lifecycle_client, rule_package_v2_payload):
    async def clear_mappings():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.mappings_json = "[]"
            await db.commit()

    asyncio.run(clear_mappings())

    payload = _v2_save_payload(rule_package_v2_payload)
    payload["route_catalog"]["processes"][0]["template_group_aliases"] = [
        {
            "source_operation_id": 11,
            "alias": "准备",
            "template_group_id": "group_prepare",
            "template_group_key": "group_prepare",
            "template_group_name": "准备",
            "template_group_path": ["准备"],
        }
    ]

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)

    assert saved.status_code == 422
    detail = saved.json()["detail"]
    assert detail["message"] == "规则包发布前需完成分组模板映射。"
    assert any(item["code"] == "group_template_mapping_missing" for item in detail["blockers"])


def test_precheck_accepts_partial_legacy_mapping(lifecycle_client, rule_package_v2_payload):
    async def keep_only_prepare_mapping():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.mappings_json = json.dumps([
                {
                    "source_operation_id": operation_id,
                    "alias": f"op-{operation_id}",
                    "template_group_key": f"group-{operation_id}",
                    "template_group_id": f"group-{operation_id}",
                    "template_group_name": f"group-{operation_id}",
                    "template_group_path": [f"group-{operation_id}"],
                    "feature_selections": [],
                }
                for operation_id in (11, 13)
            ] + [{
                "source_operation_id": 11,
                "alias": "op-11-slot",
                "template_group_key": "slot",
                "template_group_id": "slot",
                "template_group_name": "槽",
                "template_group_path": ["槽"],
                "feature_selections": ["槽类特征"],
            }], ensure_ascii=False)
            await db.commit()

    asyncio.run(keep_only_prepare_mapping())

    payload = _v2_save_payload(rule_package_v2_payload)
    response = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert body["blockers"] == []
    assert next(item for item in body["checklist"] if item["code"] == "template_mapping")["status"] == "passed"


def test_group_mapping_coverage_passes_after_mappings_completed_over_multiple_saves(
    lifecycle_client,
    rule_package_v2_payload,
):
    async def require_two_feature_groups():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.tree_json = json.dumps([{
                "key": "side-a",
                "name": "A侧",
                "path": ["A侧"],
                "feature_selections": [],
                "children": [
                    {
                        "key": "hole",
                        "name": "孔",
                        "path": ["A侧", "孔"],
                        "feature_selections": ["孔类结构"],
                        "children": [],
                    },
                    {
                        "key": "slot",
                        "name": "槽",
                        "path": ["A侧", "槽"],
                        "feature_selections": ["槽类特征"],
                        "children": [],
                    },
                ],
            }], ensure_ascii=False)
            template.mappings_json = "[]"
            await db.commit()

    asyncio.run(require_two_feature_groups())

    first_save = lifecycle_client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": 12,
            "expected_template_revision": 1,
            "mappings": [{
                "source_operation_id": 11,
                "alias": "钻孔（A侧/孔）",
                "template_group_path": ["A侧", "孔"],
            }],
        },
    )
    assert first_save.status_code == 200, first_save.text
    assert [item["template_group_path"] for item in first_save.json()["mappings"]] == [["A侧", "孔"]]

    payload = _v2_save_payload(rule_package_v2_payload)
    incomplete_precheck = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=payload,
    )
    assert incomplete_precheck.status_code == 200, incomplete_precheck.text
    assert incomplete_precheck.json()["ok"] is False
    missing_mapping = next(
        item for item in incomplete_precheck.json()["blockers"]
        if item["code"] == "group_template_mapping_missing"
    )
    assert "A侧 / 槽" in missing_mapping["message"]

    second_save = lifecycle_client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": 12,
            "expected_template_revision": first_save.json()["template_revision"],
            "mappings": [{
                "source_operation_id": 12,
                "alias": "铣槽（A侧/槽）",
                "template_group_path": ["A侧", "槽"],
            }],
        },
    )
    assert second_save.status_code == 200, second_save.text
    assert {
        tuple(item["template_group_path"])
        for item in second_save.json()["mappings"]
    } == {("A侧", "孔"), ("A侧", "槽")}

    operations = []
    for index, process in enumerate(rule_package_v2_payload["route_catalog"]["processes"]):
        source_operation_id = 11 + index
        operations.append({
            "operation_id": source_operation_id,
            "operation_name": process["display_name"],
            "process_id": process["process_id"],
            "source_operation_ids": [source_operation_id],
            "process_type": "加工工序" if process["steps"] else "辅助工序",
            "precision": "粗加工" if process["steps"] else "辅助工序",
            "steps": [
                {
                    "step_id": step["step_id"],
                    "step_name": step["name"],
                    "kind": step.get("kind", "primary"),
                    "source_steps": [{
                        "source_operation_id": source_operation_id,
                        "source_step_order": step_order,
                        "source_step_name": step["name"],
                    }],
                }
                for step_order, step in enumerate(process["steps"], start=1)
            ],
        })

    final_route_save = lifecycle_client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": 12,
            "expected_template_revision": second_save.json()["template_revision"],
            "mappings": [],
            "operations": operations,
            "replace_all": True,
        },
    )
    assert final_route_save.status_code == 200, final_route_save.text
    assert [item["process_id"] for item in final_route_save.json()["mapping_output"]] == [
        process["process_id"] for process in rule_package_v2_payload["route_catalog"]["processes"]
    ]

    legacy_refresh = lifecycle_client.put(
        "/api/extract/group-templates/mappings",
        json={
            "project_id": 12,
            "expected_template_revision": final_route_save.json()["template_revision"],
            "mappings": [
                {
                    "source_operation_id": 11,
                    "alias": "钻孔（A侧/孔）更新",
                    "template_group_path": ["A侧", "孔"],
                },
                {
                    "source_operation_id": 12,
                    "alias": "铣槽（A侧/槽）更新",
                    "template_group_path": ["A侧", "槽"],
                },
            ],
        },
    )
    assert legacy_refresh.status_code == 200, legacy_refresh.text
    assert legacy_refresh.json()["mapping_output"] == final_route_save.json()["mapping_output"]

    completed_precheck = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=payload,
    )
    assert completed_precheck.status_code == 200, completed_precheck.text
    completed_body = completed_precheck.json()
    # Coverage is complete, but these steps deliberately have no candidates.
    # Coverage alone must not publish a permanently empty executable package.
    assert completed_body["ok"] is False, completed_body
    assert {item['code'] for item in completed_body['blockers']} == {'empty_export_route'}
    assert next(
        item for item in completed_precheck.json()["checklist"]
        if item["code"] == "template_mapping"
    )["status"] == "passed"
    assert not any(item["code"] == "group_template_mapping_missing" for item in completed_body["blockers"])


def test_step_mapping_precheck_passes_after_partial_group_mapping_is_completed(
    lifecycle_client,
    rule_package_v2_payload,
):
    async def seed_two_feature_groups_and_source_step():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add(DocumentOperationDetail(
                project_id=12,
                pdf_name="source.pdf",
                operation_seq=10,
                page_no=1,
                operation_name="铣槽",
                normalized_name="铣槽",
                operation_content="铣槽",
            ))
            template = await db.get(ProjectGroupTemplate, 1)
            template.tree_json = json.dumps([{
                "key": "side-a",
                "name": "A侧",
                "path": ["A侧"],
                "feature_selections": [],
                "children": [
                    {
                        "key": "hole",
                        "name": "孔",
                        "path": ["A侧", "孔"],
                        "feature_selections": ["孔(盲孔)"],
                        "children": [],
                    },
                    {
                        "key": "slot",
                        "name": "槽",
                        "path": ["A侧", "槽"],
                        "feature_selections": ["通槽"],
                        "children": [],
                    },
                ],
            }], ensure_ascii=False)
            template.mappings_json = "[]"
            template.step_mappings_json = "[]"
            template.mapping_output_json = "[]"
            await db.commit()

    asyncio.run(seed_two_feature_groups_and_source_step())

    source_operation_id = 900001
    route_processes = rule_package_v2_payload["route_catalog"]["processes"]
    operations = []
    for index, process in enumerate(route_processes):
        process_id = process["process_id"]
        operation = {
            "operation_id": 11 + index,
            "operation_name": process["display_name"],
            "process_id": process_id,
            "source_operation_ids": [source_operation_id] if process_id == "process_mill_slot" else [],
            "process_type": "加工工序" if process["steps"] else "辅助工序",
            "precision": "粗加工" if process["steps"] else "辅助工序",
            "steps": [],
        }
        for step in process["steps"]:
            step_input = {
                "step_id": step["step_id"],
                "step_name": step["name"],
                "kind": step.get("kind", "primary"),
                "source_steps": [],
            }
            if process_id == "process_mill_slot":
                step_input["source_steps"] = [{
                    "source_operation_id": source_operation_id,
                    "source_step_order": 1,
                    "source_step_name": "铣槽",
                }]
            operation["steps"].append(step_input)
        operations.append(operation)

    payload = _v2_save_payload(rule_package_v2_payload)
    payload["input_schema"]["fields"][1]["options"].extend([
        {"value": "孔", "label": "孔"},
        {"value": "通槽", "label": "通槽"},
    ])
    for process in payload["route_catalog"]["processes"]:
        process["source_operation_ids"] = [source_operation_id] if process["process_id"] == "process_mill_slot" else []
        process["template_group_aliases"] = []

    def step_mapping(path, feature):
        return {
            "source_operation_id": source_operation_id,
            "source_operation_name": "铣槽",
            "source_step_order": 1,
            "source_step_name": "铣槽",
            "template_group_path": path,
            "candidate_features": [feature],
            "status": "confirmed",
            "source": "user_confirmed",
            "final_targets": [{"process_id": "process_mill_slot", "step_id": "slot.mill"}],
        }

    first_save = lifecycle_client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": 12,
            "expected_template_revision": 1,
            "mappings": [step_mapping(["A侧", "孔"], "孔(盲孔)")],
            "operations": operations,
            "replace_all": True,
        },
    )
    assert first_save.status_code == 200, first_save.text
    assert len(first_save.json()["step_mappings"]) == 1

    incomplete_precheck = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=payload,
    )
    assert incomplete_precheck.status_code == 200, incomplete_precheck.text
    assert incomplete_precheck.json()["ok"] is False
    missing_group = next(
        item for item in incomplete_precheck.json()["blockers"]
        if item["code"] == "group_template_mapping_missing"
    )
    assert "A侧 / 槽" in missing_group["message"]

    second_save = lifecycle_client.put(
        "/api/extract/group-templates/step-mappings",
        json={
            "project_id": 12,
            "expected_template_revision": first_save.json()["template_revision"],
            "mappings": [
                step_mapping(["A侧", "孔"], "孔(盲孔)"),
                step_mapping(["A侧", "槽"], "通槽"),
            ],
            "operations": operations,
            "replace_all": True,
        },
    )
    assert second_save.status_code == 200, second_save.text
    assert {
        tuple(mapping["template_group_path"])
        for mapping in second_save.json()["step_mappings"]
    } == {("A侧", "孔"), ("A侧", "槽")}
    slot_route = next(
        process for process in second_save.json()["mapping_output"]
        if process["process_id"] == "process_mill_slot"
    )
    assert slot_route["steps"][0]["candidates"] == {
        "A侧/孔": ["孔(盲孔)"],
        "A侧/槽": ["通槽"],
    }

    completed_precheck = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=payload,
    )
    assert completed_precheck.status_code == 200, completed_precheck.text
    assert completed_precheck.json()["ok"] is True, completed_precheck.text
    assert completed_precheck.json()["blockers"] == []


def test_precheck_accepts_confirmed_step_mapping_for_source_operation(
    lifecycle_client,
    rule_package_v2_payload,
):
    async def save_step_mapping():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add(DocumentOperationDetail(project_id=12, pdf_name='source.pdf', operation_seq=10,
                                           page_no=1, operation_name='铣槽', normalized_name='铣槽', operation_content='铣槽'))
            template = await db.get(ProjectGroupTemplate, 1)
            template.mappings_json = "[]"
            template.step_mappings_json = json.dumps(json.loads(template.step_mappings_json) + [
                {
                    "source_operation_id": 900001,
                    "source_operation_name": "铣槽",
                    "source_step_key": "op_900001_s01",
                    "source_step_order": 1,
                    "source_step_name": "铣槽",
                    "source_step_text_hash": "sha256:test",
                    "template_group_path": ["槽"],
                    "candidate_features": ["槽类特征"],
                    "status": "confirmed",
                }
            ], ensure_ascii=False)
            await db.commit()

    asyncio.run(save_step_mapping())
    payload = _v2_save_payload(rule_package_v2_payload)
    for process in payload["route_catalog"]["processes"]:
        process["template_group_aliases"] = []
        process["source_operation_ids"] = [900001]
    mill_slot = next(
        process for process in payload["route_catalog"]["processes"]
        if process["process_id"] == "process_mill_slot"
    )

    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=payload,
    )

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is True
    assert next(item for item in body["checklist"] if item["code"] == "template_mapping") == {
        "code": "template_mapping",
        "label": "分组模板映射",
        "status": "passed",
        "message": "每个包含特征的模板分组均已关联至少一个有效特征；无需逐个映射工步或组内全部特征。",
    }


def test_save_allows_publish_without_step_mappings_when_process_mappings_exist(lifecycle_client, rule_package_v2_payload):
    payload = _v2_save_payload(rule_package_v2_payload)
    for index, process in enumerate(payload["route_catalog"]["processes"], start=0):
        process["template_group_aliases"] = [
            {
                "source_operation_id": 11 + index,
                "alias": process["display_name"],
                "template_group_id": f"group-{11 + index}",
                "template_group_key": f"group-{11 + index}",
                "template_group_name": process["display_name"],
                "template_group_path": [f"group-{11 + index}"],
            }
        ]

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)

    assert saved.status_code == 200
    body = saved.json()
    assert body["status"] == "published"


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


@pytest.mark.parametrize("invalid_route", ["stale", "manifest_mismatch"])
def test_publish_rejects_noncurrent_or_inconsistent_route_before_superseding(
    lifecycle_client, rule_package_v2_payload, invalid_route,
):
    payload = _v2_save_payload(rule_package_v2_payload)
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert published.status_code == 200

    async def seed_current_route():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add(NormalizedRouteVersion(id=32, project_id=12, version=2, route_json="[]"))
            await db.commit()

    asyncio.run(seed_current_route())
    if invalid_route == "manifest_mismatch":
        payload["route_version_id"] = 32

    precheck = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
    assert precheck.status_code == 200
    assert precheck.json()["ok"] is False
    assert any(item["code"] == "route_version" and item["status"] == "blocking"
               for item in precheck.json()["checklist"])

    rejected = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert rejected.status_code in {409, 422}

    async def persisted_packages():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return (await db.execute(select(FinalizedRulePackage))).scalars().all()

    packages = asyncio.run(persisted_packages())
    assert len(packages) == 1
    assert packages[0].id == published.json()["id"]
    assert packages[0].status == "published"


@pytest.fixture
def demo_publication_payload(lifecycle_client, rule_package_v2_payload):
    """A small publishable package whose mapped route is independently specified."""
    payload = _v2_save_payload(rule_package_v2_payload)
    payload["route_catalog"]["processes"] = [payload["route_catalog"]["processes"][3]]
    process = payload["route_catalog"]["processes"][0]
    process["main"] = True
    process["constraints"] = {"requires": [], "must_run_after": [], "must_run_before": [], "conflicts_with": []}
    payload["route_rules"]["rules"] = []
    payload["test_cases"] = []

    async def seed_route():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.mappings_json = json.dumps([{
                "source_operation_id": 14,
                "alias": "铣槽",
                "template_group_key": "slot",
                "template_group_id": "slot",
                "template_group_name": "槽",
                "template_group_path": ["槽"],
                "feature_selections": ["槽类特征"],
            }], ensure_ascii=False)
            template.mapping_output_json = json.dumps([{
                "process_name": "铣槽",
                "process_type": "加工工序",
                "precision": "粗加工",
                "steps": [{"step_name": "铣削槽", "candidates": {"槽": ["槽类特征"]}, "step_id": "slot.mill"}],
                "process_id": "process_mill_slot",
            }], ensure_ascii=False)
            await db.commit()

    asyncio.run(seed_route())
    return payload


def test_precheck_preserves_segment_ids_for_rule_repair_navigation(
    lifecycle_client,
    demo_publication_payload,
    monkeypatch,
):
    async def reject_unconfirmed_rule_sources(*args, **kwargs):
        raise HTTPException(409, {
            "message": "人工规则来源尚未确认。",
            "rule_ids": ["user.quench"],
            "segment_ids": ["segment-quench"],
        })

    monkeypatch.setattr(
        "app.routers.extract.require_confirmed_user_rule_sources",
        reject_unconfirmed_rule_sources,
    )
    response = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck",
        json=demo_publication_payload,
    )

    assert response.status_code == 200
    blocker = next(item for item in response.json()["blockers"] if item["code"] == "user_rule_sources_unconfirmed")
    assert blocker["rule_ids"] == ["user.quench"]
    assert blocker["segment_ids"] == ["segment-quench"]


def test_publish_freezes_three_demo_tables_and_source_versions(lifecycle_client, demo_publication_payload):
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert set(body["demo_tables"]) == {"factor_table", "full_route_table", "rule_table"}
    assert body["demo_tables"]["full_route_table"] == [{
        "process_name": "铣槽", "process_type": "加工工序", "precision": "粗加工",
        "steps": [{"step_name": "铣削槽", "candidates": {"槽": ["槽类特征"]}, "step_id": "slot.mill"}],
        "process_id": "process_mill_slot",
    }]
    assert body["demo_tables"]["rule_table"] == [{"target": "process_mill_slot", "when": True}]
    assert body["export_sources"]["route_version_id"] == 31
    assert body["export_sources"]["workflow_revision"] == 0
    assert body["export_sources"]["template_revision"] == 1
    assert body["export_sources"]["compiler_version"] == "demo-three-table/5"
    assert body["export_sources"]["rule_package_content_hash"] == body["content_hash"]
    assert len(body["export_sources"]["demo_tables_hash"]) == 64
    assert body["export_error"] is None

    async def change_current_mapping():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.mapping_output_json = "[]"
            template.template_revision = 2
            await db.commit()

    asyncio.run(change_current_mapping())
    latest = lifecycle_client.get("/api/extract/finalized-rule-packages/latest", params={"project_id": 12})
    assert latest.status_code == 200
    assert latest.json()["demo_tables"] == body["demo_tables"]
    assert latest.json()["export_sources"] == body["export_sources"]


def test_publication_projects_mapped_steps_and_freezes_original_source(lifecycle_client, demo_publication_payload):
    payload = deepcopy(demo_publication_payload)
    payload['route_catalog']['processes'][0]['steps'].append({'step_id': 'slot.unmapped', 'name': '未映射工步'})

    async def add_unmapped_step():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            route = json.loads(template.mapping_output_json)
            route[0]['steps'].append({'step_id': 'slot.unmapped', 'step_name': '未映射工步', 'candidates': {}})
            template.mapping_output_json = json.dumps(route, ensure_ascii=False)
            await db.commit()
    asyncio.run(add_unmapped_step())

    checked = lifecycle_client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
    assert checked.status_code == 200, checked.text
    assert checked.json()['ok'] is True, checked.text
    assert checked.json()['export_summary']['exported_step_count'] == 1
    assert checked.json()['export_summary']['excluded_steps'][0]['step_id'] == 'slot.unmapped'
    published = lifecycle_client.post('/api/extract/finalized-rule-packages', json=payload)
    assert published.status_code == 200, published.text
    body = published.json()
    assert [s['step_id'] for s in body['demo_tables']['full_route_table'][0]['steps']] == ['slot.mill']
    assert body['export_sources']['compiler_version'] == 'demo-three-table/5'
    assert len(body['export_sources']['source_full_route_table'][0]['steps']) == 2
    assert body['export_sources']['mapping_output_hash'] != body['export_sources']['exported_route_hash']
    assert body['export_sources']['projection_report'] == checked.json()['export_summary']
    latest = lifecycle_client.get('/api/extract/finalized-rule-packages/latest', params={'project_id': 12})
    assert latest.json()['demo_tables'] == body['demo_tables'], latest.text
    assert latest.json()['export_error'] is None


@pytest.mark.parametrize('compiler_version', ['demo-three-table/5', 'demo-three-table/4', 'demo-three-table/3', 'demo-three-table/2', 'demo-three-table/1', None, 'unknown'])
def test_projected_snapshot_rejects_rehashed_rule_change(lifecycle_client, demo_publication_payload, compiler_version):
    from app.services.finalized_rule_package_helpers import _snapshot_hash
    saved = lifecycle_client.post('/api/extract/finalized-rule-packages', json=demo_publication_payload)
    assert saved.status_code == 200, saved.text

    async def change_rule_and_rehash():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = await db.get(FinalizedRulePackage, saved.json()['id'])
            tables = json.loads(row.demo_tables_json)
            tables['rule_table'][0] = {'target': 'process_mill_slot', 'when': False}
            sources = json.loads(row.export_sources_json)
            sources['demo_tables_hash'] = _snapshot_hash(tables)
            sources['compiler_version'] = compiler_version
            row.demo_tables_json = json.dumps(tables)
            row.export_sources_json = json.dumps(sources)
            await db.commit()
    asyncio.run(change_rule_and_rehash())
    latest = lifecycle_client.get('/api/extract/finalized-rule-packages/latest', params={'project_id': 12})
    assert latest.status_code == 200, latest.text
    assert latest.json()['demo_tables'] is None
    assert latest.json()['export_error']


def test_fixed_route_publishes_three_tables_and_generates_without_factors(lifecycle_client, demo_publication_payload):
    payload = deepcopy(demo_publication_payload)
    payload["input_schema"]["fields"] = []
    payload["factor_dictionary"] = {"schema_version": "2.0", "fields": []}
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert saved.status_code == 200, saved.text
    body = saved.json()
    assert body["status"] == "published"
    assert set(body["demo_tables"]) == {"factor_table", "full_route_table", "rule_table"}
    assert body["demo_tables"]["factor_table"] == []
    assert body["demo_tables"]["rule_table"] == [{"target": "process_mill_slot", "when": True}]
    generated = lifecycle_client.post("/api/generate/", json={"project_id": 12, "factor_values": {}})
    assert generated.status_code == 200, generated.text
    assert generated.json()["selected_process_ids"] == ["process_mill_slot"]
    assert generated.json()["rule_package_id"] == body["id"]


def test_precheck_rejects_outdated_workflow_revision(lifecycle_client, demo_publication_payload):
    async def advance_workflow():
        async with lifecycle_client.lifecycle_session_factory() as db:
            project = await db.get(Project, 12)
            project.workflow_revision = 1
            await db.commit()

    asyncio.run(advance_workflow())
    checked = lifecycle_client.post(
        "/api/extract/finalized-rule-packages/precheck", json=demo_publication_payload,
    )
    assert checked.status_code == 409, checked.text
    assert checked.json()["detail"]["workflow_revision"] == 1


@pytest.mark.parametrize("mutation", ["project", "route", "package", "package_hash"])
def test_frozen_exports_reject_sources_from_a_different_package(
    lifecycle_client, demo_publication_payload, mutation,
):
    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages", json=demo_publication_payload,
    )
    assert saved.status_code == 200, saved.text

    async def mix_export_source():
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = await db.get(FinalizedRulePackage, saved.json()["id"])
            sources = json.loads(row.export_sources_json)
            if mutation == "project":
                sources["project_id"] = 999
            elif mutation == "route":
                sources["route_version_id"] = 999
            elif mutation == "package_hash":
                sources["rule_package_content_hash"] = "0" * 64
            else:
                catalog = json.loads(row.route_catalog_json)
                catalog["processes"][0]["display_name"] = "其他规则包工序"
                row.route_catalog_json = json.dumps(catalog, ensure_ascii=False)
            row.export_sources_json = json.dumps(sources)
            await db.commit()

    asyncio.run(mix_export_source())
    exported = lifecycle_client.get(
        f"/api/extract/finalized-rule-packages/{saved.json()['id']}",
        params={"project_id": 12},
    )
    assert exported.status_code == 200, exported.text
    assert exported.json()["demo_tables"] is None
    assert exported.json()["export_error"]


@pytest.mark.parametrize("compiler_version", ["demo-three-table/1", "demo-three-table/2", "unknown"])
@pytest.mark.parametrize("changed_rule", [False, True])
def test_legacy_frozen_exports_validate_against_their_own_package_without_live_mapping(
    lifecycle_client, demo_publication_payload, changed_rule, compiler_version,
):
    saved = lifecycle_client.post(
        "/api/extract/finalized-rule-packages", json=demo_publication_payload,
    )
    assert saved.status_code == 200, saved.text

    async def make_legacy_snapshot():
        from app.services.finalized_rule_package_helpers import _snapshot_hash
        from app.services.rule_packages.demo_tables import compile_demo_tables
        from app.services.rule_packages.lifecycle import v2_package_from_row

        async with lifecycle_client.lifecycle_session_factory() as db:
            row = await db.get(FinalizedRulePackage, saved.json()["id"])
            sources = json.loads(row.export_sources_json)
            sources.pop("rule_package_content_hash")
            for key in ("source_full_route_table", "exported_route_hash", "projection_report"):
                sources.pop(key)
            sources["compiler_version"] = compiler_version
            tables = compile_demo_tables(
                v2_package_from_row(row), json.loads(row.demo_tables_json)["full_route_table"],
                _legacy_snapshot=True,
            )
            if changed_rule:
                tables["rule_table"][0] = {"target": "process_mill_slot", "when": {
                    "field": "selected_processes", "op": "contains", "value": "process_mill_slot",
                }}
            row.demo_tables_json = json.dumps(tables)
            sources["demo_tables_hash"] = _snapshot_hash(tables)
            row.export_sources_json = json.dumps(sources)
            template = await db.get(ProjectGroupTemplate, 1)
            template.mapping_output_json = "[]"
            await db.commit()
            return tables

    frozen_legacy_tables = asyncio.run(make_legacy_snapshot())
    response = lifecycle_client.get(
        f"/api/extract/finalized-rule-packages/{saved.json()['id']}", params={"project_id": 12},
    )
    assert response.status_code == 200, response.text
    if changed_rule or compiler_version != "demo-three-table/1":
        assert response.json()["demo_tables"] is None
        assert response.json()["export_error"]
    else:
        assert response.json()["demo_tables"] == frozen_legacy_tables
        assert response.json()["export_error"] is None


@pytest.mark.parametrize("variant", [
    "required_bool", "optional_enum", "dictionary_requiredness",
    "normalized_cad_option", "group_path_multi_enum", "optional_negation",
    "optional_inequality", "optional_empty_collection", "free_route_order",
])
@pytest.mark.parametrize("tamper", [False, True])
def test_v1_frozen_export_survives_compiler_evolution_but_rejects_changed_rules(
    lifecycle_client, variant, tamper,
):
    from app.services.finalized_rule_package_helpers import _snapshot_hash
    from app.services.rule_packages.contracts import RulePackageV2
    from app.services.rule_packages.hashing import rule_package_content_hash

    field = {"key": "choice", "label": "选择", "type": "boolean", "required": True}
    factor = {"key": "choice", "label": "选择", "type": "bool",
              "source": "manual_defaults.choice", "visible": True, "required": True}
    rules = []
    if variant in {"optional_enum", "optional_negation", "optional_inequality"}:
        field.update(type="single_select", required=False, allow_custom=False, options=[{"value": "A", "label": "A"}])
        factor.update(type="enum", options=["A"])
        factor.pop("required")
    elif variant == "dictionary_requiredness":
        factor.pop("required")
    elif variant == "normalized_cad_option":
        field = {"key": "cad.features", "label": "特征", "type": "multi_select",
                 "allow_custom": False, "options": [{"value": "孔(盲孔)", "label": "盲孔"}]}
        factor = {"key": "feature_type", "label": "特征", "type": "enum",
                  "source": "input_json[].features[].feature_select", "visible": False, "options": ["孔(盲孔)"]}
    elif variant == "group_path_multi_enum":
        field = {"key": "cad.paths", "label": "分组", "type": "multi_select",
                 "source": "input_json[].group_path", "allow_custom": False, "options": [{"value": "A", "label": "A"}]}
        factor = {"key": "cad.paths", "label": "分组", "type": "multi_enum",
                  "source": "input_json[].group_path", "visible": False, "options": ["A"]}
    elif variant == "optional_empty_collection":
        field = {"key": "choice", "label": "选择", "type": "multi_select",
                 "allow_custom": False, "options": [{"value": "A", "label": "A"}]}
        factor.update(type="multi_enum", options=["A"])
        factor.pop("required")
    if variant == "optional_negation":
        rules = [{"rule_id": "legacy-not", "when": {"not": {"field": "choice", "op": "eq", "value": "A"}},
                  "then": {"include_process_ids": ["main"]}}]
    elif variant in {"optional_inequality", "optional_empty_collection"}:
        rules = [{"rule_id": "legacy-optional",
                  "when": {"field": "choice", "op": "neq" if variant == "optional_inequality" else "contains_all",
                           "value": "A" if variant == "optional_inequality" else []},
                  "then": {"include_process_ids": ["main"]}}]
    dictionary_field = deepcopy(field)
    if variant == "dictionary_requiredness":
        dictionary_field["required"] = False
    package = RulePackageV2.model_validate({
        "manifest": {"package_name": "legacy-frozen", "project_id": 12, "route_version_id": 31, "scope": {"key": "12"}},
        "factor_dictionary": {"fields": [dictionary_field]}, "input_schema": {"fields": [field]},
        "route_catalog": {"processes": [{"process_id": "main", "display_name": "清洗", "main": True}]},
        "route_rules": {"rules": rules},
    })
    tables = {
        "factor_table": [factor],
        "full_route_table": [{"process_id": "main", "process_name": "清洗", "process_type": "辅助工序", "precision": "辅助工序", "steps": []}],
        "rule_table": [{"target": "main", "required": True}],
    }
    if variant == "free_route_order":
        # V1 preserved mapped order when no explicit ordering constrained it.
        other = package.route_catalog.processes[0].model_copy(update={"process_id": "other", "display_name": "标记", "default_sequence": 10})
        package.route_catalog.processes.insert(0, other)
        tables["full_route_table"].insert(0, {**tables["full_route_table"][0], "process_id": "other", "process_name": "标记"})
        tables["rule_table"].insert(0, {"target": "other", "required": True})
    if tamper:
        tables["rule_table"] = [{"target": "main", "when": False}]

    async def store_frozen():
        native = package.model_dump(mode="json", by_alias=True)
        async with lifecycle_client.lifecycle_session_factory() as db:
            row = FinalizedRulePackage(
                project_id=12, route_version_id=31, version=1, package_name="legacy-frozen", status="published",
                manifest_json=json.dumps(native["manifest"]), factor_dictionary_json=json.dumps(native["factor_dictionary"]),
                input_schema_json=json.dumps(native["input_schema"]), route_catalog_json=json.dumps(native["route_catalog"]),
                route_rules_json=json.dumps(native["route_rules"]), test_cases_json="[]",
                demo_tables_json=json.dumps(tables), content_hash=rule_package_content_hash(package),
                export_sources_json=json.dumps({"compiler_version": "demo-three-table/1", "project_id": 12,
                    "route_version_id": 31, "demo_tables_hash": _snapshot_hash(tables)}),
            )
            db.add(row)
            await db.commit()
            return row.id

    row_id = asyncio.run(store_frozen())
    response = lifecycle_client.get(f"/api/extract/finalized-rule-packages/{row_id}", params={"project_id": 12})
    assert response.status_code == 200, response.text
    if tamper:
        assert response.json()["demo_tables"] is None
        assert response.json()["export_error"]
    else:
        assert response.json()["demo_tables"] == tables, response.json()["export_error"]
        assert response.json()["export_error"] is None


def test_publication_requires_template_reimport_after_route_reordered(lifecycle_client, rule_package_v2_payload):
    from app.services.route_analysis import save_normalized_route_version
    payload = _v2_save_payload(rule_package_v2_payload)
    processes = payload["route_catalog"]["processes"]
    processes[0]["default_sequence"], processes[1]["default_sequence"] = 200, 100

    async def reorder():
        async with lifecycle_client.lifecycle_session_factory() as db:
            route = await save_normalized_route_version(
                project_id=12, db=db, source_signature="same-sources", total_docs=1,
                normalized_route=[{"id": p["process_id"], "normalized_step_name": p["display_name"], "sequence": p["default_sequence"]}
                                  for p in sorted(processes, key=lambda p: p["default_sequence"])],
            )
            return route.id

    payload["route_version_id"] = payload["manifest"]["route_version_id"] = asyncio.run(reorder())
    payload["expected_workflow_revision"] = 1
    checked = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
    assert checked.status_code == 200, checked.text
    assert not checked.json()["ok"]
    assert any(i["code"] == "group_template_missing" for i in checked.json()["blockers"])
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert published.status_code == 422, published.text


@pytest.mark.parametrize("explicit_targets", [True, False])
def test_publication_rejects_candidates_from_removed_merged_source(lifecycle_client, demo_publication_payload, explicit_targets):
    payload = deepcopy(demo_publication_payload)
    process = payload["route_catalog"]["processes"][0]
    process["source_operation_ids"] = [900001]
    process["template_group_aliases"] = []

    async def seed_stale_lineage():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add_all([
                DocumentOperationDetail(project_id=12, pdf_name="fixture.pdf", operation_seq=10, operation_name="铣槽", operation_content="铣削槽", page_no=1),
                DocumentOperationDetail(project_id=12, pdf_name="fixture.pdf", operation_seq=20, operation_name="铣平面", operation_content="铣平面", page_no=1),
            ])
            template = await db.get(ProjectGroupTemplate, 1)
            template.tree_json = json.dumps([{"path": ["任意分组"], "children": [], "feature_selections": ["槽类特征", "平面"]}], ensure_ascii=False)
            template.mappings_json = "[]"
            template.step_mappings_json = json.dumps([{
                "source_operation_id": source_id, "source_step_order": 1, "source_step_name": name,
                "template_group_path": ["任意分组"], "candidate_features": [feature],
                "status": "confirmed", "source": "user_confirmed",
                "final_targets": [{"process_id": process["process_id"], "step_id": "slot.mill"}] if explicit_targets else [],
            } for source_id, name, feature in [(900001, "铣槽", "槽类特征"), (900002, "铣平面", "平面")]], ensure_ascii=False)
            mapped = json.loads(template.mapping_output_json)
            mapped[0]["steps"][0]["candidates"] = {"任意分组": ["槽类特征", "平面"]}
            template.mapping_output_json = json.dumps(mapped, ensure_ascii=False)
            await db.commit()

    asyncio.run(seed_stale_lineage())
    checked = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
    assert checked.status_code == 200, checked.text
    assert not checked.json()["ok"]
    assert any(i["code"] == "stale_step_mapping" for i in checked.json()["blockers"])
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert published.status_code == 422, published.text


def test_repeated_mapping_deletions_and_relinks_publish_only_current_saved_features(
    lifecycle_client, demo_publication_payload,
):
    client = lifecycle_client
    payload = deepcopy(demo_publication_payload)
    payload["route_catalog"]["processes"][0]["source_operation_ids"] = [900001]
    payload["route_catalog"]["processes"][0]["template_group_aliases"] = []

    async def seed_step_source():
        async with client.lifecycle_session_factory() as db:
            db.add(DocumentOperationDetail(
                project_id=12, document_id=None, pdf_name="fixture.pdf", operation_seq=10,
                operation_name="铣槽", operation_content="铣削槽", page_no=1,
            ))
            template = (await db.execute(select(ProjectGroupTemplate))).scalar_one()
            template.tree_json = json.dumps([
                {"key": "slot", "name": "槽", "path": ["槽"], "children": [], "feature_selections": ["通槽"]},
                {"key": "face", "name": "端面", "path": ["端面"], "children": [], "feature_selections": ["平面"]},
            ], ensure_ascii=False)
            template.mappings_json = "[]"
            template.step_mappings_json = "[]"
            await db.commit()

    asyncio.run(seed_step_source())
    operations = [{
        "operation_id": 7001, "process_id": "process_mill_slot",
        "operation_name": "铣槽", "source_operation_ids": [900001],
        "process_type": "加工工序", "precision": "粗加工",
        "steps": [{
            "step_id": "slot.mill", "step_name": "铣削槽", "source_operation_id": 900001,
            "source_step_order": 1, "source_step_name": "铣槽",
        }],
    }]
    slot = {
        "source_operation_id": 900001, "source_operation_name": "铣槽", "source_step_order": 1,
        "source_step_name": "铣槽", "template_group_path": ["槽"],
        "candidate_features": ["通槽"], "status": "confirmed", "source": "user_confirmed",
        "final_targets": [{"process_id": "process_mill_slot", "step_id": "slot.mill"}],
    }
    face = {**slot, "template_group_path": ["端面"], "candidate_features": ["平面"]}
    revision = 1
    for mappings, ready in [([slot], False), ([slot, face], True), ([face], False),
                            ([], False), ([slot, face], True), ([slot], False), ([slot, face], True)]:
        saved = client.put("/api/extract/group-templates/step-mappings", json={
            "project_id": 12, "expected_template_revision": revision,
            "replace_all": True, "operations": operations, "mappings": mappings,
        })
        assert saved.status_code == 200, saved.text
        revision += 1
        current = client.get("/api/extract/group-templates/current", params={"project_id": 12}).json()
        assert current["template_revision"] == revision
        assert [item["template_group_path"] for item in current["step_mappings"]] == [
            item["template_group_path"] for item in mappings
        ]
        checked = client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
        assert checked.status_code == 200, checked.text
        assert checked.json()["ok"] is ready, checked.text
        if not ready:
            assert any(item["code"] == "group_template_mapping_missing" for item in checked.json()["blockers"])

    published = client.post("/api/extract/finalized-rule-packages", json=payload)
    assert published.status_code == 200, published.text
    assert published.json()["status"] == "published"
    assert published.json()["export_sources"]["template_revision"] == 8
    assert published.json()["demo_tables"]["full_route_table"][0]["steps"] == [{
        "step_name": "铣削槽", "step_id": "slot.mill",
        "candidates": {"槽": ["通槽"], "端面": ["平面"]},
    }]


def test_published_snapshot_executes_in_actual_downstream_route_engine(
    lifecycle_client, demo_publication_payload,
):
    engine_path = Path(
        "/Users/zhaoyongwei/Desktop/KmAI-Win7-SP1-x64-20261018-r24/"
        "KmMpsMcpServer/skills/process-route-generator/scripts/config_route_engine.py"
    )
    if not engine_path.is_file():
        pytest.skip("The actual downstream CAD engine is not available in this checkout")

    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert saved.status_code == 200, saved.text
    snapshot = saved.json()["demo_tables"]
    table_filenames = {
        "factor_table": "factor_table.json",
        "full_route_table": "full_route_table.json",
        "rule_table": "rule_table.json",
    }
    archive_buffer = io.BytesIO()
    with zipfile.ZipFile(archive_buffer, "w", compression=zipfile.ZIP_STORED) as archive:
        for table_key, filename in table_filenames.items():
            archive.writestr(
                filename,
                json.dumps(snapshot[table_key], ensure_ascii=False, indent=2) + "\n",
            )
    with zipfile.ZipFile(io.BytesIO(archive_buffer.getvalue())) as archive:
        assert sorted(archive.namelist()) == sorted(table_filenames.values())
        exported_tables = {
            table_key: json.loads(archive.read(filename).decode("utf-8"))
            for table_key, filename in table_filenames.items()
        }
    spec = importlib.util.spec_from_file_location("published_snapshot_route_engine", engine_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    engine = module.ConfigRouteEngine(
        exported_tables["factor_table"],
        exported_tables["full_route_table"],
        exported_tables["rule_table"],
    )

    result = engine.run({
        "input_json": [{
            "group_path": "槽/",
            "features": [{"feature_select": "槽类特征"}],
        }],
        "manual_defaults": {"material_grade": "9Cr18", "cad": {"features": ["槽类特征"]}},
    })

    assert [process["process_name"] for process in result["route"]] == ["铣槽"]
    assert result["route"][0]["precision"] == "粗加工"
    assert result["route"][0]["steps"][0]["candidates"] == {"槽": ["槽类特征"]}
    assert result["route"][0]["steps"][0]["is_last"] is True


@pytest.mark.parametrize('change', ['rename', 'move_step', 'remove_step'])
def test_saved_final_tree_edits_precheck_publish_and_historical_exports_stay_consistent(
    lifecycle_client, demo_publication_payload, change,
):
    client = lifecycle_client
    payload = deepcopy(demo_publication_payload)
    process = payload['route_catalog']['processes'][0]
    process['source_operation_ids'] = [900001]
    process['template_group_aliases'] = []
    operations = [{
        'operation_id': 7001, 'process_id': process['process_id'], 'operation_name': process['display_name'],
        'source_operation_ids': [900001], 'process_type': '加工工序', 'precision': '粗加工',
        'steps': [{'step_id': 'slot.mill', 'step_name': '铣削槽', 'source_operation_id': 900001,
                   'source_step_order': 1, 'source_step_name': '铣槽'}],
    }]
    mapping = {
        'source_operation_id': 900001, 'source_operation_name': '铣槽', 'source_step_order': 1,
        'source_step_name': '铣槽', 'template_group_path': ['槽'], 'candidate_features': ['通槽'],
        'status': 'confirmed', 'source': 'user_confirmed',
        'final_targets': [{'process_id': process['process_id'], 'step_id': 'slot.mill'}],
    }

    async def seed_source():
        async with client.lifecycle_session_factory() as db:
            db.add(DocumentOperationDetail(project_id=12, pdf_name='fixture.pdf', operation_seq=10,
                                           operation_name='铣槽', operation_content='铣削槽', page_no=1))
            template = await db.get(ProjectGroupTemplate, 1)
            template.tree_json = json.dumps([{
                'key': 'slot', 'name': '槽', 'path': ['槽'], 'children': [],
                'feature_selections': ['通槽'],
            }], ensure_ascii=False)
            template.mappings_json = '[]'
            template.step_mappings_json = '[]'
            await db.commit()

    asyncio.run(seed_source())
    initial_mapping = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': 12, 'expected_template_revision': 1, 'replace_all': True,
        'operations': operations, 'mappings': [mapping],
    })
    assert initial_mapping.status_code == 200, initial_mapping.text
    checked = client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
    assert checked.status_code == 200 and checked.json()['ok'], checked.text
    initial = client.post('/api/extract/finalized-rule-packages', json=payload)
    assert initial.status_code == 200, initial.text
    frozen = initial.json()['demo_tables']

    if change == 'rename':
        operations[0]['operation_name'] = '精铣槽（已改名）'
        operations[0]['steps'][0]['step_name'] = '精铣槽底'
    elif change == 'move_step':
        operations[0]['process_id'] = 'moved_slot_process'
        mapping['final_targets'][0]['process_id'] = 'moved_slot_process'
    else:
        operations[0]['steps'] = []
    updated = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': 12, 'expected_template_revision': 2, 'replace_all': True,
        'operations': operations, 'mappings': [] if change == 'remove_step' else [mapping],
    })
    assert updated.status_code == 200, updated.text
    stale_save = client.put('/api/extract/group-templates/step-mappings', json={
        'project_id': 12, 'expected_template_revision': 2, 'replace_all': True,
        'operations': operations, 'mappings': [mapping],
    })
    assert stale_save.status_code == 409, stale_save.text
    stale_precheck = client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
    assert stale_precheck.status_code == 200 and not stale_precheck.json()['ok'], stale_precheck.text
    assert client.post('/api/extract/finalized-rule-packages', json=payload).status_code == 422

    if change != 'remove_step':
        if change == 'rename':
            process['display_name'] = operations[0]['operation_name']
            process['steps'][0]['name'] = operations[0]['steps'][0]['step_name']
        else:
            process['process_id'] = 'moved_slot_process'
        ready = client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
        assert ready.status_code == 200 and ready.json()['ok'], ready.text
        for version in (2, 3):
            published = client.post('/api/extract/finalized-rule-packages', json=payload)
            assert published.status_code == 200, published.text
            assert published.json()['version'] == version
            assert published.json()['demo_tables']['full_route_table'] == updated.json()['mapping_output']
        latest = client.get('/api/extract/finalized-rule-packages/latest', params={'project_id': 12})
        assert latest.json()['version'] == 3
    historical = client.get(f"/api/extract/finalized-rule-packages/{initial.json()['id']}", params={'project_id': 12})
    assert historical.status_code == 200 and historical.json()['demo_tables'] == frozen, historical.text


def test_precheck_and_publish_reject_empty_mapped_route_without_creating_package(
    lifecycle_client, demo_publication_payload,
):
    async def clear_route():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            template.mapping_output_json = "[]"
            await db.commit()

    asyncio.run(clear_route())
    precheck = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=demo_publication_payload)
    assert precheck.status_code == 200
    assert precheck.json()["ok"] is False
    assert any(item["code"] == "demo_tables" and item["status"] == "blocking"
               for item in precheck.json()["checklist"])
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert saved.status_code == 422
    assert "全集路线" in saved.json()["detail"]["message"]

    async def package_count():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return len((await db.execute(select(FinalizedRulePackage))).scalars().all())

    assert asyncio.run(package_count()) == 0


def test_precheck_rejects_missing_machining_precision_with_process_location(
    lifecycle_client, demo_publication_payload,
):
    async def clear_precision():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            rows = json.loads(template.mapping_output_json)
            rows[0]["precision"] = ""
            template.mapping_output_json = json.dumps(rows, ensure_ascii=False)
            await db.commit()

    asyncio.run(clear_precision())
    precheck = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=demo_publication_payload)
    assert precheck.status_code == 200
    body = precheck.json()
    assert body["ok"] is False
    assert any(item["code"] == "missing_process_precision" and "铣槽" in item["message"]
               for item in body["blockers"])

    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert published.status_code == 422
    assert "铣槽" in published.text

    async def package_count():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return len((await db.execute(select(FinalizedRulePackage))).scalars().all())

    assert asyncio.run(package_count()) == 0


def test_legacy_package_reports_missing_snapshot_without_using_current_mapping(lifecycle_client, rule_package_v2_payload):
    async def seed_package():
        async with lifecycle_client.lifecycle_session_factory() as db:
            db.add(FinalizedRulePackage(
                project_id=12, route_version_id=31, version=1, package_name="legacy-v2",
                schema_version="2.0", status="published",
                manifest_json=json.dumps(rule_package_v2_payload["manifest"]),
                input_schema_json=json.dumps(rule_package_v2_payload["input_schema"]),
                route_catalog_json=json.dumps(rule_package_v2_payload["route_catalog"]),
                route_rules_json=json.dumps(rule_package_v2_payload["route_rules"]),
            ))
            await db.commit()

    asyncio.run(seed_package())
    latest = lifecycle_client.get("/api/extract/finalized-rule-packages/latest", params={"project_id": 12})
    assert latest.status_code == 200
    assert latest.json()["demo_tables"] is None
    assert latest.json()["export_sources"] == {}
    assert "重新发布" in latest.json()["export_error"]


def test_precheck_explains_unrepresentable_rules_without_superseding_previous_package(
    lifecycle_client, demo_publication_payload,
):
    first = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert first.status_code == 200, first.text
    incompatible = deepcopy(demo_publication_payload)
    incompatible["route_catalog"]["processes"].append({
        "process_id": "process_quench", "process_code": "Q", "display_name": "淬火",
        "phase": "heat_treatment", "default_sequence": 500, "main": False,
        "steps": [],
        "constraints": {"requires": [], "must_run_after": [], "must_run_before": [], "conflicts_with": []},
    })
    incompatible["route_catalog"]["processes"][0]["constraints"]["conflicts_with"] = ["process_quench"]
    target_process = incompatible["route_catalog"]["processes"][0]
    incompatible["route_rules"]["process_configurations"] = [{
        "process_id": target_process["process_id"],
        "occurrence": "always",
        "relations": [{
            "relation_type": "requires",
            "source_process_ids": ["process_quench"],
            "target_process_ids": [target_process["process_id"]],
        }],
    }]

    async def append_mapping_output():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            rows = json.loads(template.mapping_output_json)
            rows.append({"process_name": "淬火", "process_type": "辅助工序", "precision": "辅助工序",
                         "steps": [], "process_id": "process_quench"})
            template.mapping_output_json = json.dumps(rows, ensure_ascii=False)
            await db.commit()

    asyncio.run(append_mapping_output())
    precheck = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=incompatible)
    assert precheck.status_code == 200
    assert precheck.json()["ok"] is False
    assert any(item["code"] == "unsupported_conflicts" for item in precheck.json()["blockers"])
    dependency_blocker = next(
        item for item in precheck.json()["blockers"]
        if item["code"] == "unsupported_requires"
    )
    assert dependency_blocker["process_id"] == target_process["process_id"]
    assert dependency_blocker["process_name"] == target_process["display_name"]
    assert dependency_blocker["prerequisite_process_names"] == ["淬火"]
    assert "第 1 项" in dependency_blocker["message"]
    assert "process_quench" not in dependency_blocker["message"]
    rejected = lifecycle_client.post("/api/extract/finalized-rule-packages", json=incompatible)
    assert rejected.status_code == 422
    latest = lifecycle_client.get("/api/extract/finalized-rule-packages/latest", params={"project_id": 12})
    assert latest.json()["id"] == first.json()["id"]
    assert latest.json()["status"] == "published"


def test_migration_adds_snapshot_columns_without_fabricating_legacy_exports(tmp_path):
    database_path = tmp_path / "snapshot-migration.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")

    async def migrate():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("ALTER TABLE finalized_rule_packages DROP COLUMN demo_tables_json"))
            await conn.execute(text("ALTER TABLE finalized_rule_packages DROP COLUMN export_sources_json"))
            await conn.execute(text("""
                INSERT INTO finalized_rule_packages
                    (project_id, version, package_name, schema_version, status)
                VALUES (12, 1, 'old-v2', '2.0', 'published')
            """))
            await ensure_project_schema(conn)
            row = (await conn.execute(text(
                "SELECT demo_tables_json, export_sources_json FROM finalized_rule_packages"
            ))).mappings().one()
        await engine.dispose()
        return row

    row = asyncio.run(migrate())
    assert row["demo_tables_json"] is None
    assert row["export_sources_json"] is None


def test_reading_superseded_export_returns_its_frozen_tables_and_checks_project(
    lifecycle_client, demo_publication_payload,
):
    first = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert first.status_code == 200, first.text
    second = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert second.status_code == 200, second.text
    historical = lifecycle_client.get(
        f"/api/extract/finalized-rule-packages/{first.json()['id']}", params={"project_id": 12},
    )
    assert historical.status_code == 200
    assert historical.json()["status"] == "superseded"
    assert historical.json()["demo_tables"] == first.json()["demo_tables"]
    assert historical.json()["export_sources"] == first.json()["export_sources"]
    wrong_project = lifecycle_client.get(
        f"/api/extract/finalized-rule-packages/{first.json()['id']}", params={"project_id": 999},
    )
    assert wrong_project.status_code == 404


def test_route_reset_preserves_archived_frozen_export_after_route_foreign_key_is_removed(
    lifecycle_client, demo_publication_payload,
):
    published = lifecycle_client.post(
        '/api/extract/finalized-rule-packages', json=demo_publication_payload,
    )
    assert published.status_code == 200, published.text
    async def reset_after_source_documents_change():
        from app.services.project_workflow_lifecycle import invalidate_project_workflow

        async with lifecycle_client.lifecycle_session_factory() as db:
            project = await db.get(Project, 12)
            await invalidate_project_workflow(db, project, from_step=2)
            await db.commit()

    asyncio.run(reset_after_source_documents_change())
    historical = lifecycle_client.get(
        f"/api/extract/finalized-rule-packages/{published.json()['id']}",
        params={'project_id': 12},
    )
    assert historical.status_code == 200, historical.text
    assert historical.json()['status'] == 'archived'
    assert historical.json()['route_version_id'] is None
    assert historical.json()['demo_tables'] == published.json()['demo_tables']
    assert historical.json()['export_sources'] == published.json()['export_sources']
    assert historical.json()['export_error'] is None


def test_version_lookup_does_not_shadow_condition_field_registry(lifecycle_client):
    response = lifecycle_client.get("/api/extract/finalized-rule-packages/condition-fields")
    assert response.status_code == 200, response.text
    assert response.json()["fields"]


@pytest.mark.parametrize(
    "mapping_status,mapping_source,target_process,is_main,step_disabled",
    [
        ("not_applicable", "user_confirmed", "process_mill_slot", True, False),
        ("not_applicable", "auto_confirmed", "process_mill_slot", False, True),
        ("not_applicable", "user_confirmed", "wrong-process", False, True),
        ("confirmed", "user_confirmed", "process_mill_slot", False, True),
        (None, "user_confirmed", "process_mill_slot", False, True),
    ],
)
def test_publication_excludes_unmapped_machining_for_all_review_statuses(
    lifecycle_client, demo_publication_payload,
    mapping_status, mapping_source, target_process, is_main, step_disabled,
):
    payload = deepcopy(demo_publication_payload)
    payload["route_catalog"]["processes"][0]["main"] = is_main
    payload["route_catalog"]["processes"].append({
        "process_id": "process_inspection", "process_code": "INSPECT", "display_name": "检验",
        "phase": "inspection", "default_sequence": 500, "main": True, "steps": [],
        "constraints": {"requires": [], "must_run_after": [], "must_run_before": [], "conflicts_with": []},
    })

    async def seed_step_review():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            mapped_route = json.loads(template.mapping_output_json)
            mapped_route[0]["steps"][0]["candidates"] = {}
            mapped_route.append({
                "process_name": "检验", "process_type": "辅助工序", "precision": "辅助工序",
                "steps": [], "process_id": "process_inspection",
            })
            template.mapping_output_json = json.dumps(mapped_route, ensure_ascii=False)
            template.step_mappings_json = json.dumps([
                {
                    "source_operation_id": 14,
                    "source_operation_name": "铣槽",
                    "source_step_key": "op_14_s01",
                    "source_step_order": 1,
                    "source_step_name": "铣削槽",
                    "status": mapping_status,
                    "source": mapping_source,
                    "final_targets": [{"process_id": target_process, "step_id": "slot.mill"}],
                }
            ] if mapping_status else [], ensure_ascii=False)
            await db.commit()

    asyncio.run(seed_step_review())
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert published.status_code == 200, published.text
    tables = published.json()["demo_tables"]
    assert [process['process_id'] for process in tables['full_route_table']] == ['process_inspection']
    assert not any(rule['target'] in {'slot.mill', 'process_mill_slot'} for rule in tables['rule_table'])
    assert published.json()['export_sources']['projection_report']['exported_step_count'] == 0


def test_publication_rejects_empty_delivery_after_unmapped_required_process_is_excluded(
    lifecycle_client, demo_publication_payload,
):
    async def remove_reviewed_candidates():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            mapped_route = json.loads(template.mapping_output_json)
            mapped_route[0]["steps"][0]["candidates"] = {}
            template.mapping_output_json = json.dumps(mapped_route, ensure_ascii=False)
            template.step_mappings_json = "[]"
            await db.commit()

    asyncio.run(remove_reviewed_candidates())
    precheck = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=demo_publication_payload)
    assert precheck.status_code == 200, precheck.text
    assert precheck.json()["ok"] is False, precheck.json()
    assert any(item['code'] == 'empty_export_route' for item in precheck.json()['blockers'])
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert published.status_code == 422, published.text

    async def count_publications():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return len((await db.execute(select(FinalizedRulePackage))).scalars().all())

    assert asyncio.run(count_publications()) == 0


@pytest.mark.parametrize('join', ['all', 'any'])
def test_generic_configuration_save_publish_and_generate_roundtrip(lifecycle_client, join):
    from app.services.rule_packages.condition_reviews import _manual_process_field_key
    from app.services.rule_packages.contracts import ProcessConfiguration

    client = lifecycle_client
    processes = [
        {'process_id': 'custom_prepare_17', 'display_name': '下料准备', 'main': True, 'default_sequence': 1, 'steps': [], 'source_operation_ids': [11]},
        {'process_id': 'custom_pretreat_29', 'display_name': '预处理', 'main': False, 'default_sequence': 2, 'steps': [], 'source_operation_ids': [12]},
        {'process_id': 'custom_finish_43', 'display_name': '表面精整', 'main': False, 'default_sequence': 3, 'steps': [], 'source_operation_ids': [13]},
    ]
    switch = _manual_process_field_key('custom_pretreat_29')
    fields = [
        {'key': switch, 'label': '是否需要预处理', 'category': '项目', 'type': 'boolean', 'operators': ['eq'], 'source': '用户直接设定', 'allow_custom': False, 'options': []},
        {'key': 'project_factor.treatment_class', 'label': '处理类别', 'category': '项目', 'type': 'single_select', 'operators': ['eq'], 'source': '用户直接设定', 'allow_custom': False, 'options': [{'value': value, 'label': value} for value in ('A', 'B', 'C')]},
        {'key': 'project_factor.needs_finish', 'label': '是否要求精整', 'category': '项目', 'type': 'boolean', 'operators': ['eq'], 'source': '用户直接设定', 'allow_custom': False, 'options': []},
    ]
    configurations = [
        {'process_id': 'custom_prepare_17', 'occurrence': 'always', 'when': None, 'relations': []},
        {'process_id': 'custom_pretreat_29', 'occurrence': 'manual', 'when': {'field': switch, 'op': 'eq', 'value': True}, 'relations': []},
        {'process_id': 'custom_finish_43', 'occurrence': 'conditional', 'when': {join: [
            {'field': 'project_factor.treatment_class', 'op': 'eq', 'value': 'A'},
            {'field': 'project_factor.needs_finish', 'op': 'eq', 'value': True},
        ]}, 'relations': [{'relation_type': 'trigger_after', 'source_process_ids': ['custom_pretreat_29'], 'target_process_ids': ['custom_finish_43'], 'source_match': 'all'}]},
    ]

    async def seed_generic_route():
        async with client.lifecycle_session_factory() as db:
            route = await db.get(NormalizedRouteVersion, 31)
            route.route_json = json.dumps([{'id': process['process_id'], 'normalized_step_name': process['display_name']} for process in processes], ensure_ascii=False)
            template = await db.get(ProjectGroupTemplate, 1)
            template.mapping_output_json = json.dumps([{'process_id': process['process_id'], 'process_name': process['display_name'], 'process_type': '辅助工序', 'precision': '辅助工序', 'steps': []} for process in processes], ensure_ascii=False)
            template.step_mappings_json = '[]'
            await db.commit()

    asyncio.run(seed_generic_route())
    confirmed = []
    for index, configuration in enumerate(configurations):
        response = client.post('/api/extract/finalized-rule-packages/rule-conditions/configuration', json={
            'project_id': 12, 'route_id': 31, 'segment_id': configuration['process_id'], 'process_id': configuration['process_id'],
            'source_text': f'用户配置：{processes[index]["display_name"]}',
            'candidate': {'kind': 'process_configuration', 'configuration': configuration, 'field_definitions': [] if index == 0 else fields[:1] if index == 1 else fields[1:]},
            'processes': [{key: process[key] for key in ('process_id', 'display_name', 'main')} for process in processes],
        })
        assert response.status_code == 200, response.text
        review = response.json()['review']
        assert ProcessConfiguration.model_validate(review['confirmed']['configuration']) == ProcessConfiguration.model_validate(configuration)
        confirmed.append({**configuration, 'source': 'user_confirmed', 'source_segment_id': configuration['process_id'], 'source_text': review['source_text'], 'confirmed_by': review['confirmed_by'], 'confirmed_at': review['confirmed_at']})

    input_fields = [{key: value for key, value in field.items() if key not in {'category', 'operators'}} for field in fields]
    compiled = client.post('/api/extract/finalized-rule-packages/compile', json={
        'project_id': 12, 'route_version_id': 31, 'package_name': '通用工序配置',
        'fields': input_fields, 'processes': processes, 'process_configurations': confirmed,
    })
    assert compiled.status_code == 200, compiled.text
    assert compiled.json()['validation']['valid'] is True, compiled.text
    package = compiled.json()['package']
    payload = {
        'project_id': 12, 'route_version_id': 31, 'package_name': '通用工序配置', 'schema_version': '2.0',
        'rule_report_md': '# 通用工序配置验收', **package,
    }
    checked = client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
    assert checked.status_code == 200, checked.text
    assert checked.json()['ok'] is True, checked.text
    published = client.post('/api/extract/finalized-rule-packages', json=payload)
    assert published.status_code == 200, published.text
    assert published.json()['status'] == 'published'
    latest = client.get('/api/extract/finalized-rule-packages/latest', params={'project_id': 12})
    assert latest.status_code == 200, latest.text
    assert latest.json()['route_rules']['process_configurations'] == published.json()['route_rules']['process_configurations']
    assert [(option['value'], option['label']) for option in latest.json()['input_schema']['fields'][1]['options']] == [('A', 'A'), ('B', 'B'), ('C', 'C')]

    # Hand-specified truth tables cover arbitrary IDs, false manual choice,
    # all/any conditions and the trigger gate through the public API.
    cases = [(True, 'A', True, True), (True, 'A', False, join == 'any'),
             (True, 'B', True, join == 'any'), (True, 'B', False, False),
             (False, 'A', True, False), (False, 'B', False, False)]
    for enabled, category, finish, expected_finish in cases:
        generated = client.post('/api/generate/', json={
            'project_id': 12, 'factor_values': {switch: enabled, 'project_factor.treatment_class': category, 'project_factor.needs_finish': finish},
            'input_metadata': {field['key']: {'origin': 'manual'} for field in fields},
        })
        assert generated.status_code == 200, generated.text
        expected_ids = ['custom_prepare_17'] + (['custom_pretreat_29'] if enabled else []) + (['custom_finish_43'] if expected_finish else [])
        assert generated.json()['selected_process_ids'] == expected_ids
        assert generated.json()['rule_package_id'] == published.json()['id']
        assert generated.json()['output_mode'] == 'finalized_rule_package_v2'


@pytest.mark.parametrize("field", [
    {"key": "length", "label": "长度", "type": "number", "validation": {"min": 0, "max": 10}},
    {"key": "text", "label": "文本", "type": "string", "validation": {"min_length": 1, "max_length": 3}},
    {"key": "choices", "label": "多选", "type": "multi_select",
     "options": [{"value": item, "label": item} for item in ["A", "B", "C"]],
     "validation": {"min_length": 1, "max_length": 2}},
])
def test_new_publication_preserves_supported_input_validation(
    lifecycle_client, demo_publication_payload, field,
):
    payload = deepcopy(demo_publication_payload)
    payload["input_schema"]["fields"] = [deepcopy(field)]
    payload["factor_dictionary"] = {"fields": [deepcopy(field)]}
    response = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True, response.text
    response = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body['demo_tables']['factor_table'][0]['validation'] == field['validation']
    assert body['export_sources']['compiler_version'] == 'demo-three-table/5'
    latest = lifecycle_client.get('/api/extract/finalized-rule-packages/latest', params={'project_id': 12})
    assert latest.json()['demo_tables'] == body['demo_tables'], latest.text
    assert latest.json()['export_error'] is None


@pytest.mark.parametrize('source', ['input_json[].features[].feature_select', 'input_json[].group_path'])
def test_publication_rejects_collection_length_that_would_become_per_row_text_length(
    lifecycle_client, demo_publication_payload, source,
):
    payload = deepcopy(demo_publication_payload)
    field = {'key': 'cad_names', 'label': 'CAD 名称集合', 'type': 'multi_select', 'source': source,
             'options': [{'value': 'A', 'label': 'A'}], 'validation': {'max_length': 2}}
    payload['input_schema']['fields'] = [field]
    payload['factor_dictionary'] = {'fields': [deepcopy(field)]}
    response = lifecycle_client.post('/api/extract/finalized-rule-packages/precheck', json=payload)
    assert response.status_code == 200, response.text
    assert response.json()['ok'] is False
    blocker = next(item for item in response.json()['blockers'] if item['code'] == 'unsupported_input_validation')
    assert blocker['field'] == 'cad_names'
    response = lifecycle_client.post('/api/extract/finalized-rule-packages', json=payload)
    assert response.status_code == 422, response.text
    assert any(item["code"] == "unsupported_input_validation" for item in response.json()["detail"]["blockers"])


@pytest.mark.parametrize("validation", [{}, {"min": None, "max": None, "min_length": None, "max_length": None}])
def test_empty_input_validation_still_publishes(lifecycle_client, demo_publication_payload, validation):
    payload = deepcopy(demo_publication_payload)
    field = {"key": "length", "label": "长度", "type": "number", "validation": validation}
    payload["input_schema"]["fields"] = [field]
    payload["factor_dictionary"] = {"fields": [deepcopy(field)]}
    response = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert response.status_code == 200, response.text
    assert response.json()["export_error"] is None


def test_removed_process_factor_does_not_block_publication_on_input_validation(
    lifecycle_client, demo_publication_payload,
):
    payload = deepcopy(demo_publication_payload)
    field = {"key": "length", "label": "长度", "type": "number", "validation": {"min": 0, "max": 10}}
    payload["input_schema"]["fields"] = [field]
    payload["factor_dictionary"] = {"fields": [deepcopy(field)]}
    payload["route_catalog"]["processes"][0]["main"] = False
    payload["route_catalog"]["processes"].append({
        "process_id": "clean", "display_name": "清洗", "main": True, "default_sequence": 1000,
    })
    payload["route_rules"]["rules"] = [{
        "rule_id": "length", "when": {"field": "length", "op": "gt", "value": 0},
        "then": {"include_process_ids": ["process_mill_slot"]},
    }]
    payload["test_cases"] = [{"case_id": "selected", "input": {"length": 5},
                               "expect": {"included_process_ids": ["process_mill_slot"]}}]

    async def remove_machining_mapping():
        async with lifecycle_client.lifecycle_session_factory() as db:
            template = await db.get(ProjectGroupTemplate, 1)
            route = json.loads(template.mapping_output_json)
            route[0]["steps"][0]["candidates"] = {}
            route.append({"process_id": "clean", "process_name": "清洗", "process_type": "辅助工序",
                          "precision": "辅助工序", "steps": []})
            template.mapping_output_json = json.dumps(route, ensure_ascii=False)
            await db.commit()

    asyncio.run(remove_machining_mapping())
    checked = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)
    assert checked.status_code == 200, checked.text
    assert checked.json()["ok"] is True, checked.text
    saved = lifecycle_client.post("/api/extract/finalized-rule-packages", json=payload)
    assert saved.status_code == 200, saved.text
    assert saved.json()["demo_tables"]["factor_table"] == []
    assert saved.json()["demo_tables"]["rule_table"] == [{"target": "clean", "required": True}]
