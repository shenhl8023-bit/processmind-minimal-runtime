import asyncio
import time

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.database import Base, async_session, configure_sqlite_engine, init_db
from app.main import app
from app.models.models import NormalizedRouteSegmentRuleReview, NormalizedRouteVersion, Project
from app.services import rule_preprocessing
from app.services.db_schema_maintenance import ensure_project_schema
from app.services.project_workflow_lifecycle import invalidate_project_workflow
from app.services.rule_packages import condition_reviews
from app.services.rule_packages.condition_contracts import RuleConditionCandidate, RulePreprocessStartRequest


def _seed_project_and_route(project_id: int, route_id: int) -> None:
    async def run():
        await init_db()
        async with async_session() as db:
            db.add(Project(id=project_id, name=f"预处理测试 {project_id}", workflow_revision=0))
            db.add(
                NormalizedRouteVersion(
                    id=route_id,
                    project_id=project_id,
                    version=1,
                    segment_count=1,
                    route_json='[{"id":"process_grind_outer","normalized_step_name":"磨外圆"}]',
                )
            )
            await db.commit()

    asyncio.run(run())


def _seed_project_and_route_with_export_process_id(project_id: int, route_id: int) -> None:
    async def run():
        await init_db()
        async with async_session() as db:
            db.add(Project(id=project_id, name=f"导出工序 ID 预处理测试 {project_id}", workflow_revision=0))
            db.add(
                NormalizedRouteVersion(
                    id=route_id,
                    project_id=project_id,
                    version=1,
                    segment_count=1,
                    route_json='[{"id":"segment-quench_core_merge","export_process_id":"process_quench","normalized_step_name":"淬火"}]',
                )
            )
            await db.commit()

    asyncio.run(run())


def test_rule_preprocess_task_persists_progress_and_is_idempotent():
    project_id = 7101
    route_id = 8101
    _seed_project_and_route(project_id, route_id)
    body = {
        "project_id": project_id,
        "route_id": route_id,
        "expected_workflow_revision": 0,
        "items": [{
            "segment_id": "process_grind_outer",
            "process_id": "process_grind_outer",
            "process_name": "磨外圆",
            "source_text": "当外圆尺寸精度达到 IT8 时，纳入磨外圆工序",
        }],
        "processes": [
            {"process_id": "process_grind_outer", "display_name": "磨外圆", "main": False},
        ],
    }

    with TestClient(app) as client:
        first = client.post("/api/extract/finalized-rule-packages/preprocess/start", json=body)
        assert first.status_code == 200
        assert first.json()["task_status"] in {"queued", "running"}

        second = client.post("/api/extract/finalized-rule-packages/preprocess/start", json=body)
        assert second.status_code == 200
        assert second.json()["route_id"] == route_id

        final = None
        for _ in range(30):
            response = client.get(
                "/api/extract/finalized-rule-packages/preprocess/status",
                params={"project_id": project_id, "route_id": route_id},
            )
            assert response.status_code == 200
            final = response.json()
            if final["task_status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert final is not None
        assert final["task_status"] == "completed"
        assert final["total_count"] == 1
        assert final["completed_count"] == 1
        assert final["failed_count"] == 0

        async def read_review():
            from sqlalchemy import select
            from app.models.models import NormalizedRouteSegmentRuleReview

            async with async_session() as db:
                return (
                    await db.execute(
                        select(NormalizedRouteSegmentRuleReview).where(
                            NormalizedRouteSegmentRuleReview.project_id == project_id,
                            NormalizedRouteSegmentRuleReview.route_version_id == route_id,
                            NormalizedRouteSegmentRuleReview.segment_id == "process_grind_outer",
                        )
                    )
                ).scalar_one()

        review = asyncio.run(read_review())
        assert review.condition_status == "pending_confirmation"
        assert review.condition_candidate_json


def test_rule_preprocess_accepts_export_process_ids_for_saved_route_segments():
    project_id = 7102
    route_id = 8102
    _seed_project_and_route_with_export_process_id(project_id, route_id)
    body = {
        "project_id": project_id,
        "route_id": route_id,
        "expected_workflow_revision": 0,
        "items": [{
            "segment_id": "segment-quench_core_merge",
            "process_id": "process_quench",
            "process_name": "淬火",
            "source_text": "当外圆尺寸精度达到 IT8 时，纳入淬火工序",
        }],
        "processes": [
            {"process_id": "process_quench", "display_name": "淬火", "main": False},
        ],
    }

    with TestClient(app) as client:
        response = client.post("/api/extract/finalized-rule-packages/preprocess/start", json=body)
        assert response.status_code == 200

        final = None
        for _ in range(30):
            status = client.get(
                "/api/extract/finalized-rule-packages/preprocess/status",
                params={"project_id": project_id, "route_id": route_id},
            )
            assert status.status_code == 200
            final = status.json()
            if final["task_status"] in {"completed", "failed"}:
                break
            time.sleep(0.05)

        assert final is not None
        assert final["task_status"] == "completed"
        assert final["completed_count"] == 1
        assert final["failed_count"] == 0

@pytest.fixture
def preprocessing_sessions(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'preprocess-reset.db'}")
    configure_sqlite_engine(engine)
    sessions = async_sessionmaker(engine, expire_on_commit=False)

    async def setup():
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            await ensure_project_schema(conn)
        async with sessions() as db:
            db.add(Project(id=1, name="隔离预处理重置", workflow_revision=0))
            db.add(NormalizedRouteVersion(id=1, project_id=1, version=1,
                route_json='[{"id":"mark","normalized_step_name":"标记"}]'))
            await db.commit()

    async def parser_context():
        return "isolated-test-parser", {}

    asyncio.run(setup())
    monkeypatch.setattr(rule_preprocessing, "async_session", sessions)
    monkeypatch.setattr(rule_preprocessing, "_active_condition_parser_context", parser_context)
    monkeypatch.setattr(condition_reviews, "_active_condition_parser_context", parser_context)
    try:
        yield sessions
    finally:
        rule_preprocessing.RULE_PREPROCESS_JOBS.pop((1, 1), None)
        rule_preprocessing.RULE_PREPROCESS_LOCKS.pop((1, 1), None)
        asyncio.run(engine.dispose())


def _preprocess_request(revision=0, source="标记固定安排。"):
    return RulePreprocessStartRequest(project_id=1, route_id=1,
        expected_workflow_revision=revision,
        items=[{"segment_id": "mark", "process_id": "mark", "process_name": "标记", "source_text": source}],
        processes=[{"process_id": "mark", "display_name": "标记"}])


async def _start_preprocessing(sessions, request):
    async with sessions() as db:
        return await rule_preprocessing.start_rule_preprocessing(request, db)


async def _reset_preprocessing(sessions, from_step):
    async with sessions() as db:
        project = await db.get(Project, 1)
        await invalidate_project_workflow(db, project, from_step=from_step, expected_workflow_revision=0)
        await db.commit()


def _paused_parser(monkeypatch):
    entered = [asyncio.Event(), asyncio.Event()]
    release = [asyncio.Event(), asyncio.Event()]
    calls = []

    async def parse(source, process_id, *args, **kwargs):
        index = len(calls)
        calls.append(source)
        entered[index].set()
        await release[index].wait()
        return RuleConditionCandidate(kind="process_configuration",
            configuration={"process_id": process_id, "occurrence": "always", "relations": []},
            preview=source, evidence=source), 1.0, []

    monkeypatch.setattr(condition_reviews, "parse_rule_condition", parse)
    return entered, release


async def _stop_preprocessing(tasks):
    for task in tasks:
        if not task.done():
            task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)


