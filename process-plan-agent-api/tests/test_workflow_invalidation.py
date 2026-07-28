import asyncio
import json
from datetime import datetime, timezone

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.database import Base
from app.database import get_db
from app.main import app
from app.models.models import (
    Factor,
    FinalizedRulePackage,
    GeneratedRoute,
    NormalizedRouteSegmentFactorReview,
    NormalizedRouteSegmentRuleReview,
    NormalizedRouteVersion,
    Operation,
    Project,
    RouteMergeSnapshot,
)
from app.services.project_workflow_lifecycle import invalidate_project_workflow
from app.services.extraction_pipeline import queue_extraction_job
from app.services.extraction_tasks import EXTRACTION_JOBS, EXTRACTION_RUNNING, EXTRACTION_TASKS
from app.services.rule_packages.confirmation_validation import require_confirmed_user_rule_sources
from app.services.rule_packages.contracts import RulePackageV2


@pytest.fixture
def workflow_db(tmp_path):
    database_path = tmp_path / "workflow-invalidation.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA foreign_keys = ON"))

    asyncio.run(setup())
    try:
        yield session_factory
    finally:
        asyncio.run(engine.dispose())


@pytest.fixture
def workflow_client(tmp_path):
    database_path = tmp_path / "workflow-api.db"
    engine = create_async_engine(f"sqlite+aiosqlite:///{database_path}")
    session_factory = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await conn.execute(text("PRAGMA foreign_keys = ON"))
        async with session_factory() as db:
            await _seed_project(db, 9)

    asyncio.run(setup())

    async def override_get_db():
        async with session_factory() as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    client = TestClient(app)
    try:
        yield client
    finally:
        app.dependency_overrides.pop(get_db, None)
        asyncio.run(engine.dispose())


def _candidate(source: str = "system", target_process_id: str = "process_prepare") -> str:
    return json.dumps({
        "kind": "condition",
        "when": {"field": "special.requirements", "op": "contains", "value": "标印"},
        "then": {"include_process_ids": [target_process_id], "exclude_process_ids": []},
        "field_definitions": [],
        "preview": "存在标印要求",
        "evidence": source,
    }, ensure_ascii=False)


async def _seed_project(db: AsyncSession, project_id: int) -> Project:
    project = Project(
        id=project_id,
        name=f"工作流失效-{project_id}",
        status="GENERATED",
        workflow_revision=7,
    )
    route = NormalizedRouteVersion(
        id=project_id * 10,
        project_id=project_id,
        version=1,
        route_json=json.dumps([{"id": "seg-1", "normalized_step_name": "标记"}], ensure_ascii=False),
    )
    operation = Operation(id=project_id * 100, project_id=project_id, name="标记", sequence=1)
    db.add_all([project, route, operation])
    await db.commit()
    db.add_all([
        Factor(operation_id=operation.id, name="是否标印"),
        RouteMergeSnapshot(project_id=project_id, source_signature="sig", normalized_superset_route_json="[]"),
        NormalizedRouteSegmentFactorReview(
            project_id=project_id,
            route_version_id=route.id,
            segment_id="seg-1",
            factor_name="是否标印",
        ),
        NormalizedRouteSegmentRuleReview(
            project_id=project_id,
            route_version_id=route.id,
            segment_id="seg-1",
            decision="accepted",
            note="第三步说明",
            summary_json='["存在标印要求"]',
            question_trail_json='[{"nodeId":"rule_reason_root","value":"requirement","label":"特殊要求"}]',
            condition_source_text="当有标印要求时，纳入标记工序",
            condition_source_hash="source-hash",
            condition_status="confirmed",
            condition_candidate_json=_candidate(),
            condition_confirmed_json=_candidate(),
            condition_confidence=0.92,
            condition_issues_json="[]",
            condition_parser_version="parser-v1",
            condition_confirmed_by="审核员",
            condition_confirmed_at=datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc),
        ),
        FinalizedRulePackage(
            project_id=project_id,
            route_version_id=route.id,
            version=1,
            package_name="workflow-rules",
            status="published",
        ),
        GeneratedRoute(project_id=project_id, input_factors="{}", result_json="{}"),
    ])
    await db.commit()
    return project


