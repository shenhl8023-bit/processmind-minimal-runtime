import asyncio
import time

from fastapi.testclient import TestClient

from app.database import async_session, init_db
from app.main import app
from app.models.models import NormalizedRouteVersion, Project


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
