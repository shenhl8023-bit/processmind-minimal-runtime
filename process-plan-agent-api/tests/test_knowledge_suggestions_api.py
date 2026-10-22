import asyncio

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    KnowledgeEvidenceSnapshot,
    KnowledgeRuleSuggestion,
    NormalizedRouteVersion,
    Project,
)
from app.services.db_schema_maintenance import ensure_project_schema


def _client(tmp_path, *, raise_server_exceptions=True):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-suggestions.db'}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with session_factory() as session:
            project = Project(id=1, name="测试项目", status="ROUTE_SET_READY")
            route = NormalizedRouteVersion(
                id=11,
                project_id=1,
                version=1,
                route_json='[{"id":"op-40","normalized_step_name":"淬火"}]',
            )
            evidence = KnowledgeEvidenceSnapshot(
                id=101,
                project_id=1,
                route_version_id=11,
                segment_id="op-40",
                query="硬度",
                item_id="chunk-1",
                content="真空淬火后硬度不低于 56 HRC",
                snapshot_hash="e" * 64,
            )
            session.add_all([project, route, evidence])
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app, raise_server_exceptions=raise_server_exceptions)
    return client, engine


def test_create_suggestion_draft_uses_existing_scoped_evidence(tmp_path):
    client, engine = _client(tmp_path)
    try:
        response = client.post(
            "/api/knowledge/suggestions/draft",
            json={
                "project_id": 1,
                "route_version_id": 11,
                "segment_id": "op-40",
                "suggestion_text": "淬火后硬度不低于 56 HRC。",
                "candidate": {"kind": "condition", "preview": "硬度 >= 56 HRC"},
                "evidence_ids": [101],
            },
        )
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "draft"
        assert body["evidence_ids"] == [101]
        assert body["candidate"]["preview"] == "硬度 >= 56 HRC"
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_legacy_domain_package_suggestions_are_hidden_from_process_knowledge(suggestion_store):
    client, change_row = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200
    suggestion_id = created.json()["id"]
    change_row(
        KnowledgeRuleSuggestion,
        suggestion_id,
        domain_package_ref_json='{"package_id":"legacy","version":1}',
    )

    listed = client.get("/api/knowledge/suggestions", params={"project_id": 1})

    assert listed.status_code == 200
    assert listed.json() == []


def test_legacy_domain_package_suggestions_cannot_be_reviewed(suggestion_store):
    client, change_row = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200
    suggestion_id = created.json()["id"]
    change_row(
        KnowledgeRuleSuggestion,
        suggestion_id,
        domain_package_ref_json='{"package_id":"legacy","version":1}',
    )

    updated = client.patch(
        f"/api/knowledge/suggestions/{suggestion_id}",
        json={"status": "pending_review"},
    )

    assert updated.status_code == 410


@pytest.fixture
def suggestion_store(tmp_path):
    client, engine = _client(tmp_path, raise_server_exceptions=False)

    def change_row(model, row_id, **changes):
        async def update():
            factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)
            async with factory() as session:
                row = await session.get(model, row_id)
                for key, value in changes.items():
                    setattr(row, key, value)
                await session.commit()
        asyncio.run(update())

    yield client, change_row
    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def _suggestion_payload(**changes):
    return {
        "project_id": 1,
        "route_version_id": 11,
        "segment_id": "op-40",
        "title": "淬火硬度要求",
        "suggestion_text": "淬火后硬度不低于 56 HRC。",
        "evidence_ids": [101],
        **changes,
    }


def test_create_suggestion_normalizes_segment_before_checking_evidence(suggestion_store):
    client, _ = suggestion_store

    response = client.post(
        "/api/knowledge/suggestions/draft",
        json=_suggestion_payload(segment_id="  op-40\n"),
    )

    assert response.status_code == 200
    assert response.json()["segment_id"] == "op-40"
    assert response.json()["evidence_ids"] == [101]


@pytest.mark.parametrize("field", ["title", "suggestion_text"])
def test_create_suggestion_rejects_whitespace_only_text(suggestion_store, field):
    client, _ = suggestion_store

    response = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload(**{field: " \n\t "}))

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["title", "suggestion_text", "evidence_ids"])
def test_update_suggestion_rejects_explicit_null_required_values(suggestion_store, field):
    client, _ = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200

    response = client.patch(f"/api/knowledge/suggestions/{created.json()['id']}", json={field: None})

    assert response.status_code == 422


