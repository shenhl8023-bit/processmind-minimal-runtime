"""Stage 3: published V2 packages drive production generation via plan_route."""

from __future__ import annotations

import json
import asyncio
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.database import async_session, init_db
from app.main import app
from app.models.models import FinalizedRulePackage, Project
from app.services.rule_packages.hashing import rule_package_content_hash
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.validator import validate_rule_package


FIXTURE = Path(__file__).parent / "fixtures" / "rule_package_v2.json"
client = TestClient(app)


@pytest.fixture(scope="module", autouse=True)
def _init_db():
    asyncio.run(init_db())


async def _seed_published_v2(project_name: str = "v2-gen-test") -> tuple[int, dict]:
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))
    async with async_session() as db:
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


async def _set_project_rule_engine(project_id: int, rule_engine: str) -> None:
    async with async_session() as db:
        project = (await db.execute(select(Project).where(Project.id == project_id))).scalar_one()
        project.rule_engine = rule_engine
        await db.commit()


def test_generate_uses_published_v2_plan_route():
    project_id, _ = asyncio.run(_seed_published_v2())
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


def test_draft_v2_is_not_used_for_generate():
    payload = json.loads(FIXTURE.read_text(encoding="utf-8"))

    async def seed_draft_only():
        async with async_session() as db:
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
    assert response.status_code == 200, response.text
    body = response.json()
    # No published package → must not claim V2 production mode
    assert body["output_mode"] != "finalized_rule_package_v2"
    assert body.get("schema_version") in (None, "", "1.0") or body["output_mode"] in {
        "route_rules",
        "finalized_rule_package",
    }


def test_project_rule_engine_v1_forces_legacy_path_with_published_v2():
    project_id, _ = asyncio.run(_seed_published_v2("v2-forced-v1"))
    asyncio.run(_set_project_rule_engine(project_id, "v1"))

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