@pytest.mark.parametrize("from_step", [3, 4])
def test_reset_starts_new_revision_while_old_parse_is_active(preprocessing_sessions, monkeypatch, from_step):
    async def scenario():
        entered, release = _paused_parser(monkeypatch)
        tasks = []
        try:
            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            old = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(old)
            await asyncio.wait_for(entered[0].wait(), 2)
            await _reset_preprocessing(preprocessing_sessions, from_step)

            response = await _start_preprocessing(preprocessing_sessions, _preprocess_request(1))
            replacement = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(replacement)
            assert response.workflow_revision == 1
            assert replacement is not old
            await asyncio.wait_for(entered[1].wait(), 2)
            assert old.done()
            assert rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)] is replacement

            release[1].set()
            await asyncio.wait_for(replacement, 3)
            async with preprocessing_sessions() as db:
                state = await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)
                review = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
                assert state.workflow_revision == 1
                assert (state.task_status, state.completed_count, state.failed_count) == ("completed", 1, 0)
                assert review.condition_status == "pending_confirmation"
                assert review.condition_candidate_json is not None
            assert (1, 1) not in rule_preprocessing.RULE_PREPROCESS_JOBS
        finally:
            await _stop_preprocessing(tasks)

    asyncio.run(scenario())


@pytest.mark.parametrize("from_step", [3, 4])
def test_reset_prevents_old_worker_from_writing_task_status(preprocessing_sessions, monkeypatch, from_step):
    async def scenario():
        entered, release = _paused_parser(monkeypatch)
        tasks = []
        try:
            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            old = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(old)
            await asyncio.wait_for(entered[0].wait(), 2)
            await _reset_preprocessing(preprocessing_sessions, from_step)
            async with preprocessing_sessions() as db:
                before = await rule_preprocessing._load_state(db, 1, 1)

            release[0].set()
            await asyncio.wait_for(old, 3)
            async with preprocessing_sessions() as db:
                assert await rule_preprocessing._load_state(db, 1, 1) == before
                review = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one_or_none()
                if from_step == 3:
                    assert review is None
                else:
                    assert review.condition_status == "draft"
                    assert review.condition_candidate_json is None
        finally:
            await _stop_preprocessing(tasks)

    asyncio.run(scenario())


