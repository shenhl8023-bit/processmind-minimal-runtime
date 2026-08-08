import asyncio
from copy import deepcopy
from datetime import datetime, timezone
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    FinalizedRulePackage,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.rule_packages.contracts import RulePackageV2
from app.services.rule_packages.hashing import rule_package_content_hash


@pytest.fixture
def status_context(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'rule-package-status.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as db:
            db.add(Project(
                id=12,
                name="状态测试",
                status="ROUTE_SET_READY",
                workflow_revision=7,
            ))
            await db.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client, session_factory
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


async def _seed_route(
    session_factory,
    *,
    route_id: int = 31,
    version: int = 1,
) -> None:
    async with session_factory() as db:
        db.add(NormalizedRouteVersion(
            id=route_id,
            project_id=12,
            version=version,
            segment_count=1,
            route_json=json.dumps([
                {
                    "id": "process_quench",
                    "normalized_step_name": "淬火",
                },
            ], ensure_ascii=False),
        ))
        await db.commit()


async def _seed_route_review(
    session_factory,
    *,
    condition_status: str,
    candidate: dict | None = None,
    confirmed: bool = False,
) -> None:
    await _seed_route(session_factory)
    payload = candidate or {
        "kind": "condition",
        "when": {
            "field": "precision.grades",
            "op": "contains",
            "value": "孔精加工",
            "factor_id": "precision.hole_finish",
        },
        "then": {
            "include_process_ids": ["process_quench"],
            "exclude_process_ids": [],
        },
    }
    raw = json.dumps(payload, ensure_ascii=False)
    async with session_factory() as db:
        db.add(NormalizedRouteSegmentRuleReview(
            project_id=12,
            route_version_id=31,
            segment_id="process_quench",
            decision="accepted",
            note="",
            summary_json="[]",
            question_trail_json="[]",
            condition_source_text="满足条件时纳入淬火",
            condition_status=condition_status,
            condition_candidate_json=raw,
            condition_confirmed_json=raw if confirmed else None,
        ))
        await db.commit()


def _v2_row(
    payload: dict,
    *,
    status: str = "published",
    version: int = 1,
    route_version_id: int = 31,
) -> FinalizedRulePackage:
    package = RulePackageV2.model_validate(payload)
    return FinalizedRulePackage(
        project_id=12,
        route_version_id=route_version_id,
        version=version,
        package_name=package.manifest.package_name,
        schema_version="2.0",
        status=status,
        manifest_json=json.dumps(payload["manifest"], ensure_ascii=False),
        input_schema_json=json.dumps(payload["input_schema"], ensure_ascii=False),
        route_catalog_json=json.dumps(payload["route_catalog"], ensure_ascii=False),
        route_rules_json=json.dumps(payload["route_rules"], ensure_ascii=False),
        test_cases_json=json.dumps(payload["test_cases"], ensure_ascii=False),
        rule_report_md="# 状态测试",
        validation_report_json=json.dumps({"valid": True}, ensure_ascii=False),
        content_hash=rule_package_content_hash(package),
        created_by="tester",
        published_by="tester" if status == "published" else None,
    )


async def _seed_route_and_package(
    session_factory,
    payload: dict,
    *,
    package_status: str,
) -> int:
    await _seed_route(session_factory)
    async with session_factory() as db:
        row = _v2_row(deepcopy(payload), status=package_status)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


async def _seed_valid_published_v2(session_factory, payload: dict) -> int:
    return await _seed_route_and_package(
        session_factory,
        payload,
        package_status="published",
    )


async def _seed_source_drifted_v2(session_factory, payload: dict) -> int:
    package_payload = deepcopy(payload)
    confirmed_at = datetime(2026, 8, 6, tzinfo=timezone.utc)
    rule = package_payload["route_rules"]["rules"][0]
    rule.update({
        "source": "user_confirmed",
        "source_segment_id": "process_quench",
        "source_text": "材料与硬度满足条件时纳入淬火",
        "confirmed_by": "reviewer",
        "confirmed_at": confirmed_at.isoformat(),
    })
    await _seed_route(session_factory)
    candidate = {
        "kind": "condition",
        "when": rule["when"],
        "then": {
            "include_process_ids": rule["then"]["include_process_ids"],
            "exclude_process_ids": rule["then"]["exclude_process_ids"],
        },
    }
    raw = json.dumps(candidate, ensure_ascii=False)
    async with session_factory() as db:
        db.add(NormalizedRouteSegmentRuleReview(
            project_id=12,
            route_version_id=31,
            segment_id="process_quench",
            condition_source_text="数据库中已经变化的条件",
            condition_status="confirmed",
            condition_candidate_json=raw,
            condition_confirmed_json=raw,
            condition_confirmed_by="reviewer",
            condition_confirmed_at=confirmed_at,
        ))
        row = _v2_row(package_payload)
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


async def _stored_package_status(session_factory, package_id: int) -> str:
    async with session_factory() as db:
        return (await db.execute(
            select(FinalizedRulePackage.status).where(
                FinalizedRulePackage.id == package_id,
            )
        )).scalar_one()


async def _seed_confirmed_review_with_unbound_factor(session_factory) -> None:
    candidate = {
        "kind": "condition",
        "when": {
            "field": "precision.grades",
            "op": "contains",
            "value": "孔精加工",
            "factor_id": "precision.removed_factor",
        },
        "then": {
            "include_process_ids": ["process_quench"],
            "exclude_process_ids": [],
        },
    }
    await _seed_route_review(
        session_factory,
        condition_status="confirmed",
        candidate=candidate,
        confirmed=True,
    )


async def _seed_current_v1_package(session_factory) -> None:
    await _seed_route(session_factory)
    async with session_factory() as db:
        db.add(FinalizedRulePackage(
            project_id=12,
            route_version_id=31,
            version=1,
            package_name="legacy-current",
            schema_version="1.0",
            status="published",
            content_hash="legacy-hash",
            created_by="tester",
            published_by="tester",
        ))
        await db.commit()


async def _seed_status_scenario(
    session_factory,
    payload: dict,
    scenario: str,
) -> None:
    package_payload = deepcopy(payload)
    if scenario == "route_changed":
        await _seed_route(session_factory, route_id=31, version=1)
        await _seed_route(session_factory, route_id=32, version=2)
        row = _v2_row(package_payload, route_version_id=31)
    else:
        await _seed_route(session_factory)
        if scenario == "malformed_v2":
            row = _v2_row(package_payload)
            row.manifest_json = "{"
        elif scenario == "invalid_v2":
            for process in package_payload["route_catalog"]["processes"]:
                process["main"] = False
            row = _v2_row(package_payload)
        elif scenario == "kmai_invalid":
            package_payload["route_rules"]["rules"][0]["when"] = {
                "not": {
                    "field": "material.grade",
                    "op": "eq",
                    "value": "9Cr18",
                    "factor_id": "material.grade",
                },
            }
            package_payload["test_cases"] = []
            row = _v2_row(package_payload)
        else:
            raise AssertionError(f"unknown scenario: {scenario}")
    async with session_factory() as db:
        db.add(row)
        await db.commit()


def test_rule_package_status_returns_404_for_unknown_project(status_context):
    client, _ = status_context

    response = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 999},
    )

    assert response.status_code == 404


