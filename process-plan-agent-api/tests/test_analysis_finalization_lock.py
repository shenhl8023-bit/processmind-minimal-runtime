"""Finalization locks only the saved route's step-three authoring surface."""

import asyncio
import json

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.route_analysis import build_saved_normalized_route_response


@pytest.fixture
def locked_route_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'analysis-lock.db'}")
    sessions = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        async with sessions() as db:
            db.add_all([Project(id=9, name="锁定项目", workflow_revision=7),
                        Project(id=10, name="其他项目", workflow_revision=7)])
            await db.flush()
            for route_id, project_id, version in [(89, 9, 1), (90, 9, 2), (100, 10, 1)]:
                db.add(NormalizedRouteVersion(
                    id=route_id, project_id=project_id, version=version,
                    segment_count=1, total_docs=2,
                    route_json=json.dumps([{
                        "id": "seg-1", "sequence": 1, "normalized_step_name": "标记",
                        "doc_coverage": {"hit_docs": 1, "total_docs": 2},
                    }], ensure_ascii=False),
                ))
            await db.flush()
            for route_id, project_id in [(90, 9), (100, 10)]:
                db.add(NormalizedRouteSegmentRuleReview(
                    project_id=project_id, route_version_id=route_id, segment_id="seg-1",
                    decision="accepted", note="第三步原回答", summary_json="[]",
                    question_trail_json="[]", condition_source_text="第四步人工规则",
                    condition_status="confirmed", condition_parser_version="manual",
                    condition_confirmed_by="用户直接设定",
                ))
            await db.commit()

    asyncio.run(setup())

    async def override_db():
        async with sessions() as db:
            yield db

    app.dependency_overrides[get_db] = override_db
    try:
        with TestClient(app) as client:
            yield client, sessions
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _enter(client, route_id=90, project_id=9, revision=7):
    return client.post("/api/extract/workflow/enter-finalization", json={
        "project_id": project_id, "route_id": route_id,
        "expected_workflow_revision": revision,
    })


def _save(client, route_id=90, project_id=9, revision=7):
    return client.post("/api/extract/segment-rule-reviews", json={
        "project_id": project_id, "route_id": route_id,
        "expected_workflow_revision": revision, "segment_id": "seg-1",
        "decision": "accepted", "note": "旧页面迟到回答",
        "summary_lines": [], "question_trail": [],
    })


def test_reading_a_complete_route_does_not_lock_it(locked_route_client):
    client, sessions = locked_route_client

    async def read():
        async with sessions() as db:
            route = await db.get(NormalizedRouteVersion, 90)
            response = await build_saved_normalized_route_response(route, db)
            assert response.model_dump()["analysis_locked"] is False

    asyncio.run(read())
    assert _save(client).status_code == 200


def test_entering_finalization_is_persistent_idempotent_and_rejects_stale_step_three_saves(locked_route_client):
    client, sessions = locked_route_client
    entered = _enter(client)
    assert entered.status_code == 200, entered.text
    assert entered.json()["analysis_locked"] is True
    locked_at = entered.json()["analysis_locked_at"]
    assert locked_at
    again = _enter(client)
    assert again.status_code == 200, again.text
    assert again.json()["analysis_locked_at"] == locked_at
    stale = _save(client)
    assert stale.status_code == 409, stale.text
    assert stale.json()["detail"]["code"] == "analysis_locked"

    async def verify():
        async with sessions() as db:
            route = await db.get(NormalizedRouteVersion, 90)
            response = await build_saved_normalized_route_response(route, db)
            assert response.model_dump()["analysis_locked"] is True
            review = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == 90,
            ))).scalar_one()
            assert review.note == "第三步原回答"
            assert review.condition_source_text == "第四步人工规则"
            assert review.condition_status == "confirmed"

    asyncio.run(verify())


def test_lock_does_not_cross_projects_or_routes(locked_route_client):
    client, sessions = locked_route_client
    assert _enter(client).status_code == 200
    assert _save(client, route_id=100, project_id=10).status_code == 200

    async def verify():
        async with sessions() as db:
            other_route = await db.get(NormalizedRouteVersion, 89)
            assert other_route.analysis_locked_at is None
            other_project = await db.get(NormalizedRouteVersion, 100)
            assert other_project.analysis_locked_at is None

    asyncio.run(verify())