def test_changed_input_replaces_active_task_and_identical_input_reuses_it(preprocessing_sessions, monkeypatch):
    async def scenario():
        entered, release = _paused_parser(monkeypatch)
        tasks = []
        try:
            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            old = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(old)
            await asyncio.wait_for(entered[0].wait(), 2)

            changed = _preprocess_request(source="标记改为新规则。")
            response = await _start_preprocessing(preprocessing_sessions, changed)
            replacement = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(replacement)
            assert replacement is not old
            await asyncio.wait_for(entered[1].wait(), 2)
            repeated = await _start_preprocessing(preprocessing_sessions, changed)
            assert repeated.input_hash == response.input_hash
            assert rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)] is replacement

            release[1].set()
            await asyncio.wait_for(replacement, 3)
            async with preprocessing_sessions() as db:
                review = (await db.execute(select(NormalizedRouteSegmentRuleReview))).scalar_one()
                assert review.condition_source_text == "标记改为新规则。"
                assert review.condition_status == "pending_confirmation"
                state = await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)
                assert (state.completed_count, state.failed_count) == (1, 0)
        finally:
            await _stop_preprocessing(tasks)

    asyncio.run(scenario())


def test_old_worker_cannot_overwrite_or_unregister_a_replacement(preprocessing_sessions, monkeypatch):
    async def scenario():
        entered, release = _paused_parser(monkeypatch)
        tasks = []
        try:
            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            old = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(old)
            await asyncio.wait_for(entered[0].wait(), 2)
            await _reset_preprocessing(preprocessing_sessions, 4)
            # Hold a newer queued owner while the superseded parser returns.
            replacement = asyncio.create_task(asyncio.Event().wait())
            tasks.append(replacement)
            rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)] = replacement
            async with preprocessing_sessions() as db:
                before = await rule_preprocessing._save_state(db, 1, 1,
                    workflow_revision=1, task_status="queued", input_hash="new-input",
                    completed_count=0, failed_count=0, started_at="new-owner")
                await db.commit()

            release[0].set()
            await asyncio.wait_for(old, 3)
            assert rule_preprocessing.RULE_PREPROCESS_JOBS.get((1, 1)) is replacement
            async with preprocessing_sessions() as db:
                assert await rule_preprocessing._load_state(db, 1, 1) == before
        finally:
            await _stop_preprocessing(tasks)

    asyncio.run(scenario())


def test_interrupted_queued_task_is_failed_and_can_restart(preprocessing_sessions, monkeypatch):
    async def scenario():
        entered, release = _paused_parser(monkeypatch)
        tasks = []
        try:
            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            old = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(old)
            await asyncio.wait_for(entered[0].wait(), 2)
            await _stop_preprocessing([old])
            async with preprocessing_sessions() as db:
                interrupted = await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)
                assert interrupted.workflow_revision == 0
                assert interrupted.task_status == "failed"

            await _start_preprocessing(preprocessing_sessions, _preprocess_request())
            replacement = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
            tasks.append(replacement)
            await asyncio.wait_for(entered[1].wait(), 2)
            release[1].set()
            await asyncio.wait_for(replacement, 3)
            async with preprocessing_sessions() as db:
                state = await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)
                assert (state.task_status, state.completed_count, state.failed_count) == ("completed", 1, 0)
        finally:
            await _stop_preprocessing(tasks)

    asyncio.run(scenario())


def test_status_does_not_mark_committed_start_failed_before_owner_registration(preprocessing_sessions, monkeypatch):
    async def scenario():
        entered, release_parser = _paused_parser(monkeypatch)
        committed = asyncio.Event()
        register_owner = asyncio.Event()
        status_entered = asyncio.Event()
        tasks = []
        async with preprocessing_sessions() as starting_db:
            real_commit = starting_db.commit

            async def pause_after_commit():
                await real_commit()
                committed.set()
                await register_owner.wait()

            monkeypatch.setattr(starting_db, "commit", pause_after_commit)
            start = asyncio.create_task(rule_preprocessing.start_rule_preprocessing(_preprocess_request(), starting_db))
            tasks.append(start)
            try:
                await asyncio.wait_for(committed.wait(), 2)

                async def read_status():
                    status_entered.set()
                    async with preprocessing_sessions() as db:
                        return await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)

                reading = asyncio.create_task(read_status())
                tasks.append(reading)
                await asyncio.wait_for(status_entered.wait(), 2)
                # Drain a potential premature status response without sleeps.
                await asyncio.wait({reading}, timeout=0.1)
                register_owner.set()
                response = await asyncio.wait_for(start, 2)
                owner = rule_preprocessing.RULE_PREPROCESS_JOBS[(1, 1)]
                tasks.append(owner)
                await asyncio.wait_for(entered[0].wait(), 2)
                status = await asyncio.wait_for(reading, 2)
                assert response.task_status == "running"
                assert status.task_status in {"queued", "running"}
                assert not owner.done()
                release_parser[0].set()
                await asyncio.wait_for(owner, 3)
                async with preprocessing_sessions() as db:
                    final = await rule_preprocessing.get_rule_preprocessing_status(1, 1, db)
                    assert (final.task_status, final.completed_count, final.failed_count) == ("completed", 1, 0)
            finally:
                register_owner.set()
                await _stop_preprocessing(tasks)

    asyncio.run(scenario())