def test_rule_package_status_reports_missing_route_without_hiding_publish_state(
    status_context,
):
    client, _ = status_context

    response = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert body["workflow_revision"] == 7
    assert body["route"] is None
    assert body["latest_package"] is None
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is False
    assert [item["code"] for item in body["blockers"]] == [
        "route_missing",
        "no_published_package",
    ]


@pytest.mark.parametrize(
    "condition_status",
    ["draft", "parsing", "pending_confirmation", "invalid"],
)
def test_rule_package_status_reports_each_persisted_pending_review(
    status_context,
    condition_status,
):
    client, session_factory = status_context
    asyncio.run(_seed_route_review(
        session_factory,
        condition_status=condition_status,
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["review_summary"] == {
        "total": 1,
        "confirmed": 0,
        "pending": 1,
        "invalid_factor_bindings": 0,
    }
    assert "pending_rule_reviews" in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is False


def test_rule_package_status_returns_archived_latest_package_as_history(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context
    asyncio.run(_seed_route_and_package(
        session_factory,
        rule_package_v2_payload,
        package_status="archived",
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["latest_package"]["status"] == "archived"
    assert body["package_executable"] is False
    assert body["can_generate"] is False
    assert "no_published_package" in [item["code"] for item in body["blockers"]]


def test_rule_package_status_reports_valid_current_v2_and_kmai_summary(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context
    asyncio.run(_seed_valid_published_v2(session_factory, rule_package_v2_payload))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["package_executable"] is True
    assert body["can_generate"] is True
    assert body["kmai_compatibility"]["available"] is True
    assert body["kmai_compatibility"]["valid"] is True
    assert body["blockers"] == []


def test_rule_package_status_reports_source_drift_without_archiving(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context
    package_id = asyncio.run(_seed_source_drifted_v2(
        session_factory,
        rule_package_v2_payload,
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert "published_rule_sources_changed" in [
        item["code"] for item in body["blockers"]
    ]
    assert body["package_executable"] is False
    assert asyncio.run(_stored_package_status(session_factory, package_id)) == "published"


def test_rule_package_status_orders_source_drift_before_invalid_package(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context
    package_id = asyncio.run(_seed_source_drifted_v2(
        session_factory,
        rule_package_v2_payload,
    ))

    async def invalidate_package() -> None:
        async with session_factory() as db:
            row = await db.get(FinalizedRulePackage, package_id)
            assert row is not None
            catalog = json.loads(row.route_catalog_json)
            for process in catalog["processes"]:
                process["main"] = False
            row.route_catalog_json = json.dumps(catalog, ensure_ascii=False)
            await db.commit()

    asyncio.run(invalidate_package())
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    codes = [item["code"] for item in body["blockers"]]
    assert codes.index("published_rule_sources_changed") < codes.index(
        "published_package_invalid"
    )


def test_rule_package_status_reports_invalid_confirmed_factor_binding(status_context):
    client, session_factory = status_context
    asyncio.run(_seed_confirmed_review_with_unbound_factor(session_factory))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["review_summary"]["invalid_factor_bindings"] == 1
    assert "invalid_factor_bindings" in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is False


def test_rule_package_status_preserves_current_v1_generation_boundary(status_context):
    client, session_factory = status_context
    asyncio.run(_seed_current_v1_package(session_factory))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["latest_package"]["schema_version"] == "1.0"
    assert body["package_executable"] is True
    assert body["can_generate"] is True
    assert body["kmai_compatibility"]["available"] is False


@pytest.mark.parametrize(
    ("scenario", "expected_code"),
    [
        ("route_changed", "published_package_route_changed"),
        ("malformed_v2", "published_package_invalid"),
        ("invalid_v2", "published_package_invalid"),
        ("kmai_invalid", "kmai_incompatible"),
    ],
)
def test_rule_package_status_uses_stable_generate_blockers(
    status_context,
    rule_package_v2_payload,
    scenario,
    expected_code,
):
    client, session_factory = status_context
    asyncio.run(_seed_status_scenario(
        session_factory,
        rule_package_v2_payload,
        scenario,
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert expected_code in [item["code"] for item in body["blockers"]]
    assert body["can_generate"] is False
    if scenario == "kmai_invalid":
        assert body["package_executable"] is True
        assert body["kmai_compatibility"]["available"] is True
        assert body["kmai_compatibility"]["valid"] is False