def test_step_two_invalidation_unlinks_packages_before_deleting_route_versions(workflow_db):
    async def run():
        async with workflow_db() as db:
            project = await _seed_project(db, 1)
            result = await invalidate_project_workflow(db, project, from_step=2)
            await db.commit()

            package = (await db.execute(select(FinalizedRulePackage))).scalar_one()
            assert package.status == "archived"
            assert package.route_version_id is None
            assert not (await db.execute(select(NormalizedRouteVersion))).scalars().all()
            assert not (await db.execute(select(Operation))).scalars().all()
            assert not (await db.execute(select(RouteMergeSnapshot))).scalars().all()
            assert not (await db.execute(select(GeneratedRoute))).scalars().all()
            assert project.workflow_revision == 8
            assert result.archived_rule_package_versions == [1]

    asyncio.run(run())


def test_step_three_invalidation_preserves_route_but_clears_answers_and_downstream(workflow_db):
    async def run():
        async with workflow_db() as db:
            project = await _seed_project(db, 2)
            result = await invalidate_project_workflow(db, project, from_step=3)
            await db.commit()

            assert len((await db.execute(select(NormalizedRouteVersion))).scalars().all()) == 1
            assert len((await db.execute(select(Operation))).scalars().all()) == 1
            assert len((await db.execute(select(RouteMergeSnapshot))).scalars().all()) == 1
            assert not (await db.execute(select(NormalizedRouteSegmentFactorReview))).scalars().all()
            assert not (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalars().all()
            assert not (await db.execute(select(GeneratedRoute))).scalars().all()
            assert result.deleted_factor_reviews == 1
            assert result.deleted_rule_reviews == 1
            assert project.workflow_revision == 8

    asyncio.run(run())


def test_step_four_invalidation_preserves_source_and_manual_boolean_rules(workflow_db):
    async def run():
        async with workflow_db() as db:
            project = await _seed_project(db, 3)
            route_id = 30
            db.add(NormalizedRouteSegmentRuleReview(
                project_id=3,
                route_version_id=route_id,
                segment_id="seg-manual",
                decision="accepted",
                summary_json="[]",
                question_trail_json="[]",
                condition_source_text="当用户选择是否标记为是时，纳入标记工序",
                condition_source_hash="manual-hash",
                condition_status="confirmed",
                condition_candidate_json=_candidate("manual"),
                condition_confirmed_json=_candidate("manual"),
                condition_parser_version="manual",
                condition_confirmed_by="用户直接设定",
            ))
            await db.commit()

            result = await invalidate_project_workflow(db, project, from_step=4)
            await db.commit()

            rows = (
                await db.execute(
                    select(NormalizedRouteSegmentRuleReview)
                    .order_by(NormalizedRouteSegmentRuleReview.segment_id)
                )
            ).scalars().all()
            manual = next(row for row in rows if row.segment_id == "seg-manual")
            system = next(row for row in rows if row.segment_id == "seg-1")
            assert manual.condition_status == "confirmed"
            assert manual.condition_confirmed_json is not None
            assert system.note == "第三步说明"
            assert system.question_trail_json.startswith("[")
            assert system.condition_source_text == "当有标印要求时，纳入标记工序"
            assert system.condition_status == "draft"
            assert system.condition_candidate_json is None
            assert system.condition_confirmed_json is None
            assert system.condition_parser_version is None
            assert result.reset_condition_reviews == 1
            assert result.preserved_manual_condition_reviews == 1
            assert project.workflow_revision == 8

    asyncio.run(run())


def test_workflow_reset_endpoint_returns_new_revision_and_counts(workflow_client):
    response = workflow_client.post("/api/extract/workflow/reset", json={
        "project_id": 9,
        "from_step": 3,
        "expected_workflow_revision": 7,
    })

    assert response.status_code == 200
    body = response.json()
    assert body["workflow_revision"] == 8
    assert body["deleted_rule_reviews"] == 1
    assert body["archived_rule_package_versions"] == [1]


def test_saved_route_response_includes_current_workflow_revision(workflow_client):
    response = workflow_client.get(
        "/api/extract/saved-normalized-route",
        params={"project_id": 9},
    )

    assert response.status_code == 200
    assert response.json()["workflow_revision"] == 7


def test_workflow_reset_rejects_stale_revision(workflow_client):
    response = workflow_client.post("/api/extract/workflow/reset", json={
        "project_id": 9,
        "from_step": 4,
        "expected_workflow_revision": 6,
    })

    assert response.status_code == 409, response.text
    assert "页面已过期" in str(response.json()["detail"])


def test_concurrent_workflow_resets_allow_only_one_matching_revision(workflow_db):
    async def run():
        async with workflow_db() as seed_db:
            await _seed_project(seed_db, 11)

        ready = 0
        gate = asyncio.Event()
        gate_lock = asyncio.Lock()

        async def reset_once():
            nonlocal ready
            async with workflow_db() as db:
                project = await db.get(Project, 11)
                async with gate_lock:
                    ready += 1
                    if ready == 2:
                        gate.set()
                await gate.wait()
                try:
                    result = await invalidate_project_workflow(
                        db,
                        project,
                        from_step=4,
                        expected_workflow_revision=7,
                    )
                    await db.commit()
                    return result.workflow_revision
                except HTTPException as exc:
                    await db.rollback()
                    return exc.status_code

        outcomes = await asyncio.gather(reset_once(), reset_once())
        assert sorted(outcomes) == [8, 409]

        async with workflow_db() as db:
            project = await db.get(Project, 11)
            assert project.workflow_revision == 8

    asyncio.run(run())


def test_segment_review_save_rejects_stale_revision(workflow_client):
    response = workflow_client.post("/api/extract/segment-rule-reviews", json={
        "project_id": 9,
        "route_id": 90,
        "segment_id": "seg-1",
        "decision": "accepted",
        "summary_lines": ["旧页面答案"],
        "question_trail": [],
        "expected_workflow_revision": 6,
    })

    assert response.status_code == 409
    assert "页面已过期" in str(response.json()["detail"])


def test_rule_package_publish_rejects_user_rule_that_differs_from_confirmed_ast(
    workflow_client,
    rule_package_v2_payload,
):
    package = json.loads(json.dumps(rule_package_v2_payload))
    package["manifest"]["project_id"] = 9
    package["manifest"]["route_version_id"] = 90
    package["manifest"]["package_name"] = "forged_user_rule"
    package["manifest"]["scope"]["key"] = "9"
    forged = package["route_rules"]["rules"][0]
    forged.update({
        "rule_id": "user.seg-1",
        "source": "user_confirmed",
        "source_segment_id": "seg-1",
        "source_text": "当有标印要求时，纳入标记工序",
        "confirmed_by": "审核员",
        "confirmed_at": "2026-07-28T10:00:00+00:00",
    })

    response = workflow_client.post("/api/extract/finalized-rule-packages", json={
        "project_id": 9,
        "route_version_id": 90,
        "expected_workflow_revision": 7,
        "package_name": "forged_user_rule",
        "schema_version": "2.0",
        "manifest": package["manifest"],
        "input_schema": package["input_schema"],
        "route_catalog": package["route_catalog"],
        "route_rules": package["route_rules"],
        "test_cases": package["test_cases"],
        "rule_report_md": "# forged",
    })

    assert response.status_code == 409, response.text
    assert "数据库中的已确认规则不一致" in str(response.json()["detail"])


def test_confirmed_user_rule_source_is_accepted(workflow_db, rule_package_v2_payload):
    async def run():
        async with workflow_db() as db:
            await _seed_project(db, 12)
            payload = json.loads(json.dumps(rule_package_v2_payload))
            rule = payload["route_rules"]["rules"][0]
            rule.update({
                "rule_id": "user.seg-1",
                "source": "user_confirmed",
                "source_segment_id": "seg-1",
                "source_text": "当有标印要求时，纳入标记工序",
                "confirmed_by": "审核员",
                "confirmed_at": "2026-07-28T10:00:00+00:00",
                "when": {"field": "special.requirements", "op": "contains", "value": "标印"},
                "then": {
                    "include_process_ids": ["process_prepare"],
                    "exclude_process_ids": [],
                    "reason": "用户确认条件",
                },
            })
            package = RulePackageV2.model_validate(payload)

            await require_confirmed_user_rule_sources(
                package,
                project_id=12,
                route_version_id=120,
                db=db,
            )

    asyncio.run(run())


def test_confirmed_manual_boolean_true_and_false_rules_are_accepted(
    workflow_db,
    rule_package_v2_payload,
):
    async def run():
        field_key = "project_factor.manual_process_nitriding"
        source_text = "当用户选择是否需要渗氮为是时，纳入渗氮工序"
        candidate = {
            "kind": "condition",
            "when": {"field": field_key, "op": "eq", "value": True},
            "then": {
                "include_process_ids": ["process_nitriding"],
                "exclude_process_ids": [],
                "reason": "用户选择是",
            },
            "field_definitions": [{
                "key": field_key,
                "label": "是否需要渗氮",
                "category": "可选工序",
                "type": "boolean",
                "operators": ["eq", "neq"],
                "source": "用户直接设定",
                "allow_custom": False,
            }],
        }
        async with workflow_db() as db:
            await _seed_project(db, 13)
            db.add(NormalizedRouteSegmentRuleReview(
                project_id=13,
                route_version_id=130,
                segment_id="process_nitriding",
                decision="accepted",
                summary_json="[]",
                question_trail_json="[]",
                condition_source_text=source_text,
                condition_source_hash="manual-hash",
                condition_status="confirmed",
                condition_candidate_json=json.dumps(candidate, ensure_ascii=False),
                condition_confirmed_json=json.dumps(candidate, ensure_ascii=False),
                condition_parser_version="manual",
                condition_confirmed_by="用户直接设定",
                condition_confirmed_at=datetime(2026, 7, 28, 10, 0, tzinfo=timezone.utc),
            ))
            await db.commit()

            payload = json.loads(json.dumps(rule_package_v2_payload))
            payload["input_schema"]["fields"].append({
                "key": field_key,
                "label": "是否需要渗氮",
                "type": "boolean",
                "required": False,
                "source": "用户直接设定",
                "options": [],
                "allow_custom": False,
            })
            audit = {
                "source": "user_confirmed",
                "source_segment_id": "process_nitriding",
                "source_text": source_text,
                "confirmed_by": "用户直接设定",
                "confirmed_at": "2026-07-28T10:00:00+00:00",
                "priority": 2000,
            }
            payload["route_rules"]["rules"].extend([
                {
                    **audit,
                    "rule_id": "user.process_nitriding.manual.true",
                    "when": {"field": field_key, "op": "eq", "value": True},
                    "then": candidate["then"],
                },
                {
                    **audit,
                    "rule_id": "user.process_nitriding.manual.false",
                    "when": {"field": field_key, "op": "eq", "value": False},
                    "then": {
                        "include_process_ids": [],
                        "exclude_process_ids": ["process_nitriding"],
                        "reason": "用户选择否",
                    },
                },
            ])
            package = RulePackageV2.model_validate(payload)

            await require_confirmed_user_rule_sources(
                package,
                project_id=13,
                route_version_id=130,
                db=db,
            )

    asyncio.run(run())


def test_extraction_queue_invalidates_downstream_before_returning(workflow_db, monkeypatch):
    async def fake_llm_config():
        return {"key": "test-key"}

    monkeypatch.setattr("app.services.extraction_pipeline.get_llm_config", fake_llm_config)

    async def run():
        async with workflow_db() as db:
            project = await _seed_project(db, 4)
            payload = await queue_extraction_job(
                project_id=4,
                force_reextract=True,
                db=db,
                project=project,
                job_factory=lambda: object(),
            )

            package = (
                await db.execute(select(FinalizedRulePackage).where(FinalizedRulePackage.project_id == 4))
            ).scalar_one()
            assert package.status == "archived"
            assert package.route_version_id is None
            assert not (
                await db.execute(select(NormalizedRouteVersion).where(NormalizedRouteVersion.project_id == 4))
            ).scalars().all()
            assert payload["workflow_revision"] == 8

    try:
        asyncio.run(run())
    finally:
        EXTRACTION_JOBS.pop(4, None)
        EXTRACTION_RUNNING.discard(4)
        EXTRACTION_TASKS.pop(4, None)