@pytest.mark.parametrize("route_id, project_id, revision, status", [
    (90, 10, 7, 404), (89, 9, 7, 409), (90, 9, 6, 409),
])
def test_failed_entry_cannot_lock_a_route(locked_route_client, route_id, project_id, revision, status):
    client, _ = locked_route_client
    response = _enter(client, route_id, project_id, revision)
    assert response.status_code == status, response.text
    assert _save(client).status_code == 200


def test_unanswered_route_cannot_enter_finalization(locked_route_client):
    client, sessions = locked_route_client

    async def clear_answer():
        async with sessions() as db:
            row = (await db.execute(select(NormalizedRouteSegmentRuleReview).where(
                NormalizedRouteSegmentRuleReview.route_version_id == 90,
            ))).scalar_one()
            await db.delete(row)
            await db.commit()

    asyncio.run(clear_answer())
    response = _enter(client)
    assert response.status_code == 409, response.text
    assert _save(client).status_code == 200


def test_full_reset_unlocks_only_after_success_and_fourth_step_reset_keeps_lock(locked_route_client):
    client, _ = locked_route_client
    assert _enter(client).status_code == 200
    failed = client.post("/api/extract/workflow/reset", json={
        "project_id": 9, "from_step": 3, "expected_workflow_revision": 6,
    })
    assert failed.status_code == 409
    assert _save(client).status_code == 409
    reset_fourth = client.post("/api/extract/workflow/reset", json={
        "project_id": 9, "from_step": 4, "expected_workflow_revision": 7,
    })
    assert reset_fourth.status_code == 200, reset_fourth.text
    assert _save(client, revision=8).status_code == 409
    reset_third = client.post("/api/extract/workflow/reset", json={
        "project_id": 9, "from_step": 3, "expected_workflow_revision": 8,
    })
    assert reset_third.status_code == 200, reset_third.text
    assert _save(client, revision=9).status_code == 200


def test_failed_reset_transaction_does_not_leave_analysis_unlocked(locked_route_client, monkeypatch):
    from app.routers import extract

    client, _ = locked_route_client
    assert _enter(client).status_code == 200
    original = extract.invalidate_project_workflow

    async def failing_reset(*args, **kwargs):
        await original(*args, **kwargs)
        raise RuntimeError("模拟重置事务未完成")

    monkeypatch.setattr(extract, "invalidate_project_workflow", failing_reset)
    with pytest.raises(RuntimeError, match="重置事务未完成"):
        client.post("/api/extract/workflow/reset", json={
            "project_id": 9, "from_step": 3, "expected_workflow_revision": 7,
        })
    assert _save(client).status_code == 409


def test_finalization_lock_does_not_prevent_fourth_step_rule_edits(locked_route_client):
    client, _ = locked_route_client
    assert _enter(client).status_code == 200
    response = client.post("/api/extract/finalized-rule-packages/rule-conditions/draft", json={
        "project_id": 9, "route_id": 90, "expected_workflow_revision": 7,
        "segment_id": "seg-1", "source_text": "第四步新的人工修改",
    })
    assert response.status_code == 200, response.text
    assert response.json()["review"]["source_text"] == "第四步新的人工修改"
    assert _save(client).status_code == 409


def test_schema_upgrade_leaves_old_routes_unlocked_and_is_repeatable(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'legacy-lock.db'}")

    async def run():
        async with engine.begin() as conn:
            await conn.execute(text("""CREATE TABLE normalized_route_versions (
                id INTEGER PRIMARY KEY, project_id INTEGER NOT NULL, version INTEGER,
                source_signature VARCHAR(255), saved_by VARCHAR(100), total_docs INTEGER,
                segment_count INTEGER, route_json TEXT, created_at DATETIME
            )"""))
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("INSERT INTO projects(id, name) VALUES(1, 'legacy')"))
            await conn.execute(text("INSERT INTO normalized_route_versions(id, project_id, version) VALUES(1, 1, 1)"))
            await ensure_project_schema(conn)
            await ensure_project_schema(conn)
            result = await conn.execute(text("SELECT analysis_locked_at FROM normalized_route_versions WHERE id=1"))
            assert result.scalar_one() is None

    try:
        asyncio.run(run())
    finally:
        asyncio.run(engine.dispose())
