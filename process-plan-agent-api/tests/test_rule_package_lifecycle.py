import asyncio
import json
from copy import deepcopy

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import FinalizedRulePackage, NormalizedRouteVersion, Project
from app.models.models import ProjectGroupTemplate
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
            session.add(ProjectGroupTemplate(
                project_id=12,
                original_filename="group-template.xml",
                source_encoding="utf-8",
                part_filename="group-template.prt",
                content_hash="a" * 64,
                feature_dictionary_version="b" * 64,
                source_xml="<Kmsoft />",
                tree_json="[]",
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
                ], ensure_ascii=False),
                step_mappings_json="[]",
                mapping_output_json="[]",
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


def test_precheck_lists_required_template_mapping_blockers_with_reasons(lifecycle_client, rule_package_v2_payload):
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
            ], ensure_ascii=False)
            await db.commit()

    asyncio.run(keep_only_prepare_mapping())

    payload = _v2_save_payload(rule_package_v2_payload)
    response = lifecycle_client.post("/api/extract/finalized-rule-packages/precheck", json=payload)

    assert response.status_code == 200
    body = response.json()
    assert body["ok"] is False
    assert body["checklist"] == [
        {"code": "schema_valid", "label": "规则包结构校验", "status": "passed", "message": "规则包结构校验通过。"},
        {"code": "route_version", "label": "路线版本关联", "status": "passed", "message": "规则包已关联当前路线版本。"},
        {"code": "user_rule_sources", "label": "人工规则确认", "status": "passed", "message": "人工规则来源已确认。"},
        {"code": "template_mapping", "label": "分组模板映射", "status": "blocking", "message": "还有 1 道必要工序未完成分组模板映射。"},
    ]
    assert body["blockers"] == [
        {
            "code": "group_template_mapping_missing",
            "message": "请先完成分组模板映射。",
            "process_id": "process_mill_slot",
            "process_name": "铣槽",
            "severity": "blocking",
            "required_by": ["rule_include"],
            "required_by_labels": ["规则包含引用"],
        }
    ]


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
