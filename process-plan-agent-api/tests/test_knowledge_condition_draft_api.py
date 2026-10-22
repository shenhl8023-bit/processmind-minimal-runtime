import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base, get_db
from app.main import app
from app.models.models import (
    KnowledgeEvidenceSnapshot,
    KnowledgeRuleSuggestion,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Project,
)
from app.services.rule_packages.condition_reviews import condition_source_hash


SOURCE_TEXT = "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序"
CANDIDATE = {
    "kind": "condition",
    "when": {"field": "precision.outer_diameter_it", "op": "lte", "value": 8},
    "then": {"include_process_ids": ["process_grind_outer"], "exclude_process_ids": []},
    "field_definitions": [],
    "preview": "外圆尺寸精度 IT 小于等于 8",
    "evidence": SOURCE_TEXT,
}
PROCESSES = [{"process_id": "process_grind_outer", "display_name": "磨外圆"}]
DRAFT_URL = "/api/extract/finalized-rule-packages/rule-conditions/draft"


@pytest.fixture
def knowledge_condition_client(tmp_path):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'knowledge-condition.db'}")
    factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as connection:
            await connection.run_sync(Base.metadata.create_all)
        async with factory() as session:
            session.add_all([
                Project(id=1, name="知识规则测试", status="ROUTE_SET_READY", workflow_revision=3),
                Project(id=2, name="其他项目", workflow_revision=0),
                NormalizedRouteVersion(
                    id=11, project_id=1, version=1,
                    route_json='[{"id":"process_grind_outer"},{"id":"process_inspect"}]',
                ),
                NormalizedRouteVersion(
                    id=12, project_id=1, version=2,
                    route_json='[{"id":"process_grind_outer"}]',
                ),
                NormalizedRouteVersion(
                    id=21, project_id=2, version=1,
                    route_json='[{"id":"process_grind_outer"}]',
                ),
                KnowledgeEvidenceSnapshot(
                    id=101, project_id=1, route_version_id=11, segment_id="process_grind_outer",
                    query="磨削精度", item_id="chunk-1", content=SOURCE_TEXT, snapshot_hash="e" * 64,
                ),
                KnowledgeEvidenceSnapshot(
                    id=102, project_id=2, route_version_id=21, segment_id="process_grind_outer",
                    query="其他资料", item_id="chunk-2", content=SOURCE_TEXT, snapshot_hash="f" * 64,
                ),
                KnowledgeRuleSuggestion(
                    id=201, project_id=1, route_version_id=11, segment_id="process_grind_outer",
                    title="磨削条件", suggestion_text=SOURCE_TEXT, evidence_ids_json="[101]",
                    status="confirmed",
                ),
                NormalizedRouteSegmentRuleReview(
                    project_id=1, route_version_id=11, segment_id="process_grind_outer",
                    condition_source_text=SOURCE_TEXT, condition_source_hash=condition_source_hash(SOURCE_TEXT),
                    condition_status="confirmed", condition_candidate_json=json.dumps(CANDIDATE),
                    condition_confirmed_json=json.dumps(CANDIDATE), condition_confirmed_by="旧审核员",
                    condition_confirmed_at=datetime(2026, 10, 1, tzinfo=timezone.utc),
                ),
            ])
            await session.commit()

    asyncio.run(setup())

    async def override_get_db():
        async with factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)

    def change_suggestion(**changes):
        async def update():
            async with factory() as session:
                row = await session.get(KnowledgeRuleSuggestion, 201)
                for key, value in changes.items():
                    setattr(row, key, value)
                await session.commit()
        asyncio.run(update())

    yield client, change_suggestion
    client.close()
    app.dependency_overrides.pop(get_db, None)
    asyncio.run(engine.dispose())


def _draft_payload(**changes):
    return {
        "project_id": 1,
        "route_id": 11,
        "segment_id": "process_grind_outer",
        "expected_workflow_revision": 3,
        "source_text": SOURCE_TEXT,
        "knowledge_suggestion_id": 201,
        **changes,
    }


