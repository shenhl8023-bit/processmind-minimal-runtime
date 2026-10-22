import asyncio
import importlib.util
import io
import json
from copy import deepcopy
from pathlib import Path
import zipfile

import pytest
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
                            {"step_name": step["name"], "candidates": {}, "step_id": step["step_id"]}
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
    assert body["demo_tables"]["rule_table"] == [{"target": "process_mill_slot", "required": True}]
    assert body["export_sources"]["route_version_id"] == 31
    assert body["export_sources"]["workflow_revision"] == 0
    assert body["export_sources"]["template_revision"] == 1
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
        "manual_defaults": {"material_grade": "9Cr18"},
    })

    assert [process["process_name"] for process in result["route"]] == ["铣槽"]
    assert result["route"][0]["precision"] == "粗加工"
    assert result["route"][0]["steps"][0]["candidates"] == {"槽": ["槽类特征"]}
    assert result["route"][0]["steps"][0]["is_last"] is True


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
        "phase": "heat_treatment", "default_sequence": 300, "main": False,
        "steps": [],
        "constraints": {"requires": [], "must_run_after": [], "must_run_before": [], "conflicts_with": []},
    })
    incompatible["route_catalog"]["processes"][0]["constraints"]["conflicts_with"] = ["process_quench"]

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
def test_publication_distinguishes_explicit_general_steps_from_unreviewed_empty_candidates(
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
    assert tables["full_route_table"][0]["steps"][0]["candidates"] == {}
    step_rule = next((rule for rule in tables["rule_table"] if rule["target"] == "slot.mill"), None)
    assert step_rule is None


def test_publication_allows_unmapped_steps_in_required_process(
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
    assert precheck.json()["ok"] is True, precheck.json()
    published = lifecycle_client.post("/api/extract/finalized-rule-packages", json=demo_publication_payload)
    assert published.status_code == 200, published.text

    async def count_publications():
        async with lifecycle_client.lifecycle_session_factory() as db:
            return len((await db.execute(select(FinalizedRulePackage))).scalars().all())

    assert asyncio.run(count_publications()) == 1