@pytest.mark.parametrize("field", ["title", "suggestion_text"])
def test_update_suggestion_rejects_whitespace_only_text(suggestion_store, field):
    client, _ = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200

    response = client.patch(f"/api/knowledge/suggestions/{created.json()['id']}", json={field: " \n\t "})

    assert response.status_code == 422


@pytest.mark.parametrize("route_json", ["[]", "{}", "not-json", "null", '[{"id":""}]'])
def test_suggestion_requires_segment_present_in_a_valid_saved_route(suggestion_store, route_json):
    client, change_row = suggestion_store
    change_row(NormalizedRouteVersion, 11, route_json=route_json)

    response = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())

    assert response.status_code == 404


@pytest.mark.parametrize("next_status", ["pending_review", "confirmed"])
def test_suggestion_review_rechecks_evidence_scope(suggestion_store, next_status):
    client, change_row = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200
    suggestion_id = created.json()["id"]
    if next_status == "confirmed":
        pending = client.patch(f"/api/knowledge/suggestions/{suggestion_id}", json={"status": "pending_review"})
        assert pending.status_code == 200
    change_row(KnowledgeEvidenceSnapshot, 101, segment_id="other-segment")

    response = client.patch(f"/api/knowledge/suggestions/{suggestion_id}", json={"status": next_status})

    assert response.status_code == 422


def test_suggestion_review_rechecks_that_target_segment_still_exists(suggestion_store):
    client, change_row = suggestion_store
    created = client.post("/api/knowledge/suggestions/draft", json=_suggestion_payload())
    assert created.status_code == 200
    change_row(NormalizedRouteVersion, 11, route_json="[]")

    response = client.patch(f"/api/knowledge/suggestions/{created.json()['id']}", json={"status": "pending_review"})

    assert response.status_code == 404


def test_create_suggestion_rejects_evidence_from_other_scope(tmp_path):
    client, engine = _client(tmp_path)
    try:
        response = client.post(
            "/api/knowledge/suggestions/draft",
            json={
                "project_id": 1,
                "route_version_id": 11,
                "segment_id": "op-40",
                "suggestion_text": "不应绑定不存在的证据。",
                "evidence_ids": [999],
            },
        )
        assert response.status_code == 422
        assert "证据" in str(response.json()["detail"])
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def test_list_filters_suggestions_and_patch_updates_status(tmp_path):
    client, engine = _client(tmp_path)
    try:
        created = client.post(
            "/api/knowledge/suggestions/draft",
            json={
                "project_id": 1,
                "route_version_id": 11,
                "segment_id": "op-40",
                "suggestion_text": "淬火后硬度不低于 56 HRC。",
                "evidence_ids": [101],
            },
        )
        suggestion_id = created.json()["id"]

        listed = client.get(
            "/api/knowledge/suggestions",
            params={"project_id": 1, "route_version_id": 11, "segment_id": "op-40", "status": "draft"},
        )
        assert listed.status_code == 200
        assert [item["id"] for item in listed.json()] == [suggestion_id]

        updated = client.patch(
            f"/api/knowledge/suggestions/{suggestion_id}",
            json={"status": "pending_review", "updated_by": "审核员"},
        )
        assert updated.status_code == 200
        assert updated.json()["status"] == "pending_review"
        assert updated.json()["updated_by"] == "审核员"

        blocked = client.patch(
            f"/api/knowledge/suggestions/{suggestion_id}",
            json={"suggestion_text": "审核后不应静默修改。", "updated_by": "编辑员"},
        )
        assert blocked.status_code == 409

        confirmed = client.patch(
            f"/api/knowledge/suggestions/{suggestion_id}",
            json={"status": "confirmed", "updated_by": "审核员"},
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["status"] == "confirmed"

        transition_blocked = client.patch(
            f"/api/knowledge/suggestions/{suggestion_id}",
            json={"status": "rejected", "updated_by": "审核员"},
        )
        assert transition_blocked.status_code == 409
    finally:
        client.close()
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())