def test_applying_confirmed_knowledge_requires_reparse_even_for_unchanged_text(knowledge_condition_client):
    client, _ = knowledge_condition_client
    response = client.post(DRAFT_URL, json=_draft_payload())

    assert response.status_code == 200
    review = response.json()["review"]
    assert review["status"] == "draft"
    assert review["candidate"] is None
    assert review["confirmed"] is None
    assert review["confirmed_by"] == ""

    premature_confirmation = client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/confirm",
        json={
            "project_id": 1, "route_id": 11, "segment_id": "process_grind_outer",
            "expected_workflow_revision": 3, "source_text": SOURCE_TEXT,
            "source_hash": review["source_hash"], "candidate": CANDIDATE, "processes": PROCESSES,
        },
    )
    assert premature_confirmation.status_code == 409

    parsed = client.post(
        "/api/extract/finalized-rule-packages/rule-conditions/parse",
        json={
            "project_id": 1, "route_id": 11, "segment_id": "process_grind_outer",
            "expected_workflow_revision": 3, "source_text": SOURCE_TEXT,
            "process_id": "process_grind_outer", "process_name": "磨外圆", "processes": PROCESSES,
        },
    )
    assert parsed.status_code == 200
    assert parsed.json()["review"]["status"] == "pending_confirmation"
    assert parsed.json()["review"]["confirmed"] is None


def test_legacy_domain_package_suggestion_cannot_enter_condition_draft(knowledge_condition_client):
    client, change_suggestion = knowledge_condition_client
    change_suggestion(domain_package_ref_json='{"package_id":"legacy","version":1}')

    response = client.post(DRAFT_URL, json=_draft_payload())

    assert response.status_code == 410


@pytest.mark.parametrize("status", ["draft", "pending_review", "rejected", "stale"])
def test_unconfirmed_knowledge_cannot_be_applied_to_condition(knowledge_condition_client, status):
    client, change_suggestion = knowledge_condition_client
    change_suggestion(status=status)

    response = client.post(DRAFT_URL, json=_draft_payload())

    assert response.status_code == 409


@pytest.mark.parametrize("changes", [
    {"project_id": 2, "route_id": 21, "expected_workflow_revision": 0},
    {"route_id": 12},
    {"segment_id": "process_inspect"},
])
def test_knowledge_application_rejects_different_project_route_or_segment(knowledge_condition_client, changes):
    client, _ = knowledge_condition_client

    response = client.post(DRAFT_URL, json=_draft_payload(**changes))

    assert response.status_code == 409


def test_knowledge_application_rejects_source_text_not_reviewed_with_the_suggestion(knowledge_condition_client):
    client, _ = knowledge_condition_client

    response = client.post(DRAFT_URL, json=_draft_payload(source_text="未经审核的替换条件"))

    assert response.status_code == 409


@pytest.mark.parametrize("evidence_ids_json", ["[]", "[999]", "[102]"])
def test_knowledge_application_requires_existing_evidence_in_the_same_scope(knowledge_condition_client, evidence_ids_json):
    client, change_suggestion = knowledge_condition_client
    change_suggestion(evidence_ids_json=evidence_ids_json)

    response = client.post(DRAFT_URL, json=_draft_payload())

    assert response.status_code == 422


def test_knowledge_application_rejects_stale_workflow_revision(knowledge_condition_client):
    client, _ = knowledge_condition_client

    response = client.post(DRAFT_URL, json=_draft_payload(expected_workflow_revision=2))

    assert response.status_code == 409
    assert response.json()["detail"]["workflow_revision"] == 3


def test_knowledge_application_compares_trimmed_reviewed_text(knowledge_condition_client):
    client, change_suggestion = knowledge_condition_client
    change_suggestion(suggestion_text=f"  {SOURCE_TEXT}\n")

    response = client.post(DRAFT_URL, json=_draft_payload(source_text=f"\n{SOURCE_TEXT}  "))

    assert response.status_code == 200
    assert response.json()["review"]["source_text"] == SOURCE_TEXT


def test_knowledge_application_rejects_missing_suggestion(knowledge_condition_client):
    client, _ = knowledge_condition_client

    response = client.post(DRAFT_URL, json=_draft_payload(knowledge_suggestion_id=999))

    assert response.status_code == 404


@pytest.mark.parametrize("endpoint,fields", [
    ("parse", {"process_id": "process_grind_outer", "process_name": "磨外圆", "processes": PROCESSES}),
    ("confirm", {"source_hash": condition_source_hash(SOURCE_TEXT), "candidate": CANDIDATE, "processes": PROCESSES}),
    ("manual", {"process_id": "process_grind_outer", "candidate": CANDIDATE, "processes": PROCESSES}),
])
def test_only_draft_endpoint_accepts_knowledge_suggestion_identity(knowledge_condition_client, endpoint, fields):
    client, _ = knowledge_condition_client

    response = client.post(
        f"/api/extract/finalized-rule-packages/rule-conditions/{endpoint}",
        json={**_draft_payload(), **fields},
    )

    assert response.status_code == 422
