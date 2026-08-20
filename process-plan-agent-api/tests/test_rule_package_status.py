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
    source_text: str = "满足条件时纳入淬火",
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
            condition_source_text=source_text,
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


async def _set_project_status(session_factory, status: str) -> None:
    async with session_factory() as db:
        project = await db.get(Project, 12)
        assert project is not None
        project.status = status
        await db.commit()


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


async def _seed_route_review_and_published_v2(
    session_factory,
    payload: dict,
    *,
    condition_status: str,
    candidate: dict | None = None,
    confirmed: bool = False,
) -> int:
    await _seed_route(session_factory)
    review_candidate = candidate or {
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
    raw = json.dumps(review_candidate, ensure_ascii=False)
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
        row = _v2_row(deepcopy(payload))
        db.add(row)
        await db.commit()
        await db.refresh(row)
        return row.id


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


def test_rule_package_status_does_not_block_on_persisted_mainline_instruction(
    status_context,
):
    client, session_factory = status_context
    asyncio.run(_seed_route_review(
        session_factory,
        condition_status="draft",
        source_text='设置为主工序，始终纳入“淬火”工序。',
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["review_summary"] == {
        "total": 0,
        "confirmed": 0,
        "pending": 0,
        "invalid_factor_bindings": 0,
    }
    assert "pending_rule_reviews" not in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is True


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


# ---------- 状态矩阵:项目未完成路线提取(project_not_ready) ----------

@pytest.mark.parametrize("project_status", ["CREATED", "UPLOADED", "EXTRACTING", "EXTRACT_ERROR", "FAILED"])
def test_rule_package_status_blocks_when_project_not_ready(
    status_context,
    project_status,
):
    client, session_factory = status_context
    asyncio.run(_set_project_status(session_factory, project_status))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert [item["code"] for item in body["blockers"]] == [
        "project_not_ready",
        "route_missing",
        "no_published_package",
    ]
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is False


@pytest.mark.parametrize("project_status", ["CREATED", "UPLOADED", "EXTRACTING", "EXTRACT_ERROR", "FAILED"])
def test_rule_package_status_keeps_package_executable_when_project_not_ready(
    status_context,
    rule_package_v2_payload,
    project_status,
):
    client, session_factory = status_context
    asyncio.run(_set_project_status(session_factory, project_status))
    asyncio.run(_seed_valid_published_v2(session_factory, rule_package_v2_payload))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert [item["code"] for item in body["blockers"]] == ["project_not_ready"]
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is True


@pytest.mark.parametrize("project_status", ["ROUTE_SET_READY", "GENERATED"])
def test_rule_package_status_allows_publish_for_each_publishable_status(
    status_context,
    rule_package_v2_payload,
    project_status,
):
    client, session_factory = status_context
    if project_status != "ROUTE_SET_READY":
        asyncio.run(_set_project_status(session_factory, project_status))
    asyncio.run(_seed_valid_published_v2(session_factory, rule_package_v2_payload))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert "project_not_ready" not in [item["code"] for item in body["blockers"]]
    assert body["can_publish"] is True
    assert body["can_generate"] is True
    assert body["package_executable"] is True


# ---------- 状态矩阵:confirmed 规则确认内容无法解析(视为待确认,阻塞发布) ----------

def test_rule_package_status_treats_unparseable_confirmed_rule_as_pending(
    status_context,
):
    client, session_factory = status_context
    # confirmed_json 是合法 JSON 但无法通过 RuleConditionCandidate schema 校验,
    # loads_candidate 返回 None —— 该确认不可信,必须按待确认处理而非已确认。
    asyncio.run(_seed_route_review(
        session_factory,
        condition_status="confirmed",
        candidate={"malformed": True},
        confirmed=True,
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
    assert [item["code"] for item in body["blockers"]] == [
        "pending_rule_reviews",
        "no_published_package",
    ]
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is False


def test_rule_package_status_counts_parsed_non_condition_confirmation_as_confirmed(
    status_context,
):
    client, session_factory = status_context
    # 合法的 process_relation 确认(可解析但 kind != condition)仍计入 confirmed,
    # 不进入无效绑定检查、不阻塞发布。
    candidate = {
        "kind": "process_relation",
        "relation": {
            "relation_type": "order_after",
            "source_process_ids": ["process_quench"],
            "target_process_ids": ["process_prepare"],
        },
    }
    asyncio.run(_seed_route_review(
        session_factory,
        condition_status="confirmed",
        candidate=candidate,
        confirmed=True,
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["review_summary"] == {
        "total": 1,
        "confirmed": 1,
        "pending": 0,
        "invalid_factor_bindings": 0,
    }
    assert [item["code"] for item in body["blockers"]] == ["no_published_package"]
    assert body["can_publish"] is True
    assert body["can_generate"] is False
    assert body["package_executable"] is False


# ---------- 状态矩阵:能力组合断言 ----------

@pytest.mark.parametrize(
    ("scenario", "expected_blockers", "expected_triple"),
    [
        ("route_only", ["no_published_package"], (True, False, False)),
        (
            "pending_review",
            ["pending_rule_reviews", "no_published_package"],
            (False, False, False),
        ),
        (
            "invalid_factor_binding",
            ["invalid_factor_bindings", "no_published_package"],
            (False, False, False),
        ),
        # 发布专属 blocker 必须只阻塞 publish,不能连带阻塞 generate:
        # 已发布包可用(package_executable=True)但发布被审核/绑定问题阻塞。
        (
            "pending_review_published",
            ["pending_rule_reviews"],
            (False, True, True),
        ),
        (
            "invalid_binding_published",
            ["invalid_factor_bindings"],
            (False, True, True),
        ),
        ("valid_v2", [], (True, True, True)),
        ("source_drift", ["published_rule_sources_changed"], (True, False, False)),
        ("route_changed", ["published_package_route_changed"], (True, False, False)),
        ("malformed_v2", ["published_package_invalid"], (True, False, False)),
        ("invalid_v2", ["published_package_invalid"], (True, False, False)),
        ("kmai_invalid", ["kmai_incompatible"], (True, False, True)),
        ("current_v1", [], (True, True, True)),
    ],
)
def test_rule_package_status_capability_matrix(
    status_context,
    rule_package_v2_payload,
    scenario,
    expected_blockers,
    expected_triple,
):
    client, session_factory = status_context
    if scenario == "route_only":
        asyncio.run(_seed_route(session_factory))
    elif scenario == "pending_review":
        asyncio.run(_seed_route_review(
            session_factory,
            condition_status="pending_confirmation",
        ))
    elif scenario == "invalid_factor_binding":
        asyncio.run(_seed_confirmed_review_with_unbound_factor(session_factory))
    elif scenario == "pending_review_published":
        asyncio.run(_seed_route_review_and_published_v2(
            session_factory,
            rule_package_v2_payload,
            condition_status="pending_confirmation",
        ))
    elif scenario == "invalid_binding_published":
        asyncio.run(_seed_route_review_and_published_v2(
            session_factory,
            rule_package_v2_payload,
            condition_status="confirmed",
            candidate={
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
            },
            confirmed=True,
        ))
    elif scenario == "valid_v2":
        asyncio.run(_seed_valid_published_v2(session_factory, rule_package_v2_payload))
    elif scenario == "source_drift":
        asyncio.run(_seed_source_drifted_v2(session_factory, rule_package_v2_payload))
    elif scenario == "current_v1":
        asyncio.run(_seed_current_v1_package(session_factory))
    else:
        asyncio.run(_seed_status_scenario(session_factory, rule_package_v2_payload, scenario))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert [item["code"] for item in body["blockers"]] == expected_blockers
    assert (
        body["can_publish"],
        body["can_generate"],
        body["package_executable"],
    ) == expected_triple

    if scenario == "valid_v2":
        assert body["route"] == {"id": 31, "version": 1}
        assert body["latest_package"]["id"] > 0
        assert body["latest_package"]["version"] == 1
        assert body["latest_package"]["route_version_id"] == 31
        assert body["latest_package"]["schema_version"] == "2.0"
        assert body["latest_package"]["status"] == "published"
        assert body["latest_package"]["content_hash"]
        assert body["kmai_compatibility"]["available"] is True
        assert body["kmai_compatibility"]["valid"] is True
        assert body["kmai_compatibility"]["factor_catalog_version"]
    elif scenario in ("pending_review_published", "invalid_binding_published"):
        # 发布专属 blocker 只阻塞 publish,不能阻塞 generate。
        assert [item["blocks"] for item in body["blockers"]] == [["publish"]]
    elif scenario == "kmai_invalid":
        assert body["kmai_compatibility"]["available"] is True
        assert body["kmai_compatibility"]["valid"] is False
        assert body["kmai_compatibility"]["error_count"] >= 1


# ---------- 状态矩阵:latest_package 变体与无路线交叉场景 ----------

def test_rule_package_status_reports_superseded_latest_package_as_history(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context
    asyncio.run(_seed_route_and_package(
        session_factory,
        rule_package_v2_payload,
        package_status="superseded",
    ))

    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert body["latest_package"]["status"] == "superseded"
    assert body["package_executable"] is False
    assert body["can_generate"] is False
    assert "no_published_package" in [item["code"] for item in body["blockers"]]


def test_rule_package_status_reports_missing_route_despite_published_package(
    status_context,
    rule_package_v2_payload,
):
    client, session_factory = status_context

    async def seed() -> None:
        async with session_factory() as db:
            db.add(_v2_row(deepcopy(rule_package_v2_payload)))
            await db.commit()

    asyncio.run(seed())
    body = client.get(
        "/api/extract/finalized-rule-packages/status",
        params={"project_id": 12},
    ).json()

    assert [item["code"] for item in body["blockers"]] == ["route_missing"]
    assert body["can_publish"] is False
    assert body["can_generate"] is False
    assert body["package_executable"] is False
